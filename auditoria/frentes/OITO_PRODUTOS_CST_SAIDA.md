# Os 8 produtos sem regra de saída — diagnóstico com o XML de compra na mão

**25/09/2026** · para levar ao contador. Cada linha traz o que o **documento** diz, não o que
eu acho.

## O que é certo, e vale para os 8

> **Nenhum dos 8 entrou com substituição tributária.** Nenhum tem CST 10/30/60/70 nem CSOSN
> 201/202/203/500 na nota de compra.

Isso decide uma coisa sozinho: **a saída destes 8 NÃO pode ser CST 60.** Declarar CST 60 é
afirmar que o ICMS já foi retido por substituição — e, nestes, não foi. Seria informação falsa
na nota, e com o efeito de não recolher ICMS que é devido.

É por isso que eles estavam travados: o sistema recusa em vez de inventar, e a recusa estava
certa. **Eles são diferentes dos outros 92 do catálogo.**

## O que cada um diz, lido do XML da nota de compra

| # | Produto | Fornecedor | Entrada | O que o XML mostra |
|---|---|---|---|---|
| 1 | LUVA ALGODÃO 4 FIOS | L J Guerra | **CST 20** | redução de base **65%**, ICMS 20% → **7% efetivo** · origem 1 (importado) |
| 2 | NVR 16CH 4K | Futura Tecnologia | **CST 20** | redução **65%**, ICMS 20% → 7% · vBC 623,00 · vICMS 124,60 |
| 3 | CÂMERA BULLET METAL 4MP | Futura Tecnologia | **CST 20** | redução **65%**, ICMS 20% → 7% · vBC 265,30 · vICMS 53,06 |
| 4 | TORRE PLUG IN PLAY | Rastreauto | **CSOSN 400** | fornecedor do **Simples**; «não tributada pelo Simples Nacional» |
| 5 | FONTE 5V 3A USB-C | One Port | **CST 41** | «não tributada» · origem 1 (importado) |
| 6 | SMART LÂMPADA RETRO 11W | Futura Tecnologia | **CST 50** | **suspensão** · origem 1 |
| 7 | SMART FITA LED WI-FI RGB | Futura Tecnologia | **CST 50** | **suspensão** · origem 1 |
| 8 | COLETE REFLETIVO TAM M | — | *(vazio)* | **não há nota de compra no sistema** |

## A leitura, e onde ela para

**Itens 4, 5, 6 e 7 — a minha leitura é CST 00 (tributação normal) na saída.**
O tratamento que o fornecedor aplicou era sobre a **operação dele**, não sobre a mercadoria:

- **CSOSN 400** é status do *regime* do fornecedor (Simples). Não diz nada sobre a nossa saída.
- **CST 50 (suspensão)** é concedida para uma operação específica. Suspensão não «viaja» com a
  mercadoria para a revenda seguinte.
- **CST 41 (não tributada)** teve um fundamento naquela operação. Sem conhecer o fundamento,
  não se herda.

**Itens 1, 2 e 3 — aqui eu paro, e é o contador que decide.**
Redução de base de 65% é um **benefício com norma**. A pergunta que decide é:

> *A redução de base que o fornecedor aplicou vale também na nossa saída interna no Amazonas,
> para estes NCMs (6116.92.00, 8521.90.00, 8525.89.19)?*

Se **sim**, a saída é CST 20 com a mesma redução. Se **não**, é CST 00 integral. Não dá para
deduzir do XML: ele mostra que o fornecedor teve o benefício, não que nós temos.

**Item 8 — falta o documento.** Sem a nota de compra do colete não há fato para ler. Ou aparece
a nota, ou é decisão declarada do dono.

## O que isso custa, e por que não é detalhe

A régua aplica **20%** de ICMS na venda interna normal no Amazonas (CFOP 5102, CST 00).
Sobre o custo médio de cada um, por **unidade vendida**:

| Produto | Custo médio | ICMS se CST 00 |
|---|---:|---:|
| NVR 16CH 4K | 1.780,00 | **356,00** |
| Torre Plug in Play | 1.600,00 | **320,00** |
| Câmera Bullet Metal 4MP | 379,00 | 75,80 |
| Smart Fita LED | 60,51 | 12,10 |
| Fonte 5V 3A USB-C | 50,00 | 10,00 |
| Colete refletivo | 45,90 | 9,18 |
| Smart Lâmpada | 19,74 | 3,95 |
| Luva algodão | 2,55 | 0,51 |

Dois produtos concentram o problema: **NVR e Torre somam R$ 676 de ICMS por unidade.** Nos
outros seis o total não chega a R$ 112.

> **A decisão não é «qual CST usar», é «quanto imposto esta empresa paga ao vender isto».**

## O que fazer, na ordem

1. **Levar os itens 1, 2 e 3 ao contador** com esta tabela e os XMLs de entrada. É a única
   pergunta que precisa de norma, e é a que vale R$ 431 por unidade (NVR + câmera).
2. **Decidir 4, 5, 6 e 7 como CST 00** se o contador concordar com a leitura acima — são
   R$ 346 por unidade, concentrados na Torre.
3. **Achar a nota de compra do colete** (item 8) ou declarar o tratamento.
4. Enquanto não houver decisão, **eles continuam recusados na emissão**, e isso está certo.

## Como registrar a decisão quando ela vier

Cada produto tem `fin_produtos.icms_entrada_cst` e `icms_entrada_fonte`. A **fonte** é
obrigatória em qualquer decisão — quem abrir daqui a um ano precisa saber de onde veio, como já
está gravado nos 6 produtos do Villa Dei Fiori.

---

### ⚠️ Uma medição que NÃO respondeu, e fica registrada como não respondida

Tentei checar se esses NCMs têm **CEST** (indicador de mercadoria sujeita a ST) na tabela
oficial `ncms`. A coluna `icms_cest` está **vazia nos 100 produtos do catálogo** — a tabela tem
10.515 NCMs mas esse campo nunca foi populado.

Ler «nenhum tem CEST» como «nenhum é sujeito a ST» seria tomar ausência de dado por fato. **Não
é conclusão, é lacuna** — e popular o CEST da tabela oficial é uma frente própria, porque
responderia esta pergunta para os 100 produtos de uma vez, não para 8.
