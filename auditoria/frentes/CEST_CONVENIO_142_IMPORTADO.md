# CEST do Convênio 142/2018 importado — e 6 produtos que entraram com ST sem poder ser ST

**25/09/2026** · autonomia do dono: *«prepara o importador, trabalha em loop em tudo referente
a fiscal e contabilidade»*.

## O que foi feito

A tabela oficial do **Convênio ICMS 142/2018** (CONFAZ) foi baixada, extraída do HTML e
importada para `ncms.icms_cest`.

| | |
|---|---|
| CESTs no Convênio | **1.051** |
| NCMs de 8 dígitos com CEST **único** → gravados | **1.317** |
| NCMs **ambíguos** (2+ CESTs) → não gravados | 1.376 |
| NCMs **fora** do Convênio → não são ST em lugar nenhum | 7.822 |

Importador: `backend/scripts/fiscal/importar_cest_convenio142.py` — idempotente, com conferência
antes de `--aplicar`.

## Por que a fonte é o Convênio, e não a nota do fornecedor

Cruzei os **14 CESTs que fornecedores declararam** nas notas de compra desta casa contra a
tabela oficial: **11 conferem, 3 estão ERRADOS.**

| O que o fornecedor declarou | O que o Convênio diz |
|---|---|
| Controle remoto de portão (8526.92.00) com CEST **01.999.00** | «outras peças e acessórios para **veículos automotores**» — não é autopeça |
| Naftalina (2902.90.20) com CEST **28.043.00** | segmento 28 = **porta a porta**, e o NCM listado é 4202.92.00 |
| Sensor magnético (8543.70.99) com CEST **28.063.00** | «produtos de **limpeza e conservação doméstica**», também porta a porta |

> Copiar o CEST do fornecedor para a nossa nota de saída propaga o erro dele **com o nosso CNPJ
> embaixo**. Convênio manda; declaração de terceiro é indício.

## O achado: 6 produtos entraram com ST e não podem ser ST

Entraram com ICMS **retido por substituição** (CST 60 / CSOSN 500) e o NCM deles **não aparece
em nenhum segmento** do Convênio — nem no 28:

| Código | Produto | NCM | Entrada |
|---|---|---|---|
| 001649 | SENSOR IVA FOTOCÉLULA 12V/24V | 8541.42.90 | CSOSN 500 |
| 008207 | SUPER PANO MICROFIBRA 29×29 | 6307.10.00 | CST 60 |
| 010605 | NAFTALINA RUBI 40G | 2902.90.20 | CST 60 |
| 024977 | LUSTRA MÓVEIS BUTTERFLY LAVANDA | 3405.20.00 | CST 60 |
| 032881 | PURIF. AMB. GLADE AERO | 3307.49.00 | CST 60 |
| 047534 | PULVERIZADOR PET 500ML | 8424.89.90 | CST 60 |

**O que isso significa, em dinheiro:** se esses produtos não são ST, o fornecedor reteve ICMS
que talvez não fosse devido — e a casa **pagou esse ICMS embutido no preço de compra**. Há
hipótese de restituição. E, ao revender, tratá-los como CST 60 seria não destacar ICMS que é
devido.

Não é conclusão fechada: pode haver protocolo estadual do AM incluindo o item, ou erro de NCM no
cadastro do próprio fornecedor. **É pergunta para o contador, com os XMLs de entrada em mãos.**

## Um erro meu no caminho, e ele quase virou relatório

A primeira contagem deu **30 produtos** em contradição. Estava errada: ela somava
«NCM fora do Convênio» com «NCM ambíguo que eu não gravei» — duas coisas diferentes. Ausência
de gravação não é ausência de CEST.

Separando: 37 fora do Convênio · 32 ambíguos · 31 com CEST único. A contradição real caiu de 30
para **7** — e depois para **6**, quando testei se os NCMs apareciam no segmento 28, que eu havia
excluído de propósito. O pano de chão está lá e saiu da lista.

> **30 → 7 → 6.** Duas medições a mais derrubaram 80% do achado. Um número que sobrevive a
> duas tentativas de matá-lo vale mais que um número grande.

## Por que o segmento 28 é excluído do casamento

O segmento 28 é «venda de mercadorias pelo sistema **porta a porta**»: a sujeição depende da
MODALIDADE da venda, não da mercadoria. Casar por ele daria CEST a produto que, na venda
normal, não é ST — que é exatamente o erro de dois dos três fornecedores acima.

## O que ficou aberto

- **1.376 NCMs ambíguos** (2+ CESTs para o mesmo NCM): decidir exige ler a descrição do produto
  contra a do Convênio. Dos 100 produtos do catálogo, **32** caem aqui.
- **Os 6 acima**, para o contador.
- A coluna `fin_produtos.cest` tem 28 valores vindos de nota de fornecedor; **3 deles são dos que
  erraram** e devem ser conferidos contra a tabela agora importada.
