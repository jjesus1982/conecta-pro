"""
PósMortem — Gerado automaticamente quando ticket fecha.
Aprende com cada incidente para nunca mais precisar
de Jordan no mesmo problema.
"""
import json
from datetime import datetime
from pathlib import Path


CTO_DIR = Path("/opt/conecta-pro/agents/cto")
POS_MORTEM_DIR = CTO_DIR / "pos_mortems"

MONITOR_TOKEN = ""  # pragma: allowlist secret
JORDAN_CHAT = "5536961034"


def telegram(msg: str):
    import urllib.request

    url = f"https://api.telegram.org/bot{MONITOR_TOKEN}/sendMessage"
    data = json.dumps(
        {"chat_id": JORDAN_CHAT, "text": msg, "parse_mode": "Markdown"}
    ).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


class PósMortem:
    """Gera e persiste pós-mortems de incidentes."""

    def __init__(self):
        POS_MORTEM_DIR.mkdir(parents=True, exist_ok=True)

    def _calcular_duracao(self, criado_em: str, resolvido_em: str) -> str:
        try:
            inicio = datetime.fromisoformat(criado_em.replace("Z", ""))
            fim = datetime.fromisoformat(resolvido_em.replace("Z", ""))
            total_min = int((fim - inicio).total_seconds() / 60)
            if total_min < 60:
                return f"{total_min} minutos"
            elif total_min < 1440:
                h = total_min // 60
                m = total_min % 60
                return f"{h}h{m:02d}min" if m else f"{h}h"
            return f"{total_min // 1440} dia(s)"
        except Exception:
            return "desconhecida"

    def _gerar_prevencao(self, ticket: dict) -> list:
        comp = ticket.get("componente", "")
        causa = ticket.get("causa_raiz", "").lower()
        cat = ticket.get("categoria", "")

        if "redis" in comp.lower() or "redis" in causa:
            return [
                "Monitorar swap > 50% proativamente",
                "Configurar maxmemory no Redis",
                "Considerar upgrade RAM do VPS",
            ]
        elif "celery" in comp.lower():
            return [
                "Health check Celery a cada 2min",
                "Separar filas críticas das normais",
            ]
        elif "deploy" in causa or "commit" in causa:
            return [
                "Staging obrigatório antes de produção",
                "Health check automático pós-deploy",
                "Rollback automático se score cai > 2pts",
            ]
        elif "swap" in causa:
            return [
                "Liberar swap automaticamente > 80%",
                "Investigar processo com memory leak",
            ]
        else:
            return [f"Adicionar monitoramento para '{comp or cat}'"]

    def gerar(self, ticket: dict) -> dict:
        """Gera pós-mortem completo para ticket fechado."""
        numero = ticket.get("numero", "?")
        duracao = self._calcular_duracao(
            ticket.get("criado_em", ""),
            ticket.get("resolvido_em", ""),
        )
        prevencao = self._gerar_prevencao(ticket)

        pm = {
            "numero": numero,
            "titulo": ticket.get("titulo", ""),
            "gerado_em": datetime.now().isoformat(),
            "duracao": duracao,
            "severidade": ticket.get("severidade", ""),
            "categoria": ticket.get("categoria", ""),
            "componente": ticket.get("componente", ""),
            "causa_raiz": ticket.get("causa_raiz", ""),
            "solucao_aplicada": ticket.get("solucao_aplicada", "Não documentada"),
            "auto_resolvido": ticket.get("auto_resolvido", False),
            "timeline": ticket.get("timeline", []),
            "acoes_preventivas": prevencao,
            "licao": (
                f"[{numero}] {ticket.get('titulo', '')[:60]}"
                f" — {ticket.get('causa_raiz', '')[:80]}"
            ),
        }

        # Persistir
        f = POS_MORTEM_DIR / f"{numero}_pos_mortem.json"
        f.write_text(json.dumps(pm, indent=2, ensure_ascii=False, default=str))

        # Registrar na MemóriaLonga
        try:
            import sys

            sys.path.insert(0, str(CTO_DIR))
            from memoria_longa import MemóriaLonga

            mem = MemóriaLonga()
            mem.registrar_licao(pm["licao"], pm["categoria"], numero)
            if pm["solucao_aplicada"] != "Não documentada":
                mem.registrar_solucao(
                    ticket.get("titulo", ""),
                    pm["solucao_aplicada"],
                    True,
                    ticket=numero,
                )
            if pm["componente"]:
                mem.registrar_componente_fragil(pm["componente"], pm["categoria"])
        except Exception as e:
            print(f"[PósMortem] Memória erro: {e}")

        # Enviar resumo no Telegram
        emoji = "✅" if pm["auto_resolvido"] else "📋"
        telegram(
            f"{emoji} *Pós-Mortem {numero}*\n\n"
            f"*{pm['titulo'][:50]}*\n"
            f"⏱ Duração: `{duracao}`\n\n"
            f"🔍 *Causa:* _{pm['causa_raiz'][:100]}_\n"
            f"💡 *Solução:* _{pm['solucao_aplicada'][:80]}_\n\n"
            f"🛡️ *Prevenção:*\n"
            + "\n".join(f"  • _{a[:60]}_" for a in prevencao[:2])
            + "\n\n📚 _Lição registrada na memória_"
        )

        print(f"[PósMortem] {numero} gerado ({duracao})")
        return pm

    def listar(self, limit: int = 10) -> list:
        pms = []
        for f in sorted(POS_MORTEM_DIR.glob("*_pos_mortem.json"), reverse=True)[:limit]:
            try:
                pms.append(json.loads(f.read_text()))
            except Exception:
                pass
        return pms
