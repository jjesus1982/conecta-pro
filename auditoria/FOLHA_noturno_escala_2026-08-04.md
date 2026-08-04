# Noturno pela escala — implementado · 04/08/2026

> Decisão do Jordan: *"vamos pela escala, igual a portte"*. Feito e persistido em julho.

---

## O que mudou

**A fórmula do motor já estava certa.** Ela faz `horas × 60/52,5` (redução da hora noturna,
52'30") e aplica 20% em cima — que é exatamente o "8 horas legais por plantão" da Portte.
O que estava errado era a **fonte** das horas.

Trocado: `horas_not` sai da **escala** (7h de relógio na janela 22:00–05:00 × plantões
agendados) em vez das batidas. Diff pequeno, porque só a origem mudou.

**Guarda de vínculo:** só conta plantão dentro do período trabalhado. A escala de julho
seguia lançada até o fim do mês para quem foi desligado dia 22 — eram **4 plantões que não
existiram**. Também conta data distinta e só `status='scheduled'`: 45% das linhas de
`shifts` são `cancelled` (troca/substituição) e contá-las inflaria o pagamento.

**Gate:** `scripts/test_noturno_escala.py` trava o invariante (adicional = 8h × plantões ×
20%). 17/17 conformes.

## Resultado em julho

| cód | rubrica | antes | agora | Portte | \|Δ\| antes | \|Δ\| agora |
|---|---|--:|--:|--:|--:|--:|
| 0020 | Adicional Noturno | 1.971,78 | **3.610,77** | 3.265,80 | 1.294,02 | **344,97** |
| 0021 | Hora Noturna Reduzida | 1.232,32 | **2.256,54** | 3.914,34 | 2.682,02 | **1.657,80** |
| 0090 | DSR s/ variáveis | 533,63 | 977,49 | 33,19 | 500,44 | 944,30 |
| | **Σ\|Δ\|** | | | | **4.476,48** | **2.947,07** |

**Melhora de R$1.529,41.** Líquido de julho: R$81.943,36 → R$84.773,76.

## ⚠️ O DSR dobrou — e isso é consequência direta

O DSR é reflexo das verbas variáveis. Como o noturno cresceu, o DSR cresceu junto:
**+R$456 → +R$944**. A Portte praticamente não paga esse reflexo (R$33,19).

A pergunta que estava parada aguardando você **dobrou de tamanho** por causa desta mudança.
Ela agora é o maior item isolado das três. Segue sem alteração até você definir.

## Os dois resíduos — nenhum deles é código

### 1. Adicional noturno em 111% — pagamos a mais

A Portte desconta **falta**; nós não temos registro de falta. Testei usar o ponto como
proxy: **103 dos 241 plantões agendados (43%) não têm batida nenhuma**. Se descontasse por
aí, cairia para 63% da Portte — o ponto está incompleto demais para servir de proxy, tanto
para pagar quanto para descontar.

É o mesmo problema de adoção já medido em `dp_adocao_o_padrao_2026-08-04.md`: enquanto a
falta não for registrada, pagamos ~11% a mais. **Resolve-se com processo, não com código.**

### 2. Hora noturna reduzida em 58% — constante que não consegui derivar

Nossa fórmula é a da CLT: 7h de relógio viram 8h legais → **1h fictícia por plantão**, paga
a 100%. A Portte paga **~1,8h por plantão**.

Tentei derivar 1,8 de todo jeito e não fecha: não é 12h/7, não é prorrogação da Súmula 60,
não é a fictícia com adicional, não é com DSR embutido. Pior: os dados da Portte mostram
**dois grupos** (1,8 e 2,025 h/plantão) e testei as três hipóteses óbvias para separá-los —
salário-base (bate exato com a Portte, zero divergência), horário do turno e pausa/posto
(MAIARA e JONHATA estão no mesmo posto, mesma pausa, grupos diferentes). Nenhuma explica.

**Não vou chutar a constante.** Implementar 1,8 sem saber de onde vem é fabricar dado que
paga dinheiro — exatamente o que a regra proíbe. Isso precisa da **cláusula da CCT** ou de
uma pergunta à Priscila.

## O que fica pendente de você

1. **DSR** — agora +R$944, o maior item. Parado desde ontem aguardando definição.
2. **Falta**: aceitar os ~11% a mais até o registro existir, ou criar o fluxo de lançamento?
3. **Constante 1,8 da hora noturna reduzida** — precisa da CCT ou da Priscila.

## Método — o que essa frente ensinou

O plano dizia que a causa era pareamento por `punch_type`. Era **3%**. A causa real só
apareceu porque as horas implícitas da Portte saíram **múltiplos exatos de 8** — e
integralidade não acontece por acaso. Foi a integralidade, não a hipótese, que provou o
método e validou de uma vez o divisor 180 e a alíquota de 20%.

Duas vezes nesta sessão o número derrubou o que eu tinha escrito com confiança. Vale mais
medir cedo do que planejar bonito.
