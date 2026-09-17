#!/bin/bash
# deploy_backend_bluegreen.sh — deploy do backend SEM downtime (requisito 24x7 do Jordan).
#
# Fluxo: build → sobe GREEN (8081, imagem nova) → espera saudável → nginx vira p/ 8081
# → recria o backend primário (8080, imagem nova) → espera saudável → nginx volta p/ 8080
# → remove green → recria os workers de celery. O tráfego público NUNCA fica sem um
# backend saudável atendendo.
#
# Falhas: se o green não ficar saudável, aborta SEM tocar no tráfego. Se o primário
# não voltar, o tráfego PERMANECE no green (não remove) e o script sai com erro.
#
# POR QUE OS WORKERS ENTRAM AQUI (passo 7): celery-* e flower rodam a MESMA imagem
# `conecta-pro-backend:latest`, mas nunca eram recriados — os containers ficavam de pé por
# semanas servindo código velho enquanto o backend era deployado várias vezes por dia.
# Consequência real (07/08/2026): 9 watchers de DP existiam no backend e NÃO existiam no
# worker; o avaliador rodava a cada 15 min sem enxergá-los e os alertas ficaram 24h
# congelados sem ninguém perceber, porque container "healthy" não diz nada sobre o código
# que ele carrega. Se você mexeu numa task, num watcher ou no beat_schedule, é este passo
# que leva a mudança para produção — não o build.
set -u
cd /opt/conecta-pro

NGINX_SITE=/etc/nginx/sites-available/erp.conectamais.pro
LOCK=/tmp/conecta_deploy.lock
LOG=/opt/conecta-pro/logs/deploy_bluegreen.log
COMPOSE_BG="docker compose -f docker-compose.yml -f docker-compose.bluegreen.yml"
COMPOSE_CELERY="docker compose -f docker-compose.yml -f docker-compose.celery.yml"
HEALTH_TIMEOUT=${HEALTH_TIMEOUT:-420}  # 7 min p/ boot do app
WORKER_TIMEOUT=${WORKER_TIMEOUT:-180}  # por worker; eles sobem bem mais rápido que o app
SKIP_CELERY=${SKIP_CELERY:-0}          # =1 pula o passo 7 (deploy só do backend)

log() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }

nginx_upstream_to() {  # $1 = porta destino
  sed -i "0,/server 127.0.0.1:80[0-9][0-9];/s//server 127.0.0.1:$1;/" "$NGINX_SITE"
  nginx -t >/dev/null 2>&1 || { log "ERRO: nginx -t falhou — revertendo"; return 1; }
  systemctl reload nginx
  log "nginx → 127.0.0.1:$1 (reload gracioso)"
}

wait_health() {  # $1 = porta, $2 = nome
  local t=0
  until curl -sf -o /dev/null "http://127.0.0.1:$1/health"; do
    sleep 5; t=$((t+5))
    [ "$t" -ge "$HEALTH_TIMEOUT" ] && { log "TIMEOUT: $2 não ficou saudável em ${HEALTH_TIMEOUT}s"; return 1; }
  done
  log "$2 saudável (porta $1, ${t}s)"
}

cleanup_green() { $COMPOSE_BG rm -sf backend-green >/dev/null 2>&1; }

# ── O sandbox do MCP e a porta 8081 ──────────────────────────────────────────
# `conecta-pro-backend-staging` publica em 127.0.0.1:8081 — a MESMA porta do green. Em
# 14/09/2026 um deploy o matou (Exited 137) para tomar a porta e ninguém religou: o R07 do
# `test_regressao_mcp` — "o caso mais importante da suíte", o que prova que o sandbox não
# vaza para produção — ficou 3 dias vermelho com `Name or service not known`.
# Agora o deploy para o staging de propósito e o devolve no fim. O `conecta-pro-mcp` fala com
# ele pela `conecta-staging-network`, que o compose do conector já declara — container parado
# some do DNS da rede, e é daí que vem o `Name or service not known`.
STAGING="conecta-pro-backend-staging"
STAGING_ESTAVA_DE_PE=0

parar_sandbox_mcp() {
  if [ -n "$(docker ps -q -f name="^${STAGING}$")" ]; then
    STAGING_ESTAVA_DE_PE=1
    log "  parando $STAGING (ele ocupa a 8081 que o green precisa)"
    docker stop "$STAGING" >/dev/null 2>&1 || true
  fi
}

religar_sandbox_mcp() {
  [ "$STAGING_ESTAVA_DE_PE" = "1" ] || return 0
  docker start "$STAGING" >/dev/null 2>&1 || { log "  AVISO: não consegui religar $STAGING"; return 0; }
  log "  $STAGING de volta (sandbox do MCP)"
}

# Serviços do compose de celery declarados sobre a imagem do backend. Lido do ARQUIVO, não
# de `docker ps`: container já recriado mostra a tag, container antigo mostra só o hash da
# imagem que a tag deixou de apontar — usar o que está rodando faria a lista encolher a cada
# execução. Assim, worker novo que alguém adicionar amanhã entra sozinho.
svcs_da_imagem_backend() {
  # Casa QUALQUER linha de image que mencione a imagem do backend — inclusive a forma com
  # variavel: `image: ${BACKEND_IMAGE:-conecta-pro-backend:latest}`.
  # Antes o padrao exigia a string exata `image: conecta-pro-backend:latest`. Quando o pin
  # por ID entrou (10/08/2026), o awk parou de casar e o passo 7 anunciou "recriando 0
  # worker(s)" — deploy que parecia OK e nao levava codigo nenhum para os 8 workers.
  # Pego na primeira execucao pela verificacao pos-deploy.
  awk '/^  [a-z0-9-]+:$/ {s=$1; sub(":","",s)}
       /^    image:.*conecta-pro-backend/ {print s}' docker-compose.celery.yml
}

wait_container_health() {  # $1 = nome do container, $2 = timeout
  local t=0 st
  while :; do
    st=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$1" 2>/dev/null)
    case "$st" in
      healthy|running) return 0 ;;
      ""|exited|dead)  log "  ! $1 está '$st'"; return 1 ;;
    esac
    sleep 5; t=$((t+5))
    [ "$t" -ge "$2" ] && { log "  ! $1 não ficou saudável em ${2}s (status: $st)"; return 1; }
  done
}

# ── lock de deploy (convivência entre terminais) ──
# O lock é um DIRETÓRIO (mkdir é atômico). Se o caminho existir como ARQUIVO, não é o nosso
# lock: ninguém o segura, `mkdir` nunca vai suceder, e o pipeline fica travado para a frota
# inteira sem que haja deploy algum em curso. Medido duas vezes em 18/08/2026 — um arquivo
# regular de 0 byte apareceu às 07:58 e de novo às 17:14, e nesse intervalo NENHUM terminal
# conseguia deployar. Arquivo aqui é lixo: remove, avisa alto e segue.
if [ -e "$LOCK" ] && [ ! -d "$LOCK" ]; then
  log "AVISO: $LOCK existe como ARQUIVO (não é o lock desta casa, que é diretório) — removendo"
  rm -f "$LOCK"
fi
if ! mkdir "$LOCK" 2>/dev/null; then
  log "ERRO: lock ocupado ($LOCK) — outro deploy em andamento"; exit 1
fi
# rm -rf (não rmdir): libera mesmo se houver owner file dentro (senão o lock vaza e trava o
# fanout). `religar_sandbox_mcp` vai JUNTO no trap porque o deploy aborta em quatro pontos
# (green não sobe, nginx não vira, primário não volta, imagem não resolve) e em nenhum deles
# passaria pelo fim — foi exatamente assim que o staging ficou 3 dias fora do ar.
trap 'religar_sandbox_mcp 2>/dev/null; rm -rf "$LOCK" 2>/dev/null' EXIT
# Quem está segurando — o `com_lock.sh` lê isto para a espera não ser cega ("lock ocupado
# por: deploy blue/green pid=X desde HH:MM" é acionável; "lock ocupado" não é).
printf 'deploy blue/green pid=%s desde=%s\n' "$$" "$(date '+%F %T')" > "$LOCK/owner" 2>/dev/null

log "═══ BLUE/GREEN INICIADO ═══"

# ── O bake publica o DISCO, não o HEAD ───────────────────────────────────────────────────
# 31/08/2026. `docker-compose.yml` declara `build: { context: ./backend }` e o Dockerfile faz
# `COPY . .` — então o contexto do build é o DIRETÓRIO daquele minuto, de TODAS as sessões.
# Provado por hash: `contract_signature.py` tinha um conteúdo no git e outro no disco, e o
# que foi para a imagem foi o do disco.
#
# ⚠️ Isto vinha sendo repetido ao contrário entre sessões ("o bake leva só o commitado"), e
# pode haver quem tenha deixado WIP solto achando que estava protegido.
#
# AVISA, NÃO RECUSA — decisão do Jordan, e o motivo é operacional: em dia de vários bakes,
# bloquear trava o trabalho de todos até alguém limpar. E ZERO SAÍDA com o disco limpo:
# aviso que aparece sempre vira ruído e para de ser lido.
avisar_wip_fora_do_head() {
  local sujos n
  sujos="$(git status --porcelain -- backend/ 2>/dev/null)"
  [ -z "$sujos" ] && return 0
  n="$(printf '%s\n' "$sujos" | grep -c '^')"
  log "⚠️  ESTE BAKE VAI PUBLICAR $n ARQUIVO(S) ALÉM DO HEAD:"
  printf '%s\n' "$sujos" | sed 's|^|      |' | while IFS= read -r l; do log "$l"; done
  log "    O contexto do build é o DISCO, não o commit. Estes arquivos vão para produção"
  log "    sem estar no git — inclusive os de outras sessões."
  WIP_FORA_DO_HEAD="$n"
}

# 1. Build da imagem nova
avisar_wip_fora_do_head
log "1/7 build..."
docker compose build backend >>"$LOG" 2>&1 || { log "ERRO no build"; exit 1; }

# FIXA a imagem deste deploy. Sem isto, todo `up` daqui pra frente resolve a tag `latest`
# no instante em que roda — e o passo 7 leva ~12 min recriando os workers um a um. Um build
# por fora do lock nesse intervalo troca a tag no meio: parte dos containers fica com a
# imagem antiga (que vira órfã) e parte com a nova, todos "healthy". Medido 3x em 10/08/2026
# (2, depois 4, depois 7 workers). Com o ID fixo, um build concorrente pode mexer na tag à
# vontade: ESTE deploy termina inteiro na MESMA imagem.
# SEM o prefixo `sha256:`. Com ele, o compose lê "sha256:abc..." como
# repositório=sha256 / tag=abc... e tenta BAIXAR:
#   Error pull access denied for sha256, repository does not exist
# O passo 7 então falhava em quase todos os workers e eles seguiam com código
# ANTIGO — o oposto do que a fixação por ID existe para evitar. Medido em
# 12/08/2026: 2 deploys seguidos deixaram 5 workers para trás, incluindo o
# celery-beat (nenhum beat novo valia). O hex puro o docker resolve localmente.
export BACKEND_IMAGE
BACKEND_IMAGE=$(docker image inspect conecta-pro-backend:latest --format '{{.Id}}' 2>/dev/null)
BACKEND_IMAGE=${BACKEND_IMAGE#sha256:}
if [ -z "${BACKEND_IMAGE:-}" ]; then
  log "ERRO: não consegui resolver o ID da imagem recém-construída"; exit 1
fi
log "  imagem deste deploy: $BACKEND_IMAGE"

# 2. Sobe GREEN com a imagem nova (tráfego segue no primário)
log "2/7 subindo green (8081)..."
parar_sandbox_mcp
$COMPOSE_BG up -d --no-deps backend-green >>"$LOG" 2>&1 || { log "ERRO ao subir green"; cleanup_green; exit 1; }
wait_health 8081 "green" || { cleanup_green; log "ABORTADO — tráfego intocado no primário"; exit 1; }

# 3. Vira o tráfego pro GREEN
log "3/7 tráfego → green..."
nginx_upstream_to 8081 || { cleanup_green; exit 1; }

# 4. Recria o primário com a imagem nova (green atendendo)
log "4/7 recriando primário (8080)..."
docker compose up -d --no-deps backend >>"$LOG" 2>&1
if ! wait_health 8080 "primário"; then
  log "ERRO: primário não voltou — TRÁFEGO PERMANECE NO GREEN (não removido). Intervenha."
  exit 1
fi

# 5. Volta o tráfego pro primário
log "5/7 tráfego → primário..."
nginx_upstream_to 8080 || exit 1
sleep 3  # drena conexões keep-alive do green

# 6. Remove o green
log "6/7 removendo green..."
cleanup_green

# 7. Recria os workers de celery sobre a imagem nova.
#
# Fica DEPOIS do passo 6 de propósito: a parte zero-downtime já terminou e o tráfego público
# já está estável no primário. Daqui pra frente nada que der errado derruba o site — por isso
# este passo é NÃO-FATAL: registra o que falhou e devolve exit 1 no fim, sem desfazer um
# deploy de backend que deu certo.
#
# Um de cada vez, e não `up -d` em todos: cada worker atende uma fila diferente e derrubar
# todos juntos deixaria TODAS as filas mudas ao mesmo tempo. Sequencial, cada fila fica fora
# só o tempo do seu próprio restart. O SIGTERM do compose é warm shutdown do celery — a task
# em andamento termina dentro do stop_grace_period (30s) antes do container morrer.
#
# celery-beat por ÚLTIMO: o beat novo pode agendar uma task que só existe no código novo. Se
# ele subir antes dos workers, essa task cai em worker velho e morre como "unregistered".
if [ "$SKIP_CELERY" = "1" ]; then
  log "7/7 celery: PULADO (SKIP_CELERY=1) — os workers seguem com o código anterior"
  log "═══ BLUE/GREEN CONCLUÍDO — zero downtime (backend apenas) ═══"
  # Mostra QUAIS ficaram para trás. Aqui o drift é intencional, então não falha o deploy —
  # mas fica registrado no log, com nome e sobrenome, em vez de virar dívida invisível.
  log "workers que ficaram com o código anterior (drift intencional deste SKIP_CELERY):"
  DENTRO_DO_DEPLOY=1 ./scripts/checar_drift_workers.sh 2>&1 | tee -a "$LOG"
  exit 0
fi

SVCS="$(svcs_da_imagem_backend | grep -vx 'celery-beat'; svcs_da_imagem_backend | grep -x 'celery-beat')"
TOTAL=$(echo "$SVCS" | grep -c .)
log "7/7 recriando $TOTAL worker(s) de celery com a imagem nova..."

FALHOS=""
for svc in $SVCS; do
  if ! $COMPOSE_CELERY up -d --no-deps --force-recreate "$svc" >>"$LOG" 2>&1; then
    log "  ! $svc: falhou ao recriar"; FALHOS="$FALHOS $svc"; continue
  fi
  # o nome do container não é derivável do nome do serviço (container_name explícito no
  # compose), então pergunta ao próprio compose qual container ele acabou de criar
  cid=$($COMPOSE_CELERY ps -q "$svc" 2>/dev/null | head -1)
  if [ -z "$cid" ] || ! wait_container_health "$cid" "$WORKER_TIMEOUT"; then
    FALHOS="$FALHOS $svc"; continue
  fi
  log "  ✓ $svc"
done

if [ -n "$FALHOS" ]; then
  log "═══ BACKEND OK, MAS WORKER(ES) COM PROBLEMA:$FALHOS ═══"
  log "    Esses seguem com o código ANTIGO. Tasks/watchers alterados NÃO estão valendo neles."
  exit 1
fi
# ── Verificação pós-deploy: os workers ficaram MESMO com a imagem do backend? ────────
# Recriar não garante: se alguém reconstruir a imagem POR FORA deste script enquanto o
# laço do passo 7 roda, a tag `latest` muda no meio e os workers já recriados ficam com a
# imagem anterior — que vira órfã. Medido duas vezes em 10/08/2026 (2 e depois 4 workers).
# O lock NÃO protege contra isso: ele serializa deploys, não `docker compose build` avulso.
# E "healthy" não denuncia código velho — foi assim que o beat rodou 46 dias quebrado.
log "verificação pós-deploy — imagem dos workers × backend:"
DENTRO_DO_DEPLOY=1 ./scripts/checar_drift_workers.sh 2>&1 | tee -a "$LOG"
if [ "${PIPESTATUS[0]}" -ne 0 ]; then
  log "⚠ DRIFT APÓS O DEPLOY — worker(es) ficaram com imagem anterior."
  log "  Causa provável: build da imagem por fora deste script durante o passo 7."
  log "  Corrigir SÓ os acusados (rápido), em vez de reassar tudo:"
  log "    docker compose -f docker-compose.yml -f docker-compose.celery.yml \\"
  log "      up -d --no-deps --force-recreate <servico>"
  exit 1
fi

# Repete no FIM: o deploy roda em background e o log é longo. Aviso perdido no meio de 300
# linhas não é aviso — é registro. Aqui fica ao lado do resultado do drift, que é onde se olha.
if [ -n "${WIP_FORA_DO_HEAD:-}" ]; then
  log "⚠️  LEMBRETE: este bake publicou $WIP_FORA_DO_HEAD arquivo(s) que NÃO estão no git."
  log "    Rode: git status --porcelain -- backend/"
fi

# ── O outro lado da parede: o frontend publicado sabe ler o que este backend passou a emitir?
# Origem: 15/09/2026. O bake das 00:47 publicou o payload achatado (`fieldsRef`/`verDaLinha`)
# e o frontend que resolve essas chaves ficou compilado no host, nunca publicado. As 29 telas
# do redesign morriam em «Algo deu errado» — o backend respondia 200 o tempo todo, e por isso
# o drift de worker e o HTTP 200 do deploy ficaram verdes. Nove horas até a Pyetra reportar.
#
# NÃO falha o deploy: a esta altura o backend já está no ar e abortar não desfaz nada. O que
# resolve é publicar o frontend, e é isso que este bloco manda fazer, alto e com o comando.
log "verificação pós-deploy — o frontend publicado lê o contrato deste backend:"
if ! python3 backend/scripts/qa/checar_contrato_front_back.py 2>&1 | tee -a "$LOG"; then
  log "⚠️  O FRONTEND NO AR NÃO SABE LER O CONTRATO DESTE BACKEND."
  log "    Toda tela do redesign vai cair em «Algo deu errado» no navegador do usuário."
  log "    Corrija AGORA, publicando o frontend:"
  log "      cd frontend && NODE_OPTIONS=--max-old-space-size=4096 npm run build"
  log "      cd .. && ./scripts/deploy/deploy_frontend.sh"
fi

log "═══ BLUE/GREEN CONCLUÍDO — zero downtime, backend + $TOTAL worker(s) ═══"
