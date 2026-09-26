# 2027 programado e rentável — a conta que precisa fechar

> Jordan, 25/09/2026: *"vamos trabalhar agora pra termos um 2027 diferente, tudo programado
> e rentável, sem prejuízo."*

Tudo aqui foi medido no razão de produção, depois das correções desta noite. Onde não
consegui medir, está dito.

---

## 1. O ponto de partida, sem maquiagem

> **Renumerado em 26/09/2026.** Os valores anteriores desta seção foram medidos antes da
> sincronia completa com o ADN. A sincronia trouxe notas autorizadas que faltavam nas
> competências abertas e o re-fechamento as repostou (R$ 376.445,66 em 08 e 09). O DRE
> agora fecha sozinho: `conferencia.resto = 0,00` — toda conta com movimento está em
> algum grupo.

    2026 (9 competências)     receita bruta   R$ 2.256.136,51
                              (−) ISS         R$    88.936,55
                              custos          R$ 1.424.759,19
                              despesas        R$   950.672,26
                              resultado       R$  −203.875,99      margem −9,0%
                              (era −R$ 208.231,49 antes da poda de duplicata; ver abaixo)

Mês a mês:

    mês         receita       custos     despesas    resultado   margem
    2026-01  263.740,26   114.080,26   170.795,48   −34.322,50   −13,0%
    2026-02  270.606,56   113.595,18   132.747,44   +10.734,58    +4,0%
    2026-03  268.950,96   115.305,66   114.605,33   +25.595,61    +9,5%
    2026-04  271.971,46   121.417,24   122.925,65   +14.029,99    +5,2%
    2026-05  262.604,96   132.262,46   138.918,65   −21.706,41    −8,3%
    2026-06  163.529,67   144.246,85   161.567,22  −146.481,19   −89,6%
    2026-07  378.286,98   110.245,22   127.476,82  +130.952,22   +34,6%
    2026-08  275.461,56   141.140,10   183.672,35   −54.485,41   −19,8%
    2026-09  100.984,10   112.868,01   117.561,53  −132.548,38  −131,3%

**Junho e julho não são meses de verdade, são um artefato.** Em junho o faturamento dos
condomínios migrou da Eletrônica para a Patrimonial; a receita despencou em junho e voltou
inflada em julho. Somados, os dois dão R$ 541.816,65 — ou R$ 270.908 por mês, que é a
média do resto do ano. **Setembro ainda está correndo** e por isso aparece pior do que é.

### R$ 5.069,00 de despesa que não existiu — resolvido no mesmo dia

**77 linhas do extrato do Inter estavam duplicadas** entre a importação de retaguarda de
11/08 e a sincronia pela API, entre março e julho. A linha da API vem sem `external_id` e
o índice único do banco é parcial — nulo não colide com nulo. **Todas tinham lançamento no
razão.**

Estavam invisíveis porque a checagem de duplicata exige favorecido preenchido e essas
cópias vinham sem nome. Em 26/09 a conciliação passou a nomear 545 transações e elas
apareceram — 73 grupos de uma vez.

**Adjudicadas contra o banco, e não foi preciso a API dele** (que devolveu 503 o dia
inteiro): `inter_transactions` é a tabela crua da ponte e guarda o payload que o Inter
mandou, desde 06/03. Em 23/03 o banco tem UMA linha de R$ 152,13 e nós tínhamos duas; nos
36 dias afetados, em todos, o nosso número excedia o do banco.

Podadas 67 transações e 67 lançamentos — **R$ 5.069,00** — com backup em
`backup_dup_multifonte_20260926`. Seis grupos ficaram de pé: o teto por dia os protegeu
porque o banco confirma tê-los. As competências 04 a 07 foram reapuradas (o resíduo somou
exatamente os R$ 5.069,00) e o balanço voltou a fechar.

    resultado de 2026:  −R$ 208.231,49  →  **−R$ 203.875,99**

### O mês representativo é agosto

    receita                 R$ 275.461,56     (inclui a NFS-e 124, Hawk Eye, R$ 1.000)
    custos                  R$ 141.140,10
    despesas                R$ 183.672,35
    resultado               R$ −54.485,41            margem −19,8%

> A versão anterior desta seção descontava «R$ 12.061,50 de duplicata Mirante (notas 26 e
> 27)» de agosto. **Era falso positivo e está retirado:** as duas notas têm códigos de
> serviço diferentes — 110201 (vigilância) e 071002 (limpeza). São dois serviços distintos
> que por coincidência custam o mesmo. O caçador passou a incluir o código na chave.

Duplicata de verdade que sobra em 2026, depois da sincronia e dos cancelamentos feitos na
prefeitura: **3 grupos, R$ 47.318,51 de excedente, R$ 1.349,12 de ISS** — Laranjeiras
(06, R$ 37.438,91), Gelain (07, R$ 6.000,00) e Prime Arena (06, R$ 3.879,60). Eram 4 grupos
e R$ 130.328,02 antes; o Ideal Flores saiu porque a nota foi cancelada no fisco.

**R$ 272.948,99 continuam em «Saídas a Classificar» — sem natureza, 638 lançamentos.** É a
maior linha isolada de despesa do ano depois de salários e terceiros, e é a que impede
saber o custo por posto.

---

## 2. O que já está em movimento, e quanto vale

Duas mudanças já decididas, ainda não refletidas num mês cheio:

| | efeito mensal | efeito anual |
|---|---|---|
| **Sólides desligada** (último pagamento 14/08) | **+R$ 28.266** | +R$ 339.192 |
| **Green Hills**, contrato de portaria a partir de 01/09 | **+R$ 22.100** | +R$ 265.200 |
| | **+R$ 50.366/mês** | **+R$ 604.392/ano** |

Aplicando sobre agosto remedido (§1):

    −R$ 54.485,41  +  R$ 50.366,00  =  **−R$ 4.119,41/mês**

**As duas maiores mudanças já em curso levam de −19,8% para −1,5% de margem. Não chegam
ao zero.** Falta R$ 4.119/mês — R$ 49.428 no ano — só para empatar. E as duas são
passado: a Sólides já foi desligada, o Green Hills já começou. **De 2027 em diante elas
não melhoram mais nada** — são o piso, não a alavanca.

---

## 3. Onde estão os R$ 4.119 que faltam

### 3.1 Os dois baldes de 39% (R$ 128.569,66/mês em agosto)

Depois de tirar a Sólides, sobram **R$ 59.205,65/mês de «Serviços de Terceiros»** e
**R$ 41.098,01/mês de «Saídas a Classificar»**. Numa empresa cujo negócio é colocar pessoa
em posto, terceiros ser 23% da receita é a anomalia central.

Dentro deles, o padrão que aparece é pagamento a **pessoa física** — Orlailson, Sebastião,
Edward, Pedro, Keyson, Sidney, Denilson e outros, cada um com R$ 5 mil a R$ 13 mil no ano,
classificados como «serviço de terceiro». Se são cobertura e diária, o lugar é folha
(5.1.1.07) e há risco trabalhista. Se são prestadores de fato, precisam de nota.

`checar_transitoria_aberta.py` já lista isso por contraparte: **293 contrapartes, 131 acima
de R$ 300** — eram 218 e 101 até 26/09, quando o maior balde («sem nome», R$ 67.110,61)
se abriu em ~110 contrapartes nomeadas. Decidir uma resolve várias — a Sólides eram 16 linhas com o mesmo destino.

**Esta é a maior alavanca de 2027, e ela não é técnica: é olhar a lista.**

### 3.2 Contrato que não vira nota

> **Corrigido em 26/09/2026.** A versão anterior desta seção somava «+R$ 5.800/mês» com os
> dois casos abaixo. Medindo cada um, a alavanca é outra — e menor.

**PARQUE DOS FRANCESES é um buraco, sim — mas de agosto, não de todo mês.** O contrato
é de R$ 1.800/mês e vale a partir de **01/08** (decisão do Jordan em 14/08, por escrito em
`corrigir_inicio_franceses.py`, revertendo uma correção de 10/08 que o punha em 01/09).
De setembro em diante está faturado e recebido: NFS-e 121 de 17/09, R$ 1.800, paga em
19/09 com R$ 1.764 (R$ 36 retidos).

**Agosto ficou sem nota.** O título de 08/2026 foi cancelado em 10/08 sob a premissa que
caiu quatro dias depois, e ninguém o recriou — e o cliente **pagou R$ 2.508,00 em 27/08**.
Dinheiro na conta, nenhuma nota atrás.

Falta uma resposta para emitir: **por qual valor?** O contrato diz R$ 1.800; entraram
R$ 2.508. Os R$ 708 de diferença não estão na proposta (item único de R$ 1.800), não estão
em título nenhum, e não são juros (vencia 10/08, pago 27/08 — daria ~R$ 1.846 com multa
de 2% e 1% ao mês).

Como alavanca de 2027 ele **não** entra: de setembro em diante já fatura sozinho. O que
há é uma competência atrasada, de valor a confirmar.

**HAWK EYE era um buraco, e de outro tamanho.** Contrato de R$ 4.000/mês desde 08/2025,
treze meses prestados, **nenhuma nota nunca emitida**. Do dinheiro, o dono explicou o
caminho: até uns quatro meses atrás caía na conta **pessoa física dele, no Itaú** — que o
sistema não conhece — e só depois passou para a conta PJ da Eletrônica. No extrato do
Inter há **uma única entrada: R$ 1.000,00 em 13/08/2026**.

Por decisão do dono («contabilize apenas o que entrou da hawkeye na conta da eletrônica»),
foi emitida a **NFS-e 124 de R$ 1.000,00**, competência 2026-08 — a primeira nota da
história desse cliente, e a primeira NFS-e de produção emitida pelo próprio ERP.

A alavanca aqui **não é contábil, é de cobrança**: fazer os R$ 4.000/mês entrarem no CNPJ
e virarem nota vale **+R$ 4.000/mês = R$ 48.000/ano**. Os outros R$ 3.000/mês de agosto
não entraram em conta nenhuma que o sistema veja.

Três travas passam a medir isso todo dia, uma por lado do triângulo:

| trava | compara |
|---|---|
| `checar_contrato_vs_faturado.py` | contrato ←→ nota |
| `checar_dinheiro_fora_do_sistema.py` | contrato ←→ dinheiro |
| `checar_recebimento_sem_nota.py` | **nota ←→ dinheiro** (nova, 26/09) |

A terceira é a que teria achado o Hawk Eye sozinha: R$ 1.000 recebidos, R$ 0 faturados.
As duas primeiras partem do contrato e por isso não alcançam quem recebe fora dele.

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

    base agosto (medida em 26/09)        −R$ 54.485/mês
    Sólides fora                         +R$ 28.266
    Green Hills                          +R$ 22.100
    ───────────────────────────────────────────────
    ponto de partida de 2027              −R$ 4.119/mês       −R$ 49.428/ano

Para virar o ano no azul, três coisas somam mais que o suficiente:

| ação | efeito mensal | de quem é |
|---|---|---|
| trazer o Hawk Eye inteiro para o CNPJ e faturar (§3.2) | +R$ 4.000 | dono / cobrança |
| atualizar o contrato do Mirante para o que é prestado | +R$ 1.500 | comercial |
| cortar 20% dos R$ 59.206 de terceiros após decidir a lista | +R$ 11.841 | dono |
| **soma** | **+R$ 17.341/mês** | |

    resultado projetado 2027   +R$ 13.222/mês   ·   +R$ 158.664/ano

**As três juntas viram o ano.** Mas a conta é sensível: o ponto de partida melhorou de
−R$ 17.131 para −R$ 4.119/mês só porque a base de agosto foi remedida depois da sincronia
completa — não porque algo tenha sido feito. E **nenhuma das três ações é contábil**: são
cobrança, comercial e decisão de corte. O sistema já as mede todo dia; executá-las é do
dono.

Ordem de tamanho, para escolher por onde: **a lista de terceiros vale quase o triplo das
outras duas somadas.** É também a única que depende só de olhar
(`checar_transitoria_aberta.py`, 218 contrapartes, 101 acima de R$ 300). Margem de verdade — 10% sobre R$ 284 mil de
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
