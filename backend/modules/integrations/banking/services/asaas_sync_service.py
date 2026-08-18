"""Sincronizador de extrato da Asaas — a rede de segurança do webhook.

Por que existe: a Asaas **interrompe a fila de webhooks após 15 respostas não-2xx
seguidas**, e apaga para sempre evento parado há mais de 14 dias. Ou seja, o webhook
pode calar sem avisar e a confirmação de um pagamento sumir. Quem descobre isso é o
extrato — mesmo papel do beat diário do Cora.

Idempotente por `(bank_account_id, external_id)`, como o `cora_sync_service`.

⚠️ **O formato de um registro NÃO foi confirmado contra dado real.** Em 18/08/2026 a
conta de sandbox tinha `totalCount: 0` (saldo zero; o único pagamento é de cartão e só
liquida em 21/09). Então os campos são lidos com nomes alternativos e o primeiro
registro de cada rodada vai **inteiro** para o log — é assim que a gente descobre o
formato de verdade, em vez de eu inventar nome de campo. Já errei isso duas vezes hoje:
o titular da chave PIX não era `ownerName` e o banco não era `bank`.

Tipos de movimentação documentados: PAYMENT_RECEIVED · PIX_TRANSACTION_CREDIT ·
TRANSFER · PAYMENT_FEE · PAYMENT_REVERSAL · RECEIVABLE_ANTICIPATION_GROSS_CREDIT.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from sqlalchemy import text

logger = logging.getLogger(__name__)

#: A Asaas devolveu 504 no extrato durante o desenvolvimento e 200 logo depois, com a
#: mesma chave. Timeout não pode virar "não houve movimento": isso faria a conciliação
#: concluir que o dinheiro não saiu.
TENTATIVAS = 3
PAGINA = 100  # limite máximo documentado


def _primeiro(d: dict, *nomes: str) -> Any:
    """Primeiro campo presente entre os candidatos — o formato não está confirmado."""
    for n in nomes:
        if d.get(n) not in (None, ""):
            return d[n]
    return None


async def _puxar_pagina(ad, offset: int, inicio: str, fim: str) -> dict:
    ultimo: Exception | None = None
    for tent in range(1, TENTATIVAS + 1):
        try:
            async with ad._client() as cli:
                r = await cli.get("/financialTransactions", headers=ad._headers(),
                                  params={"offset": offset, "limit": PAGINA,
                                          "startDate": inicio, "finishDate": fim},
                                  timeout=120.0)
            if r.status_code == 200:
                return r.json() or {}
            ultimo = RuntimeError(f"HTTP {r.status_code}: {r.text[:160]}")
        except httpx.TransportError as exc:
            ultimo = exc
        logger.warning("Asaas extrato: tentativa %s/%s falhou (%s)", tent, TENTATIVAS, ultimo)
    # Levanta em vez de devolver vazio: extrato vazio por falha de rede seria lido como
    # "não houve movimento", que é pior que não ter extrato.
    raise RuntimeError(f"extrato Asaas indisponível após {TENTATIVAS} tentativas: {ultimo}")


def sincronizar_extrato_asaas(dias: int = 30) -> dict:
    """Puxa saldo + extrato da Asaas e persiste em `bank_transactions`. Sync (Celery)."""
    import asyncio
    from datetime import date, timedelta

    from core.database.session import get_sync_db
    from modules.integrations.banking.adapters.asaas import AsaasAdapter

    fim = date.today()
    inicio = fim - timedelta(days=dias)
    ad = AsaasAdapter.from_env()

    async def _tudo():
        saldo = await ad.get_balance()
        itens, offset = [], 0
        while True:
            pag = await _puxar_pagina(ad, offset, inicio.isoformat(), fim.isoformat())
            itens.extend(pag.get("data") or [])
            if not pag.get("hasMore"):
                break
            offset += PAGINA
        return saldo, itens

    saldo, itens = asyncio.run(_tudo())
    rel = {"saldo": float(saldo.available), "no_feed": len(itens), "novos": 0, "ja_tinha": 0}

    if itens:
        # O formato real, uma vez por rodada. É como se descobre o nome dos campos sem
        # inventar — ver o aviso no topo do arquivo.
        logger.info("Asaas extrato: formato do 1º registro: %s",
                    json.dumps(itens[0], ensure_ascii=False)[:700])

    with get_sync_db() as db:
        conta = db.execute(text(
            "SELECT id FROM bank_accounts WHERE bank_code='461' AND ativo IS NOT FALSE LIMIT 1"
        )).fetchone()
        if not conta:
            # Falha clara em vez de criar conta sozinho: conta bancária nasce por decisão
            # do Jordan, e uma criada por engano recebe lançamento que não é dela.
            raise LookupError("Conta Asaas (bank_code 461) não registrada em bank_accounts")
        acc = conta[0]

        for t in itens:
            ext = str(_primeiro(t, "id", "transactionId", "externalReference") or "")
            if not ext:
                logger.warning("Asaas extrato: registro sem identificador — ignorado: %s",
                               json.dumps(t, ensure_ascii=False)[:200])
                continue
            if db.execute(text("SELECT 1 FROM bank_transactions WHERE bank_account_id=:a "
                               "AND external_id=:e"), {"a": acc, "e": ext}).fetchone():
                rel["ja_tinha"] += 1
                continue

            valor = _primeiro(t, "value", "amount") or 0
            tipo = (_primeiro(t, "type", "transactionType") or "").upper()
            db.execute(text(
                "INSERT INTO bank_transactions "
                "(id, bank_account_id, transaction_type, category, amount, description, "
                " transaction_date, status, origin, source_type, external_id, "
                " reconciliation_status, raw_data, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :acc, :ttype, :cat, :amount, :descr, "
                " :tdate, 'confirmado', 'banking_api', 'asaas_extrato', :ext, "
                " 'pendente', CAST(:raw AS jsonb), NOW(), NOW())"
            ), {
                "acc": acc,
                "ttype": "credito" if float(valor) >= 0 else "debito",
                "cat": tipo[:50] or "asaas",
                "amount": valor,
                "descr": (_primeiro(t, "description", "descricao") or tipo or "Asaas")[:255],
                "tdate": _primeiro(t, "date", "paymentDate", "dateCreated"),
                "ext": ext[:120],
                # CAST(... AS jsonb), nunca `::jsonb` colado no parâmetro: o `::` faz o
                # SQLAlchemy não reconhecer o bind (custou um webhook que devolvia 200
                # enquanto falhava por dentro).
                "raw": json.dumps(t, ensure_ascii=False),
            })
            rel["novos"] += 1

        db.execute(text("UPDATE bank_accounts SET current_balance=:s, available_balance=:s, "
                        "updated_at=NOW() WHERE id=:a"), {"s": rel["saldo"], "a": acc})
        db.commit()

    logger.info("Asaas extrato: %s no feed, %s novos, %s já tinha, saldo R$%.2f",
                rel["no_feed"], rel["novos"], rel["ja_tinha"], rel["saldo"])
    return rel
