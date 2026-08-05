# Task 2 (salário-família) e Task 5 (férias) — folha de julho da Portte lida na íntegra

> Li a folha 07/2026 completa direto do Drive (`Conecta Patrimonial - Geral`, 13 páginas,
> 51 empregados). É a fonte que faltava: tem o **Resumo por Rubrica** com referência e valor.

---

## TASK 2 — Salário-família

### O apontamento anterior estava errado

O relatório de comparação lia `995 SALARIO FAMILIA 12,00 763,20` como **"12 cotas de R$63,60"**.
Não é. O `12,00` é a soma do **número de filhos** de 8 pessoas, e o valor traz proporcionais:

| pessoa | filhos | valor |
|---|--:|--:|
| ADEMIR SALUSTIANO | 3 | 202,62 |
| EDILENE SALES | 2 | 135,08 |
| GRACIENE PEREIRA | 2 | 135,08 |
| BIANCA HELLEM | 1 | 67,54 |
| CELIANE GARCIA | 1 | 67,54 |
| MEIRE GABRIELA | 1 | 67,54 |
| CARLOS EDUARDO | 1 | 63,04 *(faltas)* |
| ALEXANDRE SOUZA | 1 | 24,76 *(admitido 20/07)* |
| | **12** | **763,20** |

**Nossa cota de R$67,54 está correta** — confere com a Portte em 6 meses e em julho.

### A causa real: testamos o campo errado

`calculo_service` linha 542:

```python
if salario_base_cadastrado <= SALARIO_FAMILIA_TETO:
```

`salario_base_cadastrado` é **R$1.670 para todo mundo**. O teto nunca filtra ninguém. A lei
(e a Portte) usam a **remuneração do mês**, não o salário contratual.

Prova em julho — separação perfeita por base INSS:

| recebeu | base INSS | | não recebeu | base INSS |
|---|--:|---|---|--:|
| ADEMIR | 1.837,00 | | ANDREA | 2.143,05 |
| CELIANE | 1.695,72 | | EIDY | 2.362,82 |
| MEIRE | 1.628,35 | | RILEM | 2.589,47 |

São exatamente os **adicionais noturnos** que empurram ANDREA/EIDY/RILEM acima do teto. Como
não aplicamos o teto sobre a remuneração, pagamos as três indevidamente.

**Nosso julho: R$1.130,17 em 11 pessoas · Portte: R$763,20 em 8.**
Pagamos a mais para ANDREA, EIDY e RILEM. Deixamos de pagar ALEXANDRE (admitido 20/07).
JONATHAN a Portte pagou fora desta folha (desligado 22/07, foi por rescisão).

### 🛑 Por que NÃO corrigi ainda

O campo está errado — isso é certo. **O valor do teto, não.** Nossa constante é
`SALARIO_FAMILIA_TETO = 1.819,26`, que é o teto de **2024** (pareado com a cota de R$62,04);
a cota que temos, R$67,54, é atual. As duas constantes estão despareadas.

Corrigir só o campo mantendo 1.819,26 **excluiria ADEMIR**, que a Portte paga com base
1.837,00. Ficaríamos errados de outro jeito.

E o dado não fecha o teto sozinho: **ELEN recebeu com base R$2.148,85** (abril) enquanto
**ANDREA não recebeu com R$2.143,05** (julho) — R$5,80 de diferença, resultados opostos. Ou
há outro critério (filho que completou 14 anos, atestado de frequência escolar vencido), ou
uma das duas é erro da Portte.

**Precisa do valor oficial do teto 2026** (Portaria Interministerial MPS/MF nº 13/2026 — a
mesma que já usamos para o INSS). Com ele, a correção é de duas linhas.

---

## TASK 5 — Férias: o mapa completo, extraído da folha real

Julho teve 3 pessoas em férias: **ANTONIO CARLOS VIEIRA**, **EDIWILSON CORREA**, **FRANCISCO
RAMON**. O bloco tem **16 rubricas**:

| cód | rubrica | julho | o que é |
|---|---|--:|---|
| 937 | **ADIANTAMENTO DE FERIAS** | **−3.940,73** | 🔴 o desconto que ignoramos |
| 8783 | DIAS FERIAS | 1.748,36 | dias de férias no mês |
| 3 | HORAS FERIAS | 813,18 | variante por horas |
| 931 | 1/3 DAS FERIAS | 1.071,54 | terço constitucional |
| 806 | MEDIA HORAS FERIAS | 309,36 | **média de variáveis (art. 142)** |
| 807 | VANTAGENS FERIAS | 343,57 | média de adicionais |
| 8192 | DIFERENCA ADICIONAL FERIAS | 262,26 | acerto |
| 8112 | DIFERENCA DE 1/3 DE FERIAS | 98,42 | acerto |
| 8189 | DIFERENCA MEDIA HORA FERIAS | 33,00 | acerto |
| 805/8190 | MEDIA/DIFERENCA VALOR FERIAS | 0,68 | acerto |
| 812 | INSS FERIAS | −345,43 | desconto |
| 821 | INSS DIFERENCA FERIAS | −22,53 | desconto |

**Confirmado o maior risco:** o `937 ADIANTAMENTO DE FERIAS` de **R$3.940,73** é desconto e
nós não o emitimos. Sem ele, pagamos a maior — é o item de R$2.203,85 do relatório original.

Também confirmado que `clt_calculator.calcular_ferias` sendo **base-only** é limitação real:
a Portte paga **R$1.047** em médias (806 + 807 + 8189) que não temos.

Exemplo íntegro — EDIWILSON (férias de 03/07 a 22/07):
```
8783 DIAS FERIAS        20,00  1.191,69 P     937 ADIANTAMENTO FERIAS  −1.849,94 D
931  1/3 DAS FERIAS     33,33    501,54 P     812 INSS FERIAS            −156,23 D
806  MEDIA HORAS FERIAS 134,19   134,19 P     821 INSS DIFERENCA          −18,80 D
807  VANTAGENS FERIAS   178,75   178,75 P
```
Proventos 3.021,59 · Descontos 2.207,33 · **Líquido 814,26**

### O que a Task 5 precisa (não cabia nesta sessão)

1. Emitir `937` a partir de `hr_vacation_requests` — **maior risco de pagamento a maior**
2. Implementar a média do art. 142 (806/807), hoje ausente
3. Segregar INSS de férias (812) do INSS mensal
4. Validar contra os 3 casos de julho, que agora estão documentados acima

Não é ajuste pequeno: é o bloco de férias inteiro. Merece sessão própria, com o oráculo já
pronto (este documento + a folha em `auditoria/folhas_portte`).

---

## Estado das 5 frentes

| | frente | estado |
|---|---|---|
| 1 | Rubrica 0020 duplicada | ✅ |
| 2 | Salário-família | 🟡 causa isolada; **falta o teto oficial 2026** |
| 3+4 | Noturno / intrajornada | ✅ Σ\|Δ\| −72% |
| 5 | Férias | 🟡 mapeada por completo; implementação é sessão própria |
| 6 | Script oficial de folha | ⬜ aberta |
