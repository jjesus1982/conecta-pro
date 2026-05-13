"""
Models SQLAlchemy do modulo chatwoot_integration (PRD Sec. 6.1).

7 tabelas no schema public, prefixo cwi_*:
- cwi_account_config       - configuracao da instancia Chatwoot
- cwi_inbox                - espelhamento de inboxes
- cwi_contact_link         - vinculo Chatwoot contact <-> CPro entidade
- cwi_conversation_link    - vinculo Chatwoot conv <-> CPro contexto
- cwi_message_log          - log de auditoria
- cwi_outbox               - fila outgoing (outbox pattern)
- cwi_inbox_event          - webhooks entrantes (inbox pattern)
"""
from .account import CwiAccountConfig
from .contact_link import CwiContactLink
from .conversation_link import CwiConversationLink
from .inbox import CwiInbox
from .inbox_event import CwiInboxEvent
from .message_log import CwiMessageLog
from .outbox import CwiOutbox

__all__ = [
    "CwiAccountConfig",
    "CwiInbox",
    "CwiContactLink",
    "CwiConversationLink",
    "CwiMessageLog",
    "CwiOutbox",
    "CwiInboxEvent",
]
