"""Carrega os PERÍODOS AQUISITIVOS da Programação de Férias da Portte em employee_vacation_periods.

Por que: a tabela tinha 67 linhas SINTÉTICAS (todas start_date 2026-01-19, geradas em 22/03),
então o "saldo de férias" exibido nas telas e usado pela rescisão não correspondia a nada.
A programação traz o período aquisitivo REAL por pessoa, os dias de direito já reduzidos por
falta (art. 130) e o LIMITE PARA GOZO — que é o que permite alertar férias em dobro (art. 137).

⚠️ NÃO carrega "Dias goz." — a programação é foto de 08/01/2026 e traz 0 para todo mundo.
Sobrescrever apagaria os dias gozados corrigidos em 04/08 a partir de evidência da folha.
O days_used existente é PRESERVADO.

Uso:
  python3 ferias_carregar_programacao.py            # dry-run (default, nada escrito)
  python3 ferias_carregar_programacao.py --persist  # grava (faz backup antes)
"""

import json
import os
import re
import sys
import unicodedata
import uuid
from collections import defaultdict
from datetime import datetime

import fitz
from sqlalchemy import create_engine, text

PDF = sys.argv[sys.argv.index("--pdf") + 1] if "--pdf" in sys.argv else "/tmp/prog.pdf"
PERSIST = "--persist" in sys.argv
DATA = re.compile(r"^\d{2}/\d{2}/\d{4}$")
SEM_COND = "00000000-0000-0000-0000-000000000001"  # convenção já usada em hr_payslips


def _norm(s: str) -> str:
    """Nome sem acento, sem conectivo. A programação omite conectivos que o cadastro tem
    (OSCAR SOARES [DA] COSTA FILHO) — sem isto a pessoa cai como 'sem cadastro'."""
    s = unicodedata.normalize("NFKD", (s or "").upper())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(w for w in s.split() if w not in {"DA", "DE", "DO", "DAS", "DOS", "E"})


def _d(s):
    return datetime.strptime(s, "%d/%m/%Y").date()


def parse_pdf(path: str) -> list[dict]:
    """Lê as linhas por coordenada (o get_text cru sai fora de ordem, por coluna)."""
    doc = fitz.open(path)
    registros, atual = [], None
    for pg in doc:
        linhas = defaultdict(list)
        for x0, y0, _x1, _y1, w, *_ in pg.get_text("words"):
            linhas[round(y0)].append((x0, w))
        for y in sorted(linhas):
            t = [w for _, w in sorted(linhas[y])]
            # a cauda é fixa: ... inicio_aq fim_aq inicio_gozo dias abono 13o dir goz rest limite afast faltas
            if len(t) < 12 or not (DATA.match(t[-12] or "") and DATA.match(t[-11] or "")):
                continue
            if not DATA.match(t[-3] or ""):  # limite p/ gozo
                continue
            if t[0].isdigit() and len(t) >= 16 and DATA.match(t[-16] if len(t) > 16 else ""):
                atual = " ".join(t[1:-16])  # linha-cabeçalho: código + nome + admissão…
            if atual is None:
                continue
            registros.append({
                "nome": atual,
                "inicio_aq": t[-12], "fim_aq": t[-11],
                "dias_dir": t[-6], "dias_goz": t[-5], "dias_rest": t[-4],
                "limite": t[-3],
                "afast": t[-2], "faltas": t[-1],
            })
    return registros


regs = parse_pdf(PDF)
por_pessoa = defaultdict(list)
for r in regs:
    por_pessoa[r["nome"]].append(r)
print(f"PDF: {len(regs)} períodos em {len(por_pessoa)} pessoas\n")

eng = create_engine(os.environ["DATABASE_URL"].replace("+asyncpg", ""))
db = eng.connect()

# de-para por nome normalizado (a programação é do CNPJ Eletrônica; o cadastro é o mesmo)
cad = {_norm(n): (str(i), c) for i, n, c in db.execute(text(
    "SELECT e.id, e.nome, (SELECT a.condominio_id FROM employee_alocacoes a "
    "  WHERE a.employee_id = e.id AND a.condominio_id IS NOT NULL "
    "  ORDER BY a.ativo DESC, a.data_inicio DESC NULLS LAST LIMIT 1) FROM employees e")).all()}

# days_used que JÁ EXISTE, por (employee_id, início do aquisitivo) — preservar
usados = {(str(e), s): (u, sold) for e, s, u, sold in db.execute(text(
    "SELECT employee_id, start_date, days_used, days_sold FROM employee_vacation_periods")).all()}
usados_por_emp = defaultdict(int)
for (e, _s), (u, _sold) in usados.items():
    usados_por_emp[e] += u or 0

linhas, sem_cadastro, sem_cond = [], [], []
for nome, periodos in por_pessoa.items():
    m = cad.get(_norm(nome))
    if not m:
        sem_cadastro.append(nome)
        continue
    eid, cond = m
    if not cond:
        # mesma sentinela que o espelho/holerite usam quando não há alocação (coluna é NOT NULL).
        # Descartar a pessoa seria pior: ela ficaria sem período aquisitivo nenhum.
        sem_cond.append(nome)
        cond = SEM_COND
    restante = usados_por_emp.get(eid, 0)  # aloca o gozado nos períodos MAIS ANTIGOS primeiro
    for p in sorted(periodos, key=lambda x: _d(x["inicio_aq"])):
        # dias_dir vem fracionário nos períodos EM CURSO (avos: 9/12 de 30 = 22,5). A coluna é
        # inteira; trunco para BAIXO — no gozo o valor é recalculado, e arredondar para cima
        # concederia dia que ainda não foi adquirido.
        dir_ = int(float(str(p["dias_dir"]).replace(",", ".")))
        usa = min(restante, dir_)
        restante -= usa
        linhas.append({
            "id": str(uuid.uuid4()), "cond": str(cond), "emp": eid,
            "ini": _d(p["inicio_aq"]), "fim": _d(p["fim_aq"]),
            "dir": dir_, "used": usa, "rest": dir_ - usa,
            "limite": _d(p["limite"]),
            "faltas": 0 if p["faltas"] == "-" else int(p["faltas"]),
            "nome": nome,
        })

print(f"a carregar: {len(linhas)} períodos de {len({x['emp'] for x in linhas})} pessoas")
if sem_cadastro:
    print(f"SEM CADASTRO ({len(sem_cadastro)}): {', '.join(sem_cadastro[:6])}")
if sem_cond:
    print(f"SEM CONDOMÍNIO ({len(sem_cond)}): {', '.join(sem_cond[:6])}")

# Quem tem VERBA DE FÉRIAS na folha gozou de fato, mesmo sem registro — não é art. 137, é
# buraco de lançamento do DP. Misturar os dois faria o alerta nascer mentiroso.
com_evidencia = {str(e) for (e,) in db.execute(text(
    "SELECT DISTINCT employee_id FROM folha_verba_espelho "
    "WHERE upper(descricao) LIKE '%FERIAS%' OR upper(descricao) LIKE '%FÉRIAS%'")).all()}
venc = [x for x in linhas if x["rest"] > 0 and x["limite"] < datetime.now().date()]
risco = [x for x in venc if x["emp"] not in com_evidencia]
sem_reg = [x for x in venc if x["emp"] in com_evidencia]
# Contrato SUSPENSO não corre aquisitivo — não há art. 137 (caso ARYELTON: rescisão indireta
# em curso, suspensão orientada pelo jurídico). Sem esta marca o alerta soa falso todo mês.
_susp = {str(e) for (e,) in db.execute(text(
    "SELECT id FROM employees WHERE lower(coalesce(status,'')) IN ('suspenso','afastado_inss')")).all()}
print(f"\n🔴 RISCO REAL art. 137 (limite vencido, saldo, e SEM verba de férias na folha): {len(risco)}")
for x in sorted(risco, key=lambda z: z["limite"]):
    _m = "  [CONTRATO SUSPENSO — aquisitivo não corre, NÃO é art.137]" if x["emp"] in _susp else ""
    print(f"   {x['nome'][:30]:<32} aquis {x['ini']}–{x['fim']}  limite {x['limite']}  saldo {x['rest']}d{_m}")
print(f"\n🟡 GOZOU segundo a FOLHA mas sem registro — DP precisa lançar (não é art. 137): {len(sem_reg)}")
for x in sorted(sem_reg, key=lambda z: z["limite"]):
    print(f"   {x['nome'][:30]:<32} limite {x['limite']}")

if not PERSIST:
    print("\n(dry-run — nada escrito; use --persist)")
    sys.exit(0)

bkp = f"/tmp/evp_backup_{datetime.now():%Y%m%d_%H%M%S}.json"
with open(bkp, "w") as f:
    json.dump([{k: str(v) for k, v in dict(r).items()} for r in
               db.execute(text("SELECT * FROM employee_vacation_periods")).mappings()], f, indent=1)
print(f"\nbackup: {bkp}")

with eng.begin() as tx:
    apagados = tx.execute(text("DELETE FROM employee_vacation_periods")).rowcount
    for x in linhas:
        tx.execute(text(
            "INSERT INTO employee_vacation_periods (id, condominio_id, employee_id, start_date, end_date,"
            " total_days_entitled, days_used, days_sold, days_remaining, absences_count,"
            " is_expired, is_fully_used, double_payment, expires_at, created_at, updated_at) "
            "VALUES (CAST(:id AS uuid), CAST(:cond AS uuid), CAST(:emp AS uuid), :ini, :fim,"
            " :dir, :used, 0, :rest, :faltas, :exp, :full, false, :limite, now(), now())"),
            {**{k: v for k, v in x.items() if k != "nome"},
             "exp": x["limite"] < datetime.now().date() and x["rest"] > 0,
             "full": x["rest"] == 0})
print(f"apagados {apagados} sintéticos · gravados {len(linhas)} reais")
