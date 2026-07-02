# Diagnóstico — Propostas mostram R$ 0,00 na tela (READ-ONLY) ✅

- **Data:** 2026-06-10
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Token:** STEP-0-VALOR-ZERO-RO
- **Modo:** 100% READ-ONLY — zero escrita/commit/deploy/build.
- **Veredito:** **bug de UI** — a lista e o detalhe leem `total_value`/`valor` (inexistentes na resposta) em vez de **`total`** (a chave que a API realmente manda). `|| 0` no fim → cai em **R$ 0,00**.

---

## a) Dado no banco — CERTO (não é bug de dado)
```
 reference_number | total | subtotal
 00001            |  1800 |     1800
 00091            | 11420 |    11420
 00092            | 11210 |    11210
```
`total` correto. Descarta bug de dado.

## b) Chave JSON do valor na API = **`total`**
- `ProposalResponse` (schema, `modules/crm/schemas/proposal.py:325`): `total: float` (+ `subtotal` l.319). **NÃO existe `total_value`** no response da proposta — `total_value` só aparece em `ProposalStats` (l.412, agregado do hub).
- `curl GET /api/v1/crm/proposals` (ref 00091):
  - `"total": 11420.0` ✅
  - `"total_value"`: **AUSENTE**
  - `"valor"` / `"value"` / `"amount"`: **AUSENTES**
- Tipo TS gerado confirma: `modulesCrmSchemasProposalProposalResponse.ts:61 → total: number`; `proposalDetailResponse.ts:62 → total: number`. **Não há `total_value` no tipo da proposta.**

## c) Propriedade que a LISTA lê = **`total_value` (errado)**
`frontend/src/app/modulos/crm/propostas/page.tsx:428`
```tsx
{formatCurrency(proposta.total_value || proposta.valor || 0)}
```
`proposta` é tipado como `any` → TS não pega o erro. `total_value` e `valor` são `undefined` → `|| 0` → **R$ 0,00**.

## d) Propriedade que o DETALHE lê = **`total_value` (errado)**
`page.tsx:577`
```tsx
<p className="font-medium">{formatCurrency(selectedItem.total_value || selectedItem.valor || 0)}</p>
```
Mesmo erro → R$ 0,00.

## e) Propriedade que o HUB lê (funciona) = **`proposals_total_value` (agregado)**
`frontend/src/app/modulos/crm/page.tsx:89`
```tsx
subtitle: kpiData?.proposals_total_value ? formatCurrency(kpiData.proposals_total_value) : 'Valor total',
```
O hub lê um **campo agregado** (`DashboardKPIs.proposals_total_value`, somado server-side a partir de `proposals.total`) — por isso mostra **24.430,00** certo. É um endpoint/campo DIFERENTE do per-proposta.

## g) Formatação NÃO é a culpada
`src/lib/utils.ts:10`
```ts
export function formatCurrency(value: number): string {
  return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(value);
}
```
**Não divide por 100**, não zera nada — apenas formata o número que recebe. Como recebe `0` (do campo errado), exibe "R$ 0,00". Input errado, não formatação.

---

## f) DIAGNÓSTICO CRAVADO + de-para da correção
**Causa exata:** a tela de Propostas (lista e detalhe) lê `proposta.total_value || proposta.valor`, mas a API manda **`total`**. Como `total_value`/`valor` não existem na resposta → `undefined` → `|| 0` → **R$ 0,00**. O hub funciona porque lê outro campo (`proposals_total_value`, agregado dos stats). Confusão entre o **nome agregado** (`total_value` em ProposalStats/KPIs) e o **campo da proposta** (`total`).

**Correção (2 linhas no `page.tsx` — NÃO aplicada, só apontada):**
| Linha | ANTES | DEPOIS |
|-------|-------|--------|
| **428** (coluna Valor da lista) | `formatCurrency(proposta.total_value \|\| proposta.valor \|\| 0)` | `formatCurrency(proposta.total ?? 0)` |
| **577** (campo Valor do detalhe) | `formatCurrency(selectedItem.total_value \|\| selectedItem.valor \|\| 0)` | `formatCurrency(selectedItem.total ?? 0)` |

> `?? 0` (nullish) é mais seguro que `|| 0` aqui — mas `|| 0` também funcionaria pois `total` nunca é falsy quando há valor. O essencial é trocar `total_value`/`valor` por **`total`**.

### Observação (separado, NÃO é a causa do R$ 0,00 na exibição)
- O **formulário de criação** (`page.tsx:107,123,165,350,351`) usa `total_value` no `formData` (input "Valor (R$)") e no mapeamento de edição (`l.165: total_value: proposta.total_value || proposta.valor`). Isso é um campo **morto** (o `ProposalCreate` do backend calcula `total` a partir dos `items`, não aceita `total_value`). Não afeta a exibição de R$ 0,00 das 3 propostas, mas é a mesma confusão de nome — vale alinhar quando mexer (fora do escopo deste diagnóstico).

---

## Resumo
- Banco OK (`total`=1800/11420/11210). API manda **`total`** (não `total_value`).
- LISTA (l.428) e DETALHE (l.577) leem `total_value`/`valor` → ausentes → `|| 0` → **R$ 0,00**.
- HUB lê `proposals_total_value` (agregado) → 24.430 certo.
- `formatCurrency` não é culpado (não divide por 100).
- **Fix:** trocar `proposta.total_value || proposta.valor || 0` por **`proposta.total ?? 0`** nas linhas **428** e **577** do `page.tsx`. Frontend é imagem baked (rebuild + recreate p/ produção, ou docker cp temporário).

*Read-only: SELECT, schema/curl da API, grep do page.tsx (lista/detalhe/hub), formatCurrency, tipos gerados. Nada escrito/buildado/deployado.*
