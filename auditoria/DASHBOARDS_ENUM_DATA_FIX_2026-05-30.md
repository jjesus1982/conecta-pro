# Verificação final — 5 telas de dashboard abrem sem 500

**Data:** 2026-05-30/31 · **Status:** ✅ **5/5 telas carregam** (prova ORM real).

## Achado pós-Camada 3
Após adicionar as colunas faltantes (Camada 3), 2 telas (executive_kpis, financial_kpis) ainda davam 500 por **divergência de enum no DADO** (valores PT/minúsculos vs nomes do enum do model). Normalização de dado (com decisões do Jordon, sem adivinhar):

### executive_kpis (varchar — UPDATE livre, backup PRE_EXECKPIS_*)
- category: FINANCEIRO→FINANCIAL, COMERCIAL→COMMERCIAL, RH→HR, **FISCAL→COMPLIANCE**, **EFICIENCIA→OPERATIONAL** (10 linhas)
- kpi_type: currency→CURRENCY, percentage→PERCENTAGE, **number→ABSOLUTE** (10)
- direction: up→INCREASE, down→DECREASE (10)
- status: active→ACTIVE (10) · alert_level: normal→NORMAL, warning→WARNING (10) · aggregation_period: monthly→MONTHLY (10)

### financial_kpis (enum nativo + zona financial/, autorizado)
- ADD VALUE (uppercase) nos tipos kpi_category/kpi_frequency/kpi_status/alert_level
- categoria: custom→CUSTOM, cash_flow→CASH_FLOW, **growth→REVENUE**; frequencia: monthly→MONTHLY; status: active→ACTIVE; alert_level: warning→WARNING, **none→NORMAL** (inferência documentada)
- **Dado financeiro preservado** (MRR=270.586,96 etc.).

## Prova
Query ORM real de cada model (carrega objetos com mapeamento completo): **5/5 OK**. Leftover inválido=0 em todas as colunas. 14/14 containers healthy.

## Decisões do Jordan (não adivinhadas)
FISCAL→COMPLIANCE, EFICIENCIA→OPERATIONAL, number→ABSOLUTE, growth→REVENUE. Inferências documentadas: none→NORMAL, up→INCREASE/down→DECREASE.
Cada UPDATE em prod precedido de backup fresco + demonstração de contagem em staging.
