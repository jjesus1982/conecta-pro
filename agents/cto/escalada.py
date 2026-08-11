"""
Escalada — CTO Sprint 6.

Sistema de escalada temporal com 4 níveis:
  1. notificar_jordan  — notificação inicial
  2. segunda_tentativa — segunda tentativa de runbook
  3. escalar           — alerta de escalada (ligação/WhatsApp)
  4. emergencia        — protocolo de emergência completo

Thresholds por severidade (minutos):
  critica: 5  → 10  → 20  → 30
  alta:    15 → 30  → 60  → 120
  media:   30 → 60  → 120 → 240
  baixa:   60 → 120 → 240 → 480

Multiplicadores:
  noturno (22h–07h): ×2
  fim_de_semana:     ×1.5
"""

import json
import subprocess
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

CTO_DIR = Path("/opt/conecta-pro/agents/cto")
ESCALADA_FILE = CTO_DIR / "memory" / "escaladas_ativas.json"
CTO_DIR.mkdir(parents=True, exist_ok=True)
(CTO_DIR / "memory").mkdir(parents=True, exist_ok=True)

# Thresholds em minutos por severidade e nível
THRESHOLDS: dict[str, list[int]] = {
    "critica": [5, 10, 20, 30],
    "alta":    [15, 30, 60, 120],
    "media":   [30, 60, 120, 240],
    "baixa":   [60, 120, 240, 480],
}

NIVEIS = ["notificar_jordan", "segunda_tentativa", "escalar", "emergencia"]

# Credenciais Telegram
BOT_TOKEN = ""  # pragma: allowlist secret
JORDAN_CHAT_ID = 5536961034


def _multiplicador_temporal() -> float:
    """Multiplica threshold em horário noturno ou fim de semana."""
    agora = datetime.now()
    mult = 1.0
    if agora.hour >= 22 or agora.hour < 7:
        mult *= 2.0
    if agora.weekday() >= 5:  # sábado=5, domingo=6
        mult *= 1.5
    return mult


def _telegram(texto: str) -> bool:
    """Envia mensagem no Telegram para Jordan."""
    try:
        payload = json.dumps({
            "chat_id": JORDAN_CHAT_ID,
            "text": texto,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read()).get("ok", False)
    except Exception:
        return False


class Escalada:
    """Gerencia escaladas ativas e dispara ações por nível."""

    def __init__(self):
        self.escaladas = self._carregar()

    def _carregar(self) -> dict:
        if ESCALADA_FILE.exists():
            try:
                return json.loads(ESCALADA_FILE.read_text())
            except Exception:
                pass
        return {}

    def _salvar(self):
        ESCALADA_FILE.write_text(
            json.dumps(self.escaladas, indent=2, ensure_ascii=False, default=str)
        )

    # ─── API pública ──────────────────────────────────────────────────────────

    def abrir(
        self,
        ticket_num: str,
        tipo: str,
        severidade: str,
        descricao: str,
    ) -> dict:
        """Abre ou atualiza escalada para um ticket."""
        agora = datetime.now().isoformat()
        if ticket_num not in self.escaladas:
            self.escaladas[ticket_num] = {
                "ticket": ticket_num,
                "tipo": tipo,
                "severidade": severidade,
                "descricao": descricao,
                "aberta_em": agora,
                "nivel_atual": 0,  # índice em NIVEIS
                "proximo_nivel_em": None,
                "historico": [],
                "resolvida": False,
            }
            # Agendar primeiro nível imediatamente
            self._agendar_proximo(ticket_num)
            self._salvar()
        return self.escaladas[ticket_num]

    def fechar(self, ticket_num: str, motivo: str = "resolvido"):
        """Marca escalada como resolvida."""
        if ticket_num in self.escaladas:
            self.escaladas[ticket_num]["resolvida"] = True
            self.escaladas[ticket_num]["fechada_em"] = datetime.now().isoformat()
            self.escaladas[ticket_num]["motivo_fechamento"] = motivo
            self._salvar()

    def verificar_todas(self) -> list[dict]:
        """
        Verifica todas as escaladas abertas e dispara próximo nível se atingido.
        Chamado a cada 5 minutos pelo cron.
        Retorna lista de ações executadas.
        """
        acoes = []
        agora = datetime.now()

        for ticket_num, esc in list(self.escaladas.items()):
            if esc.get("resolvida"):
                continue

            proximo = esc.get("proximo_nivel_em")
            if not proximo:
                continue

            try:
                proximo_dt = datetime.fromisoformat(proximo)
            except Exception:
                continue

            if agora >= proximo_dt:
                nivel_idx = esc["nivel_atual"]
                if nivel_idx >= len(NIVEIS):
                    continue
                nome_nivel = NIVEIS[nivel_idx]
                acao = self._executar_nivel(ticket_num, nome_nivel)
                acoes.append(acao)

                # Avançar para próximo nível
                esc["nivel_atual"] = nivel_idx + 1
                if nivel_idx + 1 < len(NIVEIS):
                    self._agendar_proximo(ticket_num)
                else:
                    esc["proximo_nivel_em"] = None  # emergência — sem próximo

                self._salvar()

        return acoes

    def listar_ativas(self) -> list[dict]:
        return [
            e for e in self.escaladas.values()
            if not e.get("resolvida")
        ]

    def resumo_telegram(self) -> str:
        ativas = self.listar_ativas()
        if not ativas:
            return "✅ Nenhuma escalada ativa."
        linhas = [f"🚨 *{len(ativas)} escalada(s) ativa(s):*\n"]
        for e in ativas:
            sev_emoji = {"critica": "🔴", "alta": "🟠", "media": "🟡", "baixa": "🟢"}.get(
                e.get("severidade", "media"), "⚪"
            )
            nivel_nome = NIVEIS[min(e["nivel_atual"], len(NIVEIS) - 1)]
            linhas.append(
                f"{sev_emoji} `{e['ticket']}` — {e['tipo']}\n"
                f"   Nível: {nivel_nome} | Aberta: {e['aberta_em'][:16].replace('T', ' ')}"
            )
        return "\n".join(linhas)

    # ─── Internos ─────────────────────────────────────────────────────────────

    def _agendar_proximo(self, ticket_num: str):
        esc = self.escaladas[ticket_num]
        severidade = esc.get("severidade", "media")
        nivel_idx = esc["nivel_atual"]

        thresholds = THRESHOLDS.get(severidade, THRESHOLDS["media"])
        if nivel_idx >= len(thresholds):
            esc["proximo_nivel_em"] = None
            return

        minutos = thresholds[nivel_idx]
        mult = _multiplicador_temporal()
        minutos_ajustados = int(minutos * mult)

        proximo = datetime.now() + timedelta(minutes=minutos_ajustados)
        esc["proximo_nivel_em"] = proximo.isoformat()

    def _executar_nivel(self, ticket_num: str, nivel: str) -> dict:
        esc = self.escaladas[ticket_num]
        ts = datetime.now().isoformat()

        acao = {
            "ticket": ticket_num,
            "nivel": nivel,
            "timestamp": ts,
            "sucesso": False,
            "mensagem": "",
        }

        try:
            if nivel == "notificar_jordan":
                acao["sucesso"] = self._nivel_notificar(esc)
                acao["mensagem"] = "Notificação Telegram enviada"
            elif nivel == "segunda_tentativa":
                acao["sucesso"] = self._nivel_segunda_tentativa(esc)
                acao["mensagem"] = "Segunda tentativa de runbook executada"
            elif nivel == "escalar":
                acao["sucesso"] = self._nivel_escalar(esc)
                acao["mensagem"] = "Alerta de escalada enviado"
            elif nivel == "emergencia":
                acao["sucesso"] = self._nivel_emergencia(esc)
                acao["mensagem"] = "Protocolo de emergência ativado"
        except Exception as e:
            acao["mensagem"] = f"Erro: {e}"

        esc["historico"].append(acao)
        return acao

    def _nivel_notificar(self, esc: dict) -> bool:
        sev_emoji = {"critica": "🔴", "alta": "🟠", "media": "🟡", "baixa": "🟢"}.get(
            esc.get("severidade", "media"), "⚪"
        )
        msg = (
            f"{sev_emoji} *Alerta CTO — {esc['ticket']}*\n\n"
            f"Tipo: `{esc['tipo']}`\n"
            f"Severidade: `{esc['severidade']}`\n"
            f"Descrição: {esc['descricao'][:150]}\n\n"
            f"_Tentativa automática de resolução falhou. Monitorando..._\n"
            f"Use `/runbooks` para ver opções manuais."
        )
        return _telegram(msg)

    def _nivel_segunda_tentativa(self, esc: dict) -> bool:
        """Tenta executar runbook novamente."""
        try:
            from runbook import RunbookExecutor
            rb = RunbookExecutor()
            tipo = esc["tipo"]
            if rb.pode_executar(tipo):
                resultado = rb.executar(tipo)
                msg = rb.resumo_telegram(resultado)
                _telegram(f"🔄 *Segunda tentativa — {esc['ticket']}*\n\n{msg}")
                if resultado.resolvido:
                    self.fechar(esc["ticket"], "resolvido na segunda tentativa")
                return resultado.resolvido
        except Exception as e:
            _telegram(
                f"⚠️ Segunda tentativa falhou para `{esc['ticket']}`:\n`{e}`"
            )
        return False

    def _nivel_escalar(self, esc: dict) -> bool:
        """Alerta de escalada — mensagem de urgência."""
        msg = (
            f"🚨 *ESCALADA — {esc['ticket']}*\n\n"
            f"⚠️ O problema `{esc['tipo']}` persiste há mais de "
            f"{self._tempo_aberta(esc)} minutos.\n\n"
            f"Severidade: `{esc['severidade']}`\n"
            f"Descrição: {esc['descricao'][:150]}\n\n"
            f"*Intervenção manual necessária.*\n"
            f"Aberta em: {esc['aberta_em'][:16].replace('T', ' ')}"
        )
        return _telegram(msg)

    def _nivel_emergencia(self, esc: dict) -> bool:
        """Protocolo de emergência — máxima urgência."""
        # Tentar runbook de último recurso
        ultimo_resultado = None
        try:
            from runbook import RunbookExecutor
            rb = RunbookExecutor()
            if rb.pode_executar(esc["tipo"]):
                ultimo_resultado = rb.executar(esc["tipo"])
        except Exception:
            pass

        msg = (
            f"🆘 *EMERGÊNCIA — {esc['ticket']}*\n\n"
            f"Problema crítico não resolvido após {self._tempo_aberta(esc)} minutos!\n\n"
            f"Tipo: `{esc['tipo']}`\n"
            f"Severidade: `{esc['severidade']}`\n"
            f"Descrição: {esc['descricao'][:150]}\n\n"
        )

        if ultimo_resultado and ultimo_resultado.resolvido:
            msg += "✅ *Resolvido na tentativa de emergência.*"
            self.fechar(esc["ticket"], "resolvido no protocolo de emergência")
        else:
            msg += (
                "❌ *Todas as tentativas automáticas falharam.*\n"
                "Intervenção imediata de Jordan é necessária.\n\n"
                "Comandos úteis:\n"
                "`docker ps` — verificar containers\n"
                "`pm2 list` — verificar frontend\n"
                "`free -m` — verificar memória"
            )

        return _telegram(msg)

    def _tempo_aberta(self, esc: dict) -> int:
        """Tempo em minutos desde abertura da escalada."""
        try:
            aberta = datetime.fromisoformat(esc["aberta_em"])
            delta = datetime.now() - aberta
            return int(delta.total_seconds() / 60)
        except Exception:
            return 0
