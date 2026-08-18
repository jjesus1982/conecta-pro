# Asaas — o que a documentação REALMENTE diz

Documentação navegada com navegador ao vivo em **18/08/2026** (`docs.asaas.com`), 505
endpoints na referência. Cada afirmação abaixo veio da página, não da minha memória.

Isto existe porque eu já escrevi um adapter de cabeça e a documentação desmentiu **dois**
pontos — os dois no caminho do dinheiro. Está registrado na seção "Erros que eu cometi".

---

## 1. Autenticação

Chave de API no header **`access_token`**. Sem OAuth2, sem mTLS, sem renovação de token
— diferente de Inter (OAuth2 + certificado) e Efí (idem). É um padrão a menos para manter.

```
access_token: $aact_...
Content-Type: application/json
```

Ambientes:
| | URL |
|---|---|
| Sandbox | `https://api-sandbox.asaas.com/v3` |
| Produção | `https://api.asaas.com/v3` |

A chave de sandbox e a de produção são **diferentes** e não se cruzam. Sandbox tem dados
próprios e não move dinheiro real.

---

## 2. Os endpoints que nos interessam

| Método | Caminho | Para quê |
|---|---|---|
| GET | `/v3/pix/addressKeys/external?type=&key=` | **consultar chave PIX de terceiro** |
| POST | `/v3/transfers` | transferência (PIX ou TED) |
| GET | `/v3/transfers/{id}` | status de uma transferência |
| POST | `/v3/transfers/{id}/cancel` | cancelar |
| GET | `/v3/finance/balance` | saldo |
| GET | `/v3/financialTransactions` | extrato (conciliação) |
| GET | `/v3/pix/transactions?endToEndIdentifier=` | achar a transação pelo E2E do Bacen |

### 2.1 Consulta de chave — o motivo de a Asaas ter entrado

É isto que o app do banco faz e o nosso sistema não fazia: digitar a chave e ver o nome
do titular **antes** de mandar o dinheiro.

`GET /v3/pix/addressKeys/external` com **query params**:
- `type` — enum: `CPF` · `CNPJ` · `EMAIL` · `PHONE` · `EVP`
- `key` — a chave

Devolve `ownerName`, `cpfCnpj`, e os dados do banco do favorecido.

> **Comparação honesta:** o `validate_pix_key` do **Inter** aponta para um endpoint que
> responde **404**, engole o erro e devolve `None` — nunca validou nada. Sondei seis
> formatos de endpoint; o escopo `dict.read` existe no catálogo do Inter mas **não está
> liberado para a nossa aplicação**. Pedido em aberto com o gerente.

### 2.2 Transferência

`POST /v3/transfers`:

| Campo | Obrigatório | Observação |
|---|---|---|
| `value` | sim | valor |
| `pixAddressKey` | para PIX | a chave |
| `pixAddressKeyType` | **sim, na prática** | enum CPF/CNPJ/EMAIL/PHONE/EVP |
| `operationType` | sim | `PIX` ou `TED` |
| `description` | não | histórico |
| `scheduleDate` | não | agendamento |
| `externalReference` | não | **nosso** identificador |
| `recurring` | não | recorrência |

---

## 3. Riscos operacionais — o que muda o desenho do código

### 3.1 ⚠️ Idempotência do envio NÃO é documentada

Procurei "idempot" nos 505 endpoints: **zero ocorrências**. A Efí prometia explicitamente
("reenviar o mesmo `idEnvio` garante que nenhum valor seja debitado mais de uma vez"); a
Asaas **não faz essa promessa em lugar nenhum**. O `externalReference` é um identificador
nosso, sem compromisso de deduplicação declarado.

**Por que isso não é detalhe:** num lote de 54 pagamentos de folha, um timeout no meio
deixa sem saber se aquela pessoa recebeu. Reenviar pode pagar duas vezes.

**Como o adapter trata:** `enviar_pix(confirmar_antes=True)` consulta antes de reenviar,
usando `buscar_por_referencia`. Até a Asaas confirmar por escrito, é assim que fica.

**→ Pergunta a fazer por escrito à Asaas:** *o reenvio de um `POST /transfers` com o mesmo
`externalReference` é deduplicado, ou cria uma segunda transferência?*

### 3.2 ⚠️ Webhook: a fila é INTERROMPIDA após 15 falhas seguidas

Três coisas na mesma página, e as três mudam o desenho:

1. **Entrega "at least once"** — o mesmo evento pode chegar **mais de uma vez**. O nosso
   handler tem que ser idempotente (chave: id do evento).
2. **15 respostas não-2xx consecutivas interrompem a fila.** Os eventos continuam a ser
   gerados e **não chegam**. Reativação manual (`interrupted: false`).
3. **Evento parado há mais de 14 dias é apagado para sempre.** Se a fila interromper numa
   sexta e ninguém olhar, perde-se a confirmação de pagamentos.

**Consequência de desenho, não opcional:** o endpoint de webhook responde **2xx
imediatamente** e enfileira o processamento. Nunca processa de forma síncrona — uma
exceção no meio do nosso código vira 500, e 15 delas cortam a torneira de eventos.

E, como a fila pode cair sem avisar, o webhook **não pode ser a única fonte de verdade**:
precisa de um sincronizador que puxe `/financialTransactions` periodicamente.

### 3.3 ⚠️ Cota: 25.000 requisições por conta a cada 12 horas

Além do rate limit por endpoint (cabeçalhos `RateLimit-Limit` / `RateLimit-Remaining` /
`RateLimit-Reset`, **429** ao estourar).

Conta da nossa folha: consultar a chave antes de cada envio gasta **duas** chamadas por
pessoa. 54 funcionários = 108. Folgado — mas um retry cego em loop não é.

**→ Pergunta a fazer por escrito à Asaas:** *qual o limite diário de valor enviado?* A
folha da Patrimonial é ~R$95k/mês.

### 3.4 GET com body devolve 403

Está na página de códigos HTTP. Uma armadilha silenciosa: o `httpx` aceita mandar body em
GET sem reclamar, e a Asaas responde **403 Forbidden** — que se lê como problema de
permissão, e se perde meia hora procurando no lugar errado.

---

## 4. Os 7 eventos de transferência

`TRANSFER_CREATED` · `TRANSFER_PENDING` · `TRANSFER_IN_BANK_PROCESSING` ·
`TRANSFER_BLOCKED` · `TRANSFER_DONE` · `TRANSFER_FAILED` · `TRANSFER_CANCELLED`

Mapeamento para o vocabulário dos nossos adapters (`STATUS_ASAAS`):

| Asaas | Nosso | Por quê |
|---|---|---|
| `PENDING` | PENDING | |
| `BANK_PROCESSING` / `IN_BANK_PROCESSING` | PROCESSING | |
| **`BLOCKED`** | **PENDING** | bloqueado é análise em curso, **não** fracasso |
| `DONE` | COMPLETED | |
| `FAILED` | FAILED | |
| `CANCELLED` | CANCELLED | |

`BLOCKED → PENDING` é deliberado. Tratar bloqueio como FAILED faria o sistema desistir de
um pagamento que ainda pode sair — e alguém pagaria de novo. Pagamento duplicado.

---

## 5. Erros que eu cometi e a documentação corrigiu

Registrados porque são exatamente o tipo de coisa que "parece certo" e sai errado:

| O que eu tinha escrito | O que a API é |
|---|---|
| `GET /pix/addressKeys/{key}` — chave no path | caminho **fixo** `/pix/addressKeys/external` com query params `type` e `key` |
| `POST /transfers` sem `pixAddressKeyType` | o tipo é campo **próprio e obrigatório** |

O segundo é o perigoso. Sem o tipo, a Asaas precisa adivinhar o que é a chave — e uma
chave de **telefone** com 11 dígitos "parece" um **CPF**. Adivinhar errado é pagar a
pessoa errada. Por isso o adapter agora deduz o tipo com `tipo_de_chave()` e manda
explícito (ordem: e-mail → telefone → CNPJ → CPF → EVP).

---

## 5.1 PROVADO contra a API (sandbox, 18/08/2026)

Isto não é leitura de documentação — é resposta da API real, com chave
`$aact_hmlg_`. O que está aqui, está verificado.

| Degrau | Resultado |
|---|---|
| Autenticação (`/finance/balance`) | ✅ 200 |
| Consulta de chave que **existe** | ✅ 200 com titular |
| Consulta de chave que **não existe** | ✅ 404 corpo vazio → `ChavePixInvalida` |
| Consulta de chave **malformada** | ✅ 400 com JSON explicando |
| Envio (`POST /transfers`) | ⚠️ passou a validação inteira, parou em **saldo insuficiente** |
| Status / `buscar_por_referencia` | ❌ não provado — depende do envio |

**A consulta de chave funciona, e é o que motivou a Asaas entrar.** Resposta real:

```
owner.name    = CONECTAMAIS PATRIMONIAL LTDA
owner.cpfCnpj = 66.014.833/0001-10
financialInstitution.name = ASAAS GESTÃO FINANCEIRA IP S.A.  (código 461)
```

⚠️ **A conta de sandbox está no CNPJ da Patrimonial** — o certo, o que tem os
funcionários. Confirmar que a de **produção** também está, antes do go-live.

### Dois erros MEUS que só a API revelou

A documentação não mostra o corpo da resposta; eu tinha suposto os nomes dos campos:

1. **`ownerName` não existe no topo** — o titular vem em `owner.name`. Eu lia o campo de
   topo primeiro, com o aninhado só como reserva. Funcionava por acidente.
2. **`bank`/`bankName` não existem** — a instituição vem em `financialInstitution`. Esse
   eu lia **errado sem reserva nenhuma**: o campo voltava vazio e o operador não veria o
   banco do favorecido na hora de conferir.

### Por que o envio não ficou provado

Conta de sandbox nova tem saldo R$0. Tentei creditar:

- `receiveInCash` → 200, mas é recebimento **fora** do Asaas: não credita saldo
- `POST /payments/{id}/confirm` → 404, não existe
- cobrança paga com cartão de teste → ✅ `CONFIRMED`, líquido R$489,56, mas
  **crédito previsto para 21/09/2026** (D+30). Não serve para hoje.

O 400 do envio foi **`"Saldo insuficiente para realizar a operação."`** — ou seja, o
payload passou por toda a validação (chave, tipo de chave, tipo de operação) e parou só
no saldo. O formato do envio está certo; falta dinheiro na conta de teste para ver a
transferência nascer e mudar de status.

**Caminho para fechar:** ou esperar o crédito de 21/09 no sandbox, ou provar em produção
com R$0,01 sob sua supervisão, depois que a conta de produção tiver saldo.

---

## 6. Estado atual no Conecta PRO

**Feito:**
- `backend/modules/integrations/banking/adapters/asaas.py` — corrigido contra a doc real
- Migration `b4c5d6e7f8a9` **aplicada**: conta `1.1.1.04 Asaas IP` no plano de contas +
  `'asaas'` no CHECK de `inter_payments.banco`

O CHECK importa: a origem do pagamento viajava dentro de um jsonb sem validação, e o
executor mandava para o **Inter** qualquer valor desconhecido — um typo pagaria pelo CNPJ
errado. Hoje um banco fora da lista é rejeitado pelo banco de dados.

**Falta:**
1. **Chave de API de sandbox** — bloqueia tudo o que segue
2. Braço `'asaas'` no roteador de pagamento (hoje levanta "banco sem executor" — falha
   limpa, mas falha)
3. `asaas_sync_service` — puxa `/financialTransactions` para o extrato/razão
4. Endpoint de webhook, com as três regras da §3.2
5. As duas perguntas por escrito à Asaas (§3.1 e §3.3)

**Nada disso se prova sem a chave de sandbox.** Com ela eu provo a consulta de chave, o
envio e o status contra a API de verdade — antes de qualquer centavo sair.
