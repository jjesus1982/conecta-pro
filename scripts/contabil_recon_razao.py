"""C-contábil — baseline de reconciliação do RAZÃO vs oráculo Onvio/espelho. READ-ONLY.
Compara accounting_entries (nossa contabilidade real) aos valores oficiais que o Onvio
trouxe do contador (fgts_guias, inss_guias, nfse_emitidas_nacional/iss) e ao espelho da
folha (hr_payslips). Saída: Σ|Δ| por pilar/competência. Mede o que JÁ bate — não presume."""
import os
from collections import defaultdict
from sqlalchemy import create_engine, text

eng = create_engine(os.environ["DATABASE_URL"].replace("+asyncpg", ""))
ANO = 2026
MESES = list(range(1, 7))


def q(c, sql, **p):
    return c.execute(text(sql), p).fetchall()


def f(x):
    return float(x or 0)


rows = []
with eng.connect() as c:
    for m in MESES:
        comp = f"{ANO}-{m:02d}"
        # --- razão (nossa) por tipo ---
        raz = {t: f(s) for t, s in q(c,
            "SELECT tipo_lancamento, sum(valor) FROM accounting_entries "
            "WHERE periodo_competencia=:comp GROUP BY 1", comp=comp)}
        # --- oráculos ---
        fgts_or = f(q(c, "SELECT sum(valor) FROM fgts_guias WHERE mes_ref=:comp", comp=comp)[0][0])
        inss_or = f(q(c, "SELECT sum(valor) FROM inss_guias WHERE mes_ref=:comp OR competencia=:comp", comp=comp)[0][0])
        rec_or = f(q(c, "SELECT sum(valor_servicos) FROM nfse_emitidas_nacional WHERE competencia=:comp", comp=comp)[0][0])
        iss_or = f(q(c, "SELECT sum(iss_valor) FROM nfse_emitidas_nacional WHERE competencia=:comp", comp=comp)[0][0])
        folha_or = f(q(c, "SELECT sum(total_earnings) FROM hr_payslips WHERE reference_year=:a AND reference_month=:m AND source_system='portte'", a=ANO, m=m)[0][0])
        # --- pares (pilar, nosso, oráculo) ---
        pares = [
            ("FGTS", raz.get("encargo_fgts", 0.0), fgts_or),
            ("ISS", raz.get("tributo_iss", 0.0), iss_or),
            ("Receita (NFS-e)", raz.get("nfse_emitida", 0.0), rec_or),
            ("Folha (bruto)", raz.get("folha", 0.0), folha_or),
            ("INSS", raz.get("encargo_inss", 0.0) + raz.get("tributo_inss", 0.0), inss_or),
        ]
        for pilar, nosso, orac in pares:
            rows.append((comp, pilar, nosso, orac, round(nosso - orac, 2)))

# saída
print("# Baseline reconciliação RAZÃO vs oráculo Onvio (2026 jan-jun) — READ-ONLY\n")
por_pilar = defaultdict(lambda: [0.0, 0.0, 0.0])
for comp, pilar, nosso, orac, d in rows:
    por_pilar[pilar][0] += nosso
    por_pilar[pilar][1] += orac
    por_pilar[pilar][2] += abs(d)
print(f"{'pilar':<18}{'Σ nosso':>16}{'Σ oráculo':>16}{'Σ|Δ|':>14}{'  status'}")
for pilar in ["Folha (bruto)", "Receita (NFS-e)", "ISS", "FGTS", "INSS"]:
    n, o, ad = por_pilar[pilar]
    st = "sem oráculo" if o == 0 else ("✓ bate (<1%)" if o and ad / o < 0.01 else "diverge")
    print(f"{pilar:<18}{n:>16,.2f}{o:>16,.2f}{ad:>14,.2f}  {st}")
print("\n## por competência (Δ = nosso − oráculo)")
print(f"{'comp':<9}{'pilar':<18}{'nosso':>14}{'oráculo':>14}{'Δ':>13}")
for comp, pilar, nosso, orac, d in rows:
    if abs(d) > 1:
        print(f"{comp:<9}{pilar:<18}{nosso:>14,.2f}{orac:>14,.2f}{d:>+13,.2f}")
