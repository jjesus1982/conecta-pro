"""
Smoke tests dos models SQLAlchemy do modulo chatwoot_integration (Slice 3).

Validamos via acesso estatico (`__table__`, `__tablename__`) - NAO
instanciamos os models pra evitar disparar init global do SQLAlchemy
(o projeto tem um relationship mal configurado em NotificationChannel
fora do nosso escopo que explode em qualquer init).

Tests com DB real virao no Slice 5 (Repositories) usando fixtures
isoladas que driblam o problema do NotificationChannel.
"""
from __future__ import annotations

from sqlalchemy import CheckConstraint, UniqueConstraint

from modules.integrations.chatwoot.models import (
    CwiAccountConfig,
    CwiContactLink,
    CwiConversationLink,
    CwiInbox,
    CwiInboxEvent,
    CwiMessageLog,
    CwiOutbox,
)

ALL_MODELS = [
    CwiAccountConfig,
    CwiInbox,
    CwiContactLink,
    CwiConversationLink,
    CwiMessageLog,
    CwiOutbox,
    CwiInboxEvent,
]


def test_todos_models_tem_tablename_com_prefixo_cwi() -> None:
    for m in ALL_MODELS:
        assert m.__tablename__.startswith("cwi_"), (
            f"{m.__name__} deveria comecar com cwi_, mas tem {m.__tablename__}"
        )


def test_tablenames_esperados_do_prd_sec_6_1() -> None:
    assert CwiAccountConfig.__tablename__ == "cwi_account_config"
    assert CwiInbox.__tablename__ == "cwi_inbox"
    assert CwiContactLink.__tablename__ == "cwi_contact_link"
    assert CwiConversationLink.__tablename__ == "cwi_conversation_link"
    assert CwiMessageLog.__tablename__ == "cwi_message_log"
    assert CwiOutbox.__tablename__ == "cwi_outbox"
    assert CwiInboxEvent.__tablename__ == "cwi_inbox_event"


def test_todos_models_tem_coluna_id() -> None:
    for m in ALL_MODELS:
        cols = {c.name for c in m.__table__.columns}
        assert "id" in cols, f"{m.__name__} sem coluna id"


def test_account_config_tem_campos_obrigatorios() -> None:
    cols = {c.name for c in CwiAccountConfig.__table__.columns}
    obrigatorios = {
        "id",
        "chatwoot_url",
        "chatwoot_account_id",
        "api_access_token",
        "webhook_secret",
        "active",
        "created_at",
        "updated_at",
    }
    assert obrigatorios.issubset(cols), f"faltam: {obrigatorios - cols}"


def test_contact_link_tem_fks_lazy_pras_entidades_cpro() -> None:
    """As 4 FKs lazy (lead/client/employee/sindico) devem existir como UUID nullable."""
    cols = {c.name: c for c in CwiContactLink.__table__.columns}
    for fk_col in ("lead_id", "client_id", "employee_id", "sindico_id"):
        assert fk_col in cols, f"FK lazy {fk_col} ausente"
        assert cols[fk_col].nullable is True


def test_contact_link_tem_unique_constraint_dupla() -> None:
    """PRD: UNIQUE (chatwoot_contact_id, chatwoot_account_id)."""
    unique_constraints = [
        c for c in CwiContactLink.__table__.constraints if isinstance(c, UniqueConstraint)
    ]
    assert any(
        {col.name for col in uc.columns} == {"chatwoot_contact_id", "chatwoot_account_id"}
        for uc in unique_constraints
    )


def test_outbox_tem_check_constraint_target_obrigatorio() -> None:
    """PRD: CHECK (conversation_id IS NOT NULL OR contact_id IS NOT NULL)."""
    checks = [c for c in CwiOutbox.__table__.constraints if isinstance(c, CheckConstraint)]
    assert len(checks) >= 1, "outbox precisa de pelo menos um CheckConstraint"


def test_inbox_event_tem_payload_jsonb() -> None:
    """PRD: payload JSONB NOT NULL."""
    payload_col = next(c for c in CwiInboxEvent.__table__.columns if c.name == "payload")
    # tipo SQL deve ser JSONB
    assert "JSONB" in str(payload_col.type).upper()
    assert payload_col.nullable is False


def test_message_log_tem_unique_em_chatwoot_message_id() -> None:
    """PRD: UNIQUE (chatwoot_message_id)."""
    unique_constraints = [
        c for c in CwiMessageLog.__table__.constraints if isinstance(c, UniqueConstraint)
    ]
    assert any(
        {col.name for col in uc.columns} == {"chatwoot_message_id"}
        for uc in unique_constraints
    )


def test_outbox_tem_indice_partial_pending() -> None:
    """PRD: CREATE INDEX cwi_outbox_pending ON cwi_outbox(created_at) WHERE status = 'pending'."""
    indexes = list(CwiOutbox.__table__.indexes)
    partial = [idx for idx in indexes if idx.dialect_options.get("postgresql", {}).get("where")]
    assert len(partial) >= 1, "esperado pelo menos um partial index"


def test_inbox_event_tem_indice_partial_pending() -> None:
    indexes = list(CwiInboxEvent.__table__.indexes)
    partial = [idx for idx in indexes if idx.dialect_options.get("postgresql", {}).get("where")]
    assert len(partial) >= 1


def test_contact_link_tem_indice_partial_em_fks_lazy() -> None:
    """PRD: indexes em lead_id e client_id apenas WHERE NOT NULL."""
    indexes = list(CwiContactLink.__table__.indexes)
    partial = [idx for idx in indexes if idx.dialect_options.get("postgresql", {}).get("where")]
    # esperado pelo menos 2 (lead, client)
    assert len(partial) >= 2
