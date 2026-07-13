"""
Gatilho de notificacao: avisa o funcionario quando ha documento para assinar.

Quando o motor de assinaturas (`UniversalSignatureService.criar_solicitacao_assinatura`)
cria uma solicitacao com signatario EMPLOYEE, este gatilho grava uma notificacao no
sino do Portal do Funcionario (tabela `portal_notifications`) para cada funcionario
signatario — para que ele SAIBA que tem algo para assinar, em vez de descobrir so ao
logar.

Principios (M1):
- A PROVA DE FALHA: qualquer erro aqui e logado e engolido. Notificar e um efeito
  colateral — NUNCA pode quebrar a criacao da solicitacao de assinatura.
- SESSAO PROPRIA: abre uma AsyncSession de curta duracao (async_session_factory),
  desacoplada da sessao que criou a solicitacao (que ja foi commitada). Assim o
  gatilho nunca interfere no estado transacional do chamador.
- ANTI-SPAM: o AutoNotificationService faz dedupe (nao cria 2o alerta se ja houver um
  nao lido). Gerar N documentos em rajada => no maximo 1 alerta ate o funcionario ler.
- SO PARA DOCUMENTOS NOVOS: e chamado apenas na CRIACAO de novas solicitacoes; nao ha
  varredura retroativa dos ~1131 requests ja existentes.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # evita import ciclico em runtime
    from modules.signatures.services.universal_signature_service import SignerInput

logger = logging.getLogger(__name__)


async def notificar_assinatura_pendente_para_employees(
    signers: list["SignerInput"],
    *,
    document_type: str,
    title: str,
) -> None:
    """Notifica no sino cada funcionario signatario de uma nova solicitacao.

    Args:
        signers: signatarios da solicitacao recem-criada (SignerInput).
        document_type: tipo do documento (fallback do titulo).
        title: titulo humano do documento (usado no texto da notificacao).
    """
    try:
        # Import tardio: SignerType vem do proprio motor; evita ciclo no import do modulo.
        from modules.signatures.services.universal_signature_service import SignerType

        alvos = [
            s
            for s in (signers or [])
            if s.signer_type == SignerType.EMPLOYEE and s.signer_id is not None
        ]
        if not alvos:
            return

        from core.database import async_session_factory
        from modules.people_management.employee_portal.services.auto_notification_service import (
            AutoNotificationService,
        )

        doc_nome = (title or document_type or "documento").strip()

        async with async_session_factory() as session:
            svc = AutoNotificationService(session)
            for s in alvos:
                try:
                    await svc.notify_signature_pending(s.signer_id, doc_nome)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Falha ao notificar funcionario %s sobre assinatura pendente: %s",
                        s.signer_id,
                        exc,
                    )
    except Exception as exc:  # noqa: BLE001
        # Blindagem final: NADA aqui pode quebrar a criacao da solicitacao.
        logger.warning(
            "Gatilho de notificacao de assinatura falhou (doc_type=%s): %s",
            document_type,
            exc,
        )
