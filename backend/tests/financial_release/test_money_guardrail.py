"""Guard-rail anti-regressão do fix-raiz Decimal→número (Financeiro).

Contexto: Pydantic v2 serializa ``Decimal`` como STRING no modo JSON (o modo do
FastAPI). Isso gerou uma classe inteira de bugs de tela (soma vira concatenação,
cards R$0, DRE zerado). O fix-raiz é o tipo ``Money`` em
``modules.financial.schemas._money`` — Decimal interno, número no JSON.

Este teste TRAVA a regressão em duas camadas:
1. Lint: nenhum schema financeiro pode voltar a anotar campo como ``Decimal`` cru.
2. Funcional: os schemas de stats/list (os que alimentam os cards das telas)
   têm que serializar valores monetários como número nativo no JSON.

Se este teste quebrar, alguém reintroduziu ``: Decimal`` num schema financeiro —
troque por ``Money``/``MoneyOpt`` (ver _money.py).
"""

import json
import re
from decimal import Decimal
from pathlib import Path

SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "modules" / "financial" / "schemas"

# _money.py define o próprio tipo; __init__.py não tem campos.
_EXEMPT = {"_money.py", "__init__.py"}

# Anotação Decimal crua: `: Decimal` ou `: Decimal | None` (fora de comentário).
_BARE_DECIMAL = re.compile(r"^\s*\w+\s*:\s*Decimal\b")


def test_no_bare_decimal_annotations_in_financial_schemas():
    """Nenhum campo de schema financeiro pode ser anotado como Decimal cru."""
    offenders: list[str] = []
    for path in sorted(SCHEMAS_DIR.glob("*.py")):
        if path.name in _EXEMPT:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.split("#", 1)[0]
            if _BARE_DECIMAL.match(stripped):
                offenders.append(f"{path.name}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Campo(s) anotado(s) como Decimal cru em schema financeiro — serializa como "
        "STRING no JSON e quebra as telas. Use Money/MoneyOpt de schemas/_money.py:\n"
        + "\n".join(offenders)
    )


def _assert_money_is_number(payload: str, fields: list[str]) -> None:
    data = json.loads(payload)
    for field in fields:
        value = data[field]
        assert isinstance(value, (int, float)) and not isinstance(value, bool), (
            f"{field}={value!r} serializou como {type(value).__name__}; "
            "esperado número nativo (fix-raiz Money regrediu)"
        )


def test_payable_stats_serializes_money_as_number():
    from modules.financial.schemas.payable import PayableAccountStats

    stats = PayableAccountStats(
        total_count=70,
        total_value=Decimal("208631.47"),
        total_paid=Decimal("5000.00"),
        total_pending=Decimal("203631.47"),
        total_overdue=Decimal("100.10"),
    )
    _assert_money_is_number(
        stats.model_dump_json(),
        ["total_value", "total_paid", "total_pending", "total_overdue"],
    )


def test_receivable_stats_serializes_money_as_number():
    from modules.financial.schemas.receivable import ReceivableAccountStats

    stats = ReceivableAccountStats(
        total_count=27,
        total_value=Decimal("529069.58"),
        total_received=Decimal("1.23"),
        total_pending=Decimal("2.34"),
        total_overdue=Decimal("3.45"),
    )
    _assert_money_is_number(
        stats.model_dump_json(),
        ["total_value", "total_received", "total_pending", "total_overdue"],
    )


def test_cashflow_projection_serializes_money_as_number():
    from datetime import date

    from modules.financial.schemas.cashflow import CashFlowProjection

    proj = CashFlowProjection(
        date=date(2026, 7, 16),
        payables=Decimal("1737.14"),
        receivables=Decimal("1.00"),
        balance=Decimal("-1736.14"),
        cumulative_balance=Decimal("66021.15"),
    )
    _assert_money_is_number(
        proj.model_dump_json(),
        ["payables", "receivables", "balance", "cumulative_balance"],
    )


def test_money_type_keeps_gt_validation():
    """O fix-raiz não pode afrouxar validação de entrada (FIN-05: valor > 0)."""
    import pytest
    from pydantic import ValidationError

    from modules.financial.schemas.payable import PayableAccountCreate

    with pytest.raises(ValidationError):
        PayableAccountCreate(
            condominio_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            description="valor zero deve falhar",
            gross_value=Decimal("0"),
            due_date="2026-08-01",
        )
