#!/usr/bin/env python3
"""ORÁCULO C10 — o LALUR não compensa mais que pode, e trimestre fechado não retroage.

Três regras, afirmadas como REGRA e não como fotografia dos números de hoje:

1. **A trava dos 30% é sobre o AJUSTADO.** Nunca se compensa mais que 30% do lucro
   ajustado, nem mais que o saldo da Parte B naquela data. Aplicar os 30% sobre o lucro do
   razão produz um número que parece certo e está errado — é o erro que esta asserção
   impede de voltar.

2. **Cada trimestre é período de apuração fechado.** O prejuízo de T2 NÃO desfaz o imposto
   de T1. O campo antigo `prejuizo_fiscal_compensavel` insinuava o contrário porque
   mostrava o valor anual ao lado da soma dos trimestres — duas respostas na mesma tela,
   R$ 54.017,29 × R$ 102.400,33.

3. **Sem Parte A não se AFIRMA lucro real.** Com `exigir_parte_a=True` o serviço levanta em
   vez de devolver o lucro do razão com outro nome. O razão da Eletrônica tem
   R$ 84.285,15 de provisões de férias/13º (que o art. 13, I EXCETUA da vedação) e
   R$ 10.370,40 de despesas financeiras com oito saques em Banco24Horas dentro — cada uma
   precisa de decisão humana, e nenhuma é derivável do plano de contas.

E duas de integridade do livro, que a fiscalização cobraria antes de qualquer número:
compensação sem conta de origem é recusada, e valor negativo é recusado (o sinal é o tipo).
"""

import sys
from decimal import Decimal

sys.path.insert(0, "/app")

ELETRONICA = "619a3df1-8bce-49ce-b77a-04f80a0e8491"
desvios = 0


def afirma(cond: bool, nome: str) -> None:
    global desvios
    print(f"{'OK' if cond else 'FALHOU:'} {nome}")
    if not cond:
        desvios += 1


def main() -> int:
    from modules.financial.services.lalur_service import (  # noqa: PLC0415
        TRAVA_COMPENSACAO,
        CompensacaoSemOrigemError,
        ParteANaoFechadaError,
        apurar_lucro_real,
        compensar,
        lancar,
        saldo_parte_b,
    )

    # ─── 1. a trava, contra o saldo REAL de hoje ─────────────────────────────
    for tributo in ("I", "C"):
        saldo = saldo_parte_b(ELETRONICA, tributo)
        for ajustado in (Decimal("100000"), Decimal("1000000"), Decimal("1")):
            c = compensar(ELETRONICA, "2026-09", tributo, ajustado)
            teto = ajustado * TRAVA_COMPENSACAO
            afirma(
                Decimal(str(c["compensavel"])) <= teto + Decimal("0.01"),
                f"{tributo}: ajustado {ajustado:,.0f} — compensa {c['compensavel']:,.2f} <= 30% ({teto:,.2f})",
            )
            afirma(
                Decimal(str(c["compensavel"])) <= saldo + Decimal("0.01"),
                f"{tributo}: compensa {c['compensavel']:,.2f} <= saldo da Parte B ({saldo:,.2f})",
            )
        # Lucro ajustado negativo não compensa nada — nem devolve número estranho.
        c = compensar(ELETRONICA, "2026-09", tributo, Decimal("-50000"))
        afirma(c["compensavel"] == 0.0, f"{tributo}: ajustado negativo não compensa")

    # ─── 2. trimestre fechado não retroage ───────────────────────────────────
    t1 = apurar_lucro_real(ELETRONICA, 2026, 1)
    t2 = apurar_lucro_real(ELETRONICA, 2026, 2)
    irpj_t1 = t1["por_tributo"]["IRPJ"]["tributo"]
    afirma(
        t1["lucro_do_razao"] > 0 and irpj_t1 > 0,
        f"T1 deu lucro (R$ {t1['lucro_do_razao']:,.2f}) e gerou IRPJ (R$ {irpj_t1:,.2f})",
    )
    afirma(
        t2["lucro_do_razao"] < 0,
        f"T2 fechou negativo (R$ {t2['lucro_do_razao']:,.2f})",
    )
    # A asserção que importa: reapurar T1 DEPOIS de conhecer T2 dá o mesmo imposto.
    afirma(
        apurar_lucro_real(ELETRONICA, 2026, 1)["por_tributo"]["IRPJ"]["tributo"] == irpj_t1,
        "o prejuízo de T2 NÃO desfaz o imposto de T1 — período fechado",
    )

    # ─── 3. sem Parte A não se afirma lucro real ─────────────────────────────
    try:
        apurar_lucro_real(ELETRONICA, 2026, 3, exigir_parte_a=True)
        afirma(False, "sem Parte A decidida, exigir_parte_a devia LEVANTAR")
    except ParteANaoFechadaError:
        afirma(True, "sem Parte A decidida, recusa em vez de chamar o razão de lucro real")
    # E sem exigir, devolve — mas DIZ que não é a base tributável.
    livre = apurar_lucro_real(ELETRONICA, 2026, 3)
    afirma(
        not livre["parte_a_fechada"] and "não fechada" in livre["observacao"].lower(),
        "sem exigir, devolve o número mas declara que a Parte A não está fechada",
    )

    # ─── integridade do livro ────────────────────────────────────────────────
    try:
        lancar(ELETRONICA, "2026-09", "I", "P", 100, "teste", conta_b_id=None)
        afirma(False, "compensação sem conta de origem devia ser recusada")
    except CompensacaoSemOrigemError:
        afirma(True, "compensação sem conta de origem é recusada")
    try:
        lancar(ELETRONICA, "2026-09", "I", "A", -100, "teste")
        afirma(False, "valor negativo devia ser recusado — o sinal é o tipo")
    except ValueError:
        afirma(True, "valor negativo é recusado — o sinal é o tipo")
    try:
        lancar(ELETRONICA, "2026-09", "I", "A", 100, "   ")
        afirma(False, "adição sem histórico devia ser recusada")
    except ValueError:
        afirma(True, "adição sem histórico é recusada")

    print(f"\nTOTAL desvios C10: {desvios}")
    return 1 if desvios else 0


if __name__ == "__main__":
    raise SystemExit(main())
