"""Redesign builder — Área do Cliente (NOVO; portal do cliente, visão admin).

Não havia builder (100% mock). Liga as 6 telas do portal com dado REAL agregado
(preview administrativo — o endpoint roda em contexto admin, não escopado por
cliente): clientes, rondas, ocorrências/chamados, recebíveis, kits de documentos.
"""

from modules.operacional.controllers.redesign_data_controller import (
    _helpers,
    b,
    brl,
    t,
)

SLUG = "area-do-cliente"
EXTRA_MENU: list[dict] = []
_ND = "#0F1B3A"


def _d(v, fmt="%d/%m/%Y"):
    try:
        return v.strftime(fmt) if v else "—"
    except Exception:
        return "—"


def _bs(v):
    s = (v or "").lower()
    if s in ("ativo", "active", "pago", "paid", "resolvido", "resolved", "concluido", "concluida", "aprovado", "assinado"):
        return b(v or "—", "ok")
    if s in ("pendente", "aberto", "open", "em_andamento", "andamento", "agendada", "scheduled", "em_aberto", "a_vencer"):
        return b(v or "—", "warn")
    if s in ("vencido", "overdue", "cancelado", "inadimplente", "critico", "critical", "protestado"):
        return b(v or "—", "bad")
    return b(v or "—", "info")


async def build(db) -> dict:
    out, safe, tbl = _helpers(db)

    # 1) Início / dashboard — clients (carteira)
    await safe("dashboard", tbl(
        "Início", "Carteira de clientes", "—",
        ["Cliente", "Segmento", "Status", "MRR", "Saúde"],
        "2fr 1.2fr 0.9fr 1fr 0.7fr",
        "SELECT coalesce(name,'—'), coalesce(segment::text,'—'), coalesce(status::text,'—'), "
        "coalesce(mrr,0), coalesce(health_score,0) FROM clients WHERE coalesce(ativo,true) "
        "ORDER BY mrr DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND), t(r[1]), _bs(r[2]), t(brl(r[3])), t(str(r[4]))]))

    # 2) Operação — inspection_rounds (posts_visited é jsonb → uso jsonb_array_length)
    await safe("operacao", tbl(
        "Operação", "Rondas e supervisão", "—",
        ["Ronda", "Inspetor", "Status", "Agendada", "Postos", "Ocorrências"],
        "1fr 1.4fr 0.9fr 1fr 0.7fr 0.9fr",
        "SELECT coalesce(code,'—'), coalesce(inspector_name,'—'), coalesce(status::text,'—'), "
        "scheduled_date, (CASE WHEN jsonb_typeof(posts_visited)='array' THEN jsonb_array_length(posts_visited) ELSE 0 END), coalesce(total_occurrences,0) "
        "FROM inspection_rounds WHERE coalesce(is_active,true) "
        "ORDER BY scheduled_date DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND), t(r[1]), _bs(r[2]), t(_d(r[3])), t(str(r[4])), t(str(r[5]))]))

    # 3) Chamados — occurrences
    await safe("chamados", tbl(
        "Chamados", "Ocorrências e chamados", "Abrir chamado",
        ["Código", "Título", "Tipo", "Severidade", "Status", "Quando"],
        "0.9fr 1.8fr 1fr 1fr 0.9fr 1fr",
        "SELECT coalesce(code,'—'), coalesce(title,'—'), coalesce(occurrence_type::text,'—'), "
        "coalesce(severity::text,'—'), coalesce(status::text,'—'), occurred_at "
        "FROM occurrences ORDER BY occurred_at DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0]), t(r[1] or "—", 600, _ND), t((r[2] or "—").replace("_", " ")), _bs(r[3]), _bs(r[4]), t(_d(r[5]))]))

    # 4) Financeiro — receivable_accounts
    await safe("financeiro", tbl(
        "Financeiro", "Contas a receber do cliente", "—",
        ["Documento", "Cliente", "Competência", "Valor", "Vencimento", "Status"],
        "1fr 1.6fr 0.9fr 1fr 1fr 0.9fr",
        "SELECT coalesce(document_number, code, '—'), coalesce(customer_name,'—'), "
        "coalesce(reference_month,'—'), coalesce(net_value,0), due_date, coalesce(status::text,'—') "
        "FROM receivable_accounts WHERE coalesce(ativo,true) ORDER BY due_date DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0]), t(r[1] or "—", 600, _ND), t(r[2]), t(brl(r[3]), 600), t(_d(r[4])), _bs(r[5])]))

    # 5) Documentos / kits — ged_document_kits
    await safe("kits", tbl(
        "Documentos", "Kits de documentos entregues", "—",
        ["Cliente", "Competência", "Docs", "Assinados", "Conclusão", "Status"],
        "1.8fr 1fr 0.7fr 0.8fr 0.9fr 0.9fr",
        "SELECT coalesce(c.name, k.client_id::text), coalesce(to_char(k.reference_month,'MM/YYYY'),'—'), "
        "coalesce(k.total_documents,0), coalesce(k.documents_signed,0), "
        "coalesce(k.completion_percentage,0), coalesce(k.status::text,'—') "
        "FROM ged_document_kits k LEFT JOIN clients c ON c.id = k.client_id "
        "ORDER BY k.created_at DESC LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND), t(r[1]), t(str(r[2])), t(str(r[3])),
                   t(f"{float(r[4]):.0f}%"), _bs(r[5])]))

    # 6) Relatórios / analytics — agregado real de recebíveis por status
    await safe("analytics", tbl(
        "Relatórios", "Recebíveis por status", "—",
        ["Status", "Contas", "Total"],
        "2fr 1fr 1.4fr",
        "SELECT coalesce(status::text,'—'), count(*), coalesce(sum(net_value),0) "
        "FROM receivable_accounts WHERE coalesce(ativo,true) GROUP BY status "
        "ORDER BY sum(net_value) DESC NULLS LAST LIMIT 50",
        lambda r: [_bs(r[0]), t(str(r[1])), t(brl(r[2]), 600)]))

    return out
