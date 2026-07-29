"""C1 — tabela GERAL de verbas backfilladas do espelho Portte (mecanismo único).
Grava, por (emp,competência), as verbas cujo valor-verdade está no espelho e o motor
não deriva do dado que temos: grupo variável/reflexo (intrajornada, hora noturna
reduzida, adicional noturno, DSR) e FALTAS/AFASTAMENTO (sick-leave pago = provento;
ausência descontada = desconto). O motor lê e emite; incide_inss controla o base_inss
(proventos somam, descontos que incidem subtraem). Idempotente por fonte."""
import os
import re
from collections import defaultdict
from sqlalchemy import create_engine, text

eng = create_engine(os.environ["DATABASE_URL"].replace("+asyncpg", ""))
ANO = 2026
FONTE = "backfill_portte_espelho_2026-07-28"


def norm(d):
    return re.sub(r"\s+", " ", (d or "").strip().upper())


def f(x):
    try:
        return float(x)
    except Exception:  # noqa: BLE001
        return 0.0


def classifica(du):
    """Portte-desc → (codigo, descricao_saida, tipo, incide_inss) | None."""
    # --- grupo variável / reflexo (proventos, incidem INSS) ---
    if "INTRAJORNADA DIURNO" in du:
        return ("0030", "Intrajornada Diurno", "provento", True)
    if "INTRAJORNADA NOTURNA" in du:
        return ("0031", "Intrajornada Noturna", "provento", True)
    if "HORA NOT" in du and "REDUZ" in du:
        return ("0021", "Hora Noturna Reduzida", "provento", True)
    if "ADICIONAL NOTURNO" in du:  # prêmio 20% (Portte: "ADICIONAL NOTURNO (INFOR)")
        return ("0020", "Adicional Noturno", "provento", True)
    if ("DSR" in du or "REPOUSO" in du) and "FALTA" not in du:
        return ("0090", "DSR sobre Variaveis", "provento", True)
    # --- faltas / afastamento ---
    if "AFAST" in du and "DOENCA" in du:
        if "INSS" in du:  # INSS paga → não incide INSS do empregador
            return ("0051", "Afastamento INSS", "provento", False)
        return ("0050", "Afastamento Doenca (ate 15d)", "provento", True)  # empregador paga
    if "DESCONTO HORAS AFAST" in du:  # espelho do que o INSS reembolsa; não incide
        return ("1050", "Desconto Horas Afastadas", "desconto", False)
    if "FALTA" in du and "DSR" in du:
        return ("1053", "DSR sobre Faltas", "desconto", True)
    if "HORAS FALTAS" in du:
        return ("1052", "Faltas Parcial", "desconto", True)
    if "FALTA" in du:  # DIAS FALTAS
        return ("1051", "Faltas", "desconto", True)
    # --- férias (INSS via linha própria "INSS FERIAS" → verbas NÃO entram no base_inss) ---
    if "FERIAS" in du or "FÉRIAS" in du:
        if "INSS" in du:                       # INSS FERIAS / INSS DIFERENCA FERIAS
            return ("1060", "INSS Ferias", "desconto", False)
        if "ADIANTAMENTO" in du:               # adiantamento recuperado
            return ("1061", "Adiantamento Ferias", "desconto", False)
        if "PROVISAO" in du or "ESTORNO" in du:  # empréstimo-em-férias (provisão/estorno)
            return ("1062", "Provisao Emprestimo Ferias", "desconto", False)
        if "HORAS FERIAS" in du:
            return ("0060", "Horas Ferias", "provento", False)
        if du.startswith("1/3") or "1/3" in du:
            return ("0061", "1/3 Ferias", "provento", False)
        return ("0062", "Ferias (medias/proporcionais)", "provento", False)  # demais proventos de férias
    return None


# (eid, mes, codigo) -> [descricao, tipo, incide, valor_acumulado]
agg = defaultdict(lambda: [None, None, None, 0.0])
with eng.connect() as c:
    for m in range(1, 7):
        for eid, ear, ded in c.execute(text(
            "SELECT employee_id::text, earnings, deductions FROM hr_payslips "
            "WHERE reference_year=:a AND reference_month=:m AND source_system='portte'"),
            {"a": ANO, "m": m}).fetchall():
            for it in ((ear or []) + (ded or [])):
                du = norm(it.get("descricao") or it.get("description"))
                cl = classifica(du)
                if not cl:
                    continue
                v = f(it.get("valor") if it.get("valor") is not None else it.get("value"))
                if v <= 0:
                    continue
                k = (eid, m, cl[0])
                agg[k][0], agg[k][1], agg[k][2] = cl[1], cl[2], cl[3]
                agg[k][3] += v

por_cod = defaultdict(lambda: [0, 0.0, None])
for (eid, m, cod), (desc, tipo, inc, val) in agg.items():
    por_cod[desc][0] += 1
    por_cod[desc][1] += val
    por_cod[desc][2] = tipo
print("verbas a backfillar (descrição → n, Σ, tipo):")
for desc, (n, s, tipo) in sorted(por_cod.items(), key=lambda x: -x[1][1]):
    print(f"  {desc:<28} n={n:<4} Σ=R$ {s:>10,.2f}  [{tipo}]")

with eng.begin() as c:
    c.execute(text("""
        CREATE TABLE IF NOT EXISTS folha_verba_espelho (
            employee_id uuid NOT NULL, ano int NOT NULL, mes int NOT NULL,
            codigo text NOT NULL, descricao text, valor numeric DEFAULT 0,
            tipo text DEFAULT 'provento', incide_inss boolean DEFAULT true,
            fonte text, PRIMARY KEY (employee_id, ano, mes, codigo))"""))
    c.execute(text("DELETE FROM folha_verba_espelho WHERE ano=:a AND fonte=:f"), {"a": ANO, "f": FONTE})
    for (eid, m, cod), (desc, tipo, inc, val) in agg.items():
        c.execute(text("""
            INSERT INTO folha_verba_espelho (employee_id, ano, mes, codigo, descricao, valor, tipo, incide_inss, fonte)
            VALUES (CAST(:e AS uuid), :a, :m, :cod, :desc, :val, :tipo, :inc, :f)"""),
            {"e": eid, "a": ANO, "m": m, "cod": cod, "desc": desc, "val": round(val, 2),
             "tipo": tipo, "inc": inc, "f": FONTE})
    print(f"\ninseridas {len(agg)} linhas em folha_verba_espelho.")
    c.execute(text("DROP TABLE IF EXISTS folha_intrajornada_espelho"))
