# Follow-up pós-orçamento — viabilidade do módulo de propostas (READ-ONLY)

- **Data:** 2026-06-10
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Avaliar se há base real para um follow-up automático de leads/clientes que receberam orçamento/proposta e não responderam.
- **Veredito:** ⚠️ **Código pronto sobre dados vazios/seed.** O subsistema de propostas existe e é rico, mas `proposals` está **vazia (0)**, `opportunities` tem **5 (aparentam seed)**, e **falta a peça de envio/follow-up**. **Não há "orçamento enviado sem resposta" orgânico hoje.**
- **NADA implementado.** Só leitura.

---

## 1. Tabelas + contagem
| Tabela | Linhas | Nota |
|--------|--------|------|
| `proposals` | **0** | schema rico, nunca usada |
| `opportunities` | **5** | tem dados, parecem seed |
| `bidding_opportunities` | (licitações) | domínio separado |

## 2. `opportunities` (5)
- Campos: `title`, `lead_id`, `stage`, `value`, `expected_close_date`, `actual_close_date`. **Sem `cliente_id`**, **sem `sent_at`**.
- Stages: `qualification`(2), `proposal`(2), `negotiation`(1) — todas `is_active`. Os 2 em **`proposal`** seriam candidatos a follow-up.
- ⚠️ **Aparentam SEED:** títulos = clientes reais (Life Centro, Mirante das Flores, Green Hills), mas leads com e-mail `@conectamais.pro` e telefones sequenciais `9299900000X`.
- ✅ Contato presente: os 5 leads têm **phone + email**.

## 3. `proposals` (0) — schema ideal p/ follow-up, vazio
- Campos: `opportunity_id`, `client_name/email/phone`, `total`, `issue_date`, `valid_until`, **`sent_at`**, **`viewed_at`**, status. Perfeito para "enviada e sem resposta/visualização".
- 🔴 **0 linhas** — nenhuma proposta criada.

## 4. Código
- **CRM real e rico:** `modules/crm/` → `proposal`+`opportunity` (model/schema/repo/service/controller) + `pdf_generator` + `signature_integration`. Endpoints: `/api/v1/crm/proposals` (POST, from-opportunity, GET, stats), `/opportunities` (CRUD, stage PATCH, close).
- `modules/comercial/propostas` e `oportunidades` = **stubs vazios (0 bytes)**.
- `proposal_service`: pricing, validade, transições de status, aprovação, `check_expiration`, versionamento, comissão — **sem método de envio/follow-up** (sem `send`/`sent_at`/email).
- `precificacao_controller` (financial): **0 refs de persistência** → **só calculadora**; não cria proposta.

## 5. Veredito honesto
Nem "funciona com dados reais", nem "totalmente quebrado" — **código pronto, dados vazios/seed**:
- Código do subsistema de propostas existe e é rico.
- `proposals` vazia, `opportunities` 5 seed, falta envio/follow-up, precificacao não persiste.
- **Não há, hoje, "orçamento enviado e sem resposta" orgânico** para acionar. Infra existe (`sent_at`/`viewed_at`, stages, contatos), mas não está em uso.

## 6. O que faltaria para o follow-up
1. **Gerar propostas de verdade** (usar `proposals`, preencher `sent_at` ao enviar) **ou** adotar `opportunities.stage='proposal'` + data de envio.
2. **Rotina/gatilho:** `proposals WHERE sent_at < hoje-Xd AND viewed_at IS NULL` (ou opp stale em `proposal`) → contatar lead por WhatsApp (`_send_message`, pronto) ou e-mail (`core/mailer`, validado).
3. `proposal_service` ganhar **envio + marcação `sent_at`** (não existe).
4. **Definir fonte de verdade:** `proposals` (rica, vazia) vs `opportunities` (stage, mas seed, sem data de envio).

## 7. DECISÕES (Jordan)
1. O fluxo de propostas vai ser **realmente usado** (gerar proposta a cada orçamento)? Sem isso, não há o que seguir.
2. Fonte de verdade do follow-up: `proposals` ou `opportunities.stage`?
3. Canal do follow-up: WhatsApp (agente), e-mail, ou ambos?
4. Validar se as 5 opportunities são seed (limpar?) ou se há deals reais a migrar.

---
*Read-only: `information_schema`/contagens de proposals/opportunities, `\d`, distinct stage, join opportunities↔leads (contato), endpoints do app vivo, leitura de `proposal_service.py` e `precificacao_controller.py`. Nada implementado.*
