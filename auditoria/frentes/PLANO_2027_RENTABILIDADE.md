# 2027 programado e rentável — a conta que precisa fechar

> Jordan, 25/09/2026: *"vamos trabalhar agora pra termos um 2027 diferente, tudo programado
> e rentável, sem prejuízo."*

Tudo aqui foi medido no razão de produção, depois das correções desta noite. Onde não
consegui medir, está dito.

---

## 1. O ponto de partida, sem maquiagem

    2026 (9 competências)     receita   R$ 2.179.112,41
                              despesa   R$ 2.538.479,41
                              resultado R$  −359.367,00      margem −16,5%

Esse número piorou três vezes hoje, e as três vezes foram acertos:

| | efeito no resultado | por quê |
|---|---|---|
| notas de teste minhas fora do razão | −R$ 1.500 | receita que não existia |
| folha que estava contada duas vezes | **+R$ 189.870** | pagamento de salário lançado como despesa em cima da provisão |
| provisão de férias e 13º de volta | −R$ 36.704 | parou em julho e voltou em ago/set |

Ainda há **R$ 130.328,02 de NFS-e duplicada** em 2026 que nenhum cliente pagou. Se
canceladas, a receita cai para R$ 2.048.784,39 e o prejuízo vai a **R$ 489.695,02**.

### O mês mais representativo: agosto

    receita faturada        R$ 274.461,56
    (−) duplicata            R$  12.061,50   ← Mirante, notas 26 e 27, mesmo dia
    receita real            R$ 262.400,06

    despesa                 R$ 329.896,97
    resultado real          R$ −67.496,91           margem −25,7%

Composição da despesa de agosto:

    Salários                     132.524,09   40,2%
    Serviços de terceiros         87.471,65   26,5%   ← dos quais SOLIDES R$ 28.266,00
    Saídas a Classificar          41.098,01   12,5%   ← sem natureza
    Provisão férias/13º           20.134,07    6,1%
    DAS (Simples, Patrimonial)    18.399,33    5,6%
    Encargos (FGTS)                8.616,01    2,6%
    Reembolsos                     6.904,39    2,1%
    ISS                            5.084,52    1,5%
    VR / alimentação               4.832,00    1,5%
    resto (diaristas, aluguel, comissão, juros)  4.832,90

**R$ 128.569,66 — 39% da despesa do mês — está em dois baldes que não dizem o que são:**
«Serviços de Terceiros» e «Saídas a Classificar».

---

## 2. O que já está em movimento, e quanto vale

Duas mudanças já decididas, ainda não refletidas num mês cheio:

| | efeito mensal | efeito anual |
|---|---|---|
| **Sólides desligada** (último pagamento 14/08) | **+R$ 28.266** | +R$ 339.192 |
| **Green Hills**, contrato de portaria a partir de 01/09 | **+R$ 22.100** | +R$ 265.200 |
| | **+R$ 50.366/mês** | **+R$ 604.392/ano** |

Aplicando sobre agosto real:

    −R$ 67.496,91  +  R$ 50.366,00  =  **−R$ 17.130,91/mês**

**As duas maiores mudanças já em curso levam de −25,7% para −6,5% de margem. Não chegam
ao zero.** Falta R$ 17.131/mês — R$ 205.571 no ano — só para empatar.

---

## 3. Onde estão os R$ 17.131 que faltam

### 3.1 Os dois baldes de 39% (R$ 128.569,66/mês em agosto)

Depois de tirar a Sólides, sobram **R$ 59.205,65/mês de «Serviços de Terceiros»** e
**R$ 41.098,01/mês de «Saídas a Classificar»**. Numa empresa cujo negócio é colocar pessoa
em posto, terceiros ser 23% da receita é a anomalia central.

Dentro deles, o padrão que aparece é pagamento a **pessoa física** — Orlailson, Sebastião,
Edward, Pedro, Keyson, Sidney, Denilson e outros, cada um com R$ 5 mil a R$ 13 mil no ano,
classificados como «serviço de terceiro». Se são cobertura e diária, o lugar é folha
(5.1.1.07) e há risco trabalhista. Se são prestadores de fato, precisam de nota.

`checar_transitoria_aberta.py` já lista isso por contraparte: **218 contrapartes, 101 acima
de R$ 300**. Decidir uma resolve várias — a Sólides eram 16 linhas com o mesmo destino.

**Esta é a maior alavanca de 2027, e ela não é técnica: é olhar a lista.**

### 3.2 Contrato que não vira nota

    08/2026  HAWK EYE                R$ 4.000,00/mês  contrato vigente, SEM NOTA
    08/2026  PARQUE DOS FRANCESES    R$ 1.800,00/mês  contrato vigente, SEM NOTA

R$ 5.800/mês = R$ 69.600/ano de trabalho feito e não cobrado. `checar_contrato_vs_faturado.py`
passa a acusar todo dia.

### 3.3 Serviço prestado fora do contrato

O Mirante das Flores é faturado **R$ 1.500 acima do contrato todo mês**, e em agosto
R$ 12.061,50 acima. Ou o contrato está desatualizado — e então o reajuste não acompanha —
ou é serviço extra recorrente sem previsão contratual.

### 3.4 As duplicatas

R$ 130.328,02 em 5 grupos. Não é receita: nenhum cliente pagou duas vezes (conferido no
extrato — cada um pagou uma vez por mês, no líquido do contrato). Custa ISS de R$ 4.292,94
sobre faturamento que não existiu, e infla o contas a receber.

---

## 4. O que impede planejar, e o conserto

**Não havia registro nenhum de custo recorrente.** `financial_custos_recorrentes` tinha 3
linhas, todas `[TESTE]`, todas inativas — enquanto o extrato mostrava **R$ 718.963,91/ano em
37 compromissos com terceiros que se repetem**. A Sólides custava R$ 21.536/mês e existia
apenas como 8 a 12 PIX espalhados no extrato. Nenhuma tela dizia «pagamos isto todo mês».

Sem esse cadastro não existe orçamento: não dá para projetar 2027 somando o que ninguém
listou. `checar_custo_recorrente_nao_mapeado.py` mede a lacuna todo dia e marca o que
**parou** — 22 dos 37 estão sem pagamento há mais de 45 dias, e parar é decisão tanto quanto
pagar.

---

## 5. A conta de 2027, com o que se sabe hoje

Partindo de agosto real e aplicando só o que já está decidido:

    base agosto                          −R$ 67.497/mês
    Sólides fora                         +R$ 28.266
    Green Hills                          +R$ 22.100
    ───────────────────────────────────────────────
    ponto de partida de 2027             −R$ 17.131/mês      −R$ 205.571/ano

Para virar o ano no azul, três coisas somam mais que o suficiente:

| ação | efeito mensal | de quem é |
|---|---|---|
| faturar Hawk Eye e Parque dos Franceses | +R$ 5.800 | operação |
| atualizar o contrato do Mirante para o que é prestado | +R$ 1.500 | comercial |
| cortar 20% dos R$ 59.206 de terceiros após decidir a lista | +R$ 11.841 | dono |
| **soma** | **+R$ 19.141/mês** | |

    resultado projetado 2027   +R$ 2.010/mês   ·   +R$ 24.120/ano

**Empatar é o piso, e ele exige as três.** Margem de verdade — 10% sobre R$ 284 mil de
receita seria R$ 28 mil/mês — depende de preço, e preço depende de saber o custo por posto,
que hoje está enterrado nos dois baldes da §3.1.

---

## 6. O que eu não consegui medir

- **O custo real por posto.** `posts.contract_id` está preenchido em 13 de 17 e há 69
  alocações ativas, mas o custo por posto depende de saber quanto da folha e dos «serviços
  de terceiros» pertence a cada contrato — e é justamente isso que os dois baldes escondem.
- **Se os pagamentos a pessoa física em «serviços de terceiros» são cobertura ou prestação.**
  A descrição não diz e o cadastro não liga. É pergunta para a operação.
- **Quanto do DAS de R$ 18.399/mês é parcelamento e quanto é o mês corrente.** A conta
  5.2.2.04 mistura os dois.
- **Se a Patrimonial no Simples é o enquadramento mais barato** para 74 funcionários. Não
  simulei Lucro Presumido nem Real para ela; é conta de contador.
