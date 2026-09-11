#!/usr/bin/env python3
"""Roda as suítes de RUNTIME do MCP — CP-MCP-011 ("rodar a cada mudança em mcp-server/").

Há duas famílias de teste no conector, e elas rodam em lugares diferentes de propósito:

  · BUILD (`checar_etiqueta_de_risco.py`) — estruturais, dentro do `docker build`. Não podem
    tocar a rede: no build não existe backend. Aprendi isso derrubando o build em 11/09,
    quando pus um teste de timeout que fazia chamada HTTP real;
  · RUNTIME (esta trava) — `test_aceites_cowork.py` (21 aceites do prompt) e
    `test_regressao_mcp.py` (os 11 casos do spec CP-MCP-011). Exigem o ERP no ar e o
    sandbox de pé, e por isso rodam AQUI, não no build.

⚠️ Elas escrevem — no SANDBOX. R07 cria um contrato lá a cada execução, de propósito: é o
caso que prova o isolamento. Se o sandbox ficar grande demais, `scripts/refrescar_sandbox.sh`
o recria do zero.

    python3 backend/scripts/qa/checar_regressao_mcp.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

CONTAINER = "conecta-pro-mcp"
FONTE = Path("/opt/conecta-pro/mcp-server")
SUITES = ("test_aceites_cowork.py", "test_regressao_mcp.py")


def _rodar(arquivo: str) -> tuple[bool, str]:
    origem = FONTE / arquivo
    if not origem.exists():
        return False, f"{arquivo} não existe no disco"
    # copia a versão do DISCO: medir a da imagem responderia "o que foi assado", e a
    # pergunta aqui é "o código de agora passa?".
    cp = subprocess.run(  # noqa: S603
        ["docker", "cp", str(origem), f"{CONTAINER}:/app/{arquivo}"],
        capture_output=True, text=True, check=False, timeout=60)
    if cp.returncode != 0:
        return False, f"não consegui copiar para o container: {cp.stderr.strip()[:120]}"
    r = subprocess.run(  # noqa: S603
        ["docker", "exec", "-w", "/app", CONTAINER, "python3", arquivo],
        capture_output=True, text=True, check=False, timeout=600)
    saida = (r.stdout or "") + (r.stderr or "")
    ultima = next((ln for ln in reversed(saida.splitlines()) if ln.startswith("TEST ")), "")
    return r.returncode == 0, ultima or saida.strip().splitlines()[-1][:120] if saida.strip() else "sem saída"


def main() -> int:
    falhando = []
    for arquivo in SUITES:
        ok, resumo = _rodar(arquivo)
        print(f"  {'ok  ' if ok else 'FALHA'}: {arquivo} — {resumo}")
        if not ok:
            falhando.append(arquivo)
            # a saída completa importa: o nome do caso que caiu é o que diz onde olhar
            r = subprocess.run(  # noqa: S603
                ["docker", "exec", "-w", "/app", CONTAINER, "python3", arquivo],
                capture_output=True, text=True, check=False, timeout=600)
            for ln in ((r.stdout or "") + (r.stderr or "")).splitlines():
                if "❌" in ln or "💥" in ln or ln.startswith("FAIL "):
                    print(f"      {ln.strip()[:150]}")
    print(f"TOTAL suítes de runtime falhando: {len(falhando)}")
    if falhando:
        print("FAIL checar_regressao_mcp")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
