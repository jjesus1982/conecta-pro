#!/bin/bash
# build_backend.sh — constrói a imagem do backend SEGURANDO o lock de deploy.
#
# Use este script em vez de `docker compose build backend` direto.
#
# POR QUE: a imagem `conecta-pro-backend:latest` é a MESMA dos 8 workers de celery. Um
# build avulso troca essa tag. Se isso acontece durante o passo 7 de um deploy — que recria
# os workers um a um — metade dos workers fica com a imagem antiga (agora órfã) e a outra
# metade com a nova, todos reportando "healthy". Aconteceu duas vezes em 10/08/2026.
#
# Aqui o build espera o deploy terminar, em vez de atropelá-lo.
#
# ATENÇÃO: construir NÃO coloca o código no ar. O backend e os workers seguem com os
# containers antigos até alguém recriá-los — que é o que o deploy blue/green faz. Se a
# intenção é DEPLOYAR, rode `./scripts/deploy_backend_bluegreen.sh` (ele já builda dentro
# do lock); este script é para quando você quer só a imagem pronta.
set -u
cd /opt/conecta-pro

exec ./scripts/com_lock.sh "$@" docker compose build backend
