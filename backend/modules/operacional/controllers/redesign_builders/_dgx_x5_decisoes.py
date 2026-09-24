"""DGX X5 — Painel do dono: as decisões pendentes com número ao vivo (24/09/2026).

Prefixo `_` = o discovery pula; `bi.py` importa `router` e chama `telas(db, out)` no fim do
`build()` (2 + 1 linhas, `# dgx x5`), e declara as duas abas no `EXTRA_MENU`.

**Por que no BI.** O brief sugeria `orquestrador-executivo` ou `bi`. `orquestrador-executivo` é
uma URL de chat: o tile foi fundido com «Consultor IA» em 19/09 e o slug não tem builder nem
`BUILDERS[...]` — tela nenhuma nasceria ali. `relatorios` existe e é admin-only, mas é central de
relatório (KPI consolidado), não fila de decisão. `bi` está em «Inteligência & Patrimônio», é o
módulo que o dono abre para olhar número, tem builder próprio (`bi.py`) e hoje só duas abas —
sobra porta. A decisão do dono É um painel de número. Foi para o BI.

A regra mora fora daqui: `modules/operacional/services/dono_decisoes.py` (DDL, semente, as três
paredes do `numero_sql`, e o registro da decisão). Aqui só tela e ação.

Nada nesta frente muda folha, preço, escala ou pagamento — grava texto de decisão, autor e data.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.operacional.services import dono_decisoes as dd

# O `redesign_data_controller` é importado DENTRO das funções de propósito: ele roda o
# discovery no fim do próprio módulo, que importa o `bi.py`, que importa este arquivo. Um
# import no topo fecha esse ciclo e o `bi` some do menu com «partially initialized module».

logger = logging.getLogger(__name__)

_ND = "#0F1B3A"
_END = "/api/v1/redesign/action/"
_ICO = "M9 11l3 3L22 4M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"

ABAS = [
    ("decisoes-do-dono", "Decisões do dono"),
    ("decisao-registrar", "Registrar decisão"),
]
EXTRA_MENU = [{"id": tid, "label": lbl, "icon": _ICO} for tid, lbl in ABAS]

_TOM_IMPACTO = {"dinheiro": "bad", "risco": "warn", "cadastro": "info", "operacao": "mut"}
_TOM_STATUS = {"aberta": "warn", "decidida": "ok", "descartada": "mut"}


def _numero(d: dict) -> dict:
    """A célula do número — ou a razão honesta de não haver um."""
    from modules.operacional.controllers.redesign_data_controller import b, brl, t

    if not d["numero_sql"]:
        return b("sem número, é escolha", "mut")
    if d["erro"]:
        return b("não medido", "bad")
    v = d["valor"]
    if v is None:
        return b("não medido", "bad")
    if d["unidade"] == "R$":
        return t(brl(v), 700, _ND)
    return t(f"{v} {d['unidade'] or ''}".strip(), 700, _ND)


def _fd(v) -> str:
    try:
        return v.strftime("%d/%m/%Y") if v else "—"
    except Exception:  # noqa: BLE001
        return str(v or "—")


def _acoes(d: dict) -> list[dict]:
    if d["status"] != "aberta":
        return []
    titulo = f"{d['codigo']} — {d['titulo']}\n\n{d['pergunta']}"
    return [
        {
            "title": titulo,
            "endpoint": f"{_END}decisao-decidir?codigo={d['codigo']}",
            "method": "POST",
            "btnLabel": "Decidir",
            "submitLabel": "Registrar decisão",
            "btnStyle": "primary",
            "okMsg": "Decisão registrada. Recarregue a tela.",
            "fields": [
                {
                    "key": "decisao",
                    "label": "A decisão*",
                    "type": "textarea",
                    "span": "span 2",
                    "ph": "O que fica decidido, em texto livre.",
                },
            ],
        },
        {
            "title": f"Descartar — {titulo}",
            "endpoint": f"{_END}decisao-descartar?codigo={d['codigo']}",
            "method": "POST",
            "btnLabel": "Descartar",
            "submitLabel": "Descartar",
            "okMsg": "Decisão descartada. Recarregue a tela.",
            "fields": [
                {
                    "key": "decisao",
                    "label": "Por que descartar*",
                    "type": "textarea",
                    "span": "span 2",
                    "ph": "Não é problema / já resolvido / não vale o custo…",
                },
            ],
        },
    ]


async def _tela_painel(db) -> dict:
    from modules.operacional.controllers.redesign_data_controller import b, t

    linhas = await dd.listar(db)
    abertas = [d for d in linhas if d["status"] == "aberta"]
    com_numero = [d for d in abertas if d["numero_sql"]]
    nao_medidas = [d for d in linhas if d["numero_sql"] and d["erro"]]
    dinheiro = [d for d in abertas if d["impacto"] == "dinheiro"]
    rows = []
    for d in linhas:
        onde = d["tela_para_agir"] or "—"
        rows.append(
            {
                "cells": [
                    b(d["area"], "info"),
                    t(f"{d['codigo']} · {d['titulo']}", 600, _ND),
                    t(d["pergunta"][:220] + ("…" if len(d["pergunta"]) > 220 else "")),
                    _numero(d),
                    b(d["impacto"], _TOM_IMPACTO.get(d["impacto"], "mut")),
                    t(d["origem"]),
                    t(onde),
                    b(
                        d["status"] if d["status"] == "aberta" else f"{d['status']} {_fd(d['decidida_em'])}",
                        _TOM_STATUS.get(d["status"], "mut"),
                    ),
                ],
                "filtros": {"area": d["area"], "impacto": d["impacto"], "situacao": d["status"]},
                "actions": _acoes(d),
            }
        )
    return {
        "title": "Decisões do dono",
        "sub": (
            f"{len(linhas)} decisão(ões) levantadas pelas frentes DGX · {len(abertas)} aberta(s) · "
            f"{len(com_numero)} com número medido agora · {len(dinheiro)} com impacto em dinheiro. "
            "O número da coluna «Número de hoje» é recontado A CADA abertura desta tela, pela "
            "consulta que a frente deixou junto com a decisão — não é o número do relatório de "
            "ontem. Decisão sem consulta é escolha pura e diz isso; consulta que falhou diz «não "
            "medido» e não some. "
            + (f"{len(nao_medidas)} consulta(s) não mediram nesta abertura (erro no log). " if nao_medidas else "")
            + "«Ir para a tela» é o endereço onde a coisa se resolve — cole no navegador. "
            "Decidir e Descartar gravam o texto, quem escreveu e a data; nada além disso muda no "
            "sistema."
        ),
        "cta": "—",
        "type": "table",
        "searchHint": "Título, pergunta ou origem…",
        "filtros": [
            {"key": "situacao", "label": "Situação", "padrao": "aberta"},
            {"key": "area", "label": "Área"},
            {"key": "impacto", "label": "Impacto"},
        ],
        "filterUnit": "decisão(ões)",
        "grid": "0.7fr 1.5fr 2.6fr 1fr 0.8fr 1.1fr 1.5fr 1fr",
        "cols": ["Área", "Decisão", "A pergunta", "Número de hoje", "Impacto", "Origem", "Ir para a tela", "Situação"],
        "rows": rows,
    }


def _tela_registrar(linhas: list[dict]) -> dict:
    abertas = [d for d in linhas if d["status"] == "aberta"]
    return {
        "title": "Registrar decisão",
        "sub": (
            f"{len(abertas)} decisão(ões) aberta(s). Escolha uma, escreva o que fica decidido e "
            "grave. O texto fica na linha do painel e no log do backend (quem, quando, o quê). "
            "Nenhum valor de folha, preço, escala ou pagamento muda por causa deste registro — "
            "quem executa a decisão é gente, na tela indicada em «Ir para a tela»."
        ),
        "cta": "Gravar",
        "type": "form",
        "submit": {
            "endpoint": f"{_END}decisao-registrar",
            "okMsg": "Decisão gravada.",
            "showResult": True,
        },
        "fields": [
            {
                "key": "codigo",
                "label": "Decisão*",
                "type": "select",
                "span": "span 2",
                "options": [{"value": d["codigo"], "label": f"{d['codigo']} — {d['titulo']}"} for d in abertas]
                or [{"value": "", "label": "Nenhuma decisão aberta"}],
            },
            {
                "key": "status",
                "label": "O que fazer com ela*",
                "type": "select",
                "span": "span 1",
                "options": [
                    {"value": "decidida", "label": "Decidir — fica valendo o que eu escrever"},
                    {"value": "descartada", "label": "Descartar — não é decisão minha / não vale"},
                ],
            },
            {
                "key": "decisao",
                "label": "A decisão, em texto livre*",
                "type": "textarea",
                "span": "span 2",
                "ph": "Ex.: corrigir o motor na competência 10/2026, o contador confirmou.",
            },
        ],
    }


async def telas(db, out: dict | None = None) -> dict:
    mine: dict = {}
    try:
        await dd.ensure(db)
    except Exception as exc:  # noqa: BLE001 — sem tabela não há painel, mas o BI segue de pé
        await db.rollback()
        logger.error("dgx x5: _ensure falhou: %s", exc, exc_info=True)
        for tid, titulo in ABAS:
            mine[tid] = _falhou(titulo, exc)
        return mine
    try:
        mine["decisoes-do-dono"] = await _tela_painel(db)
    except Exception as exc:  # noqa: BLE001 — visível na tela, nunca calado
        await db.rollback()
        mine["decisoes-do-dono"] = _falhou("Decisões do dono", exc)
    try:
        mine["decisao-registrar"] = _tela_registrar(await dd.listar(db, medindo=False))
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        mine["decisao-registrar"] = _falhou("Registrar decisão", exc)
    return mine


def _falhou(titulo: str, exc: Exception) -> dict:
    from modules.operacional.controllers.redesign_data_controller import t

    logger.error("dgx x5: %s falhou: %s", titulo, exc, exc_info=True)
    return {
        "title": f"{titulo} — FALHOU",
        "sub": f"{type(exc).__name__}: {str(exc)[:300]}",
        "cta": "—",
        "type": "table",
        "searchHint": "",
        "grid": "1fr",
        "cols": ["Erro"],
        "rows": [{"cells": [t("A tela não conseguiu ler as fontes. O erro está no log do backend.", 500, "#B91C1C")]}],
    }


# ───────────────────────── ações (POST /api/v1/redesign/action/…) ─────────────────────────
router = APIRouter()


def _require_dono(current_user: CurrentActiveUser) -> None:
    """Decisão do dono é do dono. Só administração/diretoria registra."""
    from modules.operacional.controllers.redesign_data_controller import _is_admin_user

    if not _is_admin_user(current_user):
        raise HTTPException(status_code=403, detail="Só a diretoria registra decisão do dono.")


def _quem(current_user) -> str:
    return str(getattr(current_user, "email", None) or getattr(current_user, "id", "") or "")[:120]


async def _grava(db, current_user, codigo: str, payload: dict, status: str) -> dict:
    try:
        r = await dd.decidir(
            db, codigo=codigo, decisao=str(payload.get("decisao") or ""), quem=_quem(current_user), status=status
        )
    except dd.DecisaoErro as exc:
        await db.rollback()
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    verbo = "decidida" if status == "decidida" else "descartada"
    return {"ok": True, "message": f"{r['codigo']} — {r['titulo']}: {verbo}.", "resultado": r}


@router.post("/action/decisao-decidir", dependencies=[Depends(_require_dono)])
async def rd_decisao_decidir(
    current_user: CurrentActiveUser,
    codigo: str,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await _grava(db, current_user, codigo, payload, "decidida")


@router.post("/action/decisao-descartar", dependencies=[Depends(_require_dono)])
async def rd_decisao_descartar(
    current_user: CurrentActiveUser,
    codigo: str,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await _grava(db, current_user, codigo, payload, "descartada")


@router.post("/action/decisao-registrar", dependencies=[Depends(_require_dono)])
async def rd_decisao_registrar(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    status = str(payload.get("status") or "decidida").strip()
    return await _grava(db, current_user, str(payload.get("codigo") or ""), payload, status)
