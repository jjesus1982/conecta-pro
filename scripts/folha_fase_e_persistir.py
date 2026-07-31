"""Fase E — persiste a folha do MOTOR em paralelo à Portte (`source_system='conecta'`).

NUNCA toca as linhas 'portte' (são a verdade). Idempotente: apaga só as 'conecta' da
competência antes de reinserir. `payslip_code` próprio ('CONECTA-...') não colide com a
UNIQUE (condominio_id, payslip_code) da linha Portte.

Uso:
  python3 folha_fase_e_persistir.py              # dry-run (default, NADA escrito)
  python3 folha_fase_e_persistir.py --persist    # grava
  python3 folha_fase_e_persistir.py --mes 6      # só uma competência
"""

import json
import os
import sys
import uuid

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from modules.people_management.folha.services.calculo_service import calcular_folha_colaborador

ANO = 2026
PERSIST = "--persist" in sys.argv
MESES = [int(sys.argv[sys.argv.index("--mes") + 1])] if "--mes" in sys.argv else list(range(1, 7))

eng = create_engine(os.environ["DATABASE_URL"].replace("+asyncpg", ""))
db = sessionmaker(bind=eng)()

INSERT_SQL = text("""
    INSERT INTO hr_payslips (
        id, condominio_id, employee_id, payslip_code, payslip_type, status,
        reference_year, reference_month, reference_period,
        base_salary, total_earnings, total_deductions, net_salary,
        earnings, deductions, informative,
        inss_base, irrf_base, fgts_base, fgts_value,
        view_count, download_count, source_system, empresa_id, created_at, updated_at)
    VALUES (
        :id, :cond, :emp, :code, 'mensal', 'draft',
        :ano, :mes, :comp,
        :base, :tp, :td, :liq,
        CAST(:ear AS jsonb), CAST(:ded AS jsonb), '[]'::jsonb,
        :binss, :birrf, :bfgts, :fgts,
        0, 0, 'conecta', :empresa, now(), now())
""")

print(f"Fase E — {'PERSISTINDO' if PERSIST else 'DRY-RUN (nada será escrito)'} | meses: {MESES}\n")
tot_ok = tot_err = tot_liq = 0
for mes in MESES:
    comp = f"{ANO}-{mes:02d}"
    # Mesmo universo da Portte, para comparar 1:1 (e herdar condominio_id/empresa_id reais).
    # total_earnings > 0: guard contra holerite Portte sem nenhum provento (não trabalhou).
    # Hoje não filtra ninguém (medido) — o líquido zero de alguns desligados vem da rescisão
    # lançada como DESCONTO ("LIQUIDO RESCISAO"), não de ausência de proventos.
    alvos = db.execute(text(
        "SELECT employee_id::text, condominio_id::text, empresa_id::text FROM hr_payslips "
        "WHERE reference_period = :c AND source_system = 'portte' "
        "AND COALESCE(total_earnings, 0) > 0 ORDER BY employee_id"
    ), {"c": comp}).fetchall()

    if PERSIST:  # idempotência — só mexe no que é 'conecta'
        apagadas = db.execute(text(
            "DELETE FROM hr_payslips WHERE reference_period = :c AND source_system = 'conecta'"
        ), {"c": comp}).rowcount
        if apagadas:
            print(f"  {comp}: {apagadas} linhas 'conecta' anteriores removidas (re-run)")

    ok = err = 0
    liq_mes = 0.0
    for seq, (eid, cond_id, empresa_id) in enumerate(alvos, start=1):
        try:
            # historico=True: o holerite Portte desta competência JÁ prova o vínculo.
            r = calcular_folha_colaborador(db, eid, mes, ANO, historico=True)
        except Exception as exc:  # noqa: BLE001 — um colaborador não derruba a competência
            print(f"    ERRO {eid[:8]}: {str(exc)[:100]}")
            err += 1
            continue
        if not r or r.get("error"):
            err += 1
            continue
        ok += 1
        liq_mes += float(r["liquido"])
        if not PERSIST:
            continue
        db.execute(INSERT_SQL, {
            "id": str(uuid.uuid4()), "cond": cond_id, "emp": eid,
            "code": f"CONECTA-{ANO}-{mes:02d}-{seq}",
            "ano": ANO, "mes": mes, "comp": comp,
            "base": r["salario_base"], "tp": r["total_proventos"],
            "td": r["total_descontos"], "liq": r["liquido"],
            "ear": json.dumps(r["proventos"], ensure_ascii=False),
            "ded": json.dumps(r["descontos"], ensure_ascii=False),
            "binss": r["base_inss"], "birrf": r["base_irrf"],
            "bfgts": r["base_fgts"], "fgts": r["fgts_empresa"],
            "empresa": empresa_id,
        })
    if PERSIST:
        db.commit()
    tot_ok += ok
    tot_err += err
    tot_liq += liq_mes
    print(f"  {comp}: {ok:3} calculados, {err} erros, líquido R$ {liq_mes:12,.2f}")

print(f"\nTotal: {tot_ok} linhas, {tot_err} erros, líquido R$ {tot_liq:,.2f}"
      f"{' — PERSISTIDAS' if PERSIST else ' (dry-run, nada escrito)'}")
db.close()
