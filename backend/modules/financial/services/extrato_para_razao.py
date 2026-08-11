"""Escritura o extrato bancário no razão — cada movimentação vira UM lançamento.

O problema que resolve (medido em 2026-08-11): o razão conhecia **6%** do
extrato (266 de 4.502) e quase só entradas — 74 baixas de recebimento somando
R$1.399.656,96 sem as saídas correspondentes. Resultado: o razão dizia
R$1.401.547,03 no banco e o banco tinha R$16.826,71.

Lados do lançamento:
  • saída  (amount < 0): D <contrapartida> / C <conta do banco>
  • entrada (amount > 0): D <conta do banco> / C <contrapartida>

Paredes:
  • idempotente por `bank_transaction_id` — relançar dobraria o caixa;
  • pula o que JÁ tem lançamento ligado (266 hoje: `banco_inter`, `baixa_recebimento`);
  • competência futura não entra;
  • `data_lancamento` é NOT NULL: sem data, pula e CONTA como pulado (nunca
    estoura o lote inteiro — foi assim que o fechamento morreu em julho).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date

import psycopg2
import psycopg2.extras

from modules.financial.services.ledger_auto_service import _raw_db_url
from modules.financial.services.plano_contas_caixa import (
    CONTA_BANCO,
    contrapartida_entrada,
    contrapartida_saida,
)

logger = logging.getLogger(__name__)


def ref_do_extrato(bank_transaction_id: str) -> str:
    """Chave natural do lançamento. É o ID da transação e não valor+data porque
    valor+data se repetem legitimamente (3 saques de R$1.000 no mesmo dia)."""
    return f"EXTRATO-{bank_transaction_id}"


def _conn():
    return psycopg2.connect(_raw_db_url())


def escriturar(preview: bool = True, limite: int = 6000) -> dict:
    """Lança no razão toda movimentação bancária que ainda não tem lançamento."""
    conn = _conn()
    hoje = date.today()
    lancados = 0
    valor = 0.0
    pulados: dict[str, int] = defaultdict(int)
    por_conta: dict[str, float] = defaultdict(float)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT b.id::text AS id, b.amount, b.description, b.transaction_date::date AS dia,
                       b.bank_account_id::text AS conta_id, b.justificativa_categoria AS cat,
                       -- empresa vem da CONTA, não da transação: o Inter é da
                       -- Eletrônica e o Cora é da Patrimonial. Sem isso o
                       -- lançamento nasce sem CNPJ e some do balancete escopado.
                       ba.empresa_id::text AS empresa_id
                FROM bank_transactions b
                JOIN bank_accounts ba ON ba.id = b.bank_account_id
                WHERE NOT EXISTS (
                    SELECT 1 FROM accounting_entries a WHERE a.bank_transaction_id = b.id
                )
                ORDER BY b.transaction_date
                LIMIT %s
                """,
                (limite,),
            )
            linhas = cur.fetchall()

            for r in linhas:
                dia = r["dia"]
                if dia is None:
                    pulados["sem_data"] += 1
                    continue
                if (dia.year, dia.month) > (hoje.year, hoje.month):
                    pulados["competencia_futura"] += 1
                    continue
                conta_banco = CONTA_BANCO.get(r["conta_id"] or "")
                if not conta_banco:
                    pulados["conta_bancaria_desconhecida"] += 1
                    continue
                v = float(r["amount"] or 0)
                if v == 0:
                    pulados["valor_zero"] += 1
                    continue

                if v < 0:
                    outra, motivo = contrapartida_saida(r["cat"], r["description"] or "")
                    cd, cc = outra, conta_banco
                else:
                    outra, motivo = contrapartida_entrada(r["description"] or "")
                    cd, cc = conta_banco, outra

                lancados += 1
                valor += abs(v)
                por_conta[outra] = round(por_conta[outra] + abs(v), 2)
                if preview:
                    continue

                hist = (f"Extrato {dia:%d/%m/%Y}: "
                        f"{(r['description'] or '').replace(chr(10), ' ')[:120]} — {motivo}")
                cur.execute(
                    """
                    INSERT INTO accounting_entries
                        (data_lancamento, conta_debito, conta_credito, valor, historico,
                         tipo_lancamento, documento_ref, periodo_competencia, status,
                         empresa_id, bank_transaction_id)
                    SELECT %s, %s, %s, %s, %s, 'extrato_bancario', %s, %s, 'confirmado',
                           %s::uuid, %s::uuid
                    WHERE NOT EXISTS (
                        SELECT 1 FROM accounting_entries WHERE documento_ref = %s
                    )
                    """,
                    (dia, cd, cc, abs(v), hist[:250], ref_do_extrato(r["id"]),
                     f"{dia:%Y-%m}", r["empresa_id"], r["id"], ref_do_extrato(r["id"])),
                )
        if preview:
            conn.rollback()
        else:
            conn.commit()
        return {
            "ok": True,
            "modo": "preview" if preview else "aplicado",
            "lancados": lancados,
            "valor": round(valor, 2),
            "pulados": dict(pulados),
            "por_conta": dict(sorted(por_conta.items(), key=lambda x: -x[1])),
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
