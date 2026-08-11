"""
Turno — Comportamento inteligente por horário.

Turno Noturno (22h-7h):
  - Ciclos mais frequentes (15min vs 30min)
  - Mais agressivo: resolve sem perguntar
  - Jordan NÃO é acordado por problemas auto-resolúveis
  - Apenas emergências reais acordam Jordan
  - Runbooks executam automaticamente sem aprovação

Turno Diurno (7h-22h):
  - Comportamento padrão
  - Jordan consultado para decisões importantes
  - Notificações normais

Fim de semana:
  - Similar ao noturno mas com threshold ainda maior
  - Apenas critica e emergencia notificam Jordan
"""
import json
from datetime import datetime
from pathlib import Path


TURNO_STATE = Path(
    "/opt/conecta-pro/agents/cto/memory/turno_state.json"
)

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


class Turno:
    """Gerencia comportamento por turno."""

    TURNO_NOTURNO_INICIO = 22
    TURNO_NOTURNO_FIM = 7

    def __init__(self):
        self.state = self._carregar()

    def _carregar(self) -> dict:
        if TURNO_STATE.exists():
            try:
                return json.loads(TURNO_STATE.read_text())
            except Exception:
                pass
        return {
            "turno_atual": None,
            "ultima_troca": None,
            "notificou_troca": False,
        }

    def _salvar(self):
        TURNO_STATE.parent.mkdir(parents=True, exist_ok=True)
        TURNO_STATE.write_text(
            json.dumps(
                self.state, indent=2,
                ensure_ascii=False, default=str,
            )
        )

    @property
    def is_noturno(self) -> bool:
        hora = datetime.now().hour
        return (
            hora >= self.TURNO_NOTURNO_INICIO
            or hora < self.TURNO_NOTURNO_FIM
        )

    @property
    def is_fim_de_semana(self) -> bool:
        return datetime.now().weekday() >= 5

    @property
    def turno_atual(self) -> str:
        if self.is_fim_de_semana:
            return "fim_de_semana"
        return "noturno" if self.is_noturno else "diurno"

    @property
    def intervalo_ciclo_min(self) -> int:
        """Intervalo do ciclo de monitoramento."""
        if self.is_noturno or self.is_fim_de_semana:
            return 15  # Mais frequente à noite
        return 30  # Padrão durante o dia

    @property
    def pode_acordar_jordan(self) -> bool:
        """Se deve notificar Jordan agora."""
        if self.is_fim_de_semana:
            return False  # Só emergências
        if self.is_noturno:
            return False  # Só emergências reais
        return True  # Diurno: sim

    @property
    def runbook_automatico(self) -> bool:
        """Se pode executar runbooks sem aprovação."""
        return self.is_noturno or self.is_fim_de_semana

    @property
    def severidade_minima_notificacao(self) -> str:
        """Severidade mínima para notificar Jordan."""
        if self.is_fim_de_semana:
            return "critica"
        if self.is_noturno:
            return "alta"
        return "media"

    def deve_notificar(self, severidade: str) -> bool:
        """Verifica se deve notificar Jordan por severidade."""
        ordem = ["info", "baixa", "media", "alta", "critica"]
        sev_min = self.severidade_minima_notificacao
        try:
            return (
                ordem.index(severidade) >= ordem.index(sev_min)
            )
        except ValueError:
            return True

    def verificar_troca_turno(self):
        """Detecta e notifica troca de turno."""
        turno_novo = self.turno_atual
        turno_anterior = self.state.get("turno_atual")

        if turno_anterior and turno_novo != turno_anterior:
            self.state["turno_atual"] = turno_novo
            self.state["ultima_troca"] = datetime.now().isoformat()
            self._salvar()

            if turno_novo == "noturno":
                _telegram(
                    "🌙 *Turno noturno iniciado*\n\n"
                    "Modo autônomo ativado:\n"
                    "  • Problemas resolvidos sem perguntar\n"
                    "  • Jordan só notificado em emergências\n"
                    "  • Ciclos a cada 15min\n\n"
                    "_Boa noite — o CTO está de plantão._ 🤖"
                )
            elif turno_novo == "diurno":
                _telegram(
                    "☀️ *Turno diurno iniciado*\n\n"
                    "Modo colaborativo ativado:\n"
                    "  • Jordan consultado em decisões\n"
                    "  • Notificações normais\n\n"
                    "_Bom dia! Resumo da noite: /status_"
                )
            elif turno_novo == "fim_de_semana":
                _telegram(
                    "🏖️ *Fim de semana — modo silencioso*\n\n"
                    "Monitoramento ativo mas silencioso.\n"
                    "Apenas emergências críticas vão notificar.\n\n"
                    "_Aproveite o descanso, Jordan!_ 😄"
                )
        else:
            self.state["turno_atual"] = turno_novo
            self._salvar()

    def resumo(self) -> str:
        """Resumo do turno atual."""
        turno = self.turno_atual
        emojis = {
            "diurno": "☀️",
            "noturno": "🌙",
            "fim_de_semana": "🏖️",
        }
        emoji = emojis.get(turno, "⏰")
        hora = datetime.now().strftime("%H:%M")

        return (
            f"{emoji} *Turno:* `{turno}` ({hora})\n"
            f"  Ciclo: `{self.intervalo_ciclo_min}min`\n"
            f"  Notif Jordan: "
            f"`{'sim' if self.pode_acordar_jordan else 'não'}`\n"
            f"  Runbook auto: "
            f"`{'sim' if self.runbook_automatico else 'não'}`\n"
            f"  Sev mínima: `{self.severidade_minima_notificacao}`"
        )
