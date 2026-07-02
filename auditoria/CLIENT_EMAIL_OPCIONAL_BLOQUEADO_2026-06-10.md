# client_email opcional na proposta — BLOQUEADO (coluna NOT NULL) — READ-ONLY

- **Data:** 2026-06-10
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Tornar `client_email` opcional na criação de proposta (backend) + adicionar o campo opcional no form (frontend).
- **Veredito:** ⛔ **Bloqueado na fundação.** A coluna `proposals.client_email` é **NOT NULL** → mudar só o schema trocaria o **422 por 500**. Conforme a regra ("NOT NULL → parar antes de migration"), **parei**.
- **NADA alterado** (só leitura). Sem migration, sem schema/model/frontend tocados.

---

## 1. O bloqueio
| Camada | Estado |
|--------|--------|
| Banco `proposals.client_email` | `varchar(255)` **NOT NULL** (`is_nullable=NO`) 🔴 |
| Model `modules/crm/models/proposal.py:88` | `Column(String(255), nullable=False)` 🔴 |
| Schema `modules/crm/schemas/proposal.py:137` (`ProposalBase`) | `client_email: EmailStr` (obrigatório, sem default) |

- **Hoje:** POST sem `client_email` → **422** (`loc=["body","client_email"]`, "Field required").
- **Se eu tornasse só o schema `Optional[EmailStr] = None`** (sem migration): o INSERT com `client_email=None` violaria o NOT NULL → **500**. E o campo "opcional" no front quebraria (e-mail vazio → 500). **Regressão, não melhoria.** Por isso parei.

## 2. Por que destravar é trivial e seguro
- **`proposals` = 0 linhas, 0 nulos** → `ALTER COLUMN client_email DROP NOT NULL` é **zero-risco** (nenhum dado existente a violar).
- **Precedente no projeto:** `alembic/versions/sprint91_lead_email_nullable.py` fez **exatamente** isso com `leads.email`. Mesmo padrão, já aplicado antes.

## 3. Plano para destravar (próximo passo — requer autorização de migration)
1. **Migration** (espelha sprint91, sob o head atual `sprint92`): `op.alter_column("proposals", "client_email", existing_type=sa.String(255), nullable=True)`; downgrade reverte. + model `nullable=True`. (Backup + `alembic current/heads` = 1 head, como fizemos no sprint92.)
2. **Schema (Parte 1):** `client_email: EmailStr | None = None` + `field_validator("client_email", mode="before")` que normaliza `""`/espaços → `None` (porque `EmailStr` **rejeita string vazia**). Testes: sem email → 201; com email válido → 201; email `""` → 201 (vira null).
3. **Frontend (Parte 2):** input "E-mail do cliente" (type email, **sem required**) no form "Nova Proposta" (entre Cliente e Valor); payload manda `null` quando vazio. Build serializado + docker cp no container `conecta-pro-frontend` (3001).

## 4. Observações
- `ProposalCreateFromOpportunity` (schema:190) **já** tem `client_email: EmailStr | None = None` — mas como a coluna é NOT NULL, esse caminho também dependeria da migration para persistir None (provavelmente hoje copia o e-mail da opportunity/lead, evitando o None).
- Forbidden zones: o schema do CRM **não** é forbidden; a migration (alembic) **é** zona que exige autorização explícita (como no sprint92).

## 5. Durabilidade (quando executar)
- Backend (migration + schema/model) → banco permanente + arquivos via docker cp sobre `5a14e5db` (bakar no rebuild).
- Frontend → docker cp no container `conecta-pro-frontend` (não-baked) → rebuild da imagem do front para bakar.

---

## Resumo
- `proposals.client_email` é **NOT NULL** (banco + model) → tornar opcional **exige migration** (DROP NOT NULL). 🔴
- `proposals`=0 linhas → ALTER zero-risco; precedente `sprint91` (leads.email). ✅
- **Parei conforme a regra** — nada alterado, sem migration.
- **Decisão sua:** autorizar a migration `client_email` nullable? Com o OK, executo migration → schema (+ normalização `""`→None) → campo no front, e valido sem/com/vazio.

*PAREI antes de qualquer migration. Nada alterado.*
