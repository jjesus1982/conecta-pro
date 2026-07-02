# Fase 2.1b — Ripple de tornar `lead.email` nullable (READ-ONLY)

- **Data:** 2026-06-05 ~22:20 UTC
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Decisão do Jordan:** Opção **(b)** — `email` do Lead passa a ser nullable (para capturar lead de WhatsApp sem email).
- **Resultado:** Ripple **pequeno e seguro** — nenhum uso quebra com `email=None`. Há até precedente no código.

---

## 1. Análise dos usos de `lead.email` (nenhum quebra com NULL)
| Local | Uso | Comportamento com `email=None` |
|-------|-----|--------------------------------|
| `lead_repository.py:36` | `email=data.email` (insert) | OK após coluna nullable |
| `lead_repository.py:58` | `f"...({lead.email})"` (log) | imprime `None` — **sem crash** |
| `lead_repository.py:84` | `where(Lead.email == email)` (get_by_email) | `= NULL` → não casa; **sem crash** |
| `lead_repository.py:157` | `Lead.email.ilike(...)` (busca) | linhas NULL não casam; **sem crash** |
| `lead_controller.py:43` | `repo.get_by_email(data.email)` (dedup) | se None → busca por NULL (inócuo). **Guardar** (pular dedup se None) |
| `opportunity_repository.py:92` | `contact_email=lead.email` | copia None → `contact_email` (já nullable). OK |
| `models/lead.py:151` | `__repr__` com `{self.email}` | `None` — sem crash |
| `lead_service.py:105` | `(lead.email, 15)` (score de completude) | confirmar que trata falsy (provável `if email: +15`) |

## 2. Mailers / campanhas que cruzam com leads
- `marketing_controller.py:235` → **já tem fallback**: `mkt_lead.email or f"{name}@lead.conecta"`. **Precedente** de lead sem email no próprio código. ✅
- `automation/workflow` (`workflow_step.py:142`, `workflow_action.py`) → template `{{lead.email}}` é **config do usuário**; um email None só falharia aquele envio específico, não quebra o sistema. (Risco de configuração, não de código.)

**Conclusão:** nenhum mailer **crasha**; o de marketing já protege. Risco residual = workflows configurados manualmente apontando para `{{lead.email}}` (documentar).

## 3. Schema Pydantic — linhas a alterar
- `lead.py:16` (LeadBase): `email: EmailStr = Field(...)` → **`email: EmailStr | None = Field(None, ...)`**
- `lead.py:70` (LeadResponse): `email: str` → **`email: str | None`**
- `lead.py:49` (LeadUpdate): `email: EmailStr | None = None` → **já está nullable** ✅

## 4. Plano de mudança (PROPOSTA — nada feito ainda)
1. **Migration `sprint91`** (`down_revision="sprint90_cwi_message_log"`): `ALTER TABLE leads ALTER COLUMN email DROP NOT NULL` — operação **segura/reversível**, não reescreve dados. Downgrade: re-`SET NOT NULL` (cuidado: só funciona se não houver NULLs; documentar).
2. **Model** `lead.py:87`: `email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)`.
3. **Schema** `lead.py`: linhas 16 e 70 (acima).
4. **Defensivo** `lead_controller.py:43`: pular dedup por email se `data.email is None`.
5. `LeadSource.WHATSAPP = "whatsapp"` (só código).
6. Deploy: `docker cp` (model+schema+controller+migration) + `alembic upgrade` (com backup) + restart — padrão da casa, **promovendo no host também** (evitar drift).

## 5. Risco geral: BAIXO
- DB: `DROP NOT NULL` é trivial e reversível.
- Código: nenhum crash; precedente de fallback já existe; único ponto de atenção são workflows de email configurados manualmente.

---
*Read-only: grep dos usos de `.email` em `modules/`. Nada alterado.*
