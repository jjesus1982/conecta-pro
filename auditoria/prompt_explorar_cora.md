# Prompt exploratório — Cora API: fechar a lacuna que temos contra o Banco Inter

> Cole isto no agente que está navegando em `https://app.cora.com.br/integracoes` e na
> documentação da API do Cora. **Objetivo: descobrir se dá para fazer pelo Cora o que já
> fazemos pelo Inter.** A pergunta central está na seção 3.

---

## 1. Contexto

Somos a **Conecta Mais**, empresa de portaria e segurança em Manaus, com dois CNPJs e uma
conta em cada banco:

| | CNPJ | banco | papel |
|---|---|---|---|
| Conecta Mais **Eletrônica** | 35.710.481/0001-03 | **Banco Inter** | segurança eletrônica |
| Conecta Mais **Patrimonial** | 66.014.833/0001-10 | **Cora** | portaria humanizada |

Temos um ERP próprio (FastAPI + PostgreSQL) que já integra os **dois** bancos por API:
extrato, conciliação, cobrança e pagamento. O ERP é a fonte da verdade contábil — todo
movimento bancário vira lançamento no razão.

**O problema que queremos resolver:** medimos agosto/2026 e **99,8% do dinheiro que sai da
conta Cora sai por PIX** (R$137.211,88 de R$137.456,78, em 88 de 90 saídas). E a API do
Cora, até onde encontramos, **não envia PIX por chave**. Resultado: 88% do dinheiro da
empresa sai pelo **app do celular**, fora do sistema — sem trilha, sem categoria, sem
conciliação automática. Pelo Inter isso não acontece, porque lá o PIX de saída é API.

---

## 2. O que JÁ funciona no Cora (não precisa explorar — já está no ar)

Autenticação: **mTLS** (certificado + chave emitidos pelo Cora) + `client_id`,
`grant_type=client_credentials` em `POST /token`.
Base: `https://matls-clients.api.cora.com.br`

| operação | endpoint | status |
|---|---|---|
| Saldo | `GET /third-party/account/balance` | ✅ em produção |
| Extrato paginado | `GET /bank-statement/statement` (valores em centavos, `entries[].transaction.type` traz PIX/TRANSFER/PAYMENT/FEE) | ✅ |
| Emitir cobrança (boleto + PIX) | `POST /v2/invoices/` — com `code` nosso ecoado e `Idempotency-Key` | ✅ |
| Consultar / cancelar cobrança | `GET /v2/invoices/{id}` · cancelamento | ✅ |
| **Pagar boleto por linha digitável** | `POST /payments/initiate` | ✅ **provado hoje** (13/08/2026) |
| Pagar DARF | `POST /payments/darf/initiate` | ✅ |
| Pagar GPS/INSS | `POST /payments/gps/initiate` | ✅ |
| Transferência (TED) | implementado no adapter | ✅ |
| Webhooks | invoice + payment | ✅ recebendo |

⚠️ Observado na prática: pagamento criado pela API volta `INITIATED` e **exige aprovação no
app do Cora**. Depois de aprovado, `GET /payments/{id}` passa a devolver **404**.

---

## 3. ⭐ AS PERGUNTAS QUE PRECISAMOS RESPONDER

### 3.1 PIX de saída por chave — o buraco principal

Pelo **Inter** fazemos, e é o que queremos replicar:

- `POST /banking/v2/pix` — **enviar PIX por chave** (CPF/CNPJ, e-mail, telefone, aleatória)
- `GET /pix/v2/dict/key` — **validar a chave antes de enviar** (confere nome/documento do
  favorecido; é o que nos protege de pagar a pessoa errada)
- `GET /banking/v2/pix/{codigo_solicitacao}` — consultar o status do PIX enviado

**Perguntar/descobrir no Cora:**
1. Existe **algum** endpoint de PIX de saída (por chave, por QR Code / copia-e-cola, ou por
   dados bancários completos)? Se existir, qual o caminho, payload e escopo?
2. Se não existe por chave, existe **PIX por QR Code / EMV copia-e-cola**? Para nós isso já
   resolveria boa parte: pagaríamos fornecedor lendo o QR.
3. Existe **validação de chave PIX** (equivalente ao DICT do Inter)? Sem isso, mesmo que o
   envio exista, perdemos a proteção contra favorecido errado.
4. O PIX de saída é um **produto/escopo separado** que precisa ser habilitado no painel de
   integrações, num plano diferente, ou por solicitação ao gerente? (É a hipótese mais
   provável: o endpoint pode existir e nosso certificado não ter o escopo.)

### 3.2 Status do pagamento depois da aprovação

Hoje, aprovado no app → `GET /payments/{id}` devolve 404, e ficamos sem saber se liquidou
até o extrato do dia seguinte.

5. Existe endpoint para **consultar pagamento aprovado/liquidado** (histórico, não só a fila
   `INITIATED`)?
6. Existe endpoint de **agendados** (`scheduled`)? Pagamos um boleto às 20h47 e queremos
   saber se ficou agendado para o próximo dia útil ou se foi recusado.
7. O **webhook de payment** dispara em quais eventos (aprovado, liquidado, recusado,
   cancelado)? Qual o payload? Precisamos disso para fechar o ciclo sem depender do extrato.

### 3.3 Aprovação no app: dá para dispensar?

8. É possível configurar a conta/certificado para que pagamento iniciado por API **liquide
   sem aprovação manual no app** — por exemplo com alçada por valor, ou um "usuário API" com
   permissão de aprovação? (No Inter, o pagamento por API liquida direto; nosso controle é o
   OTP do nosso próprio sistema.)
9. Existe **alçada/limite por API** configurável (teto diário, por operação)?

### 3.4 Coisas menores que fariam diferença

10. O extrato devolve o **identificador do pagamento** (`pay_...`) na linha correspondente?
    Hoje casamos por valor e data, que é frágil.
11. Existe **listagem de boletos a pagar / DDA** (boletos emitidos contra nosso CNPJ)? Isso
    nos deixaria montar contas a pagar sem digitar linha digitável.
12. A cobrança emitida (`/v2/invoices/`) devolve o `code` no **webhook de recebimento**?
    (Queremos conciliar recebimento com o título automaticamente.)

---

## 4. O que fazemos pelo Inter (referência do que é "completo")

Para calibrar o que estamos pedindo — este é o conjunto que consideramos fechado:

**Autenticação:** mTLS (certificado + chave) + OAuth2 em `/oauth/v2/token`, com escopos por
operação.

**Dinheiro que entra**
- `POST /cobranca/v3/cobrancas` — emitir boleto (devolve linha digitável, PDF e PIX copia-e-cola)
- `GET`/`cancelar` boleto
- `POST /pix/v2/cobv` — cobrança PIX com vencimento
- PIX recebidos + **devolução de PIX**
- Webhooks de PIX e de boleto

**Dinheiro que sai**
- `POST /banking/v2/pix` — **PIX por chave** ⭐
- `GET /pix/v2/dict/key` — **validar chave antes** ⭐
- `POST /banking/v2/pagamento` — boleto/código de barras
- `POST /banking/v2/pagamento/darf` e `/tributos`
- `POST /banking/v2/pagamento/lote` — **lote** (pagar vários de uma vez)
- `POST /banking/v2/transferencia` — TED
- `GET /banking/v2/pagamento/{id}` — status do pagamento ⭐

**Leitura**
- `GET /banking/v2/saldo` e `GET /banking/v2/extrato`

---

## 5. Formato da resposta que queremos

Para cada pergunta de 1 a 12: **sim/não**, e se sim:

- endpoint (método + caminho), payload mínimo e resposta
- escopo/permissão necessária e **onde se habilita** (painel de integrações, plano,
  solicitação ao gerente)
- se é GA, beta ou roadmap — e, se roadmap, prazo informado

Ao final, uma conclusão direta: **o que dá para fazer hoje pelo Cora que ainda não fazemos,
e o que continua impossível.** Se PIX de saída não existir de forma alguma, diga isso com
clareza — essa resposta também tem valor: significa que a decisão passa a ser mover a saída
de dinheiro para a conta do Inter.

**Não invente endpoint.** Se não achar na documentação ou no painel, escreva "não
encontrado" em vez de supor um caminho plausível.
