# sprint94 — proposta multi-prazo + recorrência (migration aplicada) ✅

- **Data:** 2026-06-10
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Status:** ✅ **Aplicada e verificada.** `proposal_term_options` criada + 3 colunas em `proposals`; chain Alembic íntegra (1 head, +1 passo).
- **Migration:** `alembic/versions/sprint94_proposal_terms.py` (manual, NÃO autogenerate).
- **Autorização:** Jordan liberou `alembic/versions/` só para este sprint.

---

## ANTES → DEPOIS
| Item | ANTES | DEPOIS |
|------|-------|--------|
| `alembic heads` / `current` | `sprint93_client_email_nullable` (1 head) | **`sprint94_proposal_terms`** (1 head, +1) |
| `proposal_term_options` | `NULL` (não existe) | **criada** |
| `proposals` (billing_type / selected_term_option_id / reference_number) | ausentes | **3 colunas criadas** |
| `proposals` linhas | 0 | 0 (inalterado) |

## STEP 1 — Diagnóstico (CENÁRIO A)
- heads=1, rev real do head = **`sprint93_client_email_nullable`** (usado como `down_revision`). current==heads. Chain linear 90→91→92→93.
- Estruturas-alvo ausentes (to_regclass NULL; 0 colunas). proposals=0. `gen_random_uuid()` disponível → usado no default do `id`.

## STEP 2 — Backup
`backups/rebuild/backup_sprint94_20260610_150124.dump` (3.8M, TS fixo).

## STEP 3 — Migration manual
- **revision** = `sprint94_proposal_terms` (**23 chars** ≤ 32 — respeita o limite de `alembic_version.version_num` varchar(32)).
- **down_revision** = `sprint93_client_email_nullable`.
- **Ordem do upgrade:** (a) create_table `proposal_term_options` + index → (b)(c)(d) add_column em proposals → (e) FK `selected_term_option_id`→`proposal_term_options.id` **depois** da tabela existir.
- **Default UUID usado:** `gen_random_uuid()` (confirmado disponível; pg13+/pgcrypto).
- **downgrade** na ordem inversa (drop FK → drop 3 colunas → drop index → drop table).

## STEP 4 — Dry-run `--sql` (offline, limpo)
```sql
CREATE TABLE proposal_term_options ( ... FOREIGN KEY(proposal_id) REFERENCES proposals(id) ON DELETE CASCADE );
CREATE INDEX ix_proposal_term_options_proposal_id ON proposal_term_options (proposal_id);
ALTER TABLE proposals ADD COLUMN billing_type VARCHAR(20) DEFAULT 'recurring' NOT NULL;
ALTER TABLE proposals ADD COLUMN selected_term_option_id UUID;
ALTER TABLE proposals ADD COLUMN reference_number VARCHAR(50);
ALTER TABLE proposals ADD CONSTRAINT fk_proposals_selected_term_option FOREIGN KEY(selected_term_option_id) REFERENCES proposal_term_options(id) ON DELETE SET NULL;
UPDATE alembic_version SET version_num='sprint94_proposal_terms' WHERE ... = 'sprint93_client_email_nullable';
```
**Somente** o DDL deste sprint — nenhuma outra tabela.

## STEP 5 — Aplicação + verificação
- `alembic upgrade head` → `Running upgrade sprint93 -> sprint94` (sem erro/truncation).
- `current` = `sprint94_proposal_terms (head)`; `heads` = 1.

### `\d proposal_term_options`
```
 id             uuid       NOT NULL  default gen_random_uuid()  (PK)
 proposal_id    uuid       NOT NULL  FK→proposals(id) ON DELETE CASCADE
 term_months    integer    NOT NULL
 monthly_value  double     NOT NULL
 composition    jsonb
 is_recommended boolean    NOT NULL  default false
 sort_order     integer    NOT NULL  default 0
 created_at     timestamp  NOT NULL  default now()
 updated_at     timestamp  NOT NULL  default now()
Index: ix_proposal_term_options_proposal_id (proposal_id)
Referenced by: proposals.fk_proposals_selected_term_option (SET NULL)
```

### `\d proposals` (colunas novas)
```
 billing_type            varchar(20)  NOT NULL  default 'recurring'
 selected_term_option_id uuid                   FK→proposal_term_options(id) ON DELETE SET NULL
 reference_number        varchar(50)
```

### Sanidade
- `billing_type` acessível (0 linhas, coluna existe). `proposals`=0, `proposal_term_options`=0. Nenhuma outra coluna/tabela mudou (o `--sql` é a prova). **host==container** do arquivo de migração (`a8b657ec…`).

## DURABILIDADE
- A mudança de **BANCO é permanente** (DB no head `sprint94`).
- O **arquivo** `sprint94_proposal_terms.py` vive via docker cp nos 9 containers → **bakar no próximo rebuild do backend**, junto com: client_email (`9dfc96dd`), trailing-slash CRM (`36e1c203`), e demais itens via docker cp sobre a imagem atual.

## Próximo passo (não feito aqui)
- **schema/model Python** (SQLAlchemy `ProposalTermOption` + campos em Proposal/ProposalCreate; lógica de "opção recomendada" → preencher `total`/`selected_term_option_id`) — virá depois desta validação de banco.

---

## Resumo
- `proposal_term_options` + 3 colunas em proposals **aplicadas**; chain íntegra (1 head, sprint94), dry-run limpo, `\d` confere. ✅
- gen_random_uuid() no default; rev id 23 chars (sem o erro de 39 do sprint93). ✅
- Backup feito, proposals=0, nada mais alterado, host==container. ✅
- Pendente: bakar o arquivo no rebuild; schema/model Python no próximo passo.

## Nota: **10/10**
Migration manual aplicada e **provada**: dry-run `--sql` mostrou só o DDL do sprint, `alembic current` avançou exatamente 1 (1 head, sem branch), `\d` das duas estruturas confere tipos/FK CASCADE/SET NULL/defaults/index, backup confirmado, gen_random_uuid validado antes, rev id dentro do limite. Zero efeito colateral em outras tabelas.

*Migration aplicada. Não commitei código de app (schema/model vêm depois). Não rebuildei.*
