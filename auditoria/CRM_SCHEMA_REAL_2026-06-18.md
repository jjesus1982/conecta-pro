# CRM Conecta PRO — Schema REAL (extração read-only)
## STEP-0-CRM-SCHEMA-EXTRACT · §13.1 (Chesterton) · §13.5 (dado real, não suposição)

**Data:** 2026-06-18 (extração executada na sessão de 2026-06-23)
**Banco:** `conecta_pro` @ `conecta-pro-postgres`
**Natureza:** EXTRAÇÃO READ-ONLY — somente `SELECT` e `\d`. Nenhum INSERT/UPDATE/DELETE/DDL executado.
**Objetivo:** mapear o que EXISTE antes de qualquer conclusão sobre "deixar igual ao HubSpot".

> ⚠️ Correção de método: o filtro de descoberta do STEP 0 usava só padrões em PT‑BR (`%oportun%`),
> e por isso **perdeu a tabela `opportunities`** (nome em inglês). Reexecutei com padrões EN
> (`%opportunit%`, `%pipeline%`, `%stage%`, `%deal%`) — `opportunities` EXISTE. Sem essa correção, a
> conclusão sobre pipeline teria sido falsa. (Chesterton: não derrubar a cerca sem enxergá-la.)

---

## STEP 0 — Tabelas candidatas a CRM (descoberta, sem filtro de opinião)

Casaram nos padrões (PT + EN). Classificadas por papel:

**Núcleo de vendas (CRM real):**
`leads`, `lead_scores`, `marketing_leads`, `opportunities`, `proposals`, `proposal_items`,
`proposal_templates`, `proposal_approvals`, `proposal_approval_levels`, `proposal_followups`,
`proposal_signatures`, `proposal_term_options`, `proposal_wizard_states`, `clients`, `customers`,
`client_contracts`, `crm_contacts`, `crm_activities`.

**Periféricas (casaram no nome, mas NÃO são pipeline de vendas):**
`client_tickets`, `client_ticket_messages`, `client_portal_tickets`, `client_portal_ticket_messages`,
`client_portal_sessions`, `ged_clients`, `gdrive_client_folders`, `gedeon_client_patterns`,
`bidding_proposals`, `bidding_proposal_items`, `bidding_opportunities` (licitações),
`marketplace_transform_pipelines` (ETL, não vendas), `cost_activities`, `fin_cost_activities` (custos ABC).

---

## STEP 1 — Schema das tabelas centrais (resumo)

### `leads` (8 registros) — topo do funil
Campos: `id, name, email, phone, company, position, company_size, industry`, **`source`** (varchar),
**`status`** (varchar), `score` (int), `probability` (float), `expected_value` (float), `notes`,
`assigned_to_id`→users, **`client_id`**→clients, `qualificacao` (jsonb), `last_contact_at`,
`next_contact_at`, `is_active`, e atribuição de marketing (recente): `utm_source/medium/campaign/
content/term, source_platform, mkt_campaign_id, ad_referral(jsonb)`.

### `opportunities` (0 registros) — **A TABELA DE DEAL/PIPELINE**
Campos: `id, title, description, lead_id`→leads, `contact_name/email/phone, company_name`,
**`stage`** (varchar 50, NOT NULL, **indexado** `ix_opportunities_stage`), **`priority`** (varchar 20),
**`value`** (float), **`probability`** (int), `expected_close_date`, `actual_close_date`, `owner_id`→users,
**`loss_reason`** (varchar), `competitor`, `win_notes`, `loss_notes`, `notes`, `is_active`.
FKs: `lead_id`→leads (SET NULL), `owner_id`→users. **Referenciada por** `proposals.opportunity_id` e
`contracts.opportunity_id`. → É um modelo de "deal" completo, estilo HubSpot. **Existe, mas está vazia.**

### `proposals` (6 registros) — propostas/orçamentos (maduro)
~52 colunas. Destaques: `number, version, parent_id`(versionamento), **`opportunity_id`**→opportunities,
`template_id`, dados do cliente (`client_name/email/phone/company/document/address`), `proposal_type`(varchar),
`subtotal/discount_type/discount_value/taxes/total`, `payment_terms/conditions/installments`,
`issue_date/valid_until`, **`status`** (varchar), lifecycle (`sent_at/viewed_at/responded_at/approved_at`),
assinatura (`signature_provider/status/signed_at/signed_document_url`), aprovação (`approval_level_id/
current_approval_level/approved_by_id`), `billing_type`, `selected_term_option_id`, `cct_breakdown/
tax_breakdown(jsonb), margin_percent`.

### `clients` (11) — base de clientes (muito rica)
~73 colunas: identidade (`code, name, trading_name, client_type, document_*`), múltiplos contatos
(`financial_contact_*`, `technical_contact_*`), endereços (entrega + cobrança), **`status`**(enum nativo
`client_status_enum`), **`segment`**(enum nativo `client_segment_enum`), scores (`health_score,
satisfaction_score, engagement_score`), financeiro (`credit_limit, total_revenue, total_debt, mrr,
billing_day, payment_terms`), `account_manager_id, sales_rep_id`, **`lead_id`**→leads (origem), `crm_origin`.

### Apoio
- `crm_contacts` (11): contatos por cliente (`client_id, name, role, email, phone, whatsapp, is_primary`).
- `crm_activities` (0): log de atividades (`client_id, user_id, type, subject, outcome, scheduled_at,
  completed_at`) — **estrutura existe, sem nenhum dado**.
- `lead_scores` (0): scoring de IA do lead (`total_score, quality, conversion_probability, stage, factors
  jsonb, next_best_action`) — **existe, vazia**.
- `customers` (11): tabela paralela a `clients` (coexistem; `clients` é a usada pelo CRM atual).
- `client_contracts` (10): contratos (`client_id, monthly_value, status` enum nativo) → base do MRR.

---

## STEP 2 — ⭐ EXISTE PIPELINE / ESTÁGIO DE VENDA? (a pergunta que motivou a extração)

### Resposta: **SIM no schema, NÃO na prática.** Existe a estrutura; não existe uso nem configurabilidade.

**Evidências (dado real):**

1. **Existe a entidade de deal/estágio:** tabela `opportunities` com coluna `stage` (varchar 50, NOT NULL,
   **com índice próprio**), `priority`, `value`, `probability`, `expected_close_date`, `loss_reason`,
   `competitor` — exatamente o esqueleto de um "Deal" do HubSpot.

2. **MAS `stage` NÃO é enum nativo do banco — é varchar.** Não há `CHECK` nem `ENUM` no Postgres. A
   integridade dos estágios é só de aplicação. (Confirmado: nenhum tipo enum `opportunitystage`/
   `dealstage`/`pipeline*` existe em `pg_enum`.)

3. **Os estágios estão hardcoded no código (StrEnum `OpportunityStage`), não em tabela de configuração:**
   `qualification → needs_analysis → proposal → negotiation → closed_won / closed_lost` (6 estágios).
   Não há tabela que defina pipelines, ordem de estágios ou probabilidade ponderada por estágio.

4. **A tabela está VAZIA (0 registros).** O pipeline foi modelado mas **nunca foi usado** — nenhuma
   oportunidade existe, e as 6 propostas atuais não estão ligadas a oportunidade (`opportunity_id` ocioso).

5. **Há um "mini-funil" no nível do LEAD** (`leads.status`, varchar): valores possíveis no app
   (`LeadStatus`): `new → contacted → qualified → proposal → negotiation → won → lost`. **Em uso real:**
   `new` (7) e `qualified` (1). Ou seja, o avanço de estágio hoje acontece (de leve) no LEAD, não em DEAL.

6. **`proposals.status` (varchar)** tem ciclo próprio (`ProposalStatus`, 10 estados): `draft, pending_
   review, pending_approval, approved, sent, viewed, accepted, rejected, expired, cancelled`. Em uso:
   `sent` (3), `draft` (3).

**Tradução:** o conceito de "estágio de venda" existe em **três lugares desconexos** (lead.status,
opportunities.stage, proposals.status), cada um varchar, sem um pipeline único, sem pesos por estágio,
e a entidade central (deal/opportunity) está zerada.

---

## STEP 3 — Volumes reais (só contagens)

| Tabela | Registros | | Tabela | Registros |
|---|---|---|---|---|
| leads | **8** | | clients | **11** |
| lead_scores | 0 | | customers | 11 |
| marketing_leads | 0 | | client_contracts | 10 |
| **opportunities** | **0** | | crm_contacts | 11 |
| proposals | **6** | | crm_activities | 0 |
| proposal_items | 15 | | proposal_templates | 0 |
| proposal_followups | 6 | | proposal_approvals | 0 |
| proposal_term_options | 7 | | proposal_wizard_states | 0 |

Maturidade de dados: **cliente e proposta têm uso real**; **lead começando**; **deal/pipeline, scoring,
atividades e templates: zerados** (estrutura sem dado).

---

## STEP 4 — Mapa de relações (FKs reais)

```
                 ┌──────────┐
                 │  leads   │ (8)
                 └────┬─────┘
        client_id │   │ lead_id (origem)        assigned_to_id→users
          ┌───────┘   └───────────┐
          ▼                       ▼
   ┌────────────┐          ┌──────────────┐  owner_id→users
   │  clients   │(11)◄─────│ opportunities│ (0)  lead_id→leads
   └────┬───────┘ lead_id  └──────┬───────┘
        │                         │ opportunity_id
   crm_contacts(11)               ▼
   crm_activities(0)        ┌────────────┐  parent_id (versão)
   client_contracts(10)     │ proposals  │ (6) ─► proposal_items(15)
        │ (MRR)             └──────┬─────┘     ─► proposal_term_options(7)
        ▼                          │ opportunity_id  ─► proposal_followups(6)
   (MRR R$ 270k)            ┌──────▼──────┐          ─► proposal_approvals / signatures / wizard
                           │  contracts   │
                           └──────────────┘
   marketing_leads(0) ─crm_lead_id─► leads ;  ─campaign_id─► marketing_campaigns
```

Cadeia de schema COMPLETA e correta: **lead → opportunity → proposal → contract → client**, com
`clients.lead_id` fechando a origem. O encanamento existe; falta a água (dados em opportunity).

---

## EXISTE vs NÃO EXISTE (resumo executivo, sem suposição)

**EXISTE (no banco, hoje):**
- Lead com funil de status (app), scoring (tabela `lead_scores`), atribuição de marketing (UTM/CTWA).
- **Entidade de Deal (`opportunities`)** com estágio, prioridade, valor, probabilidade, data de
  fechamento, motivo de perda e concorrente — modelo equivalente ao "Deal" do HubSpot. **Vazia.**
- Proposta madura: 10 status, versionamento (`parent_id`), aprovação em níveis, assinatura eletrônica,
  opções de prazo, follow-ups, templates, wizard.
- Cliente rico: segmentos, scores (health/satisfaction/engagement), MRR, múltiplos contatos, endereços.
- Múltiplos contatos por cliente (`crm_contacts`) e log de atividades (`crm_activities`, vazio).

**NÃO EXISTE (vs HubSpot):**
- **Pipeline configurável**: não há tabela de "pipeline" nem de definição de estágios. Estágios são
  StrEnum no código, um único fluxo implícito, não editável por tela/DB.
- **Probabilidade ponderada por estágio**: `probability` é um inteiro livre por oportunidade, não um peso
  derivado do estágio (HubSpot dá % por estágio).
- **Integridade de estágio no banco**: `lead.status`, `opportunities.stage`, `proposals.status` são todos
  varchar — sem ENUM/CHECK no Postgres (só validação de app).
- **Uso do pipeline**: 0 oportunidades; propostas não vinculadas a deal (`opportunity_id` ocioso).
- **Timeline/engajamento estilo HubSpot** (tasks, e‑mails rastreados, calls, sequences): só há
  `crm_activities` genérica (vazia); não há tabelas dedicadas de task/email/sequence.
- **Forecast/relatório de pipeline ponderado**: inexistente (consequência dos itens acima).

---

## Conclusão objetiva (sem opinião de produto, só fato)

Para "ficar igual ao HubSpot", **o esqueleto do deal/pipeline JÁ EXISTE** (`opportunities`) e está
ligado a leads/proposals/contracts — não precisa criar a entidade do zero. O que falta é, em ordem de
fato: **(a)** usar a tabela (criar oportunidades a partir de lead/proposta), **(b)** transformar o
estágio em um pipeline configurável com pesos (hoje é StrEnum + varchar), **(c)** unificar os três
"status" desconexos em uma visão de funil única, **(d)** popular atividades/timeline. Nada disso é
afirmação de "deveria"; é o delta entre o que o banco TEM e o que o HubSpot OFERECE.

---

## Metadados da extração
- Steps executados: 0 (PT+EN), 1, 2.1, 2.2, 3, 4 — todos read-only.
- Desvio metodológico corrigido: filtro PT‑only perdia `opportunities` (corrigido com padrões EN).
- **Nota de completude da extração (0–10): 9,5** — cobriu tabelas, colunas, enums (nativos e de app),
  valores reais, contagens e FKs; apanhou o erro de naming PT/EN. −0,5: não rodei `\d+` cru de cada
  sub-tabela de proposta (resumidas via information_schema), conforme orientação de "resumir".
- Arquivo: `/opt/conecta-pro/auditoria/CRM_SCHEMA_REAL_2026-06-18.md`
