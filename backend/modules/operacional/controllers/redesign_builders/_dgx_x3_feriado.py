"""DGX X3 — Feriado trabalhado e HE 100%: o que a CCT manda pagar × o que a folha pagou.

24/09/2026. Telas `feriado-trabalhado` (lista nominal da competência, divergência em vermelho e
total em R$) e `feriado-apurar` (o form que roda a apuração), no **g-folha** — é dinheiro de folha,
e quem decide o que fazer com o número é o DP.

A regra mora fora daqui: `people_management/folha/services/feriado_conferencia.py` (escopo do
feriado importado da F7, pareamento importado do `horas_service`, a citação da CCT/CLT, a DDL).
Aqui só tela e ação. **Paralelo cego:** nenhum holerite muda — a tela diz isso com essas palavras
e `scripts/orq/test_oraculo_x3_feriado_he100.py` prova (Σ|Δ| nos holerites = R$ 0,00).

Prefixo `_` = o discovery pula; `departamento_pessoal.py` importa `router` (topo) e chama
`telas(db, out)` antes de `montar_grupos` (as abas estão em `_dp_grupos.GRUPOS`, fim do g-folha).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

#: ANTES do import do data_controller (mesmo motivo da F1/W5: o ciclo fecha com o router pronto)
router = APIRouter()

from modules.operacional.controllers.redesign_data_controller import b, brl, t  # noqa: E402
from modules.people_management.folha.services import feriado_conferencia as fc  # noqa: E402

logger = logging.getLogger(__name__)
_ND = "#0F1B3A"
_ACT = "/api/v1/redesign/action/"
ABAS = [("feriado-trabalhado", "Feriado trabalhado e HE 100%"), ("feriado-apurar", "Apurar feriado/HE 100%")]


def _fd(d) -> str:
    return d.strftime("%d/%m/%Y") if d else "—"


def _opc_comp(comps: list[str]) -> list[dict]:
    return [{"value": c, "label": f"{c[5:7]}/{c[:4]}"} for c in comps]


async def _tela_lista(db, comp: str | None) -> dict:
    if not comp:
        return {
            "title": "Feriado trabalhado e HE 100%",
            "sub": "Nenhuma competência com holerite ainda.",
            "cta": "—",
            "type": "table",
            "grid": "1fr",
            "cols": ["Situação"],
            "rows": [{"cells": [t("aguardando dado honesto")]}],
        }
    await fc.apurar(db, comp)
    lns = await fc.linhas(db, comp)
    res = await fc.resumo(db, comp)
    rows = []
    for x in lns:
        divergente = x["diferenca"] > 0.005
        rows.append(
            {
                "cells": [
                    t(x["nome"][:34], 600, _ND),
                    t(_fd(x["data"])),
                    b(fc.TIPOS.get(x["tipo"], x["tipo"]), "bad" if x["tipo"] == "feriado_trabalhado" else "warn"),
                    t((x["feriado"] or "—")[:38]),
                    b(x["escopo"] or "—", "info"),
                    b("sim" if x["teve_turno"] else "não", "ok" if x["teve_turno"] else "mut"),
                    t(f"{x['horas']:.2f}h" + ("  ⚠ sem par de batidas" if x["horas"] <= 0 else "")),
                    t(brl(x["pago_como"])),
                    t(brl(x["deveria_ser"])),
                    b(brl(x["diferenca"]), "bad") if divergente else b("R$ 0,00", "ok"),
                    t((x["pago_detalhe"] or "—")[:150]),
                ],
                "filtros": {
                    "Tipo": fc.TIPOS.get(x["tipo"], x["tipo"]),
                    "Situação": "divergente" if divergente else "em dia",
                    "Escala": x["escala"] or "—",
                },
            }
        )
    return {
        "title": f"Feriado trabalhado e HE 100% — {comp[5:7]}/{comp[:4]}",
        "sub": (
            f"{res['linhas']} linha(s) · {res['pessoas']} pessoa(s) · {res['feriados']} feriado(s) com gente "
            f"trabalhando · {res['horas']:.2f}h · pago {brl(res['pago'])} · devido pela regra {brl(res['devido'])} · "
            f"**diferença {brl(res['diferenca'])}**. "
            f"Feriado trabalhado não compensado se paga em DOBRO (art. 9º da Lei 605/49, Súmula 146 do TST e, no "
            f"12x36, Súmula 444 do TST); HE em feriado/domingo/dia de descanso é 100% (CCT SINDECOMPRESTS "
            f"AM000613/2025 — cct_cargos.horas_extras_noturnas_percentual = 100,00). A rubrica **0011 Hora Extra "
            f"100% existe e nunca foi emitida** pelo motor. "
            f"**Esta tela NÃO muda holerite nenhum** — é conferência em paralelo cego; quem prova é o oráculo "
            f"`x3_feriado_he100` (Σ|Δ| nos holerites = R$ 0,00). "
            f"O escopo do feriado é o da F7: de cliente vale só para aquele condomínio."
        ),
        "cta": "—",
        "type": "table",
        "searchHint": "Colaborador, feriado…",
        "filtros": [
            {"key": "Tipo", "label": "Tipo"},
            {"key": "Situação", "label": "Situação"},
            {"key": "Escala", "label": "Escala"},
        ],
        "grid": "1.6fr 0.8fr 1.2fr 1.6fr 0.7fr 0.6fr 0.8fr 0.9fr 0.9fr 0.9fr 2.4fr",
        "cols": [
            "Colaborador",
            "Dia",
            "Tipo",
            "Feriado / motivo",
            "Escopo",
            "Tinha escala?",
            "Horas",
            "Pago",
            "Deveria ser",
            "Diferença",
            "O que o holerite pagou",
        ],
        "rows": rows,
    }


def _tela_apurar(comps: list[str]) -> dict:
    return {
        "title": "Apurar feriado / HE 100%",
        "sub": (
            "Recruza feriados (`cct_feriados`, com o escopo da F7), turnos (`shifts`), batidas "
            "(`gp_clock_punches`) e o holerite da competência. Idempotente: rodar de novo atualiza as linhas, "
            "nunca duplica. **Não escreve nada na folha** — só na tabela de conferência desta frente."
        ),
        "cta": "Apurar",
        "type": "form",
        "submit": {
            "endpoint": _ACT + "feriado-apurar",
            "okMsg": "Apuração concluída — veja a aba «Feriado trabalhado e HE 100%».",
            "showResult": True,
        },
        "fields": [
            {
                "key": "competencia",
                "label": "Competência*",
                "type": "select",
                "span": "span 1",
                "options": _opc_comp(comps),
            }
        ],
    }


async def telas(db, out: dict | None = None) -> dict:
    mine: dict = {}
    try:
        comps = await fc.competencias(db)
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        comps = []
        logger.error("dgx x3: competências falharam: %s", exc, exc_info=True)
    comp = comps[0] if comps else None
    for tid, titulo, fn in (
        ("feriado-trabalhado", "Feriado trabalhado e HE 100%", lambda: _tela_lista(db, comp)),
        ("feriado-apurar", "Apurar feriado/HE 100%", lambda: _tela_apurar(comps)),
    ):
        try:
            r = fn()
            mine[tid] = await r if hasattr(r, "__await__") else r
        except Exception as exc:  # noqa: BLE001 — visível na tela, nunca calado
            await db.rollback()
            logger.error("dgx x3: tela %s falhou: %s", tid, exc, exc_info=True)
            from ._dgx_f7_ponto import _falhou

            mine[tid] = _falhou(titulo, exc)
    if out is not None:
        out.update(mine)
    return mine


@router.post("/action/feriado-apurar")
async def rd_feriado_apurar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    """Roda a apuração da competência. Não toca em `hr_payslips` — paralelo cego."""
    from modules.people_management.ponto.he_classificacao import HEClassificacaoErro

    comp = str(payload.get("competencia") or "").strip()
    try:
        r = await fc.apurar(db, comp)
        res = await fc.resumo(db, comp)
    except HEClassificacaoErro as exc:
        await db.rollback()
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    return {
        "ok": True,
        "result": {**r, **res},
        "message": (
            f"{res['linhas']} linha(s) em {comp[5:7]}/{comp[:4]} · {res['pessoas']} pessoa(s) · "
            f"diferença {brl(res['diferenca'])}. Nenhum holerite foi alterado (paralelo cego)."
        ),
    }
