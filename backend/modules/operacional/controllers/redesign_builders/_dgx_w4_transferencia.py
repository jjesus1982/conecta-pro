"""DGX W4 — Transferência entre as empresas do grupo (24/09/2026): o «Transferir (filial destino)»
do `/Colaboradores/Index` do DGX. A regra mora em
`people_management/hr/services/transferencia.py`; aqui só se pinta e se despacha.

Prefixo `_` = o discovery pula; `departamento_pessoal.py` importa `router` no topo e chama
`telas(db, out)` ANTES de `montar_grupos` (abas no grupo Admissão & Cadastro, `_dp_grupos`).

Telas (deep-link `/redesign/departamento-pessoal?t=<id>`):
  `transferencias`             — lista com status e ações Simular · Efetivar · Cancelar
  `transferencia-nova`         — colaborador, empresa destino, data, motivo, cargo/salário novos
  `transferencia-simular`      — o antes/depois: o que muda e o que NÃO muda
  `transferencias-conferencia` — a régua: eSocial × sistema (nasceu do GEILSON, ver o serviço)

Por que fica em Admissão & Cadastro e não em Desligamento: transferência NÃO é rescisão. É o
vínculo mudando de CNPJ, continuando. Pendurá-la no Desligamento seria ensinar o erro que esta
frente existe para desfazer — e a Ficha do colaborador, que ela alimenta, já mora aqui.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.people_management.hr.services import transferencia as tr

logger = logging.getLogger(__name__)
_ND = "#0F1B3A"
_ACT = "/api/v1/redesign/action/"

router = APIRouter()

SQL_LISTA = """
SELECT t.id::text, t.data, t.status, t.motivo, t.empresa_origem_cnpj, t.empresa_destino_cnpj,
       e.nome, coalesce(e.matricula,'—'), c.cargo_nome, t.novo_salario, t.observacao,
       u.name, t.efetivada_em, t.esocial_s2299_id::text, t.esocial_s2200_id::text
  FROM dp_transferencias t
  LEFT JOIN employees e ON e.id = t.employee_id
  LEFT JOIN cct_cargos c ON c.id = t.novo_cargo_id
  LEFT JOIN users u ON u.id = t.efetivada_por
 ORDER BY t.data DESC, t.criado_em DESC NULLS LAST
 LIMIT 300
"""
SQL_EMPRESAS = "SELECT cnpj, razao_social FROM empresas WHERE coalesce(status,'ativa') = 'ativa' ORDER BY is_principal DESC, razao_social"
SQL_CARGOS = "SELECT id::text, cargo_nome, piso_salarial FROM cct_cargos WHERE is_active ORDER BY cargo_nome"
SQL_PESSOAS = """
SELECT e.id::text, e.nome, coalesce(e.matricula,''), coalesce(em.razao_social,'(sem empresa)')
  FROM employees e LEFT JOIN empresas em ON em.id = e.empresa_id
 WHERE e.status = 'ativo' AND coalesce(e.is_homologacao,false) = false
   AND coalesce(e.status,'') NOT IN ('candidato','pj_ativo','pj_inativo')
 ORDER BY e.nome
"""
_TOM = {"rascunho": "warn", "efetivada": "ok", "cancelada": "mut"}


def _d(v) -> str:
    return v.strftime("%d/%m/%Y") if v else "—"


def _gate_dp(current_user: CurrentActiveUser) -> None:
    from .departamento_pessoal import _require_modulo_dp  # lazy: departamento_pessoal importa este módulo

    _require_modulo_dp(current_user)


def _erro(exc: tr.TransferenciaErro) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=str(exc))


async def _opts(db: AsyncSession) -> tuple[list[dict], list[dict], list[dict]]:
    pessoas = [
        {"value": r[0], "label": f"{r[1]}" + (f" · {r[2]}" if r[2] else "") + f" — {r[3]}"}
        for r in (await db.execute(text(SQL_PESSOAS))).fetchall()
    ]
    empresas = [{"value": r[0], "label": f"{r[1]} — {r[0]}"} for r in (await db.execute(text(SQL_EMPRESAS))).fetchall()]
    cargos = [
        {"value": r[0], "label": f"{r[1]} — piso {r[2]}"} for r in (await db.execute(text(SQL_CARGOS))).fetchall()
    ]
    vazio = [{"value": "", "label": "— selecione —"}]
    return vazio + pessoas, vazio + empresas, [{"value": "", "label": "— manter o cargo atual —"}] + cargos


async def telas(db: AsyncSession, out: dict) -> None:
    from modules.operacional.controllers.redesign_data_controller import S, b, initials, t

    try:
        await tr._ensure(db)
        rows = (await db.execute(text(SQL_LISTA))).fetchall()
        pessoas, empresas, cargos = await _opts(db)
        regua = await tr.regua(db)
    except Exception as exc:  # noqa: BLE001 — visível, nunca calado
        await db.rollback()
        logger.error("dgx w4: transferências falharam: %s", exc, exc_info=True)
        out["transferencias"] = {
            "title": "Transferências — FALHOU",
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

    motivo_opts = [{"value": k, "label": f"{k} — {v}"} for k, v in tr.MOTIVOS.items()]
    hoje = tr.hoje_manaus().isoformat()
    linhas = []
    for r in rows:
        acoes = []
        if r[2] == "rascunho":
            acoes = [
                {
                    "title": f"EFETIVAR a transferência de {r[6]} para {r[5]}",
                    "endpoint": f"{_ACT}transferencia-efetivar?transferencia_id={r[0]}",
                    "method": "POST",
                    "btnLabel": "Efetivar",
                    "submitLabel": "Efetivar",
                    "btnStyle": "primary",
                    "gated": True,
                    "confirm": (
                        "Isto TROCA a empresa do colaborador, remaneja a alocação e cria 2 RASCUNHOS de eSocial "
                        "(S-2299 + S-2200). Nada é transmitido ao governo. Confirma?"
                    ),
                    "okMsg": "Transferência efetivada. Recarregue a tela.",
                    "showResult": True,
                    "fields": [],
                },
                {
                    "title": f"CANCELAR o rascunho de {r[6]}",
                    "endpoint": f"{_ACT}transferencia-cancelar?transferencia_id={r[0]}",
                    "method": "POST",
                    "btnLabel": "Cancelar",
                    "submitLabel": "Cancelar rascunho",
                    "btnStyle": "danger",
                    "okMsg": "Rascunho cancelado. Recarregue a tela.",
                    "fields": [{"key": "motivo", "label": "Por quê?", "type": "text"}],
                },
            ]
        linhas.append(
            {
                "cells": [
                    t(_d(r[1]), 600),
                    t(r[6] or "—", 600, _ND, initials(r[6] or "")),
                    t(f"{r[4] or '—'} → {r[5]}"),
                    t(f"{r[3]} — {tr.MOTIVOS.get(r[3], '?')}"),
                    t((r[8] or "mantém o cargo") + (f" · R$ {r[9]}" if r[9] is not None else "")),
                    b(r[2], _TOM.get(r[2], "mut")),
                    t(
                        (f"{r[11]} · {_d(r[12])}" if r[11] else "—")
                        + (" · 2 rascunhos eSocial" if r[13] and r[14] else "")
                    ),
                ],
                "filtros": {"status": r[2], "destino": r[5] or "—"},
                "actions": acoes,
            }
        )

    n_rasc = sum(1 for r in rows if r[2] == "rascunho")
    n_efet = sum(1 for r in rows if r[2] == "efetivada")
    out["transferencias"] = {
        "title": "Transferências entre as empresas do grupo",
        "sub": (
            f"{n_efet} efetivada(s) · {n_rasc} em rascunho · {len(rows)} no histórico · "
            "transferência NÃO é rescisão: admissão, período aquisitivo de férias, banco de horas, dependentes e "
            "documentos ficam como estão · os 2 eventos do eSocial entram como RASCUNHO (S-2299 na origem + S-2200 "
            "no destino) e a transmissão continua sendo ato humano"
            + (
                f" · {len(regua['so_no_governo'])} pessoa(s) transferida(s) no governo SEM registro aqui (aba Conferência)"
                if regua["so_no_governo"]
                else ""
            )
        ),
        "cta": "Nova transferência",
        "ctaTo": "transferencia-nova",
        "type": "table",
        "searchHint": "Buscar colaborador, CNPJ ou motivo…",
        "grid": "0.8fr 1.6fr 1.6fr 1.8fr 1.4fr 0.8fr 1.4fr",
        "cols": [
            "Data",
            "Colaborador",
            "Origem → destino",
            "Motivo (eSocial)",
            "Cargo/salário novos",
            "Status",
            "Efetivada por",
        ],
        "rows": linhas,
    }

    campos_base = [
        {"key": "employee_id", "label": "Colaborador*", "type": "select", "span": "span 2", "options": pessoas},
        {"key": "empresa_destino_cnpj", "label": "Empresa destino*", "type": "select", "options": empresas},
        {"key": "data", "label": "Data da transferência*", "type": "date", "value": hoje},
        {"key": "novo_cargo_id", "label": "Novo cargo (opcional)", "type": "select", "options": cargos},
        {"key": "novo_salario", "label": "Novo salário (opcional)", "type": "number", "ph": "2500.00"},
    ]
    out["transferencia-nova"] = {
        "title": "Nova transferência",
        "sub": "Grava como RASCUNHO — nada muda no colaborador até você clicar em Efetivar na lista. "
        "Cargo e salário em branco = mantém os atuais.",
        "cta": "Gravar rascunho",
        "type": "form",
        "submit": {
            "endpoint": _ACT + "transferencia-nova",
            "okMsg": "Rascunho gravado. Confira na aba Transferências e efetive.",
            "showResult": True,
        },
        "fields": campos_base
        + [
            {
                "key": "motivo",
                "label": "Motivo (tabela 19 do eSocial)*",
                "type": "select",
                "span": "span 2",
                "options": motivo_opts,
            },
            {"key": "observacao", "label": "Observação", "type": "textarea", "span": "span 2"},
        ],
    }
    out["transferencia-simular"] = {
        "title": "Simular transferência",
        "sub": "O antes/depois, sem gravar nada: o que muda (empresa, cargo, salário, alocação) e o que NÃO muda "
        "(data de admissão, período aquisitivo de férias, banco de horas, dependentes, documentos).",
        "cta": "Simular",
        "type": "form",
        "submit": {"endpoint": _ACT + "transferencia-simular", "okMsg": "Simulação pronta.", "showResult": True},
        "fields": campos_base,
    }

    gov, sis, cas = regua["so_no_governo"], regua["so_no_sistema"], regua["casados"]
    out["transferencias-conferencia"] = {
        "title": "Conferência — eSocial × sistema",
        "sub": (
            f"Espelho do governo lido até {regua['espelho_de'] or 'nunca'} · {regua['limite']} "
            "Esta régua nasceu do GEILSON: S-2299 com motivo 11 em 30/06/2026 no eSocial, ativo no nosso "
            "cadastro, e nenhuma transferência registrada — o DP descobriu consultando o governo."
        ),
        "cta": "—",
        "type": "dash",
        "panelGrid": "1fr 1fr",
        "kpis": [
            {
                "v": str(len(gov)),
                "l": "Só no governo",
                "icon": "M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z",
                "color": "#B91C1C",
            },
            {
                "v": str(len(sis)),
                "l": "Só no sistema",
                "icon": "M12 8v4l3 3M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20",
                "color": "#B45309",
            },
            {"v": str(len(cas)), "l": "Conferidos", "icon": "M20 6 9 17l-5-5", "color": "#16A34A"},
        ],
        "panels": [
            {
                "title": "Transferido no eSocial e SEM registro aqui — abra uma transferência para cada um",
                "rows": [
                    {
                        "left": f"{x['nome']} · CPF {x['cpf']}",
                        "right": f"S-2299 motivo {x['motivo']} em {x['quando_no_governo']} · aqui: {x['status_aqui']} em {x['empresa_aqui']}",
                        **S["bad"],
                    }
                    for x in gov
                ]
                or [{"left": "nenhum — o governo e o sistema batem", "right": "—", **S["ok"]}],
            },
            {
                "title": "Efetivado aqui e SEM S-2299 (10/11) no espelho — pode ser só espelho velho",
                "rows": [
                    {
                        "left": f"{x['nome']} · CPF {x['cpf'] or '—'}",
                        "right": f"transferida em {x['quando_aqui']} para {x['destino']} (motivo {x['motivo']})",
                        **S["warn"],
                    }
                    for x in sis
                ]
                or [{"left": "nenhum", "right": "—", **S["ok"]}],
            },
            {
                "title": "Conferidos — os dois lados batem",
                "rows": [
                    {
                        "left": x["nome"],
                        "right": f"governo {x['quando_no_governo']} · sistema {x['quando_aqui']} · motivo {x['motivo']}",
                        **S["ok"],
                    }
                    for x in cas
                ]
                or [{"left": "nenhuma transferência conferida ainda", "right": "—", **S["mut"]}],
            },
        ],
    }


# ----------------------------------------------------------------------------- ações
@router.post("/action/transferencia-simular", dependencies=[Depends(_gate_dp)])
async def rd_simular(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    try:
        r = await tr.simular(
            db,
            employee_id=(payload.get("employee_id") or "").strip(),
            empresa_destino_cnpj=(payload.get("empresa_destino_cnpj") or "").strip(),
            data=payload.get("data") or None,
            novo_cargo_id=(payload.get("novo_cargo_id") or "").strip() or None,
            novo_salario=payload.get("novo_salario"),
        )
    except tr.TransferenciaErro as exc:
        raise _erro(exc) from exc
    return {"ok": True, "message": f"{r['colaborador']} — simulação em {r['data']}. Nada foi gravado.", **r}


@router.post("/action/transferencia-nova", dependencies=[Depends(_gate_dp)])
async def rd_nova(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    try:
        r = await tr.criar(
            db,
            employee_id=(payload.get("employee_id") or "").strip(),
            empresa_destino_cnpj=(payload.get("empresa_destino_cnpj") or "").strip(),
            data=payload.get("data") or None,
            motivo=(payload.get("motivo") or "10").strip(),
            novo_cargo_id=(payload.get("novo_cargo_id") or "").strip() or None,
            novo_salario=payload.get("novo_salario"),
            observacao=payload.get("observacao"),
            user_id=str(getattr(current_user, "id", "") or "") or None,
        )
    except tr.TransferenciaErro as exc:
        raise _erro(exc) from exc
    return {
        "ok": True,
        "message": f"Rascunho gravado: {r['colaborador']} → {r['destino']} em {r['data']}. "
        "Nada mudou ainda — efetive na aba Transferências.",
        **r,
    }


@router.post("/action/transferencia-efetivar", dependencies=[Depends(_gate_dp)])
async def rd_efetivar(
    transferencia_id: str, current_user: CurrentActiveUser, db: AsyncSession = Depends(get_db)
) -> dict:
    try:
        r = await tr.efetivar(
            db, transferencia_id=transferencia_id, user_id=str(getattr(current_user, "id", "") or "") or None
        )
    except tr.TransferenciaErro as exc:
        raise _erro(exc) from exc
    return {
        "ok": True,
        "message": f"{r['colaborador']} transferido para {r['destino']}. 2 rascunhos de eSocial criados "
        "(S-2299 + S-2200) — NADA foi transmitido ao governo.",
        **r,
    }


@router.post("/action/transferencia-cancelar", dependencies=[Depends(_gate_dp)])
async def rd_cancelar(
    transferencia_id: str,
    current_user: CurrentActiveUser,
    payload: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        r = await tr.cancelar(
            db,
            transferencia_id=transferencia_id,
            user_id=str(getattr(current_user, "id", "") or "") or None,
            motivo=(payload or {}).get("motivo"),
        )
    except tr.TransferenciaErro as exc:
        raise _erro(exc) from exc
    return {"ok": True, "message": "Rascunho cancelado. Nada foi alterado no colaborador.", **r}
