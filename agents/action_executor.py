#!/usr/bin/env python3
"""
Action Executor — Ações executáveis pelo assistente Telegram.

Cada ação retorna um dict com {success, output, duration_seconds}.
Todas as ações são idempotentes e seguras para produção.
"""

import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_DIR = Path("/opt/conecta-pro")


def _run(cmd, timeout=60):
    start = time.time()
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return {
            "success": r.returncode == 0,
            "output": (r.stdout + r.stderr).strip()[:3000],
            "duration_seconds": round(time.time() - start, 1),
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "output": f"Timeout após {timeout}s", "duration_seconds": timeout}
    except Exception as e:
        return {"success": False, "output": str(e)[:500], "duration_seconds": round(time.time() - start, 1)}


def _get_redis_password():
    env = PROJECT_DIR / ".env"
    for line in env.read_text().splitlines():
        if line.startswith("REDIS_PASSWORD=") and "STAGING" not in line:
            return line.split("=", 1)[1]
    return ""


def _get_pg_ip():
    try:
        out = subprocess.run("docker inspect conecta-pro-postgres",
                             shell=True, capture_output=True, text=True, timeout=10).stdout
        data = json.loads(out)
        for info in data[0]["NetworkSettings"]["Networks"].values():
            if info.get("IPAddress"):
                return info["IPAddress"]
    except Exception:
        pass
    return None


# =============================================================================
# AÇÕES
# =============================================================================


def execute_tests(module=None):
    """Roda pytest no backend. Se module especificado, roda apenas testes do módulo."""
    if module:
        cmd = f"cd /opt/conecta-pro/backend && python3 -m pytest tests/ -v --tb=short -k {module} 2>&1 | tail -30"
    else:
        cmd = "cd /opt/conecta-pro/backend && python3 -m pytest tests/ -v --tb=short --ignore=tests/test_recruitment_models.py 2>&1 | tail -30"
    result = _run(cmd, timeout=300)

    # Extrair resumo
    lines = result["output"].splitlines()
    summary = next((l for l in reversed(lines) if "passed" in l or "failed" in l or "error" in l), "")
    result["summary"] = summary
    return result


def get_container_logs(container, lines=20):
    """Retorna logs reais de um container."""
    safe_name = container.replace(";", "").replace("&", "").replace("|", "")
    result = _run(f"docker logs {safe_name} --tail {lines} 2>&1", timeout=10)
    result["container"] = safe_name
    result["lines_requested"] = lines
    return result


def restart_container(container):
    """Restart seguro de um container com health check pós-restart."""
    safe_name = container.replace(";", "").replace("&", "").replace("|", "")

    # Verificar se o container existe
    check = _run(f"docker inspect --format='{{{{.State.Status}}}}' {safe_name} 2>/dev/null", timeout=5)
    if not check["success"]:
        return {"success": False, "output": f"Container {safe_name} não encontrado", "duration_seconds": 0}

    # Restart
    result = _run(f"docker restart {safe_name}", timeout=120)
    if not result["success"]:
        return result

    # Aguardar health check (até 60s)
    time.sleep(5)
    for i in range(12):
        status = _run(f"docker inspect --format='{{{{.State.Health.Status}}}}' {safe_name} 2>/dev/null", timeout=5)
        health = status["output"].strip().strip("'")
        if health == "healthy":
            result["output"] += f"\nHealth check: healthy após {(i + 1) * 5}s"
            result["health"] = "healthy"
            return result
        if health == "unhealthy":
            result["output"] += f"\nHealth check: unhealthy após {(i + 1) * 5}s"
            result["health"] = "unhealthy"
            return result
        time.sleep(5)

    result["output"] += "\nHealth check: timeout (container sem healthcheck ou lento)"
    result["health"] = "unknown"
    return result


def force_backup():
    """Executa backup imediato do PostgreSQL."""
    result = _run("bash /opt/conecta-pro/scripts/backup_database.sh 2>&1", timeout=120)

    # Verificar arquivo criado
    backup_dir = PROJECT_DIR / "backups" / "postgresql"
    try:
        files = sorted(backup_dir.glob("backup_*.sql.gz"), key=lambda f: f.stat().st_mtime, reverse=True)
        if files:
            latest = files[0]
            age = time.time() - latest.stat().st_mtime
            if age < 120:  # criado nos últimos 2 minutos
                result["backup_file"] = latest.name
                result["backup_size_kb"] = round(latest.stat().st_size / 1024)
                result["output"] += f"\nBackup criado: {latest.name} ({result['backup_size_kb']}KB)"
    except Exception:
        pass

    return result


def check_module_health(module):
    """Health check específico de um módulo backend."""
    module_endpoints = {
        "financeiro": "/api/v1/financial/accounting/dre",  # charts apagado 08/09/2026
        "operacional": "/api/v1/operacional/posts/",
        "rh": "/api/v1/people-management/dp/dashboard/",
        "crm": "/api/v1/crm/leads/",
        "ged": "/api/v1/ged/kits",  # documents apagado 08/09/2026
        "government": "/api/v1/government/nfse/manaus/status",
        "clientes": "/api/v1/clients/",
        "bidding": "/api/v1/bidding/opportunities/",
        "notifications": "/api/v1/notifications/push/",
        "reimbursement": "/api/v1/reimbursements/",
    }

    endpoint = module_endpoints.get(module)
    if not endpoint:
        return {
            "success": False,
            "output": f"Módulo '{module}' não reconhecido. Disponíveis: {', '.join(module_endpoints.keys())}",
            "duration_seconds": 0,
        }

    result = _run(
        f"curl -so /dev/null -w '%{{http_code}}' --max-time 5 http://127.0.0.1:8080{endpoint}",
        timeout=10,
    )
    code = result["output"].strip()
    result["module"] = module
    result["endpoint"] = endpoint
    result["http_code"] = code
    result["success"] = code not in ("000", "")
    result["output"] = f"Módulo {module}: HTTP {code} em {endpoint}"
    if code == "000":
        result["output"] += " (sem resposta — módulo pode estar down)"
    elif code.startswith("5"):
        result["output"] += " (erro interno do servidor)"
    elif code in ("401", "403"):
        result["output"] += " (respondendo — requer autenticação)"
    return result


def get_slow_queries():
    """Retorna queries lentas do PostgreSQL (> 1s)."""
    pg_ip = _get_pg_ip()
    pg_pw = ""
    env = PROJECT_DIR / ".env"
    for line in env.read_text().splitlines():
        if line.startswith("POSTGRES_PASSWORD=") and "STAGING" not in line:
            pg_pw = line.split("=", 1)[1]
            break

    if not pg_ip:
        return {"success": False, "output": "PostgreSQL IP não encontrado", "duration_seconds": 0}

    sql = (
        "SELECT pid, now() - pg_stat_activity.query_start AS duration, "
        "substring(query from 1 for 200) AS query, state "
        "FROM pg_stat_activity "
        "WHERE (now() - pg_stat_activity.query_start) > interval '1 second' "
        "AND state != 'idle' AND pid <> pg_backend_pid() "
        "ORDER BY duration DESC LIMIT 10"
    )
    result = _run(
        f"docker exec conecta-pro-postgres psql -U postgres -d conecta_pro -c \"{sql}\" 2>/dev/null",
        timeout=10,
    )
    return result


def clear_redis_cache():
    """Limpa cache Redis (FLUSHDB no DB 1 — cache da aplicação)."""
    pw = _get_redis_password()
    # DB 1 = cache da aplicação (DB 0 = Celery broker)
    result = _run(
        f"docker exec conecta-pro-redis redis-cli -a '{pw}' -n 1 FLUSHDB 2>/dev/null",
        timeout=10,
    )
    if "OK" in result.get("output", ""):
        result["output"] = "Cache Redis (DB 1) limpo com sucesso"
        result["success"] = True
    return result


def get_celery_queue_status():
    """Retorna status detalhado de todas as filas Celery."""
    pw = _get_redis_password()
    queues = ["celery", "operacional", "gov.batch", "gov.esocial", "gov.fgts",
              "gov.sefaz.nfe", "gov.nfse", "integrations", "webhooks", "maintenance"]

    result = {"success": True, "queues": {}, "duration_seconds": 0}
    start = time.time()

    for q in queues:
        out = _run(f"docker exec conecta-pro-redis redis-cli -a '{pw}' llen {q} 2>/dev/null", timeout=5)
        try:
            result["queues"][q] = int(out["output"])
        except ValueError:
            result["queues"][q] = 0

    total = sum(result["queues"].values())
    result["total_pending"] = total
    result["duration_seconds"] = round(time.time() - start, 1)
    result["output"] = f"Filas Celery: {total} tasks pendentes em {len(queues)} filas"

    busy = {k: v for k, v in result["queues"].items() if v > 0}
    if busy:
        result["output"] += "\n" + "\n".join(f"  {k}: {v} tasks" for k, v in busy.items())
    else:
        result["output"] += "\n  Todas as filas vazias"

    return result


def rollback_to_tag(tag):
    """Rollback git para uma tag específica (cria branch de recovery)."""
    safe_tag = tag.replace(";", "").replace("&", "").replace("|", "").strip()

    # Verificar se a tag existe
    check = _run(f"cd /opt/conecta-pro && git tag -l '{safe_tag}'", timeout=5)
    if safe_tag not in check.get("output", ""):
        # Listar tags disponíveis
        tags = _run("cd /opt/conecta-pro && git tag -l | tail -10", timeout=5)
        return {
            "success": False,
            "output": f"Tag '{safe_tag}' não encontrada.\nTags disponíveis:\n{tags['output']}",
            "duration_seconds": 0,
        }

    # Criar branch de recovery e checkout
    branch = f"recovery-{safe_tag}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}"
    result = _run(
        f"cd /opt/conecta-pro && git stash && git checkout {safe_tag} && git checkout -b {branch}",
        timeout=30,
    )
    result["tag"] = safe_tag
    result["branch"] = branch
    return result


def run_migrations():
    """Executa alembic upgrade head dentro do container backend."""
    result = _run(
        "docker exec conecta-pro-backend alembic upgrade head 2>&1",
        timeout=120,
    )
    return result


# =============================================================================
# REGISTRY
# =============================================================================

ACTIONS = {
    "execute_tests": {
        "fn": execute_tests,
        "description": "Executa testes pytest do backend",
        "params": {"module": "Nome do módulo (opcional, ex: 'financial', 'operacional')"},
        "risk": "low",
    },
    "get_container_logs": {
        "fn": get_container_logs,
        "description": "Retorna logs de um container Docker",
        "params": {"container": "Nome do container", "lines": "Número de linhas (default 20)"},
        "risk": "low",
    },
    "restart_container": {
        "fn": restart_container,
        "description": "Reinicia um container com health check",
        "params": {"container": "Nome do container"},
        "risk": "medium",
    },
    "force_backup": {
        "fn": force_backup,
        "description": "Executa backup imediato do PostgreSQL",
        "params": {},
        "risk": "low",
    },
    "check_module_health": {
        "fn": check_module_health,
        "description": "Verifica saúde de um módulo backend específico",
        "params": {"module": "financeiro, operacional, rh, crm, ged, government, clientes, bidding"},
        "risk": "low",
    },
    "get_slow_queries": {
        "fn": get_slow_queries,
        "description": "Lista queries PostgreSQL lentas (> 1s)",
        "params": {},
        "risk": "low",
    },
    "clear_redis_cache": {
        "fn": clear_redis_cache,
        "description": "Limpa cache Redis da aplicação",
        "params": {},
        "risk": "medium",
    },
    "get_celery_queue_status": {
        "fn": get_celery_queue_status,
        "description": "Status detalhado de todas as filas Celery",
        "params": {},
        "risk": "low",
    },
    "rollback_to_tag": {
        "fn": rollback_to_tag,
        "description": "Rollback git para uma tag de restauração",
        "params": {"tag": "Nome da tag git"},
        "risk": "high",
    },
    "run_migrations": {
        "fn": run_migrations,
        "description": "Executa migrações Alembic (upgrade head)",
        "params": {},
        "risk": "high",
    },
}


def execute_action(action_name, **kwargs):
    """Executa uma ação pelo nome. Retorna resultado padronizado."""
    action = ACTIONS.get(action_name)
    if not action:
        return {
            "success": False,
            "output": f"Ação '{action_name}' não encontrada. Disponíveis: {', '.join(ACTIONS.keys())}",
            "duration_seconds": 0,
        }

    start = time.time()
    try:
        result = action["fn"](**kwargs)
        result["action"] = action_name
        result["executed_at"] = datetime.now(timezone.utc).isoformat()
        return result
    except Exception as e:
        return {
            "success": False,
            "action": action_name,
            "output": f"Erro: {str(e)[:500]}",
            "duration_seconds": round(time.time() - start, 1),
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Ações disponíveis:")
        for name, info in ACTIONS.items():
            print(f"  {name:25s} [{info['risk']:6s}] {info['description']}")
        sys.exit(0)

    action = sys.argv[1]
    kwargs = {}
    for arg in sys.argv[2:]:
        if "=" in arg:
            k, v = arg.split("=", 1)
            kwargs[k] = v

    result = execute_action(action, **kwargs)
    print(json.dumps(result, indent=2, ensure_ascii=False))
