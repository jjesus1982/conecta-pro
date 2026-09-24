"""Oráculo — validador de CPF/CNPJ das integrações governamentais (24/09/2026).

Por que existe: `government_integrations.utils.validar_cpf` misturava duas variantes da fórmula
do dígito verificador ((soma*10) % 11 seguido de `11 - resto`) e REPROVAVA CPF válido —
529.982.247-25 dava dígito 9 em vez de 2. É o validador usado pela consulta à Receita: um CPF
verdadeiro era barrado antes de sair de casa. Achado pela frente DGX F6.

O que afirma: CPFs de dígito conhecido passam, os com dígito trocado e os de dígitos iguais
reprovam; o CNPJ da Conecta Mais passa. Roda em qualquer lugar (função pura). Sai 0/1.
"""

from __future__ import annotations

import sys

from modules.government_integrations.utils import validar_cnpj, validar_cpf

CASOS = [
    ("529.982.247-25", True),
    ("123.456.789-09", True),
    ("000.000.001-91", True),
    ("529.982.247-26", False),
    ("111.111.111-11", False),
    ("123", False),
]


def main() -> int:
    falhas = [c for c, esperado in CASOS if validar_cpf(c) is not esperado]
    if not validar_cnpj("35.710.481/0001-03"):
        falhas.append("CNPJ 35.710.481/0001-03")
    for f in falhas:
        print(f"FALHOU: {f}")
    print(f"TOTAL validar_cpf: {len(falhas)} falha(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
