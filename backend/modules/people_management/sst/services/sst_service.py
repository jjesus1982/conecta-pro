"""Service SST — Wiring real com banco de dados, CCT 2026 e dados reais."""

import logging
from datetime import date, datetime, timedelta
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

        # CCT Clausula 29a: acidente de trabalho gera estabilidade 12 meses
        gera_estab = _deve_gerar_estabilidade(tipo, cid)
        estab_ate = None
        if gera_estab and data_fim:
            estab_ate = data_fim + timedelta(days=CCT_ESTABILIDADE_MESES * 30)

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

        # Recalcular estabilidade CCT com data real de retorno
        if af.gera_estabilidade:
            af.estabilidade_ate = dt_retorno + timedelta(days=CCT_ESTABILIDADE_MESES * 30)

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
        """Status do PCMSO calculado a partir de dados reais (gp_asos)."""
        total = await self._count_employees()
        stats = await self._get_pcmso_stats()

        percentual = round(stats["realizados"] * 100 / total, 1) if total > 0 else 0

        return {
            "programa": "PCMSO — Programa de Controle Medico de Saude Ocupacional",
            "obrigatorio_cct": True,
            "clausula_cct": "23a — SINDECOMPRESTS/SINDICOND-AM 2026",
            "vigente": stats["realizados"] > 0,
            "coordenador": "Dr. Medico do Trabalho",
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
        """Colaboradores sem ASO periodico vigente."""
        sem_aso = []
        try:
            result = await self.db.execute(
                text(
                    "SELECT e.id, e.nome, e.cargo FROM employees e "
                    "WHERE e.status = 'ativo' "
                    "AND NOT EXISTS (SELECT 1 FROM gp_asos a WHERE a.employee_id = e.id::text "
                    "AND a.tipo = 'periodico' AND a.status = 'realizado') "
                    "ORDER BY e.nome"
                )
            )
            for row in result.fetchall():
                sem_aso.append({"employee_id": str(row[0]), "nome": row[1], "cargo": row[2]})
        except Exception as exc:
            logger.debug("Consulta sem ASO: %s", exc)
        return sem_aso

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
            "status": af.status,
            "ajuda_medicamento_ativa": af.ajuda_medicamento_ativa,
            "ajuda_medicamento_valor": (float(af.ajuda_medicamento_valor) if af.ajuda_medicamento_valor else None),
            "gera_estabilidade": af.gera_estabilidade,
            "estabilidade_ate": str(af.estabilidade_ate) if af.estabilidade_ate else None,
        }


def _deve_gerar_estabilidade(tipo: str, cid: str | None) -> bool:
    """Verifica se o afastamento gera estabilidade (CCT Clausula 29a)."""
    if tipo in TIPOS_COM_ESTABILIDADE:
        return True
    if cid and cid[0].upper() in CID_ACIDENTE_PREFIXOS:
        return True
    return False
