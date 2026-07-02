# RAIO-X FINAL DO CONECTA PRO — Mapa de Prontidão por Módulo (READ-ONLY)

**Data:** 2026-05-31 · **Tipo:** inventário read-only do sistema auditado (nenhum código/DB/container alterado; a única escrita foi este relatório). **Objetivo:** mapear, módulo por módulo, o que está pronto pra desenvolver e o que tem mina enterrada.

## Método (e a honestidade sobre auth)
- **Sem token fresco do navegador** → endpoints **NÃO** foram curl-testados com auth. Usei o método **determinístico por ORM**: carregar 1 amostra de **cada** model (365 mappers). Qualquer model com **coluna/tabela faltando ou enum divergente falha** = 500 garantido no endpoint que o usa.
- Isso captura **schema drift + enums** com precisão. **Não** captura: bugs de lógica de negócio, 500 que só aparecem com payload específico, nem problemas pós-auth de código.

## Critério de veredito (explícito)
- 🟢 **SÃO** = 0 models falhando.
- 🟡 **Defeito parcial** = até 33% dos models do módulo falham.
- 🔴 **Boa parte quebrada** = mais de 33% dos models do módulo falham.

## NÚMEROS GERAIS
- **~40 módulos · 3520 rotas · 365 models** testados → **221 OK / 144 FALHAM**.
- Falhas: **74 coluna ausente · 66 tabela ausente · 3 enum divergente · 1 bug de ORM** (não-drift).
- → O schema drift é **muito maior** que as 5 dashboards já corrigidas: ~140 tabelas do ERP ainda divergem do model.

---

## TABELA COMPLETA — STATUS MÓDULO POR MÓDULO (31 módulos com models, ordenado por saúde)

| # | Módulo | Models OK | Models FAIL | % OK | Tipo de falha | Veredito |
|---:|---|---:|---:|---:|---|---|
| 1 | crm | 16 | 0 | 100% | — | 🟢 SÃO |
| 2 | recruitment | 7 | 0 | 100% | — | 🟢 SÃO |
| 3 | ged | 6 | 0 | 100% | — | 🟢 SÃO |
| 4 | clients | 5 | 0 | 100% | — | 🟢 SÃO |
| 5 | audit | 5 | 0 | 100% | — | 🟢 SÃO |
| 6 | document_kits | 4 | 0 | 100% | — | 🟢 SÃO |
| 7 | equipment_management | 4 | 0 | 100% | — | 🟢 SÃO |
| 8 | gedeon | 4 | 0 | 100% | — | 🟢 SÃO |
| 9 | reimbursement | 4 | 0 | 100% | — | 🟢 SÃO |
| 10 | empresas | 2 | 0 | 100% | — | 🟢 SÃO |
| 11 | monitoring | 2 | 0 | 100% | — | 🟢 SÃO |
| 12 | core | 1 | 0 | 100% | — | 🟢 SÃO |
| 13 | people_management | 31 | 2 | 94% | 2 enum (data case) | 🟡 defeito parcial |
| 14 | ai | 8 | 2 | 80% | col (chat context) | 🟡 defeito parcial |
| 15 | reports | 4 | 1 | 80% | 1 col | 🟡 defeito parcial |
| 16 | operacional | 23 | 6 | 79% | tabelas diaristas fiscais + col INSS/IRRF | 🟡 defeito parcial |
| 17 | bidding | 10 | 5 | 67% | col (pricing/assessment) | 🟡 defeito parcial |
| 18 | integrations | 24 | 12 | 67% | col/tabela | 🟡 defeito parcial |
| 19 | config | 3 | 2 | 60% | col (codigo/nome legado) | 🔴 boa parte quebrada |
| 20 | financial | 34 | 45 | 43% | tabelas ABC custeio + nfe/nfse + estoque + col | 🔴 boa parte quebrada |
| 21 | hr | 6 | 10 | 38% | **tabelas inteiras ausentes** (folha/férias/docs) | 🔴 boa parte quebrada |
| 22 | notifications | 6 | 10 | 38% | col | 🔴 boa parte quebrada |
| 23 | client_portal | 1 | 2 | 33% | col (sender_type) | 🔴 boa parte quebrada |
| 24 | campo | 3 | 6 | 33% | tabelas + col | 🔴 boa parte quebrada |
| 25 | health_occupational | 3 | 6 | 33% | — | 🔴 boa parte quebrada |
| 26 | retention | 4 | 10 | 29% | col | 🔴 boa parte quebrada |
| 27 | services | 1 | 4 | 20% | col | 🔴 boa parte quebrada |
| 28 | automation | 0 | 8 | 0% | col (workflow_*) | 🔴 boa parte quebrada |
| 29 | cct | 0 | 3 | 0% | tabelas (benefit/compliance/salary) | 🔴 boa parte quebrada |
| 30 | government_integrations | 0 | 6 | 0% | tabelas (nfe/nfse/efd/ecd) | 🔴 boa parte quebrada |
| 31 | mobile | 0 | 4 | 0% | col | 🔴 boa parte quebrada |

**Contagem:** 🟢 **12 sãos** · 🟡 **6 defeito parcial** · 🔴 **13 boa parte quebrada**.

> Nota: o critério é estrito (>33% fail = 🔴). Módulos como financial/hr **não estão totalmente caídos** — boa parte das rotas funciona; o 🔴 sinaliza que **metade do módulo tem drift** e exige rodada de migrations antes de desenvolver em cima.

### Mapa rota↔módulo (rotas servidas, por prefixo de URL)
people-management 722 · financial 536 (+financeiro 31) · government 440 · operacional 244 · ged 197 · crm 114 · bidding 87 · recruitment 79 · integrations 78 · notifications 76 · retention 70 · campo 64 · services 63 · clients 51 · config 47 · document-kits 45 · health-occupational 40 · empresas 36 · portal 36 · analytics 32 · reports 32 · audit 31 · maintenances 28 · security 28 · comodatos 26 · reimbursements 26 · cct 25 · gedeon 22 · installations 20 · equipment 19 · mobile 17 · documents 16 · monitoring 16 · onvio 15 · fiscal 13 · gdrive 12 · auth 9 · users 9 · workflows 9 · marketing 8 · webhooks 8 · banking 5 · whatsapp 5 · juridico 3 · search 1.

---

## MAPA DE PRONTIDÃO — módulos que o Jordan vai tocar primeiro
| Módulo | Pronto pra desenvolver? | Evidência |
|---|---|---|
| **comercial/CRM** | 🟢 **PRONTO JÁ** | 16/16 models OK; contracts=10, clients=11 presentes |
| **DP — cadastro (people_management)** | 🟡 quase | 31/33 OK; só 2 enums de data (case: `admissional`→`ADMISSIONAL`, `provision`) — fix igual aos 11 já feitos |
| **DP — folha/férias/docs (hr)** | 🔴 **PENDÊNCIA PESADA** | 10 **tabelas inteiras não existem**: employee_documents, payroll_events/exports/integrations, vacation_requests/periods, employee_notifications/preferences |
| **propostas/precificação (bidding)** | 🟡 defeito | 5 colunas faltam: bidding_pricing.assessment_id, bidding_analyses.opportunity_id, raw_assessment, metadata_extra, updated_at |
| **financeiro (financial)** | 🔴 **PENDÊNCIA PESADA** | 45 falhas: módulo **ABC de custeio/precificação não existe no banco** (fin_cost_pools/drivers/objects/activities/allocations/analyses); nfe/nfse drift de nome; estoque sem colunas; payable/payment sem created_by |
| **operacional** | 🟡 defeito | tabelas fiscais de diaristas ausentes (documentos/eventos_esocial/retencoes); tabela_inss/irrf sem `is_active` |

---

## INTEGRAÇÕES EXTERNAS (estado; transação não disparada)
| Integração | Configurada? | Última atividade | Estado |
|---|---|---|---|
| **Banco Inter** | ✅ cert `conecta_certificado.p12` (Abr 4) presente | sem atividade recente nos logs | 🟡 configurado, inativo recentemente |
| **Onvio** | ✅ scripts + cron | **sync 07/mai** (período 04.2026, success, 621 API / 8 novos) | 🟢 funcionando (mensal) |
| **Sólides** | ✅ 44 mapeamentos | **último sync 15/mar** | 🔴 **STALE** (~2,5 meses) |
| **NFS-e (nacional/Manaus)** | ✅ tabelas `nfses`(27) / `nfse_entrada`(10) | 27 NFS-e reais no banco | 🟡 dado OK, mas model espera `nfse`/`nfse_lotes` (não existem) → drift de nome |

---

## LISTA ÚNICA E CONSOLIDADA DE PENDÊNCIAS (as "não-surpresas")
1. 🔴 **Schema drift massivo: ~140 tabelas** (74 colunas + 66 tabelas ausentes) — muito além das 5 dashboards. Concentra em **financial (45)**, integrations, retention, notifications, hr, automation.
2. 🟡 **3 enums divergentes** (data vs nomes do enum): `fin_accounting_periods` (periodstatus), `gp_asos` (aso_type_enum: `admissional`→`ADMISSIONAL`), `portal_access_logs` (portal_access_action_enum: `provision`). Fix igual aos 11 já feitos.
3. 🟡 **/reports/kpis** — dado de tenant já religado; falta a lógica de filtro do endpoint.
4. 🟡 **Offsite de backup** — rclone B2 instalado mas **não configurado** (backups só locais).
5. 🔴 **Sólides sync parado em 15/mar** — reativar.
6. 🟡 **NFS-e drift de nome** — model `nfse` vs banco `nfses`.
7. 🟢 **1 bug de ORM (não-drift):** `fin_journal_entries` precisa de `.unique()` no result (eager load) — bug de código, não schema.
8. 🟢 **Framework de agentes** — inerte, **já em quarentena** (encerrado).
9. 🟢 **Migrations órfãs** `sprint77_openclaw_*` em `alembic/versions/` (drop registrado em `drop_openclaw_tables`).
10. ⚪ **234 tabelas "só-no-banco"** (legado, mapa Frente 2) — inócuas, mas existem.

---

## O QUE NÃO FOI POSSÍVEL VERIFICAR (honestidade)
- **Endpoints com auth real** — sem token fresco; ORM-load pega schema/enum (a maior fonte de 500), mas **não** lógica de negócio nem 500 dependentes de payload.
- **Validade do certificado A1/p12** — exige a senha do .p12 (não usada).
- **Transações reais de integração** (emitir NFS-e, pagamento Inter) — só verifiquei estado/config.
- **Endpoint-a-endpoint:** quantas das ~140 falhas viram 500 visível depende de quais endpoints o front chama — não enumerei rota a rota.

---

## RESUMO (12 linhas)
1. ~40 módulos · 3520 rotas · 365 models (método ORM determinístico; endpoints não curl-testados com token).
2. 221 OK · 144 FALHAM → drift muito maior que as 5 dashboards já corrigidas.
3. Falhas: 74 colunas + 66 tabelas ausentes + 3 enums + 1 bug de ORM.
4. Veredito geral: 🟢 12 sãos · 🟡 6 defeito parcial · 🔴 13 boa parte quebrada.
5. 🟢 sãos: crm, recruitment, ged, clients, audit, document_kits, equipment, gedeon, reimbursement, empresas, monitoring, core.
6. 🔴 piores: financial (45), integrations (12), notifications (10), hr (10), retention (10), automation (8).
7. Pronto pra desenvolver JÁ: 🟢 comercial/CRM (contracts=10, clients=11).
8. Pendência leve: DP-cadastro (2 enums), operacional, propostas (poucas colunas).
9. Pendência PESADA: 🔴 financeiro (ABC custeio inexistente no banco) e 🔴 DP-folha (10 tabelas ausentes).
10. Integrações: Onvio 🟢 (07/mai) · NFS-e 🟡 (27 reais, drift de nome) · Inter 🟡 (cert ok, inativo) · Sólides 🔴 (15/mar).
11. Não-surpresas: 3 enums · /reports/kpis filtro · offsite B2 · Sólides stale · agentes em quarentena · migrations órfãs.
12. Recomendação: comece pelo comercial (verde); financeiro e DP-folha exigem rodada de migrations antes — são as minas reais.
