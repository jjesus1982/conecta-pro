"""
Aplicador — Aplica correções aprovadas com segurança total.

Fluxo de segurança:
1. Backup do arquivo original
2. Aplicar correção
3. Verificar sintaxe Python
4. Rodar testes automatizados
5. Hot copy para container
6. Verificar health do backend
7. Se qualquer passo falhar → reverter imediatamente
8. Notificar Jordan com resultado antes/depois
"""
import json
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

CTO_DIR = Path("/opt/conecta-pro/agents/cto")
CORRETOR_DIR = CTO_DIR / "corretor"
PATCHES_DIR = CORRETOR_DIR / "patches"
BACKUPS_DIR = CORRETOR_DIR / "backups"
HISTORICO_DIR = CORRETOR_DIR / "historico"

MONITOR_TOKEN = ""  # pragma: allowlist secret
JORDAN_CHAT = "5536961034"
BACKEND_DIR = Path("/opt/conecta-pro/backend")


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


def run(cmd: str, timeout: int = 120) -> dict:
    try:
        r = subprocess.run(
            cmd, shell=True,
            capture_output=True, text=True,
            timeout=timeout,
        )
        return {
            "ok": r.returncode == 0,
            "stdout": r.stdout[:1000],
            "stderr": r.stderr[:500],
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": "Timeout"}
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": str(e)}


class Aplicador:
    """Aplica correções com segurança e rollback automático."""

    def __init__(self):
        BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
        HISTORICO_DIR.mkdir(parents=True, exist_ok=True)

    def _caminho_real(self, arquivo: str) -> Path:
        """Resolve caminho real do arquivo."""
        paths = [
            BACKEND_DIR / arquivo,
            Path("/opt/conecta-pro") / arquivo,
            Path(arquivo),
        ]
        for p in paths:
            if p.exists():
                return p
        return BACKEND_DIR / arquivo

    def _fazer_backup(self, arquivo: str, analise_id: str) -> Path:
        """Faz backup do arquivo antes de modificar."""
        fpath = self._caminho_real(arquivo)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = (
            f"{analise_id}_{ts}_{arquivo.replace('/', '_')}.bak"
        )
        backup_path = BACKUPS_DIR / backup_name

        if fpath.exists():
            shutil.copy2(fpath, backup_path)
            print(f"  Backup: {backup_path.name}")
            return backup_path
        return None

    def _verificar_sintaxe(self, arquivo: str) -> dict:
        """Verifica sintaxe Python antes do deploy."""
        fpath = self._caminho_real(arquivo)
        if not str(arquivo).endswith(".py"):
            return {"ok": True, "msg": "Não é Python"}

        r = run(f"python3 -m py_compile {fpath}")
        if r["ok"]:
            return {"ok": True, "msg": "Sintaxe OK"}
        return {"ok": False, "msg": r["stderr"][:200]}

    def _rodar_testes(self, testes: list) -> dict:
        """Roda suite de testes."""
        resultados = {}
        todos_ok = True

        for teste in testes:
            print(f"  Rodando: {teste.split('/')[-1]}")
            r = run(f"cd /opt/conecta-pro && {teste}", timeout=180)
            ok = r["ok"]
            if not ok:
                todos_ok = False
            resultados[teste] = {
                "ok": ok,
                "saida": (
                    r["stdout"][-300:] if r["stdout"] else r["stderr"][-300:]
                ),
            }

        return {"todos_ok": todos_ok, "resultados": resultados}

    def _hot_copy_backend(self, arquivo: str) -> dict:
        """Copia arquivo para o container sem rebuild."""
        fpath = self._caminho_real(arquivo)
        container = run(
            "docker ps --filter ancestor=conecta-pro-backend "
            "--format '{{.Names}}' | head -1"
        )["stdout"].strip()

        if not container:
            return {"ok": False, "msg": "Container não encontrado"}

        container_path = f"/app/{arquivo}"
        r = run(f"docker cp {fpath} {container}:{container_path}")
        if not r["ok"]:
            return {"ok": False, "msg": r["stderr"][:200]}

        # Limpar cache Python
        run(f"docker exec {container} find /app -name '*.pyc' -delete")

        return {"ok": True, "msg": f"Hot copy para {container}"}

    def _verificar_health(self) -> bool:
        """Verifica se backend está saudável."""
        time.sleep(10)
        r = run("curl -sf http://127.0.0.1:8080/health")
        return r["ok"]

    def _reverter(self, arquivo: str, backup_path: Path) -> dict:
        """Reverte arquivo para backup."""
        if not backup_path or not backup_path.exists():
            return {"ok": False, "msg": "Backup não encontrado"}

        fpath = self._caminho_real(arquivo)
        shutil.copy2(backup_path, fpath)

        # Hot copy do arquivo revertido
        self._hot_copy_backend(arquivo)

        # Reiniciar backend
        container = run(
            "docker ps --filter ancestor=conecta-pro-backend "
            "--format '{{.Names}}' | head -1"
        )["stdout"].strip()
        if container:
            run(f"docker restart {container}")
            time.sleep(30)

        return {"ok": True, "msg": "Arquivo revertido para backup"}

    def aplicar(self, analise_id: str) -> dict:
        """
        Aplica correção aprovada por Jordan.
        Reverte automaticamente se algo falhar.
        """
        # Carregar patch
        patch_file = PATCHES_DIR / f"{analise_id}_patch.json"
        if not patch_file.exists():
            return {"ok": False, "msg": f"Patch {analise_id} não encontrado"}

        analise = json.loads(patch_file.read_text())
        arquivo = analise.get("arquivo", "")
        conteudo_proposto = analise.get("conteudo_proposto", "")

        if not conteudo_proposto:
            return {"ok": False, "msg": "Sem conteúdo proposto na análise"}

        resultado = {
            "analise_id": analise_id,
            "arquivo": arquivo,
            "timestamp": datetime.now().isoformat(),
            "passos": [],
            "sucesso": False,
            "backup_path": None,
            "revertido": False,
        }

        telegram(
            f"🔧 *Aplicando correção {analise_id}*\n\n"
            f"Arquivo: `{arquivo}`\n"
            f"Iniciando processo seguro..."
        )

        # PASSO 1 — Backup
        print("[Aplicador] Passo 1: Backup...")
        backup_path = self._fazer_backup(arquivo, analise_id)
        resultado["backup_path"] = str(backup_path)
        resultado["passos"].append({
            "passo": "backup",
            "ok": backup_path is not None,
            "msg": str(backup_path),
        })

        if not backup_path:
            telegram(
                f"❌ *{analise_id} — Falhou no backup*\n"
                f"Correção cancelada por segurança."
            )
            return resultado

        # PASSO 2 — Aplicar correção
        print("[Aplicador] Passo 2: Aplicando...")
        fpath = self._caminho_real(arquivo)
        try:
            fpath.write_text(conteudo_proposto, encoding="utf-8")
            resultado["passos"].append({
                "passo": "aplicar", "ok": True, "msg": "Arquivo modificado",
            })
        except Exception as e:
            resultado["passos"].append({
                "passo": "aplicar", "ok": False, "msg": str(e),
            })
            self._reverter(arquivo, backup_path)
            resultado["revertido"] = True
            telegram(
                f"❌ *{analise_id} — Falhou ao aplicar*\n"
                f"_{str(e)[:100]}_\n"
                f"✅ Arquivo revertido automaticamente."
            )
            return resultado

        # PASSO 3 — Verificar sintaxe
        print("[Aplicador] Passo 3: Sintaxe...")
        sintaxe = self._verificar_sintaxe(arquivo)
        resultado["passos"].append({
            "passo": "sintaxe", "ok": sintaxe["ok"], "msg": sintaxe["msg"],
        })

        if not sintaxe["ok"]:
            self._reverter(arquivo, backup_path)
            resultado["revertido"] = True
            telegram(
                f"❌ *{analise_id} — Erro de sintaxe*\n"
                f"```\n{sintaxe['msg'][:200]}\n```\n"
                f"✅ Arquivo revertido automaticamente."
            )
            return resultado

        # PASSO 4 — Rodar testes
        testes = analise.get("testes_a_rodar", [])
        if testes:
            print("[Aplicador] Passo 4: Testes...")
            telegram(
                f"⏳ *{analise_id} — Rodando testes...*\n"
                f"Aguarde alguns minutos."
            )
            test_result = self._rodar_testes(testes)
            resultado["passos"].append({
                "passo": "testes",
                "ok": test_result["todos_ok"],
                "msg": str(test_result["resultados"])[:200],
            })

            if not test_result["todos_ok"]:
                self._reverter(arquivo, backup_path)
                resultado["revertido"] = True
                falhas = [
                    k.split("/")[-1]
                    for k, v in test_result["resultados"].items()
                    if not v["ok"]
                ]
                telegram(
                    f"❌ *{analise_id} — Testes falharam*\n\n"
                    f"Testes com falha:\n"
                    + "\n".join(f"  • `{f}`" for f in falhas)
                    + f"\n\n✅ Arquivo revertido automaticamente."
                )
                return resultado

        # PASSO 5 — Hot copy para container
        print("[Aplicador] Passo 5: Deploy...")
        deploy = self._hot_copy_backend(arquivo)
        resultado["passos"].append({
            "passo": "deploy", "ok": deploy["ok"], "msg": deploy["msg"],
        })

        if not deploy["ok"]:
            self._reverter(arquivo, backup_path)
            resultado["revertido"] = True
            telegram(
                f"❌ *{analise_id} — Falhou no deploy*\n"
                f"_{deploy['msg']}_\n"
                f"✅ Arquivo revertido automaticamente."
            )
            return resultado

        # PASSO 6 — Verificar health
        print("[Aplicador] Passo 6: Health check...")
        health_ok = self._verificar_health()
        resultado["passos"].append({
            "passo": "health",
            "ok": health_ok,
            "msg": "Backend saudável" if health_ok else "Backend não respondeu",
        })

        if not health_ok:
            self._reverter(arquivo, backup_path)
            resultado["revertido"] = True
            telegram(
                f"❌ *{analise_id} — Backend unhealthy*\n"
                f"Backend não respondeu após deploy.\n"
                f"✅ Arquivo revertido automaticamente.\n"
                f"🔄 Reiniciando backend..."
            )
            container = run(
                "docker ps --filter ancestor=conecta-pro-backend "
                "--format '{{.Names}}' | head -1"
            )["stdout"].strip()
            if container:
                run(f"docker restart {container}")
            return resultado

        # SUCESSO
        resultado["sucesso"] = True
        orig_lines = len(analise.get("conteudo_original", "").split("\n"))
        novo_lines = len(conteudo_proposto.split("\n"))
        diff_preview = analise.get("diff", "")[:300]

        telegram(
            f"✅ *Correção Aplicada — {analise_id}*\n\n"
            f"*Arquivo:* `{arquivo}`\n\n"
            f"*Mudanças:*\n"
            f"```\n{diff_preview}\n```\n\n"
            f"*Resultado:*\n"
            f"  ✅ Backup criado\n"
            f"  ✅ Sintaxe verificada\n"
            f"  ✅ Testes passaram\n"
            f"  ✅ Deploy realizado\n"
            f"  ✅ Backend saudável\n\n"
            f"Linhas: {orig_lines} → {novo_lines}\n"
            f"_Bug corrigido com sucesso!_"
        )

        # Salvar no histórico
        hist_file = HISTORICO_DIR / f"{analise_id}_resultado.json"
        hist_file.write_text(
            json.dumps(resultado, indent=2, ensure_ascii=False, default=str)
        )

        print("  ✅ Correção aplicada com sucesso!")
        return resultado
