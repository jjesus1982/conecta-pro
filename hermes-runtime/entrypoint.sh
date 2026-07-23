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

echo "[entrypoint] HERMES_HOME=$HERMES_HOME  API :$API_SERVER_PORT  gateway=foreground"
exec hermes gateway
