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

# ---- clone PINADO na tag (== v0.19.0 interna). --depth 1 + tag = detached,
#      sem tracking branch => `hermes update` nao tem para onde puxar. ----
# 18/09/2026 — de v2026.7.20 (0.19.0) para v2026.9.14 (0.21.3). Doze releases.
# Motivos, em ordem de peso:
#   1. v2026.8.31 traz RESPOSTA A COMPROMETIMENTO DE CADEIA DE SUPRIMENTOS (entrada de
#      catalogo MCP e skill do Blender removidas apos comprometimento upstream). Ficar atras
#      de correcao de seguranca num agente que fala com o ERP nao se justifica.
#   2. v2026.9.11 e "The state.db Patch Release" — corrige o proprio banco de estado que
#      acabamos de por em volume.
#   3. >= 0.21 tem a decomposicao de setembro: os chamadores resolvem
#      `build_skills_system_prompt` por `agent.prompt_builder`, e a ADAPTACAO DA CASA no
#      plugin skill-retrieval deixa de ser necessaria — ela SAI junto com este upgrade.
# Rollback: `conecta-pro-hermes:v0.19.0-rollback` (imagem 998672a936fa) e o volume salvo em
# .backup_hermes/volume_antes_upgrade_*.tgz.
ARG HERMES_TAG=v2026.9.14
RUN git clone --depth 1 --branch "${HERMES_TAG}" \
        https://github.com/NousResearch/hermes-agent.git /app

WORKDIR /app

# ---- deps Python: core + extra `mcp` (cliente MCP mora no extra [mcp];
#      openai/fastapi/uvicorn ja sao core) + extra `sms` (traz SO o aiohttp
#      ==3.14.1 patched-CVE, exigido pelo adapter da plataforma `api_server`
#      OpenAI-compat em gateway/platforms/api_server.py; sem ele o gateway sobe
#      mas NAO expoe :8642 -> "API Server: aiohttp not installed").
#      --locked = hashes da uv.lock verificados (rejeita transitive adulterada).
#      venv em /app/venv. ----
ENV UV_PROJECT_ENVIRONMENT=/app/venv \
    UV_NO_CONFIG=1
RUN uv sync --extra mcp --extra sms --locked

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
