# Por que a criação do canal WhatsApp (Baileys) falha — diagnóstico (READ-ONLY)

- **Data:** 2026-06-05 ~16:40 UTC
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Sintoma:** Ao clicar para criar a caixa de entrada "WhatsApp 0800 - Atendimento" (provider Baileys) no Chatwoot, o canal **não é criado** (`inboxes=0`, `channel_whatsapp=0`, Redis db4 vazio).
- **Veredito:** 🔴 **Erro de configuração — a integração Baileys ↔ Chatwoot nunca foi totalmente conectada.** Dois bloqueios: (1) nome de variável errado no Chatwoot e (2) API key não alinhada com a baileys-api.

---

## 1. O erro real (do log da web fazerai)

A cada tentativa de criar o inbox:
```
Errno::ECONNREFUSED (Failed to open TCP connection to :80 (Connection refused - connect(2) for nil port 80))
app/services/whatsapp/providers/whatsapp_baileys_service.rb:292  validate_provider_config?
app/models/channel/whatsapp.rb:309                               validate_provider_config
→ errors.add(:provider_config, 'Invalid Credentials')
```
O Chatwoot tenta validar o provider conectando a uma **URL vazia** (host `nil`, porta cai para 80) → recusa → o inbox **não é salvo**. Você está na instância certa (fazerai); o problema não é a UI, é a config.

---

## 2. Causa-raiz #1 — nome de variável errado no Chatwoot

O código da baileys (no container `chatwoot-fazerai`) resolve a URL assim:
```ruby
DEFAULT_URL     = ENV.fetch('BAILEYS_PROVIDER_DEFAULT_URL', nil)        # linha 10
DEFAULT_API_KEY = ENV.fetch('BAILEYS_PROVIDER_DEFAULT_API_KEY', nil)    # linha 11
def provider_url
  whatsapp_channel.provider_config['provider_url'].presence || DEFAULT_URL   # linha 493
end
```
Mas o que está setado no container é:
```
BAILEYS_PROVIDER_URL = http://baileys-api:3025      ← nome ERRADO (falta o _DEFAULT_)
(não existe BAILEYS_PROVIDER_DEFAULT_URL nem BAILEYS_PROVIDER_DEFAULT_API_KEY)
```
Resultado: `DEFAULT_URL = nil`. Como o **campo "provider_url" do formulário também ficou vazio**, `provider_url` resolve para vazio → `GET ""/status/auth` → `:80 nil` → `ECONNREFUSED`.

> A URL `http://baileys-api:3025` em si está **correta** (os dois containers estão na mesma rede `chatwoot-fazerai-net`); só está gravada com o **nome de variável que o código não lê**.

---

## 3. Causa-raiz #2 — API key não alinhada

A `baileys-api` **exige** autenticação:
```
GET http://baileys-api:3025/status/auth   (sem key)  → 401 {"error":"Unauthorized","message":"Valid API key required"}
```
Mas:
- A `baileys-api` **não tem nenhuma variável de API key** no ambiente (só `REDIS_URL`, `LOG_LEVEL`, `LD_PRELOAD`).
- O `chatwoot-fazerai` **não tem `BAILEYS_PROVIDER_DEFAULT_API_KEY`**.

Ou seja, mesmo corrigindo a URL, a validação `…/status/auth` voltaria **401** por falta de uma chave compartilhada idêntica nos dois lados. A integração foi subida mas **nunca teve a API key configurada** — coerente com a instância estar vazia e nunca ter pareado.

---

## 4. Confirmações de apoio (read-only)
- `provider_url`/`api_key` vêm de `provider_config['provider_url']` / `['api_key']` (formulário) **ou** das constantes `DEFAULT_*` (env). Ambos vazios hoje.
- Redes: `chatwoot-fazerai` e `baileys-api` ambos em `chatwoot-fazerai-net` → conectividade OK (não é problema de rede).
- baileys-api viva e saudável (`/status` 200, v3.1.5); só rejeita por falta de key.
- Chatwoot antigo (`chatwoot_production`) tem 1 inbox legado (não-WhatsApp) — não é onde você está.

---

## 5. Como corrigir (PROPOSTAS — nada executado)

**Opção A — rápida, pela própria tela (sem mexer em infra):**
No formulário de criação do inbox Baileys, **preencher manualmente** os campos avançados:
- **provider_url:** `http://baileys-api:3025`
- **api_key:** a chave que a baileys-api aceita (ver ressalva abaixo).
Isso popula `provider_config` e contorna o `DEFAULT_URL` vazio.

**Opção B — correta/definitiva (config de infra, exige recriar o container do Chatwoot):**
Definir no `chatwoot-fazerai` os nomes que o código realmente lê:
```
BAILEYS_PROVIDER_DEFAULT_URL=http://baileys-api:3025
BAILEYS_PROVIDER_DEFAULT_API_KEY=<chave>
```
(remover/!substituir o atual `BAILEYS_PROVIDER_URL`, que não é usado).

**Pré-requisito comum às duas opções — definir e alinhar a API key:**
A `baileys-api` exige `x-api-key`, mas hoje não há chave configurada em nenhum dos lados. É preciso:
1. Descobrir/definir o nome da var de API key que a imagem `fazer-ai/baileys-api` espera (ex.: `API_KEY`) e setá-la na `baileys-api`;
2. Usar **exatamente a mesma** chave no Chatwoot (campo `api_key` da Opção A ou `BAILEYS_PROVIDER_DEFAULT_API_KEY` da Opção B).
> Sem essa chave compartilhada, o `…/status/auth` continua retornando 401 e o canal não cria.

**Antes de tudo — decisão de negócio:**
- Confirmar se o canal de WhatsApp oficial é **Baileys** (via Chatwoot) ou **Evolution API** (o `backend/.env` aponta para Evolution). Hoje há os dois caminhos de pé; convém escolher um para não manter integrações concorrentes.

---

## 6. Próximo passo sugerido (read-only)
Posso investigar (sem alterar) **qual API key a `fazer-ai/baileys-api` espera** (config/secret/Redis) e qual o nome de env correto, para que a correção (Opção A ou B) saia certa de primeira. É só pedir.

---
*Read-only: leitura de log (arquivo), `env`, código-fonte no container e `GET /status/auth`. Nenhuma sessão iniciada; nenhum container/banco/env/config alterado.*
