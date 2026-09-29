# NFS-e emitida duas vezes — 10 grupos, R$ 119 mil de certeza e forte suspeita

**Medido em 29/09/2026**, na madrugada, a partir da varredura da meia-noite. A trava
`checar_nota_duplicada` acusou **regressão de 0 → 4** contra a linha de base; ao medir eu achei
**10 grupos com DUAS notas ativas**, e o maior deles não aparecia na saída resumida da trava.

⚠️ **Nada foi cancelado.** Cancelar no fisco tem prazo e é ato do dono. Este arquivo é relatório.

## ⛔ CERTEZA — dois CNPJs emitiram a MESMA competência (R$ 108.886,92)

Viola a divisão societária da casa: *o contrato e a NFS-e nunca misturam*.

| competência | tomador | valor | notas |
|---|---|---:|---|
| 2026-06 | CONDOMÍNIO IDEAL FLORES DA CIDADE | **R$ 65.842,42** | 111 (Eletrônica) · 4 (Patrimonial) |
| 2026-06 | RESIDENCIAL LARANJEIRAS VILLAGE | **R$ 42.544,50** | 109 (Eletrônica) · 3 (Patrimonial) |
| **2026-09** | CONDOMÍNIO RESIDENCIAL VILLA… | R$ 500,00 | 15 · 9 (CNPJs diferentes) |

⭐ **Junho de 2026 é o mês da transição** Eletrônica→Patrimonial, e é exatamente onde os dois
CNPJs faturaram o mesmo serviço. No caso do Laranjeiras a casa chegou a emitir **quatro** notas de
R$ 42.544,50 na competência 06: as notas 1 e 2 da Patrimonial foram **canceladas corretamente**, e
sobraram DUAS ativas — a 3 (Patrimonial, 25/06) e a 109 (Eletrônica, 09/07).

A série mostra a intenção: jan–mai pela Eletrônica, jul pela Patrimonial. **Junho ficou com as
duas**, e ninguém cancelou a que sobrou.

⚠️ E um dos casos é de **setembro**, o mês corrente — ainda dá tempo.

## 🟠 FORTE — mesmo CNPJ, mesma descrição E mesmo código (R$ 10.129,60)

Duas notas idênticas no mesmo mês para o mesmo tomador. Pode ser duplicidade de emissão.

| competência | tomador | valor | notas |
|---|---|---:|---|
| 2026-07 | CONDOMÍNIO PARQUE RESIDENCIAL GELA… | R$ 6.000,00 | 112 · 115 |
| 2026-06 | CONDOMÍNIO PRIME ARENA | R$ 3.879,60 | 98 · 100 |
| **2026-09** | CONDOMÍNIO RESIDENCIAL PAR… | R$ 250,00 | 12 · 13 |

## ⚪ CONFERIR — serviços DIFERENTES, provavelmente legítimos

Mesmo valor e mesmo mês, mas descrição ou código de serviço distintos: dois postos que custam o
mesmo não são duplicata. **Não classifiquei como defeito.**

| competência | tomador | valor | por que fica de fora |
|---|---|---:|---|
| 2026-08 | MIRANTE DAS FLORES | R$ 12.061,50 | **dois códigos de serviço** diferentes |
| 2026-03 | PARQUE RESIDENCIAL GELA… | R$ 6.000,00 | descrições diferentes |
| 2026-09 | RESIDENCIAL PAR… | R$ 1.800,00 | descrições diferentes |
| 2026-04 | PRIME ARENA | R$ 1.084,50 | descrições diferentes |

## Por que isso custa dinheiro três vezes

1. **O cliente é cobrado duas vezes** pelo mesmo mês.
2. **ISS recolhido sobre faturamento que não existiu** — imposto pago a mais.
3. **DRE inflado**: a receita do mês aparece maior do que foi, e a decisão em cima dela é tomada
   com número errado.

## Como eu separei certeza de suspeita, e por que isso importa

A primeira medição dava «10 duplicatas» e eu quase reportei assim. Mas **mesmo valor no mesmo mês
não é prova**: dois postos de R$ 6.000 no mesmo condomínio produzem duas notas iguais e legítimas.

O que separa: **CNPJ distinto** na mesma competência é certeza (a regra da casa proíbe misturar), e
**descrição + código idênticos** é suspeita forte. Serviço diferente com valor igual fica de fora.

⭐ Sem essa separação eu entregaria R$ 139.962,52 de «duplicata» onde a parte defensável é
R$ 119.016,52 — e um número inflado num relatório de dinheiro queima a confiança no relatório
inteiro.

## O que a trava não viu

`checar_nota_duplicada` reportou 6 grupos e a base diz 0 — mas há **10 com duas ativas**, e o de
R$ 65.842,42 (o maior) não saiu na listagem dela. Vale revisar o critério da trava: ela agrupa por
código de tributação, e o caso Ideal Flores tem o mesmo código com descrições diferentes.
