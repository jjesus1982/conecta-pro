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
import os
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
#: O critério de "pronto" da missão é "o Jordan usou". `--quem <email>` troca a pessoa.
DONO = os.getenv("USO_REAL_DONO", "jjesus@conectamais.pro")
ALEMBIC = Path("/opt/conecta-pro/backend/alembic/versions")


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
        # escritas AUTENTICADAS por rota (crm_audit_log: todo POST/PUT/PATCH/DELETE com user_id
        # do JWT — é a única fonte que diz QUEM): por segmento, 30 dias, e a última do dono.
        escritas = (await db.execute(text("""
            SELECT split_part(path, '/', 4) AS seg, count(*) AS n, count(DISTINCT user_id) AS pessoas,
                   max(ts)::date AS ultima,
                   max(ts) FILTER (WHERE user_id::text IN (SELECT id::text FROM users WHERE email = :dono))::date AS ultima_dono
            FROM crm_audit_log WHERE ts > now() - interval '30 days' AND path LIKE '/api/v1/%'
            GROUP BY 1"""), {"dono": DONO})).all()
        telas = (await db.execute(text("""
            SELECT split_part(path, '/', 6) AS slug, count(*) AS n, count(DISTINCT user_id) AS pessoas,
                   max(ts)::date AS ultima,
                   max(ts) FILTER (WHERE user_id::text IN (SELECT id::text FROM users WHERE email = :dono))::date AS ultima_dono
            FROM crm_audit_log WHERE ts > now() - interval '30 days' AND method = 'GET'
              AND path LIKE '/api/v1/redesign/data/%' GROUP BY 1"""), {"dono": DONO})).all()
        out = [{"_telas": {r.slug: {"n": int(r.n), "pessoas": int(r.pessoas),
                                   "ultima": r.ultima.isoformat() if r.ultima else None,
                                   "ultima_dono": r.ultima_dono.isoformat() if r.ultima_dono else None}
                           for r in telas},
                "_escritas": {r.seg: {"n": int(r.n), "pessoas": int(r.pessoas),
                                     "ultima": r.ultima.isoformat() if r.ultima else None,
                                     "ultima_dono": r.ultima_dono.isoformat() if r.ultima_dono else None}
                              for r in escritas}}]
        for nome, vivas in tabelas:
            if not vivas:
                # `n_live_tup` é ESTIMATIVA e fica em 0 até o autovacuum passar: em 06/09/2026
                # `fin_journal_entries` tinha 11 linhas e `cct_convencoes` 1 com n_live_tup=0.
                # Zero é a única contagem que vale a pena confirmar — e é barata.
                try:
                    vivas = int((await db.execute(text(f'SELECT count(*) FROM "{nome}"'))).scalar() or 0)
                except Exception:  # noqa: BLE001
                    # Sessão async: uma consulta que falha ABORTA a transação e toda consulta
                    # seguinte falha junto — sem rollback, 15 tabelas com linhas saíram como 0
                    # (06/09/2026) e a quarentena só não as levou porque o script recusa mover
                    # tabela com linhas. Rollback aqui e no `max()` abaixo.
                    await db.rollback()
                    vivas = 0
            ultima = None
            if vivas and datas.get(nome):
                expr = ", ".join(f'max("{c}")' for c in datas[nome])
                try:
                    vals = (await db.execute(text(f'SELECT {expr} FROM "{nome}"'))).one()
                    vals = [v for v in vals if v is not None]
                    if vals:
                        ultima = max(v.date() if isinstance(v, datetime) else v for v in vals)
                except Exception:  # noqa: BLE001 — coluna de data com outro tipo: fica sem data
                    await db.rollback()
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


def _nascimento() -> dict[str, str]:
    """tabela -> data do commit que criou a migration mais antiga que a cita (host, git)."""
    if not ALEMBIC.is_dir():
        return {}
    datas: dict[str, str] = {}
    for arq in ALEMBIC.glob("*.py"):
        r = subprocess.run(["git", "-C", "/opt/conecta-pro", "log", "--diff-filter=A", "--format=%as", "--", str(arq)],
                           capture_output=True, text=True)
        dia = (r.stdout.strip().splitlines() or [""])[-1]
        if not dia:
            continue
        for nome in set(re.findall(r"""['"]([a-z][a-z0-9_]{3,})['"]""", arq.read_text(errors="replace"))):
            if nome not in datas or dia < datas[nome]:
                datas[nome] = dia
    return datas


def relatorio(tabelas: list[dict], rotas: dict[str, dict], por_tabela: bool, so_mortas: bool,
              escritas: dict[str, dict] | None = None, dono: str = DONO,
              telas: dict[str, dict] | None = None) -> int:
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
        nasc = _nascimento()
        print(f"tabelas com 0 linhas — medido em {hoje} (nascimento = migration mais antiga que a cita; "
              f"'sem migration' = criada por create_all/SQL solto):")
        for t in mortas:
            print(f"   {t['tabela']:<48} {nasc.get(t['tabela'], 'sem migration')}")
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
    if escritas:
        print(f"\nescritas AUTENTICADAS por rota (crm_audit_log, 30 dias) · última de {dono}:")
        print(f"   {'rota':<24}{'escritas':>9}{'pessoas':>9}  {'última':<12}{'última do dono':<14}")
        for seg, e in sorted(escritas.items(), key=lambda kv: -kv[1]["n"]):
            print(f"   /api/v1/{seg:<16}{e['n']:>9}{e['pessoas']:>9}  {e['ultima'] or '—':<12}{e['ultima_dono'] or '—':<14}")
    print(f"\ntelas do redesign ABERTAS (crm_audit_log GET, 30 dias) · última de {dono}:")
    if not telas:
        print("   (nenhum registro — o middleware só grava leituras de tela a partir do bake de 06/09/2026)")
    else:
        print(f"   {'tela':<40}{'aberturas':>10}{'pessoas':>9}  {'última':<12}{'última do dono':<14}")
        for slug, e in sorted(telas.items(), key=lambda kv: -kv[1]["n"]):
            print(f"   {slug:<40}{e['n']:>10}{e['pessoas']:>9}  {e['ultima'] or '—':<12}{e['ultima_dono'] or '—':<14}")
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
    if "--quem" in sys.argv:
        global DONO
        DONO = sys.argv[sys.argv.index("--quem") + 1]
    if not Path("/opt/conecta-pro").is_dir():
        print("RECUSO: roda no HOST (precisa do docker e do /var/log/nginx)")
        return 2
    r = subprocess.run(["docker", "exec", "-e", "PYTHONPATH=/app", "-e", f"USO_REAL_DONO={DONO}",
                        "conecta-pro-backend", "python3", "/app/scripts/qa/checar_uso_real.py", "--banco"],
                       capture_output=True, text=True, timeout=900)
    linha = next((ln for ln in r.stdout.splitlines() if ln.startswith("[")), "")
    if not linha:
        print(f"RECUSO: o container não respondeu — {(r.stderr or r.stdout).strip()[-200:]}")
        return 2
    dados = json.loads(linha)
    escritas = dados[0]["_escritas"] if dados and "_escritas" in dados[0] else {}
    telas = dados[0].get("_telas", {}) if dados and "_escritas" in dados[0] else {}
    tabelas = [d for d in dados if "tabela" in d]
    return relatorio(tabelas, _rotas(), "--tabelas" in sys.argv, "--mortas" in sys.argv, escritas, DONO, telas)


if __name__ == "__main__":
    raise SystemExit(main())
