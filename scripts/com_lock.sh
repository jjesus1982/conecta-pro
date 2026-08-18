#!/bin/bash
# com_lock.sh — roda um comando segurando o LOCK DE DEPLOY.
#
# POR QUE EXISTE
#   O `deploy_backend_bluegreen.sh` já segura o lock durante todo o seu ciclo, INCLUSIVE o
#   build. O buraco era outro: quem constrói a imagem POR FORA do script (um
#   `docker compose build backend` avulso) não passa por lock nenhum. Se isso acontece
#   enquanto o passo 7 recria os workers, a tag `latest` muda no MEIO do laço: os workers já
#   recriados ficam com a imagem anterior — que vira órfã — e o resto pega a nova.
#   Medido duas vezes em 10/08/2026: 2 e depois 4 workers com código velho, todos "healthy".
#
#   Este script fecha esse buraco: qualquer operação que MUDE a imagem do backend passa a
#   esperar o deploy terminar, em vez de atropelá-lo.
#
# USO
#   ./scripts/com_lock.sh docker compose build backend
#   ./scripts/com_lock.sh --espera 1800 ./scripts/qualquer_coisa.sh
#
#   --espera N   segundos a esperar pelo lock (padrão 900). 0 = não espera, falha na hora.
#
# SAÍDAS
#   0   comando rodou (e este é o código de saída DELE)
#   2   lock ocupado além da espera — o comando NÃO rodou
set -u

LOCK=/tmp/conecta_deploy.lock
ESPERA=900

if [ "${1:-}" = "--espera" ]; then
    ESPERA="${2:?--espera exige um número de segundos}"
    shift 2
fi
[ $# -gt 0 ] || { echo "uso: $0 [--espera N] <comando...>" >&2; exit 64; }

quem_segura() {  # descreve o dono atual, para a espera não ser cega
    if [ -f "$LOCK/owner" ]; then
        cat "$LOCK/owner" 2>/dev/null
    else
        echo "desconhecido (lock sem arquivo owner)"
    fi
}

# Mesmo guarda do deploy: o lock é um DIRETÓRIO. Caminho existindo como ARQUIVO não é lock
# desta casa — ninguém o segura e `mkdir` nunca sucederia, então esperar seria esperar para
# sempre. Aconteceu duas vezes em 18/08/2026 e travou a frota inteira. Lixo: remove e avisa.
if [ -e "$LOCK" ] && [ ! -d "$LOCK" ]; then
    echo "AVISO: $LOCK existe como ARQUIVO (o lock desta casa é diretório) — removendo lixo"
    rm -f "$LOCK"
fi

t=0
until mkdir "$LOCK" 2>/dev/null; do
    if [ "$t" -eq 0 ]; then
        echo "lock ocupado por: $(quem_segura)"
        echo "esperando até ${ESPERA}s (o build ficaria com a imagem trocada no meio se eu atropelasse)"
    fi
    if [ "$t" -ge "$ESPERA" ]; then
        echo "ERRO: lock ainda ocupado após ${ESPERA}s — comando NÃO executado." >&2
        echo "      dono: $(quem_segura)" >&2
        exit 2
    fi
    sleep 5
    t=$((t + 5))
done

# Só removo o lock que EU criei — nunca o de outro processo.
trap 'rm -rf "$LOCK" 2>/dev/null' EXIT
printf 'com_lock pid=%s em=%s\ncomando: %s\n' "$$" "$(date '+%F %T')" "$*" > "$LOCK/owner" 2>/dev/null

[ "$t" -gt 0 ] && echo "lock obtido após ${t}s"
"$@"
