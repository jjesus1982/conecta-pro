"""DGX U1 — Movimentação em dois passos + Supervisão planejada (24/09/2026). Regra em
`operacional/services/movimentacao_service.py` (pedir/aprovar/recusar) e
`operacional/services/supervisao_planejada.py`; aqui só se pinta e se despacha. Prefixo `_` = o
discovery pula; `operacional.py` importa `router` no topo e chama `telas(db, out)` antes de
`montar_grupos` (abas no FIM de g-postos, `_op_grupos`).

Telas (deep-link `/redesign/operacional?t=<id>`):
  g-postos · supervisao-planos · supervisao-plano-novo · supervisao-mapa · supervisao-hoje
A tela `movimentacoes` (F5) ganha as linhas pendentes/recusadas por `linhas_pedidos()` e a Central
de Aprovações ganha as pendentes por `linhas_central()` — UMA fonte (`op_movimentacao_pedidos`).
"""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.auth.module_scope import user_has_module
from core.database import get_db
from modules.operacional.services import movimentacao_service as ms
from modules.operacional.services import supervisao_planejada as sp

logger = logging.getLogger(__name__)
_ND = "#0F1B3A"
_END = "/api/v1/redesign/action/"

SQL_PEDIDOS = """
SELECT r.id::text, r.data_inicio, r.status, e.nome, c.nome, p.name, r.funcao, r.motivo, cb.nome, r.solicitado_por,
       r.solicitante_nome, coalesce(u.name, u.email), r.pedido_em, r.decisao_motivo, coalesce(du.name, du.email), r.decidido_em,
       (SELECT concat_ws(' · ', c2.nome, a.funcao) FROM employee_alocacoes a JOIN condominios c2 ON c2.id = a.condominio_id
         WHERE a.employee_id = r.employee_id AND a.ativo ORDER BY a.data_inicio DESC LIMIT 1)
FROM op_movimentacao_pedidos r
LEFT JOIN employees e ON e.id = r.employee_id
LEFT JOIN condominios c ON c.id = r.condominio_id
LEFT JOIN posts p ON p.id = r.posto_id
LEFT JOIN employees cb ON cb.id = r.coberto_employee_id
LEFT JOIN users u ON u.id = r.pedido_por
LEFT JOIN users du ON du.id = r.decidido_por
WHERE r.status = 'pendente' OR r.decidido_em >= (now() AT TIME ZONE 'America/Manaus') - interval '90 days'
ORDER BY (r.status = 'pendente') DESC, r.pedido_em DESC
"""
SQL_SUPERVISORES = """
SELECT e.id::text, e.nome FROM employees e
WHERE e.status IN ('ativo','pj_ativo') AND (
  upper(coalesce(e.cargo,'')) LIKE '%GERENTE%' OR upper(coalesce(e.cargo,'')) LIKE '%SUPERVIS%'
  OR e.id IN (SELECT employee_id FROM users WHERE is_active AND role IN ('admin','gerente_operacional') AND employee_id IS NOT NULL))
ORDER BY e.nome
"""
# ⚠️ 28/09/2026 — era `JOIN condominios` (INNER) e sumia com 6 dos 15 postos ATIVOS: os 5 do
# Conecta Village e o Conecta Base, cujo cliente não tem linha em `condominios`. Eram exatamente
# os postos da própria casa — o Orlailson não conseguia criar plano de supervisão para eles e a
# tela não dizia por quê (o select simplesmente não os oferecia). LEFT JOIN com o nome do cliente
# como rótulo de fallback: 9 → 15 opções. As demais consultas desta tela já usavam LEFT JOIN por
# `pl.posto_id`, então o plano criado aqui aparece na listagem e no mapa sem mais nenhuma mudança.
SQL_POSTOS = (
    "SELECT p.id::text, coalesce(c.nome, cl.name, '(sem condomínio)'), p.name FROM posts p "
    "LEFT JOIN clients cl ON cl.id = p.client_id "
    "LEFT JOIN condominios c ON c.client_id = p.client_id "
    "WHERE p.is_active ORDER BY 2, 3"
)
SQL_CONDS = "SELECT id::text, nome FROM condominios WHERE ativo ORDER BY nome"
SQL_MODELOS = (
    "SELECT id::text, codigo || ' — ' || nome FROM checklist_templates WHERE coalesce(is_ativo,true) "
    "AND categoria_equipamento IN ('posto','veiculo','ronda','supervisao') ORDER BY coalesce(is_padrao,false) DESC, nome"
)
SQL_PLANOS = """
SELECT pl.id::text, p.name, c.nome, e.nome, t.codigo, pl.frequencia, pl.dias_semana::text, pl.hora_inicio::text, pl.hora_fim::text,
       pl.vigencia_inicio, pl.vigencia_fim, pl.ativo,
       (SELECT count(*) FROM op_supervisao_ocorrencias o WHERE o.plano_id = pl.id AND date_trunc('month', o.data) = date_trunc('month', CAST(:h AS date))),
       (SELECT count(*) FROM op_supervisao_ocorrencias o WHERE o.plano_id = pl.id AND date_trunc('month', o.data) = date_trunc('month', CAST(:h AS date)) AND o.status = 'realizada')
FROM op_supervisao_planos pl
LEFT JOIN posts p ON p.id = pl.posto_id LEFT JOIN condominios c ON c.id = pl.condominio_id
LEFT JOIN employees e ON e.id = pl.supervisor_employee_id LEFT JOIN checklist_templates t ON t.id = pl.checklist_template_id
ORDER BY pl.ativo DESC, coalesce(p.name, c.nome), e.nome
"""
SQL_MAPA = """
SELECT to_char(o.data, 'MM/YYYY'), coalesce(p.name, c.nome), e.nome, count(*),
       count(*) FILTER (WHERE o.status = 'realizada'), count(*) FILTER (WHERE o.status = 'atrasada'),
       count(*) FILTER (WHERE o.status = 'nao_realizada'), count(*) FILTER (WHERE o.status = 'planejada'), min(o.data)
FROM op_supervisao_ocorrencias o JOIN op_supervisao_planos pl ON pl.id = o.plano_id
LEFT JOIN posts p ON p.id = pl.posto_id LEFT JOIN condominios c ON c.id = pl.condominio_id
LEFT JOIN employees e ON e.id = pl.supervisor_employee_id
WHERE o.data >= (date_trunc('month', CAST(:h AS date)) - interval '2 months')::date
GROUP BY 1, 2, 3 ORDER BY 9 DESC, 2, 3
"""
SQL_DIAS = """
SELECT coalesce(p.name, c.nome), o.data, o.status
FROM op_supervisao_ocorrencias o JOIN op_supervisao_planos pl ON pl.id = o.plano_id
LEFT JOIN posts p ON p.id = pl.posto_id LEFT JOIN condominios c ON c.id = pl.condominio_id
WHERE date_trunc('month', o.data) = date_trunc('month', CAST(:h AS date)) ORDER BY 1, 2
"""
SQL_HOJE = """
SELECT e.nome, coalesce(p.name, c.nome), pl.hora_inicio::text, pl.hora_fim::text, t.codigo, o.status, o.realizada_em,
       o.checklist_preenchido_id IS NOT NULL, o.checkin_visita_id IS NOT NULL
FROM op_supervisao_ocorrencias o JOIN op_supervisao_planos pl ON pl.id = o.plano_id
LEFT JOIN posts p ON p.id = pl.posto_id LEFT JOIN condominios c ON c.id = pl.condominio_id
LEFT JOIN employees e ON e.id = pl.supervisor_employee_id LEFT JOIN checklist_templates t ON t.id = pl.checklist_template_id
WHERE o.data = CAST(:h AS date) ORDER BY e.nome, pl.hora_inicio NULLS LAST, 2
"""
_MARCA = {"realizada": "✓", "atrasada": "⏱", "nao_realizada": "✗", "planejada": "·"}
_BADGE = {"realizada": "ok", "atrasada": "warn", "nao_realizada": "bad", "planejada": "info"}


def _d(v) -> str:
    return v.strftime("%d/%m/%Y") if v else "—"


def _dh(v) -> str:
    return v.strftime("%d/%m %H:%M") if v else "—"


def _opts(rows, label, vazio="— escolha —") -> list[dict]:
    return [{"value": "", "label": vazio}] + [{"value": r[0], "label": label(r)} for r in rows]


def e_dp(user) -> bool:
    """Quem aloca direto e quem aprova: `module:dp` ou admin (mesma régua do reembolso no redesign)."""
    return user_has_module(user, "dp")


def _falhou(out: dict, tid: str, titulo: str, exc: Exception) -> None:
    from modules.operacional.controllers.redesign_data_controller import t

    out[tid] = {
        "title": f"{titulo} — FALHOU",
        "sub": f"{type(exc).__name__}: {str(exc)[:300]}",
        "cta": "—",
        "type": "table",
        "searchHint": "",
        "grid": "1fr",
        "cols": ["Erro"],
        "rows": [{"cells": [t("A tela não conseguiu ler as fontes. O erro está no log do backend.", 500, "#B91C1C")]}],
    }


def _acoes_pedido(pid: str, quem: str, para: str) -> list[dict]:
    return [
        {
            "title": f"APROVAR a movimentação de {quem} para {para}",
            "endpoint": f"{_END}movimentacao-aprovar?pedido_id={pid}",
            "method": "POST",
            "btnLabel": "Aprovar",
            "submitLabel": "Aprovar",
            "btnStyle": "primary",
            "okMsg": "Aprovado: alocação criada e a anterior encerrada no dia anterior. Recarregue a tela.",
            "fields": [],
        },
        {
            "title": f"RECUSAR a movimentação de {quem} para {para}",
            "endpoint": f"{_END}movimentacao-recusar?pedido_id={pid}",
            "method": "POST",
            "btnLabel": "Recusar",
            "submitLabel": "Recusar",
            "btnStyle": "danger",
            "okMsg": "Pedido recusado. Nada mudou na alocação.",
            # `ms.recusar` exige 3+ caracteres (400) — o `*` diz isso antes do envio
            "fields": [{"key": "motivo", "label": "Por quê?*", "type": "text"}],
        },
    ]


async def linhas_pedidos(db) -> list[dict]:
    """Linhas pendentes/recusadas para o ledger `movimentacoes` (F5) — mesmas 9 colunas."""
    from modules.operacional.controllers.redesign_data_controller import b, initials, t

    await ms._ensure(db)
    out = []
    for r in (await db.execute(text(SQL_PEDIDOS))).fetchall():
        (
            pid,
            ini,
            status,
            nome,
            cond,
            posto,
            funcao,
            motivo,
            coberto,
            sol,
            sol_nome,
            pediu,
            pedido_em,
            dec_mot,
            dec,
            dec_em,
            de,
        ) = r
        para = " · ".join(x for x in (cond, posto, funcao) if x) or "—"
        quem = (ms.SOLICITANTES.get(sol or "", sol or "—")) + (f" ({sol_nome})" if sol_nome else "")
        if status == "pendente":
            sit = b("pendente", "warn")
            aprov = f"aguarda DP · pedido por {pediu or '—'} {_dh(pedido_em)}"
        else:
            sit = b(f"recusada {_d(dec_em)}", "bad")
            aprov = f"{dec or '—'}: {dec_mot or '—'}"
        out.append(
            {
                "cells": [
                    t(_d(ini), 600),
                    b("Pedido", "info"),
                    t(nome or "—", 600, _ND, initials(nome or "")),
                    t(f"{de or '—'} → {para}"),
                    t(ms.MOTIVOS.get(motivo or "", motivo or "—")),
                    t(coberto or "—"),
                    t(quem),
                    t(aprov),
                    sit,
                ],
                "filtros": {"mes": f"{ini:%m/%Y}" if ini else "—", "condominio": cond or "—", "status": status},
                "actions": _acoes_pedido(pid, nome or "—", para) if status == "pendente" else [],
            }
        )
    return out


async def linhas_central(db) -> list[dict]:
    """Pendentes na Central de Aprovações (6 colunas: Área · Tipo · Descrição · Risco · Solicitado por · Criado)."""
    await ms._ensure(db)
    out = []
    for r in (await db.execute(text(SQL_PEDIDOS))).fetchall():
        if r[2] != "pendente":
            continue
        pid, ini, _s, nome, cond, posto, funcao, motivo, _cb, sol, sol_nome, pediu, pedido_em, *_rest, de = r
        para = " · ".join(x for x in (cond, posto, funcao) if x) or "—"
        desc = f"{nome} · {de or 'sem vaga'} → {para} em {_d(ini)} · {ms.MOTIVOS.get(motivo or '', motivo or '')}"
        quem = (
            (ms.SOLICITANTES.get(sol or "", sol or ""))
            + (f" {sol_nome}" if sol_nome else "")
            + (f" · {pediu}" if pediu else "")
        )
        out.append(
            {
                "cells": [
                    {"isText": True, "v": "Operacional", "w": 600, "tc": _ND, "ini": ""},
                    {"isText": True, "v": "Movimentação", "w": 600, "tc": _ND, "ini": ""},
                    {"isText": True, "v": desc[:120], "w": 500, "tc": "#334155", "ini": ""},
                    {"isBadge": True, "v": "Médio", "color": "#B45309", "bg": "#FFFBEB"},
                    {"isText": True, "v": quem or "—", "w": 500, "tc": "#334155", "ini": ""},
                    {"isText": True, "v": _dh(pedido_em), "w": 500, "tc": "#64748B", "ini": ""},
                ],
                "actions": _acoes_pedido(pid, nome or "—", para),
            }
        )
    return out


async def telas(db, out: dict) -> None:
    from modules.operacional.controllers.redesign_data_controller import b, initials, t

    hoje = sp.hoje_manaus()
    try:
        await sp.gerar_ocorrencias(db, hoje)
        planos = (await db.execute(text(SQL_PLANOS), {"h": hoje})).fetchall()
        mapa = (await db.execute(text(SQL_MAPA), {"h": hoje})).fetchall()
        dias = (await db.execute(text(SQL_DIAS), {"h": hoje})).fetchall()
        hoje_rows = (await db.execute(text(SQL_HOJE), {"h": hoje})).fetchall()
        sups = (await db.execute(text(SQL_SUPERVISORES))).fetchall()
        postos = (await db.execute(text(SQL_POSTOS))).fetchall()
        conds = (await db.execute(text(SQL_CONDS))).fetchall()
        modelos = (await db.execute(text(SQL_MODELOS))).fetchall()
    except Exception as exc:  # noqa: BLE001 — visível, nunca calado
        await db.rollback()
        logger.error("dgx u1: supervisão planejada falhou: %s", exc, exc_info=True)
        for tid, tit in (
            ("supervisao-planos", "Planos de supervisão"),
            ("supervisao-mapa", "Mapa realizado × planejado"),
            ("supervisao-hoje", "Supervisão de hoje"),
        ):
            _falhou(out, tid, tit, exc)
        return

    def _dias_txt(js: str) -> str:
        import json

        try:
            return ", ".join(sp.DIAS_SEMANA.get(int(x), str(x)) for x in json.loads(js or "[]")) or "—"
        except (ValueError, TypeError):
            return js or "—"

    linhas = []
    for r in planos:
        pid, posto, cond, sup, chk, freq, ds, hi, hf, vi, vf, ativo, plan_mes, real_mes = r
        onde = posto or cond or "—"
        linhas.append(
            {
                "cells": [
                    t(onde, 600, _ND),
                    t(sup or "—", 600, _ND, initials(sup or "")),
                    t(chk or "—"),
                    t(sp.FREQUENCIAS.get(freq, freq) + ("" if freq in ("diaria", "mensal") else f" ({_dias_txt(ds)})")),
                    t(f"{(hi or '—')[:5]}–{(hf or '—')[:5]}" if (hi or hf) else "—"),
                    t(f"{_d(vi)} → {_d(vf) if vf else 'sem fim'}"),
                    t(f"{real_mes} / {plan_mes}"),
                    b("ativo", "ok") if ativo else b("inativo", "mut"),
                ],
                "filtros": {"supervisor": sup or "—", "situacao": "ativo" if ativo else "inativo"},
                "actions": [
                    {
                        "title": ("DESATIVAR" if ativo else "REATIVAR") + f" o plano de {sup} em {onde}",
                        "endpoint": f"{_END}supervisao-plano-toggle?plano_id={pid}&ativo={'0' if ativo else '1'}",
                        "method": "POST",
                        "btnLabel": "Desativar" if ativo else "Reativar",
                        "submitLabel": "Confirmar",
                        "btnStyle": "danger" if ativo else "primary",
                        "okMsg": "Plano atualizado. Recarregue a tela.",
                        "fields": [],
                    }
                ],
            }
        )
    out["supervisao-planos"] = {
        "title": "Planos de supervisão — quem vai onde, com que frequência",
        "sub": (
            f"{sum(1 for r in planos if r[11])} plano(s) ativo(s) · a coluna Mês é realizadas / planejadas em {hoje:%m/%Y} · "
            "checklist executado ou check-in do gerente no posto fecha o dia"
        ),
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar posto ou supervisor…",
        "grid": "1.4fr 1.4fr 1fr 1.3fr 0.8fr 1.3fr 0.7fr 0.7fr",
        "cols": [
            "Posto / condomínio",
            "Supervisor",
            "Checklist",
            "Frequência",
            "Horário",
            "Vigência",
            "Mês",
            "Situação",
        ],
        "filtros": [{"key": "supervisor", "label": "Supervisor"}, {"key": "situacao", "label": "Situação"}],
        "rows": linhas
        or [{"cells": [t("Nenhum plano ainda — crie em 'Novo plano de supervisão'", 500)] + [t("—")] * 7}],
    }

    out["supervisao-plano-novo"] = {
        "title": "Novo plano de supervisão",
        "cta": "Criar plano",
        "sub": (
            "Posto OU condomínio (um dos dois). Semanal/quinzenal exigem os dias da semana; mensal repete o dia do mês da vigência. "
            "As ocorrências nascem por dia (hoje na hora, os próximos à 00:30 ou ao abrir o mapa)."
        ),
        "type": "form",
        "submit": {"endpoint": _END + "supervisao-plano-criar", "okMsg": "Plano criado.", "showResult": True},
        "fields": [
            {
                "key": "supervisor_employee_id",
                "label": "Supervisor*",
                "type": "select",
                "span": "span 2",
                "options": _opts(sups, lambda r: r[1].title(), "— supervisor / gerente —"),
            },
            {
                "key": "posto_id",
                "label": "Posto",
                "type": "select",
                "options": _opts(postos, lambda r: f"{r[1]} · {r[2]}", "— posto —"),
            },
            {
                "key": "condominio_id",
                "label": "ou Condomínio inteiro",
                "type": "select",
                "options": _opts(conds, lambda r: r[1], "— condomínio —"),
            },
            {
                "key": "checklist_template_id",
                "label": "Checklist",
                "type": "select",
                "options": _opts(modelos, lambda r: r[1], "— sem checklist fixo —"),
            },
            {
                "key": "frequencia",
                "label": "Frequência*",
                "type": "select",
                "options": [{"value": k, "label": v} for k, v in sp.FREQUENCIAS.items()],
            },
            {
                "key": "dias_semana",
                "label": "Dias da semana (semanal/quinzenal)",
                "type": "multiselect",
                "span": "span 2",
                "options": [{"value": str(k), "label": v} for k, v in sp.DIAS_SEMANA.items()],
            },
            {"key": "hora_inicio", "label": "Hora início (HH:MM)", "type": "text", "ph": "08:00"},
            {"key": "hora_fim", "label": "Hora fim (HH:MM)", "type": "text", "ph": "12:00"},
            {"key": "vigencia_inicio", "label": "Vigência início*", "type": "date", "value": hoje.isoformat()},
            {"key": "vigencia_fim", "label": "Vigência fim", "type": "date"},
            {"key": "observacao", "label": "Observação", "type": "textarea", "span": "span 2"},
        ],
    }

    # mapa: mês × posto (linhas) + dia a dia do mês atual (painéis)
    linhas = []
    for mes, onde, sup, tot, real, atr, nao, plan, _min in mapa:
        pct = round(100.0 * real / tot, 1) if tot else 0.0
        linhas.append(
            {
                "cells": [
                    t(mes, 600),
                    t(onde or "—", 600, _ND),
                    t(sup or "—"),
                    t(str(tot)),
                    t(str(real), 600, "#16A34A"),
                    t(str(atr), 600, "#B45309" if atr else "#64748B"),
                    t(str(nao), 600, "#B91C1C" if nao else "#64748B"),
                    t(str(plan)),
                    b(f"{pct:.0f}%", "ok" if pct >= 90 else ("warn" if pct >= 60 else "bad")),
                ],
                "filtros": {"mes": mes, "posto": onde or "—"},
            }
        )
    por_posto: dict[str, list] = {}
    for onde, dia, status in dias:
        por_posto.setdefault(onde or "—", []).append(f"{dia:%d}{_MARCA.get(status, '?')}")
    out["supervisao-mapa"] = {
        "title": "Supervisão — realizado × planejado",
        "sub": (
            f"Por mês e posto (3 meses). Painéis: dia a dia de {hoje:%m/%Y} · ✓ realizada · ⏱ atrasada (hoje, passou da hora) · "
            "✗ não realizada · · planejada"
        ),
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar posto ou supervisor…",
        "grid": "0.7fr 1.5fr 1.4fr 0.6fr 0.6fr 0.6fr 0.6fr 0.6fr 0.6fr",
        "cols": [
            "Mês",
            "Posto / condomínio",
            "Supervisor",
            "Planejadas",
            "Realizadas",
            "Atrasadas",
            "Não realiz.",
            "A vencer",
            "%",
        ],
        "filtros": [{"key": "mes", "label": "Mês"}, {"key": "posto", "label": "Posto"}],
        "rows": linhas or [{"cells": [t("Sem ocorrências ainda — crie um plano", 500)] + [t("—")] * 8}],
        "panelGrid": "1fr 1fr",
        "panels": [
            {
                "title": f"{onde} — {hoje:%m/%Y}",
                "rows": [
                    {"left": " ".join(marcas), "right": f"{sum(1 for m in marcas if m.endswith('✓'))}/{len(marcas)}"}
                ],
            }
            for onde, marcas in por_posto.items()
        ]
        or [{"title": f"Dia a dia — {hoje:%m/%Y}", "rows": [{"left": "Sem ocorrências neste mês", "right": "—"}]}],
    }

    linhas = []
    for sup, onde, hi, hf, chk, status, real_em, via_chk, via_vis in hoje_rows:
        via = " + ".join(x for x, ok in (("checklist", via_chk), ("check-in", via_vis)) if ok)
        linhas.append(
            {
                "cells": [
                    t(sup or "—", 600, _ND, initials(sup or "")),
                    t(onde or "—", 600),
                    t(f"{(hi or '—')[:5]}–{(hf or '—')[:5]}" if (hi or hf) else "—"),
                    t(chk or "—"),
                    b(sp.STATUS.get(status, status), _BADGE.get(status, "mut")),
                    t(f"{_dh(real_em)}" + (f" via {via}" if via else "") if real_em else "—"),
                ],
                "filtros": {"supervisor": sup or "—", "status": sp.STATUS.get(status, status)},
            }
        )
    n_real = sum(1 for r in hoje_rows if r[5] == "realizada")
    out["supervisao-hoje"] = {
        "title": f"Supervisão de hoje — {hoje:%d/%m/%Y}",
        "sub": f"{n_real} de {len(hoje_rows)} realizada(s) · fecha sozinha com o checklist ou o check-in no posto",
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar supervisor ou posto…",
        "grid": "1.5fr 1.5fr 0.8fr 1fr 0.9fr 1.4fr",
        "cols": ["Supervisor", "Posto / condomínio", "Horário", "Checklist", "Status", "Realizada em"],
        "filtros": [{"key": "supervisor", "label": "Supervisor"}, {"key": "status", "label": "Status"}],
        "rows": linhas or [{"cells": [t("Nada planejado para hoje", 500)] + [t("—")] * 5}],
    }


# ───────────────────────── ações (POST /api/v1/redesign/action/…) ─────────────────────────
router = APIRouter()


def _require_dp(current_user: CurrentActiveUser) -> None:
    if not e_dp(current_user):
        raise HTTPException(status_code=403, detail="Aprovar ou recusar movimentação é restrito ao DP.")


@router.post("/action/movimentacao-aprovar", dependencies=[Depends(_require_dp)])
async def rd_movimentacao_aprovar(
    current_user: CurrentActiveUser,
    pedido_id: str,
    payload: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
) -> dict:
    uid = str(getattr(current_user, "id", "") or "") or None
    try:
        r = await ms.aprovar(db, pedido_id=pedido_id, user_id=uid)
    except ms.MovimentacaoErro as exc:
        await db.rollback()
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    from modules.operacional.publishers import publish_alocacao_criada

    try:
        emp = (
            await db.execute(
                text(
                    "SELECT employee_id::text, coalesce(posto_id, condominio_id)::text FROM op_movimentacao_pedidos WHERE id = CAST(:i AS uuid)"
                ),
                {"i": pedido_id},
            )
        ).fetchone()
        await publish_alocacao_criada(allocation_id=r["id"], employee_id=emp[0], post_id=emp[1])
    except Exception as exc:  # noqa: BLE001 — evento é aviso, não regra
        logger.warning("dgx u1: publish alocacao_criada falhou: %s", exc)
    enc = len(r["encerrou"])
    return {
        "ok": True,
        "message": f"Aprovado e alocado. {enc} alocação(ões) anterior(es) encerrada(s) no dia anterior."
        if enc
        else "Aprovado e alocado (não havia alocação anterior).",
        **r,
    }


@router.post("/action/movimentacao-recusar", dependencies=[Depends(_require_dp)])
async def rd_movimentacao_recusar(
    current_user: CurrentActiveUser,
    pedido_id: str,
    payload: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        r = await ms.recusar(
            db,
            pedido_id=pedido_id,
            motivo=str(payload.get("motivo") or ""),
            user_id=str(getattr(current_user, "id", "") or "") or None,
        )
    except ms.MovimentacaoErro as exc:
        await db.rollback()
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    return {"ok": True, "message": "Pedido recusado. A alocação atual não mudou.", **r}


@router.post("/action/supervisao-plano-criar")
async def rd_supervisao_plano_criar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    p = {k: (v if isinstance(v, list) else (str(v).strip() if v is not None else "")) for k, v in payload.items()}
    dias = p.get("dias_semana") or []
    if isinstance(dias, str):
        dias = [x for x in dias.replace("[", "").replace("]", "").replace('"', "").split(",") if x.strip()]
    try:
        r = await sp.criar_plano(
            db,
            supervisor_employee_id=p.get("supervisor_employee_id", ""),
            frequencia=p.get("frequencia", ""),
            posto_id=p.get("posto_id") or None,
            condominio_id=p.get("condominio_id") or None,
            checklist_template_id=p.get("checklist_template_id") or None,
            dias_semana=dias,
            hora_inicio=p.get("hora_inicio") or None,
            hora_fim=p.get("hora_fim") or None,
            vigencia_inicio=p.get("vigencia_inicio") or None,
            vigencia_fim=p.get("vigencia_fim") or None,
            observacao=p.get("observacao"),
            user_id=str(getattr(current_user, "id", "") or "") or None,
        )
    except sp.SupervisaoPlanejadaErro as exc:
        await db.rollback()
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    return {
        "ok": True,
        "message": f"Plano criado (vigência desde {date.fromisoformat(r['vigencia_inicio']):%d/%m/%Y}).",
        **r,
    }


@router.post("/action/supervisao-plano-toggle")
async def rd_supervisao_plano_toggle(
    current_user: CurrentActiveUser,
    plano_id: str,
    ativo: str = "1",
    payload: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        r = await sp.ativar_plano(db, plano_id=plano_id, ativo=ativo in ("1", "true", "sim"))
    except sp.SupervisaoPlanejadaErro as exc:
        await db.rollback()
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    return {
        "ok": True,
        "message": "Plano " + ("reativado." if r["ativo"] else "desativado (planejadas futuras removidas)."),
        **r,
    }
