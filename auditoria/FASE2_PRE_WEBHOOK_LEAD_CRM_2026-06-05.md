# Fase 2-pré — Mapa: webhook de entrada + modelo Lead/CRM (READ-ONLY)

- **Data:** 2026-06-05 ~21:12 UTC
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Mapear o que existe para construir o fluxo de ENTRADA (Chatwoot → backend → Lead/CRM + log de mensagens).
- **Resultado:** Nada de webhook inbound existe ainda; modelos Lead/Client mapeados; tabela de log a criar.

---

## 1. Webhook de entrada — NÃO existe
Não há endpoint que receba eventos do Chatwoot/WhatsApp. Os "webhook" encontrados são de outros domínios (REP/ponto, payroll, scheduled reports).
- **Referência de padrão** para criar: `modules/hr/rep_integration/controllers/webhook_controller.py`.
- **Segredo disponível** para validar assinatura: `WHATSAPP_WEBHOOK_SECRET` (já no `.env`).
- **A construir:** `POST` (ex.: `/api/v1/integrations/chatwoot/webhook`) que recebe `message_created`/`conversation_created` do Chatwoot e processa as **mensagens de entrada**.

## 2. Modelo Lead — `modules/crm/models/lead.py`
- `__tablename__ = "leads"`; enums `LeadStatus` (29) e `LeadSource` (41).
- **`LeadSource`**: `website, referral, social_media, cold_call, email_campaign, event, partner, other` — **não há `whatsapp`** → adicionar `WHATSAPP = "whatsapp"` (é `StrEnum` armazenado como string; provável sem migration de enum no DB, confirmar tipo da coluna).
- Campo `phone` (max 20, com `validate_phone`); `assigned_to` → User.
- Schemas: `modules/crm/schemas/lead.py` (LeadBase/Create/Update).

## 3. Cruzar número → cliente/contato
| Fonte | Campos de telefone |
|-------|--------------------|
| `modules/clients/models/client.py` (`clients`) | `phone`, `whatsapp`, `financial_contact_phone`, `technical_contact_phone` |
| `client_contacts` (via `crm/controllers/contact_controller.py`) | `phone`, `whatsapp` (ligado a `client_id`) |
| `leads` | `phone` |
| Oportunidades (`opportunity_repository`) | `contact_phone` |

**Estratégia de match (proposta):** normalizar o número recebido (E.164/dígitos) e procurar, em ordem: `clients.whatsapp` → `clients.phone` → `client_contacts.whatsapp/phone` → `leads.phone`. Se achar → vincular a mensagem ao cliente/lead. Se **não** achar → **criar Lead** (`source=whatsapp`, status inicial, `phone`).

## 4. Tabela de log de mensagens — NÃO existe
- `cwi_message_log` → **NÃO EXISTE** no banco `conecta_pro`.
- **A criar** (alembic): registrar entrada/saída — sugestão de colunas: `id, direction(in/out), phone, chatwoot_conversation_id, chatwoot_message_id, content, client_id (nullable), lead_id (nullable), status, created_at`. Índice por `phone` e `chatwoot_message_id` (idempotência do webhook).

## 5. Migrations (alembic)
- Pasta: `alembic/versions/`; última: `sprint89_inter_kit_fk.py` (2026-05-06).
- Próxima seria **sprint90** para criar `cwi_message_log` (+ eventual ajuste do enum LeadSource se for enum nativo do PG).

---

## 6. Esboço do fluxo de entrada (PROPOSTA — nada implementado)
1. **Chatwoot** dispara webhook em `message_created` (mensagem `incoming`) → `POST /api/v1/integrations/chatwoot/webhook` (valida assinatura).
2. Backend extrai `phone`, `conversation_id`, `message_id`, `content`.
3. **Idempotência**: se `chatwoot_message_id` já está em `cwi_message_log` → ignora.
4. **Match** número → cliente/contato/lead (§3). Sem match → cria Lead (`source=whatsapp`).
5. Grava em `cwi_message_log` (vinculado a client_id/lead_id).
6. (Opcional) cria uma **atividade/contato** no CRM (`client_contacts` activity `type=whatsapp`) ou nota no lead.

### Pré-requisitos / decisões
- Onde montar o router: módulo `integrations` (junto do `connectors/whatsapp`) — fora das zonas proibidas.
- Configurar no **Chatwoot** um Webhook/Automation apontando para o backend (`http://conecta-pro-backend:8080/...` — rede já conectada nos dois sentidos).
- Definir política: toda mensagem de entrada vira Lead, ou só de números desconhecidos?
- Decidir se loga **saída** também (as que o backend envia) para histórico unificado.

---
*Read-only: `grep`/leitura de modelos + `psql` (to_regclass). Nada criado/alterado.*
