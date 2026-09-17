#!/usr/bin/env python3
"""Roda as suítes de RUNTIME do MCP — CP-MCP-011 ("rodar a cada mudança em mcp-server/").

Há duas famílias de teste no conector, e elas rodam em lugares diferentes de propósito:

  · BUILD (`checar_etiqueta_de_risco.py`) — estruturais, dentro do `docker build`. Não podem
    tocar a rede: no build não existe backend. Aprendi isso derrubando o build em 11/09,
    quando pus um teste de timeout que fazia chamada HTTP real;
  · RUNTIME (esta trava) — `test_aceites_cowork.py`, os 21 aceites do prompt. Exige o ERP
    no ar e o sandbox de pé, e por isso roda AQUI, não no build.

O `test_regressao_mcp.py` (os 11 casos do spec CP-MCP-011) NÃO está mais aqui: o
`checar_etiqueta_de_risco` o pega pelo glob de `mcp-server/test_*.py`, e ele é o único que
ESCREVE — o R07 cria um contrato no sandbox a cada execução, de propósito, porque é o caso
que prova o isolamento. Rodar nos dois lugares dobrava essa escrita e fazia o mesmo vermelho
tocar duas vezes. Se o sandbox ficar grande demais, `scripts/refrescar_sandbox.sh` o recria.

    python3 backend/scripts/qa/checar_regressao_mcp.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

CONTAINER = "conecta-pro-mcp"
DOCKER = "/usr/bin/docker"  # nosec B607 — ruff S607 recusa executável parcial
FONTE = Path("/opt/conecta-pro/mcp-server")
# 17/09/2026: `test_regressao_mcp.py` SAIU daqui. O `checar_etiqueta_de_risco` varre
# `mcp-server/test_*.py` por glob e já o roda; mantê-lo nos dois fazia a suíte que ESCREVE no
# sandbox (R07 cria um contrato a cada execução) rodar duas vezes por noite, e o mesmo
# vermelho tocar duas vezes. Aqui fica só o que ninguém mais roda — é o `_FORA` de lá.
SUITES = ("test_aceites_cowork.py",)


def _rodar(arquivo: str) -> tuple[bool, str]:
    origem = FONTE / arquivo
    if not origem.exists():
        return False, f"{arquivo} não existe no disco"
    # copia a versão do DISCO: medir a da imagem responderia "o que foi assado", e a
    # pergunta aqui é "o código de agora passa?".
    cp = subprocess.run(  # noqa: S603
        [DOCKER, "cp", str(origem), f"{CONTAINER}:/app/{arquivo}"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if cp.returncode != 0:
        return False, f"não consegui copiar para o container: {cp.stderr.strip()[:120]}"
    r = subprocess.run(  # noqa: S603
        [DOCKER, "exec", "-w", "/app", CONTAINER, "python3", arquivo],
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )
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
                [DOCKER, "exec", "-w", "/app", CONTAINER, "python3", arquivo],
                capture_output=True,
                text=True,
                check=False,
                timeout=600,
            )
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
