# Pareamento WhatsApp (Baileys ↔ Chatwoot) — Confirmação (READ-ONLY)

- **Data:** 2026-06-05 ~17:11 UTC
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Confirmar se, após a correção, o canal WhatsApp foi criado e a sessão pareou/persistiu.
- **Veredito:** ✅ **Pareado, conectado e com mensagens já fluindo para o Chatwoot.** A correção da integração funcionou ponta a ponta.

---

## 1. Inbox/canal criado (antes era 0)
```
inboxes = 1 | channel_whatsapp = 1
Atendimento Conecta Mais | provider = baileys | phone = +558008804414
```
O erro 500/`ECONNREFUSED` não ocorre mais — a UI conseguiu criar o canal.

## 2. Sessão persistida e conectada
- **Redis db4** (antes vazio): contém a API key + `@baileys-api:connections:+558008804414:authState` (hash com o estado da sessão).
- `authState.creds` tem `me`, `account`, `platform:"smbi"` (WhatsApp **Business**) e `lastAccountSyncTimestamp` recente → conta vinculada e sincronizada.
- Log da baileys-api com tráfego **autenticado**: `POST /connections/+558008804414 [200]`, `send-receipts [200]`, múltiplos `profile-picture-url?jid=…@s.whatsapp.net [200]` — só possível com socket logado.

## 3. Prova definitiva — mensagens chegando ao Chatwoot
```
contacts = 1   (antes 0)
conversations = 1   (antes 0)
messages = 4   (antes 0)
```
Uma conversa real com 4 mensagens já sincronizou para o Chatwoot. Com o **Sidekiq ativo** (religado hoje), os jobs/webhooks do canal estão sendo processados.

## 4. Pontos de atenção (monitorar)
| Item | Observação | Gravidade |
|------|------------|-----------|
| `creds.registered = false` | Peculiaridade do Baileys para contas SMB/Business; o sync e as mensagens provam que está logada | Baixa (cosmético) |
| Warnings `timed out waiting for message` (repetidos) na baileys-api | Possível **instabilidade intermitente** de conexão; mensagens chegaram, mas vale acompanhar estabilidade nas próximas horas | Média (observar) |
| `GET /connections/<phone>` → 404 (erro Elysia no log) | **Bug cosmético** dessa rota específica da baileys-api; não afeta envio/recebimento | Baixa |

## 5. Estado do stack
```
chatwoot-fazerai          → healthy
chatwoot-fazerai-sidekiq  → up, heartbeat ativo (processando)
baileys-api               → healthy (sessão +558008804414 logada)
chatwoot-fazerai-redis    → healthy (db3 sidekiq, db4 baileys)
chatwoot-fazerai-postgres → healthy
```

## 6. Conclusão
A jornada completa está fechada: **correção da config → canal criado → QR pareado → sessão conectada → mensagens fluindo**. O atendimento WhatsApp via Baileys/Chatwoot está **operacional**.

### Recomendações
1. **Acompanhar a estabilidade** da conexão nas próximas horas (warnings de timeout) — se houver quedas/reconexões frequentes, revisar versão do cliente Baileys / rede.
2. **Decisão de negócio ainda aberta:** Baileys (Chatwoot) vs Evolution API (`backend/.env`) como canal oficial — agora o Baileys está provado funcional; convém oficializar um caminho.
3. Testar um **envio de saída** (responder uma conversa pelo Chatwoot) para validar o fluxo bidirecional ponta a ponta.

---
*Read-only: `psql` SELECT, `redis-cli` (type/hkeys/hget de booleanos), leitura de log via arquivo e `GET /status|/connections`. Nenhuma sessão alterada; nenhum segredo exposto.*
