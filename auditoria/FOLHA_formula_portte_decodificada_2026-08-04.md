# A fórmula da Portte, decodificada · 04/08/2026

> Jordan: *"as respostas está na folha gerada pela portte... você tem acesso a cct,
> pode consultar você mesmo"*. Estava certo nas duas coisas.

---

## Onde estava a resposta

Na coluna **REFERÊNCIA** da folha da Portte — que traz as horas de cada rubrica. A extração
já existia em `auditoria/folhas_portte/extracao` (jan–jun, 7 condomínios). **96 observações.**

Exemplo (AILTON, junho):

```
246 ADICIONAL NOTURNO (INFOR)   ref 112:00   R$ 207,82
247 HORA NOT REDUZIDA           ref  14:30   R$ 272,30
245 INTRAJORNADA NOTURNA        ref  14:00   R$ 262,91
```

## 1. As horas sempre estiveram certas

`H_reduzida / plantão = 1,0000` **exato nas 96 observações**. A hora fictícia é 1h por
plantão — precisamente o que o motor já calculava. Eu vinha procurando um erro nas horas.
Não havia.

## 2. O que faltava era o FATOR — e ele se separa sozinho

Os dois grupos que eu não conseguia explicar (1,8 × 2,025) separam **48/48, perfeito**, pela
presença de **ADICIONAL DE RONDA**:

$$(1 + 0{,}20_{\text{noturno}} + \text{ronda\%}) \times 1{,}50_{\text{hora extra}}$$

| | calculado | Portte mediu |
|---|--:|--:|
| sem ronda | 1,800 | **1,7991** |
| com ronda 15% | 2,025 | **2,0241** |

É construção CLT clássica: a hora fictícia é paga como **hora extra (50%, a alíquota da
CCT)** sobre a base que inclui os adicionais **habituais**. A CCT no banco confirma as duas
peças — `adicional_noturno_percentual = 20` e `horas_extras_percentual = 50`.

A intrajornada **diurna** usa a mesma construção sem o prêmio noturno, e fecha exato:

| | sem ronda | com ronda |
|---|--:|--:|
| Intrajornada Diurno | **1,5000** | **1,7250** = (1 + 0,15) × 1,50 |

## 3. Intrajornada: era cálculo desligado, não ausente

A flag `recebe_intrajornada` já batia **21/21** com a Portte em 6 meses. O motor lia a flag
e zerava o valor. Ligado: 1h por plantão, mesmo fator.

## 4. DSR — respondido por evidência, não por decisão

Era sua pendência. A folha da Portte responde: em **101 de 101** pessoas-mês com noturno e
**sem** hora extra, o DSR é **ZERO**. Ela reflete o DSR só sobre o extraordinário — no 12x36
o repouso já está contemplado no piso.

Nosso DSR saía **R$2.198** contra **R$33,19** dela. Base corrigida para só hora extra.

**Não custa nada a ninguém:** quem paga hoje é a folha da Portte; nosso motor é que estava
divergindo.

## Resultado em julho

| cód | rubrica | início do dia | agora | Portte |
|---|---|--:|--:|--:|
| 0020 | Adicional Noturno | 1.971,78 | 3.610,77 | 3.265,80 |
| 0021 | Hora Noturna Reduzida | 1.232,32 | 4.322,78 | 3.914,34 |
| 0031 | Intrajornada Noturna | — | 2.470,09 | 2.005,15 |
| 0030 | Intrajornada Diurno | — | 2.823,78 | 1.738,82 |
| 0090 | DSR sobre variáveis | 533,63 | 0,00 | 33,19 |
| | **Σ\|Δ\|** | **8.220** | **2.337** | **−72%** |

53 holerites persistidos, líquido R$90.582,48. Gate `test_noturno_escala.py`: 17/17.

## O único resíduo que sobra

**Todas as rubricas ficam ACIMA da Portte** — 111%, 110%, 123%, 162%. Sempre na mesma
direção, sempre pela mesma causa: contamos plantão **agendado** e ela desconta **falta**.

Já testei o ponto como proxy de falta e não serve: 43% dos plantões agendados não têm batida
nenhuma. É o mesmo problema de adoção do DP — resolve-se com registro, não com código.

---

## Dois incidentes desta sessão, registrados

**1. O deploy builda da ÁRVORE DE TRABALHO, não do git HEAD.** Um deploy de outra sessão
rodou enquanto meu arquivo estava no meio de uma edição (SQL já com `:nt`, parâmetro ainda
não) e **bakeou o estado quebrado**. O git estava correto; a imagem não. Com 3 sessões
paralelas, isso pode acontecer a qualquer momento — editar em passos que deixem o arquivo
sempre executável.

**2. O script da Fase E dependia da própria saída.** Ele apaga as linhas `conecta` antes de
reinserir, e buscava o `condominio_id` no último holerite — ou seja, no que acabara de
apagar. Quem foi admitido no mês (ALEXANDRE, 19/07) entrava com `condominio_id` NULL,
violava o NOT NULL e **derrubava a competência inteira depois de já ter apagado**. Julho
ficou zerado por alguns minutos. Corrigido: resolve pela **alocação vigente** primeiro.

Esse era um bug latente — só apareceu porque foi a primeira vez que o script rodou sem
encontrar a saída anterior. Valia ter aparecido agora, e não no fechamento de um mês.
