"""
TEMPLATE — copie para redesign_builders/<seu_modulo>.py (nome do arquivo SEM hífen;
o slug real vai em SLUG). Você edita SÓ o arquivo do SEU módulo.
Ver auditoria/parity/DIVISAO_3T.md + BRIEFING_T2/T4.

Como ligar uma tela:
  1. Ache um menu-id não-wired em frontend/src/app/redesign/_modules/<slug>.json.
  2. Ache a tabela real do clássico (docker exec conecta-pro-backend python3 ... pg_stat_user_tables).
  3. await safe("<id>", tbl(...)) lendo essa tabela. Enum/json → ::text / ->>'k' no coalesce.
  4. Deploy blue-green → grep container → curl /redesign/data/<slug> prova dado real → commit.
  Ação legal (transmitir/pagar) = GATED. Nunca fabricar dado (vazio real = "aguardando dado").
"""
from sqlalchemy import text  # noqa: F401

from modules.operacional.controllers.redesign_data_controller import (  # noqa: F401
    IC, S, _ICF, _fmtdate, _helpers, _scalar, b, brl, initials, t,
)

# Slug do módulo (com hífen). Casa com BUILDERS / _modules/<slug>.json.
SLUG = "meu-modulo"

# Telas de ação (form/escrita) anexadas ao menu do módulo. Some ao menu existente.
EXTRA_MENU: list[dict] = [
    # {"id": "minha-acao", "label": "Minha ação", "icon": "M12 5v14M5 12h14"},
]


async def build(db) -> dict:
    """Devolve {screen_id: patch}. SOBRESCREVE o _build_<mod> do monólito.
    PONTO DE PARTIDA: copie o corpo do _build_<seu_modulo> atual de
    redesign_data_controller.py e ADICIONE suas telas novas aqui."""
    out, safe, tbl = _helpers(db)
    # await safe("minha-tela", tbl(
    #     "Título", f"{await _scalar(db, 'SELECT count(*) FROM tabela')} itens", "—",
    #     ["Coluna A", "Coluna B"], "1fr 1fr",
    #     "SELECT a, b FROM tabela ORDER BY a LIMIT 200",
    #     lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1])]))
    return out


# Para /action/* do seu módulo, descomente e registre no router (é incluído pelo registry):
# from fastapi import APIRouter, Body, Depends
# from core.auth.dependencies import CurrentActiveUser
# from core.database import get_db
# router = APIRouter()
# @router.post("/action/minha-acao")
# async def _minha_acao(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
#     return {"ok": True, "message": "..."}
