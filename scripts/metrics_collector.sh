#!/bin/bash
# Coleta métricas customizadas para node_exporter textfile collector
# Executado via cron a cada 5 minutos

OUTPUT="/opt/conecta-pro/monitoring/textfile_collector/custom_metrics.prom"
TMP="${OUTPUT}.tmp"

# --- SSL Certificate Days Remaining ---
ssl_days=0
cert_file="/etc/letsencrypt/live/erp.conectamais.pro/fullchain.pem"
if [ -f "$cert_file" ]; then
  expiry=$(openssl x509 -enddate -noout -in "$cert_file" 2>/dev/null | cut -d= -f2)
  if [ -n "$expiry" ]; then
    expiry_epoch=$(date -d "$expiry" +%s 2>/dev/null)
    now_epoch=$(date +%s)
    ssl_days=$(( (expiry_epoch - now_epoch) / 86400 ))
  fi
fi

# --- Backup Age (seconds since last backup) ---
backup_age=999999
latest_backup=$(ls -t /opt/conecta-pro/backups/postgresql/backup_*.sql.gz 2>/dev/null | head -1)
if [ -n "$latest_backup" ]; then
  backup_mtime=$(stat -c %Y "$latest_backup" 2>/dev/null)
  now_epoch=$(date +%s)
  backup_age=$(( now_epoch - backup_mtime ))
fi

# --- PM2 Restarts ---
pm2_restarts=0
if command -v pm2 &>/dev/null; then
  pm2_restarts=$(timeout 10 pm2 jlist 2>/dev/null | python3 -c "
import sys,json
try:
    data=json.load(sys.stdin)
    print(data[0]['pm2_env']['restart_time'] if data else 0)
except: print(0)
" 2>/dev/null)
fi

# --- Celery Queue Length (via Redis) ---
celery_queue_len=0
redis_pass=$(grep "^REDIS_PASSWORD=" /opt/conecta-pro/.env 2>/dev/null | head -1 | cut -d= -f2)
if [ -n "$redis_pass" ]; then
  celery_queue_len=$(docker exec conecta-pro-redis redis-cli -a "$redis_pass" llen celery 2>/dev/null | grep -oP '\d+' || echo 0)
fi

# --- Write metrics ---
cat > "$TMP" << METRICS
# HELP ssl_cert_days_remaining Days until SSL certificate expires
# TYPE ssl_cert_days_remaining gauge
ssl_cert_days_remaining{domain="erp.conectamais.pro"} $ssl_days
# HELP backup_age_seconds Seconds since last successful backup
# TYPE backup_age_seconds gauge
backup_age_seconds $backup_age
# HELP pm2_restart_count Total PM2 restarts for frontend process
# TYPE pm2_restart_count gauge
pm2_restart_count{process="conecta-pro-frontend"} $pm2_restarts
# HELP celery_queue_length Number of tasks in default Celery queue
# TYPE celery_queue_length gauge
celery_queue_length{queue="celery"} $celery_queue_len
METRICS

mv "$TMP" "$OUTPUT"
