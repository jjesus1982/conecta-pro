"""Service SST — Wiring real com banco de dados, CCT 2026 e dados reais."""

import calendar
import logging
from datetime import date, datetime, timedelta

from dateutil.relativedelta import relativedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.people_management.sst.models.afastamento import (
    Afastamento,
    StatusAfastamento,
    TipoAfastamento,
)

logger = logging.getLogger(__name__)

# Constantes CCT 2026
CCT_AJUDA_MEDICAMENTO_VALOR = 300.00
CCT_ESTABILIDADE_MESES = 12

# Tipos de afastamento que geram estabilidade (CCT Clausula 29a)
TIPOS_COM_ESTABILIDADE = (
    TipoAfastamento.ACIDENTE_TRABALHO,
    TipoAfastamento.ACIDENTE_TRAJETO,
)

# Prefixos CID que indicam causa externa (acidente)
CID_ACIDENTE_PREFIXOS = ("W", "V", "X", "Y")

# Graus de risco NR-1 (1=baixo, 2=medio, 3=alto)
# Derivados da CCT (cct_cargos) via employees.cct_cargo_id — NAO ha lista fantasma.
GRAU_RISCO_BAIXO = 1
GRAU_RISCO_MEDIO = 2
GRAU_RISCO_ALTO = 3


def somar_meses(d: date, meses: int) -> date:
    """d + N meses (dia clampado no fim do mês) — cálculo do vencimento de treinamento."""
    m = d.month - 1 + meses
    ano = d.year + m // 12
    mes = m % 12 + 1
    dia = min(d.day, calendar.monthrange(ano, mes)[1])
    return date(ano, mes, dia)


def _grau_risco_cct(peric: float, insal: float) -> int:
    """Deriva o grau de risco NR-1 a partir dos adicionais da CCT.

    Cargos com periculosidade (>0) sao expostos a risco grave/iminente (grau alto).
    Cargos com insalubridade (>0) tem grau medio. Demais, grau baixo.
    Fonte unica: cct_cargos (adicional_periculosidade/insalubridade_percentual).
    """
    if peric > 0:
        return GRAU_RISCO_ALTO
    if insal > 0:
        return GRAU_RISCO_MEDIO
    return GRAU_RISCO_BAIXO


class SSTService:
    """Service SST com wiring real ao banco de dados."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ================================================================
    # DASHBOARD
    # ================================================================

    async def get_dashboard(self) -> dict[str, Any]:
        """Dashboard SST com dados reais dos colaboradores."""
        total_colab = await self._count_employees()
        afastados = await self._count_afastados_ativos()
        taxa = round((afastados / total_colab * 100) if total_colab > 0 else 0, 1)

        asos_vencendo = await self.verificar_vencimentos_aso(30)
        cats_abertas = await self._count_cats_abertas()
        estabilidade_ativos = await self.listar_estabilidade_ativos()
        ajuda_med = await self.listar_ajuda_medicamento_ativos()

        nr1 = await self._calcular_indice_nr1()
        pcmso = await self._get_pcmso_stats()

        return {
            "total_colaboradores": total_colab,
            "afastados_ativos": afastados,
            "taxa_afastamento": f"{taxa}%",
            "risco_nr1": f"{nr1['indice']}%",
            "asos_vencendo_30d": len(asos_vencendo),
            "cats_abertas": cats_abertas,
            "colaboradores_estabilidade": len(estabilidade_ativos),
            "pcmso_vigente": pcmso["realizados"] > 0,
            "ppra_vigente": await self._has_riscos_mapeados(),
            "ajuda_medicamento_ativa": len(ajuda_med),
            "custo_afastamentos_mes": round(len(ajuda_med) * CCT_AJUDA_MEDICAMENTO_VALOR, 2),
            "cct_referencia": "SINDECOMPRESTS/SINDICOND-AM 2026",
        }

    # ================================================================
    # AFASTAMENTOS
    # ================================================================

    async def listar_afastamentos(self, status: str | None = None) -> list[dict]:
        """Lista afastamentos com filtro opcional por status."""
        query = select(Afastamento).order_by(Afastamento.data_inicio.desc())
        if status:
            query = query.where(Afastamento.status == status)
        result = await self.db.execute(query)
        return [self._afastamento_to_dict(a) for a in result.scalars().all()]

    async def get_afastamento(self, afastamento_id: str) -> dict | None:
        """Busca afastamento por ID."""
        result = await self.db.execute(select(Afastamento).where(Afastamento.id == afastamento_id))
        af = result.scalar_one_or_none()
        return self._afastamento_to_dict(af) if af else None

    async def registrar_afastamento(self, data: dict) -> dict:
        """Registra novo afastamento com regras CCT 2026."""
        dias = data.get("dias_previstos")
        data_fim = None
        dt_inicio = datetime.strptime(data["data_inicio"], "%Y-%m-%d").date()
        if dias:
            data_fim = dt_inicio + timedelta(days=int(dias))

        tipo = data.get("tipo", TipoAfastamento.DOENCA)
        cid = data.get("cid")

        # CCT Clausula 29a / art. 118 Lei 8.213: acidente gera estabilidade de 12 MESES
        # de calendário (não 30d×12). Provisiona a partir do fim do afastamento; sem
        # previsão de fim, usa o início (recalculado no retorno). NUNCA fica None quando
        # gera estabilidade — senão o afastado some do painel de estabilidade e pode ser
        # demitido dentro do período estável (reintegração).
        gera_estab = _deve_gerar_estabilidade(tipo, cid)
        estab_ate = None
        if gera_estab:
            base = data_fim or dt_inicio
            estab_ate = base + relativedelta(months=CCT_ESTABILIDADE_MESES)

        # CCT Clausula 15a: ajuda medicamento para afastados com atestado
        ajuda_med = data.get("atestado", True) and tipo in (
            TipoAfastamento.DOENCA,
            TipoAfastamento.ACIDENTE_TRABALHO,
            TipoAfastamento.ACIDENTE_TRAJETO,
        )

        afastamento = Afastamento(
            id=str(uuid4()),
            employee_id=data["employee_id"],
            employee_nome=data.get("employee_nome", ""),
            employee_cargo=data.get("employee_cargo"),
            tipo=tipo,
            motivo=data.get("motivo"),
            data_inicio=dt_inicio,
            data_fim_prevista=data_fim,
            dias_previstos=dias,
            atestado=data.get("atestado", True),
            cid=cid,
            medico=data.get("medico"),
            crm=data.get("crm"),
            status=StatusAfastamento.ATIVO,
            ajuda_medicamento_ativa=ajuda_med,
            ajuda_medicamento_valor=CCT_AJUDA_MEDICAMENTO_VALOR if ajuda_med else None,
            gera_estabilidade=gera_estab,
            estabilidade_ate=estab_ate,
        )
        self.db.add(afastamento)
        await self.db.flush()
        await self.db.refresh(afastamento)
        logger.info("Afastamento registrado: %s — %s", afastamento.employee_nome, tipo)
        return self._afastamento_to_dict(afastamento)

    async def registrar_retorno(self, afastamento_id: str, data_retorno: str) -> dict | None:
        """Registra retorno de afastamento e calcula estabilidade CCT."""
        result = await self.db.execute(select(Afastamento).where(Afastamento.id == afastamento_id))
        af = result.scalar_one_or_none()
        if not af:
            return None

        dt_retorno = datetime.strptime(data_retorno, "%Y-%m-%d").date()
        af.data_retorno = dt_retorno
        af.status = StatusAfastamento.ENCERRADO

        # Recalcular estabilidade CCT com data real de retorno (12 meses de calendário)
        if af.gera_estabilidade:
            af.estabilidade_ate = dt_retorno + relativedelta(months=CCT_ESTABILIDADE_MESES)

        await self.db.flush()
        await self.db.refresh(af)
        logger.info("Retorno registrado: %s em %s", af.employee_nome, data_retorno)
        return self._afastamento_to_dict(af)

    # ================================================================
    # NR-1 (Gerenciamento de Riscos) — CALCULO REAL
    # ================================================================

    async def get_dashboard_nr1(self) -> dict[str, Any]:
        """Dashboard NR-1 com indice de risco calculado a partir de dados reais."""
        nr1 = await self._calcular_indice_nr1()
        total = await self._count_employees()
        afastados = await self._count_afastados_ativos()
        riscos = await self._get_risk_stats()

        # Classificar colaboradores por nivel de risco derivado da CCT (cct_cargos)
        grupos = await self._grau_risco_por_cargo()
        alto = sum(g["qtd"] for g in grupos if g["grau"] >= GRAU_RISCO_ALTO)
        medio = sum(g["qtd"] for g in grupos if g["grau"] == GRAU_RISCO_MEDIO)
        baixo = sum(g["qtd"] for g in grupos if g["grau"] <= GRAU_RISCO_BAIXO)

        # Acoes pendentes = riscos sem medida implementada
        acoes_pendentes = riscos.get("sem_medida", 0)

        nivel = "VERDE"
        if nr1["indice"] > 40:
            nivel = "VERMELHO"
        elif nr1["indice"] > 25:
            nivel = "LARANJA"
        elif nr1["indice"] > 15:
            nivel = "AMARELO"

        return {
            "indice_risco_geral": f"{nr1['indice']}%",
            "fonte": "Calculo baseado em riscos mapeados, afastamentos e cargos",
            "total_colaboradores": total,
            "colaboradores_risco_alto": alto + afastados,
            "colaboradores_risco_medio": medio,
            "colaboradores_risco_baixo": baixo,
            "afastados_ativos": afastados,
            "riscos_mapeados": riscos.get("total", 0),
            "acoes_corretivas_pendentes": acoes_pendentes,
            "nivel_alerta": nivel,
            "recomendacoes": nr1["recomendacoes"],
        }

    async def listar_colaboradores_risco(self) -> list[dict]:
        """Lista colaboradores por nivel de risco NR-1."""
        afastamentos = await self.listar_afastamentos(status=StatusAfastamento.ATIVO)
        risco_alto = []
        for af in afastamentos:
            risco_alto.append(
                {
                    "employee_id": af["employee_id"],
                    "nome": af["employee_nome"],
                    "cargo": af.get("employee_cargo"),
                    "nivel_risco": "alto",
                    "motivo": f"Afastado desde {af['data_inicio']} — {af['tipo']}",
                }
            )

        return risco_alto

    # ================================================================
    # PCMSO / PPRA — DADOS REAIS DO BANCO
    # ================================================================

    async def get_pcmso_status(self) -> dict[str, Any]:
        """Status do PCMSO: documento REAL (sst_pcmso) + execução real (gp_asos)."""
        from modules.people_management.sst.services.esteira_pcmso_service import (
            carregar_pcmso,
        )

        total = await self._count_employees()
        stats = await self._get_pcmso_stats()

        percentual = round(stats["realizados"] * 100 / total, 1) if total > 0 else 0

        # Documento oficial do PCMSO (médico coordenador, vigência, countdown)
        documento = None
        try:
            documento = await carregar_pcmso(self.db)
            if documento:
                documento.pop("exames_por_funcao", None)  # mapa completo fica na esteira
        except Exception as exc:
            logger.debug("Tabela sst_pcmso indisponível: %s", exc)

        return {
            "programa": "PCMSO — Programa de Controle Medico de Saude Ocupacional",
            "obrigatorio_cct": True,
            "clausula_cct": "23a — SINDECOMPRESTS/SINDICOND-AM 2026",
            "vigente": bool(documento and documento["vigente_hoje"]) or stats["realizados"] > 0,
            "coordenador": (
                documento["medico_coordenador"]
                if documento
                else "aguardando cadastro do PCMSO (sst_pcmso)"
            ),
            "documento": documento,
            "total_colaboradores": total,
            "exames_realizados": stats["realizados"],
            "exames_pendentes": stats["pendentes"],
            "exames_vencidos": stats["vencidos"],
            "percentual_cobertura": percentual,
            "status": ("vigente" if percentual >= 80 else "atencao" if percentual > 0 else "pendente"),
        }

    async def get_ppra_status(self) -> dict[str, Any]:
        """Status do PPRA calculado a partir de dados reais (gp_risks)."""
        riscos = await self._get_risk_stats()

        return {
            "programa": "PPRA — Programa de Prevencao de Riscos Ambientais",
            "obrigatorio_cct": True,
            "clausula_cct": "23a — SINDECOMPRESTS/SINDICOND-AM 2026",
            "vigente": riscos["total"] > 0,
            "responsavel": "Tecnico de Seguranca do Trabalho",
            "riscos_mapeados": riscos["total"],
            "medidas_implementadas": riscos["com_medida"],
            "medidas_pendentes": riscos["sem_medida"],
            "percentual_controle": riscos["percentual"],
            "status": "vigente" if riscos["total"] > 0 else "pendente",
        }

    # ================================================================
    # ASOs
    # ================================================================

    async def verificar_vencimentos_aso(self, dias: int = 30) -> list[dict]:
        """ASOs proximos do vencimento (consulta banco gp_asos)."""
        vencendo = []
        try:
            hoje = date.today()
            limite = hoje + timedelta(days=dias)
            result = await self.db.execute(
                text(
                    "SELECT aso_id, employee_id, tipo, data_realizacao, data_validade "
                    "FROM gp_asos WHERE data_validade IS NOT NULL "
                    "AND data_validade BETWEEN :hoje AND :limite "
                    "ORDER BY data_validade"
                ),
                {"hoje": hoje, "limite": limite},
            )
            for row in result.fetchall():
                vencendo.append(
                    {
                        "aso_id": row[0],
                        "employee_id": row[1],
                        "tipo": row[2],
                        "data_validade": str(row[4]),
                        "dias_restantes": (row[4] - hoje).days,
                    }
                )
        except Exception as exc:
            logger.debug("Tabela gp_asos sem dados: %s", exc)
        return vencendo

    async def listar_sem_aso(self) -> list[dict]:
        """Colaboradores ativos sem NENHUM ASO realizado digitalizado.

        Semântica alinhada à carga retroativa (fato Jordan 2026-07-08: todos
        fizeram admissional em papel — 'sem ASO' = documento não digitalizado).
        Cast ::text dos DOIS lados: uuid=text quebrava a query e o except
        engolia o erro, devolvendo total=0 falso.
        """
        sem_aso = []
        try:
            result = await self.db.execute(
                text(
                    "SELECT e.id, e.nome, e.cargo FROM employees e "
                    "WHERE e.status = 'ativo' "
                    "AND NOT EXISTS (SELECT 1 FROM gp_asos a "
                    "WHERE a.employee_id::text = e.id::text "
                    "AND a.status = 'realizado') "
                    "ORDER BY e.nome"
                )
            )
            for row in result.fetchall():
                sem_aso.append({"employee_id": str(row[0]), "nome": row[1], "cargo": row[2]})
        except Exception as exc:
            await self.db.rollback()
            logger.warning("Consulta sem ASO falhou (retornando vazio): %s", exc)
        return sem_aso

    # ================================================================
    # TREINAMENTOS NR (sst_treinamentos) — 4º pilar do compliance NR-1
    # ================================================================

    @staticmethod
    def _situacao_treinamento(vencimento: date, hoje: date) -> str:
        if vencimento < hoje:
            return "vencido"
        if vencimento <= hoje + timedelta(days=30):
            return "vencendo"
        return "em_dia"

    async def criar_treinamento(self, data: dict, created_by: str | None = None) -> dict:
        """Registra treinamento NR REALIZADO (dado real — nunca fabricado).

        vencimento é CALCULADO: data_realizacao + validade_meses (meses).
        """
        from modules.people_management.sst.schemas.sst_schemas import NORMAS_TREINAMENTO

        norma = str(data.get("norma") or "")
        if norma not in NORMAS_TREINAMENTO:
            raise ValueError(f"norma inválida '{norma}'. Válidas: {', '.join(NORMAS_TREINAMENTO)}")
        try:
            dt_realizacao = date.fromisoformat(str(data["data_realizacao"])[:10])
        except (KeyError, ValueError) as exc:
            raise ValueError("data_realizacao inválida (use YYYY-MM-DD)") from exc
        if dt_realizacao > date.today():
            raise ValueError("data_realizacao no futuro — registre só treinamentos REALIZADOS")
        validade_meses = int(data.get("validade_meses") or 12)
        if not 1 <= validade_meses <= 120:
            raise ValueError("validade_meses deve estar entre 1 e 120")
        vencimento = somar_meses(dt_realizacao, validade_meses)

        emp = (
            await self.db.execute(
                text("SELECT id, nome FROM employees WHERE id::text = :eid"),
                {"eid": str(data["employee_id"])},
            )
        ).mappings().first()
        if not emp:
            raise ValueError("Funcionário não encontrado")

        row = (
            await self.db.execute(
                text(
                    "INSERT INTO sst_treinamentos "
                    "(employee_id, norma, descricao, data_realizacao, validade_meses, "
                    " vencimento, certificado_path, created_by) "
                    "VALUES (:eid, :norma, :descricao, :realizacao, :meses, :venc, :cert, :autor) "
                    "RETURNING id, employee_id, norma, descricao, data_realizacao, "
                    "validade_meses, vencimento, certificado_path, created_by"
                ),
                {
                    "eid": str(data["employee_id"]),
                    "norma": norma,
                    "descricao": data.get("descricao"),
                    "realizacao": dt_realizacao,
                    "meses": validade_meses,
                    "venc": vencimento,
                    "cert": data.get("certificado_path"),
                    "autor": created_by,
                },
            )
        ).mappings().first()
        await self.db.commit()
        hoje = date.today()
        return {
            "id": str(row["id"]),
            "employee_id": str(row["employee_id"]),
            "employee_nome": emp["nome"],
            "norma": row["norma"],
            "descricao": row["descricao"],
            "data_realizacao": str(row["data_realizacao"]),
            "validade_meses": row["validade_meses"],
            "vencimento": str(row["vencimento"]),
            "situacao": self._situacao_treinamento(row["vencimento"], hoje),
            "certificado_path": row["certificado_path"],
            "created_by": row["created_by"],
        }

    async def listar_treinamentos(
        self,
        employee_id: str | None = None,
        norma: str | None = None,
        vencendo_em_dias: int | None = None,
    ) -> list[dict]:
        """Lista treinamentos NR com nome real do funcionário.

        vencendo_em_dias=N: só vencidos + os que vencem nos próximos N dias.
        """
        query = (
            "SELECT t.id, t.employee_id, e.nome AS employee_nome, t.norma, t.descricao, "
            "t.data_realizacao, t.validade_meses, t.vencimento, t.certificado_path, t.created_by "
            "FROM sst_treinamentos t JOIN employees e ON e.id = t.employee_id WHERE 1=1"
        )
        params: dict[str, Any] = {}
        if employee_id:
            query += " AND t.employee_id::text = :eid"
            params["eid"] = employee_id
        if norma:
            query += " AND t.norma = :norma"
            params["norma"] = norma
        if vencendo_em_dias is not None:
            query += " AND t.vencimento <= :limite"
            params["limite"] = date.today() + timedelta(days=vencendo_em_dias)
        query += " ORDER BY t.vencimento ASC, e.nome"
        rows = (await self.db.execute(text(query), params)).mappings().all()
        hoje = date.today()
        return [
            {
                "id": str(r["id"]),
                "employee_id": str(r["employee_id"]),
                "employee_nome": r["employee_nome"],
                "norma": r["norma"],
                "descricao": r["descricao"],
                "data_realizacao": str(r["data_realizacao"]),
                "validade_meses": r["validade_meses"],
                "vencimento": str(r["vencimento"]),
                "situacao": self._situacao_treinamento(r["vencimento"], hoje),
                "certificado_path": r["certificado_path"],
                "created_by": r["created_by"],
            }
            for r in rows
        ]

    async def excluir_treinamento(self, treinamento_id: str) -> bool:
        """Exclui um registro de treinamento (correção de lançamento errado)."""
        result = await self.db.execute(
            text("DELETE FROM sst_treinamentos WHERE id::text = :tid"),
            {"tid": treinamento_id},
        )
        await self.db.commit()
        return result.rowcount > 0

    # ================================================================
    # REGULARIZAÇÃO DE ASOs VENCIDAS (plano das 88)
    # ================================================================

    async def listar_asos_regularizacao(self) -> dict[str, Any]:
        """Lista priorizada de funcionários ATIVOS com o último ASO vencido.

        Priorização: mais vencido primeiro (dias_vencido DESC). Inclui o posto
        atual REAL (allocations ativas → posts) para logística das clínicas e
        se já existe um novo ASO agendado (evita agendamento duplicado).
        """
        hoje = date.today()
        rows = (
            await self.db.execute(
                text(
                    """
                    WITH ultimo_aso AS (
                        SELECT DISTINCT ON (a.employee_id)
                               a.employee_id, a.aso_id, a.tipo, a.data_validade, a.clinica
                        FROM gp_asos a
                        WHERE a.data_validade IS NOT NULL
                        ORDER BY a.employee_id, a.data_validade DESC
                    ),
                    posto_atual AS (
                        SELECT DISTINCT ON (al.employee_id)
                               al.employee_id, p.id AS posto_id, p.name AS posto_nome
                        FROM allocations al
                        JOIN posts p ON p.id = al.post_id
                        WHERE al.is_active = true AND al.status = 'active'
                          AND (al.end_date IS NULL OR al.end_date >= CURRENT_DATE)
                        ORDER BY al.employee_id, al.is_primary DESC, al.start_date DESC
                    ),
                    agendados AS (
                        SELECT employee_id, min(data_agendamento) AS proxima_data
                        FROM gp_asos
                        WHERE status = 'agendado' AND data_agendamento >= CURRENT_DATE
                        GROUP BY employee_id
                    )
                    SELECT e.id AS employee_id, e.nome, e.cargo,
                           u.aso_id, u.tipo, u.data_validade,
                           (CURRENT_DATE - u.data_validade) AS dias_vencido,
                           pa.posto_id, pa.posto_nome, ag.proxima_data
                    FROM ultimo_aso u
                    JOIN employees e ON e.id = u.employee_id AND e.status = 'ativo'
                    LEFT JOIN posto_atual pa ON pa.employee_id = u.employee_id
                    LEFT JOIN agendados ag ON ag.employee_id = u.employee_id
                    WHERE u.data_validade < CURRENT_DATE
                    ORDER BY u.data_validade ASC, e.nome
                    """
                )
            )
        ).mappings().all()

        pendentes = [
            {
                "employee_id": str(r["employee_id"]),
                "nome": r["nome"],
                "cargo": r["cargo"],
                "aso_id": r["aso_id"],
                "tipo_ultimo_aso": r["tipo"],
                "data_validade": str(r["data_validade"]),
                "dias_vencido": int(r["dias_vencido"]),
                "posto_id": str(r["posto_id"]) if r["posto_id"] else None,
                "posto_nome": r["posto_nome"] or "Sem posto ativo",
                "ja_agendado": r["proxima_data"] is not None,
                "proxima_data_agendada": str(r["proxima_data"]) if r["proxima_data"] else None,
            }
            for r in rows
        ]

        # Resumo por posto (logística: agrupar exames por localização)
        por_posto: dict[str, dict[str, Any]] = {}
        for p in pendentes:
            grupo = por_posto.setdefault(
                p["posto_nome"],
                {"posto_nome": p["posto_nome"], "posto_id": p["posto_id"], "pendentes": 0, "mais_vencido_dias": 0},
            )
            grupo["pendentes"] += 1
            grupo["mais_vencido_dias"] = max(grupo["mais_vencido_dias"], p["dias_vencido"])

        # Registros vencidos TOTAIS (inclui históricos de quem já renovou/saiu)
        registros_vencidos = (
            await self.db.execute(
                text("SELECT count(*) FROM gp_asos WHERE data_validade < CURRENT_DATE")
            )
        ).scalar() or 0

        return {
            "gerado_em": str(hoje),
            "registros_aso_vencidos_total": registros_vencidos,
            "funcionarios_pendentes": len(pendentes),
            "ja_agendados": sum(1 for p in pendentes if p["ja_agendado"]),
            "nota": (
                "registros_aso_vencidos_total conta TODAS as linhas vencidas em gp_asos "
                "(inclui históricos); funcionarios_pendentes conta funcionários ATIVOS "
                "cujo ASO mais recente está vencido — é a fila real de regularização."
            ),
            "resumo_por_posto": sorted(
                por_posto.values(), key=lambda g: g["pendentes"], reverse=True
            ),
            "pendentes": pendentes,
        }

    # ================================================================
    # PAINEL DE REGULARIZAÇÃO SST — os "descalços" (onda de admissões 2026)
    # ================================================================

    async def get_regularizacao_descalcos(self) -> dict[str, Any]:
        """Painel de acompanhamento dos "descalços" — read-computed, dado REAL.

        Coorte estável = funcionários ATIVOS admitidos na onda 2026
        (data_admissao >= 2026-01-01). Como data_admissao NÃO muda, o
        denominador da barra de progresso é fixo: conforme a Márcia registra
        ASO retroativo, ficha de EPI assinada e certificado de treinamento, os
        percentuais SOBEM sozinhos (nada aqui grava/fabrica cumprimento).

        Por funcionário (FATO no banco):
        - aso_ok: existe gp_asos status='realizado' vigente (data_validade
          nula ou >= hoje)
        - epi_ok: existe entrega gp_epi_deliveries com ficha sst_fichas_epi
          ASSINADA
        - treinamento_ok: certificado VÁLIDO (training_certificates) em TODOS
          os cursos NR obrigatórios (training_courses is_mandatory=true:
          NR-1, Uso de EPI, Ronda)

        descalcos = coorte com aso_ok=false (os 19 sem ASO admissional),
        priorizados por dias_pendente (admissão mais antiga no topo). Também
        devolve o bloco dos ASOs VENCIDOS (renovação) via
        listar_asos_regularizacao().
        """
        rows = (
            await self.db.execute(
                text(
                    """
                    WITH req AS (
                        SELECT id, name FROM training_courses
                        WHERE is_mandatory = true AND is_active = true
                          AND (name ILIKE '%NR-1%' OR name ILIKE '%EPI%'
                               OR name ILIKE '%Ronda%')
                    ),
                    coorte AS (
                        SELECT e.id, e.matricula, e.nome, e.cargo, e.data_admissao,
                               (CURRENT_DATE - e.data_admissao) AS dias_pendente
                        FROM employees e
                        WHERE e.status = 'ativo'
                          AND e.data_admissao IS NOT NULL
                          AND e.data_admissao >= DATE '2026-01-01'
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
                    SELECT c.id AS employee_id, c.matricula, c.nome, c.cargo,
                           c.data_admissao, c.dias_pendente,
                           pa.posto_id, pa.posto_nome,
                           EXISTS(
                               SELECT 1 FROM gp_asos a
                               WHERE a.employee_id = c.id AND a.status = 'realizado'
                                 AND (a.data_validade IS NULL
                                      OR a.data_validade >= CURRENT_DATE)
                           ) AS aso_ok,
                           EXISTS(
                               SELECT 1 FROM gp_epi_deliveries d
                               JOIN sst_fichas_epi f ON f.id = d.ficha_epi_id
                               WHERE d.employee_id = c.id AND f.status = 'assinada'
                           ) AS epi_ok,
                           (SELECT count(*) FROM gp_epi_deliveries d
                            WHERE d.employee_id = c.id) AS epi_entregas,
                           (SELECT count(DISTINCT tc.course_id)
                            FROM training_certificates tc
                            WHERE tc.employee_id = c.id AND tc.status = 'valid'
                              AND tc.course_id IN (SELECT id FROM req)
                              AND (tc.expires_at IS NULL
                                   OR tc.expires_at >= now())) AS treino_feitos,
                           (SELECT count(*) FROM req) AS treino_req
                    FROM coorte c
                    LEFT JOIN posto_atual pa ON pa.employee_id = c.id
                    ORDER BY c.dias_pendente DESC NULLS LAST, c.nome
                    """
                )
            )
        ).mappings().all()

        coorte: list[dict[str, Any]] = []
        for r in rows:
            treino_req = int(r["treino_req"] or 0)
            treino_feitos = int(r["treino_feitos"] or 0)
            # treinamento_ok só é True quando há cursos obrigatórios cadastrados
            # E todos têm certificado válido (honesto: sem cursos = não avaliável)
            treinamento_ok = treino_req > 0 and treino_feitos >= treino_req
            item = {
                "employee_id": str(r["employee_id"]),
                "matricula": r["matricula"],
                "nome": r["nome"],
                "cargo": r["cargo"],
                "posto": r["posto_nome"] or "Sem posto ativo",
                "posto_id": str(r["posto_id"]) if r["posto_id"] else None,
                "data_admissao": str(r["data_admissao"]) if r["data_admissao"] else None,
                "dias_pendente": int(r["dias_pendente"]) if r["dias_pendente"] is not None else None,
                "aso_ok": bool(r["aso_ok"]),
                "epi_ok": bool(r["epi_ok"]),
                "epi_entregas": int(r["epi_entregas"] or 0),
                "treinamento_ok": treinamento_ok,
                "treinamentos_feitos": treino_feitos,
                "treinamentos_obrigatorios": treino_req,
            }
            coorte.append(item)

        total = len(coorte)
        aso_ok_n = sum(1 for c in coorte if c["aso_ok"])
        epi_ok_n = sum(1 for c in coorte if c["epi_ok"])
        treino_ok_n = sum(1 for c in coorte if c["treinamento_ok"])
        regularizados_n = sum(
            1 for c in coorte if c["aso_ok"] and c["epi_ok"] and c["treinamento_ok"]
        )

        def _pct(n: int) -> float:
            return round(n / total * 100, 1) if total else 0.0

        # descalços = coorte SEM ASO admissional realizado (o núcleo dos 19)
        descalcos = [c for c in coorte if not c["aso_ok"]]

        # Prioridade textual: os 2 mais antigos ainda descalços
        prioridade = None
        if descalcos:
            top = descalcos[:2]
            nomes = " e ".join(
                f"{c['nome'].split()[0].title()} ({c['dias_pendente']}d)" for c in top
            )
            prioridade = (
                f"Priorizar {nomes} — admissão mais antiga sem ASO/EPI/treinamento."
            )

        # Bloco dos ASOs VENCIDOS (renovação) — reusa a lista priorizada existente
        try:
            vencidos = await self.listar_asos_regularizacao()
        except Exception as exc:  # à prova de falha — o painel dos descalços não cai por isto
            logger.warning("Bloco de ASOs vencidos indisponível: %s", exc)
            vencidos = {"funcionarios_pendentes": 0, "pendentes": [], "erro": str(exc)}

        return {
            "gerado_em": str(date.today()),
            "resumo": {
                "coorte_onda_2026": total,
                "descalcos": len(descalcos),
                "aso_ok": aso_ok_n,
                "epi_ok": epi_ok_n,
                "treinamento_ok": treino_ok_n,
                "regularizados_total": regularizados_n,
                "pct_aso": _pct(aso_ok_n),
                "pct_epi": _pct(epi_ok_n),
                "pct_treinamento": _pct(treino_ok_n),
                "pct_regularizado_total": _pct(regularizados_n),
                "prioridade": prioridade,
                "aso_vencidos_renovacao": vencidos.get("funcionarios_pendentes", 0),
            },
            "nota": (
                "Coorte estável = ativos admitidos em 2026 (data_admissao não muda), "
                "por isso a barra sobe sozinha conforme a Márcia regulariza. Cada _ok é "
                "FATO no banco (ASO realizado vigente / ficha de EPI assinada / certificado "
                "de treinamento válido) — nada aqui grava ou fabrica cumprimento."
            ),
            "cursos_obrigatorios": ["NR-1", "Uso de EPI", "Ronda"],
            "descalcos": descalcos,
            "aso_vencidos": vencidos,
        }

    # ================================================================
    # ESTABILIDADE (CCT Clausula 29a)
    # ================================================================

    async def listar_estabilidade_ativos(self) -> list[dict]:
        """Colaboradores com estabilidade ativa pos-acidente (CCT 2026)."""
        hoje = date.today()
        result = await self.db.execute(
            select(Afastamento).where(
                Afastamento.gera_estabilidade.is_(True),
                Afastamento.estabilidade_ate >= hoje,
            )
        )
        return [
            {
                "employee_id": af.employee_id,
                "nome": af.employee_nome,
                "cargo": af.employee_cargo,
                "tipo_afastamento": af.tipo,
                "data_retorno": str(af.data_retorno) if af.data_retorno else None,
                "estabilidade_ate": str(af.estabilidade_ate),
                "dias_restantes": (af.estabilidade_ate - hoje).days,
                "clausula_cct": "29a — Estabilidade 12 meses pos-acidente",
            }
            for af in result.scalars().all()
        ]

    # ================================================================
    # AJUDA MEDICAMENTO (CCT Clausula 15a)
    # ================================================================

    async def listar_ajuda_medicamento_ativos(self) -> list[dict]:
        """Colaboradores recebendo ajuda medicamento R$ 300/mes (CCT 2026)."""
        result = await self.db.execute(
            select(Afastamento).where(
                Afastamento.ajuda_medicamento_ativa.is_(True),
                Afastamento.status == StatusAfastamento.ATIVO,
            )
        )
        return [
            {
                "employee_id": af.employee_id,
                "nome": af.employee_nome,
                "cargo": af.employee_cargo,
                "data_inicio_afastamento": str(af.data_inicio),
                "valor_mensal": float(af.ajuda_medicamento_valor or 0),
                "clausula_cct": "15a — Ajuda medicamento ate R$ 300/mes",
            }
            for af in result.scalars().all()
        ]

    # ================================================================
    # CAT
    # ================================================================

    async def _count_cats_abertas(self) -> int:
        """Conta CATs abertas no banco."""
        try:
            result = await self.db.execute(text("SELECT count(*) FROM gp_cats WHERE status = 'aberta'"))
            return result.scalar() or 0
        except Exception:
            return 0

    # ================================================================
    # HELPERS — CALCULOS REAIS
    # ================================================================

    async def _count_employees(self) -> int:
        """Conta colaboradores ativos."""
        try:
            result = await self.db.execute(text("SELECT count(*) FROM employees WHERE status = 'ativo'"))
            return result.scalar() or 0
        except Exception:
            return 0

    async def _count_afastados_ativos(self) -> int:
        """Conta afastamentos ativos."""
        result = await self.db.execute(
            select(func.count(Afastamento.id)).where(Afastamento.status == StatusAfastamento.ATIVO)
        )
        return result.scalar() or 0

    async def _count_by_cargo(self) -> dict[str, int]:
        """Conta colaboradores ativos agrupados por cargo."""
        try:
            result = await self.db.execute(
                text("SELECT cargo, count(*) FROM employees WHERE status = 'ativo' GROUP BY cargo")
            )
            return {row[0]: row[1] for row in result.fetchall()}
        except Exception:
            return {}

    async def _grau_risco_por_cargo(self) -> list[dict[str, Any]]:
        """Colaboradores ativos agrupados por cargo com grau de risco REAL da CCT.

        Junta employees.cct_cargo_id -> cct_cargos e deriva o grau de risco NR-1
        dos adicionais de periculosidade/insalubridade (fonte unica da CCT).
        Fallback: cargos sem cct_cargo_id vinculado ficam com grau baixo (1).
        """
        try:
            # Insalubridade/periculosidade sao POR FUNCIONARIO (dependem do posto/atividade real,
            # NAO do cargo). Ex.: um ASG que limpa lixeira e insalubre; outro ASG no mesmo cargo nao.
            # Fonte: employees.insalubridade_percentual/periculosidade_percentual (folha real Dominio).
            result = await self.db.execute(
                text(
                    "SELECT COALESCE(cc.cargo_nome, e.cargo) AS cargo, "
                    "COALESCE(e.periculosidade_percentual, 0) AS peric, "
                    "COALESCE(e.insalubridade_percentual, 0) AS insal, "
                    "count(*) AS qtd "
                    "FROM employees e "
                    "LEFT JOIN cct_cargos cc ON cc.id = e.cct_cargo_id "
                    "WHERE e.status = 'ativo' "
                    "GROUP BY 1, 2, 3"
                )
            )
            grupos = []
            for row in result.fetchall():
                peric = float(row[1] or 0)
                insal = float(row[2] or 0)
                grupos.append(
                    {
                        "cargo": row[0],
                        "peric": peric,
                        "insal": insal,
                        "qtd": int(row[3]),
                        "grau": _grau_risco_cct(peric, insal),
                    }
                )
            return grupos
        except Exception as exc:
            logger.debug("grau risco por cargo (CCT): %s", exc)
            return []

    async def _get_pcmso_stats(self) -> dict[str, int]:
        """Estatisticas PCMSO baseadas em dados reais de gp_asos."""
        total = await self._count_employees()
        realizados = 0
        vencidos = 0
        try:
            hoje = date.today()
            # ASOs realizados com validade vigente
            r = await self.db.execute(
                text(
                    "SELECT count(DISTINCT employee_id) FROM gp_asos "
                    "WHERE status = 'realizado' "
                    "AND (data_validade IS NULL OR data_validade >= :hoje)"
                ),
                {"hoje": hoje},
            )
            realizados = r.scalar() or 0

            # ASOs vencidos
            r2 = await self.db.execute(
                text(
                    "SELECT count(DISTINCT employee_id) FROM gp_asos "
                    "WHERE data_validade IS NOT NULL AND data_validade < :hoje "
                    "AND status = 'realizado'"
                ),
                {"hoje": hoje},
            )
            vencidos = r2.scalar() or 0
        except Exception as exc:
            logger.debug("gp_asos stats: %s", exc)

        return {
            "realizados": realizados,
            "vencidos": vencidos,
            "pendentes": max(0, total - realizados),
        }

    async def _get_risk_stats(self) -> dict[str, Any]:
        """Estatisticas de riscos mapeados baseadas em gp_risks."""
        total = 0
        com_medida = 0
        try:
            r = await self.db.execute(text("SELECT count(*) FROM gp_risks"))
            total = r.scalar() or 0

            r2 = await self.db.execute(
                text(
                    "SELECT count(*) FROM gp_risks "
                    "WHERE medidas_controle IS NOT NULL "
                    "AND medidas_controle::text != '[]' "
                    "AND medidas_controle::text != 'null'"
                )
            )
            com_medida = r2.scalar() or 0
        except Exception as exc:
            logger.debug("gp_risks stats: %s", exc)

        sem_medida = max(0, total - com_medida)
        percentual = round(com_medida * 100 / total, 1) if total > 0 else 0

        return {
            "total": total,
            "com_medida": com_medida,
            "sem_medida": sem_medida,
            "percentual": percentual,
        }

    async def _has_riscos_mapeados(self) -> bool:
        """Verifica se existem riscos mapeados."""
        try:
            r = await self.db.execute(text("SELECT count(*) FROM gp_risks"))
            return (r.scalar() or 0) > 0
        except Exception:
            return False

    async def _calcular_indice_nr1(self) -> dict[str, Any]:
        """Calcula indice de risco NR-1 baseado em dados reais da operacao."""
        total = await self._count_employees()
        if total == 0:
            return {"indice": 0, "recomendacoes": []}

        afastados = await self._count_afastados_ativos()
        riscos = await self._get_risk_stats()
        grupos = await self._grau_risco_por_cargo()

        # Fator 1: taxa de afastamento (peso 30%)
        taxa_af = (afastados / total * 100) if total > 0 else 0

        # Fator 2: grau medio de risco por cargo, derivado da CCT (peso 30%)
        grau_total = sum(g["grau"] * g["qtd"] for g in grupos)
        cobertos = sum(g["qtd"] for g in grupos)
        grau_medio = (grau_total / cobertos) if cobertos > 0 else 1
        fator_cargo = (grau_medio / GRAU_RISCO_ALTO) * 100  # normalizado 0-100

        # Fator 3: cobertura de medidas de controle (peso 20%)
        fator_medidas = 100 - riscos["percentual"] if riscos["total"] > 0 else 50

        # Fator 4: cobertura PCMSO (peso 20%)
        pcmso = await self._get_pcmso_stats()
        cobertura_pcmso = (pcmso["realizados"] / total * 100) if total > 0 else 0
        fator_pcmso = 100 - cobertura_pcmso

        # Indice ponderado
        indice = round(
            taxa_af * 0.30 + fator_cargo * 0.30 + fator_medidas * 0.20 + fator_pcmso * 0.20,
            1,
        )
        indice = min(100, max(0, indice))

        # Recomendacoes dinamicas
        recomendacoes = []
        if pcmso["pendentes"] > 0:
            recomendacoes.append(f"Agendar exames periodicos para {pcmso['pendentes']} colaboradores")
        if riscos["sem_medida"] > 0:
            recomendacoes.append(f"Implementar medidas de controle para {riscos['sem_medida']} riscos pendentes")
        if afastados > 0:
            recomendacoes.append(f"Monitorar {afastados} colaboradores afastados (retorno e reabilitacao)")
        if not recomendacoes:
            recomendacoes.append("Manter programa de prevencao ativo")

        return {"indice": indice, "recomendacoes": recomendacoes}

    # ================================================================
    # NR-1 COMPLIANCE — painel "calçado" por funcionário (dados REAIS)
    # ================================================================

    async def get_nr1_compliance(self) -> dict[str, Any]:
        """Painel NR-1 por funcionário ativo — score HONESTO por fatos no banco.

        Checks aplicáveis por funcionário:
        1. ASO em dia (gp_asos: último ASO com data_validade >= hoje)
        2. EPIs com ficha ASSINADA (gp_epi_deliveries → sst_fichas_epi.status)
        3. Exposição a riscos mapeada (gp_risks — mapa vigente; o vínculo por
           posto NÃO é resolvível hoje: gp_risks.posto_id não casa com posts/
           condominios, limitação declarada, não mascarada)
        4. Treinamentos NR (sst_treinamentos): em dia = treinamento NR-1 com
           vencimento válido; vencido/sem registro = pendência (entra no score).
        """
        hoje = date.today()

        employees = (
            await self.db.execute(
                text("SELECT id, nome, cargo FROM employees WHERE status = 'ativo' ORDER BY nome")
            )
        ).mappings().all()

        # Último ASO por funcionário (validade mais recente)
        asos = (
            await self.db.execute(
                text(
                    "SELECT DISTINCT ON (employee_id) employee_id, data_validade, status, tipo "
                    "FROM gp_asos "
                    "ORDER BY employee_id, data_validade DESC NULLS LAST"
                )
            )
        ).mappings().all()
        aso_por_emp = {str(a["employee_id"]): dict(a) for a in asos}

        # Entregas de EPI × fichas assinadas
        epis = (
            await self.db.execute(
                text(
                    "SELECT d.employee_id::text AS eid, "
                    "count(*) AS entregas, "
                    "count(*) FILTER (WHERE f.status = 'assinada') AS com_ficha_assinada, "
                    "count(*) FILTER (WHERE d.ficha_epi_id IS NULL) AS sem_ficha "
                    "FROM gp_epi_deliveries d "
                    "LEFT JOIN sst_fichas_epi f ON f.id = d.ficha_epi_id "
                    "GROUP BY d.employee_id"
                )
            )
        ).mappings().all()
        epi_por_emp = {e["eid"]: dict(e) for e in epis}

        # Mapa de riscos vigente (global — posto_id sem FK resolvível, honesto)
        riscos_ativos = (
            await self.db.execute(text("SELECT count(*) FROM gp_risks WHERE status <> 'encerrado'"))
        ).scalar() or 0

        # Treinamentos NR (sst_treinamentos): 4º pilar — em dia = NR-1 válido.
        # Guard mantido só para ambientes ainda sem a migração 2026-07-08.
        treino_tabela = (
            await self.db.execute(text("SELECT to_regclass('sst_treinamentos')::text"))
        ).scalar()
        treino_por_emp: dict[str, dict[str, Any]] = {}
        if treino_tabela:
            treinos_rows = (
                await self.db.execute(
                    text(
                        "SELECT employee_id::text AS eid, count(*) AS total, "
                        "max(vencimento) FILTER (WHERE norma = 'NR-1') AS nr1_vencimento "
                        "FROM sst_treinamentos GROUP BY employee_id"
                    )
                )
            ).mappings().all()
            treino_por_emp = {t["eid"]: dict(t) for t in treinos_rows}

        funcionarios: list[dict[str, Any]] = []
        calcados = 0
        asos_vencidos_func = 0
        treinos_nr1_validos = 0
        for emp in employees:
            eid = str(emp["id"])
            checks: dict[str, Any] = {}

            # 1. ASO
            aso = aso_por_emp.get(eid)
            if not aso or not aso.get("data_validade"):
                checks["aso"] = {"ok": False, "situacao": "sem_aso", "data_validade": None}
            elif aso["data_validade"] >= hoje:
                checks["aso"] = {
                    "ok": True, "situacao": "em_dia", "data_validade": str(aso["data_validade"]),
                }
            else:
                checks["aso"] = {
                    "ok": False, "situacao": "vencido", "data_validade": str(aso["data_validade"]),
                }
                asos_vencidos_func += 1

            # 2. EPI com ficha assinada
            epi = epi_por_emp.get(eid)
            if not epi:
                checks["epi"] = {
                    "ok": False, "situacao": "sem_entrega_registrada",
                    "entregas": 0, "com_ficha_assinada": 0,
                }
            else:
                ok = epi["entregas"] > 0 and epi["com_ficha_assinada"] == epi["entregas"]
                situacao = "fichas_assinadas" if ok else (
                    "sem_ficha" if epi["sem_ficha"] == epi["entregas"] else "ficha_pendente"
                )
                checks["epi"] = {
                    "ok": ok, "situacao": situacao,
                    "entregas": epi["entregas"],
                    "com_ficha_assinada": epi["com_ficha_assinada"],
                }

            # 3. Riscos mapeados (mapa global vigente — limitação de vínculo declarada)
            checks["riscos"] = {
                "ok": riscos_ativos > 0,
                "situacao": "mapa_vigente" if riscos_ativos > 0 else "sem_mapa",
                "fonte": "gp_risks (mapa global — vínculo por posto não resolvível hoje)",
            }

            # 4. Treinamentos NR — em dia = tem treinamento NR-1 com vencimento válido
            if treino_tabela:
                treino = treino_por_emp.get(eid)
                nr1_venc = treino.get("nr1_vencimento") if treino else None
                if nr1_venc and nr1_venc >= hoje:
                    checks["treinamentos"] = {
                        "ok": True, "situacao": "nr1_em_dia",
                        "nr1_vencimento": str(nr1_venc), "registros": treino["total"],
                    }
                elif nr1_venc:
                    checks["treinamentos"] = {
                        "ok": False, "situacao": "nr1_vencido",
                        "nr1_vencimento": str(nr1_venc), "registros": treino["total"],
                    }
                elif treino:
                    checks["treinamentos"] = {
                        "ok": False, "situacao": "sem_treinamento_nr1",
                        "nr1_vencimento": None, "registros": treino["total"],
                        "nota": "Há treinamentos registrados, mas nenhum NR-1",
                    }
                else:
                    checks["treinamentos"] = {
                        "ok": False, "situacao": "sem_treinamento",
                        "nr1_vencimento": None, "registros": 0,
                    }
            else:
                checks["treinamentos"] = {
                    "ok": None, "situacao": "sem_fonte",
                    "nota": "Sem tabela de treinamentos NR no banco — item não avaliado (não entra no score)",
                }

            if checks["treinamentos"].get("ok") is True:
                treinos_nr1_validos += 1

            aplicaveis = [c for c in checks.values() if c["ok"] is not None]
            ok_count = sum(1 for c in aplicaveis if c["ok"])
            score = round(ok_count / len(aplicaveis) * 100) if aplicaveis else 0
            calcado = bool(aplicaveis) and ok_count == len(aplicaveis)
            if calcado:
                calcados += 1

            funcionarios.append(
                {
                    "employee_id": eid,
                    "nome": emp["nome"],
                    "cargo": emp["cargo"],
                    "checks": checks,
                    "score": score,
                    "calcado": calcado,
                }
            )

        # ASOs vencidos TOTAIS (todas as linhas, pendência visível — inclui históricos)
        asos_vencidos_total = (
            await self.db.execute(
                text("SELECT count(*) FROM gp_asos WHERE data_validade < CURRENT_DATE")
            )
        ).scalar() or 0
        fichas_pendentes = (
            await self.db.execute(
                text("SELECT count(*) FROM sst_fichas_epi WHERE status = 'pendente_assinatura'")
            )
        ).scalar() or 0
        entregas_sem_ficha = (
            await self.db.execute(
                text("SELECT count(*) FROM gp_epi_deliveries WHERE ficha_epi_id IS NULL")
            )
        ).scalar() or 0

        return {
            "resumo": {
                "total_funcionarios_ativos": len(employees),
                "calcados": calcados,
                "descalcados": len(employees) - calcados,
                "asos_vencidos_registros": asos_vencidos_total,
                "funcionarios_aso_vencido": asos_vencidos_func,
                "fichas_epi_pendentes_assinatura": fichas_pendentes,
                "entregas_epi_sem_ficha": entregas_sem_ficha,
                "riscos_mapeados_vigentes": riscos_ativos,
                "treinamentos_fonte": treino_tabela or "sem_tabela",
                "funcionarios_nr1_treinamento_valido": treinos_nr1_validos,
                "funcionarios_nr1_treinamento_pendente": len(employees) - treinos_nr1_validos,
            },
            "funcionarios": funcionarios,
        }

    # ================================================================
    # PRONTUÁRIO SST 360 — dossiê completo por funcionário
    # ================================================================

    async def get_prontuario(self, employee_id: str) -> dict[str, Any] | None:
        """Prontuário SST 360 — TUDO de saúde ocupacional de um funcionário.

        O dossiê que se abre quando o fiscal pergunta "me mostra o do João".
        Cada bloco é isolado em try/except: um domínio falho não derruba o
        prontuário (vem com {"erro": ...} honesto no bloco). Todo bloco carrega
        `fonte` (tabela real) e vazios são declarados, nunca mascarados.
        """
        hoje = date.today()

        # Identificação (bloco raiz — se o funcionário não existe, 404 no controller)
        emp = (
            await self.db.execute(
                text(
                    "SELECT id, nome, cpf, matricula, cargo, data_admissao, "
                    "data_demissao, status FROM employees WHERE id::text = :eid"
                ),
                {"eid": str(employee_id)},
            )
        ).mappings().first()
        if not emp:
            return None
        eid = str(emp["id"])

        prontuario: dict[str, Any] = {
            "gerado_em": str(hoje),
            "identificacao": {
                "fonte": "employees + allocations→posts",
                "employee_id": eid,
                "nome": emp["nome"],
                "cpf": emp["cpf"],
                "matricula": emp["matricula"],
                "cargo": emp["cargo"],
                "data_admissao": str(emp["data_admissao"]) if emp["data_admissao"] else None,
                "data_demissao": str(emp["data_demissao"]) if emp["data_demissao"] else None,
                "status": emp["status"],
                "posto_atual": None,  # preenchido abaixo (allocations ativas → posts)
            },
        }

        # --- Posto atual (allocations ativas → posts) --------------------
        try:
            posto = (
                await self.db.execute(
                    text(
                        """
                        SELECT p.id AS posto_id, p.name AS posto_nome
                        FROM allocations al
                        JOIN posts p ON p.id = al.post_id
                        WHERE al.employee_id::text = :eid
                          AND al.is_active = true AND al.status = 'active'
                          AND (al.end_date IS NULL OR al.end_date >= CURRENT_DATE)
                        ORDER BY al.is_primary DESC, al.start_date DESC
                        LIMIT 1
                        """
                    ),
                    {"eid": eid},
                )
            ).mappings().first()
            prontuario["identificacao"]["posto_atual"] = (
                {"posto_id": str(posto["posto_id"]), "nome": posto["posto_nome"]}
                if posto
                else None  # honesto: sem alocação ativa
            )
        except Exception as exc:
            logger.warning("Prontuário %s: bloco posto falhou: %s", eid, exc)
            prontuario["identificacao"]["posto_atual_erro"] = str(exc)

        # --- Compliance NR-1 (os 4 checks + score) ------------------------
        try:
            compliance = await self.get_nr1_compliance()
            meu = next(
                (f for f in compliance.get("funcionarios", []) if f["employee_id"] == eid),
                None,
            )
            if meu:
                prontuario["compliance"] = {
                    "fonte": "get_nr1_compliance (gp_asos + gp_epi_deliveries/sst_fichas_epi + gp_risks + sst_treinamentos)",
                    "score": meu["score"],
                    "calcado": meu["calcado"],
                    "checks": meu["checks"],
                }
            else:
                prontuario["compliance"] = {
                    "fonte": "get_nr1_compliance",
                    "score": None,
                    "calcado": None,
                    "checks": None,
                    "nota": "Funcionário fora do painel NR-1 (painel avalia apenas status='ativo')",
                }
        except Exception as exc:
            logger.warning("Prontuário %s: bloco compliance falhou: %s", eid, exc)
            prontuario["compliance"] = {"fonte": "get_nr1_compliance", "erro": str(exc)}

        # --- ASOs (histórico + próximo vencimento) ------------------------
        try:
            asos = (
                await self.db.execute(
                    text(
                        "SELECT aso_id, tipo, status, data_agendamento, data_realizacao, "
                        "data_validade, clinica, medico, crm, apto, exames, "
                        "esocial_status, recibo_s2220 "
                        "FROM gp_asos WHERE employee_id::text = :eid "
                        "ORDER BY COALESCE(data_realizacao, data_agendamento) DESC NULLS LAST"
                    ),
                    {"eid": eid},
                )
            ).mappings().all()
            historico = []
            proximo_vencimento: str | None = None
            for a in asos:
                historico.append(
                    {
                        "aso_id": a["aso_id"],
                        "tipo": str(a["tipo"]) if a["tipo"] else None,
                        "status": str(a["status"]) if a["status"] else None,
                        "data_agendamento": str(a["data_agendamento"]) if a["data_agendamento"] else None,
                        "data_realizacao": str(a["data_realizacao"]) if a["data_realizacao"] else None,
                        "data_validade": str(a["data_validade"]) if a["data_validade"] else None,
                        "vencido": bool(a["data_validade"] and a["data_validade"] < hoje),
                        "clinica": a["clinica"],
                        "medico": a["medico"],
                        "crm": a["crm"],
                        "apto": a["apto"],
                        "exames": a["exames"],
                        "esocial_status": a["esocial_status"],
                        "recibo_s2220": a["recibo_s2220"],
                    }
                )
            validades = [a["data_validade"] for a in asos if a["data_validade"]]
            if validades:
                proximo_vencimento = str(max(validades))
            prontuario["asos"] = {
                "fonte": "gp_asos",
                "total": len(historico),
                "proximo_vencimento": proximo_vencimento,
                "vencido": bool(validades) and max(validades) < hoje,
                "historico": historico,
            }
        except Exception as exc:
            logger.warning("Prontuário %s: bloco ASOs falhou: %s", eid, exc)
            prontuario["asos"] = {"fonte": "gp_asos", "erro": str(exc)}

        # --- EPIs (entregas + fichas c/ status de assinatura) --------------
        try:
            entregas = (
                await self.db.execute(
                    text(
                        "SELECT d.delivery_id, d.epi_nome, d.epi_ca, d.quantidade, d.nr, "
                        "d.data_entrega, d.data_validade, d.data_devolucao, "
                        "d.ficha_epi_id::text AS ficha_epi_id, f.status AS ficha_status "
                        "FROM gp_epi_deliveries d "
                        "LEFT JOIN sst_fichas_epi f ON f.id = d.ficha_epi_id "
                        "WHERE d.employee_id::text = :eid ORDER BY d.data_entrega DESC"
                    ),
                    {"eid": eid},
                )
            ).mappings().all()
            fichas = (
                await self.db.execute(
                    text(
                        "SELECT id::text AS ficha_id, status, itens, assinatura_hash, "
                        "assinado_em, created_at "
                        "FROM sst_fichas_epi WHERE employee_id::text = :eid "
                        "ORDER BY created_at DESC"
                    ),
                    {"eid": eid},
                )
            ).mappings().all()
            prontuario["epis"] = {
                "fonte": "gp_epi_deliveries + sst_fichas_epi",
                "total_entregas": len(entregas),
                "entregas": [
                    {
                        "delivery_id": e["delivery_id"],
                        "epi_nome": e["epi_nome"],
                        "ca": e["epi_ca"],
                        "quantidade": e["quantidade"],
                        "nr": e["nr"],
                        "data_entrega": str(e["data_entrega"]) if e["data_entrega"] else None,
                        "data_validade": str(e["data_validade"]) if e["data_validade"] else None,
                        "data_devolucao": str(e["data_devolucao"]) if e["data_devolucao"] else None,
                        "ficha_epi_id": e["ficha_epi_id"],
                        "ficha_status": e["ficha_status"] or ("sem_ficha" if not e["ficha_epi_id"] else None),
                    }
                    for e in entregas
                ],
                "total_fichas": len(fichas),
                "fichas_assinadas": sum(1 for f in fichas if f["status"] == "assinada"),
                "fichas": [
                    {
                        "ficha_id": f["ficha_id"],
                        "status": f["status"],
                        "itens": f["itens"] or [],
                        "assinatura_hash": f["assinatura_hash"],
                        "assinado_em": f["assinado_em"].isoformat() if f["assinado_em"] else None,
                        "created_at": f["created_at"].isoformat() if f["created_at"] else None,
                    }
                    for f in fichas
                ],
            }
        except Exception as exc:
            logger.warning("Prontuário %s: bloco EPIs falhou: %s", eid, exc)
            prontuario["epis"] = {"fonte": "gp_epi_deliveries + sst_fichas_epi", "erro": str(exc)}

        # --- Riscos da FUNÇÃO (PGR GES — gp_risks.funcoes_aplicaveis) -------
        try:
            from modules.people_management.hr.services.esocial_service import (
                _cargo_token,
                _json_list,
            )

            token = _cargo_token(emp["cargo"])
            riscos_rows = (
                await self.db.execute(
                    text(
                        "SELECT risk_id, categoria, descricao, nivel, fonte_geradora, "
                        "medidas_controle, epi_recomendado, status, cod_agente_nocivo, "
                        "utiliz_epc, utiliz_epi, medicao, funcoes_aplicaveis "
                        "FROM gp_risks WHERE COALESCE(status,'') <> 'encerrado'"
                    )
                )
            ).mappings().all()
            da_funcao = []
            for r in riscos_rows:
                if token and token in _json_list(r["funcoes_aplicaveis"]):
                    da_funcao.append(
                        {
                            "risk_id": r["risk_id"],
                            "categoria": r["categoria"],
                            "descricao": r["descricao"],
                            "nivel": r["nivel"],
                            "fonte_geradora": r["fonte_geradora"],
                            "medidas_controle": _json_list(r["medidas_controle"]),
                            "epi_recomendado": _json_list(r["epi_recomendado"]),
                            "cod_agente_nocivo": r["cod_agente_nocivo"],
                            "utiliz_epc": r["utiliz_epc"],
                            "utiliz_epi": r["utiliz_epi"],
                            "medicao": r["medicao"],
                            "status": r["status"],
                        }
                    )
            prontuario["riscos_funcao"] = {
                "fonte": "gp_risks.funcoes_aplicaveis (PGR MBS Engenharia — GES por função) + Tabela 24 eSocial",
                "cargo": emp["cargo"],
                "funcao_token": token,
                "total": len(da_funcao),
                "riscos": da_funcao,
                **(
                    {"nota": "Cargo não mapeado no PGR (sem token de função) — nenhum risco atribuível"}
                    if not token
                    else {}
                ),
            }
        except Exception as exc:
            logger.warning("Prontuário %s: bloco riscos falhou: %s", eid, exc)
            prontuario["riscos_funcao"] = {"fonte": "gp_risks", "erro": str(exc)}

        # --- Treinamentos NR (c/ vencimentos) -------------------------------
        try:
            treinos = (
                await self.db.execute(
                    text(
                        "SELECT id::text AS id, norma, descricao, data_realizacao, "
                        "validade_meses, vencimento, certificado_path, created_by "
                        "FROM sst_treinamentos WHERE employee_id::text = :eid "
                        "ORDER BY vencimento DESC"
                    ),
                    {"eid": eid},
                )
            ).mappings().all()
            prontuario["treinamentos"] = {
                "fonte": "sst_treinamentos",
                "total": len(treinos),
                "treinamentos": [
                    {
                        "id": t["id"],
                        "norma": t["norma"],
                        "descricao": t["descricao"],
                        "data_realizacao": str(t["data_realizacao"]),
                        "validade_meses": t["validade_meses"],
                        "vencimento": str(t["vencimento"]),
                        "situacao": self._situacao_treinamento(t["vencimento"], hoje),
                        "certificado_path": t["certificado_path"],
                        "created_by": t["created_by"],
                    }
                    for t in treinos
                ],
            }
        except Exception as exc:
            logger.warning("Prontuário %s: bloco treinamentos falhou: %s", eid, exc)
            prontuario["treinamentos"] = {"fonte": "sst_treinamentos", "erro": str(exc)}

        # --- Afastamentos (c/ estabilidade + status eSocial S-2230) ---------
        try:
            afs = (
                await self.db.execute(
                    text(
                        "SELECT id::text AS id, tipo, motivo, data_inicio, data_fim_prevista, "
                        "data_retorno, dias_previstos, cid, medico, crm, status, "
                        "gera_estabilidade, estabilidade_ate, ajuda_medicamento_ativa, "
                        "esocial_status, recibo_s2230, esocial_protocolo "
                        "FROM sst_afastamentos WHERE employee_id::text = :eid "
                        "ORDER BY data_inicio DESC"
                    ),
                    {"eid": eid},
                )
            ).mappings().all()
            estabilidade_vigente = next(
                (
                    str(a["estabilidade_ate"])
                    for a in afs
                    if a["gera_estabilidade"] and a["estabilidade_ate"] and a["estabilidade_ate"] >= hoje
                ),
                None,
            )
            prontuario["afastamentos"] = {
                "fonte": "sst_afastamentos (CCT Cláusula 29ª + eSocial S-2230)",
                "total": len(afs),
                "estabilidade_vigente_ate": estabilidade_vigente,
                "afastamentos": [
                    {
                        "id": a["id"],
                        "tipo": a["tipo"],
                        "motivo": a["motivo"],
                        "data_inicio": str(a["data_inicio"]),
                        "data_fim_prevista": str(a["data_fim_prevista"]) if a["data_fim_prevista"] else None,
                        "data_retorno": str(a["data_retorno"]) if a["data_retorno"] else None,
                        "dias_previstos": a["dias_previstos"],
                        "cid": a["cid"],
                        "medico": a["medico"],
                        "crm": a["crm"],
                        "status": a["status"],
                        "gera_estabilidade": a["gera_estabilidade"],
                        "estabilidade_ate": str(a["estabilidade_ate"]) if a["estabilidade_ate"] else None,
                        "ajuda_medicamento_ativa": a["ajuda_medicamento_ativa"],
                        "esocial_status": a["esocial_status"],
                        "recibo_s2230": a["recibo_s2230"],
                        "esocial_protocolo": a["esocial_protocolo"],
                    }
                    for a in afs
                ],
            }
        except Exception as exc:
            logger.warning("Prontuário %s: bloco afastamentos falhou: %s", eid, exc)
            prontuario["afastamentos"] = {"fonte": "sst_afastamentos", "erro": str(exc)}

        # --- CATs (c/ recibos eSocial S-2210) --------------------------------
        try:
            cats = (
                await self.db.execute(
                    text(
                        "SELECT cat_id, tipo_acidente, data_acidente, hora_acidente, local, "
                        "descricao, gravidade, parte_corpo, agente_causador, afastamento, "
                        "numero_cat_inss, status, esocial_status, numero_recibo_esocial, "
                        "esocial_protocolo, esocial_transmitida_em "
                        "FROM gp_cats WHERE employee_id::text = :eid ORDER BY data_acidente DESC"
                    ),
                    {"eid": eid},
                )
            ).mappings().all()
            prontuario["cats"] = {
                "fonte": "gp_cats (eSocial S-2210)",
                "total": len(cats),
                "cats": [
                    {
                        "cat_id": c["cat_id"],
                        "tipo_acidente": c["tipo_acidente"],
                        "data_acidente": str(c["data_acidente"]),
                        "hora_acidente": c["hora_acidente"],
                        "local": c["local"],
                        "descricao": c["descricao"],
                        "gravidade": c["gravidade"],
                        "parte_corpo": c["parte_corpo"],
                        "agente_causador": c["agente_causador"],
                        "afastamento_dias": c["afastamento"],
                        "numero_cat_inss": c["numero_cat_inss"],
                        "status": c["status"],
                        "esocial_status": c["esocial_status"],
                        "recibo_esocial": c["numero_recibo_esocial"],
                        "esocial_protocolo": c["esocial_protocolo"],
                        "esocial_transmitida_em": (
                            c["esocial_transmitida_em"].isoformat()
                            if c["esocial_transmitida_em"]
                            else None
                        ),
                    }
                    for c in cats
                ],
            }
        except Exception as exc:
            logger.warning("Prontuário %s: bloco CATs falhou: %s", eid, exc)
            prontuario["cats"] = {"fonte": "gp_cats", "erro": str(exc)}

        return prontuario

    @staticmethod
    def _afastamento_to_dict(af: Afastamento) -> dict:
        """Converte Afastamento para dict."""
        return {
            "id": af.id,
            "employee_id": af.employee_id,
            "employee_nome": af.employee_nome,
            "employee_cargo": af.employee_cargo,
            "tipo": af.tipo,
            "motivo": af.motivo,
            "data_inicio": str(af.data_inicio),
            "data_fim_prevista": str(af.data_fim_prevista) if af.data_fim_prevista else None,
            "data_retorno": str(af.data_retorno) if af.data_retorno else None,
            "dias_previstos": af.dias_previstos,
            "atestado": af.atestado,
            "cid": af.cid,
            "medico": af.medico,
            "crm": af.crm,
            "status": af.status,
            "ajuda_medicamento_ativa": af.ajuda_medicamento_ativa,
            "ajuda_medicamento_valor": (float(af.ajuda_medicamento_valor) if af.ajuda_medicamento_valor else None),
            "gera_estabilidade": af.gera_estabilidade,
            "estabilidade_ate": str(af.estabilidade_ate) if af.estabilidade_ate else None,
            # eSocial S-2230 — status/recibo/protocolo REAIS (nunca fabricados)
            "esocial_status": af.esocial_status,
            "recibo_s2230": af.recibo_s2230,
            "esocial_protocolo": af.esocial_protocolo,
        }


def _deve_gerar_estabilidade(tipo: str, cid: str | None) -> bool:
    """Verifica se o afastamento gera estabilidade (CCT Clausula 29a)."""
    if tipo in TIPOS_COM_ESTABILIDADE:
        return True
    if cid and cid[0].upper() in CID_ACIDENTE_PREFIXOS:
        return True
    return False
