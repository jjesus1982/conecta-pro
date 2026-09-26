"""
Lucro Real — Classificação Automática de Saídas Bancárias

Classifica transações de débito por categoria fiscal do Lucro Real usando:
- Regras por CNPJ (instituições conhecidas: CEF/FGTS, SOLIDES, etc.)
- Regex sobre descrição (PIX ENVIADO, TARIFA, SAQUE, etc.)
- Fallback para análise de contraparte

Categorias (alinhadas com justificativa_service.py):
  salario             — folha de pagamento de funcionários
  adiantamento        — adiantamentos a funcionários
  servico_sem_nf      — fornecedores sem obrigação fiscal (PF/MEI)
  imposto             — FGTS, INSS, IRPJ, CSLL, DAS, DARF
  taxa_bancaria       — tarifas, saques, IOF
  transferencia_interna — movimentação entre contas próprias
  reembolso           — reembolsos a funcionários
  outros              — não classificado automaticamente

Schema real (bank_transactions):
  transaction_type, amount, description, transaction_date,
  reconciliation_status, justificativa, justificativa_categoria,
  justificativa_responsavel, justificativa_data, requires_justification
"""

import logging
import os
import re

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "").replace("+asyncpg", "")

# ─────────────────────────────────────────────────────────────
# CNPJs conhecidos — prioridade máxima na classificação
# ─────────────────────────────────────────────────────────────
CNPJ_RULES: list[tuple[str, str, str]] = [
    # (cnpj_fragment, categoria, descricao_padrao)
    ("00360305", "imposto", "Recolhimento FGTS — Caixa Econômica Federal"),
    ("31680151", "servico_sem_nf", "Serviço — SOLIDES (plataforma RH)"),
    ("90400888", "salario", "Pagamento de salário/remuneração a colaborador"),
    ("18236120", "salario", "Pagamento de salário/remuneração a colaborador"),
    ("60701190", "servico_sem_nf", "Serviço/pró-labore — Jordan Santos de Jesus"),
    ("37880206", "salario", "Pagamento de salário/remuneração a colaborador"),
    ("60746948", "servico_sem_nf", "Serviço/vigilância — prestador PF/MEI"),
    ("10664513", "salario", "Pagamento de salário/remuneração a colaborador"),
    ("59285411", "salario", "Pagamento de salário/remuneração a colaborador"),
    ("22896431", "salario", "Pagamento de salário/remuneração a colaborador"),
    ("00000000", "servico_sem_nf", "Serviço — prestador externo"),
    ("14796606", "reembolso", "Reembolso transporte — Uber"),
    ("02282709", "servico_sem_nf", "Serviço jurídico — advocacia"),
]

# ─────────────────────────────────────────────────────────────
# Regras regex sobre description — ordenadas por prioridade
# ─────────────────────────────────────────────────────────────
REGEX_RULES: list[tuple[str, str, str]] = [
    # (padrão regex, categoria, descrição padrão)
    (r"tarifa|taxa saque|taxa ted|taxa pix|tarifa mens|anuidade|iof ", "taxa_bancaria", "Tarifa/taxa bancária"),
    (r"saque banco|banco24h|banco 24h|caixa elet", "taxa_bancaria", "Saque em terminal bancário"),
    (
        r"darf|das |irpj|csll|cofins|\bpis\b|simples nacional|receita federal|pgdas|inss|fgts|gps |grf ",
        "imposto",
        "Recolhimento de imposto/tributo federal",
    ),
    (
        r"pix enviado interno|transferencia interna|transferencia propria|ted propria",
        "transferencia_interna",
        "Transferência entre contas próprias Conecta Mais",
    ),
    (r"folha|pagto.*funcionario|salario|13.*salario|ferias|rescis", "salario", "Pagamento de folha/salário"),
    (r"adiantamento|adianto|adian\.", "adiantamento", "Adiantamento a colaborador"),
    (r"reembolso|reimburso", "reembolso", "Reembolso de despesa a colaborador"),
    (r"aluguel|locacao|locação", "servico_sem_nf", "Aluguel/locação de imóvel ou equipamento"),
    (r"energia|light |cpfl|eletrobras|cemig|coelce|endesa|equatorial", "outros", "Conta de energia elétrica"),
    (r"internet|vivo|claro|tim |oi |nextel|net serv|telecom", "outros", "Serviço de telecom/internet"),
]


def _so_digitos(valor: str | None) -> str:
    return re.sub(r"\D", "", valor or "")


def _classificar_tx(
    description: str,
    counterparty_document: str | None = None,
    cpfs_funcionarios: frozenset[str] = frozenset(),
) -> tuple[str, str]:
    """
    Retorna (categoria, descricao_justificativa) para uma transação.
    Prioridade: CNPJ da contraparte → CPF de funcionário → regex → outros
    """
    desc = description or ""
    doc = _so_digitos(counterparty_document)

    # 1. CNPJ da CONTRAPARTE — lido da coluna counterparty_document.
    #    NÃO usar o "Cp :XXXXXXXX" da descrição: aquilo é o CNPJ do banco DESTINO
    #    do PIX, não de quem recebeu. Medido em 25/09/2026 sobre as 3.954 transações
    #    com esse padrão: o fragmento coincide com o CNPJ da contraparte em 32.
    #    Era essa leitura que carimbava "FGTS — Caixa Econômica" em todo salário pago
    #    a quem tem conta na Caixa.
    if len(doc) == 14:
        for cnpj, categoria, texto in CNPJ_RULES:
            if doc.startswith(cnpj):
                return categoria, texto

    # 2. Contraparte é funcionário do cadastro → folha, sem depender da descrição.
    if len(doc) == 11 and doc in cpfs_funcionarios:
        return "salario", "Pagamento de salário/remuneração a colaborador"

    # 3. Regex sobre description completa
    desc_lower = desc.lower()
    for padrao, categoria, texto in REGEX_RULES:
        if re.search(padrao, desc_lower):
            # Pessoa física não recolhe tributo: o fisco não recebe por CPF.
            if categoria == "imposto" and len(doc) == 11:
                return "outros", "Pagamento a pessoa física (CPF) — não é tributo; revisar"
            return categoria, texto

    return "outros", "Saída sem classificação automática — requer revisão manual"


def _cpfs_de_funcionarios(conn) -> frozenset[str]:
    """CPFs do cadastro de funcionários, só dígitos."""
    cur = conn.cursor()
    cur.execute("SELECT regexp_replace(coalesce(cpf, ''), '\\D', '', 'g') FROM employees")
    return frozenset(r[0] for r in cur.fetchall() if len(r[0]) == 11)


def classificar_automatico(
    preview: bool = True,
    apenas_sem_categoria: bool = True,
    responsavel: str = "Sistema — Lucro Real Auto",
) -> dict:
    """
    Classifica automaticamente saídas bancárias.

    Args:
        preview: se True, apenas calcula sem salvar no banco
        apenas_sem_categoria: se True, só processa as sem categoria ou mal-classificadas
        responsavel: nome do responsável pela classificação

    Returns:
        {
          total_processadas, classificadas_auto, nao_classificadas,
          distribuicao: {categoria: {qtd, valor}},
          correcoes_aplicadas: int,  # re-classificações de erros
          preview: bool
        }
    """
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur_plain = conn.cursor()

    try:
        # Buscar débitos a classificar
        if apenas_sem_categoria:
            # Inclui: sem categoria OU categorias sabidamente erradas (tarifa→salario)
            cur.execute("""
                SELECT id, description, amount, justificativa_categoria, counterparty_document
                FROM bank_transactions
                WHERE transaction_type = 'debit'
                  AND (
                    justificativa_categoria IS NULL
                    OR (
                      description ILIKE '%tarifa%'
                      AND justificativa_categoria != 'taxa_bancaria'
                    )
                    OR (
                      description ILIKE '%saque banco%'
                      AND justificativa_categoria != 'taxa_bancaria'
                    )
                    OR (
                      description ILIKE '%darf%'
                      AND justificativa_categoria NOT IN ('imposto','taxa_bancaria')
                    )
                  )
                ORDER BY ABS(amount) DESC
            """)
        else:
            cur.execute("""
                SELECT id, description, amount, justificativa_categoria, counterparty_document
                FROM bank_transactions
                WHERE transaction_type = 'debit'
                ORDER BY ABS(amount) DESC
            """)

        rows = cur.fetchall()
        total = len(rows)
        cpfs_func = _cpfs_de_funcionarios(conn)

        distribuicao: dict[str, dict] = {}
        correcoes = 0
        classificadas = 0
        updates: list[tuple] = []

        for row in rows:
            tx_id = str(row["id"])
            desc = str(row["description"] or "")
            valor = float(abs(row["amount"] or 0))
            cat_atual = row["justificativa_categoria"]

            cat_nova, texto_novo = _classificar_tx(desc, row["counterparty_document"], cpfs_func)

            # Contar como correção se estava errado
            if cat_atual and cat_nova != cat_atual and cat_nova != "outros":
                correcoes += 1

            if cat_nova != "outros":
                classificadas += 1

            # Acumular na distribuição
            if cat_nova not in distribuicao:
                distribuicao[cat_nova] = {"qtd": 0, "valor": 0.0}
            distribuicao[cat_nova]["qtd"] += 1
            distribuicao[cat_nova]["valor"] = round(distribuicao[cat_nova]["valor"] + valor, 2)

            if not preview:
                updates.append((texto_novo, cat_nova, responsavel, tx_id))

        # Aplicar no banco se não for preview
        if not preview and updates:
            cur_plain.executemany(
                """
                UPDATE bank_transactions SET
                    justificativa             = %s,
                    justificativa_categoria   = %s,
                    justificativa_responsavel = %s,
                    justificativa_data        = NOW(),
                    reconciliation_status     = CASE
                        WHEN reconciliation_status NOT IN ('conciliado','justificado')
                        THEN 'justificado'
                        ELSE reconciliation_status
                    END,
                    requires_justification    = FALSE,
                    updated_at                = NOW()
                WHERE id = %s
                """,
                updates,
            )
            conn.commit()

        pct_auto = round((classificadas / total * 100), 1) if total > 0 else 0.0

        return {
            "preview": preview,
            "total_processadas": total,
            "classificadas_auto": classificadas,
            "nao_classificadas": total - classificadas,
            "correcoes_aplicadas": correcoes if not preview else 0,
            "percentual_auto": pct_auto,
            "distribuicao": distribuicao,
            "mensagem": (
                f"Preview: {classificadas}/{total} seriam classificadas ({pct_auto}%)"
                if preview
                else f"Aplicado: {classificadas}/{total} classificadas ({pct_auto}%), {correcoes} correções"
            ),
        }

    except Exception as exc:
        conn.rollback()
        logger.error("classificar_automatico: %s", exc)
        raise
    finally:
        cur.close()
        cur_plain.close()
        conn.close()


def relatorio_compliance() -> dict:
    """
    Relatório de compliance Lucro Real: estado atual das justificativas.
    """
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT
              COUNT(*) FILTER (WHERE transaction_type='debit') AS total_debitos,
              COUNT(*) FILTER (WHERE transaction_type='debit' AND reconciliation_status='conciliado') AS conciliados,
              COUNT(*) FILTER (WHERE transaction_type='debit' AND reconciliation_status='justificado') AS justificados,
              COUNT(*) FILTER (WHERE transaction_type='debit' AND reconciliation_status='pendente') AS pendentes,
              COALESCE(SUM(ABS(amount)) FILTER (WHERE transaction_type='debit' AND reconciliation_status='pendente'),0) AS valor_pendente,
              COALESCE(SUM(ABS(amount)) FILTER (WHERE transaction_type='debit' AND reconciliation_status='justificado'),0) AS valor_justificado,
              COUNT(*) FILTER (WHERE transaction_type='debit' AND justificativa_categoria IS NULL AND reconciliation_status!='conciliado') AS sem_categoria
            FROM bank_transactions
        """)
        r = cur.fetchone()

        return {
            "total_debitos": r[0],
            "conciliados": r[1],
            "justificados": r[2],
            "pendentes_criticos": r[3],
            "valor_pendente": round(float(r[4]), 2),
            "valor_justificado": round(float(r[5]), 2),
            "sem_categoria": r[6],
            "compliance_pct": round(((r[1] + r[2]) / r[0] * 100) if r[0] > 0 else 100.0, 1),
        }
    finally:
        cur.close()
        conn.close()
