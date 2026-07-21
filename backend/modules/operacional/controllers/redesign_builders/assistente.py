"""
redesign_builders/assistente.py — T4 (módulo NOVO, sem base no monólito).
Visibilidade do histórico do Assistente IA (assistant_conversations). Só leitura —
o chat ao vivo é interativo e não dispara ação daqui.
"""
from modules.operacional.controllers.redesign_data_controller import (  # noqa: F401
    _fmtdate,
    _helpers,
    _scalar,
    b,
    brl,
    initials,
    t,
)

SLUG = "assistente"


def _role_tone(role: str):
    r = (role or "").lower()
    if r in ("assistant", "ai", "bot"):
        return ("Assistente", "info")
    if r in ("user", "usuario", "usuário"):
        return ("Usuário", "ok")
    return ((role or "—").capitalize(), "mut")


async def build(db) -> dict:
    out, safe, tbl = _helpers(db)

    # ---- Assistente IA (últimas mensagens — READ) ----
    await safe("chat", tbl(
        "Assistente IA", f"{await _scalar(db, 'SELECT count(*) FROM assistant_conversations')} mensagens registradas",
        "—", ["Autor", "Mensagem", "Ação executada", "Data"], "1fr 3fr 1.2fr 1.2fr",
        "SELECT coalesce(role,'—'), left(coalesce(content,'—'),120), coalesce(action_executed,'—'), created_at "
        "FROM assistant_conversations ORDER BY created_at DESC NULLS LAST LIMIT 100",
        lambda r: [b(*_role_tone(r[0])), t(r[1], 500, "#0F1B3A"),
                   b((r[2] or '—').replace('_', ' ').capitalize(), "mut") if (r[2] and r[2] != '—') else t('—'), t(_fmtdate(r[3]))]))

    # ---- Histórico (conversas por chat_id — agregado real) ----
    await safe("historico", tbl(
        "Histórico", "Conversas do assistente por sessão",
        "—", ["Sessão (chat)", "Mensagens", "Última interação"], "2fr 1fr 1.4fr",
        "SELECT coalesce(chat_id::text,'—'), count(*), max(created_at) "
        "FROM assistant_conversations GROUP BY chat_id ORDER BY max(created_at) DESC NULLS LAST LIMIT 100",
        lambda r: [t(r[0], 600, "#0F1B3A"), b(f"{r[1]} msgs", "info"), t(_fmtdate(r[2]))]))

    return out
