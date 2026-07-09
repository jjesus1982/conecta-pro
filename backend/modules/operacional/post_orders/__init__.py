"""
Module: post_orders
Description: Instruções de posto (post orders) — o gestor edita as instruções
de cada posto e o líder lê no celular. Versionadas com histórico (últimas 10
versões em jsonb).

Tabela: operacional_post_orders (1 registro por posto, post_id UNIQUE).
"""

from .controllers import post_orders_router

__all__ = ["post_orders_router"]
