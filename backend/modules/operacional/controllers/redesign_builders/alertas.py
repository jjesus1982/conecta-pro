"""redesign_builders/alertas.py — a tela de ALERTAS, que não existia.

🔴 POR QUE ESTE MÓDULO NASCEU EM 30/09/2026.

O digest diário — *«Bom dia — o que precisa da sua atenção»* — apontava para `/notificacoes`, que
devolve **404**: essa pasta não existe no frontend. Medido: **374 notificações** para esse destino,
a última de hoje, **e nenhuma delas foi sequer aberta**. A única coisa que alguém abriria de
manhã levava ao vazio.

Varri os 70 destinos distintos dos últimos 90 dias: **618 notificações apontavam para páginas
inexistentes** (`/notificacoes`, `/ged/kits/<uuid>`, `/crm/tarefas`, `/dp/esocial`). Só uma fonte
ainda escrevia — o digest.

⭐ E o destino certo não existia: o digest consolida alertas de MÓDULOS DIFERENTES (CRM, ponto,
fiscal, prazos), então não cabe na Central de Aprovações (que é de rascunhos) e não havia módulo
`alertas`. O Jordan mandou criar de verdade em vez de apontar para a home.

## ⭐ POR QUE É TELA DE TRIAGEM E NÃO DE LISTA

Medido antes de desenhar: **Orlailson tem 1.892 não lidas, a Pyetra 1.374, o Jordan 735**. Uma
tela que despeja 1.892 linhas não ajuda — vira mais pilha. Então ela mostra primeiro o FORMATO
(quanto de cada família, quanto de cada severidade) e só depois a lista, com teto e com o total
verdadeiro dito em voz alta.

## ⚠️ POR QUE OS DADOS VÊM POR ROTA DE AÇÃO, E NÃO DO `build(db)`

Notificação é **por usuário**, e `build(db)` não recebe quem está olhando — montar a tabela ali
mostraria o sino de todo mundo para todo mundo. A rota `/action/alertas-listar` tem
`CurrentActiveUser` e filtra por ele. É o mesmo molde de «Ponto por período».
"""

import logging
from datetime import date  # noqa: F401 — usado na assinatura futura; mantém o import estável

from fastapi import APIRouter, Body, Depends
from sqlalchemy import text

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.operacional.controllers.redesign_data_controller import b, t

logger = logging.getLogger(__name__)
_log = logger

SLUG = "alertas"

EXTRA_MENU: list[dict] = [
    {
        "id": "meus-alertas",
        "label": "Meus alertas",
        "icon": "M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 0 1-3.46 0",
    },
]

#: Famílias medidas no banco em 30/09 (60 dias): crm 1746 · comercial 1340 · financeiro 978 ·
#: sistema 673 · ponto 439 · dp 320 · documentos 274 · operacional 198 · ai 70. A lista sai do
#: BANCO, não daqui — esta nota existe só para quem ler entender a ordem de grandeza.
_SEVERIDADES = [
    {"value": "", "label": "Qualquer severidade"},
    {"value": "critico", "label": "Crítico"},
    {"value": "atencao", "label": "Atenção"},
    {"value": "aviso", "label": "Aviso"},
    {"value": "info", "label": "Informativo"},
]

#: Teto de linhas. Sem teto, quem tem 1.892 não lidas trava o navegador. Com teto, o que se deve
#: é DIZER que cortou — silêncio aqui viraria «acabou», que é a mentira mais cara desta casa.
_TETO = 200


async def build(db) -> dict:
    """A tela. Sem linhas: elas vêm da rota de ação, que sabe QUEM está olhando."""
    try:
        familias = (
            await db.execute(
                text(
                    "SELECT DISTINCT extra_data->>'familia' f FROM communication_notifications "
                    " WHERE extra_data->>'familia' IS NOT NULL "
                    "   AND created_at >= now() - interval '90 days' ORDER BY 1"
                )
            )
        ).all()
    except Exception as exc:  # noqa: BLE001 — a tela não pode sumir por causa das opções
        _log.warning("alertas: famílias indisponíveis (%s)", exc)
        familias = []

    return {
        "meus-alertas": {
            "title": "Meus alertas",
            "sub": (
                "O que os vigias do sistema viram e endereçaram a VOCÊ. Mostra primeiro quanto há "
                "de cada tipo, depois a lista. O padrão é «não lidas dos últimos 7 dias» — o "
                "histórico continua alcançável, mas não é o que abre. É consulta: listar não "
                "altera nada."
            ),
            "cta": "Ver",
            "type": "form",
            "submit": {
                "endpoint": "/api/v1/redesign/action/alertas-listar",
                "okMsg": "Alertas carregados.",
                "showResult": True,
            },
            "fields": [
                {
                    "key": "acao",
                    "label": "O que fazer*",
                    "type": "select",
                    "span": "span 2",
                    "value": "listar",
                    "options": [
                        {"value": "listar", "label": "Listar — só mostrar, não altera nada"},
                        {
                            "value": "marcar_lidas",
                            "label": "Marcar como lidas — os alertas que o filtro abaixo pegar",
                        },
                    ],
                },
                {
                    "key": "dias",
                    "label": "Período (dias para trás)",
                    "type": "select",
                    "value": "7",
                    "options": [
                        {"value": "1", "label": "Hoje e ontem"},
                        {"value": "7", "label": "Últimos 7 dias"},
                        {"value": "30", "label": "Últimos 30 dias"},
                        {"value": "90", "label": "Últimos 90 dias"},
                    ],
                },
                {
                    "key": "so_nao_lidas",
                    "label": "Só não lidas",
                    "type": "select",
                    "value": "sim",
                    "options": [
                        {"value": "sim", "label": "Sim — só o que falta ver"},
                        {"value": "nao", "label": "Não — tudo do período"},
                    ],
                },
                {
                    "key": "familia",
                    "label": "Família",
                    "type": "select",
                    "options": [{"value": "", "label": "Todas"}]
                    + [{"value": f[0], "label": f[0]} for f in familias if f[0]],
                },
                {
                    "key": "severidade",
                    "label": "Severidade",
                    "type": "select",
                    "options": _SEVERIDADES,
                },
            ],
        }
    }


# ── a rota, que é quem sabe de QUEM é o sino ────────────────────────────────────────────────
router = APIRouter()

_WHERE = (
    " n.user_id = CAST(:uid AS uuid) "
    " AND n.is_active "
    " AND n.created_at >= now() - make_interval(days => CAST(:dias AS int)) "
)


def _filtros(payload: dict, uid: str) -> tuple[str, dict]:
    """Monta o WHERE e os parâmetros. ⚠️ CAST explícito em todo `:ref` — sem isso o asyncpg
    levanta `AmbiguousParameterError`."""
    cond = [_WHERE]
    par: dict = {"uid": uid, "dias": int(payload.get("dias") or 7)}
    if (payload.get("so_nao_lidas") or "sim").lower() == "sim":
        cond.append(" AND n.read_at IS NULL ")
    if (payload.get("familia") or "").strip():
        cond.append(" AND n.extra_data->>'familia' = CAST(:fam AS text) ")
        par["fam"] = payload["familia"].strip()
    if (payload.get("severidade") or "").strip():
        cond.append(" AND n.extra_data->>'severidade' = CAST(:sev AS text) ")
        par["sev"] = payload["severidade"].strip()
    return "".join(cond), par


@router.post("/action/alertas-listar")
async def alertas_listar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)
):
    """Os alertas DESTE usuário. `acao=listar` não altera nada; `marcar_lidas` marca o que o
    filtro pegou — e diz quantos, antes e depois."""
    uid = str(getattr(current_user, "id", "") or "")
    if not uid:
        return {"ok": False, "message": "Não consegui identificar quem está pedindo."}
    onde, par = _filtros(payload, uid)
    acao = (payload.get("acao") or "listar").strip().lower()

    if acao == "marcar_lidas":
        n = (
            await db.execute(
                text(
                    "UPDATE communication_notifications n SET read_at = now() "
                    f" WHERE {onde} AND n.read_at IS NULL"
                ),
                par,
            )
        ).rowcount or 0
        await db.commit()
        _log.info("alertas: %s marcou %s como lidas", getattr(current_user, "email", "?"), n)
        return {
            "ok": True,
            "message": f"{n} alerta(s) marcado(s) como lido(s). Isto não apaga nada — eles saem "
                       "da fila de «não lidas» e continuam no histórico.",
        }

    # ── 1. o FORMATO primeiro: quanto há de cada coisa ──
    resumo = (
        await db.execute(
            text(
                "SELECT coalesce(n.extra_data->>'familia','(sem família)') fam, "
                "       coalesce(n.extra_data->>'severidade','—') sev, count(*) n "
                f"  FROM communication_notifications n WHERE {onde} "
                " GROUP BY 1,2 ORDER BY 3 DESC LIMIT 12"
            ),
            par,
        )
    ).all()
    total = (
        await db.execute(
            text(f"SELECT count(*) FROM communication_notifications n WHERE {onde}"), par
        )
    ).scalar() or 0

    # ── 2. só então a lista, com teto ──
    linhas = (
        await db.execute(
            text(
                "SELECT to_char(n.created_at,'DD/MM HH24:MI'), "
                "       coalesce(n.extra_data->>'familia','—'), "
                "       coalesce(n.extra_data->>'severidade','—'), "
                "       coalesce(n.title,'—'), coalesce(n.action_url,''), "
                "       (n.read_at IS NOT NULL) "
                f"  FROM communication_notifications n WHERE {onde} "
                " ORDER BY n.created_at DESC LIMIT " + str(_TETO)
            ),
            par,
        )
    ).all()

    _SEV = {
        "critico": ("Crítico", "bad"),
        "atencao": ("Atenção", "warn"),
        "aviso": ("Aviso", "info"),
        "info": ("Info", "mut"),
    }
    rows = [
        {
            "cells": [
                t(r[0]),
                t(r[1]),
                b(*_SEV.get((r[2] or "").lower(), ((r[2] or "—").capitalize(), "mut"))),
                t(r[3][:110], 600, "#0F1B3A"),
                b("lido", "ok") if r[5] else b("novo", "warn"),
            ]
        }
        for r in linhas
    ]

    cabeca = " · ".join(f"{x[0]}/{x[1]}: {x[2]}" for x in resumo[:6]) or "nada no período"
    corte = (
        f" ⚠️ Mostrando os {_TETO} mais recentes de {total} — estreite o período, a família ou a "
        "severidade para ver o resto."
        if total > _TETO
        else ""
    )
    return {
        "ok": True,
        "message": f"{total} alerta(s) no filtro. Onde está o peso → {cabeca}.{corte}",
        "tabela": {
            "cols": ["Quando", "Família", "Severidade", "O quê", "Estado"],
            # ⚠️ `auto` nas colunas de SELO: o comprimido tem largura FIXA em pixels e fração é
            # proporção — foi assim que um selo cobriu o texto vizinho em 97 px na conferência
            # de kits. E os mínimos têm ORÇAMENTO: mínimo que não cabe é transbordo com outro nome.
            "grid": "minmax(96px,0.8fr) minmax(88px,0.8fr) auto minmax(180px,2.4fr) auto",
            "rows": rows,
        },
    }
