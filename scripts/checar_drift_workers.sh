#!/usr/bin/env bash
# Detecta DRIFT de código entre o backend e os workers do Celery. READ-ONLY.
#
# POR QUE EXISTE
#   O deploy tem SKIP_CELERY=1, que pula o passo 7/7 e deixa os workers com a imagem
#   anterior. É legítimo quando o diff é só de tela — economiza ~12 min. Mas cada skip
#   acumula: em março/2026 o celery-beat rodou 46 DIAS em loop de crash porque um fix
#   foi para o backend e não para os workers, e "healthy" não denuncia código velho.
#
# COMO DECIDE
#   Compara o SHA da IMAGEM que cada container roda — não o conteúdo dos arquivos.
#   Mesma imagem = mesmo código, sem ambiguidade. `conecta-pro-backend-green` é ignorado:
#   ele só existe durante o blue/green e ter imagem diferente ali é o esperado.
#
# Uso:  ./scripts/checar_drift_workers.sh          (sai 1 se houver drift)
set -uo pipefail

REF_CONTAINER="conecta-pro-backend"
ref=$(docker inspect --format '{{.Image}}' "$REF_CONTAINER" 2>/dev/null) || {
    echo "ERRO: $REF_CONTAINER não está de pé."; exit 2; }

# Um deploy em curso deixa o green com imagem nova por alguns minutos — não é drift.
if pgrep -f "deploy_backend_blue[g]reen.sh" >/dev/null 2>&1; then
    echo "AVISO: deploy em curso — o resultado abaixo é instantâneo e pode mudar."
fi

echo "referência: $REF_CONTAINER  ${ref:7:12}"
echo

drift=0
while read -r c; do
    [ "$c" = "$REF_CONTAINER" ] && continue
    case "$c" in *-green) continue ;; esac          # efêmero do blue/green
    img=$(docker inspect --format '{{.Image}}' "$c" 2>/dev/null)
    up=$(docker ps --filter "name=^${c}$" --format '{{.Status}}')
    if [ "$img" = "$ref" ]; then
        printf "  OK     %-32s %s\n" "$c" "${img:7:12}"
    else
        printf "  DRIFT  %-32s %s   (%s)\n" "$c" "${img:7:12}" "$up"
        drift=$((drift + 1))
    fi
done < <(docker ps --format '{{.Names}}' | grep -E "^conecta-pro-(celery|flower)" | sort)

echo
if [ "$drift" -eq 0 ]; then
    echo "Sem drift: todos os workers rodam a mesma imagem do backend."
    exit 0
fi
echo "$drift worker(s) com código ANTERIOR ao backend."
echo "Corrigir: ./scripts/deploy_backend_bluegreen.sh   (bake completo, sem SKIP_CELERY)"
exit 1
