"""
Timeline do CRM — registro automático de atividades (best-effort).

log_activity insere uma linha em crm_activities ligada a lead/deal/proposta/cliente.
Best-effort: nunca quebra o fluxo que a chamou (segue padrão _try_generate_commission).
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def log_activity(
    db: AsyncSession,
    tipo: str,
    subject: str,
    *,
    description: str | None = None,
    lead_id: str | None = None,
    opportunity_id: str | None = None,
    client_id: str | None = None,
    proposal_id: str | None = None,
    user_id: str | None = None,
) -> None:
    """Registra uma atividade na timeline. Best-effort (não quebra o chamador)."""
    try:
        from modules.crm.models.activity_task import CrmActivity

        db.add(
            CrmActivity(
                type=str(tipo)[:50],
                subject=str(subject)[:255],
                description=description,
                lead_id=str(lead_id) if lead_id else None,
                opportunity_id=str(opportunity_id) if opportunity_id else None,
                client_id=str(client_id) if client_id else None,
                proposal_id=str(proposal_id) if proposal_id else None,
                user_id=str(user_id) if user_id else None,
            )
        )
        await db.commit()
    except Exception as exc:  # noqa: BLE001 — timeline nunca quebra o fluxo
        logger.debug("Timeline log_activity ignorado: %s", exc)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
