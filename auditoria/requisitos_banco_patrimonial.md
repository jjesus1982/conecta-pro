# O que exigir de um banco para a Conecta Mais Patrimonial

> Checklist derivado do que o ERP **realmente usa hoje** — cada linha aponta o endpoint
> equivalente no Banco Inter, que é o nosso padrão de "completo". Serve para pesquisar
> banco novo e para cobrar do gerente da Cora.
> Medido em 13/08/2026.

## O problema, dimensionado

A conta Patrimonial fica no Cora. Em agosto/2026, **88 das 90 saídas foram PIX**
(R$137.211,88 de R$137.456,78 — 99,8%), e a **API do Cora não envia PIX** (confirmado na
documentação: nem por chave, nem por QR/copia-e-cola; o endpoint de PIX é só de cobrança e
a própria doc diz "não permite a realização de transferência Pix").

**O que NÃO é o problema — e é importante não confundir:** rastreabilidade. O extrato do
Cora devolve `transaction.id`, `type` e `counterParty` (nome + documento), e o ERP já captura
tudo: 91/91 com id, 90/91 com CPF/CNPJ, 89/91 com método, 87/91 já categorizadas. Todo PIX
pago no celular volta identificado e conciliado no dia seguinte.

**O que É o problema:** não existe **controle prévio**. Sem PIX na API, o pagamento nasce no
app do celular — sem o OTP do nosso sistema, sem o teto diário
(`CONECTA_LIMITE_DIARIO_PAGAMENTOS`), sem propor→aprovar. O sistema só descobre depois.

⚠️ **Não resolver isto movendo a saída para o Inter.** São CNPJs diferentes: pagar despesa
da Patrimonial (66.014.833/0001-10) pela conta da Eletrônica (35.710.481/0001-03) joga o
custo no CNPJ errado, distorce a apuração e, se recorrente, é confusão patrimonial.

---

## Bloco 1 — Inegociáveis (é por isto que a troca se justifica)

| # | Requisito | Inter (referência) | Por quê |
|---|---|---|---|
| 1 | **PIX de saída por CHAVE via API** | `POST /banking/v2/pix` | 99,8% da nossa saída. Sem isto nada muda. |
| 2 | **Validação de chave antes de pagar** (DICT) | `GET /pix/v2/dict/key` | Confere nome/documento do favorecido. É o que impede pagar a pessoa errada. |
| 3 | **Liquidação sem aprovação manual no app** — ou alçada por valor para usuário-API | pagamento por API liquida direto | O Cora exige aprovação no celular **até para boleto e TED**. Isso quebra o ciclo automático mesmo no que a API faz. Nosso controle humano já é o OTP. |
| 4 | **Consulta de status do pagamento depois de aprovado** | `GET /banking/v2/pagamento/{id}` | No Cora, aprovado → 404. Ficamos cegos até o extrato do dia seguinte. |

Se um banco falhar em **1** ou **3**, ele é estruturalmente igual ao Cora para o nosso uso.

## Bloco 2 — Necessários (o ERP já usa; sem eles regredimos)

| # | Requisito | Inter | Cora hoje |
|---|---|---|---|
| 5 | Extrato com **id da transação + tipo + contraparte (nome e documento)** | `GET /banking/v2/extrato` | ✅ tem — e é bom |
| 6 | Saldo | `GET /banking/v2/saldo` | ✅ |
| 7 | **Webhook** de pagamento (liquidado / recusado) com payload documentado | webhooks pix + boleto + status | ⚠️ existe, eventos não documentados publicamente |
| 8 | Pagar **boleto por linha digitável** | `POST /banking/v2/pagamento` | ✅ (provado 13/08) |
| 9 | Pagar **DARF e GPS/INSS** | `/pagamento/darf`, `/tributos` | ✅ |
| 10 | **TED** por dados bancários | `POST /banking/v2/transferencia` | ✅ |
| 11 | **Emitir cobrança** (boleto + PIX) com identificador nosso ecoado | `/cobranca/v3/cobrancas`, `/pix/v2/cobv` | ✅ (`code` + Idempotency-Key) |
| 12 | Consultar / cancelar cobrança | ✅ | ✅ |
| 13 | **PIX recebidos** e **devolução de PIX** | `/pix/v2/pix`, refund | ⚠️ não verificado |
| 14 | Autenticação **mTLS + OAuth2** com certificado | ✅ | ✅ |

## Bloco 3 — Desejáveis (ganho real, não bloqueia)

| # | Requisito | Inter | Por quê |
|---|---|---|---|
| 15 | **Pagamento em lote** | `POST /banking/v2/pagamento/lote` | Folha de diaristas: hoje são dezenas de PIX de R$32 (VT+VR). Em lote vira uma operação. |
| 16 | **DDA por API** (boletos emitidos contra nosso CNPJ) | — | Montaria o contas a pagar sozinho, sem digitar linha digitável. O Cora tem DDA só no app. |
| 17 | Sandbox | ✅ | Testar money-out sem mover dinheiro. |
| 18 | Teto/alçada configurável por API | — | Segunda trava além da nossa. |

---

## Três perguntas para fazer a QUALQUER banco (e ao gerente do Cora)

Estas três decidem a arquitetura e nenhuma está na documentação pública do Cora:

1. **PIX de saída por API existe?** Se não existe hoje, está no roadmap e com que prazo?
2. **O webhook de pagamento dispara em liquidado e recusado?** Qual o payload exato?
   (É o que fecha o ciclo sem varrer extrato.)
3. **Existe dispensa de aprovação no app**, ou alçada por valor para um usuário-API?

Peça **por escrito**. As três mudam o desenho do sistema.

---

## Como decidir

- **Banco novo atende 1 e 3** → vale a troca; a Patrimonial passa a ter o mesmo controle
  prévio que a Eletrônica tem hoje.
- **Não atende** → é o Cora com outro nome. Melhor ficar onde está: o Cora tem a favor a
  justificativa que você digita no app (que o ERP lê e usa para classificar) e um extrato
  com contraparte identificada, que nem todo banco entrega.
- **Alternativa que não é banco:** um PSP com cash-out PIX por API, mantendo a conta Cora
  para o resto. Adiciona um intermediário no caminho do dinheiro — só compensa se o volume
  de PIX de saída justificar.

## Reforma que independe do banco escolhido

Enquanto não houver PIX por API, o controle prévio pode existir **fora do banco**: o ERP
propõe o pagamento (valor, favorecido, categoria, com OTP), você aprova, e o sistema gera a
**ordem para você executar no app** — depois casa automaticamente com a saída do extrato
pelo `transaction.id`. Não impede um PIX feito direto no celular, mas transforma o caminho
normal em "aprovado no sistema, executado no app" em vez de "executado no app, descoberto
depois".
