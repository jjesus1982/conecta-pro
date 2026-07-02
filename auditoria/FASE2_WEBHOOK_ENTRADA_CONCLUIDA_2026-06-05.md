# Fase 2 — Entrada WhatsApp (webhook Chatwoot → Lead/CRM) CONCLUÍDA

- **Data:** 2026-06-05 ~22:40 UTC
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Receber mensagens do Chatwoot via webhook, logar (entrada+saída) e capturar Lead.
- **Resultado:** ✅ **Implementada, deployada e testada ponta a ponta.** Dados de teste limpos.

---

## 1. O que foi entregue
- **Migration `sprint90`**: tabela `cwi_message_log` (log append-only).
- **Migration `sprint91`**: `leads.email` agora **nullable** (lead de WhatsApp não tem email).
- **`LeadSource.WHATSAPP`** adicionado ao enum.
- **Schema** `LeadBase.email`/`LeadResponse.email` → opcionais; dedup por email no controller só roda se email informado.
- **Webhook** `POST /api/v1/whatsapp/webhook` (em `connectors/whatsapp/controller.py`, sem JWT):
  - Valida HMAC SHA256 contra `WHATSAPP_WEBHOOK_SECRET` (se configurado).
  - Processa `message_created`; extrai phone/conversa/msg/content/tipo defensivamente.
  - **Loga entrada + saída** em `cwi_message_log` (idempotente via `ON CONFLICT (chatwoot_message_id)`).
  - **Entrada:** normaliza telefone (remove `+`/`55`) → dedup em `leads.phone` → cria Lead (`source=whatsapp`, `email=NULL`) se novo.
  - **Saída:** só loga (não cria Lead).
- **Bug pré-existente corrigido** em `lead_service._score_response_time`: `datetime.now() - lead.created_at` quebrava quando `created_at` ainda é None (lead recém-criado antes do commit). Agora trata como "muito recente" (100). *Afetava qualquer criação via `repo.create`, não só o webhook.*

## 2. Teste ponta a ponta (com dados de teste, depois limpos)
| Cenário | Resultado |
|---------|-----------|
| POST entrada (msg nova) | `200` Lead criado (`email=NULL`, `source=whatsapp`) ✅ |
| POST entrada repetido (idempotência/dedup) | mesmo `lead_id`, **sem duplicar** ✅ |
| POST saída | `lead_id=None` (não cria lead), mas **logado** ✅ |
| Log da conversa | `in=1, out=1`, lead vinculado só na entrada ✅ |
| Idempotência do log | 1 linha apesar de 2 POSTs da mesma msg ✅ |
- **Limpeza:** dados de teste removidos → `cwi_message_log` vazia, `leads` de volta aos 11 originais.

## 3. Deploy
- Backups do banco antes de cada migration (`backups/fase2/`).
- `docker cp` dos arquivos para os **9 containers** backend-image + migrations no backend.
- `alembic upgrade head` (head = `sprint91_lead_email_nullable`).
- Restart do **backend** (serve o webhook + model novo).
- **host == container** confirmado (sem drift).

## 4. Pendências / operação (PROPOSTAS — não feitas)
1. **🔐 `WHATSAPP_WEBHOOK_SECRET` NÃO está no env do backend** → o webhook hoje **aceita requisições sem validação HMAC**. Antes de expor, passar o segredo no compose (env do backend) e configurar o mesmo no Chatwoot.
2. **Configurar o Webhook no Chatwoot** (Conta 1 → Integrations/Webhooks ou Automation) apontando para `http://conecta-pro-backend:8080/api/v1/whatsapp/webhook` com o segredo.
3. **Workers:** receberam o código novo em disco (cp), mas **não foram reiniciados** — rodam o código antigo em memória até o próximo restart. É **inócuo** (mudança email-nullable é retrocompatível; workers não servem o webhook).
4. Validar payload real do Chatwoot na primeira mensagem (extração é defensiva, mas confirmar os campos `sender.phone_number`/`conversation.id` da versão fazer-ai).

## 5. Verificação real pendente (operacional)
Após configurar o webhook no Chatwoot: enviar uma mensagem real de WhatsApp para `+558008804414` e conferir no banco que `cwi_message_log` recebeu a linha e (se número novo) um Lead `source=whatsapp` foi criado.

---
*Mudanças: 2 migrations (com backup), 1 webhook + helpers, edições em model/schema/controllers/service, deploy por docker cp + restart (host==container). Dados de teste limpos. Token/segredos não expostos.*
