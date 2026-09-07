# Quarentena de 06/09/2026 — 251 tabelas fora do `public`

**O que foi feito:** `ALTER TABLE public.X SET SCHEMA lixo_20260906` para 251 tabelas com **0 linhas**
(confirmado por `count(*)`, não por estimativa) de famílias que o mapa classificou como 🔴
(`auditoria/MAPA_CONECTA_PRO_20260906.md`): `ai_*` 50, `fin_*` 13 (segunda contabilidade), `marketplace_*`,
`chatbot_*`, `ocr_*`, `push_*`, `scheduler_*`, `workflow_*`, GED genérico, `health_*` (duplicata de `gp_epi_*`),
`cost_*/custos_*`, `purchase_orders/approvals`, e famílias de 2–4 tabelas sem dado nem rota usada.
`public`: 688 → 437 tabelas.

**Por que mover e não apagar:** é reversível em segundos, e qualquer código vivo que ainda toque numa
delas dá `UndefinedTable` — que é o sinal que se quer ver, na varredura da meia-noite, antes de apagar.

**Não entraram (e por quê):** 15 tabelas alvo de chave estrangeira de tabela viva (`payment_methods`,
`notification_channels/templates`, `api_keys/endpoints`, `webhook_configs`, `purchase_requisitions/*`,
`fraud_patterns/rules`, `rep_devices/events`) e as 3 do schema `retention`. Tabelas com 0 linhas de
famílias 🟢/🟡 (`hr_*`, `employee_*`, `contract_*`, `proposal_*`, `juridico_*`, `sst_*`, `cct_*`…) ficam
para a etapa do módulo dono.

**Reverter tudo:** `psql "$URL" -f auditoria/lixo_20260906/reverter.sql`
**Reverter uma:** `ALTER TABLE lixo_20260906."nome" SET SCHEMA public;`
**Apagar de vez** (só após ≥30 dias com varredura verde e nenhum `UndefinedTable` nos logs):
`auditoria/lixo_20260906/apagar_de_vez.sql`

Lista completa: `tabelas.txt`. Modelos SQLAlchemy de parte delas continuam no código de pacotes vivos
(`integrations/connectors/solides/models.py`, `financial/models/purchase_*`, `notifications/push/*`…) —
`create_all` **não** roda no startup (medido: `init_db` sem chamador), então não voltam sozinhas.
