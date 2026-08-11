#!/usr/bin/env python3
"""
CTO Monitor Bot — Bot Telegram bidirecional do CTO Autônomo.

Bot: @conecta_pro_monitor_bot — APAGADO pelo Jordan em 11/08/2026 (nao ha canal Telegram)
Jordan: TELEGRAM_CHAT_ID=5536961034

Comandos:
  /start       Boas-vindas
  /ajuda       Lista de comandos
  /status      Estado geral do sistema
  /tickets     Tickets abertos
  /ticket XXXX Detalhe de um ticket
  /sistema     Métricas do servidor
  /padroes     Padrões aprendidos
  /aprovado    Aprovar ação pendente
  /recusado    Recusar ação pendente

Linguagem natural: Redis caiu? Postgres lento? Celery parou?
"""
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# ─── Paths ────────────────────────────────────────────────────────────────────
PROJECT_DIR = Path("/opt/conecta-pro")
AGENTS_DIR  = PROJECT_DIR / "agents"
CTO_DIR     = AGENTS_DIR / "cto"
CORE_DIR    = AGENTS_DIR / "core"

sys.path.insert(0, str(CTO_DIR))
sys.path.insert(0, str(CORE_DIR))

# ─── Credenciais ──────────────────────────────────────────────────────────────
MONITOR_BOT_TOKEN = os.getenv(
    "MONITOR_BOT_TOKEN",
    "",
)
JORDAN_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "5536961034"))

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [CTO-BOT] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(CTO_DIR / "monitor_bot.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("cto_bot")

# ─── Estado global ────────────────────────────────────────────────────────────
_acao_pendente: Optional[dict] = None  # {"tipo", "cmd", "ticket_num", "conf"}
_last_update_id: int = 0


# ─── Telegram helpers ─────────────────────────────────────────────────────────

def _tg(method: str, payload: dict, timeout: int = 10) -> dict:
    """Chama API Telegram via curl."""
    import urllib.request, urllib.parse
    url = f"https://api.telegram.org/bot{MONITOR_BOT_TOKEN}/{method}"
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(url, data=data,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        logger.error(f"Telegram API error ({method}): {e}")
        return {}


def send(text: str, chat_id: int = JORDAN_CHAT_ID,
         keyboard: Optional[list] = None, parse_mode: str = "Markdown") -> bool:
    payload: dict = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    if keyboard:
        payload["reply_markup"] = {
            "keyboard": [[{"text": k} for k in row] for row in keyboard],
            "one_time_keyboard": True,
            "resize_keyboard": True,
        }
    r = _tg("sendMessage", payload)
    return r.get("ok", False)


def get_updates(offset: int = 0, timeout: int = 3) -> list:
    r = _tg("getUpdates", {"offset": offset, "timeout": timeout, "limit": 10})
    return r.get("result", [])


# ─── CTOBrain (lazy) ──────────────────────────────────────────────────────────
_brain = None

def get_brain():
    global _brain
    if _brain is None:
        try:
            from brain import CTOBrain
            _brain = CTOBrain()
        except Exception as e:
            logger.error(f"CTOBrain load error: {e}")
    return _brain


# ─── AutoRemediator (lazy) ────────────────────────────────────────────────────
_remediator = None

def get_remediator():
    global _remediator
    if _remediator is None:
        try:
            from auto_remediator import AutoRemediator
            _remediator = AutoRemediator()
        except Exception as e:
            logger.error(f"AutoRemediator load error: {e}")
    return _remediator


# ─── Handlers ─────────────────────────────────────────────────────────────────

def cmd_start(chat_id: int):
    send(
        "🤖 *CTO Autônomo Online*\n\n"
        "Olá Jordan! Estou monitorando a Conecta Mais 24h.\n\n"
        "Use /ajuda para ver os comandos disponíveis.",
        chat_id=chat_id,
    )


def cmd_ajuda(chat_id: int):
    send(
        "*Comandos disponíveis:*\n\n"
        "`/status` — Estado geral do sistema\n"
        "`/tickets` — Tickets abertos\n"
        "`/ticket CTO-0001` — Detalhe de um ticket\n"
        "`/sistema` — CPU, RAM, disco, swap\n"
        "`/padroes` — Padrões aprendidos\n"
        "`/diagnostico [tipo]` — Investigar causa raiz\n"
        "`/relatorio` — Relatório matinal agora\n"
        "`/aprender` — Atualizar conhecimento do banco\n"
        "`/anomalias` — Ver mudanças detectadas\n"
        "`/memoria` — Memória de longo prazo\n"
        "`/licoes` — Últimas lições aprendidas\n"
        "`/frageis` — Componentes mais problemáticos\n"
        "`/relatorio_semanal` — Relatório de 7 dias\n"
        "`/visao360` — Visão 360°: correlações técnico-negócio\n"
        "`/propostas` — Propostas proativas do CTO\n"
        "`/agentes` — Status dos 80 agentes (13 módulos)\n"
        "`/modulo [nome]` — Detalhe de um módulo específico\n"
        "`/team` — Resumo executivo do time de suporte\n\n"
        "🔧 *Sprint 6 — Runbooks + Escalada:*\n"
        "`/runbooks` — Ver últimos runbooks executados\n"
        "`/resolver [tipo]` — Executar runbook manualmente\n"
        "   Tipos: RedisDown, SwapHigh, CeleryUnhealthy,\n"
        "          BackendUnhealthy, DiskSpaceLow, PM2ExcessiveRestarts\n"
        "`/escaladas` — Ver escaladas ativas\n\n"
        "📊 *Sprint 7 — Dashboard + Pós-Mortem:*\n"
        "`/posmortem` — Últimos pós-mortems gerados\n"
        "`/dashboard` — Forçar atualização do dashboard ao vivo\n\n"
        "🌙 *Sprint 8 — Turno + Semanal:*\n"
        "`/turno` — Turno atual (dia/noite/fim de semana)\n"
        "`/semanal` — Relatório semanal sob demanda\n\n"
        "🔧 *Sprint 10 — Corretor de Código:*\n"
        "`/correcoes` — Correções aguardando aprovação\n"
        "`/corrigir [desc]` — Propor correção de bug\n"
        "`/corretor` — Status e estatísticas do corretor\n"
        "`aprovar CORR-XXXX` — Aplicar correção aprovada\n"
        "`rejeitar CORR-XXXX` — Cancelar correção\n\n"
        "*Linguagem natural:*\n"
        "Apenas descreva o problema:\n"
        "_Redis caiu_, _Postgres lento_, _Celery parou_\n\n"
        "Quando eu propor uma ação, responda *sim* ou *não*.",
        chat_id=chat_id,
    )


def cmd_status(chat_id: int):
    brain = get_brain()
    if not brain:
        send("❌ CTOBrain indisponível.", chat_id=chat_id)
        return

    try:
        texto = brain.resumo_para_telegram()
        send(texto, chat_id=chat_id)
    except Exception as e:
        send(f"❌ Erro ao gerar status: {e}", chat_id=chat_id)


def cmd_tickets(chat_id: int):
    brain = get_brain()
    if not brain:
        send("❌ CTOBrain indisponível.", chat_id=chat_id)
        return

    abertos = brain.listar_tickets(status="aberto", limit=10)
    if not abertos:
        send("✅ Nenhum ticket aberto.", chat_id=chat_id)
        return

    linhas = [f"📋 *{len(abertos)} ticket(s) aberto(s):*\n"]
    for t in abertos:
        sev_emoji = {"critica": "🔴", "alta": "🟠", "media": "🟡", "baixa": "🟢"}.get(
            t.get("severidade", "media"), "⚪"
        )
        linhas.append(
            f"{sev_emoji} `{t['numero']}` — {t['titulo'][:50]}\n"
            f"   _Cat: {t.get('categoria', '?')} | {t['criado_em'][:10]}_"
        )
    send("\n".join(linhas), chat_id=chat_id)


def cmd_ticket(chat_id: int, numero: str):
    brain = get_brain()
    if not brain:
        send("❌ CTOBrain indisponível.", chat_id=chat_id)
        return

    numero = numero.upper().strip()
    ticket_file = CTO_DIR / "tickets" / f"{numero}.json"
    if not ticket_file.exists():
        send(f"❌ Ticket `{numero}` não encontrado.", chat_id=chat_id)
        return

    t = json.loads(ticket_file.read_text())
    sev_emoji = {"critica": "🔴", "alta": "🟠", "media": "🟡", "baixa": "🟢"}.get(
        t.get("severidade", "media"), "⚪"
    )
    status_emoji = "✅" if t["status"] == "resolvido" else "🔄"

    linhas = [
        f"*{t['numero']}* {sev_emoji}",
        f"*{t['titulo']}*\n",
        f"Status: {status_emoji} {t['status']}",
        f"Categoria: {t.get('categoria', '?')}",
        f"Criado: {t['criado_em'][:16].replace('T', ' ')}",
    ]
    if t.get("causa_raiz"):
        linhas.append(f"\n*Causa:* {t['causa_raiz']}")
    if t.get("solucao_proposta"):
        linhas.append(f"*Solução:* {t['solucao_proposta']}")
    if t.get("resolvido_em"):
        linhas.append(f"Resolvido: {t['resolvido_em'][:16].replace('T', ' ')}")

    hist = t.get("historico", [])[-3:]
    if hist:
        linhas.append(f"\n*Histórico ({len(t['historico'])} entradas):*")
        for h in hist:
            linhas.append(f"  • {h['timestamp'][:16].replace('T', ' ')} — {h['acao'][:60]}")

    send("\n".join(linhas), chat_id=chat_id)


def cmd_sistema(chat_id: int):
    def _r(cmd):
        try:
            return subprocess.run(cmd, shell=True, capture_output=True,
                                  text=True, timeout=10).stdout.strip()
        except Exception:
            return "?"

    load   = _r("cat /proc/loadavg | awk '{print $1, $2, $3}'")
    mem    = _r("free -b | awk '/^Mem:/ {printf \"%.1f/%.1f GB (%.0f%%)\", $3/1073741824, $2/1073741824, $3/$2*100}'")
    disk   = _r("df -h / | tail -1 | awk '{print $3\"/\"$2\" (\"$5\")\"}'")
    swap   = _r("free -b | awk '/^Swap:/ {if($2>0) printf \"%.1f/%.1f GB\", $3/1073741824, $2/1073741824; else print \"sem swap\"}'")
    uptime = _r("uptime -p")

    # Containers críticos
    cnames = ["conecta-pro-backend", "conecta-pro-postgres",
              "conecta-pro-redis", "conecta-pro-frontend"]
    container_lines = []
    for cn in cnames:
        st = _r(f"docker inspect --format '{{{{.State.Status}}}}' {cn} 2>/dev/null")
        emoji = "✅" if st == "running" else "❌"
        container_lines.append(f"  {emoji} `{cn.replace('conecta-pro-','')}` {st or 'N/A'}")

    send(
        f"💻 *Sistema — {datetime.now().strftime('%d/%m %H:%M')}*\n\n"
        f"Load: `{load}`\n"
        f"RAM:  `{mem}`\n"
        f"Disk: `{disk}`\n"
        f"Swap: `{swap}`\n"
        f"Up:   `{uptime}`\n\n"
        "*Containers:*\n" + "\n".join(container_lines),
        chat_id=chat_id,
    )


def cmd_padroes(chat_id: int):
    padroes_file = AGENTS_DIR / "knowledge" / "patterns_learned.json"
    if not padroes_file.exists():
        send("📭 Nenhum padrão aprendido ainda.", chat_id=chat_id)
        return

    try:
        data = json.loads(padroes_file.read_text())
    except Exception as e:
        send(f"❌ Erro ao ler padrões: {e}", chat_id=chat_id)
        return

    if not data:
        send("📭 Nenhum padrão aprendido ainda.", chat_id=chat_id)
        return

    linhas = [f"🧠 *{len(data)} Padrões Aprendidos:*\n"]
    for nome, p in sorted(data.items(), key=lambda x: x[1].get("confidence", 0), reverse=True)[:10]:
        conf = p.get("confidence", 0)
        bar  = "█" * int(conf / 20) + "░" * (5 - int(conf / 20))
        linhas.append(
            f"`{nome}`\n"
            f"  Conf: {bar} {conf:.0f}/100 | Ocorr: {p.get('occurrences', 0)}"
        )
        if p.get("preventive_command"):
            linhas.append(f"  Cmd: `{p['preventive_command'][:50]}`")

    send("\n".join(linhas), chat_id=chat_id)


def handle_natural_language(text: str, chat_id: int):
    """Diagnóstico de linguagem natural + proposta de ação."""
    global _acao_pendente

    brain = get_brain()
    remediator = get_remediator()

    if not brain:
        send("❌ CTOBrain indisponível para diagnóstico.", chat_id=chat_id)
        return

    diag = brain.diagnosticar(text)

    # Criar ticket
    ticket = brain.criar_ticket(
        titulo=text[:60],
        descricao=text,
        severidade=diag.get("urgencia", "media"),
        categoria="incidente",
        causa_raiz=diag.get("causa_raiz", ""),
        solucao_proposta=diag.get("solucao_recomendada", ""),
        auto_resolvido=False,
        requer_jordan=diag.get("requer_jordan", False),
    )

    urgencia = diag.get("urgencia", "media")
    urg_emoji = {"critica": "🔴", "alta": "🟠", "media": "🟡", "baixa": "🟢"}.get(urgencia, "⚪")

    msg_linhas = [
        f"{urg_emoji} *Diagnóstico — {ticket['numero']}*\n",
        f"*Causa:* {diag.get('causa_raiz', 'Não identificada')}",
        f"*Contexto:* {diag.get('contexto_negocio', '')}",
        f"*Solução:* {diag.get('solucao_recomendada', '')}",
    ]

    # Verificar ações disponíveis
    acoes = diag.get("acoes_possiveis", [])
    tipo = _inferir_tipo(text)

    pode_remediar = (
        remediator is not None
        and tipo is not None
        and remediator.pode_remediar(tipo)
        and not diag.get("requer_jordan", False)
    )

    if pode_remediar:
        _acao_pendente = {
            "tipo": tipo,
            "ticket": ticket["numero"],
            "conf": 70.0,
        }
        msg_linhas.append(
            f"\n🤔 *Posso executar a remediação automaticamente.*\n"
            f"Tipo: `{tipo}`\n"
            f"Confirma? Responda *sim* ou *não*"
        )
        send("\n".join(msg_linhas), chat_id=chat_id,
             keyboard=[["sim", "não"]])
    else:
        if acoes:
            msg_linhas.append("\n*Ações manuais sugeridas:*")
            for a in acoes[:3]:
                msg_linhas.append(f"  `{a}`")
        if diag.get("requer_jordan"):
            msg_linhas.append("\n⚠️ *Requer intervenção manual de Jordan.*")
        send("\n".join(msg_linhas), chat_id=chat_id)


def handle_aprovacao(aprovado: bool, chat_id: int):
    """Processa aprovação/recusa de ação pendente."""
    global _acao_pendente

    if not _acao_pendente:
        send("ℹ️ Nenhuma ação pendente no momento.", chat_id=chat_id)
        return

    acao = _acao_pendente
    _acao_pendente = None
    brain = get_brain()
    remediator = get_remediator()

    if not aprovado:
        send(f"✋ Ação recusada. Ticket `{acao['ticket']}` permanece aberto.", chat_id=chat_id)
        if brain:
            brain.atualizar_ticket(acao["ticket"], "Ação recusada por Jordan", "aberto")
        return

    send(f"⚙️ Executando remediação para `{acao['tipo']}`...", chat_id=chat_id)

    if not remediator:
        send("❌ AutoRemediator indisponível.", chat_id=chat_id)
        return

    resultado = remediator.remediar(acao["tipo"], confidence=acao["conf"])

    if resultado["sucesso"]:
        send(
            f"✅ *Remediação concluída!*\n"
            f"Tipo: `{acao['tipo']}`\n"
            f"Tempo: `{resultado.get('tempo_s', 0):.1f}s`\n"
            f"Saída: `{str(resultado.get('saida', ''))[:200]}`",
            chat_id=chat_id,
        )
        if brain:
            brain.atualizar_ticket(
                acao["ticket"],
                f"Remediação executada: {acao['tipo']}",
                "resolvido",
                resultado=str(resultado.get("saida", ""))[:200],
            )
    else:
        send(
            f"❌ *Remediação falhou*\n"
            f"Motivo: {resultado.get('motivo', 'erro desconhecido')}\n"
            f"Ticket `{acao['ticket']}` permanece aberto.",
            chat_id=chat_id,
        )


def _inferir_tipo(texto: str) -> Optional[str]:
    """Mapeia texto livre para tipo de remediação."""
    t = texto.lower()
    if "redis" in t:
        return "RedisDown"
    if any(k in t for k in ["swap", "memoria", "memory", "oom", "ram"]):
        return "SwapHigh"
    if "celery" in t:
        return "CeleryUnhealthy"
    if any(k in t for k in ["postgres", "pg ", "banco", "db "]):
        return "PostgresConnectionLost"
    if any(k in t for k in ["pm2", "frontend", "next"]):
        return "PM2ExcessiveRestarts"
    if any(k in t for k in ["disco", "disk", "espaço", "space"]):
        return "DiskSpaceLow"
    if any(k in t for k in ["cpu", "load", "lento", "slow"]):
        return "HighMemoryUsage"
    return None


# ─── Comandos Sprint 2 ───────────────────────────────────────────────────────

def cmd_diagnostico(chat_id: int, tipo: str):
    """Diagnóstico avançado sob demanda — correlaciona logs, commits e banco."""
    send("🔍 Investigando... aguarde.", chat_id=chat_id)
    brain = get_brain()
    if not brain:
        send("❌ CTOBrain indisponível.", chat_id=chat_id)
        return
    try:
        diag = brain.diagnosticar_avancado(tipo, contexto={"tipo": tipo})
        evidencias = diag.get("evidencias", [])
        msg = (
            f"🔍 *Diagnóstico: {tipo}*\n\n"
            f"*Causa raiz:* {diag.get('causa_raiz','?')[:150]}\n"
        )
        if evidencias:
            msg += "\n*Evidências:*\n"
            for e in evidencias[:3]:
                msg += f"  • {e[:80]}\n"
        acao = diag.get("acao_recomendada", "") or diag.get("solucao_recomendada", "")
        if acao:
            msg += f"\n💡 *Ação:* {acao[:120]}"
        conf = diag.get("confianca", 0)
        if conf:
            msg += f"\n📊 Confiança: {conf}%"
        if diag.get("requer_jordan"):
            msg += "\n⚠️ _Requer ação manual_"
        send(msg, chat_id=chat_id)
    except Exception as e:
        send(f"⚠️ Erro no diagnóstico: {e}", chat_id=chat_id)


def cmd_relatorio(chat_id: int):
    """Envia relatório matinal sob demanda."""
    send("📊 Gerando relatório...", chat_id=chat_id)
    try:
        import sys as _sys
        _sys.path.insert(0, str(CTO_DIR))
        from relatorio_matinal import gerar_relatorio
        relatorio = gerar_relatorio()
        send(relatorio, chat_id=chat_id)
    except Exception as e:
        send(f"⚠️ Erro ao gerar relatório: {e}", chat_id=chat_id)


def cmd_aprender(chat_id: int):
    """Força ciclo de aprendizado contínuo agora."""
    send("🧠 Aprendendo com o banco...", chat_id=chat_id)
    brain = get_brain()
    if not brain:
        send("❌ CTOBrain indisponível.", chat_id=chat_id)
        return
    try:
        resultado  = brain.executar_aprendizado()
        mudancas   = resultado.get("mudancas", [])
        snap_m     = resultado.get("snapshot", {}).get("metricas", {})
        func_ativ  = (snap_m.get("funcionarios") or {}).get("ativos", "?")
        msg = (
            f"✅ *Aprendizado concluído*\n\n"
            f"Snapshot salvo\n"
            f"Funcionários ativos: {func_ativ}\n"
            f"Mudanças detectadas: {len(mudancas)}"
        )
        if mudancas:
            msg += "\n\n*Mudanças:*"
            for m in mudancas[:4]:
                emoji = {"critica": "🔴", "alta": "⚠️"}.get(m["urgencia"], "ℹ️")
                msg += f"\n  {emoji} {m['mensagem']}"
        send(msg, chat_id=chat_id)
    except Exception as e:
        send(f"⚠️ Erro no aprendizado: {e}", chat_id=chat_id)


def cmd_memoria(chat_id: int):
    """Resumo da memória de longo prazo."""
    try:
        from memoria_longa import MemóriaLonga
        mem = MemóriaLonga()
        r = mem.resumo()
        msg = (
            f"🧠 *Memória de longo prazo:*\n\n"
            f"✅ Soluções validadas: {r['solucoes']}\n"
            f"⚠️ Componentes frágeis: {r['componentes_frageis']}\n"
            f"📚 Lições aprendidas: {r['licoes']}\n"
            f"📋 Fatos do sistema: {r['fatos']}\n"
        )
        frageis = r.get("top_frageis", [])
        if frageis:
            msg += "\n*Mais frágeis:*\n"
            for f in frageis:
                msg += f"  • `{f['componente']}`: {f['total_falhas']}x\n"
        send(msg, chat_id=chat_id)
    except Exception as e:
        send(f"⚠️ {e}", chat_id=chat_id)


def cmd_relatorio_semanal(chat_id: int):
    """Relatório semanal de tickets."""
    try:
        from ticket_manager import TicketManager
        tm = TicketManager()
        relatorio = tm.relatorio_periodo(dias=7)
        send(relatorio, chat_id=chat_id)
    except Exception as e:
        send(f"⚠️ {e}", chat_id=chat_id)


def cmd_licoes(chat_id: int):
    """Lista lições aprendidas recentes."""
    try:
        from memoria_longa import MemóriaLonga
        mem = MemóriaLonga()
        licoes = mem.dados.get("licoes_aprendidas", [])[-5:]
        if not licoes:
            send("ℹ️ Sem lições registradas ainda.", chat_id=chat_id)
            return
        msg = "📚 *Últimas lições aprendidas:*\n\n"
        for lc in reversed(licoes):
            msg += f"• _{lc['licao'][:80]}_\n"
            msg += f"  `{lc['registrado_em'][:10]}`\n\n"
        send(msg, chat_id=chat_id)
    except Exception as e:
        send(f"⚠️ {e}", chat_id=chat_id)


def cmd_frageis(chat_id: int):
    """Lista componentes mais frágeis."""
    try:
        from memoria_longa import MemóriaLonga
        mem = MemóriaLonga()
        frageis = mem.componentes_mais_frageis(5)
        if not frageis:
            send("✅ Sem componentes frágeis registrados.", chat_id=chat_id)
            return
        msg = "⚠️ *Componentes mais frágeis:*\n\n"
        for c in frageis:
            msg += (
                f"🔧 `{c['componente']}`: "
                f"{c['total_falhas']} falhas\n"
            )
        send(msg, chat_id=chat_id)
    except Exception as e:
        send(f"⚠️ {e}", chat_id=chat_id)


def cmd_anomalias(chat_id: int):
    """Lista mudanças e anomalias detectadas recentemente."""
    f = CTO_DIR / "memory" / "mudancas_detectadas.json"
    if not f.exists():
        send("ℹ️ Nenhuma anomalia registrada ainda.", chat_id=chat_id)
        return
    try:
        historico = json.loads(f.read_text())
        if not historico:
            send("✅ Sem anomalias registradas.", chat_id=chat_id)
            return
        recentes = historico[-5:]
        msg = "📈 *Anomalias recentes:*\n\n"
        for entry in recentes:
            ts = entry["timestamp"][:16].replace("T", " ")
            msg += f"_{ts}_\n"
            for m in entry["mudancas"][:3]:
                emoji = {"critica": "🔴", "alta": "⚠️"}.get(m["urgencia"], "ℹ️")
                msg += f"  {emoji} {m['mensagem']}\n"
            msg += "\n"
        send(msg, chat_id=chat_id)
    except Exception as e:
        send(f"⚠️ Erro: {e}", chat_id=chat_id)


def cmd_visao360(chat_id: int):
    """Visão 360°: correlaciona eventos técnicos com impacto de negócio."""
    try:
        from visao_360 import gerar_visao_360
        texto = gerar_visao_360()
        send(texto, chat_id=chat_id)
    except Exception as e:
        send(f"⚠️ Visão 360° erro: {e}", chat_id=chat_id)


def cmd_propostas(chat_id: int):
    """CTO proativo: lista propostas de melhoria detectadas agora."""
    try:
        from proatividade import gerar_listagem_propostas
        texto = gerar_listagem_propostas()
        send(texto, chat_id=chat_id)
    except Exception as e:
        send(f"⚠️ Propostas erro: {e}", chat_id=chat_id)


# ─── Loop principal ───────────────────────────────────────────────────────────

def processar_update(update: dict):
    """Processa um update do Telegram."""
    msg = update.get("message", {})
    chat_id = msg.get("chat", {}).get("id")
    text    = msg.get("text", "").strip()

    if not chat_id or not text:
        return

    # Segurança: só Jordan pode usar
    if chat_id != JORDAN_CHAT_ID:
        send("⛔ Acesso restrito.", chat_id=chat_id)
        logger.warning(f"Acesso negado para chat_id={chat_id}")
        return

    logger.info(f"Mensagem recebida: {text[:80]!r}")

    tl = text.lower().strip()

    # Aprovação de ação pendente
    if tl in ("sim", "s", "yes", "aprovado", "/aprovado"):
        handle_aprovacao(True, chat_id)
        return
    if tl in ("não", "nao", "n", "no", "recusado", "/recusado"):
        handle_aprovacao(False, chat_id)
        return

    # Comandos
    if tl.startswith("/start"):
        cmd_start(chat_id)
    elif tl.startswith("/ajuda") or tl.startswith("/help"):
        cmd_ajuda(chat_id)
    elif tl.startswith("/status"):
        cmd_status(chat_id)
    elif tl.startswith("/tickets"):
        cmd_tickets(chat_id)
    elif tl.startswith("/ticket"):
        parts = text.split(maxsplit=1)
        if len(parts) > 1:
            cmd_ticket(chat_id, parts[1])
        else:
            send("Uso: `/ticket CTO-0001`", chat_id=chat_id)
    elif tl.startswith("/sistema"):
        cmd_sistema(chat_id)
    elif tl.startswith("/padroes"):
        cmd_padroes(chat_id)
    elif tl.startswith("/diagnostico"):
        parts = text.split(maxsplit=1)
        tipo = parts[1] if len(parts) > 1 else "geral"
        cmd_diagnostico(chat_id, tipo)
    elif tl.startswith("/relatorio"):
        cmd_relatorio(chat_id)
    elif tl.startswith("/aprender"):
        cmd_aprender(chat_id)
    elif tl.startswith("/anomalias"):
        cmd_anomalias(chat_id)
    elif tl.startswith("/memoria"):
        cmd_memoria(chat_id)
    elif tl.startswith("/relatorio_semanal"):
        cmd_relatorio_semanal(chat_id)
    elif tl.startswith("/licoes"):
        cmd_licoes(chat_id)
    elif tl.startswith("/frageis"):
        cmd_frageis(chat_id)
    elif tl.startswith("/visao360"):
        cmd_visao360(chat_id)
    elif tl.startswith("/propostas"):
        cmd_propostas(chat_id)
    elif tl.startswith("/agentes"):
        cmd_agentes(chat_id)
    elif tl.startswith("/modulo"):
        parts = text.split(maxsplit=1)
        if len(parts) > 1:
            cmd_modulo(chat_id, parts[1])
        else:
            send("Uso: `/modulo operacional`", chat_id=chat_id)
    elif tl.startswith("/team"):
        cmd_team(chat_id)
    elif tl.startswith("/autoevolucao"):
        cmd_autoevolucao(chat_id)
    elif tl.startswith("/auditar"):
        cmd_auditar(chat_id)
    elif tl.startswith("/posmortem"):
        cmd_posmortem(chat_id)
    elif tl.startswith("/dashboard"):
        cmd_dashboard(chat_id)
    elif tl.startswith("/runbooks"):
        cmd_runbooks(chat_id)
    elif tl.startswith("/resolver"):
        parts = text.split(maxsplit=1)
        if len(parts) > 1:
            cmd_resolver(chat_id, parts[1].strip())
        else:
            send(
                "Uso: `/resolver [tipo]`\n\n"
                "Tipos disponíveis:\n"
                "`RedisDown` | `SwapHigh` | `CeleryUnhealthy`\n"
                "`BackendUnhealthy` | `DiskSpaceLow` | `PM2ExcessiveRestarts`",
                chat_id=chat_id,
            )
    elif tl.startswith("/escaladas"):
        cmd_escaladas(chat_id)
    elif tl.startswith("/turno"):
        cmd_turno(chat_id)
    elif tl.startswith("/semanal"):
        cmd_semanal(chat_id)
    elif tl.startswith("/conhecimento"):
        cmd_conhecimento(chat_id)
    elif tl.startswith("/buscar "):
        termo = text.split(" ", 1)[1].strip()
        cmd_buscar(chat_id, termo)
    elif tl.startswith("/tabela "):
        nome = text.split(" ", 1)[1].strip()
        cmd_tabela(chat_id, nome)
    elif tl.startswith("/endpoint "):
        path = text.split(" ", 1)[1].strip()
        cmd_endpoint(chat_id, path)
    elif tl.startswith("/integracao "):
        nome = text.split(" ", 1)[1].strip()
        cmd_integracao(chat_id, nome)
    elif tl.startswith("/predicoes") or tl.startswith("/tendencias"):
        cmd_predicoes(chat_id)
    # Sprint 10 — Corretor de Código
    elif tl.startswith("/correcoes"):
        cmd_correcoes(chat_id)
    elif tl.startswith("/corrigir"):
        parts = text.split(maxsplit=1)
        if len(parts) > 1:
            cmd_corrigir(chat_id, parts[1].strip())
        else:
            send("Uso: `/corrigir [descrição do bug]`", chat_id=chat_id)
    elif tl.startswith("/corretor"):
        cmd_corretor(chat_id)
    elif tl.lower().startswith("aprovar corr-"):
        analise_id = text.split(maxsplit=1)[1].strip().upper()
        cmd_aprovar_correcao(chat_id, analise_id)
    elif tl.lower().startswith("rejeitar corr-"):
        analise_id = text.split(maxsplit=1)[1].strip().upper()
        cmd_rejeitar_correcao(chat_id, analise_id)
    else:
        # Linguagem natural
        handle_natural_language(text, chat_id)


# ─── Comandos Sprint 8 ───────────────────────────────────────────────────────

def cmd_turno(chat_id: int):
    """Status do turno atual."""
    try:
        from turno import Turno
        t = Turno()
        send(f"⏰ *Turno atual*\n\n{t.resumo()}", chat_id=chat_id)
    except Exception as e:
        send(f"⚠️ {e}", chat_id=chat_id)


def cmd_semanal(chat_id: int):
    """Envia relatório semanal agora."""
    send("📊 Gerando relatório semanal...", chat_id=chat_id)
    try:
        from relatorio_semanal import gerar_relatorio_semanal
        rel = gerar_relatorio_semanal()
        send(rel, chat_id=chat_id)
    except Exception as e:
        send(f"⚠️ {e}", chat_id=chat_id)


# ─── Comandos Sprint 5 ───────────────────────────────────────────────────────

def cmd_agentes(chat_id: int):
    """Status consolidado dos 80 agentes em 13 módulos."""
    brain = get_brain()
    if not brain:
        send("❌ CTOBrain indisponível.", chat_id=chat_id)
        return
    try:
        resumo = brain.resumo_team_support()
        send(resumo, chat_id=chat_id)
    except Exception as e:
        send(f"⚠️ Erro: {e}", chat_id=chat_id)


def cmd_modulo(chat_id: int, nome: str):
    """Status detalhado de um módulo específico por nome."""
    brain = get_brain()
    if not brain:
        send("❌ CTOBrain indisponível.", chat_id=chat_id)
        return
    try:
        status = brain.status_modulo(nome)
        send(status, chat_id=chat_id)
    except Exception as e:
        send(f"⚠️ Erro: {e}", chat_id=chat_id)


def cmd_team(chat_id: int):
    """Resumo executivo do time de suporte com estatísticas do TeamBridge."""
    brain = get_brain()
    if not brain:
        send("❌ CTOBrain indisponível.", chat_id=chat_id)
        return
    try:
        resumo = brain.resumo_team_support()

        # Adicionar estatísticas do estado interno do bridge
        sys.path.insert(0, str(CTO_DIR))
        from team_bridge import TeamBridge
        bridge = TeamBridge()
        estado = bridge.estado

        msg = (
            f"🏢 *Team Support — Visão Executiva*\n\n"
            f"{resumo}\n"
            f"─────────────────\n"
            f"Ciclos processados: `{estado.get('total_ciclos', 0)}`\n"
            f"Tickets criados: `{estado.get('tickets_criados', 0)}`\n"
            f"Alertas escalados: `{estado.get('alertas_escalados', 0)}`\n"
        )
        modulos_problema = estado.get("modulos_com_falha", {})
        if modulos_problema:
            msg += "\n*Módulos com falha recorrente:*\n"
            for mod, cont in sorted(modulos_problema.items(), key=lambda x: -x[1])[:3]:
                msg += f"  ⚠️ `{mod}`: {cont}x\n"
        send(msg, chat_id=chat_id)
    except Exception as e:
        send(f"⚠️ Erro: {e}", chat_id=chat_id)


# ─── Comandos Sprint 9 ───────────────────────────────────────────────────────

def cmd_autoevolucao(chat_id: int):
    """Relatório de auto-evolução do sistema."""
    brain = get_brain()
    if not brain:
        send("❌ CTOBrain indisponível.", chat_id=chat_id)
        return
    try:
        rel = brain.relatorio_evolucao()
        send(rel, chat_id=chat_id)
    except Exception as e:
        send(f"⚠️ Erro: {e}", chat_id=chat_id)


def cmd_auditar(chat_id: int):
    """Executa auditoria completa agora."""
    send("🔬 Executando auditoria completa...", chat_id=chat_id)
    brain = get_brain()
    if not brain:
        send("❌ CTOBrain indisponível.", chat_id=chat_id)
        return
    try:
        resultado = brain.auditoria_completa()
        send(resultado, chat_id=chat_id)
    except Exception as e:
        send(f"⚠️ Erro: {e}", chat_id=chat_id)


# ─── Comandos Sprint 7 ───────────────────────────────────────────────────────


def cmd_posmortem(chat_id: int):
    """Lista pós-mortems recentes."""
    try:
        sys.path.insert(0, str(CTO_DIR))
        from pos_mortem import PósMortem
        pms = PósMortem().listar(5)
        if not pms:
            send("ℹ️ Nenhum pós-mortem gerado ainda.\n"
                 "_Pós-mortems são criados automaticamente quando um ticket fecha._",
                 chat_id=chat_id)
            return
        linhas = ["📋 *Últimos pós-mortems:*\n"]
        for pm in pms:
            emoji = "✅" if pm.get("auto_resolvido") else "🔧"
            linhas.append(
                f"{emoji} *{pm['numero']}*\n"
                f"  _{pm['titulo'][:45]}_\n"
                f"  ⏱ {pm['duracao']}\n"
            )
        send("\n".join(linhas), chat_id=chat_id)
    except Exception as e:
        send(f"⚠️ {e}", chat_id=chat_id)


def cmd_dashboard(chat_id: int):
    """Força atualização do dashboard ao vivo."""
    send("📊 Atualizando dashboard com dados ao vivo...", chat_id=chat_id)
    try:
        r = subprocess.run(
            "python3 /opt/conecta-pro/agents/dashboard_api.py",
            shell=True, capture_output=True, text=True, timeout=45,
        )
        if r.returncode == 0:
            # Parse output for key metrics
            linhas = [l for l in r.stdout.splitlines() if "✅" in l]
            msg = "✅ *Dashboard atualizado!*\n\n" + "\n".join(linhas)
            send(msg, chat_id=chat_id)
        else:
            send(f"⚠️ Erro: {r.stderr[:150]}", chat_id=chat_id)
    except Exception as e:
        send(f"⚠️ {e}", chat_id=chat_id)


# ─── Comandos Sprint 6 ───────────────────────────────────────────────────────

def cmd_runbooks(chat_id: int):
    """Histórico dos últimos runbooks executados."""
    brain = get_brain()
    if not brain:
        send("❌ CTOBrain indisponível.", chat_id=chat_id)
        return
    try:
        resumo = brain.resumo_runbooks(limit=5)
        send(resumo, chat_id=chat_id)
    except Exception as e:
        send(f"⚠️ Erro: {e}", chat_id=chat_id)


def cmd_resolver(chat_id: int, tipo: str):
    """Executa runbook manualmente para um tipo de problema."""
    TIPOS_VALIDOS = {
        "RedisDown", "SwapHigh", "CeleryUnhealthy",
        "BackendUnhealthy", "DiskSpaceLow", "PM2ExcessiveRestarts",
    }
    if tipo not in TIPOS_VALIDOS:
        send(
            f"❌ Tipo `{tipo}` inválido.\n\n"
            f"Tipos disponíveis:\n"
            + "\n".join(f"`{t}`" for t in sorted(TIPOS_VALIDOS)),
            chat_id=chat_id,
        )
        return

    send(f"🔧 Executando runbook `{tipo}`... aguarde.", chat_id=chat_id)
    brain = get_brain()
    if not brain:
        send("❌ CTOBrain indisponível.", chat_id=chat_id)
        return

    try:
        sys.path.insert(0, str(CTO_DIR))
        from runbook import RunbookExecutor
        rb = RunbookExecutor()
        resultado = rb.executar(tipo)
        msg = rb.resumo_telegram(resultado)
        send(msg, chat_id=chat_id)

        # Atualizar ticket se já existir ou criar novo
        if resultado.resolvido:
            ticket = brain.criar_ticket(
                titulo=f"Runbook manual: {tipo}",
                descricao=f"Executado manualmente via /resolver",
                severidade="media",
                categoria="remediacao_manual",
                causa_raiz=f"Disparado por Jordan via Telegram",
                solucao_proposta=resultado.mensagem,
                auto_resolvido=True,
            )
            logger.info(f"[Sprint6] Runbook manual {tipo}: {ticket.get('numero')} resolvido")
        elif resultado.requer_jordan:
            send(
                f"⚠️ Runbook `{tipo}` não conseguiu resolver.\n"
                f"Intervenção manual necessária.\n"
                f"Mensagem: {resultado.mensagem[:200]}",
                chat_id=chat_id,
            )
    except Exception as e:
        send(f"⚠️ Erro ao executar runbook: {e}", chat_id=chat_id)


def cmd_escaladas(chat_id: int):
    """Lista escaladas ativas."""
    brain = get_brain()
    if not brain:
        send("❌ CTOBrain indisponível.", chat_id=chat_id)
        return
    try:
        sys.path.insert(0, str(CTO_DIR))
        from escalada import Escalada
        esc = Escalada()
        esc.escaladas = esc._carregar()
        msg = esc.resumo_telegram()
        send(msg, chat_id=chat_id)
    except Exception as e:
        send(f"⚠️ Erro ao listar escaladas: {e}", chat_id=chat_id)


# ─── Comandos Sprint 0 — Conhecimento Total ──────────────────────────────────

def cmd_conhecimento(chat_id: int):
    """Resumo do que o CTO conhece sobre o sistema."""
    brain = get_brain()
    if not brain:
        send("❌ Brain não disponível", chat_id=chat_id)
        return
    resumo = brain.resumo_conhecimento()
    send(resumo, chat_id=chat_id)


def cmd_buscar(chat_id: int, termo: str):
    """Busca qualquer coisa no sistema."""
    send(f"🔍 Buscando `{termo}`...", chat_id=chat_id)
    brain = get_brain()
    if not brain:
        send("❌ Brain não disponível", chat_id=chat_id)
        return
    try:
        resultado = brain.buscar_no_sistema(termo)
        msg = f"🔍 *Resultados para '{termo}':*\n\n"

        codigo = resultado.get("codigo", [])
        if codigo:
            msg += f"*Código ({len(codigo)} arquivos):*\n"
            for r in codigo[:3]:
                msg += f"  📁 `{r['arquivo']}`\n"
                for f in r.get("funcoes", [])[:2]:
                    msg += f"    • `{f['nome']}` linha {f['linha']}\n"

        endpoints = resultado.get("endpoints", [])
        if endpoints:
            msg += f"\n*Endpoints:*\n"
            for e in endpoints[:3]:
                msg += f"  `{e['method']} {e['path']}`\n"

        grep = resultado.get("grep", [])
        if grep:
            msg += f"\n*Arquivos (grep):*\n"
            for g in grep[:3]:
                short = g.replace("/opt/conecta-pro/backend/", "")
                msg += f"  `{short}`\n"

        if not codigo and not endpoints and not grep:
            msg += "_Nenhum resultado encontrado_"

        send(msg, chat_id=chat_id)
    except Exception as e:
        send(f"⚠️ {e}", chat_id=chat_id)


def cmd_tabela(chat_id: int, nome: str):
    """Info de uma tabela do banco."""
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).parent))
        from conhecimento_total import ConhecimentoTotal
        ct = ConhecimentoTotal()
        info = ct.buscar_tabela(nome)

        if isinstance(info, dict) and "colunas" in info:
            colunas = info["colunas"]
            registros = info.get("total_registros", 0)
            msg = (f"🗄️ *Tabela: {nome}*\n\n"
                   f"Registros: `{registros:,}`\n"
                   f"Colunas: `{len(colunas)}`\n\n"
                   f"*Colunas:*\n")
            for col in colunas[:12]:
                null = "?" if col.get("is_nullable") == "YES" else ""
                msg += f"  `{col['column_name']}`: {col['data_type']}{null}\n"
            send(msg, chat_id=chat_id)
        elif isinstance(info, dict) and info:
            msg = f"🗄️ *Tabelas com '{nome}':*\n\n"
            for k, v in list(info.items())[:5]:
                msg += f"  `{k}`: {v.get('total_registros', 0):,} registros\n"
            send(msg, chat_id=chat_id)
        else:
            send(f"❌ Tabela '{nome}' não encontrada", chat_id=chat_id)
    except Exception as e:
        send(f"⚠️ {e}", chat_id=chat_id)


def cmd_endpoint(chat_id: int, path: str):
    """Onde um endpoint está implementado."""
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).parent))
        from conhecimento_total import ConhecimentoTotal
        ct = ConhecimentoTotal()
        endpoints = ct.buscar_endpoint(path)

        if not endpoints:
            send(f"❌ Nenhum endpoint com '{path}'", chat_id=chat_id)
            return
        msg = f"🔗 *Endpoints com '{path}':*\n\n"
        for e in endpoints[:5]:
            msg += f"`{e['method']} {e['path']}`\n"
            arq = e.get("arquivo", "?").replace("modules/", "")
            msg += f"  📁 `{arq}`\n\n"
        send(msg, chat_id=chat_id)
    except Exception as e:
        send(f"⚠️ {e}", chat_id=chat_id)


def cmd_integracao(chat_id: int, nome: str):
    """Info sobre uma integração externa."""
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).parent))
        from conhecimento_total import ConhecimentoTotal
        ct = ConhecimentoTotal()
        info = ct.info_integracao(nome)

        if isinstance(info, dict) and "descricao" in info:
            msg = (f"🔌 *Integração: {nome}*\n\n"
                   f"_{info['descricao']}_\n\n"
                   f"Tipo: `{info.get('tipo', '?')}`\n"
                   f"Arquivos: `{len(info.get('arquivos', []))}`\n"
                   f"Funções: `{len(info.get('funcoes', []))}`\n\n")
            creds = info.get("credenciais_necessarias", [])
            if creds:
                msg += "*Credenciais:*\n"
                for c in creds:
                    msg += f"  • `{c}`\n"
            urls = info.get("endpoints_externos", [])
            if urls:
                msg += "*Endpoints externos:*\n"
                for u in urls[:3]:
                    msg += f"  • `{u[:60]}`\n"
            send(msg, chat_id=chat_id)
        else:
            send(f"❌ Integração '{nome}' não encontrada\n\nDisponíveis: cora, inter, solides, nfse, esocial, reinf, sefaz, redis, celery, telegram, govbr", chat_id=chat_id)
    except Exception as e:
        send(f"⚠️ {e}", chat_id=chat_id)


# ─── Comandos Sprint 10 — Corretor de Código ────────────────────────────────

def cmd_correcoes(chat_id: int):
    """Lista correções aguardando aprovação de Jordan."""
    brain = get_brain()
    if not brain:
        send("❌ CTOBrain indisponível.", chat_id=chat_id)
        return
    try:
        pendentes = brain.correcoes_pendentes()
        if not pendentes:
            send("✅ Nenhuma correção aguardando aprovação.", chat_id=chat_id)
            return
        linhas = [f"🔧 *{len(pendentes)} correção(ões) aguardando:*\n"]
        for p in pendentes[:5]:
            risco = p.get("risco", {})
            emoji = risco.get("emoji", "⚠️")
            nivel = risco.get("nivel", "?")
            linhas.append(
                f"{emoji} `{p['analise_id']}`\n"
                f"  _{p['descricao'][:60]}_\n"
                f"  Risco: {nivel}\n"
            )
        linhas.append("_Responda_ `aprovar CORR-XXXX` _ou_ `rejeitar CORR-XXXX`")
        send("\n".join(linhas), chat_id=chat_id)
    except Exception as e:
        send(f"⚠️ Erro: {e}", chat_id=chat_id)


def cmd_corrigir(chat_id: int, descricao: str):
    """Propõe correção de bug sob demanda de Jordan."""
    send(
        f"🔍 Analisando bug...\n_{descricao[:80]}_\n\nAguarde.",
        chat_id=chat_id,
    )
    brain = get_brain()
    if not brain:
        send("❌ CTOBrain indisponível.", chat_id=chat_id)
        return
    try:
        analise = brain.propor_correcao(descricao=descricao)
        if analise.get("erro"):
            send(
                f"⚠️ Análise falhou:\n_{analise['erro']}_\n\n"
                f"Dica: forneça o arquivo e o trecho exato:\n"
                f"`/corrigir [desc] | arquivo.py | errado → correto`",
                chat_id=chat_id,
            )
    except Exception as e:
        send(f"⚠️ Erro na análise: {e}", chat_id=chat_id)


def cmd_corretor(chat_id: int):
    """Status e estatísticas do corretor de código."""
    brain = get_brain()
    if not brain:
        send("❌ CTOBrain indisponível.", chat_id=chat_id)
        return
    try:
        msg = brain.resumo_corretor()
        send(msg, chat_id=chat_id)
    except Exception as e:
        send(f"⚠️ Erro: {e}", chat_id=chat_id)


def cmd_aprovar_correcao(chat_id: int, analise_id: str):
    """Aplica correção aprovada por Jordan."""
    send(
        f"✅ Aprovado! Aplicando `{analise_id}`...\n"
        f"Backup → Sintaxe → Testes → Deploy → Health\n"
        f"Acompanhe aqui.",
        chat_id=chat_id,
    )
    brain = get_brain()
    if not brain:
        send("❌ CTOBrain indisponível.", chat_id=chat_id)
        return
    try:
        resultado = brain.aprovar_correcao(analise_id)
        if resultado.get("sucesso"):
            send(
                f"✅ *{analise_id} aplicado com sucesso!*\n"
                f"Todos os testes passaram. Backend saudável.",
                chat_id=chat_id,
            )
        elif resultado.get("revertido"):
            send(
                f"⚠️ *{analise_id} foi revertido*\n"
                f"Algo falhou — arquivo restaurado automaticamente.",
                chat_id=chat_id,
            )
        elif resultado.get("ok") is False:
            send(f"❌ {resultado.get('msg', 'Erro desconhecido')}", chat_id=chat_id)
    except Exception as e:
        send(f"⚠️ Erro ao aplicar: {e}", chat_id=chat_id)


def cmd_rejeitar_correcao(chat_id: int, analise_id: str):
    """Cancela correção rejeitada por Jordan."""
    brain = get_brain()
    if not brain:
        send("❌ CTOBrain indisponível.", chat_id=chat_id)
        return
    try:
        brain.rejeitar_correcao(analise_id)
        send(
            f"↩️ *Correção `{analise_id}` cancelada.*\n"
            f"Nenhuma alteração foi feita.",
            chat_id=chat_id,
        )
    except Exception as e:
        send(f"⚠️ Erro: {e}", chat_id=chat_id)


def run():
    global _last_update_id
    logger.info("CTO Monitor Bot iniciando...")

    # Notificação de startup
    brain = get_brain()
    if brain:
        try:
            resumo = brain.resumo_para_telegram()
            send(
                f"🚀 *CTO Autônomo — Sprint 2 Online*\n\n"
                f"{resumo}\n\n"
                f"Novos: /diagnostico /relatorio /aprender /anomalias\n"
                f"Use /ajuda para todos os comandos.",
            )
            logger.info("Startup notification enviada.")
        except Exception as e:
            logger.error(f"Startup notification error: {e}")
    else:
        send("🤖 CTO Monitor Bot online. CTOBrain indisponível — verificar logs.")

    logger.info(f"Polling getUpdates a cada 3s para chat_id={JORDAN_CHAT_ID}")

    while True:
        try:
            updates = get_updates(offset=_last_update_id + 1)
            for upd in updates:
                _last_update_id = upd["update_id"]
                processar_update(upd)
        except KeyboardInterrupt:
            logger.info("Bot encerrado por KeyboardInterrupt.")
            break
        except Exception as e:
            logger.error(f"Loop error: {e}")
        time.sleep(3)


if __name__ == "__main__":
    run()


# ─── Comandos Sprint 11 ───────────────────────────────────────────────────────

def cmd_predicoes(chat_id: int):
    """Preview de tendências e predições."""
    brain = get_brain()
    if not brain:
        send("❌ CTOBrain indisponível.", chat_id=chat_id)
        return
    try:
        preview = brain.predicoes_atuais()
        resumo = brain.resumo_predicao()
        msg = preview
        if resumo:
            msg += (
                f"\n\n📈 *Preditor:*\n"
                f"  Coletas: `{resumo.get('total_coletas', 0)}`\n"
                f"  Alertas gerados: `{resumo.get('total_alertas', 0)}`\n"
                f"  Histórico: `{resumo.get('cobertura_horas', 0)}h`"
            )
        send(msg, chat_id=chat_id)
    except Exception as e:
        send(f"⚠️ Erro: {e}", chat_id=chat_id)
