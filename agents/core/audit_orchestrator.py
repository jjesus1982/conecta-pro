"""
AuditOrchestrator — Orquestrador de auditoria de código.
Diferente do BaseOrchestrator (monitora endpoints),
este audita arquivos, detecta bugs e corrige automaticamente.

Ciclo:
1. Para cada módulo do ERP
2. Para cada skill solicitada
3. CodeReader detecta bugs
4. CodeFixer corrige os autocorrigíveis
5. Relatório enviado ao Telegram
6. Commit automático
"""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "/opt/conecta-pro/agents/core")
from code_reader import CodeReader
from code_fixer import CodeFixer


TELEGRAM_TOKEN = ""  # pragma: allowlist secret
TELEGRAM_CHAT = "5536961034"
REPORTS_DIR = Path("/opt/conecta-pro/reports/auditorias")

# Mapeamento módulo → path no backend
MODULOS = {
    "departamento_pessoal": "people_management",
    "recursos_humanos": "people_management/human_resources",
    "financeiro": "financial",
    "fiscal_contabil": "government_integrations",
    "operacional": "operacional",
    "ged": "ged",
    "crm": "crm",
    "marketing": "marketing",
    "licitacoes": "bidding",
    "saude_ocupacional": "sst",
    "portais": "hr/employee_portal",
    "equipamentos": "equipment",
    "administrativo": "config",
}

# Skills disponíveis para auditoria automática
SKILLS_AUTO = {
    3: "API RESTful",
    6: "Autenticação",
    9: "UX/Acessibilidade",
    10: "Documentação",
}


class AuditOrchestrator:
    """
    Audita código do ERP módulo por módulo,
    corrige bugs automaticamente e reporta.
    """

    def __init__(self, token: str):
        self.token = token
        self.reader = CodeReader()
        self.fixer = CodeFixer(token=token)
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    def _telegram(self, mensagem: str):
        """Envia mensagem no Telegram."""
        subprocess.run(
            f'curl -sf -X POST '
            f'"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage" '
            f'-d "chat_id={TELEGRAM_CHAT}&parse_mode=HTML" '
            f'--data-urlencode "text={mensagem}" > /dev/null',
            shell=True,
        )

    def _commitar(self, mensagem: str):
        subprocess.run(
            f"cd /opt/conecta-pro && git add -A && "
            f'git commit -m "{mensagem}" && '
            f"git push origin feature/people-management-reorganization",
            shell=True, capture_output=True,
        )

    def auditar_modulo(
        self,
        modulo: str,
        skills: list = None,
        auto_fix: bool = True,
    ) -> dict:
        """Audita um módulo com as skills especificadas."""
        if skills is None:
            skills = list(SKILLS_AUTO.keys())

        backend_path = MODULOS.get(modulo, modulo)
        print(f"\n🔍 Auditando: {modulo} ({backend_path})")
        print(f"   Skills: {[SKILLS_AUTO.get(s, s) for s in skills]}")

        arquivos_backend = self.reader.ler_modulo_backend(backend_path)
        arquivos_frontend = self.reader.ler_modulo_frontend(modulo)

        print(f"   Arquivos backend: {len(arquivos_backend)}")
        print(f"   Arquivos frontend: {len(arquivos_frontend)}")

        todos_bugs = []
        if 3 in skills:
            todos_bugs.extend(
                self.reader.skill03_api_restful(arquivos_backend)
            )
        if 6 in skills:
            todos_bugs.extend(
                self.reader.skill06_auth(arquivos_backend)
            )
        if 9 in skills:
            todos_bugs.extend(
                self.reader.skill09_ux(arquivos_frontend)
            )
        if 10 in skills:
            todos_bugs.extend(self.reader.skill10_docs())

        print(f"   Bugs encontrados: {len(todos_bugs)}")
        autocorrigiveis = sum(
            1 for b in todos_bugs if b.get("autocorrigivel")
        )
        print(f"   Autocorrigíveis: {autocorrigiveis}")

        resultado_fix = {"corrigidos": 0, "pulados": 0}
        if auto_fix and autocorrigiveis > 0:
            print(f"   🔧 Aplicando correções...")
            resultado_fix = self.fixer.corrigir_bugs(todos_bugs)
            print(f"   ✅ Corrigidos: {resultado_fix['corrigidos']}")

        return {
            "modulo": modulo,
            "skills_auditadas": skills,
            "arquivos_analisados": (
                len(arquivos_backend) + len(arquivos_frontend)
            ),
            "bugs_encontrados": len(todos_bugs),
            "autocorrigiveis": autocorrigiveis,
            "corrigidos": resultado_fix["corrigidos"],
            "bugs": todos_bugs,
            "timestamp": datetime.now().isoformat(),
        }

    def auditar_todos(
        self,
        skills: list = None,
        auto_fix: bool = True,
    ) -> dict:
        """
        Audita TODOS os 13 módulos com as skills especificadas.
        Este é o ciclo completo de auditoria.
        """
        if skills is None:
            skills = list(SKILLS_AUTO.keys())

        inicio = datetime.now()
        print(f"\n{'='*60}")
        print(f"CICLO DE AUDITORIA — {inicio.strftime('%Y-%m-%d %H:%M')}")
        print(f"Skills: {[SKILLS_AUTO.get(s, s) for s in skills]}")
        print(f"Módulos: {len(MODULOS)}")
        print(f"{'='*60}")

        resultados = {}
        total_bugs = 0
        total_corrigidos = 0

        for modulo in MODULOS:
            resultado = self.auditar_modulo(
                modulo, skills=skills, auto_fix=auto_fix
            )
            resultados[modulo] = resultado
            total_bugs += resultado["bugs_encontrados"]
            total_corrigidos += resultado["corrigidos"]

        duracao = (datetime.now() - inicio).seconds

        if total_corrigidos > 0:
            self._commitar(
                f"fix(audit): {total_corrigidos} bugs corrigidos "
                f"automaticamente — ciclo auditoria "
                f"{inicio.strftime('%Y-%m-%d')}"
            )

        report = {
            "timestamp": inicio.isoformat(),
            "duracao_segundos": duracao,
            "skills_auditadas": skills,
            "modulos": len(MODULOS),
            "total_bugs": total_bugs,
            "total_corrigidos": total_corrigidos,
            "resultados": resultados,
        }
        report_path = (
            REPORTS_DIR
            / f"auditoria_{inicio.strftime('%Y%m%d_%H%M')}.json"
        )
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False)
        )

        emoji_geral = "✅" if total_bugs == 0 else (
            "🔧" if total_corrigidos == total_bugs else "⚠️"
        )
        msg = (
            f"{emoji_geral} <b>AUDITORIA CONECTA PRO</b>\n"
            f"📅 {inicio.strftime('%d/%m/%Y %H:%M')}\n\n"
            f"🔍 <b>Bugs encontrados:</b> {total_bugs}\n"
            f"🔧 <b>Corrigidos auto:</b> {total_corrigidos}\n"
            f"⏳ <b>Pendentes:</b> {total_bugs - total_corrigidos}\n"
            f"⏱ <b>Duração:</b> {duracao}s\n\n"
        )
        modulos_com_bugs = [
            (m, r) for m, r in resultados.items()
            if r["bugs_encontrados"] > 0
        ]
        if modulos_com_bugs:
            msg += "<b>Módulos com pendências:</b>\n"
            for modulo, r in modulos_com_bugs[:8]:
                pendentes = r["bugs_encontrados"] - r["corrigidos"]
                if pendentes > 0:
                    msg += f"  ⚠️ {modulo}: {pendentes} pendentes\n"
        else:
            msg += "🏆 <b>Nenhum bug encontrado!</b>"

        self._telegram(msg)
        print(f"\n{'='*60}")
        print(f"RESULTADO FINAL")
        print(f"Bugs encontrados: {total_bugs}")
        print(f"Corrigidos: {total_corrigidos}")
        print(f"Duração: {duracao}s")
        print(f"Telegram: ✅ enviado")
        print(f"{'='*60}")

        return report


if __name__ == "__main__":
    import urllib.request
    import urllib.parse

    # Obter token
    data = urllib.parse.urlencode({
        "username": "jjesus@conectamais.pro",
        "password": "Jordan0612",  # pragma: allowlist secret
    }).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:8080/api/v1/auth/login",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        token = json.loads(r.read())["access_token"]

    orch = AuditOrchestrator(token=token)
    orch.auditar_todos(skills=[3, 6, 9, 10], auto_fix=True)
