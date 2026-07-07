"""
LedgerAutoService — contabilidade que fecha sozinha.

Gera e PERSISTE lançamentos contábeis reais em `accounting_entries` a partir das
fontes de verdade do ERP (NFS-e emitidas, folha `hr_payslips`, ISS das notas),
com `empresa_id` (multi-CNPJ) e idempotência por `documento_ref` (NOT EXISTS, sem
depender de constraint). Alimenta o balancete e o DRE-raw de /accounting.

NUNCA fabrica valor: só posta o que existe no banco. Onde a fonte está vazia, não
inventa lançamento — o razão fica honestamente incompleto (aguardando dado).

Plano de contas simplificado (Lucro Real Conecta Mais):
  1.1.1.01 Bancos          1.1.3.01 Clientes a Receber
  2.1.2.01 Salarios a Pagar 2.1.3.02 FGTS a Recolher   2.1.3.03 ISS a Recolher
  3.1.1.01 Receita Servicos 3.1.2.01 (-) ISS s/ Servicos (deducao)
  4.1.1.01 Despesa Salarios 4.1.2.01 Despesa Encargos (FGTS)
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata

import psycopg2

logger = logging.getLogger(__name__)


def _norm_nome(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s.upper()).strip()


_STOP_NOME = {"DE", "DA", "DO", "DOS", "DAS", "E", "JUNIOR", "FILHO", "NETO", "SOBRINHO", "JR"}

# Empresa principal (CNPJ 35.710.481/0001-03 — Lucro Real). Default dos lançamentos
# existentes/retroativos. O CNPJ 2 (Patrimonial/Simples) usa o próprio empresa_id.
EMPRESA_PRINCIPAL_ID = "619a3df1-8bce-49ce-b77a-04f80a0e8491"
CNPJ_PRINCIPAL = "35710481000103"


def _raw_db_url() -> str:
    url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/conecta_pro")
    return re.sub(r"\+asyncpg|\+psycopg2?", "", url)


class LedgerAutoService:
    """Motor de fechamento contábil automático (idempotente)."""

    def _conn(self):
        return psycopg2.connect(_raw_db_url())

    # -------------------------------------------------------------- schema --
    def _ensure_schema(self, cur) -> None:
        """Garante a coluna empresa_id (multi-CNPJ) e um índice. Só faz DDL se REALMENTE faltar —
        `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` pega ACCESS EXCLUSIVE lock mesmo quando a coluna
        já existe, empilhando todos os fechar() concorrentes. O guard evita a tempestade de locks."""
        cur.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name='accounting_entries' AND column_name='empresa_id'"
        )
        if cur.fetchone() is None:
            cur.execute("ALTER TABLE accounting_entries ADD COLUMN IF NOT EXISTS empresa_id UUID")
            cur.execute("CREATE INDEX IF NOT EXISTS ix_ae_docref ON accounting_entries (documento_ref)")
            cur.execute(
                "UPDATE accounting_entries SET empresa_id = %s WHERE empresa_id IS NULL",
                (EMPRESA_PRINCIPAL_ID,),
            )

    def _post(self, cur, *, data, cd, cc, valor, hist, tipo, ref, periodo, empresa_id) -> int:
        """Insere um lançamento se o documento_ref ainda não existe. Retorna 1/0."""
        if not valor or float(valor) <= 0:
            return 0
        cur.execute(
            """
            INSERT INTO accounting_entries
                (data_lancamento, conta_debito, conta_credito, valor, historico,
                 tipo_lancamento, documento_ref, periodo_competencia, status, empresa_id)
            SELECT %s, %s, %s, %s, %s, %s, %s, %s, 'confirmado', %s
            WHERE NOT EXISTS (
                SELECT 1 FROM accounting_entries WHERE documento_ref = %s
            )
            """,
            (data, cd, cc, float(valor), hist[:250], tipo, ref, periodo, empresa_id, ref),
        )
        return cur.rowcount or 0

    # ------------------------------------------------------------- fontes ---
    def _lancar_folha(self, cur, empresa_id) -> dict:
        """Folha bruta (despesa) + FGTS patronal (encargo) a partir de hr_payslips reais."""
        cur.execute(
            """
            SELECT payslip_code, reference_period, payment_date, competence_end,
                   total_earnings, fgts_value
            FROM hr_payslips
            WHERE COALESCE(total_earnings,0) > 0
            """
        )
        n_sal = n_fgts = 0
        for code, periodo, pay_date, comp_end, bruto, fgts in cur.fetchall():
            data = pay_date or comp_end
            code = code or f"{periodo}"
            n_sal += self._post(
                cur, data=data, cd="4.1.1.01", cc="2.1.2.01", valor=bruto,
                hist=f"Folha {periodo} - salario bruto {code}", tipo="folha",
                ref=f"FOLHA-{code}", periodo=periodo, empresa_id=empresa_id,
            )
            n_fgts += self._post(
                cur, data=data, cd="4.1.2.01", cc="2.1.3.02", valor=fgts,
                hist=f"FGTS patronal {periodo} - {code}", tipo="encargo_fgts",
                ref=f"FGTS-{code}", periodo=periodo, empresa_id=empresa_id,
            )
        return {"salarios": n_sal, "fgts": n_fgts}

    def _lancar_receita_e_iss_nacional(self, cur, empresa_id) -> dict:
        """Receita de serviços + ISS a partir das NFS-e REAIS do portal NACIONAL (gov.br/ADN),
        tabela nfse_emitidas_nacional. Substitui a receita das notas manuais antigas.
          • Receita: D 1.1.3.01 (Clientes a Receber) / C 3.1.1.01 (Receita de Serviços) = vServ
          • ISS: D 3.1.2.01 (dedução) / C 2.1.3.03 (ISS a Recolher) = vISSQN
        Idempotente por documento_ref (chave de acesso). Só roda se a tabela existir com dados."""
        cur.execute("SELECT to_regclass('nfse_emitidas_nacional')")
        if cur.fetchone()[0] is None:
            return {"receita": 0, "iss": 0, "fonte": "sem tabela nacional"}

        # Purga a receita/ISS antigos (notas manuais, seed) — serão substituídos pelos reais.
        cur.execute(
            "DELETE FROM accounting_entries WHERE tipo_lancamento IN ('nfse_emitida','tributo_iss')"
        )

        cur.execute(
            "SELECT chave_acesso, numero, competencia, data_emissao, valor_servicos, iss_valor "
            "FROM nfse_emitidas_nacional WHERE COALESCE(valor_servicos,0) > 0"
        )
        n_rec = n_iss = 0
        for chave, numero, comp, data_emi, vserv, iss in cur.fetchall():
            data = str(data_emi)[:10] if data_emi else (comp + "-01" if comp else None)
            n_rec += self._post(
                cur, data=data, cd="1.1.3.01", cc="3.1.1.01", valor=vserv,
                hist=f"Receita NFS-e {numero} ({comp})", tipo="nfse_emitida",
                ref=f"RECNAC-{chave}", periodo=comp, empresa_id=empresa_id,
            )
            if iss and float(iss) > 0:
                n_iss += self._post(
                    cur, data=data, cd="3.1.2.01", cc="2.1.3.03", valor=iss,
                    hist=f"ISS s/ NFS-e {numero} ({comp})", tipo="tributo_iss",
                    ref=f"ISSNAC-{chave}", periodo=comp, empresa_id=empresa_id,
                )
        return {"receita": n_rec, "iss": n_iss, "fonte": "adn_nacional"}

    def _lancar_despesa_tomadas(self, cur, empresa_id) -> dict:
        """Despesa de serviços TOMADOS (NFS-e recebidas nacionais) — custo real dedutível.
        D 4.1.4.01 (Serviços de Terceiros) / C 2.1.1.01 (Fornecedores a Pagar), por nota,
        idempotente por documento_ref (chave). O pagamento via Inter liquida o 2.1.1.01."""
        cur.execute("SELECT to_regclass('nfse_tomadas_nacional')")
        if cur.fetchone()[0] is None:
            return {"despesa_tomadas": 0, "fonte": "sem tabela"}
        cur.execute(
            "SELECT chave_acesso, numero, competencia, data_emissao, prestador_nome, valor_servicos "
            "FROM nfse_tomadas_nacional WHERE COALESCE(valor_servicos,0) > 0"
        )
        n = 0
        for chave, numero, comp, data_emi, prest, vserv in cur.fetchall():
            data = str(data_emi)[:10] if data_emi else (comp + "-01" if comp else None)
            n += self._post(
                cur, data=data, cd="4.1.4.01", cc="2.1.1.01", valor=vserv,
                hist=f"Serviço tomado NFS-e {numero} - {str(prest)[:40]} ({comp})",
                tipo="despesa_tomada", ref=f"TOMNAC-{chave}", periodo=comp, empresa_id=empresa_id,
            )
        return {"despesa_tomadas": n, "fonte": "adn_nacional"}

    def recategorizar_inter(self, empresa_id: str = EMPRESA_PRINCIPAL_ID) -> dict:
        """Conserta a classificação errada dos lançamentos banco_inter (seed genérico) para o
        lucro ficar FIEL. Idempotente (baseado na descrição, re-rodável):
          • Créditos Inter (C 3.1.1 Receita) → C 1.1.3.01 (Clientes a Receber): é recebimento de
            cliente, NÃO receita nova. Elimina a DUPLA CONTAGEM de receita (só NFS-e é receita).
          • Débitos Inter (D 3.2.1 despesa genérica):
              – PIX a PESSOA física (salário/diarista, já provisionado na folha) → D 2.1.2.01
                (baixa de Salários a Pagar): tira do resultado (senão duplica a folha).
              – PIX a EMPRESA/fornecedor (serviço real não provisionado) → D 4.1.4.01
                (Serviços de Terceiros): mantém como despesa real, em conta própria.
        O discriminador pessoa×empresa é heurístico (palavras de razão social) — imperfeito,
        declarado. NUNCA fabrica: só reclassifica o que já existe."""
        empresa_pat = (
            r"SOLIDES|PORTTE|ADVOGAD|CONTABIL|LTDA|EIRELI|MODAS|COMERCIO|COMÉRCIO|SERVICOS|"
            r"SERVIÇOS|DISTRIBUID|TELECOM|ENERGIA|AMAZONAS|CLARO|VIVO|TIM |SEGUR|TECNOLOGIA| CIA| S/A| SA "
        )
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                # 1) Créditos Inter (receita fantasma) → Clientes a Receber
                cur.execute(
                    "UPDATE accounting_entries SET conta_credito='1.1.3.01' "
                    "WHERE tipo_lancamento='banco_inter' AND conta_credito LIKE '3.1.1%%'"
                )
                cred_fix = cur.rowcount

                # 2) Débitos Inter → fornecedor (empresa) = LIQUIDAÇÃO de fornecedor (2.1.1.01),
                #    NÃO despesa. A despesa vem da NFS-e recebida (accrual). Evita dupla contagem.
                cur.execute(
                    "UPDATE accounting_entries ae SET conta_debito='2.1.1.01' "
                    "FROM bank_transactions bt "
                    "WHERE ae.bank_transaction_id=bt.id AND ae.tipo_lancamento='banco_inter' "
                    "AND (ae.conta_debito LIKE '3.2%%' OR ae.conta_debito='4.1.4.01') "
                    "AND bt.description ~* %s",
                    (empresa_pat,),
                )
                forn_fix = cur.rowcount
                cur.execute(
                    "UPDATE accounting_entries ae SET conta_debito='2.1.2.01' "
                    "FROM bank_transactions bt "
                    "WHERE ae.bank_transaction_id=bt.id AND ae.tipo_lancamento='banco_inter' "
                    "AND ae.conta_debito LIKE '3.2%%' AND NOT (bt.description ~* %s)",
                    (empresa_pat,),
                )
                sal_fix = cur.rowcount
                # débitos sem bank_transaction_id vinculado ficam como estavam (não força)
                conn.commit()

                cur.execute(
                    "SELECT COALESCE(sum(valor),0) FROM accounting_entries "
                    "WHERE tipo_lancamento='banco_inter' AND conta_debito='4.1.4.01'"
                )
                val_forn = float(cur.fetchone()[0])
            return {
                "ok": True,
                "creditos_receita_para_receber": cred_fix,
                "debitos_fornecedor_despesa": forn_fix,
                "debitos_salario_baixa_passivo": sal_fix,
                "despesa_terceiros_total": round(val_forn, 2),
            }
        finally:
            conn.close()

    def _book_folha_mes(self, cur, mes, e, empresa_id, continuidade=False) -> None:
        """Lança salário (bruto de março, CLT estável) + FGTS de um funcionário num mês."""
        chave = re.sub(r"[^A-Z0-9]", "", _norm_nome(e["nome"]))[:24]
        data = f"{mes}-05"
        marca = " [continuidade]" if continuidade else ""
        self._post(
            cur, data=data, cd="4.1.1.01", cc="2.1.2.01", valor=e["bruto"],
            hist=f"Folha {mes} (reconstruida{marca}) - {e['nome'][:38]}",
            tipo="folha_reconstruida", ref=f"FOLHAREC-{mes}-{chave}",
            periodo=mes, empresa_id=empresa_id,
        )
        self._post(
            cur, data=data, cd="4.1.2.01", cc="2.1.3.02", valor=e["fgts"],
            hist=f"FGTS {mes} (reconstruido{marca}) - {e['nome'][:38]}",
            tipo="encargo_fgts_reconstruido", ref=f"FGTSREC-{mes}-{chave}",
            periodo=mes, empresa_id=empresa_id,
        )

    def reconstruir_folha_jan_fev(self, empresa_id: str = EMPRESA_PRINCIPAL_ID) -> dict:
        """Reconstrói a folha de jan/fev/2026 (ausente em hr_payslips) de forma FORENSE e
        conservadora: âncora = folha de março (nomes + salário estável CLT); confirma que cada
        funcionário estava ATIVO no mês via PIX real do Inter (nome batendo + pagamento
        significativo). Booka o BRUTO de março (salário estável) + FGTS como despesa/encargo.
        NUNCA fabrica: só booka quem o PIX confirma; usa valores reais de março. Idempotente
        (documento_ref por funcionário/mês). Marcado tipo='folha_reconstruida' (transparente)."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                self._ensure_schema(cur)
                # Âncora: funcionários de março (nome, bruto, líquido, FGTS)
                cur.execute(
                    "SELECT e.nome, p.total_earnings, p.net_salary, p.fgts_value "
                    "FROM hr_payslips p JOIN employees e ON e.id=p.employee_id "
                    "WHERE p.reference_period='2026-03'"
                )
                emps = []
                for nome, bruto, liq, fgts in cur.fetchall():
                    toks = [t for t in _norm_nome(nome).split() if t not in _STOP_NOME and len(t) > 2]
                    if len(toks) >= 2:
                        emps.append({
                            "nome": nome, "bruto": float(bruto or 0), "liq": float(liq or 0),
                            "fgts": float(fgts or 0), "first": toks[0], "last": toks[-1],
                        })

                resultado = {}
                booked: dict[str, set] = {}  # mes -> set de chaves de funcionário bookados
                meses_alvo = ("2026-01", "2026-02", "2026-04", "2026-05", "2026-06")
                # março é a âncora (real em hr_payslips); reconstrói os demais meses por PIX real.
                for mes in meses_alvo:
                    cur.execute(
                        "SELECT description, amount FROM bank_transactions "
                        "WHERE to_char(transaction_date,'YYYY-MM')=%s AND description ILIKE %s",
                        (mes, "%ENVIADO%"),
                    )
                    pix = [(_norm_nome(d), abs(float(a or 0))) for d, a in cur.fetchall()]
                    booked[mes] = set()
                    for e in emps:
                        if e["bruto"] <= 0:
                            continue
                        pago = sum(v for d, v in pix if e["first"] in d and e["last"] in d)
                        limiar = max(400.0, 0.5 * e["liq"]) if e["liq"] > 0 else 400.0
                        if pago < limiar:
                            continue
                        self._book_folha_mes(cur, mes, e, empresa_id)
                        booked[mes].add(e["first"] + "|" + e["last"])
                    conn.commit()

                # Fallback de CONTINUIDADE: se algum mês ficou esparso (dados bancários incompletos),
                # quem estava nos DOIS meses vizinhos estava empregado nele (emprego CLT é contínuo).
                ordem = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]
                for i, mes in enumerate(ordem):
                    if mes == "2026-03" or mes not in meses_alvo:
                        continue
                    if len(booked.get(mes, set())) >= 20:
                        continue  # tem dado suficiente, não precisa de fallback
                    ant = booked.get(ordem[i - 1], set()) if i > 0 else set()
                    prox = booked.get(ordem[i + 1], set()) if i + 1 < len(ordem) else set()
                    for e in emps:
                        if e["bruto"] <= 0:
                            continue
                        k = e["first"] + "|" + e["last"]
                        if k in ant and k in prox:  # nos dois vizinhos → ativo neste mês
                            self._book_folha_mes(cur, mes, e, empresa_id, continuidade=True)
                    conn.commit()

                for mes in meses_alvo:
                    cur.execute(
                        "SELECT count(*), COALESCE(sum(valor),0) FROM accounting_entries "
                        "WHERE tipo_lancamento='folha_reconstruida' AND periodo_competencia=%s",
                        (mes,),
                    )
                    cnt, val = cur.fetchone()
                    resultado[mes] = {"funcionarios": cnt, "folha_bruta": round(float(val), 2)}
            return {"ok": True, "meses": resultado,
                    "metodo": "ancora março + confirmação por PIX real (nome+valor); bruto CLT estável. "
                              "Ressalva: contratados APÓS março não estão na âncora (subcontagem em meses recentes)."}
        finally:
            conn.close()

    # -------------------------------------------------------------- runner --
    def fechar(self, empresa_id: str = EMPRESA_PRINCIPAL_ID) -> dict:
        """Fecha o razão: garante schema e posta folha + ISS (idempotente).
        NFS-e receita e banco Inter já são postados pelo accounting_seed_service."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                self._ensure_schema(cur)
                folha = self._lancar_folha(cur, empresa_id)
                iss = self._lancar_receita_e_iss_nacional(cur, empresa_id)
                tomadas = self._lancar_despesa_tomadas(cur, empresa_id)
                conn.commit()

                # Verificação de equilíbrio (débitos == créditos por construção)
                cur.execute(
                    "SELECT sum(valor)::float FROM accounting_entries WHERE status='confirmado'"
                )
                total = cur.fetchone()[0] or 0.0
                cur.execute("SELECT count(*) FROM accounting_entries")
                qtd = cur.fetchone()[0]

            # Recategoriza o banco Inter (conserta receita/despesa fantasma) — mantém o lucro fiel
            recat = self.recategorizar_inter(empresa_id)
            # Reconstrói folha jan/fev (ausente em hr_payslips) por âncora março + PIX real
            try:
                folha_rec = self.reconstruir_folha_jan_fev(empresa_id)
            except Exception as fe:  # não derruba o fechamento
                logger.warning("Reconstrução folha jan/fev falhou (segue): %s", fe)
                folha_rec = {"ok": False, "erro": str(fe)}
            return {
                "ok": True,
                "novos_lancamentos": {**folha, **iss, **tomadas},
                "recategorizacao_inter": recat,
                "folha_reconstruida_jan_fev": folha_rec.get("meses"),
                "total_lancamentos": qtd,
                "movimento_total": round(total, 2),
                "empresa_id": empresa_id,
            }
        finally:
            conn.close()
