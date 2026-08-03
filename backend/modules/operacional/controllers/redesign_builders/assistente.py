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


async def build(db, current_user=None) -> dict:
    """Histórico do Assistente IA escopado ao usuário logado (parede self-only).
    `assistant_conversations.user_id` = dono da conversa → cada um vê SÓ as próprias
    (conversas de IA podem conter consultas sensíveis). Sem usuário → vazio. uid=UUID
    validado, do token, in-linado (tbl() não aceita params)."""
    import uuid as _uuid
    out, safe, tbl = _helpers(db)
    uid = getattr(current_user, "id", None) if current_user is not None else None
    try:
        uid_lit = f"'{uid}'" if uid and _uuid.UUID(str(uid)) else "'00000000-0000-0000-0000-000000000000'"
    except Exception:
        uid_lit = "'00000000-0000-0000-0000-000000000000'"

    # ---- Assistente IA (MINHAS últimas mensagens — READ) ----
    await safe("chat", tbl(
        "Assistente IA", f"{await _scalar(db, f'SELECT count(*) FROM assistant_conversations WHERE user_id={uid_lit}')} mensagens registradas",
        "—", ["Autor", "Mensagem", "Ação executada", "Data"], "1fr 3fr 1.2fr 1.2fr",
        f"SELECT coalesce(role,'—'), left(coalesce(content,'—'),120), coalesce(action_executed,'—'), created_at "
        f"FROM assistant_conversations WHERE user_id={uid_lit} ORDER BY created_at DESC NULLS LAST LIMIT 100",
        lambda r: [b(*_role_tone(r[0])), t(r[1], 500, "#0F1B3A"),
                   b((r[2] or '—').replace('_', ' ').capitalize(), "mut") if (r[2] and r[2] != '—') else t('—'), t(_fmtdate(r[3]))]))

    # ---- Meu histórico (conversas por chat_id — agregado real, só meu) ----
    await safe("historico", tbl(
        "Histórico", "Minhas conversas por sessão",
        "—", ["Sessão (chat)", "Mensagens", "Última interação"], "2fr 1fr 1.4fr",
        f"SELECT coalesce(chat_id::text,'—'), count(*), max(created_at) "
        f"FROM assistant_conversations WHERE user_id={uid_lit} GROUP BY chat_id ORDER BY max(created_at) DESC NULLS LAST LIMIT 100",
        lambda r: [t(r[0], 600, "#0F1B3A"), b(f"{r[1]} msgs", "info"), t(_fmtdate(r[2]))]))

    return out
