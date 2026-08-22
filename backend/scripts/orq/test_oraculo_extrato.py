"""Oráculo do extrato bancário: sem ele, nada mais no financeiro é verdade.

Contas a pagar, conciliação, DRE e guias todos derivam do extrato. E ele quebrou
em SILÊNCIO três vezes em 11-12/08/2026:

  1. 880 linhas duplicadas (R$563.979,07) — dois imports da mesma conta, e depois
     mais 294 de um par de fontes diferente que a primeira limpeza não pegou;
  2. sinal invertido em 94 registros (R$785 mil) — o sync re-adivinhava a direção
     pela descrição e "RECEBID" não está contido em "RECEBIMENTO" (falta o D),
     então todo recebimento de boleto virava SAÍDA;
  3. a ponte `inter_transactions`→`bank_transactions` deduplicava exigindo
     descrição idêntica; a mesma transação vinda do CSV e da API tem texto
     diferente, e ela recriava a linha TODO DIA.

Nenhuma das três é divergência de SALDO — a regra proativa `caixa_divergente` não
pegaria nenhuma. Por isso este oráculo afirma INVARIANTES da estrutura, não o
saldo.

Roda:
    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_oraculo_extrato.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from core.database import async_session_factory  # noqa: E402
from modules.financial.services.periodo_contabil import (  # noqa: E402
    ABERTURA_NO_CORTE,
    CORTE_CONTABIL,
)

# Estorno de PIX enviado ENTRA como positivo — é devolução, não erro de sinal.
# Sem esta exceção o oráculo acusaria 11 linhas legítimas ("Pix enviado
# devolvido"), e falso positivo mata a confiança mais rápido que defeito não
# achado.
_DEVOLUCAO = "DEVOLVID|ESTORNO|DEVOLUCAO"

# Quanto o saldo do banco pode divergir do nosso extrato na data conferida.
# R$0,01 e não zero: o saldo vem em centavos do banco e a soma é numeric.
TOLERANCIA = 0.01


async def main() -> None:  # noqa: PLR0915
    falhas: list[str] = []
    nao_coberto: list[str] = []

    async with async_session_factory() as db:
        # ── (1) DUPLICATA ────────────────────────────────────────────────────
        # NÃO se testa `external_id` repetido: o índice UNIQUE
        # `idx_bank_tx_external_id` já impede, e afirmar o que o banco garante é
        # decoração — descoberto ao tentar provar este oráculo em vermelho, que é
        # exatamente para isso que se prova em vermelho.
        #
        # As três duplicações reais vieram de linhas SEM external_id: a mesma
        # transação importada por DUAS FONTES (csv_import+inter, depois
        # inter_csv_2026+banking_api, depois a ponte recriando).
        #
        # A assinatura é (conta, data, valor, favorecido) aparecendo em mais de uma
        # fonte. O favorecido é obrigatório na chave: sem ele, 21 pagamentos de
        # R$32,00 do mesmo dia — para pessoas DIFERENTES — viram falso positivo só
        # porque foram importados metade por uma fonte, metade por outra.
        #
        # Mesmo assim é SUSPEITA, não veredito: quem decide é o banco. Em
        # 12/08/2026 os três grupos foram consultados no extrato do Inter — dois
        # eram pagamentos gêmeos legítimos (Sólides 17/06 R$736,00 e Alan 09/08
        # R$32,00, o banco tem 2 de cada) e um era duplicata de verdade (Loide
        # 07/08 R$32,00, o banco tem 1), removida. Daí a linha de base.
        # ── (0) as garantias do BANCO continuam de pé ────────────────────────
        # Duas das três invariantes que este oráculo ia afirmar já são impostas
        # pelo Postgres — descobri ao tentar provar em vermelho e o INSERT ser
        # recusado. Afirmar o que o banco garante é decoração; o que vale é
        # afirmar que a GARANTIA não sumiu. Constraint some em migration
        # distraída, e aí o defeito volta calado.
        for nome_obj, sql in (
            ("idx_bank_tx_external_id (UNIQUE)",
             "SELECT count(*) FROM pg_indexes WHERE tablename='bank_transactions' "
             "AND indexname='idx_bank_tx_external_id' AND indexdef LIKE '%UNIQUE%'"),
            ("ck_bank_tx_sinal_coerente (CHECK)",
             "SELECT count(*) FROM pg_constraint con JOIN pg_class c ON c.oid=con.conrelid "
             "WHERE c.relname='bank_transactions' AND con.conname='ck_bank_tx_sinal_coerente'"),
        ):
            if not int((await db.execute(text(sql))).scalar() or 0):
                falhas.append(f"garantia do banco AUSENTE: {nome_obj} — o defeito volta calado")
            else:
                print(f"OK garantia do banco de pé: {nome_obj}")

        # Adjudicados contra o extrato do Inter em 12/08/2026: Sólides 17/06
        # R$736,00, Alan 09/08 R$32,00 e Loide 07/08 R$32,00 são pagamentos
        # GÊMEOS legítimos — o banco tem dois de cada. Cheguei a apagar o da
        # Loide achando que era duplicata (o filtro por nome na descrição não
        # contou o par) e foi a checagem (3) contra o saldo do próprio banco que
        # denunciou, com a diferença exata de R$32,00. Restaurado.
        # 14/08/2026: subiu para 8. Não apareceu duplicata nova — apareceu NOME. Ao
        # preencher `counterparty_name` de 226 linhas de PIX interno (o nome estava
        # dentro da descrição, no campo errado), pares que já existiam passaram a ser
        # visíveis para esta contagem. Os 5 novos são VT+VR de R$32,00 pagos duas
        # vezes no mesmo dia à mesma pessoa, mais dois R$100,00 do Jordan em 02/02 com
        # external_id distintos (07:15 e 07:20).
        #
        # ⭐ Quem adjudicou não foi o olho: foi a checagem (3). Desde hoje ela cobre os
        # DOIS bancos contra o saldo que eles próprios informam, e fecha exata nos dois
        # (Inter R$5.397,69 · Cora R$51.832,90). Duplicata inflaria o saldo; saldo que
        # fecha é prova mais forte que esta heurística de semelhança.
        # 22/08/2026: subiu para 12. Adjudicados contra o extrato do Inter — e o método
        # importa, porque errei duas vezes antes de acertar. Casar por NOME na descrição
        # do banco deu respostas contraditórias para o MESMO caso (uma vez "banco tem 2",
        # outra "banco tem 0"): a descrição vem como "PAGAMENTO DE TITULO - FULL TELECOM
        # LTDA" e qualquer variação de acento, corte ou maiúscula muda o resultado.
        #
        # ⭐ O que decide é CONTAGEM POR VALOR NO DIA INTEIRO: para cada dia, quantos
        # lançamentos de cada valor o banco tem contra quantos temos. Em 25/06 são 18 e
        # 18 — dois de R$152,23 e dois de R$153,78, os dois contratos da Full Telecom
        # pagos no mesmo dia. Nenhum valor nosso excede o do banco em nenhum dos dias.
        #
        # Cheguei a montar o DELETE das 12 linhas. O que segurou foi conferir com o
        # banco antes — a mesma lição do pagamento da Loide, que eu apaguei achando que
        # era duplicata e o saldo denunciou com a diferença exata de R$32,00.
        BASE_PARES_LEGITIMOS = 12
        susp = (await db.execute(text("""
            SELECT count(*) AS grupos, coalesce(sum(n - 1), 0) AS excedentes
            FROM (SELECT count(*) AS n
                  FROM bank_transactions
                  WHERE coalesce(counterparty_name, '') <> ''
                  GROUP BY bank_account_id, transaction_date, amount,
                           unaccent(upper(counterparty_name))
                  HAVING count(DISTINCT coalesce(imported_from, origin, '?')) > 1) x
        """))).mappings().first()
        grupos = int(susp["grupos"] or 0)
        if grupos > BASE_PARES_LEGITIMOS:
            falhas.append(
                f"{grupos - BASE_PARES_LEGITIMOS} grupo(s) NOVO(S) de possível duplicata "
                f"multi-fonte (mesma conta, data, valor e favorecido em fontes diferentes); "
                f"linha de base adjudicada contra o extrato do banco: {BASE_PARES_LEGITIMOS}")
        else:
            print(f"OK duplicata multi-fonte: {grupos} grupo(s), todos adjudicados "
                  f"contra o extrato do banco")

        # ── linha do Inter SEM external_id não pode voltar a crescer ─────────────
        # 22/08/2026: 645 das 4.450 linhas do Inter (14,5%) estavam sem external_id,
        # enquanto o Cora tinha 0%. Isso DESLIGA a garantia do banco: o índice único é
        # parcial (`WHERE external_id IS NOT NULL`) e nulo nunca colide com nulo — então
        # a mesma transação entrava de novo a cada reimportação. Foi o que fez o saldo do
        # Inter divergir R$1.999,34 do banco, e o que a checagem de duplicata multi-fonte
        # NÃO enxerga (ela exige favorecido preenchido, e essas cópias vêm sem nome).
        #
        # A ponte agora grava `inter_tx_<id da origem>`. Este teste guarda o número: as
        # 645 antigas ficam (apagar linha de extrato exige conferir cada uma no banco),
        # mas nenhuma NOVA pode nascer sem id.
        SEM_ID_HERDADAS = 645
        sem_id = int((await db.execute(text("""
            SELECT count(*) FROM bank_transactions t JOIN bank_accounts a ON a.id = t.bank_account_id
             WHERE a.bank_code = '077' AND t.external_id IS NULL
        """))).scalar() or 0)
        if sem_id > SEM_ID_HERDADAS:
            falhas.append(
                f"{sem_id - SEM_ID_HERDADAS} linha(s) NOVA(S) do Inter sem external_id — "
                f"a ponte voltou a gravar sem identificador e o índice único não protege "
                f"nulo; é assim que a duplicata volta calada (herdadas: {SEM_ID_HERDADAS})")
        else:
            print(f"OK external_id do Inter: {sem_id} sem id, nenhuma nova além das herdadas")

        # Alcance declarado em voz alta: onde o favorecido está vazio, esta prova
        # não alcança. Não é falha — é o limite do teste, e esconder limite de
        # teste é como um oráculo passa a mentir.
        sem_nome = (await db.execute(text(
            "SELECT count(*) FILTER (WHERE coalesce(counterparty_name,'') = ''), count(*) "
            "FROM bank_transactions"))).first()
        print(f"   alcance: {sem_nome[1] - sem_nome[0]}/{sem_nome[1]} linhas têm favorecido "
              f"({100 * (sem_nome[1] - sem_nome[0]) / max(sem_nome[1], 1):.0f}%)")

        # ── (2) SINAL ────────────────────────────────────────────────────────
        # A direção do dinheiro é fato do banco (`tipoOperacao`), não adivinhação
        # sobre o texto. Aqui o texto serve só de DELATOR: se a descrição diz
        # recebimento e o valor é negativo, alguém adivinhou — e errou.
        for rotulo, cond in (
            ("RECEBIMENTO/RECEBIDO com valor negativo",
             f"amount < 0 AND unaccent(upper(coalesce(description,''))) ~ 'RECEBIMENTO|RECEBIDO' "
             f"AND unaccent(upper(coalesce(description,''))) !~ '{_DEVOLUCAO}'"),
            ("ENVIADO/PAGAMENTO com valor positivo",
             f"amount > 0 AND unaccent(upper(coalesce(description,''))) ~ 'PIX ENVIADO|PAGAMENTO DE TITULO|TED ENVIADA' "
             f"AND unaccent(upper(coalesce(description,''))) !~ '{_DEVOLUCAO}'"),
        ):
            r = (await db.execute(text(
                f"SELECT count(*), coalesce(sum(abs(amount)),0) FROM bank_transactions WHERE {cond}"))).first()
            if int(r[0] or 0):
                falhas.append(f"{r[0]} linha(s) com {rotulo} — R$ {float(r[1]):,.2f}")
            else:
                print(f"OK sinal coerente: nenhuma {rotulo}")

        # ── (3) SALDO CONTRA O PRÓPRIO BANCO ─────────────────────────────────
        # Medição contra algo de FORA. Confere numa data JÁ FECHADA (D-2), não
        # hoje: movimento do dia entra no saldo do banco antes de entrar no nosso
        # extrato, e cobrar essa defasagem seria acusar o funcionamento normal.
        conferir = date.today() - timedelta(days=2)
        contas = (await db.execute(text(
            "SELECT id::text, bank_name FROM bank_accounts ORDER BY bank_name"))).fetchall()
        for cid, nome in contas:
            abertura = ABERTURA_NO_CORTE.get(cid)
            if abertura is None:
                nao_coberto.append(f"{nome}: sem saldo de abertura em ABERTURA_NO_CORTE")
                continue
            nosso = float((await db.execute(text(
                "SELECT coalesce(sum(amount), 0) FROM bank_transactions "
                "WHERE bank_account_id::text = :c AND transaction_date >= :ini "
                "  AND transaction_date <= :ate"),
                {"c": cid, "ini": CORTE_CONTABIL, "ate": conferir})).scalar() or 0)
            esperado = round(abertura + nosso, 2)

            saldo_banco = await _saldo_do_banco(nome, conferir)
            if saldo_banco is None and "cora" in (nome or "").lower():
                # O Cora não tem saldo HISTÓRICO (não existe `dataSaldo`), mas tem o de
                # AGORA — e isso confronta igual, só que ancorado em hoje. Ficava como
                # "não coberto" por engano: o endpoint sempre existiu.
                await _confrontar_cora_hoje(db, cid, nome, abertura, falhas, nao_coberto)
                continue
            if saldo_banco is None:
                # Fonte não respondeu, ou não oferece saldo histórico. Não é
                # "passou" nem "falhou": é não medido, e tem que aparecer assim.
                nao_coberto.append(
                    f"{nome}: saldo do banco em {conferir} indisponível — nosso extrato "
                    f"diz R$ {esperado:,.2f}, sem confronto externo")
                continue
            dif = round(esperado - saldo_banco, 2)
            if abs(dif) > TOLERANCIA:
                falhas.append(
                    f"{nome}: em {conferir} nosso extrato diz R$ {esperado:,.2f} e o banco "
                    f"diz R$ {saldo_banco:,.2f} — diferença de R$ {dif:,.2f}")
            else:
                print(f"OK {nome}: R$ {esperado:,.2f} = saldo do próprio banco em {conferir}")

        # ── (4) folha marcada PAGA tem que ter prova bancária ──
        # Isto não existia, e por isso 12 pagamentos (R$14.713,80) ficaram meses sem
        # par sem ninguém notar: "aguardando_app" e "pendente_pagamento" não incomodam
        # tela nenhuma. A prova é o `pix_e2e_id` (endToEndId, nos pagos pelo Inter) ou
        # o `comprovante_id` no formato `bank_tx:<uuid>` (nos fechados pelo extrato).
        # Marcar pago sem prova é a forma silenciosa de a folha "fechar" sem dinheiro.
        sem_prova = (await db.execute(text(
            "SELECT count(*) FROM payroll_payments WHERE status = 'pago' "
            "AND coalesce(pix_e2e_id,'') = '' "
            "AND coalesce(comprovante_id,'') NOT LIKE 'bank_tx:%'"))).scalar() or 0
        if sem_prova:
            falhas.append(
                f"{sem_prova} pagamento(s) de folha marcados 'pago' sem prova bancária "
                f"(nem endToEndId, nem linha do extrato)")
        else:
            total = (await db.execute(text(
                "SELECT count(*) FROM payroll_payments WHERE status = 'pago'"))).scalar()
            print(f"OK folha: os {total} pagamentos marcados pagos têm prova bancária")

        # ── (5) as parcelas de uma competência têm que fechar o líquido ──
        # A folha passou a ser paga em parcelas (40% no dia 20, 60% no dia 5). Cada
        # parcela isolada PARECE certa — só a soma denuncia se alguém ficou faltando
        # receber. Um lote que soma 95% paga a menos e ninguém vê.
        quebras = (await db.execute(text("""
            SELECT e.nome, p.mes, p.ano,
                   round(sum(p.valor_liquido), 2) AS pago,
                   round(max(h.net_salary), 2) AS liquido
            FROM payroll_payments p
            JOIN employees e ON e.id = p.employee_id
            JOIN hr_payslips h ON h.employee_id = p.employee_id
                 AND h.reference_month = p.mes AND h.reference_year = p.ano
                 AND h.payslip_type IN ('mensal','monthly')
            WHERE p.parcelas_total > 1
            GROUP BY e.nome, p.mes, p.ano
            HAVING abs(round(sum(p.valor_liquido), 2) - round(max(h.net_salary), 2)) > 0.05
        """))).mappings().all()
        if quebras:
            for q in quebras[:5]:
                falhas.append(
                    f"parcelas não fecham: {q['nome']} {q['mes']:02d}/{q['ano']} — "
                    f"soma R$ {q['pago']:,.2f} × líquido R$ {q['liquido']:,.2f}")
        else:
            n_par = (await db.execute(text(
                "SELECT count(*) FROM payroll_payments WHERE parcelas_total > 1"))).scalar()
            print(f"OK folha em parcelas: {n_par} linha(s) parcelada(s), "
                  f"soma fecha o líquido em todas")

    for n in nao_coberto:
        print(f"NÃO COBERTO: {n}")
    if falhas:
        for f in falhas:
            print(f"FALHOU: {f}")
        raise AssertionError(f"{len(falhas)} invariante(s) do extrato quebrada(s)")
    print("TEST oraculo_extrato PASS")


async def _confrontar_cora_hoje(db, cid: str, nome: str, abertura: float,
                                falhas: list, nao_coberto: list) -> None:
    """Confronta o Cora pelo saldo de AGORA, distinguindo defasagem de defeito.

    Diferença aqui tem duas causas possíveis, e tratá-las igual seria mentir nas duas
    direções: se o extrato do dia ainda não foi sincronizado (o beat roda 08:10), o
    movimento da tarde está no banco e não está em casa — isso é funcionamento normal.
    Se as linhas de hoje já batem e o saldo ainda diverge, aí falta linha de verdade.

    Por isso, quando diverge, o teste puxa o extrato de hoje AO VIVO (só leitura) e
    refaz a conta. Se o vivo fecha, era defasagem; se não fecha, é defeito.
    """
    from modules.integrations.banking.adapters.cora import CoraAdapter

    try:
        saldo_banco = float((await CoraAdapter().get_balance()).available)
    except Exception as exc:  # noqa: BLE001 — banco fora do ar não é defeito nosso
        nao_coberto.append(f"{nome}: saldo do Cora indisponível ({str(exc)[:60]})")
        return

    hoje = date.today()
    nosso = float((await db.execute(text(
        "SELECT coalesce(sum(amount), 0) FROM bank_transactions "
        "WHERE bank_account_id::text = :c AND transaction_date >= :ini"),
        {"c": cid, "ini": CORTE_CONTABIL})).scalar() or 0)
    dif = round(abertura + nosso - saldo_banco, 2)
    if abs(dif) <= TOLERANCIA:
        print(f"OK {nome}: R$ {abertura + nosso:,.2f} = saldo do próprio banco agora")
        return

    # Diverge. Comparar SOMAS não diz de que lado está a sobra: uma entrada a mais no
    # banco e uma saída a mais em casa mexem a soma no mesmo sentido. Então compara-se
    # LINHA A LINHA. Foi assim que um fantasma de R$1.494,90 (ordem de pagamento
    # gravada como se fosse saída) foi chamado de "defasagem" na primeira versão deste
    # teste, em 14/08/2026 — a conta fechava em módulo e escondia a direção.
    guardado = [round(float(v), 2) for (v,) in (await db.execute(text(
        "SELECT amount FROM bank_transactions "
        "WHERE bank_account_id::text = :c AND transaction_date = :d"),
        {"c": cid, "d": hoje})).fetchall()]
    try:
        extrato = await CoraAdapter().get_statement(hoje, hoje)
        vivo = [round(float(t.amount), 2) for t in extrato.transactions]
    except Exception as exc:  # noqa: BLE001
        nao_coberto.append(
            f"{nome}: diverge R$ {dif:,.2f} e o extrato de hoje não veio ({str(exc)[:50]}) "
            f"— não dá para separar defasagem de defeito")
        return

    from collections import Counter

    so_nosso = Counter(guardado) - Counter(vivo)   # temos e o banco não → fantasma
    so_banco = Counter(vivo) - Counter(guardado)   # banco tem e não chegou → defasagem
    if so_nosso:
        linhas = ", ".join(f"R$ {v:,.2f}" for v in sorted(so_nosso.elements()))
        falhas.append(
            f"{nome}: LINHA FANTASMA — temos hoje {linhas} que o banco não reporta. "
            f"Ordem de pagamento iniciada não é saída: enquanto o banco não debitar, "
            f"não pode estar no extrato nem no razão")
        return
    if so_banco:
        linhas = ", ".join(f"R$ {v:,.2f}" for v in sorted(so_banco.elements()))
        nao_coberto.append(
            f"{nome}: {linhas} de hoje ainda não sincronizado(s) — o beat das 08:10 "
            f"fecha isso")
        return
    falhas.append(
        f"{nome}: nosso extrato diz R$ {abertura + nosso:,.2f} e o banco diz "
        f"R$ {saldo_banco:,.2f} — diferença de R$ {dif:,.2f} que NÃO é o movimento do dia")


async def _saldo_do_banco(nome: str, dia: date) -> float | None:
    """Saldo que o PRÓPRIO banco informa naquele dia, ou None se não dá para saber.

    Só o Inter oferece saldo histórico (`GET /banking/v2/saldo?dataSaldo=`). O
    Cora não tem o parâmetro — por isso ele sai como NÃO COBERTO em vez de
    comparar contra o saldo de hoje, que mediria outra coisa.
    """
    if "inter" not in (nome or "").lower():
        return None
    try:
        from modules.integrations.inter.inter_sync_service import _build_adapter

        ad = _build_adapter()
        try:
            return float((await ad.get_balance(dia)).available)
        finally:
            await ad.close()
    except Exception as exc:  # noqa: BLE001 — fonte fora do ar não é defeito nosso
        print(f"   (saldo do Inter em {dia} indisponível: {str(exc)[:70]})")
        return None


if __name__ == "__main__":
    asyncio.run(main())
