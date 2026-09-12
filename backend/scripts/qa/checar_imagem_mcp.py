#!/usr/bin/env python3
"""A imagem do MCP tem o código que está no disco? E os conectores rodam essa imagem?

Existe `checar_bake_pendente.py` para o backend e NADA equivalente para o `mcp-server/` —
e o preço apareceu em 11/09/2026. Um `docker build` falhou (um teste de build fazia chamada
HTTP e no build não há backend), a tag `conecta-pro-mcp:latest` continuou apontando para a
imagem anterior, e o meu conferidor comparou os 4 containers com a tag: **4/4 ✅**. Estava
certo e não queria dizer o que eu li.

⭐ **CONCORDÂNCIA NÃO É ATUALIDADE.** Comparar containers com a tag responde "eles concordam
entre si?". Não responde "eles têm o código de hoje?". Com a build quebrada os quatro
concordavam perfeitamente sobre a versão errada, e o verde era sobre o consenso, não sobre
o conteúdo. Por isso esta trava compara **conteúdo do disco × conteúdo da imagem** — e só
então imagem × containers.

⭐ E compara nas DUAS direções, por sugestão do `conecta-pro-d4`, cuja trava de escopo tinha
o mesmo defeito: olhar só `disco → imagem` acha arquivo novo que não foi assado, e perde
arquivo que EXISTE na imagem e sumiu do disco — que é o que uma imagem parada produz.

    python3 backend/scripts/qa/checar_imagem_mcp.py
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path("/opt/conecta-pro")
FONTE = RAIZ / "mcp-server"
TAG = "conecta-pro-mcp:latest"
CONECTORES = ("conecta-pro-mcp", "conecta-pro-mcp-internal",
              "conecta-pro-mcp-ged", "conecta-pro-mcp-pessoas")
# o que a imagem carrega e muda comportamento. `changelog.json` entra: `changelog_mcp()` lê
# dele, e um changelog velho dentro da imagem mente com a chancela de uma ferramenta.
# ⭐ 12/09/2026 — DERIVADO do Dockerfile, não escolhido de memória. A lista à mão tinha 6
# nomes e deixava fora `carimbo.py` — o middleware que carimba o `request_id` em TODA
# resposta e escreve o log de acesso LGPD. Um `carimbo.py` velho dentro da imagem passaria
# invisível por esta própria trava, que existe justamente para não deixar código velho
# rodando com a chancela de "imagem em dia".
#
# Mesma falha de desenho das outras deste dia: a régua media o subconjunto que eu lembrava,
# e o Dockerfile é a lista de verdade — quem decide o que entra na imagem é ele.
def _alvos_do_dockerfile() -> tuple[str, ...]:
    dockerfile = (FONTE / "Dockerfile").read_text()
    nomes = re.findall(r"^COPY\s+([\w.\-]+\.(?:py|json))\s", dockerfile, re.M)
    # os testes acompanham a imagem mas não mudam o comportamento servido; o que importa
    # aqui é código e dado que a execução lê.
    return tuple(n for n in dict.fromkeys(nomes)
                 if not n.startswith("test_") and n != "requirements.txt")


ALVOS = _alvos_do_dockerfile()


def _sh(cmd: list[str], timeout: int = 120) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, check=False,  # noqa: S603
                       timeout=timeout)
    return r.stdout if r.returncode == 0 else ""


def _sha_disco(nome: str) -> str | None:
    f = FONTE / nome
    if not f.exists():
        return None
    return hashlib.sha256(f.read_bytes()).hexdigest()[:16]


def _shas_na_imagem() -> dict[str, str] | None:
    """sha de cada alvo DENTRO da imagem — não do container, que tem camada gravável.

    O `docker cp` de outra sessão apareceria como igual se eu medisse o container; a imagem
    é o que um container novo recebe, e é o que sobrevive a um restart.
    """
    lista = " ".join(f"/app/{n}" for n in ALVOS)
    saida = _sh(["docker", "run", "--rm", "--entrypoint", "sh", TAG, "-c",
                 f"for f in {lista}; do [ -f $f ] && "
                 f"echo \"$(basename $f) $(sha256sum $f | cut -c1-16)\"; done"])
    if not saida.strip():
        return None
    fora = {}
    for linha in saida.splitlines():
        partes = linha.split()
        if len(partes) == 2:
            fora[partes[0]] = partes[1]
    return fora


def main() -> int:
    if not FONTE.exists():
        print("NÃO VERIFICADO: mcp-server/ não existe no disco.")
        return 0
    na_imagem = _shas_na_imagem()
    if na_imagem is None:
        # não conseguir medir é motivo para RECUSAR, nunca para liberar
        print(f"  não consegui ler {TAG} — a imagem existe? `docker images {TAG}`")
        print("FAIL checar_imagem_mcp")
        return 1

    problemas: list[str] = []
    for nome in ALVOS:
        disco, img = _sha_disco(nome), na_imagem.get(nome)
        if disco is None and img is None:
            continue
        if disco is None:
            problemas.append(f"{nome}: existe NA IMAGEM e sumiu do disco "
                             f"(imagem parada, ou o arquivo foi apagado sem reassar)")
        elif img is None:
            problemas.append(f"{nome}: existe no disco e NÃO ESTÁ na imagem — nunca foi assado")
        elif disco != img:
            problemas.append(f"{nome}: disco {disco} × imagem {img} — build pendente")

    criada = (_sh(["docker", "inspect", "-f", "{{.Created}}", TAG]) or "?")[:19]
    img_id = (_sh(["docker", "inspect", "-f", "{{.Id}}", TAG]) or "")[7:19]

    desalinhados = []
    for c in CONECTORES:
        atual = (_sh(["docker", "inspect", "-f", "{{.Image}}", c]) or "")[7:19]
        if not atual:
            continue  # container não existe nesta máquina; não é achado desta trava
        if atual != img_id:
            desalinhados.append(f"{c}: roda {atual}, a tag é {img_id}")

    print(f"  imagem {img_id} criada em {criada}")
    for p in problemas:
        print(f"  📦 {p}")
    for d in desalinhados:
        print(f"  🔀 {d}")

    if problemas:
        print("  A imagem NÃO tem o código do disco. Container concordar com container não "
              "prova nada — eles concordariam sobre a versão errada.")
    if problemas or desalinhados:
        print(f"TOTAL arquivos fora da imagem: {len(problemas)} · "
              f"conectores desalinhados: {len(desalinhados)}")
        print("FAIL checar_imagem_mcp")
        return 1
    print(f"OK imagem em dia com o disco ({len(ALVOS)} arquivos) e "
          f"{len(CONECTORES)} conectores nela")
    return 0


if __name__ == "__main__":
    sys.exit(main())
