"""Teste-âncora do registry: fail-closed + filtro por módulo (sem pytest)."""
from modules.ai.conversation.services.orquestrador import tool_registry as tr


async def _noop(db, user, scope, **args):
    return {"ok": True}


def main() -> None:
    # 1) tool com módulo registra e é recuperável
    t_fin = tr.register(tr.ToolDef("t_fin", "financeiro", "d", {"type": "object", "properties": {}}, _noop))
    t_op = tr.register(tr.ToolDef("t_op", "operacional", "d", {"type": "object", "properties": {}}, _noop))
    assert tr.get_tool("t_fin") is t_fin
    print("OK registrou tool com módulo")

    # 2) fail-closed: tool sem módulo NÃO registra
    reprovou = False
    try:
        tr.register(tr.ToolDef("t_sem", "", "d", {"type": "object", "properties": {}}, _noop))
    except ValueError:
        reprovou = True
    assert reprovou, "tool sem módulo deveria ter sido recusada"
    assert tr.get_tool("t_sem") is None
    print("OK fail-closed: tool sem módulo recusada")

    # 3) filtro: gestor com {operacional} não recebe a tool de financeiro
    got = {t.name for t in tr.tools_for_modules({"operacional"})}
    assert "t_op" in got and "t_fin" not in got, f"filtro errado: {got}"
    print("OK filtro por módulo (financeiro fora do escopo operacional)")

    # 4) schema OpenAI bem formado
    sch = tr.openai_schema(t_op)
    assert sch["type"] == "function" and sch["function"]["name"] == "t_op"
    print("OK schema OpenAI")

    # 5) fail-closed: tool com nome duplicado NÃO sobrescreve a original
    t_dup1 = tr.register(tr.ToolDef("dup", "financeiro", "primeira", {"type": "object", "properties": {}}, _noop))
    reprovou_dup = False
    try:
        tr.register(tr.ToolDef("dup", "operacional", "segunda", {"type": "object", "properties": {}}, _noop))
    except ValueError:
        reprovou_dup = True
    assert reprovou_dup, "tool duplicada deveria ter sido recusada"
    assert tr.get_tool("dup") is t_dup1, "registro original foi sobrescrito pela duplicata"
    print("OK duplicada rejeitada")

    print("TEST tool_registry PASS")


if __name__ == "__main__":
    main()
