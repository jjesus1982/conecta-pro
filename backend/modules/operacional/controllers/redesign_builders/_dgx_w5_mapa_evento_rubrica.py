"""DGX W5 — o mapa evento do ponto → rubrica da folha, como CADASTRO (24/09/2026).

Tela `ponto-evento-rubrica` (g-folha): evento × rubrica × escopo × fórmula × origem, com Editar,
Inativar e o form `ponto-evento-rubrica-nova`. A coluna **«o motor usa?»** diz a verdade: hoje NÃO
— `calculo_service.py` segue com a regra em Python e este cadastro é a DECLARAÇÃO fiel dela,
provada linha a linha por `scripts/orq/test_oraculo_w5_mapa_evento_rubrica.py` (Σ|Δ| = R$ 0,00 nas
153 verbas de ponto de 08+09/2026). Mesma honestidade da F1.

Grupo: **g-folha**, ao lado de «Rubricas» (F1). É a folha que decide em que rubrica a ocorrência
vira dinheiro; o ponto só produz a ocorrência. Quem mexe nisto quando a CCT muda é o DP/folha.

Prefixo `_` = o discovery pula; `departamento_pessoal.py` importa `router` (topo) e chama
`telas(db, out)` ANTES de `montar_grupos` (as abas estão em `_dp_grupos.GRUPOS`, g-folha).
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

#: ANTES do import do data_controller (mesmo motivo da F1: o ciclo fecha com o router já definido)
router = APIRouter()

from modules.operacional.controllers.redesign_data_controller import _helpers, b, brl, t  # noqa: E402
from modules.people_management.folha.services.mapa_evento_rubrica import (  # noqa: E402
    BASES,
    ESCOPOS,
    EVENTOS,
    _ensure,
)

_ND = "#0F1B3A"
_ACT = "/api/v1/redesign/action/"

_SQL_LISTA = """
SELECT m.id, m.evento, m.rubrica_codigo, m.escopo, m.escopo_id, m.formula, m.base, m.percentual,
       m.ativo, m.vigencia_inicio, m.vigencia_fim, m.origem_regra,
       r.descricao AS rubrica_desc, r.tipo AS rubrica_tipo
  FROM ponto_evento_rubrica m
  LEFT JOIN rubricas_folha r ON r.codigo = m.rubrica_codigo
 ORDER BY m.ativo DESC, m.evento, m.escopo, m.id
"""

#: a competência mais recente do motor próprio — para medir o uso real de cada rubrica
_SQL_COMP = """
SELECT reference_year, reference_month FROM hr_payslips
 WHERE source_system = 'conecta' AND payslip_code NOT LIKE '13O-%'
   AND make_date(reference_year, reference_month, 1) <= date_trunc('month', now() AT TIME ZONE 'America/Manaus')
 ORDER BY 1 DESC, 2 DESC LIMIT 1
"""
_SQL_USO = """
SELECT e->>'codigo', count(*), round(sum((e->>'valor')::numeric), 2)
  FROM hr_payslips p, jsonb_array_elements(p.earnings || p.deductions) e
 WHERE p.source_system = 'conecta' AND p.reference_year = :a AND p.reference_month = :m
 GROUP BY 1
"""
_SQL_RUBRICAS = "SELECT codigo, descricao FROM rubricas_folha WHERE ativo ORDER BY codigo"


def _onde_vale(escopo: str, escopo_id: str, nomes: dict[str, str]) -> str:
    if escopo == "empresa":
        return "toda a empresa"
    return f"{escopo}: {nomes.get(str(escopo_id), escopo_id or '—')}"


def _campos(r: dict | None, rubricas: list[tuple[str, str]]) -> list[dict]:
    """Os campos do form (inclusão e edição). `r` preenchido = edição."""

    def g(k: str, d: str = "") -> str:
        return ("" if r is None else str(r.get(k) or "")) or d

    ops_ev = [
        {"value": ev, "label": f"{meta['rotulo']}" + ("" if meta["produzido"] else " (o motor não produz)")}
        for ev, meta in EVENTOS.items()
    ]
    ops_rub = [{"value": c, "label": f"{c} — {d}"} for c, d in rubricas]
    f = [
        {
            "key": "evento",
            "label": "Evento do ponto",
            "type": "select",
            "options": ops_ev,
            "span": 2,
            "value": g("evento"),
        },
        {
            "key": "rubrica_codigo",
            "label": "Rubrica da folha",
            "type": "select",
            "options": ops_rub,
            "span": 2,
            "value": g("rubrica_codigo"),
        },
        {
            "key": "escopo",
            "label": "Escopo",
            "type": "select",
            "options": [{"value": e, "label": e} for e in ESCOPOS],
            "value": g("escopo", "empresa"),
        },
        {
            "key": "escopo_id",
            "label": "Id do escopo (vazio = empresa)",
            "type": "text",
            "ph": "uuid do condomínio/colaborador, nome da função ou da escala",
            "value": g("escopo_id"),
        },
        {
            "key": "base",
            "label": "Base",
            "type": "select",
            "options": [{"value": x, "label": x.replace("_", " ")} for x in BASES],
            "value": g("base", "valor_hora"),
        },
        {
            "key": "percentual",
            "label": "Percentual / fator",
            "type": "number",
            "ph": "1,5 · 0,20",
            "value": (None if r is None or r.get("percentual") is None else f"{float(r['percentual']):g}"),
        },
        {
            "key": "formula",
            "label": "Fórmula (como se lê: horas × valor_hora × 1,5)",
            "type": "text",
            "span": 2,
            "ph": "arred(salario_base ÷ 30) × dias",
            "value": g("formula"),
        },
        {
            "key": "vigencia_inicio",
            "label": "Vigência — início",
            "type": "date",
            "value": (str(r["vigencia_inicio"]) if r and r.get("vigencia_inicio") else ""),
        },
        {
            "key": "vigencia_fim",
            "label": "Vigência — fim",
            "type": "date",
            "value": (str(r["vigencia_fim"]) if r and r.get("vigencia_fim") else ""),
        },
        {
            "key": "origem_regra",
            "label": "Origem da regra (obrigatória)",
            "type": "textarea",
            "span": 2,
            "ph": "cláusula da CCT, artigo da lei ou arquivo:linha do motor",
            "value": g("origem_regra"),
        },
    ]
    if r is not None:
        f.insert(0, {"key": "id", "type": "hidden", "label": "id", "value": str(r["id"])})
    return f


async def telas(db, out: dict | None = None) -> dict:
    await _ensure(db)
    mine, _safe, _tbl = _helpers(db)

    comp = (await db.execute(text(_SQL_COMP))).first()
    uso: dict[str, tuple[int, Decimal]] = {}
    if comp:
        for cod, n, soma in (await db.execute(text(_SQL_USO), {"a": comp[0], "m": comp[1]})).fetchall():
            uso[cod] = (int(n), soma)
    comp_txt = f"{int(comp[1]):02d}/{comp[0]}" if comp else "—"

    linhas = [dict(r) for r in (await db.execute(text(_SQL_LISTA))).mappings().all()]
    # nomes dos escopos que têm id (condomínio e colaborador); função/escala já são o próprio nome
    nomes: dict[str, str] = {}
    ids_cond = [r["escopo_id"] for r in linhas if r["escopo"] == "condominio" and r["escopo_id"]]
    ids_col = [r["escopo_id"] for r in linhas if r["escopo"] == "colaborador" and r["escopo_id"]]
    for sql, ids in (
        ("SELECT id::text, nome FROM condominios WHERE id::text = ANY(CAST(:v AS text[]))", ids_cond),
        ("SELECT id::text, nome FROM employees WHERE id::text = ANY(CAST(:v AS text[]))", ids_col),
    ):
        if ids:
            for _id, _n in (await db.execute(text(sql), {"v": ids})).fetchall():
                nomes[_id] = _n
    rubricas = [(c, d) for c, d in (await db.execute(text(_SQL_RUBRICAS))).fetchall()]

    def _linha(r: dict) -> dict:
        meta = EVENTOS.get(r["evento"], {"rotulo": r["evento"], "produzido": False})
        u = uso.get(r["rubrica_codigo"])
        # honestidade: o motor NÃO lê este cadastro. Diz isso, e diz se a rubrica saiu na folha.
        motor = b("não — declaração", "mut")
        motor_extra = f"emitida {u[0]}× ({brl(float(u[1]))}) em {comp_txt}" if u else "não emitida na competência"
        return {
            "cells": [
                t(meta["rotulo"], 700, _ND),
                t(f"{r['rubrica_codigo']} — {r['rubrica_desc'] or '(sem linha em rubricas_folha)'}", 600, _ND),
                t(_onde_vale(r["escopo"], r["escopo_id"], nomes)),
                t(r["formula"] or "—"),
                t(
                    (r["base"] or "—").replace("_", " ")
                    + (f" · {float(r['percentual']):g}" if r["percentual"] is not None else "")
                ),
                t((r["origem_regra"] or "—")[:150]),
                motor,
                t(motor_extra),
                b("ativa", "ok") if r["ativo"] else b("inativa", "mut"),
            ],
            "edit": {
                "title": f"Editar {meta['rotulo']} → {r['rubrica_codigo']}",
                "endpoint": _ACT + "evento-rubrica-salvar",
                "method": "POST",
                "okMsg": "Mapa salvo. Recarregue a tela.",
                "fields": _campos(r, rubricas),
            },
            "actions": [
                {
                    "title": ("Reativar" if not r["ativo"] else "Inativar")
                    + f" — {meta['rotulo']} → {r['rubrica_codigo']}",
                    "endpoint": _ACT + "evento-rubrica-inativar",
                    "method": "POST",
                    "btnLabel": "Reativar" if not r["ativo"] else "Inativar",
                    "submitLabel": "Confirmar",
                    "btnStyle": "outline" if r["ativo"] else "primary",
                    "okMsg": "Linha atualizada. Recarregue a tela.",
                    "fields": [{"key": "id", "type": "hidden", "label": "id", "value": str(r["id"])}],
                }
            ],
            "filtro": {"Estado": "ativas" if r["ativo"] else "inativas", "Escopo": r["escopo"]},
        }

    sem_caminho = [
        m["rotulo"] for e, m in EVENTOS.items() if not m["produzido"] and e not in {x["evento"] for x in linhas}
    ]
    n_at = sum(1 for r in linhas if r["ativo"])
    mine["ponto-evento-rubrica"] = {
        "title": "Mapa evento → rubrica (ponto → folha)",
        "sub": (
            f"{len(linhas)} linha(s) ({n_at} ativas) · qual ocorrência do ponto vira qual rubrica da folha, com a "
            f"fórmula e a origem de cada regra. **O motor de folha NÃO lê este cadastro**: `calculo_service.py` segue "
            f"com a regra em Python e isto é a declaração fiel dela — o oráculo `w5_mapa_evento_rubrica` prova ao "
            f"centavo (Σ|Δ| = R$ 0,00 nas verbas de ponto de 08 e 09/2026). Cascata: colaborador > escala > função > "
            f"condomínio > empresa."
            + (f" · Sem caminho nenhum aqui (o motor não os produz): {', '.join(sem_caminho)}." if sem_caminho else "")
        ),
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar evento, rubrica, fórmula…",
        "grid": "1.2fr 1.6fr 1fr 1.6fr 0.9fr 2fr 0.8fr 1.1fr 0.6fr",
        "cols": [
            "Evento",
            "Rubrica",
            "Onde vale",
            "Fórmula",
            "Base · fator",
            "Origem da regra",
            "O motor usa?",
            "Na folha",
            "Status",
        ],
        "rows": [_linha(r) for r in linhas],
    }
    mine["ponto-evento-rubrica-nova"] = {
        "title": "Nova linha do mapa",
        "sub": "Liga um evento do ponto a uma rubrica da folha, num escopo. Cadastrar aqui NÃO faz o motor calcular: "
        "a regra continua em calculo_service.py (paralelo cego). A origem da regra é obrigatória — quem ler daqui a "
        "um ano precisa saber de onde o número veio.",
        "cta": "Salvar linha",
        "type": "form",
        "submit": {
            "endpoint": _ACT + "evento-rubrica-salvar",
            "okMsg": "Linha cadastrada — veja a aba Mapa evento → rubrica.",
        },
        "fields": _campos(None, rubricas),
    }
    if out is not None:
        out.update(mine)
    return mine


# ── ações ────────────────────────────────────────────────────────────────────────────────────


def _enum(v, opts, rot: str) -> str:
    s = str(v or "").strip().lower()
    if s not in opts:
        raise HTTPException(status_code=400, detail=f"{rot}: use um de {', '.join(opts)}.")
    return s


def _data(v, rot: str):
    s = str(v or "").strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{rot}: use AAAA-MM-DD.") from None


@router.post("/action/evento-rubrica-salvar")
async def rd_evento_rubrica_salvar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    await _ensure(db)
    rid = str(payload.get("id") or "").strip()
    evento = _enum(payload.get("evento"), tuple(EVENTOS), "Evento")
    codigo = str(payload.get("rubrica_codigo") or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{1,10}", codigo):
        raise HTTPException(status_code=400, detail="Rubrica: 1 a 10 letras/dígitos (ex.: 0040).")
    existe = (await db.execute(text("SELECT ativo FROM rubricas_folha WHERE codigo = :c"), {"c": codigo})).scalar()
    if existe is None:
        raise HTTPException(
            status_code=400, detail=f"Rubrica {codigo} não existe em rubricas_folha — cadastre-a antes (aba Rubricas)."
        )
    if existe is False:
        raise HTTPException(
            status_code=409, detail=f"Rubrica {codigo} está INATIVA — reative-a antes de mapear um evento nela."
        )
    origem = str(payload.get("origem_regra") or "").strip()
    if len(origem) < 5:
        raise HTTPException(
            status_code=400, detail="Origem da regra obrigatória (cláusula da CCT, lei ou arquivo:linha do motor)."
        )
    formula = str(payload.get("formula") or "").strip()
    if len(formula) < 3:
        raise HTTPException(
            status_code=400, detail="Fórmula obrigatória — escreva como se lê: «horas × valor_hora × 1,5»."
        )
    escopo = _enum(payload.get("escopo") or "empresa", ESCOPOS, "Escopo")
    escopo_id = str(payload.get("escopo_id") or "").strip()
    if escopo != "empresa" and not escopo_id:
        raise HTTPException(
            status_code=400, detail=f"Escopo '{escopo}' exige o id (condomínio/colaborador) ou o nome (função/escala)."
        )
    if escopo == "empresa":
        escopo_id = ""
    pct = str(payload.get("percentual") or "").strip().replace(",", ".")
    try:
        percentual = Decimal(pct) if pct else None
    except InvalidOperation:
        raise HTTPException(status_code=400, detail=f"Percentual: número inválido ({pct!r}).") from None
    v = {
        "evento": evento,
        "rubrica_codigo": codigo,
        "escopo": escopo,
        "escopo_id": escopo_id,
        "formula": formula,
        "base": _enum(payload.get("base") or "valor_hora", BASES, "Base"),
        "percentual": percentual,
        "vigencia_inicio": _data(payload.get("vigencia_inicio"), "Vigência início"),
        "vigencia_fim": _data(payload.get("vigencia_fim"), "Vigência fim"),
        "origem_regra": origem,
    }
    if v["vigencia_inicio"] and v["vigencia_fim"] and v["vigencia_fim"] < v["vigencia_inicio"]:
        raise HTTPException(status_code=400, detail="Vigência: o fim é anterior ao início.")
    dup = (
        await db.execute(
            text(
                "SELECT id FROM ponto_evento_rubrica WHERE evento = CAST(:evento AS varchar) AND escopo = :escopo "
                "AND escopo_id = :escopo_id AND ativo"
            ),
            v,
        )
    ).scalar()
    if dup is not None and str(dup) != rid:
        raise HTTPException(
            status_code=409,
            detail=f"Já existe linha ativa de '{evento}' no escopo {escopo}{'/' + escopo_id if escopo_id else ''} (id {dup}). Edite-a.",
        )
    if rid:
        if not rid.isdigit():
            raise HTTPException(status_code=400, detail="id inválido.")
        v["id"] = int(rid)
        sets = ", ".join(f"{k} = :{k}" for k in v if k != "id")
        n = (
            await db.execute(text(f"UPDATE ponto_evento_rubrica SET {sets}, updated_at = now() WHERE id = :id"), v)
        ).rowcount  # noqa: S608
        if not n:
            raise HTTPException(status_code=404, detail="Linha não encontrada.")
        msg = f"Mapa de '{evento}' atualizado."
    else:
        v["criado_por"] = (getattr(current_user, "email", "") or "")[:120]
        cols = ", ".join(v)
        v["id"] = (
            await db.execute(
                text(
                    f"INSERT INTO ponto_evento_rubrica ({cols}) VALUES ({', '.join(':' + k for k in v)}) RETURNING id"
                ),
                v,
            )  # noqa: S608
        ).scalar()
        msg = f"Mapa de '{evento}' → {codigo} cadastrado (id {v['id']})."
    await db.commit()
    return {
        "ok": True,
        "id": v["id"],
        "message": msg + " O motor de folha NÃO lê este cadastro ainda (W5 = paralelo cego).",
    }


@router.post("/action/evento-rubrica-inativar")
async def rd_evento_rubrica_inativar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    """Alterna ativo/inativo. Nunca apaga: a linha é a explicação de holerites já emitidos."""
    await _ensure(db)
    rid = str(payload.get("id") or "").strip()
    if not rid.isdigit():
        raise HTTPException(status_code=400, detail="id inválido.")
    r = (
        await db.execute(
            text("SELECT evento, rubrica_codigo, ativo FROM ponto_evento_rubrica WHERE id = :id"), {"id": int(rid)}
        )
    ).first()
    if not r:
        raise HTTPException(status_code=404, detail="Linha não encontrada.")
    if r[2] and EVENTOS.get(r[0], {}).get("produzido"):
        outras = (
            await db.execute(
                text(
                    "SELECT count(*) FROM ponto_evento_rubrica WHERE evento = CAST(:e AS varchar) AND ativo AND id <> :id"
                ),
                {"e": r[0], "id": int(rid)},
            )
        ).scalar()
        if not outras:
            raise HTTPException(
                status_code=409,
                detail=f"'{r[0]}' é produzido pelo motor de folha e esta é a única linha ativa — o oráculo ficaria vermelho. "
                "Cadastre a linha substituta antes de inativar esta.",
            )
    await db.execute(
        text("UPDATE ponto_evento_rubrica SET ativo = NOT ativo, updated_at = now() WHERE id = :id"), {"id": int(rid)}
    )
    await db.commit()
    return {
        "ok": True,
        "message": f"{r[0]} → {r[1]} {'inativado' if r[2] else 'reativado'} em {date.today():%d/%m/%Y}.",
    }
