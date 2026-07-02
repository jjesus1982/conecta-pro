# Migration `proposal_followups` — estado/auditoria de follow-up ✅

- **Data:** 2026-06-10
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Status:** ✅ **Aplicada.** Tabela `proposal_followups` criada via Alembic; chain íntegra (1 head, +1 passo). Outras tabelas intactas.
- **Autorização:** Jordan autorizou tocar `alembic/versions/` restrito a ESTA migração.
- **Commit:** **`dd57f47b`** — `feat(crm): migration proposal_followups (estado/auditoria de follow-up)`

---

## 1. Pré-flight (chain limpa)
- **Backup:** `backups/rebuild/pre_followup_mig_20260610_020955.dump` (3.8M) — TS fixo em variável.
- `alembic current` ANTES = `sprint91_lead_email_nullable (head)`.
- `alembic heads` ANTES = **1 head** (`sprint91_lead_email_nullable`).
- ✅ Chain limpa (current == head, sem divergência). `down_revision` usado = **`sprint91_lead_email_nullable`** (head real, não inventado).

## 2. Padrão seguido (verificado)
- `proposals.id` e `proposal_items.proposal_id` = **uuid**; `proposal_items` usa **FK real same-schema** (`proposal_items_proposal_id_fkey → proposals`). proposals está em `public` → **sem o problema cross-schema do campo**.
- `id` default: `gen_random_uuid()` (disponível; mesmo padrão de `crm_contacts`) — escolhido p/ robustez na inserção pela rotina.

## 3. Migração (`sprint92_proposal_followups`)
```python
revision = "sprint92_proposal_followups"
down_revision = "sprint91_lead_email_nullable"

def upgrade():
    op.create_table(
        "proposal_followups",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("proposal_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("proposals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),       # 1=2d, 2+=7d
        sa.Column("channel", sa.String(20), nullable=True),        # whatsapp|email|both|none
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),  # pending|sent|failed|skipped
        sa.Column("scheduled_for", sa.DateTime(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_proposal_followups_proposal", "proposal_followups", ["proposal_id"])
    op.create_index("ix_proposal_followups_status_sched", "proposal_followups", ["status", "scheduled_for"])

def downgrade():
    op.drop_index("ix_proposal_followups_status_sched", table_name="proposal_followups")
    op.drop_index("ix_proposal_followups_proposal", table_name="proposal_followups")
    op.drop_table("proposal_followups")
```
- Sem efeito colateral em outras tabelas (só create/drop da nova).

## 4. Aplicação + validação
- `alembic upgrade head` → `Running upgrade sprint91_lead_email_nullable -> sprint92_proposal_followups`.
- `alembic current` DEPOIS = **`sprint92_proposal_followups (head)`** (avançou exatamente 1 passo). `heads` = **1**.
- `\d proposal_followups`: colunas/tipos certos; PK `id` (gen_random_uuid), **FK `proposal_id → proposals(id) ON DELETE CASCADE`**, 2 índices (`ix_proposal_followups_proposal`, `ix_proposal_followups_status_sched`).
- **Outras tabelas intactas:** proposals=0, opportunities=5, leads=18, proposal_followups=0 (vazia, como esperado).

## 5. Integridade host↔container
- Migração copiada aos **9 containers**; **host==container** (`5b4f1815…`). Sem drift (versions 121→122 nos dois).
- Black reformatou o arquivo no commit (reordenou imports) → re-commit + re-sync da versão final.

## 6. Durabilidade
- Arquivo de migração vive via docker cp sobre a imagem `c4bde53` → **bakar no próximo rebuild** (a mudança no BANCO já é permanente; o arquivo precisa entrar na imagem). **NÃO rebuildei.**

## 7. Próximo passo (separado — NÃO feito)
- Criar a rotina Celery `crm.followup_proposals` (flag `FOLLOWUP_AUTO_SEND=false` → só gera lista + Telegram, sem contatar cliente) que usa esta tabela para a cadência 2d/7d. Ver `FFOLLOWUP_PRE_ROTINA_DESENHO_2026-06-10.md`.

---

## Resumo
- `proposal_followups` criada (Alembic `sprint92` sob `sprint91`, 1 head, +1 passo). ✅
- FK real same-schema, 2 índices, id gen_random_uuid; outras tabelas intactas. ✅
- Backup feito, host==container, commit `dd57f47b`. ✅
- Pendente: bakar no rebuild; construir a rotina (separado). Não rebuildei.

*PAREI. Não criei a rotina Celery. Não rebuildei.*
