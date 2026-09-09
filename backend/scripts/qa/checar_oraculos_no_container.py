#!/usr/bin/env python3
"""Todo oráculo do disco está DENTRO do container que roda a varredura? (09/09/2026)

Origem: hoje, três vezes, um arquivo ficou no git e fora da imagem porque o bake fechou o contexto minutos antes.
Com oráculo isso é pior que com código: a varredura da meia-noite roda de DENTRO do container, então um oráculo
que existe só no disco não protege ninguém — e o número que se anuncia ("142 oráculos") vira uma afirmação sobre o
disco, não sobre o que vigia o sistema.

Irmão do `checar_bake_pendente` (que compara o CÓDIGO no ar com a imagem), aplicado ao INSTRUMENTO DE MEDIÇÃO.
Roda no host. Linha canônica: `TOTAL oráculos fora do container: N` (binária: N = 0).
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
ORQ = os.path.join(ROOT, "backend", "scripts", "orq")
CONTAINER = "conecta-pro-backend"


def main() -> int:
    disco = {f for f in os.listdir(ORQ) if f.startswith("test_") and f.endswith(".py")}
    out = subprocess.run(  # noqa: S603 — comando fixo, sem entrada do usuário
        ["/usr/bin/docker", "exec", CONTAINER, "sh", "-c", "ls /app/scripts/orq/test_*.py 2>/dev/null"],
        capture_output=True, text=True, timeout=120,
    ).stdout
    dentro = {os.path.basename(l.strip()) for l in out.splitlines() if l.strip()}
    if not dentro:
        print("ERRO: não consegui listar os oráculos no container")
        return 2
    faltando = sorted(disco - dentro)
    sobrando = sorted(dentro - disco)  # oráculo apagado do repo que continua rodando (docker cp não apaga)
    for f in faltando:
        print(f"  fora do container: {f}  — está no disco/git e NÃO roda na varredura")
    for f in sobrando:
        print(f"  fantasma: {f}  — roda na varredura e não existe mais no repositório")
    print(f"oráculos: {len(disco)} no disco · {len(dentro)} no container")
    print(f"TOTAL oráculos fora do container: {len(faltando)}")
    return 1 if (faltando or sobrando) else 0


if __name__ == "__main__":
    sys.exit(main())
