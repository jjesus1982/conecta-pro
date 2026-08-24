#!/usr/bin/env bash
# Copia para dentro de um container e PROVA que chegou, comparando sha256.
#
# Por que existe: `docker cp ... >/dev/null` falhou três vezes em 24/08/2026 sem eu perceber.
# A terceira foi a pior — não custou tempo, custou CONFIANÇA NA MEDIÇÃO: a trava de período
# acusava 3 no container e `confere` no git, e eu quase reabri uma família que estava fechada
# corretamente. O container é que tinha a versão velha.
#
# Regra que depende de memória falha na terceira vez. Esta já falhou.
#
#   scripts/cp_verificado.sh <arquivo-local> <container>:<caminho-absoluto-no-container>
#
# Sai 0 só quando os dois sha256 batem. Qualquer outra coisa é erro, e erro barulhento.
set -euo pipefail

if [ $# -ne 2 ]; then
    echo "uso: $0 <arquivo> <container>:<caminho>" >&2
    exit 2
fi

ORIGEM="$1"
DESTINO="$2"
CONTAINER="${DESTINO%%:*}"
CAMINHO="${DESTINO#*:}"

[ -f "$ORIGEM" ] || { echo "ERRO: $ORIGEM não existe no disco" >&2; exit 2; }
# Destino de DIRETÓRIO (terminado em /) esconde o nome final e impede a conferência — o
# `sha256sum` cairia sobre um caminho que não é arquivo. Exigir o caminho completo é o que
# torna a prova possível.
case "$CAMINHO" in
    */)  echo "ERRO: destino terminado em '/' é diretório; informe o caminho COMPLETO do" >&2
         echo "      arquivo no container (ex.: /app/scripts/qa/x.py)" >&2
         exit 2 ;;
    /*)  ;;
    *)   echo "ERRO: informe o caminho ABSOLUTO do arquivo no container" >&2; exit 2 ;;
esac

docker cp "$ORIGEM" "$CONTAINER:$CAMINHO"

NO_DISCO="$(sha256sum "$ORIGEM" | cut -d' ' -f1)"
NO_CONTAINER="$(docker exec "$CONTAINER" sha256sum "$CAMINHO" 2>/dev/null | cut -d' ' -f1 || true)"

if [ -z "$NO_CONTAINER" ]; then
    echo "ERRO: $CAMINHO não existe em $CONTAINER depois do cp — a cópia NÃO chegou" >&2
    exit 1
fi
if [ "$NO_DISCO" != "$NO_CONTAINER" ]; then
    echo "ERRO: sha DIVERGE — disco=${NO_DISCO:0:16} container=${NO_CONTAINER:0:16}" >&2
    echo "      o container está servindo OUTRA versão do arquivo" >&2
    exit 1
fi

echo "ok ${ORIGEM##*/} → $CONTAINER:$CAMINHO (sha ${NO_DISCO:0:16})"
