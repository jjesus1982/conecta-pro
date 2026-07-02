# Fase 1.1 — Passo B: código de migração pronto + validação da API (READ-ONLY até aqui)

- **Data:** 2026-06-05 ~19:48 UTC
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Reescrever o chokepoint de envio WhatsApp do backend (Evolution → Chatwoot/Baileys).
- **Status:** ✅ **Fluxo validado com envio REAL** + ✅ **código novo escrito e com sintaxe OK**. ⏸️ **Deploy aguardando seu OK** (envolve restart do backend).

---

## 1. Validação do fluxo (envio real, provado)
A partir do `conecta-pro-backend`, com o token do bot (user 2):
- `GET /conversations` → **200** (auth + rede OK).
- 1ª tentativa de envio → **401** (bot não era membro do inbox) → **corrigido**: bot adicionado ao **inbox 1** (`InboxMember`).
- Envio na conversa 1 → **200**, `msg_id=10`, `message_type=outgoing`, `status=sent`.
- Confirmação no banco: **msg 10 com `source_id` (Baileys) e `status=read`** → chegou no seu WhatsApp e foi **lida**.

### Formatos da API capturados (para código fiel)
- Criar contato existente → **422** (precisa cair para busca).
- `GET /contacts/search?q=<fone>` → 200, `payload[0].id`.
- `GET /contacts/{id}/contactable_inboxes` → 200, lista com `inbox.id` + `source_id`.
- `POST /conversations {source_id, inbox_id, contact_id}` → `id`.
- `POST /conversations/{id}/messages {content, message_type:"outgoing"}` → envia.

## 2. Código novo (pronto, ainda NÃO no ar)
Arquivo de revisão: `modules/integrations/connectors/whatsapp/service.py.chatwoot-new` (sintaxe OK).
- **`__init__`**: lê `CHATWOOT_BASE_URL` (default `http://chatwoot-fazerai:3000`), `CHATWOOT_ACCOUNT_ID=1`, `CHATWOOT_INBOX_ID=1`, token de `CHATWOOT_API_TOKEN` **ou** do arquivo `/app/.chatwoot_token`. `enabled` segue de `WHATSAPP_API_ENABLED`.
- **`_send_message`**: fluxo contato→conversa→mensagem (com fallback de busca no 422).
- **`check_status`**: passa a checar a API do Chatwoot.
- **Senders inalterados**: `send_kit_notification`, `send_certificate_alert`, `send_nfse_notification`, `send_custom` (mesmas assinaturas) — **URLs de API `/send/*` continuam idênticas**.
- **Sem env nova obrigatória** (defaults + token em arquivo) → permite deploy por `docker cp` + `docker restart`, **sem recriar** o backend (evita reverter código).
- Backup do original: `service.py.bak-evolution-20260605_194835`.

## 3. Plano de deploy (PROPOSTA — aguardando OK)
```
# 1. token em arquivo no container (legivel pelo app)
docker cp <tokenfile> conecta-pro-backend:/app/.chatwoot_token
docker exec -u 0 conecta-pro-backend chmod 644 /app/.chatwoot_token
# 2. codigo novo
docker cp service.py.chatwoot-new conecta-pro-backend:/app/modules/integrations/connectors/whatsapp/service.py
# 3. restart (≈30-60s downtime da API do ERP)
docker restart conecta-pro-backend
# 4. teste real: whatsapp_service.send_custom(<seu numero>, "teste") via o codigo novo
```

## 4. ⚠️ Decisões necessárias
1. **Restart do backend** = breve downtime da API do ERP (`:8080`). Quando? (agora / horário combinado)
2. **Escopo:** os **8 celery workers** (que rodam as notificações agendadas de kit/certidão/NFS-e) e os **2 senders duplicados** (`diaristas`, `client_portal`) ainda usam o código Evolution antigo — que agora aponta para um serviço **removido**, então **falham**. Opções:
   - **(a)** Migrar **só o backend** agora (cobre os endpoints HTTP `/send/*`), workers depois.
   - **(b)** Migrar **backend + 8 workers** na mesma janela (cp+restart em todos) — migração completa do `connectors/whatsapp`.
   - **(c)** Migrar tudo + consolidar os 2 senders duplicados (mais trabalho, elimina a duplicação).
3. **Persistir env** (`CHATWOOT_*`) e a **rede no compose** no próximo restart planejado (para sobreviver a um `compose recreate`).

## 5. Pendências já mapeadas
- Rede backend↔chatwoot: **resolvida a quente** (não persistida no compose ainda).
- Bot + inbox membership: **OK**.
- SMTP do Chatwoot quebrado (à parte) — ver `CHATWOOT_EMAIL_SMTP_2026-06-05.md`.

---
*Até aqui: validação read-only + envios de teste para o SEU número + adição do bot ao inbox + escrita do código em arquivo de revisão. O `service.py` em produção NÃO foi alterado. Deploy aguarda aprovação.*
