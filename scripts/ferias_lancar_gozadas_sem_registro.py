"""Lança em employee_vacation_periods as férias que a FOLHA prova, mas que não têm solicitação.

Problema: 4 pessoas gozaram férias segundo a folha da Portte e não têm registro em
hr_vacation_requests, então `days_used` ficava 0 e o saldo exibido (e o que a RESCISÃO consome)
ficava inflado — CASTRO GAMA aparecia com 82 dias.

Oráculo (evidência dura, nada estimado):
  dias gozados = Σ dias AUSENTES (30 − dias_trabalhados de `folha_dias_espelho`)
                 nos meses em que a pessoa TEM verba de férias em `folha_verba_espelho`

A restrição "só mês com verba de férias" é o que separa férias de afastamento: a ELEN tem 11
dias ausentes em maio que são doença, não férias — e o mês de maio não tem verba de férias dela.

NÃO converte hora→dia. A rubrica da Portte é "Horas Férias" e dividir pelo valor-dia deu 39,6
dias para o ANTONIO DINIZ (acima do máximo legal): exigiria presumir jornada = fabricar.

Uso:
  python3 ferias_lancar_gozadas_sem_registro.py            # dry-run
  python3 ferias_lancar_gozadas_sem_registro.py --persist  # grava (backup antes)
"""

import json
import os
import sys
from datetime import datetime

from sqlalchemy import create_engine, text

PERSIST = "--persist" in sys.argv
eng = create_engine(os.environ["DATABASE_URL"].replace("+asyncpg", ""))
db = eng.connect()

# quem tem verba de férias na folha e days_used ZERO nos períodos — o buraco de registro
candidatos = db.execute(text("""
    SELECT DISTINCT CAST(v.employee_id AS TEXT), e.nome, e.status
    FROM folha_verba_espelho v JOIN employees e ON e.id = v.employee_id
    -- SÓ 0060 (Horas Férias = pagamento do dia GOZADO) e 1061 (Adiantamento, que só existe
    -- para quem de fato sai de férias). 0061/0062 aparecem em 26-27 pessoas porque incluem
    -- FÉRIAS PROPORCIONAIS DE RESCISÃO — indenização, não gozo. Usar elas marcaria como
    -- "gozou" gente que foi demitida (LORINALDO, TATIANA…).
    WHERE v.codigo IN ('0060', '1061')
      AND EXISTS (SELECT 1 FROM employee_vacation_periods p
                  WHERE p.employee_id = v.employee_id AND p.days_used = 0 AND p.days_remaining > 0)
      AND NOT EXISTS (SELECT 1 FROM employee_vacation_periods p
                      WHERE p.employee_id = v.employee_id AND p.days_used > 0)
    ORDER BY 2""")).all()

plano = []
for eid, nome, status in candidatos:
    meses_fer = {m for (m,) in db.execute(text(
        "SELECT DISTINCT mes FROM folha_verba_espelho WHERE CAST(employee_id AS TEXT)=:e "
        "AND ano=2026 AND codigo IN ('0060', '1061')"),
        {"e": eid}).all()}
    if not meses_fer:
        continue
    dias = 0.0
    detalhe = []
    for mes, trab in db.execute(text(
        "SELECT mes, dias_trabalhados FROM folha_dias_espelho "
        "WHERE CAST(employee_id AS TEXT)=:e AND ano=2026 ORDER BY mes"), {"e": eid}).all():
        if mes not in meses_fer:
            continue  # mês sem verba de férias: a ausência ali é afastamento/falta, não férias
        aus = 30.0 - float(trab)
        if aus <= 0:
            continue
        dias += aus
        detalhe.append(f"m{mes:02d}:{aus:.0f}d")
    if dias <= 0:
        continue
    # consome o período aquisitivo ABERTO mais ANTIGO (ordem legal de gozo)
    periodos = db.execute(text(
        "SELECT CAST(id AS TEXT), start_date, end_date, total_days_entitled, days_used "
        "FROM employee_vacation_periods WHERE CAST(employee_id AS TEXT)=:e AND days_remaining > 0 "
        "ORDER BY start_date"), {"e": eid}).all()
    restante = round(dias)
    for pid, ini, fim, dir_, used in periodos:
        if restante <= 0:
            break
        usa = min(restante, dir_ - used)
        if usa <= 0:
            continue
        plano.append({"pid": pid, "nome": nome, "status": status, "ini": ini, "fim": fim,
                      "dir": dir_, "usa": usa, "detalhe": ", ".join(detalhe), "total": round(dias)})
        restante -= usa
    if restante > 0:
        plano.append({"pid": None, "nome": nome, "status": status, "ini": None, "fim": None,
                      "dir": 0, "usa": restante, "detalhe": ", ".join(detalhe), "total": round(dias)})

print(f"{len(candidatos)} pessoas com férias na folha e nenhum período com days_used\n")
print(f"{'pessoa':<32}{'status':<14}{'período aquisitivo':<26}{'dir':>4}{'lançar':>8}   evidência")
for x in plano:
    per = f"{x['ini']}–{x['fim']}" if x["pid"] else "*** SEM PERÍODO ABERTO ***"
    print(f"{x['nome'][:31]:<32}{x['status']:<14}{per:<26}{x['dir']:>4}{x['usa']:>8}   {x['detalhe']}")

orfaos = [x for x in plano if not x["pid"]]
if orfaos:
    print(f"\n⚠️ {len(orfaos)} lançamento(s) sem período aquisitivo aberto — NÃO serão gravados:")
    for x in orfaos:
        print(f"   {x['nome']}: sobram {x['usa']}d de {x['total']}d")

if not PERSIST:
    print("\n(dry-run — nada escrito; use --persist)")
    sys.exit(0)

bkp = f"/tmp/evp_pre_lancamento_{datetime.now():%Y%m%d_%H%M%S}.json"
with open(bkp, "w") as f:
    json.dump([{k: str(v) for k, v in dict(r).items()} for r in
               db.execute(text("SELECT * FROM employee_vacation_periods")).mappings()], f, indent=1)
print(f"\nbackup: {bkp}")

with eng.begin() as tx:
    n = 0
    for x in plano:
        if not x["pid"]:
            continue
        tx.execute(text(
            "UPDATE employee_vacation_periods SET days_used = days_used + :u, "
            "days_remaining = total_days_entitled - (days_used + :u), "
            "is_fully_used = (total_days_entitled - (days_used + :u)) = 0, "
            "is_expired = CASE WHEN (total_days_entitled - (days_used + :u)) = 0 THEN false ELSE is_expired END, "
            "updated_at = now() WHERE CAST(id AS TEXT) = :p"), {"u": x["usa"], "p": x["pid"]})
        n += 1
print(f"{n} período(s) atualizado(s)")
