#!/usr/bin/env python3
"""USO REAL por família: quem escreveu no banco e quem bateu na API — e quando.

Nasceu do critério de "pronto" da missão de 06/09/2026: *uma funcionalidade está pronta
quando o Jordan a usou em produção, num caso real*. Todo o arsenal media `exibido == banco`
e `código == API`; nada media USO. E o mapa que sustenta a missão foi tirado à mão:

    686 tabelas · 463 nunca receberam uma linha (67%) · famílias inteiras mortas
    (ai_ 50, chatbot_ 11, marketplace_ 11, ocr_ 9, push_ 9, scheduler_ 7 …)

Este caçador torna esse número REPETÍVEL e o cruza com a API: uma família com dado antigo
e zero requisição em 15 dias está PARADA, não viva — e tabela nova nascendo com 0 linhas é
regressão (o sistema acumulou 463 assim porque nascer morto nunca acusou nada).

Duas fontes, dois lugares:
  · BANCO   (container)  n_live_tup + max(created_at/updated_at) por tabela, agrupado pelo
                         prefixo do nome (`gp_`, `ai_`, `crm_` …; sem `_` = a própria tabela)
  · ROTAS   (host)       /var/log/nginx/access.log* (≈15 dias) por primeiro segmento após
                         /api/v1/ — só o que um cliente HTTP de fato pediu

⚠️ Ausência fora da janela não é prova (regra do T1): o nginx guarda 15 dias; "0 req" quer
dizer "0 em 15 dias", não "nunca". `git log` não serve para isto — trabalho de DADO não gera
commit; por isso a fonte é o banco e o log, nunca o repositório.

    python3 backend/scripts/qa/checar_uso_real.py              # host: banco (via docker) + rotas
    python3 backend/scripts/qa/checar_uso_real.py --tabelas    # + uma linha por tabela
    python3 backend/scripts/qa/checar_uso_real.py --mortas     # só as tabelas com 0 linhas
    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/qa/checar_uso_real.py --banco

Linha canônica (lida por `checar_regressao`): `TOTAL: <n> tabela(s) com 0 linhas`.
Exit 1 quando há tabela morta (é dívida: entra na base e só acusa quando CRESCE).
"""
from __future__ import annotations

import gzip
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

NGINX = Path("/var/log/nginx")
_RE_LOG = re.compile(r'\[(\d{2}/\w{3}/\d{4}):[^\]]*\] "(?:GET|POST|PUT|PATCH|DELETE) /api/v1/([a-z0-9_-]+)')
_IGNORAR_ROTAS = {"auth", "health", "notifications"}
_COLS_DATA = ("created_at", "criado_em", "data_criacao", "updated_at", "atualizado_em")


def _familia(tabela: str) -> str:
    return tabela.split("_", 1)[0] + "_" if "_" in tabela else tabela


# ── BANCO (roda no container) ────────────────────────────────────────────────
async def _banco() -> list[dict]:
    from sqlalchemy import text  # noqa: PLC0415

    from core.database import async_session_factory  # noqa: PLC0415

    async with async_session_factory() as db:
        tabelas = (await db.execute(text(
            "SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY relname"))).all()
        cols = (await db.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND column_name = ANY(:c)"), {"c": list(_COLS_DATA)})).all()
        datas: dict[str, list[str]] = defaultdict(list)
        for t, c in cols:
            datas[t].append(c)
        out = []
        for nome, vivas in tabelas:
            ultima = None
            if vivas and datas.get(nome):
                expr = ", ".join(f'max("{c}")' for c in datas[nome])
                try:
                    vals = (await db.execute(text(f'SELECT {expr} FROM "{nome}"'))).one()
                    vals = [v for v in vals if v is not None]
                    if vals:
                        ultima = max(v.date() if isinstance(v, datetime) else v for v in vals)
                except Exception:  # noqa: BLE001 — coluna de data com outro tipo: fica sem data
                    pass
            out.append({"tabela": nome, "linhas": int(vivas or 0),
                        "ultima": ultima.isoformat() if ultima else None})
    return out


# ── ROTAS (roda no host) ─────────────────────────────────────────────────────
def _rotas() -> dict[str, dict]:
    uso: dict[str, dict] = defaultdict(lambda: {"req": 0, "ultima": None})
    if not NGINX.is_dir():
        return {}
    for arq in sorted(NGINX.glob("access.log*")):
        abrir = gzip.open if arq.suffix == ".gz" else open
        try:
            with abrir(arq, "rt", errors="replace") as fh:
                for ln in fh:
                    m = _RE_LOG.search(ln)
                    if not m:
                        continue
                    dia = datetime.strptime(m.group(1), "%d/%b/%Y").date()
                    seg = m.group(2)
                    u = uso[seg]
                    u["req"] += 1
                    if u["ultima"] is None or dia > u["ultima"]:
                        u["ultima"] = dia
        except OSError:
            continue
    return {k: {"req": v["req"], "ultima": v["ultima"].isoformat() if v["ultima"] else None}
            for k, v in uso.items() if k not in _IGNORAR_ROTAS}


def _dias(iso: str | None) -> str:
    return "—" if not iso else str(max(0, (date.today() - date.fromisoformat(iso)).days))


def relatorio(tabelas: list[dict], rotas: dict[str, dict], por_tabela: bool, so_mortas: bool) -> int:
    fam: dict[str, dict] = defaultdict(lambda: {"tab": 0, "com_dado": 0, "mortas": 0, "ultima": None})
    for t in tabelas:
        f = fam[_familia(t["tabela"])]
        f["tab"] += 1
        f["com_dado"] += 1 if t["linhas"] else 0
        f["mortas"] += 0 if t["linhas"] else 1
        if t["ultima"] and (f["ultima"] is None or t["ultima"] > f["ultima"]):
            f["ultima"] = t["ultima"]
    mortas = [t for t in tabelas if not t["linhas"]]
    hoje = date.today().isoformat()

    if so_mortas:
        print(f"tabelas com 0 linhas — medido em {hoje}:")
        for t in mortas:
            print(f"   {t['tabela']}")
        print(f"\nTOTAL: {len(mortas)} tabela(s) com 0 linhas")
        return 1 if mortas else 0

    print(f"USO REAL — medido em {hoje} · banco: {len(tabelas)} tabelas · nginx: {'sem log' if not rotas else '≈15 dias'}\n")
    print(f"{'família':<22}{'tab':>5}{'c/dado':>8}{'0-lin':>7}  {'últ.escrita':<12}{'dias':>5}   {'req/15d':>8}  {'últ.req':<10}")
    for nome, f in sorted(fam.items(), key=lambda kv: (-kv[1]['mortas'], kv[0])):
        chave = nome.rstrip("_").replace("_", "-")
        r = rotas.get(chave) or rotas.get(nome.rstrip("_")) or {}
        print(f"{nome:<22}{f['tab']:>5}{f['com_dado']:>8}{f['mortas']:>7}  {f['ultima'] or '—':<12}"
              f"{_dias(f['ultima']):>5}   {r.get('req', 0):>8}  {r.get('ultima') or '—':<10}")
    if rotas:
        so_rota = sorted(set(rotas) - {n.rstrip('_').replace('_', '-') for n in fam} - {n.rstrip('_') for n in fam})
        if so_rota:
            print("\nrotas com uso e sem família de tabela com o mesmo nome (prefixo ≠ tabela, normal):")
            for k in so_rota:
                print(f"   /api/v1/{k:<24} {rotas[k]['req']:>6} req · última {rotas[k]['ultima']}")
    if por_tabela:
        print("\npor tabela (linhas · última escrita):")
        for t in tabelas:
            print(f"   {t['tabela']:<48}{t['linhas']:>8}  {t['ultima'] or '—'}")
    total_dado = sum(1 for t in tabelas if t["linhas"])
    print(f"\n{total_dado} tabela(s) com dado · {len(mortas)} com 0 linhas ({100 * len(mortas) // max(len(tabelas), 1)}%)")
    print(f"TOTAL: {len(mortas)} tabela(s) com 0 linhas")
    return 1 if mortas else 0


def main() -> int:
    if "--banco" in sys.argv:
        import asyncio  # noqa: PLC0415
        if not Path("/app/scripts").is_dir():
            print("RECUSO: --banco roda DENTRO do container (precisa do banco)")
            return 2
        print(json.dumps(asyncio.run(_banco())))
        return 0
    if not Path("/opt/conecta-pro").is_dir():
        print("RECUSO: roda no HOST (precisa do docker e do /var/log/nginx)")
        return 2
    r = subprocess.run(["docker", "exec", "-e", "PYTHONPATH=/app", "conecta-pro-backend",
                        "python3", "/app/scripts/qa/checar_uso_real.py", "--banco"],
                       capture_output=True, text=True, timeout=900)
    linha = next((ln for ln in r.stdout.splitlines() if ln.startswith("[")), "")
    if not linha:
        print(f"RECUSO: o container não respondeu — {(r.stderr or r.stdout).strip()[-200:]}")
        return 2
    return relatorio(json.loads(linha), _rotas(), "--tabelas" in sys.argv, "--mortas" in sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
