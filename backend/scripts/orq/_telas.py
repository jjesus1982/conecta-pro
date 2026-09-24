"""Helper de oráculo: as telas que o backend REALMENTE serve, e a vigia sobre elas.

Nasceu em 24/09/2026 de uma dívida medida: `checar_nao_vigiado.py` saltou de 409 para 449
depois da onda fiscal. A régua dele é «tela é vigiada quando algum oráculo cita o slug dela».
Os oráculos da onda existiam e eram bons — provavam a REGRA (tributação, numeração, recusa) —
mas nenhum citava o id da tela, então as 40 telas novas nasceram descobertas.

A saída preguiçosa seria escrever os slugs num comentário e enganar o contador. Esta função
faz a coisa de verdade: monta o builder do módulo, confere que cada tela existe e que ela não
é uma casca vazia. Se alguém apagar a tela, renomear o id ou quebrar o builder, o oráculo da
frente fica vermelho — que é o ponto.

Uso, no fim do `main()` do oráculo da frente:

    from _telas import conferir_telas
    falhas += await conferir_telas(db, "fiscal", ("nfe-nova", "nfes-emitidas"))
"""

from __future__ import annotations

import inspect
from typing import Any


async def ids_do_modulo(db: Any, slug: str) -> set[str]:
    """Ids servidos pelo módulo — raiz e abas de grupo (tela dentro de `tabs` também conta)."""
    from modules.operacional.controllers.redesign_data_controller import BUILDERS  # noqa: PLC0415

    builder = BUILDERS.get(slug)
    if builder is None:
        raise LookupError(f"módulo «{slug}» não tem builder")
    telas = await (
        builder(db, current_user=None) if "current_user" in inspect.signature(builder).parameters else builder(db)
    )
    ids = set(telas)
    for v in telas.values():
        if isinstance(v, dict) and v.get("type") == "tabs":
            ids |= {ab.get("id") for ab in (v.get("tabs") or []) if ab.get("id")}
    return ids


#: Chaves que fazem uma tela ter conteúdo. Uma tela do redesign é sempre uma destas formas;
#: um dict sem nenhuma delas é casca — monta, aparece no menu e não mostra nada.
_CONTEUDO = ("rows", "fields", "cards", "items", "tabs", "series", "kpis", "blocks", "sections", "chat")


async def conferir_telas(db: Any, modulo: str, esperadas: tuple[str, ...]) -> list[str]:
    """Devolve a lista de falhas. Vazia = as telas existem e têm conteúdo declarado.

    Não afirma que o conteúdo está CERTO — isso é o resto do oráculo da frente. Afirma que a
    tela não sumiu e não virou casca, que é o que o mapa do não-vigiado quer saber.
    """
    falhas: list[str] = []
    try:
        ids = await ids_do_modulo(db, modulo)
    except Exception as e:  # noqa: BLE001 — builder que explode é a falha, e tem de ser dita
        return [f"(telas) o builder do módulo «{modulo}» não montou: {type(e).__name__}: {e}"]

    from modules.operacional.controllers.redesign_data_controller import BUILDERS  # noqa: PLC0415

    builder = BUILDERS[modulo]
    telas = await (
        builder(db, current_user=None) if "current_user" in inspect.signature(builder).parameters else builder(db)
    )
    for tid in esperadas:
        if tid not in ids:
            falhas.append(f"(telas) «{tid}» não existe no módulo «{modulo}» — tela sumiu ou o id mudou")
            continue
        scr = telas.get(tid)
        if isinstance(scr, dict) and scr.get("type") not in (None, "redirect") and not any(k in scr for k in _CONTEUDO):
            falhas.append(f"(telas) «{tid}» monta mas é casca: sem {'/'.join(_CONTEUDO[:5])}")
    return falhas
