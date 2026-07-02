# Mapa das rotas de saída WhatsApp no backend — Fase 1-pré (READ-ONLY)

- **Data:** 2026-06-05 ~18:00 UTC
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Mapear todo o código de envio (saída) de WhatsApp acoplado ao Evolution, para planejar a migração para Baileys/Chatwoot.
- **Drift:** ✅ **host == container** (md5 idêntico em `service.py`) — o código do host reflete o que roda; o plano pode mirar os arquivos do host (com `docker cp` no deploy, conforme padrão do projeto).

---

## 1. Chokepoint principal (Evolution-coupled)

**`modules/integrations/connectors/whatsapp/service.py`** — classe `WhatsAppService`:
```python
self.base_url = EVOLUTION_API_URL           # default https://api.evolution.app.br
self.api_key  = EVOLUTION_API_KEY
self.instance = WHATSAPP_INSTANCE_ID         # "conecta-pro"
# _send_message():
url = f"{self.base_url}/message/sendText/{self.instance}"
headers = {"apikey": self.api_key}
POST url (aiohttp)
```
- **Tudo passa por `_send_message`** → é o ponto único onde repontar para o Chatwoot/Baileys migra todos os envios de uma vez.
- Métodos de alto nível (as "rotas de saída"): `send_kit_notification`, `send_certificate_alert`, `send_nfse_notification`, `send_custom`, `check_status` (este usa `/instance/fetchInstances`, específico do Evolution).

### Endpoints HTTP expostos — `connectors/whatsapp/controller.py`
| Rota | Método |
|------|--------|
| `GET /status` | check_status (Evolution fetchInstances) |
| `POST /send/kit-notification` | send_kit_notification |
| `POST /send/certificate-alert` | send_certificate_alert |
| `POST /send/nfse-notification` | send_nfse_notification |
| `POST /send/custom` | send_custom |

---

## 2. Emissores SEPARADOS (também acoplados ao Evolution) — precisam migrar à parte

| Local | O que é |
|-------|---------|
| `modules/operacional/diaristas/services/notificacao_service.py` (`_enviar_whatsapp`, linha 449; chamado na 388) | **Sender duplicado** próprio, fala direto com `EVOLUTION_API_URL` |
| `modules/client_portal/controllers/whatsapp_controller.py` | Controller separado que usa `EVOLUTION_API_URL` |
| `modules/integrations/whatsapp/services/whatsapp_service.py` (2ª classe `WhatsAppService`, linha 131) | **2ª implementação** (config-driven via `WhatsAppConfig`/`WhatsAppProvider`); não chama Evolution direto no grep — provável camada "provider-aware" (bom candidato para receber um provider Baileys/Chatwoot) |

> ⚠️ **Duplicação:** existem ao menos **3 caminhos de envio** (connectors service, diaristas, client_portal) + 1 serviço alternativo. A migração ideal consolida tudo em **um único cliente** apontando para Chatwoot/Baileys.

---

## 3. Zonas proibidas — limpas ✅
`financial/`, `fiscal_contabil/`, `government_integrations/` → **nenhuma chamada de envio** (`sendText`/`_send_message`/`EVOLUTION_API_URL`). Só há **flags** `notify_whatsapp` (coluna em `financial/models/customer.py`, schemas em `receivable.py`) — não é lógica de envio. **A migração não toca essas zonas.**

## 4. Entrada (webhook) — observação
- O fluxo de **entrada** hoje é via **Chatwoot ↔ Baileys** (já validado), não pelo backend.
- O backend tem webhooks genéricos (`WHATSAPP_WEBHOOK_SECRET`), mas o recebimento operacional de mensagens vive no Chatwoot. A migração de saída do backend deve decidir se passa a **postar no Chatwoot** (cria mensagem na conversa) ou fala **direto com a baileys-api**.

---

## 5. Implicação para o plano de migração (Fase 1) — PROPOSTA
1. **Repontar o chokepoint** `connectors/whatsapp/service.py::_send_message` para Chatwoot/Baileys em vez de `EVOLUTION sendText`:
   - **Opção Chatwoot (recomendada):** POST `/{account}/conversations/{id}/messages` (ou criar conversa por número) — mantém tudo no Chatwoot (histórico, agentes). Exige token de API do Chatwoot.
   - **Opção Baileys direto:** POST `http://baileys-api:3025/connections/+558008804414/...` com `x-api-key` — mais baixo nível, sem histórico no Chatwoot.
2. **Consolidar** os senders duplicados (`diaristas`, `client_portal`) para usar o mesmo cliente.
3. **`check_status`**: trocar `fetchInstances` (Evolution) por um health do Baileys (`/status/auth`) ou do Chatwoot.
4. **Sem mudança nas zonas proibidas**; sem mudança de URLs de API expostas (os endpoints `/send/*` continuam, só muda o backend de transporte).
5. **Deploy:** como o código é baked, aplicar via `docker cp` + restart (padrão do projeto) — e validar que `WHATSAPP_API_ENABLED` volte a `true` apontando para o novo transporte.

---

## 6. Resumo (as "rotas de saída")
- **5 endpoints** no controller principal (`/status`, `/send/kit-notification`, `/send/certificate-alert`, `/send/nfse-notification`, `/send/custom`).
- **+ senders separados**: `diaristas` (`_enviar_whatsapp`) e `client_portal/whatsapp_controller`.
- **+ 1 serviço alternativo** (`integrations/whatsapp/services/whatsapp_service.py`).
- Total prático a migrar: **o chokepoint `_send_message` + 2 senders duplicados + 1 serviço** = a superfície completa de saída.

---
*Read-only: apenas `grep`/`md5sum`/leitura de código (host e container). Nenhum arquivo, container ou config alterado.*
