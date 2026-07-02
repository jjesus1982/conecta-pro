# Correção aplicada — Integração Baileys ↔ Chatwoot

- **Data:** 2026-06-05 ~17:01 UTC
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Ação:** Corrigir a config que impedia a criação do canal WhatsApp/Baileys (erro 500 `ECONNREFUSED`).
- **Resultado:** ✅ **Sucesso e provado.** Chatwoot agora autentica na baileys-api (HTTP 200). Pronto para criar o inbox e parear.
- **Autorização:** comandos enviados pelo administrador. Backup do `.env` feito antes.

---

## 1. O que estava quebrado (recap)
- Chatwoot tinha `BAILEYS_PROVIDER_URL` (nome errado) → o código lê `BAILEYS_PROVIDER_DEFAULT_URL` → URL vazia → `GET ""/status/auth` → `Errno::ECONNREFUSED` → **500** ao criar inbox.
- Nenhuma API key provisionada na baileys-api (que valida `x-api-key` contra o Redis db4) → 401.

## 2. O que foi feito

| # | Passo | Detalhe |
|---|-------|---------|
| 0 | Backup | `/opt/chatwoot-fazerai/.env.bak.20260605_165633` |
| 1 | Gerar API key | `docker exec baileys-api bun scripts/manage-api-keys.ts create user` → key role **user** (48 hex), gravada no Redis db4 (`@baileys-api:api-keys:…`) |
| 2 | Conferir no Redis | chave presente em `chatwoot-fazerai-redis` db4 |
| 3 | Corrigir `.env` | removido `BAILEYS_PROVIDER_URL`; adicionados `BAILEYS_PROVIDER_DEFAULT_URL=http://baileys-api:3025` e `BAILEYS_PROVIDER_DEFAULT_API_KEY=<key>` |
| 4 | Recriar serviços | `docker compose up -d --no-deps --force-recreate chatwoot-fazerai chatwoot-fazerai-sidekiq` |

> Role escolhida: **user** (suficiente). Verificado no código: `/status/auth` e `/connections/*` usam `authMiddleware` (qualquer key válida); `adminGuard` só protege rotas admin (ex.: logout-all), fora do fluxo do Chatwoot.

## 3. Prova real (pós-correção)

| Teste | Resultado | Significado |
|-------|-----------|-------------|
| `GET /status/auth` **com** key (de dentro do chatwoot) | **HTTP 200 "OK"** | Chatwoot alcança e autentica na baileys-api ✅ |
| `GET /status/auth` **sem** key (controle) | **HTTP 401** | autenticação está ativa e funcionando ✅ |
| `BAILEYS_PROVIDER_URL` no `.env` | **0 ocorrências** | nome errado removido ✅ |

O erro `ECONNREFUSED`/500 **não ocorre mais**.

## 4. Estado final do stack
```
chatwoot-fazerai          → Up (healthy)
chatwoot-fazerai-sidekiq  → Up (processo Sidekiq novo, heartbeat fresco ~4s → processando)
baileys-api               → Up 6 days (healthy)
chatwoot-fazerai-postgres → Up 6 days (healthy)
chatwoot-fazerai-redis    → Up 6 days (healthy)
```
- **Nota:** ao recriar, o `chatwoot-fazerai-sidekiq` voltou já com a config correta e heartbeat ativo (segue a política `restart: unless-stopped` aplicada hoje mais cedo).

## 5. Próximo passo (você, na UI)
1. Acessar `https://chat.conectamais.pro` → **Configurações → Caixas de entrada → Adicionar → WhatsApp → Baileys**.
2. Como os defaults agora estão no `.env`, a validação passa (200) e o canal é criado.
3. Aparece o **QR Code / código de pareamento** → escanear no celular (WhatsApp → Aparelhos conectados).
4. A sessão fica gravada no Redis db4; mensagens passam a fluir Baileys ↔ Chatwoot (Sidekiq ativo processa os jobs/webhooks).

## 6. Observações / pendências
- **Decisão de negócio ainda aberta:** Baileys (Chatwoot) **vs** Evolution API (`backend/.env`) como canal oficial de WhatsApp — os dois seguem de pé.
- **Persistir no compose:** as vars foram para o `.env` (que é `env_file` do compose) — já persistente. ✅
- **Backup do `.env`** preservado para rollback: restaurar `.env.bak.20260605_165633` e recriar os 2 serviços reverte a mudança.
- A API key tem role **user**; se no futuro precisar de operações admin (ex.: `logout-all` em massa), gerar uma key `admin` à parte.

---

## 7. Como reverter
```bash
cd /opt/chatwoot-fazerai
cp .env.bak.20260605_165633 .env
docker compose up -d --no-deps --force-recreate chatwoot-fazerai chatwoot-fazerai-sidekiq
# (opcional) revogar a key: docker exec baileys-api bun scripts/manage-api-keys.ts delete <key>
```

---
*Mudanças aplicadas: criação de 1 API key no baileys-api (Redis db4) + 2 linhas no `/opt/chatwoot-fazerai/.env` + recriação de 2 containers do stack Chatwoot. Nenhum outro serviço, rede, firewall ou SSH tocado. Key não exposta em texto puro.*
