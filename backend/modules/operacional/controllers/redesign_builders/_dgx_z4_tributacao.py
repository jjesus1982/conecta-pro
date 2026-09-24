"""DGX Z4 — o simulador de tributação da NF-e, a tela que o contador confere (24/09/2026).

Prefixo `_` = o discovery pula; `fiscal.py` importa `router` e chama `telas(db, out)` no fim do
`build()` (2 + 1 linhas, `# dgx z4`). Grupo do menu: «Notas fiscais».

A regra mora FORA daqui: `modules/fiscal/services/tributacao_nfe.py` — normas, alíquotas, CFOP,
CST/CSOSN, desoneração. Aqui só tela. **A tela não tem régua própria**: `simular()` devolve o
retorno do serviço sem tocar em número nenhum, e o oráculo confere célula a célula. Se um dia
alguém arredondar aqui, o oráculo fica vermelho.

Três telas:

* `nfe-tributacao-mapa` — o §1 do relatório em tela: cada empresa × cada operação, com o CFOP,
  o CST/CSOSN, a base, a alíquota e **a norma ao lado**. É o que vai para o contador.
* `nfe-tributacao-simulador` — o formulário: escolhe empresa, produto e destino, e devolve o
  cálculo linha a linha com a norma.
* `nfe-tributacao-divergencias` — a régua da casa contra o que a praça de Manaus pratica, lida
  dos XMLs reais dos fornecedores em `nfe_entradas.xml_raw`. Não é para copiar o fornecedor: é
  para achar onde a nossa regra destoa do mercado antes da primeira nota.

**Nenhuma transmissão à SEFAZ, nenhuma nota emitida, nenhuma linha escrita em banco.** Esta
frente é read-only: não tem `_ensure`, não cria tabela, não semeia. O emissor (Z2) e a tela de
emitir (Z3) são de outras frentes e não são tocados aqui.
"""

from __future__ import annotations

import logging
from collections import Counter
from decimal import Decimal

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.fiscal.services import tributacao_nfe as tn

#: DECLARADO AQUI, antes do import do `redesign_data_controller`: o discovery dele roda no fim
#: do próprio módulo e importa `fiscal.py`, que importa este arquivo. Com o `router` lá embaixo,
#: `fiscal.py` morria com «partially initialized module ... has no attribute 'router'» e o módulo
#: fiscal inteiro caía para o fallback do monólito — sem nenhuma das telas. Medido em 24/09/2026.
router = APIRouter()

from modules.operacional.controllers.redesign_data_controller import b, t  # noqa: E402

logger = logging.getLogger(__name__)
_ND = "#0F1B3A"
_NS = "{http://www.portalfiscal.inf.br/nfe}"

ABAS = [
    ("nfe-tributacao-mapa", "Mapa da tributação (NF-e)"),
    ("nfe-tributacao-simulador", "Simulador de tributação da NF-e"),
    ("nfe-tributacao-divergencias", "Nossa regra × a praça de Manaus"),
]
_ICO = "M9 11H3v10h6V11zM15 3H9v18h6V3zM21 7h-6v14h6V7z"
EXTRA_MENU: list[dict] = [{"id": i, "label": lbl, "icon": _ICO, "grupo": "Notas fiscais"} for i, lbl in ABAS]

_SN = [{"value": "sim", "label": "Sim"}, {"value": "nao", "label": "Não"}]
_UFS = sorted(set(tn._UF_POR_IBGE.values()))

#: os quatro destinos do §1, na ordem em que o contador lê
_DESTINOS_MAPA = [
    ("Dentro do Amazonas (contribuinte)", {"uf": "AM", "contribuinte": True, "suframa": None}),
    ("Dentro do Amazonas (não contribuinte)", {"uf": "AM", "contribuinte": False, "suframa": None}),
    ("Outro estado (contribuinte)", {"uf": "SP", "contribuinte": True, "suframa": None}),
    ("Outro estado (não contribuinte)", {"uf": "SP", "contribuinte": False, "suframa": None}),
    ("Para a ZFM, com SUFRAMA do destinatário", {"uf": "AM", "contribuinte": True, "suframa": "210140500"}),
]
_PROD_MAPA = {"ncm": "85311000", "valor": 1000, "quantidade": 1, "origem": "0"}


def _vazia(titulo: str, sub: str) -> dict:
    return {
        "title": titulo, "sub": sub, "cta": "—", "type": "table",
        "grid": "1fr", "cols": ["Situação"], "rows": [{"cells": [t("aguardando dado honesto")]}],
    }  # fmt: skip


def _falhou(titulo: str, exc: Exception) -> dict:
    logger.error("dgx z4: %s falhou: %s", titulo, exc, exc_info=True)
    return {
        "title": f"{titulo} — FALHOU", "sub": f"{type(exc).__name__}: {str(exc)[:300]}", "cta": "—",
        "type": "table", "grid": "1fr", "cols": ["Erro"],
        "rows": [{"cells": [t("A tela não conseguiu ler as fontes. O erro está no log do backend.", 500, "#B91C1C")]}],
    }  # fmt: skip


def _require_fiscal(current_user: CurrentActiveUser) -> None:
    from core.auth.module_scope import user_has_module

    if not user_has_module(current_user, "fiscal"):
        raise HTTPException(status_code=403, detail="Tributação da NF-e é do fiscal.")


def _pct(v) -> str:
    return "—" if v is None else f"{Decimal(str(v)):.2f}%".replace(".", ",")


def _rs(v) -> str:
    return (
        "—" if v is None else ("R$ " + f"{Decimal(str(v)):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    )


# ────────────────────────────── o cálculo (régua única) ──────────────────────────────
async def simular(db, payload: dict) -> dict:
    """O que a tela mostra. Devolve o retorno do serviço SEM tocar em número — é a régua única.

    O oráculo confere campo a campo contra `tributacao_nfe.calcular()`. Qualquer conta feita
    aqui (arredondar, somar frete, "ajustar") faz o oráculo ficar vermelho, de propósito.
    """
    p = payload or {}
    cnpj = str(p.get("empresa_cnpj") or "").strip()
    if not cnpj:
        raise HTTPException(status_code=400, detail="Escolha a empresa emitente.")
    produto = {
        "ncm": str(p.get("ncm") or "").strip(),
        "valor": p.get("valor") or 0,
        "quantidade": p.get("quantidade") or 1,
        "origem": str(p.get("origem") or "0"),
    }
    destinatario = {
        "uf": str(p.get("uf") or "AM").upper().strip(),
        "contribuinte": str(p.get("contribuinte") or "sim").lower() != "nao",
        "suframa": str(p.get("suframa") or "").strip() or None,
    }
    try:
        return await tn.calcular(db, cnpj, produto, destinatario, str(p.get("operacao") or "revenda"))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ─────────────────────────────────── tela 1: o mapa ───────────────────────────────────
async def _tela_mapa(db) -> dict:
    empresas = (
        await db.execute(
            text(
                "SELECT cnpj, coalesce(nome_fantasia, razao_social), regime_tributario, "
                "coalesce(inscricao_estadual,''), coalesce(inscricao_suframa,'') "
                "FROM empresas WHERE status='ativa' ORDER BY is_principal DESC"
            )
        )
    ).fetchall()
    if not empresas:
        return _vazia("Mapa da tributação (NF-e)", "Nenhuma empresa ativa em `empresas`.")

    rows: list[dict] = []
    bloqueadas = 0
    for cnpj, nome, regime, _ie, _suf in empresas:
        for rotulo, dest in _DESTINOS_MAPA:
            for op, op_lbl in (("revenda", "revenda"), ("producao", "produção própria")):
                r = await tn.calcular(db, cnpj, _PROD_MAPA, dest, op)
                if r["bloqueios"]:
                    bloqueadas += 1
                norma = next(
                    (ln["norma"] for ln in r["linhas"] if ln["rotulo"] in ("Alíquota de ICMS", "CSOSN", "CST / CSOSN")),
                    tn.SEM_FONTE,
                )
                rows.append(
                    {
                        "cells": [
                            t(nome[:28], 600, _ND),
                            t("Simples Nacional" if regime == "simples_nacional" else "Lucro real"),
                            t(f"{rotulo} · {op_lbl}"),
                            t(r["cfop"] or "—", 600, _ND),
                            b(r["cst_ou_csosn"] or "sem fonte", "ok" if r["cst_ou_csosn"] else "bad"),
                            t(_rs(r["base"])),
                            t(_pct(r["aliquota"]), 600, "#0F1B3A" if r["aliquota"] else "#94A3B8"),
                            t(_rs(r["valor"])),
                            t(_rs((r["deson"] or {}).get("vICMSDeson"))),
                            t(norma[:110]),
                            b("bloqueada", "bad") if r["bloqueios"] else b("emissível", "ok"),
                        ],
                        "filtros": {"empresa": nome, "regime": regime, "operacao": op},
                    }
                )
    return {
        "title": "Mapa da tributação (NF-e)",
        "sub": (
            f"{len(rows)} combinações empresa × destino × operação, calculadas pelo MESMO serviço "
            f"que o simulador (`fiscal/services/tributacao_nfe.py`). {bloqueadas} estão bloqueadas "
            "— a coluna Norma diz de onde cada alíquota veio, e «sem fonte» significa decisão do "
            "contador, nunca um número chutado. Produto-base do mapa: NCM 85311000, R$ 1.000,00, "
            "origem 0 (nacional). O SUFRAMA do destinatário NÃO transforma a venda em operação de "
            "ZFM quando o emitente já está em Manaus — " + tn.N_ZFM
        ),
        "cta": "—",
        "type": "table",
        "filtros": [
            {"key": "empresa", "label": "Empresa"},
            {"key": "regime", "label": "Regime"},
            {"key": "operacao", "label": "Operação"},
        ],
        "grid": "1.3fr 0.9fr 1.9fr 0.5fr 0.6fr 0.8fr 0.6fr 0.8fr 0.8fr 2.4fr 0.8fr",
        "cols": [
            "Empresa",
            "Regime",
            "Operação",
            "CFOP",
            "CST/CSOSN",
            "Base",
            "Alíquota",
            "ICMS",
            "Desonerado",
            "Norma",
            "Situação",
        ],  # fmt: skip
        "rows": rows,
    }


# ──────────────────────────────── tela 2: o simulador ────────────────────────────────
async def _tela_simulador(db) -> dict:
    empresas = (
        await db.execute(
            text(
                "SELECT cnpj, coalesce(nome_fantasia, razao_social), regime_tributario "
                "FROM empresas WHERE status='ativa' ORDER BY is_principal DESC"
            )
        )
    ).fetchall()
    opts = [
        {
            "value": c,
            "label": f"{n} — {'Simples Nacional' if reg == 'simples_nacional' else 'Lucro real'} ({c})",
        }
        for c, n, reg in empresas
    ]
    return {
        "title": "Simulador de tributação da NF-e",
        "sub": (
            "A tela que o contador confere ANTES da primeira nota real. Devolve CFOP, CST/CSOSN, "
            "base, alíquota, valor, desoneração e a mensagem fiscal — cada linha com a NORMA ao "
            "lado. Onde a norma não está no repositório, sai «" + tn.SEM_FONTE + "» e o campo fica "
            "vazio: alíquota inventada aqui vira multa depois. Nada é transmitido à SEFAZ e nada é "
            "gravado — é só cálculo."
        ),
        "cta": "Calcular tributação",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/redesign/action/nfe-tributacao-simular",
            "okMsg": "Cálculo pronto — confira a norma de cada linha.",
            "showResult": True,
        },
        "fields": [
            {
                "key": "empresa_cnpj",
                "label": "Empresa emitente*",
                "type": "select",
                "span": "span 2",
                "ph": "Escolha o CNPJ que vai emitir",
                "options": opts,
            },
            {
                "key": "operacao",
                "label": "Operação*",
                "type": "select",
                "span": "span 1",
                "options": [
                    {"value": "revenda", "label": "Revenda (mercadoria de terceiros)"},
                    {"value": "producao", "label": "Produção do próprio estabelecimento"},
                ],
            },
            {"key": "ncm", "label": "NCM", "type": "text", "span": "span 1", "ph": "85311000"},
            {"key": "valor", "label": "Valor unitário (R$)*", "type": "number", "span": "span 1", "ph": "1000.00"},
            {"key": "quantidade", "label": "Quantidade", "type": "number", "span": "span 1", "ph": "1"},
            {
                "key": "origem",
                "label": "Origem da mercadoria",
                "type": "select",
                "span": "span 2",
                "options": [
                    {"value": "0", "label": "0 — Nacional"},
                    {"value": "1", "label": "1 — Estrangeira, importação direta"},
                    {"value": "2", "label": "2 — Estrangeira, adquirida no mercado interno"},
                    {"value": "3", "label": "3 — Nacional, conteúdo importado 40–70%"},
                    {"value": "5", "label": "5 — Nacional, conteúdo importado até 40%"},
                    {"value": "8", "label": "8 — Nacional, conteúdo importado acima de 70%"},
                ],
            },
            {
                "key": "uf",
                "label": "UF do destinatário*",
                "type": "select",
                "span": "span 1",
                "options": [{"value": u, "label": u} for u in _UFS],
            },
            {
                "key": "contribuinte",
                "label": "Destinatário é contribuinte do ICMS?",
                "type": "select",
                "span": "span 1",
                "options": _SN,
            },
            {
                "key": "suframa",
                "label": "Inscrição SUFRAMA do destinatário",
                "type": "text",
                "span": "span 2",
                "ph": "210140500 — deixe vazio se não houver",
            },
        ],  # fmt: skip
    }


# ───────────────────── tela 3: a nossa regra × o que a praça pratica ─────────────────────
def _itens_dos_xmls(xmls: list[str]) -> list[dict]:
    """Extrai NCM/CFOP/CST/CSOSN/alíquota dos XMLs de NF-e de entrada.

    O parser do sync (`nfe_entrada_sync_service.processar_xml_nfe`) lê só `det/prod` e joga
    `det/imposto` fora — por isso `nfe_compras_estoque` tem NCM e nenhum tributo. O XML bruto
    continua salvo, então dá para reler sem ir à SEFAZ de novo.
    """
    out: list[dict] = []
    from defusedxml.ElementTree import fromstring  # XML de terceiro é entrada não confiável

    for xml in xmls:
        try:
            inf = fromstring(xml).find(f".//{_NS}infNFe")
        except Exception as exc:  # noqa: BLE001 — XML torto de fornecedor não derruba a tela
            logger.warning("dgx z4: XML de NF-e de entrada ilegível, pulado: %s", exc)
            continue
        if inf is None:
            continue
        emit = inf.find(f"{_NS}emit")
        crt = emit.findtext(f"{_NS}CRT") if emit is not None else None
        uf = emit.findtext(f".//{_NS}UF") if emit is not None else None
        for det in inf.findall(f"{_NS}det"):
            prod = det.find(f"{_NS}prod")
            icms = det.find(f"{_NS}imposto/{_NS}ICMS")
            if prod is None or icms is None or not len(icms):
                continue
            n = icms[0]
            out.append(
                {
                    "ncm": prod.findtext(f"{_NS}NCM") or "—",
                    "descricao": (prod.findtext(f"{_NS}xProd") or "—")[:40],
                    "cfop": prod.findtext(f"{_NS}CFOP") or "—",
                    "crt": crt,
                    "uf": uf,
                    "cst": n.findtext(f"{_NS}CST"),
                    "csosn": n.findtext(f"{_NS}CSOSN"),
                    "picms": n.findtext(f"{_NS}pICMS"),
                }
            )
    return out


async def _tela_divergencias(db) -> dict:
    xmls = [
        r[0]
        for r in (
            await db.execute(
                text(
                    "SELECT xml_raw FROM nfe_entradas "
                    "WHERE xml_raw IS NOT NULL AND length(xml_raw) > 2000 "
                    "ORDER BY data_emissao DESC NULLS LAST LIMIT 120"
                )
            )
        ).fetchall()
    ]
    itens = _itens_dos_xmls(xmls)
    if not itens:
        return _vazia(
            "Nossa regra × a praça de Manaus",
            "Nenhuma NF-e de entrada com XML completo em `nfe_entradas` — sem referência de mercado.",
        )

    # o que a casa faria para a MESMA operação: interna no AM, a contribuinte. Os CNPJs vêm do
    # BANCO por regime — nada de literal aqui: se o contador mudar o regime de uma empresa,
    # esta tela muda junto.
    dest_am = {"uf": "AM", "contribuinte": True, "suframa": None}
    por_regime = dict(
        (
            await db.execute(
                text(
                    "SELECT regime_tributario, min(cnpj) FROM empresas WHERE status='ativa' GROUP BY regime_tributario"
                )
            )
        ).fetchall()
    )
    cnpj_normal = por_regime.get("lucro_real") or por_regime.get("lucro_presumido")
    cnpj_simples = por_regime.get("simples_nacional")
    nosso_normal = await tn.calcular(db, cnpj_normal, _PROD_MAPA, dest_am, "revenda") if cnpj_normal else None
    nosso_simples = await tn.calcular(db, cnpj_simples, _PROD_MAPA, dest_am, "revenda") if cnpj_simples else None
    if not (nosso_normal and nosso_simples):
        return _vazia(
            "Nossa regra × a praça de Manaus",
            "Falta empresa ativa de um dos dois regimes em `empresas` — sem régua para comparar.",
        )

    internos = [i for i in itens if (i["cfop"] or "").startswith("5")]
    por_ncm: dict[str, Counter] = {}
    for i in internos:
        # o código vai CRU (só o número): comparar "CSOSN 102" com "102" nunca dava igual, e 13
        # itens de fornecedor do Simples apareciam como divergência sendo idênticos à nossa regra.
        por_ncm.setdefault(i["ncm"], Counter())[
            (i["cfop"], i["cst"] or i["csosn"] or "—", i["picms"] or "—", i["crt"] or "?")
        ] += 1

    rows: list[dict] = []
    divergentes = 0
    for ncm in sorted(por_ncm, key=lambda k: -sum(por_ncm[k].values())):
        for (cfop, codigo, picms, crt), n in por_ncm[ncm].most_common():
            nosso = nosso_simples if crt == "1" else nosso_normal
            igual_cfop = cfop == nosso["cfop"]
            igual_cod = codigo == (nosso["cst_ou_csosn"] or "")
            if igual_cfop and igual_cod:
                causa, tone = "igual à nossa regra", "ok"
            elif codigo in ("60", "500"):
                causa, tone = "ICMS já retido por ST — a casa não tem CEST/MVA para decidir", "warn"
                divergentes += 1
            elif codigo in ("20", "70"):
                causa, tone = "redução de base (Lei AM 2.826/2003 / Conv. 52/91) — não modelada", "warn"
                divergentes += 1
            elif cfop in ("5405", "5929", "5403", "5912"):
                causa, tone = f"CFOP {cfop} de outra natureza (ST/ordem/remessa) — fora do nosso mapa", "mut"
            else:
                causa, tone = f"nossa regra daria {nosso['cfop']}/{nosso['cst_ou_csosn']}", "bad"
                divergentes += 1
            rows.append(
                {
                    "cells": [
                        t(ncm, 600, _ND),
                        t(f"{n}×"),
                        t("Simples" if crt == "1" else "Normal"),
                        t(cfop),
                        b(codigo, "mut"),
                        t("—" if picms == "—" else f"{picms}%"),
                        t(f"{nosso['cfop']} / {nosso['cst_ou_csosn']}"),
                        t(_pct(nosso["aliquota"])),
                        b(causa[:70], tone),
                    ],
                    "filtros": {"regime": "Simples" if crt == "1" else "Normal", "situacao": causa[:70]},
                }
            )
    st = sum(1 for i in itens if (i["cst"] in ("60",)) or (i["csosn"] == "500"))
    return {
        "title": "Nossa regra × a praça de Manaus",
        "sub": (
            f"{len(itens)} itens lidos dos XMLs reais de {len(xmls)} NF-e de entrada "
            f"(`nfe_entradas.xml_raw`), {len(internos)} deles de operação interna do AM (CFOP 5xxx). "
            f"{st} itens ({st * 100 // max(len(itens), 1)}%) vieram com ICMS já retido por ST "
            "(CST 60 / CSOSN 500) — e a casa NÃO tem CEST nem MVA para decidir isso: `ncms.icms_cest` "
            "e `ncms.icms_st_mva` estão vazios nas 10.515 linhas. "
            f"{divergentes} linhas divergem da nossa regra. Isto NÃO é para copiar o fornecedor — é "
            "para o contador ver onde a nossa régua destoa do mercado antes da primeira nota. "
            "`nfe_compras_estoque` não serve aqui: tem NCM e nenhum tributo."
        ),
        "cta": "—",
        "type": "table",
        "filtros": [{"key": "regime", "label": "Regime do fornecedor"}, {"key": "situacao", "label": "Divergência"}],
        "grid": "0.9fr 0.5fr 0.7fr 0.6fr 0.8fr 0.6fr 0.9fr 0.7fr 2.6fr",
        "cols": [
            "NCM",
            "Itens",
            "Fornecedor",
            "CFOP dele",
            "CST/CSOSN dele",
            "Alíquota dele",
            "Nosso CFOP/CST",
            "Nossa alíquota",
            "Leitura",
        ],  # fmt: skip
        "rows": rows,
    }


async def telas(db, out: dict | None = None) -> dict:
    mine: dict = {}
    for tid, titulo, fn in (
        ("nfe-tributacao-mapa", "Mapa da tributação (NF-e)", _tela_mapa),
        ("nfe-tributacao-simulador", "Simulador de tributação da NF-e", _tela_simulador),
        ("nfe-tributacao-divergencias", "Nossa regra × a praça de Manaus", _tela_divergencias),
    ):
        try:
            mine[tid] = await fn(db)
        except Exception as exc:  # noqa: BLE001 — visível na tela, nunca calado
            await db.rollback()
            mine[tid] = _falhou(titulo, exc)
    if isinstance(out, dict):
        out.update(mine)
    return mine


# ───── ação (POST /api/v1/redesign/action/…) — o `router` está declarado lá no topo ─────
@router.post("/action/nfe-tributacao-simular", dependencies=[Depends(_require_fiscal)])
async def rd_nfe_tributacao_simular(
    current_user: CurrentActiveUser,
    payload: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Calcula a tributação. Read-only: não grava, não emite, não fala com a SEFAZ."""
    r = await simular(db, payload)
    logger.info(
        "dgx z4: %s simulou %s → %s/%s",
        getattr(current_user, "email", "?"), payload.get("empresa_cnpj"), r["cfop"], r["cst_ou_csosn"],
    )  # fmt: skip
    linhas = " · ".join(
        f"{ln['rotulo']}: {'—' if ln['valor'] is None else ln['valor']} [{ln['norma']}]" for ln in r["linhas"]
    )
    return {
        "ok": True,
        "cfop": r["cfop"],
        "cst_ou_csosn": r["cst_ou_csosn"],
        "base": r["base"],
        "aliquota": r["aliquota"],
        "valor": r["valor"],
        "deson": r["deson"],
        "mensagem_fiscal": r["mensagem_fiscal"],
        "origem_regra": r["origem_regra"],
        "linhas": r["linhas"],
        "bloqueios": r["bloqueios"],
        "resumo": (
            f"{r['empresa']['nome']} ({r['regime']}, CRT {r['crt']}) · {r['destino_label']} · "
            f"CFOP {r['cfop']} · {'CSOSN' if r['crt'] == '1' else 'CST'} {r['cst_ou_csosn']} · "
            f"base {_rs(r['base'])} · alíquota {_pct(r['aliquota'])} · ICMS {_rs(r['valor'])}. "
            + ("BLOQUEIOS: " + " | ".join(r["bloqueios"]) + " " if r["bloqueios"] else "")
            + (r["mensagem_fiscal"] or "")
            + " — nada foi transmitido nem gravado."
        ),
        "detalhe": linhas,
    }
