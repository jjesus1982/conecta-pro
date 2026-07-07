"""
Module: triage
Description: Painel de triagem operacional para gestores (visão consolidada
de ocorrências abertas, passagens de turno do dia, avaliações da semana e
situação das escalas).

Somente leitura — agrega dados de occurrences, operacional_passagens_turno,
operacional_avaliacoes_equipe, scales e posts (SQL raw).
"""

from .controllers import triage_router

__all__ = ["triage_router"]
