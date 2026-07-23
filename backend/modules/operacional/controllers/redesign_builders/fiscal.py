"""Fiscal (T1) — delega ao _build_fiscal e liga o menu json 'certidoes' às CNDs reais
(ged_certidoes) que já são montadas como 'certidoes-cnd'. Ação fiscal (transmitir) segue GATED.
nfse-multi/sped/ecac/consultor = capacidade sem tabela → honesto vazio."""
import os
from datetime import date as _date

from modules.operacional.controllers.redesign_data_controller import (
    IC, _ICF, _build_fiscal, _fmtdate, _helpers, _scalar, b, brl, doc, t,
)

SLUG = "fiscal"
EXTRA_MENU: list[dict] = []

_GTONE = {"pago": "ok", "paga": "ok", "conciliado": "ok", "pendente": "warn", "vencido": "bad", "vencida": "bad"}


def _guia_existe(fp) -> bool:
    """True só se o arquivo_pdf da guia existe em disco sob /app/uploads (evita botão-lixo)."""
    if not fp:
        return False
    try:
        c = os.path.realpath(fp)
        return c.startswith("/app/uploads/") and os.path.exists(c)
    except Exception:  # noqa: BLE001
        return False


async def build(db) -> dict:
    out = await _build_fiscal(db)
    _, _safe, tbl = _helpers(db)

    # DOCUMENTOS — Certidões (CND): baixar/abrir o PDF real por certidão. Rota provada 200:
    # /api/v1/gedeon/cnd/pdf/{document_type} (FileResponse de ged_certidoes.file_path). Só liga o
    # botão onde o arquivo EXISTE (file_path preenchido) — senão o endpoint 404 (nunca botão-lixo).
    _hoje = _date.today()

    def _cnd_sit(exp):
        if exp is None:
            return b("—", "info")
        d = exp.date() if hasattr(exp, "date") else exp
        try:
            dias = (d - _hoje).days
        except TypeError:
            return b("—", "info")
        return b("Vencida", "bad") if dias < 0 else (b(f"Vence em {dias}d", "warn") if dias <= 30 else b("Válida", "ok"))

    try:
        out["certidoes-cnd"] = await tbl(
            "Certidões (CND)", f"{await _scalar(db, 'SELECT count(*) FROM ged_certidoes')} certidões", "—",
            ["Certidão", "Tipo", "Órgão emissor", "Emissão", "Validade", "Situação"], "1.8fr 1.1fr 1.3fr 0.9fr 0.9fr 1fr",
            "SELECT coalesce(name,'—'), coalesce(document_type,'—'), coalesce(issuing_body,'—'), issue_date, expiry_date, "
            "(file_path IS NOT NULL AND file_path<>''), document_type FROM ged_certidoes ORDER BY expiry_date ASC NULLS LAST LIMIT 200",
            lambda r: [t((r[0] or '—')[:48], 600, "#0F1B3A"), t((r[1] or '—').replace('certidao_negativa_', 'CND ').replace('_', ' ')),
                       t((r[2] or '—')[:32]), t(_fmtdate(r[3])), t(_fmtdate(r[4])), _cnd_sit(r[4])],
            docsfn=lambda r: [doc("CND", f"/api/v1/gedeon/cnd/pdf/{r[6]}", fmt="pdf")] if r[5] else [])
    except Exception:  # noqa: BLE001
        pass

    # DOCUMENTOS — Guias FGTS/INSS (Onvio): baixar o PDF real da guia. Rota nova read-only
    # /api/v1/fiscal/guias-drive/guia-onvio/{fonte}/{id}/pdf. Botão SÓ onde o arquivo existe em
    # disco (checagem os no builder) — muitas guias têm path mas o Onvio não manteve o arquivo local.
    try:
        out["guias-fgts"] = await tbl(
            "Guias FGTS", f"{await _scalar(db, 'SELECT count(*) FROM fgts_guias')} guias (Onvio)", "—",
            ["Competência", "Tipo", "Documento", "Status"], "1fr 1.4fr 0.9fr 0.9fr",
            "SELECT id, coalesce(mes_ref,'—'), coalesce(tipo,'—'), arquivo_pdf, coalesce(status,'—') "
            "FROM fgts_guias ORDER BY mes_ref DESC NULLS LAST, tipo LIMIT 200",
            lambda r: [t(r[1], 600, "#0F1B3A"), t((r[2] or '—').replace('_', ' ').capitalize()),
                       b("PDF", "ok") if _guia_existe(r[3]) else (b("no Drive", "mut") if r[3] else t("—")),
                       b((r[4] or '—').capitalize(), _GTONE.get((r[4] or '').lower(), "info"))],
            docsfn=lambda r: [doc("Guia FGTS", f"/api/v1/fiscal/guias-drive/guia-onvio/fgts/{r[0]}/pdf", fmt="pdf")] if _guia_existe(r[3]) else [])
    except Exception:  # noqa: BLE001
        pass
    try:
        out["guias-inss"] = await tbl(
            "Guias INSS", f"{await _scalar(db, 'SELECT count(*) FROM inss_guias')} guias (Onvio)", "—",
            ["Competência", "Documento", "Status"], "1.2fr 0.9fr 0.9fr",
            "SELECT id, coalesce(competencia, mes_ref, '—'), arquivo_pdf, coalesce(status,'—') "
            "FROM inss_guias ORDER BY mes_ref DESC NULLS LAST LIMIT 200",
            lambda r: [t(r[1], 600, "#0F1B3A"), b("PDF", "ok") if _guia_existe(r[2]) else (b("no Drive", "mut") if r[2] else t("—")),
                       b((r[3] or '—').capitalize(), _GTONE.get((r[3] or '').lower(), "info"))],
            docsfn=lambda r: [doc("Guia INSS", f"/api/v1/fiscal/guias-drive/guia-onvio/inss/{r[0]}/pdf", fmt="pdf")] if _guia_existe(r[2]) else [])
    except Exception:  # noqa: BLE001
        pass

    # O item de menu json 'certidoes' estava vazio; aponta pras mesmas CNDs reais (agora com PDF).
    if "certidoes-cnd" in out:
        out["certidoes"] = out["certidoes-cnd"]

    # FIDELIDADE ao hub clássico (/modulos/fiscal): o clássico HEADLINEIA "NFS-e Emitidas"
    # (nfse_emitidas_nacional, fonte autoritativa cStat 100 = 86) e "Certidões" (ged_certidoes = 9),
    # NÃO o histórico importado (nfse_manaus_historico = 831). A visão redesign mostrava 831 como
    # KPI principal → divergia do que o Jordan vê no clássico. Alinhamos os KPIs da visão aos
    # MESMOS números do clássico (86/9), mantendo obrigações + faturamento como contexto. O
    # histórico (831) segue disponível na aba 'nfse'. Números provados: 86 e 9 batem o clássico.
    try:
        n_emit = await _scalar(db, "SELECT count(*) FROM nfse_emitidas_nacional") or 0
        n_cnd = await _scalar(db, "SELECT count(*) FROM ged_certidoes") or 0
        obr_pend = await _scalar(
            db, "SELECT count(*) FROM fiscal_obligations "
                "WHERE status::text NOT IN ('pago','paga','concluido','concluida')") or 0
        fat12 = await _scalar(
            db, "SELECT coalesce(sum(valor_servicos),0) FROM nfse_manaus_historico "
                "WHERE data_emissao >= (SELECT max(data_emissao) FROM nfse_manaus_historico) - interval '12 months'") or 0
        if isinstance(out.get("painel"), dict):
            out["painel"]["kpis"] = [
                {"v": str(n_emit), "l": "NFS-e Emitidas", "icon": _ICF["chart"], "color": "#0F1B3A"},
                {"v": str(n_cnd), "l": "Certidões", "icon": _ICF["chart"], "color": "#16A34A" if n_cnd else "#C2410C"},
                {"v": str(obr_pend), "l": "Obrigações em aberto", "icon": IC["alert"], "color": "#C2410C" if obr_pend else "#0F1B3A"},
                {"v": brl(fat12), "l": "Faturamento (12m)", "icon": _ICF["money"], "color": "#0F1B3A"},
            ]
    except Exception:  # noqa: BLE001 — a visão não pode derrubar o módulo
        pass
    return out
