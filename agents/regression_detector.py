"""
Detector de Regressão — Monitor Conecta PRO

Responsabilidades:
- Comparar score atual vs histórico
- Identificar qual módulo regrediu
- Tentar reverter via git se possível
- Alertar Jordan com contexto completo
- Registrar regressões para análise
"""
import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

STATE_FILE = Path(
    "/opt/conecta-pro/reports/monitor_state.json")
REGRESSION_LOG = Path(
    "/opt/conecta-pro/reports/regressoes.json")
BOT_TOKEN = ""  # pragma: allowlist secret
CHAT_ID = "5536961034"

# Threshold de regressão por módulo
# Se score cair mais que isso → alerta
THRESHOLDS = {
    "GED":         0.5,
    "Financeiro":  0.5,
    "DP":          0.5,
    "Operacional": 0.5,
    "AI+Gov":      0.3,   # mais sensível — módulo crítico
    "geral":       0.5,
}


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            return {}
    return {}


def load_regressoes() -> list:
    if REGRESSION_LOG.exists():
        try:
            return json.loads(
                REGRESSION_LOG.read_text())
        except Exception:
            return []
    return []


def save_regressao(regressao: dict):
    historico = load_regressoes()
    historico.append(regressao)
    # Manter últimas 50
    historico = historico[-50:]
    REGRESSION_LOG.write_text(
        json.dumps(historico, indent=2,
                   ensure_ascii=False,
                   default=str))


def send_telegram(mensagem: str) -> bool:
    try:
        r = subprocess.run([
            'curl', '-sf', '-X', 'POST',
            f'https://api.telegram.org/bot{BOT_TOKEN}'
            '/sendMessage',
            '-H', 'Content-Type: application/json',
            '-d', json.dumps({
                'chat_id': CHAT_ID,
                'text': mensagem,
                'parse_mode': 'HTML'
            })
        ], capture_output=True, text=True, timeout=15)
        return r.returncode == 0
    except Exception as e:
        logger.error(f"Telegram error: {e}")
        return False


def get_ultimo_commit() -> str:
    """Obter hash do último commit."""
    r = subprocess.run(
        ['git', '-C', '/opt/conecta-pro',
         'log', '--oneline', '-1'],
        capture_output=True, text=True
    )
    return r.stdout.strip()


def get_commits_recentes(n: int = 5) -> list:
    """Obter últimos N commits."""
    r = subprocess.run(
        ['git', '-C', '/opt/conecta-pro',
         'log', '--oneline', f'-{n}'],
        capture_output=True, text=True
    )
    return r.stdout.strip().split('\n')


def tentar_reverter(commit_hash: str) -> bool:
    """
    Tentar reverter o último commit se causou regressão.
    SEGURO: usa git revert (não destrói histórico).
    """
    try:
        r = subprocess.run(
            ['git', '-C', '/opt/conecta-pro',
             'revert', '--no-edit', commit_hash],
            capture_output=True, text=True,
            timeout=30
        )
        if r.returncode == 0:
            logger.info(
                f"Revert aplicado: {commit_hash}")
            return True
        else:
            logger.error(
                f"Revert falhou: {r.stderr[:200]}")
            return False
    except Exception as e:
        logger.error(f"Erro ao reverter: {e}")
        return False


def verificar_regressao_por_modulo(
        scores_atuais: dict,
        scores_anteriores: dict) -> list:
    """
    Verificar regressão em cada módulo individualmente.
    Retorna lista de módulos que regrediram.
    """
    regressoes = []
    for modulo, score_atual in scores_atuais.items():
        score_ant = scores_anteriores.get(modulo, 0)
        threshold = THRESHOLDS.get(
            modulo, THRESHOLDS["geral"])
        diff = score_atual - score_ant
        if diff < -threshold:
            regressoes.append({
                "modulo": modulo,
                "score_anterior": score_ant,
                "score_atual": score_atual,
                "diferenca": round(diff, 1),
                "threshold": threshold
            })
    return regressoes


def analisar_e_alertar(
        score_geral_atual: float,
        scores_por_modulo: dict) -> dict:
    """
    Analisar o ciclo atual vs histórico.
    Alertar Jordan se houver regressão.
    Retorna resultado da análise.
    """
    agora = datetime.now().strftime("%d/%m %H:%M")
    state = load_state()
    historico = state.get("score_historico", [])

    resultado = {
        "tem_regressao": False,
        "regressoes": [],
        "reverteu": False,
        "commit_revertido": None
    }

    if len(historico) < 2:
        logger.info("Histórico insuficiente — "
                    "aguardando mais ciclos")
        return resultado

    # Score de referência = média dos últimos 3 ciclos
    ultimos = historico[-3:] if len(historico) >= 3 \
        else historico
    media_ref = sum(h["score"] for h in ultimos) \
        / len(ultimos)
    diff_geral = score_geral_atual - media_ref
    threshold_geral = THRESHOLDS["geral"]

    # Verificar regressão geral
    if diff_geral < -threshold_geral:
        resultado["tem_regressao"] = True

        # Obter contexto do git
        ultimo_commit = get_ultimo_commit()
        commits_recentes = get_commits_recentes(3)

        # Montar alerta detalhado
        alerta = (
            f"⚠️ <b>REGRESSÃO DETECTADA!</b>\n\n"
            f"📊 Score: {round(media_ref, 1)} → "
            f"{score_geral_atual} "
            f"({diff_geral:+.1f})\n"
            f"⏰ {agora}\n\n"
        )

        # Verificar regressão por módulo
        scores_ant_modulo = {}
        if len(historico) >= 2:
            ultimo_ciclo = historico[-2] \
                if len(historico) >= 2 else {}
            scores_ant_modulo = ultimo_ciclo.get(
                "scores_modulo", {})

        regressoes_modulo = verificar_regressao_por_modulo(
            scores_por_modulo,
            scores_ant_modulo
        )

        if regressoes_modulo:
            alerta += "📉 <b>Módulos afetados:</b>\n"
            for r in regressoes_modulo:
                alerta += (
                    f"  • {r['modulo']}: "
                    f"{r['score_anterior']} → "
                    f"{r['score_atual']} "
                    f"({r['diferenca']:+.1f})\n"
                )
            resultado["regressoes"] = regressoes_modulo

        alerta += (
            f"\n🔍 <b>Último commit:</b>\n"
            f"<code>{ultimo_commit}</code>\n\n"
        )

        # AUTO-REVERT DESABILITADO — 2026-04-07
        # Causa raiz de todos os rogue reverts:
        #   git revert --no-edit bypassa commit-msg hook.
        # Requer autorização explícita de Jordan Jesus.
        # Ref: CLAUDE.md "PROIBIDO ABSOLUTO"
        if diff_geral < -1.0 and ultimo_commit:
            commit_hash = ultimo_commit.split(' ')[0]
            alerta += (
                "⚠️ <b>Regressão severa detectada</b>\n"
                f"Commit suspeito: <code>{commit_hash}</code>\n"
                "Auto-revert DESABILITADO por segurança.\n"
                "Aguardando autorização de Jordan Jesus.\n\n"
            )
            logger.warning(
                f"AUTO-REVERT BLOQUEADO para {commit_hash} "
                f"— requer autorização manual (Jordan Jesus)"
            )

        alerta += "🔧 Verifique o sistema."

        # Enviar alerta
        send_telegram(alerta)
        logger.warning(
            f"Regressão detectada: "
            f"{media_ref:.1f} → {score_geral_atual}")

        # Registrar regressão
        save_regressao({
            "timestamp": agora,
            "score_anterior": round(media_ref, 1),
            "score_atual": score_geral_atual,
            "diferenca": round(diff_geral, 1),
            "commit": ultimo_commit,
            "reverteu": resultado["reverteu"],
            "modulos_afetados": regressoes_modulo
        })

    else:
        logger.info(
            f"Sem regressão — score {score_geral_atual}"
            f" (ref: {media_ref:.1f}, "
            f"diff: {diff_geral:+.1f})")

    return resultado


def get_relatorio_regressoes() -> str:
    """Retornar relatório de regressões para o Telegram."""
    historico = load_regressoes()
    if not historico:
        return "✅ Nenhuma regressão registrada"

    total = len(historico)
    ultima = historico[-1]
    revertidas = sum(
        1 for r in historico if r.get("reverteu"))

    return (
        f"📉 Regressões registradas: {total}\n"
        f"🔄 Revertidas automaticamente: {revertidas}\n"
        f"⏰ Última: {ultima.get('timestamp', '?')}\n"
        f"   Score: {ultima.get('score_anterior', '?')}"
        f" → {ultima.get('score_atual', '?')}"
    )
