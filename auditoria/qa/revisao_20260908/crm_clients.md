# Revisão CRM + clients (agente só-leitura, 08/09/2026 ~05h)

303 rotas revisadas · VIVA 45 / LIGAR 48 / INTERNA 78 / MORTA 132. `contract_signature.py` não revisado (trabalho alheio).

## Defeitos (mais grave primeiro)
1. `clients/services/client_ai_service.py:231, 269-275, 395` — classe 1 — compara `Client.status == ClientStatus.ATIVO` ("ativo") mas o enum do banco só tem active/blocked/cancelled/churned/defaulter/prospect/suspended; o StrEnum em `clients/models/client.py:36-43` não tem nenhum label do banco → GET /clients/ai/dashboard 500. 25 clientes todos 'active'. Correção: alinhar ClientStatus aos labels do banco.
2. `client_ai_service.py:451,475` (first_contract_date), `:357` (average_ticket) — classe 2 — atributos inexistentes no model → 500 em /clients/{id}/ai/{profile,segmentation,churn-risk,recommendations}. Só o clássico chama.
3. `crm/services/dashboard_service.py:382` — classe 2 — `.date()` em `date` (actual_close_date) → GET /crm/dashboard/trends/sales 500 sempre que existe deal ganho.
4. `crm/repositories/commission_repository.py:330-331` + `commission_controller.py:402-418` — classe 2 — get_by_id sem selectinload(rule) → GET /crm/commissions/{id} 500 MissingGreenlet.
5. `crm/schemas/contract.py:411` — classe 1/2 — `clauses: list[dict]` mas contract_templates.clauses é list[str] em 2 dos 4 modelos → GET /crm/contracts/templates 500. Correção: `list[dict | str] | None`.
6. `clients/controllers/client_controller.py:275 × 342` — classe 6/3 — /condominiums/{id} declarada antes de /condominiums/stats → 422 sempre.
7. `crm/services/contract_service.py:74-78,127-128` — classe 5 — reajuste com IGPM 4,50/IPCA 4,23/INPC 4,18 fixos (2024) em renew/calculate-adjustment; 14 contratos com adjustment_enabled. Correção: índice real (BCB/SGS) ou percentual explícito.
8. `crm/services/orchestration.py:1501-1555` (followup_em_lote ← POST /crm/followups/lote, botão no redesign crm.py:640) — classe 8 — ignore_antispam=True e sem DISTINCT por telefone: cada clique reenvia a todas as propostas sent sem resposta. Correção: tirar ignore_antispam e DISTINCT ON (phone).
9. `crm/services/growth_services.py:354-425` (process_due_enrollments ← beat horário) + `_action_send_whatsapp:157-171` — classe 8 — passo WhatsApp da cadência não consulta is_opted_out, sem antispam, sem registro em crm_followups, telefone cru. Dormente (0 enrollments) mas armado pelo MCP inscrever_em_sequencia. Correção: rotear por F.send_followup.
10. `crm/controllers/growth_controller.py:1151-1160` (GET /crm/forecast) — classe 4+5 — "fechado no mês" = updated_at no mês de now() UTC. Correção: actual_close_date e Manaus.
11. `crm/services/dashboard_service.py:125,134` — classe 4 — leads_new_today compara created_at (UTC naive) com date.today() Manaus.
12. `crm/controllers/client_controller.py:35-39,100-101` (GET /crm/clients, /resumo, /{id}) — classe 5 — MRR e contratos_ativos somam client_contracts (10, ponte) e não contracts (14 active). Correção: ler de contracts.
13. `operacional/controllers/redesign_data_controller.py:3124` (action opportunity-stage) — classe 5 — chama só update_stage; a rota do CRM faz ensure_contract_for_won_opportunity + log_activity. Mover para closed_won pela tela nova não gera contrato nem timeline. Correção: reaproveitar o handler do controller.
14. `growth_controller.py:452` (POST /crm/sequences/process-due), `contact_controller.py:203,252` (GET/POST /crm/activities/) — classe 6 — duplicam o beat e /activities/timeline. Apagar.
Leves sem chamador: GET /crm/negociacoes/status, /crm/pipeline-resumo, /crm/forecast/by-seller, /crm/apresentacoes/exemplo, DELETE /crm/quotas/{qid}.

## MORTA (132) — resumo por grupo
- clients: /stats · enable-plus · condominiums activate/start-implantation/finish-implantation/stats · units ×9 (units=0) · /{id}/contracts e /contracts/* ×7 (client_contracts só pela ponte) · integrations ×6 · ai ×6 (500).
- crm/clients: /resumo, /{id}. leads: /stats, recalculate-score, recommended-action. opportunities: from-lead, pipeline/stats. proposals: /stats, templates ×5, submit, approve.
- contracts: /stats, /alerts, GET templates e templates/{id} (500 até corrigir), sla-reports ×4. commissions: 20 das 21 (fica GET /crm/commissions — agente).
- contacts: activities/recent, GET/POST activities/. dashboard: 12 rotas (só clássico). enrichment/taxas.
- growth: sequences/{sid}/enrollments, sequences/process-due, workflows ×6, forms ×5 + public forms ×2, booking-links ×4 + bookings + public booking ×2, segments ×6, properties ×3 + entities custom, scoring ×6, quotas DELETE, forecast/by-seller, negociacoes/status, pipeline-resumo, apresentacoes/exemplo.

## LIGAR (48) — para o redesign
clients: /{id}/full (ficha), activate/suspend/block, set-defaulter/clear-defaulter, condominiums CRUD (10 reais). leads: DELETE (arquivar). proposals: accept/reject (botões), items PUT/POST/DELETE (175 itens). contracts: templates POST/PUT/approve/DELETE (após schema), suspend/terminate, renew/calculate-adjustment (após índice), items ×3 (7 reais), addendums ×3 (7 reais). contacts: CRUD (13 reais), clients/{id}/360, activities/timeline GET/POST (134), tasks PATCH/DELETE. enrichment cnpj/cep (autofill). products CRUD (115 produtos CFTV).

## VIVA/INTERNA
Fluxo comercial vivo: leads (MCP/Hermes), oportunidades, propostas (send/whatsapp/completo/marcar-enviada/pdf/public/sign/track.gif), contratos (pdf, pdf-modelo, abrir-assinatura, enviar-link, submit, activate), growth (docs, pricing, followups, negociações, visitas, reuniões, NPS, apresentações, orçamento PDF, whatsapp/cadastrar).
