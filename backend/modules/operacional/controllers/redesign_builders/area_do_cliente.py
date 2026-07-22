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


# Status em PT (traduz + colore) — o _bs só coloria, deixando o valor cru/minúsculo.
_AC_ST = {"active": ("Ativo", "ok"), "ativo": ("Ativo", "ok"), "inactive": ("Inativo", "mut"),
          "pago": ("Pago", "ok"), "paga": ("Paga", "ok"), "paid": ("Pago", "ok"),
          "pendente": ("Pendente", "warn"), "pending": ("Pendente", "warn"),
          "vencido": ("Vencido", "bad"), "overdue": ("Vencido", "bad"), "inadimplente": ("Inadimplente", "bad"),
          "cancelado": ("Cancelado", "bad"), "cancelada": ("Cancelada", "bad"), "cancelled": ("Cancelado", "bad"),
          "concluido": ("Concluído", "ok"), "concluida": ("Concluída", "ok"), "completed": ("Concluído", "ok"),
          "agendada": ("Agendada", "warn"), "scheduled": ("Agendada", "warn"),
          "em_andamento": ("Em andamento", "warn"), "aberto": ("Aberto", "warn"), "open": ("Aberto", "warn"),
          "resolvido": ("Resolvido", "ok"), "em_montagem": ("Em montagem", "warn"),
          "completo": ("Completo", "ok"), "enviado": ("Enviado", "ok"), "a_vencer": ("A vencer", "warn")}

_SEG = {"small": "Pequeno", "medium": "Médio", "large": "Grande", "enterprise": "Enterprise", "mid_market": "Mid Market"}
_TIPO = {"incidente": "Incidente", "manutencao": "Manutenção", "seguranca": "Segurança",
         "limpeza": "Limpeza", "reclamacao": "Reclamação", "solicitacao": "Solicitação"}


def _st(v):
    lbl, tone = _AC_ST.get((v or "").lower(), ((v or "—").replace("_", " ").capitalize(), "info"))
    return b(lbl, tone)


def _seg(v):
    return _SEG.get((v or "").lower(), (v or "—").capitalize())


def _tipo(v):
    return _TIPO.get((v or "").lower(), (v or "—").replace("_", " ").capitalize())


def _is_uuid(s):
    s = (s or "").strip()
    return len(s) == 36 and s.count("-") == 4 and " " not in s


async def build(db) -> dict:
    out, safe, tbl = _helpers(db)

    # 1) Início / dashboard — clients (carteira)
    await safe("dashboard", tbl(
        "Início", "Carteira de clientes", "—",
        ["Cliente", "Segmento", "Status", "MRR", "Saúde"],
        "2fr 1.2fr 0.9fr 1fr 0.7fr",
        "SELECT coalesce(name,'—'), coalesce(segment::text,'—'), coalesce(status::text,'—'), "
        "coalesce(mrr,0), health_score FROM clients WHERE coalesce(ativo,true) "
        "ORDER BY mrr DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND), t(_seg(r[1])), _st(r[2]), t(brl(r[3])),
                   t("n/d" if r[4] is None else f"{float(r[4]):.0f}", 500,
                     "#94A3B8" if r[4] is None else "#334155")]))

    # 2) Operação — inspection_rounds (posts_visited é jsonb → uso jsonb_array_length)
    await safe("operacao", tbl(
        "Operação", "Rondas e supervisão", "—",
        ["Ronda", "Inspetor", "Status", "Agendada", "Postos", "Ocorrências"],
        "1fr 1.4fr 0.9fr 1fr 0.7fr 0.9fr",
        "SELECT coalesce(code,'—'), coalesce(inspector_name,'—'), coalesce(status::text,'—'), "
        "scheduled_date, (CASE WHEN jsonb_typeof(posts_visited)='array' THEN jsonb_array_length(posts_visited) ELSE 0 END), coalesce(total_occurrences,0) "
        "FROM inspection_rounds WHERE coalesce(is_active,true) "
        "ORDER BY scheduled_date DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND), t(r[1]), _st(r[2]), t(_d(r[3])), t(str(r[4])), t(str(r[5]))]))

    # 3) Chamados — occurrences
    await safe("chamados", tbl(
        "Chamados", "Ocorrências e chamados", "Abrir chamado",
        ["Código", "Título", "Tipo", "Severidade", "Status", "Quando"],
        "0.9fr 1.8fr 1fr 1fr 0.9fr 1fr",
        "SELECT coalesce(code,'—'), coalesce(title,'—'), coalesce(occurrence_type::text,'—'), "
        "coalesce(severity::text,'—'), coalesce(status::text,'—'), occurred_at "
        "FROM occurrences ORDER BY occurred_at DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0]), t(r[1] or "—", 600, _ND), t(_tipo(r[2])), _st(r[3]), _st(r[4]), t(_d(r[5]))]))

    # 4) Financeiro — receivable_accounts
    await safe("financeiro", tbl(
        "Financeiro", "Contas a receber do cliente", "—",
        ["Documento", "Cliente", "Competência", "Valor", "Vencimento", "Status"],
        "1fr 1.6fr 0.9fr 1fr 1fr 0.9fr",
        "SELECT coalesce(document_number, code, '—'), coalesce(customer_name,'—'), "
        "coalesce(reference_month,'—'), coalesce(net_value,0), due_date, coalesce(status::text,'—') "
        "FROM receivable_accounts WHERE coalesce(ativo,true) ORDER BY due_date DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0]), t(r[1] or "—", 600, _ND), t(r[2]), t(brl(r[3]), 600), t(_d(r[4])), _st(r[5])]))

    # 5) Documentos / kits — ged_document_kits
    await safe("kits", tbl(
        "Documentos", "Kits de documentos entregues", "—",
        ["Cliente", "Competência", "Docs", "Assinados", "Conclusão", "Status"],
        "1.8fr 1fr 0.7fr 0.8fr 0.9fr 0.9fr",
        "SELECT coalesce(c.name, k.client_id::text), coalesce(to_char(k.reference_month,'MM/YYYY'),'—'), "
        "coalesce(k.total_documents,0), coalesce(k.documents_signed,0), "
        "coalesce(k.completion_percentage,0), coalesce(k.status::text,'—') "
        "FROM ged_document_kits k LEFT JOIN ged_clients c ON c.id = k.client_id "
        "ORDER BY k.created_at DESC LIMIT 200",
        lambda r: [t("—" if _is_uuid(r[0]) else (r[0] or "—"), 600, _ND), t(r[1]), t(str(r[2])), t(str(r[3])),
                   t(f"{float(r[4]):.0f}%"), _st(r[5])]))

    # 6) Relatórios / analytics — agregado real de recebíveis por status
    await safe("analytics", tbl(
        "Relatórios", "Recebíveis por status", "—",
        ["Status", "Contas", "Total"],
        "2fr 1fr 1.4fr",
        "SELECT coalesce(status::text,'—'), count(*), coalesce(sum(net_value),0) "
        "FROM receivable_accounts WHERE coalesce(ativo,true) GROUP BY status "
        "ORDER BY sum(net_value) DESC NULLS LAST LIMIT 50",
        lambda r: [_st(r[0]), t(str(r[1])), t(brl(r[2]), 600)]))

    return out
