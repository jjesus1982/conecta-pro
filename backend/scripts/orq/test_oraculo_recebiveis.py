"""Oráculo dos recebíveis: título vencido só existe se o dinheiro NÃO entrou.

Em 13/08/2026 a tela dizia "recebíveis vencidos R$152.077,82" e o Jordan respondeu
"não tenho inadimplência, ZERO inadimplência". Ele estava certo: R$147.577,82 já
estavam nas duas contas. Três defeitos empilhados no casamento entrada × título:

  1. exigia o valor BRUTO com tolerância de R$0,01 — mas o título é bruto e o
     cliente paga LÍQUIDO (ISS 5% + INSS 11%). Medido: Michelangelo 99%,
     Villa Dei Fiori 99%, Prime Arena 90%, Laranjeiras 87%. Nenhum cliente com
     retenção jamais baixava;
  2. lia o nome do pagador da DESCRIÇÃO. No Cora a descrição é a justificativa que
     o Jordan digita no app ("[CORA] Serviço de Agente de Portaria") e não nomeia
     ninguém — o pagador só existe em `counterparty_name`, que era ignorada;
  3. o token do nome era a palavra mais longa: "CONDOMINIO IDEAL FLORES" dava
     `CONDOMINIO`, que casa com toda a carteira — unicidade quebrada, nada baixava.

O que este oráculo trava:
  (a) nenhum título vencido tem, sem vínculo, uma entrada do MESMO pagador dentro
      da janela de retenção — se tem, a inadimplência é fabricada pelo casamento;
  (b) título baixado nunca recebeu MAIS do que o bruto (folga de 0,5%);
  (c) uma entrada não paga dois títulos;
  (d) `paid_value` do que foi baixado bate com a soma das entradas amarradas —
      é onde a retenção fica visível em vez de sumir.

Roda:
    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_oraculo_recebiveis.py
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from core.database import async_session_factory  # noqa: E402

PISO = 0.80
TETO = 1.005


async def main() -> None:
    falhas: list[str] = []
    async with async_session_factory() as db:
        # ── (a) inadimplência com o dinheiro na conta ────────────────────────
        # O token do pagador é a primeira palavra com 4+ letras que não seja tipo
        # de pessoa jurídica — o mesmo critério do serviço. Sem tirar "CONDOMINIO"
        # a checagem casaria qualquer cliente com qualquer entrada.
        fantasmas = (await db.execute(text("""
            WITH vencidos AS (
                SELECT r.id, r.customer_name, r.gross_value, r.due_date,
                       (SELECT w FROM regexp_split_to_table(r.customer_name, '[^A-Za-zÀ-ÿ]+') w
                         WHERE length(w) >= 4
                           AND upper(w) NOT IN ('CONDOMINIO','CONDOMÍNIO','RESIDENCIAL',
                                                'EDIFICIO','EDIFÍCIO','EMPRESARIAL','LTDA',
                                                'COMERCIO','SERVICOS','EMPRESA','CENTRO')
                         ORDER BY length(w) DESC LIMIT 1) AS tok
                FROM receivable_accounts r
                WHERE r.status = 'pendente' AND r.due_date < CURRENT_DATE
                  AND coalesce(r.customer_name,'') <> ''
            )
            SELECT v.customer_name, v.gross_value, sum(bt.amount) AS entrou
            FROM vencidos v
            JOIN bank_transactions bt
              ON bt.amount > 0 AND bt.receivable_payment_id IS NULL
             AND bt.transaction_date BETWEEN v.due_date - 5 AND v.due_date + 5
             AND lower(coalesce(bt.counterparty_name,'')) LIKE lower('%' || v.tok || '%')
            WHERE v.tok IS NOT NULL
            GROUP BY 1, 2
            HAVING sum(bt.amount) BETWEEN v.gross_value * :piso AND v.gross_value * :teto
        """), {"piso": PISO, "teto": TETO})).mappings().all()
        if fantasmas:
            falhas.append(
                f"{len(fantasmas)} título(s) 'vencido(s)' com o dinheiro já na conta: "
                + "; ".join(f"{f['customer_name'][:24]} deve R$ {float(f['gross_value']):,.2f} "
                            f"e entrou R$ {float(f['entrou']):,.2f}" for f in fantasmas[:4]))
        else:
            venc = float((await db.execute(text(
                "SELECT coalesce(sum(gross_value),0) FROM receivable_accounts "
                "WHERE status='pendente' AND due_date < CURRENT_DATE"))).scalar() or 0)
            print(f"OK inadimplência R$ {venc:,.2f} — nenhuma com entrada correspondente sem vínculo")

        # ── (b) ninguém paga mais do que deve ────────────────────────────────
        acima = (await db.execute(text(
            "SELECT customer_name, gross_value, paid_value FROM receivable_accounts "
            "WHERE status='paga' AND paid_value IS NOT NULL AND gross_value > 0 "
            "  AND paid_value > gross_value * :teto"), {"teto": TETO})).mappings().all()
        if acima:
            falhas.append(
                f"{len(acima)} título(s) baixado(s) com valor ACIMA do bruto: "
                + "; ".join(f"{a['customer_name'][:22]} bruto R$ {float(a['gross_value']):,.2f} "
                            f"recebido R$ {float(a['paid_value']):,.2f}" for a in acima[:4])
                + " — a janela de retenção virou porta de entrada")
        else:
            print("OK nenhum título recebeu mais do que o bruto")

        # ── (c) uma entrada não quita dois títulos ───────────────────────────
        # (Vários títulos apontando para a MESMA transação: o dinheiro seria contado
        # duas vezes. O caminho inverso — vários PIX para um título — é legítimo e
        # está em `_baixar_recebiveis_parcelados`.)
        dobrada = (await db.execute(text(
            "SELECT transacao_bancaria_id, count(*) n FROM receivable_accounts "
            "WHERE transacao_bancaria_id IS NOT NULL AND status='paga' "
            "GROUP BY 1 HAVING count(*) > 1"))).mappings().all()
        if dobrada:
            falhas.append(f"{len(dobrada)} transação(ões) bancária(s) quitando mais de um título — "
                          f"o mesmo dinheiro contado duas vezes")
        else:
            print("OK nenhuma entrada bancária quitou dois títulos")

        # ── (d) o recebido bate com as entradas amarradas ────────────────────
        divergentes = (await db.execute(text("""
            SELECT r.customer_name, r.paid_value, sum(bt.amount) AS amarrado
            FROM receivable_accounts r
            JOIN bank_transactions bt ON bt.receivable_payment_id = r.id
            WHERE r.status = 'paga' AND r.paid_value IS NOT NULL
            GROUP BY 1, 2 HAVING abs(r.paid_value - sum(bt.amount)) > 0.01
        """))).mappings().all()
        if divergentes:
            falhas.append(
                f"{len(divergentes)} título(s) com paid_value diferente das entradas amarradas: "
                + "; ".join(f"{d['customer_name'][:22]}: registra R$ {float(d['paid_value']):,.2f}, "
                            f"amarrado R$ {float(d['amarrado']):,.2f}" for d in divergentes[:4]))
        else:
            print("OK o valor recebido bate com as entradas amarradas em cada título")

        # ── (e) NF-e de RETORNO não vira dívida ──────────────────────────────
        # Toda NF-e que chega com nosso CNPJ no destinatário virava conta a pagar,
        # sem olhar o CFOP. Equipamento NOSSO voltando do conserto (CFOP 2913) era
        # cobrado de nós: R$25.600 numa nota só, R$32.612,69 em seis.
        fantasmas_nfe = (await db.execute(text("""
            SELECT e.numero, e.emitente_nome, p.net_value,
                   (SELECT string_agg(DISTINCT m[1], ',')
                      FROM regexp_matches(e.xml_raw, '<CFOP>(\\d{4})</CFOP>', 'g') m) AS cfops
            FROM nfe_entradas e
            JOIN payable_accounts p ON p.nota_fiscal_numero = e.numero AND p.origem = 'nfe_entrada'
            WHERE p.status = 'pendente' AND e.xml_raw ~ '<CFOP>'
              AND NOT EXISTS (
                SELECT 1 FROM regexp_matches(e.xml_raw, '<CFOP>(\\d{4})</CFOP>', 'g') m2
                 WHERE m2[1] !~ '^[1256](9[0-9][0-9]|41[45]|91[0-9]|92[0-9]|55[0-9]|20[12])$')
        """))).mappings().all()
        if fantasmas_nfe:
            falhas.append(
                f"{len(fantasmas_nfe)} conta(s) a pagar de NF-e que NÃO gera pagamento "
                f"(retorno/devolução): "
                + "; ".join(f"n{f['numero']} {f['emitente_nome'][:22]} "
                            f"R$ {float(f['net_value']):,.2f} CFOP {f['cfops']}"
                            for f in fantasmas_nfe[:4])
                + " — a nota existe, a dívida não")
        else:
            print("OK nenhuma NF-e de retorno/devolução virou conta a pagar")

    if falhas:
        for f in falhas:
            print(f"FALHOU: {f}")
        raise AssertionError(f"{len(falhas)} invariante(s) dos recebíveis quebrada(s)")
    print("TEST oraculo_recebiveis PASS")


if __name__ == "__main__":
    asyncio.run(main())
