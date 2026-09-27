#!/usr/bin/env python3
"""Oráculo C8 — o simulador de regime reproduz as guias REAIS e recusa o que não sabe.

## A regra que isto afirma

A fórmula do Simples não é decorada: é `(RBT12 × nominal − deduzir) / RBT12`, e a prova de
que a tabela está certa são **as duas guias reais da Patrimonial**, que caem em faixas
DIFERENTES (07/2026 na 2ª, 08/2026 na 3ª) e fecham nas duas.

E três coisas que o simulador tem de RECUSAR em vez de responder:

  • RBT12 na **6ª faixa** — as fontes dão dedução de R$ 828.000, o que faria a alíquota
    CAIR de 16,89% para 10,00% ao cruzar R$ 3,6 mi. Curva progressiva não cai. Enquanto não
    confirmada na fonte oficial, recusa — e a Patrimonial está a 87% desse teto.
  • RBT12 zero ou negativo.
  • Empresa sem receita na competência.

## O erro do material de mercado, travado aqui

A planilha do curso que o dono comprou usa, na aba `REAL`, **PIS 1,65% e COFINS 7,6%** —
as alíquotas NÃO-cumulativas. Para vigilância e limpeza são 0,65% e 3,00%, CUMULATIVAS por
lei (Lei 10.833/2003, art. 10, XXIV). São 5,6 pontos de diferença, e quem decidisse o regime
por aquela planilha escolheria errado.

## E a armadilha que me pegou

A CPP patronal **não é igual nos três regimes**: no Anexo IV são 20% + RAT 3% = 23%
(terceiros 5,8% NÃO é devido no Simples); no Lucro Real e no Presumido são 28,8%. Excluí-la
"porque é devida em todos" — como fiz na primeira comparação de 26/09 — superestima a
vantagem do Lucro Real em 5,8 pontos de folha.

Linha canônica: `TOTAL desvios C8: <n>`.
"""

from __future__ import annotations

import sys

desvios = 0


def afirma(cond: bool, msg: str) -> None:
    global desvios
    if cond:
        print(f"OK {msg}")
    else:
        desvios += 1
        print(f"FALHOU: {msg}")


#: (competência, receita bruta, DAS da guia, faixa esperada, RBT12 que produz a guia).
#: Os RBT12 foram obtidos INVERTENDO a fórmula a partir da guia real — por isso a
#: tolerância de R$ 1,00: o resíduo é do RBT12 reconstruído, não da fórmula.
GUIAS_REAIS = [
    ("2026-07", 255_400.06, 17_048.87, 2, 348_387.10),
    ("2026-08", 262_161.56, 18_399.33, 3, 390_320.55),
]

PATRIMONIAL = "7d79ed12-d480-4906-b2e0-2b2c4d299bab"
ELETRONICA = "619a3df1-8bce-49ce-b77a-04f80a0e8491"


def main() -> int:
    from modules.financial.services.simulador_regime import (  # noqa: PLC0415
        ANEXO_IV,
        COFINS_CUMULATIVO,
        PIS_CUMULATIVO,
        FaixaNaoConfirmadaError,
        RBT12NaoDeterminadoError,
        aliquota_efetiva_anexo_iv,
        simular,
    )

    # ─── a fórmula contra as guias REAIS, em faixas diferentes ───────────────
    for comp, receita, das_guia, faixa_esp, rbt in GUIAS_REAIS:
        efetiva, faixa = aliquota_efetiva_anexo_iv(rbt)
        calculado = receita * efetiva
        afirma(faixa == faixa_esp, f"{comp}: cai na faixa {faixa_esp}")
        afirma(
            abs(calculado - das_guia) < 1.00,
            f"{comp}: DAS calculado R$ {calculado:,.2f} ≈ guia R$ {das_guia:,.2f}",
        )

    # ─── a curva é contínua nas fronteiras: tabela errada quebra aqui ────────
    for teto, _nominal, _ded in ANEXO_IV[:-1]:
        antes, _ = aliquota_efetiva_anexo_iv(teto)
        depois, _ = aliquota_efetiva_anexo_iv(teto + 1.0)
        afirma(
            depois >= antes - 1e-9,
            f"em R$ {teto:,.0f} a alíquota não CAI ({antes:.4%} → {depois:.4%})",
        )

    # ─── o que ele tem de recusar ────────────────────────────────────────────
    try:
        aliquota_efetiva_anexo_iv(3_700_000)
        afirma(False, "6ª faixa devia RECUSAR — dedução não confirmada na fonte oficial")
    except FaixaNaoConfirmadaError:
        afirma(True, "6ª faixa recusada — dedução não confirmada")
    for ruim in (0, -1):
        try:
            aliquota_efetiva_anexo_iv(ruim)
            afirma(False, f"RBT12 {ruim} devia recusar")
        except RBT12NaoDeterminadoError:
            afirma(True, f"RBT12 {ruim} recusado")

    # ─── PIS/COFINS cumulativos: o erro da planilha de mercado ───────────────
    afirma(PIS_CUMULATIVO == 0.0065, "PIS cumulativo 0,65% (não 1,65% não-cumulativo)")
    afirma(COFINS_CUMULATIVO == 0.0300, "COFINS cumulativo 3,00% (não 7,60%)")

    r = simular(PATRIMONIAL, "2026-08")
    real = r["cenarios"]["lucro_real"]["abertura"]
    afirma(
        abs(real["pis"] / r["receita"] - 0.0065) < 1e-9,
        "no Lucro Real o PIS sai a 0,65% da receita, não 1,65%",
    )

    # ─── a CPP NÃO é igual nos três: 23% no Anexo IV, 28,8% no Real ──────────
    simples = r["cenarios"]["simples"]["abertura"]
    folha = r["folha"]
    afirma(
        abs(simples["cpp_patronal_fora_do_das"] / folha - 0.23) < 1e-9,
        "Anexo IV: CPP 20% + RAT 3% = 23% (terceiros NÃO é devido no Simples)",
    )
    afirma(
        abs(real["cpp_patronal"] / folha - 0.288) < 1e-9,
        "Lucro Real: CPP 20% + RAT 3% + terceiros 5,8% = 28,8%",
    )
    afirma(
        real["cpp_patronal"] > simples["cpp_patronal_fora_do_das"],
        "a CPP do Lucro Real é MAIOR — excluí-la da comparação favorece o Real indevidamente",
    )

    # ─── empresa sem receita recusa, não devolve zero ────────────────────────
    try:
        simular(ELETRONICA, "2020-01")
        afirma(False, "competência sem receita devia recusar")
    except RBT12NaoDeterminadoError:
        afirma(True, "competência sem receita recusa, não devolve zero")

    print(f"\nTOTAL desvios C8: {desvios}")
    return 1 if desvios else 0


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    raise SystemExit(main())
