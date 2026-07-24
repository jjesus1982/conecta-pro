"""Orquestrador ESCOPADO por usuário (Peça 3): POST /consultores/chat/consultar.

- admin (diretoria) -> delega ao Orquestrador Executivo (Hermes) já deployado.
- demais -> engine in-backend com tools filtradas por user_modules (belt) + escopo
  posto/self (suspenders). Roda com a identidade do próprio usuário (get_current_active_user).

COMPOSIÇÃO EXPLÍCITA DOS TIERS (lição m5 do review da Task 5):
As tools de POSTO (tools_posto.POSTO_TOOLS) declaram module="operacional" — se o conjunto
do GESTOR fosse montado com `tools_for_modules(user_modules(user))` ingenuamente, elas
ENTRARIAM (com post_ids vazio → "aguardando dado": inofensivo, mas confuso) e, no tier
LÍDER, entrariam DUAS vezes (uma por module="operacional", outra pelo add explícito de
POSTO_TOOLS) → nomes de função DUPLICADOS no schema OpenAI. Por isso o conjunto de MÓDULO
(panoramas org-wide) é montado por `_modulo_tools()`, que exclui as tools posto-scoped. O
tier decide o resto:
  - gestor/dev = _modulo_tools(user_modules) (só panoramas org-wide dos módulos permitidos)
  - líder      = _modulo_tools(user_modules) + POSTO_TOOLS + SELF_TOOLS + justificar
  - clt        = SELF_TOOLS + justificar
(As SELF_TOOLS/justificar têm module="self", fora dos módulos canônicos, então
`tools_for_modules` nunca as devolve — não precisam ser excluídas do conjunto de módulo.)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_active_user
from core.auth.module_scope import user_modules
from core.database import get_db
from modules.ai.conversation.services.orquestrador import tools_modulos  # noqa: F401 — registra as tools de módulo
from modules.ai.conversation.services.orquestrador.engine import OrqScope, run_engine
from modules.ai.conversation.services.orquestrador.tool_registry import ToolDef, tools_for_modules
from modules.ai.conversation.services.orquestrador.tools_ponto import JUSTIFICAR_TOOL
from modules.ai.conversation.services.orquestrador.tools_posto import POSTO_TOOLS
from modules.ai.conversation.services.orquestrador.tools_self import SELF_TOOLS
from modules.operacional.scope import get_operational_scope

router = APIRouter(prefix="/consultores/chat", tags=["Consultores — Chat escopado"])

_SYSTEM_BASE = (
    "Você é o consultor de IA da Conecta PRO para ESTE usuário. Responda usando SOMENTE as tools "
    "disponíveis (elas já vêm escopadas ao que este usuário pode ver). NUNCA invente número, saldo, "
    "posto ou colaborador; se uma tool responder 'aguardando dado' ou nada, diga honestamente que o "
    "dado está fora do seu escopo ou indisponível. Dinheiro que sai, ato legal e folha exigem "
    "aprovação humana — você PROPÕE (ex.: justificar ponto vai para o DP aprovar), nunca executa."
)


class ConsultarIn(BaseModel):
    pergunta: str = Field(..., min_length=3, max_length=2000)


def _modulo_tools(mods: set[str]) -> list[ToolDef]:
    """Panoramas org-wide dos módulos permitidos (belt), EXCLUINDO as tools escopadas
    (posto/self/cliente) que possam carregar um module canônico (ex.: as posto-scoped
    declaram module="operacional" mas pertencem ao tier LÍDER, não ao gestor). O filtro é
    ESTRUTURAL por scope_kind=="org" — pega qualquer tool posto/self/cliente futura sem
    depender de uma lista de nomes (m13)."""
    return [t for t in tools_for_modules(mods) if t.scope_kind == "org"]


async def _resolver_tier_e_tools(db: AsyncSession, user) -> tuple[OrqScope, list[ToolDef]]:
    """Decide o tier (gestor/líder/clt) e monta o conjunto de tools escopadas.
    (admin é tratado antes, na rota — delega ao Hermes.)"""
    mods = user_modules(user)
    op = await get_operational_scope(current_user=user, db=db)
    emp = op.employee_id

    # LÍDER: escopado a postos (scope.py já força isso mesmo p/ role admin). É CLT + posto.
    if not op.all_posts and op.post_ids:
        tools = _modulo_tools(mods) + list(POSTO_TOOLS) + list(SELF_TOOLS) + [JUSTIFICAR_TOOL]
        return OrqScope(tier="lider", employee_id=emp, post_ids=op.post_ids), tools

    # GESTOR/DEV: módulos org-wide (nada de posto/self privilegiado).
    if op.is_manager or mods:
        return OrqScope(tier="gestor", is_manager=True, all_posts=True), _modulo_tools(mods)

    # CLT: só sobre si + a ação de justificar ponto.
    if emp:
        return OrqScope(tier="clt", employee_id=emp), list(SELF_TOOLS) + [JUSTIFICAR_TOOL]

    # Sem escopo algum: chat honesto sem tools.
    return OrqScope(tier="clt", employee_id=None), []


@router.post("/consultar")
async def consultar(
    payload: ConsultarIn,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_active_user),
):
    pergunta = payload.pergunta.strip()

    # DIRETORIA (admin) -> Orquestrador Executivo (Hermes) já deployado.
    if (getattr(user, "role", "") or "").lower() == "admin":
        from modules.ai.conversation.controllers.executivo_controller import (
            ConsultarIn as _ExecIn,
            consultar as _exec_consultar,
        )
        out = await _exec_consultar(_ExecIn(pergunta=pergunta), db=db, user=user)
        out["tier"] = "diretoria"
        return out

    scope, tools = await _resolver_tier_e_tools(db, user)
    return await run_engine(
        db, user, scope, tools, pergunta,
        system_prompt=_SYSTEM_BASE, origem="consultor_escopado",
    )
