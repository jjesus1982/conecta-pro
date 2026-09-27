#!/usr/bin/env python3
"""ORÁCULO D1 — toda tabela de faixas do Simples no repositório é CONTÍNUA na fronteira.

A REGRA, não a fotografia. A parcela a deduzir de cada faixa da LC 123/2006 existe por um
motivo aritmético: fazer a alíquota EFETIVA no piso da faixa N bater exatamente com a
efetiva no teto da faixa N-1. Se não batesse, faturar um real a mais faria o imposto dar
um pulo, e a lei não é assim construída.

Isso transforma a tabela numa coisa AUTO-VERIFICÁVEL: não preciso confiar em nenhuma fonte
externa para saber se um número foi digitado errado. A própria dedução prova a alíquota.

Foi assim que apareceu, em 27/09/2026, o Anexo III do `crm/regime_tributario` com a 3ª
faixa em 13,20% quando as outras três cópias do repositório diziam 13,50%: o erro produz
DOIS saltos, −0,30pp entrando na faixa e +0,30pp saindo dela, porque a faixa errada está
entre duas certas. Uma cópia digitada à mão, um dígito trocado, e a precificação inteira
sub-declarava imposto naquela faixa.

A ÚNICA descontinuidade legítima é a entrada na 6ª faixa (acima de R$ 3,6 milhões): ali o
ISS sai do DAS e passa a ser recolhido direto ao município, então o DAS cobre menos
tributos e a efetiva cai de verdade. Ela aparece nas TRÊS tabelas independentes do
repositório, com autores diferentes — é a lei, não erro de ninguém. Por isso é a exceção
declarada aqui, e só ela.

Este oráculo NÃO fixa os valores das tabelas. Ele afirma a propriedade. Se amanhã a lei
mudar as alíquotas, a propriedade continua valendo e o oráculo continua certo.
"""

import sys

sys.path.insert(0, "/app")

TETO_5A_FAIXA = 3_600_000.00  # onde o ISS sai do DAS — a única quebra que a lei quer


def _efetiva(rbt12: float, nominal: float, deduzir: float) -> float:
    return (rbt12 * nominal - deduzir) / rbt12


def _conferir(nome: str, faixas) -> list[str]:
    """Cada fronteira interior tem de casar. Devolve as que não casam."""
    falhas = []
    for i in range(1, len(faixas)):
        fronteira = float(faixas[i - 1][0])
        if fronteira == TETO_5A_FAIXA:
            continue  # ISS sai do DAS aqui; a queda é da lei
        topo = _efetiva(fronteira, float(faixas[i - 1][1]), float(faixas[i - 1][2]))
        base = _efetiva(fronteira, float(faixas[i][1]), float(faixas[i][2]))
        if abs(base - topo) > 1e-9:
            falhas.append(
                f"{nome}: salto de {base - topo:+.4%} em R$ {fronteira:,.2f} "
                f"({topo:.4%} -> {base:.4%}) — parcela a deduzir não casa com a alíquota"
            )
    return falhas


def main() -> int:
    from modules.crm.services.regime_tributario import FAIXAS as CRM
    from modules.empresas.services.empresa_service import _SIMPLES_ANEXO_III as EMP
    from modules.financial.agents.tax_calculator import SIMPLES_ANEXO_III as TAX
    from modules.financial.services.simulador_regime import ANEXO_IV as SIM

    tabelas = {
        "crm/regime_tributario FAIXAS['III']": CRM["III"],
        "crm/regime_tributario FAIXAS['IV']": CRM["IV"],
        "empresas/empresa_service _SIMPLES_ANEXO_III": EMP,
        "financial/tax_calculator SIMPLES_ANEXO_III": TAX,
        "financial/simulador_regime ANEXO_IV": SIM,
    }

    desvios: list[str] = []
    for nome, faixas in tabelas.items():
        desvios += _conferir(nome, faixas)

    # E a mesma régua na fronteira de 3,6M, ao contrário: ali TEM de haver queda. Se um dia
    # alguém "consertar" a dedução da 6ª faixa para deixar contínuo, terá apagado o fato de
    # o ISS sair do DAS — e o oráculo precisa gritar nesse caso também.
    for nome, faixas in tabelas.items():
        for i in range(1, len(faixas)):
            if float(faixas[i - 1][0]) != TETO_5A_FAIXA:
                continue
            topo = _efetiva(TETO_5A_FAIXA, float(faixas[i - 1][1]), float(faixas[i - 1][2]))
            base = _efetiva(TETO_5A_FAIXA, float(faixas[i][1]), float(faixas[i][2]))
            if base >= topo:
                desvios.append(
                    f"{nome}: a 6ª faixa NÃO cai em R$ 3,6M ({topo:.4%} -> {base:.4%}). "
                    f"Acima desse teto o ISS sai do DAS; se a efetiva não cai, a dedução "
                    f"da 6ª faixa está errada ou o ISS foi contado duas vezes"
                )

    for d in desvios:
        print(f"   x {d}")
    print(f"TOTAL desvios D1: {len(desvios)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
