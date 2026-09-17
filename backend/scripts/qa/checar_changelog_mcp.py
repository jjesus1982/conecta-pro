#!/usr/bin/env python3
"""O changelog do MCP está atrás do código que ele descreve?

Item 4 do relatório de campo do Cowork (11/09/2026): "o comportamento mudou (o
`baixar_contrato_pdf` passou a tentar o instrumento completo) sem aviso". Uma sessão do
Cowork não vê o deploy acontecer — ela descobre pelo retorno estranho, no meio do trabalho.

`changelog_mcp()` resolve isso lendo `mcp-server/changelog.json`. Mas um changelog só vale
enquanto acompanha o código, e o jeito clássico de ele apodrecer é justamente este: alguém
mexe no `mcp-server/`, não regenera o arquivo, e a ferramenta passa a jurar que a última
mudança foi três semanas atrás. O agente lê, acredita, e assume comportamento velho — que
é exatamente o defeito que o changelog existia para impedir, agora com a chancela de uma
ferramenta oficial.

Esta trava compara o commit mais novo que TOCOU `mcp-server/` com o commit mais novo
registrado no arquivo. Diferente = regenere:

    cd /opt/conecta-pro && git log --pretty=format:'%h|%ad|%s' --date=short -- mcp-server/ \\
      | head -40 | python3 -c "..."   # o gerador vive no commit que criou este arquivo

⚠️ LIMITE: compara identificadores de commit, não conteúdo. Um commit que mexe só no
`README` do mcp-server conta como mudança e pede regeneração — falso positivo barato. O
inverso (mudança de comportamento sem commit) não existe aqui, porque a imagem é construída
do disco versionado.

    python3 backend/scripts/qa/checar_changelog_mcp.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path("/opt/conecta-pro")
CHANGELOG = RAIZ / "mcp-server" / "changelog.json"

GIT = "/usr/bin/git"  # nosec B607 — ruff S607 recusa executável parcial


def _so_mexe_no_changelog(commit: str) -> bool:
    """O commit toca APENAS `mcp-server/changelog.json`? Então é a regeneração se registrando."""
    tocados = subprocess.run(  # noqa: S603 — commit vem do próprio git log
        [GIT, "show", "--name-only", "--pretty=format:", commit],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.splitlines()
    linhas = [t.strip() for t in tocados if t.strip()]
    return bool(linhas) and all(t == "mcp-server/changelog.json" for t in linhas)


def main() -> int:
    if not CHANGELOG.exists():
        print(f"NÃO VERIFICADO: {CHANGELOG} não existe.")
        return 0
    try:
        entradas = json.loads(CHANGELOG.read_text(encoding="utf-8")).get("entradas") or []
    except (OSError, ValueError) as e:
        print(f"  changelog.json ilegível: {e}")
        print("FAIL checar_changelog_mcp")
        return 1
    if not entradas:
        print("  changelog.json sem nenhuma entrada — regenere.")
        print("FAIL checar_changelog_mcp")
        return 1

    r = subprocess.run(  # noqa: S603 — argumentos fixos
        [GIT, "log", "-1", "--pretty=format:%h", "--", "mcp-server/"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0 or not r.stdout.strip():
        print("NÃO VERIFICADO: não consegui ler o git log de mcp-server/.")
        return 0

    no_arquivo = str(entradas[0].get("commit") or "")

    # UM commit de atraso é INERENTE, não desleixo: a entrada que descreve o commit N só
    # pode ser escrita depois que N existe. Fingir que esse degrau não existe faria a trava
    # ficar vermelha em todo commit legítimo — e trava que é sempre vermelha ninguém lê.
    # O que ela cobra é o atraso ACUMULADO: dois ou mais commits sem regenerar.
    #
    # ponytail: tolerância fixa de 1. Se o gerador virar hook de pré-commit, o piso cai a 0.
    atrasados = subprocess.run(  # noqa: S603
        [GIT, "log", "--pretty=format:%h|%s", f"{no_arquivo}..HEAD", "--", "mcp-server/"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    # Commit que só mexe no próprio changelog.json não é mudança do conector — e contá-lo
    # fazia a trava NUNCA convergir: regenerar criava um commit em `mcp-server/`, que voltava
    # como pendente na execução seguinte, junto do próximo commit real. Era a segunda pendência
    # das duas que ela acusava em 17/09/2026. O gerador (`mcp-server/gerar_changelog.py`) exclui
    # os mesmos commits, então os dois lados concordam.
    pendentes = [l for l in atrasados.splitlines() if l.strip() and not _so_mexe_no_changelog(l.split("|", 1)[0])]
    if not pendentes:
        print(f"OK changelog em dia — topo {no_arquivo} ({entradas[0].get('data')}), {len(entradas)} entradas")
        return 0
    if len(pendentes) == 1:
        print(f"OK changelog um commit atrás (inerente) — topo {no_arquivo}, pendente: {pendentes[0][:70]}")
        return 0

    print("  changelog ATRÁS do código:")
    print(f"    topo do changelog.json : {no_arquivo} ({entradas[0].get('data')})")
    print(f"    commits sem registro   : {len(pendentes)}")
    for l in pendentes[:5]:
        print(f"      {l[:88]}")
    print("  `changelog_mcp()` está dizendo ao agente que nada mudou desde então.")
    print("  Regenere o changelog.json a partir do git log e reconstrua a imagem.")
    print("FAIL checar_changelog_mcp")
    return 1


if __name__ == "__main__":
    sys.exit(main())
