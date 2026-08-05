# Bloco de férias — implementado · 05/08/2026

> Task 5 das 5 frentes. Fórmulas derivadas da folha 07/2026 da Portte e conferidas **ao
> centavo** nos 3 casos reais do mês. No ar e persistido.

---

## 1. A causa era mais simples do que o apontamento

O relatório de comparação dizia "13 rubricas de férias ausentes". Verdade, mas não era o
problema. O problema era:

> **Pagávamos o mês CHEIO a quem estava de férias** — e as férias já haviam sido pagas no
> adiantamento, até 2 dias antes do gozo (art. 145 CLT).

Duplicidade pura. **R$2.473,19 a mais em 3 pessoas, só em julho.**

A prova é aritmética direta:

```
EDIWILSON — Portte paga DIAS NORMAIS 10 dias  =   595,84
            nós pagávamos o mês cheio         = 1.787,53
            diferença                           1.191,69  ← exatamente os DIAS FERIAS
```

## 2. As fórmulas, derivadas do dado real

A folha da Portte traz a coluna **REFERÊNCIA** (as horas/dias de cada rubrica). Foi ela que
permitiu derivar em vez de adivinhar. Conferido nos 3 casos, sem exceção:

| fórmula | |
|---|---|
| **dias férias** | salário / 30 × dias |
| **vantagens** | adicionais habituais (peric + insal + ronda) × dias / 30 |
| **1/3** | **(férias + vantagens) / 3** — incide sobre a remuneração, não só sobre os dias |
| **adiantamento** | (tudo acima) − INSS férias |

Verificação do 1/3 — o ponto que eu teria errado se tivesse presumido:

```
EDIWILSON  1.191,69 + 134,19 + 178,75 = 1.504,63 / 3 = 501,54 ✓
FRANCISCO    556,67 + 172,46 +  83,50 =   812,63 / 3 = 270,88 ✓
ANTONIO      813,18 +   2,71 +  81,32 + 0,15 = 897,36 / 3 = 299,12 ✓
```

Verificação do adiantamento:

```
EDIWILSON  2.006,17 − 156,23 = 1.849,94 ✓
FRANCISCO  1.083,51 −  92,85 =   990,66 ✓
ANTONIO    1.196,48 −  96,35 = 1.100,13 ✓
```

O adiantamento **anula** os proventos de férias no mês. O que sobra é o que foi trabalhado —
que é exatamente o comportamento correto.

## 3. Fonte de dados: só solicitação APROVADA

`hr_vacation_requests` com `status='APPROVED'`. **Isso não é detalhe.**

Em julho havia **5 solicitações `SUBMITTED` de 30 dias** — ANILSON, ADEMIR, ANDREW, ADAILSON,
AILTON — de gente que trabalhou o mês inteiro. O ADAILSON bateu ponto **116 vezes** em julho.
Contar pedido não aprovado como férias teria tirado meio salário de cinco pessoas.

## 4. Resultado

| pessoa | antes | agora | Portte |
|---|--:|--:|--:|
| ANTONIO CARLOS VIEIRA | +791,81 | **+121,89** | 858,64 |
| EDIWILSON CORREA | +1.069,49 | **−9,46** | 814,26 |
| FRANCISCO RAMON | +611,89 | **+167,57** | 1.205,82 |
| **Σ\|Δ\|** | **2.473,19** | **298,92** | **−88%** |

**Zero regressão:** dos 53 holerites de julho, **só os 3 de férias mudaram**. Total do mês:
R$90.582,48 → **R$88.389,29**. Persistido e baked.

## 5. Os dois resíduos — declarados, não estimados

**a) Média do art. 142** (rubrica 806 da Portte, R$134–172 por pessoa). Exige **12 meses** de
histórico e temos 6 (jan–jun/2026); a outra metade do período aquisitivo está em 2025, na
Portte. Testei derivar da média simples do espelho e não fecha:

| | nosso cálculo | Portte |
|---|--:|--:|
| FRANCISCO | 18,73 | 172,46 |
| EDIWILSON | 160,85 | 134,19 |

Não estimei. Como ela entraria dos **dois lados** (provento e adiantamento), mexe pouco no
líquido e muito na **base de INSS/FGTS** — que é o que vai para o eSocial.

**b) Os 3 registros estão exatamente 1 dia curtos** contra a Portte em `hr_vacation_requests`.
Padrão consistente demais para ser coincidência. É dado do DP, não fórmula.

## 6. A programação de férias 2026 — o que ela é e o que não é

Arquivo em `auditoria/ferias_programacao/`. CNPJ **Eletrônica**, emitida **08/01/2026**,
47 empregados.

**É** relatório de saldo/direito: período aquisitivo real, dias de direito (já reduzidos por
falta, art. 130 — daí os 22,5 / 17,5 / 12,5) e **limite para gozo** por pessoa.

**NÃO é** agendamento: a coluna "Início gozo férias" está vazia para todos os 47.

⚠️ **"Dias goz. = 0" é o estado de janeiro**, não o atual. Carregar por cima apagaria os dias
gozados que foram corrigidos em 04/08 a partir de evidência da folha.

O que ela habilita: alimentar `employee_vacation_periods` (congelada desde março) com período
aquisitivo e limite reais, e ligar o alerta de férias em dobro de forma contínua.

## 7. Um caso conferido e retirado

Cruzei os 13 destacados da programação contra a folha real. **12 regularizaram** entre
fevereiro e junho — a programação é foto de janeiro, anterior aos gozos.

O 13º, **ARYELTON BRAGA FIGUEIRA**, eu havia levantado como risco de férias em dobro
(limite 22/06 sem gozo). **Retirado**: o Jordan esclareceu que o contrato está **suspenso** por
orientação do escritório jurídico, com ação de rescisão indireta em curso. Com o contrato
suspenso a contagem do aquisitivo não corre — não há art. 137.

O sistema já o trata certo, sem intervenção: fora da folha de julho, 0 turnos lançados, 0
batidas desde junho. A Portte parou no mesmo mês.

**Regra para o futuro:** o alerta de "férias vencendo" precisa **pular contrato suspenso**,
senão ele volta como falso positivo todo mês.

Ponta solta (operacional, do Jordan): ele ainda tem **alocação ativa** em
`employee_alocacoes`, o que pode exibi-lo em relatório de cobertura.

---

## Estado das 5 frentes

| | frente | |
|---|---|---|
| 1 | Rubrica 0020 duplicada | ✅ |
| 2 | Salário-família | 🟡 falta o **teto oficial 2026** |
| 3+4 | Noturno / intrajornada | ✅ Σ\|Δ\| −72% |
| 5 | **Férias** | ✅ **Σ\|Δ\| −88%** |
| 6 | Script oficial | ✅ |

**Resíduo que atravessa tudo:** as rubricas ficam ~11% acima da Portte porque contamos plantão
**agendado** e ela desconta **falta**. Não é código — é adoção do DP.
