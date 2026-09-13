"""Frente 05 — conformidade de vigilante no redesign (Gestão de Pessoas).

Telas: `vigilante-aptidao` (painel: quem vence em 30/60/90, quem está SEM DADO — separado),
`vigilante-pessoas` (aptidão por pessoa, com ações por linha), `vigilante-equipamentos`
(armamento/colete em posse, entregar/devolver por linha) e os FORMs `vigilante-curso-novo` /
`vigilante-equipamento-novo`. Ações em POST /api/v1/redesign/action/vigilante-*.

Ligado por `gestao_de_pessoas.py` (menu, router e `telas()` no fim do build). A regra é a do
serviço `hr/services/conformidade_vigilante` — nada é calculado aqui. Vazio real = "sem dado".
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.operacional.controllers.redesign_data_controller import IC, S, _fmtdate, b, t
from modules.people_management.hr.schemas.vigilante import (
    CursoCreate,
    EntregaCreate,
    EquipamentoCreate,
    NomeDeGuerraUpdate,
)
from modules.people_management.hr.services import conformidade_vigilante as cv

logger = logging.getLogger(__name__)

_IC_CURSO = "M12 3a5 5 0 1 0 0 10 5 5 0 0 0 0-10M8 13l-2 8 6-3 6 3-2-8"
MENU: list[dict] = [
    {"id": "vigilante-aptidao", "label": "Vigilante · Aptidão", "icon": IC["shield"]},
    {"id": "vigilante-pessoas", "label": "Vigilante · Por pessoa", "icon": IC["users"]},
    {"id": "vigilante-equipamentos", "label": "Vigilante · Armamento e colete", "icon": IC["shield"]},
    {"id": "vigilante-curso-novo", "label": "Vigilante · Cadastrar curso", "icon": _IC_CURSO},
    {"id": "vigilante-equipamento-novo", "label": "Vigilante · Cadastrar equipamento", "icon": IC["shield"]},
]

_TIPOS_CURSO = [
    ("formacao", "Formação"),
    ("reciclagem_patrimonial", "Reciclagem patrimonial"),
    ("reciclagem_escolta_armada", "Reciclagem escolta armada"),
    ("reciclagem_vspp", "Reciclagem VSPP"),
    ("outro", "Outro"),
]
_ACT = "/api/v1/redesign/action/"


def _sel(key, label, options, ph="Selecione", span="span 1"):
    return {"key": key, "label": label, "type": "select", "span": span, "ph": ph, "options": options}


def _campos_curso(validade_padrao: int | None) -> list[dict]:
    return [
        _sel("tipo", "Tipo*", [{"value": v, "label": l} for v, l in _TIPOS_CURSO]),
        {"key": "data_conclusao", "label": "Data de CONCLUSÃO do curso*", "type": "date", "span": "span 1"},
        {
            "key": "validade_meses",
            "label": "Validade (meses)",
            "type": "number",
            "span": "span 1",
            "value": str(validade_padrao) if validade_padrao else "",
            "ph": "parâmetro não configurado — informe" if not validade_padrao else "",
        },
        {"key": "local", "label": "Local / escola", "type": "text", "span": "span 1", "ph": "Ex.: Escola X — Manaus"},
        {"key": "certificado_url", "label": "Certificado (link)", "type": "text", "span": "span 2", "ph": "https://…"},
    ]


def _situacao(p: dict) -> dict:
    if not p["sujeito"]:
        return b("Não exige", "mut")
    if p["apto"]:
        return b("Apto", "ok")
    return b("Sem dado", "warn") if any("sem" in m for m in p["motivos"]) else b("Inapto", "bad")


async def telas(db: AsyncSession) -> dict:
    out: dict = {}
    try:
        out.update(await _telas(db))
    except Exception:  # noqa: BLE001 — DDL ausente/erro não pode derrubar o módulo inteiro
        await db.rollback()
        logger.exception("frente 05: telas de vigilante indisponíveis")
        out["vigilante-aptidao"] = {
            "title": "Vigilante · Aptidão",
            "sub": "aguardando dado — tabelas da frente 05 não aplicadas neste banco",
            "type": "dash",
            "panelGrid": "1fr",
            "kpis": [],
            "panels": [
                {"title": "Sem dado", "rows": [{"left": "Ver FRENTE_05_vigilante.md (DDL)", "right": "—", **S["mut"]}]}
            ],
        }
    return out


async def _telas(db: AsyncSession) -> dict:
    hoje = cv.hoje_manaus()
    validade_padrao = await cv.validade_meses_padrao(db)
    funcoes = await cv.funcoes_exigem_credencial(db)
    pessoas = await cv.aptidao(db)
    escalados = await cv.aptidao(db, so_escalados_hoje=True)
    venc = await cv.vencimentos(db)
    equip = await cv.posse_equipamentos(db)
    ativos = (
        await db.execute(
            text(
                "SELECT id::text, nome, coalesce(nullif(nome_de_guerra,''), '') FROM employees "
                "WHERE status='ativo' AND coalesce(is_homologacao,false)=false ORDER BY nome"
            )
        )
    ).fetchall()
    opt_pessoas = [{"value": i, "label": f"{n}" + (f" ({g})" if g else "")} for i, n, g in ativos]

    esc_suj = [p for p in escalados if p["sujeito"]]
    esc_inapto = [p for p in esc_suj if not p["apto"]]
    esc_sem_dado = [p for p in esc_inapto if any("sem" in m for m in p["motivos"])]
    esc_vencido = [p for p in esc_inapto if p not in esc_sem_dado]

    def _venc_rows(itens, estilo):
        return [
            {"left": f"{x['nome']} · {x['item']}", "right": f"{_fmtdate(x['vence_em'])} ({x['dias']}d)", **S[estilo]}
            for x in itens
        ] or [{"left": "ninguém", "right": "—", **S["mut"]}]

    v30 = [x for x in venc["vencendo"] if x["janela"] == 30]
    v60 = [x for x in venc["vencendo"] if x["janela"] == 60]
    v90 = [x for x in venc["vencendo"] if x["janela"] == 90]
    regua = (
        "chave `vigilante.funcoes_exigem_credencial` AUSENTE → todo mundo está sujeito (conservador)"
        if funcoes is None
        else "funções que exigem credencial: " + ", ".join(funcoes)
    )
    out = {}
    out["vigilante-aptidao"] = {
        "title": "Vigilante · Aptidão",
        "sub": f"{len(esc_suj)} escalado(s) hoje sujeito(s) à régua · {hoje:%d/%m/%Y}",
        "cta": "—",
        "type": "dash",
        "panelGrid": "1fr 1fr",
        "kpis": [
            {"v": str(len(esc_suj)), "l": "Escalados hoje (sujeitos)", "icon": IC["users"], "color": "#0F1B3A"},
            {"v": str(len(esc_suj) - len(esc_inapto)), "l": "Aptos", "icon": IC["shield"], "color": "#16A34A"},
            {
                "v": str(len(esc_vencido)),
                "l": "Vencidos",
                "icon": IC["alert"],
                "color": "#B91C1C" if esc_vencido else "#0F1B3A",
            },
            {
                "v": str(len(esc_sem_dado)),
                "l": "SEM DADO",
                "icon": IC["alert"],
                "color": "#B45309" if esc_sem_dado else "#0F1B3A",
            },
        ],
        "panels": [
            {
                "title": "SEM DADO — escalados hoje (o DP precisa cadastrar)",
                "rows": [
                    {
                        "left": f"{p['nome']} · {p['cargo'] or '—'} · {p['posto']}",
                        "right": "; ".join(p["motivos"]),
                        **S["warn"],
                    }
                    for p in esc_sem_dado
                ]
                or [{"left": "ninguém sem dado", "right": "—", **S["ok"]}],
            },
            {
                "title": "VENCIDOS — escalados hoje (não podem assumir posto)",
                "rows": [
                    {"left": f"{p['nome']} · {p['posto']}", "right": "; ".join(p["motivos"]), **S["bad"]}
                    for p in esc_vencido
                ]
                or [{"left": "ninguém vencido", "right": "—", **S["ok"]}],
            },
            {"title": "Vence em até 30 dias", "rows": _venc_rows(v30, "bad")},
            {"title": "Vence em 31–60 dias", "rows": _venc_rows(v60, "warn")},
            {"title": "Vence em 61–90 dias", "rows": _venc_rows(v90, "info")},
            {
                "title": "Régua em vigor",
                "rows": [
                    {"left": regua, "right": "", **S["mut"]},
                    {
                        "left": "validade da reciclagem (system_configs)",
                        "right": f"{validade_padrao} meses da conclusão" if validade_padrao else "NÃO CONFIGURADA",
                        **(S["mut"] if validade_padrao else S["bad"]),
                    },
                    {"left": "ausência de dado", "right": "= inapto (nunca 'válido')", **S["mut"]},
                ],
            },
        ],
    }

    def _acoes_pessoa(p):
        return [
            {
                "title": f"Cadastrar curso — {p['nome']}",
                "sub": "A validade conta da CONCLUSÃO do curso, não da emissão do certificado.",
                "endpoint": _ACT + "vigilante-curso",
                "method": "POST",
                "btnLabel": "Curso",
                "submitLabel": "Cadastrar curso",
                "btnStyle": "primary",
                "okMsg": "Curso cadastrado. Recarregue a tela.",
                "fields": [{"key": "employee_id", "type": "hidden", "value": p["id"]}, *_campos_curso(validade_padrao)],
            },
            {
                "title": f"Nome de guerra — {p['nome']}",
                "sub": "Identificação operacional (rádio, escala). Não é nome social.",
                "endpoint": _ACT + "vigilante-nome-de-guerra",
                "method": "POST",
                "btnLabel": "Nome de guerra",
                "submitLabel": "Salvar",
                "btnStyle": "outline",
                "okMsg": "Nome de guerra salvo. Recarregue a tela.",
                "fields": [
                    {"key": "employee_id", "type": "hidden", "value": p["id"]},
                    {
                        "key": "nome_de_guerra",
                        "label": "Nome de guerra",
                        "type": "text",
                        "span": "span 2",
                        "value": p["nome_de_guerra"] or "",
                    },
                ],
            },
        ]

    out["vigilante-pessoas"] = {
        "title": "Vigilante · Por pessoa",
        "sub": f"{sum(1 for p in pessoas if p['sujeito'])} sujeito(s) à régua entre {len(pessoas)} ativos",
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar pessoa…",
        "grid": "2fr 1fr 1.4fr 1fr 1fr 1.4fr 1fr 1fr",
        "cols": ["Colaborador", "Nome de guerra", "Cargo", "CNV", "Validade CNV", "Reciclagem", "Vence em", "Situação"],
        "rows": [
            {
                "cells": [
                    t(p["nome"], 600, "#0F1B3A"),
                    t(p["nome_de_guerra"] or "—"),
                    t(p["cargo"] or "—"),
                    t(p["cnv"] or "—"),
                    t(
                        _fmtdate(p["cnv_validade"]) if p["cnv_validade"] else "sem dado",
                        500,
                        "#B45309" if not p["cnv_validade"] else "#334155",
                    ),
                    t((p["curso_tipo"] or "sem dado").replace("_", " ")),
                    t(
                        _fmtdate(p["curso_vence_em"]) if p["curso_vence_em"] else "sem dado",
                        500,
                        "#B45309" if not p["curso_vence_em"] else "#334155",
                    ),
                    _situacao(p),
                ],
                "actions": _acoes_pessoa(p),
            }
            for p in pessoas
        ],
    }

    livres = [e for e in equip if not e["alocacao_id"] and e["status"] == "ativo"]

    def _acoes_equip(e):
        if e["alocacao_id"]:
            return [
                {
                    "title": f"Devolver {e['tipo']} {e['numero_serie']}",
                    "sub": f"Em posse de {e['responsavel']} desde {_fmtdate(e['entregue_em'])}.",
                    "endpoint": _ACT + "vigilante-devolver",
                    "method": "POST",
                    "btnLabel": "Devolver",
                    "submitLabel": "Registrar devolução",
                    "btnStyle": "outline",
                    "okMsg": "Devolução registrada. Recarregue a tela.",
                    "fields": [
                        {"key": "equipamento_id", "type": "hidden", "value": e["id"]},
                        {
                            "key": "observacao",
                            "label": "Observação",
                            "type": "textarea",
                            "span": "span 2",
                            "ph": "estado do equipamento, motivo…",
                        },
                    ],
                }
            ]
        if e["status"] != "ativo":
            return None
        return [
            {
                "title": f"Entregar {e['tipo']} {e['numero_serie']}",
                "sub": "Armamento só sai para quem está APTO (CNV e reciclagem válidas).",
                "endpoint": _ACT + "vigilante-entregar",
                "method": "POST",
                "btnLabel": "Entregar",
                "submitLabel": "Registrar entrega",
                "btnStyle": "primary",
                "okMsg": "Entrega registrada. Recarregue a tela.",
                "fields": [
                    {"key": "equipamento_id", "type": "hidden", "value": e["id"]},
                    _sel("employee_id", "Responsável*", opt_pessoas, span="span 2"),
                    {
                        "key": "observacao",
                        "label": "Observação",
                        "type": "textarea",
                        "span": "span 2",
                        "ph": "opcional",
                    },
                ],
            }
        ]

    out["vigilante-equipamentos"] = {
        "title": "Vigilante · Armamento e colete",
        "sub": f"{len(equip)} equipamento(s) · {sum(1 for e in equip if e['alocacao_id'])} em posse · {len(livres)} disponíveis",
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar série ou responsável…",
        "grid": "1fr 1.4fr 1.2fr 0.8fr 1fr 2fr 1.2fr",
        "cols": ["Tipo", "Nº de série", "Modelo", "Calibre", "Estado", "Responsável", "Entregue em"],
        "rows": [
            {
                "cells": [
                    t(e["tipo"].capitalize(), 600, "#0F1B3A"),
                    t(e["numero_serie"], 600, "#0F1B3A"),
                    t(e["modelo"] or "—"),
                    t(e["calibre"] or "—"),
                    b("Em posse", "info")
                    if e["alocacao_id"]
                    else b(e["status"].capitalize(), "ok" if e["status"] == "ativo" else "warn"),
                    t(
                        (e["responsavel"] + (f" ({e['nome_de_guerra']})" if e["nome_de_guerra"] else ""))
                        if e["responsavel"]
                        else "disponível"
                    ),
                    t(_fmtdate(e["entregue_em"]) if e["entregue_em"] else "—"),
                ],
                "actions": _acoes_equip(e),
            }
            for e in equip
        ],
    }

    out["vigilante-curso-novo"] = {
        "title": "Vigilante · Cadastrar curso",
        "sub": "Formação ou reciclagem CONCLUÍDA. Vence em = conclusão + validade (meses).",
        "cta": "Cadastrar",
        "type": "form",
        "submit": {"endpoint": _ACT + "vigilante-curso", "okMsg": "Curso cadastrado"},
        "fields": [_sel("employee_id", "Colaborador*", opt_pessoas, span="span 2"), *_campos_curso(validade_padrao)],
    }
    out["vigilante-equipamento-novo"] = {
        "title": "Vigilante · Cadastrar equipamento",
        "sub": "Arma ou colete — UM por número de série. Sem série não é controle.",
        "cta": "Cadastrar",
        "type": "form",
        "submit": {"endpoint": _ACT + "vigilante-equipamento", "okMsg": "Equipamento cadastrado"},
        "fields": [
            _sel(
                "tipo",
                "Tipo*",
                [{"value": "armamento", "label": "Armamento"}, {"value": "colete", "label": "Colete balístico"}],
            ),
            {"key": "numero_serie", "label": "Nº de série*", "type": "text", "span": "span 1", "ph": "gravado na peça"},
            {"key": "modelo", "label": "Modelo", "type": "text", "span": "span 1", "ph": "Ex.: Taurus RT 838"},
            {"key": "calibre", "label": "Calibre", "type": "text", "span": "span 1", "ph": "Ex.: .38"},
        ],
    }
    return out


# ───────────────────────── ações (POST /api/v1/redesign/action/vigilante-*) ─────────────────────────

router = APIRouter()


def _erro(e: Exception) -> HTTPException:
    if isinstance(e, ValidationError):
        msg = "; ".join(f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors())
        return HTTPException(status_code=422, detail=msg)
    return HTTPException(status_code=422, detail=str(e))


def _limpa(payload: dict) -> dict:
    """Formulário manda '' para campo vazio; para o schema isso é 'não informado'."""
    return {k: (None if v == "" else v) for k, v in (payload or {}).items()}


@router.post("/action/vigilante-curso")
async def rd_vigilante_curso(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    try:
        body = CursoCreate(**_limpa(payload))
        r = await cv.cadastrar_curso(db, user_id=str(current_user.id), **body.model_dump())
    except (ValidationError, ValueError) as e:
        raise _erro(e) from e
    return {"ok": True, "message": f"Curso cadastrado — vence em {_fmtdate(r['vence_em'])}", **r}


@router.post("/action/vigilante-equipamento")
async def rd_vigilante_equipamento(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    try:
        body = EquipamentoCreate(**_limpa(payload))
        r = await cv.cadastrar_equipamento(db, **body.model_dump())
    except (ValidationError, ValueError) as e:
        raise _erro(e) from e
    return {"ok": True, "message": "Equipamento cadastrado", **r}


@router.post("/action/vigilante-entregar")
async def rd_vigilante_entregar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    p = _limpa(payload)
    if not p.get("equipamento_id"):
        raise HTTPException(status_code=422, detail="equipamento não informado")
    try:
        body = EntregaCreate(**{k: p.get(k) for k in ("employee_id", "observacao")})
        r = await cv.entregar(
            db,
            equipamento_id=p["equipamento_id"],
            employee_id=str(body.employee_id),
            user_id=str(current_user.id),
            observacao=body.observacao,
        )
    except (ValidationError, ValueError) as e:
        raise _erro(e) from e
    return {"ok": True, "message": "Entrega registrada", **r}


@router.post("/action/vigilante-devolver")
async def rd_vigilante_devolver(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    p = _limpa(payload)
    if not p.get("equipamento_id"):
        raise HTTPException(status_code=422, detail="equipamento não informado")
    try:
        r = await cv.devolver(
            db, equipamento_id=p["equipamento_id"], user_id=str(current_user.id), observacao=p.get("observacao")
        )
    except ValueError as e:
        raise _erro(e) from e
    return {"ok": True, "message": "Devolução registrada", **r}


@router.post("/action/vigilante-nome-de-guerra")
async def rd_vigilante_nome_de_guerra(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    p = _limpa(payload)
    if not p.get("employee_id"):
        raise HTTPException(status_code=422, detail="colaborador não informado")
    try:
        body = NomeDeGuerraUpdate(nome_de_guerra=p.get("nome_de_guerra"))
    except ValidationError as e:
        raise _erro(e) from e
    if not await cv.definir_nome_de_guerra(db, employee_id=p["employee_id"], nome_de_guerra=body.nome_de_guerra):
        raise HTTPException(status_code=404, detail="colaborador não encontrado")
    return {"ok": True, "message": "Nome de guerra salvo"}
