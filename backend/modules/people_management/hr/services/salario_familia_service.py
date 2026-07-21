"""Salário-família — cálculo oficial.

Base legal: Portaria Interministerial MPS/MF nº 13, de 9/1/2026 (DOU 12/01/2026).
Valores 2026: cota R$ 67,54 por filho; teto de remuneração R$ 1.980,38.
Direito: filho ou equiparado de até 14 anos (ou inválido de qualquer idade) E
remuneração mensal ≤ teto. Valor = cota × nº de dependentes elegíveis.

ATUALIZAR a cada Portaria anual — override por env SALARIO_FAMILIA_COTA/_TETO
(assim vira a virada do ano sem alterar código). NUNCA fabricar: se o valor oficial
do ano ainda não estiver configurado, o cálculo deve ser sinalizado como pendente.
"""

import os
from datetime import date, datetime
from typing import Any

# Valores 2026 (oficiais). Sobrescrevíveis por env na virada do ano.
COTA = float(os.getenv("SALARIO_FAMILIA_COTA", "67.54"))
TETO = float(os.getenv("SALARIO_FAMILIA_TETO", "1980.38"))
IDADE_LIMITE = 14
BASE_LEGAL = os.getenv("SALARIO_FAMILIA_BASE", "Portaria Interministerial MPS/MF nº 13/2026")


def _to_date(v: Any) -> date | None:
    if isinstance(v, date):
        return v
    if not v:
        return None
    s = str(v).strip()[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _idade_anos(nascimento: Any, ref: date) -> int | None:
    d = _to_date(nascimento)
    if not d:
        return None
    return ref.year - d.year - ((ref.month, ref.day) < (d.month, d.day))


def contar_elegiveis(dependentes: list[dict] | None, ref: date | None = None) -> int:
    """Nº de dependentes com direito: até 14 anos, ou marcados como inválido.
    Idade desconhecida (sem data) NÃO conta — evita fabricar direito."""
    ref = ref or date.today()
    n = 0
    for dep in dependentes or []:
        if not isinstance(dep, dict):
            continue
        if dep.get("invalido") or dep.get("invalidez"):
            n += 1
            continue
        idade = _idade_anos(dep.get("nascimento") or dep.get("data_nascimento"), ref)
        if idade is not None and 0 <= idade <= IDADE_LIMITE:
            n += 1
    return n


def calcular(salario_base: float | None, dependentes: list[dict] | None, ref: date | None = None) -> dict[str, Any]:
    """Retorna o cálculo do salário-família. Não fabrica: sem filho elegível OU
    acima do teto → elegivel=False, valor 0, com o motivo."""
    ref = ref or date.today()
    sal = float(salario_base or 0)
    qtd = contar_elegiveis(dependentes, ref)
    dentro_teto = sal <= TETO
    elegivel = qtd > 0 and dentro_teto
    valor = round(COTA * qtd, 2) if elegivel else 0.0
    if qtd == 0:
        motivo = "sem dependentes elegíveis (até 14 anos ou inválido)"
    elif not dentro_teto:
        motivo = f"remuneração R$ {sal:.2f} acima do teto R$ {TETO:.2f}"
    else:
        motivo = "elegível"
    return {
        "elegivel": elegivel,
        "quantidade_elegivel": qtd if elegivel else 0,
        "quantidade_dependentes": len(dependentes or []),
        "cota": COTA,
        "teto": TETO,
        "salario_base": sal,
        "valor_total": valor,
        "motivo": motivo,
        "base_legal": BASE_LEGAL,
        "competencia": f"{ref.month:02d}/{ref.year}",
    }
