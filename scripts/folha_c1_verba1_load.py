"""C1 verba 1 (empréstimo/consignado) — carga jan-jun por CONTRATO-SEGMENTO.
Fonte = espelho Portte (hr_payslips source='portte'), verba "DESC. EMP. CRED. TRAB Nº".
Modelo: 1 linha employee_deductions por (employee, contrato, run-de-meses-consecutivos-mesmo-valor).
data_inicio/data_fim cobrem o run → o filtro-de-data do motor aplica a verba só nos meses certos
(trata gaps: contrato que pula um mês vira 2 runs; parcela final menor vira run próprio).
BACKUP antes de qualquer DELETE. Idempotente: apaga 'consignado' e recarrega do zero."""
import os
import re
import json
from collections import defaultdict
from datetime import date
from sqlalchemy import create_engine, text

URL = os.environ["DATABASE_URL"].replace("+asyncpg", "")
eng = create_engine(URL)
ANO = 2026
MESES = [1, 2, 3, 4, 5, 6]


def norm(d):
    return re.sub(r"\s+", " ", (d or "").strip().upper())


def is_loan(du):
    return ("EMP" in du and "CRED" in du and "TRAB" in du) and not any(
        x in du for x in ["PROVISAO", "PROVISÃO", "FERIAS", "FÉRIAS", "FE N", "ESTORNO"]
    )


def eom(mes):
    return date(ANO + (1 if mes == 12 else 0), (1 if mes == 12 else mes + 1), 1)


# (employee_uuid, descricao_norm) -> {mes: valor}   (guarda descricao original p/ gravar)
loans = defaultdict(dict)
orig_desc = {}
with eng.connect() as c:
    for m in MESES:
        rows = c.execute(text(
            "SELECT employee_id::text, deductions FROM hr_payslips "
            "WHERE reference_year=:a AND reference_month=:m AND source_system='portte'"),
            {"a": ANO, "m": m}).fetchall()
        for eid, ded in rows:
            for it in (ded or []):
                d = (it.get("descricao") or it.get("description") or "").strip()
                du = norm(d)
                v = float((it.get("valor") if it.get("valor") is not None else it.get("value")) or 0)
                if is_loan(du) and v > 0:
                    k = (eid, du)
                    # acumula linhas do MESMO contrato no mesmo mês (Portte às vezes
                    # repete o Nº como placeholder "#CONTRATO" → várias linhas colapsam
                    # na mesma chave; a verba do motor é o TOTAL mensal por contrato).
                    loans[k][m] = round(loans[k].get(m, 0.0) + v, 2)
                    orig_desc.setdefault(k, d[:120])

# ---- segmentação: runs de meses CONSECUTIVOS com MESMO valor ----
segments = []  # (employee_uuid, descricao, valor, data_inicio, data_fim, n_meses)
for (eid, du), mv in loans.items():
    ms = sorted(mv)
    run_start = ms[0]
    prev = ms[0]
    for m in ms[1:] + [None]:
        contiguous = (m is not None and m == prev + 1 and mv[m] == mv[run_start])
        if not contiguous:
            segments.append((eid, orig_desc[(eid, du)], mv[run_start],
                             date(ANO, run_start, 1), eom(prev) - __import__("datetime").timedelta(days=1),
                             prev - run_start + 1))
            if m is not None:
                run_start = m
        prev = m if m is not None else prev

print(f"contratos distintos: {len(loans)} · segmentos gerados: {len(segments)}")
# distribuição por nº de meses do segmento
dist = defaultdict(int)
for s in segments:
    dist[s[5]] += 1
print(f"segmentos por duração (meses): {dict(sorted(dist.items()))}")
tot_por_mes = defaultdict(float)
for eid, d, v, di, df, n in segments:
    for m in MESES:
        if di <= eom(m) - __import__("datetime").timedelta(days=1) and df >= date(ANO, m, 1):
            tot_por_mes[m] += v
print("Σ empréstimo por mês que o modelo vai gerar:")
for m in MESES:
    print(f"  2026-{m:02d}: R$ {tot_por_mes[m]:>12,.2f}")

# ---- BACKUP + gravação ----
with eng.begin() as c:
    cur = c.execute(text(
        "SELECT id::text, employee_id::text, tipo, descricao, valor::text, data_inicio::text, "
        "data_fim::text, ativo FROM employee_deductions WHERE tipo='consignado'")).fetchall()
    bkp = [dict(zip(["id", "employee_id", "tipo", "descricao", "valor", "data_inicio", "data_fim", "ativo"], r)) for r in cur]
    open("/tmp/employee_deductions_consignado_backup.json", "w").write(json.dumps(bkp, ensure_ascii=False, indent=2))
    print(f"\nbackup {len(bkp)} linhas 'consignado' → /tmp/employee_deductions_consignado_backup.json")
    c.execute(text("DELETE FROM employee_deductions WHERE tipo='consignado'"))
    ins = text(
        "INSERT INTO employee_deductions (id, employee_id, tipo, descricao, valor, base_calculo, "
        "parcela_atual, total_parcelas, data_inicio, data_fim, ativo, observacao, created_at, updated_at) "
        "VALUES (gen_random_uuid(), CAST(:eid AS uuid), 'consignado', :desc, :valor, 'fixo', "
        "1, :n, :di, :df, true, 'C1 verba1 carga jan-jun por contrato-segmento (fonte espelho Portte)', now(), now())")
    for eid, d, v, di, df, n in segments:
        c.execute(ins, {"eid": eid, "desc": d, "valor": v, "n": n, "di": di, "df": df})
    print(f"inseridos {len(segments)} segmentos.")
