# Fundação do módulo Propostas (CRM) — mapa factual para lançar 3 propostas reais

- **Data:** 2026-06-10
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Responder com precisão as 6 perguntas, para registrar 3 propostas reais (Amsterdam, Franceses, Parque Imperial) com segurança.
- **Modo:** 100% READ-ONLY (este arquivo é o único output; zero escrita em banco/código/commit/deploy).

---

## STEP 1 — Schema `proposals` (vínculo ao cliente)
**NÃO existe `client_id` nem `lead_id`.** O cliente é gravado como **TEXTO**:
| Campo | Tipo | Obrigatório |
|-------|------|-------------|
| `client_name` | varchar(255) | **SIM (NOT NULL)** |
| `client_document` (CNPJ) | varchar(20) | não |
| `client_email` | varchar(255) | **não — nullable=YES** ✅ (commit `9dfc96dd`) |
| `client_phone` | varchar(20) | não |
| `client_company` | varchar(255) | não |
| `client_address` | text | não |
| `opportunity_id` | uuid | não — **único vínculo relacional** |

FKs reais da tabela: `opportunity_id`→opportunities (ON DELETE SET NULL), `parent_id`→proposals, `template_id`→proposal_templates, `created_by_id`/`approved_by_id`→users. **Nenhuma FK para `clients`/`leads`.**

## STEP 2 — Numeração: IMPOSTA pelo sistema
- `number` varchar(50) **NOT NULL, UNIQUE, sem default no banco**.
- `ProposalCreate` **não tem campo `number`** (o `number:` no schema é só na RESPOSTA).
- Gerado no repositório:
```python
def _generate_proposal_number(self) -> str:
    now = datetime.utcnow()
    return f"PROP-{now.strftime('%Y%m%d')}-{uuid4().hex[:6].upper()}"
# proposal_repository.create:  number=self._generate_proposal_number()
```
➡️ Formato **`PROP-YYYYMMDD-<6 hex maiúsculo>`** (ex.: `PROP-20260610-A1B2C3`). **Não dá para informar 00091/00092/00001.**

## STEP 3 — Form do frontend (`crm/propostas/page.tsx`)
- "Cliente" = **`<Input>` texto livre** ("Nome do cliente") — NÃO é select de clientes (não captura `client_id`). O único `<Select>` é o filtro de status.
- Payload do create: `{ title, client_name, client_email (→null se vazio), total_value, status }`.
- ⚠️ `total_value` **não** é campo do `ProposalCreate` backend → **ignorado**. O form **não** envia `items` (→ total 0) nem `client_document` (CNPJ). Proposta criada pela UI sai "magra": sem itens, sem valor real, sem CNPJ.

## STEP 4 — Status + regra do follow-up
- Enum `ProposalStatus`: `draft, pending_review, pending_approval, approved, sent, viewed, accepted, rejected, expired, cancelled`.
- **`POST /{id}/send`** → `update_status(SENT)`:
```python
proposal.status = status.value          # 'sent'
if status == ProposalStatus.SENT:
    proposal.sent_at = datetime.utcnow()
# responded_at só é setado em ACCEPTED/REJECTED
```
- **Follow-up** (`crm.followup_proposals`):
```sql
SELECT id, number, client_name, client_email, client_phone, total, sent_at
FROM proposals WHERE status='sent' AND responded_at IS NULL AND sent_at IS NOT NULL
```
Cadência: 1º quando `now ≥ sent_at + 2d`; seguintes `≥ último follow-up + 7d` (FOLLOWUP_FIRST_DAYS=2, FOLLOWUP_NEXT_DAYS=7).

## STEP 5 — Os 3 prospects existem? **NÃO**
- CNPJ Amsterdam `29.280.795/0001-10` (`29280795000110`) e Franceses `03.843.564/0001-84` (`03843564000184`): **0** em `clients` e `leads`.
- Por nome (ILIKE Amsterdam/Imperial/Frances/Parque): único hit = **CONDOMINIO PARQUE RESIDENCIAL GELAIN** (CNPJ `00736037000182`) — **outro cliente real, NÃO "Parque Imperial"** (homônimo parcial da palavra "Parque"). Nada de Amsterdam/Imperial/Franceses.
- Totais: **11 clients, 18 leads, 0 proposals**.

---

## STEP 6 — Respostas objetivas

### a) Vincular proposta a prospect que NÃO é cliente — caminhos REAIS
Há **um único** caminho suportado pelo schema+controller: **preencher os campos de TEXTO** da proposta — `client_name` (obrigatório); `client_document`=CNPJ, `client_email`, `client_phone`, `client_company` (opcionais).
- **Não** existe `client_id` nem `lead_id` na tabela → **não** precisa criar lead, **não** precisa promover a cliente, **não** há como "ligar" a um registro existente.
- `opportunity_id` é opcional (e não há opportunity para eles) → deixar nulo.

### b) Numeração
**IMPOSTA** pelo sistema. Formato `PROP-YYYYMMDD-<6 hex>`. Informável: **NÃO**. Para preservar o nº do PDF (00091/00092/00001), embutir em campo livre — **`title`** (recomendado) ou `notes`. Não há `external_id`/`reference` genérico (só `signature_external_id`, de assinatura).

### c) Os 3 existem no CRM?
**NÃO.** Evidência STEP 5: 0 por CNPJ em clients/leads; único quase-match é GELAIN (CNPJ `00736037000182`), que **não** é Parque Imperial.

### d) Recomendação técnica (menor atrito/risco)
Registrar os 3 via **`POST /api/v1/crm/proposals` (curl/API com JWT)** — **não** pela UI (o form atual não envia CNPJ, itens nem valor). Payload por proposta:
- `title` — embutir o nº do PDF (ex.: `"Proposta 00091 — Amsterdam"`), já que `number` é imposto;
- `client_name` (obrigatório), `client_document`=CNPJ, `client_email`/`client_phone` (opcionais);
- `items: [...]` com os itens/valores reais (para `total` ≠ 0);
- **sem** `opportunity_id`, **sem** `number`.
Depois **`POST /{id}/send`** → status=sent + sent_at → entra na cadência de follow-up.
- **Risco único:** `number` gerado (`PROP-2026...`) ≠ números dos PDFs → usar `title`/`notes` para o nº original. Demais fundações OK (prospect por texto aceito; client_email opcional já entregue `9dfc96dd`; create atômico já corrigido `eb60ea82`).

---

## Resumo
- Vínculo cliente = **texto** (sem client_id/lead_id); `client_name` obrigatório, resto opcional; `client_email` já nullable. ✅
- Número **imposto** (`PROP-YYYYMMDD-hex`) — nº do PDF vai no `title`/`notes`. ✅
- Os 3 **não existem** no CRM (Gelain é homônimo, não Parque Imperial). ✅
- **Menor atrito:** POST direto na API com client_name+CNPJ(texto)+items, depois /send. UI atual é insuficiente (sem CNPJ/itens/valor).

*Read-only respeitado: só leitura de schema/código/banco; nenhuma escrita em banco, nenhum commit/deploy. Este .md é o único arquivo gerado.*
