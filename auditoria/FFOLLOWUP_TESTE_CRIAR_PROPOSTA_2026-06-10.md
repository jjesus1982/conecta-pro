# Teste de criação de proposta — subsistema NÃO funciona hoje (bug latente async)

- **Data:** 2026-06-10
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Provar se o subsistema de propostas CRIA proposta de verdade antes de construir o "enviar/sent_at".
- **Veredito:** ⛔ **NÃO cria limpo.** `POST /api/v1/crm/proposals` retorna **500** (`MissingGreenlet` — lazy-load async em `calculate_totals`) e **deixa uma proposta parcial** no banco. Bug latente, nunca exercido (proposals=0). Como o módulo campo.
- **Escrita feita:** criar + deletar 1 proposta de teste (revertido). **Nada consertado, nada commitado, sem rebuild.**

---

## 1. Campos obrigatórios do POST (read-only)
`ProposalCreate(ProposalBase)`:
- **Obrigatórios:** `title`, `client_name`, `client_email` (EmailStr), e **cada item** exige `name` (descoberto: 1º POST deu 422 `items[0].name required`).
- Defaults: `proposal_type=service`, `installments=1`, `discount/taxes=0`, `items=[]`, `valid_until`→+30 dias. Status inicial `DRAFT`; `sent_at` null.
- Controller: `POST ""` → `repo.create(data, created_by_id)`.

## 2. Teste de criação
- **1ª tentativa:** 422 — item exigia `name`. (ajuste permitido)
- **2ª tentativa** (com `name` no item): **HTTP 500**.

## 3. Erro EXATO (bug latente)
```
sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called;
can't call await_only() here. Was IO attempted in an unexpected place?
```
**Causa raiz:** `proposal_repository.create` faz `await db.commit()` + `await db.refresh(proposal)` e **depois** chama `proposal.calculate_totals()`, que acessa `self.items` (relacionamento **lazy**):
```python
# models/proposal.py
def calculate_totals(self):
    if self.items:                      # <-- lazy-load dispara IO sync...
        self.subtotal = sum(item.total for item in self.items)
# repository/proposal_repository.py (após commit+refresh)
proposal.calculate_totals()            # <-- ...em contexto async -> MissingGreenlet
```
➡️ Acesso lazy a `proposal.items` fora do greenlet async → `MissingGreenlet` → 500.

## 4. Agravante — proposta PARCIAL persistida apesar do 500
O repo faz **commit da proposta+itens (linha 60) ANTES** de `calculate_totals`. Quando `calculate_totals` estoura, a linha **já está gravada**:
- Criada: `id=e5dad2cf-…`, `number=PROP-20260610-602BE6`, `status=draft`, `sent_at=null`, `total` nunca calculado (default 0).
- ⚠️ O endpoint retorna 500, mas **deixa uma proposta inconsistente** no banco (sem rollback). Pior que o campo (que dava rollback no flush).

## 5. Limpeza
- Deletados `proposal_items` + a proposta de teste → **`proposals` = 0** (volta ao estado inicial). As 5 `opportunities` seed **não foram tocadas**.

## 6. Veredito
**O subsistema de propostas NÃO cria proposta hoje.** Código existe e é rico, mas o caminho de criação tem um **bug async latente** (`MissingGreenlet` em `calculate_totals` após commit) — nunca exercido (0 linhas). É o mesmo padrão do módulo campo: pronto no papel, quebrado na 1ª execução real.

## 7. O que faltaria (fix — tarefa separada, decisão Jordan)
- Em `proposal_repository.create`: calcular totais **dentro do greenlet** — opções:
  1. `await db.refresh(proposal, ["items"])` antes de `calculate_totals` (eager-load do relacionamento), **ou**
  2. calcular o total a partir dos objetos `item` já em memória (antes do commit/expire), **ou**
  3. `calculate_totals` receber os itens explicitamente (sem lazy-load).
- Garantir **rollback** se o pós-processamento falhar (não deixar proposta parcial).
- Só depois construir o **"enviar/sent_at"** + o follow-up.

---

## Resumo
- POST /crm/proposals: 422 (item sem `name`) → **500 `MissingGreenlet`** (lazy-load em calculate_totals). ⛔
- Deixou proposta parcial (commit antes do erro) → **limpei** (proposals=0). ✅
- Subsistema **não cria proposta hoje** — bug latente async, como o campo. Fix no repo/model é pré-requisito do follow-up.
- Nada consertado/commitado. Opportunities seed intactas. Não rebuildei.

*PAREI conforme a regra (500 → reportar exato e parar).*
