"""
Orquestrador Geral — Conecta PRO.

Executa todos os 13 orquestradores de módulo em sequência,
consolida scores, detecta módulos críticos e envia relatório
via Telegram para @conecta_pro_monitor_bot.

Uso:
    python3 agents/orchestrator_geral.py

Cron (a cada 30 min):
    */30 * * * * cd /opt/conecta-pro && \\
      MONITOR_BOT_TOKEN=... TELEGRAM_CHAT_ID=... \\
      python3 agents/orchestrator_geral.py >> logs/orchestrator.log 2>&1
"""
import importlib.machinery
import importlib.util
import json
import logging
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

# ── Paths ────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
AGENTS_CORE = ROOT / "agents" / "core"
AGENTS_MOD = ROOT / "agents" / "modules"
REPORTS_DIR = ROOT / "reports" / "modules"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(AGENTS_CORE))
sys.path.insert(0, str(AGENTS_MOD))

# ── Load base classes from .pyc if .py missing ───────────
def _load_pyc(name: str, pyc_path: Path):
    """Load a module from its compiled bytecode."""
    loader = importlib.machinery.SourcelessFileLoader(name, str(pyc_path))
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Ensure base_agent and base_orchestrator are importable
for _mod_name in ("base_agent", "base_orchestrator"):
    if _mod_name not in sys.modules:
        _src = AGENTS_CORE / f"{_mod_name}.py"
        _pyc = AGENTS_CORE / "__pycache__" / f"{_mod_name}.cpython-312.pyc"
        if not _src.exists() and _pyc.exists():
            _load_pyc(_mod_name, _pyc)

# ── Logging ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("orchestrator_geral")

# ── Telegram ─────────────────────────────────────────────
BOT_TOKEN = os.environ.get(
    "MONITOR_BOT_TOKEN",
    "",
)
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "5536961034")


def send_telegram(text: str) -> bool:
    """Envia mensagem via Telegram Bot API."""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = json.dumps(
            {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
        ).encode()
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            return result.get("ok", False)
    except Exception as e:
        logger.error(f"Telegram error: {e}")
        return False


# ── Token management ─────────────────────────────────────
import time as _time
import subprocess as _subprocess


_LOGIN_CMD = [
    "curl", "-sf", "-X", "POST",
    "http://127.0.0.1:8080/api/v1/auth/login",
    "-H", "Content-Type: application/x-www-form-urlencoded",
    "-d", "username=jjesus@conectamais.pro&password=Jordan0612",
]


def _fazer_login(timeout: int = 15) -> str:
    """Faz um único login; retorna token ou '' em falha."""
    try:
        r = _subprocess.run(
            _LOGIN_CMD, capture_output=True, text=True, timeout=timeout
        )
        return json.loads(r.stdout).get("access_token", "")
    except Exception:
        return ""


def _obter_token_com_retry(max_tentativas: int = 4) -> str:
    """Obtém token com retry exponencial (60s → 120s → 180s)."""
    for tentativa in range(max_tentativas):
        token = _fazer_login()
        if token:
            logger.info(f"✅ Token obtido (tentativa {tentativa + 1})")
            return token
        if tentativa < max_tentativas - 1:
            espera = 65 * (tentativa + 1)
            logger.warning(
                f"[TOKEN] Rate limit — aguardando {espera}s "
                f"(tentativa {tentativa + 1}/{max_tentativas})..."
            )
            _time.sleep(espera)
    logger.error("[TOKEN] Falhou após todas as tentativas")
    return ""


def _token_valido(token: str) -> bool:
    """Verifica se o token ainda é válido via /auth/me."""
    if not token:
        return False
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:8080/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


def _injetar_token(token: str) -> None:
    """Monkey-patcha BaseAgent e BaseOrchestrator com o token fornecido."""
    _t = token  # captura no closure

    import base_agent
    import base_orchestrator

    base_agent.BaseAgent.obter_token = (
        lambda self: setattr(self, "token", _t) or _t
    )
    base_orchestrator.BaseOrchestrator._obter_token_compartilhado = (
        lambda self: _t
    )


def obter_token_compartilhado() -> str:
    """Obtém token com retry e injeta em BaseAgent/BaseOrchestrator."""
    token = _obter_token_com_retry()
    if token:
        _injetar_token(token)
        logger.info("✅ Token compartilhado injetado em BaseAgent + BaseOrchestrator")
    else:
        logger.warning("⚠️ Token não obtido — agentes usarão obter_token() individual")
    return token


# ── Orquestradores ────────────────────────────────────────
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


def carregar_orquestrador(modulo_file: str):
    """Importa dinamicamente um arquivo de orquestrador."""
    caminho = AGENTS_MOD / f"{modulo_file}.py"
    spec = importlib.util.spec_from_file_location(modulo_file, str(caminho))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.OrchestratorClass


def formatar_telegram(resultados: list, media: float, duracao: float) -> str:
    """Formata mensagem Telegram com resultados do ciclo."""
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    emoji_media = "🟢" if media >= 8 else "🟡" if media >= 6 else "🔴"

    linhas = [
        "🤖 <b>Conecta PRO — Ciclo de Monitoramento</b>",
        f"📅 {agora} | ⏱ {duracao:.0f}s",
        "",
        f"{emoji_media} <b>Score Geral: {media:.1f}/10</b>",
        "",
        "<b>Módulos:</b>",
    ]

    for r in resultados:
        score = r.get("score", 0)
        modulo = r.get("modulo", "?")
        status = r.get("status", "ok")
        emoji = "✅" if score >= 8 else "⚠️" if score >= 6 else "❌"
        if status == "erro":
            emoji = "💥"
        linhas.append(f"{emoji} {modulo}: {score:.1f}/10")

    criticos = [
        r for r in resultados if r.get("score", 10) < 6
    ]
    if criticos:
        linhas.append("")
        linhas.append("🚨 <b>Críticos (score &lt; 6):</b>")
        for r in criticos:
            linhas.append(f"  • {r['modulo']}: {r['score']:.1f}/10")

    correcoes = sum(
        len(r.get("correcoes_aplicadas", [])) for r in resultados
    )
    if correcoes:
        linhas.append("")
        linhas.append(f"🔧 <b>{correcoes} correção(ões) aplicada(s) automaticamente</b>")

    return "\n".join(linhas)


# ── Main ─────────────────────────────────────────────────


def executar_ciclo():
    inicio = datetime.now()
    logger.info("=" * 60)
    logger.info(f"CICLO GERAL INICIADO — {inicio.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Orquestradores: {len(ORCHESTRATORS)}")
    logger.info("=" * 60)

    # Token compartilhado — evita rate limit
    token_atual = obter_token_compartilhado()
    if not token_atual:
        logger.warning("⚠️ Token não obtido — agentes usarão obter_token() individual")

    resultados = []
    scores = []

    for idx, (nome_modulo, arquivo) in enumerate(ORCHESTRATORS):
        logger.info(f"\n▶ [{idx + 1}/{len(ORCHESTRATORS)}] Executando: {nome_modulo} ({arquivo}.py)")

        # Verifica/renova token antes de cada módulo
        if not _token_valido(token_atual):
            logger.warning(f"[TOKEN] Inválido antes de '{nome_modulo}' — renovando...")
            novo = _obter_token_com_retry()
            if novo:
                token_atual = novo
                _injetar_token(token_atual)
                logger.info(f"[TOKEN] Renovado com sucesso antes de '{nome_modulo}'")
            else:
                logger.error(f"[TOKEN] Falhou renovar antes de '{nome_modulo}' — tentando mesmo assim")

        try:
            OrcClass = carregar_orquestrador(arquivo)
            orc = OrcClass()
            resultado = orc.executar()
            score = resultado.get("score", 0.0)
            scores.append(score)
            resultados.append(
                {
                    "modulo": nome_modulo,
                    "score": score,
                    "agentes": resultado.get("agentes_executados", 0),
                    "correcoes_aplicadas": resultado.get("correcoes_aplicadas", []),
                    "status": "ok",
                }
            )
            emoji = "✅" if score >= 8 else "⚠️" if score >= 6 else "❌"
            logger.info(f"  {emoji} {nome_modulo}: {score:.1f}/10")
        except Exception as e:
            logger.error(f"  💥 ERRO em {nome_modulo}: {e}")
            resultados.append(
                {
                    "modulo": nome_modulo,
                    "score": 0.0,
                    "agentes": 0,
                    "correcoes_aplicadas": [],
                    "status": "erro",
                    "erro": str(e),
                }
            )
            scores.append(0.0)

    # Consolidar
    media = round(sum(scores) / len(scores), 1) if scores else 0.0
    fim = datetime.now()
    duracao = (fim - inicio).total_seconds()

    # Relatório JSON
    relatorio_geral = {
        "timestamp": inicio.isoformat(),
        "duracao_segundos": round(duracao, 1),
        "score_geral": media,
        "total_modulos": len(ORCHESTRATORS),
        "modulos_ok": sum(1 for s in scores if s >= 8),
        "modulos_alerta": sum(1 for s in scores if 6 <= s < 8),
        "modulos_criticos": sum(1 for s in scores if s < 6),
        "resultados": resultados,
        "total_correcoes": sum(
            len(r.get("correcoes_aplicadas", [])) for r in resultados
        ),
    }

    nome_report = f"ciclo_geral_{inicio.strftime('%Y%m%d_%H%M')}.json"
    report_path = REPORTS_DIR / nome_report
    report_path.write_text(
        json.dumps(relatorio_geral, indent=2, ensure_ascii=False, default=str)
    )

    # Symlink latest
    latest = REPORTS_DIR / "ciclo_geral_latest.json"
    if latest.exists() or latest.is_symlink():
        latest.unlink()
    latest.symlink_to(nome_report)

    logger.info("\n" + "=" * 60)
    logger.info(f"CICLO CONCLUÍDO em {duracao:.0f}s")
    logger.info(f"Score Geral: {media}/10")
    logger.info(
        f"OK: {relatorio_geral['modulos_ok']} | "
        f"Alerta: {relatorio_geral['modulos_alerta']} | "
        f"Crítico: {relatorio_geral['modulos_criticos']}"
    )
    logger.info("=" * 60)

    # Telegram
    msg = formatar_telegram(resultados, media, duracao)
    ok_tg = send_telegram(msg)
    logger.info(f"Telegram: {'✅ enviado' if ok_tg else '❌ falhou'}")

    return relatorio_geral


if __name__ == "__main__":
    resultado = executar_ciclo()
    print(json.dumps(resultado, indent=2, default=str, ensure_ascii=False))
