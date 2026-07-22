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


_LEAD_TONE = {"novo": "info", "new": "info", "em_contato": "warn", "contacted": "warn",
              "qualificado": "ok", "qualified": "ok", "convertido": "ok", "converted": "ok",
              "perdido": "bad", "lost": "bad"}


async def build(db) -> dict:
    out, safe, tbl = _helpers(db)
    out.update(await _base(db))

    # ---- Leads (override: + coluna Origem, que o clássico mostra e a base não) ----
    await safe("leads", tbl(
        "Leads", f"{await _scalar(db, 'SELECT count(*) FROM leads')} leads", "Novo lead",
        ["Lead", "Empresa", "Origem", "Valor estimado", "Status"], "2fr 1.5fr 1fr 1fr 0.9fr",
        "SELECT name, coalesce(company,'—'), coalesce(source,'—'), coalesce(expected_value,0), coalesce(status::text,'—') "
        "FROM leads ORDER BY created_at DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0])), t(r[1]),
                   b((r[2] or '—').replace('_', ' ').capitalize(), "mut"), t(brl(r[3]), 600),
                   b((r[4] or '—').replace('_', ' ').capitalize(), _LEAD_TONE.get((r[4] or '').lower(), "info"))]))

    # ---- Fidelidade: oportunidades e propostas mostram KPIs de resumo no clássico.
    #      Tela 'table' não tem KPI-card (não edito ModuleView) → trago no subtítulo. ----
    try:
        _ot = await _scalar(db, "SELECT count(*) FROM opportunities")
        _oneg = await _scalar(db, "SELECT count(*) FROM opportunities WHERE stage::text='negotiation'")
        _oprop = await _scalar(db, "SELECT count(*) FROM opportunities WHERE stage::text='proposal'")
        _opipe = await _scalar(db, "SELECT coalesce(sum(value),0) FROM opportunities WHERE stage::text NOT IN ('closed_won','closed_lost')")
        if isinstance(out.get("oportunidades"), dict):
            out["oportunidades"]["sub"] = f"{_ot} oportunidades · Em negociação {_oneg} · Em proposta {_oprop} · Pipeline {brl(_opipe)}"
        _pt = await _scalar(db, "SELECT count(*) FROM proposals")
        _pd = await _scalar(db, "SELECT count(*) FROM proposals WHERE status::text='draft'")
        _ps = await _scalar(db, "SELECT count(*) FROM proposals WHERE status::text='sent'")
        _pa = await _scalar(db, "SELECT count(*) FROM proposals WHERE status::text='accepted'")
        if isinstance(out.get("propostas"), dict):
            out["propostas"]["sub"] = f"{_pt} propostas · Rascunho {_pd} · Enviadas {_ps} · Aprovadas {_pa}"
    except Exception:  # noqa: BLE001
        await db.rollback()

    # ---- Contatos (override: + Email e Principal, que o clássico mostra) ----
    await safe("contatos", tbl(
        "Contatos", f"{await _scalar(db, 'SELECT count(*) FROM crm_contacts')} contatos",
        "—", ["Contato", "Cliente", "Cargo", "Email", "Telefone", "Principal"], "1.6fr 1.8fr 1fr 1.8fr 1.1fr 0.8fr",
        "SELECT c.name, coalesce(cl.name,'—'), coalesce(c.role,'—'), coalesce(c.email,'—'), "
        "coalesce(nullif(c.phone,''), c.whatsapp, '—'), c.is_primary "
        "FROM crm_contacts c LEFT JOIN clients cl ON cl.id=c.client_id "
        "ORDER BY c.is_primary DESC NULLS LAST, c.name LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0])), t(r[1]), t((r[2] or '—').capitalize()),
                   t(r[3]), t(r[4]), b("Principal", "ok") if r[5] else b("—", "mut")]))

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
