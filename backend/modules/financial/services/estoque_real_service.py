"""
EstoqueRealService — estoque REAL a partir das NF-e de entrada (nfe_compras_estoque).

Entrada: já populada pelo nfe_entrada_sync_service (itens dos procNFe → nfe_compras_estoque).
Saída: baixa por vínculo material↔serviço quando se emite/registra um serviço. Cada baixa:
  1. reduz qty_on_hand do item,
  2. registra em nfe_estoque_movimentos (histórico auditável),
  3. posta o CUSTO (COGS) no razão accounting_entries: D 4.1.3.01 (Custo de Materiais) /
     C 1.1.4.01 (Estoque), alimentando o DRE (despesa) → elo com o Financeiro.

NUNCA fabrica: custo = avg_cost real do item; saldo insuficiente é barrado.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import date
from decimal import Decimal

import psycopg2

logger = logging.getLogger(__name__)

EMPRESA_PRINCIPAL_ID = "619a3df1-8bce-49ce-b77a-04f80a0e8491"


def _db_url() -> str:
    return re.sub(r"\+asyncpg|\+psycopg2?", "", os.getenv("DATABASE_URL", ""))


def _num(v) -> float:
    return float(v) if isinstance(v, (Decimal, int, float)) else 0.0


class EstoqueRealService:
    def _conn(self):
        return psycopg2.connect(_db_url())

    def _ensure(self, cur) -> None:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS nfe_estoque_movimentos (
                id SERIAL PRIMARY KEY,
                item_code VARCHAR, descricao TEXT, tipo VARCHAR,
                quantidade NUMERIC, custo_unitario NUMERIC, valor_total NUMERIC,
                servico_ref VARCHAR, nfse_id UUID, motivo TEXT,
                empresa_id UUID, data_mov DATE DEFAULT CURRENT_DATE,
                created_at TIMESTAMP DEFAULT NOW()
            )
            """
        )

    # ------------------------------------------------------------- leitura --
    def listar_itens(self, busca: str | None = None) -> list[dict]:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                q = ("SELECT item_code, descricao, ncm, unidade, qty_on_hand, avg_cost, "
                     "last_purchase_date, last_nfe_key FROM nfe_compras_estoque")
                params: list = []
                if busca:
                    q += " WHERE descricao ILIKE %s OR item_code ILIKE %s"
                    params = [f"%{busca}%", f"%{busca}%"]
                q += " ORDER BY (qty_on_hand*avg_cost) DESC NULLS LAST"
                cur.execute(q, params)
                out = []
                for r in cur.fetchall():
                    qoh, avg = _num(r[4]), _num(r[5])
                    out.append({
                        "item_code": r[0], "descricao": r[1], "ncm": r[2], "unidade": r[3],
                        "qty_on_hand": qoh, "avg_cost": round(avg, 2),
                        "valor_total": round(qoh * avg, 2),
                        "last_purchase_date": str(r[6]) if r[6] else None,
                        "last_nfe_key": r[7],
                    })
                return out
        finally:
            conn.close()

    def resumo(self) -> dict:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                self._ensure(cur)
                cur.execute(
                    "SELECT count(*), COALESCE(sum(qty_on_hand*avg_cost),0), COALESCE(sum(qty_on_hand),0) "
                    "FROM nfe_compras_estoque"
                )
                n_itens, valor, unidades = cur.fetchone()
                cur.execute(
                    "SELECT COALESCE(sum(valor_total),0), count(*) FROM nfe_estoque_movimentos "
                    "WHERE tipo='saida' AND to_char(data_mov,'YYYY-MM')=to_char(CURRENT_DATE,'YYYY-MM')"
                )
                saidas_valor, saidas_qtd = cur.fetchone()
                cur.execute("SELECT count(*) FROM nfe_compras_estoque WHERE qty_on_hand <= 0")
                zerados = cur.fetchone()[0]
                return {
                    "total_itens": n_itens,
                    "valor_total_estoque": round(_num(valor), 2),
                    "unidades_total": round(_num(unidades), 2),
                    "itens_zerados": zerados,
                    "saidas_mes_valor": round(_num(saidas_valor), 2),
                    "saidas_mes_qtd": saidas_qtd,
                }
        finally:
            conn.close()

    def listar_movimentos(self, limite: int = 100) -> list[dict]:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                self._ensure(cur)
                cur.execute(
                    "SELECT id, item_code, descricao, tipo, quantidade, custo_unitario, valor_total, "
                    "servico_ref, motivo, data_mov FROM nfe_estoque_movimentos "
                    "ORDER BY created_at DESC LIMIT %s",
                    (limite,),
                )
                return [{
                    "id": r[0], "item_code": r[1], "descricao": r[2], "tipo": r[3],
                    "quantidade": _num(r[4]), "custo_unitario": round(_num(r[5]), 2),
                    "valor_total": round(_num(r[6]), 2), "servico_ref": r[7],
                    "motivo": r[8], "data": str(r[9]) if r[9] else None,
                } for r in cur.fetchall()]
        finally:
            conn.close()

    # -------------------------------------------------------------- escrita --
    def registrar_saida(self, item_code: str, quantidade: float, servico_ref: str | None = None,
                        motivo: str | None = None, nfse_id: str | None = None,
                        empresa_id: str = EMPRESA_PRINCIPAL_ID) -> dict:
        """Baixa de material vinculada a um serviço/NFS-e. Reduz saldo, registra movimento
        e posta o custo (COGS) no razão. Barra saldo insuficiente."""
        q = float(quantidade)
        if q <= 0:
            raise ValueError("Quantidade deve ser maior que zero.")
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                self._ensure(cur)
                cur.execute(
                    "SELECT descricao, qty_on_hand, avg_cost FROM nfe_compras_estoque WHERE item_code=%s",
                    (item_code,),
                )
                row = cur.fetchone()
                if not row:
                    raise ValueError("Item não encontrado no estoque.")
                desc, qoh, avg = row[0], _num(row[1]), _num(row[2])
                if q > qoh:
                    raise ValueError(f"Saldo insuficiente: {qoh:g} disponível(is), {q:g} solicitado(s).")
                valor = round(q * avg, 2)

                cur.execute(
                    "UPDATE nfe_compras_estoque SET qty_on_hand = qty_on_hand - %s, updated_at=NOW() "
                    "WHERE item_code=%s",
                    (q, item_code),
                )
                cur.execute(
                    "INSERT INTO nfe_estoque_movimentos "
                    "(item_code, descricao, tipo, quantidade, custo_unitario, valor_total, "
                    " servico_ref, nfse_id, motivo, empresa_id) "
                    "VALUES (%s,%s,'saida',%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                    (item_code, desc, q, avg, valor, servico_ref, nfse_id, motivo, empresa_id),
                )
                mov_id = cur.fetchone()[0]

                # COGS no razão (D Custo de Materiais / C Estoque) — idempotente por documento_ref
                ref = f"SAIDA-EST-{mov_id}"
                hist = f"Baixa estoque: {str(desc)[:60]} x{q:g}"
                if servico_ref:
                    hist += f" (serviço: {servico_ref})"
                cur.execute(
                    "INSERT INTO accounting_entries "
                    "(data_lancamento, conta_debito, conta_credito, valor, historico, "
                    " tipo_lancamento, documento_ref, periodo_competencia, status, empresa_id) "
                    "SELECT CURRENT_DATE, '4.1.3.01', '1.1.4.01', %s, %s, 'baixa_estoque', %s, "
                    " to_char(CURRENT_DATE,'YYYY-MM'), 'confirmado', %s "
                    "WHERE NOT EXISTS (SELECT 1 FROM accounting_entries WHERE documento_ref=%s)",
                    (valor, hist[:250], ref, empresa_id, ref),
                )
                conn.commit()
                return {
                    "ok": True, "movimento_id": mov_id, "item": desc, "item_code": item_code,
                    "quantidade": q, "custo_unitario": round(avg, 2), "custo_total": valor,
                    "saldo_restante": round(qoh - q, 4), "lancamento_cogs": ref,
                }
        finally:
            conn.close()
