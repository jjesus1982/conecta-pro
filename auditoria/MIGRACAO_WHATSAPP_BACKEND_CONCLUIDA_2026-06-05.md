# Migração WhatsApp do backend: Evolution → Chatwoot/Baileys — CONCLUÍDA

- **Data:** 2026-06-05 ~20:00 UTC
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Migrar o envio de WhatsApp do backend (Evolution API, removida) para o Chatwoot/Baileys.
- **Resultado:** ✅ **Concluída, testada com envio real e persistida no compose.**
- **Autorização:** deploy aprovado (backend + workers, agora).

---

## 1. O que foi feito
1. **Rede** (a quente, sem recriar): `conecta-pro-backend` + 8 workers conectados à `chatwoot-fazerai-net`.
2. **Bot** `noreply@conectamais.pro` (user 2) confirmado + **adicionado como membro do inbox 1** (necessário para enviar).
3. **Código reescrito** (`connectors/whatsapp/service.py`): `_send_message` e `check_status` agora falam com a **Application API do Chatwoot** (contato → conversa → mensagem). Os 4 senders de alto nível e os endpoints `/send/*` ficaram **idênticos**.
4. **Deploy** via `docker cp` + `docker restart` (padrão do projeto, **sem recriar** → sem risco de reverter código) em **9 containers** (backend + celery batch/beat/nfse/sefaz/integrations/operacional/priority + flower). Token entregue em `/app/.chatwoot_token` (modo 644).
5. **Config persistida** (compose + `.env`) para sobreviver a um `compose up`:
   - `WHATSAPP_API_ENABLED=true`, `CHATWOOT_BASE_URL=http://chatwoot-fazerai:3000`, `CHATWOOT_ACCOUNT_ID=1`, `CHATWOOT_INBOX_ID=1`, `CHATWOOT_API_TOKEN=…`
   - Rede `chatwoot-fazerai-net` adicionada ao serviço backend + declarada `external: true`.
   - `docker compose config` → **YAML válido**, **0 refs a evolution**.

## 2. Prova de funcionamento (envio real)
- Teste via API do Chatwoot a partir do backend → `msg_id=10`, `status=sent`, depois **`read`** no seu WhatsApp.
- Teste pelo **código novo já em produção** (`whatsapp_service.send_custom`) → `{'status':'sent','conversation_id':4,'message_id':13}`; **msg 13 entregue pelo Baileys** (`status=delivered`).
- CONFIG do serviço no backend: `base=http://chatwoot-fazerai:3000 inbox=1 enabled=True has_token=True`.

## 3. Esclarecimento importante (sem regressão nos workers)
- O **único chamador** de `whatsapp_service.send_*` é o `controller.py` (endpoints HTTP, servidos pelo **backend**). **Nenhum task de celery** chama esses senders.
- Os workers têm `WHATSAPP_API_ENABLED` **não definida** (sempre foi assim — não mexi no env deles). O deploy do código neles foi **redundante e inócuo**.
- Portanto a migração desse serviço está **funcionalmente completa só com o backend**.

## 4. Estado final
```
conecta-pro-backend  → healthy, enviando via Chatwoot/Baileys ✅
8 workers            → running (código novo presente, mas não chamam este serviço)
baileys-api          → healthy (sessão +558008804414)
chatwoot-fazerai     → healthy (Sidekiq processando)
Evolution            → removido (sessão anterior)
```

## 5. Backups / rollback
- `service.py.bak-evolution-20260605_194835` (código original).
- `docker-compose.yml.bak-rmevolution-20260605_174638`, `.env.bak-rmevolution-…`, `backend/.env.bak-rmevolution-…`.
- Reverter código: `docker cp service.py.bak-evolution-... <container>:/app/.../service.py && docker restart <container>`.

## 6. Pendências (ainda abertas — PROPOSTAS)
1. **Senders duplicados NÃO migrados** — `operacional/diaristas/services/notificacao_service.py` (`_enviar_whatsapp`) e `client_portal/controllers/whatsapp_controller.py` ainda chamam o Evolution direto → **falham** (Evolution removido). Migrar/consolidar se forem usados.
2. **2º `WhatsAppService`** em `integrations/whatsapp/services/whatsapp_service.py` (config-driven) — avaliar se está em uso.
3. **SMTP do Chatwoot quebrado** (e-mail) — à parte (ver `CHATWOOT_EMAIL_SMTP_2026-06-05.md`).
4. **Estabilidade do Baileys** — acompanhar os warnings `timed out waiting for message`.

---
*Mudanças aplicadas: rede (runtime + compose), bot/inbox membership, reescrita do service.py + deploy por docker cp/restart em 9 containers, edição de compose e 2 `.env`. Backend não recriado. Token não exposto. Envio validado ponta a ponta.*
