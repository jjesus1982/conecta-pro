# Estrutura interna de Propostas (CRM) — mapa para evoluir multi-prazo + recorrência (READ-ONLY)

- **Data:** 2026-06-10
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Mapear a estrutura interna antes de evoluir Propostas para multi-prazo + recorrência.
- **Modo:** 100% READ-ONLY (só leitura de schema/código; zero escrita/commit/deploy).
- **Achado crítico:** **WeasyPrint NÃO instalado** → PDF hoje sai PLACEHOLDER (bug pré-existente, não corrigido).

---

## 1. `proposal_items` (item de proposta)
```
 id               uuid          NOT NULL  (PK)
 proposal_id      uuid          NOT NULL  FK→proposals.id ON DELETE CASCADE
 code             varchar(50)
 name             varchar(255)  NOT NULL
 description      text
 unit             varchar(20)   NOT NULL   -- "un","hr","mês"... (TEXTO LIVRE)
 quantity         double        NOT NULL
 unit_price       double        NOT NULL
 discount_percent double        NOT NULL
 total            double        NOT NULL   -- quantity*unit_price - desconto
 sort_order       integer       NOT NULL
 is_optional      boolean        NOT NULL
 is_active        boolean        NOT NULL
 created_at/updated_at timestamp NOT NULL
```
➡️ Item **plano**: `total = quantity*unit_price − discount`. **NENHUM conceito estruturado de recorrência/período/mensal** — só `unit` (texto livre) poderia carregar "mês".

## 2. `proposals` — total e campos de prazo/recorrência
- **Cálculo (Python, sem trigger):**
```python
def calculate_totals(self):
    self.subtotal = sum(item.total for item in self.items) if self.items else 0.0
    self.total = self.subtotal - self.discount_amount + self.taxes
# chamado no repo.create/update/new_version (eb60ea82: na memória, antes do commit)
```
- **Colunas monetárias/prazo existentes:** `subtotal, taxes, total` (double), `tax_breakdown` (jsonb), `discount_type/value/reason`, `installments` (int = parcelas), `payment_terms`/`payment_conditions` (texto), `valid_until` (date = validade da PROPOSTA).
- ⚠️ **NENHUMA coluna de recorrência / mensalidade / período / vigência de contrato / billing.** `installments` = parcelas de pagamento (não recorrência); `valid_until` = validade da proposta (não prazo do contrato).

## 3. `proposal_templates`
Colunas: `name, description, default_title, default_description, terms_conditions, payment_terms, validity_days, proposal_type, header_html, footer_html, css_styles, is_default, is_active`.
- ➡️ Template carrega **apenas presets de texto/HTML** (título/termos/pagamento/validade/estilo do PDF). **NÃO há itens/composição** (sem tabela template_items; sem relação de itens).
- **0 templates cadastrados** — nenhum "portaria remota"/"manutenção".

## 4. `pdf_generator.py` (modules/crm/services/, 20KB)
- **Entrada:** dataclass **`ProposalData`** com: `number, version, issue_date, valid_until, items[], subtotal, discount_value, taxes, total, cct_value?, margin_percent?, introduction?, terms?, payment_terms?, notes?, salesperson_name/email?`.
  - 👀 Tem **`cct_value` e `margin_percent`** (CCT/margem — relevante p/ vigilância), mas `ProposalCreate` **não** tem esses campos hoje → o PDF os receberia nulos (gap a preencher na evolução).
- **Saída:** `proposta_<number>_v<version>.pdf` via HTML.
- **Engine:** **WeasyPrint** (`HTML(string=html).write_pdf`). **Fallback reportlab** gera PDF-placeholder ("Instale weasyprint para PDF completo") se WeasyPrint ausente.
- 🔴 **BUG PRÉ-EXISTENTE:** `import weasyprint` → **ModuleNotFoundError** no container. **Hoje o PDF sai PLACEHOLDER**, não o documento real. (Reporto, não corrijo — fora do escopo deste RO.)
- Sem TODO/NotImplemented; o fallback é gracioso (não quebra, mas degrada).

## 5. `ProposalCreate` (input completo)
Herda `ProposalBase`: `title*, description, proposal_type(=service), client_name*, client_email(|None), client_phone, client_company, client_document, client_address, terms_conditions, payment_terms, payment_conditions, installments(1-120), notes, valid_until`.
Próprios: `opportunity_id, template_id, discount_type, discount_value, discount_reason, taxes, items: list[ProposalItemCreate]`.
**Shape do item (`ProposalItemCreate`):**
```
code?(50), name*(1-255), description?, unit(def "un", 20), quantity(def 1, ≥0),
unit_price(def 0, ≥0), discount_percent(def 0, 0-100), is_optional(False), sort_order(0)
```
➡️ Para "multi-prazo/recorrência" hoje só dá pra expressar via **`unit`="mês"** (texto) + `quantity`/`unit_price` — **sem campo estruturado** de período/recorrência/vigência.

## 6. Consumidores de `proposals.total` (semântica)
| Consumidor | Uso |
|------------|-----|
| `calculate_totals` (writer) | seta `total = Σ item.total − desconto + taxes` |
| `repo.list` (filtro) | `Proposal.total >= min_value` / `<= max_value` (faixa de valor) |
| `repo.get_stats` | `total_value += p.total`, `pending_value += p.total`, `accepted_value += p.total`, avg |
| `crm.followup_proposals` | SELECT `total` para a lista no Telegram |
| `ProposalResponse`/UI | exibe o `total` (campo "Valor") |
- **Todos tratam `total` como "o valor monetário da proposta" (número plano).** **Nenhum** assume semântica anual/única-vs-recorrente.
- ➡️ **Se você preencher `total` com a MENSALIDADE da opção recomendada:** é **tecnicamente consistente** com todos os consumidores (filtro, follow-up, response). **Ressalva (não é bug):** os **stats** (`total_value`/`pending_value`/`accepted_value`/avg) passariam a **somar/medir valores mensais** — se misturados com propostas de valor único, o "valor do pipeline" fica semanticamente misto (reporting, não quebra de código).

---

## Síntese para a evolução (fatos)
- **Recorrência/multi-prazo: inexistente no schema.** proposals/items não têm período/recorrência/vigência/billing. Caminho atual = `unit`="mês" (texto) nos itens. Evoluir "de verdade" exigiria **novas colunas/tabela** (migration) — ex.: `proposal_items.recurrence`/`period_months`, ou um conceito de "opção/plano" por prazo.
- **Templates não compõem itens** (e há 0). Não servem como "bundles" de itens hoje.
- **PDF degradado:** WeasyPrint ausente → placeholder. Instalar weasyprint (dependência) é pré-requisito para PDF real. ProposalData já prevê `cct_value`/`margin_percent`, mas o input (ProposalCreate) não os captura.
- **`total` é seguro de usar como mensalidade** para o follow-up/listagem; só atente aos stats (mistura mensal × único).

---
*Read-only: `\d` de proposal_items/proposals/proposal_templates, leitura de calculate_totals/pdf_generator/ProposalCreate, grep de consumidores de `.total`, `import weasyprint` (só checagem de presença, não execução). Nada escrito em banco/código; nenhum commit/deploy.*
