"""
RelatórioSemanal — Enviado toda segunda-feira às 8h BRT (11h UTC).
Resumo completo da semana para Jordan.

Estrutura:
1. Headline da semana
2. Incidentes: total, auto-resolvidos, escalados
3. Top 3 problemas críticos
4. Saúde do sistema (agora)
5. O que o CTO aprendeu esta semana
6. Stats runbooks e padrões
7. Recomendação da semana
"""
import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path


CTO_DIR = Path("/opt/conecta-pro/agents/cto")
TICKETS_DIR = CTO_DIR / "tickets"
MEMORY_DIR = CTO_DIR / "memory"

MONITOR_TOKEN = ""  # pragma: allowlist secret
JORDAN_CHAT = "5536961034"


def _telegram(msg: str):
    import urllib.request
    url = (
        f"https://api.telegram.org/"
        f"bot{MONITOR_TOKEN}/sendMessage"
    )
    data = json.dumps({
        "chat_id": JORDAN_CHAT,
        "text": msg,
        "parse_mode": "Markdown",
    }).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


def gerar_relatorio_semanal() -> str:
    """Gera relatório completo dos últimos 7 dias."""
    hoje = datetime.now()
    semana_atras = hoje - timedelta(days=7)
    data_inicio = semana_atras.strftime("%d/%m")
    data_fim = hoje.strftime("%d/%m/%Y")

    secoes = []

    # ─── CABEÇALHO ──────────────────────────────────
    secoes.append(
        f"📊 *Relatório Semanal do CTO*\n"
        f"_{data_inicio} → {data_fim}_\n"
    )

    # ─── 1. TICKETS DA SEMANA ──────────────────────
    tickets_semana = []
    auto_resolvidos = 0
    precisou_jordan = 0
    por_severidade: dict = {}

    if TICKETS_DIR.exists():
        for f in TICKETS_DIR.glob("CTO-*.json"):
            try:
                t = json.loads(f.read_text())
                criado = datetime.fromisoformat(
                    t["criado_em"].replace("Z", "")
                )
                if criado >= semana_atras:
                    tickets_semana.append(t)
                    if t.get("auto_resolvido"):
                        auto_resolvidos += 1
                    if t.get("requer_jordan"):
                        precisou_jordan += 1
                    sev = t.get("severidade", "media")
                    por_severidade[sev] = (
                        por_severidade.get(sev, 0) + 1
                    )
            except Exception:
                pass

    total_tickets = len(tickets_semana)
    taxa_auto = (
        round(auto_resolvidos / total_tickets * 100)
        if total_tickets else 0
    )

    emoji_saude = (
        "🟢" if taxa_auto >= 80
        else "🟡" if taxa_auto >= 50
        else "🔴"
    )

    secoes.append(
        f"{emoji_saude} *Incidentes da semana:*\n"
        f"  Total: `{total_tickets}`\n"
        f"  ✅ Auto-resolvidos: `{auto_resolvidos}` ({taxa_auto}%)\n"
        f"  👤 Precisou Jordan: `{precisou_jordan}`\n"
    )

    if por_severidade:
        _ordem = ["critica", "alta", "media", "baixa", "info"]
        sev_txt = " | ".join(
            f"{s}: {n}"
            for s, n in sorted(
                por_severidade.items(),
                key=lambda x: _ordem.index(x[0])
                if x[0] in _ordem else 99,
            )
        )
        secoes.append(f"  _{sev_txt}_\n")

    # ─── 2. TOP 3 PROBLEMAS ────────────────────────
    criticos = [
        t for t in tickets_semana
        if t.get("severidade") in ("critica", "alta")
    ]
    if criticos:
        secoes.append("🔴 *Top problemas:*")
        for t in criticos[:3]:
            status_e = (
                "✅" if t.get("status") == "resolvido"
                else "⏳"
            )
            secoes.append(
                f"  {status_e} `{t['numero']}`: "
                f"_{t['titulo'][:45]}_"
            )
        secoes.append("")

    # ─── 3. SAÚDE DO SISTEMA ───────────────────────
    def _run(cmd: str) -> str:
        try:
            r = subprocess.run(
                cmd, shell=True, capture_output=True,
                text=True, timeout=10,
            )
            return r.stdout.strip()
        except Exception:
            return "?"

    cpu = _run("cat /proc/loadavg | awk '{print $1}'")
    ram = _run(
        "free -m | awk 'NR==2{printf \"%.0f\","
        "$3/$2*100}'"
    )
    containers = _run(
        "docker ps --filter status=running "
        "--format '{{.Names}}' | wc -l"
    )
    swap_mb = _run("free -m | awk 'NR==3{print $3}'")

    emoji_swap = (
        "🔴" if int(swap_mb or 0) > 3000
        else "⚠️" if int(swap_mb or 0) > 2000
        else "✅"
    )

    secoes.append(
        f"🖥️ *Sistema agora:*\n"
        f"  CPU: `{cpu}` | RAM: `{ram}%` | "
        f"Containers: `{containers}`\n"
        f"  {emoji_swap} Swap: `{swap_mb}MB`\n"
    )

    # ─── 4. O QUE O CTO APRENDEU ───────────────────
    mem_file = MEMORY_DIR / "memoria_longa.json"
    if mem_file.exists():
        try:
            mem = json.loads(mem_file.read_text())
            licoes = mem.get("licoes_aprendidas", [])
            licoes_semana = [
                l for l in licoes
                if datetime.fromisoformat(
                    l["registrado_em"].replace("Z", "")
                ) >= semana_atras
            ]
            if licoes_semana:
                secoes.append("🧠 *Aprendido esta semana:*")
                for l in licoes_semana[:3]:
                    secoes.append(f"  • _{l['licao'][:70]}_")
                secoes.append("")
        except Exception:
            pass

    # ─── 5. RUNBOOKS ───────────────────────────────
    try:
        import sys as _sys
        _sys.path.insert(0, str(CTO_DIR))
        from runbook import RunbookExecutor
        rb = RunbookExecutor()
        stats = rb.resumo()
        if stats.get("total_execucoes", 0) > 0:
            secoes.append(
                f"🔧 *Runbooks:* "
                f"{stats['total_execucoes']} execuções | "
                f"Taxa sucesso: {stats['taxa_sucesso']}%\n"
            )
    except Exception:
        pass

    # ─── 6. PADRÕES APRENDIDOS ─────────────────────
    try:
        import sys as _sys
        _sys.path.insert(
            0, str(Path("/opt/conecta-pro/agents/core"))
        )
        from pattern_learner import PatternLearner
        learner = PatternLearner()
        r = learner.resumo()
        if r.get("padroes_alta_confianca", 0) > 0:
            secoes.append(
                f"📈 *Padrões:* "
                f"{r['total_padroes']} aprendidos | "
                f"{r['padroes_alta_confianca']} alta confiança\n"
            )
    except Exception:
        pass

    # ─── 7. TURNO — como foi a semana ──────────────
    turno_file = MEMORY_DIR / "turno_state.json"
    if turno_file.exists():
        try:
            ts = json.loads(turno_file.read_text())
            ultima_troca = ts.get("ultima_troca", "")
            if ultima_troca:
                secoes.append(
                    f"⏰ Último turno: "
                    f"`{ts.get('turno_atual','?')}` "
                    f"(troca: {ultima_troca[:16]})\n"
                )
        except Exception:
            pass

    # ─── RODAPÉ ────────────────────────────────────
    secoes.append(
        "_Próximo relatório: segunda-feira 08h BRT_\n"
        "_/tickets para detalhes | /turno para estado atual_"
    )

    return "\n".join(secoes)


def executar():
    """Gera e envia relatório semanal."""
    print(
        f"[RelatórioSemanal] "
        f"{datetime.now().strftime('%d/%m %H:%M')}..."
    )
    relatorio = gerar_relatorio_semanal()
    _telegram(relatorio)
    print("✅ Relatório semanal enviado")
    return relatorio


if __name__ == "__main__":
    executar()
