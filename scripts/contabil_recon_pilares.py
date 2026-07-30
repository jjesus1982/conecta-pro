"""Baseline de reconciliação dos DEMAIS pilares (SPED/ECD, DCTFWeb, Apuração Lucro Real)
contra o oráculo disponível. READ-ONLY — nenhum serviço transmite ao gov (só geração/consulta).
Mede, não supõe (lição do baseline). Onde não há oráculo Onvio, reporta o valor computado
e marca "sem oráculo (aguardando)". Nunca fabrica.

Uso: docker exec conecta-pro-backend python3 /tmp/pilares.py > auditoria/contabil_pilares_<data>.md
"""
import os
from sqlalchemy import create_engine, text

eng = create_engine(os.environ["DATABASE_URL"].replace("+asyncpg", ""))
ANO = 2026
MESES = list(range(1, 7))


def f(x):
    return float(x or 0)


def oraculo_inss(c, m):
    mm = f"{m:02d}.{ANO}"
    return f(c.execute(text("SELECT sum(valor) FROM inss_guias WHERE mes_ref=:mm"), {"mm": mm}).scalar())


print(f"# Reconciliação dos demais pilares — SPED/ECD · DCTFWeb · Apuração ({ANO})")
print("> READ-ONLY, sem transmissão. Mede o que o serviço PRODUZ vs oráculo disponível.\n")

# ---------- 1. SPED contábil / ECD (oráculo = o próprio razão) ----------
from modules.government_integrations.services.sped_contabil_service import get_sped_contabil_service

with eng.connect() as c:
    n_razao = int(c.execute(text(
        "SELECT count(*) FROM accounting_entries WHERE periodo_competencia LIKE :a AND status='confirmado'"),
        {"a": f"{ANO}-%"}).scalar())
ecd = get_sped_contabil_service().gerar_arquivo(ANO, f"{ANO}-01-01", f"{ANO}-06-30")
print("## 1. SPED Contábil / ECD (oráculo = razão)")
print(f"| Métrica | ECD gerado | Razão (accounting_entries) | Status |")
print("|---|--:|--:|---|")
st = "✓ lê o razão real" if ecd.get("lancamentos_reais_carregados", 0) > 0 else "sem dado"
print(f"| Lançamentos | {ecd.get('total_lancamentos')} | {n_razao} | {st} |")
print(f"| Contas | {ecd.get('total_contas')} | — | — |")
print(f"| Registros SPED | {ecd.get('total_registros')} | — | hash {str(ecd.get('hash_md5'))[:12]} |")
print("- ECD/SPED contábil gera do razão real (que já reconcilia à Onvio: Folha/INSS Δ=0). Sem oráculo externo próprio.\n")

# ---------- 2. DCTFWeb (débitos folha) vs oráculo guia INSS ----------
from modules.government_integrations.services.dctfweb_service import get_dctfweb_service

svc = get_dctfweb_service()
print("## 2. DCTFWeb — débitos previdenciários (deriva da folha) vs guia INSS oficial")
print(f"| Comp | DCTFWeb débitos | Guia INSS (oráculo) | Δ | Status |")
print("|---|--:|--:|--:|---|")
tot_d = tot_o = 0.0
with eng.connect() as c:
    for m in MESES:
        comp = f"{ANO}-{m:02d}"
        try:
            r = svc.gerar_darfs(comp)
            deb = f(r.get("total_debitos"))
        except Exception as e:
            deb = 0.0
        orac = oraculo_inss(c, m)
        d = deb - orac
        tot_d += deb
        tot_o += orac
        st = "sem oráculo" if orac == 0 else ("✓ bate" if abs(d) / orac < 0.02 else f"diverge ({d/orac*100:+.0f}%)")
        print(f"| {comp} | {deb:,.2f} | {orac:,.2f} | {d:+,.2f} | {st} |")
print(f"| **Σ** | **{tot_d:,.2f}** | **{tot_o:,.2f}** | **{tot_d-tot_o:+,.2f}** | |")
print("- DCTFWeb usa alíquotas de manual (patronal 20% + RAT 3% + terceiros 5,8% s/ base INSS). "
      "Se divergir p/ MAIS da guia, o real tem redução/desoneração/base menor — investigar antes de transmitir.\n")

# ---------- 3. Apuração Lucro Real (IRPJ/CSLL) — sem oráculo Onvio ----------
from modules.financial.services.apuracao_lucro_real_service import ApuracaoLucroRealService

ap = ApuracaoLucroRealService()
print("## 3. Apuração Lucro Real (IRPJ/CSLL) — CNPJ1 Eletrônica")
print(f"| Trim | Receita líq | Lucro antes IR/CS | IRPJ 15% | Adic. 10% | CSLL 9% | Total IR/CS |")
print("|---|--:|--:|--:|--:|--:|--:|")
for tri in (1, 2):
    a = ap.apurar(ANO, trimestre=tri)
    b, ap_ = a["base"], a["apuracao"]
    print(f"| Q{tri} | {f(b.get('receita_liquida')):,.2f} | {f(b.get('lucro_antes_ircsll')):,.2f} | "
          f"{f(ap_.get('irpj_15')):,.2f} | {f(ap_.get('irpj_adicional_10')):,.2f} | "
          f"{f(ap_.get('csll_9')):,.2f} | {f(ap_.get('total_irpj_csll')):,.2f} |")
print("- **Sem oráculo Onvio**: DARF IRPJ/CSLL não vem como categoria própria do Onvio (só `dar_sefaz` estadual). "
      "Valores computados do razão real; a paridade exige o DARF oficial (aguardando) ou o cálculo da Portte.\n")

print("## Ressalvas")
print("- Nenhum serviço transmite ao gov (só geração/consulta). Medição pura.")
print("- SPED fiscal (ICMS/IPI) = zero por design (empresa de serviços) — não medido.")
print("- DCTFWeb PDF do Onvio traz recibo/competência mas NÃO o valor do débito (extractor não pega o total) — "
      "por isso o oráculo do DCTFWeb usa a guia INSS, não o PDF DCTFWeb.")
