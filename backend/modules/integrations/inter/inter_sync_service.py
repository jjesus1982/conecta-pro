"""D6.1 — InterSyncService: sincroniza extrato em inter_transactions."""

import json
import logging
import os
from datetime import date, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _build_adapter():
    from modules.integrations.banking.adapters.base import BankCredentials
    from modules.integrations.banking.adapters.inter import InterAdapter

    return InterAdapter(
        BankCredentials(
            client_id=os.getenv("INTER_CLIENT_ID", ""),
            client_secret=os.getenv("INTER_CLIENT_SECRET", ""),
            certificate_path=os.getenv("INTER_CERT_PATH", "/app/credentials/inter/Inter_API_Certificado.crt"),
            private_key_path=os.getenv("INTER_KEY_PATH", "/app/credentials/inter/Inter_API_Chave.key"),
            agency=os.getenv("INTER_AGENCY"),
            account=os.getenv("INTER_ACCOUNT"),
            environment=os.getenv("INTER_ENVIRONMENT", "production"),
        )
    )


class InterSyncService:
    """Sincroniza extrato Inter → inter_transactions (dedup por UNIQUE constraint)."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def sincronizar_extrato(self, dias: int = 7) -> dict[str, Any]:
        """Puxa extrato dos últimos N dias e persiste em inter_transactions.

        Returns:
            {sincronizadas, duplicadas, erros}
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=dias)

        adapter = _build_adapter()
        sincronizadas = 0
        duplicadas = 0
        erros: list[str] = []

        try:
            statement = await adapter.get_statement(start_date, end_date)
        except Exception as exc:
            logger.error("D6.1 falha ao buscar extrato Inter: %s", exc)
            return {"sincronizadas": 0, "duplicadas": 0, "erros": [str(exc)]}
        finally:
            await adapter.close()

        for tx in statement.transactions:
            try:
                tipo_op = "C" if tx.transaction_type and "credit" in str(tx.transaction_type).lower() else "D"
                tipo_tx = str(tx.transaction_type.value) if tx.transaction_type else None
                valor = abs(float(tx.amount)) if tx.amount else 0
                desc = (tx.description or "")[:255]
                dt = tx.date.date() if hasattr(tx.date, "date") else tx.date

                raw_dict = {
                    "transaction_id": tx.transaction_id,
                    "date": str(dt),
                    "amount": float(tx.amount) if tx.amount else None,
                    "transaction_type": tipo_tx,
                    "description": tx.description,
                    "balance_after": float(tx.balance_after) if tx.balance_after else None,
                    "counterpart_name": tx.counterpart_name,
                    "counterpart_document": tx.counterpart_document,
                    "counterpart_bank": tx.counterpart_bank,
                    "counterpart_agency": tx.counterpart_agency,
                    "counterpart_account": tx.counterpart_account,
                    "category": tx.category,
                    "reference": tx.reference,
                }
                detalhes_dict = None
                if tx.counterpart_document or tx.counterpart_name:
                    detalhes_dict = {
                        "cpf_cnpj": tx.counterpart_document,
                        "nome": tx.counterpart_name,
                        "banco": tx.counterpart_bank,
                        "agencia": tx.counterpart_agency,
                        "conta": tx.counterpart_account,
                    }

                await self.db.execute(
                    text("""
                        INSERT INTO inter_transactions
                          (data_lancamento, tipo_operacao, tipo_transacao,
                           valor, descricao, raw_payload, detalhes_destinatario)
                        VALUES
                          (:dt, :op, :tipo, :valor, :desc,
                           CAST(:raw AS jsonb), CAST(:dest AS jsonb))
                        ON CONFLICT ON CONSTRAINT uq_inter_transactions_dedup
                        DO UPDATE SET
                          raw_payload = EXCLUDED.raw_payload,
                          detalhes_destinatario = EXCLUDED.detalhes_destinatario
                        WHERE inter_transactions.raw_payload IS NULL
                    """),
                    {
                        "dt": dt,
                        "op": tipo_op,
                        "tipo": tipo_tx,
                        "valor": valor,
                        "desc": desc,
                        "raw": json.dumps(raw_dict),
                        "dest": json.dumps(detalhes_dict) if detalhes_dict else None,
                    },
                )
                sincronizadas += 1
            except Exception as exc:
                logger.warning("D6.1 erro ao inserir tx: %s", exc)
                erros.append(str(exc))
                duplicadas += 1

        await self.db.commit()
        logger.info("D6.1 sync: sincronizadas=%d duplicadas=%d erros=%d", sincronizadas, duplicadas, len(erros))
        return {"sincronizadas": sincronizadas, "duplicadas": duplicadas, "erros": erros}

    async def listar_transactions(
        self,
        inicio: date | None = None,
        fim: date | None = None,
        tipo_operacao: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Lista inter_transactions com filtros opcionais."""
        where = ["1=1"]
        params: dict[str, Any] = {"limit": limit}

        if inicio:
            where.append("data_lancamento >= :inicio")
            params["inicio"] = inicio
        if fim:
            where.append("data_lancamento <= :fim")
            params["fim"] = fim
        if tipo_operacao:
            where.append("tipo_operacao = :tipo_op")
            params["tipo_op"] = tipo_operacao.upper()

        rows = (
            (
                await self.db.execute(
                    text(f"""
                    SELECT id, data_lancamento, tipo_operacao, tipo_transacao,
                           valor, descricao, created_at
                    FROM inter_transactions
                    WHERE {" AND ".join(where)}
                    ORDER BY data_lancamento DESC
                    LIMIT :limit
                """),
                    params,
                )
            )
            .mappings()
            .all()
        )

        return [dict(r) for r in rows]

    async def resumo(self, dias: int = 30) -> dict:
        """Totais crédito/débito por tipo nos últimos N dias."""
        inicio = date.today() - timedelta(days=dias)
        rows = (
            (
                await self.db.execute(
                    text("""
                    SELECT tipo_operacao, tipo_transacao,
                           COUNT(*) AS qtd, SUM(valor) AS total
                    FROM inter_transactions
                    WHERE data_lancamento >= :inicio
                    GROUP BY tipo_operacao, tipo_transacao
                    ORDER BY tipo_operacao, total DESC
                """),
                    {"inicio": inicio},
                )
            )
            .mappings()
            .all()
        )

        return {
            "periodo_dias": dias,
            "resumo": [dict(r) for r in rows],
        }
