"""
Visao Integrada de Desempenho — cruza RH com ponto, campo, SST e treinamento.

Objetivo do dono: "melhorar o desempenho da minha equipe". Este service
quebra o silo do RH cruzando, por funcionario ativo:

- performance_reviews          -> ultima nota de avaliacao de desempenho
- evaluation_360_cycles        -> ultimo score 360 concluido
- operacional_avaliacoes_equipe-> media das notas do lider/supervisor (1-5)
- gp_clock_punches (30d)       -> batidas, dias com batida, conformidade geofence
- occurrences                  -> ocorrencias de campo (90d)
- training_enrollments         -> treinamentos concluidos
- sst_afastamentos             -> afastamentos (total + ativo)
- employees.data_admissao      -> tempo de casa

Toda tabela cruzada tem guard de existencia (information_schema): tabela
ausente vira bloco "indisponivel" — nunca numero fabricado. O score
composto e TRANSPARENTE: cada componente sai com valor bruto, score
normalizado 0-10, peso e disponibilidade; o composto e a media ponderada
APENAS dos componentes disponiveis (pesos renormalizados).
"""

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

JANELA_PONTO_DIAS = 30
JANELA_OCORRENCIAS_DIAS = 90

# Cobertura minima dos pesos para emitir score composto — evita ranquear
# alguem por um unico componente marginal (ex.: so treinamento, 10%).
COBERTURA_MINIMA = 0.30

# Pesos declarados do score composto (renormalizados sobre o que existir)
PESOS_COMPONENTES: dict[str, float] = {
    "avaliacao_desempenho": 0.30,
    "avaliacao_360": 0.15,
    "avaliacao_lider": 0.15,
    "conformidade_ponto": 0.15,
    "ocorrencias": 0.15,
    "treinamentos": 0.10,
}

# Tabelas cruzadas e o componente/indicador que dependem delas
TABELAS_FONTE: dict[str, str] = {
    "performance_reviews": "avaliacao_desempenho",
    "evaluation_360_cycles": "avaliacao_360",
    "operacional_avaliacoes_equipe": "avaliacao_lider",
    "gp_clock_punches": "conformidade_ponto",
    "occurrences": "ocorrencias",
    "training_enrollments": "treinamentos",
    "sst_afastamentos": "afastamentos",
}


class IntegratedPerformanceService:
    """Monta a visao integrada de desempenho por funcionario."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _tabelas_existentes(self) -> set[str]:
        rows = (
            await self.db.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = ANY(:nomes)"
                ),
                {"nomes": list(TABELAS_FONTE.keys())},
            )
        ).scalars()
        return set(rows)

    async def _map(self, sql: str, params: dict | None = None) -> dict[str, dict]:
        """Executa query com employee_id na 1a coluna e devolve dict por employee_id."""
        rows = (await self.db.execute(text(sql), params or {})).mappings().all()
        return {str(r["employee_id"]): dict(r) for r in rows if r["employee_id"] is not None}

    async def visao_integrada(self, employee_id: str | None = None) -> dict[str, Any]:
        """Visao integrada de todos os ativos (ou de um funcionario)."""
        existentes = await self._tabelas_existentes()
        fontes = {t: ("ok" if t in existentes else "ausente") for t in TABELAS_FONTE}
        avisos: list[str] = []

        filtro_emp = "AND e.id = :emp" if employee_id else ""
        params_emp = {"emp": employee_id} if employee_id else {}
        employees = (
            (
                await self.db.execute(
                    text(
                        "SELECT e.id::text AS employee_id, e.nome, e.cargo, e.posto_atual_nome, "
                        "e.data_admissao, "
                        "EXTRACT(YEAR FROM AGE(CURRENT_DATE, e.data_admissao)) * 12 + "
                        "EXTRACT(MONTH FROM AGE(CURRENT_DATE, e.data_admissao)) AS tempo_casa_meses "
                        f"FROM employees e WHERE e.status = 'ativo' {filtro_emp} ORDER BY e.nome"
                    ),
                    params_emp,
                )
            )
            .mappings()
            .all()
        )
        if employee_id and not employees:
            return {"erro": "Funcionario ativo nao encontrado", "employee_id": employee_id}

        # ------- coletas em lote (uma query por fonte, com guard) -------
        reviews: dict[str, dict] = {}
        if "performance_reviews" in existentes:
            reviews = await self._map(
                "SELECT DISTINCT ON (employee_id) employee_id::text AS employee_id, "
                "overall_score, review_period_end, status::text AS status "
                "FROM performance_reviews WHERE overall_score IS NOT NULL "
                "ORDER BY employee_id, completed_at DESC NULLS LAST, created_at DESC"
            )

        e360: dict[str, dict] = {}
        if "evaluation_360_cycles" in existentes:
            e360 = await self._map(
                "SELECT DISTINCT ON (employee_id) employee_id::text AS employee_id, "
                "final_score, status::text AS status, period_end "
                "FROM evaluation_360_cycles WHERE final_score IS NOT NULL "
                "ORDER BY employee_id, completed_at DESC NULLS LAST, created_at DESC"
            )

        lider: dict[str, dict] = {}
        if "operacional_avaliacoes_equipe" in existentes:
            lider = await self._map(
                "SELECT employee_id::text AS employee_id, "
                "ROUND(AVG(nota)::numeric, 2) AS media_nota, COUNT(*) AS avaliacoes "
                "FROM operacional_avaliacoes_equipe WHERE is_active IS NOT FALSE "
                "GROUP BY employee_id"
            )

        ponto: dict[str, dict] = {}
        if "gp_clock_punches" in existentes:
            ponto = await self._map(
                "SELECT employee_id::text AS employee_id, COUNT(*) AS batidas, "
                "COUNT(DISTINCT punch_timestamp::date) AS dias_com_batida, "
                "COUNT(*) FILTER (WHERE dentro_geofence IS NOT NULL) AS batidas_com_geofence, "
                "COUNT(*) FILTER (WHERE dentro_geofence IS TRUE) AS batidas_dentro_geofence "
                "FROM gp_clock_punches "
                f"WHERE punch_timestamp >= now() - INTERVAL '{JANELA_PONTO_DIAS} days' "
                "GROUP BY employee_id"
            )

        ocorr: dict[str, dict] = {}
        ocorrencias_fluxo_ativo = False
        if "occurrences" in existentes:
            total_occ = (await self.db.execute(text("SELECT count(*) FROM occurrences"))).scalar() or 0
            ocorrencias_fluxo_ativo = total_occ > 0
            if ocorrencias_fluxo_ativo:
                ocorr = await self._map(
                    "SELECT employee_id::text AS employee_id, COUNT(*) AS ocorrencias_90d "
                    "FROM occurrences WHERE is_active IS NOT FALSE "
                    f"AND occurred_at >= now() - INTERVAL '{JANELA_OCORRENCIAS_DIAS} days' "
                    "GROUP BY employee_id"
                )
            else:
                avisos.append(
                    "occurrences existe mas sem registros — fluxo de campo em implantacao; "
                    "componente 'ocorrencias' marcado como aguardando dado real."
                )

        trein: dict[str, dict] = {}
        if "training_enrollments" in existentes:
            trein = await self._map(
                "SELECT employee_id::text AS employee_id, COUNT(*) AS inscricoes, "
                "COUNT(*) FILTER (WHERE status = 'attended' OR attended_at IS NOT NULL) AS concluidos "
                "FROM training_enrollments GROUP BY employee_id"
            )

        afast: dict[str, dict] = {}
        if "sst_afastamentos" in existentes:
            afast = await self._map(
                "SELECT employee_id::text AS employee_id, COUNT(*) AS total, "
                "COUNT(*) FILTER (WHERE data_retorno IS NULL) AS ativos "
                "FROM sst_afastamentos GROUP BY employee_id"
            )

        if not lider and "operacional_avaliacoes_equipe" in existentes:
            avisos.append(
                "operacional_avaliacoes_equipe sem registros — avaliacoes do lider/supervisor "
                "ainda nao foram lancadas; componente marcado como aguardando dado real."
            )

        # ------- montagem por funcionario -------
        funcionarios = []
        for emp in employees:
            eid = emp["employee_id"]
            componentes: dict[str, dict[str, Any]] = {}

            # Avaliacao de desempenho (0-10)
            r = reviews.get(eid)
            componentes["avaliacao_desempenho"] = self._componente(
                disponivel="performance_reviews" in existentes and r is not None,
                score=float(r["overall_score"]) if r else None,
                valor_bruto=float(r["overall_score"]) if r else None,
                fonte="performance_reviews (ultima nota)",
                peso=PESOS_COMPONENTES["avaliacao_desempenho"],
                obs=None if r else self._obs_ausencia("performance_reviews", existentes, "sem avaliacao registrada"),
            )

            # Avaliacao 360 (0-10)
            s = e360.get(eid)
            componentes["avaliacao_360"] = self._componente(
                disponivel="evaluation_360_cycles" in existentes and s is not None,
                score=float(s["final_score"]) if s else None,
                valor_bruto=float(s["final_score"]) if s else None,
                fonte="evaluation_360_cycles (ultimo ciclo com score)",
                peso=PESOS_COMPONENTES["avaliacao_360"],
                obs=None if s else self._obs_ausencia("evaluation_360_cycles", existentes, "sem ciclo 360 concluido"),
            )

            # Avaliacao do lider (nota 1-5 -> x2 = 0-10)
            ld = lider.get(eid)
            componentes["avaliacao_lider"] = self._componente(
                disponivel="operacional_avaliacoes_equipe" in existentes and ld is not None,
                score=round(float(ld["media_nota"]) * 2, 2) if ld else None,
                valor_bruto={"media_nota_1a5": float(ld["media_nota"]), "avaliacoes": ld["avaliacoes"]} if ld else None,
                fonte="operacional_avaliacoes_equipe (media nota 1-5, normalizada x2)",
                peso=PESOS_COMPONENTES["avaliacao_lider"],
                obs=None
                if ld
                else self._obs_ausencia(
                    "operacional_avaliacoes_equipe", existentes, "aguardando avaliacoes do supervisor de campo"
                ),
            )

            # Conformidade de ponto (share de batidas dentro do geofence, 30d)
            p = ponto.get(eid)
            score_ponto = None
            obs_ponto = None
            if "gp_clock_punches" not in existentes:
                obs_ponto = "tabela gp_clock_punches ausente"
            elif not p:
                obs_ponto = f"sem batidas nos ultimos {JANELA_PONTO_DIAS} dias"
            elif not p["batidas_com_geofence"]:
                obs_ponto = "batidas sem dado de geofence — conformidade nao calculavel"
            else:
                score_ponto = round(p["batidas_dentro_geofence"] * 10.0 / p["batidas_com_geofence"], 2)
            componentes["conformidade_ponto"] = self._componente(
                disponivel=score_ponto is not None,
                score=score_ponto,
                valor_bruto=(
                    {
                        "batidas_30d": p["batidas"],
                        "dias_com_batida": p["dias_com_batida"],
                        "dentro_geofence": p["batidas_dentro_geofence"],
                        "com_geofence": p["batidas_com_geofence"],
                    }
                    if p
                    else None
                ),
                fonte=f"gp_clock_punches ({JANELA_PONTO_DIAS}d, % batidas dentro do geofence)",
                peso=PESOS_COMPONENTES["conformidade_ponto"],
                obs=obs_ponto,
            )

            # Ocorrencias de campo (90d): 10 - 2 por ocorrencia, piso 0
            oc = ocorr.get(eid)
            if not ocorrencias_fluxo_ativo:
                componentes["ocorrencias"] = self._componente(
                    disponivel=False,
                    score=None,
                    valor_bruto=None,
                    fonte="occurrences (90d)",
                    peso=PESOS_COMPONENTES["ocorrencias"],
                    obs="fluxo de ocorrencias de campo em implantacao — aguardando dado real",
                )
            else:
                qtd = int(oc["ocorrencias_90d"]) if oc else 0
                componentes["ocorrencias"] = self._componente(
                    disponivel=True,
                    score=max(0.0, round(10.0 - 2.0 * qtd, 2)),
                    valor_bruto={"ocorrencias_90d": qtd},
                    fonte="occurrences (90d; 10 - 2 por ocorrencia, piso 0)",
                    peso=PESOS_COMPONENTES["ocorrencias"],
                    obs=None,
                )

            # Treinamentos: % de inscricoes concluidas
            t = trein.get(eid)
            componentes["treinamentos"] = self._componente(
                disponivel="training_enrollments" in existentes and t is not None and t["inscricoes"] > 0,
                score=round(t["concluidos"] * 10.0 / t["inscricoes"], 2) if t and t["inscricoes"] else None,
                valor_bruto={"concluidos": t["concluidos"], "inscricoes": t["inscricoes"]} if t else None,
                fonte="training_enrollments (% inscricoes concluidas)",
                peso=PESOS_COMPONENTES["treinamentos"],
                obs=None
                if t
                else self._obs_ausencia("training_enrollments", existentes, "sem inscricoes em treinamento"),
            )

            # Score composto transparente (so componentes disponiveis)
            disponiveis = {k: c for k, c in componentes.items() if c["disponivel"] and c["score"] is not None}
            peso_total = sum(c["peso"] for c in disponiveis.values())
            score_composto = None
            score_obs = None
            if peso_total >= COBERTURA_MINIMA:
                score_composto = round(
                    sum(c["score"] * c["peso"] for c in disponiveis.values()) / peso_total, 2
                )
            elif peso_total > 0:
                score_obs = (
                    f"cobertura insuficiente ({peso_total:.0%} < {COBERTURA_MINIMA:.0%} dos pesos) — "
                    "score composto retido para nao ranquear por dado marginal"
                )
            else:
                score_obs = "nenhum componente com dado real ainda"

            af = afast.get(eid)
            indicadores = {
                "tempo_casa_meses": int(emp["tempo_casa_meses"]) if emp["tempo_casa_meses"] is not None else None,
                "data_admissao": emp["data_admissao"].isoformat() if emp["data_admissao"] else None,
                "batidas_30d": p["batidas"] if p else 0,
                "dias_com_batida_30d": p["dias_com_batida"] if p else 0,
                "atrasos": {
                    "disponivel": False,
                    "motivo": "requer escala vinculada as batidas — nao derivavel so do ponto",
                },
                "afastamentos": (
                    {"total": af["total"], "ativos": af["ativos"]}
                    if af
                    else ({"total": 0, "ativos": 0} if "sst_afastamentos" in existentes else {"indisponivel": True})
                ),
            }

            funcionarios.append(
                {
                    "employee_id": eid,
                    "nome": emp["nome"],
                    "cargo": emp["cargo"],
                    "posto": emp["posto_atual_nome"],
                    "score_composto": score_composto,
                    "score_obs": score_obs,
                    "peso_coberto": round(peso_total, 2),
                    "componentes": componentes,
                    "componentes_indisponiveis": [k for k, c in componentes.items() if not c["disponivel"]],
                    "indicadores": indicadores,
                }
            )

        funcionarios.sort(key=lambda f: (f["score_composto"] is None, -(f["score_composto"] or 0)))

        payload: dict[str, Any] = {
            "gerado_em": datetime.now(UTC).isoformat(),
            "janela_ponto_dias": JANELA_PONTO_DIAS,
            "janela_ocorrencias_dias": JANELA_OCORRENCIAS_DIAS,
            "pesos_declarados": PESOS_COMPONENTES,
            "metodo_score": (
                "media ponderada dos componentes DISPONIVEIS (0-10), pesos renormalizados; "
                "componentes indisponiveis sao listados, nunca imputados; "
                f"score so e emitido com cobertura >= {COBERTURA_MINIMA:.0%} dos pesos"
            ),
            "fontes": fontes,
            "avisos": avisos,
            "total_funcionarios": len(funcionarios),
        }
        if employee_id:
            payload["funcionario"] = funcionarios[0]
        else:
            payload["funcionarios"] = funcionarios
        return payload

    @staticmethod
    def _componente(
        disponivel: bool,
        score: float | None,
        valor_bruto: Any,
        fonte: str,
        peso: float,
        obs: str | None,
    ) -> dict[str, Any]:
        return {
            "disponivel": disponivel,
            "score": score,
            "valor_bruto": valor_bruto,
            "fonte": fonte,
            "peso": peso,
            "obs": obs,
        }

    @staticmethod
    def _obs_ausencia(tabela: str, existentes: set[str], motivo_sem_registro: str) -> str:
        if tabela not in existentes:
            return f"tabela {tabela} ausente"
        return motivo_sem_registro


__all__ = ["IntegratedPerformanceService"]
