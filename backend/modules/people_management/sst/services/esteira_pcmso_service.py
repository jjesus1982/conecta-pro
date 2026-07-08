"""Esteira PCMSO Preventiva — projeção da agenda de exames periódicos (NR-7).

Motor PREVENTIVO: em vez de reagir a ASOs vencidos, projeta para os próximos
N meses QUANDO cada funcionário ativo precisa do exame periódico e QUAIS exames
a função dele exige segundo o PCMSO oficial (sst_pcmso.exames_por_funcao —
Tabela 27 do eSocial, PCMSO do médico coordenador).

PRINCÍPIOS (dado real, projeção transparente):
- NADA é gravado aqui — a projeção é calculada AO VIVO; a fonte da verdade da
  realização é sempre gp_asos (um exame só existe quando registrado lá).
- Base do relógio periódico = último ASO REALIZADO (data_realizacao não nula,
  qualquer tipo exceto demissional — admissional/retorno/mudança também zeram
  o relógio clínico, NR-7). Próximo vencimento = data_validade do registro
  (ou data_realizacao + 12 meses quando a validade não foi gravada).
- Funcionário SEM nenhum ASO realizado = "pendente_imediato" (honesto: não há
  histórico; o exame precisa ser agendado JÁ).
- Função sem mapa no PCMSO → exames_definidos=False + nota honesta
  "exames a definir no PCMSO" — nunca inventamos a bateria de exames.
"""

from __future__ import annotations

import logging
import unicodedata
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Periodicidade padrão do exame periódico (NR-7 / PCMSO vigente): anual
PERIODICIDADE_MESES = 12

_MESES_PT = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]

# Siglas usadas pelo PCMSO oficial (Dr. Pojucan) → termo do cargo no ERP.
# Fonte: nomenclatura do próprio documento PCMSO 05/2026-04/2027.
_SIGLAS_PCMSO = {
    "AGP": "AGENTE DE PORTARIA",
    "ASG": "SERVICOS GERAIS",
}


def _normalizar(s: str | None) -> str:
    """Uppercase sem acentos (cargos do ERP têm acento; PCMSO usa siglas)."""
    if not s:
        return ""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).upper().strip()


def _mes_label(ano: int, mes: int) -> str:
    return f"{_MESES_PT[mes - 1]}/{ano}"


async def carregar_pcmso(db: AsyncSession) -> dict[str, Any] | None:
    """Carrega o PCMSO vigente mais recente de sst_pcmso (fonte real).

    Retorna dict com médico, vigência, dias p/ vencer o PCMSO em si e o mapa
    exames_por_funcao — ou None (honesto) se nenhum PCMSO foi cadastrado.
    """
    row = (
        await db.execute(
            text(
                "SELECT id, medico_coordenador, crm, uf, nit, elaborador, "
                "vigencia_inicio, vigencia_fim, exames_por_funcao, observacoes "
                "FROM sst_pcmso ORDER BY vigencia_fim DESC LIMIT 1"
            )
        )
    ).mappings().first()
    if row is None:
        return None

    hoje = date.today()
    vig_ini: date = row["vigencia_inicio"]
    vig_fim: date = row["vigencia_fim"]
    return {
        "pcmso_id": str(row["id"]),
        "medico_coordenador": row["medico_coordenador"],
        "crm": row["crm"],
        "uf": row["uf"],
        "elaborador": row["elaborador"],
        "vigencia_inicio": str(vig_ini),
        "vigencia_fim": str(vig_fim),
        "vigente_hoje": vig_ini <= hoje <= vig_fim,
        "dias_para_vencer_pcmso": (vig_fim - hoje).days,
        "grupos_funcao": sorted((row["exames_por_funcao"] or {}).keys()),
        "exames_por_funcao": row["exames_por_funcao"] or {},
    }


def mapear_grupo_pcmso(
    cargo: str | None, exames_por_funcao: dict[str, Any]
) -> tuple[str | None, list[dict[str, Any]]]:
    """Casa o cargo do funcionário com um grupo do PCMSO (Tabela 27).

    Match por termo normalizado (sem acento): cada grupo lista 'funcoes'
    (ex.: AGP, LIDER, ASG); casa se o termo (ou a expansão da sigla oficial)
    está contido no cargo. Sem match → (None, []) — exames a definir no PCMSO.
    """
    cargo_norm = _normalizar(cargo)
    if not cargo_norm:
        return None, []

    for grupo, spec in (exames_por_funcao or {}).items():
        for funcao in spec.get("funcoes") or []:
            termo = _normalizar(funcao)
            expansao = _SIGLAS_PCMSO.get(termo, termo)
            if termo == cargo_norm or termo in cargo_norm or expansao in cargo_norm:
                return grupo, list(spec.get("exames") or [])
    return None, []


class EsteiraPCMSOService:
    """Projeção preventiva da agenda de exames periódicos por funcionário."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def projetar_agenda(self, horizonte_meses: int = 12) -> dict[str, Any]:
        """Agenda projetada dos próximos `horizonte_meses` — nada é gravado.

        Para CADA funcionário ativo: último ASO realizado → próximo vencimento
        (12 meses); sem ASO → pendente imediato. Ordena por data prevista e
        anexa os exames da função (sst_pcmso.exames_por_funcao).
        """
        hoje = date.today()
        pcmso = await carregar_pcmso(self.db)
        exames_por_funcao: dict[str, Any] = (pcmso or {}).get("exames_por_funcao", {})

        rows = (
            await self.db.execute(
                text(
                    """
                    WITH ultimo_realizado AS (
                        SELECT DISTINCT ON (a.employee_id)
                               a.employee_id, a.tipo, a.data_realizacao, a.data_validade
                        FROM gp_asos a
                        WHERE a.data_realizacao IS NOT NULL AND a.tipo <> 'demissional'
                        ORDER BY a.employee_id, a.data_realizacao DESC
                    ),
                    agendado_futuro AS (
                        SELECT employee_id, min(data_agendamento) AS proxima_data
                        FROM gp_asos
                        WHERE status = 'agendado' AND data_agendamento >= CURRENT_DATE
                        GROUP BY employee_id
                    ),
                    posto_atual AS (
                        SELECT DISTINCT ON (al.employee_id)
                               al.employee_id, p.id AS posto_id, p.name AS posto_nome
                        FROM allocations al
                        JOIN posts p ON p.id = al.post_id
                        WHERE al.is_active = true AND al.status = 'active'
                          AND (al.end_date IS NULL OR al.end_date >= CURRENT_DATE)
                        ORDER BY al.employee_id, al.is_primary DESC, al.start_date DESC
                    )
                    SELECT e.id AS employee_id, e.nome, e.cargo,
                           u.tipo AS base_tipo, u.data_realizacao AS base_realizacao,
                           (COALESCE(
                               u.data_validade,
                               (u.data_realizacao + INTERVAL '12 months')::date
                           )) AS vencimento_base,
                           ag.proxima_data,
                           pa.posto_id, pa.posto_nome
                    FROM employees e
                    LEFT JOIN ultimo_realizado u ON u.employee_id = e.id
                    LEFT JOIN agendado_futuro ag ON ag.employee_id = e.id
                    LEFT JOIN posto_atual pa ON pa.employee_id = e.id
                    WHERE e.status = 'ativo'
                    ORDER BY e.nome
                    """
                )
            )
        ).mappings().all()

        limite = self._somar_meses(hoje, horizonte_meses)
        agenda: list[dict[str, Any]] = []
        alem_do_horizonte = 0

        for r in rows:
            vencimento: date | None = r["vencimento_base"]
            if vencimento is None:
                situacao = "pendente_imediato"
                data_prevista = hoje
                dias_para_vencer = None
                dias_vencido = None
            elif vencimento < hoje:
                situacao = "vencido"
                data_prevista = hoje  # ação é imediata; vencimento real fica exposto
                dias_para_vencer = None
                dias_vencido = (hoje - vencimento).days
            else:
                situacao = "previsto"
                data_prevista = vencimento
                dias_para_vencer = (vencimento - hoje).days
                dias_vencido = None
                if vencimento > limite:
                    alem_do_horizonte += 1
                    continue  # fora do horizonte pedido

            grupo, exames = mapear_grupo_pcmso(r["cargo"], exames_por_funcao)
            agenda.append(
                {
                    "employee_id": str(r["employee_id"]),
                    "nome": r["nome"],
                    "cargo": r["cargo"],
                    "posto_id": str(r["posto_id"]) if r["posto_id"] else None,
                    "posto_nome": r["posto_nome"] or "Sem posto ativo",
                    "situacao": situacao,
                    "data_prevista": str(data_prevista),
                    "mes": f"{data_prevista.year:04d}-{data_prevista.month:02d}",
                    "vencimento_base": str(vencimento) if vencimento else None,
                    "dias_para_vencer": dias_para_vencer,
                    "dias_vencido": dias_vencido,
                    "base": (
                        {
                            "tipo": r["base_tipo"],
                            "data_realizacao": str(r["base_realizacao"]),
                        }
                        if r["base_realizacao"]
                        else None
                    ),
                    "grupo_pcmso": grupo,
                    "exames_definidos": bool(exames),
                    "exames_previstos": exames,
                    "nota_exames": (
                        None if exames else "exames a definir no PCMSO (função sem mapa)"
                    ),
                    "ja_agendado": r["proxima_data"] is not None,
                    "proxima_data_agendada": (
                        str(r["proxima_data"]) if r["proxima_data"] else None
                    ),
                }
            )

        agenda.sort(key=lambda i: (i["data_prevista"], i["nome"]))

        return {
            "gerado_em": str(hoje),
            "horizonte_meses": horizonte_meses,
            "pcmso": (
                {k: v for k, v in pcmso.items() if k != "exames_por_funcao"}
                if pcmso
                else None
            ),
            "total_funcionarios_ativos": len(rows),
            "totais": {
                "pendente_imediato": sum(
                    1 for i in agenda if i["situacao"] == "pendente_imediato"
                ),
                "vencidos": sum(1 for i in agenda if i["situacao"] == "vencido"),
                "previstos": sum(1 for i in agenda if i["situacao"] == "previsto"),
                "ja_agendados": sum(1 for i in agenda if i["ja_agendado"]),
                "sem_mapa_exames": sum(1 for i in agenda if not i["exames_definidos"]),
                "alem_do_horizonte": alem_do_horizonte,
            },
            "resumo_por_mes": self._resumo_por_mes(agenda),
            "resumo_por_posto": self._resumo_por_posto(agenda),
            "agenda": agenda,
            "nota": (
                "Projeção calculada AO VIVO a partir de gp_asos (último exame "
                "realizado + 12 meses, NR-7) e do PCMSO oficial (sst_pcmso). "
                "NADA é gravado — agendar/realizar de verdade continua sendo o "
                "único jeito de mudar a situação. Vencidos e pendentes imediatos "
                "entram no mês atual (ação já)."
            ),
        }

    # ------------------------------------------------------------------
    # Resumos
    # ------------------------------------------------------------------

    @staticmethod
    def _resumo_por_mes(agenda: list[dict[str, Any]]) -> list[dict[str, Any]]:
        por_mes: dict[str, dict[str, Any]] = {}
        for item in agenda:
            mes = item["mes"]
            ano, m = int(mes[:4]), int(mes[5:7])
            g = por_mes.setdefault(
                mes,
                {
                    "mes": mes,
                    "label": _mes_label(ano, m),
                    "total": 0,
                    "pendente_imediato": 0,
                    "vencidos": 0,
                    "previstos": 0,
                    "agendados": 0,
                },
            )
            g["total"] += 1
            if item["situacao"] == "pendente_imediato":
                g["pendente_imediato"] += 1
            elif item["situacao"] == "vencido":
                g["vencidos"] += 1
            else:
                g["previstos"] += 1
            if item["ja_agendado"]:
                g["agendados"] += 1
        return sorted(por_mes.values(), key=lambda g: g["mes"])

    @staticmethod
    def _resumo_por_posto(agenda: list[dict[str, Any]]) -> list[dict[str, Any]]:
        por_posto: dict[str, dict[str, Any]] = {}
        for item in agenda:
            g = por_posto.setdefault(
                item["posto_nome"],
                {
                    "posto_nome": item["posto_nome"],
                    "posto_id": item["posto_id"],
                    "total": 0,
                    "acao_imediata": 0,
                },
            )
            g["total"] += 1
            if item["situacao"] in ("vencido", "pendente_imediato"):
                g["acao_imediata"] += 1
        return sorted(por_posto.values(), key=lambda g: g["total"], reverse=True)

    @staticmethod
    def _somar_meses(d: date, meses: int) -> date:
        """d + N meses (dia clampado no fim do mês)."""
        import calendar

        m = d.month - 1 + meses
        ano = d.year + m // 12
        mes = m % 12 + 1
        dia = min(d.day, calendar.monthrange(ano, mes)[1])
        return date(ano, mes, dia)
