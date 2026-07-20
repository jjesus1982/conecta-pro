"""
Dashboard Fiscal-Financeiro — Conecta PRO
Integra: NFS-e + NF-e + Inter + Folha + Estoque + DRE
Base para declaração Lucro Real / Receita Federal
"""

import logging
import os
from datetime import datetime

import psycopg2

logger = logging.getLogger(__name__)
DATABASE_URL = os.getenv("DATABASE_URL", "").replace("+asyncpg", "")

# Apuração fiscal É por CNPJ (Lucro Real × Simples). Default = Eletrônica (Lucro Real),
# dona deste dashboard. Multi-CNPJ: um dia a Patrimonial passa o próprio empresa_id.
EMPRESA_PRINCIPAL_ID = "619a3df1-8bce-49ce-b77a-04f80a0e8491"


def _get_conn():
    return psycopg2.connect(DATABASE_URL)


def get_dashboard_fiscal(mes: int, ano: int, empresa_id: str = EMPRESA_PRINCIPAL_ID) -> dict:
    """
    Retorna dashboard fiscal-financeiro completo para o período, ESCOPADO por empresa
    (apuração é por CNPJ — não mistura Lucro Real com Simples).
    """
    conn = _get_conn()
    cur = conn.cursor()

    try:
        # CNPJ da empresa (para a NF-e produto por emitente) — resolvido do empresa_id,
        # sem hardcode. Não achou => string vazia (casa 0 NF-e).
        cur.execute(
            "SELECT regexp_replace(COALESCE(cnpj,''),'[^0-9]','','g') FROM empresas WHERE id = %s",
            (empresa_id,),
        )
        _row = cur.fetchone()
        cnpj_emp = _row[0] if _row and _row[0] else ""
        # ------------------------------------------------------------------
        # 1. RECEITAS — NFS-e emitidas (saída)
        #    Fonte autoritativa: nfse_emitidas_nacional (todas validas cStat 100).
        #    Filtro mensal pela coluna `competencia` (varchar 'YYYY-MM').
        #    Colunas reais: valor_servicos, iss_valor
        # ------------------------------------------------------------------
        cur.execute(
            """
            SELECT
                COUNT(*) AS qtd,
                COALESCE(SUM(valor_servicos), 0) AS total,
                COALESCE(SUM(iss_valor), 0) AS total_iss
            FROM nfse_emitidas_nacional
            WHERE CAST(substr(competencia, 6, 2) AS int) = %s
              AND CAST(left(competencia, 4)   AS int) = %s
              AND empresa_id = %s
            """,
            (mes, ano, empresa_id),
        )
        r = cur.fetchone()
        receita_servicos = {"qtd_nfse": r[0], "valor": float(r[1]), "iss": float(r[2])}

        # ------------------------------------------------------------------
        # 2. RECEITAS — NF-e vendas emitidas
        #    Colunas reais: valor_total_nota, emitente_cnpj
        # ------------------------------------------------------------------
        cur.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(valor_total_nota), 0)
            FROM nfes
            WHERE EXTRACT(MONTH FROM data_emissao) = %s
              AND EXTRACT(YEAR  FROM data_emissao) = %s
              AND status = 'autorizada'
              AND regexp_replace(COALESCE(emitente_cnpj,''),'[^0-9]','','g') = %s
            """,
            (mes, ano, cnpj_emp),
        )
        r = cur.fetchone()
        receita_vendas = {"qtd_nfe": r[0], "valor": float(r[1])}

        total_receitas = receita_servicos["valor"] + receita_vendas["valor"]

        # ------------------------------------------------------------------
        # 3. DESPESAS — NFS-e recebidas (tomadas)
        #    Fonte autoritativa: nfse_tomadas_nacional (competencia 'YYYY-MM').
        #    Colunas reais: valor_servicos, competencia
        # ------------------------------------------------------------------
        cur.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(valor_servicos), 0)
            FROM nfse_tomadas_nacional
            WHERE CAST(substr(competencia, 6, 2) AS int) = %s
              AND CAST(left(competencia, 4)   AS int) = %s
              AND empresa_id = %s
            """,
            (mes, ano, empresa_id),
        )
        r = cur.fetchone()
        despesa_servicos = {"qtd": r[0], "valor": float(r[1])}

        # ------------------------------------------------------------------
        # 4. DESPESAS — NF-e compras recebidas
        #    Colunas reais: created_at, valor_total
        # ------------------------------------------------------------------
        cur.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(valor_total), 0)
            FROM nfe_entradas
            WHERE EXTRACT(MONTH FROM created_at) = %s
              AND EXTRACT(YEAR  FROM created_at) = %s
              AND empresa_id = %s
            """,
            (mes, ano, empresa_id),
        )
        r = cur.fetchone()
        despesa_material = {"qtd": r[0], "valor": float(r[1])}

        # ------------------------------------------------------------------
        # 5. DESPESAS — Folha de pagamento
        #    Colunas reais: reference_month, reference_year
        # ------------------------------------------------------------------
        cur.execute(
            """
            SELECT
                COALESCE(SUM(total_earnings),   0) AS proventos,
                COALESCE(SUM(total_deductions), 0) AS descontos,
                COALESCE(SUM(net_salary),       0) AS liquido,
                COUNT(*)                            AS funcionarios
            FROM hr_payslips
            WHERE reference_month = %s
              AND reference_year  = %s
            """,
            (mes, ano),
        )
        r = cur.fetchone()
        folha = {
            "proventos": float(r[0]),
            "descontos": float(r[1]),
            "liquido": float(r[2]),
            "funcionarios": r[3],
        }

        total_despesas = despesa_servicos["valor"] + despesa_material["valor"] + folha["proventos"]

        # ------------------------------------------------------------------
        # 6. DRE SIMPLIFICADO — Lucro Real
        # ------------------------------------------------------------------
        resultado_bruto = total_receitas - total_despesas
        irpj_base = max(0, resultado_bruto)
        irpj = irpj_base * 0.15
        irpj_adicional = max(0, irpj_base - 20000) * 0.10
        csll = irpj_base * 0.09
        resultado_liquido = resultado_bruto - irpj - irpj_adicional - csll

        dre = {
            "receita_bruta": total_receitas,
            "receita_servicos": receita_servicos["valor"],
            "receita_vendas": receita_vendas["valor"],
            "deducoes_iss": receita_servicos["iss"],
            "receita_liquida": total_receitas - receita_servicos["iss"],
            "despesa_folha": folha["proventos"],
            "despesa_servicos_tomados": despesa_servicos["valor"],
            "despesa_material": despesa_material["valor"],
            "total_despesas": total_despesas,
            "resultado_bruto": resultado_bruto,
            "irpj_estimado": round(irpj + irpj_adicional, 2),
            "csll_estimado": round(csll, 2),
            "resultado_liquido": round(resultado_liquido, 2),
        }

        # ------------------------------------------------------------------
        # 7. CONTAS A PAGAR PENDENTES
        #    Colunas reais: net_value, due_date, status='pendente'
        # ------------------------------------------------------------------
        cur.execute(
            """
            SELECT
                COUNT(*),
                COALESCE(SUM(net_value), 0),
                COUNT(CASE WHEN due_date < CURRENT_DATE THEN 1 END)
            FROM payable_accounts
            WHERE status = 'pendente'
              AND ativo IS NOT FALSE
            """,
        )
        r = cur.fetchone()
        payables = {"total": r[0], "valor": float(r[1]), "vencidas": r[2]}

        # ------------------------------------------------------------------
        # 8. CONTAS A RECEBER PENDENTES
        #    Colunas reais: net_value, due_date, status='pendente'
        # ------------------------------------------------------------------
        cur.execute(
            """
            SELECT
                COUNT(*),
                COALESCE(SUM(net_value), 0),
                COUNT(CASE WHEN due_date < CURRENT_DATE THEN 1 END)
            FROM receivable_accounts
            WHERE status = 'pendente'
              AND ativo IS NOT FALSE
              AND deleted_at IS NULL
            """,
        )
        r = cur.fetchone()
        receivables = {"total": r[0], "valor": float(r[1]), "vencidas": r[2]}

        # ------------------------------------------------------------------
        # 9. FLUXO DE CAIXA — Banco Inter
        #    Colunas reais: transaction_type ('credit'/'debit'), amount, transaction_date
        #    Débitos já armazenados como valores negativos
        # ------------------------------------------------------------------
        cur.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN transaction_type = 'credit' THEN  amount ELSE 0 END), 0) AS entradas,
                COALESCE(SUM(CASE WHEN transaction_type = 'debit'  THEN  amount ELSE 0 END), 0) AS saidas,
                COALESCE(SUM(amount), 0)                                                         AS saldo_liquido
            FROM bank_transactions
            WHERE EXTRACT(MONTH FROM transaction_date) = %s
              AND EXTRACT(YEAR  FROM transaction_date) = %s
              AND ativo IS NOT FALSE
            """,
            (mes, ano),
        )
        r = cur.fetchone()
        fluxo_caixa = {
            "entradas": float(r[0]),
            "saidas": float(r[1]),
            "saldo_liquido": float(r[2]),
        }

        # ------------------------------------------------------------------
        # 10. TRANSAÇÕES SEM JUSTIFICATIVA (reconciliation_status = 'pendente'
        #     que exigem justificativa)
        # ------------------------------------------------------------------
        cur.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(ABS(amount)), 0)
            FROM bank_transactions
            WHERE requires_justification = TRUE
              AND reconciliation_status NOT IN ('conciliado', 'justificado')
              AND EXTRACT(MONTH FROM transaction_date) = %s
              AND EXTRACT(YEAR  FROM transaction_date) = %s
            """,
            (mes, ano),
        )
        r = cur.fetchone()
        sem_justificativa = {"qtd": r[0], "valor": float(r[1])}

        # ------------------------------------------------------------------
        # 11. ESTOQUE VALORIZADO — nfe_compras_estoque
        #     Colunas reais: qty_on_hand, avg_cost
        # ------------------------------------------------------------------
        cur.execute(
            """
            SELECT
                COUNT(*),
                COALESCE(SUM(qty_on_hand * avg_cost), 0)
            FROM nfe_compras_estoque
            WHERE qty_on_hand > 0
            """,
        )
        r = cur.fetchone()
        estoque = {"itens": r[0], "valor_total": float(r[1])}

        return {
            "periodo": f"{mes:02d}/{ano}",
            "gerado_em": datetime.now().isoformat(),
            "dre": dre,
            "contas_a_pagar": payables,
            "contas_a_receber": receivables,
            "fluxo_caixa_mes": fluxo_caixa,
            "sem_justificativa": sem_justificativa,
            "estoque": estoque,
            "folha": folha,
            "alertas": _gerar_alertas(payables, sem_justificativa, resultado_bruto),
        }

    finally:
        cur.close()
        conn.close()


def _gerar_alertas(payables: dict, sem_justif: dict, resultado: float) -> list:
    alertas = []
    if payables["vencidas"] > 0:
        alertas.append(
            {
                "tipo": "vencimento",
                "nivel": "vermelho",
                "msg": (f"{payables['vencidas']} contas vencidas — R$ {payables['valor']:,.2f} pendente"),
            }
        )
    if sem_justif["qtd"] > 0:
        alertas.append(
            {
                "tipo": "justificativa",
                "nivel": "amarelo",
                "msg": (f"{sem_justif['qtd']} saídas sem justificativa — R$ {sem_justif['valor']:,.2f}"),
            }
        )
    if resultado < 0:
        alertas.append(
            {
                "tipo": "resultado",
                "nivel": "vermelho",
                "msg": f"Resultado negativo: R$ {resultado:,.2f}",
            }
        )
    return alertas
