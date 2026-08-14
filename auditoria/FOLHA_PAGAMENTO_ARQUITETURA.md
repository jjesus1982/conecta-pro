# Pagamento de folha — o que o financeiro tem, medido em 14/08/2026

Levantamento a pedido do Jordan, antes do **adiantamento de 40% no dia 20** e dos **60%
por volta de 05/09**, com pagamento em **lote por condomínio**.

Resposta curta à pergunta "o financeiro pixa ou recebe a folha do DP?": **as duas coisas
existem, mas não se encontram.** Ele recebe a folha do DP e sabe mandar PIX — só que o
PIX que ele sabe mandar sai do **CNPJ errado**.

---

## 1. O caminho que existe hoje, ponta a ponta

```
hr_payslips (DP)
   ↓  folha_payment_service.preparar_lote_folha(mes, ano)
   ↓  folha_payment_service.registrar_lote_pendente(mes, ano)
payroll_payments  (status 'pendente_pagamento')
   ↓  ordem_pagamento_service.montar_lote(competencia, banco)
folha_lote_ordem  (RASCUNHO → OTP → APROVADO)
   ↓  execução MANUAL no app do banco
   ↓  ordem_pagamento_service.fechar_pelo_extrato()
payroll_payments  (status 'pago', com a linha do extrato como prova)
```

Esse caminho **está no ar e foi provado**: 96 de 96 pagamentos de folha estão fechados com
prova bancária, e o oráculo do extrato passou a exigir essa prova todo dia.

## 2. Quatro serviços de pagamento, e só três ligados

| serviço | paga o quê | banco | ligado a tela? |
|---|---|---|---|
| `pagamento_pj_service` | folha **PJ** | Inter, OTP próprio | ✅ `/action/pagar-folha-pj` |
| `pagamentos_diaristas_service` | diaristas | Inter, OTP próprio | ✅ `/action/pagar-diaristas` |
| `ordem_pagamento_service` | folha **CLT** | qualquer (executa no app) | ✅ 4 telas em `_fin_pagar` |
| `folha_lote_service` | folha CLT **por posto** | Inter, 1 OTP por lote | ❌ **órfão** |

⭐ O `folha_lote_service` é quase exatamente o que o Jordan pediu — "escolhe o posto,
confere a lista, um OTP libera o lote inteiro", com trava anti-duplicidade que consulta o
extrato. Está escrito, tem 235 linhas, e **nenhum código de produção o chama**: só testes.

---

## 3. O problema central: o PIX sai do CNPJ errado

`folha_lote_service.executar_lote` e `folha_payment_service.pagar_funcionario_pix`
constroem o `InterAdapter` com as variáveis `INTER_*`. O Inter é da **Conecta Mais
Eletrônica**.

**A folha é da Patrimonial** — 52 funcionários ativos, contra 1 na Eletrônica. E a
Patrimonial banca no **Cora, que não envia PIX por API** (confirmado na documentação
deles: nem por chave, nem por QR).

Ou seja: o único caminho automático que existe pagaria a folha da Patrimonial com dinheiro
da Eletrônica. Isso não é detalhe técnico — é **confusão patrimonial entre dois CNPJs**.

É exatamente o buraco que a **Efí** fecha: ela envia PIX por API, e a conta está sendo
aberta no CNPJ da Patrimonial. Enquanto ela não sai, o caminho correto é o que já está no
ar: **o sistema aprova o lote (OTP + teto) e você executa no app do Cora**, e o extrato do
dia seguinte fecha cada item.

---

## 4. O que trava o plano de 40% + 60%

### 4.1 Trava dura: o banco não deixa dois pagamentos na mesma competência

`payroll_payments` tem `uq_payroll_payment_emp_mes_ano UNIQUE (employee_id, mes, ano)`.

**Um funcionário só pode ter UMA linha de pagamento por competência.** O adiantamento de
40% e o saldo de 60% são dois pagamentos do mesmo mês para a mesma pessoa — o segundo
`INSERT` é recusado pelo banco.

Não é configuração: é migration.

### 4.2 Não existe conceito de adiantamento

Varri `modules/financial` e `modules/people_management`: a palavra "adiantamento" só
aparece em **comentários**, explicando que adiantamento **não** entra no líquido. Não há
campo de parcela, percentual, nem tipo de pagamento.

`payroll_payments.valor_liquido` é um número só, o líquido cheio.

### 4.3 A regra de fechamento quebra

O `fechar_pelo_extrato` casa a saída pelo **valor igual ao líquido** (±R$0,50) — foi essa
regra que fechou 84 de 96 pagamentos sem nenhum ambíguo. Um pagamento de 40% não bate com
o líquido, e o de 60% também não. **Os dois ficariam sem par**, exatamente como os 12 que
passamos hoje inteiro resolvendo.

Precisa virar: casa contra o valor da PARCELA, e a soma das parcelas fecha o líquido.

### 4.4 Um lote por competência, não vários

`montar_lote` grava `referencia = 'ORDEM-<BANCO>-<competencia>'` com
`uq_lote_ref UNIQUE (referencia)`. **Só cabe um lote por banco por mês** — lote por
condomínio precisa de vários.

---

## 5. O que trava o lote por condomínio

Os 52 ativos da Patrimonial, hoje:

- **`posto_atual_nome` preenchido em 52 de 52** — 7 postos distintos
- **`cliente_nome` vazio em 13 de 52** — 7 clientes distintos
- ⚠️ **posto e cliente estão cruzados**: há funcionário com `posto: PRIME` e
  `cliente: CONDOMINIO MIRANTE DAS FLORES`, `posto: VILLA DEI FIORI` e
  `cliente: RESIDENCIAL LARANJEIRAS`, e assim por diante

Agrupar por posto funciona hoje. Agrupar por **cliente** não — 1 em cada 4 funcionários
ficaria de fora do lote, e os que entrassem poderiam entrar no lote do condomínio errado.

**Isso é dado do operacional, que é curado à mão pelo Jordan.** Não toco; entra como
relatório. Mas é pré-requisito do que ele pediu.

---

## 6. Dois defeitos encontrados no caminho

### 6.1 A consulta do DP soma as duas fontes

`preparar_lote_folha` lê `hr_payslips WHERE reference_month = X AND reference_year = Y`,
**sem filtrar `source_system` nem `payslip_type`**. Medido agora:

| competência | holerites lidos | soma | fontes | tipos |
|---|---:|---:|---|---|
| 06/2026 | **112** | R$ 160.811,99 | conecta + portte | mensal + monthly |
| 07/2026 | **102** | R$ 165.612,95 | conecta + portte | mensal + monthly |
| 11/2026 | 47 | R$ 35.864,16 | conecta | **decimo_terceiro_1a** |

São 56 funcionários em junho, não 112. A folha real é ~R$80 mil, não R$160 mil.

O estrago é contido pela constraint `uq_payroll_payment_emp_mes_ano`: o segundo holerite
da mesma pessoa é recusado. **Mas isso significa que QUAL das duas fontes vence é sorte** —
depende da ordem física das linhas. E as duas divergem (ADAILSON: Portte R$643,95 × nosso
R$652,35). Hoje a Portte venceu em todos os casos medidos, por acidente, não por regra.

Em novembro, a mesma consulta pegaria os holerites de **13º** como se fossem folha mensal.

### 6.2 Sem filtro de tipo, o 13º entra na folha

Consequência direta do anterior, mas vale destacar porque tem data marcada: quando o DP
gerar o 13º, a preparação de folha de novembro vai enxergá-lo.

---

## 7. O que precisa ser construído, em ordem

Ordem escolhida para que cada passo já sirva ao dia 20, mesmo que o seguinte atrase.

1. **Filtrar a fonte na consulta do DP** — decidir a fonte autoritativa
   (`source_system`) e o tipo (`payslip_type IN ('mensal','monthly')`). Sem isso, tudo o
   que vier depois herda o número errado. *Uma linha de SQL, e é o mais urgente.*
2. **Parcela em `payroll_payments`** — trocar a unique por
   `(employee_id, mes, ano, parcela)` e adicionar `parcela` + `percentual`. Migration.
3. **Fechamento por parcela** — `fechar_pelo_extrato` casa o valor da parcela, e a soma
   das parcelas tem que fechar o líquido. É a invariante que impede pagar 40% duas vezes
   e achar que fechou.
4. **Vários lotes por competência** — referência passa a incluir o agrupador
   (`ORDEM-CORA-2026-08-VILLA_DOS_PASSAROS-P1`).
5. **Agrupador no lote** — `folha_lote_ordem` ganha `agrupador` (posto hoje, cliente
   quando o cadastro estiver correto).
6. **Corrigir posto × cliente** — operacional, decisão do Jordan, pré-requisito do lote
   por condomínio de verdade.
7. **Efí** — quando a conta abrir, o `_chamar_efi` no executor troca "executa no app" por
   "executa por API", sem mexer em nada do que está acima.

**Para o dia 20 dá para chegar com 1 + 2 + 3.** Os itens 4 e 5 são o "por condomínio"; o 6
é do operacional; o 7 depende do banco.

---

## 8. O que já está pronto e não precisa ser refeito

- Lote com **OTP humano e teto diário** (R$100.000, e a folha medida foi R$94.394,91 —
  94% do teto num lote só; por isso o guard existe no serviço, não só na tela)
- **Fechamento pelo extrato** por CPF + valor, provado em 96 de 96
- **Anti-duplicidade** que consulta o extrato antes de preparar (no `folha_lote_service`)
- **Invariante diária**: folha marcada paga sem prova bancária derruba o oráculo
- **Trilha de auditoria** em `inter_payment_audit` e `folha_lote_ordem`
