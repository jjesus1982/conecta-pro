"""Tipo monetário canônico dos schemas financeiros.

Causa-raiz de uma classe inteira de bugs de tela ("soma vira string", cards R$0,
DRE zerado): o Pydantic v2 serializa ``Decimal`` como **string** no modo JSON — que
é o modo que o FastAPI usa nas respostas. O front então faz ``reduce`` concatenando
strings ("2890.00" + "689.00" = "2890.00689.00…") ou lê um campo numérico que veio
como texto e mostra 0.

``Money`` resolve na origem: continua sendo ``Decimal`` internamente (precisão
contábil e validações ``gt=0``/``ge=0`` preservadas), mas **serializa como número
nativo** (float) no JSON. Assim o bug morre no backend e não reaparece a cada tela
nova. Use ``Money`` em TODO campo de valor monetário de schema financeiro (entrada
e saída) — nunca ``Decimal`` cru. O guard-rail em testes trava a regressão disso.
"""

from decimal import Decimal
from typing import Annotated

from pydantic import PlainSerializer

Money = Annotated[
    Decimal,
    PlainSerializer(
        lambda v: float(v) if v is not None else None,
        return_type=float,
        when_used="always",
    ),
]

MoneyOpt = Annotated[
    Decimal | None,
    PlainSerializer(
        lambda v: float(v) if v is not None else None,
        return_type=float,
        when_used="always",
    ),
]

__all__ = ["Money", "MoneyOpt"]
