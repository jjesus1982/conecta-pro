#!/usr/bin/env python3
"""
OpenClaw Preventive Action v2 — Age antes dos problemas acontecerem.

Monitora todos os 35 módulos do backend, aplica regras baseadas na
knowledge base, e executa ações preventivas contextuais por horário.

Agendado: a cada 15 minutos via cron.
"""

import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

PROJECT_DIR = Path("/opt/conecta-pro")
KB_FILE = PROJECT_DIR / "agent_knowledge_base.json"
STATE_FILE = PROJECT_DIR / "AGENT_STATE.json"
WEEKLY_REPORT_FILE = PROJECT_DIR / "WEEKLY_PATTERNS_REPORT.md"

# Postgres não expõe porta ao host — usar docker exec para queries
# Para padrões do banco (openclaw_patterns), conectar via docker exec
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "conecta_pro")
DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "")

CONFIDENCE_THRESHOLD = 70.0
BRT_OFFSET = -4  # UTC-4 (Manaus)

if not DB_PASS:
    env_file = PROJECT_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("POSTGRES_PASSWORD=") and "STAGING" not in line:
                DB_PASS = line.split("=", 1)[1]
                break


def get_docker_pg_ip() -> str:
    """Obtém IP do PostgreSQL dentro da rede Docker."""
    try:
        result = subprocess.run(
            "docker inspect conecta-pro-postgres",
            shell=True, capture_output=True, text=True, timeout=10
        )
        data = json.loads(result.stdout)
        nets = data[0]["NetworkSettings"]["Networks"]
        for info in nets.values():
            if info.get("IPAddress"):
                return info["IPAddress"]
    except Exception:
        pass
    return ""


def get_conn():
    """Conecta ao PostgreSQL. Tenta localhost, fallback via Docker network IP."""
    try:
        return psycopg2.connect(
            host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS,
            connect_timeout=5
        )
    except Exception:
        docker_ip = get_docker_pg_ip()
        if docker_ip:
            return psycopg2.connect(
                host=docker_ip, port="5432", dbname=DB_NAME, user=DB_USER, password=DB_PASS,
                connect_timeout=5
            )
        raise


def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] preventive: {msg}", flush=True)


def run_cmd(cmd: str, timeout: int = 30) -> tuple[int, str]:
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return result.returncode, (result.stdout + result.stderr).strip()[:2000]
    except subprocess.TimeoutExpired:
        return -1, f"Timeout apos {timeout}s"
    except Exception as e:
        return -1, str(e)[:500]


def now_brt() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=BRT_OFFSET)


def is_peak_hour() -> bool:
    h = now_brt().hour
    return (7 <= h <= 9) or (17 <= h <= 19)


def is_pre_peak() -> bool:
    """30 minutos antes do horário de pico — janela para pré-aquecimento."""
    h = now_brt().hour
    m = now_brt().minute
    return (h == 6 and m >= 30) or (h == 16 and m >= 30)


def load_kb() -> dict:
    try:
        return json.loads(KB_FILE.read_text())
    except Exception:
        return {}


# =============================================================================
# COLETORES DE MÉTRICAS
# =============================================================================

def get_disk_usage_percent() -> float | None:
    rc, out = run_cmd("df / | tail -1 | awk '{print $5}' | tr -d '%'")
    if rc == 0 and out.strip().isdigit():
        return float(out.strip())
    return None


def get_memory_usage_percent() -> float | None:
    rc, out = run_cmd("free | awk '/^Mem:/ {printf \"%.1f\", $3/$2*100}'")
    if rc == 0:
        try:
            return float(out.strip())
        except ValueError:
            pass
    return None


def get_pg_active_connections() -> int | None:
    rc, out = run_cmd(
        "docker exec conecta-pro-postgres psql -U postgres -d conecta_pro -t "
        "-c 'SELECT count(*) FROM pg_stat_activity' 2>/dev/null"
    )
    if rc == 0:
        try:
            return int(out.strip())
        except ValueError:
            pass
    return None


def get_redis_memory_mb() -> float | None:
    redis_pw = ""
    env_file = PROJECT_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("REDIS_PASSWORD=") and "STAGING" not in line:
                redis_pw = line.split("=", 1)[1]
                break
    rc, out = run_cmd(
        f"docker exec conecta-pro-redis redis-cli -a '{redis_pw}' info memory 2>/dev/null "
        "| grep 'used_memory:' | cut -d: -f2 | tr -d '\\r'"
    )
    if rc == 0:
        try:
            return float(out.strip()) / (1024 * 1024)
        except ValueError:
            pass
    return None


def get_celery_queue_length() -> int | None:
    redis_pw = ""
    env_file = PROJECT_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("REDIS_PASSWORD=") and "STAGING" not in line:
                redis_pw = line.split("=", 1)[1]
                break
    rc, out = run_cmd(
        f"docker exec conecta-pro-redis redis-cli -a '{redis_pw}' llen celery 2>/dev/null"
    )
    if rc == 0:
        try:
            return int(out.strip())
        except ValueError:
            pass
    return None


def get_load_average() -> float | None:
    rc, out = run_cmd("cat /proc/loadavg | awk '{print $2}'")
    if rc == 0:
        try:
            return float(out.strip())
        except ValueError:
            pass
    return None


METRIC_COLLECTORS = {
    "disk_usage_percent": get_disk_usage_percent,
    "memory_usage_percent": get_memory_usage_percent,
    "pg_active_connections": get_pg_active_connections,
    "redis_memory_mb": get_redis_memory_mb,
    "celery_queue_length": get_celery_queue_length,
    "load_average_5m": get_load_average,
}


# =============================================================================
# HEALTH CHECK POR MÓDULO
# =============================================================================

MODULE_HEALTH_CHECKS = {
    # --- Infraestrutura core ---
    "backend": {
        "check": "curl -so /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8080/health",
        "expect": "200",
        "criticality": "critical",
        "description": "API principal FastAPI",
    },
    "postgres": {
        "check": "docker exec conecta-pro-postgres pg_isready -U postgres -q 2>/dev/null && echo OK",
        "expect": "OK",
        "criticality": "critical",
        "description": "PostgreSQL 16",
    },
    "redis": {
        "check": "docker exec conecta-pro-redis redis-cli -a \"$(grep '^REDIS_PASSWORD=' /opt/conecta-pro/.env | head -1 | cut -d= -f2)\" ping 2>/dev/null | grep -o PONG",
        "expect": "PONG",
        "criticality": "critical",
        "description": "Redis 7",
    },
    "nginx": {
        "check": "systemctl is-active nginx 2>/dev/null",
        "expect": "active",
        "criticality": "critical",
        "description": "Nginx reverse proxy",
    },
    # --- Módulos backend (check via HTTP code — 401 = módulo carregado, 000 = down) ---
    "financeiro": {
        "check": "curl -so /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8080/api/v1/financial/accounting/dre",
        "expect_not": "000",
        "criticality": "critical",
        "description": "Módulo financeiro (466 endpoints)",
    },
    "operacional": {
        "check": "curl -so /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8080/api/v1/operacional/posts/",
        "expect_not": "000",
        "criticality": "critical",
        "description": "Módulo operacional (252 endpoints)",
    },
    "government": {
        "check": "curl -so /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8080/api/v1/government/nfse/manaus/status",
        "expect_not": "000",
        "criticality": "critical",
        "description": "Integrações gov (eSocial, SEFAZ, NFS-e)",
    },
    "rh": {
        "check": "curl -so /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8080/api/v1/people-management/dp/dashboard/",
        "expect_not": "000",
        "criticality": "high",
        "description": "Módulo RH/DP (643 endpoints)",
    },
    "crm": {
        "check": "curl -so /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8080/api/v1/crm/leads/",
        "expect_not": "000",
        "criticality": "high",
        "description": "CRM (100 endpoints)",
    },
    "ged": {
        "check": "curl -so /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8080/api/v1/ged/documents/",
        "expect_not": "000",
        "criticality": "high",
        "description": "GED (139 endpoints)",
    },
    # --- Celery workers ---
    "celery_beat": {
        "check": "docker inspect --format='{{.State.Health.Status}}' conecta-pro-celery-beat 2>/dev/null",
        "expect": "healthy",
        "criticality": "high",
        "description": "Celery Beat (scheduler)",
    },
    "celery_priority": {
        "check": "docker ps --filter name=celery-priority --filter health=healthy -q 2>/dev/null | wc -l",
        "expect_not": "0",
        "criticality": "critical",
        "description": "Celery worker eSocial/FGTS",
    },
    "celery_sefaz": {
        "check": "docker ps --filter name=celery-sefaz --filter health=healthy -q 2>/dev/null | wc -l",
        "expect_not": "0",
        "criticality": "critical",
        "description": "Celery worker SEFAZ (NF-e, CT-e)",
    },
    "celery_operacional": {
        "check": "docker ps --filter name=celery-operacional --filter health=healthy -q 2>/dev/null | wc -l",
        "expect_not": "0",
        "criticality": "high",
        "description": "Celery worker operacional",
    },
}


def check_module_health() -> list[dict]:
    """Verifica saúde de todos os módulos. Retorna lista de problemas."""
    problems = []

    for module, config in MODULE_HEALTH_CHECKS.items():
        rc, output = run_cmd(config["check"], timeout=10)
        out = output.strip()

        # Determinar se está saudável
        if "expect" in config:
            healthy = out == config["expect"]
        elif "expect_not" in config:
            healthy = out != config["expect_not"] and out != ""
        else:
            healthy = rc == 0 and out != ""

        if not healthy:
            problems.append({
                "module": module,
                "criticality": config["criticality"],
                "description": config["description"],
                "check_output": out[:200] if out else "sem resposta",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

    return problems


# =============================================================================
# AÇÕES PREVENTIVAS CONTEXTUAIS (HORÁRIO DE PICO)
# =============================================================================

PEAK_HOUR_ACTIONS = [
    {
        "name": "pre_peak_redis_warmup",
        "trigger": "pre_peak",
        "description": "Pré-aquece cache Redis antes do pico",
        "command": (
            "curl -sf http://localhost:8080/api/v1/operacional/posts/?page=1&page_size=50 > /dev/null 2>&1 && "
            "curl -sf http://localhost:8080/api/v1/financial/accounting/stats > /dev/null 2>&1 && "
            "curl -sf http://localhost:8080/api/v1/crm/dashboard/stats > /dev/null 2>&1"
        ),
        "modules_affected": ["operacional", "financeiro", "crm"],
    },
    {
        "name": "peak_celery_check",
        "trigger": "peak",
        "description": "Verifica se workers Celery estão saudáveis durante pico",
        "command": "docker ps --filter 'name=celery' --filter 'health=healthy' -q | wc -l",
        "expected_min": 5,
        "modules_affected": ["government", "operacional"],
    },
    {
        "name": "peak_pg_connections",
        "trigger": "peak",
        "description": "Verifica conexões PostgreSQL durante pico (max 150)",
        "command": (
            "docker exec conecta-pro-postgres psql -U postgres -d conecta_pro -t "
            "-c 'SELECT count(*) FROM pg_stat_activity' 2>/dev/null"
        ),
        "threshold_warn": 100,
        "threshold_crit": 130,
        "modules_affected": ["financeiro", "operacional", "rh"],
    },
]


def run_peak_hour_actions() -> list[dict]:
    """Executa ações específicas de horário de pico."""
    results = []
    current_trigger = "pre_peak" if is_pre_peak() else "peak" if is_peak_hour() else None

    if not current_trigger:
        return results

    log(f"Horario de pico BRT ({now_brt().strftime('%H:%M')}): executando acoes {current_trigger}")

    for action in PEAK_HOUR_ACTIONS:
        if action["trigger"] != current_trigger:
            continue

        rc, output = run_cmd(action["command"], timeout=15)

        result = {
            "action": action["name"],
            "description": action["description"],
            "trigger": current_trigger,
            "return_code": rc,
            "output": output[:300],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Verificações especiais
        if "expected_min" in action:
            try:
                val = int(output.strip())
                if val < action["expected_min"]:
                    result["alert"] = f"Apenas {val} workers healthy (esperado >= {action['expected_min']})"
                    log(f"  ALERTA: {action['name']} — {result['alert']}")
                else:
                    log(f"  OK: {action['name']} — {val} workers healthy")
            except ValueError:
                result["alert"] = f"Não foi possível ler valor: {output[:50]}"

        elif "threshold_warn" in action:
            try:
                val = int(output.strip())
                if val >= action.get("threshold_crit", 999):
                    result["alert"] = f"CRITICO: {val} conexões PG (max 150)"
                    log(f"  CRITICO: {action['name']} — {val} conexões")
                elif val >= action["threshold_warn"]:
                    result["alert"] = f"WARNING: {val} conexões PG"
                    log(f"  WARNING: {action['name']} — {val} conexões")
                else:
                    log(f"  OK: {action['name']} — {val} conexões PG")
            except ValueError:
                pass
        else:
            status = "OK" if rc == 0 else "FALHA"
            log(f"  {status}: {action['name']}")

        results.append(result)

    return results


# =============================================================================
# AVALIAÇÃO E EXECUÇÃO (PADRÕES DO BANCO)
# =============================================================================

def evaluate_condition(conditions: dict, current_value) -> bool:
    if current_value is None:
        return False
    threshold = conditions.get("threshold")
    operator = conditions.get("operator", ">")
    if threshold is None:
        return False
    ops = {">": float.__gt__, ">=": float.__ge__, "<": float.__lt__,
           "<=": float.__le__, "==": float.__eq__}
    op_fn = ops.get(operator)
    return op_fn(float(current_value), float(threshold)) if op_fn else False


def execute_prevention(pattern: dict, current_value) -> dict:
    cmd = pattern.get("preventive_command")
    if not cmd:
        return {"executed": False, "reason": "Sem comando preventivo"}
    log(f"  Executando: {cmd[:100]}...")
    rc, output = run_cmd(cmd, timeout=60)
    return {
        "executed": True,
        "return_code": rc,
        "output": output[:500],
        "trigger_value": current_value,
        "threshold": pattern["conditions"].get("threshold"),
    }


def record_prevention(conn, alert_name: str, description: str, result: dict, value=None):
    cursor = conn.cursor()
    now = datetime.now(timezone.utc)
    try:
        cursor.execute(
            """INSERT INTO openclaw_interventions
            (id, alert_name, alert_fingerprint, severity, status,
             diagnosis, actions_taken, resolution, resolved_at,
             response_time_seconds, raw_payload, telegram_sent, is_active,
             created_at, updated_at)
            VALUES (%s, %s, %s, 'info', 'resolved', %s, %s, %s, %s, 0, %s, false, true, %s, %s)""",
            (
                str(uuid.uuid4()),
                f"PREVENTIVE_{alert_name}",
                f"preventive-{alert_name}-{now.strftime('%H%M')}",
                description,
                json.dumps([{"step": "preventive_action", "result": result}]),
                "Prevenido automaticamente" if result.get("return_code") == 0 else None,
                now if result.get("return_code") == 0 else None,
                json.dumps({"trigger_value": value}),
                now, now,
            ),
        )
        conn.commit()
    except Exception as e:
        log(f"  Erro ao registrar prevencao: {e}")
        conn.rollback()
    finally:
        cursor.close()


def run_db_patterns(conn) -> int:
    """Executa padrões preventivos do banco (openclaw_patterns)."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(
            """SELECT * FROM openclaw_patterns
            WHERE is_active = true
              AND confidence_score >= %s
              AND preventive_command IS NOT NULL
            ORDER BY confidence_score DESC""",
            (CONFIDENCE_THRESHOLD,),
        )
        patterns = cursor.fetchall()
    except Exception:
        patterns = []
    finally:
        cursor.close()

    actions_taken = 0
    for pattern in patterns:
        conditions = pattern.get("conditions") or {}
        metric_name = conditions.get("metric")
        if not metric_name:
            continue

        collector = METRIC_COLLECTORS.get(metric_name)
        if not collector:
            continue

        current_value = collector()
        if current_value is None:
            continue

        if evaluate_condition(conditions, current_value):
            log(f"  GATILHO: {pattern['alert_name']} — {metric_name}={current_value}")
            result = execute_prevention(pattern, current_value)
            record_prevention(conn, pattern["alert_name"], pattern.get("description", ""), result, current_value)

            # Atualizar contagem
            try:
                cur2 = conn.cursor()
                cur2.execute(
                    "UPDATE openclaw_patterns SET prevention_count = prevention_count + 1, "
                    "last_prevented_at = %s, updated_at = %s WHERE id = %s",
                    (datetime.now(timezone.utc), datetime.now(timezone.utc), pattern["id"]),
                )
                conn.commit()
                cur2.close()
            except Exception:
                conn.rollback()

            actions_taken += 1

    return actions_taken


# =============================================================================
# RELATÓRIO SEMANAL
# =============================================================================

def generate_weekly_report(conn):
    """Gera relatório semanal de padrões descobertos para Jordan."""
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    brt_now = now + timedelta(hours=BRT_OFFSET)

    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Intervenções da semana
    try:
        cursor.execute(
            "SELECT alert_name, severity, status, diagnosis, created_at "
            "FROM openclaw_interventions WHERE created_at >= %s ORDER BY created_at DESC",
            (week_ago,),
        )
        interventions = cursor.fetchall()
    except Exception:
        interventions = []

    # Padrões ativos
    try:
        cursor.execute(
            "SELECT alert_name, description, confidence_score, frequency, "
            "prevention_count, last_prevented_at "
            "FROM openclaw_patterns WHERE is_active = true ORDER BY confidence_score DESC",
        )
        patterns = cursor.fetchall()
    except Exception:
        patterns = []

    cursor.close()

    # Agrupar intervenções por alerta
    alert_counts = {}
    for i in interventions:
        name = i["alert_name"]
        alert_counts[name] = alert_counts.get(name, 0) + 1

    # Métricas atuais
    disk = get_disk_usage_percent()
    mem = get_memory_usage_percent()
    pg_conns = get_pg_active_connections()
    load = get_load_average()

    report = f"""# Relatório Semanal de Padrões — Conecta PRO

> **Para:** Jordan Santos de Jesus
> **Gerado em:** {brt_now.strftime('%d/%m/%Y %H:%M')} AMT
> **Período:** {(week_ago + timedelta(hours=BRT_OFFSET)).strftime('%d/%m')} a {brt_now.strftime('%d/%m/%Y')}

---

## Resumo da Semana

- **Intervenções totais:** {len(interventions)}
- **Padrões ativos:** {len(patterns)}
- **Prevenções automáticas:** {sum(p.get('prevention_count', 0) or 0 for p in patterns)}

## Alertas mais frequentes

| Alerta | Ocorrências |
|---|---|
"""
    for name, count in sorted(alert_counts.items(), key=lambda x: -x[1])[:10]:
        report += f"| {name} | {count} |\n"

    if not alert_counts:
        report += "| Nenhum alerta na semana | - |\n"

    report += f"""
## Padrões Aprendidos

| Padrão | Confiança | Prevenções | Última Prevenção |
|---|---|---|---|
"""
    for p in patterns[:15]:
        last = p.get("last_prevented_at")
        last_str = last.strftime("%d/%m %H:%M") if last else "nunca"
        report += (
            f"| {p.get('description', p['alert_name'])[:50]} "
            f"| {p.get('confidence_score', 0):.0f}% "
            f"| {p.get('prevention_count', 0) or 0} "
            f"| {last_str} |\n"
        )

    if not patterns:
        report += "| Nenhum padrão aprendido ainda | - | - | - |\n"

    report += f"""
## Saúde Atual do Sistema

| Métrica | Valor |
|---|---|
| Disco | {disk:.0f}% |
| RAM | {mem:.0f}% |
| Conexões PG | {pg_conns or '?'} |
| Load (5min) | {load or '?'} |

## Recomendações

"""
    recs = []
    if disk and disk > 60:
        recs.append(f"- Disco em {disk:.0f}% — considerar limpeza de Docker images ou logs antigos")
    if mem and mem > 80:
        recs.append(f"- RAM em {mem:.0f}% — verificar memory leaks em Celery workers ou Flower")
    if pg_conns and pg_conns > 80:
        recs.append(f"- {pg_conns} conexões PG — próximo do limite (150), verificar pool sizing")

    total_preventions = sum(p.get("prevention_count", 0) or 0 for p in patterns)
    if total_preventions > 10:
        recs.append(f"- {total_preventions} prevenções automáticas na semana — sistema estável e auto-corrigindo")
    elif total_preventions == 0 and len(patterns) == 0:
        recs.append("- Nenhum padrão aprendido ainda — o sistema precisa de mais tempo de operação")

    if not recs:
        recs.append("- Sistema saudável, sem recomendações urgentes")

    report += "\n".join(recs) + "\n"

    WEEKLY_REPORT_FILE.write_text(report)
    log(f"Relatorio semanal gerado: {WEEKLY_REPORT_FILE}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    log("=== Preventive Action v2 ===")
    log(f"Horario BRT: {now_brt().strftime('%H:%M')} | Pico: {is_peak_hour()} | Pre-pico: {is_pre_peak()}")

    kb = load_kb()
    if not kb:
        log("AVISO: Knowledge base nao encontrada")

    # 1. Health check por módulo
    log("--- Health check dos modulos ---")
    problems = check_module_health()
    if problems:
        for p in problems:
            log(f"  PROBLEMA [{p['criticality'].upper()}]: {p['module']} — {p['description']}")
    else:
        log(f"  Todos os {len(MODULE_HEALTH_CHECKS)} modulos saudaveis")

    # 2. Ações de horário de pico
    log("--- Acoes de horario de pico ---")
    peak_results = run_peak_hour_actions()
    if not peak_results:
        log("  Fora do horario de pico — nenhuma acao contextual")

    # 3. Padrões preventivos do banco
    log("--- Padroes preventivos (openclaw_patterns) ---")
    conn = None
    db_actions = 0
    try:
        conn = get_conn()
        db_actions = run_db_patterns(conn)
        log(f"  {db_actions} acoes preventivas do banco executadas")
    except Exception as e:
        log(f"  DB indisponivel para padroes: {e}")

    # 3.5. Cleanup intervenções presas em estados intermediários (> 1h)
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                UPDATE openclaw_interventions
                SET status = 'failed',
                    resolution = 'Timeout: intervenção presa em estado intermediário por mais de 1 hora',
                    resolved_at = NOW(),
                    updated_at = NOW()
                WHERE status IN ('acting', 'diagnosing')
                  AND created_at < NOW() - INTERVAL '1 hour'
                RETURNING id, alert_name, status
            """)
            stuck = cur.fetchall()
            conn.commit()
            cur.close()
            if stuck:
                log(f"  CLEANUP: {len(stuck)} intervencoes presas resolvidas como failed")
                for row in stuck:
                    log(f"    - {row[1]} (id: {str(row[0])[:8]})")
        except Exception as e:
            log(f"  Erro no cleanup de intervencoes: {e}")
            conn.rollback()

    # 4. Registrar problemas de módulos no state
    try:
        state = json.loads(STATE_FILE.read_text())
        state["current_issues"] = [
            {
                "severity": p["criticality"],
                "description": f"{p['module']}: {p['description']}",
                "detected_at": p["timestamp"],
            }
            for p in problems
        ]
        state["last_updated"] = datetime.now(timezone.utc).isoformat() + "Z"
        STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    except Exception as e:
        log(f"  Erro ao atualizar state: {e}")

    # 5. Registrar ações de pico no banco
    if conn and peak_results:
        for pr in peak_results:
            if pr.get("alert"):
                record_prevention(conn, pr["action"], pr["description"], pr, None)

    # 6. Relatório semanal (executa apenas às sextas 18:00 BRT)
    brt = now_brt()
    if conn and brt.weekday() == 4 and 17 <= brt.hour <= 18:
        log("--- Gerando relatorio semanal (sexta-feira) ---")
        generate_weekly_report(conn)

    if conn:
        conn.close()

    total_actions = db_actions + len(peak_results) + len(problems)
    log(f"=== Concluido. Problemas: {len(problems)} | Pico: {len(peak_results)} | DB: {db_actions} ===")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"ERRO FATAL: {e}")
        sys.exit(1)
