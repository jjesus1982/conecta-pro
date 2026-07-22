"""Lint do manifesto de risco das tools MCP. Roda a partir de /opt/conecta-pro/mcp-server."""
import re, pathlib
from tool_risk_manifest import TOOL_RISK, VALID_CLASSES, tools_include

SERVER = pathlib.Path(__file__).parent / "server.py"

def _declared_tools() -> set[str]:
    """Todos os nomes de função decorados com @mcp.tool em server.py."""
    src = SERVER.read_text(encoding="utf-8")
    # captura: linha @mcp.tool (com/sem parênteses) seguida de async def NOME(
    names = set()
    for m in re.finditer(r"@mcp\.tool[^\n]*\n\s*async def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", src):
        names.add(m.group(1))
    return names

def test_classes_sao_validas():
    for tool, klass in TOOL_RISK.items():
        assert klass in VALID_CLASSES, f"{tool}: classe inválida {klass!r}"

def test_toda_tool_esta_classificada():
    declared = _declared_tools()
    faltando = sorted(declared - set(TOOL_RISK))
    assert not faltando, f"tools sem classe no manifesto (fail-closed = 🔴): {faltando}"

def test_manifesto_nao_tem_tool_fantasma():
    declared = _declared_tools()
    fantasma = sorted(set(TOOL_RISK) - declared)
    assert not fantasma, f"manifesto classifica tools que não existem em server.py: {fantasma}"

def test_tools_include_so_expostas():
    inc = set(tools_include())
    assert inc == {t for t, k in TOOL_RISK.items() if k in {"read", "write_low", "propose"}}
    assert inc == set(TOOL_RISK), "nenhuma classe 🔴 deve existir no manifesto de tools expostas"

if __name__ == "__main__":  # standalone, sem pytest (não instalado no container/host)
    import sys, traceback
    _fns = [test_classes_sao_validas, test_toda_tool_esta_classificada,
            test_manifesto_nao_tem_tool_fantasma, test_tools_include_so_expostas]
    _fail = 0
    for fn in _fns:
        try:
            fn(); print(f"PASS {fn.__name__}")
        except Exception:
            _fail += 1; print(f"FAIL {fn.__name__}"); traceback.print_exc()
    sys.exit(1 if _fail else 0)
