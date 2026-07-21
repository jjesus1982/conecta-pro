"""
redesign_builders/crm.py — T4.
Sobrescreve _build_crm: reusa a base e ADICIONA clientes, growth (funil de
atividades) e consultor comercial (histórico de interações). Só leitura.
"""
from modules.operacional.controllers.redesign_data_controller import (  # noqa: F401
    _build_crm as _base,
    _fmtdate,
    _helpers,
    _scalar,
    b,
    brl,
    initials,
    t,
)

SLUG = "crm"


async def build(db) -> dict:
    out, safe, tbl = _helpers(db)
    out.update(await _base(db))

    # ---- Clientes (clients) ----
    await safe("clientes", tbl(
        "Clientes", f"{await _scalar(db, 'SELECT count(*) FROM clients WHERE ativo=true')} clientes ativos",
        "—", ["Cliente", "Segmento", "MRR", "Status"], "2fr 1.4fr 1fr 0.9fr",
        "SELECT name, coalesce(segment::text,'—'), coalesce(mrr,0), status::text FROM clients ORDER BY mrr DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0])), t((r[1] or '—').capitalize()), t(brl(r[2]), 600),
                   b("Ativo", "ok") if r[3] == "active" else b((r[3] or '—').capitalize(), "mut")]))

    # ---- Growth · funil de atividades (crm_activities agregado — real) ----
    await safe("growth", tbl(
        "Growth (Automação)", "Funil de atividades comerciais por tipo",
        "—", ["Tipo de atividade", "Quantidade", "Última"], "2fr 1fr 1.2fr",
        "SELECT coalesce(type,'—'), count(*), max(coalesce(completed_at, scheduled_at, created_at)) "
        "FROM crm_activities GROUP BY type ORDER BY count(*) DESC",
        lambda r: [t((r[0] or '—').replace('_', ' ').capitalize(), 600, "#0F1B3A"),
                   b(f"{r[1]}", "info"), t(_fmtdate(r[2]))]))

    # ---- Consultor Comercial IA · histórico de interações (crm_activities READ) ----
    await safe("consultor", tbl(
        "Consultor Comercial IA", f"{await _scalar(db, 'SELECT count(*) FROM crm_activities')} interações comerciais",
        "—", ["Assunto", "Tipo", "Resultado", "Data"], "2fr 1fr 1.2fr 1fr",
        "SELECT coalesce(subject,'—'), coalesce(type,'—'), coalesce(outcome,'—'), coalesce(completed_at, scheduled_at, created_at) "
        "FROM crm_activities ORDER BY coalesce(completed_at, scheduled_at, created_at) DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), b((r[1] or '—').replace('_', ' ').capitalize(), "info"),
                   t((r[2] or '—').capitalize()), t(_fmtdate(r[3]))]))

    return out
