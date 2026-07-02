# Fase 2 — Confirmação de tipos + correção da cadeia alembic (drift)

- **Data:** 2026-06-05 ~21:20 UTC
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Confirmar tipos antes da migration da Fase 2 (cwi_message_log) e estado do alembic.
- **Resultado:** Tipos OK (baixo risco) + 🔴→✅ **cadeia alembic estava QUEBRADA (drift) e foi corrigida.**

---

## 1. Tipos confirmados (baixo risco)
- **`leads.source` = `character varying` (varchar)** — **não é enum nativo do PG**. Adicionar `WHATSAPP="whatsapp"` ao `LeadSource` (StrEnum) é **só código**, sem `ALTER TYPE`/migration de enum. ✅
- **`clients.phone/whatsapp/financial_contact_phone/technical_contact_phone` = varchar.** ✅

## 2. ⚠️ Realidade dos dados — impacto no match número→cliente
- **`clients`: 11 registros, 0 com `phone`, 0 com `whatsapp`** (campos vazios).
- **Consequência:** cruzar o número de uma mensagem de entrada com um cliente via `clients` **não funciona hoje** (não há telefone gravado).
- **Implicação de design:** mensagens de entrada vão, na prática, **virar Lead** (funil inbound) — comportamento aceitável, mas decisão a confirmar. Alternativas: popular telefones de `clients` (a partir das NFS-e/contratos), ou tentar match também em `client_contacts`.

## 3. 🔴→✅ Cadeia alembic estava QUEBRADA (mesmo padrão de drift)
**Sintoma:** `alembic current` falhava com `KeyError: 'drop_openclaw_tables'`.

**Causa-raiz (drift host↔container):**
- Host: **119** migrations. Container: **112** → **7 arquivos faltando no container**:
  `camada3_benchmarks.py`, `camada3_exec_kpis_20260530.py`, `camada3_financial_kpis.py`, `camada3_report_schedules.py`, `camada3_report_templates.py`, `drop_openclaw_tables.py`, `frente2_renames_20260530.py` (todos do trabalho de 2026-05-30, criados no host mas nunca copiados para o container).
- O container tinha `findp_b1b2_20260601.py` (`down_revision="drop_openclaw_tables"`), mas **não** tinha o `drop_openclaw_tables.py` → cadeia partida.

**Correção aplicada:** `docker cp` dos 7 arquivos host→container (apenas adiciona arquivos da fonte da verdade; **não roda nenhuma migration**).

**Verificação pós-fix:**
- Container: **119** migrations (== host).
- `alembic current` → **`findp_b1b2_20260601 (head)`** ✅
- `alembic heads` → **1 head, sem branch** ✅
- DB (`alembic_version`) já estava em `findp_b1b2_20260601` (head) → **sem migrations pendentes** (os 7 arquivos só faltavam no FS do container, não na aplicação ao banco).

> Mesmo tipo de drift do `service.py`: arquivos no host não chegaram ao container. Reforça incluir **md5/contagem host-vs-container no checklist de deploy**.

## 4. Pronto para a Fase 2 (implementação)
Agora é possível criar a migration da Fase 2 com `down_revision = "findp_b1b2_20260601"`:
- Tabela **`cwi_message_log`** (idempotência por `chatwoot_message_id`).
- Enum `LeadSource` + `WHATSAPP` (só código).
- Endpoint de webhook (módulo `integrations`, fora das zonas proibidas).

### Decisões ainda pendentes (suas)
1. Toda mensagem de entrada vira Lead, ou só de número desconhecido? (hoje, na prática, **tudo vira Lead** — clients sem telefone).
2. Logar só entrada ou entrada+saída?
3. Popular telefones de `clients` para habilitar match futuro?

---
*Read-only de confirmação + `docker cp` de 7 migrations (sincronização host→container, sem rodar migration). Banco não alterado. Telefones não expostos.*
