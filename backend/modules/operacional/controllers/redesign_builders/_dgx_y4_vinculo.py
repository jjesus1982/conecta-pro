"""DGX Y4 — de qual CLIENTE é cada colaborador: fonte, confiança e o que o dado não diz.

24/09/2026. Tela `vinculo-cliente` no **g-visao** do DP — é cadastro, não folha. Uma linha por
ativo: o cliente resolvido, de ONDE ele saiu e com que confiança; conflito e sem-fonte em
vermelho, com o botão **Definir cliente** para o humano resolver o que o dado não diz.

A regra mora fora daqui: `operacional/services/vinculo_cliente.py` (a precedência declarada, a
DDL, o porquê de `employees.cliente_id` ser campo morto). Aqui só tela e ação.

Prefixo `_` = o discovery pula; `departamento_pessoal.py` importa `router` (topo) e chama
`telas(db, out)` antes de `montar_grupos` (a aba está em `_dp_grupos.GRUPOS`, fim do g-visao).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

#: ANTES do import do data_controller (mesmo motivo da X3: o ciclo fecha com o router pronto)
router = APIRouter()

from modules.operacional.controllers.redesign_data_controller import b, t  # noqa: E402
from modules.operacional.services import vinculo_cliente as vc  # noqa: E402

logger = logging.getLogger(__name__)
_ND = "#0F1B3A"
_ACT = "/api/v1/redesign/action/"
ABAS = [("vinculo-cliente", "Vínculo com o cliente")]

#: Cor do selo de confiança. `conflito`/`sem_fonte` são os dois vermelhos da tela.
_TOM = {"alta": "ok", "média": "warn", "nenhuma": "bad"}


async def _clientes(db) -> list[dict]:
    """Os clientes que têm posto — quem não tem posto não recebe colaborador."""
    rows = (
        await db.execute(
            text("SELECT c.id::text, c.name FROM clients c WHERE c.id IN (SELECT client_id FROM posts) ORDER BY c.name")
        )
    ).all()
    return [{"value": r[0], "label": r[1]} for r in rows]


def _acao_definir(eid: str, nome: str, opcoes: list[dict], atual: str | None) -> dict:
    return {
        "title": f"Definir o cliente de {nome}",
        "endpoint": _ACT + f"vinculo-definir-cliente?employee_id={eid}",
        "method": "POST",
        "btnLabel": "Definir cliente",
        "submitLabel": "Gravar",
        "btnStyle": "outline",
        "okMsg": "Vínculo definido. Recarregue a tela.",
        "fields": [
            {"key": "client_id", "label": "Cliente*", "type": "select", "span": "span 2", "options": opcoes},
            {
                "key": "motivo",
                "label": "Por que este cliente?*",
                "type": "textarea",
                "span": "span 2",
                "ph": "O que você sabe que o sistema não sabe — é o que o DP vai ler daqui a um ano.",
            },
        ],
        **({"confirm": f"{nome} hoje resolve para {atual}. Trocar à mão?"} if atual else {}),
    }


async def _tela(db) -> dict:
    mapa = await vc.mapa_cliente(db)
    opcoes = await _clientes(db)
    linhas = sorted(mapa.values(), key=lambda r: (r["fonte"] not in ("conflito", "sem_fonte"), r["nome"]))
    rows = []
    for x in linhas:
        ruim = x["fonte"] in ("conflito", "sem_fonte")
        rows.append(
            {
                "cells": [
                    t(x["nome"][:34], 600, _ND),
                    t((x["cargo"] or "—")[:26]),
                    b(x["cliente_nome"] or "— o dado não diz —", "bad" if ruim else "ok"),
                    b(vc.FONTES[x["fonte"]], "bad" if ruim else ("info" if x["fonte"] != "turno" else "warn")),
                    b(x["confianca"], _TOM[x["confianca"]]),
                    t(x["condominio_nome"] or "—"),
                    t((x["evidencia"] or "nenhuma fonte")[:130]),
                ],
                "filtros": {
                    "Fonte": vc.FONTES[x["fonte"]],
                    "Confiança": x["confianca"],
                    "Situação": "precisa de gente" if ruim else "resolvido pelo dado",
                },
                "actions": [_acao_definir(x["employee_id"], x["nome"], opcoes, x["cliente_nome"])],
            }
        )
    censo: dict[str, int] = {}
    for x in linhas:
        censo[x["fonte"]] = censo.get(x["fonte"], 0) + 1
    ruins = censo.get("conflito", 0) + censo.get("sem_fonte", 0)
    com_cond = sum(1 for x in linhas if x["condominio_id"])
    return {
        "title": "Vínculo com o cliente",
        "sub": (
            f"{len(linhas)} colaborador(es) ativo(s) · **{len(linhas) - ruins} com cliente resolvido pelo dado** · "
            f"{censo.get('conflito', 0)} em conflito e {censo.get('sem_fonte', 0)} sem fonte nenhuma (em vermelho, "
            f"no topo) · {com_cond} com condomínio, que é o que dá escopo a feriado de cliente e a regra de ponto. "
            "A verdade do vínculo é a **alocação vigente**, não o cadastro: `employees.cliente_id` não tem chave "
            "estrangeira, tem dois escritores em todo o sistema e hoje está órfão em 37 dos 63 ativos e nulo em "
            "outros 14 — por isso a cascata que procurava o condomínio por ele resolvia ZERO pessoas. "
            "Precedência: definido por pessoa › alocação por posto › alocação por condomínio › turno dos últimos "
            "60 dias › cadastro. Quando as duas alocações discordam, a tela diz **conflito** e não escolhe no "
            "escuro — quem escolhe é você. "
            "**Definir cliente é a exceção, não a regra**: o certo é corrigir a alocação, que é o dado que o "
            "resto do sistema usa; definir à mão grava em `employees.cliente_id` e serve para quem não tem posto "
            "(escritório, afastado) ou para desempatar um conflito enquanto a operação não arruma."
        ),
        "cta": "—",
        "type": "table",
        "searchHint": "Colaborador, cliente, condomínio…",
        "filtros": [
            {"key": "Situação", "label": "Situação"},
            {"key": "Fonte", "label": "Fonte"},
            {"key": "Confiança", "label": "Confiança"},
        ],
        "grid": "1.5fr 1.1fr 1.5fr 1.4fr 0.7fr 1fr 2.2fr",
        "cols": ["Colaborador", "Cargo", "Cliente resolvido", "Fonte", "Confiança", "Condomínio", "Evidência"],
        "rows": rows,
    }


async def telas(db, out: dict | None = None) -> dict:
    mine: dict = {}
    try:
        mine["vinculo-cliente"] = await _tela(db)
    except Exception as exc:  # noqa: BLE001 — visível na tela, nunca calado
        await db.rollback()
        logger.error("dgx y4: tela vinculo-cliente falhou: %s", exc, exc_info=True)
        from ._dgx_f7_ponto import _falhou

        mine["vinculo-cliente"] = _falhou("Vínculo com o cliente", exc)
    if out is not None:
        out.update(mine)
    return mine


@router.post("/action/vinculo-definir-cliente")
async def rd_vinculo_definir_cliente(
    current_user: CurrentActiveUser,
    employee_id: str,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Declara à mão o cliente de UMA pessoa. Não existe versão em lote de propósito: preencher
    os 51 cadastros órfãos por inferência é decisão do dono, e o resolvedor existe para que não
    seja preciso."""
    try:
        r = await vc.definir_cliente(
            db,
            employee_id=employee_id,
            client_id=str(payload.get("client_id") or "").strip(),
            motivo=str(payload.get("motivo") or ""),
            definido_por=getattr(current_user, "email", None),
            user_id=str(getattr(current_user, "id", "") or "") or None,
        )
    except vc.VinculoErro as exc:
        await db.rollback()
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    return {
        "ok": True,
        "result": r,
        "message": (
            f"Cliente definido: {r['cliente_nome']}. A fonte agora é «{vc.FONTES[r['fonte_depois']]}» "
            f"(antes era «{vc.FONTES[r['fonte_antes']]}»). O caminho certo continua sendo corrigir a alocação."
        ),
    }
