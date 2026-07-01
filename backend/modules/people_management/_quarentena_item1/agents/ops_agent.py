"""
OPS Agent - Operacoes.
Escalas, alocacao, supervisao, disciplinar.
"""

import logging
from datetime import datetime
from typing import Any
from uuid import uuid4

from ..core.events import Event, EventPriority, GPEventTypes
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class SchedulerSkill:
    """Criacao e otimizacao de escalas."""

    ESCALAS_TIPO = {
        "12x36": {"horas_trabalho": 12, "horas_folga": 36},
        "6x1": {"horas_trabalho": 8, "dias_folga_semana": 1},
        "5x2": {"horas_trabalho": 8, "dias_folga_semana": 2},
        "24x48": {"horas_trabalho": 24, "horas_folga": 48},
    }

    def criar_escala(
        self,
        tipo: str,
        posto_id: str,
        employee_ids: list[str],
        inicio: str,
        fim: str,
    ) -> dict[str, Any]:
        if tipo not in self.ESCALAS_TIPO:
            raise ValueError(f"Tipo de escala invalido: {tipo}")

        return {
            "escala_id": str(uuid4()),
            "tipo": tipo,
            "posto_id": posto_id,
            "employees": employee_ids,
            "inicio": inicio,
            "fim": fim,
            "configuracao": self.ESCALAS_TIPO[tipo],
            "status": "rascunho",
            "created_at": datetime.utcnow().isoformat(),
        }

    def calcular_cobertura(self, postos: list[dict], alocacoes: list[dict]) -> dict[str, Any]:
        """Calcula percentual de cobertura dos postos."""
        total = len(postos)
        cobertos = sum(1 for p in postos if any(a.get("posto_id") == p.get("id") for a in alocacoes))
        return {
            "total_postos": total,
            "postos_cobertos": cobertos,
            "postos_descobertos": total - cobertos,
            "percentual_cobertura": round(cobertos / total * 100, 1) if total > 0 else 0,
        }


class AllocatorSkill:
    """Alocacao de funcionarios em postos."""

    def alocar(
        self,
        employee_id: str,
        posto_id: str,
        turno: str,
        inicio: str,
        fim: str | None = None,
    ) -> dict[str, Any]:
        return {
            "alocacao_id": str(uuid4()),
            "employee_id": employee_id,
            "posto_id": posto_id,
            "turno": turno,
            "inicio": inicio,
            "fim": fim,
            "status": "ativa",
        }

    def desalocar(self, alocacao_id: str, motivo: str) -> dict[str, Any]:
        return {
            "alocacao_id": alocacao_id,
            "status": "encerrada",
            "motivo": motivo,
            "encerrada_em": datetime.utcnow().isoformat(),
        }


class DisciplineSkill:
    """Gestao disciplinar: advertencias, suspensoes."""

    TIPOS = {
        "advertencia_verbal": {"pontos": 1, "validade_dias": 180},
        "advertencia_escrita": {"pontos": 2, "validade_dias": 365},
        "suspensao_1_dia": {"pontos": 3, "dias_suspensao": 1},
        "suspensao_3_dias": {"pontos": 5, "dias_suspensao": 3},
        "suspensao_5_dias": {"pontos": 7, "dias_suspensao": 5},
        "justa_causa": {"pontos": 10, "dias_suspensao": 0},
    }

    def aplicar_medida(
        self,
        employee_id: str,
        tipo: str,
        motivo: str,
        aplicado_por: str,
    ) -> dict[str, Any]:
        if tipo not in self.TIPOS:
            raise ValueError(f"Tipo disciplinar invalido: {tipo}")

        config = self.TIPOS[tipo]
        return {
            "medida_id": str(uuid4()),
            "employee_id": employee_id,
            "tipo": tipo,
            "motivo": motivo,
            "pontos": config["pontos"],
            "dias_suspensao": config.get("dias_suspensao", 0),
            "aplicado_por": aplicado_por,
            "aplicado_em": datetime.utcnow().isoformat(),
            "status": "aplicada",
        }


class OPSAgent(BaseAgent):
    """Agent de Operacoes."""

    AGENT_NAME = "OPS_AGENT"
    AGENT_VERSION = "1.0.0"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.register_skill("SCHEDULER", SchedulerSkill())
        self.register_skill("ALLOCATOR", AllocatorSkill())
        self.register_skill("DISCIPLINE", DisciplineSkill())

    @property
    def handled_events(self) -> list[str]:
        return [
            GPEventTypes.FUNCIONARIO_ADMITIDO,
            GPEventTypes.FUNCIONARIO_DEMITIDO,
            GPEventTypes.PONTO_BATIDO,
            GPEventTypes.PONTO_ATRASO,
            GPEventTypes.PONTO_FALTA,
            GPEventTypes.CERTIFICADO_EMITIDO,
            GPEventTypes.CAT_ABERTA,
        ]

    async def _process_event(self, event: Event) -> None:
        handlers = {
            GPEventTypes.FUNCIONARIO_ADMITIDO: self._on_admitido,
            GPEventTypes.FUNCIONARIO_DEMITIDO: self._on_demitido,
            GPEventTypes.PONTO_ATRASO: self._on_atraso,
            GPEventTypes.PONTO_FALTA: self._on_falta,
            GPEventTypes.CAT_ABERTA: self._on_cat,
        }
        handler = handlers.get(event.event_type)
        if handler:
            await handler(event)

    async def _on_admitido(self, event: Event) -> None:
        logger.info(f"OPS: Funcionario {event.payload.get('employee_id')} disponivel para escala")

    async def _on_demitido(self, event: Event) -> None:
        logger.info(f"OPS: Removendo {event.payload.get('employee_id')} de escalas futuras")

    async def _on_atraso(self, event: Event) -> None:
        logger.info(f"OPS: Notificando supervisor sobre atraso de {event.payload.get('employee_id')}")

    async def _on_falta(self, event: Event) -> None:
        logger.info(f"OPS: Notificando supervisor sobre falta de {event.payload.get('employee_id')}")

    async def _on_cat(self, event: Event) -> None:
        logger.info("OPS: CAT aberta - acidente registrado")
        await self.emit_event(
            event_type=GPEventTypes.OCORRENCIA_REGISTRADA,
            payload={**event.payload, "tipo": "acidente_trabalho"},
            priority=EventPriority.CRITICO,
            affected_modules=["DP", "GED", "PORTAL"],
        )
