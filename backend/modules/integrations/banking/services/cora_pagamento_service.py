"""Pagamentos da Patrimonial pela conta CORA (Multi-CNPJ E4) — serviço ISOLADO.

Não toca no fluxo do Inter (crítico, da Eletrônica). Cobre o que a API do Cora
suporta: pagar BOLETO (linha digitável) e GUIAS DARF/GPS. PIX por chave NÃO
existe no Cora (§4.4) → folha/diaristas seguem no "pago pelo app + conciliação"
(cora_sync_service + webhook).

Modelo de gate (dinheiro que sai):
  1. gate OTP do ERP (regra da casa) — CHAMADOR valida antes.
  2. adapter inicia → Cora devolve INITIATED.
  3. até o D7 (auto-aprovação) cair, o Jordan APROVA NO APP; o webhook
     payment.approved/completed concilia sozinho (já implementado).
Persistimos o pagamento em bank_transactions (external_id = pay_...) para o
webhook casar e o ERP acompanhar — nunca simula liquidação.
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import text

logger = logging.getLogger(__name__)


async def _conta_e_empresa(db):
    row = (await db.execute(text(
        "SELECT ba.id, e.id AS emp_id FROM bank_accounts ba "
        "JOIN empresas e ON e.slug = 'conecta_patrimonial' "
        "WHERE ba.bank_code='403' LIMIT 1"
    ))).fetchone()
    if not row:
        raise LookupError("conta Cora (403) não registrada em bank_accounts")
    return str(row.id), str(row.emp_id)


async def _registrar(db, conta_id: str, pay: dict, tipo: str, descricao: str):
    """Grava o pagamento iniciado como bank_transaction pendente (webhook atualiza)."""
    pay_id = pay.get("id") or (pay.get("data") or {}).get("id") or ""
    amount = int(pay.get("amount") or (pay.get("data") or {}).get("amount") or 0) / 100
    await db.execute(
        text(
            "INSERT INTO bank_transactions "
            "(id, bank_account_id, transaction_type, category, amount, description, "
            " transaction_date, status, origin, source_type, external_id, "
            " reconciliation_status, reconciliation_note, created_at, updated_at) "
            "VALUES (gen_random_uuid(), :acc, 'debit', :cat, :amt, :descr, CURRENT_DATE, "
            " 'pendente', 'api', 'cora_pagamento', :ext, 'pendente', "
            " 'Iniciado via Cora — aguardando aprovacao no app (INITIATED)', NOW(), NOW())"
        ),
        {"acc": conta_id, "cat": tipo, "amt": amount, "descr": descricao[:250], "ext": pay_id},
    )
    await db.commit()
    return pay_id, amount


async def pagar_boleto(db, *, linha_digitavel: str, descricao: str, code: str,
                       agendar_para: date | None = None) -> dict:
    """Inicia pagamento de boleto pela Cora (Patrimonial). Retorna INITIATED."""
    from modules.integrations.banking.adapters.cora import CoraAdapter

    conta_id, _ = await _conta_e_empresa(db)
    cora = CoraAdapter()
    await cora.authenticate()
    pay = await cora.iniciar_pagamento_boleto(linha_digitavel=linha_digitavel, code=code, agendar_para=agendar_para)
    pay_id, amount = await _registrar(db, conta_id, pay, "pagamento", descricao)
    logger.info("Cora pagamento boleto INICIADO %s (R$%.2f) — aguardando app", pay_id, amount)
    return {"payment_id": pay_id, "valor": amount, "status": "aguardando_aprovacao_app",
            "banco": "cora", "raw": pay}


async def pagar_guia(db, *, tipo: str, data: dict, descricao: str, code: str) -> dict:
    """Inicia DARF (tipo='darf') ou GPS (tipo='gps') pela Cora. Retorna INITIATED."""
    from modules.integrations.banking.adapters.cora import CoraAdapter

    conta_id, _ = await _conta_e_empresa(db)
    cora = CoraAdapter()
    await cora.authenticate()
    if tipo == "darf":
        pay = await cora.iniciar_darf(code=code, data=data)
    elif tipo == "gps":
        pay = await cora.iniciar_gps(code=code, data=data)
    else:
        raise ValueError(f"tipo de guia não suportado ainda: {tipo}")
    pay_id, amount = await _registrar(db, conta_id, pay, "tributo", descricao)
    logger.info("Cora %s INICIADO %s (R$%.2f) — aguardando app", tipo, pay_id, amount)
    return {"payment_id": pay_id, "valor": amount, "status": "aguardando_aprovacao_app",
            "banco": "cora", "raw": pay}


async def transferir(db, *, destination: dict, valor_centavos: int, descricao: str, code: str,
                     category: str | None = None, scheduled: str | None = None) -> dict:
    """TED da Patrimonial pela Cora (§4.4) — por dados bancários (o Cora NÃO envia PIX).
    `destination` conforme adapter.iniciar_transferencia. `valor_centavos` em CENTAVOS.
    Retorna INITIATED — o Jordan APROVA NO APP Cora; o webhook concilia. Nunca simula liquidação."""
    from modules.integrations.banking.adapters.cora import CoraAdapter

    conta_id, _ = await _conta_e_empresa(db)
    cora = CoraAdapter()
    await cora.authenticate()
    pay = await cora.iniciar_transferencia(destination=destination, amount=valor_centavos,
                                           code=code, description=descricao, category=category,
                                           scheduled=scheduled)
    pay_id, amount = await _registrar(db, conta_id, pay, "transferencia", descricao)
    logger.info("Cora TED INICIADA %s (R$%.2f) — aguardando app", pay_id, amount)
    return {"payment_id": pay_id, "valor": amount, "status": "aguardando_aprovacao_app",
            "banco": "cora", "raw": pay}
