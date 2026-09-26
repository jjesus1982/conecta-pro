#!/usr/bin/env python3
"""O que falta para o balanço de abertura ficar de pé — e o que dele é INVENTADO.

## Por que esta trava existe

Os livros deste sistema começam em 01/01/2026. O que a empresa tinha e devia em
31/12/2025 está com a contabilidade anterior, e em 26/09/2026 o dono decidiu **não pedir
mais nada a ela**: *«nós vamos fazer nossa própria contabilidade, por isso temos que
assumir esses problemas e resolver»*.

Resolver, aqui, não é inventar um saldo de abertura. É **levantar** o que se sabe, medir
o que falta e não deixar o que falta virar número. Um balanço de abertura fabricado fecha
a equação e mente em todas as linhas — e é indetectável depois, porque tudo bate.

## Como um razão que começa do zero DENUNCIA o que veio antes

Conta de ATIVO com saldo credor, ou de PASSIVO com saldo devedor, é impossível num razão
íntegro. Num razão que começa do zero, é pista: quem paga em 2026 uma dívida criada em
2025 deixa débito sem o crédito que o originou.

**Pista não é prova, e esta trava não conclui.** Medido em 26/09/2026, das sete contas
invertidas, NENHUMA era saldo de abertura puro:

    2.1.5.01 Sócios         conta corrente de DUAS mãos — saldo devedor é legítimo
                            (o sócio retirou mais do que pôs), não é inversão
    2.1.6.01 Empréstimos    dez débitos, ZERO créditos: ou a dívida é anterior aos
                            livros, ou são empréstimos CONCEDIDOS na conta errada
                            («Emprestimo Bruno», «Emprestimo Jean») — e aí é ativo
    2.1.1.02 FGTS           paga ~R$ 14 mil/mês e provisiona ~R$ 7 mil: o problema é a
                            provisão sub-registrada, não a abertura
    2.1.2.09 Tributos       só recebe débito, nunca crédito — é acumulador de tributo
                            não identificado, não passivo de abertura
    1.1.2.01 Clientes       −R$ 187 mil na Eletrônica e +R$ 165 mil na Patrimonial: é o
                            dinheiro dos condomínios que entrou no Inter para notas
                            emitidas pela Patrimonial, não abertura

Quem parasse na primeira leitura lançaria uma abertura de seis dígitos em cima de cinco
explicações erradas.

## O que JÁ se sabe, sem pedir nada a ninguém

O saldo bancário de 31/12/2025 é aritmética, não arquivo de terceiro:

    saldo(31/12/2025) = saldo no corte − movimento de 01/01 até o corte

E o capital social SUBSCRITO é fato público, lido da Receita pela BrasilAPI
(`relatorios_controller._capital_social_subscrito`): Eletrônica R$ 500.000 e Patrimonial
R$ 100.000. Subscrito **não** é integralizado — só o contrato social diz quanto entrou.

## O que só o dono sabe, e é curto

 1. quanto do capital social foi INTEGRALIZADO, e em quê;
 2. o que a empresa possuía de equipamento em 31/12/2025 — `equipments` tem ZERO linhas,
    e o razão traz R$ 1.725,00 de imobilizado comprado em 2026;
 3. quais dos dez débitos em `2.1.6.01` são dívida anterior e quais são empréstimo
    concedido a funcionário;
 4. quanto os clientes deviam em 31/12/2025.

Linha canônica: `TOTAL: <n> lacuna(s) no balanço de abertura`.
"""

from __future__ import annotations

import asyncio
import sys

#: Contas cuja natureza NÃO se julga por sinal, com o motivo.
#: Conta corrente de sócio é de duas mãos; conta de apuração passa por zero.
SEM_JULGAMENTO_DE_SINAL = {
    "2.1.5.01": "conta corrente do sócio é de duas mãos — devedor significa que ele retirou mais",
    "3.3.1.01": "conta de passagem da apuração — nasce e morre no mesmo fechamento",
    "3.2.1.01": "lucros/prejuízos acumulados: prejuízo DEBITA o PL, e isso é o certo",
    "3.9.9.01": "é exatamente a medida do que não foi levantado — ver abaixo",
}


async def main() -> int:
    try:
        from sqlalchemy import text  # noqa: PLC0415

        from core.database import async_session_factory  # noqa: PLC0415
        from modules.financial.services.periodo_contabil import (  # noqa: PLC0415
            ABERTURA_NO_CORTE,
            CORTE_CONTABIL,
        )
    except ModuleNotFoundError:
        print("RECUSO: roda DENTRO do container (precisa do banco)")
        return 2

    lacunas: list[str] = []

    async with async_session_factory() as db:
        # ── 1. o que o razão declara como NÃO LEVANTADO ──────────────────────────────
        nao_levantado = (await db.execute(text("""
            SELECT round(sum(CASE WHEN conta_debito = '3.9.9.01' THEN valor ELSE -valor END), 2)
              FROM accounting_entries
             WHERE '3.9.9.01' IN (conta_debito, conta_credito) AND status = 'confirmado'
        """))).scalar() or 0
        print(f"3.9.9.01 «Saldo de Abertura a Identificar»: R$ {float(nao_levantado):,.2f}")
        print("   — é o contrapeso do capital social declarado, e mede o que o razão NÃO"
              " sabe que a empresa tinha.")
        if abs(float(nao_levantado)) > 0.005:
            lacunas.append(
                f"saldo de abertura não levantado: R$ {float(nao_levantado):,.2f} em 3.9.9.01"
            )

        # ── 2. o banco em 31/12/2025, que é derivável ────────────────────────────────
        print("\nsaldo bancário em 31/12/2025 (derivado: saldo no corte − movimento até o corte):")
        for cid, saldo_corte in ABERTURA_NO_CORTE.items():
            linha = (await db.execute(text("""
                SELECT coalesce(ba.bank_name, ba.name),
                       round(coalesce(sum(t.amount), 0), 2)
                  FROM bank_accounts ba
                  LEFT JOIN bank_transactions t
                    ON t.bank_account_id = ba.id AND t.transaction_date < :corte
                 WHERE ba.id = CAST(:c AS uuid) GROUP BY 1"""),
                {"c": cid, "corte": CORTE_CONTABIL})).first()
            if not linha:
                continue
            derivado = round(float(saldo_corte) - float(linha[1] or 0), 2)
            print(f"   {linha[0]:<16} R$ {derivado:>12,.2f}")
        nao_cobertas = (await db.execute(text("""
            SELECT coalesce(bank_name, name) FROM bank_accounts WHERE id::text <> ALL(:ids)"""),
            {"ids": list(ABERTURA_NO_CORTE)})).scalars().all()
        for nome in nao_cobertas:
            print(f"   {nome:<16} SEM saldo de abertura declarado — não dá para derivar")
            lacunas.append(f"conta bancária «{nome}» sem saldo de abertura no corte")

        # ── 3. contas com saldo de natureza IMPOSSÍVEL ───────────────────────────────
        invertidas = (await db.execute(text("""
            SELECT p.code, p.name, p.account_type,
                   round(sum(CASE WHEN a.conta_debito = p.code THEN a.valor ELSE -a.valor END), 2) dev
              FROM accounting_entries a
              JOIN fin_accounting_accounts p ON p.code IN (a.conta_debito, a.conta_credito)
             WHERE a.status = 'confirmado' AND p.account_type IN ('ASSET', 'LIABILITY', 'EQUITY')
             GROUP BY 1, 2, 3
            HAVING abs(sum(CASE WHEN a.conta_debito = p.code THEN a.valor ELSE -a.valor END)) > 0.005
             ORDER BY 1"""))).all()
        fora_da_natureza = []
        for code, name, tipo, dev in invertidas:
            if code in SEM_JULGAMENTO_DE_SINAL:
                continue
            d = float(dev)
            if (d > 0) if tipo == "ASSET" else (d < 0):
                continue
            fora_da_natureza.append((code, name, tipo, d))
        print(f"\ncontas com saldo IMPOSSÍVEL para a natureza: {len(fora_da_natureza)}")
        for code, name, tipo, d in fora_da_natureza:
            print(f"   {code:<10} {name[:36]:<36} {tipo:<10} R$ {d:>12,.2f}")
            lacunas.append(f"{code} «{name[:30]}» com saldo de natureza impossível (R$ {d:,.2f})")
        if fora_da_natureza:
            print("   → PISTA, não prova. Pode ser abertura, pode ser classificação errada,")
            print("     pode ser efeito entre as duas empresas. Cada uma pede a sua leitura;")
            print("     em 26/09/2026, das sete invertidas, nenhuma era abertura pura.")

        # ── 4. o que só o dono sabe ──────────────────────────────────────────────────
        n_equip = (await db.execute(text("SELECT count(*) FROM equipments"))).scalar() or 0
        if not n_equip:
            print("\nimobilizado: `equipments` tem ZERO linhas — não há inventário de bens")
            lacunas.append("sem inventário de equipamento: o imobilizado de abertura é desconhecido")

        emprestimo = (await db.execute(text("""
            SELECT count(*) FILTER (WHERE conta_debito = '2.1.6.01'),
                   count(*) FILTER (WHERE conta_credito = '2.1.6.01')
              FROM accounting_entries WHERE '2.1.6.01' IN (conta_debito, conta_credito)
               AND status = 'confirmado'"""))).first()
        if emprestimo and emprestimo[0] and not emprestimo[1]:
            print(f"\nempréstimos: {emprestimo[0]} pagamento(s) e NENHUM recebimento registrado")
            print("   → ou a dívida nasceu antes dos livros, ou são empréstimos CONCEDIDOS")
            print("     lançados como devolução — e aí o lugar é o ATIVO. É pergunta do dono.")
            lacunas.append("2.1.6.01 só tem débito: dívida anterior ou empréstimo concedido?")

    print(f"\nTOTAL: {len(lacunas)} lacuna(s) no balanço de abertura")
    return 1 if lacunas else 0


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    raise SystemExit(asyncio.run(main()))
