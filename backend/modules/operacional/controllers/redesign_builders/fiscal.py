"""Fiscal (T1) — delega ao _build_fiscal e liga o menu json 'certidoes' às CNDs reais
(ged_certidoes) que já são montadas como 'certidoes-cnd'. Ação fiscal (transmitir) segue GATED.
nfse-multi/sped/ecac/consultor = capacidade sem tabela → honesto vazio."""

import logging
import os
from datetime import date as _date

from sqlalchemy import text as _sql

from modules.operacional.controllers.redesign_data_controller import (
    _ICF,
    IC,
    _build_fiscal,
    _fmtdate,
    _helpers,
    _scalar,
    b,
    brl,
    doc,
    t,
)

logger = logging.getLogger(__name__)

SLUG = "fiscal"

#: Lido pelo loader no IMPORT e deduplicado por "id" (ver f82d7448 — dict virava aba
#: fantasma). NUNCA popular isto dentro de build(): cresceria a cada requisição.
_ICO_CALC = "M9 11H3v10h6V11zM15 3H9v18h6V3zM21 7h-6v14h6V7z"
EXTRA_MENU: list[dict] = [
    {"id": "nova-obrigacao", "label": "Nova obrigação", "icon": _ICO_CALC},
    # Multi-CNPJ (11/08/2026): sem estes três itens as telas existiriam sem porta de entrada.
    {"id": "painel-por-empresa", "label": "Painel por empresa (CNPJ)", "icon": _ICO_CALC},
    # LIGAR 08/09/2026 (revisão 100%): rotas que existiam sem tela.
    {"id": "parcelamentos", "label": "Parcelamentos e acordos", "icon": _ICO_CALC},
    {"id": "parcelamento-novo", "label": "Registrar parcelamento", "icon": _ICO_CALC},
    {"id": "apuracao-lucro-real", "label": "Apuração IRPJ/CSLL (Lucro Real)", "icon": _ICO_CALC},
    {"id": "dre-mensal", "label": "DRE mês a mês", "icon": _ICO_CALC},
    {"id": "aging-receber", "label": "A receber por competência", "icon": _ICO_CALC},
    {"id": "aging-pagar", "label": "A pagar por competência", "icon": _ICO_CALC},
    {"id": "kpis-financeiros", "label": "KPIs financeiros (beat)", "icon": _ICO_CALC},
    {"id": "nfse-emitir-dps", "label": "NFS-e nacional — emitir DPS", "icon": "M3 3v18h18", "grupo": "Notas fiscais"},
    {
        "id": "nfse-multi-tributos",
        "label": "Tributos da NFS-e (multi-CNPJ)",
        "icon": _ICO_CALC,
        "grupo": "Notas fiscais",
    },
    {"id": "nfe-entrada-xml", "label": "Importar XML de NF-e de compra", "icon": _ICO_CALC, "grupo": "Notas fiscais"},
    {"id": "nfse-emitidas", "label": "NFS-e emitidas (nacional)", "icon": _ICO_CALC, "grupo": "Notas fiscais"},
    # dgx z6 — item escrito aqui (e não importado de `dgx_z6_bartolo.MENU`) pelo mesmo motivo do
    # `bi.py`/x5: o EXTRA_MENU é lido no IMPORT, e um import no topo fecharia o ciclo com o
    # `redesign_data_controller`. O id tem de casar com `dgx_z6_bartolo.TELA`.
    {
        "id": "bartolo-fiscal",
        "label": "Bartolo — tire sua dúvida",
        "icon": "M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z",
        "grupo": "Notas fiscais",
    },
    {"id": "calc-simples", "label": "Calcular DAS (Simples)", "icon": _ICO_CALC, "grupo": "Cálculos"},
    {"id": "calc-lucro-real", "label": "Calcular Lucro Real", "icon": _ICO_CALC, "grupo": "Cálculos"},
    {"id": "calc-comparativo", "label": "Comparar regimes", "icon": _ICO_CALC, "grupo": "Cálculos"},
    {"id": "calc-limite-simples", "label": "Limite do Simples", "icon": _ICO_CALC, "grupo": "Cálculos"},
    {"id": "calc-retencoes", "label": "Calcular retenções", "icon": _ICO_CALC, "grupo": "Cálculos"},
    {"id": "sync-guias", "label": "Sincronizar guias", "icon": _ICO_CALC, "grupo": "Certidões & sincronismo"},
    {"id": "sync-nfe-entrada", "label": "Puxar NF-e de compra", "icon": _ICO_CALC, "grupo": "Certidões & sincronismo"},
    {
        "id": "certidoes-cobertura",
        "label": "Cobertura de certidões",
        "icon": _ICO_CALC,
        "grupo": "Certidões & sincronismo",
    },
    {"id": "consultor-fiscal", "label": "Consultor fiscal", "icon": _ICO_CALC, "grupo": "Consultor fiscal"},
    {
        "id": "consultor-fiscal-arquivo",
        "label": "Consultor fiscal — com anexo",
        "icon": _ICO_CALC,
        "grupo": "Consultor fiscal",
    },
]

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
        return (
            b("Vencida", "bad") if dias < 0 else (b(f"Vence em {dias}d", "warn") if dias <= 30 else b("Válida", "ok"))
        )

    try:
        out["certidoes-cnd"] = await tbl(
            "Certidões (CND)",
            f"{await _scalar(db, 'SELECT count(*) FROM ged_certidoes')} certidões",
            "—",
            ["Certidão", "Tipo", "Órgão emissor", "Emissão", "Validade", "Situação"],
            "1.8fr 1.1fr 1.3fr 0.9fr 0.9fr 1fr",
            "SELECT coalesce(name,'—'), coalesce(document_type,'—'), coalesce(issuing_body,'—'), issue_date, expiry_date, "
            "(file_path IS NOT NULL AND file_path<>''), document_type FROM ged_certidoes ORDER BY expiry_date ASC NULLS LAST LIMIT 200",
            lambda r: [
                t((r[0] or "—")[:48], 600, "#0F1B3A"),
                t((r[1] or "—").replace("certidao_negativa_", "CND ").replace("_", " ")),
                t((r[2] or "—")[:32]),
                t(_fmtdate(r[3])),
                t(_fmtdate(r[4])),
                _cnd_sit(r[4]),
            ],
            docsfn=lambda r: [doc("CND", f"/api/v1/gedeon/cnd/pdf/{r[6]}", fmt="pdf")] if r[5] else [],
        )
    except Exception:  # noqa: BLE001
        pass

    # DOCUMENTOS — Guias FGTS/INSS (Onvio): baixar o PDF real da guia. Rota nova read-only
    # /api/v1/fiscal/guias-drive/guia-onvio/{fonte}/{id}/pdf. Botão SÓ onde o arquivo existe em
    # disco (checagem os no builder) — muitas guias têm path mas o Onvio não manteve o arquivo local.
    try:
        out["guias-fgts"] = await tbl(
            "Guias FGTS",
            f"{await _scalar(db, 'SELECT count(*) FROM fgts_guias')} guias — histórico Onvio até "
            f"{await _scalar(db, "SELECT coalesce(max(mes_ref),'—') FROM fgts_guias")}; as de 2026 (GFD) estão em Guias / Obrigações",
            "—",
            ["Competência", "Tipo", "Documento", "Status"],
            "1fr 1.4fr 0.9fr 0.9fr",
            "SELECT id, coalesce(mes_ref,'—'), coalesce(tipo,'—'), arquivo_pdf, coalesce(status,'—') "
            "FROM fgts_guias ORDER BY mes_ref DESC NULLS LAST, tipo LIMIT 200",
            lambda r: [
                t(r[1], 600, "#0F1B3A"),
                t((r[2] or "—").replace("_", " ").capitalize()),
                b("PDF", "ok") if _guia_existe(r[3]) else (b("no Drive", "mut") if r[3] else t("—")),
                b((r[4] or "—").capitalize(), _GTONE.get((r[4] or "").lower(), "info")),
            ],
            docsfn=lambda r: (
                [doc("Guia FGTS", f"/api/v1/fiscal/guias-drive/guia-onvio/fgts/{r[0]}/pdf", fmt="pdf")]
                if _guia_existe(r[3])
                else []
            ),
        )
    except Exception:  # noqa: BLE001
        pass
    try:
        out["guias-inss"] = await tbl(
            "Guias INSS",
            f"{await _scalar(db, 'SELECT count(*) FROM inss_guias')} guias — histórico Onvio até "
            f"{await _scalar(db, "SELECT coalesce(max(mes_ref),'—') FROM inss_guias")}; as de 2026 (DCTFWeb) estão em Guias / Obrigações",
            "—",
            ["Competência", "Documento", "Status"],
            "1.2fr 0.9fr 0.9fr",
            "SELECT id, coalesce(competencia, mes_ref, '—'), arquivo_pdf, coalesce(status,'—') "
            "FROM inss_guias ORDER BY mes_ref DESC NULLS LAST LIMIT 200",
            lambda r: [
                t(r[1], 600, "#0F1B3A"),
                b("PDF", "ok") if _guia_existe(r[2]) else (b("no Drive", "mut") if r[2] else t("—")),
                b((r[3] or "—").capitalize(), _GTONE.get((r[3] or "").lower(), "info")),
            ],
            docsfn=lambda r: (
                [doc("Guia INSS", f"/api/v1/fiscal/guias-drive/guia-onvio/inss/{r[0]}/pdf", fmt="pdf")]
                if _guia_existe(r[2])
                else []
            ),
        )
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
        # Certidão vencida é risco operacional (sem CRF-FGTS não se fatura em cliente grande
        # nem se participa de licitação), e o painel mostrava só a contagem total em verde —
        # 9 certidões, 3 delas vencidas, e nada denunciava. Medido em 11/08/2026.
        cnd_venc = await _scalar(db, "SELECT count(*) FROM ged_certidoes WHERE expiry_date < CURRENT_DATE") or 0
        # O filtro era `NOT IN ('pago','paga','concluido','concluida')`: quatro grafias de
        # "feito" e nenhuma delas é a que a tabela usa. O vocabulário real é 'cumprida' (26) e
        # 'pendente' (5) — então TODA obrigação cumprida contava como pendente e o painel
        # anunciava 31 onde havia 5. As grafias antigas ficam por segurança; a real entrou.
        obr_pend = (
            await _scalar(
                db,
                "SELECT count(*) FROM fiscal_obligations "
                "WHERE lower(coalesce(status::text,'')) "
                "NOT IN ('cumprida','cumprido','pago','paga','concluido','concluida')",
            )
            or 0
        )
        # A janela ancorava na ÚLTIMA NOTA da tabela de histórico (parada em 29/12/2025), não em
        # hoje, e somava só o arquivo — as 99 notas de 2026 ficavam de fora. O erro era de 4%
        # por coincidência de magnitude, mas CRESCE sozinho: o arquivo não anda mais, então o
        # KPI ia congelar enquanto a empresa fatura. Agora: 12 meses a partir de hoje, nas duas
        # tabelas (histórico Manaus até 2025 + nacional de 2026 em diante).
        fat12 = (
            await _scalar(
                db,
                "SELECT coalesce((SELECT sum(valor_servicos) FROM nfse_manaus_historico "
                "            WHERE data_emissao >= CURRENT_DATE - interval '12 months'), 0) "
                "     + coalesce((SELECT sum(valor_servicos) FROM nfse_emitidas_nacional "
                "            WHERE data_emissao >= CURRENT_DATE - interval '12 months'), 0)",
            )
            or 0
        )
        if isinstance(out.get("painel"), dict):
            out["painel"]["kpis"] = [
                {"v": str(n_emit), "l": "NFS-e Emitidas", "icon": _ICF["chart"], "color": "#0F1B3A"},
                {
                    "v": f"{n_cnd - cnd_venc}/{n_cnd}" if cnd_venc else str(n_cnd),
                    "l": f"Certidões ({cnd_venc} vencida{'s' if cnd_venc > 1 else ''})" if cnd_venc else "Certidões",
                    "icon": _ICF["chart"],
                    "color": "#C2410C" if cnd_venc or not n_cnd else "#16A34A",
                },
                {
                    "v": str(obr_pend),
                    "l": "Obrigações em aberto",
                    "icon": IC["alert"],
                    "color": "#C2410C" if obr_pend else "#0F1B3A",
                },
                {"v": brl(fat12), "l": "Faturamento (12m)", "icon": _ICF["money"], "color": "#0F1B3A"},
            ]
    except Exception:  # noqa: BLE001 — a visão não pode derrubar o módulo
        pass

    await _multicnpj(db, out, tbl)
    _calculadoras_tributarias(out)
    await _nova_obrigacao(db, out)
    _retencoes_e_syncs(out)
    # ── Fios soltos do fiscal, 2a rodada (2026-08-10) ───────────────────────────────
    out["consultor-fiscal"] = {
        "title": "Consultor fiscal",
        "sub": "Pergunta ancorada nas notas, guias e obrigações reais. É consulta — não "
        "emite, não transmite, não cancela nada.",
        "cta": "Perguntar",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/fiscal/consultor/perguntar",
            "okMsg": "Consulta respondida",
            "showResult": True,
        },
        "fields": [
            {"key": "area", "label": "Área*", "type": "text", "span": "span 1", "ph": "Ex.: NFS-e, Simples, retenções"},
            {"key": "ano", "label": "Ano", "type": "number", "span": "span 1", "ph": "2026"},
            {"key": "pergunta", "label": "Pergunta*", "type": "textarea", "span": "span 2"},
        ],
    }
    out["consultor-fiscal-arquivo"] = {
        "title": "Consultor fiscal — analisando um anexo",
        "sub": "Anexe guia, nota ou intimação e pergunte sobre o documento.",
        "cta": "Analisar",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/fiscal/consultor/perguntar-arquivo",
            "multipart": True,
            "query": True,
            "okMsg": "Análise concluída",
            "showResult": True,
        },
        "fields": [
            {"key": "arquivo", "label": "Arquivo*", "type": "file", "span": "span 2"},
            {"key": "area", "label": "Área", "type": "text", "span": "span 1"},
            {"key": "ano", "label": "Ano", "type": "number", "span": "span 1", "ph": "2026"},
            {"key": "pergunta", "label": "Pergunta*", "type": "textarea", "span": "span 2"},
        ],
    }
    out["nfse-multi-tributos"] = {
        "title": "Tributos da NFS-e (multi-CNPJ)",
        "sub": "Calcula os tributos de uma nota aplicando as liminares do CNPJ escolhido. "
        "Cálculo puro — não emite nota.",
        "cta": "Calcular",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/fiscal/nfse-multi/calcular-tributos",
            "okMsg": "Tributos calculados",
            "showResult": True,
        },
        "fields": [
            {
                "key": "valor_servico",
                "label": "Valor do serviço (R$)*",
                "type": "number",
                "span": "span 1",
                "ph": "1000.00",
            },
            {
                "key": "empresa_slug",
                "label": "Empresa",
                "type": "select",
                "span": "span 1",
                "ph": "Selecione",
                "options": [
                    {"value": "eletronica", "label": "ConectaMais Eletrônica"},
                    {"value": "patrimonial", "label": "ConectaMais Patrimonial"},
                ],
            },
        ],
    }
    out["nfe-entrada-xml"] = {
        "title": "Importar XML de NF-e de compra",
        "sub": "Lê o XML da nota do fornecedor e atualiza o estoque. É ENTRADA: não emite nem transmite nada ao fisco.",
        "cta": "Importar",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/fiscal/nfe-entrada/upload-xml",
            "multipart": True,
            "okMsg": "XML importado",
            "showResult": True,
        },
        "fields": [
            {"key": "arquivo", "label": "XML da NF-e*", "type": "file", "span": "span 2"},
        ],
    }

    await _ligar_20260908(db, out)
    await _ligar_lote3_20260908(db, out)

    # dgx z6 — «Bartolo — tire sua dúvida» (a ação entra pelo `router` do próprio módulo, que o
    # discovery monta sozinho porque o arquivo não tem prefixo `_`; aqui só a tela).
    from .dgx_z6_bartolo import telas as _z6_telas  # dgx z6

    out.update(await _z6_telas(db, out))  # dgx z6
    return out


def _fmt_kpi(v, unidade: str) -> str:
    u = (unidade or "").strip()
    if u in ("R$", "BRL"):
        return brl(v)
    n = f"{float(v or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".").rstrip("0").rstrip(",")
    return f"{n}{'%' if u == '%' else (' ' + u if u else '')}"


async def _ligar_20260908(db, out: dict) -> None:
    """Rotas que existiam sem tela (revisão 100%, 08/09/2026). Cada bloco é independente:
    uma falha não derruba as outras."""
    import asyncio

    _, _, tbl = _helpers(db)
    hoje = _date.today()
    try:
        out["parcelamentos"] = await tbl(
            "Parcelamentos e acordos",
            "Acordos com PGFN/RFB/Prefeitura e o saldo devedor de cada um",
            "Registrar",
            ["Órgão", "Acordo", "Descrição", "Total", "Parcelas", "Saldo devedor", "Status"],
            "0.8fr 1.1fr 2fr 1fr 0.8fr 1fr 0.8fr",
            "SELECT id::text, coalesce(orgao,'—'), coalesce(numero_acordo,'—'), coalesce(descricao,'—'), "
            "coalesce(valor_total,0), coalesce(num_parcelas,0), coalesce(parcelas_pagas,0), coalesce(parcela_valor,0), "
            "coalesce(status,'ativo') FROM fiscal_parcelamentos ORDER BY status, orgao, created_at DESC LIMIT 200",
            lambda r: [
                t(r[1], 600, "#0F1B3A"),
                t(r[2]),
                t((r[3] or "—")[:60]),
                t(brl(r[4]), 600),
                t(f"{r[6]}/{r[5]}"),
                t(brl(max(float(r[5] or 0) - float(r[6] or 0), 0) * float(r[7] or 0)), 600),
                b(str(r[8]).capitalize(), "ok" if str(r[8]) == "ativo" else "info"),
            ],
            actionsfn=lambda r: [
                {
                    "title": f"Remover acordo {r[2]}",
                    "sub": "Apaga o registro do parcelamento (não altera nada no órgão).",
                    "endpoint": f"/api/v1/financial/relatorios/parcelamentos/{r[0]}",
                    "method": "DELETE",
                    "btnLabel": "Remover",
                    "submitLabel": "Remover",
                    "btnStyle": "danger",
                    "confirm": f"Remover o acordo {r[2]}?",
                    "okMsg": "Removido. Recarregue.",
                    "fields": [],
                }
            ],
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("tela parcelamentos: %s", exc)
    out["parcelamento-novo"] = {
        "title": "Registrar parcelamento",
        "sub": "Acordo já firmado com o órgão. Só registra — não negocia nem paga.",
        "cta": "Registrar",
        "type": "form",
        "submit": {"endpoint": "/api/v1/financial/relatorios/parcelamentos", "okMsg": "Parcelamento registrado"},
        "fields": [
            {
                "key": "orgao",
                "label": "Órgão*",
                "type": "select",
                "span": "span 1",
                "options": [
                    {"value": "PGFN", "label": "PGFN (Dívida Ativa)"},
                    {"value": "RFB", "label": "Receita Federal"},
                    {"value": "PREFEITURA", "label": "Prefeitura (ISS)"},
                    {"value": "FGTS", "label": "FGTS"},
                    {"value": "INSS", "label": "INSS"},
                    {"value": "SEFAZ", "label": "SEFAZ-AM"},
                ],
            },
            {"key": "numero_acordo", "label": "Nº do acordo*", "type": "text", "span": "span 1"},
            {"key": "descricao", "label": "Descrição*", "type": "text", "span": "span 2"},
            {"key": "valor_total", "label": "Valor total (R$)*", "type": "number", "span": "span 1"},
            {"key": "num_parcelas", "label": "Nº de parcelas*", "type": "number", "span": "span 1"},
            {"key": "parcela_valor", "label": "Valor da parcela (R$)*", "type": "number", "span": "span 1"},
            {"key": "dia_vencimento", "label": "Dia do vencimento*", "type": "number", "span": "span 1"},
            {
                "key": "competencia_inicio",
                "label": "1ª competência (MM/AAAA)*",
                "type": "text",
                "span": "span 1",
                "ph": "02/2026",
            },
            {"key": "parcelas_pagas", "label": "Parcelas já pagas", "type": "number", "span": "span 1"},
            {"key": "observacao", "label": "Observação", "type": "textarea", "span": "span 2"},
        ],
    }
    try:
        from modules.financial.controllers.relatorios_controller import apuracao_lucro_real

        a = await apuracao_lucro_real(ano=hoje.year, trimestre=None, empresa_id=None, _user={})
        base, ap = a.get("base", {}), a.get("apuracao", {})
        out["apuracao-lucro-real"] = {
            "title": f"Apuração IRPJ/CSLL — Lucro Real {hoje.year}",
            "sub": "Base = resultado do razão (receita − ISS − despesas dedutíveis), não presunção. "
            "Consulta — não gera guia.",
            "type": "dash",
            "panelGrid": "1fr 1fr",
            "kpis": [
                {
                    "v": brl(base.get("lucro_antes_ircsll", 0)),
                    "l": "Lucro antes de IRPJ/CSLL",
                    "icon": _ICO_CALC,
                    "color": "#16A34A" if float(base.get("lucro_antes_ircsll", 0) or 0) >= 0 else "#DC2626",
                },
                {
                    "v": brl(ap.get("total_irpj_csll", 0)),
                    "l": "IRPJ + CSLL devidos",
                    "icon": _ICO_CALC,
                    "color": "#C2410C",
                },
                {
                    "v": brl(base.get("receita_liquida", 0)),
                    "l": "Receita líquida",
                    "icon": _ICO_CALC,
                    "color": "#0F1B3A",
                },
                {
                    "v": brl(base.get("despesas_dedutiveis_total", 0)),
                    "l": "Despesas dedutíveis",
                    "icon": _ICO_CALC,
                    "color": "#0F1B3A",
                },
            ],
            "panels": [
                {
                    "title": "Base de cálculo",
                    "rows": [
                        {"left": k.replace("_", " ").capitalize(), "right": brl(v)}
                        for k, v in base.items()
                        if isinstance(v, (int, float))
                    ],
                },
                {
                    "title": "Apuração",
                    "rows": [
                        {"left": k.replace("_", " ").capitalize(), "right": brl(v) if "carga" not in k else f"{v}%"}
                        for k, v in ap.items()
                        if isinstance(v, (int, float))
                    ],
                },
            ],
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("tela apuracao-lucro-real: %s", exc)
    try:
        from modules.financial.controllers.relatorios_controller import get_dre_mensal

        d = await get_dre_mensal(ano=hoje.year, condominio_id=None, db=db, _current_user={})
        m = d.get("meses", {})
        ms = m.get("months", [])
        out["dre-mensal"] = {
            "title": f"DRE mês a mês — {hoje.year}",
            "sub": "Receita, custos, despesas e resultado por competência (razão real).",
            "type": "dash",
            "panelGrid": "1fr",
            "kpis": [
                {
                    "v": brl(sum(m.get("receita_bruta", []))),
                    "l": "Receita bruta no ano",
                    "icon": _ICO_CALC,
                    "color": "#16A34A",
                },
                {
                    "v": brl(sum(m.get("lucro_liquido", []))),
                    "l": "Resultado no ano",
                    "icon": _ICO_CALC,
                    "color": "#16A34A" if sum(m.get("lucro_liquido", [])) >= 0 else "#DC2626",
                },
            ],
            "panels": [
                {
                    "title": "Por competência",
                    "rows": [
                        {
                            "left": f"{ms[i][5:]}/{ms[i][:4]} · receita {brl(m['receita_bruta'][i])} · custos {brl(m['custos'][i])} · despesas {brl(m['despesas'][i])}",
                            "right": brl(m["lucro_liquido"][i]),
                        }
                        for i in range(len(ms))
                    ],
                }
            ],
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("tela dre-mensal: %s", exc)
    try:
        from modules.financial.services.fluxo_caixa_service import FluxoCaixaService

        svc = FluxoCaixaService()
        for key, titulo, fn, campo in (
            ("aging-receber", "A receber por competência", svc.contas_a_receber, "a_receber"),
            ("aging-pagar", "A pagar por competência", svc.contas_a_pagar, "a_pagar"),
        ):
            r = await asyncio.to_thread(fn, hoje.year)
            meses = r.get("meses", [])
            out[key] = {
                "title": f"{titulo} — {hoje.year}",
                "sub": "Faturado × recebido (FIFO por competência). O que ainda falta entrar/sair, mês a mês.",
                "type": "dash",
                "panelGrid": "1fr",
                "kpis": [
                    {
                        "v": brl(sum(float(x.get(campo, 0) or 0) for x in meses)),
                        "l": "Em aberto no ano",
                        "icon": _ICO_CALC,
                        "color": "#C2410C",
                    }
                ],
                "panels": [
                    {
                        "title": "Por competência",
                        "rows": [
                            {
                                "left": f"{x.get('competencia')} · {x.get('notas', x.get('titulos', 0))} docs · "
                                f"{brl(x.get('faturado', x.get('devido', 0)))} faturado · {brl(x.get('recebido', x.get('pago', 0)))} liquidado",
                                "right": brl(x.get(campo, 0)),
                            }
                            for x in meses
                        ],
                    }
                ],
            }
    except Exception as exc:  # noqa: BLE001
        logger.warning("tela aging: %s", exc)
    try:
        rows = (
            await db.execute(
                _sql(
                    "SELECT coalesce(nome_curto, nome), coalesce(valor_atual,0), coalesce(unidade,''), categoria::text, ultima_atualizacao "
                    'FROM financial_kpis WHERE coalesce(ativo, true) ORDER BY "order" NULLS LAST, nome'
                )
            )
        ).fetchall()
        out["kpis-financeiros"] = {
            "title": "KPIs financeiros (beat)",
            "sub": "Os indicadores que o beat recalcula todo dia às 04:25.",
            "type": "dash",
            "panelGrid": "1fr",
            "kpis": [{"v": _fmt_kpi(r[1], r[2]), "l": r[0], "icon": _ICO_CALC, "color": "#0F1B3A"} for r in rows[:6]],
            "panels": [
                {
                    "title": "Todos",
                    "rows": [
                        {"left": f"{r[0]} ({r[3]}) · {str(r[4])[:16]}", "right": _fmt_kpi(r[1], r[2])} for r in rows
                    ],
                }
            ],
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("tela kpis-financeiros: %s", exc)


#: SQL de empresa: `ged_certidoes` guarda o CNPJ como TEXTO e `empresas.cnpj` vem formatado
#: ("35.710.481/0001-03"). Comparar cru não casa nunca — normaliza dígitos dos dois lados.
_SO_DIGITOS = "regexp_replace(coalesce({}, ''), '[^0-9]', '', 'g')"


async def _multicnpj(db, out: dict, tbl) -> None:
    """O fiscal deixa de tratar o grupo como uma empresa só.

    O grupo tem DOIS CNPJs desde 2026 — Eletrônica (Lucro Real) e Patrimonial (Simples
    Anexo III) — e até 11/08/2026 nenhuma tela dizia de qual empresa era a linha. O painel
    somava, e a soma escondia o que importa (medido nesse dia):

      • Patrimonial faturou R$ 443.381,11 em 16 notas e tinha **zero** obrigação fiscal
        cadastrada — sendo Simples, que deve DAS todo mês;
      • Patrimonial tinha **1 das 8** certidões da Eletrônica: sem CRF-FGTS nem CND Federal
        não se fatura em cliente grande nem se entra em licitação;
      • as 99 NFS-e de 2026 (`nfse_emitidas_nacional`) apareciam só como CONTAGEM no KPI —
        a tela "NFS-e" lista `nfse_manaus_historico`, que é arquivo e parou em 29/12/2025.
        Havia número para ver e nenhuma tela para clicar.

    Nada aqui inventa dado: buraco é mostrado COMO buraco ("FALTA", "sem obrigação
    cadastrada"), nunca preenchido com linha fabricada.
    """
    try:
        empresas = (
            await db.execute(
                _sql(
                    "SELECT id::text, coalesce(nome_fantasia, razao_social, '—') AS nome, "
                    "coalesce(cnpj,'—'), coalesce(regime_tributario::text,'—') "
                    "FROM empresas ORDER BY nome"
                )
            )
        ).fetchall()
    except Exception:  # noqa: BLE001 — a visão não pode derrubar o módulo
        return
    if not empresas:
        return

    async def _num(sql: str, params: dict):
        """_scalar do controller não aceita binds; aqui precisa (CNPJ/empresa por linha)."""
        return (await db.execute(_sql(sql), params)).scalar() or 0

    # ── Painel por empresa ────────────────────────────────────────────────────────
    linhas = []
    for eid, nome, cnpj, regime in empresas:
        p = {"e": eid, "c": cnpj}
        cnd_tot = await _num(
            f"SELECT count(*) FROM ged_certidoes WHERE {_SO_DIGITOS.format('cnpj')} = {_SO_DIGITOS.format(':c')}", p
        )
        cnd_ven = await _num(
            f"SELECT count(*) FROM ged_certidoes WHERE {_SO_DIGITOS.format('cnpj')} = {_SO_DIGITOS.format(':c')} AND expiry_date < CURRENT_DATE",
            p,
        )
        obr_tot = await _num("SELECT count(*) FROM fiscal_obligations WHERE empresa_id::text = :e", p)
        obr_pen = await _num(
            "SELECT count(*) FROM fiscal_obligations WHERE empresa_id::text = :e AND lower(coalesce(status::text,'')) = 'pendente'",
            p,
        )
        notas = await _num("SELECT count(*) FROM nfse_emitidas_nacional WHERE empresa_id::text = :e", p)
        fat = await _num(
            "SELECT coalesce(sum(valor_servicos),0) FROM nfse_emitidas_nacional WHERE empresa_id::text = :e AND data_emissao >= CURRENT_DATE - interval '12 months'",
            p,
        )
        # Empresa que EMITE nota e não tem obrigação nenhuma é buraco de cadastro, não um
        # zero natural — o número sozinho passaria por "nada a pagar".
        obr_txt = "sem obrigação cadastrada" if (obr_tot == 0 and notas > 0) else f"{obr_pen} pendente(s) de {obr_tot}"
        linhas.append(
            [
                t(nome[:34], 600, "#0F1B3A"),
                t(cnpj),
                t(regime.replace("_", " ")),
                t(f"{cnd_tot - cnd_ven}/{cnd_tot}", 600),
                b(f"{cnd_ven} vencida(s)", "bad") if cnd_ven else b("em dia", "ok"),
                b(obr_txt, "bad")
                if (obr_tot == 0 and notas > 0)
                else (b(obr_txt, "warn") if obr_pen else b(obr_txt, "ok")),
                t(brl(fat), 600),
            ]
        )
    out["painel-por-empresa"] = {
        "title": "Painel por empresa (CNPJ)",
        "sub": "Cada CNPJ do grupo com as próprias certidões, obrigações e faturamento — o total agregado escondia quem está descoberto",
        "cta": "—",
        "type": "table",
        "cols": ["Empresa", "CNPJ", "Regime", "Certidões", "Situação", "Obrigações", "Faturamento 12m"],
        "grid": "1.6fr 1.3fr 1.1fr 0.8fr 1.1fr 1.5fr 1.2fr",
        "rows": [{"cells": c} for c in linhas],
    }

    # ── Cobertura de certidões: tipo × empresa, com o que FALTA ───────────────────
    # A linha é o TIPO (document_type), não o nome: a mesma certidão tem nome diferente em cada
    # empresa ("CND Estadual (SEFAZ-AM)" × "Certidão Negativa Estadual") e a grade por nome
    # mostrava FALTA cruzado nas duas — 10 "faltas" que não existiam (07/09/2026).
    _ROTULO = {
        "certidao_negativa_estadual": "CND Estadual (SEFAZ-AM)",
        "certidao_negativa_federal": "CND Federal (RFB/PGFN)",
        "certidao_negativa_fgts": "CRF — FGTS (Caixa)",
        "certidao_negativa_inss": "CND Previdenciária",
        "certidao_negativa_municipal": "CND Municipal (Manaus)",
        "certidao_negativa_trabalhista": "CNDT — Trabalhista (TST)",
        "certidao_negativa_falencia": "Falência e Recuperação (TJ-AM)",
        "alvara_funcionamento": "Alvará de Funcionamento",
        "registro_cnpj": "Registro CNPJ Ativo",
    }
    tipos = [
        r[0]
        for r in (
            await db.execute(
                _sql(
                    "SELECT DISTINCT document_type::text FROM ged_certidoes WHERE document_type IS NOT NULL ORDER BY 1"
                )
            )
        ).fetchall()
    ]
    if tipos:
        cob = []
        for tipo in tipos:
            rotulo = _ROTULO.get(tipo, tipo.replace("certidao_negativa_", "CND ").replace("_", " ").capitalize())
            cel = [t(rotulo[:42], 600, "#0F1B3A")]
            for _eid, _nome, cnpj, _rg in empresas:
                r = (
                    await db.execute(
                        _sql(
                            f"SELECT expiry_date FROM ged_certidoes WHERE document_type::text = :n "
                            f"AND {_SO_DIGITOS.format('cnpj')} = {_SO_DIGITOS.format(':c')} "
                            f"ORDER BY expiry_date DESC NULLS LAST LIMIT 1"
                        ),
                        {"n": tipo, "c": cnpj},
                    )
                ).first()
                if r is None:
                    cel.append(b("FALTA", "bad"))
                elif r[0] is None:
                    cel.append(b("cadastrada, sem validade", "info"))
                else:
                    venc = r[0]
                    d = venc.date() if hasattr(venc, "date") else venc
                    vencida = d is not None and d < _date.today()
                    cel.append(
                        b(f"VENCIDA {_fmtdate(venc)}", "bad") if vencida else b(f"ok até {_fmtdate(venc)}", "ok")
                    )
            cob.append(cel)
        out["certidoes-cobertura"] = {
            "title": "Cobertura de certidões por CNPJ",
            "sub": "Um tipo por linha, um CNPJ por coluna. FALTA = nunca foi cadastrada para aquela empresa",
            "cta": "—",
            "type": "table",
            "cols": ["Certidão"] + [n[:22] for _i, n, _c, _r in empresas],
            "grid": "2fr " + " ".join(["1.3fr"] * len(empresas)),
            "rows": [{"cells": c} for c in cob],
        }

    def _cobranca_da_nota(cancelada, st):
        if cancelada:
            return b("Nota cancelada", "mut")
        if not st:
            return b("Sem conta a receber", "warn")
        status, emitida = st.split("|", 1)
        if status in ("paga", "pago"):
            return b("Recebida", "ok")
        if emitida:
            return b("Boleto emitido", "ok")
        if status in ("pendente", "parcial"):
            return b("A emitir", "warn")
        return b(status.capitalize(), "info")

    # ── NFS-e emitidas (nacional): as notas de 2026 ganham tela ───────────────────
    try:
        out["nfse-emitidas"] = await tbl(
            "NFS-e emitidas (nacional)",
            f"{await _scalar(db, 'SELECT count(*) FROM nfse_emitidas_nacional')} notas — as de 2026, por empresa emitente",
            "—",
            ["Número", "Empresa", "Tomador", "Valor", "ISS", "Emissão", "Cobrança"],
            "1fr 1.5fr 2fr 1.1fr 1fr 1fr 1fr",
            # Fluxo natural nota → boleto (dono, 07/09/2026): a coluna diz em que pé está a conta a
            # receber da mesma empresa/tomador/competência e o botão emite a cobrança nela
            # (Eletrônica → Inter, Patrimonial → Cora). Regra de casamento é a do serviço
            # (`cobranca_recebivel_service.emitir_por_nota`).
            "SELECT coalesce(n.numero::text,'—'), coalesce(e.nome_fantasia, e.razao_social, '—'), "
            "coalesce(n.tomador_nome,'—'), coalesce(n.valor_servicos,0), coalesce(n.iss_valor,0), n.data_emissao, "
            "n.chave_acesso, coalesce(n.cancelada, FALSE), "
            # O VÍNCULO GRAVADO vem primeiro (18/09/2026). O palpite por competência abaixo
            # continua como rede — ele acerta o recorrente —, mas não alcança contrato de
            # valor único, cujas parcelas vencem em DATAS e nascem sem `reference_month`.
            "coalesce("
            " (SELECT r.status::text || CASE WHEN r.boleto_id IS NOT NULL OR r.pix_txid IS NOT NULL THEN '|emitida' ELSE '|' END "
            "    FROM receivable_accounts r WHERE r.deleted_at IS NULL AND r.metadata->>'nfse_chave' = n.chave_acesso LIMIT 1), "
            " (SELECT r.status::text || CASE WHEN r.boleto_id IS NOT NULL OR r.pix_txid IS NOT NULL THEN '|emitida' ELSE '|' END "
            "    FROM receivable_accounts r WHERE r.deleted_at IS NULL AND r.empresa_id = n.empresa_id "
            "     AND regexp_replace(coalesce(r.customer_document,''), '\\D', '', 'g') = regexp_replace(coalesce(n.tomador_cnpj,''), '\\D', '', 'g') "
            "     AND r.reference_month = substr(n.competencia, 6, 2) || '/' || substr(n.competencia, 1, 4) "
            "     AND coalesce(r.metadata->>'nfse_chave','') = '' "
            "    ORDER BY (r.status::text IN ('pendente','parcial')) DESC, abs(r.net_value - n.valor_servicos) LIMIT 1) "
            ") , "
            # Há alguma conta EM ABERTO e sem nota desse tomador, em qualquer competência?
            # Só então o botão «Vincular conta» aparece. Sem isto ele nascia em 99 linhas —
            # todas de jan–jul, período vivido fora do Conecta PRO, onde não há recebível
            # nenhum por decisão do dono. Botão que não pode funcionar ensina a ignorar botão.
            "(SELECT count(*) FROM receivable_accounts r "
            "   WHERE r.deleted_at IS NULL AND r.empresa_id = n.empresa_id "
            "    AND regexp_replace(coalesce(r.customer_document,''), '\\D', '', 'g') = regexp_replace(coalesce(n.tomador_cnpj,''), '\\D', '', 'g') "
            "    AND r.status::text IN ('pendente','parcial') AND coalesce(r.metadata->>'nfse_chave','') = '') "
            "FROM nfse_emitidas_nacional n LEFT JOIN empresas e ON e.id = n.empresa_id "
            "ORDER BY n.data_emissao DESC NULLS LAST LIMIT 200",
            lambda r: [
                t(r[0], 600, "#0F1B3A"),
                t((r[1] or "—")[:26]),
                t((r[2] or "—")[:38]),
                t(brl(r[3]), 600),
                t(brl(r[4])),
                t(_fmtdate(r[5])),
                _cobranca_da_nota(r[7], r[8]),
            ],
            docsfn=lambda r: [
                doc("DANFSe", f"/api/v1/financial/fiscal/nfse-emitida/{r[6]}/danfse")
            ],  # LIGAR 08/09/2026
            actionsfn=lambda r: (
                []
                if r[7]  # nota cancelada não gera nem vincula nada
                else [
                    {
                        "endpoint": f"/api/v1/financial/receivables/emitir-cobranca-por-nota/{r[6]}",
                        "method": "POST",
                        "btnLabel": "Gerar boleto",
                        "submitLabel": "Emitir no banco",
                        "btnStyle": "primary",
                        "okMsg": "Cobrança emitida no banco. Recarregue.",
                        "fields": [],
                    }
                ]
                if (r[8] or "").split("|")[0] in ("pendente", "parcial") and not (r[8] or "").endswith("|emitida")
                # Nota sem conta atrás dela: até 18/09 a linha só ficava muda e o dinheiro
                # ficava sem dono. Agora dá para DIZER qual conta ela cobre — é o caminho dos
                # contratos de valor único, que o palpite por competência nunca alcança.
                else [
                    {
                        "endpoint": f"/api/v1/financial/receivables/vincular-nota/{r[6]}",
                        "method": "POST",
                        "btnLabel": "Vincular conta",
                        "submitLabel": "Vincular",
                        "btnStyle": "outline",
                        "okMsg": "Nota vinculada à conta a receber. Recarregue.",
                        # Vazio = procura a única candidata em aberto. Com mais de uma o
                        # servidor devolve 409 com a lista, em vez de escolher por você.
                        "fields": [
                            {
                                "name": "receivable_id",
                                "label": "Conta a receber (deixe vazio se houver só uma em aberto)",
                                "required": False,
                            }
                        ],
                    }
                ]
                if not (r[8] or "").strip() and (r[9] or 0) > 0
                else []
            ),
        )
    except Exception:  # noqa: BLE001
        pass

    # ── Empresa nas tabelas que já existiam ──────────────────────────────────────
    # LEFT JOIN de propósito nas duas: linha sem empresa vinculada mostra "—" e CONTINUA
    # aparecendo. INNER JOIN aqui apagaria da tela justamente o dado órfão, que é o que
    # mais precisa ser visto.
    try:
        out["guias"] = await tbl(
            "Guias / Obrigações",
            f"{await _scalar(db, 'SELECT count(*) FROM fiscal_obligations')} obrigações",
            "Nova guia",
            ["Obrigação", "Empresa", "Competência", "Valor", "Vencimento", "Status"],
            "1.6fr 1.3fr 1fr 1fr 1fr 0.9fr",
            "SELECT coalesce(o.nome,'—'), coalesce(e.nome_fantasia, e.razao_social, '—'), "
            "coalesce(to_char(make_date(o.competencia_ano, greatest(o.competencia_mes,1), 1),'MM/YYYY'),'—'), "
            "coalesce(o.valor_devido,0), o.data_vencimento, o.status::text, o.id::text "
            "FROM fiscal_obligations o LEFT JOIN empresas e ON e.id = o.empresa_id "
            "ORDER BY o.data_vencimento DESC NULLS LAST LIMIT 200",
            lambda r: [
                t(r[0], 600, "#0F1B3A"),
                t((r[1] or "—")[:24]),
                t(r[2]),
                t(brl(r[3]), 600),
                t(_fmtdate(r[4])),
                b("Cumprida", "ok")
                if (r[5] or "").lower() in ("cumprida", "cumprido", "pago", "paga", "concluida")
                else b((r[5] or "Pendente").capitalize(), "warn"),
            ],
            # LIGAR 08/09/2026: não havia como dar baixa numa obrigação pela tela nova.
            actionsfn=lambda r: (
                []
                if (r[5] or "").lower() in ("concluida", "cancelada")
                else [
                    {
                        "title": f"Dar baixa — {r[0]}",
                        "sub": "Registra o pagamento da guia. Só marca — não paga nada.",
                        "endpoint": f"/api/v1/financial/fiscal/obrigacao/{r[6]}",
                        "method": "PATCH",
                        "btnLabel": "Dar baixa",
                        "submitLabel": "Registrar baixa",
                        "btnStyle": "primary",
                        "okMsg": "Obrigação atualizada. Recarregue.",
                        "fields": [
                            {
                                "key": "status",
                                "label": "Status*",
                                "type": "select",
                                "span": "span 1",
                                "options": [
                                    {"value": "concluida", "label": "Concluída (paga)"},
                                    {"value": "cancelada", "label": "Cancelada"},
                                    {"value": "pendente", "label": "Pendente"},
                                ],
                            },
                            {"key": "valor_pago", "label": "Valor pago (R$)", "type": "number", "span": "span 1"},
                            {"key": "data_pagamento", "label": "Data do pagamento", "type": "date", "span": "span 1"},
                            {"key": "numero_recibo", "label": "Nº do recibo", "type": "text", "span": "span 1"},
                            {"key": "observacoes", "label": "Observações", "type": "textarea", "span": "span 2"},
                        ],
                    }
                ]
            ),
        )
    except Exception:  # noqa: BLE001
        pass

    try:
        out["certidoes-cnd"] = await tbl(
            "Certidões (CND)",
            f"{await _scalar(db, 'SELECT count(*) FROM ged_certidoes')} certidões",
            "—",
            ["Certidão", "Empresa", "Tipo", "Órgão emissor", "Validade", "Situação"],
            "1.7fr 1.3fr 1fr 1.2fr 0.9fr 1fr",
            "SELECT coalesce(c.name,'—'), coalesce(e.nome_fantasia, e.razao_social, '—'), "
            "coalesce(c.document_type,'—'), coalesce(c.issuing_body,'—'), c.expiry_date, "
            "(c.file_path IS NOT NULL AND c.file_path<>''), c.document_type "
            "FROM ged_certidoes c LEFT JOIN empresas e ON "
            f"     {_SO_DIGITOS.format('e.cnpj')} = {_SO_DIGITOS.format('c.cnpj')} "
            "ORDER BY c.expiry_date ASC NULLS LAST LIMIT 200",
            lambda r: [
                t((r[0] or "—")[:44], 600, "#0F1B3A"),
                t((r[1] or "—")[:24]),
                t((r[2] or "—").replace("certidao_negativa_", "CND ").replace("_", " ")),
                t((r[3] or "—")[:28]),
                t(_fmtdate(r[4])),
                _cnd_situacao(r[4]),
            ],
            docsfn=lambda r: [doc("CND", f"/api/v1/gedeon/cnd/pdf/{r[6]}", fmt="pdf")] if r[5] else [],
        )
    except Exception:  # noqa: BLE001
        pass

    # O alias 'certidoes' -> 'certidoes-cnd' é feito lá em cima, ANTES deste bloco: sem
    # re-apontar, o menu continuaria servindo a tabela velha, sem a coluna Empresa.
    if "certidoes-cnd" in out:
        out["certidoes"] = out["certidoes-cnd"]

    # A tela 'nfse' lista `nfse_manaus_historico`, que só tem o CNPJ do TOMADOR — não sabe
    # quem emitiu. É base anterior a 2026, quando só existia a Eletrônica; deduzir isso e
    # carimbar "Eletrônica" em 831 linhas seria inventar dado. O que se pode afirmar com
    # honestidade é o que ela É, para ninguém confundir com faturamento corrente.
    # Guias FGTS/INSS vêm do Onvio e as tabelas NÃO têm coluna de empresa — são cegas a CNPJ
    # por esquema, não por código. Medido em 11/08/2026: a última competência é 12.2025, ou
    # seja, nada de 2026. Uma tela que mostra 46 guias sem dizer que a mais nova é de dezembro
    # passa dado velho por corrente — o mesmo erro que fez o KPI de faturamento errar por 8
    # meses. Não dá para atribuir empresa sem inventar; dá para datar honestamente.
    for _slug, _tab, _col in (
        ("guias-fgts", "fgts_guias", "mes_ref"),
        ("guias-inss", "inss_guias", "coalesce(competencia, mes_ref)"),
    ):
        if not isinstance(out.get(_slug), dict):
            continue
        try:
            ult = (
                await db.execute(_sql(f"SELECT {_col} FROM {_tab} ORDER BY {_col} DESC NULLS LAST LIMIT 1"))
            ).scalar()
        except Exception as exc:  # noqa: BLE001 — sem a data, a tela fica como estava
            logger.warning("[fiscal] competência de %s indisponível: %s", _tab, exc)
            continue
        out[_slug]["sub"] = (
            f"{out[_slug].get('sub', '')} — última competência na base: "
            f"{ult or 'nenhuma'}; sem empresa na origem (não dá para separar "
            f"por CNPJ)"
        ).strip()

    if isinstance(out.get("nfse"), dict):
        out["nfse"]["sub"] = (
            f"{out['nfse'].get('sub', '')} — ARQUIVO anterior a 2026 "
            f"(sem empresa emitente na base). As notas atuais estão em "
            f"'NFS-e emitidas (nacional)'."
        ).strip()


def _cnd_situacao(exp):
    """Situação da certidão pela validade — vencida, vencendo (30d) ou válida."""
    if exp is None:
        return b("—", "info")
    d = exp.date() if hasattr(exp, "date") else exp
    try:
        dias = (d - _date.today()).days
    except TypeError:
        return b("—", "info")
    return b("Vencida", "bad") if dias < 0 else (b(f"Vence em {dias}d", "warn") if dias <= 30 else b("Válida", "ok"))


def _retencoes_e_syncs(out: dict) -> None:
    """Retenção na fonte + os dois sincronizadores que não tinham botão.

    RETENÇÕES importa agora: a liminar de PIS/COFINS/INSS da Patrimonial **não foi
    deferida**, então há retenção real sobre as NFS-e. Provado 201 com R$10.000 →
    INSS 1.100 · IR 150 · CSLL 100 · PIS 65 · COFINS 300.

    Os dois syncs PUXAM, não transmitem — a diferença que decide o risco:
      `nfe-entrada/sync-sefaz` → `buscar_nfe_recebidas`, consulta a distribuição do SEFAZ-AM
      `guias-drive/sync`       → baixa e classifica os PDFs do pacote mensal do Drive
    Nenhum dos dois emite, cancela ou inutiliza nota. Emissão continua FORA (fala com a
    SEFAZ e é irreversível — decisão do Jordan, não wiring).
    """
    out["calc-retencoes"] = {
        "title": "Calcular retenções na fonte — NFS-e",
        "sub": "INSS, IR, CSLL, PIS e COFINS retidos por nota. Escolha o regime do CNPJ emissor.",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/financial/fiscal/calcular/retencoes-nfse",
            "okMsg": "Retenções calculadas",
            "showResult": True,
        },
        "cta": "Calcular",
        "fields": [
            {
                "key": "valor_servico",
                "label": "Valor da nota (R$)*",
                "type": "number",
                "span": "span 1",
                "ph": "10000.00",
            },
            {
                "key": "regime_empresa",
                "label": "Regime do emissor*",
                "type": "select",
                "span": "span 1",
                "ph": "Selecione",
                "options": [
                    {"value": "simples_nacional", "label": "Simples Nacional (Patrimonial)"},
                    {"value": "lucro_real", "label": "Lucro Real (Eletrônica)"},
                ],
            },
            {
                "key": "liminares",
                "label": "Liminares ativas",
                "type": "multiselect",
                "span": "span 2",
                "options": [
                    {"value": "pis_cofins_zero", "label": "PIS/COFINS zerado"},
                    {"value": "inss_nao_retido", "label": "INSS não retido"},
                ],
            },
        ],
    }

    out["sync-guias"] = {
        "title": "Sincronizar guias do Drive",
        "sub": "Baixa e classifica os PDFs do pacote mensal (Portte/Onvio) em obrigações.",
        "type": "form",
        "submit": {"endpoint": "/api/v1/fiscal/guias-drive/sync", "okMsg": "Guias sincronizadas"},
        "fields": [
            {
                "key": "forcar",
                "label": "Reprocessar PDFs já sincronizados",
                "type": "select",
                "span": "span 2",
                "ph": "Não",
                "options": [
                    {"value": "false", "label": "Não — só os novos"},
                    {"value": "true", "label": "Sim — reprocessar tudo"},
                ],
            },
        ],
    }

    out["sync-nfe-entrada"] = {
        "title": "Puxar NF-e de compra (SEFAZ-AM)",
        "sub": "Consulta a distribuição do SEFAZ. Só LÊ — não emite, não cancela, não inutiliza.",
        "type": "form",
        "submit": {"endpoint": "/api/v1/fiscal/nfe-entrada/sync-sefaz", "okMsg": "Consulta enviada ao SEFAZ"},
        "fields": [
            {
                "key": "ultimo_nsu",
                "label": "Último NSU",
                "type": "text",
                "span": "span 2",
                "ph": "0 — começa do início",
            },
        ],
    }


async def _nova_obrigacao(db, out: dict) -> None:
    """Formulário de criar obrigação fiscal — o KPI 'Obrigações em aberto' não tinha por onde.

    `POST /financial/fiscal/obrigacao` existe e estava sem superfície (raio-x 2026-08-07).
    Wiring puro: o submit aponta direto para ela. O gate `fiscal:obrigacao:create` continua
    valendo no backend — a tela não afrouxa permissão.

    O select de condomínio sai do banco: sem opção real, o campo viraria caixa vazia e o
    POST falharia com condominio_id inválido. Sem condomínio cadastrado, a tela não é criada.
    """
    try:
        rows = (
            await db.execute(_sql("SELECT id::text, nome FROM condominios WHERE coalesce(ativo,true) ORDER BY nome"))
        ).fetchall()
    except Exception:  # noqa: BLE001 — a tela não pode derrubar o módulo
        return
    if not rows:
        return

    out["nova-obrigacao"] = {
        "title": "Nova obrigação fiscal",
        "sub": "DAS, DCTF, DIRF, EFD… — alimenta o KPI 'Obrigações em aberto'.",
        "type": "form",
        "submit": {"endpoint": "/api/v1/financial/fiscal/obrigacao", "okMsg": "Obrigação criada"},
        "fields": [
            {
                "key": "condominio_id",
                "label": "Condomínio*",
                "type": "select",
                "span": "span 2",
                "ph": "Selecione",
                "options": [{"value": r[0], "label": r[1]} for r in rows],
            },
            {
                "key": "tipo",
                "label": "Tipo*",
                "type": "select",
                "span": "span 1",
                "ph": "Selecione",
                "options": [
                    {"value": x, "label": x}
                    for x in ("DAS", "DCTF", "DIRF", "EFD", "FGTS", "INSS", "ISS", "IRPJ", "CSLL")
                ],
            },
            {"key": "nome", "label": "Nome*", "type": "text", "span": "span 1", "ph": "DAS competência 07/2026"},
            {
                "key": "competencia_mes",
                "label": "Mês da competência",
                "type": "number",
                "span": "span 1",
                "ph": "1 a 12",
            },
            {
                "key": "competencia_ano",
                "label": "Ano da competência*",
                "type": "number",
                "span": "span 1",
                "ph": str(_date.today().year),
            },
            {"key": "data_vencimento", "label": "Vencimento*", "type": "date", "span": "span 1"},
            {"key": "valor_devido", "label": "Valor devido (R$)", "type": "number", "span": "span 1", "ph": "0.00"},
            {"key": "descricao", "label": "Descrição", "type": "text", "span": "span 2"},
        ],
    }


def _calculadoras_tributarias(out: dict) -> None:
    """Liga as 4 calculadoras que o backend já tem e nenhuma tela alcançava.

    Medido em 2026-08-07 (`backend_recon fiscal --surface redesign`): o motor tributário
    inteiro estava codado e sem superfície. As rotas existem em
    `financial/controllers/fiscal_controller.py` e são **cálculo puro** — nenhuma transmite
    nada ao governo, apesar da flag 🏛️ que o recon põe por causa de 'das'/'fiscal' no path.

    O `submit.endpoint` aponta DIRETO para a rota existente: zero backend novo, é wiring.
    """
    _LIMINARES = [
        {"value": "pis_cofins_zero", "label": "PIS/COFINS zerado"},
        {"value": "inss_nao_retido", "label": "INSS não retido"},
    ]

    out["calc-simples"] = {
        "title": "Calcular DAS — Simples Nacional",
        "sub": "Anexo III. Aplica liminares se informadas. Cálculo puro: não transmite nada.",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/financial/fiscal/calcular/simples",
            "okMsg": "DAS calculado",
            "showResult": True,
        },
        "cta": "Calcular",
        "fields": [
            {
                "key": "receita_mes",
                "label": "Receita bruta do mês (R$)*",
                "type": "number",
                "span": "span 1",
                "ph": "50000.00",
            },
            {
                "key": "rbt12",
                "label": "Receita acumulada 12 meses (R$)*",
                "type": "number",
                "span": "span 1",
                "ph": "500000.00",
            },
            {
                "key": "liminares",
                "label": "Liminares ativas",
                "type": "multiselect",
                "span": "span 2",
                "options": _LIMINARES,
            },
        ],
    }

    out["calc-lucro-real"] = {
        "title": "Calcular impostos — Lucro Real",
        "sub": "IRPJ, CSLL, PIS e COFINS não-cumulativos, ISS.",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/financial/fiscal/calcular/lucro-real",
            "okMsg": "Impostos calculados",
            "showResult": True,
        },
        "cta": "Calcular",
        "fields": [
            {
                "key": "receita_mes",
                "label": "Receita do mês (R$)*",
                "type": "number",
                "span": "span 1",
                "ph": "100000.00",
            },
            {
                "key": "receita_trimestre",
                "label": "Receita do trimestre (R$)*",
                "type": "number",
                "span": "span 1",
                "ph": "300000.00",
            },
            {
                "key": "custos_dedutiveis_mes",
                "label": "Créditos PIS/COFINS do mês (R$)",
                "type": "number",
                "span": "span 2",
                "ph": "0.00",
            },
        ],
    }

    out["calc-comparativo"] = {
        "title": "Comparar regimes — Simples × Lucro Real",
        "sub": "Qual regime paga menos para uma receita anual. Responde a transição de CNPJ.",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/financial/fiscal/calcular/comparativo-regimes",
            "okMsg": "Comparativo calculado",
            "showResult": True,
        },
        "cta": "Comparar",
        "fields": [
            {
                "key": "receita_anual",
                "label": "Receita bruta anual (R$)*",
                "type": "number",
                "span": "span 1",
                "ph": "1200000.00",
            },
            {
                "key": "custos_dedutiveis_anual",
                "label": "Custos dedutíveis no ano (R$)",
                "type": "number",
                "span": "span 1",
                "ph": "0.00",
            },
            {
                "key": "liminares",
                "label": "Liminares ativas",
                "type": "multiselect",
                "span": "span 2",
                "options": _LIMINARES,
            },
        ],
    }

    out["calc-limite-simples"] = {
        "title": "Verificar limite do Simples",
        "sub": "Quanto falta para estourar o teto e ser desenquadrado.",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/financial/fiscal/calcular/verificar-limite-simples",
            "okMsg": "Limite verificado",
            "showResult": True,
        },
        "cta": "Verificar",
        "fields": [
            {
                "key": "rbt12",
                "label": "Receita bruta 12 meses (R$)*",
                "type": "number",
                "span": "span 2",
                "ph": "500000.00",
            },
        ],
    }


async def _ligar_lote3_20260908(db, out: dict) -> None:
    """LIGAR lote 3 (08/09/2026): rotas que existiam sem tela. Cada bloco é independente (try/except + rollback)."""
    import logging as _lg

    from sqlalchemy import text as _T  # noqa: N812  # alias curto pré-existente

    from modules.operacional.controllers.redesign_builders._ligar_generico import (
        selecionar,
    )
    from modules.operacional.controllers.redesign_data_controller import _helpers

    _log = _lg.getLogger(__name__)
    _, _safe, tbl = _helpers(db)
    _SN = [{"value": "true", "label": "Sim"}, {"value": "false", "label": "Não"}]

    def _fd(v, fmt="%d/%m/%Y"):
        try:
            return v.strftime(fmt) if v else "—"
        except Exception:  # noqa: BLE001
            return str(v or "—")

    async def _n(sql):
        try:
            return (await db.execute(_T(sql))).scalar() or 0
        except Exception:  # noqa: BLE001
            await db.rollback()
            return 0

    out["nfse-emitir-dps"] = {  # POST /government/nfse-nacional/emitir — dry_run por padrão
        "title": "NFS-e nacional — emitir DPS",
        "sub": "Emite uma nota pelo padrão nacional (ADN). A empresa escolhida define o CNPJ E o certificado que assina. Fica em SIMULAÇÃO (dry_run) até você trocar para 'não' — aí transmite de verdade. Tomador e serviço em JSON.",
        "cta": "Emitir",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/government/nfse-nacional/emitir",
            "okMsg": "Processado — veja o resultado.",
            "showResult": True,
        },
        "fields": [
            selecionar(
                "empresa",
                "Empresa que emite*",
                [
                    {
                        "value": "conecta_patrimonial",
                        "label": "ConectaMais Patrimonial — vigilância, portaria, limpeza",
                    },
                    {"value": "conecta_eletronica", "label": "ConectaMais Eletrônica — CFTV, monitoramento, automação"},
                ],
                "span 2",
            ),
            {
                "key": "tomador",
                "label": "Tomador (JSON)*",
                "type": "json",
                "span": "span 2",
                "value": '{"cpf_cnpj": "", "razao_social": "", "logradouro": "", "numero": "S/N", "bairro": "", "codigo_municipio": "1302603", "uf": "AM", "cep": "", "email": ""}',
            },
            {
                "key": "servico",
                "label": "Serviço (JSON)*",
                "type": "json",
                "span": "span 2",
                "value": '{"codigo_tributacao_nacional": "110201", "descricao": "", "valor_servico": 0}',
            },
            {"key": "competencia", "label": "Competência (AAAA-MM)", "type": "text", "span": "span 1"},
            selecionar(
                "tipo_tributacao",
                "Tributação",
                [
                    {"value": "1", "label": "1 — no município"},
                    {"value": "2", "label": "2 — fora do município"},
                    {"value": "3", "label": "3 — isenção"},
                    {"value": "4", "label": "4 — imune"},
                ],
                "span 1",
            ),
            selecionar("dry_run", "Simulação (dry run)?", _SN, "span 1"),
        ],
    }
