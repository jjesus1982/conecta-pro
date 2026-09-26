# Patrimonial — arrumar para a linha de crédito

**Data:** 26/09/2026
**Pedido do dono:** *"temos que focar na patrimonial para que não aconteça o que aconteceu
na eletronica, se afundar em dividas, impostos e etc… ver onde podemos economizar, o que
podemos tirar, de onde, planejar, pois preciso dela organizada para quando eu for tentar uma
linha de crédito, estar toda regularizada."*

CNPJ 66.014.833/0001-10 · Simples Nacional · aberta em 31/03/2026 · 7 condomínios ·
~R$ 262 mil/mês de faturamento · ~51 funcionários.

---

## 1. O que estava errado nos livros (e já foi corrigido)

O balanço não estava errado por pouco. Seis defeitos, todos medidos:

| # | defeito | tamanho | como foi corrigido |
|---|---|---|---|
| 1 | Junho inteiro fora do razão | R$ 236.170,73 de receita | corte contábil passou a ser POR EMPRESA |
| 2 | Pagamento de fornecedor contado 2× | R$ 119.280,90 (as duas empresas) | pagar nota tomada = liquidação, não despesa |
| 3 | DAS nunca lançado | R$ 35.448,20 | `lancar_das_parcelamento` virou multi-empresa |
| 4 | DAS de agosto lançado na EMPRESA ERRADA | R$ 18.399,33 | consulta passou a filtrar `empresa_id` |
| 5 | ISS lançado à parte numa empresa do Simples | R$ 9.792,84 | no Simples o ISS é componente do DAS |
| 6 | Nota real rebaixada a "homologação" | R$ 36.932,63 | ambiente nunca mais é rebaixado |

### 1.1 O corte contábil era da irmã, não dela

A decisão de 11/08 — *"de janeiro a julho a empresa operou fora do sistema"* — era sobre a
**Eletrônica**, cujo dado de jan–jul veio de CSV e da Portte. A **Patrimonial abriu o CNPJ em
31/03/2026** e toda a vida dela aconteceu dentro do Conecta PRO, com fonte primária: as notas
do ADN e o PGDAS-D. Aplicar a arqueologia da irmã nela custava junho inteiro — 11 notas,
R$ 315.764,86 emitidas contra R$ 79.594,13 lançados — e fazia junho aparecer com prejuízo de
R$ 58 mil por falta de receita, não por falta de resultado.

O corte agora mora em `empresas.corte_contabil`, lido tanto pelo Python quanto pelo gatilho
`fn_bloqueia_periodo_fechado`: **dois leitores, um fato**. Patrimonial = 01/06/2026;
Eletrônica = 01/08/2026 (inalterado). Provado dos dois lados: um lançamento de 15/06 passa
para a Patrimonial e é recusado para a Eletrônica.

### 1.2 O ISS estava sendo contado duas vezes

A guia do DAS abre o documento por tributo, e a linha está lá:

```
07/2026  DAS R$ 17.048,87  →  1010 ISS - SIMPLES NACIONAL  R$ 4.709,56
08/2026  DAS R$ 18.399,33  →  1010 ISS - SIMPLES NACIONAL  R$ 6.311,95
```

O razão vinha lançando, ALÉM disso, o ISS destacado em cada NFS-e (R$ 9.792,84 em 5 notas),
contra um passivo `2.1.2.01 ISS a Recolher` que tinha 5 créditos e **zero débitos** — porque
não há o que pagar. A alíquota que aparece na nota (2,01% → 4,36% em quatro meses) é a
alíquota efetiva de ISS do Simples subindo com o RBT12, não um ISS municipal próprio.

### 1.3 A nota que sumiu do faturamento

A NFS-e 13 (R$ 36.932,63, Laranjeiras Village, 24/07) estava marcada como `homologacao`.
Não era: a conciliação, ao reencontrá-la numa varredura de homologação, **sobrescreveu o
ambiente** com o ambiente em que estava consultando. Com ela fora, o razão de julho dizia
R$ 212.428,81 — e o PGDAS-D entregue à Receita (recibo 01.07.26226.0527542-9) declarou
**R$ 255.400,06**. O upsert agora só promove homologação → produção, nunca o contrário.

---

## 2. O achado grave: a contribuição patronal não está em documento nenhum

Empresa do Simples paga a CPP patronal de um jeito **ou** de outro, nunca de nenhum:

- **tributação substituída** (Anexo III) — a CPP vem DENTRO do DAS e aparece na linha
  `1006 INSS - SIMPLES NACIONAL`, que no Anexo III é ~43% da guia;
- **Anexo IV, cessão de mão de obra** — a CPP fica FORA do DAS e é declarada na DCTFWeb,
  normalmente abatida pela retenção de 11% da Lei 9.711/98 que os tomadores fazem na nota.

O que os documentos do próprio governo dizem:

| documento | o que diz |
|---|---|
| Guia DAS 07/2026 | INSS de **R$ 171,06** em R$ 17.048,87 — 1,0% da guia |
| Guia DAS 08/2026 | **nenhuma linha de INSS** |
| DCTFWeb 07 e 08/2026 | só `1082-01 CP SEGURADOS` — **nenhum débito patronal** |
| DCTFWeb, dados iniciais | *"Classificação Tributária 1 — Simples com tributação previdenciária SUBSTITUÍDA"* |

A classificação declarada (substituída) é justamente a hipótese que a guia do DAS desmente.
No meio das duas, a patronal desaparece.

**O tamanho, medido:**

| competência | folha | patronal estimada (20% + RAT 3%) | retenção 11% dos clientes | descoberto |
|---|---|---|---|---|
| 06/2026 | 111.388,40 | 25.619,33 | 27.512,95 | −1.893,62 |
| 07/2026 | 102.322,90 | 23.534,27 | 22.689,44 | +844,83 |
| 08/2026 | 106.577,20 | 24.512,76 | 26.845,79 | −2.333,03 |

A retenção dos clientes cobre a patronal quase ao real — é o retrato exato do Anexo IV. E a
existência dessa retenção é ela própria a prova: tomador só retém 11% em cessão de mão de
obra. O sistema, por sua vez, tem `anexo_simples = 'III'` cadastrado.

**A consequência prática é boa e ruim ao mesmo tempo:**

- **boa** — o dinheiro já foi retido pelos clientes. A DCTFWeb de 08/2026 informa
  R$ 19.544,08 de crédito de retenção, dos quais só R$ 7.011,23 foram usados:
  **R$ 12.532,85 sobrando**, e sobrando todo mês. O caixa não está devendo.
- **ruim** — nada disso está declarado. Uma empresa com quatro meses de contribuição
  patronal sem documento **não é "toda regularizada"**, e é exatamente assim que a
  Eletrônica afundou.

**O que precisa ser feito** (é decisão de enquadramento, não de código): acertar a
classificação tributária no eSocial de `01 — substituída` para `03 — não substituída`,
declarar a patronal na DCTFWeb e abater com o crédito de retenção que já está lá. Isso é
retroativo a junho. O contador que for assinar precisa ver estas duas páginas.

---

## 2-B. A apuração fechava as duas empresas num resultado só

Achado posterior, e igualmente bloqueante: `apurar(competencia)` zerava 4.x e 5.x contra o
PL varrendo a competência INTEIRA, sem filtrar `empresa_id`, e o `_post` não gravava a
empresa. Os **277 lançamentos de encerramento** existentes — todas as competências desde
2022 — somavam as duas pessoas jurídicas. A ECD de cada CNPJ filtra por empresa e saía sem
nenhum deles.

Uma empresa cujo resultado é encerrado junto com o da irmã **não tem balanço próprio**. Sem
isso não há o que apresentar ao banco.

Refeito por empresa (141 contas encerradas; os antigos em
`backup_apuracao_sem_empresa_20260926`). Não dava para ratear os antigos: o valor de cada um
é a SOMA das duas empresas.

| resultado ao PL | 06/2026 | 07/2026 | 08/2026 |
|---|---|---|---|
| **Patrimonial** | +177.763,95 | +85.129,85 | **+5.573,90** |
| Eletrônica | −81.396,61 | +22.463,55 | −22.126,79 |

O oráculo do balanço foi de 1 invariante quebrada para **0** — inclusive a de 2026-01..03,
que falhava desde antes deste trabalho.

---

## 3. O que o razão mostra agora

| competência | receita | despesa | resultado |
|---|---|---|---|
| 2026-06 | 315.764,86 | 138.000,91 | +177.763,95 |
| 2026-07 | 249.361,44 | 164.231,59 | +85.129,85 |
| 2026-08 | 262.161,56 | 256.587,66 | **+5.573,90** |
| 2026-09 (parcial) | 76.024,10 | 178.200,22 | −102.176,12 |

**Só agosto é lido direto.** Junho e julho estão inflados e setembro deflacionado, por dois
motivos que não são operação:

- **junho** faturou três meses ao Laranjeiras Village de uma vez (R$ 110.619,21 em três notas
  do dia 25/06, na virada do contrato), e a conta bancária dela (Cora) só nasceu em 15/07 —
  em junho o dinheiro saiu pela conta da irmã, então a despesa está incompleta;
- **setembro** tem só 3 dos 7 clientes faturados até 26/09.

**Agosto, o mês honesto:**

| conta | R$ | % da receita |
|---|---|---|
| Salários (porteiros e vigilantes) | 132.524,09 | 50,6% |
| Serviços de terceiros | 62.193,91 | **23,7%** |
| Férias e 13º (provisão) | 20.134,07 | 7,7% |
| DAS | 18.399,33 | 7,0% |
| Encargos (só FGTS) | 8.616,01 | 3,3% |
| Reembolsos de equipe | 6.904,39 | 2,6% |
| Diaristas e coberturas | 3.928,96 | 1,5% |
| resto | 4.436,90 | 1,7% |
| **resultado** | **+5.573,90** | **+2,1%** |

---

## 4. Onde está o dinheiro que dá para economizar

| item | R$/mês | situação |
|---|---|---|
| **Sólides** | ~28.000 | **já cortado.** Último pagamento 14/08 (R$ 28.266 de quitação); em setembro restam R$ 790,70/mês de assinatura |
| **Portte Contábil** | 2.710 por empresa | sai com a contabilidade própria — R$ 65.040/ano nas duas |
| **Tratamento odontológico** | 4.625 | é do dono, não da empresa. Numa DRE que o banco vai ler, essa linha atrai pergunta |
| **Advogados — dívida de maio/2025** | 3.000 | pago pela Patrimonial, mas a Patrimonial nasceu em 31/03/2026. É dívida da irmã |

Sem a Sólides, agosto teria fechado em **+R$ 33.573,90 (12,8%)**. Com os outros três itens
fora, em **+R$ 41.198,90 (15,7%)**.

**Onde NÃO há o que cortar:** salário (50,6%) é o produto; a CCT define o piso e o efetivo é
o que os contratos exigem. Cortar ali é devolver posto.

---

## 5. O que precisa de decisão do dono

1. **Classificação previdenciária** (§2) — a mais urgente. É o que impede "toda regularizada".
2. **Faturamento de setembro** — 4 dos 7 clientes sem nota em 26/09, R$ 186.137,46.
3. **Odontológico e advogados** — sair da despesa da empresa? (implicação: vira distribuição
   ao sócio / conta entre as empresas do grupo).
4. **R$ 6.038,62 de julho** — o PGDAS-D declarou R$ 255.400,06 e as notas somam
   R$ 249.361,44 mesmo com a nota 13 restaurada. A numeração pula de 21 para 23: falta a
   NFS-e nº 22. Ou ela foi cancelada no fisco, ou houve receita sem nota.

---

## 6. Vigias novos

- `checar_patronal_nao_declarada.py` — empresa do Simples cuja CPP não está nem no DAS nem
  na DCTFWeb. Hoje: **2** (07 e 08/2026 da Patrimonial).
- `checar_fornecedor_saldo_invertido.py` — `2.1.4.01` com saldo devedor, ou seja, pagamento
  sem nota escriturada. Hoje: **1** (Patrimonial, −R$ 9.858,54).

O primeiro nasceu lendo o PDF da guia direto — e o container não tem `pdfplumber`, então ele
**alarmava sempre**, provando tanto quanto um verde cego. A composição por tributo agora é
extraída pelo `DASExtractor` na importação e gravada em `detalhes_json->composicao`; o
caçador lê do banco. Provado que sabe ir a 2 → 1 → 2 conforme o dado muda.
