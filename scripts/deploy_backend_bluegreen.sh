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
if ! mkdir "$LOCK" 2>/dev/null; then
  log "ERRO: lock ocupado ($LOCK) — outro deploy em andamento"; exit 1
fi
trap 'rm -rf "$LOCK" 2>/dev/null' EXIT  # rm -rf (não rmdir): libera mesmo se houver owner file dentro (senão o lock vaza e trava o fanout)
# Quem está segurando — o `com_lock.sh` lê isto para a espera não ser cega ("lock ocupado
# por: deploy blue/green pid=X desde HH:MM" é acionável; "lock ocupado" não é).
printf 'deploy blue/green pid=%s desde=%s\n' "$$" "$(date '+%F %T')" > "$LOCK/owner" 2>/dev/null

log "═══ BLUE/GREEN INICIADO ═══"

# 1. Build da imagem nova
log "1/7 build..."
docker compose build backend >>"$LOG" 2>&1 || { log "ERRO no build"; exit 1; }

# FIXA a imagem deste deploy. Sem isto, todo `up` daqui pra frente resolve a tag `latest`
# no instante em que roda — e o passo 7 leva ~12 min recriando os workers um a um. Um build
# por fora do lock nesse intervalo troca a tag no meio: parte dos containers fica com a
# imagem antiga (que vira órfã) e parte com a nova, todos "healthy". Medido 3x em 10/08/2026
# (2, depois 4, depois 7 workers). Com o ID fixo, um build concorrente pode mexer na tag à
# vontade: ESTE deploy termina inteiro na MESMA imagem.
export BACKEND_IMAGE
BACKEND_IMAGE=$(docker image inspect conecta-pro-backend:latest --format '{{.Id}}' 2>/dev/null)
if [ -z "${BACKEND_IMAGE:-}" ]; then
  log "ERRO: não consegui resolver o ID da imagem recém-construída"; exit 1
fi
log "  imagem deste deploy: ${BACKEND_IMAGE#sha256:}"

# 2. Sobe GREEN com a imagem nova (tráfego segue no primário)
log "2/7 subindo green (8081)..."
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

log "═══ BLUE/GREEN CONCLUÍDO — zero downtime, backend + $TOTAL worker(s) ═══"
