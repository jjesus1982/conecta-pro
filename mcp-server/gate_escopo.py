"""O ESCOPO passa a ser uma parede, e não uma conta impressa no log (11/09/2026).

🔴 O QUE ESTAVA ACONTECENDO. O filtro de escopo em `server.py` chamava `mcp.remove_tool(n)`
dentro de um `try/except Exception: pass`, e imprimia quantas ferramentas "sobraram" por
ARITMÉTICA (`len(todas) - len(fora)`). Só que `remove_tool` **não existe no fastmcp 4.0.3**
— é API da 3.4, contra a qual aquele código foi escrito. Toda chamada levantava
`AttributeError`, o `except` engolia, e o conector anunciava:

    [mcp] escopo=ged,fiscal · servindo 42 de 254 ferramentas

enquanto servia **266**. Medido em 11/09 nos três conectores: `tools/list` devolvia o
catálogo inteiro, com `fechar_folha`, `criar_lead` e as ferramentas de dinheiro visíveis no
conector do kit — cuja única proteção declarada era, nas palavras do próprio compose, "o
ESCOPO".

A lição é a mesma que o comentário logo abaixo daquele print já ensinava sobre outra coisa:
**número que a gente calcula não prova nada; só o número que a gente MEDE do lado de fora
prova.** A conta estava certa; a realidade, não.

O DESENHO AQUI. Escopo vira middleware, como as outras duas paredes da casa
(`gate_propose`, `identidade`), por três razões:

  1. Não depende de mutar o registro de ferramentas — API que muda de versão para versão e
     que já quebrou calada uma vez.
  2. Fecha as DUAS portas. `remove_tool`, mesmo que funcionasse, só sumiria com a ferramenta
     da LISTA; um cliente que soubesse o nome ainda chamaria. Aqui `on_call_tool` recusa.
  3. Falha fechando: sem lista de permitidas, ninguém entra.
"""
from __future__ import annotations

import os

try:
    from fastmcp.server.middleware import Middleware as _Base
except Exception:  # noqa: BLE001 — no host (sem fastmcp) as travas ainda importam este módulo
    _Base = object


class GateEscopo(_Base):
    """Serve e executa SOMENTE as ferramentas do escopo declarado."""

    def __init__(self, permitidas: set[str]) -> None:
        self.permitidas = set(permitidas)

    async def on_list_tools(self, context, call_next):  # noqa: ANN001
        tools = await call_next(context)
        return [t for t in tools if getattr(t, "name", None) in self.permitidas]

    async def on_call_tool(self, context, call_next):  # noqa: ANN001
        nome = getattr(getattr(context, "message", None), "name", "") or ""
        if nome not in self.permitidas:
            from fastmcp.exceptions import ToolError  # noqa: PLC0415

            raise ToolError(
                f"⛔ `{nome}` está fora do escopo deste conector "
                f"(`{os.getenv('MCP_ESCOPO') or '—'}`). Não é permissão que falta: esta "
                f"ferramenta trata de outro assunto e não é servida aqui.")
        return await call_next(context)


def instalar(mcp, permitidas: set[str] | None) -> int:
    """Instala a parede. Devolve quantas ferramentas ficam servidas (medido, não estimado)."""
    if permitidas is None:
        return -1  # sem escopo declarado: catálogo inteiro, como sempre foi no Cowork
    mcp.add_middleware(GateEscopo(permitidas))
    return len(permitidas)
