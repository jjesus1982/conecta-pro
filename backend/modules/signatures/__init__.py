"""
Módulo de Assinatura Universal — Conecta PRO.

Motor central de assinatura eletrônica para QUALQUER documento gerado pelo
sistema. Suporta 3 tipos de assinante:

1. FUNCIONÁRIO (employee) — assina pelo Portal do Funcionário (JWT do portal).
2. EMPRESA (company)      — assina Jordan/Pyetra pelo painel admin (JWT admin).
3. CLIENTE (customer)     — assina por LINK seguro (token de uso único, sem conta).

Persistência única em `sig_signature_requests` + `sig_signatures`
(já existentes no banco, ver alembic/versions/sprint40_create_signature_tables.py).

A ficha de EPI e demais documentos do portal continuam usando
`portal_digital_signatures` via SignatureService legado — este módulo NÃO
substitui nem quebra aquele fluxo; roda em paralelo.
"""

from modules.signatures.services.universal_signature_service import (
    SignerInput,
    SignerType,
    UniversalSignatureService,
)

__all__ = [
    "UniversalSignatureService",
    "SignerInput",
    "SignerType",
]
