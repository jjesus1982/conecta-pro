# ============================================================================
# Conecta PRO — Hermes Agent runtime (Fase 5.2a)
# ----------------------------------------------------------------------------
# Orquestrador autonomo (NousResearch Hermes Agent, MIT) que fala com o
# conector MCP do ERP (conecta-pro-mcp) e com a OpenAI. Imagem self-contained:
# deps BAKED via `uv sync --locked` (hash-verified pela uv.lock). NAO roda o
# install.sh (ele muta o host via apt). Checkout PINADO na tag v2026.8.16
# (== versao interna 0.20.2) — auto-update desligado.
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

# ---- clone PINADO na tag (== v0.20.2 interna). --depth 1 + tag = detached,
#      sem tracking branch => `hermes update` nao tem para onde puxar. ----
# 18/09/2026 — de v2026.7.20 (0.19.0) para v2026.8.16 (0.20.2).
#
# ⛔ O TETO E O CLIENTE MCP, e ele foi MEDIDO, nao deduzido. Construi a v2026.9.14 (0.21.3),
#    subi num container isolado com copia do estado, e os conectores PARARAM DE SERVIR
#    FERRAMENTAS: so expunham get_prompt/list_prompts/list_resources/read_resource, e
#    `ponto_dashboard` sumiu do catalogo — a triagem de ponto e a auditoria de kit nao
#    funcionariam. O sinal que me fez conferir foi o custo cair DEMAIS (15.843 tokens):
#    estava barato porque nao havia ferramenta nenhuma.
#    Causa: 0.21.x traz `mcp==2.0.0`; a 0.19/0.20.2 trazem `mcp` 1.x, e os nossos tres
#    conectores rodam fastmcp 4.0.4, que nao serve tools ao cliente 2.0.
#    Fronteira exata: v2026.8.16 (0.20.2) = mcp 1.28.1 · v2026.8.19 (0.20.5) em diante = 2.0.0.
#    Subir alem disto exige atualizar o fastmcp de `mcp-server/` e revalidar as paredes de
#    escopo e identidade. Projeto separado.
#
# O que esta versao ganha: um mes de correcoes, satisfaz o `>=0.20.0` do plugin
# skill-retrieval, e 21.809 tokens de entrada por turno contra 25.455 na 0.19 (−14%), com as
# 99 ferramentas MCP intactas (conecta 8 · ged 46 · pessoas 45) e o `ponto_dashboard`
# devolvendo dado real.
#
# A correcao de cadeia de suprimentos da v2026.8.31 fica de fora, e conferi que ela NAO nos
# alcanca: era a entrada de catalogo e a skill do BLENDER, que nao existem nesta instalacao.
#
# Rollback: `conecta-pro-hermes:v0.19.0-rollback` (imagem 998672a936fa) e o volume salvo em
# .backup_hermes/volume_antes_upgrade_*.tgz. Voltando para a 0.19, a ADAPTACAO DA CASA do
# plugin continua correta (ela e condicional a versao, < 0.21).
ARG HERMES_TAG=v2026.8.16
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
