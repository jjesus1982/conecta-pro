"""DGX Z6 — «Bartolo — tire sua dúvida»: o apoio dentro do fluxo fiscal (24/09/2026).

O dono: *«e o Bartolo como chat dando o apoio nisso, tirando dúvidas, etc.»* — no fluxo de
emissão de nota fiscal da onda 8.

**Não nasce chat novo.** Bartolo é o nome que o dono dá ao assistente que a casa já tem: o
`POST /consultores/chat/consultar` do `consultor_escopado_controller`, com a lente `fiscal`.
A ação daqui CHAMA essa rota in-process (`consultar(ConsultarIn(...), db, user)`), e não uma
cópia dela — um cérebro só, as mesmas tools, o mesmo RBAC, a mesma regra de honestidade. Se um
dia a lente mudar, esta tela muda junto sem ninguém lembrar dela.

**O que esta tela acrescenta** é a PORTA: capacidade que só existe no terminal não existe para o
dono. Aqui ele clica uma das 10 perguntas frequentes — as mesmas 10 do §1 do relatório, feitas
pela rota real antes e depois da frente — ou escreve a dele.

**Sem prefixo `_` de propósito** (mesma decisão da Z5): o discovery do `redesign_data_controller`
pula módulos com `_`, e é ele que monta o `router` daqui. Assim a ação entra sozinha, sem
disputar o nome `router` no `fiscal.py` com as frentes Z1/Z3/Z5 desta mesma onda. Sem `SLUG`,
sem `build` e sem `EXTRA_MENU` aqui: a aba e a chamada de `telas()` ficam no `fiscal.py`, em
2 linhas.

**Só leitura.** Esta frente não emite, não assina, não transmite, não cancela e não inutiliza
documento fiscal, e não cria tabela nenhuma (não há `_ensure`: não há DDL a aplicar). O único
efeito de escrita no caminho é o registro de conversa que o próprio motor do chat já fazia
antes desta frente existir.
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

logger = logging.getLogger(__name__)

TELA = "bartolo-fiscal"
LABEL = "Bartolo — tire sua dúvida"
#: Ícone de balão de conversa (o mesmo vocabulário visual do «Consultor fiscal»).
ICON = "M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"

#: Item de menu — o `fiscal.py` o acrescenta ao seu `EXTRA_MENU` (grupo «Notas fiscais»,
#: onde moram as telas da onda 8).
MENU = {"id": TELA, "label": LABEL, "icon": ICON, "grupo": "Notas fiscais"}

#: As 10 perguntas do §1 do relatório `auditoria/frentes/DGX_Z6_bartolo.md`. Elas estão aqui,
#: e não num arquivo de texto à parte, porque são a MEDIDA da frente: foram feitas pela rota
#: real antes do código existir (a linha de base) e depois (a prova). Mudar uma aqui sem
#: refazer as duas medições torna o relatório mentiroso.
FREQUENTES: tuple[str, ...] = (
    "Qual NCM devo usar para fita isolante?",
    "Por que a NF-e número 2 foi rejeitada?",
    "Posso vender material para o Ideal Flores com ICMS desonerado?",
    "Qual CFOP para venda de material dentro do Amazonas?",
    "Quantas NF-e de saída existem e qual o status de cada uma?",
    "O produto de código VTV-121 está com NCM válido para eu emitir nota?",
    "Qual a alíquota de ICMS numa venda de material da Conecta Eletrônica para um cliente em Manaus?",
    "Tenho um orçamento aprovado; o que falta para ele virar NF-e?",
    "A Conecta Patrimonial, que é do Simples Nacional, usa CST ou CSOSN na NF-e de material?",
    'O que significa a rejeição "Informado NCM inexistente" e como eu corrijo?',
)


def _tela() -> dict:
    return {
        "title": LABEL,
        "sub": (
            "Dúvida de nota fiscal de material — NCM, CFOP, CST/CSOSN, tributação, rejeição, "
            "orçamento que vira nota. Ele lê as notas, o cadastro de produto e a tabela oficial "
            "de NCM da casa. É consulta: não emite, não assina, não transmite e não cancela "
            "nada. Quando não souber, ele diz que não sabe — nunca inventa NCM, alíquota ou CFOP."
        ),
        "cta": "Perguntar ao Bartolo",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/redesign/action/bartolo-perguntar",
            "okMsg": "Bartolo respondeu.",
            "showResult": True,
        },
        "fields": [
            {
                "key": "frequente",
                "label": "Perguntas frequentes (clique numa)",
                "type": "select",
                "span": "span 2",
                "ph": "Escolha uma — ou escreva a sua no campo abaixo",
                "options": [{"value": p, "label": p} for p in FREQUENTES],
            },
            {
                "key": "pergunta",
                "label": "Ou escreva a sua pergunta",
                "type": "textarea",
                "span": "span 2",
                "ph": "Ex.: o NCM 85365090 serve para o smart interruptor que vou faturar?",
            },
        ],
    }


async def telas(db, out: dict | None = None) -> dict:
    """A tela é estática (form). `db` entra pela assinatura que o `fiscal.py` chama."""
    return {TELA: _tela()}


# ───────────────────────── ação (POST /api/v1/redesign/action/…) ─────────────────────────
router = APIRouter()


@router.post("/action/bartolo-perguntar")
async def rd_bartolo_perguntar(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Pergunta ao Bartolo pela MESMA rota do chat, com a lente fiscal.

    O texto livre vence a pergunta frequente (quem escreveu, escreveu de propósito). Sem
    nenhum dos dois, a tela recusa em vez de perguntar coisa nenhuma ao modelo.

    A resposta vai em `message` porque é ali que o painel do redesign renderiza texto longo
    com quebra de linha; o painel «Resultado» recebe só os escalares. O §5 do relatório diz
    qual diff de `frontend/` deixaria isso melhor.
    """
    from modules.ai.conversation.controllers.consultor_escopado_controller import (
        ConsultarIn,
        consultar,
    )

    pergunta = str(payload.get("pergunta") or "").strip() or str(payload.get("frequente") or "").strip()
    if len(pergunta) < 3:
        return {"ok": False, "message": "Escreva a sua pergunta ou escolha uma das frequentes."}

    t0 = time.time()
    try:
        out = await consultar(ConsultarIn(pergunta=pergunta, persona="fiscal"), db=db, user=current_user)
    except Exception as exc:  # noqa: BLE001 — erro do motor é erro visível, nunca resposta vazia
        logger.error("dgx z6: bartolo falhou: %s", exc, exc_info=True)
        return {
            "ok": False,
            "message": f"O Bartolo não conseguiu responder ({type(exc).__name__}). "
            f"O erro está no log do backend. Nada foi emitido nem alterado.",
        }

    resposta = str(out.get("resposta") or "").strip()
    return {
        "ok": bool(resposta),
        "message": resposta or "O Bartolo não devolveu resposta. Tente de novo em instantes.",
        "pergunta": pergunta,
        "segundos": round(time.time() - t0, 1),
        "modelo": out.get("modelo") or "—",
        "ancorada_em_dado_real": bool(out.get("grounded")),
        "aviso": out.get("disclaimer") or "",
    }
