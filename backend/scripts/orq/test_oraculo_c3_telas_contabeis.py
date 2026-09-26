"""C3 — balancete, balanço e índices contam a MESMA população do razão.

Nasceu em 25/09/2026, do loop de contabilidade. Os três relatórios liam a mesma tabela e
discordavam entre si porque cada um recortava de um jeito, sem que nada na tela dissesse:

 · DRE      — filtrava por `periodo_competencia` e excluía `tipo_lancamento='apuracao'`
 · Balancete— filtrava por `EXTRACT(YEAR FROM data_lancamento)` e não excluía nada
 · Balanço  — não filtrava período nem tipo

Efeitos medidos em produção antes da correção:

 · Balancete de agosto/2026 = R$ 6.775.023,46 contra R$ 2.271.067,60 da competência.
   As 168 apurações, de competências 2022-12 a 2026-08, foram TODAS lançadas com data de
   agosto. O balancete do mês estava três vezes inflado.
 · Painel de Patrimônio Líquido exibia «Receitas do período R$ 59.998,33» quando o razão
   tinha R$ 2.183.235,44 — trinta e seis vezes menor. A apuração (D 4.1.1.01 / C 3.3.1.01)
   zerava as contas de receita, e o painel somava o resíduo.
 · «Prova de caixa: bate ✓, divergência R$ 0,00» — comparando o razão 1.1.1.x com a soma de
   `bank_transactions`, que é a tabela DE ONDE o razão foi escriturado. Bate por construção.
   Ao lado, o razão dizia saldo NEGATIVO de R$ 4.258,33 numa conta bancária.
 · «Liquidez corrente −0,29 · posição apertada» — índice calculado sobre ativo negativo.

O QUE ELE AFIRMA

 (a) **O balancete fecha em qualquer recorte.** Σ débitos = Σ créditos, no ano e em cada mês.
     Partida dobrada que não fecha num recorte é recorte que partiu lançamento ao meio.

 (b) **O balancete conta por competência, como o DRE.** O total de um mês tem de bater com a
     soma do razão daquela COMPETÊNCIA, não da data de digitação.

 (c) **O balanço exclui apuração.** A receita que o painel de PL exibe tem de bater com a
     recontagem do razão sem apuração. Esta é a trava do «36 vezes menor».

 (d) **A identidade patrimonial fecha:** Ativo = Passivo + PL.

 (e) **A prova de caixa não pode ser tautológica.** Ela compara o razão com o saldo que os
     BANCOS informam — fonte independente. Comparar com `bank_transactions` é amarração, e
     tem nome separado. Se as duas comparações forem a mesma coisa, o defeito voltou.

 (f) **Índice não se publica sobre base negativa.** Ativo circulante ≤ 0 e a liquidez sai
     `None`, com a razão escrita — não um número de duas casas que descreve outra empresa.

VERMELHO ANTES: com o código de até 25/09/2026, (b) acusava agosto R$ 4.503.955,86 a mais,
(c) acusava receita R$ 2.123.237,11 menor que o razão, (e) acusava a prova de caixa batendo
contra a própria fonte e (f) acusava liquidez publicada sobre ativo negativo.
"""

from __future__ import annotations

import asyncio
import sys


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory
    from modules.financial.controllers.relatorios_controller import balancete_real
    from modules.operacional.controllers.redesign_builders._fin_contabil import build_contabil

    ano = 2026
    falhas: list[str] = []
    medidas: list[str] = []

    async with async_session_factory() as db:
        # (a) fecha em qualquer recorte
        nao_fecham = []
        for mes in [None, *range(1, 13)]:
            b = await balancete_real(ano=ano, mes=mes, db=db, _user={})
            if b["linhas"] and not b["fecha"]:
                nao_fecham.append(f"{mes or 'ano'}: R$ {b['diferenca']:,.2f}")
        if nao_fecham:
            falhas.append(f"(a) balancete não fecha em {len(nao_fecham)} recorte(s): {nao_fecham[:3]}")
        medidas.append(f"recortes conferidos: 13")

        # (b) a base é a competência
        mes_teste = 8
        bal = await balancete_real(ano=ano, mes=mes_teste, db=db, _user={})
        por_comp = float(
            (
                await db.execute(
                    text("SELECT coalesce(sum(valor),0) FROM accounting_entries WHERE periodo_competencia = :c"),
                    {"c": f"{ano:04d}-{mes_teste:02d}"},
                )
            ).scalar()
            or 0
        )
        if abs(bal["total_debito"] - por_comp) > 0.02:
            por_data = float(
                (
                    await db.execute(
                        text(
                            "SELECT coalesce(sum(valor),0) FROM accounting_entries "
                            "WHERE to_char(data_lancamento,'YYYY-MM') = :c"
                        ),
                        {"c": f"{ano:04d}-{mes_teste:02d}"},
                    )
                ).scalar()
                or 0
            )
            falhas.append(
                f"(b) balancete de {mes_teste:02d}/{ano} soma R$ {bal['total_debito']:,.2f}; a "
                f"competência tem R$ {por_comp:,.2f} e a DATA de lançamento tem R$ {por_data:,.2f} "
                "— a base do período não é a competência"
            )
        medidas.append(f"balancete {mes_teste:02d}/{ano}: R$ {bal['total_debito']:,.2f}")

        # (e) a prova de caixa mede contra fonte independente
        amarr = bal.get("amarracao_extrato") or {}
        prova = bal.get("prova_de_caixa") or {}
        if "saldo_informado_pelos_bancos" not in prova:
            falhas.append(
                "(e) a prova de caixa não compara com o saldo informado pelos bancos "
                "— está medindo o razão contra a própria fonte"
            )
        elif amarr.get("extrato_liquido") == prova.get("saldo_informado_pelos_bancos"):
            falhas.append("(e) amarração e prova de caixa usam a MESMA fonte — uma das duas é redundante")
        medidas.append(
            f"caixa: razão R$ {prova.get('saldo_contabil_1_1_1', 0):,.2f} · "
            f"bancos R$ {prova.get('saldo_informado_pelos_bancos', 0):,.2f}"
        )

        # (c) e (d) — balanço
        out: dict = {}
        await build_contabil(db, out)
        bp = out.get("balanco-patrimonial")
        if not bp:
            falhas.append("(c/d) o balanço não foi montado — o except do builder engoliu a falha")
        else:
            painel = next((p for p in bp["panels"] if p["title"] == "Patrimônio Líquido"), None)
            rotulo = (painel or {}).get("rows", [{}])[0].get("right", "")
            exibida = float(
                str(rotulo).replace("R$", "").replace(".", "").replace(",", ".").strip() or 0
            )
            razao = float(
                (
                    await db.execute(
                        text(
                            """
                            WITH mov AS (
                                SELECT conta_credito AS conta, valor AS v FROM accounting_entries
                                 WHERE coalesce(tipo_lancamento,'') <> 'apuracao'
                                UNION ALL
                                SELECT conta_debito, -valor FROM accounting_entries
                                 WHERE coalesce(tipo_lancamento,'') <> 'apuracao'
                            )
                            SELECT round(sum(mov.v), 2) FROM mov
                              JOIN fin_accounting_accounts a ON a.code = mov.conta
                             WHERE upper(a.account_type) = 'REVENUE'
                            """
                        )
                    )
                ).scalar()
                or 0
            )
            if abs(exibida - razao) > 1.0:
                falhas.append(
                    f"(c) o painel de PL exibe receita R$ {exibida:,.2f} e o razão sem apuração tem "
                    f"R$ {razao:,.2f} — diferença R$ {razao - exibida:,.2f}"
                )
            medidas.append(f"receita no painel de PL: R$ {exibida:,.2f} · razão R$ {razao:,.2f}")

            if "Fecha" not in str(bp["kpis"][3]["v"]):
                falhas.append(f"(d) a identidade patrimonial não fecha: {bp['kpis'][3]['v']}")

        # (f) índice não se publica sobre base negativa
        liq = out.get("indices-liquidez")
        if liq:
            ac_neg = "AC R$ -" in liq["sub"]
            publicou = liq["kpis"][0]["v"] != "—"
            if ac_neg and publicou:
                falhas.append(
                    f"(f) liquidez corrente publicada como {liq['kpis'][0]['v']} sobre ativo "
                    "circulante negativo — índice sem significado"
                )
            medidas.append(f"liquidez corrente: {liq['kpis'][0]['v']}")

    print(" · ".join(medidas))
    for f in falhas:
        print("FALHOU:", f)
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) nas telas contábeis")
    print(
        "OK telas contábeis: balancete fecha em todo recorte e conta por competência, o balanço "
        "exclui apuração e fecha, a prova de caixa mede contra os bancos e índice sobre base "
        "negativa não é publicado"
    )
    print(f"TOTAL desvios C3: {len(falhas)}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        print("TOTAL desvios C3: >0")
        sys.exit(1)
