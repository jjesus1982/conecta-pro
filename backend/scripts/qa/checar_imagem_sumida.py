#!/usr/bin/env python3
"""Todo container de produção roda uma imagem que AINDA EXISTE no daemon?

Origem: 19/09/2026. Entre 00:43 e 07:22, `conecta-pro-backend:latest` desapareceu do daemon.
Os 9 containers (backend + 8 workers) seguiram rodando a camada antiga, agora órfã e sem tag
— e `./scripts/checar_drift_workers.sh` reportou **"sem drift: todos os workers rodam a mesma
imagem do backend"**, porque ele compara os containers ENTRE SI. Todos errados juntos passa.

O que isso significa na prática: naquele estado, recriar qualquer um dos 9 containers falharia
por falta de imagem, e ninguém saberia o que estava servindo. Quem acusou foi `checar_mcp_tools`,
e por acidente — ele lê UM arquivo de parede que por acaso mora no backend.

⚠️ A causa continua ABERTA. O prune das 00:43 (`-af --filter until=24h`) NÃO explica: a imagem
tinha 1,7h e o filtro protege o que tem menos de 24h; e `conecta-pro-hermes:v0.19.0-rollback`,
com tag e sem container desde 11/09, sobreviveu a 8 execuções. O daemon usa a image store do
containerd (docker 29.1.3, `io.containerd.snapshotter.v1`), onde a semântica de prune difere da
clássica. Esta trava não descobre o culpado — ela garante que a próxima vez não passe em branco.

Linha canônica: `TOTAL: <n> container(es) rodando imagem que sumiu do daemon`.
"""

from __future__ import annotations

import json
import subprocess
import sys

#: Prefixo dos containers que servem produção. Staging e descartáveis ficam de fora de
#: propósito: imagem de sandbox some o tempo todo e isso não é incidente.
PREFIXO = "conecta-pro-"
FORA = ("staging", "-test", "bake-teste")


def _sh(*cmd: str) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout.strip()  # noqa: S603
    except Exception:  # noqa: BLE001
        return ""


def main() -> int:
    nomes = [
        n
        for n in _sh("docker", "ps", "--format", "{{.Names}}").splitlines()
        if n.startswith(PREFIXO) and not any(f in n for f in FORA)
    ]
    if not nomes:
        print("RECUSO: nenhum container de produção no ar — sem isso a trava não mede nada.")
        return 2

    # ⚠️ 19/09/2026 — DOIS estados, e confundi-los foi meu erro de leitura na manhã de hoje.
    # `docker images -q` NÃO lista imagem sem tag (dangling), então "não aparece na listagem"
    # ≠ "não existe". Provado com imagem descartável: depois de `rmi -f` da única tag, o ID
    # some de `docker images -q --no-trunc` e `docker image inspect <id>` CONTINUA funcionando.
    #
    # Eu tinha rodado `docker images | grep conecta`, não achei a linha do backend e anunciei
    # que a imagem tinha sumido do daemon — ela estava lá, sem tag. A diferença importa:
    #   · SEM TAG  = a tag foi movida ou removida e ninguém recriou o container. É o drift que
    #     o CLAUDE.md manda evitar: recriar traz outro código. Grave, mas recuperável.
    #   · AUSENTE  = a camada foi mesmo recolhida. Aí recriar o container FALHA.
    sem_tag, ausentes = [], []
    for n in nomes:
        bruto = _sh("docker", "inspect", n, "--format", "{{json .Image}}")
        img = json.loads(bruto) if bruto else ""
        if not img:
            continue
        tags = _sh("docker", "image", "inspect", img, "--format", "{{json .RepoTags}}")
        if not tags:
            ausentes.append((n, img))
        elif json.loads(tags) == []:
            sem_tag.append((n, img))

    for n, img in ausentes:
        print(f"  {n}: roda {img[:26]}… AUSENTE do daemon — recriar este container FALHA")
    for n, img in sem_tag:
        print(
            f"  {n}: roda {img[:26]}… presente mas SEM TAG — a tag foi movida e o container "
            "não foi recriado; recriar traz outro código"
        )
    print(f"containers de produção conferidos: {len(nomes)} · sem tag: {len(sem_tag)} · ausentes: {len(ausentes)}")
    print(f"TOTAL: {len(sem_tag) + len(ausentes)} container(es) rodando imagem sem tag ou ausente")
    return 1 if (sem_tag or ausentes) else 0


if __name__ == "__main__":
    sys.exit(main())
