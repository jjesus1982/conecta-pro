#!/usr/bin/env python3
"""10ª trava — a parede do agente está no GIT, na IMAGEM e apontando para rota que existe.

Nasceu de três tropeços do MESMO dia (23/08/2026), que pareciam três defeitos e eram um:

  1. Derrubei os DOIS conectores por ~4 minutos. `docker compose up -d mcp` não subiu nada
     porque o conector público NÃO está no `docker-compose.yml` — vive em
     `mcp-server/docker-compose.mcp.yml`. O `docker rm` já tinha rodado. Serviço sem
     definição no lugar onde procurei.
  2. Esqueci o `COPY` no Dockerfile do MCP DUAS vezes. Na primeira o filtro de escopo nunca
     foi aplicado e o log não disse nada; na segunda o conector nem subiu.
  3. A F1 funcionava e NÃO EXISTIA: os dois arquivos novos estavam fora do git e o controller
     vivia só por `docker cp`, num dia em que o backend foi recriado duas vezes.

É um defeito só: **a peça está no ar sem estar onde deveria estar.** Uma trava, os três casos.

⚠️ O ponto que dá o valor todo: a comparação é contra a **IMAGEM**, não contra o sistema de
arquivos do container. `docker cp` escreve na camada do container e some no próximo
`--force-recreate` — medir o container devolveria VERDE para exatamente a falha nº 3.

    python3 backend/scripts/qa/checar_mcp_tools.py

Roda no HOST (precisa de git, docker e dos caminhos do repositório). Sem dívida aceitável:
ou confere, ou não confere.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path("/opt/conecta-pro")
SERVER = REPO / "mcp-server" / "server.py"
DOCKERFILE = REPO / "mcp-server" / "Dockerfile"

#: O que CADA conector deve ser. Isto aqui é a declaração — não é leitura do mundo, é a
#: intenção contra a qual o mundo é medido. A ausência de `MCP_ESCOPO` no público é uma
#: DECISÃO registrada aqui: sem esta linha, o dia em que alguém exportar MCP_ESCOPO no
#: ambiente errado, o Cowork do Jordan perde ferramentas em silêncio e nada acusa.
DECLARACAO: dict[str, dict] = {
    "conecta-pro-mcp": {
        "compose": "mcp-server/docker-compose.mcp.yml",
        "MCP_ESCOPO": None,
        "MCP_MODO": None,
        "porque": "Cowork do Jordan: pessoa lê e decide na hora. Sem escopo (vê tudo) e sem "
                  "parede (pôr gate aqui viraria decisão informada em fila).",
    },
    "conecta-pro-mcp-internal": {
        "compose": "docker-compose.yml",
        "MCP_ESCOPO": "comercial,juridico,financeiro",
        "MCP_MODO": "agente",
        "porque": "Conector do AGENTE: escopo corta por assunto e a parede F1 barra `propose`.",
    },
}

#: (caminho no repo, container cuja imagem deve contê-lo, caminho dentro da imagem)
#: Peça de parede = código cuja ausência afrouxa uma regra SEM dar erro. É a família inteira:
#: o gate, o filtro de escopo, o manifesto que os alimenta, e a rota que leva o pedido ao
#: humano — esta última no backend, porque a parede do MCP termina lá.
PECAS_DE_PAREDE: list[tuple[str, str, str]] = [
    ("mcp-server/gate_propose.py", "conecta-pro-mcp-internal", "/app/gate_propose.py"),
    ("mcp-server/tool_scopes.py", "conecta-pro-mcp-internal", "/app/tool_scopes.py"),
    ("mcp-server/identidade.py", "conecta-pro-mcp-internal", "/app/identidade.py"),
    ("mcp-server/tool_risk_manifest.py", "conecta-pro-mcp-internal",
     "/app/tool_risk_manifest.py"),
    ("backend/modules/ai/conversation/controllers/agente_aprovacao_controller.py",
     "conecta-pro-backend",
     "/app/modules/ai/conversation/controllers/agente_aprovacao_controller.py"),
]


def _sh(*args: str, timeout: int = 180) -> str:
    r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    return (r.stdout or "").strip()


def _inspect(container: str, fmt: str) -> str:
    return _sh("docker", "inspect", container, "--format", fmt)


# ── 1. todo conector no ar tem definição versionada ───────────────────────────────────
def containers_versionados() -> list[str]:
    erros: list[str] = []
    nomes = [n for n in _sh("docker", "ps", "--format", "{{.Names}}").splitlines()
             if "mcp" in n]
    if not nomes:
        return ["nenhum conector MCP no ar — o agente está sem ferramentas"]

    for nome in nomes:
        d = DECLARACAO.get(nome)
        if d is None:
            erros.append(f"{nome}: está no ar e NÃO tem declaração aqui — se ninguém sabe o "
                         f"que ele deveria ser, ninguém percebe quando muda")
            continue
        compose = REPO / d["compose"]
        if not compose.exists():
            erros.append(f"{nome}: {d['compose']} não existe")
            continue
        if _sh("git", "-C", str(REPO), "ls-files", d["compose"]) == "":
            erros.append(f"{nome}: {d['compose']} NÃO está no git — subir de novo depende da "
                         f"máquina de alguém")
        if nome not in compose.read_text():
            erros.append(f"{nome}: {d['compose']} não define este container_name")

    for nome in DECLARACAO:
        if nome not in nomes:
            erros.append(f"{nome}: declarado e FORA DO AR")
    return erros


# ── 2. peça de parede: no git, sem diff, e DENTRO DA IMAGEM ───────────────────────────
def pecas_no_git_e_na_imagem() -> list[str]:
    erros: list[str] = []
    for rel, container, dentro in PECAS_DE_PAREDE:
        f = REPO / rel
        if not f.exists():
            erros.append(f"{rel}: não existe no disco")
            continue

        if _sh("git", "-C", str(REPO), "ls-files", rel) == "":
            erros.append(f"{rel}: NÃO está no git. Arquivo novo não entra por "
                         f"`git commit -- <arq>`; precisa de `git add {rel}` antes.")
        elif _sh("git", "-C", str(REPO), "diff", "HEAD", "--name-only", "--", rel):
            erros.append(f"{rel}: tem alteração não commitada — a imagem e o git divergem")

        img = _inspect(container, "{{.Image}}")
        if not img:
            erros.append(f"{rel}: container {container} não está no ar")
            continue
        # Contra a IMAGEM, nunca contra o container: `docker cp` vive na camada do container
        # e some no próximo recreate. Foi assim que a F1 pareceu existir.
        na_imagem = _sh("docker", "run", "--rm", "--entrypoint", "sh", img,
                        "-c", f"sha256sum {dentro} 2>/dev/null || echo AUSENTE").split()[0]
        if na_imagem == "AUSENTE":
            erros.append(f"{rel}: AUSENTE na imagem de {container}. Está no ar só por "
                         f"`docker cp` (volátil) ou faltou COPY no Dockerfile.")
        elif na_imagem != hashlib.sha256(f.read_bytes()).hexdigest():
            erros.append(f"{rel}: a imagem de {container} tem uma VERSÃO DIFERENTE — "
                         f"o bake é anterior a esta edição")
    return erros


# ── 3. todo módulo local que o server importa está no COPY ────────────────────────────
def imports_no_dockerfile() -> list[str]:
    """O `COPY` esquecido não dá erro: o `try/except ImportError` engole e o filtro some."""
    if not (SERVER.exists() and DOCKERFILE.exists()):
        return ["mcp-server/server.py ou Dockerfile ausente"]
    copiados = set(re.findall(r"^COPY\s+(\S+)", DOCKERFILE.read_text(), re.M))
    locais = {n for n in re.findall(r"^\s*(?:from|import)\s+([a-z_][a-z0-9_]*)",
                                    SERVER.read_text(), re.M)
              if (SERVER.parent / f"{n}.py").exists()}
    # comparar NOME DE ARQUIVO dos dois lados: `COPY gate_propose.py` × módulo
    # `gate_propose`. A primeira versão comparava módulo com arquivo e acusava as duas peças
    # que ESTÃO no Dockerfile — trava que grita sem motivo é trava que se aprende a ignorar.
    return [f"mcp-server/{n}.py: importado por server.py e SEM COPY no Dockerfile — "
            f"o import falha calado e a regra some"
            for n in sorted(locais) if f"{n}.py" not in copiados]


# ── 4. a imagem no ar é a que foi construída ──────────────────────────────────────────
def imagem_no_ar_e_a_construida() -> list[str]:
    erros: list[str] = []
    for nome in DECLARACAO:
        tag = _inspect(nome, "{{.Config.Image}}")
        rodando = _inspect(nome, "{{.Image}}")
        if not tag or not rodando:
            continue
        atual = _sh("docker", "image", "inspect", tag, "--format", "{{.Id}}")
        if atual and atual != rodando:
            erros.append(f"{nome}: roda uma imagem ANTERIOR à `{tag}` atual — foi construída "
                         f"e não foi recriada; o código novo não está servindo")
    return erros


# ── 5. o ambiente é o declarado ───────────────────────────────────────────────────────
def ambiente_confere() -> list[str]:
    erros: list[str] = []
    for nome, d in DECLARACAO.items():
        bruto = _inspect(nome, "{{json .Config.Env}}")
        if not bruto:
            continue
        env = dict(e.split("=", 1) for e in json.loads(bruto) if "=" in e)
        for chave in ("MCP_ESCOPO", "MCP_MODO"):
            real = env.get(chave) or None
            if real != d[chave]:
                erros.append(
                    f"{nome}: {chave} é {real!r}, declarado {d[chave]!r}. "
                    + (f"Se a mudança é intencional, mude a DECLARAÇÃO junto. ({d['porque']})"))
    return erros


# ── 6. toda tool aponta para rota que existe ──────────────────────────────────────────
def _segmentos(p: str) -> list[str]:
    """Query string fora, e QUALQUER segmento com `{` vira coringa: no server.py o caminho é
    montado com f-string (`/crm/docs{p}`, `/crm/audit?{...}`), e tratar isso como literal
    acusava 4 rotas que existem."""
    return [("*" if "{" in s else s)
            for s in p.split("?")[0].strip("/").split("/") if s]


def tools_apontam_para_rota() -> list[str]:
    """Rota removida no backend não quebra o MCP no arranque — quebra na hora do uso, com
    404 dentro da conversa, que é o pior lugar para descobrir."""
    saida = _sh("docker", "exec", "conecta-pro-backend", "python3", "-c",
                "from main_production import app; import json; "
                "print('<<J>>' + json.dumps(sorted({r.path for r in app.routes})) + '<<J>>')",
                timeout=420)
    m = re.search(r"<<J>>(.*?)<<J>>", saida, re.S)
    if not m:
        return ["não consegui listar as rotas montadas do backend — trava NÃO verificada"]
    rotas = [_segmentos(r[len("/api/v1"):]) for r in json.loads(m.group(1))
             if r.startswith("/api/v1")]

    chamadas = set(re.findall(r'erp\.(?:get|post|put|patch|delete)(?:_bytes)?\(\s*f?"(/[^"]*)"',
                              SERVER.read_text()))
    erros: list[str] = []
    for caminho in sorted(chamadas):
        alvo = _segmentos(re.sub(r"\{[^}]*\}", "{x}", caminho))
        if not alvo:
            continue
        # prefixo: `erp.get("/crm/deals/" + id)` chega aqui como ["crm","deals"]
        casou = any(len(r) >= len(alvo) and all(a in ("*", b) or b == "*"
                                                for a, b in zip(alvo, r[:len(alvo)]))
                    for r in rotas)
        if not casou:
            erros.append(f"server.py chama /api/v1{caminho} e essa rota NÃO está montada")
    return erros


CHECAGENS = [
    ("conector no ar tem definição versionada", containers_versionados),
    ("peça de parede no git E na imagem", pecas_no_git_e_na_imagem),
    ("módulo importado está no COPY", imports_no_dockerfile),
    ("imagem no ar == imagem construída", imagem_no_ar_e_a_construida),
    ("ambiente == declaração", ambiente_confere),
    ("tool aponta para rota existente", tools_apontam_para_rota),
]


def main() -> int:
    total = 0
    for titulo, fn in CHECAGENS:
        try:
            erros = fn()
        except Exception as e:  # noqa: BLE001
            # Trava que morre calada é trava que não existe — a exceção CONTA como falha.
            erros = [f"a checagem estourou ({type(e).__name__}: {str(e)[:120]})"]
        total += len(erros)
        print(f"  {'x' if erros else 'ok'} {titulo}")
        for e in erros:
            print(f"      - {e}")

    if total:
        print(f"\n{total} problema(s). A peça está no ar sem estar onde deveria estar — "
              "é sempre o mesmo defeito, e ele não dá erro sozinho.")
        return 1
    print("\nconfere: a parede está no git, na imagem e apontando para rota que existe")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
