"""C2 — o DRE não pode subtrair do total o que não mostra em linha.

Nasceu em 25/09/2026, do loop de contabilidade, quando a recontagem do razão bateu ao
centavo com o DRE (−R$ 435.016,91 em 2026) e MESMO ASSIM o demonstrativo mentia: as linhas
visíveis somavam +R$ 89.571,41. A diferença de R$ 524.588,32 era a conta transitória
«5.9.9.01 Saídas a Classificar» — subtraída do EBITDA, sem nenhuma linha no demonstrativo.
Quem lia a tela via um lucro de R$ 89 mil virar prejuízo de R$ 435 mil sem explicação.

Somavam-se a isso: R$ 280.464,67 de custo (VR, férias/13º, diaristas, reembolsos, EPI) fora
dos itens do próprio grupo, «Resultado Financeiro: 0,00» gravado fixo enquanto 5.2.3.01
tinha R$ 10.415,30, e rótulos citando «razão 4.1.1 / 4.1.2» — códigos de um plano de contas
aposentado em 13/08/2026.

O QUE ELE AFIRMA

 (a) **Resto zero.** Toda conta de resultado com movimento no período está dentro de algum
     grupo. Nada é subtraído do total sem linha. Medido pelo campo `conferencia.resto`, que
     é a diferença entre a soma dos grupos e o lucro antes do IR.

 (b) **Cada grupo é a soma dos seus itens.** Grupo com itens cujo total não bate com o valor
     do grupo é exatamente o defeito de Custos dos Serviços: o número certo por cima de uma
     lista incompleta, que é pior que um número errado — parece conferível.

 (c) **A natureza vem do plano, não do prefixo.** Nenhuma conta dentro de Receita Bruta pode
     ter `account_type` diferente de REVENUE. Oito contas ativas contradizem o prefixo —
     4.1.2 FGTS, 4.1.3 INSS Patronal, 4.2.1 Software, 4.2.2 Infraestrutura são EXPENSE com
     código de receita. Classificar por prefixo faria o MESMO lançamento sair como receita
     no DRE e despesa no Balanço.

 (d) **O total não se mexeu.** O lucro antes do IR do demonstrativo tem de bater com a
     recontagem independente, feita aqui por `account_type` direto no razão. Esta é a trava
     contra "consertar a linha estragando o total".

 (e) **Resultado Financeiro não é constante.** Se 5.2.3.x tem movimento, a linha de
     resultado financeiro não pode sair 0,00 — era literal `"valor": 0.0` no código.

VERMELHO ANTES: com o `_dre_simplificado` de até 25/09/2026, (a) acusava resto de
R$ 524.588,32, (b) acusava Custos dos Serviços com itens R$ 280.464,67 menores que o grupo,
e (e) acusava Resultado Financeiro 0,00 contra R$ 10.415,30 no razão.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date

#: Contas de resultado por natureza declarada no plano — a régua independente de (d).
_NATUREZA_RESULTADO = ("REVENUE", "EXPENSE", "COST")


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory
    from modules.financial.controllers.relatorios_controller import _dre_simplificado

    ano = date.today().year
    falhas: list[str] = []
    medidas: list[str] = []

    async with async_session_factory() as db:
        dre = await _dre_simplificado(ano, 1, 12, db)
        grupos = dre.get("grupos") or []
        conf = dre.get("conferencia") or {}

        if not grupos:
            falhas.append("o DRE voltou sem grupos — não há o que conferir; isto não é um verde")
            print(" · ".join(medidas) or "(sem medidas)")
            for f in falhas:
                print("FALHOU:", f)
            raise AssertionError("DRE vazio")

        # (a) resto zero
        resto = float(conf.get("resto", 999999))
        if abs(resto) > 0.02:
            falhas.append(
                f"(a) R$ {resto:,.2f} entram no total sem linha no demonstrativo "
                "— há conta de resultado fora dos grupos"
            )
        medidas.append(f"resto: R$ {resto:,.2f}")

        # (b) cada grupo é a soma dos seus itens
        for g in grupos:
            itens = g.get("itens")
            if not itens:
                continue
            soma = round(sum(float(i.get("valor") or 0) for i in itens), 2)
            valor = round(float(g.get("valor") or 0), 2)
            if abs(soma - valor) > 0.02:
                falhas.append(
                    f"(b) grupo «{g.get('nome')}» vale R$ {valor:,.2f} mas seus itens somam "
                    f"R$ {soma:,.2f} — faltam R$ {valor - soma:,.2f} em linha"
                )
        com_itens = sum(1 for g in grupos if g.get("itens"))
        medidas.append(f"grupos com itens conferidos: {com_itens}/{len(grupos)}")

        # (c) natureza vem do plano
        tipos = {
            r[0]: (r[1] or "").upper()
            for r in (
                await db.execute(text("SELECT code, account_type FROM fin_accounting_accounts"))
            ).fetchall()
        }
        receita = next((g for g in grupos if g.get("grupo") == "receita_bruta"), None)
        intrusas = []
        for it in (receita or {}).get("itens", []):
            code = str(it.get("nome", "")).split(" ")[0]
            if code in tipos and tipos[code] != "REVENUE":
                intrusas.append(f"{code}={tipos[code]}")
        if intrusas:
            falhas.append(f"(c) conta sem natureza de receita dentro da Receita Bruta: {intrusas}")
        contraditorias = sum(
            1
            for c, t in tipos.items()
            if (c.startswith("4") and t != "REVENUE") or (c.startswith("5") and t not in ("EXPENSE", "COST"))
        )
        medidas.append(f"contas cujo prefixo contradiz o account_type: {contraditorias}")

        # (d) o total não se mexeu — recontagem independente por account_type
        recontado = (
            await db.execute(
                text(
                    """
                    WITH mov AS (
                        SELECT conta_debito AS conta, valor AS v FROM accounting_entries
                         WHERE status = 'confirmado' AND coalesce(tipo_lancamento,'') <> 'apuracao'
                           AND periodo_competencia BETWEEN :ci AND :cf
                        UNION ALL
                        SELECT conta_credito, -valor FROM accounting_entries
                         WHERE status = 'confirmado' AND coalesce(tipo_lancamento,'') <> 'apuracao'
                           AND periodo_competencia BETWEEN :ci AND :cf
                    )
                    SELECT round(-sum(mov.v), 2)
                      FROM mov JOIN fin_accounting_accounts a ON a.code = mov.conta
                     WHERE upper(a.account_type) IN ('REVENUE', 'EXPENSE', 'COST')
                    """
                ),
                {"ci": f"{ano:04d}-01", "cf": f"{ano:04d}-12"},
            )
        ).scalar()
        recontado = round(float(recontado or 0), 2)
        lair = round(float(conf.get("lucro_antes_do_ir", 0)), 2)
        if abs(recontado - lair) > 0.02:
            falhas.append(
                f"(d) o demonstrativo diz R$ {lair:,.2f} antes do IR, a recontagem do razão por "
                f"account_type diz R$ {recontado:,.2f} — diferença R$ {recontado - lair:,.2f}"
            )
        medidas.append(f"lucro antes do IR: demonstrativo R$ {lair:,.2f} · razão R$ {recontado:,.2f}")

        # (e) resultado financeiro não é constante
        fin_razao = (
            await db.execute(
                text(
                    """
                    WITH mov AS (
                        SELECT conta_debito AS conta, valor AS v FROM accounting_entries
                         WHERE status = 'confirmado' AND coalesce(tipo_lancamento,'') <> 'apuracao'
                           AND periodo_competencia BETWEEN :ci AND :cf
                        UNION ALL
                        SELECT conta_credito, -valor FROM accounting_entries
                         WHERE status = 'confirmado' AND coalesce(tipo_lancamento,'') <> 'apuracao'
                           AND periodo_competencia BETWEEN :ci AND :cf
                    )
                    SELECT round(sum(v), 2) FROM mov WHERE conta LIKE '5.2.3%'
                    """
                ),
                {"ci": f"{ano:04d}-01", "cf": f"{ano:04d}-12"},
            )
        ).scalar()
        fin_razao = round(float(fin_razao or 0), 2)
        linha_fin = next((g for g in grupos if g.get("grupo") == "despesas_financeiras"), None)
        exibido = round(float((linha_fin or {}).get("valor") or 0), 2)
        if abs(fin_razao) > 0.02 and abs(exibido) < 0.02:
            falhas.append(
                f"(e) razão tem R$ {fin_razao:,.2f} em juros/encargos (5.2.3.x) e a linha de "
                "Resultado Financeiro saiu 0,00"
            )
        medidas.append(f"resultado financeiro: razão R$ {-fin_razao:,.2f} · exibido R$ {exibido:,.2f}")

    print(" · ".join(medidas))
    for f in falhas:
        print("FALHOU:", f)
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) no DRE")
    print(
        "OK DRE: resto zero, todo grupo é a soma dos seus itens, a natureza vem do plano de "
        "contas, o total bate com a recontagem do razão e o resultado financeiro é real"
    )
    print(f"TOTAL desvios C2: {len(falhas)}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        print("TOTAL desvios C2: >0")
        sys.exit(1)
