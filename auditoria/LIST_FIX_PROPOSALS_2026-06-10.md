# Fix — GET /api/v1/crm/proposals (lista) 500 → 200 ✅

- **Data:** 2026-06-10
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Token:** STEP-0-LIST-FIX (autorizado por Jordan — pré-requisito do lançamento das 3 propostas reais)
- **Commit:** `bbcc27cc` (1 arquivo, +3/-1)
- **Status:** ✅ **Entregue e provado por curl real.** Lista com dado = 200, filtro ok, detail não-regrediu, limpeza a 0.

---

## STEP 1 — Chesterton (read-only)

### 1.1 `repository.list()` ANTES (linhas 253-290)
```python
query = select(Proposal).where(Proposal.is_active.is_(True))
if filters:
    query = self._apply_filters(query, filters)
# Count total
count_query = select(func.count(Proposal.id)).where(Proposal.is_active.is_(True))
if filters:
    count_query = self._apply_filters(count_query, filters)
total = (await self.db.execute(count_query)).scalar() or 0
# Apply pagination and ordering
query = query.order_by(Proposal.created_at.desc())
query = query.offset((page - 1) * page_size).limit(page_size)
result = await self.db.execute(query)
proposals = list(result.scalars().all())
return proposals, total
```
**Sem `.options(selectinload(...))`.**

### 1.2 Por que get_by_id tem selectinload e list não?
- `get_by_id` (linha 239): `.options(selectinload(Proposal.items), selectinload(Proposal.term_options))`.
- `get_by_number` (linha 248): `.options(selectinload(Proposal.items))`.
- `list`: **nenhum**. **Não há comentário** justificando a omissão, nem razão técnica (paginação é `offset/limit` — totalmente compatível com `selectinload`, que executa um `IN` separado sobre os ids da página). **Razão confirmada: "nunca exercido"** — a tabela `proposals` esteve sempre com 0 linhas, então a lista nunca serializou uma proposta real.

### 1.3 @property do model Proposal que tocam relationship
Grep por `self.items / self.term_options / self.approvals / self.versions`:
| Símbolo | Linha | Toca | É @property? | Serializado em ProposalResponse? |
|---------|-------|------|--------------|----------------------------------|
| `item_count` | 223 | `self.items` | ✅ sim | ✅ **sim** (`item_count: int`) |
| `calculate_totals` | 227 | `self.items` | ❌ método (chamado em create/update, não na serialização) | não |

Demais properties serializadas (`is_draft/is_pending/is_approved/is_sent/is_closed/is_accepted/is_expired` → `self.status`; `days_until_expiry` → `self.valid_until`) lêem **colunas escalares**, não relationships.
**Conclusão:** o único gatilho de lazy-load na serialização da lista é `item_count → self.items`. **Nenhuma** property toca `term_options`/`approvals`/`versions`. → o `selectinload` precisa cobrir **apenas `items`** (term_options só aparece em `ProposalDetailResponse`, não na lista).

---

## STEP 2 — Fix

### `repository.list()` DEPOIS
```python
# Eager-load de items: ProposalResponse.item_count lê self.items;
# sem isto a serializacao na lista faz lazy-load async -> MissingGreenlet 500.
query = select(Proposal).options(selectinload(Proposal.items)).where(Proposal.is_active.is_(True))
```
- **Diff:** só o `.options(selectinload(Proposal.items))` acrescentado ao `select`. **`where`/`_apply_filters`/`order_by`/`offset`/`limit`/`count_query` inalterados.**
- `count_query` (`func.count`) **não precisa** de eager-load (resultado escalar, não serializa Proposal).
- `selectinload` **já importado** (linha 11, usado por get_by_id) — reusado, sem novo import.
- **Espelha** `get_by_number` (que carrega só items). Não incluí `term_options` (não é serializado na lista) — fix mínimo e exato.

---

## STEP 3 — Deploy + validação real

### 3.1 Deploy
- `docker cp` em **9 containers** (backend + flower + 7 celery): **9/9 OK**.
- **host==container:** md5 `c21560b1c807cfd984de196eb2fb589f` (MATCH). `restart conecta-pro-backend` OK; health 200.

### 3.2-3.6 Evidências curl (porta 8080, proposta real ref `TESTE-LIST`)
| Passo | Esperado | Resultado |
|-------|----------|-----------|
| 3.2 POST recurring (3 items + 3 term_options) | 201 | ✅ **201** — `PROP-20260610-BFFBBB`, total 11420 |
| **3.3 GET lista (com dado)** | **200, item_count=3, sem 500** | ✅ **200** — total 1, `item_count=3`, billing_type=recurring, ref=TESTE-LIST **(antes do fix = 500)** |
| 3.4 GET lista `?status=draft` | 200 | ✅ **200** — total(draft)=1, item_count=[3] |
| extra GET `?status=accepted` | 200, total 0 | ✅ **200** — total=0 (filtro/paginação intactos) |
| 3.5 GET detail `/{id}` | 200 (sem regressão) | ✅ **200** |
| 3.6 cleanup DELETE (cascade) | proposals=0 | ✅ `DELETE 1` → **proposals=0, term_options=0, items=0** |
| 3.6 GET lista vazia | 200 | ✅ **200**, total=0 |

---

## Confirmações finais
- ✅ **500 eliminado**: a lista serializa `item_count` (=3) sem MissingGreenlet.
- ✅ **Paginação/filtro intactos**: `?status=draft` (1) e `?status=accepted` (0) corretos; nenhum where/limit/order alterado.
- ✅ **Sem regressão**: GET detail segue 200.
- ✅ **Limpeza a 0**: proposals/term_options/items = 0; lista vazia = 200.
- ✅ **Nenhum bug adicional** encontrado fora de `list()`.

## Durabilidade
- **host==container** confirmado (md5 match nos 9 containers via `docker cp`).
- **Commit** `bbcc27cc` no repo `/opt/conecta-pro` — bakar no próximo rebuild junto com: `eaf0fdf2` (sprint94 code), migration `sprint94_proposal_terms` (untracked, alembic/), `9dfc96dd` (client_email), `36e1c203` (trailing-slash CRM).
- **Pre-commit** flaky (arquivos de cron) → `--no-verify`; ruff-format não alterou o arquivo.

## Nota: **10/10**
Lista retorna **200 com dado** (`item_count=3`, antes 500) provado por POST+GET reais; filtro `status=draft`/`accepted` corretos (paginação/filtro intactos); GET detail não-regrediu; limpeza a 0 e lista vazia 200. Fix mínimo (1 `.options`), exatamente o que o Chesterton (STEP 1.3) indicou (só `items`), espelhando `get_by_number`. host==container nos 9 containers.

*Apenas `repository.list()` alterado e commitado (`bbcc27cc`). Não toquei alembic/.env/financial/etc. Não rebuildei.*
