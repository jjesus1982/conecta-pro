"""Um registro ruim não pode derrubar a listagem inteira.

Origem (30/09/2026): `listar_propostas` devolvia 500 a partir do 2º registro. A causa era UM
campo de UM registro — `discount_type='percent'` onde o enum exige `'percentage'`. A listagem
inteira do CRM ficou inacessível por causa de uma linha, e o cliente MCP só via
«Internal Server Error», sem campo, sem id, sem classe de exceção.

A regra que isto afirma: **listar é leitura**, e leitura degrada, não quebra. O registro que
não serializa sai da lista com um aviso nomeado — quem o criou aparece no log com id e campo,
que é o que permite corrigir em vez de adivinhar.

⚠️ Vale para LISTAGEM, não para detalhe nem para escrita. Pedir UM registro e receber um
registro mutilado seria pior que o erro: ali o 4xx/5xx é a resposta honesta.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def serializar_lista[T](
    modelo: type[T], registros: list[Any], *, rotulo: str = "registro"
) -> tuple[list[T], list[dict]]:
    """(itens que serializaram, problemas). Nunca levanta por causa de um registro."""
    itens: list[T] = []
    problemas: list[dict] = []
    for r in registros:
        try:
            itens.append(modelo.model_validate(r))
        except Exception as exc:  # noqa: BLE001 — um registro ruim não derruba a lista
            campos = []
            for e in getattr(exc, "errors", lambda: [])():
                loc = ".".join(str(x) for x in (e.get("loc") or ()))
                campos.append({"campo": loc, "valor": str(e.get("input"))[:80], "erro": e.get("type")})
            ident = str(getattr(r, "id", None) or getattr(r, "number", None) or "?")
            problemas.append({rotulo: ident, "campos": campos or [{"erro": type(exc).__name__}]})
            logger.warning(
                "listagem: %s %s fora do contrato e OMITIDO — %s",
                rotulo,
                ident,
                campos or str(exc)[:200],
            )
    return itens, problemas
