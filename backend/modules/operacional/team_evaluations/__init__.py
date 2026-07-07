"""
Module: team_evaluations
Description: Avaliação de equipe pelos líderes de posto (nota 1-5 por competência).

Tabela: operacional_avaliacoes_equipe (SQL raw, sem model ORM).
"""

from .controllers import team_evaluation_router

__all__ = ["team_evaluation_router"]
