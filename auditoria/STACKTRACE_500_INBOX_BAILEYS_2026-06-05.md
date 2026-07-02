# Stack trace do erro 500 ao criar inbox Baileys (READ-ONLY)

- **Data:** 2026-06-05 ~16:45 UTC
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Capturar o stack trace do `500 Internal Server Error` no POST de criação do inbox WhatsApp/Baileys.
- **Veredito:** 🔴 Confirma a causa-raiz já mapeada — `validate_provider_config?` conecta a uma **URL vazia** → `ECONNREFUSED` → 500.

> Nota: `docker logs chatwoot-fazerai` trava (driver de log); o trace foi lido direto do arquivo `-json.log`.

---

## 1. Sequência da requisição (do log da web fazerai)

```
Started POST "/api/v1/accounts/1/inboxes" for 45.236.8.40 at 2026-06-05 16:37:57 +0000
Processing by Api::V1::Accounts::InboxesController#create as JSON
Parameters: {"name" => "WhatsApp 0800 - Atendimento", "channel" => {"type" => "whatsapp", "phone_n…}}
Completed 500 Internal Server Error in 221ms (ActiveRecord: 7.0ms)
```

## 2. Stack trace (exceção)

```
Errno::ECONNREFUSED (Failed to open TCP connection to :80
                    (Connection refused - connect(2) for nil port 80)):

app/services/whatsapp/providers/whatsapp_baileys_service.rb:292
    in 'Whatsapp::Providers::WhatsappBaileysService#validate_provider_config?'
app/controllers/api/v1/accounts/inboxes_controller.rb:158
    in 'Api::V1::Accounts::InboxesController#create_channel'
app/controllers/api/v1/accounts/inboxes_controller.rb:37
    in 'block in Api::V1::Accounts::InboxesController#create'
app/controllers/api/v1/accounts/inboxes_controller.rb:36
    in 'Api::V1::Accounts::InboxesController#create'
app/controllers/concerns/request_exception_handler.rb:11
    in 'RequestExceptionHandler#handle_with_exception'
```

Repetido em **todas** as tentativas (16:37:57, 16:38:21, 16:39:28, 16:40:05 — origem IP `45.236.8.40`), sempre `Completed 500` em 71–221ms.

---

## 3. Leitura do trace

- A linha que estoura é `whatsapp_baileys_service.rb:292` → `validate_provider_config?`, que faz `HTTParty.get("#{provider_url}/status/auth", …)`.
- `provider_url` está **vazio** em runtime → o `HTTParty` tenta abrir `:80` com host `nil` → `Errno::ECONNREFUSED`.
- Como a exceção sobe pelo `create_channel` → `create` e cai no `RequestExceptionHandler`, o resultado vira **HTTP 500** (não uma validação amigável). Por isso o inbox não é criado e a tela mostra erro genérico.

### Por que `provider_url` está vazio (causa-raiz, já detalhada no relatório anterior)
```ruby
DEFAULT_URL = ENV.fetch('BAILEYS_PROVIDER_DEFAULT_URL', nil)   # ← código lê este nome
def provider_url
  whatsapp_channel.provider_config['provider_url'].presence || DEFAULT_URL
end
```
- Env presente no container: `BAILEYS_PROVIDER_URL=http://baileys-api:3025` → **nome errado** (falta `_DEFAULT_`).
- Logo `DEFAULT_URL = nil`; campo `provider_url` do formulário também vazio → `provider_url` = vazio → 500.
- Bloqueio secundário: a `baileys-api` exige `x-api-key` (401 sem ela) e **não há chave configurada** em nenhum dos lados.

---

## 4. Correção (PROPOSTA — nada executado)
Igual ao relatório `FALHA_CRIAR_CANAL_BAILEYS_2026-06-05.md`:
1. **Definitiva (infra):** no `chatwoot-fazerai`, trocar `BAILEYS_PROVIDER_URL` por **`BAILEYS_PROVIDER_DEFAULT_URL=http://baileys-api:3025`** e adicionar **`BAILEYS_PROVIDER_DEFAULT_API_KEY=<chave>`** → recriar o container.
2. **Rápida (UI):** preencher manualmente os campos `provider_url` e `api_key` no formulário do inbox.
3. **Pré-requisito:** definir e **alinhar a mesma API key** na `baileys-api` e no Chatwoot (hoje ausente nos dois).
4. **Decisão de negócio:** confirmar Baileys vs Evolution API como canal oficial.

---
*Read-only: leitura do log via arquivo. Nenhum container/banco/env/config alterado.*
