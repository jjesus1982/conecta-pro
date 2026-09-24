"""DGX U2 — férias completas (24/09/2026): aviso em lote, recibo timbrado, conta a pagar, cobertura na
aprovação, ficha de férias por pessoa. Prefixo `_` = o discovery pula; `departamento_pessoal.py` chama
`telas(db, out)` ANTES de `montar_grupos` (abas no fim do g-ferias em `_dp_grupos.GRUPOS`) e
`mapa_descobertos(db, out)` DEPOIS da frente 08 (painel no `mapa-ferias`); inclui `router`.

A regra mora em `hr/services/ferias_dgx.py`. Aqui só tela e porta:
- `ferias` (SOBRESCREVE a tabela do builder): por linha, Aprovar (com substituto/posto opcionais),
  Rejeitar, Cancelar, Gerar conta, Cobertura; documentos Recibo (PDF) e Aviso (PDF) nas aprovadas.
- `aviso-ferias-lote`: mês de gozo + filtros → UM PDF (uma página por pessoa) e, se pedido, um pedido
  de assinatura do funcionário por aviso (mesmo helper do holerite).
- `ferias-pessoa`: ficha (saldo, mapa art. 133, períodos aquisitivos, gozos com conta/cobertura/recibo,
  avisos a assinar).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.auth.module_scope import exigir_dono
from core.database import get_db
from modules.operacional.controllers.redesign_data_controller import S, _fmtdate, _helpers, b, brl, doc, initials, t
from modules.people_management.hr.services import ferias_dgx as fd

_ND = "#0F1B3A"
_ACT = "/api/v1/redesign/action/"
_FER_ST = {
    "submitted": ("Pendente", "warn"),
    "approved": ("Aprovada", "ok"),
    "rejected": ("Rejeitada", "bad"),
    "cancelled": ("Cancelada", "mut"),
    "canceled": ("Cancelada", "mut"),
}

router = APIRouter()


def _gate_dp(current_user: CurrentActiveUser) -> None:
    from .departamento_pessoal import _require_modulo_dp  # lazy: departamento_pessoal importa este módulo

    _require_modulo_dp(current_user)


def _uuid(v, msg="Selecione a férias.") -> str:
    try:
        return str(UUID(str(v or "").strip()))
    except ValueError:
        raise HTTPException(status_code=422, detail=msg)


def _erro(exc: fd.FeriasErro) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=str(exc))


def _unome(u) -> str:
    return str(getattr(u, "name", "") or getattr(u, "email", "") or "redesign")


def _mes_br(m: str) -> str:
    return f"{m[5:7]}/{m[:4]}"


# ----------------------------------------------------------------------------- telas
async def _opt_pessoas(db) -> list[dict]:
    rows = (
        await db.execute(
            text(
                "SELECT id::text, nome FROM employees WHERE status = 'ativo' AND coalesce(is_homologacao,false) = false ORDER BY nome"
            )
        )
    ).fetchall()
    return [{"value": "", "label": "— sem substituto —"}] + [{"value": r[0], "label": r[1]} for r in rows]


async def _opt_postos(db) -> list[dict]:
    rows = (
        await db.execute(text("SELECT p.id::text, p.name FROM posts p WHERE p.is_active ORDER BY p.name"))
    ).fetchall()
    return [{"value": "", "label": "— posto onde o coberto tem turno no período —"}] + [
        {"value": r[0], "label": r[1]} for r in rows
    ]


async def _tela_ferias(db, out: dict) -> None:
    _, _safe, tbl = _helpers(db)
    pessoas, postos = await _opt_pessoas(db), await _opt_postos(db)
    f_sub = {
        "key": "substituto_id",
        "label": "Substituto (opcional — registra a cobertura F8 e a movimentação F5)",
        "type": "select",
        "span": "span 2",
        "options": pessoas,
    }
    f_pos = {
        "key": "posto_id",
        "label": "Posto coberto (opcional)",
        "type": "select",
        "span": "span 2",
        "options": postos,
    }

    def _row(r):
        lbl, tone = _FER_ST.get((r[5] or "").lower(), (r[5] or "—", "info"))
        return [
            t(r[1] or "—", 600, _ND, initials(r[1] or "")),
            t(_fmtdate(r[2])),
            t(_fmtdate(r[3])),
            t(str(r[4]) if r[4] is not None else "—"),
            b(lbl, tone),
            b("gerada", "ok") if r[6] else t("—"),
            b("registrada", "info") if r[7] else t("—"),
        ]

    def _docs(r):
        if (r[5] or "").upper() != "APPROVED":
            return None
        return [
            doc("Recibo (PDF)", f"/api/v1/redesign/ferias/{r[0]}/recibo/pdf", fmt="pdf"),
            doc("Aviso (PDF)", f"/api/v1/redesign/ferias/{r[0]}/aviso/pdf", fmt="pdf"),
        ]

    def _acts(r):
        st, vid, nome = (r[5] or "").upper(), r[0], r[1] or "—"
        cancelar = {
            "title": f"Cancelar as férias de {nome}",
            "sub": "Marca a solicitação como CANCELADA. O registro continua existindo.",
            "endpoint": f"/api/v1/people-management/hr/vacations/{vid}",
            "method": "DELETE",
            "btnLabel": "Cancelar",
            "submitLabel": "Cancelar solicitação",
            "btnStyle": "outline",
            "okMsg": "Solicitação cancelada. Recarregue.",
            "fields": [],
        }
        if st in ("CANCELLED", "CANCELADA", "CANCELED", "REJECTED", "REJEITADA"):
            return None
        if st == "SUBMITTED":
            return [
                {
                    "title": f"Aprovar férias de {nome}",
                    "sub": "Com substituto, a cobertura do posto (F8) e a movimentação `cobertura de férias` (F5) nascem na hora. "
                    "Sem substituto, a resposta diz de quando a quando o posto fica descoberto.",
                    "endpoint": f"{_ACT}ferias-aprovar-u2?vid={vid}",
                    "method": "POST",
                    "btnLabel": "Aprovar",
                    "submitLabel": "Aprovar",
                    "btnStyle": "primary",
                    "okMsg": "Férias aprovadas. Recarregue a tela.",
                    "fields": [f_sub, f_pos],
                },
                {
                    "title": f"Rejeitar férias de {nome}",
                    "endpoint": f"{_ACT}vacation-reject?vid={vid}",
                    "method": "POST",
                    "btnLabel": "Rejeitar",
                    "submitLabel": "Rejeitar",
                    "btnStyle": "outline",
                    "okMsg": "Férias rejeitada",
                    "fields": [
                        {
                            "key": "reason",
                            "label": "Motivo (obrigatório)",
                            "type": "textarea",
                            "span": "span 2",
                            "value": "",
                        }
                    ],
                },
                cancelar,
            ]
        if st != "APPROVED":
            return [cancelar]
        acts = []
        if not r[6]:
            acts.append(
                {
                    "title": f"Gerar conta a pagar — férias de {nome}",
                    "sub": "Registra UM pagável com o líquido da calculadora CLT, vencendo 2 dias antes do início (art. 145). "
                    "Não paga ninguém: o pagamento segue o fluxo do Financeiro.",
                    "endpoint": f"{_ACT}ferias-gerar-conta?vid={vid}",
                    "method": "POST",
                    "btnLabel": "Gerar conta",
                    "submitLabel": "Gerar",
                    "btnStyle": "outline",
                    "gated": True,
                    "confirm": f"Registrar a conta a pagar das férias de {nome} (líquido da calculadora, sem pagar)?",
                    "okMsg": "Conta a pagar registrada. Recarregue.",
                    "fields": [],
                }
            )
        if not r[7]:
            acts.append(
                {
                    "title": f"Cobertura das férias de {nome}",
                    "sub": "Quem cobre o posto no período — grava em Coberturas (F8) e Movimentações (F5).",
                    "endpoint": f"{_ACT}ferias-cobertura?vid={vid}",
                    "method": "POST",
                    "btnLabel": "Cobertura",
                    "submitLabel": "Registrar cobertura",
                    "btnStyle": "outline",
                    "okMsg": "Cobertura registrada. Recarregue.",
                    "fields": [f_sub, f_pos],
                }
            )
        return acts + [cancelar]

    n = (await db.execute(text("SELECT count(*) FROM hr_vacation_requests"))).scalar() or 0
    out["ferias"] = await tbl(
        "Férias",
        f"{n} solicitações (fonte canônica) · aprovada ganha Recibo e Aviso em PDF, conta a pagar e cobertura",
        "Solicitar férias",
        ["Colaborador", "Início", "Fim", "Dias", "Status", "Conta", "Cobertura"],
        "2fr 0.9fr 0.9fr 0.5fr 0.9fr 0.7fr 0.8fr",
        "SELECT v.id::text, coalesce(e.nome,'—'), v.start_date, v.end_date, v.days_requested, coalesce(v.status::text,'—'), "
        "v.payable_id::text, v.cobertura_id::text FROM hr_vacation_requests v LEFT JOIN employees e ON e.id = v.employee_id "
        "ORDER BY v.start_date DESC NULLS LAST LIMIT 200",
        _row,
        docsfn=_docs,
        actionsfn=_acts,
    )
    out["ferias"]["ctaTo"] = "solicitar-ferias"


async def _tela_aviso_lote(db, out: dict) -> None:
    meses = (
        await db.execute(
            text(
                "SELECT DISTINCT to_char(start_date,'YYYY-MM') AS m, count(*) FROM hr_vacation_requests WHERE status = 'APPROVED' "
                "AND start_date >= (CURRENT_DATE - interval '3 months') GROUP BY 1 ORDER BY 1"
            )
        )
    ).fetchall()
    clientes = (
        await db.execute(
            text(
                "SELECT DISTINCT e.cliente_nome FROM hr_vacation_requests h JOIN employees e ON e.id = h.employee_id WHERE h.status = 'APPROVED' AND e.cliente_nome IS NOT NULL ORDER BY 1"
            )
        )
    ).fetchall()
    cargos = (
        await db.execute(
            text(
                "SELECT DISTINCT e.cargo FROM hr_vacation_requests h JOIN employees e ON e.id = h.employee_id WHERE h.status = 'APPROVED' AND e.cargo IS NOT NULL ORDER BY 1"
            )
        )
    ).fetchall()
    out["aviso-ferias-lote"] = {
        "title": "Aviso de férias em lote",
        "sub": "Um PDF timbrado com um aviso por pessoa (art. 135 CLT — 30 dias de antecedência), das férias APROVADAS com início no mês. "
        "Opcionalmente abre um pedido de assinatura do colaborador por aviso, pelo mesmo caminho do holerite (não duplica se rodar de novo).",
        "cta": "Gerar avisos",
        "type": "form",
        "submit": {"endpoint": _ACT + "aviso-ferias-lote", "okMsg": "Avisos gerados — o PDF abre em seguida."},
        "fields": [
            {
                "key": "mes",
                "label": "Mês de gozo*",
                "type": "select",
                "span": "span 1",
                "ph": "Nenhuma férias aprovada nos últimos 3 meses / futuras" if not meses else "Selecione",
                "options": [{"value": m, "label": f"{_mes_br(m)} · {n} aprovada(s)"} for m, n in meses],
            },
            {
                "key": "assinatura",
                "label": "Enfileirar para assinatura do colaborador",
                "type": "select",
                "span": "span 1",
                "options": [
                    {"value": "nao", "label": "não — só o PDF"},
                    {"value": "sim", "label": "sim — um pedido por aviso"},
                ],
            },
            {
                "key": "cliente",
                "label": "Cliente (opcional)",
                "type": "select",
                "span": "span 1",
                "options": [{"value": "", "label": "todos"}] + [{"value": c[0], "label": c[0]} for c in clientes],
            },
            {
                "key": "cargo",
                "label": "Função (opcional)",
                "type": "select",
                "span": "span 1",
                "options": [{"value": "", "label": "todas"}] + [{"value": c[0], "label": c[0]} for c in cargos],
            },
        ],
    }


async def _tela_ficha(db, out: dict) -> None:
    rows = (
        await db.execute(
            text(
                "SELECT id::text, nome FROM employees WHERE coalesce(status,'') NOT IN ('candidato','pj_ativo','pj_inativo') AND coalesce(is_homologacao,false) = false ORDER BY nome"
            )
        )
    ).fetchall()
    out["ferias-pessoa"] = {
        "title": "Ficha de férias por pessoa",
        "sub": "Saldo (mesma conta do MCP `saldo_ferias`), posição no mapa do art. 133, períodos aquisitivos gravados, cada gozo com aviso, "
        "conta a pagar, cobertura e recibo, e os avisos na fila de assinatura. Só leitura.",
        "cta": "Abrir ficha",
        "type": "form",
        "submit": {"endpoint": _ACT + "ferias-pessoa", "okMsg": "Ficha aberta.", "showResult": True},
        "fields": [
            {
                "key": "employee_id",
                "label": "Colaborador*",
                "type": "select",
                "span": "span 2",
                "ph": "Selecione",
                "options": [{"value": r[0], "label": r[1]} for r in rows],
            }
        ],
    }


async def telas(db: AsyncSession, out: dict) -> None:
    await fd.ensure(db)
    for fn in (_tela_ferias, _tela_aviso_lote, _tela_ficha):
        try:
            await fn(db, out)
        except Exception as exc:  # noqa: BLE001 — uma tela quebrada não derruba o módulo
            await db.rollback()
            import logging

            logging.getLogger(__name__).warning("dgx u2 %s: %s", fn.__name__, exc)


async def mapa_descobertos(db: AsyncSession, out: dict) -> None:
    """Painel «postos descobertos» no `mapa-ferias` (frente 08) — férias aprovadas sem cobertura."""
    scr = out.get("mapa-ferias")
    if not isinstance(scr, dict) or scr.get("type") != "table":
        return
    try:
        desc = await fd.descobertos(db)
    except Exception:  # noqa: BLE001
        await db.rollback()
        return
    rows = [
        {
            "left": f"{d['nome']} — {d['posto']}",
            "right": f"{_fmtdate(d['inicio'])} a {_fmtdate(d['fim'])} ({d['dias']}d)",
            **S["warn"],
        }
        for d in desc
    ] or [{"left": "Toda férias aprovada em curso/futura tem cobertura registrada", "right": "0", **S["ok"]}]
    scr.setdefault("panels", []).append(
        {"title": f"Postos descobertos — férias aprovadas sem cobertura ({len(desc)})", "rows": rows}
    )


# ----------------------------------------------------------------------------- ações
def _msg_descoberto(f: dict, postos: list[tuple[str, str]]) -> str:
    onde = ", ".join(p[1] for p in postos) or "posto não identificado (sem turno no período nem posto atual)"
    return f"Posto {onde} ficará DESCOBERTO de {_fmtdate(f['inicio'])} a {_fmtdate(f['fim'])} — informe um substituto pela ação Cobertura da linha."


@router.post("/action/ferias-aprovar-u2", dependencies=[Depends(_gate_dp)])
async def rd_ferias_aprovar(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    vid: str | None = None,
) -> dict:
    """Aprova pelo caminho que já existia (`ferias-aprovar`: parede de escopo + `approve_vacation` + evento
    GEDEON) e, se veio substituto, registra a cobertura (F8 → F5). Sem substituto, diz o que fica descoberto."""
    from .departamento_pessoal import rd_action_ferias_aprovar

    vid = _uuid(vid or payload.get("vid"))
    r = await rd_action_ferias_aprovar(current_user, vid, db)
    f = await fd.carregar(db, vid)
    sub = str(payload.get("substituto_id") or "").strip()
    msg = f"Férias de {f['nome']} aprovadas ({_fmtdate(f['inicio'])} a {_fmtdate(f['fim'])})."
    if sub:
        try:
            c = await fd.registrar_cobertura(
                db,
                vid,
                sub,
                str(payload.get("posto_id") or "").strip() or None,
                None,
                getattr(current_user, "id", None),
                _unome(current_user),
            )
            msg += f" Cobertura registrada: {c['dias']} dia(s), {c['em_folga']} em folga trabalhada" + (
                " · movimentação F5 criada." if c.get("alocacao_id") else "."
            )
        except fd.FeriasErro as exc:
            msg += f" Cobertura NÃO registrada ({exc}). " + _msg_descoberto(
                f, await fd.postos_do_periodo(db, f["employee_id"], f["inicio"], f["fim"])
            )
    else:
        msg += " " + _msg_descoberto(f, await fd.postos_do_periodo(db, f["employee_id"], f["inicio"], f["fim"]))
    return {**(r if isinstance(r, dict) else {}), "ok": True, "message": msg}


@router.post("/action/ferias-cobertura", dependencies=[Depends(_gate_dp)])
async def rd_ferias_cobertura(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    vid: str | None = None,
) -> dict:
    vid = _uuid(vid or payload.get("vid"))
    try:
        c = await fd.registrar_cobertura(
            db,
            vid,
            str(payload.get("substituto_id") or "").strip(),
            str(payload.get("posto_id") or "").strip() or None,
            str(payload.get("observacao") or "").strip() or None,
            getattr(current_user, "id", None),
            _unome(current_user),
        )
    except fd.FeriasErro as exc:
        raise _erro(exc) from exc
    return {
        "ok": True,
        "message": f"Cobertura registrada: {c['dias']} dia(s), {c['em_folga']} em folga trabalhada, {c['horas']:.1f} h."
        + (" Movimentação (F5) criada." if c.get("alocacao_id") else ""),
        **c,
    }


@router.post("/action/ferias-gerar-conta", dependencies=[Depends(_gate_dp)])
async def rd_ferias_gerar_conta(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    vid: str | None = None,
) -> dict:
    vid = _uuid(vid or payload.get("vid"))
    try:
        r = await fd.gerar_conta(db, vid, getattr(current_user, "id", None))
    except fd.FeriasErro as exc:
        raise _erro(exc) from exc
    return {
        "ok": True,
        "message": f"Conta a pagar de {brl(r['valor'])} para {r['nome']}, vencendo {_fmtdate(r['vencimento'])} (art. 145) — "
        f"PIX {r['pix'] or 'sem chave cadastrada'}. Não paga: siga pelo Financeiro → Pagar.",
        "payable_id": r["payable_id"],
    }


@router.post("/action/aviso-ferias-lote", dependencies=[Depends(_gate_dp)])
async def rd_aviso_ferias_lote(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    mes = str(payload.get("mes") or "").strip()
    if len(mes) != 7 or mes[4] != "-":
        raise HTTPException(status_code=422, detail="Selecione o mês de gozo.")
    cliente, cargo = (
        (str(payload.get("cliente") or "").strip() or None),
        (str(payload.get("cargo") or "").strip() or None),
    )
    ids = await fd.ids_do_mes(db, mes, cliente, cargo)
    if not ids:
        raise HTTPException(status_code=400, detail=f"Nenhuma férias aprovada com início em {_mes_br(mes)} no filtro.")
    enfileirados = 0
    if str(payload.get("assinatura") or "").lower() in ("sim", "true", "1"):
        for vid in ids:
            r = await fd.enfileirar_aviso(db, vid, await fd.pdf_aviso(db, vid), getattr(current_user, "id", None))
            enfileirados += 1 if r else 0
    from urllib.parse import urlencode

    q = urlencode({k: v for k, v in (("mes", mes), ("cliente", cliente), ("cargo", cargo)) if v})
    return {
        "ok": True,
        "message": f"{len(ids)} aviso(s) de férias de {_mes_br(mes)}"
        + (f" · {enfileirados} pedido(s) de assinatura garantido(s)." if enfileirados else "."),
        "doc": {
            "label": f"Avisos de férias {_mes_br(mes)}",
            "url": f"/api/v1/redesign/ferias/aviso-lote/pdf?{q}",
            "fmt": "pdf",
            "mode": "blob",
        },
    }


@router.post("/action/ferias-pessoa", dependencies=[Depends(_gate_dp)])
async def rd_ferias_pessoa(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    try:
        sec = await fd.ficha(db, _uuid(payload.get("employee_id"), "Selecione o colaborador."))
    except fd.FeriasErro as exc:
        raise _erro(exc) from exc
    return {"ok": True, "message": f"Ficha de férias de {sec['saldo'].get('colaborador', '—')}.", **sec}


# ----------------------------------------------------------------------------- PDFs (GET, padrão do redesign)
def _pdf(conteudo: bytes, nome: str) -> Response:
    return Response(
        content=conteudo,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nome}"', "Cache-Control": "no-store"},
    )


@router.get("/ferias/aviso-lote/pdf", summary="Avisos de férias do mês em UM PDF (padrão-ouro)")
async def rd_aviso_lote_pdf(
    mes: str,
    current_user: CurrentActiveUser,
    cliente: str | None = None,
    cargo: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    try:
        return _pdf(
            await fd.pdf_aviso_lote(db, await fd.ids_do_mes(db, mes, cliente or None, cargo or None)),
            f"avisos-ferias-{mes}.pdf",
        )
    except fd.FeriasErro as exc:
        raise _erro(exc) from exc


async def dono_da_ferias(db: AsyncSession, vid: str) -> str | None:
    """De quem é esta férias. Usado pela parede self-only do portal (Y5)."""
    row = (
        await db.execute(
            text("SELECT employee_id::text FROM hr_vacation_requests WHERE id = CAST(:v AS uuid)"),
            {"v": vid},
        )
    ).first()
    return row[0] if row else None


@router.get("/ferias/{vid}/recibo/pdf", summary="Recibo de férias (padrão-ouro, mesmos números da calculadora)")
async def rd_recibo_pdf(vid: str, current_user: CurrentActiveUser, db: AsyncSession = Depends(get_db)):
    vid = _uuid(vid)
    exigir_dono(current_user, await dono_da_ferias(db, vid))  # y5: recibo de terceiro era 200 %PDF
    try:
        return _pdf(await fd.pdf_recibo(db, vid), f"recibo-ferias-{vid[:8]}.pdf")
    except fd.FeriasErro as exc:
        raise _erro(exc) from exc


@router.get("/ferias/{vid}/aviso/pdf", summary="Aviso de férias individual (padrão-ouro)")
async def rd_aviso_pdf(vid: str, current_user: CurrentActiveUser, db: AsyncSession = Depends(get_db)):
    vid = _uuid(vid)
    exigir_dono(current_user, await dono_da_ferias(db, vid))  # y5: aviso de terceiro era 200 %PDF
    try:
        return _pdf(await fd.pdf_aviso(db, vid), f"aviso-ferias-{vid[:8]}.pdf")
    except fd.FeriasErro as exc:
        raise _erro(exc) from exc
