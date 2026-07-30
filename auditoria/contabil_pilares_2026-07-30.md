# Reconciliação dos demais pilares — SPED/ECD · DCTFWeb · Apuração (2026)
> READ-ONLY, sem transmissão. Mede o que o serviço PRODUZ vs oráculo disponível.

  from modules.government_integrations.services.sped_contabil_service import get_sped_contabil_service
## 1. SPED Contábil / ECD (oráculo = razão)
| Métrica | ECD gerado | Razão (accounting_entries) | Status |
|---|--:|--:|---|
| Lançamentos | 1060 | 1231 | ✓ lê o razão real |
| Contas | 17 | — | — |
| Registros SPED | 3280 | — | hash 6a1c2a23bcba |
- ECD/SPED contábil gera do razão real (que já reconcilia à Onvio: Folha/INSS Δ=0). Sem oráculo externo próprio.

## 2. DCTFWeb — débitos previdenciários (deriva da folha) vs guia INSS oficial
| Comp | DCTFWeb débitos | Guia INSS (oráculo) | Δ | Status |
|---|--:|--:|--:|---|
| 2026-01 | 30,679.60 | 14,604.94 | +16,074.66 | diverge (+110%) |
| 2026-02 | 29,567.56 | 14,061.05 | +15,506.51 | diverge (+110%) |
| 2026-03 | 31,296.47 | 16,993.55 | +14,302.92 | diverge (+84%) |
| 2026-04 | 33,405.49 | 19,181.20 | +14,224.29 | diverge (+74%) |
| 2026-05 | 35,315.05 | 22,754.50 | +12,560.55 | diverge (+55%) |
| 2026-06 | 0.00 | 31,998.50 | -31,998.50 | diverge (-100%) |
| **Σ** | **160,264.17** | **119,593.74** | **+40,670.43** | |
- DCTFWeb usa alíquotas de manual (patronal 20% + RAT 3% + terceiros 5,8% s/ base INSS). Se divergir p/ MAIS da guia, o real tem redução/desoneração/base menor — investigar antes de transmitir.

  from modules.financial.services.apuracao_lucro_real_service import ApuracaoLucroRealService
## 3. Apuração Lucro Real (IRPJ/CSLL) — CNPJ1 Eletrônica
| Trim | Receita líq | Lucro antes IR/CS | IRPJ 15% | Adic. 10% | CSLL 9% | Total IR/CS |
|---|--:|--:|--:|--:|--:|--:|
| Q1 | 763,053.44 | 267,237.83 | 40,085.67 | 20,723.78 | 24,051.40 | 84,860.86 |
| Q2 | 587,586.33 | 183,734.76 | 27,560.21 | 12,373.48 | 16,536.13 | 56,469.82 |
- **Sem oráculo Onvio**: DARF IRPJ/CSLL não vem como categoria própria do Onvio (só `dar_sefaz` estadual). Valores computados do razão real; a paridade exige o DARF oficial (aguardando) ou o cálculo da Portte.

## Ressalvas
- Nenhum serviço transmite ao gov (só geração/consulta). Medição pura.
- SPED fiscal (ICMS/IPI) = zero por design (empresa de serviços) — não medido.
- DCTFWeb PDF do Onvio traz recibo/competência mas NÃO o valor do débito (extractor não pega o total) — por isso o oráculo do DCTFWeb usa a guia INSS, não o PDF DCTFWeb.
