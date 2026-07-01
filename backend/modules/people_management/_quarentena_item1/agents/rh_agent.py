"""
RH Agent - Recursos Humanos.
Recrutamento, treinamento, avaliacao, desenvolvimento.
"""

import logging
from datetime import datetime
from typing import Any
from uuid import uuid4

from ..core.events import Event, GPEventTypes
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class RecruiterSkill:
    """Recrutamento e selecao."""

    ETAPAS_SELECAO = [
        "triagem_curriculo",
        "entrevista_rh",
        "teste_tecnico",
        "entrevista_gestor",
        "exame_admissional",
        "documentacao",
        "aprovado",
    ]

    def criar_vaga(
        self,
        titulo: str,
        departamento: str,
        salario_range: dict[str, float],
        requisitos: list[str],
        posto_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "vaga_id": str(uuid4()),
            "titulo": titulo,
            "departamento": departamento,
            "salario_range": salario_range,
            "requisitos": requisitos,
            "posto_id": posto_id,
            "etapas": self.ETAPAS_SELECAO,
            "status": "aberta",
            "created_at": datetime.utcnow().isoformat(),
        }

    def avancar_etapa(self, candidato_id: str, etapa_atual: str) -> dict[str, Any]:
        idx = self.ETAPAS_SELECAO.index(etapa_atual) if etapa_atual in self.ETAPAS_SELECAO else -1
        if idx < 0 or idx >= len(self.ETAPAS_SELECAO) - 1:
            return {"candidato_id": candidato_id, "etapa": etapa_atual, "pode_avancar": False}
        proxima = self.ETAPAS_SELECAO[idx + 1]
        return {
            "candidato_id": candidato_id,
            "etapa_anterior": etapa_atual,
            "etapa_nova": proxima,
            "pode_avancar": True,
        }


class TrainerSkill:
    """Treinamentos e certificados."""

    NRS_OBRIGATORIAS_SEGURANCA = ["NR-05", "NR-06", "NR-10", "NR-35"]

    def criar_treinamento(
        self,
        titulo: str,
        tipo: str,
        carga_horaria: int,
        obrigatorio: bool = False,
        validade_dias: int = 365,
    ) -> dict[str, Any]:
        return {
            "treinamento_id": str(uuid4()),
            "titulo": titulo,
            "tipo": tipo,
            "carga_horaria": carga_horaria,
            "obrigatorio": obrigatorio,
            "validade_dias": validade_dias,
            "status": "agendado",
        }

    def emitir_certificado(
        self,
        treinamento_id: str,
        employee_id: str,
        nota: float = None,
    ) -> dict[str, Any]:
        return {
            "certificado_id": str(uuid4()),
            "treinamento_id": treinamento_id,
            "employee_id": employee_id,
            "nota": nota,
            "emitido_em": datetime.utcnow().isoformat(),
            "status": "valido",
        }

    def verificar_nrs_pendentes(self, certificados_employee: list[str]) -> list[str]:
        """Retorna NRs obrigatorias que o funcionario nao possui."""
        return [nr for nr in self.NRS_OBRIGATORIAS_SEGURANCA if nr not in certificados_employee]


class EvaluatorSkill:
    """Avaliacao de desempenho 360."""

    DIMENSOES = [
        "competencia_tecnica",
        "trabalho_equipe",
        "pontualidade",
        "iniciativa",
        "comunicacao",
        "lideranca",
    ]

    def criar_avaliacao(
        self,
        employee_id: str,
        avaliador_id: str,
        periodo: str,
    ) -> dict[str, Any]:
        return {
            "avaliacao_id": str(uuid4()),
            "employee_id": employee_id,
            "avaliador_id": avaliador_id,
            "periodo": periodo,
            "dimensoes": dict.fromkeys(self.DIMENSOES),
            "comentario": None,
            "status": "pendente",
        }

    def calcular_media(self, notas: dict[str, float]) -> float:
        """Calcula media das dimensoes avaliadas."""
        valid = [v for v in notas.values() if v is not None]
        return round(sum(valid) / len(valid), 2) if valid else 0.0


class RHAgent(BaseAgent):
    """Agent de Recursos Humanos."""

    AGENT_NAME = "RH_AGENT"
    AGENT_VERSION = "1.0.0"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.register_skill("RECRUITER", RecruiterSkill())
        self.register_skill("TRAINER", TrainerSkill())
        self.register_skill("EVALUATOR", EvaluatorSkill())

    @property
    def handled_events(self) -> list[str]:
        return [
            GPEventTypes.FUNCIONARIO_ADMITIDO,
            GPEventTypes.FUNCIONARIO_DEMITIDO,
            GPEventTypes.TREINAMENTO_AGENDADO,
            GPEventTypes.TREINAMENTO_REALIZADO,
        ]

    async def _process_event(self, event: Event) -> None:
        handlers = {
            GPEventTypes.FUNCIONARIO_ADMITIDO: self._on_admitido,
            GPEventTypes.FUNCIONARIO_DEMITIDO: self._on_demitido,
            GPEventTypes.TREINAMENTO_REALIZADO: self._on_treinamento_realizado,
        }
        handler = handlers.get(event.event_type)
        if handler:
            await handler(event)

    async def _on_admitido(self, event: Event) -> None:
        employee_id = event.payload.get("employee_id")
        logger.info(f"RH: Iniciando onboarding para {employee_id}")
        await self.emit_event(
            event_type=GPEventTypes.TREINAMENTO_AGENDADO,
            payload={"employee_id": employee_id, "tipo": "onboarding"},
            affected_modules=["PORTAL"],
        )

    async def _on_demitido(self, event: Event) -> None:
        logger.info(f"RH: Agendando entrevista de desligamento para {event.payload.get('employee_id')}")

    async def _on_treinamento_realizado(self, event: Event) -> None:
        trainer = self.get_skill("TRAINER")
        cert = trainer.emitir_certificado(
            treinamento_id=event.payload.get("treinamento_id", ""),
            employee_id=event.payload.get("employee_id", ""),
        )
        await self.emit_event(
            event_type=GPEventTypes.CERTIFICADO_EMITIDO,
            payload=cert,
            affected_modules=["DP", "GED", "OPS", "PORTAL"],
        )
