"""Redesign builder — Licitações.

Estende `_build_licitacoes` (base: visao, oportunidades, editais, propostas,
certidoes, contratos) e liga disputas·documentos·resultados lendo as tabelas
reais de licitação (bidding_*), hoje vazias = 0 linhas honestas. A tela `ia`
não tem tabela de origem no clássico → deixada como está (sem fabricar dado).
"""

from modules.operacional.controllers.redesign_data_controller import (
    _build_licitacoes,
    _helpers,
    b,
    brl,
    t,
)

SLUG = "licitacoes"
EXTRA_MENU: list[dict] = []
_ND = "#0F1B3A"


def _d(v, fmt="%d/%m/%Y"):
    try:
        return v.strftime(fmt) if v else "—"
    except Exception:
        return "—"


def _bs(v):
    s = (v or "").lower()
    if s in ("ganho", "homologado", "vencido_ganho", "adjudicado", "ativo", "publicado", "won"):
        return b(v or "—", "ok")
    if s in ("aberto", "em_disputa", "disputa", "aguardando", "participando", "em_analise", "publicada"):
        return b(v or "—", "warn")
    if s in ("perdido", "cancelado", "deserto", "fracassado", "revogado", "impugnado"):
        return b(v or "—", "bad")
    return b(v or "—", "info")


# Status/modalidade — espelha statusLabel do clássico (licitacoes/page.tsx)
_BID_ST = {"draft": ("Rascunho", "mut"), "analyzing": ("Em Análise", "info"),
           "decided_go": ("Participar", "info"), "proposal_ready": ("Proposta Pronta", "warn"),
           "in_dispute": ("Em Disputa", "warn"), "won": ("GANHA", "ok"), "lost": ("Perdida", "bad")}
_MODAL = {"pregao_eletronico": "Pregão Eletrônico", "pregao_presencial": "Pregão Presencial",
          "concorrencia": "Concorrência", "tomada_precos": "Tomada de Preços",
          "convite": "Convite", "dispensa": "Dispensa", "inexigibilidade": "Inexigibilidade"}


def _bid_status(v):
    lbl, tone = _BID_ST.get((v or "").lower(), (v or "—", "info"))
    return b(lbl, tone)


def _modal(v):
    return _MODAL.get((v or "").lower(), (v or "—").replace("_", " ").capitalize())


_PROP_ST = {"draft": ("Rascunho", "mut"), "sent": ("Enviada", "warn"), "accepted": ("Aceita", "ok"),
            "rejected": ("Recusada", "bad"), "expired": ("Expirada", "bad")}
_CONTR_ST = {"draft": ("Rascunho", "mut"), "active": ("Ativo", "ok"), "suspended": ("Suspenso", "warn"),
             "cancelled": ("Cancelado", "bad"), "expired": ("Expirado", "bad"), "finished": ("Encerrado", "mut")}


def _prop_status(v):
    lbl, tone = _PROP_ST.get((v or "").lower(), ((v or "—").capitalize(), "info"))
    return b(lbl, tone)


def _contr_status(v):
    lbl, tone = _CONTR_ST.get((v or "").lower(), ((v or "—").capitalize(), "info"))
    return b(lbl, tone)


async def build(db) -> dict:
    out = await _build_licitacoes(db)
    _o2, _s2, tbl = _helpers(db)

    async def safe(key, coro):
        try:
            out[key] = await coro
        except Exception:
            try:
                await db.rollback()
            except Exception:
                pass

    # 1) Disputas — bidding_tenders em que participamos
    await safe("disputas", tbl(
        "Disputas", "Licitações em disputa", "—",
        ["Número", "Órgão", "Modalidade", "Abertura", "Status"],
        "1fr 1.8fr 1.1fr 1fr 0.9fr",
        "SELECT coalesce(numero,'—'), coalesce(orgao_nome,'—'), coalesce(modalidade::text,'—'), "
        "data_abertura, coalesce(status::text,'—') FROM bidding_tenders WHERE coalesce(participando,false) "
        "ORDER BY data_abertura DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND), t(r[1]), t(_modal(r[2])), t(_d(r[3])), _bid_status(r[4])]))

    # 2) Documentos — bidding_tender_documents
    await safe("documentos", tbl(
        "Documentos", "Documentos de licitação", "—",
        ["Documento", "Tipo", "Obrigatório", "Criado"],
        "2fr 1.2fr 1fr 1fr",
        "SELECT coalesce(nome,'—'), coalesce(tipo::text,'—'), coalesce(obrigatorio,false), created_at "
        "FROM bidding_tender_documents ORDER BY created_at DESC LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND), t((r[1] or "—").replace("_", " ")),
                   (b("Sim", "warn") if r[2] else b("Não", "mut")), t(_d(r[3]))]))

    # 3) Resultados — bidding_tenders homologadas/com resultado
    await safe("resultados", tbl(
        "Resultados", "Resultados de licitações", "—",
        ["Número", "Órgão", "Objeto", "Valor homologado", "Status"],
        "1fr 1.5fr 2fr 1.2fr 0.9fr",
        "SELECT coalesce(numero,'—'), coalesce(orgao_nome,'—'), coalesce(objeto_resumido, objeto, '—'), "
        "coalesce(valor_homologado,0), coalesce(status::text,'—') FROM bidding_tenders "
        "WHERE (status IN ('won','lost') OR data_resultado IS NOT NULL OR coalesce(valor_homologado,0)>0) "
        "ORDER BY coalesce(data_resultado, data_abertura) DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND), t(r[1]), t((r[2] or "—")[:80]), t(brl(r[3]), 600), _bid_status(r[4])]))

    # Editais — SOBRESCREVE a base (Modalidade+Status crus) → PT
    await safe("editais", tbl(
        "Editais", "Editais monitorados", "—",
        ["Nº / Objeto", "Órgão", "Modalidade", "Valor estimado", "Status", "Participa"],
        "2fr 1.6fr 1.1fr 1fr 0.9fr 0.8fr",
        "SELECT coalesce(objeto_resumido, objeto, numero, '—'), coalesce(orgao_nome,'—'), "
        "coalesce(modalidade,'—'), valor_estimado, coalesce(status,'—'), coalesce(participando,false) "
        "FROM bidding_tenders ORDER BY data_abertura DESC NULLS LAST LIMIT 200",
        lambda r: [t((r[0] or "—")[:70], 600, _ND), t(r[1]), t(_modal(r[2])), t(brl(r[3] or 0)),
                   _bid_status(r[4]), (b("Sim", "ok") if r[5] else b("Não", "mut"))]))

    # Propostas — SOBRESCREVE a base (Status cru) → PT
    await safe("propostas", tbl(
        "Propostas", "Propostas comerciais", "—",
        ["Número", "Cliente", "Título", "Valor", "Status"], "1fr 1.6fr 1.6fr 1fr 0.9fr",
        "SELECT coalesce(number,'—'), coalesce(client_name,'—'), coalesce(title,'—'), "
        "coalesce(total,subtotal,0), status::text FROM proposals ORDER BY created_at DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, _ND), t(r[1]), t(r[2]), t(brl(r[3]), 600), _prop_status(r[4])]))

    # Contratos — SOBRESCREVE a base (Status cru 'Active') → PT
    await safe("contratos", tbl(
        "Contratos", "Contratos de prestação", "—",
        ["Contrato", "Cliente", "Mensal", "Total", "Status"], "1.2fr 1.6fr 1fr 1fr 0.9fr",
        "SELECT coalesce(ct.contract_number,'—'), coalesce(cl.name, ct.name, '—'), "
        "coalesce(ct.monthly_value,0), coalesce(ct.total_value,0), ct.status::text "
        "FROM contracts ct LEFT JOIN clients cl ON cl.id=ct.client_id ORDER BY ct.start_date DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, _ND), t(r[1]), t(brl(r[2]), 600), t(brl(r[3])), _contr_status(r[4])]))

    return out
