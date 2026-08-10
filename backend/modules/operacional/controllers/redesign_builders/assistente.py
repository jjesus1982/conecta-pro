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
EXTRA_MENU: list[dict] = [
    {"id": "memorias", "label": "Memórias do consultor", "icon": "M9 11l3 3L22 4M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"},
    {"id": "anomalias", "label": "Alertas de anomalia", "icon": "M9 11l3 3L22 4M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"},
]



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

    # Memorias e anomalias (2026-08-10): aprovar/rejeitar e confirmar/descartar levam {id}
    # no CAMINHO -> acao por LINHA. Sao o gate humano do que a IA aprendeu e do que ela
    # suspeitou: nada disso entra sozinho.
    await safe("memorias", tbl(
        "Memórias do consultor", "O que a IA quer guardar — só entra se você aprovar", "—",
        ["Conteúdo", "Origem", "Confiança", "Status"], "2.6fr 1fr 0.8fr 0.9fr",
        "SELECT id, coalesce(conteudo,'—'), coalesce(origem,'—'), confidence, coalesce(status::text,'pendente') "
        "FROM consultor_memorias ORDER BY created_at DESC NULLS LAST LIMIT 200",
        lambda r: [t((r[1] or '—')[:110]), t((r[2] or '—').capitalize()),
                   t(f"{float(r[3]):.0%}" if r[3] is not None else "—"),
                   b((r[4] or '—').capitalize(), "ok" if (r[4] or '').lower() in ("aprovada", "aprovado") else "warn")],
        actionsfn=lambda r: None if (r[4] or '').lower() in ("aprovada", "aprovado", "rejeitada") else [
            {"title": "Aprovar esta memória",
             "sub": "Aprovada, ela passa a influenciar as respostas do consultor.",
             "endpoint": f"/api/v1/ai/consultor/memorias/{r[0]}/aprovar",
             "method": "POST", "btnLabel": "Aprovar", "submitLabel": "Aprovar memória",
             "btnStyle": "primary", "okMsg": "Memória aprovada. Recarregue.", "fields": []},
            {"title": "Rejeitar esta memória",
             "endpoint": f"/api/v1/ai/consultor/memorias/{r[0]}/rejeitar",
             "method": "POST", "btnLabel": "Rejeitar", "submitLabel": "Rejeitar memória",
             "btnStyle": "outline", "okMsg": "Memória rejeitada. Recarregue.", "fields": []},
        ]))
    await safe("anomalias", tbl(
        "Alertas de anomalia", "Suspeitas levantadas automaticamente — o veredito é humano", "—",
        ["Alerta", "Categoria", "Severidade", "Valor", "Status"],
        "2fr 1.1fr 0.9fr 1fr 0.9fr",
        "SELECT id, coalesce(title,'—'), coalesce(category::text,'—'), coalesce(severity::text,'—'), "
        "transaction_value, coalesce(status::text,'—') "
        "FROM fraud_alerts ORDER BY created_at DESC NULLS LAST LIMIT 200",
        lambda r: [t((r[1] or '—')[:80], 600, "#0F1B3A"), t((r[2] or '—').replace('_', ' ').capitalize()),
                   b((r[3] or '—').capitalize(), "bad" if (r[3] or '').lower() in ("alta", "high", "critical") else "warn"),
                   t(brl(r[4]) if r[4] is not None else "—", 600),
                   b((r[5] or '—').capitalize(), "info")],
        actionsfn=lambda r: [
            {"title": "Confirmar: é anomalia mesmo",
             "sub": "Confirma o alerta. Não move dinheiro nem bloqueia nada sozinho.",
             "endpoint": f"/api/v1/ai/fraud/anomalias/{r[0]}/confirmar",
             "method": "POST", "btnLabel": "Confirmar", "submitLabel": "Confirmar anomalia",
             "btnStyle": "primary", "okMsg": "Anomalia confirmada. Recarregue.", "fields": []},
            {"title": "Descartar: é falso positivo",
             "endpoint": f"/api/v1/ai/fraud/anomalias/{r[0]}/descartar",
             "method": "POST", "btnLabel": "Descartar", "submitLabel": "Descartar alerta",
             "btnStyle": "outline", "okMsg": "Alerta descartado. Recarregue.", "fields": []},
        ]))

    return out
