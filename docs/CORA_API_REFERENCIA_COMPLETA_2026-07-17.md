# BANCO CORA — REFERÊNCIA COMPLETA DA API (Integração Direta)

**Data da leitura:** 2026-07-17 · **Fonte:** 100% do portal developers.cora.com.br (Home + todas as
páginas /docs + Termos + as 36 páginas /reference, enumeradas via `llms.txt`) · **Uso:** fonte única
para implementar o `CoraAdapter` (Etapa E4 do `PLANO_EXECUCAO_MULTI_CNPJ_2026-07-17.md`).
**Modalidade nossa:** Integração Direta ("Cliente Direto" — ERP próprio na própria conta PJ).

---

## 1. FUNDAÇÃO

### 1.1 URLs base
| Ambiente | Integração Direta (mTLS) — A NOSSA | Parceria Cora (não usar) |
|---|---|---|
| Stage | `https://matls-clients.api.stage.cora.com.br/` | `https://api.stage.cora.com.br/` |
| Produção | `https://matls-clients.api.cora.com.br/` | `https://api.cora.com.br/` |

Os exemplos da doc usam o host de Parceria; na Integração Direta troca-se SÓ o host, mantendo o path.

### 1.2 Credenciamento (autoatendimento)
- App/Cora Web → **Conta → Integrações via APIs** → gera **Client-ID** (`int-<hash>`) + zip com
  `certificate.pem` + `private-key.key` (emitidos PELA Cora — não é nosso cert A1).
- **Par de cert/key DIFERENTE por ambiente** (stage ≠ produção). Duas contas de teste chegam POR
  E-MAIL no início da integração.
- **Requisito comercial: assinatura CoraPro R$44,90/mês.**
- Validade do certificado mTLS: **NÃO documentada** — confirmar com suporteapi@cora.com.br e
  monitorar/rotacionar por conta própria.

### 1.3 Autenticação (o nosso fluxo)
```bash
curl --cert certificate.pem --key private-key.key \
  --header 'Content-Type: application/x-www-form-urlencoded' \
  -X POST 'https://matls-clients.api.stage.cora.com.br/token' \
  -d 'grant_type=client_credentials&client_id=seu_client_id'
```
- **Sem client_secret, sem Basic auth** — a autenticação É o mTLS + client_id.
- Resposta: `access_token` (JWT RS256, Keycloak), `expires_in: 86400` (**24h** — Inter é 1h),
  `refresh_expires_in: 0` (**não há refresh token** — renovar = repetir a chamada), `scope: offline_access`.
- **mTLS em TODAS as requisições**, não só no /token. Python/httpx: `cert=(cert_path, key_path)`.

### 1.4 Convenções globais
- **Valores em CENTAVOS (Integer)** — R$10,01 = `1001`. (Inter usa decimal — atenção na conversão!)
- Cobrança mínima: **R$5,00 (500)**.
- `Idempotency-Key: <UUID>` **obrigatório em todo POST/DELETE transacional**.
- Datas: request `YYYY-MM-DD`; response ISO `YYYY-MM-DDTHH:MM:SS`.
- Paginação: `page` (inicia em **0** nos docs gerais; **1** na consulta de boletos — conferir por
  endpoint!) + `size`/`perPage`.
- Erros: `{code, message, errors[]}` — `invalid_request` 400, `server_error` 5xx, 401 `{"error":"access_denied"}`
  (típico de credencial do ambiente errado).
- Banco Cora: código **403**, agência sempre **0001**.
- Rate limits: **não publicados** (só: extrato com `perPage`>~500 → 503/504).

---

## 2. CONTA

| Endpoint | Método/Path | Retorno |
|---|---|---|
| Dados da conta | `GET /third-party/account/` | `{agency:"0001", accountNumber, accountDigit, bankCode:"403", bankName:"Cora SCD"}` |
| Saldo | `GET /third-party/account/balance` | `{balance: <Int centavos>}` |
| Extrato | `GET /bank-statement/statement` | ver abaixo |

**Extrato** — params: `start`/`end` (`YYYY-MM-DD`), `type` (`CREDIT`\|`DEBIT`), `transaction_type`
(`TRANSFER`\|`PAYMENT`\|`PIX`\|`FEE`), `page` (default 1), `perPage` (default 10, **manter <500**),
`aggr` (bool → `creditTotal`/`debitTotal`).
Response: `start/end {date, balance}` (saldo inicial/final do período), `entries[]`:
`{id: ent_..., type, amount, createdAt, transaction: {id: trx_..., type, description, counterParty: {name, identity}}}`,
`header {businessName, businessDocument}`.
⚠️ **Data inválida ("2023-04-31") retorna 500, não 400** — validar antes de chamar.
Conciliação: `entry.id`/`transaction.id` = chave idempotente (análogo ao nosso `| e2e:` do Inter).

---

## 3. COBRANÇA (recebimento) — invoices v2 (v1 não existe mais)

### 3.1 Emissão de boleto + PIX ("bolepix") — `POST /v2/invoices/`
Headers: `Idempotency-Key` (obrig.), `Authorization: Bearer`, `Content-Type: application/json`.

Request:
- `code` (String, opc.) — **NOSSO id de conciliação** (equivalente ao `seuNumero` do Inter), ecoado nas consultas.
- `customer` (obrig.): `name` (≤60), `email` (≤60, opc.), `document{identity (só dígitos), type CPF|CNPJ}`,
  `address` (opc.; se enviado, street/number/district/city/state/complement/zip_code obrigatórios).
- `services[]` (obrig.): `{name (obrig.), description (obrig., ≤100), amount (Int centavos, total ≥500)}`.
- `payment_terms` (obrig.): `due_date` (obrig., hoje ou futuro); `fine{date, amount (fixo centavos — TEM
  PRECEDÊNCIA sobre rate), rate (%)}`; `interest{rate}` (% ao mês, cobrado por dia pós-vencimento);
  `discount{type FIXED|PERCENT, value}` (vale até 1 dia ANTES do vencimento).
- `notification` (opc.): `name` + `channels[]{channel EMAIL|SMS (SMS=só CoraPro), contact, rules[]}`.
  Regras: `NOTIFY_{FIFTEEN|TEN|SEVEN|FIVE|TWO}_DAYS_BEFORE_DUE_DATE`, `NOTIFY_ON_DUE_DATE`,
  `NOTIFY_{TWO|FIVE|SEVEN|TEN|FIFTEEN}_DAYS_AFTER_DUE_DATE`, `NOTIFY_WHEN_PAID`.
- `payment_forms`: `["BANK_SLIP","PIX"]` (híbrido) · `["PIX"]` (só QR) · `["BANK_SLIP"]`.

Response 200: `id (inv_...)`, `status`, `total_amount`, `total_paid`, `occurrence_date`, `code`,
`payment_options.bank_slip {barcode(44), digitable(47), our_number, registered, url (PDF permanente no GCS)}`,
`payments[] {id, status, method BANK_SLIP|PIX, total_paid, interest, fine, finalized_at, order}`,
`pix.emv` (copia-e-cola **cobv** — mesmo formato que já resolvemos no caso Sólides).

**Status do boleto:** `DRAFT → OPEN → IN_PAYMENT → PAID` · `LATE` (vencido) · `CANCELLED` ·
`INITIATED` · `RECURRENCE_DRAFT`.

Regras de ouro: QR PIX exige **chave PIX cadastrada na conta**; **PIX pago cancela automaticamente o
código de barras** (sem baixa manual como no Inter); notificações e-mail são grátis e geridas pela Cora.

### 3.2 Carnê (parcelado) — `POST /v2/invoices/installments`
`installment.number_of` 2–24; `service.amount` = TOTAL (dividido pelas parcelas); vencimentos por
`day_of_month` OU `dates[]` (um dos dois, senão 422); `customer.email` OBRIGATÓRIO aqui;
**`payment_forms` só `["BANK_SLIP"]`** (PIX em carnê → erro `INS-0001`). Response traz `document_url`
(PDF do carnê) + `result[]` por parcela. ⚠️ Resposta pode levar ~40s; só a 1ª parcela registra na
hora (demais ~1min, assíncrono).

### 3.3 Consultas e cancelamento
- **Lista**: `GET /v2/invoices/?start&end&state&search&page&perPage(max 200)` — `start/end` filtram por
  VENCIMENTO, **exceto com `state=PAID`, quando filtram por DATA DE PAGAMENTO** (→ é o pull de
  recebidos, com `fine_paid`/`interest_paid`/`discount_paid` discriminados).
- **Detalhe**: `GET /v2/invoices/{invoice_id}` — 404 se não existir OU não for da nossa conta.
- **Cancelar**: `DELETE /v2/invoices/{invoice_id}` → 204; `REC-0006` = já pago.
- **Notificações**: `GET /v2/invoices/{id}/notifications` (status SUCCESS/SCHEDULED/TRIGGERED) ·
  `DELETE .../notifications` (cancela). **Não existe editar/reenviar** — cancelar e reemitir.

---

## 4. SAÍDA DE DINHEIRO (pagamentos/transferências)

⚠️ **REGRA NATIVA DA CORA: toda saída iniciada por API fica `INITIATED` até APROVAÇÃO NO APP** (celular
do titular). A API só inicia; o app aprova/reprova; o webhook fecha o loop. `payment_terms.due_date` =
prazo-limite para aprovar. O gate humano de dinheiro-que-sai vira o próprio app da Cora.

### 4.1 Pagar boleto — `POST /payments/initiate`
Request: `digitable_line` (obrig.), `code` (opc., nosso id), `scheduled_at` (opc.).
Response 201: `id (pay_...)`, `status: INITIATED`, `amount` (centavos, já com juros/multa/desconto),
`creditor {name, document, type}`, `bank_slip {barcode, digitable, registered, fine, interest, ...}`,
`payment_terms {due_date}`.
Erros: `PAY-0001` (agendado não pagável), `REC-0001` (boleto não registrado na CIP), `REC-0007`
(boleto emitido pela própria conta).

### 4.2 DARF — `POST /payments/darf/initiate`
`data {name, code (receita 4-5 díg.), identity, type:"DARF", reference_date, due_date, scheduled_at?,
amount {main (obrig.), fine?, interest?}}` — DARF SEM código de barras (dados estruturados).

### 4.3 GPS — `POST /payments/gps/initiate`
`data {name, code (ex 2100), identity, identification_type NIT|PASEP|PIS, competence "aaaa-mm",
scheduled_at?, amount {other_entity, inss, charge}}` — os 3 amounts obrigatórios mesmo zerados.

### 4.4 Transferência (TED) — `POST /transfers/initiate`
**NÃO EXISTE PIX DE SAÍDA POR CHAVE/COPIA-E-COLA NA API** — transferência é por dados bancários:
`destination {bank_code, account_number (COM dígito, ≤13), branch_number (≤4), holder {name,
document {identity, type?}}, account_type CHECKING|SAVINGS|PAYMENT}`, `amount`, `description?`,
`code?`, `category?` (PAYROLL, TAXES, RENT...), **`scheduled`** (não `scheduled_at`!).
Response **200**: `id (trn_...)`, `status: INITIATED`; a resposta separa `account_number`/`account_number_digit`.
⚠️ Banco inexistente → **500** (não 400). Não há cancelamento de transferência via API (reprovar no app).

### 4.5 Consultas
- `GET /payments/?status=INITIATED&start&end&page&size` — **só enxerga INITIATED**; aprovado/reprovado
  SOME da lista (acompanhar por webhook/extrato). Doc admite bugs no filtro por status/datas.
- `DELETE /payments/initiate/{payment_id}` → 204 (só antes da aprovação); `PAY-0006` = não iniciado;
  ⚠️ "não é seu"/inexistente → **500**.
- `GET /transfer/third-party/transfers/?status&start&end` (path DIFERENTE da iniciação!) — status
  evidenciados: `INITIATED`, `COMPLETED` (+ `canceled`/`refunded` via webhook).
- `GET /banks` — lista de bancos (name, ispb, code, short_name).

**Fluxo de estados (reconstruído dos webhooks):**
pagamento: `INITIATED → approved|reproved (app) → created/completed | error` ·
transferência: `INITIATED → completed|canceled → (refunded)`.

---

## 5. WEBHOOKS

- **Criar**: `POST /endpoints/` `{url, resource, trigger}` (+Idempotency-Key) → `{id: end_..., active: true,
  connectionTimeout: 1000, readTimeout: 2000}`.
- **Listar**: `GET /endpoints/` · **Excluir**: `DELETE /endpoints/{id}` (422 se não for nosso).
  **Não existe atualização** — delete + create.
- **Recursos × triggers**:
  - `invoice`: drafted · created · paid · canceled · overdue · `*`
  - `transfer`: completed · canceled · refunded · `*`
  - `payment`: initiated · created · **approved** · **reproved** · completed · error · `*`
  - `register`: completed (Parceria) · `service_receipt` (NFS-e): issued · cancelled · cancel_error · error
- **Formato da notificação: POST com CORPO VAZIO** — tudo nos headers:
  `webhook-event-id` · `webhook-event-type` (`resource.trigger`, ex `invoice.paid`) ·
  `webhook-resource-id` (`inv_/pay_/trn_/nfse_...`). Responder 200.
- ⚠️ **SEM assinatura/HMAC/allowlist documentados e SEM política de retry documentada** →
  REGRA DO ADAPTER: webhook é só GATILHO — sempre re-consultar o recurso pela API autenticada antes
  de conciliar (nosso princípio "valor exibido == fato no banco"), e manter polling de reconciliação
  como rede de segurança contra evento perdido.

---

## 6. NFS-e VIA CORA (existe, mas com modelo próprio)

**Modelo: a NFS-e da Cora é SEMPRE atrelada a uma cobrança (invoice) — 1 nota por cobrança, sem
emissão avulsa.** Útil como plano B/complemento; NÃO substitui nossa emissão via prefeitura/ADN.

- Cidades: `GET /fiscal-receipts/available-cities` (`ibgeCode`, exige certificado?, `allowCancellation`).
- Disponibilidade: `GET /fiscal-receipts/businesses/check-availability`.
- Cadastro emissor: `POST /fiscal-receipts/issuer` `{municipal_register, state_register?, tax_regime
  (SIMPLES_NACIONAL | NORMAL_LUCRO_REAL | ...), special_tax_regime (NONE...), rps {last_number, serie}}`.
- Certificado: `POST /fiscal-receipts/credentials` (multipart) — **arquivo .pem** (nosso A1 é .pfx →
  converter), senha, login/senha da prefeitura se exigidos.
- CNAEs: `GET /fiscal-receipts/businesses/cnaes` · Códigos de serviço: `GET .../service-codes` (LC 116).
- Emissão: `POST /fiscal-receipts/service-receipt` `{receivable {id: inv_..., type: "INVOICE"},
  fiscal_receipt {type: "NFSE", trigger ON_OPEN|ON_PAYMENT, cnae, service_code, municipal_tax_code,
  description, customer {email obrig. + address}, tax {iss {value ("500"=5%!), withheld}}}` →
  `{id: nfse_..., status: WAITING_TRIGGER}`. 1 nota/cobrança (`FR-020`).
- Status: `COMPLETED` · `WAITING_TRIGGER` · `WAITING_CERTIFICATE` · `ERROR` · `REQUESTED`.
- Consulta: `GET /fiscal-receipt-api/service-receipt/{id}` (retorna XML+PDF URLs).
- Edição: `PATCH /fiscal-receipts/service-receipt` (só WAITING_*/ERROR; `FR-018` se emitida).
- Cancelamento: `DELETE /fiscal-receipts/service-receipt/{id}` — **depende da cidade permitir**
  (`allowCancellation`); senão, só no portal da prefeitura.

---

## 7. STAGE (sandbox)

- Ambiente completo; contas de teste chegam por e-mail; credenciais próprias.
- **Inserir saldo**: emitir boleto pela conta A e pagá-lo pela conta B com
  `POST /v2/invoices/pay` `{id: inv_...}` (EXCLUSIVO de stage). Auto-pagamento é bloqueado
  (`REC-0007`). Dispara o fluxo real: status→PAID, webhook `invoice.paid`, entrada no extrato.
- O "Try it" do portal não suporta mTLS — testar por cURL/httpx/Postman.

## 8. TERMOS DE USO (o que nos obriga)

- Tarifas: TED R$2,00 · boleto código de barras R$1,70 · boleto via PIX R$0,50 (1% até R$49,99) ·
  cancelamento R$0,30. CoraPro R$44,90/mês.
- Aprovação da integração vale **12 meses com prorrogação tácita**; Cora pode exigir política de
  segurança cibernética e demonstração técnica.
- Uso permitido: exatamente o nosso (ERP próprio, conta própria). PROIBIDO: BaaS/plataforma para terceiros.
- Cora pode **suspender/descontinuar a qualquer tempo sem aviso e sem indenização**; "não está
  obrigada a fornecer suporte" → reforça a necessidade do nosso modo-manual de fallback.
- Compartilhar credenciais = bloqueio; incidente deve ser notificado imediatamente.
- Confidencialidade sobre tudo que trafega; foro São Paulo-SP.

## 9. GOTCHAS CONSOLIDADOS (checklist do CoraAdapter)

1. Centavos everywhere; ISS como inteiro ×100 ("500"=5%).
2. Idempotency-Key UUID em todo POST/DELETE transacional.
3. Gate humano NATIVO (app) para toda saída; nosso OTP vira camada complementar; loop fecha por webhook.
4. Sem PIX de saída por chave → folha/diaristas: transferência com dados bancários completos OU
   padrão "pago pelo app + conciliação".
5. Webhook: corpo vazio, sem assinatura, sem retry documentado → re-consultar sempre + polling.
6. Erros atípicos: data inválida no extrato = 500; banco inexistente = 500; "não é seu" = 500/422.
7. Casing inconsistente na doc: `total_items` vs `totalItems`/`hasMore`; `zip_code` vs `zipcode`;
   `scheduled_at` vs `scheduled`; stage `/invoices/pay` responde em camelCase.
8. `GET /payments/` só vê INITIATED; consulta de boletos pagos = `state=PAID` com datas de pagamento.
9. Carnê: sem PIX, resposta lenta, registro assíncrono das parcelas.
10. Comprovante bancário via API: NÃO existe → gerar o nosso (padrão-ouro) a partir de
    webhook + extrato + consulta do recurso.
11. Cert mTLS da Cora ≠ nosso cert A1; validade não documentada (perguntar ao suporte); pares
    distintos stage/produção.
12. Cancelamento de notificação existe; edição não (cancelar boleto e reemitir).
