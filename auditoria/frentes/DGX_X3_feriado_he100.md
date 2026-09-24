# DGX X3 — Feriado trabalhado e HE 100%: o que a CCT manda pagar e o motor não produz (24/09/2026)

**Branch:** `dgx/x3-feriado-he100` (base `327297120`, fase5-hermes-camada-cognitiva)
**Módulo:** folha (`folha_feriado_conferencia` + 2 linhas em `ponto_evento_rubrica`) · **Sessão:** agent-x3
**Paralelo cego.** `calculo_service.py` NÃO foi tocado — só LIDO. Nenhum holerite mudou
(o oráculo prova: Σ|Δ| em `hr_payslips` = R$ 0,00). DDL idempotente aplicada só no sandbox; em
produção acontece no 1º acesso à aba. **Container HTTP:** `teste-dgx-x3`, porta 8263 — **parado ao fim**.

---

## 1. O §1: quem trabalhou em feriado, o que recebeu, e o que a regra manda pagar

**O passivo medido em 07, 08 e 09/2026 é de R$ 5.399,01**, em 71 linhas nominais — 42 de feriado
trabalhado (todas em 09/2026) e 29 de hora extra que o espelho já classificou como 100% e a folha
pagou como 50% ou não pagou.

### Como o número foi feito (cada peça é dado, nenhuma é estimativa)

| Peça | De onde vem |
|---|---|
| **Quem tinha turno** | `shifts` (status ≠ cancelled, não `is_off_day`) — vira a coluna «Tinha escala?» |
| **Quem bateu** | `gp_clock_punches`, pareadas pelas primitivas do `horas_service` (`dia_do_plantao`, `janelas_de_turno`, `MAX_TURNO_H`) — a régua do «um plantão é UM dia» (DGX V1/W1) |
| **Quais dias são feriado para aquela pessoa** | `config_ponto.feriados_do_periodo` (DGX F7) — **importada, não recriada**: feriado de CLIENTE vale só para o condomínio dele; estadual/municipal, só para o condomínio da mesma UF/cidade |
| **O que o holerite pagou** | `hr_payslips.earnings` da competência, códigos `0011` (HE 100%), `0040`/`0070`/`0010` (HE 50%) |
| **O valor-hora** | `hr_payslips.base_salary` (a base pós-piso que o motor usou) ÷ divisor da escala (180 no 12x36, 220 no 44h) — a mesma conta do `calculo_service` L404-406 |
| **O que a regra manda** | dobra do plantão (feriado) ou 2× o valor-hora (HE 100%) — ver §2 |

### 1.1 Feriado trabalhado — os 2 feriados de setembro

Em 07–09/2026 há **2 feriados** em `cct_feriados`: **05/09 Elevação do Amazonas** (estadual/AM) e
**07/09 Independência** (nacional). Em cada um, **21 pessoas trabalharam** (42 linhas). O holerite
de 09/2026 pagou, para esses dias, **a primeira vez apenas** — dentro do salário mensal (verba
0001). A verba `0011 Hora Extra 100%` **não aparece em nenhum holerite de 2026**. Nenhum
adicional de feriado foi emitido por ninguém.

### feriado_trabalhado — 42 linha(s) · Σ diferença R$ 3.723,20

| Competência | Dia | Colaborador | Escala | Horas | Valor-hora | Pago | Deveria ser | **Diferença** | Motivo |
|---|---|---|---|---|---|---|---|---|---|
| 09/2026 | 07/09 | KELLY PATRICIA DA SILVA DE SOUZA | 12x36 | 12.52h | R$ 9,28 | R$ 116,19 | R$ 232,37 | **R$ 116,18** | Independencia do Brasil |
| 09/2026 | 05/09 | ANTONIO CARLOS CASTRO GAMA | 12x36 | 12.09h | R$ 9,28 | R$ 112,20 | R$ 224,39 | **R$ 112,19** | Elevacao do Amazonas a Categoria de Provincia |
| 09/2026 | 07/09 | ANTONIO DINIZ ASSIS DOS SANTOS | 12x36 | 12.05h | R$ 9,28 | R$ 111,82 | R$ 223,65 | **R$ 111,83** | Independencia do Brasil |
| 09/2026 | 05/09 | CARLOS EDUARDO DA SILVA FAÇANHA | 12x36 | 12.01h | R$ 9,28 | R$ 111,45 | R$ 222,91 | **R$ 111,46** | Elevacao do Amazonas a Categoria de Provincia |
| 09/2026 | 05/09 | RENE RICARDO CRUZ GONÇALVES | 12x36 | 12.01h | R$ 9,28 | R$ 111,45 | R$ 222,91 | **R$ 111,46** | Elevacao do Amazonas a Categoria de Provincia |
| 09/2026 | 07/09 | ALEXANDRE SOUZA DA SILVA | 12x36 | 12.01h | R$ 9,28 | R$ 111,45 | R$ 222,91 | **R$ 111,46** | Independencia do Brasil |
| 09/2026 | 05/09 | ANTONIO DINIZ ASSIS DOS SANTOS | 12x36 | 12.00h | R$ 9,28 | R$ 111,36 | R$ 222,72 | **R$ 111,36** | Elevacao do Amazonas a Categoria de Provincia |
| 09/2026 | 05/09 | FERNANDO SOUZA SIMPLICIO JUNIOR | 12x36 | 12.00h | R$ 9,28 | R$ 111,36 | R$ 222,72 | **R$ 111,36** | Elevacao do Amazonas a Categoria de Provincia |
| 09/2026 | 05/09 | RUAN RODRIGUES FIGUEIREDO | 12x36 | 12.00h | R$ 9,28 | R$ 111,36 | R$ 222,72 | **R$ 111,36** | Elevacao do Amazonas a Categoria de Provincia |
| 09/2026 | 07/09 | FERNANDO SOUZA SIMPLICIO JUNIOR | 12x36 | 12.00h | R$ 9,28 | R$ 111,36 | R$ 222,72 | **R$ 111,36** | Independencia do Brasil |
| 09/2026 | 07/09 | EDUARDO OLIVEIRA DE SOUZA | 12x36 | 11.99h | R$ 9,28 | R$ 111,27 | R$ 222,53 | **R$ 111,26** | Independencia do Brasil |
| 09/2026 | 07/09 | RENE RICARDO CRUZ GONÇALVES | 12x36 | 11.97h | R$ 9,28 | R$ 111,08 | R$ 222,16 | **R$ 111,08** | Independencia do Brasil |
| 09/2026 | 07/09 | CARLOS EDUARDO DA SILVA FAÇANHA | 12x36 | 11.94h | R$ 9,28 | R$ 110,80 | R$ 221,61 | **R$ 110,81** | Independencia do Brasil |
| 09/2026 | 05/09 | EDUARDO OLIVEIRA DE SOUZA | 12x36 | 11.89h | R$ 9,28 | R$ 110,34 | R$ 220,68 | **R$ 110,34** | Elevacao do Amazonas a Categoria de Provincia |
| 09/2026 | 05/09 | ALEXANDRE SOUZA DA SILVA | 12x36 | 11.82h | R$ 9,28 | R$ 109,69 | R$ 219,38 | **R$ 109,69** | Elevacao do Amazonas a Categoria de Provincia |
| 09/2026 | 05/09 | ERIKA CRISTINA MAQUINE PEREIRA | 12x36 | 11.02h | R$ 9,93 | R$ 109,43 | R$ 218,86 | **R$ 109,43** | Elevacao do Amazonas a Categoria de Provincia |
| 09/2026 | 07/09 | RUAN RODRIGUES FIGUEIREDO | 12x36 | 11.58h | R$ 9,28 | R$ 107,46 | R$ 214,92 | **R$ 107,46** | Independencia do Brasil |
| 09/2026 | 07/09 | ERIKA CRISTINA MAQUINE PEREIRA | 12x36 | 10.67h | R$ 9,93 | R$ 105,95 | R$ 211,91 | **R$ 105,96** | Independencia do Brasil |
| 09/2026 | 05/09 | ADEILSON DINIZ DEODATO | 12x36 | 11.08h | R$ 9,28 | R$ 102,82 | R$ 205,64 | **R$ 102,82** | Elevacao do Amazonas a Categoria de Provincia |
| 09/2026 | 05/09 | FRANCISCO RAMON FARIAS DE SOUZA | 12x36 | 11.04h | R$ 9,28 | R$ 102,45 | R$ 204,90 | **R$ 102,45** | Elevacao do Amazonas a Categoria de Provincia |
| 09/2026 | 07/09 | JONHATA DINIZ BENAION | 12x36 | 11.03h | R$ 9,28 | R$ 102,36 | R$ 204,72 | **R$ 102,36** | Independencia do Brasil |
| 09/2026 | 05/09 | ANDREA GONÇALVES DOS SANTOS | 12x36 | 11.00h | R$ 9,28 | R$ 102,08 | R$ 204,16 | **R$ 102,08** | Elevacao do Amazonas a Categoria de Provincia |
| 09/2026 | 07/09 | DANIEL VIDAL LARROQUE | 12x36 | 11.00h | R$ 9,28 | R$ 102,08 | R$ 204,16 | **R$ 102,08** | Independencia do Brasil |
| 09/2026 | 07/09 | FRANCISCO RAMON FARIAS DE SOUZA | 12x36 | 11.00h | R$ 9,28 | R$ 102,08 | R$ 204,16 | **R$ 102,08** | Independencia do Brasil |
| 09/2026 | 05/09 | DANIEL VIDAL LARROQUE | 12x36 | 10.99h | R$ 9,28 | R$ 101,99 | R$ 203,97 | **R$ 101,98** | Elevacao do Amazonas a Categoria de Provincia |
| 09/2026 | 07/09 | ADAILSON SERRA ALVES | 12x36 | 10.99h | R$ 9,28 | R$ 101,99 | R$ 203,97 | **R$ 101,98** | Independencia do Brasil |
| 09/2026 | 07/09 | ANDREA GONÇALVES DOS SANTOS | 12x36 | 10.99h | R$ 9,28 | R$ 101,99 | R$ 203,97 | **R$ 101,98** | Independencia do Brasil |
| 09/2026 | 05/09 | MATHEUS HENRIQUE CABRAL DA SILVA | 12x36 | 10.97h | R$ 9,28 | R$ 101,80 | R$ 203,60 | **R$ 101,80** | Elevacao do Amazonas a Categoria de Provincia |
| 09/2026 | 07/09 | MATHEUS HENRIQUE CABRAL DA SILVA | 12x36 | 10.83h | R$ 9,28 | R$ 100,50 | R$ 201,00 | **R$ 100,50** | Independencia do Brasil |
| 09/2026 | 07/09 | ADEILSON DINIZ DEODATO | 12x36 | 9.60h | R$ 9,28 | R$ 89,09 | R$ 178,18 | **R$ 89,09** | Independencia do Brasil |
| 09/2026 | 07/09 | ANTONIO CARLOS CASTRO GAMA | 12x36 | 7.98h | R$ 9,28 | R$ 74,05 | R$ 148,11 | **R$ 74,06** | Independencia do Brasil |
| 09/2026 | 07/09 | MEIRE GABRIELA DA SILVA E SILVA | 12x36 | 12.57h | R$ 5,57 | R$ 70,01 | R$ 140,03 | **R$ 70,02** | Independencia do Brasil |
| 09/2026 | 05/09 | MEIRE GABRIELA DA SILVA E SILVA | 12x36 | 12.00h | R$ 5,57 | R$ 66,84 | R$ 133,68 | **R$ 66,84** | Elevacao do Amazonas a Categoria de Provincia |
| 09/2026 | 05/09 | JONHATA DINIZ BENAION | 12x36 | 7.00h | R$ 9,28 | R$ 64,96 | R$ 129,92 | **R$ 64,96** | Elevacao do Amazonas a Categoria de Provincia |
| 09/2026 | 07/09 | KALEL SILVA DE JESUS | 44h | 4.00h | R$ 7,92 | R$ 31,68 | R$ 63,36 | **R$ 31,68** | Independencia do Brasil |
| 09/2026 | 07/09 | GRACIENE PEREIRA DE CASTRO | 44h | 4.05h | R$ 7,59 | R$ 30,74 | R$ 61,48 | **R$ 30,74** | Independencia do Brasil |
| 09/2026 | 07/09 | TELMA MARIA LAGES MEIRA | 44h | 4.01h | R$ 7,59 | R$ 30,44 | R$ 60,87 | **R$ 30,43** | Independencia do Brasil |
| 09/2026 | 05/09 | ANTONIO CARLOS VIEIRA | 44h | 3.84h | R$ 7,92 | R$ 30,41 | R$ 60,83 | **R$ 30,42** | Elevacao do Amazonas a Categoria de Provincia |
| 09/2026 | 05/09 | GEILSON RODRIGUES DE ANDRADE | 44h | 4.00h | R$ 7,59 | R$ 30,36 | R$ 60,72 | **R$ 30,36** | Elevacao do Amazonas a Categoria de Provincia |
| 09/2026 | 05/09 | VANDERLICE SANTOS DA SILVA | 44h | 3.99h | R$ 7,59 | R$ 30,28 | R$ 60,57 | **R$ 30,29** | Elevacao do Amazonas a Categoria de Provincia |
| 09/2026 | 05/09 | GRACIENE PEREIRA DE CASTRO | 44h | 3.73h | R$ 7,59 | R$ 28,31 | R$ 56,62 | **R$ 28,31** | Elevacao do Amazonas a Categoria de Provincia |
| 09/2026 | 05/09 | ADAILSON SERRA ALVES | 12x36 | 3.00h | R$ 9,28 | R$ 27,84 | R$ 55,68 | **R$ 27,84** | Elevacao do Amazonas a Categoria de Provincia |


### 1.2 Hora extra que deveria ser 100% e saiu como 50% (ou não saiu)

O espelho de ponto (`time_sheets.daily_summary`) **já classifica** o dia: `overtime_type = '100'`
quando é feriado (12x36) ou feriado/domingo/dia de descanso (44h) — `espelho_service.py` L551-553.
Medido nas três competências: **53 dias-pessoa com `overtime_type = 100`, 136,58 h**. A folha não
lê `time_sheets` para HE: a verba `0040` sai do excedente MENSAL sobre o divisor da escala
(`calculo_service.py` L608-623), a 1,5 — sem olhar em que dia a hora caiu. Resultado nas três
competências: **`0040` emitida 2× em 08/2026 (R$ 208,94), `0070` 20× em 07/2026 (R$ 280,53), nada
em 09/2026** — e `0011` zero vezes.

As linhas abaixo são as de HE 100% **fora de feriado** (domingo / dia de descanso). As que caem em
feriado não entram aqui: a dobra do plantão inteiro (§1.1) já as cobre, e somar as duas seria
pagar a mesma hora duas vezes.

### he100 — 29 linha(s) · Σ diferença R$ 1.675,81

| Competência | Dia | Colaborador | Escala | Horas | Valor-hora | Pago | Deveria ser | **Diferença** | Motivo |
|---|---|---|---|---|---|---|---|---|---|
| 08/2026 | 02/08 | DANIEL VIDAL LARROQUE | 12x36 | 4.13h | R$ 9,28 | R$ 0,00 | R$ 76,65 | **R$ 76,65** | domingo / dia de descanso (espelho) |
| 09/2026 | 06/09 | KALEL SILVA DE JESUS | 44h | 4.03h | R$ 7,92 | R$ 0,00 | R$ 63,84 | **R$ 63,84** | domingo / dia de descanso (espelho) |
| 07/2026 | 12/07 | KALEL SILVA DE JESUS | 44h | 4.00h | R$ 7,92 | R$ 0,00 | R$ 63,36 | **R$ 63,36** | domingo / dia de descanso (espelho) |
| 07/2026 | 26/07 | KALEL SILVA DE JESUS | 44h | 4.00h | R$ 7,92 | R$ 0,00 | R$ 63,36 | **R$ 63,36** | domingo / dia de descanso (espelho) |
| 08/2026 | 02/08 | ANTONIO CARLOS VIEIRA | 44h | 3.98h | R$ 7,92 | R$ 0,00 | R$ 63,04 | **R$ 63,04** | domingo / dia de descanso (espelho) |
| 09/2026 | 13/09 | ANTONIO CARLOS VIEIRA | 44h | 3.93h | R$ 7,92 | R$ 0,00 | R$ 62,25 | **R$ 62,25** | domingo / dia de descanso (espelho) |
| 07/2026 | 12/07 | PAULO DA SILVA LAMEGO | 44h | 4.10h | R$ 7,59 | R$ 0,00 | R$ 62,24 | **R$ 62,24** | domingo / dia de descanso (espelho) |
| 07/2026 | 26/07 | PAULO DA SILVA LAMEGO | 44h | 4.10h | R$ 7,59 | R$ 0,00 | R$ 62,24 | **R$ 62,24** | domingo / dia de descanso (espelho) |
| 07/2026 | 05/07 | FERNANDO MIGUEL GOMES DA SILVA | 44h | 4.00h | R$ 7,59 | R$ 0,00 | R$ 60,72 | **R$ 60,72** | domingo / dia de descanso (espelho) |
| 07/2026 | 05/07 | JAQUELINE CARLOS DOS SANTOS | 44h | 4.00h | R$ 7,59 | R$ 0,00 | R$ 60,72 | **R$ 60,72** | domingo / dia de descanso (espelho) |
| 07/2026 | 19/07 | JAQUELINE CARLOS DOS SANTOS | 44h | 4.00h | R$ 7,59 | R$ 0,00 | R$ 60,72 | **R$ 60,72** | domingo / dia de descanso (espelho) |
| 08/2026 | 02/08 | JAQUELINE CARLOS DOS SANTOS | 44h | 4.00h | R$ 7,59 | R$ 0,00 | R$ 60,72 | **R$ 60,72** | domingo / dia de descanso (espelho) |
| 08/2026 | 02/08 | PAULO DA SILVA LAMEGO | 44h | 4.00h | R$ 7,59 | R$ 0,00 | R$ 60,72 | **R$ 60,72** | domingo / dia de descanso (espelho) |
| 08/2026 | 09/08 | ANGELA LOPES MACEDO | 44h | 4.00h | R$ 7,59 | R$ 0,00 | R$ 60,72 | **R$ 60,72** | domingo / dia de descanso (espelho) |
| 09/2026 | 06/09 | ANGELA LOPES MACEDO | 44h | 4.00h | R$ 7,59 | R$ 0,00 | R$ 60,72 | **R$ 60,72** | domingo / dia de descanso (espelho) |
| 09/2026 | 06/09 | JAQUELINE CARLOS DOS SANTOS | 44h | 4.00h | R$ 7,59 | R$ 0,00 | R$ 60,72 | **R$ 60,72** | domingo / dia de descanso (espelho) |
| 09/2026 | 06/09 | PAULO DA SILVA LAMEGO | 44h | 4.00h | R$ 7,59 | R$ 0,00 | R$ 60,72 | **R$ 60,72** | domingo / dia de descanso (espelho) |
| 09/2026 | 13/09 | JAQUELINE CARLOS DOS SANTOS | 44h | 4.00h | R$ 7,59 | R$ 0,00 | R$ 60,72 | **R$ 60,72** | domingo / dia de descanso (espelho) |
| 07/2026 | 19/07 | EDILENE SALES SOUSA | 44h | 3.98h | R$ 7,59 | R$ 0,00 | R$ 60,42 | **R$ 60,42** | domingo / dia de descanso (espelho) |
| 07/2026 | 19/07 | PAULO DA SILVA LAMEGO | 44h | 3.98h | R$ 7,59 | R$ 0,00 | R$ 60,42 | **R$ 60,42** | domingo / dia de descanso (espelho) |
| 09/2026 | 13/09 | PAULO DA SILVA LAMEGO | 44h | 3.98h | R$ 7,59 | R$ 0,00 | R$ 60,42 | **R$ 60,42** | domingo / dia de descanso (espelho) |
| 08/2026 | 09/08 | PAULO DA SILVA LAMEGO | 44h | 3.97h | R$ 7,59 | R$ 0,00 | R$ 60,26 | **R$ 60,26** | domingo / dia de descanso (espelho) |
| 09/2026 | 06/09 | CELIANE GARCIA DE SOUSA | 44h | 3.97h | R$ 7,59 | R$ 0,00 | R$ 60,26 | **R$ 60,26** | domingo / dia de descanso (espelho) |
| 07/2026 | 26/07 | ANGELA LOPES MACEDO | 44h | 4.00h | R$ 7,59 | R$ 1,30 | R$ 60,72 | **R$ 59,42** | domingo / dia de descanso (espelho) |
| 07/2026 | 12/07 | ANGELA LOPES MACEDO | 44h | 3.98h | R$ 7,59 | R$ 1,29 | R$ 60,42 | **R$ 59,13** | domingo / dia de descanso (espelho) |
| 07/2026 | 05/07 | CELIANE GARCIA DE SOUSA | 44h | 4.00h | R$ 7,59 | R$ 12,33 | R$ 60,72 | **R$ 48,39** | domingo / dia de descanso (espelho) |
| 07/2026 | 26/07 | CELIANE GARCIA DE SOUSA | 44h | 4.00h | R$ 7,59 | R$ 12,33 | R$ 60,72 | **R$ 48,39** | domingo / dia de descanso (espelho) |
| 07/2026 | 19/07 | ANTONIO CARLOS VIEIRA | 44h | 4.00h | R$ 4,22 | R$ 0,00 | R$ 33,76 | **R$ 33,76** | domingo / dia de descanso (espelho) |
| 07/2026 | 05/07 | PAULO DA SILVA LAMEGO | 44h | 0.05h | R$ 7,59 | R$ 0,00 | R$ 0,76 | **R$ 0,76** | domingo / dia de descanso (espelho) |


### 1.3 Os totais por competência

| Competência | Linhas | Pessoas | Feriados com gente | Horas | Pago | Devido pela regra | **Diferença** |
|---|---|---|---|---|---|---|---|
| 07/2026 | 15 (só he100) | 8 | — (nenhum feriado em julho) | 56,19h | R$ 27,25 | R$ 831,30 | **R$ 804,05** |
| 08/2026 | 6 (só he100) | 5 | — (nenhum feriado em agosto) | 24,08h | R$ 0,00 | R$ 382,11 | **R$ 382,11** |
| 09/2026 | 50 (42 feriado + 8 he100) | 28 | 2 (05/09 e 07/09) | 446,17h | R$ 3.723,17 | R$ 7.936,02 | **R$ 4.212,85** |
| **Total** | **71** | — | **2** | **526,44h** | **R$ 3.750,42** | **R$ 9.149,43** | **R$ 5.399,01** |

### 1.4 O que o número NÃO é

- **Não é o passivo total da empresa.** São três competências e **dois** feriados. O ano de 2026
  tem 16 feriados em `cct_feriados`: 14 estão fora desta janela e não foram apurados. A tela apura
  qualquer competência que o dono escolher.
- **Não considera compensação.** A lei fala em feriado **não compensado**. Não existe registro de
  folga compensatória em lugar nenhum do sistema — se houve compensação, a linha cai. §7.3.
- **Não tem encargo.** É a verba bruta: INSS/FGTS/IRRF e reflexos não entram. §7.4.
- **Subestima onde a batida falta.** Os 44h aparecem com ~4h no feriado: é o que as batidas
  emparelhadas dizem — o turno partido pelo almoço perde um par com frequência, e a apuração
  nunca estima o que não foi batido. A tela marca «⚠ sem par de batidas» num dia com batida e
  nenhum par fechado (hoje: nenhum caso; havia 2 falsos antes da correção do §4).

---

## 2. O que a CCT manda — e a cláusula que NÃO existe aqui

| Regra | Fonte, citada no `origem_regra` de cada linha |
|---|---|
| **Feriado trabalhado = pagamento em dobro** | art. 9º da Lei 605/49 · **Súmula 146 do TST** · e, para o 12x36 (42 dos 63 ativos), a **Súmula 444 do TST**, expressa: a jornada 12x36 é válida «assegurada a remuneração em dobro dos feriados trabalhados» |
| **HE em feriado/domingo/descanso = 100%** | **CCT SINDECOMPRESTS AM000613/2025**, vigência 01/01–31/12/2026 (`cct_convencoes.registro_mte`), materializada em `cct_cargos.horas_extras_noturnas_percentual = 100,00` nas **51 funções** da convenção e em `modules/cct/models/schedule.ADICIONAIS.hora_extra_feriado_percentual = 100,0` |
| **Quem decide que o dia é 100%** | `hr/services/espelho_service.py` L551-553 (12x36 → só feriado; 44h → feriado, domingo ou dia sem jornada esperada) |

⚠️ **A cláusula numerada não existe neste repositório.** Procurei em `modules/cct/**`, nas 11
tabelas `cct_*`, em `docs/**` e nos relatórios de auditoria: a única cláusula com número citada em
qualquer lugar é a **23ª** (adicional de ronda 15%, em `rubricas_folha.origem_regra`). O texto da
CCT AM000613/2025 não está digitalizado aqui — existe o **registro MTE** e existem os
**percentuais** que dela foram extraídos em 2026. Citei a convenção pelo registro e o campo onde o
percentual vive, que é o mais longe que dá para ir sem inventar um número de cláusula. §7.1.

Por que `pago_como = horas × valor_hora` no feriado: o dia **já está pago uma vez** dentro do
salário mensal (verba 0001, 30 dias). A dobra é a **segunda** vez. `deveria_ser = horas ×
valor_hora × 2`; `diferenca = deveria_ser − pago_como − verba 0011` (que é R$ 0,00 em tudo).

---

## 3. O que foi feito

| Arquivo | O quê |
|---|---|
| `backend/modules/people_management/folha/services/feriado_conferencia.py` (novo) | `apurar(db, competencia)` (idempotente), `linhas`, `resumo`, `trabalhado_por_feriado`, `competencias`, `_horas_por_dia`, `DDL`, `SEMENTE_MAPA`, `_ensure`, `demo()` |
| `backend/modules/operacional/controllers/redesign_builders/_dgx_x3_feriado.py` (novo) | `telas(db, out)` → `feriado-trabalhado` (table) e `feriado-apurar` (form); `router` com `POST /action/feriado-apurar` |
| `backend/scripts/orq/test_oraculo_x3_feriado_he100.py` (novo) | O oráculo (§4) |
| `.../redesign_builders/_dgx_f7_ponto.py` | A tela `feriados` da F7 ganhou a coluna **«Trabalhado (MM/AAAA)»** — nº de pessoas que trabalharam naquele feriado na competência corrente, em vermelho; «fora da competência» quando o feriado não é do mês apurado. Falha da coluna não derruba a tela (`try/except` + `logger.debug`) |
| `.../redesign_builders/departamento_pessoal.py` | 2 linhas no topo (`router`) + 2 linhas depois da W5 (`telas`), comentário `# dgx x3` |
| `.../redesign_builders/_dp_grupos.py` | 2 tuplas no **FIM** do g-folha |

### Reuso (cavar antes de construir)

Nada da régua foi reescrito. **Importados**: `config_ponto.feriados_do_periodo` (escopo do feriado,
F7) · `horas_service.dia_do_plantao` / `janelas_de_turno` / `MAX_TURNO_H` / `SQL_BATIDAS` /
`params_batidas` (pareamento) · `he_classificacao.competencia_valida` (validação de `AAAA-MM`, W3) ·
`mapa_evento_rubrica._ensure` + `EVENTOS` (o cadastro da W5, que já marcava os dois eventos como
`produzido=False`) · `redesign_data_controller.b/brl/t` (DSL de tela) · `_dgx_f7_ponto._falhou`.

**Uma diferença deliberada** em `_horas_por_dia`: a versão do `beneficio_ponto` (U5) não carrega a
continuidade (`ultimo`) na varredura das batidas SOLITÁRIAS — lá não importa, o VT/VR conta dia com
horas. Aqui importava: sem ela, a saída das 07:10 do plantão que entrou 18:45 da véspera inventava
um feriado trabalhado. Duas linhas do §1 nasceram assim e o oráculo (b) as pegou (§4).

### DDL que `_ensure` aplica em produção no 1º acesso (idempotente)

```sql
CREATE TABLE IF NOT EXISTS folha_feriado_conferencia (
  id serial PRIMARY KEY,
  competencia varchar(7) NOT NULL,
  tipo varchar(24) NOT NULL CHECK (tipo IN ('feriado_trabalhado','he100')),
  employee_id varchar(50) NOT NULL, nome varchar(180) NOT NULL DEFAULT '',
  cargo varchar(120), escala varchar(20), condominio varchar(180),
  data date NOT NULL, feriado varchar(160), escopo varchar(20),
  teve_turno boolean NOT NULL DEFAULT false,
  horas numeric(6,2) NOT NULL DEFAULT 0, valor_hora numeric(12,2) NOT NULL DEFAULT 0,
  pago_como numeric(12,2) NOT NULL DEFAULT 0, pago_detalhe text,
  verbas jsonb NOT NULL DEFAULT '{}'::jsonb,
  deveria_ser numeric(12,2) NOT NULL DEFAULT 0, diferenca numeric(12,2) NOT NULL DEFAULT 0,
  regra text NOT NULL DEFAULT '', apurado_em timestamptz NOT NULL DEFAULT now());
CREATE UNIQUE INDEX IF NOT EXISTS ux_folha_feriado_conf
  ON folha_feriado_conferencia (competencia, tipo, employee_id, data);
CREATE INDEX IF NOT EXISTS ix_folha_feriado_conf_comp ON folha_feriado_conferencia (competencia);
-- + 2 INSERT ... WHERE NOT EXISTS em ponto_evento_rubrica (escopo empresa):
--   feriado_trabalhado → 0011 e he100 → 0011
```

Nenhum DROP/DELETE/UPDATE em dado que a frente não criou. O único DELETE é dentro de
`folha_feriado_conferencia`, da própria competência, das linhas que a apuração daquele instante
não produziu (feriado removido, batida corrigida) — senão a tela mostraria fantasma.

### As 2 linhas novas do mapa evento→rubrica (W5)

`feriado_trabalhado → 0011` e `he100 → 0011`, escopo empresa, fórmula `horas × valor_hora × 2`,
base `valor_hora`, fator 2,0000, `origem_regra` citando Lei 605/49 art. 9º + Súmulas 146/444 do TST
e a CCT AM000613/2025. **Nascem com «o motor usa? NÃO»**: a W5 já marcava os dois eventos como
`produzido=False`, e a coluna «O motor usa?» da tela `ponto-evento-rubrica` mostra
«não — declaração» com «não emitida na competência» ao lado. A rubrica é a **0011** nos dois
porque não existe rubrica de adicional de feriado em `rubricas_folha` (35 rubricas, nenhuma com
«feriado» no nome) — criar uma que ninguém emite é cadastro morto. §7.2.

### Telas (g-folha, deep-link `/redesign/departamento-pessoal?t=<id>`)

- **`feriado-trabalhado`** (table, 50 linhas em 09/2026): Colaborador · Dia · Tipo ·
  Feriado/motivo · Escopo · **Tinha escala?** · Horas · Pago · Deveria ser ·
  **Diferença (em vermelho)** · O que o holerite pagou (verba a verba). Filtros Tipo × Situação ×
  Escala. O subtítulo traz o total e diz, com essas palavras, que a tela **não muda holerite
  nenhum**. A tela apura ao abrir (idempotente).
- **`feriado-apurar`** (form, 1 campo): competência → `POST /action/feriado-apurar`, `showResult`.
- **`feriados`** (F7, g-ponto) ganhou a coluna **«Trabalhado (09/2026)»**: `21 pessoa(s)` em
  vermelho nos dois feriados de setembro, «fora da competência» nos outros 14.

---

## 4. Oráculo — `backend/scripts/orq/test_oraculo_x3_feriado_he100.py`

Afirma, em 07, 08 e 09/2026: **(a)** `apurar` 2× não duplica (e o que ele diz ter gravado == o que
a tabela tem); **(b)** a lista de quem trabalhou em feriado == a recontada por **SQL próprio**,
com a régua de escopo da F7 escrita em SQL (nacional; estadual por UF; municipal por cidade;
cliente por condomínio) e a régua do «um plantão é UM dia» também em SQL (janela do turno; sem
turno, a batida a menos de 13h da véspera é a continuação do plantão anterior); **(c)** ninguém
aparece por feriado de CLIENTE de outro condomínio; **(d)** o valor pago lido em cada linha == o
do holerite (recontado direto de `hr_payslips.earnings`); **(e)** **Σ|Δ| em `hr_payslips` =
R$ 0,00** — soma de proventos, descontos, líquido e contagem idênticas antes e depois de apurar;
**(f)** as 2 linhas novas do mapa existem, têm `origem_regra` e `produzido is False`;
**(g)** fiação (o build do DP chama a frente e as abas estão em `_dp_grupos`).

```bash
WT=$(git rev-parse --show-toplevel)
ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' \
       | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\n' ' ')
docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" \
  --tmpfs /app/logs:rw,mode=1777 --tmpfs /app/uploads:rw,uid=999,gid=999 \
  -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env \
  -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \
  conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_x3_feriado_he100.py
```

**VERMELHO** (antes de qualquer código):
```
FALHOU: feriado_conferencia não importa: ModuleNotFoundError: No module named 'modules.people_management.folha.services.feriado_conferencia'
TOTAL desvios: 1
exit=1
```

**O oráculo mordeu duas vezes durante a frente** — e as duas mordidas eram defeito de verdade:

1. Com a primeira recontagem (dia CIVIL da batida) e antes da semente do mapa:
```
FALHOU: (f) 'feriado_trabalhado' não tem linha ativa em ponto_evento_rubrica
FALHOU: (f) 'he100' não tem linha ativa em ponto_evento_rubrica
FALHOU: (b) 2026-09: 795abf6c… trabalhou em feriado 05/09 e a tabela não tem
FALHOU: (b) 2026-09: 0adfb14d… trabalhou em feriado 07/09 e a tabela não tem   (+4 iguais)
TOTAL desvios: 9
```
2. Depois de consertar a recontagem, a direção inverteu e apareceu o defeito do **serviço** (a
   batida solitária, sem a corrente de continuidade, inventava feriado trabalhado):
```
FALHOU: (b) 2026-09: 4fb9bcb3… em 07/09 está na tabela e o SQL próprio não acha
FALHOU: (b) 2026-09: 66c823e6… em 05/09 está na tabela e o SQL próprio não acha
TOTAL desvios: 2
```
JONILSON MARTINS bateu 06/09 18:45 (entrada) → 07/09 06:46 (saída) → 07/09 07:10 (sobra). A sobra
das 07:10 virava «trabalhou no feriado de 07/09». Eram **2 linhas de passivo falso** — R$ 0,00 cada
(0h), mas dois nomes acusados de um feriado que não trabalharam. Sem o oráculo, os dois estariam
na lista nominal do §1.

**VERDE** (depois do serviço, do cadastro e da fiação):
```
2026-07, 2026-08, 2026-09 · 79 linha(s) de conferência · feriado_trabalhado=42 · he100=29 · passivo Σ = R$ 5.399,01 · Σ|Δ| nos holerites = R$ 0,00
TOTAL desvios: 0
OK feriado/HE 100%: a lista de quem trabalhou em feriado == a recontada por SQL próprio com a régua de escopo, feriado de cliente não vaza para outro condomínio, o pago lido == o do holerite, Σ|Δ| nos holerites = R$ 0,00 e as linhas novas do mapa dizem «o motor NÃO usa»
exit=0
```
(79 linhas na corrida do oráculo = as 71 reais + 8 da fixture de (c), apagada ao fim; o
`passivo Σ` já exclui a fixture.)

**A fixture de (c) não nasceu cega.** Medido: `condominios.client_id` casa com
`employees.cliente_id` em **1 de 63** ativos, e esse um não bate ponto — sem fixture, o teste do
escopo de cliente passaria por não achar ninguém («0 falhas» não é «0 esquecidos»). A fixture cria
o condomínio que falta para uma pessoa REAL (uma das 13 cujo `cliente_id` existe em `clients`) e o
feriado de cliente dela; prova os dois lados (quem é do condomínio **aparece**; quem não é, **não
aparece**) e apaga tudo no `finally`, mesmo em falha. Conferido no sandbox ao fim: `FIXTURE DGX X3`
em `cct_feriados` + `condominios` + `folha_feriado_conferencia` = **0**.

**Prova por HTTP** (`teste-dgx-x3`, porta 8263, **parado ao fim**):
```
GET /api/v1/redesign/data/departamento-pessoal → 200
g-folha, últimas abas: ['evento-coletivo-novo', 'feriado-trabalhado', 'feriado-apurar', 'folha-apontamentos-importar']
feriado-trabalhado: table · 50 linhas · cols [Colaborador, Dia, Tipo, Feriado / motivo, Escopo,
  Tinha escala?, Horas, Pago, Deveria ser, Diferença, O que o holerite pagou]
  linha 1: KELLY PATRICIA DA SILVA DE SOUZA · 07/09/2026 · badge VERMELHO «Feriado trabalhado» ·
           Independencia do Brasil · badge «nacional» · «não» · 12.52h · R$ 116,19 · R$ 232,37 ·
           badge VERMELHO R$ 116,18 · «R$ 116,19 já dentro do salário mensal (0001) · 0011 …»
feriado-apurar: form · submit /api/v1/redesign/action/feriado-apurar · campos ['competencia']
feriados (F7): cols [..., 'Trabalhado (09/2026)', 'Estado']
  07/09/2026 Independencia do Brasil · nacional · Brasil · 2026 · só 2026 · «21 pessoa(s)» · ativo
  05/09/2026 Elevacao do Amazonas    · estadual · UF AM · 2026 · só 2026 · «21 pessoa(s)» · ativo
  25/12/2026 Natal                   · nacional · Brasil · 2026 · só 2026 · «fora da competência» · ativo
POST action/feriado-apurar {"competencia":"2026-09"} → 200
  «50 linha(s) em 09/2026 · 28 pessoa(s) · diferença R$ 4.212,85. Nenhum holerite foi alterado (paralelo cego).»
POST … {"competencia":"2026/09"} → 400 "Competência inválida: '2026/09' (use AAAA-MM)."
POST … {"competencia":""}        → 400 "Competência inválida: '' (use AAAA-MM)."
QA_API=http://127.0.0.1:8263 checar_tela_sem_porta.py → TOTAL: 1 sem porta (crm/atividades, anterior à X3)
```

**Vizinhos, todos verdes** depois da frente:
`test_oraculo_w5_mapa_evento_rubrica` 0 · `test_oraculo_ponto_configuravel` 0 ·
`test_oraculo_rubricas_dizem_a_verdade` 0 · `test_oraculo_cct_como_dado` 0 vermelho(s) e 6 avisos
(os mesmos de antes — adicionais opcionais pagos a parte da função).

`ruff check` e `ruff format` limpos nos 6 arquivos.

---

## 5. O que NÃO foi feito e por quê

- **O motor não emite nada.** `calculo_service.py` segue sem `0011` e sem verba de feriado. A
  frente é medição e cadastro; pagar é decisão do dono (§7). O dia em que o motor emitir, este
  oráculo é a trava: (e) passa a comparar contra o novo valor e (d) contra a verba nova.
- **`pago_como` do `he100` é RATEIO.** A folha paga HE pelo excedente MENSAL, não por dia: não
  existe, no holerite, «a HE do dia 06/09». O rateio é `verba de HE × horas da linha ÷ horas de HE
  do mês no espelho`, escrito no `pago_detalhe` de cada linha com os três números à vista. Onde a
  folha não emitiu HE nenhuma, o rateio é R$ 0,00 — que é o fato, não uma aproximação.
- **Encargos não entram.** A diferença é verba bruta. INSS/FGTS/IRRF sobre o adicional, e o
  reflexo em DSR (Súm. 172 do TST) e em 13º/férias, não foram calculados: cada um é uma decisão de
  base de incidência que o dono precisa tomar antes de virar número. §7.4.
- **Compensação não é lida.** Não há tabela de folga compensatória; a lei fala em feriado **não
  compensado**. Assumir que nenhum foi compensado é o pior caso — está dito no §1.4 e no §7.3.
- **`ponto_he_classificacao` (W3) não foi tocada.** Ela classifica o MOTIVO da HE (faturável ×
  custo nosso) e já separa `he50`/`he100`; esta frente pergunta outra coisa (quanto deveria ter
  sido pago). Cruzar as duas — «HE 100% não paga **e** repassável ao cliente» — é trabalho de uma
  próxima, e as duas tabelas já têm a mesma chave (employee, data).
- **Os 14 feriados fora de 07–09/2026 não foram apurados.** A tela apura qualquer competência; eu
  medi as três que o brief pediu. Jan–jul/2026 é backfill do espelho da Portte (verba copiada, não
  calculada) — o feriado trabalhado lá é um fato do PONTO e a conferência funciona, mas o «pago» é
  o que a Portte pagou, não o que o nosso motor calculou.
- **Não criei rubrica nova.** `feriado_trabalhado` foi mapeado na `0011 Hora Extra 100%` que já
  existe. Uma `0012 Feriado Trabalhado` com natureza eSocial própria é cadastro, e é do dono. §7.2.
- **Frontend**: nada. `table` + `form` renderizam genericamente; as abas vêm do `_dp_grupos`.
- **`checar_regressao.py`**: nada — `scripts/orq/test_*.py` é globado pela meia-noite (o
  orquestrador registra, conforme o contrato).

---

## 6. Como o Jordan testa amanhã

1. Depois do bake: **Departamento Pessoal → Folha de pagamento → aba «Feriado trabalhado e
   HE 100%»** (`/redesign/departamento-pessoal?t=feriado-trabalhado`). Abre já apurado em 09/2026:
   **50 linhas, 28 pessoas, diferença R$ 4.212,85.**
2. Leia o subtítulo até o fim: ele traz o total, a regra (Lei 605/49 art. 9º, Súmulas 146 e 444 do
   TST, CCT AM000613/2025) e diz, com essas palavras, que **a tela não muda holerite nenhum**.
3. Coluna **Diferença**: tudo em vermelho. Coluna **O que o holerite pagou**: leia uma linha —
   «R$ 116,19 já dentro do salário mensal (0001) · 0011 Hora Extra 100%: R$ 0,00 · holerite
   09/2026: nenhuma verba de HE/100%». É a frase inteira do problema.
4. Filtre **Tipo = «Feriado trabalhado»**: 42 linhas, 21 pessoas em cada um dos 2 feriados de
   setembro. Filtre **Tipo = «Hora extra que deveria ser 100%»**: 8 linhas, todas de domingo.
5. Aba **«Apurar feriado/HE 100%»**: escolha 08/2026 e Apure. Volta «6 linha(s) … diferença
   R$ 382,11. Nenhum holerite foi alterado». Apure de novo: **o mesmo número** (idempotente).
6. Vá a **Ponto & Jornada → Feriados** (`?t=feriados`): 05/09 e 07/09 agora trazem
   **«21 pessoa(s)»** em vermelho na coluna «Trabalhado (09/2026)».
7. Vá a **Folha → «Mapa evento → rubrica»** (`?t=ponto-evento-rubrica`): agora são **10 linhas**.
   As duas novas — «Feriado trabalhado → 0011» e «Hora extra 100% → 0011» — dizem
   **«não — declaração»** na coluna «O motor usa?» e **«não emitida na competência»** ao lado.
   É a declaração do que deveria ser, ao lado do fato de que não é.
8. Confira que nada mudou: abra o contracheque de 09/2026 de qualquer um dos 21. Continua igual.

---

## 7. Decisões que só o dono pode tomar

1. **A cláusula da CCT.** O texto da AM000613/2025 **não está no sistema** — só o registro MTE e os
   percentuais extraídos dela. Preciso do PDF (ou do número da cláusula de feriado/HE 100%) para
   trocar a citação genérica por uma citação de cláusula em cada `origem_regra`. Enquanto isso, a
   base legal citada é a lei e as súmulas, que valem de qualquer forma.
2. **Pagar ou não pagar os R$ 5.399,01** — e a partir de quando. Se sim: é rubrica nova (adicional
   de feriado, com natureza eSocial própria) ou entra na `0011` que já existe? Hoje mapeei os dois
   eventos na `0011`; criar uma `0012 Feriado Trabalhado` é um clique na aba «Nova rubrica» (F1) e
   um clique em «Editar» na linha do mapa — nenhuma linha de código.
3. **Ligar o motor.** Fazer `calculo_service` emitir a verba em feriado trabalhado é o passo
   seguinte, e é o único que muda dinheiro. Ele **exige** decidir antes: (a) a dobra incide sobre o
   plantão inteiro ou só sobre as horas caídas dentro do dia do feriado, quando o turno vira a
   meia-noite? (b) o 12x36 compensa o feriado na folga do dia seguinte, ou não? A Súmula 444 diz
   que não compensa — mas quem tem que afirmar isso para esta empresa é você.
4. **Encargos e reflexos.** A diferença é bruta. INSS/FGTS/IRRF, DSR sobre o adicional (Súm. 172 do
   TST) e reflexo em 13º/férias multiplicam o número — e cada base de incidência é uma decisão.
5. **`employees.cliente_id` está órfão em 47 dos 63 ativos** (aponta para um `clients.id` que não
   existe; outros 44 estão nulos, e só 13 têm FK válida). Consequência **medida hoje**: a cascata
   da F7/W5 não resolve condomínio para quase ninguém, então **feriado de CLIENTE não alcança
   ninguém**, e feriado estadual/municipal vale para todos por falta de UF/cidade em `condominios`
   (10 dos 11 condomínios têm `cidade` e `estado` vazios). Não é defeito desta frente — é dado.
   Mas no dia em que um cliente tiver feriado próprio, ele não vai funcionar até isso ser arrumado.
6. **Quem bateu no feriado sem escala lançada**: 5 das 42 linhas têm «Tinha escala? não»
   (ALEXANDRE SOUZA 05 e 07/09, FRANCISCO RAMON 05 e 07/09, KELLY PATRICIA 07/09). Trabalharam e a
   escala não foi lançada. É problema de operação, não de folha — mas aparece aqui porque o
   dinheiro depende dele.
7. **As 4h dos 44h no feriado.** ASG/artífice aparecem com ~4h no feriado, não 8h: o turno partido
   pelo almoço perde um par de batidas com frequência. Se eles de fato trabalharam o dia inteiro, o
   passivo desses nomes **dobra**. Isso se resolve no ponto, não aqui.
