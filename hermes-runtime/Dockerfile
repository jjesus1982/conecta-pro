# ============================================================================
# Conecta PRO — Hermes Agent runtime (Fase 5.2a)
# ----------------------------------------------------------------------------
# Orquestrador autonomo (NousResearch Hermes Agent, MIT) que fala com o
# conector MCP do ERP (conecta-pro-mcp) e com a OpenAI. Imagem self-contained:
# deps BAKED via `uv sync --locked` (hash-verified pela uv.lock). NAO roda o
# install.sh (ele muta o host via apt). Checkout PINADO na tag v2026.9.14
# (== versao interna 0.21.3) — auto-update desligado.
# ============================================================================
FROM python:3.11-slim

# ---- toolchain do sistema (deps do Hermes: git p/ clone, ripgrep p/ busca,
#      ffmpeg p/ TTS, nodejs/npm p/ browser-tool, curl/ca-certificates p/ uv) +
#      build-essential p/ eventuais source-builds (maturin/cffi) do uv sync ----
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        ripgrep \
        ffmpeg \
        nodejs \
        npm \
        ca-certificates \
        curl \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# ---- uv (instalador oficial; binario em /root/.local/bin) ----
RUN curl -fsSL https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

# ---- clone PINADO na tag (== v0.21.3 interna). --depth 1 + tag = detached,
#      sem tracking branch => `hermes update` nao tem para onde puxar. ----
# 18/09/2026 — de v2026.7.20 (0.19.0) para v2026.9.14 (0.21.3). Doze releases, ~2 meses.
#
# ⚠️ O "TETO DO CLIENTE MCP" QUE EU DIAGNOSTIQUEI AQUI NAO EXISTIA. Fica escrito porque o erro
#    custou uma tarde e quase virou um projeto inteiro.
#    Na primeira tentativa a 0.21.3 subiu com os conectores servindo SO 4 verbos genericos
#    (get_prompt/list_prompts/list_resources/read_resource) e `ponto_dashboard` fora do
#    catalogo. Conclui "0.21 traz mcp==2.0.0 e o nosso fastmcp 4.0.4 nao serve tools a esse
#    cliente", parei na 0.20.2 e propus um projeto de upgrade do fastmcp dos tres conectores.
#    ERRADO. Escrevi um cliente com `mcp==2.0.0` apontado para o nosso conector: ele serviu as
#    41 ferramentas normalmente. O protocolo estava certo o tempo todo.
#    A causa era uma linha de CONFIG: a semantica de `tools.include: []` INVERTEU entre as
#    versoes, e o comentario do upstream e explicito —
#      "include: [] -> register nothing (an explicit empty whitelist)".
#    Na 0.19 `if include_set:` tratava lista vazia como falsy e liberava tudo. Os numeros que
#    eu li como "protocolo quebrado" (ged 4, pessoas 4) eram exatamente os 4 verbos genericos.
#    Tirar o bloco `tools:` de `ged` e `pessoas` resolveu: 99 ferramentas na 0.21.3.
#
#    A licao: numero que MELHORA demais merece a mesma desconfianca que numero que piora. O
#    custo caiu para 15.843 tokens e estava barato porque nao havia ferramenta nenhuma.
#
# O que esta versao entrega, medido:
#    prompt_tokens   25.455 (0.19) -> 21.809 (0.20.2) -> 18.552 (0.21.3)
#    ferramentas MCP 99 intactas (conecta 8 · ged 46 · pessoas 45)
#    ponto_dashboard dado real: 64 colaboradores, 17 presentes
#    plugin          o ORIGINAL do autor volta a servir — a adaptacao da casa sai, e na 0.21
#                    ela nao e so desnecessaria: DESLIGA o plugin (import removido em 14/09).
#    v2026.8.31 traz a resposta ao comprometimento de cadeia de suprimentos (Blender), e
#    v2026.9.11 e "The state.db Patch Release" — as duas entram junto.
#
# Rollback: `conecta-pro-hermes:v0.19.0-rollback` e `:v0.20.2`, volumes em
# .backup_hermes/. Voltando para < 0.21, TROQUE tambem o plugin pela variante adaptada
# (`plugins/skill-retrieval/__init__.py.para-hermes-0.19-0.20`) — o cacador
# `checar_hermes_skill_retrieval.py` cobra a variante certa nos dois sentidos.
ARG HERMES_TAG=v2026.9.14
RUN git clone --depth 1 --branch "${HERMES_TAG}" \
        https://github.com/NousResearch/hermes-agent.git /app

WORKDIR /app

# ---- deps Python: core + extra `mcp` (cliente MCP mora no extra [mcp];
#      openai/fastapi/uvicorn ja sao core) + extra `sms` (traz SO o aiohttp
#      ==3.14.1 patched-CVE, exigido pelo adapter da plataforma `api_server`
#      OpenAI-compat em gateway/platforms/api_server.py; sem ele o gateway sobe
#      mas NAO expoe :8642 -> "API Server: aiohttp not installed").
#
#      --frozen (era --locked ate 18/09/2026): instala EXATAMENTE o que a uv.lock
#      fixa, com os hashes dela — a protecao que importa continua de pe. O que ele
#      NAO faz e reexigir que a lock "confira" com o pyproject, e essa exigencia
#      passou a ser impossivel: da v2026.8.16 em diante a lock upstream declara
#      `exclude-newer-span = "P14D"`, um recorte RELATIVO ("nada publicado nos
#      ultimos 14 dias"). Ele anda com o calendario, entao `--locked` reprova
#      sozinho depois de duas semanas — o uv diz
#      "Resolving despite existing lockfile due to removal of global exclude newer".
#      Medido em 18/09/2026: a lock e INCONSISTENTE por esse motivo em v2026.8.16,
#      v2026.8.31, v2026.9.11 e v2026.9.14; so a nossa antiga v2026.7.20 passava,
#      porque e anterior ao recurso.
#      A alternativa seria `uv lock` (regenerar), e essa sim perderia a curadoria:
#      trocaria o conjunto testado pelo upstream pelo que o uv resolvesse hoje.
#      venv em /app/venv. ----
ENV UV_PROJECT_ENVIRONMENT=/app/venv \
    UV_NO_CONFIG=1
RUN uv sync --extra mcp --extra sms --frozen

# ---- HERMES_HOME = /data (config.yaml + SOUL.md + estado). Auto-update OFF. ----
ENV HERMES_HOME=/data \
    PATH="/app/venv/bin:${PATH}" \
    HERMES_NO_UPDATE=1 \
    HERMES_DISABLE_UPDATE_CHECK=1

RUN mkdir -p /data
COPY config.yaml /data/config.yaml
COPY SOUL.md /data/SOUL.md
# memoria persistente semeada com o que esta casa ja decidiu
COPY MEMORY.md /data/MEMORY.md
# skills que o AGENTE escreveu e o Jordan aprovou — memória procedural, versionada no repositório
# junto com o resto. Sem isso, um rebuild devolve um agente que sabe os fatos e esqueceu COMO fazer.
COPY skills/ /data/skills/
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# API OpenAI-compat do gateway
EXPOSE 8642

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
