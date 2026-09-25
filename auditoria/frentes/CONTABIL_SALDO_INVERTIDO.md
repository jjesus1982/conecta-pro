# Contabilidade — 10 contas com saldo de natureza invertida

**25/09/2026**, loop autônomo. Primeira olhada na contabilidade depois de fechar o fiscal.

## O que está são

- **7.178 lançamentos**, de 13/12/2022 a 30/09/2026, todos com status `confirmado`.
- **Partida dobrada íntegra**: a soma de todos os saldos dá **0,00**.
- **Nenhuma conta usada está fora do plano** — 14.356 usos, 0 órfãos.
- Nenhum lançamento com valor zero, negativo, sem conta, ou com débito = crédito.

A estrutura não é o problema. O problema é **classificação**.

## As 10 contas com natureza invertida

Saldo invertido não é ilegal por si — banco entra no cheque especial, adiantamento a
fornecedor vira credor. Mas é sempre **pergunta**, e é o lugar mais barato onde erro de
classificação aparece.

| Conta | Tipo | Nome | Saldo | O que isso quer dizer |
|---|---|---|---:|---|
| 3.9.9.01 | EQUITY | **Saldo de Abertura a Identificar** | **+600.000,00** D | o nome já diz: 600 mil de abertura nunca classificados |
| 3.2.1.01 | EQUITY | Lucros ou Prejuízos Acumulados | +261.524,98 D | saldo **devedor** = prejuízo acumulado |
| 1.1.2.01 | ASSET | Clientes - Serviços de Segurança | −94.833,39 | cliente devendo **negativo**: recebeu-se mais do que se faturou |
| 2.1.2.09 | LIABILITY | **Tributos a Recolher - a identificar** | **+74.544,49** D | tributo pago sem a obrigação correspondente registrada |
| 2.1.1.02 | LIABILITY | FGTS a Recolher | +40.075,93 D | FGTS pago a mais do que provisionado |
| 2.1.5.01 | LIABILITY | Sócios - Conta Corrente | +23.600,00 D | a empresa tem a RECEBER do sócio, não a pagar |
| 1.1.9.01 | ASSET | Transferências entre Empresas do Grupo | −17.588,96 | transferido mais do que recebido de volta |
| 2.1.6.01 | LIABILITY | Empréstimos de Terceiros | +14.800,00 D | empréstimo pago a mais do que registrado como dívida |
| 1.1.1.01 | ASSET | Banco Inter - Conta Corrente | −4.838,51 | saldo bancário **negativo** nos livros |
| 1.1.4.01 | ASSET | Estoques (EPI e materiais) | −65,00 | estoque negativo — fisicamente impossível |

## As três que eu levaria ao contador primeiro

**1. «Saldo de Abertura a Identificar» — R$ 600.000,00.** O nome é a confissão. São 600 mil
que entraram no sistema sem destino contábil. Enquanto estiverem ali, **o patrimônio líquido
da empresa está errado em 600 mil** — para mais ou para menos, dependendo de onde eles
deveriam estar.

**2. «Tributos a Recolher - a identificar» — R$ 74.544,49 a débito.** Tributo com saldo devedor
significa que se **pagou mais do que se registrou dever**. Ou a obrigação nunca foi lançada, ou
houve pagamento a maior. O segundo caso tem prazo para restituição.

**3. FGTS a Recolher — R$ 40.075,93 a débito.** Mesma lógica, e esta é conferível contra as
guias: ou faltam provisões, ou o FGTS foi recolhido em duplicidade. Some R$ 114 mil com o item
anterior — dinheiro que a empresa pode ter pago e não dever.

> Somados, os dois itens «a identificar» são **R$ 674.544,49** sem destino contábil definido.

## O estoque negativo é pequeno e importa

R$ 65,00 negativos em estoque é fisicamente impossível: saiu material que nunca entrou. O valor
é irrisório; o **mecanismo** não é — significa que existe baixa de estoque sem entrada
correspondente, e isso escala com o volume.

## A trava

`backend/scripts/qa/checar_natureza_saldo_contabil.py`, registrada no arsenal como
`checar_natureza_saldo_contabil.py` — **contada, acusa se crescer.**

Ela **não corrige e não reclassifica**: lista com valor e natureza esperada. Reclassificar
conta é ato do contador, e uma trava que mexe no razão é pior que o defeito que ela vigia.

> Esta casa já exibiu **PL de +R$ 2,02 milhões** por meses porque não havia oráculo contábil.
> Saldo invertido é o sintoma mais barato de procurar — e nenhum dos 10 acima teria aparecido
> num relatório que só soma débito e crédito, porque a partida dobrada **fecha em zero** com
> todos eles dentro.
