# F-C.2 pré — Autorização (nome) + ligação cobrança→cliente (READ-ONLY)

- **Data:** 2026-06-09
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Antes de enviar boleto/nota, mapear (a) como **validar quem pede** e (b) como **ligar a cobrança ao cliente**.
- **Veredito:** Vínculo cobrança→cliente **existe na estrutura** (`inter_cobrancas.cliente_id`) mas está **vazio (0 cobranças)** e o `listar` **não filtra por cliente**. Autorização por **nome de pessoa** é **impossível hoje** (contatos vazios) — só razão social/CNPJ.

---

## 1. Autorização por nome — só razão social
- `clients.name` = **razão social** (100%, é o nome do condomínio).
- `financial_contact_name` / `technical_contact_name` = **VAZIOS** (amostragem 0/5).
- ➜ Validar **nome da pessoa** (síndico/responsável) **não dá hoje**. Chaves disponíveis: **CNPJ** (100%, forte) e **razão social** (nome do condomínio).

## 2. `inter_cobrancas` — estrutura pronta, dados zerados
| Coluna | Tipo | Obs |
|--------|------|-----|
| **cliente_id** | uuid | **vínculo cobrança→cliente** — índice `ix_inter_cobrancas_cliente` (⚠️ **sem FK constraint**, ligação soft) |
| pagador | jsonb | provável CNPJ/nome do pagador |
| status | varchar(30) | indexado `ix_inter_cobrancas_status` |
| vencimento | date | indexado `ix_inter_cobrancas_vencimento` |
| valor | numeric(15,2) | |
| url_boleto / pix_copia_cola / linha_digitavel / barcode | text | dados do boleto |
| cobranca_id_inter (UNIQUE), seu_numero (UNIQUE), descricao, raw_payload | | |

- **`total = 0` cobranças** — infra existe, **nada emitido ainda**.
- Outras tabelas Inter no banco: `inter_transactions`, `inter_pix_recebidos`, `inter_conciliacao_folha`, `inter_payments`, `inter_payment_otp/audit`, `inter_transaction_categorias`.

## 3. `cobranca_service` (D6.3) — métodos
`sincronizar_status()`, **`listar(status, vencimento_inicio, vencimento_fim, limit)`**, `emitir(...)`, `estatisticas()`.
- ⚠️ **`listar` NÃO filtra por `cliente_id`/CNPJ** (só status + janela de vencimento). O SELECT **não retorna `cliente_id`** (retorna `pagador`).
- ➜ Para "cobranças do cliente X": **adicionar param `cliente_id`/`cnpj`** (coluna+índice já existem — adição pequena).

## 4. Fluxo "enviar boleto do cliente" — o que falta (fatos)
1. Identificar cliente → **por CNPJ** (viável) → `clients.id`.
2. Buscar cobrança → `inter_cobrancas WHERE cliente_id = :id AND status` (coluna/índice prontos; **`listar` precisaria do filtro**).
3. **Bloqueio de dados:** 0 cobranças — nada a enviar até emitir.
4. **Autorização por nome de pessoa:** indisponível (contatos vazios) — só CNPJ/razão social.

## 5. DECISÕES (suas — não decidi escopo)
1. Autorização: aceitar **CNPJ + razão social** (o que dá hoje) ou exigir **popular nome do responsável** antes?
2. Adicionar filtro **`cliente_id`/`cnpj`** (e retorno de `cliente_id`) ao `cobranca_service.listar`?
3. Como `cliente_id` é preenchido no `emitir`? Confirmar a origem do vínculo antes de confiar nele (sem dados para validar hoje).

---
*Read-only: `select` em clients, `\d inter_cobrancas` + contagens, leitura de `cobranca_service.listar`, `find/grep` em `modules/integrations/inter`. Nada implementado. Escopo aguardando sua definição.*
