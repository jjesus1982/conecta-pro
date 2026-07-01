"""
SST Agent - Saude e Seguranca do Trabalho.
PCMSO, PPRA/PGR, EPIs, CIPA, laudos, CAT.
"""

import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from ..core.events import Event, EventPriority, GPEventTypes
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class HealthSkill:
    """Gestao de ASOs e exames ocupacionais."""

    TIPOS_ASO = [
        "admissional",
        "periodico",
        "demissional",
        "retorno_trabalho",
        "mudanca_funcao",
    ]

    VALIDADE_DIAS = {
        "admissional": 0,  # Valido apenas para admissao
        "periodico": 365,  # Anual (pode ser semestral para riscos)
        "demissional": 0,
        "retorno_trabalho": 0,
        "mudanca_funcao": 0,
    }

    def agendar_aso(
        self,
        employee_id: str,
        tipo: str,
        data_agendamento: str,
        clinica: str = "",
    ) -> dict[str, Any]:
        if tipo not in self.TIPOS_ASO:
            raise ValueError(f"Tipo ASO invalido: {tipo}")

        return {
            "aso_id": str(uuid4()),
            "employee_id": employee_id,
            "tipo": tipo,
            "data_agendamento": data_agendamento,
            "clinica": clinica,
            "status": "agendado",
            "resultado": None,
        }

    def registrar_resultado(
        self,
        aso_id: str,
        apto: bool,
        restricoes: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "aso_id": aso_id,
            "apto": apto,
            "restricoes": restricoes or [],
            "realizado_em": datetime.utcnow().isoformat(),
            "status": "realizado",
        }

    def verificar_vencimentos(
        self,
        asos: list[dict[str, Any]],
        dias_antecedencia: int = 30,
    ) -> list[dict[str, Any]]:
        """Verifica ASOs que vao vencer nos proximos X dias."""
        vencendo = []
        hoje = datetime.utcnow().date()
        for aso in asos:
            if aso.get("tipo") == "periodico" and aso.get("realizado_em"):
                realizado = datetime.fromisoformat(aso["realizado_em"]).date()
                vencimento = realizado + timedelta(days=self.VALIDADE_DIAS["periodico"])
                dias_restantes = (vencimento - hoje).days
                if 0 <= dias_restantes <= dias_antecedencia:
                    vencendo.append(
                        {
                            "aso_id": aso.get("aso_id"),
                            "employee_id": aso.get("employee_id"),
                            "vencimento": vencimento.isoformat(),
                            "dias_restantes": dias_restantes,
                        }
                    )
        return vencendo


class SafetySkill:
    """Gestao de EPIs e NRs."""

    EPIS_VIGILANCIA = [
        {"nome": "Colete balistico", "validade_meses": 60, "nr": "NR-6"},
        {"nome": "Coturno", "validade_meses": 12, "nr": "NR-6"},
        {"nome": "Lanterna tatica", "validade_meses": 24, "nr": "NR-6"},
        {"nome": "Radio comunicador", "validade_meses": 36, "nr": "NR-6"},
        {"nome": "Capa de chuva", "validade_meses": 12, "nr": "NR-6"},
    ]

    def registrar_entrega_epi(
        self,
        employee_id: str,
        epi_nome: str,
        quantidade: int = 1,
    ) -> dict[str, Any]:
        epi_config = next((e for e in self.EPIS_VIGILANCIA if e["nome"] == epi_nome), None)
        validade_meses = epi_config["validade_meses"] if epi_config else 12

        return {
            "entrega_id": str(uuid4()),
            "employee_id": employee_id,
            "epi": epi_nome,
            "quantidade": quantidade,
            "data_entrega": datetime.utcnow().isoformat(),
            "validade_ate": (datetime.utcnow() + timedelta(days=validade_meses * 30)).isoformat(),
            "nr": epi_config["nr"] if epi_config else "NR-6",
            "status": "entregue",
        }


class AccidentSkill:
    """CAT e investigacao de acidentes."""

    def abrir_cat(
        self,
        employee_id: str,
        tipo_acidente: str,
        descricao: str,
        data_acidente: str,
        local: str,
        testemunhas: list[str] | None = None,
        gravidade: str = "leve",
    ) -> dict[str, Any]:
        return {
            "cat_id": str(uuid4()),
            "employee_id": employee_id,
            "tipo": tipo_acidente,
            "descricao": descricao,
            "data_acidente": data_acidente,
            "local": local,
            "testemunhas": testemunhas or [],
            "gravidade": gravidade,
            "status": "aberta",
            "created_at": datetime.utcnow().isoformat(),
        }


class RiskSkill:
    """PPRA/PGR e mapeamento de riscos."""

    CATEGORIAS_RISCO = [
        "fisico",
        "quimico",
        "biologico",
        "ergonomico",
        "acidente",
    ]

    def mapear_risco(
        self,
        posto_id: str,
        categoria: str,
        descricao: str,
        nivel: str = "medio",
    ) -> dict[str, Any]:
        if categoria not in self.CATEGORIAS_RISCO:
            raise ValueError(f"Categoria de risco invalida: {categoria}")
        return {
            "risco_id": str(uuid4()),
            "posto_id": posto_id,
            "categoria": categoria,
            "descricao": descricao,
            "nivel": nivel,
            "medidas_controle": [],
            "status": "identificado",
        }


class SSTAgent(BaseAgent):
    """Agent de Saude e Seguranca do Trabalho."""

    AGENT_NAME = "SST_AGENT"
    AGENT_VERSION = "1.0.0"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.register_skill("HEALTH", HealthSkill())
        self.register_skill("SAFETY", SafetySkill())
        self.register_skill("ACCIDENT", AccidentSkill())
        self.register_skill("RISK", RiskSkill())

    @property
    def handled_events(self) -> list[str]:
        return [
            GPEventTypes.FUNCIONARIO_ADMITIDO,
            GPEventTypes.FUNCIONARIO_DEMITIDO,
            GPEventTypes.OCORRENCIA_REGISTRADA,
            GPEventTypes.EPI_ENTREGUE,
        ]

    async def _process_event(self, event: Event) -> None:
        handlers = {
            GPEventTypes.FUNCIONARIO_ADMITIDO: self._on_admitido,
            GPEventTypes.FUNCIONARIO_DEMITIDO: self._on_demitido,
            GPEventTypes.OCORRENCIA_REGISTRADA: self._on_ocorrencia,
        }
        handler = handlers.get(event.event_type)
        if handler:
            await handler(event)

    async def _on_admitido(self, event: Event) -> None:
        employee_id = event.payload.get("employee_id")
        logger.info(f"SST: Agendando ASO admissional para {employee_id}")
        health = self.get_skill("HEALTH")
        aso = health.agendar_aso(employee_id, "admissional", datetime.utcnow().isoformat())
        await self.emit_event(
            event_type=GPEventTypes.ASO_AGENDADO,
            payload=aso,
            affected_modules=["DP", "PORTAL"],
        )

    async def _on_demitido(self, event: Event) -> None:
        employee_id = event.payload.get("employee_id")
        logger.info(f"SST: Agendando ASO demissional para {employee_id}")
        health = self.get_skill("HEALTH")
        health.agendar_aso(employee_id, "demissional", datetime.utcnow().isoformat())

    async def _on_ocorrencia(self, event: Event) -> None:
        if event.payload.get("tipo") == "acidente_trabalho":
            accident = self.get_skill("ACCIDENT")
            cat = accident.abrir_cat(
                employee_id=event.payload.get("employee_id", ""),
                tipo_acidente="tipico",
                descricao=event.payload.get("descricao", "Acidente de trabalho"),
                data_acidente=datetime.utcnow().isoformat(),
                local=event.payload.get("local", ""),
                gravidade=event.payload.get("gravidade", "leve"),
            )
            await self.emit_event(
                event_type=GPEventTypes.CAT_ABERTA,
                payload=cat,
                priority=EventPriority.CRITICO,
                affected_modules=["DP", "GED", "OPS", "PORTAL"],
            )
