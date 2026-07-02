# Fix create de proposta — atômico + sem lazy-load async ✅ RESOLVIDO

- **Data:** 2026-06-10
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Status:** ✅ **RESOLVIDO.** `POST /api/v1/crm/proposals` (era 500 `MissingGreenlet`) agora **201** com totais calculados; agravante de proposta parcial **eliminado** (atômico).
- **Arquivo:** `modules/crm/repositories/proposal_repository.py` (só `create`) · **Backup:** `proposal_repository.py.bak-proposalfix-20260610-013413`
- **Commit:** **`eb60ea82`** — `fix(crm): create de proposta atomico + calcula totais sem lazy-load async (corrige 500 MissingGreenlet)`

---

## 1. Abordagem escolhida (e por quê)
**Opção (a): calcular totais em memória antes do commit + commit único.**
- `_create_item` **já calcula `item.total`** em memória (chama `item.calculate_total()`). Então basta montar a lista de itens, **atribuir `proposal.items = items`** (coleção em memória) e chamar `proposal.calculate_totals()` — que passa a ler `self.items` da **memória**, sem lazy-load → sem `MissingGreenlet`.
- Reusa o `calculate_totals()` existente (lógica de desconto/taxas) **sem duplicar**.
- `Proposal.items` tem `cascade="all, delete-orphan"` e `proposal.id` vem do construtor (uuid4) → `db.add(proposal)` adiciona os itens em cascata, **sem precisar do flush antecipado**.
- Mais limpa que `refresh(["items"])` pré-cálculo, e não muda o model/schema/controller.

## 2. Diff (essência)
**Antes** (bugado): `add(proposal)` → `flush()` → add itens → **commit** → `refresh` → `calculate_totals()` (lazy → MissingGreenlet) → **commit** (2º).
**Depois** (atômico):
```python
items = [self._create_item(proposal.id, item_data, i) for i, item_data in enumerate(data.items)]
proposal.items = items                 # coleção em memória
proposal.calculate_totals()            # lê da memória, sem IO
self.db.add(proposal)                  # cascade adiciona os itens
try:
    await self.db.commit()             # COMMIT ÚNICO no fim (atômico)
except Exception:
    await self.db.rollback()
    raise
await self.db.refresh(proposal, ["items"])  # eager-load p/ serialização da resposta
return proposal
```

## 3. TESTE PRINCIPAL — POST /api/v1/crm/proposals
- Payload: title/client_name/client_email + 2 itens (1×1000 + 2×500).
- **HTTP 201** · `number=PROP-20260610-A6D85B` · `status=draft` · `sent_at=None` · **`subtotal=2000.0` · `total=2000.0`** (calculado certo) · 2 itens.
- Banco confirma: `subtotal=2000, total=2000, itens=2, sent_at=null`. ✅

## 4. TESTE DE ATOMICIDADE (agravante resolvido)
- Forçado `Proposal.calculate_totals` a lançar exceção (no novo código isso é **antes** do commit).
- `proposals` ANTES = 1 → exceção capturada → `proposals` DEPOIS = **1 (inalterado)** → linhas `'PROPOSTA ATOMICIDADE'` = **0**.
- ✅ **Nenhuma proposta parcial** persistida. O `try/except → rollback` cobre ainda falhas no próprio commit.

## 5. Limpeza e estado
- Propostas de teste deletadas (itens + proposta) → **`proposals` = 0**.
- **`opportunities` seed (5) intactas** (não tocadas).
- **host==container** (`cf8c4a86…`) · backend **healthy** · **health 200**.

## 6. Durabilidade
- Commit `eb60ea82` vive via docker cp sobre a imagem `c4bde53` → **bakar no próximo rebuild** (1 item). **NÃO rebuildei.**

## 7. Próximo passo (separado)
- Agora que `create` funciona, construir o **"enviar/sent_at"** (marcar proposta como enviada) + a **rotina de follow-up** (proposals com `sent_at < hoje-Xd` e `viewed_at null` → contatar lead por WhatsApp/e-mail). **Não feito aqui.**

---

## Resumo
- `create` de proposta **corrigido**: totais em memória (sem lazy-load) + **commit único atômico**. ✅
- POST 201 com total=2000 calculado; atomicidade provada (0 parcial). ✅
- proposals=0, opportunities seed intactas, host==container, health 200, commit `eb60ea82`. ✅
- Pendente: bakar no rebuild; depois construir enviar/sent_at + follow-up (separado). Não rebuildei.

*PAREI. Não construí o "enviar/sent_at". Não rebuildei.*
