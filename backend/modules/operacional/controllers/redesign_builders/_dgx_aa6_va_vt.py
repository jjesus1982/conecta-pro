"""DGX AA6 — VA e VT por contrato: a dedução da base do INSS, com procedência (24/09/2026).

Telas (abas do grupo «Benefícios & Reembolsos» do DP):
  `va-vt-contrato`  — por cliente e competência: pessoas, dias, VA, VT, dedução e o que ela vale
                      em INSS. Por linha: «Texto da nota» (a discriminação legal pronta) e
                      «Sobrescrever» (o dono manda, com justificativa registrada).
  `va-vt-efetivo`   — o efetivo divergente, nome a nome: quem cada fonte vê e a causa provável.

A regra mora em `folha/services/va_vt_contrato.py`. Nada aqui muda folha, holerite, alocação ou
pagamento: é leitura + a decisão do dono em `va_vt_contrato_decisao`.
Prefixo `_` = o discovery pula; `departamento_pessoal.py` pluga `router` e `telas(db, out)` (# dgx aa6).
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.operacional.controllers.redesign_data_controller import b, brl, t
from modules.people_management.folha.services import va_vt_contrato as vv

_ND = "#0F1B3A"
_ACT = "/api/v1/redesign/action/"
_FONTE_ROTULO = {
    "allocations": "alocação",
    "employee_alocacoes": "alocação antiga",
    "escala": "escala",
    "ponto": "ponto",
}


def _competencias(n: int = 3) -> list[tuple[int, int]]:
    hoje = date.today()
    y, m = hoje.year, hoje.month
    fora = []
    for _ in range(n):
        fora.append((y, m))
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return fora


router = APIRouter()


def _erro(e: Exception) -> None:
    raise HTTPException(status_code=400, detail=str(e))


@router.post("/action/va-vt-decisao")
async def rd_va_vt_decisao(
    current_user: CurrentActiveUser,
    client_id: str,
    ano: int,
    mes: int,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """O dono sobrescreve VA/VT/pessoas do contrato. A justificativa é obrigatória e fica gravada."""
    try:
        r = await vv.registrar_decisao(db, client_id, ano, mes, payload, getattr(current_user, "email", None) or "—")
    except ValueError as e:
        await db.rollback()
        _erro(e)
    return {
        "ok": True,
        "message": f"Decisão registrada para {mes:02d}/{ano}: VA {vv.reais(r['va'] or 0)} · VT {vv.reais(r['vt'] or 0)}. "
        "A emissão passa a usar este número, com o seu nome e a justificativa.",
    }


@router.post("/action/va-vt-texto-nota")
async def rd_va_vt_texto(
    current_user: CurrentActiveUser,
    client_id: str,
    ano: int,
    mes: int,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """A discriminação que vai NA NOTA. Sem ela escrita na nota, a dedução é glosável."""
    linhas = await vv.apurar(db, ano, mes, client_id=client_id)
    if not linhas:
        _erro(ValueError("contrato sem apuração nesta competência"))
    ln = linhas[0]
    if not ln["sabe"]:
        _erro(
            ValueError(
                "a apuração não sabe o VA/VT deste contrato — "
                + "; ".join(ln["motivos"][:3])
                + ". Use «Sobrescrever» e digite o número que você assina."
            )
        )
    bruto = (payload.get("valor_bruto") or "").replace(".", "").replace(",", ".")
    try:
        bruto_d = vv._c(bruto)
    except Exception:  # noqa: BLE001
        _erro(ValueError("valor bruto inválido — use 29.600,00"))
    # a CONTAGEM é declaração legal na nota e a escala não a responde sozinha: quando não é
    # confiável, quem assina digita. Nunca imprimimos um número de cabeças que não sabemos.
    pessoas = ln["pessoas"]
    digitado = str(payload.get("pessoas") or "").strip()
    if digitado.isdigit():
        pessoas = int(digitado)
    if pessoas is None:
        _erro(
            ValueError(
                "a quantidade de funcionários deste contrato não é confiável ("
                + f"presentes {ln['pessoas_presentes']}, escala {ln['pessoas_escala']}, "
                + f"alocação {ln['efetivo'].get('allocations')}, "
                + f"alocação antiga {ln['efetivo'].get('employee_alocacoes')}"
                + ") — digite a quantidade que o senhor assina no campo «Funcionários no contrato»."
            )
        )
    texto = vv.texto_discriminacao(bruto_d, ln["va"], ln["vt"], pessoas, f"{mes:02d}/{ano}")
    return {"ok": True, "message": texto, "texto": texto}


async def telas(db, out: dict) -> dict:
    """Monta as duas abas dentro de `out` e devolve `out` (o builder do DP chama depois de montar_grupos)."""
    await vv._ensure(db)
    comps = _competencias(3)

    linhas_valor: list[dict] = []
    linhas_efetivo: list[dict] = []
    for ano, mes in comps:
        rot = f"{mes:02d}/{ano}"
        try:
            dados = await vv.apurar(db, ano, mes)
        except Exception:  # noqa: BLE001
            await db.rollback()
            continue
        for ln in dados:
            ded = (ln["va"] or 0) + (ln["vt"] or 0)
            inss = float(vv.inss_de(ded)) if ln["sabe"] else None
            estado = (
                b("decisão do dono", "info")
                if ln.get("decisao")
                else (b("apurado", "ok") if ln["sabe"] else b("não sei", "warn"))
            )
            acoes = [
                {
                    "title": f"Sobrescrever VA/VT de «{ln['cliente']}» em {rot}",
                    "endpoint": f"{_ACT}va-vt-decisao?client_id={ln['client_id']}&ano={ano}&mes={mes}",
                    "method": "POST",
                    "btnLabel": "Sobrescrever",
                    "submitLabel": "Registrar decisão",
                    "btnStyle": "outline",
                    "okMsg": "Decisão registrada — a emissão passa a usar este número.",
                    "fields": [
                        {
                            "key": "pessoas",
                            "label": "Funcionários no contrato",
                            "type": "number",
                            "value": str(ln["pessoas"] if ln["pessoas"] is not None else ln["pessoas_presentes"]),
                        },
                        {"key": "va", "label": "Vale Alimentação (R$)", "value": f"{ln['va_apurado'] or 0:.2f}"},
                        {"key": "vt", "label": "Vale Transporte (R$)", "value": f"{ln['vt_apurado'] or 0:.2f}"},
                        {
                            "key": "justificativa",
                            "label": "Por quê? (obrigatório — fica na nota e no registro)",
                            "type": "textarea",
                            "span": "span 2",
                            "ph": "ex.: o jardineiro é faturado na nota da Eletrônica, não entra na dedução da Patrimonial",
                        },
                    ],
                }
            ]
            if ln["sabe"]:
                acoes.append(
                    {
                        "title": f"Texto da nota — {ln['cliente']} {rot}",
                        "endpoint": f"{_ACT}va-vt-texto-nota?client_id={ln['client_id']}&ano={ano}&mes={mes}",
                        "method": "POST",
                        "btnLabel": "Texto da nota",
                        "submitLabel": "Gerar",
                        "btnStyle": "outline",
                        "showResult": True,
                        "okMsg": "Copie para a descrição da nota — sem isso escrito, a dedução é glosável.",
                        "fields": [
                            {"key": "valor_bruto", "label": "Valor bruto da nota (R$)", "ph": "29.600,00"},
                            {
                                "key": "pessoas",
                                "label": "Funcionários no contrato"
                                + ("" if ln["pessoas_confiavel"] else " (obrigatório — as fontes discordam)"),
                                "type": "number",
                                "value": str(ln["pessoas"]) if ln["pessoas"] is not None else "",
                                "ph": f"presentes no posto: {ln['pessoas_presentes']} (escala {ln['pessoas_escala']})",
                            },
                        ],
                    }
                )
            linhas_valor.append(
                {
                    "cells": [
                        t(ln["cliente"], 600, _ND),
                        (
                            t(str(ln["pessoas"]), 600)
                            if ln["pessoas"] is not None
                            else t(f"{ln['pessoas_presentes']}?", 600, "#B45309")
                        ),
                        t(f"{ln['dias_va']} / {ln['dias_vt']}"),
                        brl(ln["va"]) if ln["va"] is not None else t("não sei", 600, "#B45309"),
                        brl(ln["vt"]) if ln["vt"] is not None else t("não sei", 600, "#B45309"),
                        brl(ded) if ln["sabe"] else t("—"),
                        brl(inss) if inss is not None else t("—"),
                        estado,
                        t(("; ".join(ln["motivos"])[:160] if ln["motivos"] else ln["fonte"])[:160]),
                    ],
                    "filtros": {"Competência": rot, "Cliente": ln["cliente"]},
                    "actions": acoes,
                }
            )
            ef = ln["efetivo"]
            linhas_efetivo.append(
                {
                    "cells": [
                        t(ln["cliente"], 600, _ND),
                        t(str(ef.get("allocations", 0))),
                        t(str(ef.get("employee_alocacoes", 0))),
                        t(str(ef.get("escala", 0))),
                        t(str(ef.get("ponto", 0))),
                        t(str(ef.get("required_headcount") or "—")),
                        (
                            b(str(ef["conciliado"]), "ok")
                            if ef.get("conciliado") is not None
                            else b(f"{len(ef.get('divergencias', []))} divergem", "warn")
                        ),
                        t(
                            " · ".join(
                                f"{d['nome']} ({'/'.join(_FONTE_ROTULO.get(f, f) for f in d['fontes']) or 'nenhuma'}): {d['causa']}"
                                for d in ef.get("divergencias", [])
                            )[:400]
                            or "—"
                        ),
                    ],
                    "filtros": {"Competência": rot},
                }
            )

    out["va-vt-contrato"] = {
        "title": "VA e VT por contrato — a dedução do INSS",
        "sub": "Decisão do dono (24/09/2026): toda nota da CONECTAMAIS PATRIMONIAL é cessão de mão de obra e retém 11% sobre "
        "bruto − (VA + VT), Art. 31 da Lei 9.711/98. O número vem de PESSOA × DIAS DE ESCALA no posto × R$/dia da CCT — "
        "nunca do desconto do empregado na folha (rubricas 1010/1011), que é outra coisa e daria imposto a MAIS. "
        "Contrato sem apuração confiável diz «não sei»: aí o senhor digita o número que assina, com justificativa.",
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar cliente…",
        "grid": "1.6fr 0.5fr 0.7fr 0.9fr 0.9fr 0.9fr 0.9fr 0.8fr 2.4fr",
        "cols": [
            "Cliente",
            "Pessoas",
            "Dias VA/VT",
            "Vale Alimentação",
            "Vale Transporte",
            "Dedução",
            "INSS 11%",
            "Estado",
            "Procedência / por que não sei",
        ],
        "rows": linhas_valor,
    }
    out["va-vt-efetivo"] = {
        "title": "Efetivo por contrato — onde as fontes discordam",
        "sub": "Quatro fontes dizem quem está em qual cliente e elas discordam. A régua do VALOR é a ESCALA (quem tem turno no "
        "posto no mês) porque é a única verificável depois do fato e a que reproduz o cronograma do dono. O ponto entra como "
        "evidência: 48% das batidas de 08/2026 não têm posto. Corrigir a alocação é decisão sua — esta tela mostra o que corrigir.",
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar cliente…",
        "grid": "1.4fr 0.6fr 0.7fr 0.5fr 0.5fr 0.6fr 0.8fr 3fr",
        "cols": [
            "Cliente",
            "Alocação",
            "Alocação antiga",
            "Escala",
            "Ponto",
            "Contratado",
            "Conciliado",
            "Divergências (nome · fontes · causa)",
        ],
        "rows": linhas_efetivo,
    }
    return out
