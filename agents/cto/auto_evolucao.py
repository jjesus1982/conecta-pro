"""
AutoEvolução — O CTO audita e melhora o próprio sistema.

Responsabilidades:
1. Auditar eficácia de cada agente
   → Agente que nunca detecta nada = ineficiente
   → Agente com muitos falsos positivos = ruidoso

2. Detectar gaps de cobertura
   → Qual área do sistema não tem agente?
   → Qual tipo de problema passou despercebido?

3. Propor novos agentes
   → Baseado em incidentes que não foram detectados
   → Jordan aprova antes de criar

4. Otimizar runbooks
   → Passo que nunca funciona = remover
   → Passo que sempre funciona = priorizar

5. Relatório mensal de evolução
   → O que melhorou, o que piorou
   → Proposta de próximos passos
"""
import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


CTO_DIR = Path("/opt/conecta-pro/agents/cto")
AGENTS_DIR = Path("/opt/conecta-pro/agents/modules")
REPORTS_DIR = Path("/opt/conecta-pro/reports")
EVOLUCAO_DIR = CTO_DIR / "evolucao"

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


class AutoEvolução:
    """CTO audita e melhora o próprio sistema."""

    def __init__(self):
        EVOLUCAO_DIR.mkdir(parents=True, exist_ok=True)
        self.auditoria = self._carregar_auditoria()

    def _carregar_auditoria(self) -> dict:
        f = EVOLUCAO_DIR / "auditoria.json"
        if f.exists():
            try:
                return json.loads(f.read_text())
            except Exception:
                pass
        return {
            "agentes_auditados": {},
            "gaps_detectados": [],
            "propostas_novos_agentes": [],
            "runbooks_otimizados": [],
            "ultima_auditoria": None,
        }

    def _salvar_auditoria(self):
        f = EVOLUCAO_DIR / "auditoria.json"
        f.write_text(
            json.dumps(
                self.auditoria, indent=2,
                ensure_ascii=False, default=str,
            )
        )

    def auditar_agentes(self) -> dict:
        """
        Audita eficácia de cada agente.
        Detecta ineficientes e ruidosos.
        """
        print("[AutoEvolução] Auditando agentes...")
        resultado = {
            "ineficientes": [],
            "ruidosos": [],
            "excelentes": [],
            "sem_dados": [],
        }

        modules_dir = REPORTS_DIR / "modules"
        if not modules_dir.exists():
            # Tentar reports/ raiz
            modules_dir = REPORTS_DIR
        if not modules_dir.exists():
            return resultado

        for f in modules_dir.glob("*.json"):
            if f.name.startswith("ciclo_") or f.name in (
                "monitor_state.json", "auditoria.json"
            ):
                continue
            try:
                dados = json.loads(f.read_text())
                nome = f.stem
                score = float(
                    dados.get("score",
                    dados.get("score_atual", 10)) or 10
                )
                erros = dados.get("erros", [])

                historico = self.auditoria["agentes_auditados"].get(
                    nome, {"scores": [], "total_alertas": 0}
                )
                historico["scores"].append(score)
                historico["scores"] = historico["scores"][-30:]
                self.auditoria["agentes_auditados"][nome] = historico

                scores = historico["scores"]
                media = sum(scores) / len(scores) if scores else 10

                if media >= 9.5 and len(scores) >= 5:
                    resultado["excelentes"].append({
                        "nome": nome,
                        "score_medio": round(media, 1),
                    })
                elif media < 6.0 and len(scores) >= 5:
                    resultado["ineficientes"].append({
                        "nome": nome,
                        "score_medio": round(media, 1),
                        "problema": (
                            "Score consistentemente baixo — "
                            "verificar implementação"
                        ),
                    })
                elif len(erros) > 10:
                    resultado["ruidosos"].append({
                        "nome": nome,
                        "total_erros": len(erros),
                        "problema": (
                            "Muitos alertas — "
                            "possível falso positivo"
                        ),
                    })
                else:
                    resultado["sem_dados"].append(nome)
            except Exception:
                pass

        self.auditoria["ultima_auditoria"] = datetime.now().isoformat()
        self._salvar_auditoria()
        return resultado

    def detectar_gaps(self) -> list:
        """
        Detecta áreas sem cobertura de monitoramento.
        Baseado em tickets que não foram auto-detectados.
        """
        gaps = []
        tickets_dir = CTO_DIR / "tickets"

        if not tickets_dir.exists():
            return gaps

        # Problemas que chegaram via Jordan (não auto-detectados)
        nao_detectados = []
        for f in tickets_dir.glob("CTO-*.json"):
            try:
                t = json.loads(f.read_text())
                if (
                    not t.get("auto_resolvido")
                    and t.get("categoria") not in [
                        "regressao_sistema",
                        "agente_monitor",
                        "auto_detectado",
                    ]
                ):
                    nao_detectados.append(t)
            except Exception:
                pass

        # Agrupar por categoria
        por_categoria: dict[str, int] = {}
        for t in nao_detectados:
            cat = t.get("categoria", "desconhecido")
            por_categoria[cat] = por_categoria.get(cat, 0) + 1

        # Categorias com muitos tickets não-detectados
        for cat, count in por_categoria.items():
            if count >= 2:
                gaps.append({
                    "area": cat,
                    "tickets_perdidos": count,
                    "sugestao": (
                        f"Criar agente específico para '{cat}'"
                    ),
                })

        self.auditoria["gaps_detectados"] = gaps
        self._salvar_auditoria()
        return gaps

    def propor_novo_agente(
        self,
        area: str,
        descricao: str,
        justificativa: str,
    ) -> dict:
        """
        Propõe novo agente para cobrir gap detectado.
        Jordan aprova antes de criar.
        """
        proposta = {
            "id": (
                f"proposta_"
                f"{datetime.now().strftime('%Y%m%d_%H%M')}"
            ),
            "area": area,
            "nome_sugerido": f"{area.title().replace(' ', '')}Agent",
            "descricao": descricao,
            "justificativa": justificativa,
            "status": "aguardando_jordan",
            "criado_em": datetime.now().isoformat(),
        }

        self.auditoria["propostas_novos_agentes"].append(proposta)
        self._salvar_auditoria()

        telegram(
            f"🤖 *Proposta de novo agente*\n\n"
            f"*{proposta['nome_sugerido']}*\n\n"
            f"_{descricao}_\n\n"
            f"*Justificativa:*\n_{justificativa}_\n\n"
            f"Responda *aprovar {proposta['id']}* "
            f"para criar o agente."
        )
        return proposta

    def otimizar_runbooks(self) -> dict:
        """
        Analisa histórico de runbooks e otimiza.
        Remove passos que nunca funcionam.
        Prioriza passos que sempre funcionam.
        """
        rb_log = CTO_DIR / "memory" / "runbook_execucoes.json"
        if not rb_log.exists():
            return {"otimizacoes": []}

        try:
            execucoes = json.loads(rb_log.read_text())
        except Exception:
            return {"otimizacoes": []}

        stats_passos: dict[str, dict] = {}
        for exec_ in execucoes:
            tipo = exec_.get("tipo", "")
            for passo in exec_.get("passos_executados", []):
                chave = f"{tipo}:passo_{passo['ordem']}"
                if chave not in stats_passos:
                    stats_passos[chave] = {"total": 0, "sucesso": 0}
                stats_passos[chave]["total"] += 1
                if passo.get("resolveu"):
                    stats_passos[chave]["sucesso"] += 1

        otimizacoes = []
        for chave, stats in stats_passos.items():
            total = stats["total"]
            sucesso = stats["sucesso"]
            taxa = sucesso / total * 100 if total >= 3 else None

            if taxa is not None:
                if taxa == 0:
                    otimizacoes.append({
                        "passo": chave,
                        "sugestao": "Remover — nunca funciona",
                        "taxa": 0,
                    })
                elif taxa >= 90:
                    otimizacoes.append({
                        "passo": chave,
                        "sugestao": (
                            "Mover para passo 1 — sempre funciona"
                        ),
                        "taxa": taxa,
                    })

        return {"otimizacoes": otimizacoes}

    def relatorio_evolucao(self) -> str:
        """Relatório mensal de evolução do sistema."""
        auditoria = self.auditar_agentes()
        gaps = self.detectar_gaps()
        otimizacoes = self.otimizar_runbooks()

        msg = (
            f"🔬 *Relatório de Auto-Evolução*\n"
            f"_{datetime.now().strftime('%d/%m/%Y')}_\n\n"
        )

        msg += (
            f"👥 *Agentes:*\n"
            f"  ✅ Excelentes: {len(auditoria['excelentes'])}\n"
            f"  ⚠️ Ineficientes: {len(auditoria['ineficientes'])}\n"
            f"  🔊 Ruidosos: {len(auditoria['ruidosos'])}\n\n"
        )

        if auditoria["ineficientes"]:
            msg += "*Agentes para revisar:*\n"
            for a in auditoria["ineficientes"][:3]:
                msg += (
                    f"  • `{a['nome']}`: "
                    f"score médio {a['score_medio']}\n"
                )
            msg += "\n"

        if gaps:
            msg += f"🕳️ *Gaps detectados:* {len(gaps)}\n"
            for g in gaps[:2]:
                msg += (
                    f"  • `{g['area']}`: "
                    f"{g['tickets_perdidos']} tickets perdidos\n"
                )
            msg += "\n"

        otz = otimizacoes.get("otimizacoes", [])
        if otz:
            msg += (
                f"⚙️ *Runbooks — {len(otz)} otimizações "
                f"sugeridas*\n\n"
            )

        # Propostas pendentes
        pendentes = [
            p for p in self.auditoria.get(
                "propostas_novos_agentes", []
            )
            if p.get("status") == "aguardando_jordan"
        ]
        if pendentes:
            msg += (
                f"📋 *Propostas aguardando aprovação:* "
                f"{len(pendentes)}\n\n"
            )

        msg += "_Use /auditar para executar auditoria completa_"
        return msg

    def executar_auditoria_completa(self) -> str:
        """Executa auditoria completa e notifica Jordan."""
        print("[AutoEvolução] Auditoria completa...")

        auditoria = self.auditar_agentes()
        gaps = self.detectar_gaps()

        # Propor novos agentes para gaps críticos
        for gap in gaps:
            if gap["tickets_perdidos"] >= 3:
                self.propor_novo_agente(
                    area=gap["area"],
                    descricao=(
                        f"Monitorar área '{gap['area']}' "
                        f"que gerou {gap['tickets_perdidos']} "
                        f"tickets não detectados"
                    ),
                    justificativa=(
                        f"{gap['tickets_perdidos']} incidentes "
                        f"em '{gap['area']}' passaram "
                        f"despercebidos pelos agentes atuais"
                    ),
                )

        relatorio = self.relatorio_evolucao()
        telegram(relatorio)
        print("✅ Auditoria completa executada")
        return relatorio
