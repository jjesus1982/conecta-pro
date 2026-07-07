"""
Reconciliation Service — Conciliação Bancária Automática Inter × Notas
Faz matching: transação Inter ↔ conta a pagar/receber

Regras de matching (em cascata):
1. Valor exato (tolerância R$0,01) + CNPJ da contraparte + data ±3 dias
2. Valor exato + data ±3 dias (sem CNPJ)
3. Valor ±2% + data ±7 dias (flexível)

Saídas sem match → flag requires_justification = True

Colunas reais usadas:
  bank_transactions: transaction_type, amount, transaction_date,
                     reconciliation_status, reconciliation_id
  payable_accounts:  gross_value, due_date, status, payment_date, paid_at
  receivable_accounts: gross_value, due_date, status, payment_date
"""

import logging
import os
import re
from datetime import timedelta
from decimal import Decimal

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "").replace("+asyncpg", "")
TOLERANCE = Decimal("0.01")
TOLERANCE_PCT = Decimal("0.02")  # 2% para matching flexível
DATE_WINDOW = 3  # dias para matching exato
DATE_WINDOW_FLEX = 7  # dias para matching flexível

# Padrão CNPJ na descrição (14 dígitos contíguos ou formatado)
_RE_CNPJ = re.compile(r"\b(\d{14})\b|\b(\d{2}[.\-]?\d{3}[.\-]?\d{3}[/\-]?\d{4}[.\-]?\d{2})\b")


INTER_BANK_ACCOUNT_ID = "20663dc9-805c-4721-bc1f-62a041cee3c1"


def _get_conn():
    return psycopg2.connect(DATABASE_URL)


def _get_or_create_reconciliation_session(mes: int, ano: int, cur) -> str:
    """
    Cria (ou recupera) um registro em bank_reconciliations representando
    a sessão de conciliação automática do período.
    Retorna o UUID da sessão para popular bank_transactions.reconciliation_id.
    """
    import calendar

    reference = f"AUTO-{ano}-{mes:02d}"
    cur.execute(
        "SELECT id FROM bank_reconciliations WHERE reference = %s LIMIT 1",
        (reference,),
    )
    row = cur.fetchone()
    if row:
        return str(row[0] if not isinstance(row, dict) else row["id"])

    _, last_day = calendar.monthrange(ano, mes)
    period_start = f"{ano}-{mes:02d}-01"
    period_end = f"{ano}-{mes:02d}-{last_day:02d}"

    cur.execute(
        """
        INSERT INTO bank_reconciliations (
            id, bank_account_id, period_type, period_start, period_end,
            opening_balance, status, total_credits, total_debits,
            total_adjustments, total_system_items, total_statement_items,
            items_reconciled, items_pending, progress_percentage,
            ativo, description, reference, match_type, created_at
        ) VALUES (
            gen_random_uuid(), %s, 'mensal', %s, %s,
            0, 'em_andamento', 0, 0,
            0, 0, 0, 0, 0, 0,
            TRUE, %s, %s, 'cascata_3_estrategias', NOW()
        )
        RETURNING id
        """,
        (
            INTER_BANK_ACCOUNT_ID,
            period_start,
            period_end,
            f"Conciliação Automática Inter × Notas — {mes:02d}/{ano}",
            reference,
        ),
    )
    new_row = cur.fetchone()
    return str(new_row[0] if not isinstance(new_row, dict) else new_row["id"])


def _normalizar_doc(doc: str) -> str:
    """Remove formatação de CPF/CNPJ — retorna apenas dígitos."""
    if not doc:
        return ""
    return re.sub(r"\D", "", doc)


def _extrair_nome_contraparte(descricao: str) -> str:
    """
    Extrai nome da empresa/pessoa da descrição do banco Inter.
    Padrões:
      - 'PAGAMENTO DE TITULO - NOME EMPRESA LTDA'
      - 'PIX ENVIADO - Cp :12345678-Nome Pessoa'
      - 'RECEBIMENTO TITULO - codigo/numero'
    """
    if not descricao:
        return ""
    # Após " - " pega o restante (nome do contraparte)
    partes = descricao.split(" - ", 1)
    if len(partes) < 2:
        return ""
    nome = partes[1].strip()
    # Remove prefixo "Cp :XXXXXXXX-" (código banco Inter)
    nome = re.sub(r"^Cp\s*:\d+[-–]\s*", "", nome).strip()
    # Truncar em 100 chars
    return nome[:100]


def _lookup_cnpj_por_nome(nome: str, cur) -> str:
    """Busca CNPJ no cadastro de fornecedores por similaridade de nome."""
    if not nome or len(nome) < 5:
        return ""
    # Pegar primeiras palavras significativas (>3 chars) para busca
    palavras = [w for w in nome.split() if len(w) > 3][:3]
    if not palavras:
        return ""
    like_pattern = "%" + palavras[0] + "%"
    cur.execute(
        "SELECT cpf_cnpj FROM suppliers WHERE name ILIKE %s LIMIT 1",
        (like_pattern,),
    )
    row = cur.fetchone()
    return _normalizar_doc(row["cpf_cnpj"] if row else "")


def _atualizar_contraparte(tx_id: str, nome: str, cnpj: str, cur) -> None:
    """Popula contraparte_nome e contraparte_documento na transação."""
    if nome or cnpj:
        cur.execute(
            """
            UPDATE bank_transactions SET
                contraparte_nome = COALESCE(contraparte_nome, %s),
                contraparte_documento = COALESCE(contraparte_documento, %s)
            WHERE id = %s
            """,
            (nome or None, cnpj or None, tx_id),
        )


def conciliar_transacao(tx_id: str, conn) -> dict:
    """
    Tenta conciliar uma transação bancária específica.
    Retorna dict com status, tipo_match e referência conciliada.
    """
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute(
        """
        SELECT id, transaction_date, transaction_type, amount, description,
               reconciliation_status, reconciliation_id
        FROM bank_transactions
        WHERE id = %s
        """,
        (tx_id,),
    )
    tx = cur.fetchone()
    if not tx:
        return {"erro": "Transação não encontrada"}

    if tx["reconciliation_status"] in ("conciliado", "justificado"):
        return {"status": "ja_conciliado", "reconciliation_id": str(tx["reconciliation_id"] or "")}

    # Obter/criar sessão de conciliação para o período da transação
    tx_date_obj = tx["transaction_date"]
    recon_session_id = _get_or_create_reconciliation_session(tx_date_obj.month, tx_date_obj.year, cur)

    valor_abs = abs(Decimal(str(tx["amount"])))
    tx_date = tx["transaction_date"]
    tx_type = tx["transaction_type"]  # 'debit' | 'credit'
    descricao = tx["description"] or ""

    data_min = tx_date - timedelta(days=DATE_WINDOW)
    data_max = tx_date + timedelta(days=DATE_WINDOW)
    data_min_flex = tx_date - timedelta(days=DATE_WINDOW_FLEX)
    data_max_flex = tx_date + timedelta(days=DATE_WINDOW_FLEX)

    # Extrair nome e CNPJ da contraparte da descrição
    nome_contraparte = _extrair_nome_contraparte(descricao)
    cnpj_contraparte = _lookup_cnpj_por_nome(nome_contraparte, cur) if nome_contraparte else ""

    # Extrair CNPJ diretamente da descrição (se houver padrão numérico)
    if not cnpj_contraparte:
        m = _RE_CNPJ.search(descricao)
        if m:
            cnpj_contraparte = _normalizar_doc(m.group(0))

    # Salvar contraparte na transação (enriquecimento)
    _atualizar_contraparte(tx_id, nome_contraparte, cnpj_contraparte, cur)

    # ── DÉBITO → buscar em payable_accounts ──────────────────────────────────
    if tx_type == "debit":
        # Estratégia 1: valor exato ±R$0,01 + CNPJ da contraparte + data ±3 dias
        match = None
        tipo_match = ""
        if cnpj_contraparte:
            cur.execute(
                """
                SELECT pa.id, pa.description, pa.gross_value, pa.net_value,
                       pa.due_date, pa.status, s.cpf_cnpj as supplier_cnpj
                FROM payable_accounts pa
                LEFT JOIN suppliers s ON s.id = pa.supplier_id
                WHERE pa.status = 'pendente'
                  AND ABS(pa.gross_value - %s) <= %s
                  AND pa.due_date BETWEEN %s AND %s
                  AND REPLACE(REPLACE(REPLACE(REPLACE(s.cpf_cnpj,'.',''),'-',''),'/',''),' ','') = %s
                ORDER BY ABS(pa.gross_value - %s)
                LIMIT 1
                """,
                (float(valor_abs), float(TOLERANCE), data_min, data_max, cnpj_contraparte, float(valor_abs)),
            )
            match = cur.fetchone()
            tipo_match = "exato_cnpj_valor_data"

        # Estratégia 2: valor exato ±R$0,01, data ±3 dias (sem CNPJ)
        if not match:
            cur.execute(
                """
                SELECT id, description, gross_value, net_value, due_date, status
                FROM payable_accounts
                WHERE status = 'pendente'
                  AND ABS(gross_value - %s) <= %s
                  AND due_date BETWEEN %s AND %s
                ORDER BY ABS(gross_value - %s)
                LIMIT 1
                """,
                (float(valor_abs), float(TOLERANCE), data_min, data_max, float(valor_abs)),
            )
            match = cur.fetchone()
            tipo_match = "valor_exato_data"

        # Estratégia 3: valor ±2%, data ±7 dias (flexível)
        if not match:
            margem = float(valor_abs * TOLERANCE_PCT)
            cur.execute(
                """
                SELECT id, description, gross_value, net_value, due_date, status
                FROM payable_accounts
                WHERE status = 'pendente'
                  AND ABS(gross_value - %s) <= %s
                  AND due_date BETWEEN %s AND %s
                ORDER BY ABS(gross_value - %s)
                LIMIT 1
                """,
                (float(valor_abs), margem, data_min_flex, data_max_flex, float(valor_abs)),
            )
            match = cur.fetchone()
            tipo_match = "valor_flex_2pct"

        if match:
            pay_id = match["id"]
            # Marcar transação como conciliada + vincular à sessão de conciliação
            cur.execute(
                """
                UPDATE bank_transactions SET
                    reconciliation_status = 'conciliado',
                    reconciliation_id = %s,
                    payable_payment_id = %s,
                    reconciled_at = %s,
                    requires_justification = FALSE,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (recon_session_id, pay_id, tx_date, tx_id),
            )
            # Marcar payable como pago + vincular transação bancária
            cur.execute(
                """
                UPDATE payable_accounts SET
                    status = 'pago',
                    payment_date = %s,
                    paid_at = NOW(),
                    transacao_bancaria_id = %s,
                    comprovante_id = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (tx_date, tx_id, tx_id, str(pay_id)),
            )
            conn.commit()
            return {
                "status": "conciliado",
                "tipo": "debito_payable",
                "match": tipo_match,
                "payable_id": str(pay_id),
                "payable_desc": match["description"],
                "valor_tx": float(valor_abs),
                "valor_payable": float(match["gross_value"]),
            }
        else:
            # Débito sem match → marcar para justificativa
            cur.execute(
                """
                UPDATE bank_transactions SET
                    requires_justification = TRUE,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (tx_id,),
            )
            conn.commit()
            return {
                "status": "sem_match",
                "tipo": "debito_sem_nota",
                "requires_justification": True,
                "valor": float(valor_abs),
                "descricao": descricao,
            }

    # ── CRÉDITO → buscar em receivable_accounts ───────────────────────────────
    elif tx_type == "credit":
        # Salvar contraparte também para créditos
        _atualizar_contraparte(tx_id, nome_contraparte, cnpj_contraparte, cur)

        match = None
        tipo_match = ""

        # Estratégia 1: valor exato ±R$0,01 + CNPJ da contraparte + data ±3 dias
        if cnpj_contraparte:
            cur.execute(
                """
                SELECT ra.id, ra.description, ra.gross_value, ra.net_value,
                       ra.due_date, ra.status, c.cpf_cnpj as customer_cnpj
                FROM receivable_accounts ra
                LEFT JOIN customers c ON c.id = ra.customer_id
                WHERE ra.status = 'pendente'
                  AND ABS(ra.gross_value - %s) <= %s
                  AND ra.due_date BETWEEN %s AND %s
                  AND REPLACE(REPLACE(REPLACE(REPLACE(c.cpf_cnpj,'.',''),'-',''),'/',''),' ','') = %s
                ORDER BY ABS(ra.gross_value - %s)
                LIMIT 1
                """,
                (float(valor_abs), float(TOLERANCE), data_min, data_max, cnpj_contraparte, float(valor_abs)),
            )
            match = cur.fetchone()
            tipo_match = "exato_cnpj_valor_data"

        # Estratégia 2: valor exato ±R$0,01, data ±3 dias (sem CNPJ)
        if not match:
            cur.execute(
                """
                SELECT id, description, gross_value, net_value, due_date, status
                FROM receivable_accounts
                WHERE status = 'pendente'
                  AND ABS(gross_value - %s) <= %s
                  AND due_date BETWEEN %s AND %s
                ORDER BY ABS(gross_value - %s)
                LIMIT 1
                """,
                (float(valor_abs), float(TOLERANCE), data_min, data_max, float(valor_abs)),
            )
            match = cur.fetchone()
            tipo_match = "valor_exato_data"

        # Estratégia 3: valor ±2%, data ±7 dias (flexível)
        if not match:
            margem = float(valor_abs * TOLERANCE_PCT)
            cur.execute(
                """
                SELECT id, description, gross_value, net_value, due_date, status
                FROM receivable_accounts
                WHERE status = 'pendente'
                  AND ABS(gross_value - %s) <= %s
                  AND due_date BETWEEN %s AND %s
                ORDER BY ABS(gross_value - %s)
                LIMIT 1
                """,
                (float(valor_abs), margem, data_min_flex, data_max_flex, float(valor_abs)),
            )
            match = cur.fetchone()
            tipo_match = "valor_flex_2pct"

        if match:
            rec_id = match["id"]
            cur.execute(
                """
                UPDATE bank_transactions SET
                    reconciliation_status = 'conciliado',
                    reconciliation_id = %s,
                    receivable_payment_id = %s,
                    reconciled_at = %s,
                    requires_justification = FALSE,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (recon_session_id, rec_id, tx_date, tx_id),
            )
            # Marcar receivable como recebido + vincular transação bancária
            cur.execute(
                """
                UPDATE receivable_accounts SET
                    status = 'recebido',
                    payment_date = %s,
                    data_recebimento = %s,
                    transacao_bancaria_id = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (tx_date, tx_date, tx_id, str(rec_id)),
            )
            conn.commit()
            return {
                "status": "conciliado",
                "tipo": "credito_receivable",
                "match": tipo_match,
                "receivable_id": str(rec_id),
                "receivable_desc": match["description"],
                "valor_tx": float(valor_abs),
                "valor_receivable": float(match["gross_value"]),
            }
        else:
            # Crédito sem match → marcar para justificativa
            cur.execute(
                """
                UPDATE bank_transactions SET
                    requires_justification = TRUE,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (tx_id,),
            )
            conn.commit()
            return {
                "status": "sem_match",
                "tipo": "credito_sem_receivable",
                "requires_justification": True,
                "valor": float(valor_abs),
                "descricao": descricao,
            }

    return {"status": "tipo_nao_processado", "tipo": tx_type}


def conciliar_todas(limite: int = 649) -> dict:
    """
    Concilia todas as transações não reconciliadas.
    Inclui as marcadas como requires_justification=TRUE para dar nova chance de match.
    """
    conn = _get_conn()
    cur = conn.cursor()

    # Busca TODAS as pendentes (inclusive as com requires_justification=TRUE
    # que podem ter match com payables agora)
    cur.execute(
        """
        SELECT id FROM bank_transactions
        WHERE reconciliation_status NOT IN ('conciliado', 'justificado')
        ORDER BY transaction_date DESC
        LIMIT %s
        """,
        (limite,),
    )
    tx_ids = [str(r[0]) for r in cur.fetchall()]
    cur.close()

    total = len(tx_ids)
    conciliados = 0
    sem_match = 0
    erros = 0
    detalhes: list[dict] = []

    for tx_id in tx_ids:
        try:
            resultado = conciliar_transacao(tx_id, conn)
            st = resultado.get("status", "")
            if st == "conciliado":
                conciliados += 1
            elif st == "sem_match":
                sem_match += 1
                detalhes.append(resultado)
        except Exception as exc:
            erros += 1
            logger.error("Erro conciliação %s: %s", tx_id, exc)
            try:
                conn.rollback()
            except Exception:
                pass

    conn.close()
    return {
        "processadas": total,
        "conciliadas": conciliados,
        "sem_match_requer_justificativa": sem_match,
        "erros": erros,
        "taxa_conciliacao_pct": round(conciliados / max(1, total) * 100, 1),
        "sem_match_detalhes": detalhes[:10],
    }
