# Diagnóstico — "Aceitar" → POST /approve → 400 (READ-ONLY) ✅

- **Data:** 2026-06-10
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Token:** STEP-0-APPROVE-400-RO
- **Modo:** READ-ONLY (proposta de TESTE criada e apagada para o curl; **3 reais intocadas**).
- **Veredito:** **bug de wiring no front** — o botão "Aceitar" (proposta `sent`) chama o endpoint **`/approve`** (workflow interno, exige `pending_approval`) em vez de **`/accept`** (aceite do cliente). 'sent' ≠ pending → **400**.

---

## a) Body EXATO do 400
`POST /api/v1/crm/proposals/{id}/approve` com body válido `{"action":"approve"}` numa proposta **não-pendente**:
```json
{"detail":"Proposta nao encontrada ou nao esta pendente"}   HTTP 400
```
(Sem o body, dá 422 `body.action Field required` — o `/approve` exige `{action}`.)

## b) `/approve` — pré-condição que gera o 400
- `proposal_controller.py:314` `process_proposal_approval` → `repo.process_approval(...)`.
- `proposal_repository.py:512-514`:
  ```python
  proposal = await self.get_by_id(proposal_id)
  if not proposal or not proposal.is_pending:   # <- exige is_pending (status pending_approval)
      return None
  ```
- Controller: se `None` → **HTTP 400 "Proposta nao encontrada ou nao esta pendente"** (l.329-333).
- As 3 propostas estão **`sent`** → `is_pending` False → `None` → **400**. `/approve` é o **workflow interno** de aprovação (pending_approval → approved/rejected), não o aceite do cliente.

## c) `/accept` — existe e é o CORRETO
- `proposal_controller.py:363` `accept_proposal` → `repo.update_status(proposal_id, ProposalStatus.ACCEPTED)`.
- `update_status` (repo): **não valida transição** (só checa existência → 404 se não acha); seta `status=accepted` e, no branch ACCEPTED/REJECTED, **`responded_at = now()`**.
- **Prova real:** `POST /accept` na proposta de teste (status `sent`) → **201, status=accepted**. ✅
- Efeito correto: marca aceite do cliente **e** preenche `responded_at` → **sai do follow-up** (que filtra `status='sent' AND responded_at IS NULL`).

## d) O botão "Aceitar" do front chama `/approve` (errado)
`frontend/src/app/modulos/crm/propostas/page.tsx`:
- l.491-500: quando `proposta.status === 'sent'` → item **"Aceitar"** (ThumbsUp) → `onClick={() => acceptMutation.mutate(proposta.id)}`.
- l.82-83 (`acceptMutation`):
  ```tsx
  mutationFn: (id) => customInstance({ url: `/api/v1/crm/proposals/${id}/approve`,  // <- ERRADO
                                       method: 'POST', data: { action: 'approve' } }),
  ```
  → chama **`/approve`** (não `/accept`). Por isso o 400.
- (l.64-65 `approveMutation` também chama `/approve` — mas esse é usado **corretamente** só no status `pending_approval`, botão "Aprovar" l.451-460. Só o `acceptMutation` está errado.)

## e) DIAGNÓSTICO + fix mínimo
**Causa: (i) botão chama endpoint errado.** O "Aceitar" (aceite do cliente numa proposta `sent`) dispara `/approve` (que exige `pending_approval`) em vez de `/accept`. Como `sent` não é `pending` → 400.

**Fix mínimo (1 linha, front — `page.tsx:83`):**
```diff
- mutationFn: (id) => customInstance({ url: `/api/v1/crm/proposals/${id}/approve`, method: 'POST', data: { action: 'approve' } }),
+ mutationFn: (id) => customInstance({ url: `/api/v1/crm/proposals/${id}/accept`,  method: 'POST' }),
```
(`/accept` não exige body. Provado: 201 status=accepted + responded_at setado.)
> Bake: front é standalone → exige rebuild #3 do frontend (ou docker cp não aplica), como os anteriores.

## f) Máquina de estados — COERENTE (não é trabalho de C)
`ProposalStatus`: `draft → pending_review → pending_approval → approved → sent → viewed → accepted/rejected`. Os endpoints batem com isso e são **distintos por design**:
| Endpoint | Transição | Pré-condição |
|----------|-----------|--------------|
| `/approve` (action=approve) | pending_approval → **approved** | `is_pending` |
| `/approve` (action=reject) | pending_approval → rejected | `is_pending` |
| `/send` | approved → **sent** | (set sent_at) |
| `/accept` | sent → **accepted** | (set responded_at) |
| `/reject` | → rejected | (set responded_at) |
- **`approved` (aprovação interna) ≠ `accepted` (aceite do cliente)** — correto, não bagunçado.
- Botões do front coerentes com o status: `pending_approval`→Aprovar/Rejeitar (`/approve`); `approved`→Enviar ao Cliente (`/send`); `sent`→**Aceitar**. **O único erro é o wiring do "Aceitar"** apontar pra `/approve`.
- ⚠️ Nota cosmética (não é o bug): `getStatusLabel` (l.194-197) rotula **tanto `approved` quanto `accepted` como "Aprovada"** — ambiguidade visual (o select l.291/364 já distingue "Aceita"/"Aprovada"). Vale alinhar junto, mas é cosmético.

---

## Resumo
- **400 = "Proposta nao encontrada ou nao esta pendente"** — `/approve` exige `pending_approval`; as propostas estão `sent`.
- **`/accept` é o endpoint certo** (sent → accepted + responded_at; provado 201) e remove do follow-up.
- **Bug:** `acceptMutation` (page.tsx:83) chama `/approve` em vez de `/accept`.
- **Fix:** 1 linha — apontar `acceptMutation` para `/accept` (sem body). É **pontual no front**, a máquina de estados do backend está coerente (não precisa do trabalho C).
- **Read-only:** proposta de teste criada e **deletada** (3 reais intactas, ainda `sent`/`responded_at` NULL).

*Read-only: curl em proposta de TESTE (criada+deletada), leitura de controller/repo/enum + page.tsx. Nada escrito/buildado. As 3 propostas reais não foram tocadas.*
