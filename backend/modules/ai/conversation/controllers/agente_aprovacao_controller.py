"""F1 — a porta por onde o pedido BARRADO do agente chega ao humano.

O gate no conector (`mcp-server/gate_propose.py`) impede que ação de classe `propose`
execute pelo agente. Sem esta rota, ele apenas recusa: o Jordan não fica sabendo que foi
pedido, e o pedido morre na conversa. Aqui ele vira rascunho INERTE na Central de
Aprovações, onde um humano decide com o dedo.

A regra que sustenta o desenho: **quem aprova não pode ser quem pede.** A versão anterior
do `aceitar_proposta` pedia `confirmar="ACEITAR"` e imprimia essa senha na própria resposta
— para humano no Cowork era aviso; para um modelo que lê a resposta era um degrau ensinando
a subir. Aqui não há degrau: o propositor é o AGENTE e a decisão acontece em outra
superfície, por outra pessoa.

O que a tela mostra é a CONSEQUÊNCIA, não o nome da função. "Aprovar aceitar_proposta?" não
é decisão informada; "gera comissão, move o deal e cria contrato" é.

⚠️ Esta rota NUNCA executa a ação. Ela grava o pedido. A execução roda só na aprovação, pelo
executor registrado — que é o mesmo caminho de qualquer rascunho do sistema.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from core.logging import logger

router = APIRouter(prefix="/agente", tags=["Agente — aprovações"])

# Espelha `gate_propose.classe_de`: desconhecido é tratado como o mais restritivo.
_GATE_POR_CLASSE = {"propose": "🟡", "write_low": "🔵"}

# Ações que mexem em DINHEIRO ou em ato de governo sobem para 🔴 e exigem OTP na aprovação.
# Lista explícita: herdar isso de heurística de nome é como o manifesto errou por 54 vezes.
_VERMELHAS = {
    "aceitar_proposta",          # gera COMISSÃO
    "lancar_diaria",             # valor a pagar
    "gerar_lote_diarias_mes",    # lote de pagamento
    "registrar_custo_recorrente",
    "fechar_folha",
    "calcular_folha_todos",
    "calcular_verbas_rescisorias",
    "aprovar_ferias",            # evento de eSocial
    "concluir_admissao",         # evento de eSocial
}


@router.post("/pedir-aprovacao")
async def pedir_aprovacao(
    current_user: CurrentActiveUser,
    payload: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Recebe do conector uma ação BARRADA e a grava como rascunho inerte.

    Corpo esperado (montado por `gate_propose.payload_de_aprovacao`):
        acao            nome da ferramenta
        vai_acontecer   lista de consequências, em português
        argumentos      o que o agente ia passar
        classe          read | write_low | propose
    """
    from modules.ai.conversation.services.orquestrador.acoes.rascunho import criar_rascunho

    acao = str(payload.get("acao") or "").strip()
    if not acao:
        raise HTTPException(status_code=400, detail="informe a ação barrada")

    consequencias = [str(c) for c in (payload.get("vai_acontecer") or []) if str(c).strip()]
    if not consequencias:
        # Sem consequência declarada não há aprovação informada — e aprovação não informada
        # é assinatura em papel em branco.
        raise HTTPException(
            status_code=422,
            detail=f"a ação `{acao}` chegou sem consequências declaradas; sem elas o "
                   "aprovador decidiria às cegas")

    vermelha = acao in _VERMELHAS
    gate = "🔴" if vermelha else _GATE_POR_CLASSE.get(
        str(payload.get("classe") or "propose"), "🟡")

    resumo = "O agente pediu esta ação e NÃO a executou. Se aprovada, ela:\n" + "\n".join(
        f"• {c}" for c in consequencias)

    try:
        r = await criar_rascunho(
            db, current_user,
            tipo=f"agente_{acao}",
            modulo=str(payload.get("modulo") or "ai"),
            titulo=f"Aprovação: {acao}",
            resumo=resumo,
            payload={"acao": acao, "argumentos": payload.get("argumentos") or {},
                     "consequencias": consequencias, "origem": "conector-agente"},
            gate=gate,
            requires_otp=vermelha,
            roles_aprovador=("admin",),
            # idempotência: o agente insistindo na mesma ação não vira fila de rascunhos
            idempotency_key=f"agente:{acao}:{sorted((payload.get('argumentos') or {}).items())}",
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("pedir_aprovacao falhou para %s", acao)
        raise HTTPException(status_code=500, detail=f"não consegui registrar o pedido: {e}") from e

    if isinstance(r, dict) and r.get("erro"):
        raise HTTPException(status_code=422, detail=str(r["erro"]))

    return {
        "ok": True,
        "registrado": True,
        "gate": gate,
        "exige_otp": vermelha,
        "rascunho": (r or {}).get("id") if isinstance(r, dict) else None,
        "message": (f"Pedido de `{acao}` registrado na Central de Aprovações "
                    f"({gate}{' · exige OTP' if vermelha else ''}). "
                    "Nada foi executado — um humano decide."),
    }
