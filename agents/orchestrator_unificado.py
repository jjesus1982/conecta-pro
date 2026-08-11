"""
OrchestradorUnificado — Sistema único de monitoramento do Conecta PRO.

Substitui:
  - orchestrator_geral.py  (ciclo 30min, 13 orquestradores)
  - skills_agent.py        (ciclo 30min, containers + endpoints + DB)
  - monitor_heartbeat.sh   (ciclo 6h, CPU/RAM/Disco/Uptime)

Modos (sys.argv[1]):
  rapido    — 5min:  containers + endpoints críticos, silencioso se OK
  completo  — 30min: rapido + 13 orquestradores + banco + Telegram
  heartbeat — 6h:    rapido + CPU/RAM/Disco/Uptime/PM2/Redis + Telegram

Uma única fonte de verdade no Telegram.
"""

import importlib.machinery
import importlib.util
import json
import logging
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
AGENTS_CORE = ROOT / "agents" / "core"
AGENTS_MOD = ROOT / "agents" / "modules"
REPORTS_DIR = ROOT / "reports" / "modules"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
Path(ROOT / "logs").mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(ROOT / "agents"))
sys.path.insert(0, str(AGENTS_CORE))
sys.path.insert(0, str(AGENTS_MOD))

# ── Estado persistente (skills_agent legacy) ──────────────────────────────────
try:
    from monitor_state import (
        registrar_ciclo,
        houve_regressao,
        get_tendencia,
        get_resumo_estado,
        load_state,
    )
    MONITOR_STATE_OK = True
except ImportError as e:
    print(f"[monitor_state] indisponível: {e}")
    def registrar_ciclo(s, ok, fail, bugs): return {}
    def houve_regressao(s): return False, 0.0, 0.0
    def get_tendencia(): return "→"
    def get_resumo_estado(): return ""
    def load_state(): return {}
    MONITOR_STATE_OK = False

try:
    from regression_detector import analisar_e_alertar
    REGRESSION_OK = True
except ImportError as e:
    print(f"[regression_detector] indisponível: {e}")
    def analisar_e_alertar(score, modulos): return {}
    REGRESSION_OK = False

# ── PatternLearner + AutoRemediator (herdeiros do OpenClaw) ───────────────────
try:
    from pattern_learner import PatternLearner
    from auto_remediator import AutoRemediator
    _LEARNER = PatternLearner()
    _REMEDIATOR = AutoRemediator()
    CONHECIMENTO_OK = True
except ImportError as e:
    print(f"[conhecimento] indisponível: {e}")
    _LEARNER = None
    _REMEDIATOR = None
    CONHECIMENTO_OK = False

# ── CTOBrain (Sprint 1 — conhecimento do negócio + tickets) ───────────────────
try:
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).parent / "cto"))
    from brain import CTOBrain
    _CTO_BRAIN = CTOBrain()
    CTO_BRAIN_OK = True
except Exception as e:
    print(f"[cto_brain] indisponível: {e}")
    _CTO_BRAIN = None
    CTO_BRAIN_OK = False

# ── TeamBridge (Sprint 5 — CTO ↔ 80 agentes) ─────────────────────────────────
try:
    from team_bridge import TeamBridge
    _TEAM_BRIDGE = TeamBridge()
    TEAM_BRIDGE_OK = True
except Exception as e:
    print(f"[team_bridge] indisponível: {e}")
    _TEAM_BRIDGE = None
    TEAM_BRIDGE_OK = False

# ── Turno (Sprint 8 — comportamento dia/noite) ────────────────────────────────
try:
    _cto_dir = str(Path(__file__).parent / "cto")
    if _cto_dir not in sys.path:
        sys.path.insert(0, _cto_dir)
    from turno import Turno
    _TURNO = Turno()
    _TURNO.verificar_troca_turno()
    TURNO_OK = True
except Exception as e:
    print(f"[turno] indisponível: {e}")
    _TURNO = None
    TURNO_OK = False

# ── Carrega base classes do .pyc se .py ausente (orchestrator_geral legacy) ───
def _load_pyc(name: str, pyc_path: Path):
    loader = importlib.machinery.SourcelessFileLoader(name, str(pyc_path))
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


for _mod_name in ("base_agent", "base_orchestrator"):
    if _mod_name not in sys.modules:
        _src = AGENTS_CORE / f"{_mod_name}.py"
        _pyc = AGENTS_CORE / "__pycache__" / f"{_mod_name}.cpython-312.pyc"
        if not _src.exists() and _pyc.exists():
            _load_pyc(_mod_name, _pyc)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("monitor_unificado")

# ── Configuração ──────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get(
    "MONITOR_BOT_TOKEN",
    "",
)
# Aceita MONITOR_CHAT_ID (skills_agent legacy) ou TELEGRAM_CHAT_ID (orchestrator_geral legacy)
CHAT_ID = os.environ.get("MONITOR_CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID", "5536961034")
API_BASE = "http://127.0.0.1:8080/api/v1"

# Containers críticos (skills_agent)
CRITICAL_CONTAINERS = [
    "conecta-pro-backend",
    "conecta-pro-frontend",
    "conecta-pro-postgres",
    "conecta-pro-redis",
]

# Endpoints por módulo para ciclo rápido (skills_agent)
ENDPOINT_CHECKS = {
    "Operacional": [
        "/operacional/posts/",
        "/operacional/scales/",
        "/operacional/shifts/",
    ],
    "GED": [
        "/ged/documents",
        "/ged/kits",
    ],
    "Financeiro": [
        "/financial/accounting/cost-centers",
    ],
    "DP/RH": [
        "/people-management/hr/employees?page_size=1",
    ],
    "Portal": [
        "/people-management/portal/auth/me",
    ],
    "IA": [
        "/ai/bartolo/health",
    ],
}

# 13 orquestradores de módulo (orchestrator_geral)
ORCHESTRATORS = [
    ("departamento_pessoal", "orch_dp"),
    ("recursos_humanos", "orch_rh"),
    ("ponto_eletronico", "orch_ponto"),
    ("financeiro", "orch_financeiro"),
    ("fiscal_contabil", "orch_fiscal"),
    ("operacional", "orch_operacional"),
    ("ged", "orch_ged"),
    ("inteligencia", "orch_inteligencia"),
    ("negocios", "orch_negocios"),
    ("saude_ocupacional", "orch_saude_ocupacional"),
    ("portais", "orch_portais"),
    ("equipamentos", "orch_equipamentos"),
    ("administrativo", "orch_administrativo"),
]

# ── Telegram ──────────────────────────────────────────────────────────────────

def telegram(texto: str) -> bool:
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = json.dumps(
            {"chat_id": CHAT_ID, "text": texto, "parse_mode": "HTML"}
        ).encode()
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read()).get("ok", False)
    except Exception as e:
        logger.error(f"[telegram] {e}")
        return False


# ── Token ─────────────────────────────────────────────────────────────────────
_LOGIN_CMD = [
    "curl", "-sf", "-X", "POST",
    "http://127.0.0.1:8080/api/v1/auth/login",
    "-H", "Content-Type: application/x-www-form-urlencoded",
    "-d", "username=jjesus@conectamais.pro&password=Jordan0612",
]


def _fazer_login(timeout: int = 15) -> str:
    try:
        r = subprocess.run(_LOGIN_CMD, capture_output=True, text=True, timeout=timeout)
        return json.loads(r.stdout).get("access_token", "")
    except Exception:
        return ""


def _obter_token_com_retry(max_tentativas: int = 4) -> str:
    for tentativa in range(max_tentativas):
        token = _fazer_login()
        if token:
            logger.info(f"✅ Token obtido (tentativa {tentativa + 1})")
            return token
        if tentativa < max_tentativas - 1:
            espera = 65 * (tentativa + 1)
            logger.warning(f"[TOKEN] Rate limit — aguardando {espera}s...")
            time.sleep(espera)
    logger.error("[TOKEN] Falhou após todas as tentativas")
    return ""


def _token_valido(token: str) -> bool:
    if not token:
        return False
    try:
        req = urllib.request.Request(
            f"{API_BASE}/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


def _injetar_token(token: str) -> None:
    """Monkey-patcha BaseAgent e BaseOrchestrator com o token compartilhado."""
    _t = token
    try:
        import base_agent
        import base_orchestrator
        base_agent.BaseAgent.obter_token = lambda self: setattr(self, "token", _t) or _t
        base_orchestrator.BaseOrchestrator._obter_token_compartilhado = lambda self: _t
    except Exception as e:
        logger.warning(f"[inject_token] {e}")


def obter_token_compartilhado() -> str:
    token = _obter_token_com_retry()
    if token:
        _injetar_token(token)
        logger.info("✅ Token injetado em BaseAgent + BaseOrchestrator")
    return token


# ── Helpers HTTP ──────────────────────────────────────────────────────────────

def http_get(path: str, token: str) -> tuple:
    try:
        req = urllib.request.Request(
            f"{API_BASE}{path}",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception:
        return 0, {}


# ── Checks do skills_agent ────────────────────────────────────────────────────

def check_containers() -> dict:
    """Verifica containers críticos (Skill 07)."""
    try:
        out = subprocess.check_output(
            ["docker", "ps", "--format", "{{.Names}}|{{.Status}}"], timeout=10
        ).decode()
    except Exception:
        return {"ok": 0, "fail": list(CRITICAL_CONTAINERS), "total": len(CRITICAL_CONTAINERS)}

    running = {}
    for line in out.strip().splitlines():
        if "|" in line:
            name, status = line.split("|", 1)
            running[name.strip()] = status.strip()

    ok = [c for c in CRITICAL_CONTAINERS if c in running and "Up" in running[c]]
    fail = [c for c in CRITICAL_CONTAINERS if c not in ok]
    return {"ok": len(ok), "fail": fail, "total": len(CRITICAL_CONTAINERS)}


def check_endpoints(token: str) -> dict:
    """Verifica endpoints por módulo (Skill 03)."""
    results = {}
    for modulo, endpoints in ENDPOINT_CHECKS.items():
        ok_count = 0
        errors = []
        for ep in endpoints:
            code, _ = http_get(ep, token)
            if code in (200, 201, 204) or code == 401:
                ok_count += 1
            else:
                errors.append(f"{ep} → {code}")
        total = len(endpoints)
        score = round((ok_count / total) * 10, 1) if total else 0
        results[modulo] = {"ok": ok_count, "total": total, "score": score, "errors": errors}
    return results


def check_database() -> dict:
    """Verifica banco de dados (Skill 05)."""
    try:
        out = subprocess.check_output(
            [
                "docker", "exec", "conecta-pro-postgres",
                "psql", "-U", "postgres", "-d", "conecta_pro",
                "-c", "SELECT COUNT(*) FROM users;",
            ],
            timeout=10,
        ).decode()
        lines = [l.strip() for l in out.splitlines() if l.strip().lstrip("-").isdigit()]
        users = int(lines[0]) if lines else -1
        return {"ok": True, "users": users}
    except Exception as e:
        return {"ok": False, "error": str(e)[:60]}


def check_recent_errors() -> dict:
    """Conta erros 500 nas últimas 200 linhas do log (Skill 01, versão rápida)."""
    try:
        out = subprocess.check_output(
            ["docker", "logs", "--tail", "200", "conecta-pro-backend"],
            timeout=15, stderr=subprocess.STDOUT,
        ).decode()
        errors_500 = out.count("500 Internal Server Error")
        return {"errors_500": errors_500}
    except Exception:
        return {"errors_500": -1}


def score_emoji(s: float) -> str:
    if s >= 9:
        return "🟢"
    if s >= 7:
        return "🟡"
    if s >= 5:
        return "🟠"
    return "🔴"


# ── Informações do sistema (heartbeat) ────────────────────────────────────────

def info_sistema() -> dict:
    info = {}
    try:
        r = subprocess.run(
            "top -bn1 | grep 'Cpu' | awk '{print $2}'",
            shell=True, capture_output=True, text=True,
        )
        info["cpu_pct"] = float(r.stdout.strip().replace("%", "") or 0)
    except Exception:
        info["cpu_pct"] = 0.0

    try:
        r = subprocess.run(
            "free -m | awk 'NR==2{printf \"%.0f\", $3*100/$2}'",
            shell=True, capture_output=True, text=True,
        )
        info["ram_pct"] = float(r.stdout.strip() or 0)
    except Exception:
        info["ram_pct"] = 0.0

    try:
        r = subprocess.run(
            "df -h / | awk 'NR==2{print $5}'",
            shell=True, capture_output=True, text=True,
        )
        info["disco_pct"] = r.stdout.strip().replace("%", "")
    except Exception:
        info["disco_pct"] = "?"

    try:
        r = subprocess.run("uptime -p", shell=True, capture_output=True, text=True)
        info["uptime"] = r.stdout.strip().replace("up ", "")
    except Exception:
        info["uptime"] = "?"

    try:
        r = subprocess.run(
            "pm2 list 2>/dev/null | grep -c online || echo 0",
            shell=True, capture_output=True, text=True,
        )
        info["pm2_online"] = int(r.stdout.strip() or 0)
    except Exception:
        info["pm2_online"] = 0

    try:
        container = subprocess.check_output(
            ["docker", "ps", "--filter", "ancestor=redis", "--format", "{{.Names}}"],
            timeout=5,
        ).decode().strip().splitlines()
        if container:
            pong = subprocess.run(
                ["docker", "exec", container[0], "redis-cli", "ping"],
                capture_output=True, text=True, timeout=5,
            )
            info["redis_ok"] = pong.stdout.strip() == "PONG"
        else:
            info["redis_ok"] = False
    except Exception:
        info["redis_ok"] = False

    try:
        code = subprocess.run(
            "curl -sf -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/docs",
            shell=True, capture_output=True, text=True, timeout=5,
        )
        info["backend_code"] = code.stdout.strip()
    except Exception:
        info["backend_code"] = "0"

    return info


# ── Carregador de orquestradores ──────────────────────────────────────────────

def carregar_orquestrador(modulo_file: str):
    """Importa dinamicamente um arquivo de orquestrador."""
    caminho = AGENTS_MOD / f"{modulo_file}.py"
    spec = importlib.util.spec_from_file_location(modulo_file, str(caminho))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.OrchestratorClass


# ── Sprint 6 — Mapeamento container → tipo de runbook ────────────────────────

_CONTAINER_RUNBOOK_MAP = {
    "conecta-pro-redis": "RedisDown",
    "conecta-pro-celery-integrations": "CeleryUnhealthy",
    "conecta-pro-backend": "BackendUnhealthy",
    "conecta-pro-frontend": "PM2ExcessiveRestarts",
}


def _executar_runbooks_containers(containers_fail: list, estado: dict):
    """Sprint 6 — Para cada container crítico em falha, executa runbook adequado."""
    for container in containers_fail:
        tipo = _CONTAINER_RUNBOOK_MAP.get(container)
        if not tipo:
            continue
        try:
            ticket = _CTO_BRAIN.criar_ticket(
                titulo=f"{container} indisponível",
                descricao=f"Container {container} não está running. Runbook {tipo} iniciado.",
                severidade="critica",
                categoria="infraestrutura",
                causa_raiz=f"Container {container} parou",
                solucao_proposta=f"Runbook automático: {tipo}",
            )
            ticket_num = ticket.get("numero", "CTO-????")
            resultado = _CTO_BRAIN.tentar_resolver(
                ticket_num=ticket_num,
                tipo=tipo,
                severidade="critica",
                descricao=f"Container {container} indisponível",
            )
            if resultado["resolvido"]:
                estado["correcoes_totais"] = estado.get("correcoes_totais", 0) + 1
                logger.info(f"[Sprint6] {container} recuperado via runbook {tipo}")
                telegram(
                    f"✅ <b>Runbook resolveu!</b>\n"
                    f"Container: <code>{container}</code>\n"
                    f"Runbook: {tipo}\n"
                    f"Ticket: {ticket_num} fechado automaticamente."
                )
            elif resultado["escalada_aberta"]:
                logger.warning(
                    f"[Sprint6] {container} não resolvido — escalada {ticket_num} aberta"
                )
            else:
                logger.warning(f"[Sprint6] {container}: runbook {tipo} indisponível")
        except Exception as e:
            logger.error(f"[Sprint6] Erro ao executar runbook para {container}: {e}")


# ── Ciclo rápido (5min) ───────────────────────────────────────────────────────

def ciclo_rapido(token: str, estado: dict) -> tuple[float, dict]:
    """
    Verifica containers + endpoints.
    Silencioso se tudo OK; alerta só em regressão ou bug persistente (3+ ciclos).
    Retorna (score_rapido, estado_atualizado).
    """
    t0 = time.time()

    containers = check_containers()
    endpoints = check_endpoints(token)

    # Score: containers (peso 2) + endpoints por módulo
    scores = []
    c_score = (containers["ok"] / containers["total"]) * 10
    scores.extend([c_score, c_score])
    for r in endpoints.values():
        scores.append(r["score"])
    score = round(sum(scores) / len(scores), 1) if scores else 0.0

    erros = containers["fail"][:]
    for mod, r in endpoints.items():
        erros.extend(r["errors"])

    estado["ciclos"] = estado.get("ciclos", 0) + 1
    score_anterior = estado.get("score_anterior", 10.0)
    delta = round(score - score_anterior, 1)
    regresso = delta <= -2.0 and score < 8.0

    # Detectar regressão avançada
    scores_modulos = {mod: r["score"] for mod, r in endpoints.items()}
    analise = analisar_e_alertar(score, scores_modulos)

    if regresso or analise.get("tem_regressao"):
        try:
            r = subprocess.run(
                ["git", "log", "--oneline", "-1"],
                capture_output=True, text=True, cwd=str(ROOT),
            )
            ultimo_commit = r.stdout.strip()
        except Exception:
            ultimo_commit = "?"

        msg = (
            f"⚠️ <b>REGRESSÃO DETECTADA!</b>\n\n"
            f"📊 Score: {score_anterior} → {score} ({delta:+.1f})\n"
            f"⏰ {datetime.now().strftime('%d/%m %H:%M')}\n\n"
            f"🔍 Commit: <code>{ultimo_commit}</code>\n\n"
            f"❌ Problemas:\n"
            + "\n".join(f"  • {e}" for e in erros[:10])
        )
        telegram(msg)

        # CTOBrain: abrir ticket de regressão automaticamente
        if CTO_BRAIN_OK:
            try:
                ticket = _CTO_BRAIN.criar_ticket(
                    titulo=f"Regressão score {score_anterior}→{score}",
                    descricao=(
                        f"Score caiu {delta:+.1f} pontos.\n"
                        f"Commit: {ultimo_commit}\n"
                        f"Erros: {'; '.join(erros[:5])}"
                    ),
                    severidade="critica" if delta <= -3.0 else "alta",
                    categoria="regressao",
                    causa_raiz=f"Possível regressão por commit: {ultimo_commit}",
                    solucao_proposta="Revisar último commit e fazer rollback se necessário",
                    requer_jordan=True,
                )
                logger.info(f"[CTOBrain] Ticket {ticket['numero']} criado para regressão")
            except Exception as e:
                logger.error(f"[CTOBrain] Erro ao criar ticket: {e}")

    elif erros:
        # Aprender com erros detectados e tentar auto-remediar
        if CONHECIMENTO_OK:
            for erro in erros[:5]:
                tipo = erro.split(":")[0].strip().replace(" ", "")
                _LEARNER.registrar_evento(tipo=tipo, severidade="warning", titulo=erro)
                p = _LEARNER.patterns.get(tipo, {})
                conf = p.get("confidence", 0.0)
                if conf >= 70.0 and _REMEDIATOR.pode_remediar(tipo):
                    resultado = _REMEDIATOR.remediar(tipo, confidence=conf)
                    if resultado["sucesso"]:
                        estado["correcoes_totais"] = estado.get("correcoes_totais", 0) + 1
                        logger.info(
                            f"[AutoRemediator] {tipo} remediado "
                            f"(conf={conf:.0f}/100, {resultado['tempo_s']}s)"
                        )

        # Sprint 6 — Tentar resolver containers críticos com runbook
        if CTO_BRAIN_OK and containers["fail"]:
            _executar_runbooks_containers(containers["fail"], estado)

        persistentes = estado.get("bugs_persistentes", {})
        chave = "|".join(sorted(erros[:5]))
        persistentes[chave] = persistentes.get(chave, 0) + 1
        if persistentes[chave] >= 3:
            msg = (
                f"🟡 <b>Problema persistente</b> ({persistentes[chave]}x ciclos)\n"
                + "\n".join(f"  ❌ {e}" for e in erros[:8])
            )
            telegram(msg)
        estado["bugs_persistentes"] = persistentes
    else:
        estado["bugs_persistentes"] = {}

    # Sprint 6 — Verificar escaladas temporais a cada ciclo rápido
    if CTO_BRAIN_OK:
        try:
            acoes_esc = _CTO_BRAIN.verificar_escaladas()
            if acoes_esc:
                logger.info(f"[Escalada] {len(acoes_esc)} ação(ões) de escalada disparada(s)")
        except Exception as e:
            logger.warning(f"[Escalada] Erro ao verificar escaladas: {e}")

    estado["score_anterior"] = score
    estado["melhor_score"] = max(estado.get("melhor_score", 0.0), score)
    duracao = round(time.time() - t0, 1)

    logger.info(
        f"[{datetime.now().strftime('%H:%M')}] "
        f"Rápido #{estado['ciclos']} | Score: {score}/10 | "
        f"Containers: {containers['ok']}/{containers['total']} | "
        f"Erros: {len(erros)} | {duracao}s"
    )
    return score, estado, containers, endpoints


# ── Ciclo completo (30min) ────────────────────────────────────────────────────

def ciclo_completo(token: str, estado: dict) -> dict:
    """
    Executa ciclo rápido + 13 orquestradores + banco.
    Envia relatório detalhado ao Telegram.
    """
    inicio = datetime.now()
    logger.info("=" * 60)
    logger.info(f"CICLO COMPLETO — {inicio.strftime('%Y-%m-%d %H:%M:%S')}")

    # Ciclo rápido primeiro
    score_rapido, estado, containers, endpoints_rapidos = ciclo_rapido(token, estado)

    # Verificar banco de dados
    db = check_database()
    errs = check_recent_errors()

    # 13 orquestradores
    resultados_orch = []
    scores_orch = []

    for idx, (nome_modulo, arquivo) in enumerate(ORCHESTRATORS):
        logger.info(f"▶ [{idx + 1}/{len(ORCHESTRATORS)}] {nome_modulo}")

        if not _token_valido(token):
            logger.warning(f"[TOKEN] Renovando antes de {nome_modulo}...")
            novo = _obter_token_com_retry()
            if novo:
                token = novo
                _injetar_token(token)

        try:
            OrcClass = carregar_orquestrador(arquivo)
            orc = OrcClass()
            resultado = orc.executar()
            score = resultado.get("score", 0.0)
            scores_orch.append(score)
            resultados_orch.append({
                "modulo": nome_modulo,
                "score": score,
                "agentes": resultado.get("agentes_executados", 0),
                "correcoes_aplicadas": resultado.get("correcoes_aplicadas", []),
                "status": "ok",
            })
            emoji = "✅" if score >= 8 else "⚠️" if score >= 6 else "❌"
            logger.info(f"  {emoji} {nome_modulo}: {score:.1f}/10")
        except Exception as e:
            logger.error(f"  💥 ERRO em {nome_modulo}: {e}")
            resultados_orch.append({
                "modulo": nome_modulo, "score": 0.0, "agentes": 0,
                "correcoes_aplicadas": [], "status": "erro", "erro": str(e),
            })
            scores_orch.append(0.0)

    # Score geral: média dos orquestradores
    media_orch = round(sum(scores_orch) / len(scores_orch), 1) if scores_orch else 0.0
    fim = datetime.now()
    duracao = (fim - inicio).total_seconds()

    # Registrar no monitor_state
    bugs_ativos = []
    for r in endpoints_rapidos.values():
        bugs_ativos.extend(r["errors"])
    state = registrar_ciclo(media_orch, [], [], bugs_ativos)
    ciclos = state.get("ciclos_executados", estado.get("ciclos", 1))
    tendencia = get_tendencia()

    # Total de correções
    correcoes = sum(len(r.get("correcoes_aplicadas", [])) for r in resultados_orch)
    estado["correcoes_totais"] = estado.get("correcoes_totais", 0) + correcoes

    # Montar mensagem Telegram
    emoji_media = score_emoji(media_orch)
    linhas = [
        f"🤖 <b>Conecta PRO — Ciclo Completo</b>",
        f"📅 {fim.strftime('%d/%m/%Y %H:%M')} | ⏱ {duracao:.0f}s",
        "",
        f"{emoji_media} <b>Score: {media_orch}/10</b>  |  📈 {tendencia}",
        f"🔄 Ciclo #{ciclos}",
        "",
        f"🐳 Containers: {containers['ok']}/{containers['total']}"
        + (f" ⚠️ ({', '.join(containers['fail'])})" if containers["fail"] else ""),
        f"🗄 Banco: {'✅ OK (' + str(db.get('users', '?')) + ' users)' if db.get('ok') else '❌ ' + db.get('error', '?')[:40]}",
        (f"⚡ Erros 500: ✅ nenhum" if errs["errors_500"] == 0
         else f"⚡ Erros 500: ⚠️ {errs['errors_500']} (últimas 200 linhas)"),
        "",
        "<b>Módulos:</b>",
    ]

    for r in resultados_orch:
        score = r["score"]
        em = "✅" if score >= 8 else "⚠️" if score >= 6 else "❌"
        if r["status"] == "erro":
            em = "💥"
        linhas.append(f"  {em} {r['modulo']}: {score:.1f}/10")

    criticos = [r for r in resultados_orch if r.get("score", 10) < 6]
    if criticos:
        linhas.append("")
        linhas.append("🚨 <b>Críticos (&lt;6):</b>")
        for r in criticos:
            linhas.append(f"  • {r['modulo']}: {r['score']:.1f}/10")

    if correcoes:
        linhas.append("")
        linhas.append(f"🔧 {correcoes} correção(ões) automática(s)")

    resumo = get_resumo_estado()
    if resumo.strip():
        linhas.append("")
        linhas.append(resumo.strip())

    ok_tg = telegram("\n".join(linhas))
    logger.info(f"Telegram: {'✅' if ok_tg else '❌'} | Score: {media_orch}/10 | {duracao:.0f}s")

    # Salvar relatório JSON
    relatorio = {
        "timestamp": inicio.isoformat(),
        "duracao_segundos": round(duracao, 1),
        "score_geral": media_orch,
        "total_modulos": len(ORCHESTRATORS),
        "modulos_ok": sum(1 for s in scores_orch if s >= 8),
        "modulos_alerta": sum(1 for s in scores_orch if 6 <= s < 8),
        "modulos_criticos": sum(1 for s in scores_orch if s < 6),
        "resultados": resultados_orch,
        "total_correcoes": correcoes,
        "containers": containers,
        "database": db,
    }
    nome_report = f"ciclo_geral_{inicio.strftime('%Y%m%d_%H%M')}.json"
    report_path = REPORTS_DIR / nome_report
    report_path.write_text(json.dumps(relatorio, indent=2, ensure_ascii=False, default=str))
    latest = REPORTS_DIR / "ciclo_geral_latest.json"
    if latest.exists() or latest.is_symlink():
        latest.unlink()
    latest.symlink_to(nome_report)

    # TeamBridge: reportar ao CTOBrain após ciclo completo
    if TEAM_BRIDGE_OK and _TEAM_BRIDGE:
        try:
            resultado_bridge = _TEAM_BRIDGE.processar_ciclo()
            tickets = resultado_bridge.get("tickets_criados", [])
            if tickets:
                logger.info(
                    f"[TeamBridge] {len(tickets)} ticket(s) criado(s): {tickets}"
                )
        except Exception as e:
            logger.warning(f"[TeamBridge] Erro ao processar ciclo: {e}")

    return estado


# ── Heartbeat (6h) ────────────────────────────────────────────────────────────

def ciclo_heartbeat(token: str, estado: dict) -> dict:
    """
    Relatório de infraestrutura completo.
    Absorve monitor_heartbeat.sh em Python puro.
    """
    logger.info(f"[{datetime.now().strftime('%H:%M')}] Heartbeat...")

    _, estado, containers, _ = ciclo_rapido(token, estado)
    info = info_sistema()

    score_atual = estado.get("score_anterior", 10.0)
    melhor = estado.get("melhor_score", 10.0)

    # Ler estatísticas do monitor_state.json
    try:
        ms = load_state()
        ciclos_total = ms.get("ciclos_executados", estado.get("ciclos", 0))
        correcoes_total = ms.get("correcoes_aplicadas_total", estado.get("correcoes_totais", 0))
        regressoes = len(ms.get("regressoes", []))
        primeira_exec = ms.get("primeira_execucao", "?")[:10]
    except Exception:
        ciclos_total = estado.get("ciclos", 0)
        correcoes_total = estado.get("correcoes_totais", 0)
        regressoes = 0
        primeira_exec = "?"

    def indicador(pct: float, warn=70, crit=90) -> str:
        if pct >= crit:
            return "🔴"
        if pct >= warn:
            return "🟡"
        return "🟢"

    backend_status = "✅ Online" if info.get("backend_code") == "200" else f"❌ ({info.get('backend_code')})"
    redis_status = "✅ OK" if info.get("redis_ok") else "❌ Falhou"
    pm2_n = info.get("pm2_online", 0)
    pm2_status = f"✅ {pm2_n} online" if pm2_n > 0 else "❌ Nenhum online"
    c_fail = containers.get("fail", [])
    c_status = (f"✅ {containers['ok']}/{containers['total']}" if not c_fail
                else f"⚠️ {containers['ok']}/{containers['total']} ({', '.join(c_fail)})")

    msg = (
        f"💚 <b>HEARTBEAT — MONITOR ATIVO</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"⏰ {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
        f"{'🟢' if score_atual >= 9 else '🟡' if score_atual >= 7 else '🔴'} "
        f"Score: {score_atual}/10  |  📈 {get_tendencia()}\n"
        f"🏆 Melhor score: {melhor}/10\n\n"
        f"🖥️ <b>Infraestrutura:</b>\n"
        f"  • Backend: {backend_status}\n"
        f"  • Frontend: {pm2_status}\n"
        f"  • Redis: {redis_status}\n"
        f"  • Containers: {c_status}\n"
        f"  {indicador(info['cpu_pct'])} CPU: {info['cpu_pct']:.1f}%\n"
        f"  {indicador(info['ram_pct'])} RAM: {info['ram_pct']:.0f}%\n"
        f"  🗄 Disco: {info['disco_pct']}%\n\n"
        f"📊 <b>Estatísticas:</b>\n"
        f"  🔄 Ciclos: {ciclos_total}\n"
        f"  🔧 Correções: {correcoes_total}\n"
        f"  📈 Regressões: {regressoes}\n"
        f"  📅 Ativo desde: {primeira_exec}\n\n"
        f"⚙️ <b>Sistema:</b>\n"
        f"  ⏱ Uptime: {info['uptime']}\n"
        f"  ✅ Próximo heartbeat em ~6h"
    )
    ok_tg = telegram(msg)
    logger.info(f"Heartbeat {'✅' if ok_tg else '❌'}")
    return estado


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    modo = sys.argv[1] if len(sys.argv) > 1 else "rapido"
    logger.info(f"{'=' * 55}")
    logger.info(f"MONITOR UNIFICADO — {modo.upper()} — {datetime.now()}")
    logger.info(f"{'=' * 55}")

    # Estado em memória (complementa monitor_state.json do legado)
    try:
        ms = load_state()
        estado = {
            "ciclos": ms.get("ciclos_executados", 0),
            "score_anterior": (ms.get("score_historico", [{}])[-1:] or [{}])[0].get("score", 10.0),
            "melhor_score": ms.get("melhor_score", 10.0),
            "correcoes_totais": ms.get("correcoes_aplicadas_total", 0),
            "bugs_persistentes": {},
        }
    except Exception:
        estado = {
            "ciclos": 0, "score_anterior": 10.0, "melhor_score": 10.0,
            "correcoes_totais": 0, "bugs_persistentes": {},
        }

    token = obter_token_compartilhado()
    if not token:
        telegram("🔴 Monitor Unificado: falha ao obter token JWT")
        sys.exit(1)

    if modo == "rapido":
        ciclo_rapido(token, estado)
    elif modo == "completo":
        estado = ciclo_completo(token, estado)
    elif modo == "heartbeat":
        estado = ciclo_heartbeat(token, estado)
    elif modo == "escaladas":
        # Sprint 6 — verificar escaladas temporais (chamado a cada 5min via cron)
        if CTO_BRAIN_OK:
            try:
                acoes = _CTO_BRAIN.verificar_escaladas()
                logger.info(f"[Escaladas] {len(acoes)} ação(ões) executada(s)")
            except Exception as e:
                logger.error(f"[Escaladas] Erro: {e}")
        else:
            logger.error("[Escaladas] CTOBrain indisponível")
    else:
        logger.error(f"Modo desconhecido: {modo}. Use: rapido | completo | heartbeat | escaladas")
        sys.exit(1)

    logger.info(f"✅ Concluído ({modo}) em {datetime.now().strftime('%H:%M:%S')}")


if __name__ == "__main__":
    main()
