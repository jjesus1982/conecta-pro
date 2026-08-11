"""
Justificativa Service — Controle de Saídas Sem Nota Fiscal
Lucro Real: toda saída deve ter nota ou justificativa documentada.

Categorias de justificativa:
- salario: pagamento de salário/pró-labore
- adiantamento: adiantamento a funcionário
- reembolso: reembolso de despesas
- taxa_bancaria: tarifas e taxas do banco
- imposto: pagamento de impostos/guias
- servico_sem_nf: serviço prestado por pessoa sem obrigação fiscal
- transferencia_interna: movimentação entre contas próprias
- outros: outros (requer descrição detalhada)

Schema real bank_transactions:
  transaction_type, amount, description, transaction_date,
  reconciliation_status, counterparty_name, counterparty_document
"""

import logging
import os

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "").replace("+asyncpg", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")

CATEGORIAS_VALIDAS = [
    "salario",
    "adiantamento",
    "reembolso",
    "taxa_bancaria",
    "imposto",
    "servico_sem_nf",
    "transferencia_interna",
    "outros",
]


def _get_conn():
    return psycopg2.connect(DATABASE_URL)


def registrar_justificativa(
    tx_id: str,
    categoria: str,
    descricao: str,
    responsavel: str = "Jordan Jesus",
) -> dict:
    """Registra justificativa para saída sem nota fiscal."""
    if categoria not in CATEGORIAS_VALIDAS:
        return {"erro": f"Categoria inválida. Use: {CATEGORIAS_VALIDAS}"}
    if len(descricao.strip()) < 10:
        return {"erro": "Descrição muito curta (mínimo 10 caracteres)"}

    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE bank_transactions SET
                justificativa            = %s,
                justificativa_categoria  = %s,
                justificativa_responsavel = %s,
                justificativa_data       = NOW(),
                requires_justification   = FALSE,
                reconciliation_status    = 'justificado',
                updated_at               = NOW()
            WHERE id = %s
            RETURNING id, amount, description, transaction_date
            """,
            (descricao, categoria, responsavel, tx_id),
        )
        row = cur.fetchone()
        if not row:
            return {"erro": "Transação não encontrada"}

        tid, valor, tx_desc, data = row
        conn.commit()

        _notificar_telegram(
            f"✅ Justificativa registrada\n"
            f"Transação: {tx_desc}\n"
            f"Valor: R$ {abs(float(valor)):,.2f}\n"
            f"Categoria: {categoria}\n"
            f"Descrição: {descricao}\n"
            f"Responsável: {responsavel}"
        )

        return {
            "status": "justificado",
            "transacao_id": str(tid),
            "valor": float(abs(valor)),
            "categoria": categoria,
            "descricao": descricao,
        }
    except Exception as e:
        conn.rollback()
        logger.error("registrar_justificativa: %s", e)
        return {"erro": str(e)}
    finally:
        cur.close()
        conn.close()


def listar_sem_justificativa(mes: int = None, ano: int = None) -> dict:
    """Lista saídas que precisam de justificativa."""
    conn = _get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        params: list = []
        where_data = ""
        if mes and ano:
            where_data = "AND EXTRACT(MONTH FROM transaction_date) = %s AND EXTRACT(YEAR  FROM transaction_date) = %s "
            params = [mes, ano]

        base_where = f"""
            WHERE requires_justification = TRUE
              AND transaction_type = 'debit'
              {where_data}
        """

        # Contagem e soma reais (sem LIMIT)
        cur_plain = conn.cursor()
        cur_plain.execute(
            f"SELECT COUNT(*), COALESCE(SUM(ABS(amount)), 0) FROM bank_transactions {base_where}",
            params,
        )
        total, total_valor = cur_plain.fetchone()

        # Primeiras 200 linhas para exibição
        cur.execute(
            f"""
            SELECT
                id,
                transaction_date AS data,
                transaction_type AS tipo,
                ABS(amount)      AS valor,
                description      AS descricao,
                reconciliation_status,
                counterparty_name     AS contraparte_nome,
                counterparty_document AS contraparte_documento
            FROM bank_transactions
            {base_where}
            ORDER BY transaction_date DESC
            LIMIT 200
            """,
            params,
        )
        rows = cur.fetchall()

        return {
            "total": int(total),
            "valor_total": round(float(total_valor), 2),
            "transacoes": [dict(r) for r in rows],
        }
    finally:
        cur.close()
        conn.close()


def verificar_fechamento_periodo(mes: int, ano: int) -> dict:
    """
    Verifica se o período pode ser fechado.
    Bloqueia se houver saídas sem justificativa.
    """
    pendentes = listar_sem_justificativa(mes, ano)
    pode_fechar = pendentes["total"] == 0

    if not pode_fechar:
        _notificar_telegram(
            f"🚨 BLOQUEIO FECHAMENTO {mes:02d}/{ano}\n"
            f"{pendentes['total']} saídas sem justificativa\n"
            f"Valor total: R$ {pendentes['valor_total']:,.2f}\n"
            f"Resolva antes de fechar o período"
        )

    return {
        "pode_fechar": pode_fechar,
        "pendentes": pendentes["total"],
        "valor_pendente": pendentes["valor_total"],
        "mes": mes,
        "ano": ano,
        "mensagem": (
            "Período pode ser fechado"
            if pode_fechar
            else f"Bloqueado: {pendentes['total']} saídas sem justificativa (R$ {pendentes['valor_total']:,.2f})"
        ),
    }


def alertar_pendentes() -> dict:
    """Alerta via Telegram sobre saídas sem justificativa."""
    pendentes = listar_sem_justificativa()
    if pendentes["total"] > 0:
        _notificar_telegram(
            f"⚠️ SAÍDAS SEM JUSTIFICATIVA\n"
            f"Total: {pendentes['total']} transações\n"
            f"Valor: R$ {pendentes['valor_total']:,.2f}\n"
            f"Acesse o Conecta PRO para justificar"
        )
    else:
        _notificar_telegram("✅ Todas as saídas estão justificadas!")
    return pendentes


def _notificar_telegram(msg: str) -> None:
    """DESATIVADA (11/08/2026) — o Telegram saiu do Conecta PRO.

    Os dois bots foram apagados e bloqueados pelo Jordan; as credenciais saíram do `.env`.
    Mantida como função (vários pontos chamam) e o texto vai para o log: nada some em
    silêncio. Canal da casa para aviso novo é o SINO.
    """
    logger.info("[telegram removido] justificativa não notificada: %s", (msg or "")[:200])


def _notificar_telegram_desativado(msg: str) -> None:
    """Corpo original preservado para referência — não é chamado."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        logger.info("Telegram (não configurado): %s", msg)
        return
    try:
        import requests

        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT, "text": msg},
            timeout=5,
        )
    except Exception as exc:
        logger.warning("Telegram erro: %s", exc)
