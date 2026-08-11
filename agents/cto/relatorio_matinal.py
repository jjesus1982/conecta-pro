"""
RelatórioMatinal — Enviado todo dia às 7h para Jordan.
Tom de CTO — direto, inteligente, com contexto de negócio.

Estrutura:
1. Noite tranquila ou incidentes + autocorreções
2. Estado atual do sistema (health + containers + RAM)
3. Mudanças detectadas no negócio (aprendizado contínuo)
4. Snapshot Conecta Mais (clientes, funcionários, alertas)
5. Tickets abertos que requerem Jordan
"""
import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

CTO_DIR      = Path("/opt/conecta-pro/agents/cto")
TICKETS_DIR  = CTO_DIR / "tickets"
MEMORY_DIR   = CTO_DIR / "memory"
KNOWLEDGE_DIR= CTO_DIR / "knowledge"

MONITOR_TOKEN = ""  # pragma: allowlist secret
JORDAN_CHAT   = "5536961034"


def _telegram(msg: str):
    import urllib.request
    url  = f"https://api.telegram.org/bot{MONITOR_TOKEN}/sendMessage"
    data = json.dumps({
        "chat_id": JORDAN_CHAT,
        "text": msg,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"Telegram erro: {e}")


def _run(cmd: str, timeout: int = 10) -> str:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True,
                           text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


def gerar_relatorio() -> str:
    agora    = datetime.now()
    data_fmt = agora.strftime("%d/%m/%Y")
    secoes   = []

    hora_fmt = agora.strftime("%H:%M")

    # ─── CABEÇALHO ───────────────────────────────────────────────────────────
    secoes.append(f"🤖 *CTO — Relatório Matinal*\n📅 {data_fmt} {hora_fmt}\n")

    # ─── 1. NOITE ─────────────────────────────────────────────────────────────
    tickets_noite = []
    autocorrecoes = 0

    for f in sorted(TICKETS_DIR.glob("*.json"), reverse=True):
        try:
            t = json.loads(f.read_text())
            criado = datetime.fromisoformat(t["criado_em"])
            if (agora - criado) < timedelta(hours=10):
                tickets_noite.append(t)
                if t.get("auto_resolvido"):
                    autocorrecoes += 1
        except Exception:
            pass

    if tickets_noite:
        criticos = [
            t for t in tickets_noite
            if t.get("severidade") in ("critica", "alta")
            and not t.get("auto_resolvido")
        ]
        secoes.append(
            f"🌙 *Durante a noite:*\n"
            f"  • {len(tickets_noite)} incidente(s) registrado(s)\n"
            f"  • {autocorrecoes} resolvido(s) automaticamente\n"
            f"  • {len(criticos)} requer(em) sua atenção\n"
        )
    else:
        secoes.append("🌙 *Noite tranquila* — sem incidentes\n")

    # ─── 2. ESTADO DO SISTEMA ─────────────────────────────────────────────────
    health_raw = _run("curl -sf http://127.0.0.1:8080/health")
    try:
        health_data = json.loads(health_raw)
        status = health_data.get("status", "?")
    except Exception:
        status = "verificando"

    ram_pct    = _run("free -m | awk 'NR==2{printf \"%.0f\",$3/$2*100}'") or "?"
    containers = _run("docker ps --filter status=running --format '{{.Names}}' | wc -l") or "?"
    load       = _run("awk '{print $1}' /proc/loadavg") or "?"

    emoji_s = "✅" if status == "healthy" else "⚠️"
    secoes.append(
        f"{emoji_s} *Sistema:* {status}\n"
        f"  🐳 {containers} containers | 💾 RAM {ram_pct}% | Load {load}\n"
    )

    # ─── 3. MUDANÇAS NO NEGÓCIO ───────────────────────────────────────────────
    mudancas_file = MEMORY_DIR / "mudancas_detectadas.json"
    if mudancas_file.exists():
        try:
            historico = json.loads(mudancas_file.read_text())
            recentes = []
            for entry in historico[-10:]:
                ts = datetime.fromisoformat(entry["timestamp"])
                if (agora - ts) < timedelta(hours=10):
                    recentes.extend(entry["mudancas"])

            if recentes:
                secoes.append("📊 *Mudanças detectadas:*")
                for m in recentes[:4]:
                    emoji = {"critica": "🔴", "alta": "⚠️"}.get(m["urgencia"], "ℹ️")
                    secoes.append(f"  {emoji} {m['mensagem']}")
                secoes.append("")
        except Exception:
            pass

    # ─── 4b. TEAM SUPPORT ────────────────────────────────────────────────────
    try:
        import sys as _sys
        _sys.path.insert(0, str(CTO_DIR))
        from team_bridge import TeamBridge
        resumo_team = TeamBridge().resumo_para_cto()
        secoes.append(resumo_team)
    except Exception:
        pass

    # ─── 5. TICKETS ABERTOS ───────────────────────────────────────────────────
    tickets_abertos = []
    for f in sorted(TICKETS_DIR.glob("*.json"), reverse=True)[:30]:
        try:
            t = json.loads(f.read_text())
            if t.get("status") == "aberto" and t.get("requer_jordan"):
                tickets_abertos.append(t)
        except Exception:
            pass

    if tickets_abertos:
        secoes.append(f"📋 *{len(tickets_abertos)} ticket(s) aguardam você:*")
        for t in tickets_abertos[:3]:
            sev_e = {"critica": "🔴", "alta": "🟠", "media": "🟡"}.get(
                t.get("severidade", "media"), "⚪"
            )
            secoes.append(f"  {sev_e} `{t['numero']}`: {t['titulo'][:45]}")
        secoes.append("\n_Responda /tickets para detalhes_")
    else:
        secoes.append("✅ *Nenhum ticket aguardando sua atenção*")

    secoes.append("\n_Precisa de algo? Estou aqui 24h._")
    return "\n".join(secoes)


def executar():
    print(f"[RelatórioMatinal] {datetime.now().strftime('%d/%m %H:%M')}...")
    relatorio = gerar_relatorio()
    _telegram(relatorio)
    print("✅ Relatório enviado ao Telegram")
    return relatorio


if __name__ == "__main__":
    executar()
