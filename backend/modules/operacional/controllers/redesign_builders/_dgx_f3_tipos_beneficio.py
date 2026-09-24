"""DGX F3 — Tipos de Benefício com regra, linhas de VT e benefício individual completo (24/09/2026).

Telas (abas do grupo "Benefícios & Reembolsos" do DP): `beneficio-tipos` (tabela com a regra
resumida; Editar/Inativar por linha), `beneficio-tipo-novo` (form completo, os 7 tipos de desconto e
os 8 modos de ponto do DGX), `beneficio-linhas` (+ `beneficio-linha-nova`) e o form `nova-beneficio`
existente ganha tipo/linha/quantidade/unitário/anular outras fontes (passa a gravar pela ação
`beneficio-individual-salvar`, que preenche as colunas novas de `employee_benefits`).

Regra e DDL moram em `folha/services/beneficio_tipos.py`. Nada aqui muda folha/holerite: o motor da
frente 03 lê a regra e continua gravando só em `folha_beneficio_conferencia` (paralelo cego).
Prefixo `_` = o discovery pula; `departamento_pessoal.py` pluga `router` e `telas(db, out)` (# dgx f3).
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.operacional.controllers.redesign_data_controller import _helpers, b, brl, t
from modules.people_management.folha.services import beneficio_tipos as bt

_ND = "#0F1B3A"
_ACT = "/api/v1/redesign/action/"
_SN = [{"value": "nao", "label": "Não"}, {"value": "sim", "label": "Sim"}]
_PRIM = {
    "VT": "Vale Transporte",
    "VR": "Vale Refeição",
    "cesta": "Cesta Básica",
    "odonto": "Assistência Odontológica",
    "seguro_vida": "Seguro de Vida",
    "assistencia_medica": "Assistência Médica",
    "PLR": "PLR",
    "premio": "Prêmio",
    "SESMT": "SESMT",
    "cartao": "Cartão de Crédito",
    "outro": "Outro",
}


def _sn(v) -> str:
    return "sim" if v else "nao"


def _opts(d: dict) -> list[dict]:
    return [{"value": k, "label": v} for k, v in d.items()]


def _num(v) -> str:
    if v is None:
        return ""
    s = f"{Decimal(v):f}"
    return s.rstrip("0").rstrip(".") if "." in s else s


def _campos_tipo(r: dict | None = None) -> list[dict]:
    """Os campos do DGX `/TiposBeneficios`, pré-preenchidos quando `r` (linha da tabela) vem."""
    r = r or {}

    def f(key, label, typ="text", span="span 1", **kw):
        d = {"key": key, "label": label, "type": typ, "span": span, **kw}
        if key in r:
            d["value"] = r[key]
        return d

    return [
        f("nome", "Nome*", span="span 2", ph="ex.: Vale Transporte SINETRAM"),
        f("tipo_primitivo", "Tipo primitivo*", "select", options=_opts(_PRIM), ph="Selecione"),
        f("mensal", "Mensal", "select", options=_SN),
        f("prevalecer_individual", "Prevalecer individual", "select", options=_SN),
        f("tipo_desconto", "Tipo de desconto*", "select", options=_opts(bt.TIPOS_DESCONTO), ph="Selecione"),
        f("coeficiente_desconto", "Coeficiente (% ou R$)", ph="4 = 4% · 8,50 = R$ 8,50"),
        f("rubrica_debito", "Rubrica de débito (código)", ph="1010"),
        f("desconto_direto_dinheiro", "Desconto direto em dinheiro", "select", options=_SN),
        f(
            "integracao_ponto",
            "Integração com ponto",
            "select",
            options=[{"value": "", "label": "Nenhuma"}, *_opts(bt.INTEGRACAO_PONTO)],
        ),
        f("desconto_por_saldo", "Desconto por saldo (mês anterior)", "select", options=_SN),
        f("limite_faltas", "Limite de faltas", "number", ph="vazio = sem limite"),
        f("limite_faltas_justificadas", "Limite de faltas justificadas", "number"),
        f("dias_trabalhados_mes", "Dias trabalhados no mês", "number"),
        f("meses_afastamento_permitido", "Meses de afastamento permitido", "number"),
        f("remover_ferias", "Remover férias", "select", options=_SN),
        f("remover_afastados", "Remover afastados", "select", options=_SN),
        f("remover_atrasados", "Remover atrasados", "select", options=_SN),
        f(
            "meio_periodo_tipo",
            "Meio período — tipo",
            "select",
            options=[
                {"value": "nenhum", "label": "Nenhum"},
                {"value": "valor", "label": "Valor"},
                {"value": "percentual", "label": "Percentual"},
            ],
        ),
        f("meio_periodo_horas", "Meio período — horas", ph="4"),
        f("meio_periodo_valor", "Meio período — desconto", ph="R$ ou %"),
        f(
            "origem_regra",
            "Origem da regra*",
            "textarea",
            span="span 2",
            ph="CCT cláusula X · decisão da Pyetra DD/MM · código…",
        ),
    ]


def _campos_linha(r: dict | None = None) -> list[dict]:
    r = r or {}

    def f(key, label, typ="text", span="span 1", **kw):
        d = {"key": key, "label": label, "type": typ, "span": span, **kw}
        if key in r:
            d["value"] = r[key]
        return d

    return [
        f("operadora", "Operadora*", ph="SINETRAM / SOLIDES"),
        f("codigo", "Código", ph="opcional"),
        f("nome", "Nome da linha*", span="span 2", ph="ex.: 640 Cidade Nova / Centro"),
        f("valor", "Valor (R$)", ph="vazio até ter fonte"),
        f(
            "tipo_passe",
            "Tipo de passe",
            "select",
            options=[{"value": "cartao", "label": "Cartão"}, {"value": "papel", "label": "Papel"}],
        ),
        f("mensal", "Linha mensal", "select", options=_SN),
        f(
            "origem_regra",
            "Origem do valor (obrigatória se houver valor)",
            "textarea",
            span="span 2",
            ph="tabela SINETRAM DD/MM/AAAA · pedido nº…",
        ),
    ]


def _resumo_desconto(tdesc, coef, rub) -> str:
    rot = bt.TIPOS_DESCONTO.get(tdesc, tdesc)
    if tdesc == "nenhum" or coef is None:
        return rot
    val = brl(float(coef)) if tdesc in ("fixo", "valor_por_dia", "unidade") else f"{_num(coef)}%"
    return f"{rot} · {val}" + (f" · rubrica {rub}" if rub else "")


async def telas(db, out: dict | None = None) -> dict:  # noqa: C901
    await bt._ensure(db)
    mine, safe, tbl = _helpers(db)

    cols_t = [
        "id",
        "nome",
        "tipo_primitivo",
        "mensal",
        "prevalecer_individual",
        "tipo_desconto",
        "coeficiente_desconto",
        "rubrica_debito",
        "desconto_direto_dinheiro",
        "integracao_ponto",
        "desconto_por_saldo",
        "limite_faltas",
        "limite_faltas_justificadas",
        "dias_trabalhados_mes",
        "meses_afastamento_permitido",
        "remover_ferias",
        "remover_afastados",
        "remover_atrasados",
        "meio_periodo_tipo",
        "meio_periodo_horas",
        "meio_periodo_valor",
        "origem_regra",
        "ativo",
        "cct_beneficio_id",
    ]

    def _tipo_row(r):
        d = dict(zip(cols_t, r, strict=True))
        form = {
            k: (
                _sn(v)
                if isinstance(v, bool)
                else (
                    ""
                    if v is None
                    else _num(v)
                    if k in ("coeficiente_desconto", "meio_periodo_horas", "meio_periodo_valor")
                    else str(v)
                )
            )
            for k, v in d.items()
            if k in {c["key"] for c in _campos_tipo()}
        }
        remover = [
            n
            for n, v in (
                ("férias", d["remover_ferias"]),
                ("afastados", d["remover_afastados"]),
                ("atrasados", d["remover_atrasados"]),
            )
            if v
        ]
        faltas = " / ".join(
            str(x) if x is not None else "—"
            for x in (d["limite_faltas"], d["limite_faltas_justificadas"], d["dias_trabalhados_mes"])
        )
        cells = [
            t(d["nome"], 600, _ND),
            b(_PRIM.get(d["tipo_primitivo"], d["tipo_primitivo"]), "info"),
            t("mensal" if d["mensal"] else "diário"),
            t(_resumo_desconto(d["tipo_desconto"], d["coeficiente_desconto"], d["rubrica_debito"]), 600),
            t(bt.INTEGRACAO_PONTO.get(d["integracao_ponto"], "—") + (" · saldo" if d["desconto_por_saldo"] else "")),
            t(faltas),
            t(", ".join(remover) or "—"),
            t(
                "—"
                if d["meio_periodo_tipo"] == "nenhum"
                else f"{d['meio_periodo_tipo']} {_num(d['meio_periodo_horas'])}h {_num(d['meio_periodo_valor'])}"
            ),
            b("CCT" if d["cct_beneficio_id"] else "—", "ok" if d["cct_beneficio_id"] else "mut"),
            t((d["origem_regra"] or "")[:90] + ("…" if len(d["origem_regra"] or "") > 90 else "")),
            b("ativo" if d["ativo"] else "inativo", "ok" if d["ativo"] else "mut"),
        ]
        acoes = [
            {
                "title": f"Editar tipo «{d['nome']}»",
                "endpoint": f"{_ACT}beneficio-tipo-salvar?tipo_id={d['id']}",
                "method": "POST",
                "btnLabel": "Editar",
                "submitLabel": "Salvar",
                "btnStyle": "outline",
                "okMsg": "Tipo salvo. O motor de benefício passa a usar a regra nova no próximo cálculo (paralelo cego).",
                "fields": _campos_tipo(form),
            }
        ]
        if d["ativo"]:
            acoes.append(
                {
                    "title": f"INATIVAR «{d['nome']}»",
                    "endpoint": f"{_ACT}beneficio-tipo-inativar?tipo_id={d['id']}",
                    "method": "POST",
                    "btnLabel": "Inativar",
                    "submitLabel": "Inativar",
                    "btnStyle": "danger",
                    "okMsg": "Tipo inativado. Sem tipo ativo de VT/VR o motor marca `sem_regra` — não calcula com constante.",
                    "fields": [{"key": "motivo", "label": "Por quê? (fica registrado)", "type": "text"}],
                }
            )
        return {"cells": cells, "actions": acoes, "filtro": "ativos" if d["ativo"] else "inativos"}

    await safe(
        "beneficio-tipos",
        tbl(
            "Tipos de benefício — a regra mora aqui",
            "Como no DGX: cada tipo carrega o desconto (7 formas), a rubrica, a integração com o ponto (8 modos), limites de falta e o que remover. "
            "O motor de VT/VR lê daqui (paralelo cego — a folha continua em calculo_service até o oráculo fechar). Origem obrigatória: regra sem fonte não entra.",
            "—",
            [
                "Tipo",
                "Primitivo",
                "Período",
                "Desconto",
                "Ponto",
                "Faltas / just. / dias",
                "Remover",
                "Meio período",
                "CCT",
                "Origem",
                "Estado",
            ],
            "1.5fr 1fr 0.6fr 1.6fr 1fr 0.9fr 1fr 0.9fr 0.4fr 2.2fr 0.6fr",
            f"SELECT {', '.join(cols_t)} FROM beneficio_tipos ORDER BY ativo DESC, tipo_primitivo, nome",
            lambda r: _tipo_row(r)["cells"],
            hint="Buscar tipo…",
            actionsfn=lambda r: _tipo_row(r)["actions"],
            filtrofn=lambda r: _tipo_row(r)["filtro"],
        ),
    )
    if "beneficio-tipos" in mine:
        mine["beneficio-tipos"]["ctaTo"] = "beneficio-tipo-novo"
        mine["beneficio-tipos"]["cta"] = "Novo tipo"

    mine["beneficio-tipo-novo"] = {
        "title": "Novo tipo de benefício",
        "type": "form",
        "cta": "Salvar tipo",
        "sub": "Tipo de desconto: Fixo (R$) · Nenhum · % do valor sobre falta · % sobre salário · % sobre valor · Unidade · Valor por dia. "
        "Coeficiente é % quando o tipo é percentual e R$ quando é fixo/dia/unidade.",
        "submit": {
            "endpoint": f"{_ACT}beneficio-tipo-salvar",
            "okMsg": "Tipo criado — veja a aba Tipos de benefício.",
            "showResult": True,
        },
        "fields": _campos_tipo(
            {
                "mensal": "nao",
                "prevalecer_individual": "nao",
                "tipo_desconto": "",
                "desconto_direto_dinheiro": "nao",
                "integracao_ponto": "",
                "desconto_por_saldo": "nao",
                "remover_ferias": "nao",
                "remover_afastados": "nao",
                "remover_atrasados": "nao",
                "meio_periodo_tipo": "nenhum",
            }
        ),
    }

    cols_l = [
        "id",
        "operadora",
        "codigo",
        "nome",
        "valor",
        "tipo_passe",
        "mensal",
        "ativo",
        "origem_regra",
        "(SELECT count(*) FROM employee_benefits eb WHERE eb.linha_id = l.id AND lower(eb.status) = 'active')",
    ]

    def _linha_row(r):
        lid, op, cod, nome, valor, passe, mensal, ativo, origem, usos = r
        form = {
            "operadora": op,
            "codigo": cod or "",
            "nome": nome,
            "valor": _num(valor),
            "tipo_passe": passe,
            "mensal": _sn(mensal),
            "origem_regra": origem or "",
        }
        cells = [
            t(op, 600, _ND),
            t(cod or "—"),
            t(nome, 600),
            b(brl(float(valor)), "ok") if valor is not None else b("sem tarifa — sem fonte", "warn"),
            t("cartão" if passe == "cartao" else "papel"),
            t("mensal" if mensal else "avulsa"),
            t(str(usos)),
            t((origem or "—")[:80]),
            b("ativa" if ativo else "inativa", "ok" if ativo else "mut"),
        ]
        acoes = [
            {
                "title": f"Editar linha {op} · {nome}",
                "endpoint": f"{_ACT}beneficio-linha-salvar?linha_id={lid}",
                "method": "POST",
                "btnLabel": "Editar",
                "submitLabel": "Salvar",
                "btnStyle": "outline",
                "okMsg": "Linha salva.",
                "fields": _campos_linha(form),
            }
        ]
        if ativo:
            acoes.append(
                {
                    "title": f"INATIVAR linha {op} · {nome}",
                    "endpoint": f"{_ACT}beneficio-linha-salvar?linha_id={lid}&ativo=nao",
                    "method": "POST",
                    "btnLabel": "Inativar",
                    "submitLabel": "Inativar",
                    "btnStyle": "danger",
                    "okMsg": "Linha inativada.",
                    "fields": _campos_linha(form),
                }
            )
        return {"cells": cells, "actions": acoes}

    sem_tarifa = (
        await db.execute(text("SELECT count(*) FROM beneficio_linhas WHERE ativo AND valor IS NULL"))
    ).scalar() or 0
    await safe(
        "beneficio-linhas",
        tbl(
            "Linhas de VT (itinerários por operadora)",
            (
                "⚠️ "
                + str(sem_tarifa)
                + " linha(s) ativa(s) SEM tarifa — a tarifa entra só com origem (tabela da operadora, data, quem confirmou). "
                if sem_tarifa
                else ""
            )
            + "Seed = R$/dia por operadora que já estava em cct_benefit_configs (SINETRAM: 27 × R$ 10 ou 30 × R$ 9 ainda não confirmado com a Pyetra). "
            "Ninguém inventa tarifa aqui.",
            "—",
            ["Operadora", "Código", "Linha", "Valor", "Passe", "Período", "Em uso", "Origem", "Estado"],
            "1fr 0.7fr 1.8fr 1fr 0.6fr 0.6fr 0.5fr 2fr 0.6fr",
            f"SELECT {', '.join(cols_l)} FROM beneficio_linhas l ORDER BY ativo DESC, operadora, nome",
            lambda r: _linha_row(r)["cells"],
            hint="Buscar linha…",
            actionsfn=lambda r: _linha_row(r)["actions"],
        ),
    )
    if "beneficio-linhas" in mine:
        mine["beneficio-linhas"]["ctaTo"] = "beneficio-linha-nova"
        mine["beneficio-linhas"]["cta"] = "Nova linha"
    mine["beneficio-linha-nova"] = {
        "title": "Nova linha de VT",
        "type": "form",
        "cta": "Salvar linha",
        "sub": "Pode nascer sem valor. Valor sem origem é recusado.",
        "submit": {"endpoint": f"{_ACT}beneficio-linha-salvar", "okMsg": "Linha criada.", "showResult": True},
        "fields": _campos_linha({"tipo_passe": "cartao", "mensal": "nao"}),
    }

    # benefício individual: o form `nova-beneficio` (já na aba do grupo) ganha os campos do DGX e grava pela ação nova
    tipos = [
        {"value": str(r[0]), "label": f"{r[1]} ({_PRIM.get(r[2], r[2])})"}
        for r in (
            await db.execute(
                text("SELECT id, nome, tipo_primitivo FROM beneficio_tipos WHERE ativo ORDER BY tipo_primitivo, nome")
            )
        ).fetchall()
    ]
    linhas = [
        {
            "value": str(r[0]),
            "label": f"{r[1]} · {r[2]}" + (f" · {brl(float(r[3]))}" if r[3] is not None else " · sem tarifa"),
        }
        for r in (
            await db.execute(
                text("SELECT id, operadora, nome, valor FROM beneficio_linhas WHERE ativo ORDER BY operadora, nome")
            )
        ).fetchall()
    ]
    extra = [
        {
            "key": "beneficio_tipo_id",
            "label": "Tipo com regra (DGX)",
            "type": "select",
            "span": "span 1",
            "ph": "Selecione",
            "options": tipos,
        },
        {
            "key": "linha_id",
            "label": "Linha (VT)",
            "type": "select",
            "span": "span 1",
            "ph": "Sem linha",
            "options": linhas,
        },
        {"key": "quantidade", "label": "Quantidade (dias/passes)", "type": "text", "span": "span 1", "ph": "ex.: 22"},
        {"key": "valor_unitario", "label": "Valor unitário (R$)", "type": "text", "span": "span 1", "ph": "ex.: 10,00"},
        {
            "key": "anular_outras_fontes",
            "label": "Anular outras fontes",
            "type": "select",
            "span": "span 1",
            "options": _SN,
            "value": "nao",
        },
    ]
    grupo = (out or {}).get("g-beneficios")
    if isinstance(grupo, dict) and isinstance(grupo.get("tabs"), list):
        for aba in grupo["tabs"]:
            scr = aba.get("screen") if isinstance(aba, dict) else None
            if aba.get("id") == "nova-beneficio" and isinstance(scr, dict) and scr.get("type") == "form":
                scr["submit"] = {
                    "endpoint": f"{_ACT}beneficio-individual-salvar",
                    "okMsg": "Benefício adicionado (manual, com tipo/linha).",
                }
                scr["sub"] = (
                    "Cadastra um benefício para o colaborador. Tipo com regra, linha, quantidade, unitário e «anular outras fontes» como no DGX."
                )
                campos = [c for c in scr.get("fields", []) if c.get("key") not in {e["key"] for e in extra}]
                pos = next((i + 1 for i, c in enumerate(campos) if c.get("key") == "type"), 1)
                scr["fields"] = campos[:pos] + extra + campos[pos:]
                if campos and campos[pos - 1].get("key") == "type":
                    campos[pos - 1]["label"] = "Tipo simples (se não escolher o tipo com regra)"
        from modules.operacional.controllers.redesign_data_controller import moved

        for tid, lbl in (
            ("beneficio-tipos", "Tipos de benefício"),
            ("beneficio-tipo-novo", "Novo tipo"),
            ("beneficio-linhas", "Linhas de VT"),
            ("beneficio-linha-nova", "Nova linha"),
        ):
            if tid in mine:
                grupo["tabs"].append({"id": tid, "label": lbl, "screen": mine[tid]})
                mine[tid] = moved("g-beneficios", tid)
    return mine


# ───────────────────────── ações ─────────────────────────
router = APIRouter()


def _erro(e: Exception):
    raise HTTPException(status_code=422, detail=str(e))


@router.post("/action/beneficio-tipo-salvar")
async def rd_beneficio_tipo_salvar(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    tipo_id: int | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    await bt._ensure(db)
    try:
        rid = await bt.salvar_tipo(db, payload, tipo_id)
    except ValueError as e:
        await db.rollback()
        _erro(e)
    return {
        "ok": True,
        "message": f"Tipo {'atualizado' if tipo_id else 'criado'} (#{rid}) — a regra vale no próximo cálculo do paralelo cego.",
        "id": rid,
    }


@router.post("/action/beneficio-tipo-inativar")
async def rd_beneficio_tipo_inativar(
    current_user: CurrentActiveUser, tipo_id: int, payload: dict = Body(default={}), db: AsyncSession = Depends(get_db)
) -> dict:
    try:
        await bt.inativar_tipo(db, tipo_id)
    except ValueError as e:
        await db.rollback()
        _erro(e)
    return {
        "ok": True,
        "message": f"Tipo #{tipo_id} inativado"
        + (f" — motivo: {payload.get('motivo')}" if payload.get("motivo") else ""),
    }


@router.post("/action/beneficio-linha-salvar")
async def rd_beneficio_linha_salvar(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    linha_id: int | None = None,
    ativo: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    await bt._ensure(db)
    if ativo is not None:
        payload = {**payload, "ativo": ativo}
    try:
        rid = await bt.salvar_linha(db, payload, linha_id)
    except ValueError as e:
        await db.rollback()
        _erro(e)
    return {"ok": True, "message": f"Linha {'atualizada' if linha_id else 'criada'} (#{rid}).", "id": rid}


@router.post("/action/beneficio-individual-salvar")
async def rd_beneficio_individual_salvar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    await bt._ensure(db)
    try:
        rid = await bt.salvar_individual(db, payload)
    except ValueError as e:
        await db.rollback()
        _erro(e)
    return {"ok": True, "message": "Benefício adicionado (manual).", "id": rid}
