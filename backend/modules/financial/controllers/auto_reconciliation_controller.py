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


