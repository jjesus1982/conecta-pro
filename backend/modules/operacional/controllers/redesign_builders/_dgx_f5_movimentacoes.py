"""DGX F5 — Movimentações no Operacional (24/09/2026): listar / incluir / encerrar alocação de
vaga com motivo tipado. A regra mora em `operacional/services/movimentacao_service.py`; aqui só
se pinta e se despacha. Prefixo `_` = o discovery pula; `operacional.py` importa `router` no topo
e chama `telas(db, out)` antes de `montar_grupos` (abas no grupo Escalas & Turnos, `_op_grupos`).

Telas: `movimentacoes` (ledger: uma linha por alocação + uma linha "Remover" quando encerrada
por remoção, filtros por mês e condomínio, ação Encerrar por linha ativa), `movimentacao-nova`
(form; tipo=remover encerra a alocação ativa do colaborador), `movimentacao-encerrar` (form).
Deep-link: `/redesign/operacional?t=movimentacoes`.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.operacional.services import movimentacao_service as ms

logger = logging.getLogger(__name__)
_ND = "#0F1B3A"
_END = "/api/v1/redesign/action/"

SQL_LEDGER = """
SELECT a.id::text, a.data_inicio, a.data_fim, a.ativo, coalesce(a.tipo,'alocar'), a.motivo, a.motivo_encerramento,
       e.nome, c.nome, p.name, a.funcao, co.nome, o.funcao, cb.nome, a.solicitado_por, a.solicitante_nome,
       u.name, a.aprovado_em, a.observacao
FROM employee_alocacoes a
LEFT JOIN employees e ON e.id = a.employee_id
LEFT JOIN condominios c ON c.id = a.condominio_id
LEFT JOIN posts p ON p.id = a.posto_id
LEFT JOIN employee_alocacoes o ON o.id = a.alocacao_origem_id
LEFT JOIN condominios co ON co.id = o.condominio_id
LEFT JOIN employees cb ON cb.id = a.coberto_employee_id
LEFT JOIN users u ON u.id = a.aprovado_por
ORDER BY coalesce(a.data_fim, a.data_inicio) DESC, a.data_inicio DESC, e.nome
LIMIT 400
"""
SQL_EMPS = (
    "SELECT id::text, nome, coalesce(cargo,'') FROM employees WHERE status = 'ativo' "
    "AND coalesce(is_homologacao,false) = false ORDER BY nome"
)
SQL_CONDS = "SELECT id::text, nome FROM condominios WHERE ativo ORDER BY nome"
SQL_POSTOS = (
    "SELECT p.id::text, c.nome, p.name FROM posts p JOIN condominios c ON c.client_id = p.client_id "
    "WHERE p.is_active ORDER BY c.nome, p.name"
)
SQL_FUNCOES = (
    "SELECT DISTINCT upper(f) FROM (SELECT funcao f FROM employee_alocacoes UNION "
    "SELECT cargo FROM employees WHERE status = 'ativo' AND coalesce(cargo,'') <> '') x ORDER BY 1"
)
SQL_ATIVAS = (
    "SELECT a.id::text, e.nome, c.nome, a.funcao, a.data_inicio FROM employee_alocacoes a "
    "JOIN employees e ON e.id = a.employee_id JOIN condominios c ON c.id = a.condominio_id "
    "WHERE a.ativo ORDER BY e.nome"
)


def _d(v) -> str:
    return v.strftime("%d/%m/%Y") if v else "—"


def _opts(rows, label, vazio="— escolha —") -> list[dict]:
    return [{"value": "", "label": vazio}] + [{"value": r[0], "label": label(r)} for r in rows]


def _motivo_opts() -> list[dict]:
    return [{"value": "", "label": "— motivo —"}] + [{"value": k, "label": v} for k, v in ms.MOTIVOS.items()]


def _acao_encerrar(r, hoje: str) -> dict:
    return {
        "title": f"ENCERRAR a alocação de {r[7]} em {r[8]} ({r[10]})",
        "endpoint": f"{_END}movimentacao-remover?alocacao_id={r[0]}",
        "method": "POST",
        "btnLabel": "Encerrar",
        "submitLabel": "Encerrar",
        "btnStyle": "danger",
        "okMsg": "Alocação encerrada. Recarregue a tela.",
        "fields": [
            {"key": "data_fim", "label": "Último dia na vaga*", "type": "date", "value": hoje},
            # `ms.remover` recusa motivo vazio (400) — mesmo defeito do form `movimentacao-nova`
            {"key": "motivo", "label": "Motivo*", "type": "select", "options": _motivo_opts()},
            {"key": "observacao", "label": "Observação", "type": "text"},
        ],
    }


async def telas(db, out: dict) -> None:
    from modules.operacional.controllers.redesign_data_controller import b, initials, t

    try:
        await ms._ensure(db)
        rows = (await db.execute(text(SQL_LEDGER))).fetchall()
        emps = (await db.execute(text(SQL_EMPS))).fetchall()
        conds = (await db.execute(text(SQL_CONDS))).fetchall()
        postos = (await db.execute(text(SQL_POSTOS))).fetchall()
        funcoes = [r[0] for r in (await db.execute(text(SQL_FUNCOES))).fetchall()]
        ativas = (await db.execute(text(SQL_ATIVAS))).fetchall()
    except Exception as exc:  # noqa: BLE001 — visível, nunca calado
        await db.rollback()
        logger.error("dgx f5: movimentações falharam: %s", exc, exc_info=True)
        out["movimentacoes"] = {
            "title": "Movimentações — FALHOU",
            "sub": f"{type(exc).__name__}: {str(exc)[:300]}",
            "cta": "—",
            "type": "table",
            "searchHint": "",
            "grid": "1fr",
            "cols": ["Erro"],
            "rows": [
                {"cells": [t("A tela não conseguiu ler as fontes. O erro está no log do backend.", 500, "#B91C1C")]}
            ],
        }
        return

    hoje = ms.hoje_manaus()
    hoje_s = hoje.isoformat()
    linhas: list[dict] = []
    n_ativas = sum(1 for r in rows if r[3])

    def _linha(r, remocao: bool) -> dict:
        (
            _id,
            ini,
            fim,
            ativo,
            tipo,
            motivo,
            motivo_enc,
            nome,
            cond,
            posto,
            funcao,
            o_cond,
            o_func,
            coberto,
            sol,
            sol_nome,
            aprov,
            aprov_em,
            _obs,
        ) = r
        para = " · ".join(x for x in (cond, posto, funcao) if x) or "—"
        if remocao:
            data, de, para_txt, mot = fim, para, "(sem vaga)", motivo_enc
            badge = b("Remover", "bad")
        else:
            data = ini
            de = " · ".join(x for x in (o_cond, o_func) if x) or "—"
            para_txt, mot = para, motivo
            badge = b("Alocar", "ok" if ativo else "mut")
        quem = (ms.SOLICITANTES.get(sol or "", sol or "—")) + (f" ({sol_nome})" if sol_nome else "")
        status = b("ativa", "ok") if ativo else b(f"encerrada {_d(fim)}", "mut")
        return {
            "cells": [
                t(_d(data), 600),
                badge,
                t(nome or "—", 600, _ND, initials(nome or "")),
                t(f"{de} → {para_txt}"),
                t(ms.MOTIVOS.get(mot or "", mot or "—")),
                t(coberto or "—"),
                t(quem),
                t(f"{aprov} · {_d(aprov_em)}" if aprov else "—"),
                status,
            ],
            "filtros": {
                "mes": f"{data:%m/%Y}" if data else "—",
                "condominio": cond or "—",
                "status": "ativa" if ativo else "encerrada",  # dgx u1
            },
            "actions": [_acao_encerrar(r, hoje_s)] if (ativo and not remocao) else [],
        }

    try:  # dgx u1 — pedidos pendentes/recusadas (op_movimentacao_pedidos) no mesmo ledger, com Aprovar/Recusar
        from ._dgx_u1_movimentacao_supervisao import linhas_pedidos

        linhas.extend(await linhas_pedidos(db))
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.warning("dgx u1: pedidos no ledger falharam: %s", exc)
    n_pend = sum(1 for x in linhas if x["filtros"].get("status") == "pendente")

    for r in rows:
        if r[4] == "remover" and r[2]:
            linhas.append(_linha(r, True))
        linhas.append(_linha(r, False))

    out["movimentacoes"] = {
        "title": "Movimentações — alocar / remover de vaga",
        "sub": (
            f"{n_ativas} alocação(ões) ativa(s) · {n_pend} pedido(s) aguardando o DP · {len(rows)} no histórico · "
            "motivo tipado (7 do DGX) · fonte: employee_alocacoes (a mesma do kit GEDEON, Hermes e 'Sem alocação' do DP)"
        ),
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar colaborador, condomínio ou motivo…",
        "grid": "0.8fr 0.7fr 1.6fr 2fr 1.3fr 1.2fr 1.1fr 1.2fr 0.9fr",
        "cols": [
            "Data",
            "Tipo",
            "Colaborador",
            "De → Para",
            "Motivo",
            "Coberto",
            "Solicitado por",
            "Aprovado",
            "Situação",
        ],
        "filtros": [
            {"key": "mes", "label": "Mês"},
            {"key": "condominio", "label": "Condomínio"},
            {"key": "status", "label": "Situação"},  # dgx u1: pendente | ativa | recusada | encerrada
        ],
        "rows": linhas or [{"cells": [t("Nenhuma movimentação registrada", 500)] + [t("—")] * 8}],
    }

    out["movimentacao-nova"] = {
        "title": "Nova movimentação",
        "cta": "Registrar",
        "sub": (
            "Alocar em nova vaga encerra a alocação ativa anterior no dia anterior e liga origem → destino. "
            "Remover encerra a alocação ativa do colaborador na data. Cobertura de férias/afastamento exige o coberto "
            "com férias aprovadas / afastamento ativo na data."
        ),
        "type": "form",
        "submit": {
            "endpoint": _END + "movimentacao-alocar",
            "okMsg": "Movimentação registrada.",
            "showResult": True,
            "confirm": "Isto muda a alocação do colaborador de verdade (kit, Hermes e DP leem daqui). Confirma?",
        },
        "fields": [
            {
                "key": "employee_id",
                "label": "Colaborador*",
                "type": "select",
                "span": "span 2",
                "options": _opts(emps, lambda r: f"{r[1]} — {r[2]}" if r[2] else r[1], "— colaborador (ativos) —"),
            },
            {
                "key": "tipo",
                "label": "Tipo de movimentação*",
                "type": "select",
                "options": [
                    {"value": "alocar", "label": "Alocar colaborador em nova vaga"},
                    {"value": "remover", "label": "Remover o colaborador da vaga atual"},
                ],
            },
            {
                "key": "data_inicio",
                "label": "Data* (início, ou último dia se remover)",
                "type": "date",
                "value": hoje_s,
            },
            {
                # 28/09/2026: sem o `*` a tela dizia que era opcional e o validador exigia
                # («Colaborador, condomínio e função são obrigatórios») — 400 em 100% do caminho
                # feliz, e por isso `op_movimentacao_pedidos` e toda escrita do app em
                # `employee_alocacoes` ficaram em ZERO. Para `tipo=remover` o endpoint ignora
                # estes dois (a tela própria é `movimentacao-encerrar`).
                "key": "condominio_id",
                "label": "Condomínio (destino)* — ao alocar",
                "type": "select",
                "options": _opts(conds, lambda r: r[1]),
            },
            {
                "key": "posto_id",
                "label": "Posto (opcional)",
                "type": "select",
                "options": _opts(postos, lambda r: f"{r[1]} · {r[2]}", "— sem posto específico —"),
            },
            {
                "key": "funcao",
                "label": "Função* — ao alocar",
                "type": "select",
                "options": [{"value": "", "label": "— função —"}] + [{"value": f, "label": f} for f in funcoes],
            },
            {"key": "motivo", "label": "Motivo*", "type": "select", "options": _motivo_opts()},
            {
                "key": "coberto_employee_id",
                "label": "Coberto (só para cobertura de férias/afastamento)",
                "type": "select",
                "span": "span 2",
                "options": _opts(emps, lambda r: r[1], "— ninguém —"),
            },
            {
                "key": "solicitado_por",
                "label": "Solicitado por*",
                "type": "select",
                "options": [{"value": k, "label": v} for k, v in ms.SOLICITANTES.items() if k != "sistema"],
            },
            {"key": "solicitante_nome", "label": "Nome de quem pediu", "type": "text", "ph": "síndico, supervisor…"},
            {
                # dgx u1 — dois passos. 28/09/2026: o default era "" ("Automático"), e
                # «automático» se decidia por `e_dp` = tem `module:dp`. Medido: dos 78 usuários
                # ativos, TODOS os que alcançam o módulo Operacional têm `module:dp` — inclusive
                # o Orlailson (gerente_operacional), que é justamente quem PEDE. Resultado: o
                # default nunca caía no ramo `pedir()`, alocava direto, e o pedido pendente (a
                # coisa que faz a escala acompanhar a realidade) nunca nascia. O padrão agora é
                # PEDIR; alocar sem passar por ninguém é a exceção declarada, e só do DP.
                "key": "pedir_aprovacao",
                "label": "Pedir aprovação do DP?",
                "type": "select",
                "value": "sim",
                "options": [
                    {"value": "sim", "label": "Sim — fica pendente até o DP aprovar"},
                    {"value": "nao", "label": "Não — alocar agora (só DP/admin)"},
                ],
            },
            {"key": "observacao", "label": "Observação", "type": "textarea", "span": "span 2"},
        ],
    }

    out["movimentacao-encerrar"] = {
        "title": "Encerrar alocação",
        "cta": "Encerrar",
        "sub": f"{len(ativas)} alocação(ões) ativa(s). Encerra em `data_fim` com motivo tipado; a pessoa fica sem vaga até nova movimentação.",
        "type": "form",
        "submit": {
            "endpoint": _END + "movimentacao-remover",
            "okMsg": "Alocação encerrada.",
            "showResult": True,
            "confirm": "Isto encerra a alocação de verdade. Confirma?",
        },
        "fields": [
            {
                "key": "alocacao_id",
                "label": "Alocação ativa*",
                "type": "select",
                "span": "span 2",
                "options": _opts(ativas, lambda r: f"{r[1]} — {r[2]} · {r[3]} desde {_d(r[4])}", "— alocação —"),
            },
            {"key": "data_fim", "label": "Último dia na vaga*", "type": "date", "value": hoje_s},
            {"key": "motivo", "label": "Motivo*", "type": "select", "options": _motivo_opts()},
            {"key": "observacao", "label": "Observação", "type": "textarea", "span": "span 2"},
        ],
    }


# ───────────────────────── ações (POST /api/v1/redesign/action/…) ─────────────────────────
router = APIRouter()


def _erro(exc: ms.MovimentacaoErro) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=str(exc))


@router.post("/action/movimentacao-alocar")
async def rd_movimentacao_alocar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    p = {k: (str(v).strip() if v is not None else "") for k, v in payload.items()}
    uid = str(getattr(current_user, "id", "") or "") or None
    try:
        if p.get("tipo") == "remover":
            aloc = (
                await db.execute(
                    text(
                        "SELECT id::text FROM employee_alocacoes WHERE employee_id = CAST(:e AS uuid) AND ativo ORDER BY data_inicio DESC LIMIT 1"
                    ),
                    {"e": p.get("employee_id") or None},
                )
            ).scalar()
            if not aloc:
                raise HTTPException(status_code=404, detail="Esse colaborador não tem alocação ativa para remover.")
            r = await ms.remover(
                db,
                alocacao_id=aloc,
                data_fim=p.get("data_inicio"),
                motivo=p.get("motivo", ""),
                observacao=p.get("observacao"),
                user_id=uid,
            )
            return {
                "ok": True,
                "message": f"Removido da vaga atual em {r['data_fim'][8:10]}/{r['data_fim'][5:7]}/{r['data_fim'][:4]}.",
                **r,
            }
        # dgx u1 — dois passos: "" = automático (DP/admin direto, resto pede); "sim" = pede; "nao" = direto só DP/admin
        from ._dgx_u1_movimentacao_supervisao import e_dp

        pedir = p.get("pedir_aprovacao") or ""
        if pedir == "nao" and not e_dp(current_user):
            raise HTTPException(
                status_code=403, detail="Alocar direto é restrito ao DP — deixe em 'Sim' e envie o pedido."
            )
        if pedir == "sim" or (pedir == "" and not e_dp(current_user)):
            r = await ms.pedir(
                db,
                employee_id=p.get("employee_id", ""),
                condominio_id=p.get("condominio_id", ""),
                funcao=p.get("funcao", ""),
                posto_id=p.get("posto_id") or None,
                data_inicio=p.get("data_inicio"),
                motivo=p.get("motivo", ""),
                solicitado_por=p.get("solicitado_por") or "supervisor",
                solicitante_nome=p.get("solicitante_nome"),
                coberto_employee_id=p.get("coberto_employee_id") or None,
                observacao=p.get("observacao"),
                user_id=uid,
            )
            return {
                "ok": True,
                "message": "Pedido registrado — fica pendente até o DP aprovar (nada mudou ainda).",
                **r,
            }
        r = await ms.alocar(
            db,
            employee_id=p.get("employee_id", ""),
            condominio_id=p.get("condominio_id", ""),
            funcao=p.get("funcao", ""),
            posto_id=p.get("posto_id") or None,
            data_inicio=p.get("data_inicio"),
            motivo=p.get("motivo", ""),
            solicitado_por=p.get("solicitado_por") or "dp",
            solicitante_nome=p.get("solicitante_nome"),
            coberto_employee_id=p.get("coberto_employee_id") or None,
            observacao=p.get("observacao"),
            user_id=uid,
        )
    except ms.MovimentacaoErro as exc:
        await db.rollback()
        raise _erro(exc) from exc
    from modules.operacional.publishers import publish_alocacao_criada

    try:
        await publish_alocacao_criada(
            allocation_id=r["id"],
            employee_id=p.get("employee_id", ""),
            post_id=p.get("posto_id") or p.get("condominio_id", ""),
        )
    except Exception as exc:  # noqa: BLE001 — evento é aviso, não regra
        logger.warning("dgx f5: publish alocacao_criada falhou: %s", exc)
    enc = len(r["encerrou"])
    return {
        "ok": True,
        "message": f"Alocado. {enc} alocação(ões) anterior(es) encerrada(s) no dia anterior."
        if enc
        else "Alocado (não havia alocação anterior).",
        **r,
    }


@router.post("/action/movimentacao-remover")
async def rd_movimentacao_remover(
    current_user: CurrentActiveUser,
    alocacao_id: str | None = None,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    aid = alocacao_id or str(payload.get("alocacao_id") or "").strip()
    if not aid:
        raise HTTPException(status_code=400, detail="Escolha a alocação.")
    try:
        r = await ms.remover(
            db,
            alocacao_id=aid,
            data_fim=payload.get("data_fim"),
            motivo=str(payload.get("motivo") or ""),
            observacao=payload.get("observacao"),
            user_id=str(getattr(current_user, "id", "") or "") or None,
        )
    except ms.MovimentacaoErro as exc:
        await db.rollback()
        raise _erro(exc) from exc
    return {
        "ok": True,
        "message": f"Alocação encerrada em {r['data_fim'][8:10]}/{r['data_fim'][5:7]}/{r['data_fim'][:4]}.",
        **r,
    }
