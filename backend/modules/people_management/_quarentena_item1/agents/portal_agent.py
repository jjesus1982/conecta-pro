"""
PORTAL Agent - Portal do Funcionario.
Notificacoes, visualizacao, solicitacoes.
"""

import logging
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from ..core.events import Event, GPEventTypes
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class NotificationType(StrEnum):
    INFO = "info"
    WARNING = "warning"
    URGENT = "urgent"
    ACTION_REQUIRED = "action_required"


class NotifierSkill:
    """Envio de notificacoes em tempo real."""

    def criar_notificacao(
        self,
        employee_id: str,
        titulo: str,
        mensagem: str,
        tipo: NotificationType = NotificationType.INFO,
        acao_url: str | None = None,
    ) -> dict[str, Any]:
        return {
            "notificacao_id": str(uuid4()),
            "employee_id": employee_id,
            "titulo": titulo,
            "mensagem": mensagem,
            "tipo": tipo.value,
            "acao_url": acao_url,
            "lida": False,
            "created_at": datetime.utcnow().isoformat(),
        }

    def criar_notificacao_em_massa(
        self,
        employee_ids: list[str],
        titulo: str,
        mensagem: str,
        tipo: NotificationType = NotificationType.INFO,
    ) -> list[dict[str, Any]]:
        return [self.criar_notificacao(eid, titulo, mensagem, tipo) for eid in employee_ids]


class ViewerSkill:
    """Disponibilizacao de documentos para visualizacao."""

    DOCUMENTOS_VISIVEIS_PORTAL = [
        "contracheque",
        "folha_ponto",
        "espelho_ponto",
        "aviso_ferias",
        "recibo_ferias",
        "advertencia_escrita",
        "suspensao",
        "certificado_treinamento",
        "ficha_epi",
        "aso_admissional",
        "aso_periodico",
    ]

    def verificar_acesso(self, employee_id: str, document_type: str) -> bool:
        """Verifica se funcionario pode ver este tipo de documento."""
        return document_type in self.DOCUMENTOS_VISIVEIS_PORTAL

    def listar_documentos_disponiveis(self) -> list[str]:
        return self.DOCUMENTOS_VISIVEIS_PORTAL.copy()


class RequestSkill:
    """Criacao de solicitacoes pelo funcionario."""

    TIPOS_SOLICITACAO = [
        "ferias",
        "abono_pecuniario",
        "atestado_medico",
        "alteracao_dados",
        "declaracao",
        "segunda_via_cracha",
        "segunda_via_uniforme",
        "adiantamento",
    ]

    def criar_solicitacao(
        self,
        employee_id: str,
        tipo: str,
        descricao: str,
        dados: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if tipo not in self.TIPOS_SOLICITACAO:
            raise ValueError(f"Tipo de solicitacao invalido: {tipo}")
        return {
            "solicitacao_id": str(uuid4()),
            "employee_id": employee_id,
            "tipo": tipo,
            "descricao": descricao,
            "dados": dados or {},
            "status": "pendente",
            "created_at": datetime.utcnow().isoformat(),
        }


class PortalAgent(BaseAgent):
    """Agent do Portal do Funcionario."""

    AGENT_NAME = "PORTAL_AGENT"
    AGENT_VERSION = "1.0.0"

    # Mapa de eventos -> notificacoes
    EVENT_NOTIFICATION_MAP = {
        GPEventTypes.FOLHA_FECHADA: ("Contracheque disponivel", NotificationType.INFO),
        GPEventTypes.ESCALA_PUBLICADA: ("Nova escala publicada", NotificationType.INFO),
        GPEventTypes.ADVERTENCIA_APLICADA: ("Advertencia aplicada", NotificationType.WARNING),
        GPEventTypes.SUSPENSAO_APLICADA: ("Suspensao aplicada", NotificationType.URGENT),
        GPEventTypes.ASO_AGENDADO: ("Exame agendado", NotificationType.ACTION_REQUIRED),
        GPEventTypes.ASO_VENCENDO: ("ASO vencendo", NotificationType.WARNING),
        GPEventTypes.TREINAMENTO_AGENDADO: ("Treinamento agendado", NotificationType.INFO),
        GPEventTypes.KIT_MONTADO: ("Kit documental disponivel", NotificationType.INFO),
        GPEventTypes.CERTIFICADO_EMITIDO: ("Certificado emitido", NotificationType.INFO),
        GPEventTypes.PONTO_ATRASO: ("Atraso registrado", NotificationType.WARNING),
        GPEventTypes.EPI_VENCENDO: ("EPI vencendo", NotificationType.WARNING),
    }

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.register_skill("NOTIFIER", NotifierSkill())
        self.register_skill("VIEWER", ViewerSkill())
        self.register_skill("REQUEST", RequestSkill())

    @property
    def handled_events(self) -> list[str]:
        return list(self.EVENT_NOTIFICATION_MAP.keys()) + [
            GPEventTypes.DOCUMENTO_CRIADO,
            GPEventTypes.DOCUMENTO_ASSINADO,
            GPEventTypes.PONTO_BATIDO,
        ]

    async def _process_event(self, event: Event) -> None:
        # Se o evento esta no mapa de notificacoes, cria notificacao
        if event.event_type in self.EVENT_NOTIFICATION_MAP:
            await self._create_notification_from_event(event)
        else:
            logger.debug(f"PORTAL: Evento {event.event_type} recebido")

    async def _create_notification_from_event(self, event: Event) -> None:
        titulo, tipo = self.EVENT_NOTIFICATION_MAP[event.event_type]
        employee_id = event.payload.get("employee_id", "")

        if not employee_id:
            return

        notifier = self.get_skill("NOTIFIER")
        notif = notifier.criar_notificacao(
            employee_id=employee_id,
            titulo=titulo,
            mensagem=f"Evento: {event.event_type}",
            tipo=tipo,
        )

        await self.emit_event(
            event_type=GPEventTypes.NOTIFICACAO_ENVIADA,
            payload=notif,
        )

        logger.info(f"PORTAL: Notificacao '{titulo}' enviada para {employee_id}")
