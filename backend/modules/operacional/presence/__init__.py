"""
Module: presence
Description: Quadro de PRESENÇA AO VIVO do módulo Operacional — cruza a escala
do dia (shifts) com as batidas de ponto REAIS (gp_clock_punches, sincronizadas
do Sólides) e com o check-in manual feito pelo líder de posto.

Princípio: quem não tem batida (nem check-in manual) NÃO é "presente" —
o quadro nunca fabrica presença.

Escopo por posto via modules.operacional.scope (líder vê só os postos dele;
gestor vê tudo).
"""

from .controllers import presence_router

__all__ = ["presence_router"]
