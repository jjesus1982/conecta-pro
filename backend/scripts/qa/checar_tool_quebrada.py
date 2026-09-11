#!/usr/bin/env python3
"""Ferramenta do MCP que QUEBRA ao ser chamada — provado chamando, não lendo.

Origem (11/09/2026): `justificativas_ponto_pendentes` existia, estava no catálogo, tinha
docstring e etiqueta de risco — e **falhava para qualquer cliente MCP**. A rota do ERP devolve
uma LISTA, a anotação dizia `-> dict`, e o FastMCP confere a anotação em tempo de execução:

    Error calling tool 'justificativas_ponto_pendentes': structured_content must be a dict
    or None. Got list: [...]

Ninguém tinha visto porque nada a chamava. Apareceu no primeiro uso real — o Hermes indo olhar
a fila do DP. É a mesma família do "código desligado" que o arsenal já caça em rota e em beat,
só que na camada do agente: **existir no catálogo não é funcionar**.

Esta trava chama de verdade cada ferramenta de LEITURA sem argumento obrigatório e reporta as
que estouram. Só `read` e só sem argumento: escrita não se testa em produção, e ferramenta que
exige parâmetro precisaria de dado inventado — que é o contrário do que esta casa faz.

    python3 backend/scripts/qa/checar_tool_quebrada.py [container]

Linha canônica: `TOTAL tools que quebram ao chamar: N` (binária: N = 0).
"""
from __future__ import annotations

import json
import subprocess
import sys

PADRAO = "conecta-pro-mcp-pessoas"

_PROVA = r'''
import json, os, urllib.request
B = os.environ["MCP_AUTH_TOKEN"]; URL = "http://127.0.0.1:8788/mcp"
sid = None
def call(p):
    global sid
    h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
         "Authorization": "Bearer " + B}
    if sid: h["Mcp-Session-Id"] = sid
    r = urllib.request.urlopen(urllib.request.Request(URL, data=json.dumps(p).encode(), headers=h), timeout=90)
    sid = r.headers.get("Mcp-Session-Id") or sid
    t = r.read().decode()
    for l in t.splitlines():
        if l.startswith("data: "): return json.loads(l[6:])
    return json.loads(t) if t.strip() else {}
call({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"trava","version":"1"}}})
urllib.request.urlopen(urllib.request.Request(URL, data=json.dumps({"jsonrpc":"2.0","method":"notifications/initialized"}).encode(),
    headers={"Content-Type":"application/json","Accept":"application/json, text/event-stream","Authorization":"Bearer "+B,"Mcp-Session-Id":sid}), timeout=30)
tools = call({"jsonrpc":"2.0","id":2,"method":"tools/list"})["result"]["tools"]
import sys as _s; _s.path.insert(0, "/app")
from tool_risk_manifest import TOOL_RISK
saida = []
for i, t in enumerate(tools):
    nome = t["name"]
    if TOOL_RISK.get(nome) != "read":
        continue
    obrig = ((t.get("inputSchema") or {}).get("required")) or []
    if obrig:
        continue
    r = call({"jsonrpc":"2.0","id":100+i,"method":"tools/call","params":{"name":nome,"arguments":{}}})
    res = r.get("result") or {}
    texto = ""
    for c in (res.get("content") or []):
        texto += str(c.get("text") or "")
    if res.get("isError") or texto.startswith("Error calling tool"):
        # ⛔ é RECUSA DE PAREDE (identidade ou gate de aprovação), não defeito: a ferramenta
        # funciona e a trava fez o trabalho dela. Contar isso como quebra transformaria as
        # duas defesas da casa em 51 falsos vermelhos — e caçador que grita sem motivo é o
        # caçador que ninguém lê.
        classe = "parede" if texto.lstrip().startswith("⛔") else (
            "lenta" if "timed out" in texto.lower() else "quebrada")
        saida.append({"tool": nome, "classe": classe, "erro": texto[:200]})
print("RESULTADO " + json.dumps(saida, ensure_ascii=False))
'''


def main() -> int:
    container = sys.argv[1] if len(sys.argv) > 1 else PADRAO
    bearer = subprocess.run(  # noqa: S603
        ["/usr/bin/docker", "exec", container, "sh", "-c", "echo $MCP_AUTH_TOKEN"],
        capture_output=True, text=True, timeout=60).stdout.strip()
    if not bearer:
        print(f"ERRO: não consegui o bearer de {container} — trava não rodou (isto não é verde)")
        return 2
    r = subprocess.run(  # noqa: S603
        ["/usr/bin/docker", "exec", "-e", f"MCP_AUTH_TOKEN={bearer}", "-i", container, "python3", "-"],
        input=_PROVA, capture_output=True, text=True, timeout=600)
    linha = next((l for l in r.stdout.splitlines() if l.startswith("RESULTADO ")), "")
    if not linha:
        print(f"ERRO: a prova não devolveu resultado — {(r.stderr or '').strip()[-300:]}")
        return 2
    achados = json.loads(linha[len("RESULTADO "):])
    quebradas = [a for a in achados if a["classe"] == "quebrada"]
    for q in quebradas:
        print(f"  {q['tool']}: {q['erro']}")
    for a in achados:
        if a["classe"] == "lenta":
            print(f"  (lenta, não respondeu no tempo da prova: {a['tool']})")
    barradas = sum(1 for a in achados if a["classe"] == "parede")
    if barradas:
        print(f"  ({barradas} barradas pela parede — comportamento esperado, não é defeito)")
    print(f"TOTAL tools que quebram ao chamar: {len(quebradas)}")
    return 1 if quebradas else 0


if __name__ == "__main__":
    sys.exit(main())
