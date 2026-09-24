"""DGX AA5 — «Como a mercadoria entrou (ICMS-ST)»: a porta do humano (24/09/2026).

Prefixo `_` = o discovery pula; `fiscal.py` importa `router` e chama `telas(db, out)` no fim do
`build()` (2 + 1 linhas, `# dgx aa5`). Grupo do menu: «Notas fiscais».

A regra mora FORA daqui: `modules/fiscal/services/icms_entrada.py` (o fato) e
`modules/fiscal/services/tributacao_nfe.py` (a régua). Aqui só tela.

**Por que esta tela existe.** A régua de saída passou a depender de como a mercadoria ENTROU.
Para 95 dos 95 produtos de `fin_produtos` esse fato é lido sozinho do XML da NF-e de entrada.
Para o resto — e para os 857 itens de `products` que não casam com nenhuma NF-e de entrada nossa — não há
documento no sistema, e a régua **recusa** a nota. Esta é a tela onde uma pessoa registra o fato
com a fonte escrita ao lado, em vez de o sistema chutar.

`telas()` roda `icms_entrada.sincronizar(db)` no primeiro acesso: DDL idempotente (duas colunas
em `fin_produtos`) e preenchimento a partir dos XMLs já guardados. Não sobrescreve nada que uma
pessoa tenha registrado.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.fiscal.services import icms_entrada as ie

#: DECLARADO AQUI, antes do import do `redesign_data_controller` — mesmo motivo do `_dgx_z4`:
#: o discovery dele importa `fiscal.py`, que importa este arquivo, e com o `router` lá embaixo
#: o módulo fiscal inteiro cai para o fallback do monólito sem erro visível.
router = APIRouter()

#: DECLARADO ANTES do import abaixo pelo mesmo motivo: `fiscal.py` lê `EXTRA_MENU` no import, e
#: o discovery do `redesign_data_controller` reentra em `fiscal.py`. Com o menu lá embaixo, o
#: módulo fiscal inteiro caía para o fallback do monólito — medido em 24/09/2026:
#: «partially initialized module '_dgx_aa5_icms_st' has no attribute 'EXTRA_MENU'».
ABAS = [
    ("nfe-icms-entrada", "Como a mercadoria entrou (ICMS-ST)"),
    ("nfe-icms-entrada-registro", "Registrar como a mercadoria entrou"),
]
_ICO = "M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"
EXTRA_MENU: list[dict] = [{"id": i, "label": lbl, "icon": _ICO, "grupo": "Notas fiscais"} for i, lbl in ABAS]

from modules.operacional.controllers.redesign_data_controller import b, t  # noqa: E402

logger = logging.getLogger(__name__)
_ND = "#0F1B3A"

_SAIDA = {
    "st": "5405 / CST 060 · ICMS zero",
    "normal": "5102 / CST 00 · ICMS 20%",
    None: "— a régua recusa a nota",
}
_TOM = {"st": "ok", "normal": "mut", None: "bad"}


def _require_fiscal(current_user: CurrentActiveUser) -> None:
    from core.auth.module_scope import user_has_module

    if not user_has_module(current_user, "fiscal"):
        raise HTTPException(status_code=403, detail="O cadastro fiscal do produto é do fiscal.")


def _falhou(titulo: str, exc: Exception) -> dict:
    logger.error("dgx aa5: %s falhou: %s", titulo, exc, exc_info=True)
    return {
        "title": f"{titulo} — FALHOU", "sub": f"{type(exc).__name__}: {str(exc)[:300]}", "cta": "—",
        "type": "table", "grid": "1fr", "cols": ["Erro"],
        "rows": [{"cells": [t("A tela não conseguiu ler as fontes. O erro está no log do backend.", 500, "#B91C1C")]}],
    }  # fmt: skip


async def _tela(db) -> dict:
    r = await ie.resumo(db)
    rows = []
    for ln in r["linhas"]:
        s = ln["situacao"]
        rows.append(
            {
                "cells": [
                    t(ln["codigo"][:24], 600, _ND),
                    t(ln["descricao"][:52]),
                    t(ln["ncm"] or "—"),
                    b(ln["cst"] or "não registrado", _TOM[s]),
                    t(_SAIDA[s], 600, _ND if s else "#B91C1C"),
                    t((ln["fonte"] or "—")[:150]),
                ],
                "filtros": {"situacao": ie.SITUACOES[s][:48]},
            }
        )
    sem = r["sem_fonte"]
    return {
        "title": "Como a mercadoria entrou (ICMS-ST)",
        "sub": (
            f"{r['fin_produtos']} produtos no catálogo fiscal: **{r['st']}** entraram com o ICMS já "
            f"retido por substituição tributária (a saída deles é CFOP 5405 / CST 060, ICMS ZERO), "
            f"**{r['normal']}** entraram tributados (5102 / CST 00 / 20%) e **{sem}** não têm "
            "tratamento com fonte — para esses a régua RECUSA a nota até alguém registrar aqui. "
            f"Fora do catálogo fiscal, `products` tem {r['products']} itens e **{r['products_sem_fato']}** "
            "deles não têm nenhuma NF-e de entrada nossa: só entram numa nota depois de cadastrados "
            "em `fin_produtos` e registrados aqui. O fato é lido do XML da nota de ENTRADA do "
            "fornecedor (106 dos 209 itens medidos vieram com ICMS-ST) e nunca é inferido por NCM — "
            "5 NCMs da casa têm entradas divergentes, então NCM não serve de chave."
        ),
        "cta": "—",
        "type": "table",
        "filtros": [{"key": "situacao", "label": "Situação"}],
        "grid": "1fr 2.2fr 0.8fr 1fr 1.3fr 3fr",
        "cols": ["Código", "Produto", "NCM", "CST/CSOSN da entrada", "Como sai", "Fonte"],
        "rows": rows,
    }


def _tela_registro() -> dict:
    """O formulário. Fica separado porque a tela do redesign é de UM tipo só (table OU form)."""
    return {
        "title": "Registrar como a mercadoria entrou",
        "sub": (
            "Use quando o sistema não tem a NF-e de ENTRADA do produto e alguém SABE, com documento "
            "na mão, como ele entrou. A fonte é obrigatória e fica gravada ao lado do número, com "
            "quem registrou e quando — número fiscal sem de-onde-veio não entra aqui. Exemplo de "
            "fonte válida: a própria NF-e de SAÍDA nº 10.026, série 1, protocolo 113263811849419, "
            "autorizada em 17/09/2026, que traz os seis itens com CST 060."
        ),
        "cta": "Registrar entrada",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/redesign/action/nfe-icms-entrada-registrar",
            "okMsg": "Registrado. A partir de agora a régua usa este fato na emissão.",
            "showResult": True,
            "confirm": "Isto muda o imposto das próximas notas deste produto. Confirma?",
        },
        "fields": [
            {
                "key": "codigo",
                "label": "Código do produto (como está em fin_produtos)*",
                "type": "text",
                "span": "span 2",
                "ph": "ex.: 118",
            },
            {
                "key": "cst",
                "label": "CST/CSOSN de ICMS da nota de ENTRADA*",
                "type": "select",
                "span": "span 2",
                "options": [
                    {"value": "60", "label": "60 — ICMS cobrado anteriormente por ST → sai 5405 / CST 060"},
                    {"value": "10", "label": "10 — tributada com cobrança de ICMS por ST → sai 5405 / CST 060"},
                    {"value": "30", "label": "30 — isenta com cobrança de ICMS por ST → sai 5405 / CST 060"},
                    {"value": "70", "label": "70 — redução de base com cobrança por ST → sai 5405 / CST 060"},
                    {"value": "500", "label": "CSOSN 500 — ICMS retido por ST (fornecedor do Simples)"},
                    {"value": "00", "label": "00 — tributada integralmente → sai 5102 / CST 00 / 20%"},
                    {"value": "102", "label": "CSOSN 102 — fornecedor do Simples, sem ST → sai 5102"},
                ],
            },
            {
                "key": "fonte",
                "label": "A fonte — que documento prova isso?*",
                "type": "textarea",
                "span": "span 2",
                "ph": "ex.: NF-e de entrada nº 12345 de FORNECEDOR X, chave 1326…, item com CST 60; "
                "ou NF-e de saída nº 10.026 série 1, protocolo 113263811849419",
            },
        ],  # fmt: skip
    }


async def telas(db, out: dict | None = None) -> dict:
    mine: dict = {}
    try:
        await ie.sincronizar(db)  # DDL idempotente + leitura dos XMLs já guardados
        mine["nfe-icms-entrada"] = await _tela(db)
        mine["nfe-icms-entrada-registro"] = _tela_registro()
    except Exception as exc:  # noqa: BLE001 — visível na tela, nunca calado
        await db.rollback()
        mine["nfe-icms-entrada"] = _falhou("Como a mercadoria entrou (ICMS-ST)", exc)
    if isinstance(out, dict):
        out.update(mine)
    return mine


# ───── ação (POST /api/v1/redesign/action/…) — o `router` está declarado lá no topo ─────
@router.post("/action/nfe-icms-entrada-registrar", dependencies=[Depends(_require_fiscal)])
async def rd_nfe_icms_entrada_registrar(
    current_user: CurrentActiveUser,
    payload: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Registra o fato de UM produto. Grava a fonte e quem registrou junto com o número."""
    quem = getattr(current_user, "email", None) or "(não identificado)"
    try:
        r = await ie.registrar(
            db,
            codigo=str(payload.get("codigo") or ""),
            cst=str(payload.get("cst") or ""),
            fonte=str(payload.get("fonte") or ""),
            quem=quem,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info("dgx aa5: %s registrou entrada do produto %s como CST %s", quem, r["codigo"], r["icms_entrada_cst"])
    return {
        "ok": True,
        **r,
        "resumo": (
            f"Produto {r['codigo']}: entrada registrada como CST/CSOSN {r['icms_entrada_cst']} — "
            f"{ie.SITUACOES[r['situacao']]}"
        ),
    }
