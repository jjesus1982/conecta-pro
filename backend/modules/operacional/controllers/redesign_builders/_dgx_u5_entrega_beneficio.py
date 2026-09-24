"""DGX U5 — Entrega de benefício em lote com período de apuração (`/EntregasBeneficios`), 24/09/2026.

Telas (abas no FIM do grupo "Benefícios & Reembolsos" do DP): `beneficio-entregas` (lote a lote, com
Apurar / Aprovar / Arquivo / Conta por linha), `beneficio-entrega-nova` (form do DGX: benefício,
referência, previsão, entregas anteriores 1 e 2, apuração manual ou por apontamento com janela) e
`beneficio-entrega-itens` (pessoa a pessoa, filtro por entrega, com o acerto contra as anteriores).

Regra e DDL moram em `folha/services/beneficio_entregas.py`. Paralelo cego: nada aqui escreve em
folha/holerite; a conta a pagar nasce pelo PayableService e não é paga.
Prefixo `_` = o discovery pula; `departamento_pessoal.py` pluga `router` e `telas(db, out)` (# dgx u5).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.operacional.controllers.redesign_data_controller import _helpers, b, brl, t
from modules.people_management.folha.services import beneficio_entregas as be

_ND = "#0F1B3A"
_ACT = "/api/v1/redesign/action/"
_TONE_STATUS = {"rascunho": "mut", "apurada": "info", "aprovada": "ok", "enviada": "ok", "paga": "ok"}
_TONE_ITEM = {
    "ok": "ok",
    "manual": "info",
    "sem_anterior": "info",
    "anterior_sem_ponto": "warn",
    "janela_divergente": "warn",
    "cortado_faltas": "warn",
    "sem_modalidade": "warn",
    "sem_parametro": "bad",
    "sem_escala": "bad",
    "sem_regra": "bad",
}
_OPS = [
    {"value": "solides", "label": "Sólides (VA + mobilidade)"},
    {"value": "sinetram", "label": "SINETRAM (VT)"},
]


def _dt(d) -> str:
    return d.strftime("%d/%m/%Y") if d else "—"


def _n(v):
    return t("—" if v is None else str(v))


def _money(v, w=500):
    return t(brl(float(v)) if v is not None else "—", w)


async def telas(db, out: dict | None = None) -> dict:  # noqa: C901
    await be._ensure(db)
    mine, safe, tbl = _helpers(db)

    def _ent_row(r):
        (
            eid,
            ref,
            tipo,
            ben,
            pi,
            pf,
            modo,
            ai,
            af,
            a1,
            a2,
            status,
            definitiva,
            pessoas,
            total,
            arquivo,
            payable,
            aprovador,
            criador,
        ) = r
        apur = "manual" if modo == "manual" else f"apontamento {_dt(ai)}–{_dt(af)}"
        cells = [
            t(f"#{eid} · {ref}", 600, _ND),
            b(f"{tipo} ({ben})", "info"),
            t(f"{_dt(pi)} – {_dt(pf)}"),
            t(apur),
            t(" / ".join(f"#{a}" for a in (a1, a2) if a) or "—"),
            _n(pessoas),
            _money(total, 600),
            b(status, _TONE_STATUS.get(status, "mut")),
            b(
                "—" if definitiva is None else ("definitiva" if definitiva else "provisória"),
                "mut" if definitiva is None else ("ok" if definitiva else "warn"),
            ),
            t((arquivo or "—").rsplit("/", 1)[-1]),
            b(f"{payable[:8]}…" if payable else "—", "ok" if payable else "mut"),
            t(aprovador or criador or "—"),
        ]
        acoes = []
        if status in ("rascunho", "apurada"):
            acoes.append(
                {
                    "title": f"Apurar entrega #{eid} ({tipo} {ref}) — roda o motor nas janelas; reapurar substitui os itens",
                    "endpoint": f"{_ACT}beneficio-entrega-apurar?entrega_id={eid}",
                    "method": "POST",
                    "btnLabel": "Apurar",
                    "submitLabel": "Apurar agora",
                    "btnStyle": "primary",
                    "okMsg": "Apurada — veja a aba Itens da entrega.",
                    "fields": [],
                }
            )
        if status == "apurada":
            acoes.append(
                {
                    "title": f"APROVAR entrega #{eid} — trava os itens (não dá para reapurar depois)",
                    "endpoint": f"{_ACT}beneficio-entrega-aprovar?entrega_id={eid}",
                    "method": "POST",
                    "btnLabel": "Aprovar",
                    "submitLabel": "Aprovar",
                    "btnStyle": "outline",
                    "okMsg": "Aprovada. Agora: Arquivo do operador e Conta a pagar.",
                    "fields": [],
                }
            )
        if status in ("aprovada", "enviada", "paga"):
            acoes.append(
                {
                    "title": f"Arquivo do operador — entrega #{eid}",
                    "endpoint": f"{_ACT}beneficio-entrega-arquivo?entrega_id={eid}",
                    "method": "POST",
                    "btnLabel": "Arquivo",
                    "submitLabel": "Gerar arquivo",
                    "btnStyle": "outline",
                    "okMsg": "Arquivo gerado e guardado — o caminho aparece na linha.",
                    "fields": [
                        {
                            "key": "operadora",
                            "label": "Operadora*",
                            "type": "select",
                            "options": _OPS if ben == "VT" else _OPS[:1],
                            "value": "solides",
                        }
                    ],
                }
            )
        if status in ("aprovada", "enviada") and not payable:
            acoes.append(
                {
                    "title": f"Gerar CONTA A PAGAR da entrega #{eid} ({brl(float(total or 0))}) — cria o título, NÃO paga",
                    "endpoint": f"{_ACT}beneficio-entrega-conta?entrega_id={eid}",
                    "method": "POST",
                    "btnLabel": "Conta",
                    "submitLabel": "Criar título a pagar",
                    "btnStyle": "danger",
                    "gated": True,
                    "okMsg": "Título criado no Financeiro (contas a pagar). Nada foi pago.",
                    "fields": [],
                }
            )
        return {"cells": cells, "actions": acoes, "filtro": status}

    await safe(
        "beneficio-entregas",
        tbl(
            "Entregas de benefício (lote)",
            "Como no DGX: cada entrega tem benefício, referência, período previsto, apuração (manual ou pelo apontamento, com janela "
            "própria) e as entregas anteriores para o acerto. Fluxo: Apurar → Aprovar (trava) → Arquivo do operador → Conta a pagar. "
            "Paralelo cego: nada vai para a folha; a conta nasce no Financeiro e não é paga aqui.",
            "—",
            [
                "Entrega",
                "Benefício",
                "Previsão",
                "Apuração",
                "Anteriores",
                "Pessoas",
                "Total",
                "Status",
                "Apuração",
                "Arquivo",
                "Conta",
                "Por",
            ],
            "0.9fr 1fr 1.2fr 1.5fr 0.6fr 0.5fr 0.8fr 0.6fr 0.7fr 1.4fr 0.6fr 0.9fr",
            "SELECT e.id, e.referencia, t.nome, t.tipo_primitivo, e.previsao_inicio, e.previsao_fim, e.apuracao_modo, "
            " e.apuracao_inicio, e.apuracao_fim, e.entrega_anterior_id, e.entrega_anterior2_id, e.status, e.apuracao_definitiva, "
            " e.quantidade_pessoas, e.total, e.arquivo_operador_path, e.payable_id::text, e.aprovado_por, e.criado_por "
            "FROM beneficio_entregas e JOIN beneficio_tipos t ON t.id = e.beneficio_tipo_id ORDER BY e.id DESC LIMIT 300",
            lambda r: _ent_row(r)["cells"],
            hint="Buscar entrega…",
            actionsfn=lambda r: _ent_row(r)["actions"],
            filtrofn=lambda r: _ent_row(r)["filtro"],
        ),
    )
    if "beneficio-entregas" in mine:
        mine["beneficio-entregas"]["ctaTo"] = "beneficio-entrega-nova"
        mine["beneficio-entregas"]["cta"] = "Nova entrega"

    tipos = [
        {"value": str(r[0]), "label": f"{r[1]} ({r[2]})"}
        for r in (
            await db.execute(
                text(
                    "SELECT id, nome, tipo_primitivo FROM beneficio_tipos WHERE ativo AND tipo_primitivo IN ('VT','VR') ORDER BY tipo_primitivo"
                )
            )
        ).fetchall()
    ]
    anteriores = [{"value": "", "label": "Nenhuma"}] + [
        {"value": str(r[0]), "label": f"#{r[0]} · {r[1]} {r[2]} · {_dt(r[3])}–{_dt(r[4])} · {r[5]}"}
        for r in (
            await db.execute(
                text(
                    "SELECT e.id, t.tipo_primitivo, e.referencia, e.previsao_inicio, e.previsao_fim, e.status FROM beneficio_entregas e "
                    "JOIN beneficio_tipos t ON t.id = e.beneficio_tipo_id ORDER BY e.id DESC LIMIT 60"
                )
            )
        ).fetchall()
    ]
    mine["beneficio-entrega-nova"] = {
        "title": "Nova entrega de benefício",
        "type": "form",
        "cta": "Criar entrega",
        "sub": "Previsão = dias que a escala diz que a pessoa vai trabalhar no período. Apuração por apontamento = o ponto da janela "
        "corrige o que as entregas anteriores entregaram (a janela deve ter o mesmo nº de dias que as previsões anteriores). "
        "Manual = a previsão pura, e o DP ajusta pessoa a pessoa na aba Itens.",
        "submit": {
            "endpoint": f"{_ACT}beneficio-entrega-salvar",
            "okMsg": "Entrega criada como rascunho — clique Apurar na aba Entregas.",
            "showResult": True,
        },
        "fields": [
            {
                "key": "beneficio_tipo_id",
                "label": "Benefício*",
                "type": "select",
                "span": "span 1",
                "options": tipos,
                "ph": "Selecione",
            },
            {"key": "referencia", "label": "Referência (MM/AAAA)*", "type": "text", "span": "span 1", "ph": "10/2026"},
            {"key": "previsao_inicio", "label": "Início do período previsto*", "type": "date", "span": "span 1"},
            {"key": "previsao_fim", "label": "Fim do período previsto*", "type": "date", "span": "span 1"},
            {
                "key": "entrega_anterior_id",
                "label": "Entrega anterior 1",
                "type": "select",
                "span": "span 1",
                "options": anteriores,
            },
            {
                "key": "entrega_anterior2_id",
                "label": "Entrega anterior 2",
                "type": "select",
                "span": "span 1",
                "options": anteriores,
            },
            {
                "key": "apuracao_modo",
                "label": "Apuração*",
                "type": "select",
                "span": "span 1",
                "value": "apontamento",
                "options": [
                    {"value": "manual", "label": "Manual"},
                    {"value": "apontamento", "label": "Pelo apontamento (ponto)"},
                ],
            },
            {"key": "apuracao_inicio", "label": "Apuração — início", "type": "date", "span": "span 1"},
            {"key": "apuracao_fim", "label": "Apuração — fim", "type": "date", "span": "span 1"},
            {"key": "observacao", "label": "Observação", "type": "textarea", "span": "span 2"},
        ],
    }

    def _item_row(r):
        iid, ent, ref, ben, status, nome, op, plan, trab, rec, dire, aj, qtd, unit, total, estado, obs = r
        cells = [
            t(nome, 600, _ND),
            t(op or "—"),
            _n(plan),
            _n(trab),
            _n(rec),
            _n(dire),
            b("—" if aj is None else f"{aj:+d}", "ok" if not aj else ("warn" if abs(aj) <= 3 else "bad")),
            _n(qtd),
            _money(unit),
            _money(total, 600),
            b((estado or "—").replace("_", " "), _TONE_ITEM.get(estado, "mut")),
            t(obs or "—"),
        ]
        acoes = []
        if status in ("rascunho", "apurada") and unit is not None:
            acoes.append(
                {
                    "title": f"Corrigir quantidade — {nome} (entrega #{ent})",
                    "endpoint": f"{_ACT}beneficio-entrega-item-editar?item_id={iid}",
                    "method": "POST",
                    "btnLabel": "Quantidade",
                    "submitLabel": "Salvar",
                    "btnStyle": "outline",
                    "okMsg": "Item corrigido; total da entrega refeito.",
                    "fields": [
                        {
                            "key": "quantidade",
                            "label": "Quantidade (dias)*",
                            "type": "number",
                            "value": "" if qtd is None else str(qtd),
                        },
                        {"key": "observacao", "label": "Motivo", "type": "text", "value": ""},
                    ],
                }
            )
        return {"cells": cells, "actions": acoes, "filtro": f"#{ent} · {ben} {ref} · {status}"}

    await safe(
        "beneficio-entrega-itens",
        tbl(
            "Itens da entrega (pessoa a pessoa)",
            "Planejado = previsão do período · Trabalhado/Direito = ponto da janela de apuração · Receb.ant = Σ quantidade nas entregas "
            "anteriores · Ajuste = direito − recebido · Qtd = planejado + ajuste. Estados sem valor ficam fora do arquivo e da conta.",
            "—",
            [
                "Colaborador",
                "Oper.",
                "Plan.",
                "Trab.",
                "Receb.ant",
                "Direito",
                "Ajuste",
                "Qtd",
                "Unit.",
                "Total",
                "Estado",
                "Obs.",
            ],
            "1.8fr 0.6fr 0.4fr 0.4fr 0.6fr 0.5fr 0.5fr 0.4fr 0.6fr 0.8fr 1fr 2fr",
            "SELECT i.id, e.id, e.referencia, t.tipo_primitivo, e.status, emp.nome, i.operadora, i.planejado, i.trabalhado, "
            " i.recebido_anterior, i.direito, i.ajuste_ponto, i.quantidade, i.unitario, i.total, i.estado, i.observacao "
            "FROM beneficio_entrega_itens i JOIN beneficio_entregas e ON e.id = i.entrega_id "
            "JOIN beneficio_tipos t ON t.id = e.beneficio_tipo_id JOIN employees emp ON emp.id = i.employee_id "
            "ORDER BY e.id DESC, emp.nome LIMIT 2000",
            lambda r: _item_row(r)["cells"],
            hint="Buscar colaborador…",
            actionsfn=lambda r: _item_row(r)["actions"],
            filtrofn=lambda r: _item_row(r)["filtro"],
        ),
    )

    grupo = (out or {}).get("g-beneficios")
    if isinstance(grupo, dict) and isinstance(grupo.get("tabs"), list):
        from modules.operacional.controllers.redesign_data_controller import moved

        for tid, lbl in (
            ("beneficio-entregas", "Entregas (lote)"),
            ("beneficio-entrega-nova", "Nova entrega"),
            ("beneficio-entrega-itens", "Itens da entrega"),
        ):
            if tid in mine:
                grupo["tabs"].append({"id": tid, "label": lbl, "screen": mine[tid]})
                mine[tid] = moved("g-beneficios", tid)
    return mine


# ───────────────────────── ações ─────────────────────────
router = APIRouter()


def _quem(u) -> str:
    return str(getattr(u, "full_name", None) or getattr(u, "email", "") or "Conecta PRO")


async def _run(db, coro):
    try:
        return await coro
    except be.EntregaTravadaError as e:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/action/beneficio-entrega-salvar")
async def rd_entrega_salvar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    rid = await _run(db, be.criar(db, payload, _quem(current_user)))
    return {"ok": True, "message": f"Entrega #{rid} criada (rascunho). Clique Apurar na aba Entregas.", "id": rid}


@router.post("/action/beneficio-entrega-apurar")
async def rd_entrega_apurar(
    current_user: CurrentActiveUser,
    entrega_id: int,
    payload: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
) -> dict:
    r = await _run(db, be.apurar(db, entrega_id))
    return {
        "ok": True,
        "message": f"Entrega #{entrega_id} apurada: {r['pessoas']} pessoa(s) com valor de {r['linhas']}, total {brl(float(r['total']))}"
        + (" — apuração provisória (mês aberto)" if r["apuracao_definitiva"] is False else "")
        + ("" if r["acerto_feito"] or r["beneficio"] is None else " · sem acerto contra anteriores"),
        **{k: (float(v) if k == "total" else v) for k, v in r.items()},
    }


@router.post("/action/beneficio-entrega-aprovar")
async def rd_entrega_aprovar(
    current_user: CurrentActiveUser,
    entrega_id: int,
    payload: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
) -> dict:
    r = await _run(db, be.aprovar(db, entrega_id, _quem(current_user)))
    return {"ok": True, "message": f"Entrega #{entrega_id} aprovada — itens travados.", "total": float(r["total"])}


@router.post("/action/beneficio-entrega-arquivo")
async def rd_entrega_arquivo(
    current_user: CurrentActiveUser,
    entrega_id: int,
    payload: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
) -> dict:
    op = str(payload.get("operadora") or "solides")
    nome, texto, avisos = await _run(db, be.gerar_arquivo(db, entrega_id, op, _quem(current_user)))
    return {
        "ok": True,
        "message": f"{nome} gerado ({len(avisos)} aviso(s)). Layout oficial do portal a confirmar antes de subir.",
        "arquivo": nome,
        "avisos_detalhe": {f"aviso {i + 1}": a for i, a in enumerate(avisos[:20])},
        "conteudo": texto,
    }


@router.post("/action/beneficio-entrega-conta")
async def rd_entrega_conta(
    current_user: CurrentActiveUser,
    entrega_id: int,
    payload: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
) -> dict:
    uid = current_user.id if isinstance(current_user.id, UUID) else UUID(str(current_user.id))
    r = await _run(db, be.gerar_conta(db, entrega_id, uid))
    return {
        "ok": True,
        "message": ("Conta já existia (não duplicada)" if r["ja_existia"] else "Conta a pagar criada")
        + f" — {r['payable_id'][:8]}… · {brl(r['valor'])}. Nada foi pago.",
        **r,
    }


@router.post("/action/beneficio-entrega-item-editar")
async def rd_entrega_item_editar(
    current_user: CurrentActiveUser, item_id: int, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    r = await _run(db, be.editar_item(db, item_id, payload.get("quantidade"), payload.get("observacao")))
    return {"ok": True, "message": f"Item #{item_id}: quantidade {r['quantidade']} — total da entrega refeito.", **r}
