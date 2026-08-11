"""
Preditor — Detecta tendências e prevê problemas futuros.

Algoritmos usados:
1. Regressão linear simples — tendência de crescimento
2. Detecção de anomalia por z-score — desvio do normal
3. Padrão temporal — "toda terça às 14h o swap sobe"
4. Correlação — "quando CPU > 6, swap > 80% em 2h"
5. Threshold progressivo — "crescimento de X% ao dia"
"""
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Optional


PREDICAO_DIR = Path("/opt/conecta-pro/agents/cto/predicao")
ALERTAS_DIR = PREDICAO_DIR / "alertas"

MONITOR_TOKEN = ""  # pragma: allowlist secret
JORDAN_CHAT = "5536961034"


def telegram(msg: str):
    import urllib.request
    url = f"https://api.telegram.org/bot{MONITOR_TOKEN}/sendMessage"
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


class Preditor:
    """Motor de predição de problemas."""

    def __init__(self):
        ALERTAS_DIR.mkdir(parents=True, exist_ok=True)
        self.alertas_enviados = self._carregar_alertas()

    def _carregar_alertas(self) -> dict:
        f = ALERTAS_DIR / "enviados.json"
        if f.exists():
            try:
                return json.loads(f.read_text())
            except Exception:
                pass
        return {}

    def _salvar_alertas(self):
        f = ALERTAS_DIR / "enviados.json"
        f.write_text(
            json.dumps(
                self.alertas_enviados,
                indent=2, ensure_ascii=False, default=str,
            )
        )

    def _ja_alertou(self, chave: str, horas: int = 6) -> bool:
        """Evita spam — uma vez por N horas."""
        ts = self.alertas_enviados.get(chave)
        if not ts:
            return False
        try:
            ultimo = datetime.fromisoformat(ts)
            return (datetime.now() - ultimo).total_seconds() < horas * 3600
        except Exception:
            return False

    def _registrar_alerta(self, chave: str):
        self.alertas_enviados[chave] = datetime.now().isoformat()
        self._salvar_alertas()

    def _regressao_linear(self, valores: list) -> dict:
        """
        Calcula tendência linear dos valores.
        Retorna: slope (taxa de crescimento por ponto),
                 previsao (lista de valores previstos)
        """
        n = len(valores)
        if n < 3:
            return {"slope": 0, "previsao": [], "tendencia": "estável"}

        x = list(range(n))
        y = valores

        x_med = sum(x) / n
        y_med = sum(y) / n

        numerador = sum((x[i] - x_med) * (y[i] - y_med) for i in range(n))
        denominador = sum((x[i] - x_med) ** 2 for i in range(n))

        slope = numerador / denominador if denominador != 0 else 0
        intercept = y_med - slope * x_med

        # Prever próximos 12 pontos (1h se coleta 5min)
        previsao = [
            round(intercept + slope * (n + i), 2)
            for i in range(12)
        ]

        return {
            "slope": round(slope, 4),
            "intercept": round(intercept, 2),
            "previsao": previsao,
            "tendencia": (
                "crescendo" if slope > 0.1
                else "decrescendo" if slope < -0.1
                else "estável"
            ),
        }

    def _z_score(self, valores: list, valor_atual: float) -> float:
        """Calcula z-score do valor atual."""
        if len(valores) < 5:
            return 0
        media = sum(valores) / len(valores)
        variancia = sum((v - media) ** 2 for v in valores) / len(valores)
        desvio = math.sqrt(variancia)
        if desvio == 0:
            return 0
        return (valor_atual - media) / desvio

    def analisar_swap(self, historico: list) -> Optional[dict]:
        """Prevê quando swap vai saturar."""
        if len(historico) < 10:
            return None

        valores = [p.get("swap_pct", 0) for p in historico]
        atual = valores[-1]

        reg = self._regressao_linear(valores[-50:])
        slope = reg["slope"]
        previsao = reg["previsao"]

        if slope > 0.5 and atual > 30:
            pontos_ate_critico = None
            for i, v in enumerate(previsao):
                if v >= 90:
                    pontos_ate_critico = i
                    break

            if pontos_ate_critico is not None:
                minutos = pontos_ate_critico * 5
                horas = minutos / 60

                if not self._ja_alertou("swap_critico", horas=6):
                    return {
                        "tipo": "swap_saturando",
                        "urgencia": "critica" if horas < 2 else "alta",
                        "atual": atual,
                        "previsao_critico_em": (
                            f"{minutos:.0f} minutos"
                            if horas < 2
                            else f"{horas:.1f} horas"
                        ),
                        "slope": slope,
                        "mensagem": (
                            f"⚠️ *Swap vai saturar em ~{horas:.1f}h*\n\n"
                            f"Atual: `{atual:.0f}%` → "
                            f"Tendência: +{slope:.1f}%/5min\n"
                            f"Previsão 1h: `{previsao[11]:.0f}%`\n\n"
                            f"_Ação preventiva recomendada antes de saturar._"
                        ),
                    }
        return None

    def analisar_disco(self, historico: list) -> Optional[dict]:
        """Prevê quando disco vai encher."""
        if len(historico) < 24:
            return None

        valores = [p.get("disco_pct", 0) for p in historico]
        atual = valores[-1]

        valor_24h = valores[-288] if len(valores) >= 288 else valores[0]
        crescimento_dia = atual - valor_24h

        if crescimento_dia > 0.5 and atual > 60:
            dias_ate_cheio = (
                (100 - atual) / crescimento_dia
                if crescimento_dia > 0 else 999
            )

            if dias_ate_cheio < 30 and not self._ja_alertou(
                "disco_cheio", horas=24
            ):
                urgencia = (
                    "critica" if dias_ate_cheio < 7
                    else "alta" if dias_ate_cheio < 14
                    else "media"
                )
                return {
                    "tipo": "disco_enchendo",
                    "urgencia": urgencia,
                    "atual": atual,
                    "dias_ate_cheio": round(dias_ate_cheio),
                    "crescimento_dia": round(crescimento_dia, 2),
                    "mensagem": (
                        f"💾 *Disco vai encher em ~{dias_ate_cheio:.0f} dias*\n\n"
                        f"Atual: `{atual:.1f}%`\n"
                        f"Crescimento: `+{crescimento_dia:.2f}%/dia`\n\n"
                        f"_Limpar logs e backups antigos._"
                    ),
                }
        return None

    def analisar_performance(self, historico: list) -> Optional[dict]:
        """Detecta degradação progressiva de performance."""
        if len(historico) < 20:
            return None

        tempos = [
            p.get("t_health", 0)
            for p in historico
            if p.get("t_health", -1) > 0
        ]

        if len(tempos) < 10:
            return None

        meio = len(tempos) // 2
        media_antes = sum(tempos[:meio]) / meio
        media_depois = sum(tempos[meio:]) / len(tempos[meio:])

        degradacao_pct = (
            (media_depois - media_antes) / media_antes * 100
            if media_antes > 0 else 0
        )

        if degradacao_pct > 50 and media_depois > 500:
            if not self._ja_alertou("performance_degradando", horas=4):
                return {
                    "tipo": "performance_degradando",
                    "urgencia": "critica" if media_depois > 2000 else "alta",
                    "ms_antes": round(media_antes),
                    "ms_depois": round(media_depois),
                    "degradacao_pct": round(degradacao_pct),
                    "mensagem": (
                        f"📈 *Performance degradando*\n\n"
                        f"Antes: `{media_antes:.0f}ms` → "
                        f"Agora: `{media_depois:.0f}ms`\n"
                        f"Degradação: `+{degradacao_pct:.0f}%`\n\n"
                        f"_Possível causa: queries lentas ou swap alto._"
                    ),
                }
        return None

    def analisar_padrao_temporal(
        self, historico: list, metrica: str
    ) -> Optional[dict]:
        """
        Detecta padrão temporal recorrente.
        Ex: "toda terça às 14h o CPU sobe acima de 7"
        """
        if len(historico) < 288:  # Precisa de 1 dia
            return None

        por_hora: dict[int, list] = {}
        for p in historico:
            hora = p.get("hora", 0)
            valor = p.get(metrica, 0)
            if hora not in por_hora:
                por_hora[hora] = []
            por_hora[hora].append(valor)

        hora_critica = None
        valor_critico = 0.0
        for hora, valores in por_hora.items():
            media = sum(valores) / len(valores)
            if media > valor_critico:
                valor_critico = media
                hora_critica = hora

        if hora_critica is not None:
            media_geral = sum(
                p.get(metrica, 0) for p in historico
            ) / len(historico)

            if valor_critico > media_geral * 1.5:
                hora_atual = datetime.now().hour
                horas_ate = (hora_critica - hora_atual) % 24

                if 0 < horas_ate <= 2:
                    chave = f"padrao_{metrica}_{hora_critica}"
                    if not self._ja_alertou(chave, horas=20):
                        return {
                            "tipo": "padrao_temporal",
                            "metrica": metrica,
                            "hora_critica": hora_critica,
                            "horas_ate": horas_ate,
                            "valor_esperado": round(valor_critico, 1),
                            "mensagem": (
                                f"⏰ *Padrão detectado*\n\n"
                                f"`{metrica}` costuma subir às `{hora_critica}h`\n"
                                f"Valor esperado: `{valor_critico:.1f}`\n"
                                f"Faltam: `{horas_ate}h`\n\n"
                                f"_Preparar ação preventiva._"
                            ),
                        }
        return None

    def analisar_correlacao(self, historico: list) -> Optional[dict]:
        """
        Detecta correlações entre métricas.
        Ex: CPU alto → swap alto em 30min
        """
        if len(historico) < 20:
            return None

        cpus = [p.get("cpu_1m", 0) for p in historico[-20:]]
        swaps = [p.get("swap_pct", 0) for p in historico[-20:]]

        cpu_atual = cpus[-1]
        swap_atual = swaps[-1]

        if cpu_atual > 6:
            swap_5_atras = swaps[-5] if len(swaps) >= 5 else swaps[0]
            swap_crescendo = swap_atual > swap_5_atras + 5

            if swap_crescendo and not self._ja_alertou(
                "correlacao_cpu_swap", horas=2
            ):
                return {
                    "tipo": "correlacao_cpu_swap",
                    "urgencia": "alta",
                    "cpu": cpu_atual,
                    "swap": swap_atual,
                    "mensagem": (
                        f"🔗 *Correlação detectada*\n\n"
                        f"CPU: `{cpu_atual:.1f}` + "
                        f"Swap crescendo: `{swap_atual:.0f}%`\n\n"
                        f"_Historicamente isso leva a problemas "
                        f"de performance em ~30min._\n\n"
                        f"Devo liberar swap agora preventivamente?"
                    ),
                }
        return None

    def analisar_erros_log(self, historico: list) -> Optional[dict]:
        """Detecta aumento anormal de erros nos logs."""
        if len(historico) < 10:
            return None

        erros = [p.get("erros_log", 0) for p in historico]
        atual = erros[-1]

        z = self._z_score(erros[:-1], atual)

        if z > 3 and atual > 5:
            if not self._ja_alertou("erros_log_anomalia", horas=1):
                media = sum(erros[:-1]) / len(erros[:-1])
                return {
                    "tipo": "erros_log_anomalia",
                    "urgencia": "alta",
                    "erros_atual": atual,
                    "media_normal": round(media, 1),
                    "z_score": round(z, 1),
                    "mensagem": (
                        f"🚨 *Anomalia nos logs*\n\n"
                        f"Erros últimos 5min: `{atual}`\n"
                        f"Normal: `{media:.1f}`\n"
                        f"Desvio: `{z:.1f}σ`\n\n"
                        f"_Algo está gerando erros acima do normal._"
                    ),
                }
        return None

    def executar_analise_completa(self, historico: list) -> list:
        """
        Executa todas as análises de predição.
        Retorna lista de alertas gerados.
        """
        if not historico:
            return []

        alertas = []
        analises = [
            self.analisar_swap(historico),
            self.analisar_disco(historico),
            self.analisar_performance(historico),
            self.analisar_correlacao(historico),
            self.analisar_erros_log(historico),
            self.analisar_padrao_temporal(historico, "cpu_1m"),
            self.analisar_padrao_temporal(historico, "swap_pct"),
        ]

        for alerta in analises:
            if alerta:
                alertas.append(alerta)
                chave = alerta["tipo"]
                telegram(alerta["mensagem"])
                self._registrar_alerta(chave)
                print(
                    f"  📊 Predição: {alerta['tipo']} — "
                    f"{alerta['urgencia']}"
                )

        return alertas
