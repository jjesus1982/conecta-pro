"""Webhook Controller — receptor de notificações da Asaas.

Três regras da documentação da Asaas ditam o desenho deste arquivo, e nenhuma delas é
opcional:

1. **A fila é INTERROMPIDA após 15 respostas não-2xx seguidas.** Os eventos continuam
   sendo gerados e param de chegar, e a reativação é manual. Por isso este endpoint
   **sempre responde 200** — uma exceção no nosso código não pode virar 500 e cortar a
   torneira de eventos.
2. **Entrega "at least once":** o mesmo evento pode chegar mais de uma vez. Em vez de
   guardar id de evento processado, seguimos o molde do Cora: o webhook é só GATILHO e
   o estado vem de uma RE-CONSULTA à API. Reprocessar o mesmo evento reescreve o mesmo
   valor — idempotente por construção, sem tabela de deduplicação para manter.
3. **Evento parado há mais de 14 dias é apagado para sempre.** Ou seja, o webhook não
   pode ser a única fonte de verdade: se a fila cair numa sexta, a confirmação some. O
   sincronizador de extrato é a rede de segurança (mesmo papel do beat diário do Cora).

Autenticação: a Asaas manda o header `asaas-access-token` com o valor que cadastramos
ao criar o webhook. Sem `ASAAS_WEBHOOK_TOKEN` no .env o endpoint aceita sem conferir e
AVISA no log — preferível a rejeitar tudo e, sem querer, interromper a fila.
"""

from __future__ import annotations

import hmac
import json
import logging
import os

from fastapi import APIRouter, Header, Request

router = APIRouter(prefix="/webhooks/asaas", tags=["Webhooks — Asaas"])
logger = logging.getLogger(__name__)

#: Evento da Asaas → status de `inter_payments`.
#: `TRANSFER_BLOCKED` vira `executado`, NÃO `erro`: bloqueado é análise em curso e o
#: dinheiro ainda pode sair. Marcar como erro faria alguém pagar de novo.
STATUS_POR_EVENTO = {
    "TRANSFER_CREATED": "executado",
    "TRANSFER_PENDING": "executado",
    "TRANSFER_IN_BANK_PROCESSING": "executado",
    "TRANSFER_BLOCKED": "executado",
    "TRANSFER_DONE": "confirmado",
    "TRANSFER_FAILED": "erro",
    "TRANSFER_CANCELLED": "cancelado",
}


@router.post("")
@router.post("/")
async def receber_webhook_asaas(
    request: Request,
    asaas_access_token: str | None = Header(None, alias="asaas-access-token"),
) -> dict:
    """Recebe o evento da Asaas. SEMPRE 200 — ver regra 1 no topo do arquivo."""
    esperado = (os.getenv("ASAAS_WEBHOOK_TOKEN") or "").strip()
    if esperado:
        # compare_digest: comparação de token em tempo constante.
        if not asaas_access_token or not hmac.compare_digest(asaas_access_token, esperado):
            logger.warning("Webhook Asaas: token inválido — evento ignorado")
            # 200 de propósito: 15 respostas de erro seguidas interrompem a fila, e um
            # atacante batendo com token errado deixaria de quebra o canal legítimo.
            return {"success": True, "ignored": "token inválido"}
    else:
        logger.warning("Webhook Asaas: ASAAS_WEBHOOK_TOKEN não configurado — aceitando "
                       "sem conferir a origem")

    try:
        corpo = await request.json()
    except Exception:  # noqa: BLE001 - corpo ilegível não pode derrubar a fila
        logger.warning("Webhook Asaas: corpo não é JSON")
        return {"success": True, "ignored": "corpo inválido"}

    evento = corpo.get("event") or ""
    logger.info("Webhook Asaas: %s (id=%s)", evento, corpo.get("id"))

    try:
        if evento.startswith("TRANSFER_"):
            await _atualizar_transferencia(evento, corpo.get("transfer") or {})
        # PAYMENT_*: recebimento é pelo Cora. Logado e ignorado de propósito.
    except Exception as exc:  # noqa: BLE001
        logger.warning("Webhook Asaas: falha ao processar %s (%s) — o sincronizador de "
                       "extrato concilia depois", evento, exc)

    return {"success": True}


async def _atualizar_transferencia(evento: str, transfer: dict) -> None:
    """Atualiza o pagamento RE-CONSULTANDO a Asaas — o evento é só o gatilho."""
    from sqlalchemy import text

    from core.database import async_session_factory
    from modules.integrations.banking.adapters.asaas import AsaasAdapter

    tid = transfer.get("id")
    if not tid:
        return

    # Re-consulta: o corpo do webhook diz o que ACONTECEU, a API diz o que É. Se a
    # consulta falhar, cai para o status do evento — melhor que não registrar nada.
    status_asaas = None
    try:
        atual = await AsaasAdapter.from_env().get_payment_status(tid)
        status_asaas = (atual or {}).get("status")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Webhook Asaas: re-consulta de %s falhou (%s) — usando o evento",
                       tid, exc)

    novo = STATUS_POR_EVENTO.get(f"TRANSFER_{status_asaas}" if status_asaas else evento) \
        or STATUS_POR_EVENTO.get(evento)
    if not novo:
        return

    async with async_session_factory() as db:
        r = await db.execute(text(
            "UPDATE inter_payments SET status = :st, "
            # `:conf` em vez de reusar `:st` aqui: o mesmo parâmetro servindo de valor
            # para uma coluna varchar E de operando numa comparação faz o asyncpg
            # desistir ("inconsistent types deduced for parameter $1").
            "confirmed_at = CASE WHEN :conf THEN NOW() ELSE confirmed_at END, "
            # CAST(:resp AS jsonb), não `:resp::jsonb`: o `::` colado no parâmetro faz o
            # SQLAlchemy não reconhecer o bind e o Postgres recebe ":resp" literal.
            "inter_response = COALESCE(inter_response,'{}'::jsonb) || CAST(:resp AS jsonb), "
            "updated_at = NOW() "
            "WHERE inter_payment_id = :tid AND banco = 'asaas'"
        ), {"st": novo, "conf": novo == "confirmado", "tid": tid,
            # json.dumps, não f-string: evento vem de fora e um aspa dupla no valor
            # produziria jsonb inválido — ou pior.
            "resp": json.dumps({"webhook_evento": evento, "webhook_status": status_asaas})})
        await db.commit()

    if r.rowcount == 0:
        # Não é ruído: transferência que a Asaas conhece e nós não é dinheiro saindo
        # por fora do sistema — exatamente o que o extrato tem de pegar.
        logger.warning("Webhook Asaas: transferência %s (%s) não casou com nenhum "
                       "inter_payments — saída fora do sistema?", tid, evento)
    else:
        logger.info("Webhook Asaas: %s → %s (%s linha)", tid, novo, r.rowcount)
