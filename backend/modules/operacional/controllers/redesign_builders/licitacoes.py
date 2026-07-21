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
        lambda r: [t(r[0] or "—", 600, _ND), t(r[1]), t((r[2] or "—").replace("_", " ")), t(_d(r[3])), _bs(r[4])]))

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
        "WHERE data_resultado IS NOT NULL ORDER BY data_resultado DESC LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND), t(r[1]), t((r[2] or "—")[:80]), t(brl(r[3]), 600), _bs(r[4])]))

    return out
