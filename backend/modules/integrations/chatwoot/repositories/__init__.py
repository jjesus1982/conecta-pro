"""
Repositories do modulo chatwoot_integration (Slice 5).

Cada repository encapsula queries para 1 model. BaseChatwootRepository
oferece CRUD generico; repos especificos adicionam metodos customizados
(lookup por chave de negocio, claim pra workers, etc).
"""
from .account import CwiAccountConfigRepository
from .base import BaseChatwootRepository
from .contact_link import CwiContactLinkRepository
from .conversation_link import CwiConversationLinkRepository
from .inbox import CwiInboxRepository
from .inbox_event import CwiInboxEventRepository
from .message_log import CwiMessageLogRepository
from .outbox import CwiOutboxRepository

__all__ = [
    "BaseChatwootRepository",
    "CwiAccountConfigRepository",
    "CwiInboxRepository",
    "CwiContactLinkRepository",
    "CwiConversationLinkRepository",
    "CwiMessageLogRepository",
    "CwiOutboxRepository",
    "CwiInboxEventRepository",
]
