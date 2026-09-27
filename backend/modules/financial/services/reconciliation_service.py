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
# Janela de retenção do RECEBÍVEL: o título é bruto, o cliente paga líquido.
RETENCAO_PISO = Decimal("0.80")  # ISS 5% + INSS 11% = ~84% no pior caso; 80% dá folga
RETENCAO_TETO = Decimal("1.005")  # ninguém paga mais que a nota

# Palavras que dizem o TIPO da pessoa jurídica, não QUAL ela é.
_GENERICOS = {
    "CONDOMINIO",
    "CONDOMÍNIO",
    "RESIDENCIAL",
    "EDIFICIO",
    "EDIFÍCIO",
    "EMPRESARIAL",
    "LTDA",
    "EIRELI",
    "MEI",
    "COMERCIO",
    "COMÉRCIO",
    "SERVICOS",
    "SERVIÇOS",
    "EMPRESA",
    "ASSOCIACAO",
    "ASSOCIAÇÃO",
    "CENTRO",
    "CLUBE",
    # Estes três entraram em 26/09/2026, quando a extração de nome passou a alcançar
    # boleto e convênio: «BANCO TOYOTA DO BRASIL SA» reduzia o token a «BANCO» e casava
    # com qualquer fornecedor que tivesse a palavra no nome.
    "BANCO",
    "PREFEITURA",
    "MUNICIPAL",
}

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


#: O mesmo fato chega em texto diferente conforme a porta: a API do Inter manda
#: `PIX ENVIADO - Cp :60701190-FULANO`, o CSV manda `Pix enviado: "Cp :00000000-FULANO`, e
#: há ainda a forma com o código de banco solto (`"00019 61638862 FULANO`). Um só formato
#: coberto deixava o resto sem contraparte — 170 lançamentos e R$ 67.110,61 parados como
#: «(sem nome)» na conta transitória em 26/09/2026, o pior bloco do relatório porque era
#: o único que ninguém conseguia DECIDIR.
#:
#: NUNCA tirar DOCUMENTO daqui: o número depois de «Cp :» é o banco DESTINO (00360305 é a
#: Caixa), não quem recebeu. Só nome.
_NOME_NA_DESCRICAO = (
    re.compile(r'^(?:Pix|TED|DOC)\s+(?:enviad|recebid)\w*\s*:\s*"Cp\s*:\s*\d+\s*[-–]\s*(?P<n>[^"]+)', re.I),
    re.compile(r'^(?:Pix|TED|DOC)\s+(?:enviad|recebid)\w*\s*:\s*"\d+\s+\d+\s+(?P<n>[^"]+)', re.I),
    re.compile(r"^(?:PIX|TED|DOC)\s+(?:ENVIADO|RECEBIDO)\s*[-–]\s*Cp\s*:\s*\d+\s*[-–]\s*(?P<n>.+)$", re.I),
    re.compile(r"^PAGAMENTO DE (?:TITULO|CONVENIO)\s*[-–]\s*(?P<n>.+)$", re.I),
    re.compile(r'^Pagamento (?:efetuado|de Convenio)\s*:\s*"(?P<n>[^"]+)', re.I),
    re.compile(r'^Compra no d[ée]bito\s*:\s*"No estabelecimento\s+(?P<n>[^"]+)', re.I),
)

#: Descrição que não tem favorecido NENHUM — procurar nome aqui é inventar contraparte.
_SEM_FAVORECIDO = re.compile(r"^(SAQUE|PAGAMENTO DARF|TARIFA|IOF|JUROS|RENDIMENTO|APLICA|RESGATE|ESTORNO)", re.I)


def _extrair_nome_contraparte(descricao: str) -> str:
    """Nome da empresa/pessoa na descrição do extrato, ou "" quando não há favorecido.

    Os formatos cobertos estão em `_NOME_NA_DESCRICAO`; o que não tem favorecido está em
    `_SEM_FAVORECIDO` e devolve "" de propósito — saque e DARF não têm contraparte, e
    inventar uma é pior que deixar em branco.
    """
    d = (descricao or "").strip()
    if not d or _SEM_FAVORECIDO.match(d):
        return ""
    for padrao in _NOME_NA_DESCRICAO:
        m = padrao.match(d)
        if m:
            nome = re.sub(r"\s+", " ", m.group("n")).strip(' "-–')
            if nome and _parece_nome(nome):
                return nome[:100]
    # Último recurso, o formato genérico "RÓTULO - NOME" que já existia aqui.
    partes = d.split(" - ", 1)
    if len(partes) < 2:
        return ""
    nome = re.sub(r"^Cp\s*:\d+[-–]\s*", "", partes[1].strip()).strip()
    return nome[:100] if _parece_nome(nome) else ""


#: Duas letras seguidas. É o mínimo para separar NOME de NÚMERO, e sem isto
#: `RECEBIMENTO TITULO - 112/90725427051` devolvia «112/90725427051» como se fosse a
#: contraparte — 295 transações do extrato carregam exatamente esse lixo em
#: `contraparte_nome`, entre elas as maiores entradas do ano.
_TEM_LETRAS = re.compile(r"[A-Za-zÀ-ÿ]{2}")


def _parece_nome(s: str) -> bool:
    """Um número de boleto não é uma contraparte. Sem letras, não é nome."""
    return bool(_TEM_LETRAS.search(s or ""))


def _lookup_cnpj_por_nome(nome: str, cur) -> str:
    """CNPJ do fornecedor cujo nome casa — e SÓ quando casa um, com token que discrimina.

    O resultado é gravado em `bank_transactions.counterparty_document`, e dali o
    classificador contábil decide a natureza do lançamento. Um documento errado aqui não
    fica parado: vira conta errada no razão. Já aconteceu por outra porta — o «Cp :»
    da descrição é o banco destino, e salário foi lançado como FGTS.

    Duas guardas, as mesmas que o resto deste arquivo já usa no casamento de título:

     · o token tem de DISCRIMINAR. Pegar a primeira palavra >3 letras dava «BANCO» para
       «BANCO TOYOTA DO BRASIL SA» e casava com qualquer fornecedor que tivesse «banco»
       no nome. `_GENERICOS` sai, e entre os que sobram vale o mais longo;
     · UNICIDADE. `LIMIT 1` escolhe um candidato entre vários sem dizer; `LIMIT 2` com
       recusa no empate devolve "" — sem documento é melhor que documento de outro.
    """
    if not nome or len(nome) < 5:
        return ""
    palavras = [w for w in re.split(r"[^A-Za-zÀ-ÿ0-9]+", nome) if len(w) > 3]
    palavras = [w for w in palavras if w.upper() not in _GENERICOS and not w.isdigit()]
    if not palavras:
        return ""
    token = max(palavras, key=len)
    cur.execute(
        "SELECT cpf_cnpj FROM suppliers WHERE name ILIKE %s LIMIT 2",
        ("%" + token + "%",),
    )
    linhas = cur.fetchall()
    if len(linhas) != 1:
        return ""
    return _normalizar_doc(linhas[0]["cpf_cnpj"])


def _atualizar_contraparte(tx_id: str, nome: str, cnpj: str, cur) -> None:
    """Grava a contraparte derivada — o NOME nas DUAS colunas, o documento só na sua.

    `bank_transactions` tem dois pares de colunas para a mesma coisa: `counterparty_name`
    /`counterparty_document`, que a sincronia do Inter preenche, e `contraparte_nome`
    /`contraparte_documento`, que esta conciliação preenchia. **29 arquivos leem o
    primeiro par; 4 tocam o segundo** — ou seja, tudo o que esta função derivava caía num
    campo que quase ninguém lia. Medido em 26/09/2026: 295 transações com
    `contraparte_nome` e `counterparty_name` VAZIO, invisíveis para o classificador
    contábil, para os caçadores e para o radar de fornecedores.

    O NOME passa a ir para as duas, sempre com `COALESCE`: preenche vazio, nunca
    sobrescreve o que o banco informou.

    **O DOCUMENTO não é copiado, de propósito.** Ele vem de `_lookup_cnpj_por_nome`, que
    até 26/09/2026 casava pela primeira palavra com `LIMIT 1` — «BANCO TOYOTA DO BRASIL
    SA» virava `ILIKE '%BANCO%'` e pegava qualquer fornecedor. Os valores históricos de
    `contraparte_documento` carregam esse erro, e `counterparty_document` é justamente de
    onde o classificador tira a natureza do lançamento. Espalhar documento suspeito é
    trocar um campo invisível por uma conta errada no razão.
    """
    if nome or cnpj:
        cur.execute(
            """
            UPDATE bank_transactions SET
                contraparte_nome = COALESCE(contraparte_nome, %s),
                contraparte_documento = COALESCE(contraparte_documento, %s),
                counterparty_name = COALESCE(NULLIF(TRIM(counterparty_name), ''), %s)
            WHERE id = %s
            """,
            (nome or None, cnpj or None, nome or None, tx_id),
        )


def conciliar_transacao(
    tx_id: str, conn, permitir_justificado: bool = False, permitir_reconciliado: bool = False
) -> dict:
    """
    Tenta conciliar uma transação bancária específica.
    Retorna dict com status, tipo_match e referência conciliada.

    `permitir_reconciliado`: reprocessa mesmo o que já está rotulado 'conciliado'.
    Existe porque o rótulo e o VÍNCULO se separaram: 5 entradas do Cora somando
    R$100.699,77 estavam "conciliado" com `receivable_payment_id` vazio — o rótulo
    dizia feito e nenhum título tinha sido baixado. Quem chama isto tem que ter
    olhado o vínculo primeiro; não é para uso geral.

    `permitir_justificado`: um débito CLASSIFICADO ('justificado') continua sendo
    o pagamento de alguma nota. Enquanto o contas-a-pagar era casca, não havia
    documento pra casar e classificar era o fim da linha. Com as notas tomadas
    registradas, esses débitos merecem uma segunda passada. O match forte
    (nome + valor exato + candidato único) é o que protege contra falso positivo.
    """
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute(
        """
        SELECT id, transaction_date, transaction_type, amount, description,
               reconciliation_status, reconciliation_id, counterparty_name
        FROM bank_transactions
        WHERE id = %s
        """,
        (tx_id,),
    )
    tx = cur.fetchone()
    if not tx:
        return {"erro": "Transação não encontrada"}

    if permitir_reconciliado:
        _bloqueio = ()
    else:
        _bloqueio = ("conciliado",) if permitir_justificado else ("conciliado", "justificado")
    if tx["reconciliation_status"] in _bloqueio:
        return {"status": "ja_conciliado", "reconciliation_id": str(tx["reconciliation_id"] or "")}

    # Obter/criar sessão de conciliação para o período da transação
    tx_date_obj = tx["transaction_date"]
    recon_session_id = _get_or_create_reconciliation_session(tx_date_obj.month, tx_date_obj.year, cur)

    valor_abs = abs(Decimal(str(tx["amount"])))
    tx_date = tx["transaction_date"]
    tx_type = tx["transaction_type"]  # 'debit' | 'credit' | 'pix_enviado' | ...
    # Direção pelo SINAL do amount (confiável): saída (baixa de pagável) = amount<0; entrada = amount>0.
    # Antes só olhava transaction_type=='debit', cego aos 4267 pix_enviado (a saída real dominante).
    _amount_raw = Decimal(str(tx["amount"]))
    es_saida = _amount_raw < 0
    es_entrada = _amount_raw > 0
    descricao = tx["description"] or ""

    # Extrair nome e CNPJ da contraparte. `counterparty_name` VEM PRIMEIRO: no Cora a
    # descrição é a justificativa que o Jordan digita no app ("[CORA] Serviço de Agente
    # de Portaria") e não nomeia ninguém — quem paga está só nesta coluna. Lendo apenas
    # a descrição, TODA entrada do Cora ficava sem nome, e sem nome não há match forte:
    # R$100.699,77 de agosto/2026 passaram batido por isso.
    nome_contraparte = (tx["counterparty_name"] or "").strip() or _extrair_nome_contraparte(descricao)
    cnpj_contraparte = _lookup_cnpj_por_nome(nome_contraparte, cur) if nome_contraparte else ""

    # Extrair CNPJ diretamente da descrição (se houver padrão numérico)
    if not cnpj_contraparte:
        m = _RE_CNPJ.search(descricao)
        if m:
            cnpj_contraparte = _normalizar_doc(m.group(0))

    # Salvar contraparte na transação (enriquecimento)
    _atualizar_contraparte(tx_id, nome_contraparte, cnpj_contraparte, cur)

    # ── SAÍDA (amount<0) → buscar em payable_accounts ────────────────────────
    if es_saida:
        # Auto-baixa SÓ com match FORTE: valor exato ±R$0,01 + data ±3 dias + NOME da contraparte
        # aparece no pagável + candidato ÚNICO. Por quê: valor-só casa demais (R$150 = 3 PIX de
        # pessoas diferentes) e o CNPJ vem PLACEHOLDER (12345678000199 nos dois lados) — o nome da
        # contraparte é o único sinal confiável. Sem nome que confere → NÃO auto-baixa (vai p/ baixa
        # manual, requires_justification). Estratégias antigas (CNPJ placeholder, valor-só, fuzzy ±2%)
        # foram removidas: risco de baixar a conta ERRADA = fabricar baixa.
        match = None
        tipo_match = ""
        # O token tem que DISCRIMINAR, não ser o mais comprido: "CONDOMINIO IDEAL
        # FLORES" dava `CONDOMINIO`, que casa com todo condomínio da carteira — dois
        # candidatos, unicidade quebrada, nada baixava. Tira as palavras de tipo antes.
        _tokens = [w for w in re.split(r"[^A-Za-zÀ-ÿ]+", (nome_contraparte or "")) if len(w) >= 4]
        _tokens = [w for w in _tokens if w.upper() not in _GENERICOS] or _tokens
        _tok = max(_tokens, key=len) if _tokens else ""
        # Janela ±30d p/ pagável: fornecedores net-30 pagam ~30d ANTES do vencimento (débito antecede
        # o due_date). Nome + valor exato + ÚNICO é forte; a guarda de unicidade rejeita ambíguos mesmo
        # na janela larga — sem risco de fabricar. O recebível usa a MESMA janela, logo abaixo:
        # a «janela estreita global» que este comentário citava (DATE_WINDOW = 3) estava morta
        # havia tempo — nenhum dos dois lados a lia.
        _pay_dmin = tx_date - timedelta(days=30)
        _pay_dmax = tx_date + timedelta(days=30)
        if _tok:
            cur.execute(
                """
                SELECT id, description, gross_value, net_value, due_date, status
                FROM payable_accounts
                -- A trava é "ainda NÃO VINCULADO", não "ainda não pago". O filtro
                -- antigo (status='pendente') tornava invisíveis 130 pagáveis que
                -- nascem marcados `pago` porque a NFS-e/folha existe — sem
                -- paid_at, sem comprovante, sem transação bancária. Eram
                -- justamente os que mais precisavam de prova, e a conciliação
                -- nunca os alcançava: 0 de 175 saídas de agosto vinculadas.
                WHERE transacao_bancaria_id IS NULL
                  AND status <> 'cancelado'
                  AND ABS(gross_value - %s) <= %s
                  AND due_date BETWEEN %s AND %s
                  AND lower(description) LIKE lower(%s)
                LIMIT 2
                """,
                (float(valor_abs), float(TOLERANCE), _pay_dmin, _pay_dmax, f"%{_tok}%"),
            )
            _cands = cur.fetchall()
            if len(_cands) == 1:
                match = _cands[0]
                tipo_match = "valor_data_nome_unico"

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
                    paid_value = %s,
                    remaining_value = 0,
                    transacao_bancaria_id = %s,
                    comprovante_id = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (tx_date, float(match["net_value"]), tx_id, tx_id, str(pay_id)),
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

    # ── ENTRADA (amount>0) → buscar em receivable_accounts ───────────────────
    elif es_entrada:
        # Salvar contraparte também para créditos
        _atualizar_contraparte(tx_id, nome_contraparte, cnpj_contraparte, cur)

        match = None
        tipo_match = ""

        # Auto-baixa de recebível SÓ com match FORTE: data ±30d + NOME do pagador
        # (contraparte) no recebível + candidato ÚNICO. O que protege contra baixar o
        # título errado é o NOME somado à unicidade — não o centavo. Por isso o valor
        # entra como JANELA DE RETENÇÃO, não como igualdade:
        #
        # o título é BRUTO e o cliente paga LÍQUIDO. ISS 5% + INSS 11% tiram até ~16%,
        # e quem não retém paga 100%. Medido em agosto/2026: Michelangelo 99%,
        # Villa Dei Fiori 99%, Prime Arena 90%, Laranjeiras 87%. Exigindo bruto exato
        # NENHUM cliente com retenção jamais baixava — a carteira acusava R$152.077,82
        # vencidos com o dinheiro já nas duas contas. Piso em 80% (folga sobre os 84%
        # do pior caso), teto em 100,5% (ninguém paga mais que a nota; a sobra seria
        # juro, e aí não é auto-baixa).
        _rec_dmin = tx_date - timedelta(days=30)
        _rec_dmax = tx_date + timedelta(days=30)
        # O token tem que DISCRIMINAR, não ser o mais comprido: "CONDOMINIO IDEAL
        # FLORES" dava `CONDOMINIO`, que casa com todo condomínio da carteira — dois
        # candidatos, unicidade quebrada, nada baixava. Tira as palavras de tipo antes.
        _tokens = [w for w in re.split(r"[^A-Za-zÀ-ÿ]+", (nome_contraparte or "")) if len(w) >= 4]
        _tokens = [w for w in _tokens if w.upper() not in _GENERICOS] or _tokens
        _tok = max(_tokens, key=len) if _tokens else ""
        if _tok:
            cur.execute(
                """
                SELECT id, description, gross_value, net_value, due_date, status
                FROM receivable_accounts
                WHERE status = 'pendente'
                  AND gross_value > 0
                  AND %s BETWEEN gross_value * %s AND gross_value * %s
                  AND due_date BETWEEN %s AND %s
                  AND lower(coalesce(customer_name,'') || ' ' || coalesce(description,'')) LIKE lower(%s)
                LIMIT 2
                """,
                (float(valor_abs), float(RETENCAO_PISO), float(RETENCAO_TETO), _rec_dmin, _rec_dmax, f"%{_tok}%"),
            )
            _cands = cur.fetchall()
            if len(_cands) == 1:
                match = _cands[0]
                _bruto = float(_cands[0]["gross_value"])
                tipo_match = (
                    "valor_data_nome_unico"
                    if abs(_bruto - float(valor_abs)) <= float(TOLERANCE)
                    else f"liquido_data_nome_unico ({float(valor_abs) / _bruto * 100:.0f}% do bruto)"
                )

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
            # Marcar receivable como PAGA (valor do enum ReceivableStatus.PAGA; 'recebido' era órfão —
            # não existia no enum, a régua seguia cobrando e sumia dos dashboards) + vincular transação.
            cur.execute(
                """
                UPDATE receivable_accounts SET
                    status = 'paga',
                    payment_date = %s,
                    data_recebimento = %s,
                    transacao_bancaria_id = %s,
                    paid_value = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (tx_date, tx_date, tx_id, float(valor_abs), str(rec_id)),
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


def conciliar_saidas(limite: int = 2000) -> dict:
    """Auto-baixa de PAGÁVEIS por conciliação — SÓ saídas (amount<0), SÓ match EXATO (CNPJ+valor+data,
    ou valor+data com candidato ÚNICO). Não toca recebíveis. Idempotente (pula conciliado/justificado).
    Bookkeeping: marca 'pago' quando o débito bate exatamente com um pagável pendente. NÃO move dinheiro.
    Para o beat diário. Os débitos sem match exato ficam com requires_justification p/ baixa manual."""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id FROM bank_transactions
        WHERE reconciliation_status NOT IN ('conciliado', 'justificado')
          AND amount < 0
        ORDER BY transaction_date DESC
        LIMIT %s
        """,
        (limite,),
    )
    tx_ids = [str(r[0]) for r in cur.fetchall()]
    cur.close()

    baixados = 0
    sem_match = 0
    erros = 0
    for tx_id in tx_ids:
        try:
            r = conciliar_transacao(tx_id, conn)
            if r.get("tipo") == "debito_payable" and r.get("status") == "conciliado":
                baixados += 1
            else:
                sem_match += 1
        except Exception as exc:  # noqa: BLE001 — uma tx nunca derruba o batch
            erros += 1
            # LOGAR o motivo, não só contar: saber que 40 falharam sem saber
            # POR QUE é o mesmo silêncio que travou o razão em julho.
            logger.warning("[conciliacao] tx %s falhou: %s", tx_id, exc)
            try:
                conn.rollback()
            except Exception:  # noqa: BLE001, S110
                pass
    conn.close()
    return {"baixados_auto": baixados, "sem_match_ou_ambiguo": sem_match, "erros": erros, "total_saidas": len(tx_ids)}


def conciliar_recebiveis(limite: int = 2000) -> dict:
    """Auto-baixa de RECEBÍVEIS — só entradas (amount>0), match forte (nome + único),
    valor dentro da janela de retenção.

    Existe separado de `conciliar_saidas` porque a seleção é outra: aqui NÃO dá para
    pular `reconciliation_status = 'conciliado'`. Em agosto/2026 havia 5 entradas do
    Cora somando R$100.699,77 marcadas "conciliado" com `receivable_payment_id` VAZIO —
    marcadas por outro caminho, sem baixar título nenhum. Um filtro por status as
    pularia para sempre e a carteira seguiria acusando vencido com o dinheiro na conta.
    O critério certo é o VÍNCULO, não o rótulo: entrada sem título amarrado ainda tem
    trabalho a fazer.
    """
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id FROM bank_transactions
        WHERE amount > 0
          AND receivable_payment_id IS NULL
        ORDER BY transaction_date DESC
        LIMIT %s
        """,
        (limite,),
    )
    tx_ids = [str(r[0]) for r in cur.fetchall()]
    cur.close()

    baixados = sem_match = erros = 0
    for tx_id in tx_ids:
        try:
            r = conciliar_transacao(tx_id, conn, permitir_reconciliado=True)
            if r.get("tipo") == "credito_receivable" and r.get("status") == "conciliado":
                baixados += 1
            else:
                sem_match += 1
        except Exception as exc:  # noqa: BLE001 — uma tx nunca derruba o batch
            erros += 1
            logger.warning("[conciliacao] entrada %s falhou: %s", tx_id, exc)
            try:
                conn.rollback()
            except Exception:  # noqa: BLE001, S110
                pass
    parciais = _baixar_recebiveis_parcelados(conn)
    provas = _vincular_prova_de_recebimento(conn)
    conn.close()
    return {
        "baixados_auto": baixados,
        "baixados_parcelados": parciais,
        "provas_vinculadas": provas,
        "sem_match_ou_ambiguo": sem_match,
        "erros": erros,
        "total_entradas": len(tx_ids),
    }


def _vincular_prova_de_recebimento(conn) -> int:
    """Título já marcado PAGO, sem transação bancária amarrada: acha a prova e amarra.

    Não muda status nem valor — só liga o título ao dinheiro. Existe porque o casamento
    só olha título `pendente`: quando outro caminho marca 'paga' (importação, baixa
    manual, outro serviço), a prova nunca chega. Medido em 13/08/2026: 27 dos 32 títulos
    pagos não tinham NENHUMA transação por trás, e 6 deles eram de agosto — dinheiro que
    está no extrato, visível, e o título dizia "pago" por afirmação, não por fato.

    Só do CORTE CONTÁBIL para frente. O lote de março/abril nasceu marcado 'paga' sem
    data nem prova; é legado de um período que o Jordan fechou, e caçar prova lá seria
    reabrir o que ele mandou fechar.
    """
    # Sem filtro de empresa na consulta abaixo: usa o corte mais antigo, senão os
    # recebíveis de jun/jul da Patrimonial nunca seriam religados.
    from modules.financial.services.periodo_contabil import corte_mais_antigo

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT id, customer_name, gross_value, payment_date, due_date
        FROM receivable_accounts
        WHERE status = 'paga' AND transacao_bancaria_id IS NULL
          AND payment_date >= %s AND coalesce(customer_name,'') <> ''
        """,
        (corte_mais_antigo(),),
    )
    ligados = 0
    for rec in cur.fetchall():
        tokens = [w for w in re.split(r"[^A-Za-zÀ-ÿ]+", rec["customer_name"]) if len(w) >= 4]
        tokens = [w for w in tokens if w.upper() not in _GENERICOS] or tokens
        if not tokens:
            continue
        tok = max(tokens, key=len)
        bruto = Decimal(str(rec["gross_value"]))
        # DUAS âncoras, não uma. `payment_date` pode estar errado — e estava: o
        # título do Parque Gelain de 10/08 tinha payment_date 16/07, e a primeira
        # versão disto pescou um "PIX RECEBIDO INTERNO" daquele dia como prova.
        # O Gelain paga R$5.940 por boleto todo dia 10; o vínculo certo estava a
        # 25 dias dali. Exigir proximidade do VENCIMENTO também mata esse erro:
        # data de pagamento é campo editável, vencimento é do contrato.
        cur.execute(
            """
            SELECT id, amount FROM bank_transactions
            WHERE amount > 0 AND receivable_payment_id IS NULL
              AND transaction_date BETWEEN %s AND %s
              AND transaction_date BETWEEN %s AND %s
              AND lower(coalesce(counterparty_name,'')) LIKE lower(%s)
              AND amount BETWEEN %s AND %s
            """,
            (
                rec["payment_date"] - timedelta(days=5),
                rec["payment_date"] + timedelta(days=5),
                rec["due_date"] - timedelta(days=15),
                rec["due_date"] + timedelta(days=15),
                f"%{tok}%",
                float(bruto * RETENCAO_PISO),
                float(bruto * RETENCAO_TETO),
            ),
        )
        cands = cur.fetchall()
        if len(cands) != 1:
            continue  # zero ou ambíguo: sem prova única, não inventa vínculo
        tx = cands[0]
        cur.execute(
            "UPDATE bank_transactions SET receivable_payment_id = %s, "
            "reconciliation_status = 'conciliado', requires_justification = FALSE, "
            "updated_at = NOW() WHERE id = %s",
            (rec["id"], tx["id"]),
        )
        cur.execute(
            "UPDATE receivable_accounts SET transacao_bancaria_id = %s, "
            "paid_value = coalesce(paid_value, %s), updated_at = NOW() WHERE id = %s",
            (tx["id"], float(tx["amount"]), rec["id"]),
        )
        conn.commit()
        ligados += 1
        logger.info("[conciliacao] prova ligada: %s R$ %.2f", rec["customer_name"], float(tx["amount"]))
    cur.close()
    return ligados


def _baixar_recebiveis_parcelados(conn) -> int:
    """Segunda fase: título quitado em MAIS DE UM PIX.

    O Prime Arena pagou R$33.479,60 em 11/08 com dois PIX — R$26.714,26 e R$3.452,85.
    Nenhum dos dois alcança sozinho o piso de retenção (80%), então o casamento uma-a-uma
    não vê nada e o título fica "vencido" com o dinheiro na conta. Somando os dois: 90%.

    Mesmo cerco da fase 1, no conjunto: MESMO pagador, janela de ±5 dias, todas as
    entradas ainda sem título, e a SOMA dentro da janela de retenção. Se o pagador tiver
    mais de um título pendente aberto, não baixa — aí a soma é ambígua e adivinhar seria
    fabricar.
    """
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT id, customer_name, gross_value, due_date
        FROM receivable_accounts
        WHERE status = 'pendente' AND gross_value > 0 AND coalesce(customer_name,'') <> ''
        """
    )
    baixados = 0
    for rec in cur.fetchall():
        tokens = [w for w in re.split(r"[^A-Za-zÀ-ÿ]+", rec["customer_name"]) if len(w) >= 4]
        tokens = [w for w in tokens if w.upper() not in _GENERICOS] or tokens
        if not tokens:
            continue
        tok = max(tokens, key=len)
        # O pagador não pode ter outro título pendente: com dois em aberto, não dá para
        # saber qual a soma quita.
        cur.execute(
            """
            SELECT count(*) AS n FROM receivable_accounts
            WHERE status = 'pendente'
              AND lower(coalesce(customer_name,'')) LIKE lower(%s)
            """,
            (f"%{tok}%",),
        )
        if (cur.fetchone() or {}).get("n", 0) != 1:
            continue
        cur.execute(
            """
            SELECT id, amount, transaction_date FROM bank_transactions
            WHERE amount > 0 AND receivable_payment_id IS NULL
              AND transaction_date BETWEEN %s AND %s
              AND lower(coalesce(counterparty_name,'')) LIKE lower(%s)
            """,
            (rec["due_date"] - timedelta(days=5), rec["due_date"] + timedelta(days=5), f"%{tok}%"),
        )
        txs = cur.fetchall()
        if len(txs) < 2:
            continue
        soma = sum(Decimal(str(t["amount"])) for t in txs)
        bruto = Decimal(str(rec["gross_value"]))
        if not (bruto * RETENCAO_PISO <= soma <= bruto * RETENCAO_TETO):
            continue
        ultima = max(txs, key=lambda t: t["transaction_date"])
        for t in txs:
            cur.execute(
                "UPDATE bank_transactions SET reconciliation_status='conciliado', "
                "receivable_payment_id=%s, reconciled_at=%s, requires_justification=FALSE, "
                "updated_at=NOW() WHERE id=%s",
                (rec["id"], t["transaction_date"], t["id"]),
            )
        cur.execute(
            "UPDATE receivable_accounts SET status='paga', payment_date=%s, data_recebimento=%s, "
            "transacao_bancaria_id=%s, paid_value=%s, updated_at=NOW() WHERE id=%s",
            (ultima["transaction_date"], ultima["transaction_date"], ultima["id"], float(soma), rec["id"]),
        )
        conn.commit()
        baixados += 1
        logger.info(
            "[conciliacao] %s quitado por %d entradas somando R$ %.2f", rec["customer_name"], len(txs), float(soma)
        )
    cur.close()
    return baixados


def conciliar_justificados(limite: int = 4000) -> dict:
    """Segunda passada sobre os débitos JÁ CLASSIFICADOS ('justificado').

    Motivo: enquanto o contas-a-pagar tinha 69 registros, um débito de fornecedor
    não tinha nota pra casar — classificar era o fim da linha. Com as NFS-e tomadas
    registradas como pagável, esses débitos podem virar baixa provada. Sobe o débito
    de "explicado por uma pessoa" para "ligado ao documento".
    Mesmo match FORTE de sempre (nome + valor exato + único): não afrouxa nada.
    """
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id FROM bank_transactions
        WHERE reconciliation_status = 'justificado' AND amount < 0
        ORDER BY transaction_date DESC
        LIMIT %s
        """,
        (limite,),
    )
    tx_ids = [str(r[0]) for r in cur.fetchall()]
    cur.close()

    baixados = sem_match = erros = 0
    for tx_id in tx_ids:
        try:
            r = conciliar_transacao(tx_id, conn, permitir_justificado=True)
            if r.get("tipo") == "debito_payable" and r.get("status") == "conciliado":
                baixados += 1
            else:
                sem_match += 1
        except Exception as exc:  # noqa: BLE001 — uma tx nunca derruba o batch
            erros += 1
            # LOGAR o motivo, não só contar: saber que 40 falharam sem saber
            # POR QUE é o mesmo silêncio que travou o razão em julho.
            logger.warning("[conciliacao] tx %s falhou: %s", tx_id, exc)
            try:
                conn.rollback()
            except Exception:  # noqa: BLE001, S110
                pass
    conn.close()
    return {"baixados_auto": baixados, "sem_match": sem_match, "erros": erros, "total_avaliados": len(tx_ids)}


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
