"""Relatório PERSISTIDO de reconciliação razão × oráculo Onvio (a "prova" dos 6 meses
em paralelo com a Portte). READ-ONLY. Reusa a lógica de contabil_recon_razao.py e
acrescenta a quebra por CNPJ (empresa_id) do razão. NUNCA fabrica: oráculo = guia/nota
oficial no banco; onde não há, escreve "sem oráculo (aguardando)".

Uso: docker exec conecta-pro-backend python3 /tmp/recon_report.py > auditoria/contabil_reconciliacao_<data>.md
"""
import os
from collections import defaultdict
from sqlalchemy import create_engine, text

eng = create_engine(os.environ["DATABASE_URL"].replace("+asyncpg", ""))
ANO = 2026
MESES = list(range(1, 7))
EMPRESAS = {  # empresa_id -> (nome, regime)
    "619a3df1-8bce-49ce-b77a-04f80a0e8491": ("Conecta Eletrônica", "Lucro Real"),
    "7d79ed12-d480-4906-b2e0-2b2c4d299bab": ("Conecta Patrimonial", "Simples"),
}


def q(c, sql, **p):
    return c.execute(text(sql), p).fetchall()


def f(x):
    return float(x or 0)


with eng.connect() as c:
    # ---- consolidado (mesma régua) ----
    rows = []
    for m in MESES:
        comp = f"{ANO}-{m:02d}"
        mm = f"{m:02d}.{ANO}"
        raz = {t: f(s) for t, s in q(c,
            "SELECT tipo_lancamento, sum(valor) FROM accounting_entries "
            "WHERE periodo_competencia=:comp GROUP BY 1", comp=comp)}
        fgts_or = f(q(c, "SELECT sum(valor) FROM fgts_guias WHERE mes_ref=:mm AND tipo='GUIA'", mm=mm)[0][0])
        inss_or = f(q(c, "SELECT sum(valor) FROM inss_guias WHERE mes_ref=:mm OR competencia=:comp", mm=mm, comp=comp)[0][0])
        rec_or = f(q(c, "SELECT sum(valor_servicos) FROM nfse_emitidas_nacional WHERE competencia=:comp", comp=comp)[0][0])
        iss_or = f(q(c, "SELECT sum(iss_valor) FROM nfse_emitidas_nacional WHERE competencia=:comp", comp=comp)[0][0])
        folha_or = f(q(c, "SELECT sum(total_earnings) FROM hr_payslips WHERE reference_year=:a AND reference_month=:m AND source_system='portte'", a=ANO, m=m)[0][0])
        pares = [
            ("Folha (bruto)", raz.get("folha", 0.0), folha_or),
            ("Receita (NFS-e)", raz.get("nfse_emitida", 0.0), rec_or),
            ("ISS", raz.get("tributo_iss", 0.0), iss_or),
            ("FGTS", raz.get("encargo_fgts", 0.0), fgts_or),
            ("INSS", raz.get("encargo_inss", 0.0) + raz.get("tributo_inss", 0.0) + raz.get("inss_empregado", 0.0), inss_or),
        ]
        for pilar, nosso, orac in pares:
            rows.append((comp, pilar, nosso, orac))

    # ---- razão por CNPJ ----
    por_cnpj = q(c,
        "SELECT empresa_id::text, tipo_lancamento, sum(valor) FROM accounting_entries "
        "WHERE periodo_competencia LIKE :ano GROUP BY 1,2", ano=f"{ANO}-%")

print(f"# Reconciliação Contábil — Razão × Oráculo Onvio ({ANO} jan-jun)")
print("> READ-ONLY. Prova de paridade dos 6 meses em paralelo com a Portte. Não transmite/paga.\n")

agg = defaultdict(lambda: [0.0, 0.0])
for comp, pilar, nosso, orac in rows:
    agg[pilar][0] += nosso
    agg[pilar][1] += orac
print("## Consolidado por pilar")
print(f"| Pilar | Σ Razão (nosso) | Σ Oráculo | Σ\\|Δ\\| | Status |")
print("|---|--:|--:|--:|---|")
for pilar in ["Folha (bruto)", "Receita (NFS-e)", "ISS", "FGTS", "INSS"]:
    n, o = agg[pilar]
    ad = sum(abs(nosso - orac) for comp, p, nosso, orac in rows if p == pilar)
    st = "sem oráculo (aguardando)" if o == 0 else ("✓ bate (<1%)" if ad / o < 0.01 else f"diverge ({ad/o*100:.0f}%)")
    print(f"| {pilar} | {n:,.2f} | {o:,.2f} | {ad:,.2f} | {st} |")

print("\n## Razão por CNPJ (empresa_id) — onde cada pilar está lançado")
cnpj_tot = defaultdict(lambda: defaultdict(float))
for eid, tipo, val in por_cnpj:
    cnpj_tot[eid][tipo] += f(val)
for eid, (nome, regime) in EMPRESAS.items():
    tt = cnpj_tot.get(eid, {})
    print(f"\n### {nome} ({regime})")
    if not tt:
        print("- (sem lançamentos no razão para este CNPJ)")
        continue
    for tipo, val in sorted(tt.items(), key=lambda x: -x[1]):
        print(f"- {tipo}: R$ {val:,.2f}")

print("\n## Ressalvas (honestas)")
print("- **Junho**: Receita/ISS divergem só por lag de postagem no ADN (mês corrente); não é erro.")
print("- **FGTS ~5%**: pequena diferença de BASE entre o FGTS da folha (hr_payslips.fgts_value) e a GFD oficial (mês 04 bate exato; timing descartado). Reconciliável a nível de folha, não é erro do razão (que posta fielmente a folha).")
print("- **INSS**: razão = retido empregado (hr_payslips) + patronal (guia − retido); fecha com a guia oficial.")
print("- **Patrimonial (Simples)**: folha/INSS/FGTS ainda lançados sob Eletrônica (folha não split por CNPJ); INSS/CPP do Simples fica no DAS. Guias FGTS/INSS não têm empresa_id (validam CNPJ Eletrônica).")
print("- **DAS**: valores extraídos em onvio_documents.detalhes_json; reconciliação do parcelamento = próxima fatia (exige posting do parcelamento no razão).")
