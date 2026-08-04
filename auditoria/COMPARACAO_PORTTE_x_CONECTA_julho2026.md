# Folha 07/2026 — Portte (verdade) × Conecta PRO — o que falta e por quê

> Primeira comparação com oráculo real. Até aqui julho não tinha contra o que ser conferido.
> Fonte: 16 PDFs no Drive (7 condomínios + geral, dos dois lados).
> **Nada de código nesta rodada — só apontamento e entendimento.**

---

## 1. O veredito em uma linha

**A aritmética do nosso motor está certa. O que está errado é a BASE que entra nela.**

Prova: para a **mesma base**, INSS e FGTS batem ao centavo.
- Base 1.837,00 → nosso INSS 141,02 · Portte 141,01
- Base 1.920,50 → nosso 148,53 · Portte 148,52
- FGTS: exatos 8% nos dois

Ou seja: não há erro de cálculo de imposto. Há **verba que não entra na base**.

## 2. Os números

| | Portte | Conecta PRO | Δ |
|---|--:|--:|--:|
| Funcionários | **51** | **50** | **−1** |
| Proventos | 102.322,90 | 90.839,41 | −11.483,49 (−11,2%) |
| Descontos | 19.530,87 | 12.512,05 | −7.018,82 (−35,9%) |
| **Líquido** | **82.792,03** | **78.327,36** | **−4.464,67 (−5,4%)** |
| INSS retido | 7.727,80 | 6.902,52 | −825,28 |
| FGTS | 7.922,32 | 7.180,70 | −741,62 |

⚠️ **O Δ de −5,4% engana.** Ele é resultado de erros que se compensam: 29 pessoas abaixo e 17 acima.
A medida honesta é **Σ|Δ| individual = R$ 10.664,27** em 51 pessoas (~R$209 por pessoa).

---

## 3. O QUE FALTA — por família de causa

### 3.1 Tudo que depende de PONTO REAL (a maior massa)

| Rubrica | Descrição | Valor Portte |
|---|---|--:|
| 207 | HORA NOT REDUZIDA | 3.914,34 |
| 206 | ADICIONAL NOTURNO (INFOR) | 3.265,80 |
| 208 | INTRAJORNADA NOTURNA | 2.005,15 |
| 209 | INTRAJORNADA DIURNO | 1.738,82 |
| 8792 / 8794 / 8069 | DIAS FALTAS + DSR + HORAS FALTAS PARCIAL | 1.748,61 |
| 150 / 210 / 212 / 250 / 8125 | HORAS EXTRAS e reflexos DSR | 322,33 |

**Prova por pessoa:** AILTON tem base Portte 2.706,55 e nossa 1.920,50 — faltam **exatamente 786,05**
= hora not. reduzida 281,69 + intrajornada noturna 281,69 + adicional noturno 222,67. Não é
aproximação: é a soma exata das três rubricas.
CASTRO GAMA: Δ de base **240,06 exatos** = intrajornada diurno.

**Por que:** medi nesta mesma semana que o ponto do 12x36 noturno tinha só 9% dos dias pareados
(a jornada cruza a meia-noite e a agregação partia em dois). Corrigi o pareamento, mas o motor
ainda não consome esse ponto para produzir noturno/intrajornada/HE.

### 3.2 Tudo que depende de EVENTO DE RH

| Bloco | Rubricas | Efeito |
|---|---|---|
| **Férias** | 8783, 3, 931, 805, 806, 807, 8112, 8189, 8190, 8192 + descontos 937, 812, 821 | 3 pessoas em férias em julho; **pagaríamos +R$2.203,85 a mais** |
| **Afastamento** | 8785, 8801, 8870, 8932 | 779,33 de dias afastados não descontados |

O caso mais grave é o **adiantamento de férias: R$3.940,73** que a Portte desconta e nós não.
EDIWILSON: Portte paga 814,26; nós pagaríamos **1.774,65** (+960,39) porque ignoramos as férias
de 03–22/07 e o adiantamento já pago.

**Por que:** é exatamente o problema de adoção que medi ontem — o registro de férias cobre 18% da
realidade e o de afastamento 24%. O motor não erra: ele não tem o evento.

### 3.3 O que aplicamos como CONSTANTE e deveria ser proporcional

| Rubrica | Nosso | Portte |
|---|---|---|
| 48 VALE TRANSPORTE | 66,80 fixo para todos | proporcional aos dias (ex.: 64,57; 62,35; 60,12) |
| 201 INSALUBRIDADE | 167,00 fixo | proporcional (GRACIENE 150,30 por faltas) |
| 204 PLANO ODONTOLÓGICO | **9,00 de TODOS** | **8,50 e só de quem tem** |
| 202 ADICIONAL DE RONDA | aplicado a alguns | EULER ficou sem (250,50) — aplicação inconsistente nossa |

⚠️ **Estamos descontando odontológico de gente que não tem o plano.** Nos 3 condomínios auditados
em detalhe, 7 pessoas foram descontadas indevidamente. É dinheiro tirado do colaborador a mais.

### 3.4 Uma pessoa inteira sumiu

**ELEN XAVIER NUNES** (matrícula 47, afastada pelo INSS) **não existe na nossa folha**.
Portte: líquido 893,85. Nós: ausente. É o mesmo padrão de "não-ativo desaparece" que corrigi na
Fase E com o flag `historico` — mas aqui reapareceu por outro caminho.

---

## 4. ⚠️ ERRO MEU, DESCOBERTO POR ESTA COMPARAÇÃO

**NAILSON GARCIA GOMES** — Portte: `ARTÍFICE DE MANUTENÇÃO PREDIAL`, salário **R$2.186,66**.
Nós: `ARTÍFICE`, salário **R$1.742,52**. Diferença de **R$444,14 no salário cadastral**.

Fui **eu** que preenchi esse salário ontem. Ele estava sem cadastro, eu vi que os colegas
"ARTÍFICE" ganhavam 1.742,52 (= piso de `ARTIFICE NAO ESPECIALIZADO`) e apliquei o mesmo.

E eu **tinha escrito, no comentário do código**, que `ARTÍFICE` poderia casar erradamente com
`ARTIFICE DE MANUTENCAO PREDIAL (ESPECIALIZADO)` a R$2.186 — e usei isso como argumento para não
fazer match aproximado. **Caí exatamente no buraco que apontei**, só que pelo outro lado: presumi
o não-especializado.

O cargo dele no nosso cadastro está incompleto, e minha "evidência dos colegas" era um universo
enviesado (os outros dois artífices são não-especializados).

**Também errado:** EDIWILSON está como `LÍDER DE PORTARIA` no nosso cadastro; na Portte é
`ARTÍFICE` (CBO 514310). Salário coincide, cargo e CBO não.

---

## 5. O buraco estrutural do documento

**Nossa folha não tem quebra por rubrica.** Mostramos 4 números por pessoa
(`Base | INSS | FGTS | Descontos | Líquido`). A Portte mostra **linha a linha, com código,
descrição e quantidade**, mais um **"Resumo por Rubrica"** com as 39 verbas consolidadas.

Consequência prática: a comparação acima só foi possível por **engenharia reversa de totais**.
Um erro que se compensa entre duas rubricas passa invisível hoje.

Também faltam, e não são cosméticos:

| Falta | Por que importa |
|---|---|
| **CPF** | é a chave do PIX da folha e do eSocial |
| **Horas-mês (180 vs 220)** | é o **divisor do valor-hora** — sem ele não há HE correta |
| **Matrícula** | chave de conciliação com eSocial/DCTFWeb |
| **CBO** | obrigatório no eSocial |
| Situação (Trabalhando/Férias/Afastado) | explica por que o valor é diferente |
| Centro de custo / Depto / Filial | rateio |
| ND/NF (dependentes IRRF / salário-família) | base do benefício |
| Bases por pessoa (INSS, FGTS, IRRF) | nosso "Base" é salário nominal, **não** base de cálculo — é enganoso |
| Quadro de encargos + Situações | mesmo zerado (Simples Anexo III), o zero explícito prova que foi calculado |
| Notas de evento datadas | "FERIAS DE 03/07 A 22/07" explica o holerite ao colaborador |

---

## 6. Ordem de ataque sugerida (quando você mandar codar)

1. **Quebra por rubrica no documento** — sem isso, toda conciliação futura é engenharia reversa.
2. **Consumir o ponto real** para noturno, intrajornada e HE — é a maior massa (R$11,2k) e o ponto
   já foi corrigido esta semana.
3. **Bloco de férias** — é o único onde pagaríamos **a mais** (+R$2,2k); risco financeiro direto.
4. **Não perder o afastado** (ELEN) — headcount errado quebra eSocial e FGTS.
5. **Proporcionalizar** VT e insalubridade; **corrigir o odonto** (8,50, e só de quem tem).
6. **Corrigir cadastro**: NAILSON (2.186,66 + cargo) e EDIWILSON (ARTÍFICE/CBO 514310).
7. Campos cadastrais no PDF: CPF, matrícula, horas-mês, CBO.

## 7. O que já está certo — e vale preservar

- **INSS e FGTS ao centavo** para a mesma base
- **Salário-família exato** (ADEMIR 202,62; EDILENE conferido)
- **Nenhum provento inventado** — não fabricamos rubrica que a Portte não tenha
- **ADEMIR bate 100%** (Δ −0,51, só arredondamento de VT): quando temos todos os dados, o cálculo fecha


---

## 8. Por condomínio (7 pares conferidos)

| Condomínio | Pessoas (P×C) | Líquido Portte | Líquido nosso | Δ |
|---|:--:|--:|--:|--:|
| Ideal Flores | 13×13 | 19.766,90 | 18.949,89 | −817,01 |
| **Laranjeiras** | **9×8** | 14.484,18 | 13.416,58 | −1.067,60 |
| Mirante das Flores | 9×9 | 14.383,11 | 13.573,28 | −809,83 |
| **Michelangelo** | 2×2 | 2.492,60 | 3.300,90 | **+808,30** ⚠️ |
| Prime Arena | 6×6 | 10.606,01 | 9.905,13 | −700,88 |
| Villa Dei Fiori | 6×6 | 10.540,27 | 9.389,77 | −1.150,50 |
| Villa dos Pássaros | 6×6 | 10.518,96 | 9.791,81 | −727,15 |

**Michelangelo é o alerta:** somos **+R$808 MAIS CAROS** que a Portte. Causa única — ANTONIO
CARLOS VIEIRA esteve de férias 15/06–14/07 e nós **não descontamos o adiantamento** (R$1.100,13).
Sempre que houver férias, pagamos a mais. Não é erro pequeno: é dinheiro saindo indevidamente.

## 9. Casos que fecham 100% (a prova de que o motor funciona)

| Colaborador | Situação | Δ |
|---|---|--:|
| **KALEL SILVA DE JESUS** | proventos **idênticos** (1.916,77) | +16,49 (só a rubrica 205 que não temos) |
| **ADEMIR SALUSTIANO** | proventos idênticos, salário-família exato | −0,51 (arredondamento VT) |
| ANTONIO WALCICLEY · EDILENE | INSS conferido ao centavo | −0,51 |

Quando o colaborador **não tem evento** (sem férias, sem falta, sem noturno), nossa folha bate.
Isso delimita o problema com precisão: **não é o cálculo, é o evento que não chega.**

## 10. Mais dois erros de cadastro achados pela comparação

| Campo | Nosso | Portte |
|---|---|---|
| **NAILSON — salário/cargo** | 1.742,52 · ARTÍFICE | **2.186,66** · ARTÍFICE DE MANUTENÇÃO PREDIAL |
| **EDIWILSON — cargo/CBO** | LÍDER DE PORTARIA | **ARTÍFICE** (CBO 514310) |
| **KELLY e ALEXANDRE — admissão** | 19/07 → contamos **13 dias** | 20/07 → conta **11 dias** |
| Grafias | BIANCA HELEM · FAÇANHA · OSCAR "DA" COSTA | HELLEM · FACANHA · OSCAR COSTA |

A data de admissão diverge em um dia e o cálculo de dias em dois — vale conferir qual é a
correta no contrato, porque afeta o proporcional de quem entrou em julho.

## 11. Ronda e salário-família: temos a rubrica, não aplicamos a todos

- **202 ADICIONAL DE RONDA** não lançado para **DANIEL SOUZA** (−225,45) e **EULER FELIPE**
  (−250,50), enquanto colegas idênticos receberam. É cobertura de cadastro, não motor.
- **995 SALÁRIO FAMÍLIA** omitido para **ALEXANDRE** (24,76) — funciona nos outros.

## 12. Resumo executivo dos números

| Métrica | Valor |
|---|--:|
| Δ líquido agregado (51 pessoas) | −R$ 4.464,67 (−5,4%) |
| **Σ\|Δ\| individual — a medida honesta** | **R$ 10.664,27** |
| Proventos que não sabemos calcular | R$ 11.483,49 |
| Descontos que não sabemos calcular | R$ 7.018,82 |
| Maior bloco ausente | Férias (prov. 5.171 + desc. 4.303) |
| Segundo maior | Noturno + intrajornada (R$ 9.185) |
| Onde pagamos A MAIS | Férias sem adiantamento e faltas sem desconto |

---

# ADENDO — 2ª passada: Portte × BANCO (não o PDF)

A 1ª passada leu nosso **PDF**, que não mostra rubricas. Esta lê o **banco**
(`hr_payslips.earnings/deductions`), onde a composição existe. Resultado: **corrige três
conclusões da 1ª passada e revela dois defeitos que o PDF jamais mostraria.**

## Nossa folha emite exatamente 12 rubricas

| | Cód | Descrição | Pessoas | Total |
|---|---|---|--:|--:|
| P | 0001 | Salário Base | 50 | 81.190,06 |
| P | 0018 | Adicional de Ronda | 13 | 3.291,76 |
| P | 0016 | Adicional de Insalubridade | 11 | 1.851,50 |
| P | **0020** | **Adicional Noturno** | 23 | 1.806,92 |
| P | 0021 | Adic. Hora Noturna Reduzida | 19 | 1.129,18 |
| P | **0020** | **Salário Família** | 10 | 1.080,64 |
| P | 0090 | DSR sobre Verbas Variáveis | 23 | 489,35 |
| D | 1001 | INSS | 50 | 6.902,52 |
| D | 1010 | Desconto VT | 50 | 3.247,60 |
| D | 1030 | Taxa Negocial CCT | 50 | 1.100,00 |
| D | 1011 | Desconto VR | 50 | 811,93 |
| D | 1020 | Plano Odontológico | 50 | 450,00 |

## 🔴 DEFEITO NOVO — código de rubrica DUPLICADO

**`0020` é usado por DUAS rubricas diferentes: "Adicional Noturno" e "Salário Família".**

O PDF nunca mostraria isso porque não imprime código. Consequências:
- **Quebra o eSocial**: `codRubr` é chave na Tabela de Rubricas (S-1010) e no S-1200. Duas
  naturezas jurídicas distintas sob o mesmo código = evento rejeitado ou, pior, aceito errado
  (salário-família **não** incide INSS/FGTS; adicional noturno **incide**).
- Quebra qualquer conciliação por código.

## Correção de 3 conclusões da 1ª passada

A 1ª passada afirmou que 206 e 207 **"NÃO existem no nosso cálculo (provado)"**. **Errado** —
existem, mas **subcalculados**. O PDF escondia.

| Portte | Nosso (banco) | Δ real |
|---|--:|--:|
| 207 HORA NOT REDUZIDA — 3.914,34 | 0021 — **1.129,18** | **−2.785,16** |
| 206 ADICIONAL NOTURNO — 3.265,80 | 0020 — **1.806,92** | **−1.458,88** |
| 208 INTRAJORNADA NOTURNA — 2.005,15 | **ausente de verdade** | −2.005,15 |
| 209 INTRAJORNADA DIURNO — 1.738,82 | **ausente de verdade** | −1.738,82 |
| 202 ADICIONAL DE RONDA — 3.725,41 | 0018 — 3.291,76 | −433,65 |

Isso muda o diagnóstico: noturno **não é rubrica faltante, é rubrica com valor errado** (o motor
produz ~29% e ~55% do devido). Intrajornada, sim, é ausência total.

## 🔴 Dois lugares onde pagamos A MAIS (o PDF não revelou)

| Rubrica | Portte | Nosso | Δ |
|---|--:|--:|--:|
| **Salário Família** | 763,20 (12 cotas) | **1.080,64** (10 pessoas) | **+317,44** |
| Insalubridade | 1.784,95 | 1.851,50 | +66,55 |
| DSR s/ variáveis | 33,19 (só reflexo de extras) | **489,35** | **+456,16** |

**Salário-família é o mais grave**: pagamos 41% a mais que a Portte com *menos* pessoas.
Ou o valor da cota está errado, ou estamos dando a quem não tem direito (teto de renda), ou
contando dependentes a mais. Requer conferência caso a caso.

**DSR sobre variáveis**: emitimos R$489 sobre um conceito que a Portte praticamente não usa
(ela só tem R$33 de reflexo de horas extras). Ou estamos certos e ela não paga, ou estamos
inventando reflexo. **Precisa de definição — é dinheiro.**

## Conclusão da 2ª passada

Valeu a pena, e por um motivo específico: **a limitação da 1ª passada não era atenção, era fonte.**
Reler o mesmo PDF daria a mesma resposta. Trocar a fonte revelou o código duplicado, corrigiu o
diagnóstico do noturno e achou R$840 de pagamento a maior que estavam invisíveis.

**Ordem de ataque revisada:**
1. **Código 0020 duplicado** — barato de corrigir, e bloqueia o eSocial se não for
2. **Salário-família +R$317 e DSR +R$456** — pagamento a maior, dinheiro saindo hoje
3. Noturno subcalculado (não ausente) — investigar por que produz 29% do devido
4. Intrajornada (209/208) — ausência real
5. Férias — o maior bloco, e onde mais pagamos a mais
