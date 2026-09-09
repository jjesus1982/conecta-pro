#!/usr/bin/env python3
"""Todo oráculo e caçador do disco está DENTRO do container que os roda? (09/09/2026)

Origem: hoje, três vezes, um arquivo ficou no git e fora da imagem porque o bake fechou o contexto minutos antes.
Com oráculo isso é pior que com código: a varredura da meia-noite roda de DENTRO do container, então um oráculo
que existe só no disco não protege ninguém — e o número que se anuncia ("142 oráculos") vira uma afirmação sobre o
disco, não sobre o que vigia o sistema.

Vale igual para `scripts/qa` (sugestão da sessão t6): o `checar_regressao` chama vários `checar_*` DE DENTRO do
container — um caçador que não subiu não reclama, e a linha de base nem percebe que ele sumiu.

Irmão do `checar_bake_pendente` (que compara o CÓDIGO no ar com a imagem), aplicado ao INSTRUMENTO DE MEDIÇÃO.
Roda no host. Linha canônica: `TOTAL instrumentos fora do container: N` (binária: N = 0).
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
ORQ = os.path.join(ROOT, "backend", "scripts", "orq")
CONTAINER = "conecta-pro-backend"


#: (pasta, prefixo exigido, o que é) — `_`-prefixados são fixture/apoio, não instrumento.
ALVOS = (("scripts/orq", "test_", "oráculo"), ("scripts/qa", "checar_", "caçador"))
#: plural correto no relato (caçador → caçadores)
_PLURAL = {"oráculo": "oráculos", "caçador": "caçadores"}


def _no_container(sub: str) -> set[str] | None:
    out = subprocess.run(  # noqa: S603 — comando fixo, sem entrada do usuário
        ["/usr/bin/docker", "exec", CONTAINER, "sh", "-c", f"ls /app/{sub}/*.py 2>/dev/null"],
        capture_output=True, text=True, timeout=120,
    ).stdout
    nomes = {os.path.basename(l.strip()) for l in out.splitlines() if l.strip()}
    # diretório inteiro ausente é OUTRA doença (imagem sem a pasta): não confundir com "faltam arquivos"
    return nomes or None


def main() -> int:
    faltando_total: list[str] = []
    for sub, prefixo, rotulo in ALVOS:
        pasta = os.path.join(ROOT, "backend", *sub.split("/"))
        disco = {f for f in os.listdir(pasta) if f.startswith(prefixo) and f.endswith(".py")}
        dentro = _no_container(sub)
        if dentro is None:
            print(f"ERRO: /app/{sub} não existe (ou está vazia) no container — não é 'faltam arquivos', é a pasta inteira")
            return 2
        dentro = {f for f in dentro if f.startswith(prefixo)}
        faltando = sorted(disco - dentro)
        sobrando = sorted(dentro - disco)
        for f in faltando:
            print(f"  fora do container: {sub}/{f}  — está no disco/git e NÃO roda ({rotulo})")
        for f in sobrando:
            print(f"  fantasma: {sub}/{f}  — roda no container e não existe mais no repositório")
        print(f"{_PLURAL[rotulo]}: {len(disco)} no disco · {len(dentro)} no container")
        faltando_total += faltando + sobrando
    print(f"TOTAL instrumentos fora do container: {len(faltando_total)}")
    return 1 if faltando_total else 0


if __name__ == "__main__":
    sys.exit(main())
