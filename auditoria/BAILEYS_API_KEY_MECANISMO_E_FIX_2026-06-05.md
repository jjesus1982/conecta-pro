# Baileys — mecanismo da API key e correção completa (READ-ONLY)

- **Data:** 2026-06-05 ~16:50 UTC
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Pergunta:** Qual o nome da variável de API key que a `baileys-api` espera?
- **Resposta curta:** 🔑 **Nenhuma.** A `baileys-api` **não usa env var para a API key** — as chaves são **provisionadas no Redis** via um script (`manage-api-keys.ts`). Hoje **não há nenhuma chave criada** → por isso responde `401` e o canal não cria.

---

## 1. Como a `baileys-api` valida a API key

Código em `/usr/src/app/src/middlewares/auth.ts`:
```js
export const REDIS_KEY_PREFIX = "@baileys-api:api-keys";
// no request: lê header "x-api-key" e checa a chave Redis:
const key = `${REDIS_KEY_PREFIX}:${apiKey}`;   // existe? → autorizado
const apiKeyHash = createHash("sha256").update(apiKey).digest("hex");
```
- Toda requisição precisa do header **`x-api-key: <chave>`**.
- A chave é válida se existir o registro Redis **`@baileys-api:api-keys:<chave>`** (no db4, `redis://chatwoot-fazerai-redis:6379/4`).
- **Não há env var de key.** `config.ts` reconhece só: `NODE_ENV, PORT, LOG_LEVEL, BAILEYS_*, REDIS_URL, REDIS_PASSWORD, WEBHOOK_*, CORS_ORIGIN, IGNORE_*, MEDIA_*` — **nenhuma** de API key.

## 2. Estado atual = nenhuma chave provisionada
```
redis db4 → keys "@baileys-api:api-keys:*"  →  (vazio)
GET /status/auth (sem key)                  →  401 "Valid API key required"
```
Logo, **não existe chave** para dar ao Chatwoot — e o Chatwoot também está com o nome de env errado (ver §4).

## 3. Como criar uma chave — script oficial `manage-api-keys.ts`
`/usr/src/app/scripts/manage-api-keys.ts` (atalho `bun scripts/manage-api-keys.ts`):
```
create [role] [key]   # role: user|admin; sem key → gera randomBytes(24) hex; grava no Redis
delete <apiKey>
list
```
`createApiKey` faz: `redis.set("@baileys-api:api-keys:<chave>", authData)`.

---

## 4. Os dois ajustes necessários (recap)
| # | Onde | Problema | Correção |
|---|------|----------|----------|
| 1 | `chatwoot-fazerai` (`/opt/chatwoot-fazerai/.env`) | usa `BAILEYS_PROVIDER_URL` (nome errado) → `DEFAULT_URL=nil` → 500 | renomear p/ `BAILEYS_PROVIDER_DEFAULT_URL=http://baileys-api:3025` |
| 2 | ambos os lados | nenhuma API key existe/compartilhada | criar chave no baileys-api **e** setar a mesma no Chatwoot (`BAILEYS_PROVIDER_DEFAULT_API_KEY`) |

Detalhe de infra: o `chatwoot-fazerai` usa **`env_file: .env`** (em `/opt/chatwoot-fazerai/.env`) — é ali que as vars devem ser ajustadas. Compose do stack: `/opt/chatwoot-fazerai/docker-compose.yml`.

---

## 5. Receita de correção (PROPOSTA — nada executado)

> Tudo abaixo são mudanças; deixo como proposta para sua aprovação.

**Passo 1 — criar a API key no baileys-api (grava no Redis db4):**
```bash
docker exec baileys-api bun scripts/manage-api-keys.ts create user
# saída: "Created API key with role 'user': <CHAVE_GERADA>"  ← anote a CHAVE
```
(conferir: `docker exec baileys-api bun scripts/manage-api-keys.ts list`)

**Passo 2 — apontar o Chatwoot para o baileys com a chave:**
Editar `/opt/chatwoot-fazerai/.env` (fazer backup antes):
```
# remover/!substituir:
# BAILEYS_PROVIDER_URL=http://baileys-api:3025
BAILEYS_PROVIDER_DEFAULT_URL=http://baileys-api:3025
BAILEYS_PROVIDER_DEFAULT_API_KEY=<CHAVE_GERADA do passo 1>
```

**Passo 3 — recriar só os serviços do Chatwoot (env_file exige recriar):**
```bash
cd /opt/chatwoot-fazerai
docker compose up -d --no-deps chatwoot-fazerai chatwoot-fazerai-sidekiq
```

**Passo 4 — criar o inbox WhatsApp (Baileys) na UI** → agora `validate_provider_config?` chama `GET http://baileys-api:3025/status/auth` com a key válida → **200** → inbox criado → **QR/código de pareamento** aparece.

**Alternativa sem mexer no .env (Opção UI):** no formulário do inbox, preencher `provider_url=http://baileys-api:3025` e `api_key=<CHAVE_GERADA>`. (Ainda exige o Passo 1 para a chave existir.)

---

## 6. Antes de aplicar — decisão de negócio
- Confirmar **Baileys (via Chatwoot) vs Evolution API** (no `backend/.env`) como canal oficial de WhatsApp — hoje os dois estão de pé. Definir um evita integrações concorrentes.
- A instância `chatwoot-fazerai` está vazia: validar que é a oficial a ser usada.

---
*Read-only: leitura de código (`auth.ts`, `config.ts`, `manage-api-keys.ts`), `env`, compose e `redis-cli keys`. Nenhuma chave criada, nenhum container/env/config alterado. Os comandos do §5 são propostas, não executados.*
