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
from modules.financial.services.periodo_contabil import periodo_fechado
from modules.financial.services.plano_contas_caixa import (
    CONTA_BANCO,
    CONTA_BANCO_POR_CODIGO,
    CONTA_ENTRADA_A_CLASSIFICAR,
    CONTA_SAIDA_A_CLASSIFICAR,
    contrapartida_entrada,
    contrapartida_por_contraparte,
    contrapartida_saida,
)

logger = logging.getLogger(__name__)


def ref_do_extrato(bank_transaction_id: str) -> str:
    """Chave natural do lançamento. É o ID da transação e não valor+data porque
    valor+data se repetem legitimamente (3 saques de R$1.000 no mesmo dia)."""
    return f"EXTRATO-{bank_transaction_id}"


def _conn():
    return psycopg2.connect(_raw_db_url())


_CNPJ_CAIXA = "00360305000104"  # FGTS via Caixa Econômica Federal


def _docs_clt(cur) -> set[str]:
    """CPFs (só dígitos) dos colaboradores CLT — PIX da Cora para um deles é SALÁRIO já
    provisionado pela folha (baixa do passivo 2.1.1.01), não despesa. O Jordan paga salário
    CLT/PJ da Patrimonial pelo app da Cora (a API não faz PIX), então a saída chega sem
    justificativa: 92 linhas, R$ 57.372,94 em agosto/2026, contadas como despesa."""
    cur.execute(
        "SELECT regexp_replace(coalesce(cpf,''), '\\D', '', 'g') AS cpf FROM employees WHERE coalesce(cpf,'') <> ''"
    )
    return {(r["cpf"] if isinstance(r, dict) else r[0]) for r in cur.fetchall()} - {""}


#: Categorias que não dizem nada — são o "não sei" gravado, não um enquadramento.
_CATEGORIA_MUDA = ("pagamento", "pix", "outros", "outro", "payment", "diversos", "transferência", "transferencia", "")


def _cat_saida(cat: str | None, documento: str | None, clt: set[str]) -> str | None:
    """Categoria efetiva de uma saída sem justificativa: contraparte CLT → salário; CNPJ com
    regra própria → a categoria da regra; Caixa → impostos (FGTS).

    A regra por CNPJ entra AQUI, na escrituração, e não reescrevendo
    `bank_transactions.justificativa_categoria`: 18 das transações da Solides foram
    justificadas pelo próprio Jordan como "outro", e sobrescrever campo que uma pessoa
    preencheu apagaria o registro de que ele olhou. A conta do razão é decisão do sistema;
    a justificativa é dele.

    Medido em 25/09/2026: a Solides (CNPJ real 10461302, 93 transações) estava inteira em
    «Saídas a Classificar» porque a regra da tabela apontava para 31680151 — que é código
    de roteamento bancário, não o CNPJ dela.
    """
    atual = (cat or "").strip().lower()
    doc = "".join(ch for ch in (documento or "") if ch.isdigit())

    if atual not in _CATEGORIA_MUDA:
        return cat
    if doc and doc in clt:
        return "salario"
    if doc == _CNPJ_CAIXA:
        return "impostos"
    if len(doc) == 14:
        from modules.financial.services.lucro_real_justificativa_service import CNPJ_RULES

        for cnpj, categoria, _texto in CNPJ_RULES:
            if doc.startswith(cnpj):
                return categoria
    return cat


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
                       b.bank_account_id::text AS conta_id,
                       -- justificativa do Jordan vence; sem ela, a categoria que o banco/
                       -- categorizador já deu. Lendo só a justificativa, 13 recebimentos de
                       -- cliente da Cora (R$ 132.898,35, ago/2026) viraram "entrada a
                       -- classificar" e a DRE somou-os como receita em cima das notas.
                       coalesce(b.justificativa_categoria, b.category) AS cat,
                       b.counterparty_name AS contraparte, b.counterparty_document AS documento,
                       -- empresa vem da CONTA, não da transação: o Inter é da
                       -- Eletrônica e o Cora é da Patrimonial. Sem isso o
                       -- lançamento nasce sem CNPJ e some do balancete escopado.
                       ba.empresa_id::text AS empresa_id,
                       ba.bank_code AS bank_code
                FROM bank_transactions b
                JOIN bank_accounts ba ON ba.id = b.bank_account_id
                WHERE NOT EXISTS (
                    SELECT 1 FROM accounting_entries a WHERE a.bank_transaction_id = b.id
                )
                  -- Ordem de pagamento INICIADA não é movimento. O serviço do Cora
                  -- grava a ordem aqui com status='pendente' assim que o banco a
                  -- aceita, antes de a saída existir — e em 14/08/2026 uma ordem de
                  -- R$1.494,90 que o Jordan nem chegou a ter debitada virou despesa
                  -- no razão. O razão só escritura o que o BANCO já reportou.
                  AND coalesce(b.status, '') <> 'pendente'
                ORDER BY b.transaction_date
                LIMIT %s
                """,
                (limite,),
            )
            linhas = cur.fetchall()
            clt = _docs_clt(cur)
            # Quem é CLIENTE não pode ser tratado como fornecedor quando o dinheiro SAI —
            # pagar um cliente é estorno, devolução ou repasse, e qual dos três só quem
            # fez sabe.
            #
            # MENOS quem é as duas coisas. A HAWK EYE é cliente E fornecedora (o dono
            # disse em 26/09: «eles são fornecedores nossos também»), e o cadastro já
            # sabia — está em `suppliers` com o mesmo CNPJ. Sem este `EXCEPT`, os
            # R$ 2.460,00 pagos a ela ficariam presos na transitória por uma regra que
            # existe para proteger outro caso.
            cur.execute(
                "SELECT regexp_replace(coalesce(c.document_number,''), '[^0-9]', '', 'g') AS doc"
                "  FROM clients c WHERE coalesce(c.document_number,'') <> ''"
                " EXCEPT"
                " SELECT regexp_replace(coalesce(s.cpf_cnpj,''), '[^0-9]', '', 'g')"
                "  FROM suppliers s WHERE coalesce(s.cpf_cnpj,'') <> ''"
            )
            docs_cliente = {x["doc"] if isinstance(x, dict) else x[0] for x in cur.fetchall()}
            docs_cliente.discard("")

            # Pagar uma nota que JÁ foi escriturada por competência não é despesa nova: é
            # liquidar o fornecedor. Sem isto o mesmo gasto entrava duas vezes no DRE — a
            # NFS-e tomada (`despesa_tomada`, D 5.2.1.04) e o PIX que a pagou (`extrato_
            # bancario`, D 5.2.1.04 de novo). Medido em 26/09/2026: 41 pagamentos,
            # R$ 87.915,90 nas duas empresas, com a Solides aparecendo em dobro sete vezes
            # no mesmo dia. O Inter já tinha esse conserto em `recategorizar_inter`; o Cora
            # da Patrimonial nasceu depois e ficou de fora.
            #
            # O casamento é por CNPJ DO PRESTADOR + valor, não por valor + data: valor
            # redondo se repete entre fornecedores diferentes, CNPJ não.
            cur.execute(
                "SELECT empresa_id::text AS empresa_id,"
                "       regexp_replace(coalesce(prestador_cnpj,''), '[^0-9]', '', 'g') AS doc,"
                "       round(valor_servicos::numeric, 2) AS v"
                "  FROM nfse_tomadas_nacional"
                " WHERE coalesce(valor_servicos, 0) > 0"
            )
            notas_tomadas = {
                (x["empresa_id"], x["doc"], float(x["v"])) for x in cur.fetchall() if len(x["doc"] or "") == 14
            }

            for r in linhas:
                dia = r["dia"]
                if dia is None:
                    pulados["sem_data"] += 1
                    continue
                if (dia.year, dia.month) > (hoje.year, hoje.month):
                    pulados["competencia_futura"] += 1
                    continue
                if periodo_fechado(dia, r["empresa_id"]):
                    # Movimentação anterior ao corte não entra mais. Aparece em
                    # `pulados` de propósito: barrar em silêncio é o mesmo defeito
                    # de "fechar julho" virando "ignorar julho".
                    pulados["periodo_fechado"] += 1
                    continue
                conta_banco = CONTA_BANCO.get(r["conta_id"] or "") or CONTA_BANCO_POR_CODIGO.get(r["bank_code"] or "")
                if not conta_banco:
                    pulados["conta_bancaria_desconhecida"] += 1
                    continue
                v = float(r["amount"] or 0)
                if v == 0:
                    pulados["valor_zero"] += 1
                    continue

                if v < 0:
                    outra, motivo = contrapartida_saida(
                        _cat_saida(r["cat"], r["documento"], clt),
                        f"{r['description'] or ''} {r['contraparte'] or ''}",
                        r["documento"],
                    )
                    chave_nota = (r["empresa_id"], _so_digitos(r["documento"]), round(abs(v), 2))
                    if chave_nota in notas_tomadas:
                        outra = "2.1.4.01"
                        motivo = "liquidação de NFS-e tomada já escriturada (não é despesa nova)"
                    cd, cc = outra, conta_banco
                else:
                    outra, motivo = contrapartida_entrada(
                        f"{r['description'] or ''} {r['contraparte'] or ''}", r["documento"], r["cat"]
                    )
                    cd, cc = conta_banco, outra

                lancados += 1
                valor += abs(v)
                por_conta[outra] = round(por_conta[outra] + abs(v), 2)
                if preview:
                    continue

                hist = f"Extrato {dia:%d/%m/%Y}: {(r['description'] or '').replace(chr(10), ' ')[:120]} — {motivo}"
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
                    (
                        dia,
                        cd,
                        cc,
                        abs(v),
                        hist[:250],
                        ref_do_extrato(r["id"]),
                        f"{dia:%Y-%m}",
                        r["empresa_id"],
                        r["id"],
                        ref_do_extrato(r["id"]),
                    ),
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


def _so_digitos(v: str | None) -> str:
    return "".join(c for c in (v or "") if c.isdigit())


def reclassificar_transitorias(preview: bool = False) -> dict:
    """Tira da transitória o que já tem regra: recomputa a contrapartida de cada lançamento
    em 4.9.9.01 / 5.9.9.01 (desde o corte) com a categoria ATUAL da transação bancária.

    O extrato entra no razão no dia; a justificativa do Jordan e a categoria do banco chegam
    depois — e o lançamento ficava na transitória para sempre (24 VT/VR de diaristas com
    justificativa `diaristas_vtvr` ainda em 5.9.9.01, medido 07/09/2026). Só reclassifica
    para conta NÃO transitória; nunca inventa: sem regra, fica onde está.

    ALCANÇA O PERÍODO FECHADO, e de propósito. Até 25/09/2026 havia um `data_lancamento >=
    CORTE_CONTABIL` aqui, e ele deixava 637 lançamentos (R$ 308.149,66) presos na
    transitória para sempre. O corte existe contra lançamento NOVO em mês encerrado — e o
    próprio gatilho do banco diz isso com todas as letras: `fn_bloqueia_periodo_fechado` é
    BEFORE **INSERT**, com a dica *"Corrigir lancamento existente (UPDATE) e permitido."*
    Reclassificar não cria lançamento; corrige a conta de um que já está lá.

    E não é cosmético. Medido antes da correção: R$ 64.739,46 de PAGAMENTO de salário
    estavam em 5.9.9.01 como despesa, em cima da provisão que a folha já havia lançado em
    5.1.1.01 — a mesma despesa contada DUAS vezes. Mais R$ 18.333,39 de pagamento a
    fornecedor e R$ 16.230,00 de transferência entre as empresas do grupo, na mesma
    situação.

    Competência já encerrada que voltar a ter resultado em aberto é fechada pela varredura
    de resíduo da task `financial.apurar_competencia`.
    """
    conn = _conn()
    n_ent = n_sai = 0
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT a.id, a.conta_debito, a.conta_credito, a.valor, b.amount, b.description,
                       b.counterparty_name AS contraparte, b.counterparty_document AS documento,
                       coalesce(b.justificativa_categoria, b.category) AS cat
                FROM accounting_entries a JOIN bank_transactions b ON b.id = a.bank_transaction_id
                WHERE a.conta_credito = %s OR a.conta_debito = %s
                """,
                (CONTA_ENTRADA_A_CLASSIFICAR, CONTA_SAIDA_A_CLASSIFICAR),
            )
            linhas = cur.fetchall()
            clt = _docs_clt(cur)
            # Quem é CLIENTE não pode ser tratado como fornecedor quando o dinheiro SAI —
            # pagar um cliente é estorno, devolução ou repasse, e qual dos três só quem
            # fez sabe.
            #
            # MENOS quem é as duas coisas. A HAWK EYE é cliente E fornecedora (o dono
            # disse em 26/09: «eles são fornecedores nossos também»), e o cadastro já
            # sabia — está em `suppliers` com o mesmo CNPJ. Sem este `EXCEPT`, os
            # R$ 2.460,00 pagos a ela ficariam presos na transitória por uma regra que
            # existe para proteger outro caso.
            cur.execute(
                "SELECT regexp_replace(coalesce(c.document_number,''), '[^0-9]', '', 'g') AS doc"
                "  FROM clients c WHERE coalesce(c.document_number,'') <> ''"
                " EXCEPT"
                " SELECT regexp_replace(coalesce(s.cpf_cnpj,''), '[^0-9]', '', 'g')"
                "  FROM suppliers s WHERE coalesce(s.cpf_cnpj,'') <> ''"
            )
            docs_cliente = {x["doc"] if isinstance(x, dict) else x[0] for x in cur.fetchall()}
            docs_cliente.discard("")
            for r in linhas:
                if r["conta_credito"] == CONTA_ENTRADA_A_CLASSIFICAR and float(r["amount"] or 0) > 0:
                    conta, motivo = contrapartida_entrada(
                        f"{r['description'] or ''} {r['contraparte'] or ''}", r["documento"], r["cat"]
                    )
                    if conta == CONTA_ENTRADA_A_CLASSIFICAR:
                        continue
                    n_ent += 1
                    if not preview:
                        cur.execute(
                            "UPDATE accounting_entries SET conta_credito=%s, "
                            "historico = left(historico || ' — reclassificado: ' || %s, 250) WHERE id=%s",
                            (conta, motivo, r["id"]),
                        )
                elif r["conta_debito"] == CONTA_SAIDA_A_CLASSIFICAR and float(r["amount"] or 0) < 0:
                    conta, motivo = contrapartida_saida(
                        _cat_saida(r["cat"], r["documento"], clt),
                        f"{r['description'] or ''} {r['contraparte'] or ''}",
                        r["documento"],
                    )
                    if conta == CONTA_SAIDA_A_CLASSIFICAR:
                        # A categoria não resolveu — é o «outros» que ficava aqui para
                        # sempre. Desde 26/09/2026 há uma segunda pergunta a fazer, e ela
                        # não é palpite: QUEM RECEBEU. A conciliação passou a extrair o
                        # favorecido da descrição e 545 transações ganharam nome; quem
                        # recebeu o dinheiro é fato do banco. Continua podendo devolver
                        # None, e aí o lançamento fica onde está.
                        achado = contrapartida_por_contraparte(
                            r["contraparte"] or "",
                            r["documento"],
                            r["description"],
                            e_cliente=_so_digitos(r["documento"]) in docs_cliente,
                        )
                        if not achado:
                            continue
                        conta, motivo = achado
                    n_sai += 1
                    if not preview:
                        cur.execute(
                            "UPDATE accounting_entries SET conta_debito=%s, "
                            "historico = left(historico || ' — reclassificado: ' || %s, 250) WHERE id=%s",
                            (conta, motivo, r["id"]),
                        )
            if not preview:
                conn.commit()
    finally:
        conn.close()
    return {"entradas_reclassificadas": n_ent, "saidas_reclassificadas": n_sai, "preview": preview}
