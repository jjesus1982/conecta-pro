"""Subscribers de RH — notificam pelo SINO os eventos que disparavam sem reação.

Ligados em 2026-08-07 (decisão Jordan). Medido antes: `rh.avaliacao_desempenho.criada`,
`rh.onboarding.item_concluido` e `rh.milestone.concluido` disparavam nos streams e nenhum
handler reagia.

O QUE ESTES HANDLERS **NÃO** FAZEM, e por quê
  Não "avançam o funil". O controller de onboarding JÁ marca o item como concluído no banco
  e só então publica (onboarding_controller.py:119-128). Um subscriber que avançasse de novo
  estaria duplicando o efeito. O evento é aviso de fato consumado, não ordem de execução.

  Também não notificam o avaliador: o payload de `rh.avaliacao_desempenho.criada` carrega
  só `employee_id` e `review_id` — quem avalia não está no evento.

O QUE FAZEM
  Inserem uma notificação in-app (o sino) para o próprio funcionário, resolvendo
  employee_id → users.employee_id. Sem usuário vinculado, registram log e saem — nunca
  inventam destinatário. Telegram é banido para notificação interna.

  No onboarding, notificam apenas quando o checklist INTEIRO fecha — assim o DP recebe um
  aviso por colaborador, não um por item.
"""

import logging

from sqlalchemy import text

from core.database import async_session_factory
from infrastructure.event_bus import ConectaEvent, EventTypes, event_bus

logger = logging.getLogger(__name__)


async def _notificar_funcionario(
    employee_id: str, titulo: str, corpo: str, ref_tipo: str, ref_id: str | None
) -> bool:
    """Insere no sino para o usuário do funcionário. False se não há a quem notificar."""
    if not employee_id:
        return False
    async with async_session_factory() as db:
        alvo = (
            await db.execute(
                text("SELECT id FROM users WHERE employee_id::text = :eid AND is_active LIMIT 1"),
                {"eid": str(employee_id)},
            )
        ).fetchone()
        if not alvo:
            # 32 dos 113 usuários não têm funcionário vinculado (medido 2026-08-07).
            # Sem destinatário real, não notifica — não se inventa um.
            logger.info("RH notificações: employee %s sem usuário ativo vinculado", employee_id)
            return False
        tenant = (await db.execute(text("SELECT id FROM tenants LIMIT 1"))).fetchone()
        if not tenant:
            logger.warning("RH notificações: nenhum tenant cadastrado")
            return False
        await db.execute(
            text("""
                INSERT INTO communication_notifications
                  (tenant_id, user_id, title, body, type, reference_type, reference_id, channels)
                VALUES (:tenant_id, :user_id, :title, :body, 'rh', :ref_tipo,
                        CAST(NULLIF(:ref_id,'') AS uuid), '["in_app"]'::jsonb)
            """),
            {
                "tenant_id": str(tenant[0]),
                "user_id": str(alvo[0]),
                "title": titulo,
                "body": corpo,
                "ref_tipo": ref_tipo,
                "ref_id": str(ref_id or ""),
            },
        )
        await db.commit()
        return True


async def on_avaliacao_criada(event: ConectaEvent) -> None:
    """Avaliação de desempenho criada → avisa o avaliado."""
    p = event.payload
    await _notificar_funcionario(
        p.get("employee_id", ""),
        "Avaliação de desempenho criada",
        "Uma avaliação de desempenho foi aberta para você.",
        "rh_avaliacao",
        p.get("review_id"),
    )


async def on_milestone_concluido(event: ConectaEvent) -> None:
    """Marco do plano de carreira concluído → avisa o funcionário."""
    p = event.payload
    await _notificar_funcionario(
        p.get("employee_id", ""),
        "Marco de carreira concluído",
        f"Você concluiu o marco {p.get('milestone_index', 0)} do seu plano de carreira.",
        "rh_plano_carreira",
        p.get("plan_id"),
    )


async def on_onboarding_item_concluido(event: ConectaEvent) -> None:
    """Item de onboarding concluído → avisa SÓ quando o checklist inteiro fecha.

    Notificar por item geraria uma notificação por clique. O valor está em saber que o
    colaborador terminou a integração.
    """
    p = event.payload
    employee_id = p.get("employee_id", "")
    if not employee_id:
        return
    async with async_session_factory() as db:
        row = (
            await db.execute(
                text(
                    "SELECT count(*) FILTER (WHERE NOT coalesce(concluido,false)) AS abertos, "
                    "count(*) AS total FROM rh_onboarding_checklist WHERE employee_id::text = :eid"
                ),
                {"eid": str(employee_id)},
            )
        ).fetchone()
    if not row or row[1] == 0 or row[0] > 0:
        return  # ainda há item aberto — nada a anunciar
    await _notificar_funcionario(
        employee_id,
        "Onboarding concluído",
        f"Todos os {row[1]} itens do seu checklist de integração foram concluídos.",
        "rh_onboarding",
        None,
    )


def registrar_subscribers() -> None:
    """Registra os handlers no ConectaEventBus. Chamado no lifespan do main_production."""
    event_bus.subscribe(EventTypes.RH_AVALIACAO_CRIADA, on_avaliacao_criada)
    event_bus.subscribe(EventTypes.RH_MILESTONE_CONCLUIDO, on_milestone_concluido)
    event_bus.subscribe(EventTypes.RH_ONBOARDING_ITEM_CONCLUIDO, on_onboarding_item_concluido)
    logger.info("RH notificações: 3 subscribers registrados no event bus")
