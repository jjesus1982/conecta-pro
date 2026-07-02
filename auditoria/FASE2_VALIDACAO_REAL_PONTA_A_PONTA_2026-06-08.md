# Fase 2 — Validação REAL ponta a ponta (mensagem de WhatsApp de verdade)

- **Data:** 2026-06-08 ~14:03 UTC
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Confirmar o fluxo de entrada com uma mensagem real (Chatwoot → webhook → log + Lead).
- **Resultado:** ✅ **100% funcional em produção.** Webhook do Chatwoot configurado e entregando.

---

## 1. Evidência — `cwi_message_log` (conversa 5, número real mascarado)
| direção | phone | conv | msg_id | lead_id | conteúdo |
|---------|-------|------|--------|---------|----------|
| **in** | 928…6006 | 5 | 17 | `24c2d895…` | "Quero um orçamento da Conecta Mais, para…" |
| out | 928…6006 | 5 | 18 | — | "Recebido" |
| out | 928…6006 | 5 | 19 | — | "Show" |
| out | 928…6006 | 5 | 20 | — | "Estou fazendo um teste" |
| out | 928…6006 | 5 | 21 | — | "Obrigado" |

- Total no log: **6** (in=2, out=4). As **saídas** (respostas do atendente) são logadas sem lead — correto.

## 2. Evidência — Lead criado automaticamente
| campo | valor |
|-------|-------|
| id | `24c2d895-3150-4d60-b4d0-d4c875ed9a1d` |
| name | **"Supervisor Operacional Conecta Mais"** (nome do perfil do WhatsApp, capturado) |
| phone | 928…6006 (11 díg, normalizado) |
| email | *(vazio/NULL — leads de WhatsApp sem email)* |
| source | **whatsapp** |
| status | new |

## 3. O que ficou comprovado
- ✅ **Webhook do Chatwoot** configurado e entregando (validação por token na URL ativa).
- ✅ **Log entrada + saída** em `cwi_message_log`.
- ✅ **Criação de Lead** na entrada, com **nome do perfil** do WhatsApp e `email=NULL`.
- ✅ **Dedup:** 2 mensagens de entrada → **1 único Lead** (a 2ª achou o da 1ª).
- ✅ **Extração defensiva** do payload do Chatwoot acertou todos os campos (`sender.phone_number`, `sender.name`, `conversation.id`, `id`, `content`, `message_type`).
- ✅ Migrations `sprint90`/`sprint91`, `email` nullable, `LeadSource.WHATSAPP`, fix do score — tudo em produção, sem regressão.

## 4. Estado: Fase 2 (entrada) CONCLUÍDA e VALIDADA EM PRODUÇÃO
O ciclo completo de WhatsApp está no ar:
- **Saída** (Fase 1): backend envia via Chatwoot/Baileys.
- **Entrada** (Fase 2): Chatwoot → webhook → log + captura de Lead no CRM.

## 5. Melhorias futuras (PROPOSTAS — não feitas)
1. **Anexos/mídia:** mensagens com imagem/áudio/documento chegam com `content` vazio e um array `attachments` no payload. Hoje o webhook só registra texto; logar tipo/URL do anexo seria um plus.
2. **Mais campos no Lead:** poderia preencher `notes` com a 1ª mensagem, ou vincular a conversa do Chatwoot ao Lead.
3. **Match com cliente:** hoje só casa com `leads.phone` (clients sem telefone). Popular `clients.phone/whatsapp` habilitaria reconhecer cliente existente em vez de criar Lead.
4. **Segurança:** trocar o segredo do webhook para um valor exclusivo (hoje reusa `WHATSAPP_WEBHOOK_SECRET` do `.env`) — opcional.

## 6. Lembrete de fragilidade (já mapeado)
- A imagem `conecta-pro-backend` é de 30/mai; o container roda muito código via `docker cp` (incluindo o webhook). **Recriar o backend reverteria tudo.** Reconstruir a imagem com o código baked elimina esse risco.

---
*Read-only nesta validação (apenas SELECTs). O fluxo foi exercitado por uma mensagem real de WhatsApp enviada pelo Jordan. Número mascarado.*
