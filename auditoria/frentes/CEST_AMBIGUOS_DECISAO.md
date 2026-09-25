# Os 15 produtos com CEST ambíguo — tabela de decisão

**25/09/2026.** Depois de importar o Convênio ICMS 142/2018, 15 produtos do catálogo fiscal
casam com **dois ou mais CESTs**. Não gravei nenhum: escolher entre dois exige ler a descrição
do produto contra a do Convênio, e CEST errado vai **dentro da nota**.

## Tentei resolver por máquina e não deu — e isso é resultado, não desistência

Comparei as palavras da descrição do produto com as da descrição de cada CEST candidato,
exigindo **vencedor com folga**. Resultado: **0 de 15**. As descrições do Convênio são
técnicas («outras máquinas automáticas para processamento de dados») e as do catálogo são
comerciais («PROGRAMADOR NICE OVIEW») — quase não compartilham vocabulário.

> Forçar a escolha com a heurística fraca teria produzido 15 classificações fiscais
> plausíveis e não verificadas. Melhor 15 em branco e uma tabela de 2 minutos.

## A maioria é decidível por quem conhece o produto

Vários pares diferem por **um detalhe físico** que o dono sabe de cabeça:

- **Papel higiênico**: `20.042.00` folha SIMPLES × `20.043.00` folha dupla/tripla/quádrupla
- **Programador Nice Oview**: `21.028.00` portátil até 10 kg × `21.029.00` as outras
- **Sabão em barra**: `20.035.00` outros sabões em barra × `20.035.01` (variante)
- **Pneu 175/70R14**: `16.002.00` × `16.004.00` — muda por tipo/aplicação

Não são questões de norma: são questões de **qual é o produto**. Quem responde é quem compra.

## A tabela

| Produto | NCM | CEST candidato | O que o Convênio diz |
|---|---|---|---|
| **PROGRAMADOR NICE OVIEW** | 84713090 | `21.028.00` | Máquinas automáticas para processamento de dados, portáteis, de peso não superior a 10 kg, conte |
|  |  | `21.029.00` | Outras máquinas automáticas para processamento de dados |
| **KIT LOCALIZADOR E TESTADOR DE CABOS RJ45 E** | 90308990 | `21.119.00` | Aparelhos e instrumentos para medida ou controle da tensão, intensidade, resistência ou da potên |
|  |  | `21.120.00` | Analisadores lógicos de circuitos digitais, de espectro de frequência, frequencímetros, fasímetr |
| **CARTUCHO RC203 P/RESPIRADOR CG-306 VO+GA C** | 84213990 | `01.039.00` | Partes dos aparelhos para filtrar ou depurar líquidos ou gases |
|  |  | `01.095.00` | Filtros de pólen do ar-condicionado |
|  |  | `21.014.00` | Partes das secadoras de roupas e centrífugas de uso doméstico e dos aparelhos para filtrar ou de |
| **PAP HIG 300MT 100% CELULOSE LIRIO DO CAMPO** | 48181000 | `20.042.00` | Papel higiênico - folha simples |
|  |  | `20.043.00` | Papel higiênico - folha dupla, tripla e quádrupla |
| **SABAO EM BARRA MARMORIZADO VERDE ECONOMICO** | 34011900 | `20.035.00` | Outros sabões, produtos e preparações, em barras, pedaços ou figuras moldados |
|  |  | `20.035.01` | Lenços umedecidos |
| **HIPERCLOR 60 BD C/ 10KG** | 38089419 | `11.001.00` | Água sanitária, branqueador e outros alvejantes |
|  |  | `11.002.00` | Sabões, desinfetantes e sanitizantes, todos em pó, flocos, palhetas, grânulos ou outras formas s |
|  |  | `11.003.00` | Sabões, desinfetantes e sanitizantes, todos líquidos para lavar roupas |
| **175/70R14 84T LANDSPIDER CYTRAXX G/P HT - ** | 40111000 | `16.001.00` | Pneus novos, dos tipos utilizados em automóveis de passageiros (incluídos os veículos de uso mis |
|  |  | `16.002.00` | Pneus novos, dos tipos utilizados em caminhões (inclusive para os fora-de-estrada), ônibus, aviõ |
|  |  | `16.004.00` | Outros tipos de pneus novos, exceto os itens classificados no CEST 16.005.00 |
| **SERRA MANUAL 12"  32D BS1232 SAFE-FLEX UNI** | 82029100 | `08.006.00` | Lâminas de serras máquinas |
|  |  | `08.007.00` | Serras manuais e outras folhas de serras (incluídas as fresas-serras e as folhas não dentadas pa |
| **VALVULA 414 - 414RC GTIN 7898661710474** | 84818099 | `01.047.00` | Válvulas para transmissão óleo-hidráulicas ou pneumáticas |
|  |  | `10.079.00` | Torneiras, válvulas (incluídas as redutoras de pressão e as termostáticas) e dispositivos semelh |
| **OLEO PEROBA 100ML JASMIM KING** | 27101999 | `06.006.00` | Óleo diesel A, exceto S10 e Marítimo |
|  |  | `06.006.01` | Óleo diesel B, exceto S10 (mistura obrigatória) |
|  |  | `06.006.02` | Óleo diesel B, exceto S10 (misturas autorizativas) |
|  |  | `06.006.03` | Óleo diesel B, exceto S10 (misturas experimentais) |
|  |  | `06.006.04` | Óleo diesel A S10 |
|  |  | `06.006.05` | Óleo diesel B S10 (mistura obrigatória) |
|  |  | `06.006.06` | Óleo diesel B S10 (misturas autorizativas) |
|  |  | `06.006.07` | Óleo diesel B S10 (misturas experimentais) |
|  |  | `06.006.08` | Óleo Diesel Marítimo |
|  |  | `06.006.09` | Outros óleos combustíveis, exceto os classificados no CEST 06.006.10 e 06.006.11 |
|  |  | `06.006.10` | Óleo combustível derivado de xisto |
|  |  | `06.007.00` | Óleos lubrificantes |
|  |  | `06.008.00` | Outros óleos de petróleo ou de minerais betuminosos (exceto óleos brutos) e preparações não espe |
|  |  | `06.008.01` | Graxa lubrificante |
|  |  | `06.009.00` | Resíduos de óleos |
|  |  | `06.019.00` | Naftas, exceto a Nafta petroquímica. |
| **PROTETOR SOLAR 30FPS 1/3 UVA 1LT NUTRIEX** | 33049990 | `20.015.00` | Outros produtos de beleza ou de maquilagem preparados e preparações para conservação ou cuidados |
|  |  | `20.016.00` | Preparações solares e antissolares |
| **CAMERA IP DE TV BULLET VIP 1230 FC+ - 4900** | 85258913 | `21.065.00` | Câmeras fotográficas digitais e câmeras de vídeo |
|  |  | `21.107.00` | Câmeras de televisão |
| **PROG V2 - PROGRAMADOR DE FUNCOES (LARANJA)** | 84713019 | `21.028.00` | Máquinas automáticas para processamento de dados, portáteis, de peso não superior a 10 kg, conte |
|  |  | `21.029.00` | Outras máquinas automáticas para processamento de dados |
| **CAMERA BULLET IP 1230 INTELBRAS** | 85258913 | `21.065.00` | Câmeras fotográficas digitais e câmeras de vídeo |
|  |  | `21.107.00` | Câmeras de televisão |
| **FONTE 3AMP 12V ELETRONICA FC** | 85044090 | `12.001.00` | Transformadores, bobinas de reatância e de auto indução, inclusive os transformadores de potênci |
|  |  | `21.036.00` | Outros transformadores, exceto os classificados nos códigos 8504.33.00 e 8504.34.00 |
total: 15 produto(s) ambíguo(s)

## Como gravar depois de decidir

```sql
UPDATE fin_produtos
   SET cest = '<CEST sem pontos>',
       observacao = coalesce(observacao,'') || ' | CEST escolhido por <quem> em <data>: <por quê>'
 WHERE codigo = '<codigo>';
```

A **razão** é obrigatória — quem abrir daqui a um ano precisa saber por que este e não o outro,
como já está gravado nos 6 produtos do Villa Dei Fiori.

> ⚠️ Ter CEST **não** significa «é ST no Amazonas»: significa que a mercadoria está numa lista
> que **pode** ser ST, se o estado aderiu ao segmento. Quem decide se há ST na operação é o
> `icms_entrada_cst` — como a mercadoria entrou —, e isso continua vindo do XML da nota de
> compra.
