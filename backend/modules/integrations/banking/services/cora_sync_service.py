"""Sync do extrato Cora (conta da CONECTAMAIS PATRIMONIAL) → bank_transactions.

Multi-CNPJ E4 (lado leitura):
- Idempotente por (bank_account_id, external_id) — o `ent_...` do extrato Cora.
- CRÉDITOS conciliam automaticamente contra NFS-e da Patrimonial pelo padrão
  PROVADO com dinheiro real: recebido LÍQUIDO == nfse.valor_liquido (bruto −
  retenções) e tomador compatível → reconciliation_status='conciliado' com a
  nota na reconciliation_note. Sem par exato = 'pendente' (nunca chutar).
- Escopo TOTALMENTE separado do Inter: conta própria (bank_code 403), nenhum
  teto/cache compartilhado; dinheiro-que-sai continua fora (D7).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy import text

logger = logging.getLogger(__name__)

_CONDOMINIO_MATRIZ = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"


def _conta_cora(db) -> dict | None:
    row = db.execute(
        text("SELECT id, account_number FROM bank_accounts WHERE bank_code='403' AND ativo IS NOT FALSE LIMIT 1")
    ).fetchone()
    return {"id": str(row.id), "numero": row.account_number} if row else None


async def _statement(dias: int):
    from modules.integrations.banking.adapters.cora import CoraAdapter

    adapter = CoraAdapter()
    await adapter.authenticate()
    fim = date.today()
    inicio = fim - timedelta(days=dias)
    saldo = await adapter.get_balance()
    extrato = await adapter.get_statement(inicio, fim)
    return saldo, extrato


def sincronizar_extrato_cora(dias: int = 60) -> dict:
    """Puxa saldo+extrato do Cora e persiste/concilia. Sync (roda em task Celery)."""
    import asyncio

    from core.database.session import get_sync_db

    saldo, extrato = asyncio.run(_statement(dias))

    rel = {"saldo": float(saldo.available), "lancamentos_feed": len(extrato.transactions),
           "novos": 0, "conciliados": 0, "pendentes": 0}

    with get_sync_db() as db:
        conta = _conta_cora(db)
        if not conta:
            raise LookupError("Conta Cora (bank_code 403) não registrada em bank_accounts")

        for t in extrato.transactions:
            existe = db.execute(
                text("SELECT 1 FROM bank_transactions WHERE bank_account_id=:acc AND external_id=:ext"),
                {"acc": conta["id"], "ext": t.transaction_id},
            ).fetchone()
            if existe:
                continue

            recon_status, recon_note = "pendente", None
            if t.amount > 0:
                # Conciliação líquido×nota (padrão provado: Mirante 15/07).
                # BLINDAGEM (auditoria 20/07): só concilia se o match for ÚNICO —
                # valor comparado com ROUND(2) (evita fragilidade de float) e
                # contraparte por prefixo. Múltiplos candidatos = deixa PENDENTE
                # (nunca aponta a nota errada). Recall menor > precisão errada.
                candidatos = db.execute(
                    text(
                        "SELECT n.numero, n.tomador_nome, n.valor_servicos FROM nfse_emitidas_nacional n "
                        "JOIN empresas e ON e.id = n.empresa_id "
                        "WHERE e.slug = 'conecta_patrimonial' "
                        "AND ROUND(n.valor_liquido, 2) = ROUND(CAST(:valor AS numeric), 2) "
                        "AND UPPER(LEFT(n.tomador_nome, 15)) = UPPER(LEFT(:contraparte, 15)) "
                        "ORDER BY n.numero"
                    ),
                    {"valor": float(t.amount), "contraparte": (t.counterpart_name or "")[:15]},
                ).fetchall()
                if len(candidatos) == 1:
                    nota = candidatos[0]
                    recon_status = "conciliado"
                    recon_note = (
                        f"NFS-e {nota.numero} ({nota.tomador_nome}) — bruto R${float(nota.valor_servicos):,.2f}, "
                        f"recebido líquido (retenções na fonte)"
                    )
                elif len(candidatos) > 1:
                    recon_note = (
                        f"{len(candidatos)} notas candidatas (mesmo líquido+tomador) — "
                        "conciliação manual (ambíguo, não chuto)"
                    )

            db.execute(
                text(
                    "INSERT INTO bank_transactions "
                    "(id, bank_account_id, transaction_type, category, amount, description, "
                    " transaction_date, status, origin, source_type, external_id, "
                    " counterparty_name, counterparty_document, reconciliation_status, "
                    " reconciliation_note, reconciled_at, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :acc, :ttype, :cat, :amount, :descr, "
                    " :tdate, 'confirmado', 'banking_api', 'cora_extrato', :ext, "
                    " :cp_nome, :cp_doc, :recon, :recon_note, "
                    " CASE WHEN :recon = 'conciliado' THEN NOW() END, NOW(), NOW())"
                ),
                {
                    "acc": conta["id"],
                    "ttype": "credit" if t.amount > 0 else "debit",
                    "cat": "recebimento_cliente" if t.amount > 0 else "pagamento",
                    "amount": float(abs(t.amount)),
                    "descr": f"[CORA] {t.description or t.transaction_type}"[:250],
                    "tdate": t.date.date(),
                    "ext": t.transaction_id,
                    "cp_nome": t.counterpart_name,
                    "cp_doc": t.counterpart_document,
                    "recon": recon_status,
                    "recon_note": recon_note,
                },
            )
            rel["novos"] += 1
            if recon_status == "conciliado":
                rel["conciliados"] += 1
            else:
                rel["pendentes"] += 1
        db.commit()

    logger.info("Cora sync: %s", rel)
    return rel
