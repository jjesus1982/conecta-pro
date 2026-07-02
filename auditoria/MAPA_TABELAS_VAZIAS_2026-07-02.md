# MAPA DAS TABELAS VAZIAS → PLANO DE CARGA (2026-07-02)
*Pedido do Jordan: alimentar o sistema exclusivamente com dados reais; mapear as vazias antes de importar.*

590 tabelas, **377 vazias**. Mas "vazio" tem 4 causas MUITO diferentes. Classificação honesta:

## ✅ FONTES REAIS — já carregadas (o loop de veracidade ligou as telas nelas)
employees 71 · posts 12 · allocations 58 · shifts 180 · diarists 14 · gp_clock_punches 4310 · gp_asos 96 · gp_epi_deliveries 220 · gp_risks 15 · hr_payslips 51 · employee_benefits 157 · employee_vacation_periods 67 · hr_certifications 51 · training 9/20 · ged_kit_documents 2046 · inter_transactions 1826 · nfses 27 · contracts 11 · clients 14 · cct_cargos 51 · sst_afastamentos 6.
→ **O dado real que temos JÁ está no sistema.** As telas foram ligadas a essas tabelas.

## 🟢 A — CARREGAR AGORA (vazia + fonte real disponível)
Poucas — a maioria do dado real já entrou. Candidatas a confirmar fonte:
- `employee_documents`=0 mas `ged_kit_documents`=2046 → a tela "documentos por funcionário" deve LER ged_kit_documents (fantasma potencial, tipo o que corrigimos no portal). **Ação: repoint, não import.**
- `allocations`=58 parcial → se a Pyetra tiver ESCALA nova (mês corrente), enriquecer alocações/postos. **Ação: pedir a escala do mês.**

## 🟡 B — ENCHE COM O USO (vazio-real CORRETO, sem fonte de carga em massa)
Vazias porque a atividade ainda não aconteceu — não há dado histórico pra importar; enchem quando o sistema for operado:
- Operações: `service_orders`, `service_executions`, `occurrences`, `substitutions`, `time_bank`.
- Portal/Notif: `portal_notifications`, `notification_logs`.
- Retention/Clima: `turnover_predictions`, `climate_responses` (predições/pesquisas geram sob uso).
→ **Ação: nada a importar. Mostram "aguardando dado" honesto (já garantido no loop).**

## 🟠 C — PRECISA DE DADO SEU (fonte externa que só você tem)
Real, mas não está em nenhuma planilha/integração — depende de você fornecer/cadastrar:
- `equipments` / `equipment_maintenances`=0 → inventário real de CFTV/equipamentos por posto (câmeras, NVRs). Você tem uma planilha/lista?
- `health_epi_inventory`=0 → estoque de EPI (temos as 220 ENTREGAS, mas não o estoque).
- `sla_configs`=0 → termos de SLA por contrato (precisa definir).
→ **Ação: aguardar você indicar a fonte; aí importo com prova.**

## ⚫ D — FEATURE MORTA / FUTURA (ignorar ou desligar — sem tela ativa nem fonte)
~200 tabelas: `ai_*` (50), `chatbot_*` (11), `marketplace_*` (11), `ocr_*` (9), `push_*` (9), `purchase_*`, `sig_*`, `ab_*`, etc. Features experimentais nunca ativadas.
→ **Ação: não alimentar. Candidatas a limpeza de schema no futuro (não urgente).**

## 🧹 LIMPEZA (dado RUIM, não vazio)
- `sst_cipa_reunioes`=2834 → **poluída**: 2834 linhas idênticas (POSTs repetidos sem dedup). Não é dado real — é lixo. **Ação: dedup (manter 1) + guard anti-duplicata no endpoint.**

---
## RESUMO PRA DECISÃO
1. **Repoint** `employee_documents`→ged_kit_documents (como no portal) — faço já, é veracidade.
2. **Limpar** sst_cipa_reunioes (2834→1) — faço já, com backup.
3. **Pedir a você**: (a) escala Pyetra do mês corrente; (b) inventário de equipamentos/CFTV; (c) estoque EPI; (d) termos de SLA. Sem isso, essas telas ficam honestamente "aguardando dado".
4. **B e D**: não há o que importar (vazio-real correto / feature morta).
