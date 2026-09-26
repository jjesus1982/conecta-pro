---
modulo: financial
versao: 2.0
atualizado: 2026-04-14
---

# Skills Financeiras Conecta PRO — Grupo A
**Empresa:** Conecta Mais — Seguranca e Tecnologia | CNPJ 35.710.481/0001-03
**Dados base:** MRR R$270.586,96 | Saldo Inter R$88.684,29 | 10 contratos ativos
**Referencia:** 13 NFS-e marco/2026 | CCT SINDECOMPRESTS 2026 | Lucro Real

## Grupo A — Core Financeiro (8 skills)

| # | Arquivo | Agente | Prioridade | Foco |
|---|---------|--------|------------|------|
| 01 | 01-projecao-fluxo-caixa-12-meses.md | CashflowPredictorAgent | CRITICA | Projecao 12 meses sazonalizada |
| 02 | 02-break-even-ponto-equilibrio.md | PricingOptimizerAgent | ALTA | Break-even por tipo de servico |
| 03 | 03-analise-margem-por-servico.md | CostingAnalyzerAgent | ALTA | Margem ABC por contrato |
| 04 | 04-framework-precificacao-margem.md | PricingOptimizerAgent | ALTA | Pricing CCT 2026 |
| 05 | 05-dre-gerencial.md | FinancialAdvisorAgent | CRITICA | DRE competencia vs caixa |
| 06 | 06-analise-fluxo-caixa-real.md | CashflowPredictorAgent | CRITICA | Extrato Inter 2.875 transacoes |
| 07 | 07-kpis-financeiros.md | RiskMonitorAgent | CRITICA | 14 KPIs + Health Score |
| 08 | 08-gestao-inadimplencia.md | CollectionNegotiatorAgent | CRITICA | Regua cobranca 10 condominios |

## Status do Negocio (base para todas as skills)

| Indicador | Valor | Status |
|-----------|-------|--------|
| MRR bruto | R$270.586,96 | 10 contratos |
| Saldo Inter | R$88.684,29 | VERMELHO |
| Health Score | 22/100 | CRITICO |
| Overdue >30d | R$46.117,28 | Laranjeiras + Gelain |
| Payable vencido | R$141.651,43 | 16 contas |
| Liquidez | 0.15x | Emergencia |
| Churn YTD | 0% | Verde |

## Agentes Disponíveis

| Agente | Arquivo | Skills que usa |
|--------|---------|----------------|
| CashflowPredictorAgent | cashflow_predictor.py | 01, 06 |
| PricingOptimizerAgent | pricing_optimizer.py | 02, 04 |
| CostingAnalyzerAgent | costing_analyzer.py | 03 |
| FinancialAdvisorAgent | financial_advisor.py | 05 |
| RiskMonitorAgent | risk_monitor.py | 07 |
| CollectionNegotiatorAgent | collection_negotiator.py | 08 |

## Grupo B — Estratégico (8 skills)

| # | Arquivo | Agente | Prioridade | Foco |
|---|---------|--------|------------|------|
| 09 | 09-matriz-riscos-negocio.md | RiskMonitorAgent | ALTA | Matriz 5x5 riscos operacionais/financeiros |
| 10 | 10-diagnostico-financeiro-completo.md | FinancialAdvisorAgent | ALTA | Diagnóstico 360° com score e plano |
| 11 | 11-plano-acao-90-dias.md | FinancialAdvisorAgent | ALTA | Plano executivo 90 dias por prioridade |
| 12 | 12-planejamento-estrategico-anual.md | FinancialAdvisorAgent | MÉDIA | OKRs anuais + simulação de cenários |
| 13 | 13-viabilidade-investimento.md | FinancialAdvisorAgent | MÉDIA | ROI/payback/TIR para investimentos |
| 14 | 14-metas-smart-financeiras.md | FinancialAdvisorAgent | MÉDIA | Metas SMART com milestones mensais |
| 15 | 15-benchmark-setorial.md | FinancialAdvisorAgent+RiskMonitorAgent | MÉDIA | Benchmark setor segurança patrimonial |
| 16 | 16-tributario-lucro-real.md | TaxCalculatorAgent | ALTA | IRPJ/CSLL/PIS/COFINS + LALUR Lucro Real |
| 17 | 17-tributario-simples-anexo-iv.md | TaxCalculatorAgent | CRITICA | Simples Anexo IV — CNPJ 66.014.833 (Patrimonial): CPP patronal FORA do DAS, retencao 11% Lei 9.711, ISS dentro do DAS, e o filtro contra literatura de Lucro Real |
