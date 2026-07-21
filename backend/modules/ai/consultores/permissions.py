"""Gates de acesso dos Consultores de IA — Fase −1 / Task 3.

Fecha o vazamento LGPD (2026-07-21): antes, 6 de 8 consultores exigiam só
"usuário logado", e o Consultor CEO (cross-módulo: folha + financeiro + jurídico)
estava aberto a qualquer um. Agora:
- Consultores de módulo → gate `require_permission("module:<x>")` (ver main_production).
- Consultor CEO → restrito à DIRETORIA (jjesus + pjesus), decisão do Jordan.
  Nem outros admins entram — é o mais sensível.
"""
from fastapi import Depends, HTTPException, status

from core.auth.dependencies import get_current_active_user

# Diretoria com acesso irrestrito ao Consultor Executivo (decisão Jordan 2026-07-21;
# espelha "Financeiro = só Jordan + Pyetra").
CONSULTOR_EXECUTIVO_EMAILS = {"jjesus@conectamais.pro", "pjesus@conectamais.pro"}


async def require_consultor_executivo(user=Depends(get_current_active_user)):
    """Gate do Consultor CEO: só jjesus + pjesus (allowlist explícita, sem bypass de admin)."""
    if getattr(user, "email", None) not in CONSULTOR_EXECUTIVO_EMAILS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Consultor Executivo restrito à diretoria",
        )
    return user
