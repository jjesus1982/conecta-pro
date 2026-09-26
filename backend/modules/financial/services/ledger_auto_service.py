"""
LedgerAutoService — contabilidade que fecha sozinha.

Gera e PERSISTE lançamentos contábeis reais em `accounting_entries` a partir das
fontes de verdade do ERP (NFS-e emitidas, folha `hr_payslips`, ISS das notas),
com `empresa_id` (multi-CNPJ) e idempotência por `documento_ref` (NOT EXISTS, sem
depender de constraint). Alimenta o balancete e o DRE-raw de /accounting.

NUNCA fabrica valor: só posta o que existe no banco. Onde a fonte está vazia, não
inventa lançamento — o razão fica honestamente incompleto (aguardando dado).

Plano de contas simplificado (Lucro Real Conecta Mais):
  1.1.1.01 Bancos          1.1.2.01 Clientes a Receber
  2.1.1.01 Salarios a Pagar 2.1.1.02 FGTS a Recolher   2.1.2.01 ISS a Recolher
  4.1.1.01 Receita Servicos 5.2.2.01 (-) ISS s/ Servicos (deducao)
  5.1.1.01 Despesa Salarios 5.1.1.02 Despesa Encargos (FGTS)
"""

from __future__ import annotations

import calendar
import logging
import os
import re
import unicodedata
from datetime import date

import psycopg2

from modules.financial.services.periodo_contabil import periodo_fechado as _periodo_fechado

logger = logging.getLogger(__name__)


def _norm_nome(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s.upper()).strip()


_STOP_NOME = {"DE", "DA", "DO", "DOS", "DAS", "E", "JUNIOR", "FILHO", "NETO", "SOBRINHO", "JR"}

# Empresa principal (CNPJ 35.710.481/0001-03 — Lucro Real). Default dos lançamentos
# existentes/retroativos. O CNPJ 2 (Patrimonial/Simples) usa o próprio empresa_id.
EMPRESA_PRINCIPAL_ID = "619a3df1-8bce-49ce-b77a-04f80a0e8491"
CNPJ_PRINCIPAL = "35710481000103"


def _fim_do_mes(periodo: str | None) -> date | None:
    """'2026-07' → date(2026, 7, 31). Data de competência quando o holerite não
    traz payment_date nem competence_end. Devolve None se não der pra derivar."""
    m = re.match(r"^(\d{4})-(\d{1,2})$", str(periodo or "").strip())
    if not m:
        return None
    ano, mes = int(m.group(1)), int(m.group(2))
    if not 1 <= mes <= 12:
        return None
    return date(ano, mes, calendar.monthrange(ano, mes)[1])


def _raw_db_url() -> str:
    url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/conecta_pro")
    return re.sub(r"\+asyncpg|\+psycopg2?", "", url)


class LedgerAutoService:
    """Motor de fechamento contábil automático (idempotente)."""

    def __init__(self) -> None:
        #: Lançamentos recusados por caírem em período fechado (antes do CORTE_CONTABIL).
        #: A recusa é correta — jan–jul foram vividos fora do sistema — mas precisa ser
        #: CONTADA: nota de competência antiga que chega hoje pelo ADN é recusada para
        #: sempre, e antes disso só deixava uma linha de log que ninguém lê.
        self.recusados_periodo_fechado: list[dict] = []

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
        """Insere um lançamento se o documento_ref ainda não existe. Retorna 1/0.

        `data` NULL é RECUSADO aqui: `data_lancamento` é NOT NULL, e um único
        registro sem data derrubava a transação inteira — o fechamento da empresa
        toda ia junto (o razão parou em julho/2026 por causa disso). Recusar 1
        lançamento é infinitamente melhor que perder o fechamento.
        """
        if not valor or float(valor) <= 0 or data is None:
            return 0
        if isinstance(data, str):
            # Receita/ISS e tomadas chegam com data em TEXTO ('2026-08-26'); comparar str com
            # date em `periodo_fechado` levantava TypeError, a transação inteira voltava e o
            # razão parou em 11/08/2026 — 27 dias sem folha, nota ou tomada (achado 07/09).
            data = date.fromisoformat(data[:10])
        if _periodo_fechado(data, empresa_id):
            # Período anterior ao corte (01/08/2026) está fechado: de janeiro a
            # julho a empresa operou FORA do sistema, e deixar lançamento novo
            # cair lá contamina todo relatório acumulado em silêncio.
            #
            # A recusa é correta; o SILÊNCIO não era. Uma nota de competência anterior
            # ao corte que chega hoje pelo ADN é recusada para sempre e some — medido em
            # 25/09/2026: as NFS-e 3 e 4 da Patrimonial (junho/2026, R$ 108.386,92)
            # chegaram às 08:30 daquele dia e nunca entraram no razão. Agora fica contado
            # e sobe no resultado do fechamento.
            self.recusados_periodo_fechado.append(
                {"data": str(data), "ref": ref, "valor": float(valor), "historico": hist[:120]}
            )
            logger.info("lançamento em período fechado recusado: %s %s", data, ref)
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
        # UMA FONTE POR COMPETÊNCIA. Cada funcionário tem DOIS holerites por mês —
        # o do nosso motor ('conecta') e o espelho da Portte — e lançar os dois
        # DOBRAVA a despesa de pessoal no razão: R$692.818,98 a mais em 7 meses
        # (jun/2026: 56 funcionários, 112 holerites, 112 lançamentos). O erro era
        # invisível porque os dois espelhos batem quase ao centavo
        # (jun: 111.340,74 × 111.388,40) — o total parecia coerente, só que era 2×.
        # Portte é a verdade fiscal [[feedback_portte_fonte_verdade]]; onde ela não
        # existir, cai no motor. Mesma regra do gerador de pagáveis.
        cur.execute(
            """
            SELECT payslip_code, reference_period, payment_date, competence_end,
                   total_earnings, fgts_value
            FROM (
                SELECT h.*, ROW_NUMBER() OVER (
                    PARTITION BY h.reference_period, h.employee_id
                    ORDER BY (h.source_system = 'portte') DESC, h.payslip_code
                ) AS prioridade
                FROM hr_payslips h
                WHERE COALESCE(h.total_earnings,0) > 0 AND h.empresa_id = %s
            ) t
            WHERE prioridade = 1
            """,
            (empresa_id,),
        )
        n_sal = n_fgts = 0
        sem_data = futuros = 0
        hoje = date.today()
        for code, periodo, pay_date, comp_end, bruto, fgts in cur.fetchall():
            # 456 dos 821 holerites (os gerados pelo nosso motor) não têm data
            # nenhuma — só a competência. Regime de COMPETÊNCIA: a obrigação nasce
            # no último dia do mês de referência.
            data = pay_date or comp_end or _fim_do_mes(periodo)
            if data is None:
                sem_data += 1
                continue
            # Não se fecha período que ainda não aconteceu. Sem esta guarda, folha
            # com competência futura (ex.: 2026-11/12 na Eletrônica, 47+47 registros
            # de total idêntico) entraria no razão como despesa real.
            if (data.year, data.month) > (hoje.year, hoje.month):
                futuros += 1
                continue
            code = code or f"{periodo}"
            n_sal += self._post(
                cur,
                data=data,
                cd="5.1.1.01",
                cc="2.1.1.01",
                valor=bruto,
                hist=f"Folha {periodo} - salario bruto {code}",
                tipo="folha",
                ref=f"FOLHA-{code}",
                periodo=periodo,
                empresa_id=empresa_id,
            )
            n_fgts += self._post(
                cur,
                data=data,
                cd="5.1.1.02",
                cc="2.1.1.02",
                valor=fgts,
                hist=f"FGTS patronal {periodo} - {code}",
                tipo="encargo_fgts",
                ref=f"FGTS-{code}",
                periodo=periodo,
                empresa_id=empresa_id,
            )
        return {
            "salarios": n_sal,
            "fgts": n_fgts,
            "sem_data_ignorados": sem_data,
            "competencia_futura_ignorados": futuros,
        }

    def _lancar_receita_e_iss_nacional(self, cur, empresa_id) -> dict:
        """Receita de serviços + ISS a partir das NFS-e REAIS do portal NACIONAL (gov.br/ADN),
        tabela nfse_emitidas_nacional. Substitui a receita das notas manuais antigas.
          • Receita: D 1.1.2.01 (Clientes a Receber) / C 4.1.1.01 (Receita de Serviços) = vServ
          • ISS: D 5.2.2.01 (dedução) / C 2.1.2.01 (ISS a Recolher) = vISSQN
        Idempotente por documento_ref (chave de acesso). Só roda se a tabela existir com dados."""
        cur.execute("SELECT to_regclass('nfse_emitidas_nacional')")
        if cur.fetchone()[0] is None:
            return {"receita": 0, "iss": 0, "fonte": "sem tabela nacional"}

        # No SIMPLES NACIONAL o ISS não é tributo à parte: ele é um COMPONENTE do DAS.
        # Provado na própria guia da Patrimonial em 26/09/2026 — o DAS de 07/2026
        # (R$ 17.048,87) traz "1010 ISS - SIMPLES NACIONAL R$ 4.709,56" dentro dele, e o
        # de 08/2026 traz R$ 6.311,95. Postar o ISS destacado na NFS-e ALÉM do DAS conta
        # o mesmo imposto duas vezes; e o passivo 2.1.2.01 que nascia disso nunca era
        # baixado (5 créditos, R$ 9.792,84, ZERO débitos) porque não há o que pagar.
        # A alíquota que aparece na nota (2,01% → 4,36% em quatro meses) é a alíquota
        # EFETIVA de ISS do Simples subindo com o RBT12, não um ISS municipal próprio.
        cur.execute("SELECT regime_tributario FROM empresas WHERE id = %s", (empresa_id,))
        linha = cur.fetchone()
        iss_no_das = ((linha[0] if linha else "") or "") == "simples_nacional"

        # Purga a receita/ISS antigos DESTA empresa (idempotência do repost) — ESCOPADO por
        # empresa_id: sem o filtro, fechar(Patrimonial) apagaria os lançamentos da Eletrônica
        # (e vice-versa). Multi-CNPJ: cada razão só mexe no que é seu.
        # SÓ o período aberto (>= corte): o repost abaixo é recusado antes do corte por
        # `_post`, então purgar tudo apagaria jan–jul (182 lançamentos, R$ 1,96 mi) e não
        # reporia — o razão arqueológico sumiria no primeiro fechamento (achado 07/09/2026).
        from modules.financial.services.periodo_contabil import corte_da_empresa

        cur.execute(
            "DELETE FROM accounting_entries "
            "WHERE tipo_lancamento IN ('nfse_emitida','tributo_iss','inss_retido_fonte') "
            "AND empresa_id = %s AND data_lancamento >= %s",
            (empresa_id, corte_da_empresa(empresa_id)),
        )

        # SÓ as notas DESTA empresa. Sem o filtro empresa_id, as 6 notas da Patrimonial
        # (Simples) caíam no razão da Eletrônica (Lucro Real) — contaminação de regime.
        cur.execute(
            "SELECT chave_acesso, numero, competencia, data_emissao, valor_servicos, iss_valor, "
            "       COALESCE(inss_retido, 0) "
            "FROM nfse_emitidas_nacional WHERE COALESCE(valor_servicos,0) > 0 AND empresa_id = %s "
            "AND COALESCE(cancelada, FALSE) = FALSE "  # nota cancelada não vira receita/ISS
            # Nota de HOMOLOGAÇÃO não é faturamento. Sem este filtro, toda nota de teste
            # virava receita de verdade no razão: em 24/09/2026 duas notas de homologação
            # (nº 8 e 9, R$ 1.500) entraram no DRE de setembro como faturamento real.
            "AND COALESCE(ambiente, '') <> 'homologacao'",
            (empresa_id,),
        )
        n_rec = n_iss = 0
        n_ret = 0
        for chave, numero, comp, data_emi, vserv, iss, inss_ret in cur.fetchall():
            data = str(data_emi)[:10] if data_emi else (comp + "-01" if comp else None)
            n_rec += self._post(
                cur,
                data=data,
                cd="1.1.2.01",
                cc="4.1.1.01",
                valor=vserv,
                hist=f"Receita NFS-e {numero} ({comp})",
                tipo="nfse_emitida",
                ref=f"RECNAC-{chave}",
                periodo=comp,
                empresa_id=empresa_id,
            )
            # Os 11% da Lei 9.711/98 que o tomador retém na cessão de mão de obra: o cliente
            # paga a nota MENOS esse valor e recolhe a diferença ao INSS em nosso nome. Sem
            # este lançamento o valor ficava eternamente em "Clientes a Receber" como se
            # fosse inadimplência — R$ 175.000,18 nas duas empresas em 26/09/2026, dos quais
            # R$ 84.709,90 da Patrimonial. É crédito a compensar, e a própria DCTFWeb o
            # reconhece como "Retenção Lei 9711/98" (R$ 19.544,08 informados em 08/2026).
            if inss_ret and float(inss_ret) > 0:
                n_ret += self._post(
                    cur,
                    data=data,
                    cd="1.1.3.02",
                    cc="1.1.2.01",
                    valor=inss_ret,
                    hist=f"INSS retido na fonte s/ NFS-e {numero} ({comp}) - Lei 9.711/98",
                    tipo="inss_retido_fonte",
                    ref=f"RETINSS-{chave}",
                    periodo=comp,
                    empresa_id=empresa_id,
                )
            if iss and float(iss) > 0 and not iss_no_das:
                n_iss += self._post(
                    cur,
                    data=data,
                    cd="5.2.2.01",
                    cc="2.1.2.01",
                    valor=iss,
                    hist=f"ISS s/ NFS-e {numero} ({comp})",
                    tipo="tributo_iss",
                    ref=f"ISSNAC-{chave}",
                    periodo=comp,
                    empresa_id=empresa_id,
                )
        return {
            "receita": n_rec,
            "iss": n_iss,
            "iss_dentro_do_das": iss_no_das,
            "inss_retido_fonte": n_ret,
            "fonte": "adn_nacional",
        }

    def _lancar_despesa_tomadas(self, cur, empresa_id) -> dict:
        """Despesa de serviços TOMADOS (NFS-e recebidas nacionais) — custo real dedutível.
        D 5.2.1.04 (Serviços de Terceiros) / C 2.1.4.01 (Fornecedores a Pagar), por nota,
        idempotente por documento_ref (chave). O pagamento via Inter liquida o 2.1.4.01."""
        cur.execute("SELECT to_regclass('nfse_tomadas_nacional')")
        if cur.fetchone()[0] is None:
            return {"despesa_tomadas": 0, "fonte": "sem tabela"}
        cur.execute(
            "SELECT chave_acesso, numero, competencia, data_emissao, prestador_nome, valor_servicos "
            "FROM nfse_tomadas_nacional WHERE COALESCE(valor_servicos,0) > 0 AND empresa_id = %s",
            (empresa_id,),
        )
        n = 0
        for chave, numero, comp, data_emi, prest, vserv in cur.fetchall():
            data = str(data_emi)[:10] if data_emi else (comp + "-01" if comp else None)
            n += self._post(
                cur,
                data=data,
                cd="5.2.1.04",
                cc="2.1.4.01",
                valor=vserv,
                hist=f"Serviço tomado NFS-e {numero} - {str(prest)[:40]} ({comp})",
                tipo="despesa_tomada",
                ref=f"TOMNAC-{chave}",
                periodo=comp,
                empresa_id=empresa_id,
            )
        return {"despesa_tomadas": n, "fonte": "adn_nacional"}

    def recategorizar_inter(self, empresa_id: str = EMPRESA_PRINCIPAL_ID) -> dict:
        """Conserta a classificação errada dos lançamentos banco_inter (seed genérico) para o
        lucro ficar FIEL. Idempotente (baseado na descrição, re-rodável):
          • Créditos Inter (C 3.1.1 Receita) → C 1.1.2.01 (Clientes a Receber): é recebimento de
            cliente, NÃO receita nova. Elimina a DUPLA CONTAGEM de receita (só NFS-e é receita).
          • Débitos Inter (D 3.2.1 despesa genérica):
              – PIX a PESSOA física (salário/diarista, já provisionado na folha) → D 2.1.1.01
                (baixa de Salários a Pagar): tira do resultado (senão duplica a folha).
              – PIX a EMPRESA/fornecedor (serviço real não provisionado) → D 5.2.1.04
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
                    "UPDATE accounting_entries SET conta_credito='1.1.2.01' "
                    "WHERE tipo_lancamento='banco_inter' AND conta_credito LIKE '3.1.1%%'"
                )
                cred_fix = cur.rowcount

                # 2) Débitos Inter → fornecedor (empresa) = LIQUIDAÇÃO de fornecedor (2.1.4.01),
                #    NÃO despesa. A despesa vem da NFS-e recebida (accrual). Evita dupla contagem.
                cur.execute(
                    "UPDATE accounting_entries ae SET conta_debito='2.1.4.01' "
                    "FROM bank_transactions bt "
                    "WHERE ae.bank_transaction_id=bt.id AND ae.tipo_lancamento='banco_inter' "
                    "AND (ae.conta_debito LIKE '3.2%%' OR ae.conta_debito='5.2.1.04') "
                    "AND bt.description ~* %s",
                    (empresa_pat,),
                )
                forn_fix = cur.rowcount
                cur.execute(
                    "UPDATE accounting_entries ae SET conta_debito='2.1.1.01' "
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
                    "WHERE tipo_lancamento='banco_inter' AND conta_debito='5.2.1.04'"
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
            cur,
            data=data,
            cd="5.1.1.01",
            cc="2.1.1.01",
            valor=e["bruto"],
            hist=f"Folha {mes} (reconstruida{marca}) - {e['nome'][:38]}",
            tipo="folha_reconstruida",
            ref=f"FOLHAREC-{mes}-{chave}",
            periodo=mes,
            empresa_id=empresa_id,
        )
        self._post(
            cur,
            data=data,
            cd="5.1.1.02",
            cc="2.1.1.02",
            valor=e["fgts"],
            hist=f"FGTS {mes} (reconstruido{marca}) - {e['nome'][:38]}",
            tipo="encargo_fgts_reconstruido",
            ref=f"FGTSREC-{mes}-{chave}",
            periodo=mes,
            empresa_id=empresa_id,
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
                        emps.append(
                            {
                                "nome": nome,
                                "bruto": float(bruto or 0),
                                "liq": float(liq or 0),
                                "fgts": float(fgts or 0),
                                "first": toks[0],
                                "last": toks[-1],
                            }
                        )

                resultado = {}
                booked: dict[str, set] = {}  # mes -> set de chaves de funcionário bookados
                # SÓ reconstrói meses SEM folha real em hr_payslips. A reconstrução é um fallback
                # FORENSE para quando a folha real está ausente; quando ela chega (ex.: espelho
                # Portte jan-jun), a real é a verdade e a reconstruída DEVE sumir — senão o razão
                # fica com folha_reconstruida + folha (refs diferentes, não deduplicam) = DOBRO.
                cur.execute("SELECT DISTINCT reference_period FROM hr_payslips WHERE COALESCE(total_earnings,0) > 0")
                _reais = {r[0] for r in cur.fetchall()}
                meses_alvo = tuple(
                    m for m in ("2026-01", "2026-02", "2026-04", "2026-05", "2026-06") if m not in _reais
                )
                if not meses_alvo:
                    return {
                        "ok": True,
                        "meses": {},
                        "metodo": "sem reconstrução — folha real (hr_payslips) presente em todos os meses.",
                    }
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
            return {
                "ok": True,
                "meses": resultado,
                "metodo": "ancora março + confirmação por PIX real (nome+valor); bruto CLT estável. "
                "Ressalva: contratados APÓS março não estão na âncora (subcontagem em meses recentes).",
            }
        finally:
            conn.close()

    # -------------------------------------------------------------- runner --
    def lancar_provisoes_trabalhistas(self, empresa_id: str = EMPRESA_PRINCIPAL_ID) -> dict:
        """Posta as provisões de férias (1/9) e 13º (1/12) sobre a folha REAL (hr_payslips),
        agregadas por competência. Idempotente por documento_ref (PROVFER-/PROV13- por mês).
          • Férias: D 5.1.1.05 (Desp. Provisão Férias) / C 2.1.1.01 (Provisões a Pagar)
          • 13º:    D 5.1.1.05 (Desp. Provisão 13º)     / C 2.1.1.01
        Mesma base da tela de Provisões (base_salary × 0,1111 / 0,0833) — sem encargos sobre a
        provisão. Bookkeeping puro: NÃO move dinheiro. Reversível apagando os refs PROVFER-/PROV13-."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                self._ensure_schema(cur)
                cur.execute(
                    "SELECT reference_period, COALESCE(sum(base_salary),0) FROM hr_payslips "
                    "WHERE COALESCE(base_salary,0) > 0 GROUP BY reference_period ORDER BY reference_period"
                )
                n_fer = n_dec = 0
                tot_fer = tot_dec = 0.0
                for periodo, base in cur.fetchall():
                    base = float(base or 0)
                    fer = round(base * 0.1111, 2)
                    dec = round(base * 0.0833, 2)
                    data = f"{periodo}-01"
                    n_fer += self._post(
                        cur,
                        data=data,
                        cd="5.1.1.05",
                        cc="2.1.1.01",
                        valor=fer,
                        hist=f"Provisão de férias {periodo} (1/9 s/ folha real)",
                        tipo="provisao_ferias",
                        ref=f"PROVFER-{periodo}",
                        periodo=periodo,
                        empresa_id=empresa_id,
                    )
                    n_dec += self._post(
                        cur,
                        data=data,
                        cd="5.1.1.05",
                        cc="2.1.1.01",
                        valor=dec,
                        hist=f"Provisão de 13º {periodo} (1/12 s/ folha real)",
                        tipo="provisao_13",
                        ref=f"PROV13-{periodo}",
                        periodo=periodo,
                        empresa_id=empresa_id,
                    )
                    tot_fer += fer
                    tot_dec += dec
                conn.commit()
            return {
                "ok": True,
                "provisoes_ferias": n_fer,
                "provisoes_13": n_dec,
                "total_ferias": round(tot_fer, 2),
                "total_13": round(tot_dec, 2),
                "total_provisionado": round(tot_fer + tot_dec, 2),
                "empresa_id": empresa_id,
            }
        finally:
            conn.close()

    def lancar_inss_empregado(self, empresa_id: str = EMPRESA_PRINCIPAL_ID) -> dict:
        """Posta o INSS retido do EMPREGADO no razão, por competência, da VERDADE Portte
        (hr_payslips.inss_value). É reclassificação da folha bruta (já lançada em 4.1.1/2.1.1.01):
          D 2.1.1.01 (Salários a Pagar) / C 2.1.1.03 (INSS a Recolher) = inss_value
        NÃO adiciona despesa (o bruto já capturou) — só separa o passivo. Idempotente por
        ref INSSEMP-{periodo}. Converge o razão à lógica progressiva da Portte sobre inss_base.
        O INSS (DARF/eSocial) do grupo é declarado sob o CNPJ1 (Eletrônica) — todas as guias
        validam 35.710.481 — então soma TODA a folha e posta sob a Eletrônica (não segue o
        empregador da folha; só salários/FGTS seguem)."""
        if empresa_id != EMPRESA_PRINCIPAL_ID:
            return {"ok": True, "lancamentos": 0, "motivo": "INSS declarado sob o CNPJ1 (Eletrônica)"}
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                self._ensure_schema(cur)
                cur.execute(
                    "SELECT reference_period, COALESCE(sum(inss_value),0) FROM hr_payslips "
                    "WHERE COALESCE(inss_value,0) > 0 "
                    "GROUP BY reference_period ORDER BY reference_period"
                )
                n, tot = 0, 0.0
                for periodo, val in cur.fetchall():
                    val = float(val or 0)
                    n += self._post(
                        cur,
                        data=f"{periodo}-01",
                        cd="2.1.1.01",
                        cc="2.1.1.03",
                        valor=val,
                        hist=f"INSS retido empregado {periodo} (verdade Portte)",
                        tipo="inss_empregado",
                        ref=f"INSSEMP-{periodo}",
                        periodo=periodo,
                        empresa_id=empresa_id,
                    )
                    tot += val
                conn.commit()
            return {"ok": True, "lancamentos": n, "total_inss": round(tot, 2), "empresa_id": empresa_id}
        finally:
            conn.close()

    def lancar_inss_patronal(self, empresa_id: str = EMPRESA_PRINCIPAL_ID) -> dict:
        """Posta o INSS PATRONAL (CPP+RAT+terceiros) no razão, por competência, como a
        diferença REAL entre a guia INSS oficial (Onvio, `inss_guias.valor`) e o INSS
        retido do empregado (`hr_payslips.inss_value`, já postado por lancar_inss_empregado):
          D 5.1.1.02 (Despesa Encargo INSS patronal) / C 2.1.1.03 (INSS a Recolher)
        Faz o passivo INSS a Recolher fechar com a guia oficial. NUNCA fabrica: só posta onde
        há guia extraída com valor > retido (patronal > 0). Idempotente por ref INSSPAT-{periodo}.
        mes_ref da guia é 'MM.YYYY' → converte p/ 'YYYY-MM'.
        A guia INSS (DARF) é sempre da Eletrônica (CNPJ1) — o patronal é dela mesmo que a folha
        do mês esteja na Patrimonial. Posta só sob o CNPJ1, somando TODA a folha do grupo."""
        if empresa_id != EMPRESA_PRINCIPAL_ID:
            return {"ok": True, "lancamentos": 0, "motivo": "INSS patronal (DARF) é do CNPJ1 (Eletrônica)"}
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                self._ensure_schema(cur)
                cur.execute(
                    r"SELECT substring(mes_ref from 4 for 4) || '-' || substring(mes_ref from 1 for 2), "
                    r"sum(valor) FROM inss_guias WHERE valor IS NOT NULL "
                    r"AND mes_ref ~ '^[0-9]{2}\.[0-9]{4}$' GROUP BY 1"
                )
                guias = {p: float(g or 0) for p, g in cur.fetchall()}
                # Toda a folha do grupo — o INSS é declarado sob a Eletrônica (a guia é dela).
                cur.execute(
                    "SELECT reference_period, COALESCE(sum(inss_value),0) FROM hr_payslips "
                    "WHERE COALESCE(inss_value,0) > 0 GROUP BY 1"
                )
                emp = {p: float(v or 0) for p, v in cur.fetchall()}
                n, tot = 0, 0.0
                for periodo in sorted(emp):
                    guia = guias.get(periodo, 0.0)
                    patronal = round(guia - emp.get(periodo, 0.0), 2)
                    if guia <= 0 or patronal <= 0:  # sem guia oficial > retido → não inventa
                        continue
                    n += self._post(
                        cur,
                        data=f"{periodo}-01",
                        cd="5.1.1.02",
                        cc="2.1.1.03",
                        valor=patronal,
                        hist=f"INSS patronal {periodo} (guia Onvio - retido empregado)",
                        tipo="encargo_inss",
                        ref=f"INSSPAT-{periodo}",
                        periodo=periodo,
                        empresa_id=empresa_id,
                    )
                    tot += patronal
                conn.commit()
            return {"ok": True, "lancamentos": n, "total_patronal": round(tot, 2), "empresa_id": empresa_id}
        finally:
            conn.close()

    def lancar_das_parcelamento(self, empresa_id: str = EMPRESA_PRINCIPAL_ID) -> dict:
        """Posta as guias de DAS do Onvio no razão da empresa a que ELAS pertencem.

        Duas naturezas caem sob a MESMA categoria `das_simples_nacional` no Onvio, e
        a diferença é contábil, não cosmética:
          • Simples Nacional (Patrimonial): DAS CORRENTE, imposto sobre a receita do
            mês — D 5.2.2.04 / C 2.1.2.05 (DAS a Recolher);
          • Lucro Real (Eletrônica, ex-Simples): PARCELAMENTO de dívida antiga —
            D 5.2.2.04 / C 2.1.2.04 (Parcelamento Simples a Pagar).

        Medido em 26/09/2026: a consulta não filtrava `empresa_id`, e a guia de agosto
        da Patrimonial (R$ 18.399,33) foi postada no razão da ELETRÔNICA como
        parcelamento — despesa e passivo na empresa errada, nos dois lados.

        `data_lancamento` é o VENCIMENTO da guia, não o 1º dia da competência: o DAS de
        julho vence em 20/08 e só passa a existir em agosto; postar em 01/07 cai no
        período fechado e o lançamento some para sempre (foi o que aconteceu com os
        R$ 17.048,87 de 07/2026). A competência continua em `periodo_competencia`, que
        é por onde o DRE agrupa.

        NUNCA fabrica: só posta guia com valor extraído. Idempotente por
        `DAS-{empresa}-{periodo}` — a ref antiga `DASPARC-{periodo}` não tinha empresa,
        então o mesmo mês só cabia em UM dos dois CNPJs.
        """
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                self._ensure_schema(cur)
                cur.execute("SELECT regime_tributario FROM empresas WHERE id = %s", (empresa_id,))
                linha = cur.fetchone()
                regime = (linha[0] if linha else "") or ""
                corrente = regime == "simples_nacional"
                conta_passivo = "2.1.2.05" if corrente else "2.1.2.04"
                rotulo = "DAS Simples Nacional" if corrente else "Parcelamento Simples"

                cur.execute(
                    "SELECT detalhes_json->>'competencia', detalhes_json->>'valor', "
                    "       detalhes_json->>'vencimento' "
                    "FROM onvio_documents WHERE categoria='das_simples_nacional' "
                    "AND empresa_id = %s "
                    "AND detalhes_json->>'valor' IS NOT NULL "
                    "AND detalhes_json->>'competencia' IS NOT NULL",
                    (empresa_id,),
                )
                n, tot = 0, 0.0
                for comp_mmYYYY, valor, vencimento in cur.fetchall():
                    # "MM/YYYY" -> "YYYY-MM"
                    try:
                        mm, yyyy = comp_mmYYYY.split("/")
                        periodo = f"{yyyy}-{mm}"
                    except (ValueError, AttributeError):
                        continue
                    v = float(valor or 0)
                    data = str(vencimento)[:10] if vencimento else f"{periodo}-01"
                    postou = self._post(
                        cur,
                        data=data,
                        cd="5.2.2.04",
                        cc=conta_passivo,
                        valor=v,
                        hist=f"{rotulo} {periodo} (guia oficial Onvio)",
                        tipo="das_parcelamento",
                        ref=f"DAS-{empresa_id[:8]}-{periodo}",
                        periodo=periodo,
                        empresa_id=empresa_id,
                    )
                    n += postou
                    # Só soma o que ENTROU. Somar a guia recusada pelo corte devolvia
                    # `lancamentos: 0, total_das: 64.490,54` — número que afirma um
                    # trabalho que não aconteceu.
                    tot += v if postou else 0.0
                conn.commit()
            return {
                "ok": True,
                "lancamentos": n,
                "total_das": round(tot, 2),
                "regime": regime,
                "conta_passivo": conta_passivo,
                "empresa_id": empresa_id,
            }
        finally:
            conn.close()

    def fechar(self, empresa_id: str = EMPRESA_PRINCIPAL_ID) -> dict:
        """Fecha o razão: garante schema e posta folha + ISS (idempotente).
        NFS-e receita e banco Inter já são postados pelo accounting_seed_service."""
        self.recusados_periodo_fechado = []
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                self._ensure_schema(cur)
                folha = self._lancar_folha(cur, empresa_id)
                iss = self._lancar_receita_e_iss_nacional(cur, empresa_id)
                tomadas = self._lancar_despesa_tomadas(cur, empresa_id)
                conn.commit()

                # Verificação de equilíbrio (débitos == créditos por construção)
                cur.execute("SELECT sum(valor)::float FROM accounting_entries WHERE status='confirmado'")
                total = cur.fetchone()[0] or 0.0
                cur.execute("SELECT count(*) FROM accounting_entries")
                qtd = cur.fetchone()[0]

            # INSS retido do empregado (verdade Portte hr_payslips) — separa o passivo
            # 2.1.1.03 da folha bruta. Sem esta chamada o razão ficava com ZERO INSS
            # (medido no baseline contábil): o método existia mas nunca era invocado.
            inss_emp = self.lancar_inss_empregado(empresa_id)
            # INSS patronal (guia oficial − retido); fecha o passivo INSS a Recolher com a guia.
            inss_pat = self.lancar_inss_patronal(empresa_id)
            # DAS/parcelamento Simples (CNPJ1) a partir da guia oficial extraída do Onvio.
            das = self.lancar_das_parcelamento(empresa_id)
            # Férias (1/9) e 13º (1/12) sobre a folha real. O método existia e só era
            # chamado por um BOTÃO de tela: foi clicado uma vez, em 26/07/2026, e provisionou
            # janeiro a junho. De julho em diante, nada — e férias e 13º não dependem de
            # clique nem de regime tributário: eles acontecem e serão pagos. Sem esta linha
            # o resultado de cada mês aparecia ~R$ 18.000 melhor do que é, e o passivo
            # crescia invisível. Idempotente por PROVFER-/PROV13-{competência}.
            provis = self.lancar_provisoes_trabalhistas(empresa_id)
            # Recategoriza o banco Inter (conserta receita/despesa fantasma) — mantém o lucro fiel
            recat = self.recategorizar_inter(empresa_id)
            # Transitórias (4.9.9.01 / 5.9.9.01) que já ganharam categoria/justificativa saem
            # pela regra do plano; sem isso a DRE somava recebimento de cliente como receita.
            try:
                from modules.financial.services.extrato_para_razao import reclassificar_transitorias

                recat["transitorias"] = reclassificar_transitorias()
            except Exception as te:  # noqa: BLE001 — não derruba o fechamento
                logger.warning("reclassificação de transitórias falhou (segue): %s", te)
            # Reconstrói folha jan/fev (ausente em hr_payslips) por âncora março + PIX real
            try:
                folha_rec = self.reconstruir_folha_jan_fev(empresa_id)
            except Exception as fe:  # não derruba o fechamento
                logger.warning("Reconstrução folha jan/fev falhou (segue): %s", fe)
                folha_rec = {"ok": False, "erro": str(fe)}
            return {
                "ok": True,
                "novos_lancamentos": {
                    **folha,
                    **iss,
                    **tomadas,
                    "inss_empregado": inss_emp.get("lancamentos", 0),
                    "inss_patronal": inss_pat.get("lancamentos", 0),
                    "das_parcelamento": das.get("lancamentos", 0),
                    "provisao_ferias": provis.get("provisoes_ferias", 0),
                    "provisao_13": provis.get("provisoes_13", 0),
                },
                "recategorizacao_inter": recat,
                "folha_reconstruida_jan_fev": folha_rec.get("meses"),
                # Recusados por período fechado: não é erro, é informação que antes só
                # existia numa linha de log. Nota de competência anterior ao corte que
                # chega hoje nunca entra no razão — e agora isso aparece no resultado.
                "recusados_periodo_fechado": len(self.recusados_periodo_fechado),
                "recusados_valor": round(sum(r["valor"] for r in self.recusados_periodo_fechado), 2),
                "recusados_detalhe": self.recusados_periodo_fechado[:20],
                "total_lancamentos": qtd,
                "movimento_total": round(total, 2),
                "empresa_id": empresa_id,
            }
        finally:
            conn.close()

    def fechar_grupo(self) -> dict:
        """Fecha o razão de TODAS as empresas ativas (multi-CNPJ). Cada empresa é fechada com
        o próprio empresa_id — sem isso, só a Eletrônica (default) era fechada e as notas da
        Patrimonial ficavam sem razão próprio. A falha de uma NÃO derruba a outra."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id, slug FROM empresas WHERE status = 'ativa' ORDER BY slug")
                empresas = [(str(r[0]), r[1]) for r in cur.fetchall()]
        finally:
            conn.close()
        if not empresas:  # fallback: pelo menos a principal
            empresas = [(EMPRESA_PRINCIPAL_ID, "principal")]
        resultados = {}
        for eid, slug in empresas:
            try:
                resultados[slug] = self.fechar(empresa_id=eid)
            except Exception as exc:  # noqa: BLE001 — isolamento entre CNPJs
                logger.error("Fechamento do razão falhou p/ %s: %s", slug, exc)
                resultados[slug] = {"ok": False, "erro": str(exc)}
        # ok só se TODAS fecharam: de 11/08 a 07/09/2026 as duas falharam todo dia e o
        # resultado dizia ok=True — a task ficava SUCCESS e ninguém viu 27 dias sem razão.
        return {"ok": all(r.get("ok") for r in resultados.values()), "empresas": resultados}
