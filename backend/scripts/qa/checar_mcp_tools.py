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
        "MCP_IDENTIDADE": None,
        "MCP_AGENTE_NOME": None,
        "porque": "Cowork do Jordan: pessoa lê e decide na hora. Sem escopo (vê tudo) e sem "
                  "parede (pôr gate aqui viraria decisão informada em fila).",
    },
    "conecta-pro-mcp-internal": {
        "compose": "docker-compose.yml",
        "MCP_ESCOPO": "comercial,juridico,financeiro",
        "MCP_MODO": "agente",
        "MCP_IDENTIDADE": None,
        "MCP_AGENTE_NOME": None,
        "porque": "Conector do AGENTE: escopo corta por assunto e a parede F1 barra `propose`. "
                  "Sem identidade própria: exige o `x-usuario-token` de QUEM perguntou.",
    },
    # 10/09/2026 — conector do KIT. Existe separado do irmão porque o `mcp-internal` roda
    # MCP_MODO=agente, que exige `x-usuario-token` por chamada, e o Hermes só manda header
    # ESTÁTICO por conexão: sob aquele modo ele fica com 6 ferramentas de 146.
    "conecta-pro-mcp-ged": {
        "compose": "docker-compose.yml",
        "MCP_ESCOPO": "ged,fiscal",
        "MCP_MODO": "agente",
        "MCP_IDENTIDADE": "propria",
        "MCP_AGENTE_NOME": "hermes-ged",
        "porque": "GANHOU PAREDE em 12/09/2026, por decisão do Jordan. Nasceu sem, com "
                  "justificativa honesta (no fechamento do kit não há terceiro sobre quem "
                  "responder) e uma premissa que envelheceu: o compose dizia 13 ferramentas de "
                  "leitura e o conector servia 42, cinco fora de leitura — `excluir_documento`, "
                  "`montar_kit_completo` e `buscar_documento` executavam sem aprovação. As duas "
                  "linhas andam juntas: MCP_MODO sozinho exigiria `x-usuario-token` nas 42 (o "
                  "default de `sensivel()` cobre leitura também) e o Hermes só manda header "
                  "estático — o conector morreria inteiro. Com identidade própria, as 37 leituras "
                  "seguem e as 3 `propose` viram pedido na Central.",
    },
    # ⭐ 11/09/2026 — conector de PESSOAS, o do Hermes (triagem diária do ponto).
    "conecta-pro-mcp-pessoas": {
        "compose": "docker-compose.yml",
        "MCP_ESCOPO": "pessoas",
        "MCP_MODO": "agente",
        "MCP_IDENTIDADE": "propria",
        "MCP_AGENTE_NOME": "hermes",
        "porque": "O assunto é o TRABALHO da pessoa (ponto, escala, posto, ocorrência, "
                  "comunicado) — 41 ferramentas. Fora do escopo por construção: fechar folha, "
                  "holerite, rescisão, fechar o mês, férias, CRM, PIX, nota. As DUAS paredes "
                  "andam juntas: identidade própria dá dono à pergunta sem exigir JWT humano, e "
                  "MCP_MODO=agente mantém o gate_propose ativo (revisar_justificativa_ponto, "
                  "propor_comunicado e enviar_whatsapp viram PEDIDO na Central e não executam). "
                  "O `identidade.py` recusa subir com identidade própria e modo desligado — mas "
                  "identidade própria virar ausente NÃO dá erro: cai para 6 ferramentas e o "
                  "Hermes emudece sem ninguém saber por quê. É por isso que as quatro chaves "
                  "são medidas aqui, e não só ESCOPO e MODO.",
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
        #
        # ⚠️ `.split()[0]` sem guarda estourava IndexError e a trava INTEIRA morria aqui
        # (medido 12/09/2026): quando o container roda uma imagem que já não existe mais no
        # daemon — outra sessão reconstruiu a tag e a camada antiga foi recolhida — o
        # `docker run` falha, a saída vem vazia, e a checagem que deveria denunciar o pior
        # estado possível não denunciava NADA. Estado sem nome é estado que não se mede.
        bruto = _sh("docker", "run", "--rm", "--entrypoint", "sh", img,
                    "-c", f"sha256sum {dentro} 2>/dev/null || echo AUSENTE").split()
        if not bruto:
            erros.append(f"{rel}: a imagem que {container} está RODANDO não existe mais no "
                         f"daemon ({img[:19]}…) — a tag foi reconstruída e o container não foi "
                         f"recriado. Não dá para saber o que está servindo; recrie o container.")
            continue
        na_imagem = bruto[0]
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
        # As quatro, não duas: IDENTIDADE e AGENTE_NOME também são parede — sem elas o
        # Hermes perde 135 das 146 ferramentas em silêncio, ou age sem dono declarado.
        for chave in ("MCP_ESCOPO", "MCP_MODO", "MCP_IDENTIDADE", "MCP_AGENTE_NOME"):
            real = env.get(chave) or None
            if real != d.get(chave):
                erros.append(
                    f"{nome}: {chave} é {real!r}, declarado {d.get(chave)!r}. "
                    + (f"Se a mudança é intencional, mude a DECLARAÇÃO junto. ({d['porque']})"))
    return erros


# ── 7. conector SEM PAREDE só pode servir LEITURA ─────────────────────────────────────
def sem_parede_so_le() -> list[str]:
    """`MCP_MODO` ausente = sem `gate_propose`: o que é `propose` EXECUTA em vez de virar pedido.

    Por que esta checagem existe (12/09/2026). O `mcp-ged` nasceu sem parede com uma justificativa
    honesta — no fechamento do kit não há terceiro sobre quem responder — e uma premissa: escopo
    pequeno, só leitura de `ged`/`fiscal`. O comentário no compose diz "13 ferramentas". Medido
    hoje: **42**, e entre elas `excluir_documento` e `montar_kit_completo`, ambas classificadas
    `propose` no manifesto. Num conector COM parede, `propose` para na Central de Aprovações;
    aqui ela roda direto, sem aprovação e sem requerente nomeado.

    Ninguém errou de propósito: o escopo `ged,fiscal` cresceu do outro lado, e a decisão de não
    ter parede continuou valendo sozinha. É essa a forma do defeito desta casa — a premissa
    envelhece e a decisão que dependia dela não sabe. Então a premissa passa a ser MEDIDA:
    sem parede, só `read`. Se o dono aceitar a escrita sem aprovação, a saída é declarar aqui
    em EXCECOES_SEM_PAREDE com o nome da ferramenta e o motivo — não apagar a checagem.
    """
    sys.path.insert(0, str(REPO / "mcp-server"))
    try:
        import tool_risk_manifest as manifesto
        import tool_scopes as escopos
    except ImportError as e:
        return [f"não consegui ler escopo/manifesto do mcp-server ({e}) — checagem NÃO feita"]

    #: Ferramenta que o dono aceitou rodar sem aprovação em conector sem parede. Vazio de
    #: propósito: a primeira entrada aqui tem de vir com decisão escrita no commit.
    EXCECOES_SEM_PAREDE: dict[str, str] = {}

    erros: list[str] = []
    for nome, d in DECLARACAO.items():
        if d.get("MCP_MODO") is not None or not d.get("MCP_ESCOPO"):
            continue  # tem parede, ou é o público (que é decisão informada de pessoa)
        servidas: set[str] = set()
        for assunto in str(d["MCP_ESCOPO"]).split(","):
            servidas |= set(escopos.ESCOPOS.get(assunto.strip(), []))
        fora = sorted(t for t in servidas
                      if manifesto.TOOL_RISK.get(t, "read") != "read" and t not in EXCECOES_SEM_PAREDE)
        if fora:
            erros.append(
                f"{nome}: SEM PAREDE (MCP_MODO ausente) e serve {len(servidas)} ferramentas, "
                f"{len(fora)} delas fora de leitura — "
                + ", ".join(f"{t} ({manifesto.TOOL_RISK.get(t)})" for t in fora)
                + ". Sem gate, `propose` EXECUTA em vez de virar pedido na Central. Decida: pôr "
                  "MCP_MODO=agente, estreitar o escopo, ou declarar cada uma em "
                  "EXCECOES_SEM_PAREDE com o motivo.")
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
    ("conector sem parede serve só leitura", sem_parede_so_le),
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
