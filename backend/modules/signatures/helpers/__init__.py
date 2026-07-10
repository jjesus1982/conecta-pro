"""Helpers do módulo de assinatura universal — ponte entre geradores e o motor."""

from modules.signatures.helpers.solicitar_assinatura_documento import (
    document_hash_sha256,
    garantir_solicitacao_assinatura,
    garantir_solicitacao_assinatura_sync,
    status_documento_sync,
)

__all__ = [
    "garantir_solicitacao_assinatura",
    "garantir_solicitacao_assinatura_sync",
    "status_documento_sync",
    "document_hash_sha256",
]
