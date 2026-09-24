# Parametrização fiscal REAL — extraída das notas do dono (24/09/2026)

> **Origem:** 9 DANFSe + 1 DANFE que o Jordan subiu para `uploads/_entrada/NFs/` em 24/09/2026,
> mais o `Cronograma de Emissão de Notas Conectamais 2026.ods`.
> **Mandato dele:** *«faça de tudo para ao emitir não pagarmos imposto indevidamente, parametrize
> o sistema de forma que saia sempre da melhor forma pra nós, pois já pagamos muitos impostos,
> não podemos pagar a mais».*
>
> **Tudo aqui é MEDIDO em documento que o fisco emitiu.** Nada é convenção, nada é palpite.
> O que não tiver fonte está marcado «sem fonte» e é decisão de humano.

## 1. Identidade das duas empresas

| | CONECTAMAIS ELETRONICA | CONECTAMAIS PATRIMONIAL |
|---|---|---|
| CNPJ | 35.710.481/0001-03 | 66.014.833/0001-10 |
| Regime | lucro real (CRT 3) | Simples Nacional (CRT 1) |
| Inscrição estadual | **054265746** (confirmada na DANFE 10.026) | **não tem, e não vai ter** — decisão do dono |
| Inscrição municipal | 45177801 | 721042001 · **no DANFSe sai como «-»** |
| Endereço legal (fisco) | Nova Palestina, 51 — Crespo — 69073488 | Rua Victor Hughes, 19 — Parque 10 de Novembro — 69055630 |
| Emite | **NF-e 55** + NFS-e | **somente NFS-e** |

## 2. NF-e de produto (só Eletrônica) — DANFE nº 10.026, 17/09/2026

| | |
|---|---|
| **Numeração real** | nº **10.026**, **série 1** · protocolo 113263811849419 |
| Emissor usado hoje | terceiro — `nfemais.com.br` |

**O achado que evita pagar imposto a mais.** Os seis itens da nota real saem com:
```
CFOP 5405 · CST 060 · BC ICMS 0,00 · V.ICMS 0,00 · %ICMS 0,00
Natureza: "Venda de mercadoria, adquirida ou recebida de terceiros, sujeita a ST"
```
**CST 060 = ICMS cobrado anteriormente por substituição tributária.** O ICMS foi pago na COMPRA;
na saída não se cobra de novo. A nossa régua devolvia **CFOP 5102** nos seis, e o emissor
produziu **CST 00 com ICMS 20%** — imposto a maior sobre mercadoria já tributada.

**Medido nos XML de entrada em produção (`nfe_entradas.xml_raw`, 209 itens):**
```
CST de ICMS na entrada:  60 → 97  ·  00 → 74  ·  53 → 13  ·  06 → 6  ·  20 → 5  ·  50 → 5  ·  41 → 4  ·  99 → 3
CFOP na entrada:       5102 → 85  ·  5929 → 61  ·  5405 → 44  ·  5912 → 5  ·  5101 → 4  ·  2909 → 4
com ICMS já retido por ST (CST 10/30/60/70/500): 97 de 207 = 47%
```
**Regra:** o CFOP/CST de SAÍDA depende de como a mercadoria ENTROU. Produto sem entrada conhecida
não sai chutando — recusa e pergunta.

**Armadilha de leitura:** a DANFE traz no rodapé *«Trib aprox: Fed R$ 365,84 (14,53%), Est
R$ 503,60 (20,00%)»*. Isso é a **Lei 12.741/2012** (imposto aproximado embutido no preço, fonte
IBPT), **não** imposto cobrado. O ICMS da nota é **zero**. Ler aqueles 20% como ICMS devido
«confirmaria» o erro em vez de achá-lo.

## 3. NFS-e — o que é igual nas duas empresas

| | |
|---|---|
| **Série da DPS** | **70000** nas duas (o código assumia 900 → fisco recusava `E0141`) |
| Último nº de DPS observado | Patrimonial **75** (08/26) · Eletrônica **125** (09/26) |
| Último nº de NFS-e observado | Patrimonial **32** · Eletrônica **123** |
| CST / cClassTrib IBS/CBS | **000 / 000001** |
| Alíquota IBS-UF / IBS-Mun | **0,10 % / 0,00 %** |
| Alíquota CBS | **0,90 %** |
| Indicador / IBGE incidência | 030103 / 1302603 (Manaus) |

### Códigos de serviço e o NBS de cada um — MEDIDOS, um por nota

| Serviço | Código nacional | **NBS** | Visto em |
|---|---|---|---|
| Agentes de portaria / vigilância | **11.02.01** | **1.1802.90.00** | PATR 28, 29, 30 |
| Limpeza, conservação, serviços gerais | **07.10.02** | **1.1803.10.00** | PATR 27, 31 |
| Manutenção (CFTV/cerca/portão/cancela) | **14.01.01** | **1.2001.89.00** | ELET 116, 121 |
| Instalação / portaria remota | **14.06.01** | **1.2003.29.00** | ELET 119, 120 |

> O `cNBS` que estava chumbado no código era `1.2003.29.00` — **certo só para 14.06.01**, errado
> nos outros três. Era por isso que o fisco devolvia descrição errada nas notas de vigilância.

## 4. NFS-e da ELETRÔNICA (lucro real)

| nº | cód | operação | ISS 5% | **exclusões** | BC IBS/CBS | IBS | CBS | IRRF | CSLL | retenções | líquido |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 116 | 14.01.01 | 3.800,00 | 190,00 | **190,00** | 3.610,00 | 3,61 | 32,49 | — | 38,00 | 38,00 | 3.762,00 |
| 119 | 14.06.01 | 6.000,00 | 300,00 | **300,00** | 5.700,00 | 5,70 | 51,30 | — | 60,00 | 60,00 | 5.940,00 |
| 120 | 14.06.01 | 2.000,00 | 100,00 | **100,00** | 1.900,00 | 1,90 | 17,10 | — | 20,00 | **120,00** | 1.880,00 |
| 121 | 14.01.01 | 1.800,00 | 90,00 | **90,00** | 1.710,00 | 1,71 | 15,39 | **18,00** | 18,00 | 36,00 | 1.764,00 |

**Três regras que saem daí, e as três economizam ou acertam imposto:**

1. **A base do IBS/CBS é o valor MENOS o ISS.** Em todas as quatro, «Exclusões e Reduções da Base
   de Cálculo» = exatamente o ISSQN apurado. Cobrar IBS/CBS sobre o valor cheio pagaria a mais.
2. **PIS e COFINS NÃO são retidos** — código **«8 - PIS/COFINS Não Retidos, CSLL Retido»**, por
   decisão judicial citada na própria nota 121: **processo nº 1038495-94.2024.4.01.3200**.
   Reter PIS/COFINS aqui seria pagar o que a Justiça já dispensou.
3. **ISS retido pelo tomador muda o líquido, não o devido.** Na 120 a retenção total é R$ 120,00
   (ISS 100 + CSLL 20) porque o ISS foi «Retido pelo Tomador»; nas outras o ISS é «Não Retido» e
   só a CSLL entra na retenção.

**IRRF — DECIDIDO PELO DONO em 24/09/2026: não reter.** Palavras dele:
*«vamos usar daqui pra frente sem a retenção do irrf»*.

O que motivou a pergunta: o **IRRF de 1%** aparecia **só na nota 121** (setembro, R$ 18,00). As
três de agosto — inclusive a **116**, com o **mesmo código de serviço `14.01.01`** e o **mesmo
tipo de tomador (condomínio)** — saíram **sem IRRF**. Uma das duas práticas estava errada, e o
dono escolheu a de agosto.

**Como implementar:** `irrf_reter = false` é **parâmetro por empresa**, semeado com a decisão
acima e a data, **não** um `if` no código nem a remoção do campo. O cálculo do IRRF continua
existindo e desligado — o dia que o contador disser o contrário, muda uma linha de tabela e as
notas voltam a sair com ele.

**O que fica registrado para o contador:** a nota 121 já foi emitida COM IRRF de R$ 18,00. Se a
posição correta for «não reter», aquela nota reteve a mais; se for «reter», as de agosto
retiveram a menos. A decisão do dono vale daqui para a frente e **não reabre o passado** — o que
fazer com a 121 e com as de agosto é decisão dele, com o contador.

## 5. NFS-e da PATRIMONIAL (Simples Nacional)

| nº | cód | operação | ISS | exclusões | BC IBS/CBS | IBS | CBS | INSS retido | retenções | líquido |
|---|---|---|---|---|---|---|---|---|---|---|
| 27 | 07.10.02 | 12.061,50 | **—** | 0,00 | 12.061,50 | 12,06 | 108,55 | 1.326,76 | 1.326,76 | 10.734,74 |
| 28 | 11.02.01 | 28.694,30 | **—** | 0,00 | 28.694,30 | 28,69 | 258,25 | 3.156,37 | 3.156,37 | 25.537,93 |
| 29 | 11.02.01 | 33.538,33 | **—** | 0,00 | 33.538,33 | 33,54 | 301,84 | 3.689,21 | 3.689,21 | 29.849,12 |
| 30 | 11.02.01 | 25.592,71 | **—** | 0,00 | 25.592,71 | 25,59 | 230,33 | 2.815,20 | 2.815,20 | 22.777,51 |
| 31 | 07.10.02 | 8.346,70 | **—** | 0,00 | 8.346,70 | 8,35 | 75,12 | 918,13 | 918,13 | 7.428,57 |

**Três regras:**

1. **ISS não sai na nota.** BC, alíquota e ISSQN apurado vêm **vazios** («-»), porque no Simples
   o ISSQN vai no DAS. Preencher 0% seria mentira; preencher 5% seria pagar duas vezes.
2. **Sem ISS na nota, não há exclusão** — a base do IBS/CBS é o valor cheio. Coerente com a regra 1
   da Eletrônica: o que se exclui é o ISS, e aqui não há ISS na nota.
3. **PIS, COFINS e CSLL não são retidos** — código **«0 - PIS/COFINS/CSLL Não Retidos»** (Simples).

### REGRA DO DONO (24/09/2026) — deduzir VA e VT antes dos 11%, sempre

Palavras dele, em duas mensagens:
> *«vamos deduzir vale-alimentação e vale-transporte antes de aplicar os 11% em todas as notas
> que tiver cessão de mão de obra, isso é regra, vai nos possibilitar economizar»*
> *«essa regra só vale para cessão de mão de obra que sempre terá nota fiscal de serviço emitida
> pela conecta patrimonial»*

**O gatilho é o EMITENTE, e isso torna a regra checável sem interpretar texto:**

| Emitente | Cessão de mão de obra? | INSS |
|---|---|---|
| **CONECTAMAIS PATRIMONIAL** | **sempre** | 11% sobre **bruto − (VA + VT)** |
| CONECTAMAIS ELETRONICA | **nunca** | não há retenção do Art. 31 |

Isso elimina um falso positivo que eu mesmo tinha produzido: classifiquei «Instalação/Portaria
Remota» do Gelain como cessão porque a palavra «portaria» aparece. **Portaria remota não é cessão
de mão de obra** — não há pessoa posta no cliente — e é da Eletrônica. Fora.

**O dinheiro, medido.** Em **agosto** as cinco notas da Patrimonial retiveram **11% do bruto, sem
dedução nenhuma** — conferido ao centavo nas cinco. O cronograma de setembro já deduz em três
linhas. A diferença só nessas três:

| Tomador | Bruto | VA+VT | INSS com dedução | INSS s/ dedução | Diferença |
|---|---|---|---|---|---|
| Prime Arena | 29.600,00 | 2.684,00 | 2.960,76 | 3.256,00 | **295,24** |
| Laranjeiras Village | 42.544,50 | 3.688,00 | 4.274,21 | 4.679,90 | **405,69** |
| Ideal Flores | 65.842,42 | 4.404,00 | 6.511,62 | 7.242,67 | **731,05** |
| | | | | | **R$ 1.431,98** |

**A condição legal que não pode ser esquecida:** a dedução só se sustenta com **VA e VT
discriminados na própria nota**. O cronograma do dono já escreve assim; a nota emitida pelo
sistema tem de escrever também, ou a dedução é glosável.

**O PROBLEMA QUE ISSO EXPÕE — o número não está no sistema.** Medido em 24/09:
- `beneficio_entregas` e `beneficio_entrega_itens`: **0 linhas**. A estrutura existe, o dado não.
- `beneficio_linhas`: 2 linhas, só a diária do VT (SINETRAM e SOLIDES, R$ 10,00/dia).
- `folha_verba_espelho` tem **«Desconto VT» (1010)** e **«Desconto VR» (1011)** — isso é o
  **desconto de 6% do empregado**, NÃO o custo do benefício pago pela empresa. Base errada.

Ou seja: hoje o sistema **não sabe** quanto de VA+VT foi entregue por contrato/mês. Enquanto não
souber, **o valor é digitado pelo humano na emissão** (como o dono já faz na planilha) e o sistema
faz a conta e escreve na nota — **nunca inventa o número**. Ligar a fonte automática
(entrega de benefício por posto → cliente) é frente própria.

**O INSS é a única retenção, e ela tem base própria.** Retenção de **11%** pelo **Art. 31 da
Lei 9.711/98**, com base = **valor bruto menos vale-alimentação e vale-transporte do mês**.
Do cronograma do dono, o caso do Prime Arena:
```
bruto 29.600,00 − (VA 1.804,00 + VT 880,00 = 2.684,00) = base 26.916,00 × 11% = 2.960,76
```
**Cobrar 11% sobre o bruto pagaria R$ 295,24 a mais só nessa nota.** VA e VT já são calculados
por este sistema, na folha.

## 6. Cronograma de setembro — 14 notas

`Cronograma de Emissão de Notas Conectamais 2026.ods`, aba «Conectamais». Cada linha tem tomador,
CNPJ, valor bruto, tipo de serviço e a descrição inteira que vai na nota. A empresa emitente é
identificada pelos dados bancários na descrição:

| Banco na descrição | Empresa |
|---|---|
| CORA SCD 403 · ag 0001 · cc 7382527-7 · PIX CNPJ 66.014.833/0001-10 | **Patrimonial** |
| INTER 077 · ag 0001 · cc 37099007-2 · PIX CNPJ 35.710.481/0001-03 | **Eletrônica** |

> A aba `Cópia_de_Conectamais` é o MODELO (datas e valores como `XX/XX`, `R$ XXXX`) e está
> **desatualizada** em duas linhas — Prime Arena/Manutenção e Villa dos Pássaros/Manutenção
> aparecem lá com a conta da Patrimonial e na aba boa com a da Eletrônica. **Vale a aba boa.**

## 7. O que fica sem fonte (não parametrizar, perguntar)

1. ~~IRRF~~ — **DECIDIDO pelo dono em 24/09: não reter daqui para a frente** (§4). Fica para
   o contador apenas o que fazer com a 121, que já saiu com R$ 18,00.
2. **CST 53, 06, 20, 50, 41 na entrada** — 33 itens. Diferimento, redução de base, suspensão e
   não tributada têm tratamento de saída próprio; não há nota real de saída que mostre qual.
3. **A nota 26 da Patrimonial** (R$ 12.061,50, código 110201) — o dono confirmou que foi erro e
   segue **válida no fisco**. Cancelar tem prazo.
4. **37 notas** emitidas no fisco sem linha no ERP (33 da Eletrônica, 4 da Patrimonial).
