#!/usr/bin/env python3
"""Ferramenta do MCP que ESCREVE e não avisa que escreve.

O consumidor do conector é um agente sem navegador e sem estado entre chamadas. Ele decide
se pode chamar uma ferramenta lendo a DESCRIÇÃO dela — é a única coisa que ele tem. Uma
tool chamada `criar_cliente` cuja descrição não diz que grava parece consulta, e consulta a
gente chama à vontade para explorar.

Medido em 11/09/2026, no relatório de campo do Jordan sobre o Cowork: das 262 ferramentas
com docstring, **8 declaravam** se liam ou escreviam. Havia **44 com nome de verbo de
escrita** (criar_, gerar_, enviar_, assinar_, excluir_…) sem uma palavra sobre gravar.
Entre elas `assinar_contrato_empresa`, `enviar_link_assinatura` e `excluir_*`.

Não é hipótese: no mesmo dia, testando, eu criei um contrato real no sistema do dono duas
vezes, porque a ferramenta não me disse na cara que aquilo ia para o banco dele.

LIMITE: julga pelo NOME do verbo, não pelo que a função faz. Uma tool de escrita batizada
com nome de leitura passa batido — o caçador mede o vocabulário, e o vocabulário é
convenção. Por isso a taxonomia `verbo_entidade` importa: ela é o que torna esta trava
possível.

    python3 backend/scripts/qa/checar_mcp_declara_escrita.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SERVER = Path("/opt/conecta-pro/mcp-server/server.py")

# Verbos que, por convenção desta casa, significam ESCRITA.
VERBOS = ("criar", "cadastr", "atualizar", "gerar", "enviar", "abrir", "assinar",
          "anexar", "vincular", "mover", "excluir", "aprovar", "registrar", "lancar")

_TOOL = re.compile(r'@mcp\.tool\s*\nasync def (\w+)\([^)]*\)[^:]*:\s*\n\s*"""(.*?)"""', re.S)


def achados() -> tuple[list[str], int, int]:
    if not SERVER.exists():
        return [], 0, 0
    tools = _TOOL.findall(SERVER.read_text())
    mudos = []
    escritoras = 0
    for nome, doc in tools:
        if not any(nome.startswith(v) for v in VERBOS):
            continue
        escritoras += 1
        if "ESCREVE" not in doc and "só lê" not in doc.lower() and "Só lê" not in doc:
            mudos.append(nome)
    return mudos, escritoras, len(tools)


def main() -> int:
    mudos, escritoras, total = achados()
    if not total:
        print("NÃO VERIFICADO: não achei o server.py do MCP.")
        return 0
    for n in mudos:
        print(f"  ✍️  {n} — escreve e não declara")
    print(f"\nTOTAL tools de escrita sem declarar: {len(mudos)} "
          f"(de {escritoras} escritoras · {total} tools)")
    if mudos:
        print("Acrescente à docstring: '⚠️ ESCREVE no Conecta PRO — não é consulta.'")
        print("FAIL checar_mcp_declara_escrita")
        return 1
    print("OK checar_mcp_declara_escrita")
    return 0


if __name__ == "__main__":
    sys.exit(main())
