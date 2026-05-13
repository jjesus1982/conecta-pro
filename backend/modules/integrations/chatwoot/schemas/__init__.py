"""Schemas Pydantic do modulo chatwoot_integration."""
from .webhook import CwiInboxEvent, ChatwootWebhookEventType

__all__ = ["CwiInboxEvent", "ChatwootWebhookEventType"]
