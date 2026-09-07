#!/usr/bin/env bash
# Nó de saída das CNDs (macOS/Linux). Deixe rodando; reconecta sozinho.
while true; do
  echo "[$(date '+%F %T')] abrindo túnel para a VPS..."
  ssh -N -R 127.0.0.1:1080 -i "$HOME/.ssh/no_saida_cnd" -o IdentitiesOnly=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=accept-new cndtunnel@82.25.75.74
  echo "[$(date '+%F %T')] túnel caiu, reconectando em 20 s..."; sleep 20
done
