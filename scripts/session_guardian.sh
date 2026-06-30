#!/bin/bash
# session_guardian.sh — protege as sessões interativas (tmux/claude/ssh) contra o OOM killer
# e remove leaks que pressionam a memória. Roda via cron a cada minuto. Sempre sai 0.
#
# Por que: o OOM do host já matou sessões (t1). A proteção oom_score_adj=-1000 torna o
# processo imune ao OOM e é HERDADA pelos filhos — então blindar o servidor tmux cobre
# todos os panes/shells, inclusive os criados depois. Também reapeia o vazamento do
# pm2 jlist (metrics_collector) que ficava preso e acumulava por dias.
LOG=/opt/conecta-pro/logs/session_guardian.log
mkdir -p /opt/conecta-pro/logs 2>/dev/null

protect() { echo -1000 > "/proc/$1/oom_score_adj" 2>/dev/null || true; }

# 1) acha as raízes por COMM (lendo /proc): tmux (server/client), claude, sshd.
#    (o cmdline do servidor tmux é "tmux new -s X", então só o comm "tmux: server" casa)
roots=""
for d in /proc/[0-9]*; do
  pid=${d#/proc/}
  c=$(cat "$d/comm" 2>/dev/null) || continue
  case "$c" in tmux*|claude|sshd) roots="$roots $pid"; protect "$pid";; esac
done

# 2) protege TODA a árvore de descendentes das raízes (panes, shells, claude, bash, etc.)
queue="$roots"
seen=" "
while [ -n "$queue" ]; do
  next=""
  for p in $queue; do
    case "$seen" in *" $p "*) continue;; esac
    seen="$seen$p "
    protect "$p"
    next="$next $(pgrep -P "$p" 2>/dev/null)"
  done
  queue="$next"
done

# 3) reapeia leaks conhecidos: pm2 jlist / metrics_collector presos > 120s
for p in $(pgrep -f 'pm2 jlist' 2>/dev/null) $(pgrep -f 'metrics_collector.sh' 2>/dev/null); do
  age=$(ps -o etimes= -p "$p" 2>/dev/null | tr -d ' ')
  [ -n "$age" ] && [ "$age" -gt 120 ] 2>/dev/null && kill -9 "$p" 2>/dev/null
done

# 4) log enxuto a cada execução (memória + nº de sessões protegidas)
avail=$(free -m | awk '/Mem:/{print $7}')
swapfree=$(free -m | awk '/Swap:/{print $4}')
nprot=$(echo "$seen" | wc -w)
echo "$(date '+%F %T') guardian: avail=${avail}MB swapfree=${swapfree}MB protegidos=${nprot}" >> "$LOG" 2>/dev/null
# mantém o log pequeno
tail -n 500 "$LOG" > "$LOG.tmp" 2>/dev/null && mv "$LOG.tmp" "$LOG" 2>/dev/null
exit 0
