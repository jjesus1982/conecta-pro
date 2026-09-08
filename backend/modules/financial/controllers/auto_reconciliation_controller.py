"""
Auto Reconciliation Controller — Conciliação Bancária Automática Inter × Notas.

Endpoints:
  POST /conciliar/auto              — executa conciliação em lote (até 649 txs)
  POST /conciliar/{tx_id}           — concilia transação específica
  GET  /conciliar/pendentes         — lista txs sem conciliação
  POST /conciliar/{tx_id}/justificar — registra justificativa para saída sem nota
  GET  /conciliar/relatorio         — resumo da conciliação
"""

import logging
import os

import psycopg2
import psycopg2.extras
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.auth.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conciliar", tags=["Conciliação Automática Inter"])

DATABASE_URL = os.getenv("DATABASE_URL", "").replace("+asyncpg", "")


def _get_conn():
    return psycopg2.connect(DATABASE_URL)


# ── MODELOS ────────────────────────────────────────────────────────────────────


class JustificativaPayload(BaseModel):
    justificativa: str
    categoria: str | None = None
    responsavel: str | None = None


# ── POST /conciliar/auto ────────────────────────────────────────────────────────


@router.post(
    "/{tx_id}/justificar",
    summary="Registrar justificativa para saída sem nota fiscal",
)
async def justificar_transacao(
    tx_id: str,
    payload: JustificativaPayload,
    _user: dict = Depends(get_current_user),
):
    """
    Registra justificativa para débito sem nota fiscal vinculada.
    Exemplos de categoria: 'despesa_pessoal', 'adiantamento', 'erro_operacional',
    'reembolso', 'taxa_bancaria', 'outros'.
    """
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE bank_transactions SET
            justificativa = %s,
            justificativa_categoria = %s,
            justificativa_responsavel = %s,
            justificativa_data = NOW(),
            reconciliation_status = 'justificado',
            updated_at = NOW()
        WHERE id = %s
          AND requires_justification = TRUE
        RETURNING id
        """,
        (payload.justificativa, payload.categoria, payload.responsavel, tx_id),
    )
    updated = cur.fetchone()
    conn.commit()
    conn.close()

    if not updated:
        raise HTTPException(
            status_code=404,
            detail="Transação não encontrada ou não requer justificativa",
        )
    return {
        "status": "justificado",
        "tx_id": tx_id,
        "justificativa": payload.justificativa,
        "categoria": payload.categoria,
    }


# ── GET /conciliar/relatorio ────────────────────────────────────────────────────


