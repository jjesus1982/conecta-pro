---
name: tributario-lucro-real
agent: TaxCalculatorAgent
prioridade: ALTA
versao: 2.0
---

# Skill 16 — Tributário Lucro Real — Conecta Mais
## CNPJ: 35.710.481/0001-03 | Manaus/AM | Regime: Lucro Real (desde jan/2026)

### IMPOSTOS DO LUCRO REAL (prestação de serviços)

**IRPJ — Imposto de Renda PJ**
- Alíquota: 15% sobre lucro real apurado
- Adicional: 10% sobre parcela do lucro que exceder R$20.000/mês (R$60k/trimestre)
- Apuração: trimestral (mar/jun/set/dez)
- DARF código: 0220
- Vencimento: último dia útil do mês seguinte ao trimestre

**CSLL — Contribuição Social sobre Lucro Líquido**
- Alíquota: 9% sobre lucro real (prestação de serviços)
- Apuração: trimestral (mesmo período IRPJ)
- DARF código: 6012

**PIS/COFINS — CUMULATIVO, não não-cumulativo** ⚠️ corrigido em 26/09/2026
- **PIS 0,65% · COFINS 3,00%** sobre a receita bruta — **SEM crédito sobre insumo.**
- Base legal: **Lei 10.833/2003, art. 10, inciso XXIV** — serviços de **vigilância e
  transporte de valores** permanecem no regime cumulativo **mesmo no Lucro Real**.
  «Lucro Real» NÃO implica «não-cumulativo»: são eixos independentes.
- Medido em 26/09/2026 no mix de receita de 2026 deste CNPJ:

  | código | serviço | R$ | regime |
  |---|---|---|---|
  | 110201 | Vigilância/monitoramento | 1.320.588,53 | **cumulativo** |
  | 071001/071002 | Limpeza e serviços gerais | 119.257,10 | **cumulativo** |
  | 140601 | Manutenção de CFTV | 114.160,00 | não-cumulativo |
  | 140101 | Lubrificação/revisão | 13.105,93 | não-cumulativo |

  **91,6% da receita é cumulativa por lei.** Toda estratégia de "recuperar crédito de
  PIS/COFINS sobre insumos" — e há literatura farta prometendo 3% a 7% — alcança, aqui,
  7,3% do faturamento. Sobre R$ 114.160/ano isso é ~R$ 10,5 mil de tributo, e o crédito
  seria uma fração disso. **Não vale a auditoria.**
- Na EFD Contribuições: CST 01, COD_CONT 51, registro 0110 com COD_INC_TRIB = 2.
  Isso está codificado em `backend/modules/government_integrations/core/sped_contribuicoes.py`
  e o CNPJ é declarado em `REGIME_PIS_COFINS` — o serviço RECUSA gerar para CNPJ sem
  regime declarado, em vez de assumir.
- Apuração: mensal, até o dia 25 do mês seguinte.

**ISS — Prefeitura de Manaus**
- Alíquota: 5% sobre receita de serviços
- Apuração: mensal
- Inscrição Municipal: 45177801
- Atenção: incentivo ISS pode ser solicitado para serviços de TI/portaria remota

**INSS Patronal (sobre folha)**
- Alíquota: 20% sobre salários (Lucro Real não tem desconto patronal reduzido)
- Adicional: 3% RAT (risco acidente trabalho — segurança)
- FAP: multiplicador a confirmar com contador

### CARGA TRIBUTÁRIA SOBRE MRR ESTIMADA
```
MRR bruto:         R$270.586,96
(-) ISS 5%:        -R$ 13.529,35
(-) PIS 1,65%:     -R$  4.464,68
(-) COFINS 7,6%:   -R$ 20.564,61
= Receita líquida: R$232.028,32 (14,25% de dedução)

IRPJ + CSLL (sobre lucro real — calcular após apuração trimestral)
  Lucro estimado: negativo no Q1/26 → IR/CSLL = R$0 no Q1
```

### ESTRATÉGIA DE OTIMIZAÇÃO TRIBUTÁRIA
1. **Migração CNPJ 2 (Simples Nacional)** — serviços humanizados saem do LR
   - Economia estimada: -8,5pp na carga tributária efetiva
2. **Créditos PIS/COFINS não-cumulativos** — aproveitar sobre serviços contábeis, vigilância terceirizada
3. **Liminares em curso** — PIS/COFINS zerados + INSS não retido (CNPJ 2 — solicitar)
4. **SUFRAMA 210140500** — incentivos para insumos e equipamentos

### OBRIGAÇÕES ACESSÓRIAS
| Obrigação | Periodicidade | Prazo | Responsável |
|---|---|---|---|
| DCTFWEB | Mensal | Dia 15 | Portte Contábil |
| SPED Contribuições | Mensal | Dia 10 | Portte Contábil |
| ECF | Anual | Julho | Portte Contábil |
| ECD | Anual | Maio | Portte Contábil |
| DIRF | Anual | Fevereiro | Portte Contábil |

**Contador:** Portte Contábil Assessoria e Consultoria Ltda
- CNPJ: 15.111.975/0001-75 | Valor: R$1.773,80/mês
- Sistema: Domínio Sistemas (TOTVS)

### ALERTAS AUTOMÁTICOS
- DARF vencendo em ≤ 5 dias → ALERTA CRÍTICO
- Lucro trimestral > R$60.000 → provisionar adicional IRPJ 10%
- Compliance LR atual: 100% ✅ (616/616 transações classificadas)
- Próxima apuração trimestral: 30/06/2026 (Q2/2026)

### CONSULTAS SQL
```sql
-- Impostos pagos no trimestre atual
SELECT justificativa_categoria, round(sum(ABS(amount))::numeric,2) as total_pago
FROM bank_transactions
WHERE justificativa_categoria = 'imposto'
AND date_trunc('quarter', transaction_date) = date_trunc('quarter', CURRENT_DATE)
GROUP BY 1;

-- Compliance Lucro Real atualizado
SELECT
    count(*) as total_debitos,
    count(CASE WHEN justificativa_categoria IS NOT NULL AND justificativa_categoria!='' THEN 1 END) as classificados,
    round(count(CASE WHEN justificativa_categoria IS NOT NULL THEN 1 END)::numeric / count(*) * 100, 1) as compliance_pct
FROM bank_transactions WHERE transaction_type = 'debit';
```
