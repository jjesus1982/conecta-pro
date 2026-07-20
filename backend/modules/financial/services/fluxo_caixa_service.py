"""
FluxoCaixaService — fecha o fluxo de caixa mês a mês com TODA saída justificada.

Recategoriza as saídas do extrato Inter (bank_transactions) que estão com rótulo genérico
(PIX, receita, DEBITO, outros_pagamentos, NULL) para categorias REAIS, por forense:
  - nome bate com funcionário (hr_payslips/employees) → Folha
  - descrição de tributo (DARF/GPS/DAS/FGTS/INSS/DAM/ISS) → Impostos
  - nome bate com fornecedor (nfse_tomadas_nacional / razão social) → Fornecedor
  - PIX a Jordan/Pyetra (sócios) → Pró-labore
  - valor R$32 → Diaristas VT+VR (mantém)
  - INTERNO/transferência → Transferência
  - tarifa/taxa → Tarifa bancária
  - senão → Outros (a revisar)

NUNCA fabrica: só classifica o que já existe no extrato. Preserva categorias boas já postas.
Também monta o DFC mensal (entradas × saídas por categoria × saldo).
"""

from __future__ import annotations

import html
import logging
import os
import re
import unicodedata

import psycopg2

logger = logging.getLogger(__name__)

# rótulos "ruins"/genéricos que devem ser reavaliados (os bons são preservados). 'Outros' entra
# aqui p/ ser re-julgado quando as heurísticas melhoram (ex.: passamos a reconhecer CEF=FGTS).
_GENERICOS = ("PIX", "receita", "DEBITO", "outros_pagamentos", "operacional", "Outros", "")

_STOP = {"DE", "DA", "DO", "DOS", "DAS", "E", "JUNIOR", "FILHO", "NETO", "JR", "LTDA", "ME", "EIRELI"}
_TRIBUTO = re.compile(r"DARF|GPS|\bDAS\b|FGTS|INSS|DAM |ISS|SIMPLES|GARE|GNRE|IPTU|GUIA|TRIBUT|IMPOSTO|"
                      r"RECEITA FEDERAL|PGFN|CEF MATRIZ|CAIXA ECONOMICA|00360305|CAIXA ECON", re.I)
_TARIFA = re.compile(r"TARIFA|TAXA|CESTA|ANUIDADE|IOF|JUROS|MANUTEN", re.I)
_TRANSF = re.compile(r"INTERNO|TRANSFER|APLICA|RESGATE|CDB|POUPAN", re.I)
_FORN_KW = re.compile(r"SOLIDES|PORTTE|ADVOGAD|CONTABIL|COMERCIO|COM[EÉ]RCIO|SERVI[CÇ]OS|DISTRIBUID|"
                      r"TELECOM|ENERGIA|CLARO|VIVO|TIM |SEGUR|TECNOLOGIA|LTDA| CIA| S/A|EIRELI|"
                      r"POSTO|COMBUST|MATERI|EQUIPAMENT|LOJA|ATACAD|SUPERM", re.I)
_SOCIOS = re.compile(r"JORDAN SANTOS DE JESUS|PYETRA", re.I)

# Vocabulário CANÔNICO de categorias de saída. O recategorizador (recente) escreve os rótulos
# capitalizados à direita, mas o banco ainda tem rótulos legados (caixa/acento diferentes) já
# gravados. Mapeia ambos para a MESMA chave para o DFC não fragmentar os totais por categoria.
_CAT_CANON = {
    "folha": "Folha", "folha_pagamento": "Folha", "salario": "Folha", "salarios": "Folha",
    "fornecedor": "Fornecedor", "fornecedores": "Fornecedor",
    "imposto": "Impostos", "impostos": "Impostos", "tributos": "Impostos", "tributo": "Impostos",
    "pro-labore": "Pró-labore", "pro_labore": "Pró-labore", "prolabore": "Pró-labore",
    "pró-labore": "Pró-labore", "pro labore": "Pró-labore",
    "tarifa bancaria": "Tarifa bancária", "tarifa bancária": "Tarifa bancária",
    "taxa_bancaria": "Tarifa bancária", "taxa bancaria": "Tarifa bancária", "tarifa": "Tarifa bancária",
    "transferencia": "Transferência", "transferência": "Transferência", "transf": "Transferência",
    "diaristas": "Diaristas", "diaristas vt+vr": "Diaristas VT+VR", "diaristas_vt_vr": "Diaristas VT+VR",
    "outros": "Outros", "outros_pagamentos": "Outros", "": "Outros",
}
# Categorias genéricas/não-informativas: contam como "saída NÃO categorizada" para honestidade.
_CAT_NAO_CATEGORIZADA = {"Outros", "BOLETO"}


def _cat_canon(cat: str | None) -> str:
    """Normaliza um rótulo de categoria para o vocabulário canônico único."""
    raw = (cat or "").strip()
    return _CAT_CANON.get(raw.lower(), raw or "Outros")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s.upper()).strip()


def _db_url() -> str:
    return re.sub(r"\+asyncpg|\+psycopg2?", "", os.getenv("DATABASE_URL", ""))


# Fluxo de caixa é por empresa (cada CNPJ tem seu banco: Inter=Eletrônica, Cora=Patrimonial).
# Default = Eletrônica (principal). Multi-CNPJ E7: bank_accounts.empresa_id segrega o extrato.
EMPRESA_PRINCIPAL_ID = "619a3df1-8bce-49ce-b77a-04f80a0e8491"


class FluxoCaixaService:
    def _conn(self):
        return psycopg2.connect(_db_url())

    def _tokens(self, nome: str):
        toks = [t for t in _norm(nome).split() if t not in _STOP and len(t) > 2]
        return (toks[0], toks[-1]) if len(toks) >= 2 else (None, None)

    def corrigir_recebidos(self, desde: str = "2026-01-01") -> dict:
        """Conserta o sinal dos recebimentos de cliente que o import gravou com o SINAL ERRADO
        (entrada gravada como saída) e neutraliza DUPLICATAS de boleto — sem fabricar dado.

        Dois casos tratados:
        1) 'PIX RECEBIDO' com amount<0 → é ENTRADA (crédito). Vira positivo, 'Recebimento cliente'.
        2) 'RECEBIMENTO TITULO - 112/<num>' (import 'manual'/'banking_api') é uma representação
           REDUNDANTE do mesmo boleto que já existe como 'Boleto de cobranca recebido: 112/<num>'
           (import 'csv_import', crédito canônico). Regra correta:
             - Se EXISTE o crédito canônico de mesmo número de boleto → o RECEBIMENTO TITULO é
               DUPLICATA: marca category='Duplicata boleto (ignorar)' e o DFC/contas a receber o
               excluem (senão dobra a entrada de caixa em março e nos meses seguintes).
             - Se NÃO existe par canônico (ex.: mai–jul) → o RECEBIMENTO TITULO é o ÚNICO registro
               daquele recebimento real: se está negativo (gravado como saída 'boleto_pago'),
               conserta o SINAL (vira crédito positivo 'Recebimento cliente').
        Idempotente. Nunca move dinheiro; só reinterpreta o sinal/categoria do que já existe.
        """
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                # Caso 1: PIX RECEBIDO negativo → é entrada.
                cur.execute(
                    "UPDATE bank_transactions SET amount = abs(amount), "
                    "category = 'Recebimento cliente', transaction_type = 'credit', updated_at = now() "
                    "WHERE description ILIKE %s AND amount < 0 AND transaction_date >= %s",
                    ("%RECEBIDO%", desde),
                )
                n_pix = cur.rowcount

                # Caso 2a: RECEBIMENTO TITULO que tem par canônico ('Boleto de cobranca recebido')
                # do mesmo número de boleto → DUPLICATA. Não conta no caixa (evita double-count).
                cur.execute(
                    """
                    UPDATE bank_transactions t
                    SET category = 'Duplicata boleto (ignorar)', updated_at = now()
                    WHERE t.description ILIKE 'RECEBIMENTO TITULO%%'
                      AND t.transaction_date >= %s
                      AND t.category IS DISTINCT FROM 'Duplicata boleto (ignorar)'
                      AND EXISTS (
                          SELECT 1 FROM bank_transactions c
                          WHERE c.description ILIKE 'Boleto de cobranca recebido%%'
                            AND c.amount > 0
                            AND regexp_replace(c.description, '^.*/', '')
                                = regexp_replace(t.description, '^.*/', '')
                      )
                    """,
                    (desde,),
                )
                n_dup = cur.rowcount

                # Caso 2b: RECEBIMENTO TITULO SEM par canônico e negativo → sinal errado; é entrada.
                cur.execute(
                    """
                    UPDATE bank_transactions t
                    SET amount = abs(t.amount), transaction_type = 'credit',
                        category = 'Recebimento cliente', updated_at = now()
                    WHERE t.description ILIKE 'RECEBIMENTO TITULO%%'
                      AND t.amount < 0
                      AND t.transaction_date >= %s
                      AND t.category IS DISTINCT FROM 'Duplicata boleto (ignorar)'
                      AND NOT EXISTS (
                          SELECT 1 FROM bank_transactions c
                          WHERE c.description ILIKE 'Boleto de cobranca recebido%%'
                            AND c.amount > 0
                            AND regexp_replace(c.description, '^.*/', '')
                                = regexp_replace(t.description, '^.*/', '')
                      )
                    """,
                    (desde,),
                )
                n_sinal = cur.rowcount
                conn.commit()
            return {"ok": True, "pix_recebido_corrigidos": n_pix,
                    "boleto_titulo_dedup": n_dup, "boleto_titulo_sinal_corrigido": n_sinal}
        finally:
            conn.close()

    def recategorizar_saidas(self, desde: str = "2026-01-01") -> dict:
        """Justifica cada saída genérica do extrato. Idempotente (roda sempre igual).
        Primeiro conserta os RECEBIDO (entradas gravadas como saída)."""
        self.corrigir_recebidos(desde)
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                # dicionários de nomes reais para matching
                cur.execute("SELECT DISTINCT nome FROM employees WHERE nome IS NOT NULL")
                emp_keys = {self._tokens(n) for (n,) in cur.fetchall()}
                emp_keys.discard((None, None))
                cur.execute("SELECT DISTINCT prestador_nome FROM nfse_tomadas_nacional WHERE prestador_nome IS NOT NULL")
                forn_keys = {self._tokens(n) for (n,) in cur.fetchall()}
                forn_keys.discard((None, None))
                # roster de DIARISTAS (diaria_diaristas + diarists) — PIX a eles = 'Diaristas'
                diar_keys = set()
                for tbl in ("diaria_diaristas", "diarists"):
                    try:
                        cur.execute(f"SELECT DISTINCT nome FROM {tbl} WHERE nome IS NOT NULL")
                        diar_keys |= {self._tokens(n) for (n,) in cur.fetchall()}
                    except Exception:  # noqa: S112
                        pass
                diar_keys.discard((None, None))

                cur.execute(
                    "SELECT id, description, amount FROM bank_transactions "
                    "WHERE amount < 0 AND transaction_date >= %s "
                    "AND COALESCE(category,'') = ANY(%s)",
                    (desde, list(_GENERICOS)),
                )
                linhas = cur.fetchall()
                cont = {}
                for tid, desc, amount in linhas:
                    d = _norm(desc)
                    val = abs(float(amount or 0))
                    cat = None
                    if _SOCIOS.search(desc or ""):
                        cat = "Pró-labore"
                    elif abs(val - 32.0) < 0.01:
                        cat = "Diaristas VT+VR"
                    elif _TRIBUTO.search(desc or ""):
                        cat = "Impostos"
                    elif _TARIFA.search(desc or ""):
                        cat = "Tarifa bancária"
                    elif _TRANSF.search(desc or ""):
                        cat = "Transferência"
                    else:
                        # nome de funcionário?
                        first_last = None
                        toks = [t for t in d.split() if t not in _STOP and len(t) > 2]
                        if len(toks) >= 2:
                            first_last = (toks[0], toks[-1])
                        # tenta bater pelo par (primeiro, último) presente na descrição
                        matched_emp = any((f in d and l in d) for (f, l) in emp_keys)
                        matched_forn = any((f in d and l in d) for (f, l) in forn_keys)
                        matched_diar = any((f in d and l in d) for (f, l) in diar_keys)
                        if matched_emp:
                            cat = "Folha"
                        elif matched_diar:
                            cat = "Diaristas"
                        elif matched_forn or _FORN_KW.search(desc or ""):
                            cat = "Fornecedor"
                        else:
                            cat = "Outros"
                    cur.execute(
                        "UPDATE bank_transactions SET category=%s, updated_at=now() WHERE id=%s",
                        (cat, tid),
                    )
                    cont[cat] = cont.get(cat, 0) + 1
                conn.commit()
            return {"ok": True, "reclassificadas": len(linhas), "por_categoria": cont}
        finally:
            conn.close()

    def dfc_mensal(self, ano: int = 2026, empresa_id: str = EMPRESA_PRINCIPAL_ID) -> dict:
        """Demonstrativo de Fluxo de Caixa mensal POR EMPRESA: entradas, saídas por categoria, saldo.
        Entradas de caixa = créditos do banco DA EMPRESA (Inter/Eletrônica ou Cora/Patrimonial);
        a RECEITA (accrual) vem das NFS-e da empresa (à parte). Multi-CNPJ: escopado por empresa_id."""
        conn = self._conn()
        try:
            # Garante que o sinal/dedup dos recebimentos esteja aplicado antes de somar o caixa.
            self.corrigir_recebidos(f"{ano}-01-01")
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT to_char(bt.transaction_date,'YYYY-MM') mes,
                           COALESCE(bt.category,'Outros') cat,
                           sum(CASE WHEN bt.amount < 0 THEN -bt.amount ELSE 0 END)::float saidas,
                           sum(CASE WHEN bt.amount > 0 THEN bt.amount ELSE 0 END)::float entradas
                    FROM bank_transactions bt
                    JOIN bank_accounts ba ON ba.id = bt.bank_account_id
                    WHERE to_char(bt.transaction_date,'YYYY')=%s
                      AND COALESCE(bt.category,'') <> 'Duplicata boleto (ignorar)'
                      AND ba.empresa_id = %s
                    GROUP BY 1,2 ORDER BY 1,2
                    """,
                    (str(ano), empresa_id),
                )
                rows = cur.fetchall()
                # receita real (NFS-e) por competência — da empresa
                cur.execute(
                    "SELECT competencia, sum(valor_servicos)::float FROM nfse_emitidas_nacional "
                    "WHERE competencia LIKE %s AND empresa_id = %s "
                    "AND COALESCE(cancelada, FALSE) = FALSE GROUP BY 1",
                    (f"{ano}-%", empresa_id),
                )
                receita = {c: v for c, v in cur.fetchall()}
            meses = {}
            for mes, cat, saidas, entradas in rows:
                m = meses.setdefault(mes, {
                    "entradas_caixa": 0.0, "saidas_por_categoria": {},
                    "saidas_total": 0.0, "saidas_nao_categorizadas": 0.0,
                })
                if entradas:
                    m["entradas_caixa"] += entradas
                if saidas:
                    canon = _cat_canon(cat)  # unifica rótulos legados (folha_pagamento→Folha etc.)
                    m["saidas_por_categoria"][canon] = round(m["saidas_por_categoria"].get(canon, 0) + saidas, 2)
                    m["saidas_total"] += saidas
                    if canon in _CAT_NAO_CATEGORIZADA:
                        m["saidas_nao_categorizadas"] += saidas
            out = []
            tot_saidas = tot_nao_cat = 0.0
            for mes in sorted(meses):
                m = meses[mes]
                tot_saidas += m["saidas_total"]
                tot_nao_cat += m["saidas_nao_categorizadas"]
                out.append({
                    "mes": mes,
                    "receita_nfse": round(receita.get(mes, 0.0), 2),
                    "entradas_caixa_inter": round(m["entradas_caixa"], 2),
                    "saidas_total": round(m["saidas_total"], 2),
                    "saidas_nao_categorizadas": round(m["saidas_nao_categorizadas"], 2),
                    "saldo_caixa": round(m["entradas_caixa"] - m["saidas_total"], 2),
                    "saidas_por_categoria": dict(sorted(m["saidas_por_categoria"].items(), key=lambda x: -x[1])),
                })
            pct_nao_cat = round(tot_nao_cat / tot_saidas * 100, 1) if tot_saidas else 0.0
            return {"ano": ano, "meses": out,
                    "saidas_total_ano": round(tot_saidas, 2),
                    "saidas_nao_categorizadas_ano": round(tot_nao_cat, 2),
                    "pct_saidas_nao_categorizadas": pct_nao_cat,
                    "obs": "Entradas de caixa = créditos Inter (parte das cobranças cai no Itaú, não integrado). "
                           "Receita = NFS-e emitidas (accrual). Saídas categorizadas por forense do extrato Inter; "
                           f"{pct_nao_cat}% (R$ {round(tot_nao_cat, 2)}) ainda em rótulo genérico "
                           "(Outros/BOLETO) — ver saidas_nao_categorizadas por mês."}
        finally:
            conn.close()

    def contas_a_receber(self, ano: int = 2026, empresa_id: str = EMPRESA_PRINCIPAL_ID) -> dict:
        """A Receber por competência = faturado (NFS-e emitidas) − recebido ALOCADO por AGING FIFO.

        O cliente paga 1-2 meses após a emissão, então casar recebido pelo mês da própria
        competência é errado (gerava a_receber negativo em jun/jul e R$0 recebido em jan/fev).
        Aqui o total recebido de cliente no ano é alocado às notas mais ANTIGAS primeiro (FIFO),
        e o a_receber de cada competência tem floor em 0 — recebimento futuro nunca negativa uma
        competência passada. Recebido = TODOS os créditos de cliente do extrato (ambas as grafias
        de categoria: 'Recebimento cliente' e 'Recebimento de cliente'), não só a tag exata.
        """
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT competencia, count(*), sum(valor_servicos)::float FROM nfse_emitidas_nacional "
                    "WHERE competencia LIKE %s AND empresa_id = %s "
                    "AND COALESCE(cancelada, FALSE) = FALSE GROUP BY 1 ORDER BY 1",
                    (f"{ano}-%", empresa_id))
                emit = {c: (n, v) for c, n, v in cur.fetchall()}
                # Recebido por mês de CAIXA (para exibir), cobrindo TODOS os créditos de cliente
                # DO BANCO DA EMPRESA (Inter/Eletrônica ou Cora/Patrimonial).
                cur.execute(
                    "SELECT to_char(bt.transaction_date,'YYYY-MM'), sum(bt.amount)::float "
                    "FROM bank_transactions bt JOIN bank_accounts ba ON ba.id = bt.bank_account_id "
                    "WHERE bt.amount > 0 AND to_char(bt.transaction_date,'YYYY')=%s "
                    "AND lower(COALESCE(bt.category,'')) IN "
                    "  ('recebimento cliente','recebimento de cliente','recebimento_cliente') "
                    "AND ba.empresa_id = %s "
                    "GROUP BY 1 ORDER BY 1",
                    (str(ano), empresa_id))
                receb_caixa = {m: v for m, v in cur.fetchall()}
            recebido_total = round(sum(receb_caixa.values()), 2)

            # AGING FIFO: aloca o total recebido às competências faturadas, da mais antiga p/ a mais nova.
            comps = sorted(emit)
            saldo_receb = recebido_total
            meses, tot_e = [], 0.0
            for comp in comps:
                n, faturado = emit[comp]
                tot_e += faturado
                alocado = min(saldo_receb, faturado)  # nunca aloca mais que o faturado da competência
                saldo_receb = round(saldo_receb - alocado, 2)
                a_receber = round(max(0.0, faturado - alocado), 2)  # floor em 0 (nunca negativo)
                meses.append({
                    "competencia": comp, "notas": n, "faturado": round(faturado, 2),
                    "recebido": round(alocado, 2),  # alias p/ a coluna 'Recebido' da linha na tela
                    "recebido_caixa": round(receb_caixa.get(comp, 0.0), 2),  # o que ENTROU no mês (informativo)
                    "recebido_alocado": round(alocado, 2),                    # FIFO aplicado à competência
                    "a_receber": a_receber,
                })
            total_faturado = round(tot_e, 2)
            # Crédito de cliente além do faturado do ano (ex.: pagam notas de ano anterior) fica em adiantamento.
            adiantamento = round(max(0.0, saldo_receb), 2)
            total_a_receber = round(sum(m["a_receber"] for m in meses), 2)
            return {"ano": ano, "meses": meses,
                    "total_faturado": total_faturado,
                    "total_recebido": recebido_total,
                    "total_a_receber": total_a_receber,
                    "adiantamento_ou_recebido_de_anos_anteriores": adiantamento,
                    "metodo": "aging FIFO (recebido alocado às notas mais antigas primeiro; a_receber com floor em 0)",
                    "fonte": "nfse_emitidas_nacional (só cStat 100) vs TODOS os créditos de cliente do extrato Inter"}
        finally:
            conn.close()

    def contas_a_pagar(self, ano: int = 2026) -> dict:
        """A Pagar = NFS-e tomadas (fornecedores) + folha, por competência (accrual real)."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT competencia, count(*), sum(valor_servicos)::float FROM nfse_tomadas_nacional "
                    "WHERE competencia LIKE %s GROUP BY 1 ORDER BY 1", (f"{ano}-%",))
                tom = {c: (n, v) for c, n, v in cur.fetchall()}
                cur.execute(
                    "SELECT periodo_competencia, sum(valor)::float FROM accounting_entries "
                    "WHERE conta_debito LIKE '4.1.1%%' AND periodo_competencia LIKE %s GROUP BY 1", (f"{ano}-%",))
                folha = {c: v for c, v in cur.fetchall()}
            meses, tt, tf = [], 0.0, 0.0
            for comp in sorted(set(tom) | set(folha)):
                n, fornec = tom.get(comp, (0, 0.0))
                fol = folha.get(comp, 0.0)
                tt += fornec; tf += fol
                meses.append({"competencia": comp, "fornecedores_notas": n, "fornecedores": round(fornec, 2),
                              "folha": round(fol, 2), "total": round(fornec + fol, 2)})
            return {"ano": ano, "meses": meses, "total_fornecedores": round(tt, 2),
                    "total_folha": round(tf, 2), "total_a_pagar": round(tt + tf, 2),
                    "fonte": "nfse_tomadas_nacional (compras) + folha do razão"}
        finally:
            conn.close()

    def fornecedores(self, ano: int = 2026) -> dict:
        """Fornecedores reais consolidados das NFS-e tomadas (quem prestou serviço p/ nós)."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT prestador_cnpj, max(prestador_nome), count(*), sum(valor_servicos)::float "
                    "FROM nfse_tomadas_nacional WHERE competencia LIKE %s "
                    "GROUP BY prestador_cnpj ORDER BY 4 DESC", (f"{ano}-%",))
                # Desescapa entidades XML/HTML que ficaram cruas na ingestão antiga (ex.: '&amp;').
                forn = [{"cnpj": c, "nome": html.unescape(nome or ""), "notas": n, "total": round(v, 2)}
                        for c, nome, n, v in cur.fetchall()]
            return {"ano": ano, "total_fornecedores": len(forn),
                    "valor_total": round(sum(f["total"] for f in forn), 2), "fornecedores": forn}
        finally:
            conn.close()
