#!/usr/bin/env python3
"""
drift_finder.py — detecta e (opcionalmente) corrige schema drift model<->banco no Conecta PRO.

USO (dentro do container backend, que tem os models + DATABASE_URL):
    docker cp drift_finder.py conecta-pro-backend:/tmp/drift_finder.py
    docker exec conecta-pro-backend python3 /tmp/drift_finder.py <DB> [--dry-run]

  <DB>  = conecta_pro (producao) | conecta_pro_drift_check (staging)
  --dry-run = so detecta e classifica, nao aplica nada.

O QUE FAZ (sem --dry-run):
  - BALDE 2: cria tabelas ausentes (model coerente) VAZIAS, sem FK constraints, com enums.
  - BALDE 1: adiciona TODAS as colunas ausentes em tabelas VAZIAS (full-diff, nao cascata).
  - Tabelas POPULADAS com coluna ausente -> DEFERIDAS (balde 3, possivel rename) — NAO toca.
  - B3_TABLES / SUSPEITO -> puladas e listadas.
  - Reverifica FAIL->OK ao final.

AJUSTE por caso: TARGET_MODS, B3_TABLES (rename-com-dado conhecido), SUSPEITO (FK->tabela inexistente).
Princípio: so CREATE/ADD; NOT NULL apenas em tabela vazia; nada que toque dado real.
"""
import sys, gc, os, re, json
sys.path.insert(0, '/app')  # backend baked no Docker: models vivem em /app
import sqlalchemy as sa
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import DefaultClause, CreateTable
from sqlalchemy import Enum as SAEnum
import asyncio
import main_production  # noqa: carrega todos os models

if len(sys.argv) < 2:
    print("uso: drift_finder.py <db> [--dry-run]"); sys.exit(1)
TARGET_DB = sys.argv[1]
DRY = "--dry-run" in sys.argv
URL = re.sub(r'/[^/]+$', '/' + TARGET_DB, os.environ["DATABASE_URL"])

# ---- AJUSTE POR CASO ----
# modulos no escopo: env CPRO_DRIFT_MODS="crm,financial" sobrepoe; senao default abaixo
TARGET_MODS = set(os.environ.get("CPRO_DRIFT_MODS", "financial,hr").split(","))
# rename-com-dado conhecido (model<->legado) -> pular. env CPRO_DRIFT_B3="nfe,nfse"
B3_TABLES = set(filter(None, os.environ.get("CPRO_DRIFT_B3", "").split(",")))
# FK -> tabela inexistente -> nao criar, revisar. env CPRO_DRIFT_SUSPEITO="employee_documents,..."
SUSPEITO = set(filter(None, os.environ.get("CPRO_DRIFT_SUSPEITO", "").split(",")))
# -------------------------

pg = postgresql.dialect()
def mod_of(c):
    m = c.__module__
    return m.split('.')[1] if m.startswith('modules.') else m.split('.')[0]
def is_enum(t): return isinstance(t, SAEnum) or t.__class__.__name__ == 'ENUM'

mappers = set()
for o in gc.get_objects():
    try:
        if isinstance(o, sa.orm.registry):
            for mp in o.mappers: mappers.add(mp)
    except Exception: pass
tmap = {}
for mp in mappers:
    try:
        if mod_of(mp.class_) in TARGET_MODS: tmap[mp.class_.__tablename__] = mp
    except Exception: pass

async def loadtest(S, mp):
    try:
        async with S() as db:
            (await db.execute(select(mp.class_).limit(1))).scalars().all()
        return ("OK", "")
    except Exception as e:
        return ("FAIL", str(e).split('\n')[0])

async def detect(S):
    """retorna (set tabelas-com-coluna-ausente, list B2, list B3, list SUSPEITO, list OUTROS)"""
    b1t, b2, b3, susp, other = set(), [], [], [], []
    for tbl, mp in sorted(tmap.items()):
        st, err = await loadtest(S, mp)
        if st == "OK": continue
        if "UndefinedTableError" in err:
            (b3 if tbl in B3_TABLES else (susp if tbl in SUSPEITO else b2)).append(tbl)
        elif "UndefinedColumnError" in err:
            b1t.add(tbl)
        else:
            other.append((tbl, err[:90]))
    return b1t, b2, b3, susp, other

def topo(b2):
    """topo-sort SO do subconjunto b2 (evita meta.sorted_tables que quebra em FK orfa global)."""
    b2set = set(b2)
    deps = {n: {fk.target_fullname.split('.')[0].replace('"', '')
                for fk in tmap[n].local_table.foreign_keys
                if fk.target_fullname.split('.')[0].replace('"', '') in b2set
                and fk.target_fullname.split('.')[0].replace('"', '') != n} for n in b2}
    order = []
    while len(order) < len(b2):
        prog = False
        for n in b2:
            if n not in order and deps[n] <= set(order):
                order.append(n); prog = True; break
        if not prog:
            order += [n for n in b2 if n not in order]; break
    return order

def normalize(tb):
    """server_default string de funcao ('gen_random_uuid()') -> text() (senao vira literal aspas)."""
    for col in tb.columns:
        arg = getattr(col.server_default, 'arg', None)
        if isinstance(arg, str) and arg.strip().endswith(')'):
            col.server_default = DefaultClause(text(arg))

async def main():
    eng = create_async_engine(URL)
    S = async_sessionmaker(eng, expire_on_commit=False)
    b1t, b2, b3, susp, other = await detect(S)
    print(f"### TARGET={TARGET_DB}")
    print(f"INICIAL: tabelas-col-ausente={len(b1t)} B2={len(b2)} B3={len(b3)} SUSPEITO={len(susp)} OUTROS={len(other)}")
    if DRY:
        # classificacao por balde COM evidencia (read-only)
        b1_vazias, b3_populadas = [], []
        async with eng.connect() as c:
            for tbl in sorted(b1t):
                rc = (await c.execute(text(f'SELECT count(*) FROM "{tbl}"'))).scalar()
                dbcols = {r[0] for r in (await c.execute(text(
                    "SELECT column_name FROM information_schema.columns WHERE table_name=:t"), {"t": tbl}))}
                miss = [col.name for col in tmap[tbl].columns if col.name not in dbcols]
                (b3_populadas if rc > 0 else b1_vazias).append((tbl, rc, len(miss)))
        print("\n=== CLASSIFICACAO (read-only) ===")
        print(f"BALDE 1 (coluna em tabela VAZIA -> aditivo autonomo): {len(b1_vazias)}")
        for t, rc, n in b1_vazias: print(f"    {t}: {n} colunas ausentes (0 linhas)")
        print(f"BALDE 2 (tabela ausente, criar vazia): {len(b2)} -> {b2}")
        print(f"BALDE 3a (tabela rename-com-dado, PARAR): {len(b3)} -> {b3}")
        print(f"BALDE 3b (tabela POPULADA c/ coluna ausente = possivel rename, PARAR): {len(b3_populadas)}")
        for t, rc, n in b3_populadas: print(f"    {t}: {n} colunas ausentes em {rc} LINHAS reais")
        print(f"SUSPEITO (FK->tabela inexistente, revisar): {len(susp)} -> {susp}")
        print(f"OUTROS (enum/codigo, decisao): {len(other)}")
        for t, e in other: print(f"    {t}: {e}")
        await eng.dispose(); return
    print("B2:", b2); print("B3:", b3); print("SUSPEITO:", susp); print("OUTROS:", other)

    # BALDE 2: criar tabelas vazias (topo-sort, sem FK, com enums manuais)
    created = []
    if b2:
        order = topo(b2)
        async with eng.begin() as conn:
            def _c(sc):
                for n in order:
                    tb = tmap[n].local_table; normalize(tb)
                    for col in tb.columns:
                        if is_enum(col.type):
                            try: col.type.create(sc, checkfirst=True)
                            except Exception: pass
                    sc.execute(CreateTable(tb, if_not_exists=True, include_foreign_key_constraints=[]))
            await conn.run_sync(_c)
        created = order
        print(f"[B2] {len(created)} tabelas criadas (vazias, sem FK).")

    # BALDE 1: full-diff por tabela; SO em tabelas vazias. Populadas -> deferidas (balde 3).
    added, deferred = [], {}
    async with eng.connect() as c:
        for tbl in sorted(b1t):
            rc = (await c.execute(text(f'SELECT count(*) FROM "{tbl}"'))).scalar()
            dbcols = {r[0] for r in (await c.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name=:t"), {"t": tbl}))}
            missing = [col for col in tmap[tbl].columns if col.name not in dbcols]
            if rc > 0:
                deferred[tbl] = {"rows": rc, "missing": [col.name for col in missing]}
            elif missing:
                async with eng.begin() as conn:
                    def _ap(sc, _tbl=tbl, _missing=missing):
                        for col in _missing:
                            if is_enum(col.type):
                                try: col.type.create(sc, checkfirst=True)
                                except Exception: pass
                            nn = "" if col.nullable else " NOT NULL"
                            sc.execute(text(f'ALTER TABLE "{_tbl}" ADD COLUMN IF NOT EXISTS "{col.name}" {col.type.compile(pg)}{nn}'))
                    await conn.run_sync(_ap)
                added += [(tbl, col.name) for col in missing]
    print(f"[B1] {len(added)} colunas adicionadas (tabelas vazias).")

    # verificar
    b1t2, b2b, b3b, suspb, otherb = await detect(S)
    print(f"\n=== FINAL ({TARGET_DB}) ===")
    print(f"B2 criadas: {len(created)} | B1 colunas: {len(added)}")
    print(f"DEFERIDO BALDE 3 (populadas c/ coluna ausente = possivel rename): {deferred}")
    print(f"RESTAM FAIL: tabelas-col={len(b1t2)} B2={len(b2b)} B3={len(b3b)} SUSP={len(suspb)} OUTROS={len(otherb)}")
    json.dump({"created": created, "added": added, "deferred": deferred,
               "remaining_tables": sorted(b1t2), "suspeito": sorted(susp),
               "b3": sorted(b3), "other": other},
              open(f"/tmp/drift_result_{TARGET_DB}.json", "w"))
    print(f"(resultado salvo em /tmp/drift_result_{TARGET_DB}.json)")
    await eng.dispose()

asyncio.run(main())
