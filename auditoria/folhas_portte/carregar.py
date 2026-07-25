#!/usr/bin/env python3
"""Carga idempotente de folha Portte em hr_payslips (espelha o formato do import June existente).
Uso (DENTRO do container backend): python3 carregar.py <load_json> <ref_year> <ref_month> [--commit]
Sem --commit = DRY-RUN (conta e mostra, não grava). Idempotente: DELETE source='portte'+competência antes.
NUNCA inventa: carrega exatamente o que está no load_json (já reconciliado por CPF/CNPJ).
"""
import json, sys, uuid
from datetime import date, datetime, timezone
from decimal import Decimal

sys.path.insert(0, "/app")
from core.database.session import SyncSessionLocal  # noqa: E402
from sqlalchemy import text  # noqa: E402

EMPRESA_CNPJ1 = "619a3df1-8bce-49ce-b77a-04f80a0e8491"
NS = uuid.UUID("11111111-2222-3333-4444-555555555555")  # namespace fixo p/ batch determinístico


def main():
    load_path, ry, rm = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    commit = "--commit" in sys.argv
    rows = json.load(open(load_path))
    batch_id = str(uuid.uuid5(NS, f"portte-{ry}-{rm:02d}"))
    period = f"{ry}-{rm:02d}"
    cstart = date(ry, rm, 1)
    cend = date(ry + (1 if rm == 12 else 0), 1 if rm == 12 else rm + 1, 1)  # 1º do mês seguinte
    from datetime import timedelta
    cend = cend - timedelta(days=1)
    pay = date(ry + (1 if rm == 12 else 0), 1 if rm == 12 else rm + 1, 6)  # dia 6 do mês seguinte
    now = datetime.now(timezone.utc)

    db = SyncSessionLocal()
    existing = db.execute(text("SELECT count(*) FROM hr_payslips WHERE source_system='portte' AND reference_year=:y AND reference_month=:m"),
                          {"y": ry, "m": rm}).scalar()
    print(f"[{period}] load_json={len(rows)} payslips · existentes portte nessa competência={existing} · batch={batch_id}")
    if not commit:
        soma = sum(Decimal(str(r["net_salary"])) for r in rows)
        print(f"DRY-RUN (sem --commit). Somatório líquido a carregar: R$ {soma}")
        print("  amostra:", rows[0]["employee_nome"], "->", rows[0]["condominio_nome"], "liq", rows[0]["net_salary"])
        return

    # idempotente: apaga o que já existe dessa competência+source antes de reinserir
    deleted = db.execute(text("DELETE FROM hr_payslips WHERE source_system='portte' AND reference_year=:y AND reference_month=:m"),
                         {"y": ry, "m": rm}).rowcount
    ins = 0
    for r in rows:
        db.execute(text("""
            INSERT INTO hr_payslips
              (id, condominio_id, employee_id, payslip_code, payslip_type, status,
               reference_year, reference_month, reference_period, payment_date, competence_start, competence_end,
               base_salary, total_earnings, total_deductions, net_salary,
               earnings, deductions, informative,
               inss_base, inss_value, irrf_base, irrf_value, fgts_base, fgts_value,
               source_system, external_id, import_batch_id, empresa_id, published_at, created_at, updated_at)
            VALUES
              (gen_random_uuid(), :cond, :emp, :code, 'monthly', 'published',
               :ry, :rm, :period, :pay, :cstart, :cend,
               :base, :earn_t, :ded_t, :net,
               CAST(:earn AS jsonb), CAST(:ded AS jsonb), CAST(:info AS jsonb),
               :inss_b, :inss_v, :irrf_b, :irrf_v, :fgts_b, :fgts_v,
               'portte', :ext, :batch, :emp_cnpj, :now, :now, :now)
        """), {
            "cond": r["condominio_id"], "emp": r["employee_id"],
            "code": f"PORTTE-{ry}-{rm:02d}-{r.get('matricula') or 'X'}",
            "ry": ry, "rm": rm, "period": period, "pay": pay, "cstart": cstart, "cend": cend,
            "base": r["base_salary"], "earn_t": r["total_earnings"], "ded_t": r["total_deductions"], "net": r["net_salary"],
            "earn": json.dumps(r["earnings"]), "ded": json.dumps(r["deductions"]),
            "info": json.dumps(r["informative"] if isinstance(r["informative"], (list, dict)) else []),
            "inss_b": r["inss_base"], "inss_v": r["inss_value"], "irrf_b": r["irrf_base"], "irrf_v": r["irrf_value"],
            "fgts_b": r["fgts_base"], "fgts_v": r["fgts_value"],
            "ext": r.get("matricula"), "batch": batch_id, "emp_cnpj": EMPRESA_CNPJ1, "now": now,
        })
        ins += 1
    db.commit()
    print(f"CARGA OK [{period}]: deletados {deleted}, inseridos {ins}. batch={batch_id}")


if __name__ == "__main__":
    main()
