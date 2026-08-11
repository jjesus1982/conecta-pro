"""
Analisador — Analisa bugs e propõe correções com contexto.

Fluxo:
1. Recebe descrição do bug (do CTO ou Jordan)
2. Localiza o código usando ConhecimentoTotal
3. Lê o arquivo real linha por linha
4. Propõe correção específica com diff
5. Mede o risco da correção
6. Apresenta para Jordan aprovar
"""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

CTO_DIR = Path("/opt/conecta-pro/agents/cto")
CORRETOR_DIR = CTO_DIR / "corretor"
PATCHES_DIR = CORRETOR_DIR / "patches"
BACKUPS_DIR = CORRETOR_DIR / "backups"

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


def run(cmd: str, timeout: int = 30) -> dict:
    try:
        r = subprocess.run(
            cmd, shell=True,
            capture_output=True, text=True,
            timeout=timeout,
        )
        return {
            "ok": r.returncode == 0,
            "stdout": r.stdout[:500],
            "stderr": r.stderr[:500],
        }
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": str(e)}


class Analisador:
    """Analisa bugs e propõe correções com risco medido."""

    # Matriz de risco por tipo de arquivo
    RISCO_BASE = {
        "controller": 0.6,   # Alto — endpoints diretos
        "service":    0.5,   # Médio-alto — lógica de negócio
        "model":      0.8,   # Muito alto — estrutura de dados
        "schema":     0.4,   # Médio — validação
        "router":     0.7,   # Alto — roteamento
        "task":       0.5,   # Médio-alto — assíncrono
        "util":       0.2,   # Baixo — utilitários
        "helper":     0.2,   # Baixo — helpers
        "config":     0.9,   # Crítico — configuração
        "migration":  1.0,   # PROIBIDO — nunca tocar
        "test":       0.1,   # Mínimo — só testes
    }

    def __init__(self):
        PATCHES_DIR.mkdir(parents=True, exist_ok=True)
        BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
        self.historico = self._carregar_historico()

    def _carregar_historico(self) -> list:
        f = CORRETOR_DIR / "historico" / "analises.json"
        if f.exists():
            try:
                return json.loads(f.read_text())
            except Exception:
                pass
        return []

    def _salvar_historico(self, analise: dict):
        f = CORRETOR_DIR / "historico" / "analises.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        self.historico.append(analise)
        f.write_text(
            json.dumps(
                self.historico[-100:],
                indent=2, ensure_ascii=False, default=str,
            )
        )

    def _calcular_risco(
        self,
        arquivo: str,
        linhas_afetadas: int,
        tipo_mudanca: str,
    ) -> dict:
        """
        Calcula risco da correção de 0 a 1.
        0 = seguro, 1 = extremamente arriscado.
        """
        # Risco base pelo tipo de arquivo
        risco = 0.3  # default
        for tipo, valor in self.RISCO_BASE.items():
            if tipo in arquivo.lower():
                risco = valor
                break

        # Aumentar risco por linhas afetadas
        if linhas_afetadas > 20:
            risco = min(risco + 0.3, 1.0)
        elif linhas_afetadas > 10:
            risco = min(risco + 0.2, 1.0)
        elif linhas_afetadas > 5:
            risco = min(risco + 0.1, 1.0)

        # Tipo de mudança
        if tipo_mudanca == "refatoracao":
            risco = min(risco + 0.2, 1.0)
        elif tipo_mudanca == "adicao":
            risco = max(risco - 0.1, 0.0)
        elif tipo_mudanca == "remocao":
            risco = min(risco + 0.15, 1.0)

        # Arquivos proibidos = risco máximo
        proibidos = [
            "main_production", "alembic/versions",
            "docker-compose", ".env", "credentials",
        ]
        for p in proibidos:
            if p in arquivo:
                risco = 1.0
                break

        # Classificar
        if risco >= 0.8:
            nivel = "CRÍTICO"
            emoji = "🔴"
        elif risco >= 0.6:
            nivel = "ALTO"
            emoji = "🟠"
        elif risco >= 0.4:
            nivel = "MÉDIO"
            emoji = "🟡"
        else:
            nivel = "BAIXO"
            emoji = "🟢"

        return {
            "score": round(risco, 2),
            "nivel": nivel,
            "emoji": emoji,
            "recomendacao": (
                "NÃO RECOMENDADO — risco extremo" if risco >= 0.8 else
                "Requer atenção especial"         if risco >= 0.6 else
                "Proceder com cuidado"            if risco >= 0.4 else
                "Seguro para aplicar"
            ),
        }

    def _ler_arquivo_real(self, caminho: str) -> Optional[str]:
        """Lê arquivo real do sistema."""
        paths = [
            Path(f"/opt/conecta-pro/backend/{caminho}"),
            Path(f"/opt/conecta-pro/{caminho}"),
            Path(caminho),
        ]
        for p in paths:
            if p.exists():
                try:
                    return p.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    pass
        return None

    def _gerar_diff(
        self,
        conteudo_original: str,
        conteudo_novo: str,
        arquivo: str,
    ) -> str:
        """Gera diff legível entre original e novo."""
        orig_lines = conteudo_original.split("\n")
        novo_lines = conteudo_novo.split("\n")

        diff = []
        for i, (orig, novo) in enumerate(zip(orig_lines, novo_lines)):
            if orig != novo:
                diff.append(f"L{i+1} - {orig.strip()[:80]}")
                diff.append(f"L{i+1} + {novo.strip()[:80]}")

        # Linhas extras
        if len(novo_lines) > len(orig_lines):
            for i in range(len(orig_lines), len(novo_lines)):
                diff.append(f"L{i+1} + {novo_lines[i].strip()[:80]}")

        return "\n".join(diff[:30])

    def analisar_bug(
        self,
        descricao: str,
        arquivo: str = None,
        linha: int = None,
        codigo_errado: str = None,
        codigo_correto: str = None,
    ) -> dict:
        """
        Analisa um bug e propõe correção completa.

        Parâmetros:
          descricao: descrição do bug em linguagem natural
          arquivo: caminho do arquivo (opcional)
          linha: linha do bug (opcional)
          codigo_errado: trecho com bug (opcional)
          codigo_correto: correção proposta (opcional)
        """
        analise_id = f"CORR-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        print(f"[Analisador] Analisando: {descricao[:50]}")

        analise = {
            "id": analise_id,
            "timestamp": datetime.now().isoformat(),
            "descricao": descricao,
            "arquivo": arquivo,
            "linha": linha,
            "status": "pendente_aprovacao",
            "risco": {},
            "diff": "",
            "conteudo_original": "",
            "conteudo_proposto": "",
            "testes_a_rodar": [],
            "impacto_estimado": "",
            "aprovado": False,
        }

        # 1. Localizar arquivo se não fornecido
        if not arquivo:
            try:
                _cto_dir = str(CTO_DIR)
                if _cto_dir not in sys.path:
                    sys.path.insert(0, _cto_dir)
                from conhecimento_total import ConhecimentoTotal
                ct = ConhecimentoTotal()
                palavras = [w for w in descricao.split() if len(w) > 4]
                for palavra in palavras[:3]:
                    resultados = ct.buscar_codigo(palavra)
                    if resultados:
                        arquivo = resultados[0]["arquivo"]
                        print(f"  Arquivo localizado: {arquivo}")
                        break
            except Exception as e:
                print(f"  Localização automática: {e}")

        if not arquivo:
            analise["erro"] = (
                "Não consegui localizar o arquivo. "
                "Forneça o caminho manualmente."
            )
            return analise

        analise["arquivo"] = arquivo

        # 2. Ler conteúdo original
        conteudo = self._ler_arquivo_real(arquivo)
        if not conteudo:
            analise["erro"] = f"Arquivo não encontrado: {arquivo}"
            return analise

        analise["conteudo_original"] = conteudo

        # 3. Gerar diff se código fornecido
        if codigo_errado and codigo_correto:
            if codigo_errado in conteudo:
                conteudo_novo = conteudo.replace(codigo_errado, codigo_correto, 1)
                analise["conteudo_proposto"] = conteudo_novo
                analise["diff"] = self._gerar_diff(conteudo, conteudo_novo, arquivo)
                linhas_afetadas = len(analise["diff"].split("\n"))
            else:
                analise["erro"] = "Código original não encontrado no arquivo"
                return analise
        else:
            analise["conteudo_proposto"] = ""
            analise["diff"] = (
                "Correção automática não determinada — "
                "forneça codigo_errado e codigo_correto"
            )
            linhas_afetadas = 1

        # 4. Calcular risco
        tipo_mudanca = "correcao" if codigo_errado else "analise"
        analise["risco"] = self._calcular_risco(arquivo, linhas_afetadas, tipo_mudanca)

        # 5. Testes a rodar
        analise["testes_a_rodar"] = self._determinar_testes(arquivo)

        # 6. Impacto estimado
        analise["impacto_estimado"] = self._estimar_impacto(arquivo, descricao)

        # 7. Salvar patch
        patch_file = PATCHES_DIR / f"{analise_id}_patch.json"
        patch_file.write_text(
            json.dumps(analise, indent=2, ensure_ascii=False, default=str)
        )

        self._salvar_historico({
            "id": analise_id,
            "descricao": descricao,
            "arquivo": arquivo,
            "risco": analise["risco"]["nivel"],
            "status": "pendente",
            "timestamp": analise["timestamp"],
        })

        print(
            f"  ✅ Análise concluída: "
            f"{analise['risco']['emoji']} "
            f"Risco {analise['risco']['nivel']}"
        )
        return analise

    def _determinar_testes(self, arquivo: str) -> list:
        """Determina quais testes rodar após correção."""
        testes = []
        if "departamento_pessoal" in arquivo or "people" in arquivo:
            testes.append(
                "pytest backend/tests/test_departamento_pessoal.py -q"
            )
        if "financeiro" in arquivo or "financial" in arquivo:
            testes.append(
                "pytest backend/tests/test_financeiro_operacional.py -q"
            )
        if "operacional" in arquivo:
            testes.append(
                "pytest backend/tests/test_financeiro_operacional.py -q"
            )
        # Sempre rodar testes críticos
        testes.append("pytest backend/tests/test_endpoints_criticos.py -q")
        return list(set(testes))

    def _estimar_impacto(self, arquivo: str, descricao: str) -> str:
        """Estima impacto da correção no sistema."""
        if "folha" in arquivo.lower() or "payroll" in descricao.lower():
            return "Impacto na folha salarial — afeta 41 funcionários"
        elif "financeiro" in arquivo.lower():
            return "Impacto financeiro — afeta contas a pagar/receber"
        elif "esocial" in arquivo.lower():
            return "Impacto fiscal — afeta transmissão eSocial"
        elif "auth" in arquivo.lower():
            return "Impacto crítico — afeta autenticação de todos os usuários"
        elif "operacional" in arquivo.lower():
            return "Impacto operacional — afeta postos e escalas"
        return "Impacto localizado — módulo específico"

    def formatar_proposta_telegram(self, analise: dict) -> str:
        """Formata proposta para aprovação no Telegram."""
        risco = analise.get("risco", {})
        emoji_risco = risco.get("emoji", "⚠️")
        nivel_risco = risco.get("nivel", "?")
        score_risco = risco.get("score", 0)
        recomendacao = risco.get("recomendacao", "")

        diff_preview = analise.get("diff", "")[:300]
        testes = analise.get("testes_a_rodar", [])

        msg = (
            f"🔧 *Correção Proposta — {analise['id']}*\n\n"
            f"*Bug:* _{analise['descricao'][:100]}_\n\n"
            f"*Arquivo:* `{analise.get('arquivo', '?')}`\n\n"
            f"{emoji_risco} *Risco: {nivel_risco}* ({score_risco*100:.0f}%)\n"
            f"_{recomendacao}_\n\n"
            f"*Impacto estimado:*\n"
            f"_{analise.get('impacto_estimado', '?')}_\n\n"
        )

        if diff_preview:
            msg += f"*Mudanças propostas:*\n```\n{diff_preview}\n```\n\n"

        if testes:
            msg += "*Testes que serão executados:*\n"
            for t in testes[:2]:
                test_name = t.split("/")[-1][:40]
                msg += f"  • `{test_name}`\n"

        msg += (
            f"\n*Se aprovado:*\n"
            f"  1. Backup do arquivo original\n"
            f"  2. Aplicar correção\n"
            f"  3. Rodar testes\n"
            f"  4. Deploy se testes passarem\n"
            f"  5. Reverter automaticamente se falhar\n\n"
            f"Responda:\n"
            f"✅ *aprovar {analise['id']}* para aplicar\n"
            f"❌ *rejeitar {analise['id']}* para cancelar"
        )
        return msg
