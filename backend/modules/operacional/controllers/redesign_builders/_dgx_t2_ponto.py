"""DGX T2 — Ponto: fechamento como ato (reabertura com motivo) e integração de batimentos
(arquivo AFD de relógio → batidas do cartão), 24/09/2026.

Prefixo `_` = o discovery pula; `departamento_pessoal.py` importa `router` e chama `telas(db, out)`
no fim do build() (2 + 1 linhas, `# dgx t2`). Abas no FIM do grupo "Ponto & Jornada" (g-ponto).

Regra mora fora daqui: `people_management/ponto/fechamento.py` (trava + reabertura + DDL) e
`people_management/ponto/integracao_batimentos.py` (parser 1510/671, idempotência, DDL).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.operacional.controllers.redesign_data_controller import b, t
from modules.people_management.ponto import fechamento, integracao_batimentos

from ._dgx_f7_ponto import _falhou, _fd, _require_dp

logger = logging.getLogger(__name__)
_ND = "#0F1B3A"
ABAS = [
    ("integracao-batimentos", "Integração de batimentos"),
    ("integracao-batimentos-importar", "Importar arquivo do relógio"),
    ("ponto-reaberturas", "Meses fechados / reaberturas"),
    ("ponto-reabrir-mes", "Reabrir mês"),
]
_MESES = [{"value": str(m), "label": f"{m:02d}"} for m in range(1, 13)]


async def _tela_integracoes(db) -> dict:
    await integracao_batimentos._ensure(db)
    rows = (
        await db.execute(
            text(
                "SELECT created_at AT TIME ZONE 'America/Manaus', origem, coalesce(arquivo,'—'), simulacao, linhas, marcacoes, importadas, duplicadas, "
                "sem_pessoa, mes_fechado, invalidas, coalesce(quem,'—'), coalesce(jsonb_array_length(erros),0) "
                "FROM ponto_integracoes_batimentos ORDER BY id DESC LIMIT 100"
            )
        )
    ).fetchall()
    fontes = (
        await db.execute(
            text(
                "SELECT coalesce(device_id,'?'), count(*), max(punch_timestamp) FROM gp_clock_punches "
                "WHERE device_type = :d AND punch_timestamp >= now() - interval '30 days' GROUP BY 1 ORDER BY 2 DESC"
            ),
            {"d": integracao_batimentos.DEVICE_TYPE},
        )
    ).fetchall()
    sub = (
        "Cada linha é uma importação de arquivo AFD (Portaria 1510 ou 671) de um relógio/terceiro. "
        "A marcação vira batida do cartão com chave afd:<origem>:<NSR> — importar de novo não duplica. "
        "Mês fechado recusa (reabra com motivo). "
        + (
            "Batidas de relógio nos últimos 30 dias: "
            + "; ".join(f"{o} = {n} (última {_fd(u, '%d/%m %H:%M')})" for o, n, u in fontes)
            if fontes
            else "Nenhuma batida de relógio nos últimos 30 dias."
        )
    )
    return {
        "title": "Integração de batimentos",
        "sub": sub,
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar origem…",
        "cols": [
            "Quando",
            "Origem",
            "Arquivo",
            "Modo",
            "Linhas/marcações",
            "Importadas",
            "Duplicadas",
            "Sem pessoa",
            "Mês fechado",
            "Inválidas",
            "Quem",
        ],
        "grid": "1fr 1fr 1.4fr 0.7fr 1fr 0.8fr 0.8fr 0.8fr 0.8fr 0.7fr 1.2fr",
        "rows": [
            {
                "cells": [
                    t(_fd(r[0], "%d/%m/%Y %H:%M")),
                    t(r[1], 600, _ND),
                    t(r[2]),
                    b("só validar" if r[3] else "gravou", "warn" if r[3] else "ok"),
                    t(f"{r[4]} / {r[5]}"),
                    b(str(r[6]), "ok" if r[6] else "mut"),
                    t(str(r[7])),
                    b(str(r[8]), "bad" if r[8] else "mut"),
                    b(str(r[9]), "warn" if r[9] else "mut"),
                    t(str(r[10])),
                    t(r[11][:30]),
                ]
            }
            for r in rows
        ],
    }


def _tela_importar() -> dict:
    return {
        "title": "Importar arquivo do relógio (AFD)",
        "sub": "Arquivo AFD do REP-C/REP-A ou de terceiro. Aceita o leiaute da Portaria 1510 (PIS) e o da 671 "
        "(CPF, hora com fuso). Só os registros de marcação (tipo 3 e 7) viram batida. Entrada/saída são "
        "alternadas por pessoa e dia. «Só validar» mostra o que aconteceria sem gravar.",
        "cta": "Importar",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/redesign/action/integracao-batimentos-importar",
            "method": "POST",
            "multipart": True,
            "showResult": True,
            "okMsg": "Arquivo processado — veja o resultado.",
            "confirm": "As marcações do arquivo viram batidas do cartão (salvo em «Só validar»). Confirma?",
        },
        "fields": [
            {
                "key": "origem",
                "label": "Origem (identificação do relógio)*",
                "type": "text",
                "span": "span 1",
                "ph": "ex.: REP-PORTARIA-01",
            },
            {
                "key": "simular",
                "label": "Modo",
                "type": "select",
                "span": "span 1",
                "options": [
                    {"value": "false", "label": "Importar (grava)"},
                    {"value": "true", "label": "Só validar (não grava)"},
                ],
            },
            {
                "key": "arquivo",
                "label": "Arquivo AFD (.txt)*",
                "type": "file",
                "accept": ".txt,.afd,.dat,text/plain",
                "span": "span 2",
            },
        ],
    }


async def _tela_reaberturas(db) -> dict:
    await fechamento._ensure(db)
    rows = (
        await db.execute(
            text(
                "SELECT r.created_at AT TIME ZONE 'America/Manaus', coalesce(e.nome, r.employee_id), r.mes, r.ano, r.motivo, coalesce(r.quem,'—'), "
                "r.espelhos, r.fechamentos, coalesce(r.status_anterior,'—') "
                "FROM ponto_reaberturas r LEFT JOIN employees e ON CAST(e.id AS text) = r.employee_id "
                "ORDER BY r.id DESC LIMIT 200"
            )
        )
    ).fetchall()
    fech = (
        await db.execute(
            text(
                "SELECT ano, mes, sum(esp), sum(fec) FROM ("
                "  SELECT reference_year ano, reference_month mes, count(*) esp, 0 fec FROM time_sheets "
                "   WHERE lower(coalesce(status,'')) IN ('fechado','aprovado','revisado','enviado_folha') GROUP BY 1,2"
                "  UNION ALL SELECT year, month, 0, count(*) FROM gp_monthly_closings WHERE fechado IS TRUE GROUP BY 1,2"
                ") x GROUP BY 1,2 ORDER BY 1 DESC, 2 DESC LIMIT 12"
            )
        )
    ).fetchall()
    sub = (
        "O mês fechado TRAVA ajuste, lançamento manual e importação de batida para a pessoa — reabrir é ato com "
        "motivo, registrado aqui. Fechados hoje: "
        + (
            "; ".join(f"{m:02d}/{a} = {int(e)} espelho(s) + {int(f)} fechamento(s) mensal" for a, m, e, f in fech)
            if fech
            else "nenhum"
        )
    )
    return {
        "title": "Meses fechados e reaberturas",
        "sub": sub,
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar colaborador…",
        "cols": [
            "Quando",
            "Colaborador",
            "Competência",
            "Motivo",
            "Quem",
            "Espelhos",
            "Fechamentos",
            "Status anterior",
        ],
        "grid": "1fr 1.8fr 0.8fr 2.4fr 1.2fr 0.7fr 0.8fr 1fr",
        "rows": [
            {
                "cells": [
                    t(_fd(r[0], "%d/%m/%Y %H:%M")),
                    t(r[1], 600, _ND),
                    t(f"{r[2]:02d}/{r[3]}"),
                    t(r[4][:120]),
                    t(r[5][:30]),
                    t(str(r[6])),
                    t(str(r[7])),
                    t(r[8]),
                ]
            }
            for r in rows
        ],
    }


async def _tela_reabrir(db) -> dict:
    rows = (
        await db.execute(
            text(
                "SELECT DISTINCT CAST(e.id AS text), e.nome FROM employees e WHERE CAST(e.id AS text) IN ("
                "  SELECT employee_id FROM time_sheets WHERE lower(coalesce(status,'')) IN ('fechado','aprovado','revisado')"
                "  UNION SELECT employee_id FROM gp_monthly_closings WHERE fechado IS TRUE) ORDER BY e.nome"
            )
        )
    ).fetchall()
    anos = sorted(
        {
            r[0]
            for r in (
                await db.execute(
                    text(
                        "SELECT DISTINCT reference_year FROM time_sheets UNION SELECT DISTINCT year FROM gp_monthly_closings"
                    )
                )
            ).fetchall()
            if r[0]
        },
        reverse=True,
    )
    return {
        "title": "Reabrir mês de ponto (uma pessoa)",
        "sub": "Volta o espelho a «aberto» (perde homologação/assinatura) e desfaz o fechamento mensal da pessoa. "
        "Espelho já ENVIADO à folha não reabre por aqui. O motivo é obrigatório e fica no histórico.",
        "cta": "Reabrir",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/redesign/action/ponto-reabrir-mes",
            "okMsg": "Mês reaberto — veja o resultado.",
            "showResult": True,
            "confirm": "Reabrir invalida a homologação e a assinatura do espelho desta pessoa na competência. Confirma?",
        },
        "fields": [
            {
                "key": "employee_id",
                "label": "Colaborador (só quem tem mês fechado)*",
                "type": "select",
                "span": "span 2",
                "ph": "Selecione",
                "options": [{"value": r[0], "label": r[1]} for r in rows],
            },
            {"key": "mes", "label": "Mês*", "type": "select", "span": "span 1", "options": _MESES},
            {
                "key": "ano",
                "label": "Ano*",
                "type": "select",
                "span": "span 1",
                "options": [{"value": str(a), "label": str(a)} for a in anos] or [{"value": "2026", "label": "2026"}],
            },
            {
                "key": "motivo",
                "label": "Motivo* (mín. 5 caracteres)",
                "type": "textarea",
                "span": "span 2",
                "ph": "ex.: batida do dia 12 ficou de fora; DP corrige e fecha de novo",
            },
        ],
    }


async def telas(db, out: dict | None = None) -> dict:
    mine: dict = {}
    montagens = [
        ("integracao-batimentos", "Integração de batimentos", lambda: _tela_integracoes(db)),
        ("integracao-batimentos-importar", "Importar arquivo do relógio", lambda: _tela_importar()),
        ("ponto-reaberturas", "Meses fechados / reaberturas", lambda: _tela_reaberturas(db)),
        ("ponto-reabrir-mes", "Reabrir mês", lambda: _tela_reabrir(db)),
    ]
    for tid, titulo, fn in montagens:
        try:
            r = fn()
            mine[tid] = await r if hasattr(r, "__await__") else r
        except Exception as exc:  # noqa: BLE001 — visível na tela, nunca calado
            await db.rollback()
            mine[tid] = _falhou(titulo, exc)
    grupo = (out or {}).get("g-ponto")
    if isinstance(grupo, dict) and isinstance(grupo.get("tabs"), list):
        from modules.operacional.controllers.redesign_data_controller import moved

        ja = {tb.get("id") for tb in grupo["tabs"]}
        for tid, lbl in ABAS:
            if tid in mine and tid not in ja:
                grupo["tabs"].append({"id": tid, "label": lbl, "screen": mine[tid]})
                mine[tid] = moved("g-ponto", tid)
    return mine


# ───────────────────────── ações (POST /api/v1/redesign/action/…) ─────────────────────────
router = APIRouter()


def _quem(current_user) -> str:
    return str(getattr(current_user, "email", None) or getattr(current_user, "id", "") or "")[:120]


@router.post("/action/integracao-batimentos-importar", dependencies=[Depends(_require_dp)])
async def rd_integracao_importar(
    current_user: CurrentActiveUser,
    arquivo: UploadFile = File(...),
    origem: str = Form(""),
    simular: str = Form("false"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    raw = await arquivo.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")
    if len(raw) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Arquivo maior que 20 MB.")
    try:
        conteudo = raw.decode("utf-8")
    except UnicodeDecodeError:
        conteudo = raw.decode("latin-1")
    try:
        r = await integracao_batimentos.importar(
            db,
            conteudo,
            origem,
            _quem(current_user),
            simular=str(simular).lower() == "true",
            arquivo=arquivo.filename or "",
        )
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    modo = "SIMULAÇÃO — nada gravado" if r["simulacao"] else "gravado"
    return {
        "ok": True,
        "message": f"{modo}: {r['marcacoes']} marcação(ões) em {r['linhas']} linha(s) — {r['importadas']} importada(s), "
        f"{r['duplicadas']} duplicada(s), {r['sem_pessoa']} sem pessoa, {r['mes_fechado']} em mês fechado, {r['invalidas']} inválida(s).",
        "resultado": r,
    }


@router.post("/action/ponto-reabrir-mes", dependencies=[Depends(_require_dp)])
async def rd_reabrir_mes(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    eid = str(payload.get("employee_id") or "").strip()
    if not eid:
        raise HTTPException(status_code=400, detail="Escolha o colaborador.")
    try:
        mes, ano = int(payload.get("mes") or 0), int(payload.get("ano") or 0)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Mês/ano inválidos.") from exc
    try:
        r = await fechamento.reabrir(db, eid, mes, ano, str(payload.get("motivo") or ""), _quem(current_user))
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "ok": True,
        "message": f"Competência {mes:02d}/{ano} reaberta (#{r['id']}): {r['espelhos']} espelho(s) e {r['fechamentos']} fechamento(s) mensal. "
        "Corrija, recalcule e feche de novo.",
        "resultado": r,
    }
