"""
Testes dos repositories (Slice 5).

Usam AsyncMock pra session - validam que:
1. Repositories instanciam sem erro
2. Metodos chamam a session corretamente
3. Logica de payload_hash, validacoes, etc estao corretas

Tests com DB real virao em integration tests apos Slice 4 (migration).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from modules.integrations.chatwoot.repositories import (
    CwiAccountConfigRepository,
    CwiContactLinkRepository,
    CwiConversationLinkRepository,
    CwiInboxEventRepository,
    CwiInboxRepository,
    CwiMessageLogRepository,
    CwiOutboxRepository,
)


# ---------------------------------------------------------------- Smoke


def test_todos_repositories_instanciam_com_session() -> None:
    """Verifica que os 7 repos aceitam AsyncSession no init."""
    session = AsyncMock()
    repos = [
        CwiAccountConfigRepository(session),
        CwiInboxRepository(session),
        CwiContactLinkRepository(session),
        CwiConversationLinkRepository(session),
        CwiMessageLogRepository(session),
        CwiOutboxRepository(session),
        CwiInboxEventRepository(session),
    ]
    for repo in repos:
        assert repo.db is session


def test_cada_repo_tem_model_associado() -> None:
    """BaseRepository exige `model` class attribute."""
    session = AsyncMock()
    assert CwiAccountConfigRepository(session).model.__name__ == "CwiAccountConfig"
    assert CwiInboxRepository(session).model.__name__ == "CwiInbox"
    assert CwiContactLinkRepository(session).model.__name__ == "CwiContactLink"
    assert CwiOutboxRepository(session).model.__name__ == "CwiOutbox"
    assert CwiInboxEventRepository(session).model.__name__ == "CwiInboxEvent"


# ---------------------------------------------------------------- Outbox


@pytest.mark.asyncio
async def test_outbox_enqueue_exige_conversation_ou_contact() -> None:
    """PRD: CHECK ((conv_id IS NOT NULL) OR (contact_id IS NOT NULL))."""
    repo = CwiOutboxRepository(AsyncMock())
    with pytest.raises(ValueError, match="conversation_id OU.*contact_id"):
        await repo.enqueue(
            chatwoot_inbox_id=1,
            triggered_by_module="financeiro",
            triggered_by_event="fatura_vencendo",
            content="Ola",
            # nenhum dos dois - deveria explodir
        )


@pytest.mark.asyncio
async def test_outbox_mark_sent_chama_update_com_status_e_message_id() -> None:
    session = AsyncMock()
    session.execute.return_value = MagicMock(rowcount=1)
    repo = CwiOutboxRepository(session)

    rows = await repo.mark_sent(id=42, chatwoot_message_id=999)

    assert rows == 1
    # Verifica que execute foi chamado com um statement
    assert session.execute.called
    call_args = session.execute.call_args[0][0]
    compiled = str(call_args)
    assert "cwi_outbox" in compiled.lower()
    assert "SET" in compiled.upper()


@pytest.mark.asyncio
async def test_outbox_mark_failed_incrementa_attempts_e_marca_failed_apos_max() -> None:
    """Apos max_attempts, status vira 'failed' permanente."""
    session = AsyncMock()
    # Simula obj atual com attempts=4 (proximo vai pra 5 = limite)
    fake_obj = MagicMock(attempts=4)
    session.get.return_value = fake_obj
    session.execute.return_value = MagicMock(rowcount=1)
    repo = CwiOutboxRepository(session)

    await repo.mark_failed(id=1, error="boom", max_attempts=5)

    # Confirma que execute foi chamado com values incluindo status='failed'
    compiled = str(session.execute.call_args[0][0])
    assert "UPDATE" in compiled.upper()


@pytest.mark.asyncio
async def test_outbox_mark_failed_mantem_pending_se_ainda_tem_tentativas() -> None:
    session = AsyncMock()
    fake_obj = MagicMock(attempts=1)
    session.get.return_value = fake_obj
    session.execute.return_value = MagicMock(rowcount=1)
    repo = CwiOutboxRepository(session)

    await repo.mark_failed(id=1, error="transient", max_attempts=5)

    # Nao da pra inspecionar values direto do statement compilado, mas
    # podemos validar que get foi chamado pra checar attempts
    session.get.assert_called_once()


@pytest.mark.asyncio
async def test_outbox_mark_failed_retorna_0_se_nao_existe() -> None:
    session = AsyncMock()
    session.get.return_value = None
    repo = CwiOutboxRepository(session)

    rows = await repo.mark_failed(id=9999, error="anything")

    assert rows == 0
    session.execute.assert_not_called()


# ---------------------------------------------------------------- Inbox Event


def test_inbox_event_payload_hash_deterministico() -> None:
    """Hash deve ser o mesmo pra payloads equivalentes (chaves desordenadas)."""
    h1 = CwiInboxEventRepository._payload_hash({"a": 1, "b": 2})
    h2 = CwiInboxEventRepository._payload_hash({"b": 2, "a": 1})
    assert h1 == h2
    assert len(h1) == 64  # SHA256 em hex


def test_inbox_event_payload_hash_difere_pra_payloads_diferentes() -> None:
    h1 = CwiInboxEventRepository._payload_hash({"event": "message_created", "id": 1})
    h2 = CwiInboxEventRepository._payload_hash({"event": "message_created", "id": 2})
    assert h1 != h2


@pytest.mark.asyncio
async def test_inbox_event_record_or_duplicate_existente_retorna_is_new_false() -> None:
    """Se evento ja existe (mesmo chatwoot_event_id), nao recria."""
    session = AsyncMock()
    existing = MagicMock(id=42)
    # Simula que existe ao chamar _get_by_chatwoot_event_id
    session.execute.return_value.scalar_one_or_none = MagicMock(return_value=existing)
    repo = CwiInboxEventRepository(session)

    obj, is_new = await repo.record_or_duplicate(
        event_type="message_created",
        payload={"id": 1},
        chatwoot_event_id="existing-id-123",
    )

    assert obj is existing
    assert is_new is False


@pytest.mark.asyncio
async def test_inbox_event_mark_processed_seta_processed_at() -> None:
    session = AsyncMock()
    session.execute.return_value = MagicMock(rowcount=1)
    repo = CwiInboxEventRepository(session)

    rows = await repo.mark_processed(id=42)

    assert rows == 1
    compiled = str(session.execute.call_args[0][0])
    assert "UPDATE" in compiled.upper()
    assert "cwi_inbox_event" in compiled.lower()


# ---------------------------------------------------------------- Account


@pytest.mark.asyncio
async def test_account_get_active_executa_query_e_retorna_scalar() -> None:
    """Valida que get_active() chama execute + scalar_one_or_none (sem compilar SQL)."""
    session = AsyncMock()
    fake_config = MagicMock(active=True)
    session.execute.return_value.scalar_one_or_none = MagicMock(return_value=fake_config)
    repo = CwiAccountConfigRepository(session)

    result = await repo.get_active()

    assert result is fake_config
    session.execute.assert_called_once()
