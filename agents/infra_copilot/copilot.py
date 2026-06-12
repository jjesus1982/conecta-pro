#!/usr/bin/env python3
"""
Copiloto de Infra — Conecta PRO. [FASE3-JL 20260612]

Padrao "Jose Luis" para infraestrutura: DETECTA problema real -> DIAGNOSTICA
(dados crus) -> PROPOE runbook -> aguarda APROVACAO humana no Telegram -> executa
SOMENTE comandos da whitelist. Nunca age sozinho. Nunca alucina: tudo que envia
vem de checagens diretas (docker/df/free/curl).

Modos:
  copilot.py detectar   (cron */5min)  — checa, deduplica e notifica incidentes
  copilot.py aprovar    (cron */1min)  — le o Telegram; "APROVAR <id>" executa o runbook
  copilot.py teste      (manual)       — envia mensagem de apresentacao
"""

import json
import logging
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = Path("/opt/conecta-pro/agents/infra_copilot")
STATE = BASE / "state.json"
OFFSET = BASE / "tg_offset.txt"
LOG = "/opt/conecta-pro/logs/infra_copilot.log"

logging.basicConfig(filename=LOG, level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("copilot")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("MONITOR_BOT_TOKEN") or ""
CHAT = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("MONITOR_CHAT_ID") or ""

# Containers em que o copiloto PODE agir (restart/start) apos aprovacao.
# Bancos de dados NUNCA entram aqui (so diagnostico + aviso).
WHITELIST_RESTART = {
    "conecta-pro-backend", "conecta-pro-frontend", "conecta-pro-flower",
    "conecta-pro-celery-beat", "conecta-pro-celery-nfse", "conecta-pro-celery-priority",
    "conecta-pro-celery-sefaz", "conecta-pro-celery-batch",
    "conecta-pro-celery-integrations", "conecta-pro-celery-operacional",
    "chatwoot-fazerai", "chatwoot-fazerai-sidekiq", "baileys-api",
    "erp-loki", "erp-promtail", "erp-redis-exporter", "erp-grafana",
    "erp-prometheus", "erp-alertmanager", "erp-node-exporter",
}
# Criticos que monitoramos mas onde NAO agimos sozinhos:
WATCH_ONLY = {"conecta-pro-postgres", "conecta-pro-redis"}
REPEAT_HOURS = 6  # nao repetir notificacao do mesmo incidente por 6h


def sh(cmd: str, timeout: int = 20) -> str:
    try:
        p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, start_new_session=True)
        out, _ = p.communicate(timeout=timeout)
        return (out or "").strip()
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(p.pid), 9)
        except Exception:
            pass
        return ""
    except Exception:
        return ""


def tg_send(msg: str) -> bool:
    if not TOKEN or not CHAT:
        log.warning("telegram ausente")
        return False
    try:
        data = urllib.parse.urlencode(
            {"chat_id": CHAT, "text": msg[:4000], "parse_mode": "HTML"}
        ).encode()
        req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data=data)
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status == 200
    except Exception as e:  # noqa: BLE001
        log.error("tg_send: %s", e)
        return False


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except Exception:  # noqa: BLE001
        return {"incidentes": {}}


def save_state(st: dict) -> None:
    try:
        STATE.write_text(json.dumps(st, indent=1))
    except Exception as e:  # noqa: BLE001
        log.error("save_state: %s", e)


# ============================== DETECCAO =====================================

def checar() -> list[dict]:
    """Checagens DIRETAS (dados crus). Retorna lista de incidentes."""
    incidentes = []

    # 1) containers criticos parados/unhealthy
    ps = sh("docker ps -a --format '{{.Names}}|{{.Status}}'")
    estados = dict(l.split("|", 1) for l in ps.splitlines() if "|" in l)
    for nome in sorted(WHITELIST_RESTART | WATCH_ONLY):
        st = estados.get(nome, "")
        if not st:
            continue  # container nem existe — nao inventamos incidente
        if st.startswith("Exited") or "unhealthy" in st.lower() or "Restarting" in st:
            diag = sh(f"docker logs --tail 5 {nome} 2>&1")[-500:]
            if nome in WHITELIST_RESTART:
                acao = f"docker restart {nome}"
            else:
                acao = None  # watch-only: diagnostico, sem acao automica
            incidentes.append({
                "id": f"ctr-{nome}",
                "titulo": f"Container <b>{nome}</b>: {st}",
                "diag": diag or "(sem logs)",
                "cmd": acao,
            })

    # 2) disco
    uso = sh("df --output=pcent / | tail -1").strip().rstrip("%")
    if uso.isdigit() and int(uso) >= 85:
        det = sh("du -sh /var/lib/docker /opt/conecta-pro/backups /var/log 2>/dev/null")
        incidentes.append({
            "id": "disk-root",
            "titulo": f"Disco / em <b>{uso}%</b>",
            "diag": det,
            "cmd": "journalctl --vacuum-time=7d && docker builder prune -f --keep-storage 20GB",
        })

    # 3) RAM
    mem = sh("free -m | awk '/^Mem:/{print int($7*100/$2)}'")
    if mem.isdigit() and int(mem) <= 8:
        top = sh("ps -eo comm,rss --sort=-rss | head -6")
        incidentes.append({
            "id": "ram-low",
            "titulo": f"RAM disponivel critica: <b>{mem}%</b>",
            "diag": top,
            "cmd": None,  # decisao humana
        })

    # 4) backend health
    code = sh("curl -sf -o /dev/null -w '%{http_code}' --max-time 10 http://localhost:8080/health || echo FAIL")
    if code != "200":
        diag = sh("docker logs --tail 8 conecta-pro-backend 2>&1")[-600:]
        incidentes.append({
            "id": "backend-health",
            "titulo": f"Backend /health respondeu <b>{code}</b>",
            "diag": diag,
            "cmd": "docker restart conecta-pro-backend",
        })

    return incidentes


def detectar() -> None:
    st = load_state()
    agora = time.time()
    novos = 0
    for inc in checar():
        reg = st["incidentes"].get(inc["id"])
        if reg and agora - reg.get("notificado_em", 0) < REPEAT_HOURS * 3600:
            continue  # ja notificado ha pouco
        st["incidentes"][inc["id"]] = {
            "cmd": inc["cmd"], "titulo": inc["titulo"],
            "notificado_em": agora, "aprovado": False,
        }
        if inc["cmd"]:
            rodape = (f"▶️ Ação proposta: <code>{inc['cmd']}</code>\n"
                      f"Para eu executar, responda: <b>APROVAR {inc['id']}</b>")
        else:
            rodape = "ℹ️ Sem ação automática segura — requer decisão humana."
        tg_send(
            f"🤖 <b>Copiloto de Infra</b> — incidente real detectado\n\n"
            f"{inc['titulo']}\n\n<b>Diagnóstico:</b>\n<pre>{inc['diag'][:800]}</pre>\n\n{rodape}"
        )
        novos += 1
        log.info("incidente notificado: %s", inc["id"])
    # incidentes resolvidos: limpar do estado os que nao estao mais firing
    ativos = {i["id"] for i in checar()}
    for iid in list(st["incidentes"].keys()):
        if iid not in ativos and agora - st["incidentes"][iid].get("notificado_em", 0) > 600:
            del st["incidentes"][iid]
    save_state(st)
    if novos:
        log.info("detectar: %s novos incidentes", novos)


# ============================== APROVACAO ====================================

def aprovar() -> None:
    """Le getUpdates; 'APROVAR <id>' do chat autorizado executa o runbook salvo."""
    if not TOKEN or not CHAT:
        return
    try:
        off = int(OFFSET.read_text().strip())
    except Exception:  # noqa: BLE001
        off = 0
    try:
        with urllib.request.urlopen(
            f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset={off + 1}&timeout=0", timeout=15
        ) as r:
            updates = json.loads(r.read()).get("result", [])
    except Exception as e:  # noqa: BLE001
        log.error("getUpdates: %s", e)
        return
    st = load_state()
    for u in updates:
        off = max(off, u["update_id"])
        msg = u.get("message") or {}
        if str(msg.get("chat", {}).get("id")) != str(CHAT):
            continue  # so o chat autorizado
        texto = (msg.get("text") or "").strip()
        if not texto.upper().startswith("APROVAR "):
            continue
        iid = texto.split(None, 1)[1].strip()
        reg = st["incidentes"].get(iid)
        if not reg:
            tg_send(f"🤖 Não encontrei incidente pendente com id <code>{iid}</code>.")
            continue
        cmd = reg.get("cmd")
        if not cmd or reg.get("aprovado"):
            tg_send(f"🤖 Incidente <code>{iid}</code> sem ação pendente.")
            continue
        # Seguranca: so executa o comando EXATO salvo pelo detector (nunca freeform)
        log.info("APROVADO %s -> %s", iid, cmd)
        reg["aprovado"] = True
        save_state(st)
        out = sh(cmd, timeout=120)
        # re-checagem pos-acao
        time.sleep(8)
        ainda = {i["id"] for i in checar()}
        status = "✅ resolvido" if iid not in ainda else "⚠️ ainda em alerta (verificar manualmente)"
        tg_send(
            f"🤖 <b>Executado</b> (id <code>{iid}</code>):\n<code>{cmd}</code>\n\n"
            f"Saída: <pre>{(out or '(ok)')[:400]}</pre>\nStatus: {status}"
        )
    try:
        OFFSET.write_text(str(off))
    except Exception:  # noqa: BLE001
        pass


def teste() -> None:
    tg_send(
        "🤖 <b>Copiloto de Infra ativado</b> (padrão José Luis)\n\n"
        "A partir de agora: quando um problema REAL acontecer (container parado, "
        "disco cheio, backend fora), eu te mando o diagnóstico cru + a ação proposta. "
        "Você responde <b>APROVAR &lt;id&gt;</b> e eu executo — nunca ajo sozinho.\n\n"
        "Checagens: a cada 5min | Aprovações: lidas a cada 1min."
    )


if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else "detectar"
    BASE.mkdir(parents=True, exist_ok=True)
    if modo == "detectar":
        detectar()
    elif modo == "aprovar":
        aprovar()
    elif modo == "teste":
        teste()
