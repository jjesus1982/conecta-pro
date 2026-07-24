# F1 — Rotas do Receber (curl-verificadas 2026-07-24)

| Rota | HTTP | Shape real / decisão |
|---|---|---|
| GET /financial/receivables/aging | 200 | `{aging_date, tipo, faixas:[{faixa, quantidade, valor_total}], ...}` (só faixas não-vazias; hoje: acima_90_dias 8 · R$242.073,20). Builder replica em SQL; oráculo compara com o endpoint. |
| GET /financial/billing-rules | 200 | array `{id, condominio_id, name, billing_type, frequency, base_value, due_day, ...}` (cols reais confirmadas na tabela; SEM trigger_days/channel/active do plano — adaptado). |
| GET /financial/billing/cobrar-recorrente/{m}/{a}/preview | 200 | **READ-ONLY seguro**: `{modo:"preview", total_clientes:10, total_mrr:270586.96, sem_pix_key:[], clientes:[{nome,...}]}`. O POST (executa cobrança) NÃO é usado. |
| GET /financial/ai/billing/contracts | 200 | `[]` (mês atual sem contratos a faturar — dado honesto). |
| GET /financial/ai/billing/summary | 200 | `{mes, total_faturado:0, ..., qtd_faturas:0}` (zeros honestos). |
| GET /financial/customers | 200 | `[]` — MAS a tabela customers tem 12 linhas (endpoint filtra algo). Builder lê a TABELA (fonte honesta): cols name, cpf_cnpj, customer_type, status, email, condominio_id. |
| ~~POST /billing/cobrar-recorrente~~ | 405 no GET | NUNCA usar (dispara cobrança real). |
| ~~GET /ai/billing/contratos-a-faturar~~ | 404 | rota certa é /ai/billing/contracts. |
