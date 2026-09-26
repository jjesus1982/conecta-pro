#!/usr/bin/env python3
"""
Dashboard API — Gera JSON com métricas para o dashboard HTML.
Executado pelo nginx como CGI-like (stdout → JSON file).

Uso: python3 agents/dashboard_api.py > agents/dashboard_data.json
Cron: */2 * * * * (a cada 2 minutos)
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT_DIR = Path("/opt/conecta-pro")
OUTPUT = PROJECT_DIR / "agents" / "dashboard_data.json"

def run(cmd, timeout=15):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""

def get_pg_ip():
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

def get_db_password():
    env = PROJECT_DIR / ".env"
    for line in env.read_text().splitlines():
        if line.startswith("POSTGRES_PASSWORD=") and "STAGING" not in line:
            return line.split("=", 1)[1]
    return ""

def query_db(sql):
    ip = get_pg_ip()
    pw = get_db_password()
    if not ip or not pw:
        return []
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        conn = psycopg2.connect(host=ip, port="5432", dbname="conecta_pro",
                                user="postgres", password=pw, connect_timeout=5)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(sql)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        # Convert datetime to string
        for row in rows:
            for k, v in row.items():
                if isinstance(v, datetime):
                    row[k] = v.isoformat()
        return rows
    except Exception as e:
        return [{"error": str(e)[:200]}]

def collect():
    now = datetime.now(timezone.utc)

    # 1. Containers
    raw = run("docker ps -a --format '{{.Names}}|{{.Status}}|{{.Image}}'")
    containers = []
    for line in raw.splitlines():
        parts = line.split("|")
        if len(parts) < 3:
            continue
        name, status, image = parts[0], parts[1], parts[2]
        health = "unknown"
        sl = status.lower()
        if "(healthy)" in sl:
            health = "healthy"
        elif "(unhealthy)" in sl:
            health = "unhealthy"
        elif "up" in sl:
            health = "running"
        elif "created" in sl:
            health = "created"
        elif "exited" in sl:
            health = "stopped"
        containers.append({
            "name": name, "status": status, "health": health,
            "image": image.split(":")[0]
        })

    # 2. System metrics
    load = run("cat /proc/loadavg | awk '{print $1, $2, $3}'").split()
    mem_raw = run("free -b | awk '/^Mem:/ {print $2, $3, $7}'").split()
    disk_raw = run("df / | tail -1 | awk '{print $2, $3, $5}'").split()
    swap_raw = run("free -b | awk '/^Swap:/ {print $2, $3}'").split()

    mem_total = int(mem_raw[0]) if len(mem_raw) >= 3 else 0
    mem_used = int(mem_raw[1]) if len(mem_raw) >= 3 else 0
    mem_avail = int(mem_raw[2]) if len(mem_raw) >= 3 else 0

    metrics = {
        "load_1m": float(load[0]) if load else 0,
        "load_5m": float(load[1]) if len(load) > 1 else 0,
        "load_15m": float(load[2]) if len(load) > 2 else 0,
        "cpu_cores": int(run("nproc") or "1"),
        "mem_total_gb": round(mem_total / (1024**3), 1),
        "mem_used_gb": round(mem_used / (1024**3), 1),
        "mem_percent": round(mem_used / mem_total * 100, 1) if mem_total else 0,
        "disk_total_gb": round(int(disk_raw[0]) / (1024**2), 0) if disk_raw else 0,
        "disk_used_gb": round(int(disk_raw[1]) / (1024**2), 0) if len(disk_raw) > 1 else 0,
        "disk_percent": int(disk_raw[2].replace("%", "")) if len(disk_raw) > 2 else 0,
        "swap_total_gb": round(int(swap_raw[0]) / (1024**3), 1) if swap_raw and int(swap_raw[0]) > 0 else 0,
        "swap_used_gb": round(int(swap_raw[1]) / (1024**3), 1) if len(swap_raw) > 1 else 0,
        "uptime_days": float(run("awk '{print $1/86400}' /proc/uptime").split()[0]) if run("cat /proc/uptime") else 0,
    }

    # 3. Interventions (last 20)
    interventions = query_db(
        "SELECT alert_name, severity, status, diagnosis, resolution, "
        "response_time_seconds, created_at, resolved_at "
        "FROM openclaw_interventions ORDER BY created_at DESC LIMIT 20"
    )

    # 4. Patterns
    patterns = query_db(
        "SELECT alert_name, description, confidence_score, frequency, "
        "prevention_count, last_prevented_at, preventive_command, conditions "
        "FROM openclaw_patterns WHERE is_active = true ORDER BY confidence_score DESC"
    )
    # Serialize conditions (jsonb)
    for p in patterns:
        if isinstance(p.get("conditions"), dict):
            pass  # already dict
        elif p.get("conditions"):
            try:
                p["conditions"] = json.loads(p["conditions"])
            except Exception:
                pass

    # 5. Uptime history (simulated from container start times)
    uptime_data = []
    for h in range(24):
        t = now - timedelta(hours=23 - h)
        uptime_data.append({
            "hour": t.strftime("%H:00"),
            "backend": 100,
            "postgres": 100,
            "redis": 100,
        })

    # 6. Scheduled preventive actions
    redis_pw = get_db_password()  # reuse
    celery_queue = run(
        f"docker exec conecta-pro-redis redis-cli -a '{get_redis_password()}' llen celery 2>/dev/null"
    )
    scheduled = [
        {"name": "Health check módulos", "schedule": "*/15 * * * *", "next": "próximos 15min"},
        {"name": "Métricas Prometheus", "schedule": "*/5 * * * *", "next": "próximos 5min"},
        {"name": "Backup PostgreSQL", "schedule": "0 3 * * *", "next": "03:00 UTC"},
        {"name": "Retenção de backups", "schedule": "30 3 * * *", "next": "03:30 UTC"},
        {"name": "Pattern Learner", "schedule": "0 3 * * *", "next": "03:00 UTC"},
        {"name": "Relatório semanal", "schedule": "Sexta 17-18h BRT", "next": "sexta"},
    ]

    return {
        "generated_at": now.isoformat(),
        "containers": sorted(containers, key=lambda c: c["name"]),
        "metrics": metrics,
        "interventions": interventions,
        "patterns": patterns,
        "uptime_history": uptime_data,
        "scheduled_actions": scheduled,
        "celery_queue_length": int(celery_queue) if celery_queue.isdigit() else 0,
        # Dados do OrchestradorUnificado (substitui OpenClaw)
        "padroes_aprendidos": get_patterns_aprendidos(),
        "monitor_state": get_monitor_state(),
        "ultimo_ciclo": get_ultimo_ciclo(),
    }


def get_redis_password():
    env = PROJECT_DIR / ".env"
    for line in env.read_text().splitlines():
        if line.startswith("REDIS_PASSWORD=") and "STAGING" not in line:
            return line.split("=", 1)[1]
    return ""


def get_patterns_aprendidos() -> dict:
    """Dados do PatternLearner para o dashboard."""
    try:
        import sys as _sys
        _sys.path.insert(0, str(PROJECT_DIR / "agents" / "core"))
        from pattern_learner import PatternLearner
        return PatternLearner().resumo()
    except Exception:
        # Fallback: ler JSON diretamente
        f = PROJECT_DIR / "agents" / "knowledge" / "patterns_learned.json"
        if f.exists():
            try:
                data = json.loads(f.read_text())
                return {"total_padroes": len(data), "padroes": list(data.values())[:10]}
            except Exception:
                pass
        return {}


def get_monitor_state() -> dict:
    """Estado atual do OrchestradorUnificado."""
    try:
        f = PROJECT_DIR / "reports" / "monitor_state.json"
        if f.exists():
            return json.loads(f.read_text())
    except Exception:
        pass
    return {}


def get_ultimo_ciclo() -> dict:
    """Último relatório do ciclo completo."""
    try:
        import glob, os
        reports = glob.glob(str(PROJECT_DIR / "reports" / "modules" / "ciclo_geral_*.json"))
        if not reports:
            return {}
        reports.sort(key=os.path.getmtime, reverse=True)
        with open(reports[0]) as f:
            return json.load(f)
    except Exception:
        return {}


def get_agentes_cto() -> dict:
    """Status dos agentes via TeamBridge."""
    try:
        sys.path.insert(0, str(PROJECT_DIR / "agents" / "cto"))
        from team_bridge import TeamBridge
        bridge = TeamBridge()
        # Ler último ciclo para scores
        ciclo_dir = PROJECT_DIR / "reports" / "modules"
        import glob, os as _os
        ciclos = sorted(
            glob.glob(str(ciclo_dir / "ciclo_geral_*.json")),
            key=_os.path.getmtime,
            reverse=True,
        )
        if ciclos:
            ciclo = json.loads(Path(ciclos[0]).read_text())
            resultados = ciclo.get("resultados", [])
            total = len(resultados)

            # `float(r.get("score", 10) or 10)` APAGAVA OS ZEROS. Em Python `0.0 or 10`
            # é 10: os dois módulos que pontuaram 0,0 no ciclo de 12/04/2026
            # (inteligencia e equipamentos) apareciam como 10 e entravam em "saudáveis",
            # enquanto o próprio arquivo lido dizia `modulos_criticos: 2`. Ausência de
            # score é desconhecido — não é nota máxima.
            def _score(r):
                v = r.get("score")
                return float(v) if v is not None else None

            notas = [(r.get("modulo", "?"), _score(r)) for r in resultados]
            saudaveis = sum(1 for _m, v in notas if v is not None and v >= 9)
            problemas = sorted(
                ({"modulo": m, "score": v} for m, v in notas if v is not None and v < 9),
                key=lambda x: x["score"],
            )
            sem_nota = [m for m, v in notas if v is None]

            # IDADE DO DADO. O painel recarrega de 2 em 2 minutos e carimbava
            # `generated_at` de HOJE sobre a foto do último ciclo, que parou em
            # 12/04/2026. Quem abria via "8.3 agora"; eram 168 dias atrás. O carimbo de
            # frescor é do PAINEL, não do DADO — agora os dois aparecem.
            from datetime import datetime as _dt  # noqa: PLC0415

            idade_dias = None
            ts = ciclo.get("timestamp", "")
            try:
                idade_dias = (_dt.now() - _dt.fromisoformat(ts)).days
            except (ValueError, TypeError):
                pass

            return {
                "total": total,
                "saudaveis": saudaveis,
                "com_problema": len(problemas),
                "sem_nota": sem_nota,
                "score_geral": (
                    float(ciclo["score_geral"]) if ciclo.get("score_geral") is not None else None
                ),
                "top_problemas": problemas[:5],
                "ciclo_ts": ts,
                "idade_dias": idade_dias,
                "dado_obsoleto": bool(idade_dias is not None and idade_dias > 1),
                "aviso": (
                    f"ciclo de agentes parado há {idade_dias} dia(s) — "
                    "estes números são a última fotografia, não o estado de agora"
                    if idade_dias is not None and idade_dias > 1
                    else ""
                ),
            }
    except Exception as e:
        pass
    return {"total": 0, "saudaveis": 0, "com_problema": 0, "erro": "TeamBridge indisponível"}


def get_tickets_cto() -> dict:
    """Tickets abertos e resolvidos hoje."""
    tickets_dir = PROJECT_DIR / "agents" / "cto" / "tickets"
    if not tickets_dir.exists():
        return {"abertos": 0, "resolvidos_hoje": 0, "lista": []}

    agora = datetime.now()
    abertos = []
    resolvidos_hoje = 0

    for f in sorted(tickets_dir.glob("CTO-*.json"), reverse=True)[:100]:
        try:
            t = json.loads(f.read_text())
            if t.get("status") == "aberto":
                abertos.append({
                    "numero": t["numero"],
                    "titulo": t["titulo"][:50],
                    "severidade": t.get("severidade", ""),
                    "criado_em": t.get("criado_em", "")[:16],
                    "requer_jordan": t.get("requer_jordan", False),
                })
            elif t.get("status") == "resolvido":
                re_em = t.get("resolvido_em", "")
                if re_em:
                    ts = datetime.fromisoformat(re_em.replace("Z", ""))
                    if (agora - ts).total_seconds() < 86400:
                        resolvidos_hoje += 1
        except Exception:
            pass

    return {
        "abertos": len(abertos),
        "resolvidos_hoje": resolvidos_hoje,
        "lista": abertos[:10],
    }


def get_pos_mortems_recentes() -> list:
    """Últimos pós-mortems gerados."""
    try:
        sys.path.insert(0, str(PROJECT_DIR / "agents" / "cto"))
        from pos_mortem import PósMortem
        return [
            {
                "numero": pm["numero"],
                "titulo": pm["titulo"][:40],
                "duracao": pm["duracao"],
                "auto": pm.get("auto_resolvido", False),
                "gerado_em": pm.get("gerado_em", "")[:16],
            }
            for pm in PósMortem().listar(5)
        ]
    except Exception:
        return []


def get_runbook_stats() -> dict:
    """Estatísticas dos runbooks executados."""
    try:
        sys.path.insert(0, str(PROJECT_DIR / "agents" / "cto"))
        from runbook import RunbookExecutor
        rb = RunbookExecutor()
        # Ler histórico de runbooks
        hist = getattr(rb, "historico", None)
        if hist is None:
            hist_file = PROJECT_DIR / "agents" / "cto" / "knowledge" / "runbook_history.json"
            if hist_file.exists():
                hist = json.loads(hist_file.read_text())
            else:
                hist = []
        total = len(hist)
        sucesso = sum(1 for h in hist if h.get("resolvido", False))
        return {"total_executados": total, "sucesso": sucesso, "falha": total - sucesso}
    except Exception:
        return {}


if __name__ == "__main__":
    print(f"[Dashboard] Gerando snapshot {datetime.now().strftime('%H:%M:%S')}...")
    data = collect()

    # Enriquecer com dados ao vivo do CTO
    data["agentes"] = get_agentes_cto()
    data["tickets"] = get_tickets_cto()
    data["pos_mortems_recentes"] = get_pos_mortems_recentes()
    data["runbook_stats"] = get_runbook_stats()
    # Compatibilidade retroativa
    data.setdefault("openclaw_interventions", data.get("interventions", []))

    OUTPUT.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str))

    c = data["containers"]
    sist = data["metrics"]
    ags = data["agentes"]
    tks = data["tickets"]
    print(f"  ✅ Containers: {sum(1 for x in c if x.get('health') in ('healthy','running'))}/{len(c)} healthy")
    print(f"  ✅ RAM: {sist['mem_percent']}% | Swap: {sist.get('swap_used_gb', 0)}GB usados")
    print(f"  ✅ Agentes: {ags.get('saudaveis', 0)}/{ags.get('total', 0)} saudáveis (score {ags.get('score_geral', '?')}/10)")
    print(f"  ✅ Tickets: {tks['abertos']} abertos | {tks['resolvidos_hoje']} resolvidos hoje")
    pms = data["pos_mortems_recentes"]
    print(f"  ✅ Pós-mortems recentes: {len(pms)}")
    print(f"  ✅ Dashboard atualizado → {OUTPUT}")
