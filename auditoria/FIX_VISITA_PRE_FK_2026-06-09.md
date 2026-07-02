# fix Visita pré — as FKs existem no banco ou só no model? (READ-ONLY)

- **Data:** 2026-06-09
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Decidir como destravar a criação de visita (bug `NoReferencedTableError`) — com ou sem migration, e quais linhas tocar.
- **Veredito:** Fix é **só código, SEM migration** (o banco não tem as FKs). Porém são **5 FKs cross-schema, não 3** — remover só as 3 do erro faria falhar na próxima. Nenhum `relationship()` depende delas.

---

## 1. Banco NÃO tem as FKs → fix só código, SEM migration ✅
`pg_constraint` para `visitas` com `contype='f'` = **0 linhas**. As FKs existem **apenas no model SQLAlchemy**. Remover o `ForeignKey(...)` não altera o banco → **nenhuma migration**.

## 2. Colunas existem, todas `uuid` nullable ✅
| Coluna | nullable | tipo |
|--------|----------|------|
| `cliente_id` | YES | uuid |
| `proposta_id` | YES | uuid |
| `oportunidade_id` | YES | uuid |

Virar UUID puro (sem FK) é transparente para o banco.

## 3. ⚠️ São 5 FKs cross-schema, não 3
O flush para na primeira FK irresolvível e reporta uma de cada vez. Remover só as 3 do erro → passa a falhar na próxima. FKs cross-schema no model `modules/campo/models/visita.py`:

| Linha | Coluna | FK alvo (outro schema) | Ação |
|-------|--------|------------------------|------|
| 131 | `cliente_id` | `clients.clients.id` | remover ForeignKey |
| 132 | `contrato_id` | `crm.contracts.id` | remover ForeignKey |
| 149 | `lead_id` | `crm.leads.id` | remover ForeignKey |
| 150 | `oportunidade_id` | `crm.opportunities.id` | remover ForeignKey |
| 215 | `proposta_id` | `crm.proposals.id` | remover ForeignKey |
| 260 | `visita_origem_id` | `visitas.id` (mesmo schema) | **MANTER** (não causa erro) |

## 4. Nenhum `relationship()` depende dessas FKs ✅
Linhas 301-304: `relationship()` de `cliente`, `lead`, `oportunidade`, `proposta` estão **todos comentados**. Remover os `ForeignKey` **não quebra JOIN automático**. As colunas viram links soft — como `responsavel_id` (que já é UUID sem FK).

---

## Plano de fix (quando autorizado — só código)
1. Editar 5 linhas em `modules/campo/models/visita.py`: trocar `Column(UUID(as_uuid=True), ForeignKey("<schema>.<tabela>.id"), nullable=True[, index=True])` por `Column(UUID(as_uuid=True), nullable=True[, index=True])` nas 5 colunas. Manter `visita_origem_id`.
2. Backup do model + deploy (docker cp nos 9) + restart.
3. **Re-teste decisivo:** `POST /api/v1/campo/visitas/` no app vivo deve voltar **201** (hoje 500) — prova o `campo` consertado de forma geral.
4. **Reaplicar a 3ª tool** (de `agent_service.py.fvisita3tools-pending-modelfix`) + re-rodar Teste A (criar AGENDADA, responsavel `ad9abb59`, origem `lead`) + B + guard.
5. Commit (model fix + tool) + bakar no próximo rebuild.

**Risco:** baixo — código-only, sem migration, sem relationship afetado, sem FK no banco. Beneficia todo o módulo `campo`, não só o agente.

---

## Resumo
- DB sem FKs em `visitas` → **fix só código, sem migration**. ✅
- **5 FKs cross-schema** a remover (não 3): `cliente_id, contrato_id, lead_id, oportunidade_id, proposta_id`. `visita_origem_id` fica. ⚠️
- Relationships comentados → **sem quebra**. ✅
- Aguardando seu OK para aplicar o fix das 5 FKs.

*Read-only: `pg_constraint`, `information_schema.columns`, `grep` no model. Nada editado.*
