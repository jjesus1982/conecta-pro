# Fase 2.1 — Migration `cwi_message_log` aplicada

- **Data:** 2026-06-05 ~21:57 UTC
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Criar a tabela de log de mensagens WhatsApp/Chatwoot (base da Fase 2 — atendimento/CRM).
- **Resultado:** ✅ **Aplicada com backup, sem drift.** DB no head `sprint90_cwi_message_log`.

---

## 1. Passos executados (na ordem)
1. **Backup do banco** `conecta_pro` (pg_dump -Fc) → `backups/fase2/conecta_pro_pre_sprint90_20260605_215643.dump` (3.8M).
2. `docker cp` da migration → container.
3. **`alembic heads` = 1 head só** (`sprint90_cwi_message_log`, sem branch) — confirmado antes do upgrade.
4. **`alembic upgrade head`** → `findp_b1b2_20260601 → sprint90_cwi_message_log`.
5. Verificação da tabela + `alembic current`.

## 2. Tabela criada — `cwi_message_log`
| Coluna | Tipo | Nullable | Default |
|--------|------|----------|---------|
| id | uuid | NOT NULL | gen_random_uuid() |
| direction | varchar(3) | NOT NULL | — (`in`/`out`) |
| phone_canonical | varchar(20) | NULL | — |
| chatwoot_conversation_id | integer | NULL | — |
| chatwoot_message_id | integer | NULL | — |
| content | text | NULL | — |
| client_id | uuid | NULL | — (sem FK) |
| lead_id | uuid | NULL | — (sem FK) |
| status | varchar(20) | NULL | — |
| created_at | timestamptz | NOT NULL | now() |

**Índices/constraints:**
- `cwi_message_log_pkey` (id)
- `uq_cwi_chatwoot_message_id` **UNIQUE** (idempotência do webhook)
- `ix_cwi_phone_canonical` (match por telefone)
- `ix_cwi_conversation` (histórico por conversa)

## 3. Decisões de design (consolidadas)
- **UUID** em `id`/`client_id`/`lead_id` (convenção da casa; `leads.id`/`clients.id` são UUID).
- **`phone_canonical` varchar(20)** = mesmo tipo de `leads.phone` (evita truncar landline).
- **Sem FK** em client_id/lead_id — escolha consciente: tabela de **LOG append-only nunca deve falhar** ao gravar por questão referencial.
- **`chatwoot_message_id` UNIQUE** com NULLs distintos (saídas ainda sem id não colidem).

## 4. Estado / rollback
- `alembic current` = **`sprint90_cwi_message_log (head)`**.
- Migration presente no **host e no container** (sem drift).
- **Reverter** (se necessário): `docker exec conecta-pro-backend sh -c 'cd /app && alembic downgrade -1'` (downgrade completo já implementado) ou restaurar o dump pré-migration.

## 5. Próximos passos da Fase 2 (PROPOSTA)
1. **Enum `LeadSource` + `WHATSAPP`** (só código, varchar — sem migration).
2. **Endpoint de webhook** (módulo `integrations`): recebe `message_created` do Chatwoot, valida assinatura, idempotência por `chatwoot_message_id`, normaliza telefone, match em `leads.phone` (cria Lead se não houver), grava em `cwi_message_log`.
3. Configurar o **Webhook/Automation no Chatwoot** apontando para `http://conecta-pro-backend:8080/...` (rede já conectada).
4. Decidir: logar só entrada ou entrada+saída; popular telefones de `clients` para match futuro.

---
*Mudança aplicada: 1 migration (CREATE TABLE + índices), com backup pré-migration. Nenhum dado existente tocado. Sem drift.*
