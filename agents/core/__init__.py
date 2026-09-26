"""Núcleo dos agentes de AUDITORIA DE CÓDIGO (`AuditOrchestrator` e amigos).

`BaseAgent` e `BaseOrchestrator` saíram em 26/09/2026 junto com os 80 agentes de
monitoramento de rota que herdavam delas — ver o commit da aposentadoria. O que
permanece aqui é outra família: lê e conserta CÓDIGO, não sonda endpoint.
"""

from .audit_orchestrator import AuditOrchestrator
from .code_fixer import CodeFixer
from .code_reader import CodeReader

__all__ = [
    "AuditOrchestrator",
    "CodeFixer",
    "CodeReader",
]
