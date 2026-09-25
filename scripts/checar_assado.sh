#!/usr/bin/env bash
# Um arquivo do disco está DENTRO da imagem, ou só no contêiner por `docker cp`?
#
# Nasceu em 25/09/2026 de um falso-verde que quase custou caro. Duas sessões precisavam saber
# se um bake tinha levado o código delas, e as duas escreveram a mesma medição errada:
#
#     docker exec conecta-pro-backend md5sum /app/arquivo.py      # ERRADO
#
# `docker exec` lê o filesystem do CONTÊINER RODANDO — que contém todos os `docker cp` feitos
# desde que ele subiu. Ele responde com confiança total «igual», e está lendo a cópia quente,
# não a imagem. A outra sessão foi conferir assim, leu ✅, e a imagem tinha a versão VELHA do
# módulo que mascara a chave PIX. Um `recreate` de qualquer sessão teria mandado 66 mensagens
# de WhatsApp com a chave PIX inteira de cada pessoa.
#
# A medição certa é um contêiner EFÊMERO a partir da imagem, que não tem cópia quente nenhuma.
#
# NOMEIE A CAMADA: imagem (o que sobrevive a um recreate) · contêiner (imagem + docker cp) ·
# processo (o que o Python já carregou — nem isto nem md5 respondem por ele; só rodar o
# caminho real responde, e é por isso que o passo final de qualquer entrega é um uso de
# verdade, não um hash).
#
# Uso:  ./scripts/checar_assado.sh [contêiner] arquivo-relativo-a-backend/ [mais arquivos...]
#       ./scripts/checar_assado.sh backend/modules/fiscal/services/danfe_layout.py
#
# Linha canônica: `TOTAL: <n> arquivo(s) fora da imagem`. Exit 1 se algum divergir.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 2

CONTAINER="conecta-pro-backend"
case "${1:-}" in conecta-pro-*) CONTAINER="$1"; shift ;; esac
[ $# -eq 0 ] && { echo "uso: $0 [contêiner] backend/caminho/arquivo.py ..."; exit 2; }

IMG=$(docker inspect --format '{{.Image}}' "$CONTAINER" 2>/dev/null) || {
  echo "RECUSO: contêiner '$CONTAINER' não existe"; exit 2; }
echo "contêiner $CONTAINER · imagem ${IMG:7:12}"
echo

fora=0
for F in "$@"; do
  REL="${F#backend/}"
  [ -f "backend/$REL" ] || { echo "  AUSENTE  backend/$REL não existe no disco"; fora=$((fora+1)); continue; }
  D=$(md5sum "backend/$REL" | cut -c1-8)
  # --entrypoint sh porque a imagem sobe uvicorn por padrão; --rm para não deixar lixo.
  # 2>/dev/null engole o «No such file» e vira string vazia, que divergindo já denuncia.
  I=$(docker run --rm --entrypoint sh "$IMG" -c "md5sum /app/$REL 2>/dev/null" | cut -c1-8)
  C=$(docker exec "$CONTAINER" md5sum "/app/$REL" 2>/dev/null | cut -c1-8)
  if [ "$D" = "$I" ]; then
    printf "  OK       %s\n" "$REL"
  else
    fora=$((fora+1))
    printf "  FORA     %s\n" "$REL"
    printf "           disco=%s imagem=%s contêiner=%s\n" "$D" "${I:-(ausente)}" "${C:-(ausente)}"
    [ "$D" = "$C" ] && printf "           ⚠️  está no contêiner por docker cp: um recreate APAGA\n"
  fi
done

echo
echo "TOTAL: $fora arquivo(s) fora da imagem"
[ "$fora" -eq 0 ] && echo "  Tudo assado. Isto NÃO prova que o processo carregou — para isso, rode o caminho real."
exit $([ "$fora" -eq 0 ] && echo 0 || echo 1)
