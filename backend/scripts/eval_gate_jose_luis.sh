#!/usr/bin/env bash
# Gate de evals do José Luís (WhatsApp cliente-facing) — Fase 5.4c/Task 5.
#
# Roda backend/evals/run_evals.py (golden_set.json completo) numa BANCADA
# THROWAWAY: container `docker run --rm` isolado, na mesma rede docker do
# banco vivo (precisa de dados reais — cwi_message_log/crm_followups/proposals
# — mas SEM tocar o backend vivo em :8080/:8081, evitando OOM in-process).
# As execuções de tool são stubadas dentro do próprio run_evals.py (zero
# efeito colateral: não manda WhatsApp real, não grava lead de verdade).
#
# Uso:
#   backend/scripts/eval_gate_jose_luis.sh              # golden_set completo
#   EVAL_JUDGE_MODEL=gpt-5.1 backend/scripts/eval_gate_jose_luis.sh
#
# Sai com código != 0 se QUALQUER caso "critical" reprovar — plugue isto
# ANTES de rebaker/deployar `agent_service.py` (ex.: no início do
# deploy_backend_bluegreen.sh, ou como step manual antes do bake).
#
# Nota sobre flakiness pré-existente do juiz-IA: os cenários raiva/preco/
# cobranca/pressa às vezes reprovam por critério subjetivo do LLM-judge sem
# ser regressão real. Se um "critical" falhar, RE-RODE só aquele cenário
# 2-3x (ver seção "reteste seletivo" abaixo) antes de declarar BLOCKED.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${ENV_FILE:-$REPO_ROOT/.env}"
IMAGE="${EVAL_IMAGE:-conecta-pro-backend:latest}"
NETWORK="${EVAL_NETWORK:-conecta-pro_conecta-pro-network}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERRO: .env não encontrado em $ENV_FILE" >&2
  exit 2
fi

POSTGRES_USER="$(grep -E '^POSTGRES_USER=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
POSTGRES_PASSWORD="$(grep -E '^POSTGRES_PASSWORD=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
POSTGRES_DB="$(grep -E '^POSTGRES_DB=' "$ENV_FILE" | head -1 | cut -d= -f2-)"

echo "== Gate de evals José Luís (bancada throwaway, imagem=$IMAGE) =="

docker run --rm --memory=2g \
  --network "$NETWORK" \
  --env-file "$ENV_FILE" \
  -e "DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER:-postgres}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB:-conecta_pro}" \
  -e PYTHONPATH=/app \
  -e "EVAL_JUDGE_MODEL=${EVAL_JUDGE_MODEL:-gpt-5.1}" \
  "$IMAGE" \
  python evals/run_evals.py
