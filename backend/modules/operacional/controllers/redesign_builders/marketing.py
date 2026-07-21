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


async def build(db) -> dict:
    out, safe, tbl = _helpers(db)

    # 1) Funil — leads
    await safe("funil", tbl(
        "Funil", "Leads no funil comercial", "Novo lead",
        ["Lead", "Empresa", "Origem", "Score", "Status"],
        "1.8fr 1.6fr 1fr 0.7fr 0.9fr",
        "SELECT coalesce(name,'—'), coalesce(company,'—'), coalesce(source,'—'), "
        "coalesce(score,0), coalesce(status,'—') FROM leads WHERE coalesce(is_active,true) "
        "ORDER BY score DESC NULLS LAST, created_at DESC LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND), t(r[1]), t(r[2]), t(str(r[3])), _bs(r[4])]))

    # 2) Campanhas — marketing_campaigns (real; hoje 0 = honesto)
    await safe("campanhas", tbl(
        "Campanhas", "Campanhas de marketing", "Nova campanha",
        ["Campanha", "Tipo", "Status", "Orçamento", "Gasto"],
        "1.8fr 1fr 0.9fr 1fr 1fr",
        "SELECT coalesce(name,'—'), coalesce(type::text,'—'), coalesce(status::text,'—'), "
        "coalesce(budget,0), coalesce(spent,0) FROM marketing_campaigns "
        "ORDER BY created_at DESC LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND), t(r[1]), _bs(r[2]), t(brl(r[3])), t(brl(r[4]))]))

    # 3) Lead magnet — marketing_assets (real; 0 = honesto)
    await safe("lead-magnet", tbl(
        "Lead magnet", "Materiais de captura", "Novo material",
        ["Material", "Tipo", "Downloads", "Criado"],
        "2fr 1.2fr 1fr 1fr",
        "SELECT coalesce(name,'—'), coalesce(type::text,'—'), coalesce(downloads,0), created_at "
        "FROM marketing_assets ORDER BY downloads DESC NULLS LAST, created_at DESC LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND), t(r[1]), t(str(r[2])), t(_d(r[3]))]))

    # 4) Biblioteca — marketing_content_drafts (real; 0 = honesto)
    await safe("biblioteca", tbl(
        "Biblioteca", "Conteúdos produzidos", "Novo conteúdo",
        ["Título", "Formato", "Objetivo", "Status"],
        "2fr 1fr 1.4fr 0.9fr",
        "SELECT coalesce(titulo,'—'), coalesce(formato_label, formato, '—'), "
        "coalesce(objetivo,'—'), coalesce(status::text,'—') FROM marketing_content_drafts "
        "ORDER BY created_at DESC LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND), t(r[1]), t(r[2]), _bs(r[3])]))

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

    return out
