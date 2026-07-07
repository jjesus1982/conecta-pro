"""
Module: shift_handover
Description: Passagem de turno entre equipes dos postos.

O líder que encerra o turno registra um resumo + pendências;
o turno seguinte lê a passagem anterior e confirma leitura.

Tabela: operacional_passagens_turno (SQL raw, sem model ORM).
"""

from .controllers import shift_handover_router

__all__ = ["shift_handover_router"]
