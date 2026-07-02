# Fase 2.2-pré — Padrão de webhook + restrição de email no Lead (READ-ONLY)

- **Data:** 2026-06-05 ~22:10 UTC
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Preparar o endpoint de webhook (entrada Chatwoot→backend) e resolver a criação de Lead.
- **Resultado:** Padrão de webhook mapeado; **bloqueio identificado**: `email` é obrigatório no Lead em 3 camadas.

---

## 1. Padrão de webhook da casa (a seguir) — `modules/hr/rep_integration/controllers/webhook_controller.py`
- `router = APIRouter(prefix="/webhook", tags=[...])`.
- `@router.post(...)` **sem JWT** (chamado por sistema externo).
- Lê `body = await request.body()`.
- **Valida HMAC SHA256:** `hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()` comparado ao header com `hmac.compare_digest(...)`.
- `db: AsyncSession = Depends(get_db)`.
- Erros: 404 (não encontrado), 400 (inativo), 401 (assinatura inválida). Parse JSON do body → lista de eventos.
- **Adaptação nossa:** validar contra `WHATSAPP_WEBHOOK_SECRET` (já no `.env`); receber `message_created` do Chatwoot.

## 2. Model Lead — restrição crítica
| Campo | Model SQLAlchemy | Schema Pydantic | Banco |
|-------|------------------|-----------------|-------|
| `name` | `String(255) NOT NULL index` | `str = Field(..., min_length=2)` | NOT NULL |
| `email` | `String(255) NOT NULL index` | **`EmailStr = Field(...)`** (formato válido obrigatório) | NOT NULL |
| `phone` | `String(20)` nullable | `str | None` (valida 10–15 díg) | nullable |
| `source` | `LeadSource` | default `OTHER` | — |

- `LeadSource` = `website, referral, social_media, cold_call, email_campaign, event, partner, other` → **sem `whatsapp`** (a adicionar).
- `LeadStatus` = `new, contacted, qualified, proposal, negotiation, won, lost`.
- `id` = UUID (string, `default uuid4`).

> 🔴 **O problema:** um lead vindo de WhatsApp tem **só telefone** (e talvez o nome do perfil). **Não tem email** — mas `email` é obrigatório (e `EmailStr` exige formato válido). É preciso decidir como tratar antes de criar Lead no webhook.

## 3. Opções para o `email` obrigatório (decisão do Jordan)

**(a) Placeholder** (ex.: `wa-5592XXXXXXXXX@conectamais.pro`)
- ✅ Zero mudança de schema; mantém o invariante "todo lead tem email".
- 🔴 **E-mails falsos** entram no funil → risco de **campanha de e-mail disparar para endereço inexistente** (bounce) e poluir relatórios.

**(b) Tornar `email` nullable** (migration sprint91 + model `nullable=True` + schema `EmailStr | None`)
- ✅ Semântica correta (WhatsApp sem email). `ALTER COLUMN ... DROP NOT NULL` é **seguro/reversível** (não reescreve dados).
- 🔴 **Ripple no código:** mapear todos os usos de `lead.email` que assumem não-nulo (respostas, campanhas, relatórios).

**(c) Não criar Lead no webhook** — só gravar `cwi_message_log`; Lead vira decisão manual/posterior.
- ✅ Conservador, não polui o funil automaticamente.
- 🔴 Perde a captura automática de lead.

### Recomendação
- Se o objetivo é **capturar lead automaticamente** do WhatsApp → **(b)** (modelo correto; migration de baixo risco no banco; risco controlável no código).
- **(a)** evitar pelo risco de e-mail falso em campanha.
- **(c)** se preferir não gerar lead automático.

## 4. Estado atual
- Tabela `cwi_message_log` **criada** (Fase 2.1), DB no head `sprint90_cwi_message_log`.
- Próxima migration (se opção **b**): `sprint91`, `down_revision="sprint90_cwi_message_log"`.

## 5. Próximos passos (após sua decisão)
1. **Decisão do email** (a/b/c).
2. Se **(b)**: grep dos usos de `lead.email` (mapear ripple) → migration sprint91 (email nullable) → ajustar model/schema.
3. `LeadSource.WHATSAPP` (só código).
4. Escrever o **webhook** (revisão antes de rodar): valida HMAC → idempotência por `chatwoot_message_id` → normaliza telefone → match em `leads.phone` (cria/atualiza Lead) → grava `cwi_message_log`.
5. Configurar o Webhook no Chatwoot apontando para o backend.

---
*Read-only: leitura de código (webhook + model + schema) e `information_schema`. Nada alterado.*
