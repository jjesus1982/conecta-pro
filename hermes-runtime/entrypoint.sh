#!/usr/bin/env bash
# ============================================================================
# Conecta PRO — Hermes Agent entrypoint (Fase 5.2a)
# Sobe o gateway em FOREGROUND com a plataforma API (OpenAI-compat) em :8642.
# `hermes gateway` = modo foreground (hermes_cli: "Run gateway in foreground").
# ============================================================================
set -euo pipefail

# Higiene: evita que um PYTHONPATH herdado sombreie o checkout do Hermes.
unset PYTHONPATH || true
unset PYTHONHOME || true

export HERMES_HOME="${HERMES_HOME:-/data}"

# --- Plataforma API OpenAI-compat (o gateway a expoe quando habilitada) ---
export API_SERVER_ENABLED=true
export API_SERVER_HOST="${API_SERVER_HOST:-0.0.0.0}"
export API_SERVER_PORT="${API_SERVER_PORT:-8642}"
# A chave de auth da API. O guard exige segredo utilizavel (>=16 chars, nao
# placeholder) — passe HERMES_API_KEY forte via -e.
export API_SERVER_KEY="${HERMES_API_KEY:?HERMES_API_KEY obrigatorio (>=16 chars)}"

# Sanidade minima: precisa de chave OpenAI e do Bearer do conector MCP.
: "${OPENAI_API_KEY:?OPENAI_API_KEY obrigatorio}"
: "${MCP_BEARER:?MCP_BEARER obrigatorio (Bearer de entrada do conector)}"

# --- Semear a memoria no lugar que a ferramenta LE ---------------------------
# 10/09/2026: o Dockerfile copiava MEMORY.md para $HERMES_HOME/MEMORY.md, mas o
# `memory_tool.py` le e escreve em $HERMES_HOME/memories/MEMORY.md. Resultado medido:
# desde 23/08 o Hermes rodou com memoria VAZIA — perguntado "o que voce sabe sobre como
# se trabalha aqui" respondeu "VAZIO", com o arquivo semeado intacto um diretorio acima.
# Semeia so quando o destino nao existe ou esta vazio: rebuild nao apaga o que ele aprendeu.
_MEM_DIR="$HERMES_HOME/memories"
_MEM="$_MEM_DIR/MEMORY.md"
mkdir -p "$_MEM_DIR"
if [ ! -s "$_MEM" ] && [ -s "$HERMES_HOME/MEMORY.md" ]; then
    cp "$HERMES_HOME/MEMORY.md" "$_MEM"
    echo "[entrypoint] memoria semeada em $_MEM ($(wc -c < "$_MEM") bytes)"
else
    echo "[entrypoint] memoria ja existe em $_MEM ($(wc -c < "$_MEM" 2>/dev/null || echo 0) bytes) — nao mexo"
fi

echo "[entrypoint] HERMES_HOME=$HERMES_HOME  API :$API_SERVER_PORT  gateway=foreground"
exec hermes gateway
