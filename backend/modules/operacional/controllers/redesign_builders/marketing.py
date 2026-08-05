"""Redesign builder — Marketing (NOVO módulo; não havia _build_marketing).

Módulo majoritariamente não construído no clássico: só `leads` tem dado real
(22). As demais telas leem tabelas REAIS porém hoje vazias (campanhas, ativos,
drafts de conteúdo) → 0 linhas HONESTAS ("aguardando dado"), nunca mock.
"""

from modules.operacional.controllers.redesign_data_controller import (
    _helpers,
    b,
    brl,
    t,
)

SLUG = "marketing"
EXTRA_MENU: list[dict] = []
_ND = "#0F1B3A"


def _d(v, fmt="%d/%m/%Y"):
    try:
        return v.strftime(fmt) if v else "—"
    except Exception:
        return "—"


def _bs(v):
    s = (v or "").lower()
    if s in ("ativo", "active", "aprovado", "approved", "publicado", "ganho", "won", "convertido", "qualificado"):
        return b(v or "—", "ok")
    if s in ("pendente", "rascunho", "draft", "em_andamento", "novo", "new", "andamento", "pausado", "paused"):
        return b(v or "—", "warn")
    if s in ("perdido", "lost", "cancelado", "rejeitado", "descartado", "encerrado"):
        return b(v or "—", "bad")
    return b(v or "—", "info")


# Lead status/source — espelha constants/crm/leadStatus.ts (LEAD_STATUS_LABELS / LEAD_SOURCE_LABELS)
_LEAD_ST = {"new": ("Novo", "info"), "novo": ("Novo", "info"), "contacted": ("Em contato", "info"),
            "qualified": ("Qualificado", "info"), "qualificado": ("Qualificado", "info"),
            "proposal": ("Proposta", "warn"), "proposta": ("Proposta", "warn"),
            "negotiation": ("Negociação", "warn"), "negociacao": ("Negociação", "warn"),
            "won": ("Convertido", "ok"), "converted": ("Convertido", "ok"), "ganho": ("Convertido", "ok"),
            "lost": ("Perdido", "bad"), "perdido": ("Perdido", "bad")}
_LEAD_SRC = {"website": "Website", "referral": "Indicação", "indicacao": "Indicação",
             "social_media": "Redes sociais", "cold_call": "Ligação fria", "event": "Evento",
             "evento": "Evento", "whatsapp": "WhatsApp", "other": "Outros", "outro": "Outros"}


def _lead_status(v):
    lbl, tone = _LEAD_ST.get((v or "").lower(), (v or "—", "info"))
    return b(lbl, tone)


def _lead_src(v):
    return _LEAD_SRC.get((v or "").lower(), (v or "—").capitalize())


_MKT = "/api/v1/marketing"

# Formatos REAIS do copywriter (crm/services/copywriter_agent.py FORMATOS) — nunca inventar.
_FORMATOS = [
    ("instagram_post", "Post de Instagram"), ("facebook_post", "Post de Facebook"),
    ("reel_roteiro", "Roteiro de Reels"), ("anuncio_meta", "Anúncio Meta (Facebook/Instagram Ads)"),
    ("anuncio_google", "Anúncio Google (Search)"), ("email", "E-mail"),
    ("whatsapp", "Mensagem de WhatsApp"),
]
# ContentStatus (crm/models/marketing_content.py)
_STATUS = [("rascunho", "Rascunho"), ("aprovado", "Aprovado"), ("arquivado", "Arquivado")]


def _opts(pares):
    return [{"value": v, "label": l} for v, l in pares]


def _conteudo_actions(r):
    """Ações por peça da biblioteca. r[0]=id. Endpoints do marketing_controller (já existem)."""
    cid = r[0]
    return [
        {"title": "Enviar peça por WhatsApp", "endpoint": f"{_MKT}/content/{cid}/send-whatsapp",
         "method": "POST", "btnLabel": "WhatsApp", "submitLabel": "Enviar agora",
         "btnStyle": "primary", "okMsg": "Peça enviada.",
         "fields": [{"key": "numero", "label": "Número (DDD + número)*", "type": "text",
                     "span": "span 2", "ph": "Ex.: 92 99999-9999"}]},
        {"title": "Alterar status da peça", "endpoint": f"{_MKT}/content/{cid}/status",
         "method": "PATCH", "btnLabel": "Status", "submitLabel": "Salvar status",
         "okMsg": "Status atualizado. Recarregue a tela.",
         "fields": [{"key": "status", "label": "Novo status*", "type": "select",
                     "span": "span 2", "ph": "Selecione", "options": _opts(_STATUS)}]},
    ]


async def build(db) -> dict:
    out, safe, tbl = _helpers(db)

    # 1) Funil — leads. id em r[0] p/ a ação de conversão (POST /leads/{id}/convert).
    await safe("funil", tbl(
        "Funil", "Leads no funil comercial", "Novo lead",
        ["Lead", "Empresa", "Origem", "Score", "Status"],
        "1.8fr 1.6fr 1fr 0.7fr 0.9fr",
        "SELECT id, coalesce(name,'—'), coalesce(company,'—'), coalesce(source,'—'), "
        "coalesce(score,0), coalesce(status,'—') FROM leads WHERE coalesce(is_active,true) "
        "ORDER BY score DESC NULLS LAST, created_at DESC LIMIT 200",
        lambda r: [t(r[1] or "—", 600, _ND), t(r[2]), t(_lead_src(r[3])), t(str(r[4])), _lead_status(r[5])]))
    # SEM ação de converter aqui: o funil lê `leads` (CRM) e /marketing/leads/{id}/convert
    # busca em `marketing_leads` — tabelas distintas. A conversão vive no lead-magnet.
    # O clássico também não tem escrita no funil (0 ações).

    # 2) Campanhas — marketing_campaigns (real; hoje 0 = honesto)
    await safe("campanhas", tbl(
        "Campanhas", "Campanhas de marketing", "Nova campanha",
        ["Campanha", "Tipo", "Status", "Orçamento", "Gasto"],
        "1.8fr 1fr 0.9fr 1fr 1fr",
        "SELECT id, coalesce(name,'—'), coalesce(type::text,'—'), coalesce(status::text,'—'), "
        "coalesce(budget,0), coalesce(spent,0) FROM marketing_campaigns "
        "ORDER BY created_at DESC LIMIT 200",
        lambda r: [t(r[1] or "—", 600, _ND), t(r[2]), _bs(r[3]), t(brl(r[4])), t(brl(r[5]))],
        editfn=lambda r: {"endpoint": f"{_MKT}/campaigns/{r[0]}", "method": "PATCH", "fields": [
            {"key": "name", "label": "Campanha", "type": "text", "value": r[1] or ""},
            {"key": "budget", "label": "Orçamento (R$)", "type": "number", "value": float(r[4] or 0)},
        ]}))

    # 3) Lead magnet — marketing_leads (leads CAPTURADOS), espelhando o clássico
    # (colunas Lead/Email/Campanha/Status/Ações). É aqui que a conversão para o CRM
    # faz sentido: /marketing/leads/{id}/convert lê `marketing_leads`.
    await safe("lead-magnet", tbl(
        "Lead magnet", "Leads capturados por campanha", "Novo lead",
        ["Lead", "E-mail", "Campanha", "Status"],
        "1.6fr 1.8fr 1.4fr 0.9fr",
        "SELECT ml.id, coalesce(ml.name,'—'), coalesce(ml.email,'—'), coalesce(mc.name,'—'), "
        "coalesce(ml.status,'—') FROM marketing_leads ml "
        "LEFT JOIN marketing_campaigns mc ON mc.id = ml.campaign_id "
        "ORDER BY ml.created_at DESC LIMIT 200",
        lambda r: [t(r[1] or "—", 600, _ND), t(r[2]), t(r[3]), _bs(r[4])],
        actionsfn=lambda r: ([] if (r[4] or "").lower() in ("converted", "convertido") else [
            {"title": f"Converter {r[1] or 'lead'} em lead do CRM",
             "endpoint": f"{_MKT}/leads/{r[0]}/convert", "method": "POST",
             "btnLabel": "Converter", "submitLabel": "Converter para o CRM",
             "btnStyle": "primary", "okMsg": "Lead convertido para o CRM. Recarregue a tela.",
             "fields": []}])))

    # 4) Biblioteca — marketing_content_drafts (real; 0 = honesto)
    await safe("biblioteca", tbl(
        "Biblioteca", "Conteúdos produzidos", "Novo conteúdo",
        ["Título", "Formato", "Objetivo", "Status"],
        "2fr 1fr 1.4fr 0.9fr",
        "SELECT id, coalesce(titulo,'—'), coalesce(formato_label, formato, '—'), "
        "coalesce(objetivo,'—'), coalesce(status::text,'—') FROM marketing_content_drafts "
        "ORDER BY created_at DESC LIMIT 200",
        lambda r: [t(r[1] or "—", 600, _ND), t(r[2]), t(r[3]), _bs(r[4])],
        editfn=lambda r: {"endpoint": f"{_MKT}/content/{r[0]}", "method": "PATCH", "fields": [
            {"key": "titulo", "label": "Título", "type": "text", "value": r[1] or ""},
        ]},
        actionsfn=_conteudo_actions))

    # 5) Copywriter IA — marketing_content_drafts (drafts gerados; 0 = honesto)
    await safe("copywriter", tbl(
        "Copywriter IA", "Textos gerados pela IA", "Gerar texto",
        ["Título", "Formato", "Público", "Status"],
        "2fr 1fr 1.4fr 0.9fr",
        "SELECT coalesce(titulo,'—'), coalesce(formato_label, formato, '—'), "
        "coalesce(publico,'—'), coalesce(status::text,'—') FROM marketing_content_drafts "
        "ORDER BY created_at DESC LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND), t(r[1]), t(r[2]), _bs(r[3])]))

    # 6) Estrategista IA — marketing_content_drafts (foco briefing/objetivo; 0 = honesto)
    await safe("estrategista", tbl(
        "Estrategista IA", "Estratégias e briefings", "Nova estratégia",
        ["Objetivo", "Público", "Briefing", "Status"],
        "1.4fr 1.2fr 2fr 0.9fr",
        "SELECT coalesce(objetivo,'—'), coalesce(publico,'—'), coalesce(left(briefing,90),'—'), "
        "coalesce(status::text,'—') FROM marketing_content_drafts ORDER BY created_at DESC LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND), t(r[1]), t(r[2]), _bs(r[3])]))

    # 7) Brand Voice — marketing_content_drafts (modelo/tom; 0 = honesto)
    await safe("brand-voice", tbl(
        "Brand Voice", "Modelos de tom de voz", "Configurar",
        ["Modelo", "Formato", "Objetivo", "Status"],
        "1.4fr 1fr 1.6fr 0.9fr",
        "SELECT coalesce(modelo,'—'), coalesce(formato_label, formato, '—'), "
        "coalesce(objetivo,'—'), coalesce(status::text,'—') FROM marketing_content_drafts "
        "WHERE modelo IS NOT NULL ORDER BY created_at DESC LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND), t(r[1]), t(r[2]), _bs(r[3])]))

    # ── FASE 2: telas-form de ESCRITA (apontam direto p/ marketing_controller, que já existe) ──
    # ModuleView.tsx:737 só desenha o CTA se screens[ctaTo] existir no payload (não precisa de menu).
    out["novo-lead"] = {
        "title": "Novo lead", "sub": "Cadastrar um lead no funil", "cta": "Cadastrar lead",
        "type": "form", "submit": {"endpoint": f"{_MKT}/leads/", "okMsg": "Lead cadastrado."},
        "fields": [
            {"key": "name", "label": "Nome*", "type": "text", "span": "span 2", "ph": "Nome do contato"},
            {"key": "email", "label": "E-mail", "type": "text", "span": "span 1"},
            {"key": "phone", "label": "Telefone", "type": "text", "span": "span 1"},
            {"key": "whatsapp", "label": "WhatsApp", "type": "text", "span": "span 1"},
            {"key": "source", "label": "Origem", "type": "select", "span": "span 1", "ph": "De onde veio",
             "options": _opts([("website", "Website"), ("indicacao", "Indicação"), ("social_media", "Redes sociais"),
                               ("whatsapp", "WhatsApp"), ("evento", "Evento"), ("outro", "Outros")])},
        ],
    }
    out["nova-campanha"] = {
        "title": "Nova campanha", "sub": "Criar uma campanha de marketing", "cta": "Criar campanha",
        "type": "form", "submit": {"endpoint": f"{_MKT}/campaigns/", "okMsg": "Campanha criada."},
        "fields": [
            {"key": "name", "label": "Nome da campanha*", "type": "text", "span": "span 2"},
            {"key": "type", "label": "Tipo", "type": "select", "span": "span 1", "ph": "Tipo",
             "options": _opts([("organic", "Orgânica"), ("paid", "Paga")])},
            # value=0: campo number vazio vira "" e o float() do Pydantic estoura 422.
            {"key": "budget", "label": "Orçamento (R$)", "type": "number", "span": "span 1", "value": 0},
            # Datas ficam de fora de propósito: são opcionais e "" quebraria a coluna date.
            {"key": "description", "label": "Descrição", "type": "textarea", "span": "span 2"},
        ],
    }
    out["gerar-texto"] = {
        "title": "Copywriter IA", "sub": "Gerar texto na voz da marca Conecta Mais", "cta": "Gerar texto",
        "type": "form", "submit": {"endpoint": f"{_MKT}/copywriter/generate", "okMsg": "Texto gerado."},
        "fields": [
            {"key": "formato", "label": "Formato*", "type": "select", "span": "span 1",
             "ph": "O que gerar", "options": _opts(_FORMATOS)},
            {"key": "n_variacoes", "label": "Variações", "type": "number", "span": "span 1", "value": 3},
            {"key": "objetivo", "label": "Objetivo", "type": "text", "span": "span 1",
             "ph": "Ex.: captar condomínios para portaria remota"},
            {"key": "publico", "label": "Público", "type": "text", "span": "span 1",
             "ph": "Ex.: síndicos e administradoras"},
            {"key": "briefing", "label": "Briefing*", "type": "textarea", "span": "span 2",
             "ph": "O que a peça precisa dizer"},
        ],
    }
    out["nova-estrategia"] = {
        "title": "Estrategista IA", "sub": "Montar plano de campanha (público, mensagem, canais)",
        "cta": "Gerar plano", "type": "form",
        "submit": {"endpoint": f"{_MKT}/estrategista/plan", "okMsg": "Plano gerado."},
        "fields": [
            {"key": "objetivo", "label": "Objetivo*", "type": "textarea", "span": "span 2",
             "ph": "Ex.: captar 15 condomínios para portaria remota em Manaus"},
            {"key": "periodo_dias", "label": "Período (dias)", "type": "number", "span": "span 1", "value": 30},
            {"key": "orcamento", "label": "Orçamento", "type": "text", "span": "span 1", "ph": "Ex.: R$ 3.000"},
            {"key": "canais_preferidos", "label": "Canais preferidos", "type": "text", "span": "span 2",
             "ph": "Ex.: Instagram, WhatsApp, Google Ads"},
        ],
    }

    # Religa os botões das tabelas (sem ctaTo o ModuleView não desenha o CTA).
    # "Novo lead" fica no lead-magnet (grava em marketing_leads, que é o que essa tela lê).
    # No funil NÃO entra: ele lê `leads` do CRM e o lead criado não apareceria ali.
    for _tela, _destino in (("lead-magnet", "novo-lead"), ("campanhas", "nova-campanha"),
                            ("copywriter", "gerar-texto"), ("estrategista", "nova-estrategia")):
        if _tela in out:
            out[_tela]["ctaTo"] = _destino

    return out
