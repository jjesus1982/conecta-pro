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
