"""Rodar corrotina de dentro de código síncrono, haja ou não um loop em execução.

Existe porque a mesma armadilha mordeu duas vezes em 10/09/2026, em módulos distantes:

  · `status_documento_sync` era chamado por `ponto_kit_service` de dentro de contexto async — o
    `asyncio.run` recusava, o except engolia, e o espelho de ponto saía SEM a informação de
    assinatura, doze vezes, com um WARNING que ninguém lê;
  · o bloco `sistema` do orquestrador do GEDEON (a metade que GERA o kit) rodava dentro da task do
    Celery, que já tem loop: 12 blocos passavam e o décimo terceiro morria com
    `asyncio.run() cannot be called from a running event loop` — o kit nunca era criado no banco.

Duas cópias da mesma correção divergem na primeira mudança. Aqui ela tem um dono.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

#: Teto de espera quando cai na thread. Montagem de kit leva minutos; consulta, segundos.
TIMEOUT_PADRAO = 900


def rodar_corotina[T](fabrica: Callable[[], Coroutine[Any, Any, T]], timeout: int = TIMEOUT_PADRAO) -> T:
    """Executa a corrotina que `fabrica()` devolve.

    Sem loop no ar: `asyncio.run` direto. Com loop: uma thread própria, que tem o seu — é o mesmo
    motivo pelo qual os helpers `_sync` usam engine com NullPool: cada loop precisa das suas
    conexões, e uma corrotina não pode ser esperada por um loop que não a criou.

    Recebe uma FÁBRICA e não a corrotina pronta: corrotina criada e não aguardada vira
    `RuntimeWarning: coroutine was never awaited` quando o caminho muda.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(fabrica())

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(lambda: asyncio.run(fabrica())).result(timeout=timeout)
