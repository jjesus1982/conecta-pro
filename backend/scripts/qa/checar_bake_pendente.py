#!/usr/bin/env python3
"""O que está NO AR por `docker cp` e não na imagem — e assar sozinho quando é seguro.

"docker cp é volátil. Só o bake entrega" (regra da casa). Mas ninguém media o que estava
no ar por cp: em 06/09/2026 eram 14 arquivos .py só no backend, de pelo menos duas
sessões, e um recreate a qualquer hora reverteria todos sem aviso. `docker diff` sabe
exatamente isso — a camada gravável do container é, por definição, o que não veio da imagem.

Medir é a primeira metade. A segunda, pedida pelo Jordan ("de a ele essa habilidade"): assar
sozinho na madrugada, com os mesmos cuidados que uma pessoa teria — e recusando, dizendo
por quê, quando qualquer um falta:

  1. há arquivo pendente (senão não há o que assar);
  2. o lock de deploy está livre;
  3. é madrugada (01:00–05:00) — ou `--agora`;
  4. `git status --porcelain -- backend/` está LIMPO: o bake publica o DISCO, e WIP de outra
     sessão iria para produção sem estar no git. Isto é o que mais recusa — e é o certo;
  5. o WhatsApp está quieto há 30 min (`cwi_message_log`) — o worker cai no meio do bake;
  6. `alembic current` == `alembic heads`: migration pendente exige mão humana
     (`alembic upgrade heads` é manual pós-bake, por decisão da casa).

    python3 backend/scripts/qa/checar_bake_pendente.py            # mede
    python3 backend/scripts/qa/checar_bake_pendente.py --assar    # mede e assa se os 6 passam
    python3 backend/scripts/qa/checar_bake_pendente.py --assar --agora

Linha canônica: `TOTAL: <n> arquivo(s) no ar fora da imagem`. Exit 1 se houver (dívida:
entra na base, acusa quando cresce; cai a zero sozinha depois do bake).
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path("/opt/conecta-pro")
LOCK = Path("/tmp/conecta_deploy.lock")
DEPLOY = REPO / "scripts/deploy_backend_bluegreen.sh"
LOG_AUTO = Path("/var/log/conecta-bake-auto.log")


def _sh(cmd: list[str], timeout: int = 120) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except subprocess.TimeoutExpired:
        return ""


def _containers() -> list[str]:
    nomes = _sh(["docker", "ps", "--format", "{{.Names}}"]).split()
    return sorted(n for n in nomes if n == "conecta-pro-backend" or "celery" in n)


def pendentes() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for c in _containers():
        linhas = _sh(["docker", "diff", c]).splitlines()
        arqs = sorted(ln[2:] for ln in linhas if ln[:1] in "CA" and ln.endswith(".py")
                      and ln[2:].startswith("/app/") and "__pycache__" not in ln)
        if arqs:
            out[c] = arqs
    return out


def _guardas() -> list[str]:
    motivos = []
    if LOCK.exists():
        motivos.append(f"lock de deploy ocupado ({(LOCK / 'owner').read_text().strip() if (LOCK / 'owner').exists() else LOCK})")
    h = datetime.now().hour
    if "--agora" not in sys.argv and not (1 <= h < 5):
        motivos.append(f"fora da janela 01:00–05:00 (agora {h:02d}h) — use --agora para forçar")
    sujo = _sh(["git", "-C", str(REPO), "status", "--porcelain", "--", "backend/"]).strip()
    if sujo:
        n = len(sujo.splitlines())
        motivos.append(f"{n} arquivo(s) de backend/ fora do HEAD (WIP de alguma sessão iria para produção): "
                       + "; ".join(sujo.splitlines()[:4]))
    wpp = _sh(["docker", "exec", "conecta-pro-backend", "python3", "-c",
               "from core.database.session import SyncSessionLocal; from sqlalchemy import text; "
               "print('N=', SyncSessionLocal().execute(text(\"select count(*) from cwi_message_log where created_at > now()-interval '30 minutes'\")).scalar())"])
    n_wpp = next((ln[2:].strip() for ln in wpp.splitlines() if ln.startswith("N=")), None)
    if n_wpp is None:
        motivos.append("não consegui perguntar ao banco se o WhatsApp está em uso — NÃO VERIFICADO")
    elif int(n_wpp) > 0:
        motivos.append(f"WhatsApp em uso: {n_wpp} mensagem(ns) nos últimos 30 min — o worker cairia no meio")
    cur = {ln.split()[0] for ln in _sh(["docker", "exec", "conecta-pro-backend", "sh", "-c", "cd /app && alembic current 2>/dev/null"], 180).splitlines() if ln.strip()}
    heads = {ln.split()[0] for ln in _sh(["docker", "exec", "conecta-pro-backend", "sh", "-c", "cd /app && alembic heads 2>/dev/null"], 180).splitlines() if ln.strip()}
    if not cur or not heads:
        motivos.append("alembic não respondeu — NÃO VERIFICADO")
    elif not heads <= cur:
        motivos.append(f"migration pendente ({sorted(heads - cur)}): `alembic upgrade heads` é manual — bake humano")
    # 7. BOOT DE PROVA do disco que vai virar imagem: main_production E celery_app (com os
    #    módulos de task importados). Em 07/09/2026 um bake recriou 2 workers em crash-loop
    #    porque celery_app incluía um pacote apagado — o servidor subia, o worker não.
    boot = _boot_de_prova()
    if boot:
        motivos.append(f"boot de prova falhou: {boot}")
    return motivos


def _boot_de_prova() -> str:
    """Importa main_production e celery_app (+ tasks) num container DESCARTÁVEL da imagem
    atual com o disco montado. Devolve '' se os dois sobem, senão o erro."""
    env = _sh(["docker", "inspect", "-f", "{{range .Config.Env}}{{.}}\n{{end}}", "conecta-pro-backend"])
    rede = _sh(["docker", "inspect", "-f", "{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}",
                "conecta-pro-backend"]).split()
    if not env or not rede:
        return "não consegui ler env/rede do backend"
    envf = Path("/tmp/conecta_boot_env.txt")
    envf.write_text(env)
    try:
        r = subprocess.run(["docker", "run", "--rm", "--network", rede[0], "--env-file", str(envf),
                            "-v", "/opt/conecta-pro/backend:/app:ro", "-w", "/app",
                            "conecta-pro-backend:latest", "python3", "-c",
                            "from celery_app import app; app.loader.import_default_modules(); "
                            "n=len([t for t in app.tasks if not t.startswith('celery.')]); assert n>50, n; "
                            "import main_production; print('BOOT_OK', n)"],
                           capture_output=True, text=True, timeout=420)
    except subprocess.TimeoutExpired:
        return "não terminou em 7min"
    finally:
        envf.unlink(missing_ok=True)
    if "BOOT_OK" in r.stdout:
        return ""
    ultimas = [ln for ln in (r.stderr + r.stdout).splitlines() if "Error" in ln or "No module" in ln]
    return (ultimas or ["sem saída"])[-1][:200]


def main() -> int:
    pend = pendentes()
    total = sum(len(v) for v in pend.values())
    for c, arqs in pend.items():
        print(f"  {c}: {len(arqs)} arquivo(s) fora da imagem")
        for a in arqs[:8]:
            print(f"     {a}")
        if len(arqs) > 8:
            print(f"     (+{len(arqs) - 8})")
    print(f"\nTOTAL: {total} arquivo(s) no ar fora da imagem")
    if "--assar" in sys.argv:
        if not total:
            print("nada a assar")
            return 0
        motivos = _guardas()
        if motivos:
            print("\nNÃO ASSO — " + " · ".join(motivos))
            return 1
        LOG_AUTO.parent.mkdir(parents=True, exist_ok=True)
        with LOG_AUTO.open("a") as fh:
            fh.write(f"\n═══ {datetime.now():%F %T} bake automático: {total} arquivo(s) pendentes ═══\n")
            p = subprocess.Popen(["bash", str(DEPLOY)], stdout=fh, stderr=subprocess.STDOUT,
                                 cwd=str(REPO), start_new_session=True)
        print(f"\nASSANDO em background (pid {p.pid}) — log: {LOG_AUTO}. Leva ~15 min; "
              f"`checar_drift_workers` roda no fim do próprio deploy.")
        return 0
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
