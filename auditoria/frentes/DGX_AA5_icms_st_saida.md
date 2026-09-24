# DGX AA5 — O ICMS que já foi pago não se cobra de novo

**Frente:** AA5 (onda 9) · **Branch:** `dgx/aa5-icms-st-saida` · **Data:** 24/09/2026
**Módulo:** fiscal · **Porta de teste:** 8295 (`teste-dgx-aa5`, **parado ao fim**)
**Ambiente de toda a frente:** HOMOLOGAÇÃO (`tpAmb = 2`). **Nenhuma transmissão em produção.**
**Banco:** sandbox `conecta_pro_staging` para escrita; produção `conecta_pro` só leitura.

---

## §1 — O estado antes, medido

### 1.1 A régua de fora do sistema: a NF-e nº 10.026 da própria empresa

O dono subiu a DANFE da **NF-e nº 10.026, série 1**, da CONECTAMAIS ELETRONICA
(CNPJ 35.710.481/0001-03, IE 054265746, Nova Palestina 51 — Crespo — Manaus/AM — CEP 69073488),
emitida em **17/09/2026** para o CONDOMINIO RESIDENCIAL PARQUE DOS FRANCESES
(CNPJ 03.843.564/0001-84, Manaus/AM), **R$ 2.518,00**, protocolo **113263811849419**, chave
`1326 0935 7104 8100 0103 5500 1000 0100 2618 0548 4852`. Emissor de terceiro: **nfemais.com.br**.

Natureza da operação impressa: *«Venda de mercadoria, adquirida ou recebida de terceiros,
suj[eita a ST]»*. Os **seis itens**, todos iguais no tributo:

```
CFOP 5405 · CST 060 · BC ICMS 0,00 · V.ICMS 0,00 · %ICMS 0,00
```

**CST 060 = ICMS cobrado anteriormente por substituição tributária.** O imposto foi pago na
COMPRA; na saída não se cobra de novo.

### 1.2 O que o nosso sistema fazia com os mesmos seis produtos

Medido rodando o oráculo desta frente contra o código de **antes** (commit `3e3158af9`):

| Item da nota real | NCM | Nossa régua ANTES | A nota real | ICMS cobrado a mais |
|---|---|---|---|---|
| CABO LAN CAT5E 305M 100% COBRE | 85444900 | **5102 · CST 00 · 20,00% · R$ 179,00** | 5405 · 060 · 0,00% · R$ 0,00 | **R$ 179,00** |
| CENTRAL FONTE SUSPENSA INTELBRAS | 85044021 | **5102 · CST 00 · 20,00% · R$ 73,00** | 5405 · 060 · 0,00% · R$ 0,00 | **R$ 73,00** |
| BOTOEIRA PORTA (2 un) | 85365090 | **5102 · CST 00 · 20,00% · R$ 36,00** | 5405 · 060 · 0,00% · R$ 0,00 | **R$ 36,00** |
| FECHADURA ELETRONICA PAPAIZ (2 un) | 83014000 | **5102 · CST 00 · 20,00% · R$ 155,60** | 5405 · 060 · 0,00% · R$ 0,00 | **R$ 155,60** |
| CONECTOR POWER BALUN (2 un) | 85369090 | **5102 · CST 00 · 20,00% · R$ 42,00** | 5405 · 060 · 0,00% · R$ 0,00 | **R$ 42,00** |
| CANALETA 10X10 COM FITA (9 un) | 39162000 | **5102 · CST 00 · 20,00% · R$ 18,00** | 5405 · 060 · 0,00% · R$ 0,00 | **R$ 18,00** |
| | | | **TOTAL** | **R$ 503,60 numa nota de R$ 2.518,00** |

E a base de cálculo saía com o valor cheio do item (R$ 895,00, R$ 365,00, …) onde a nota real
traz **0,00**.

### 1.3 A armadilha de leitura que NÃO foi seguida

A DANFE traz nos dados adicionais: *«Trib aprox: Fed R$ 365,84 (14,53%), Est R$ 503,60 (20,00%),
Mun R$ 0,00 — Fonte: IBPT/empresometro.com.br/AM — A906AF»*. Isso é a **Lei 12.741/2012**
(imposto **aproximado** embutido no preço, informação ao consumidor), **não** imposto cobrado.
O ICMS da nota é **zero**. Ler aqueles 20% como ICMS devido seria confirmar o defeito em vez de
achá-lo. (Coincidência que ajuda a entender o tamanho do erro: R$ 503,60 é exatamente o que a
nossa régua cobraria — 20% sobre R$ 2.518,00.)

### 1.4 Quanto disso é o catálogo inteiro — medição própria

Parser próprio sobre `nfe_entradas.xml_raw` (51 notas com XML de fornecedores de Manaus),
**restrito ao grupo `det/imposto/ICMS`**, em produção e no sandbox (números idênticos):

```
itens de NF-e de entrada .............................. 209
CST de ICMS na entrada : 60 → 97 · 00 → 73 · 20 → 5 · 50 → 5 · 41 → 4
CSOSN na entrada       : 102 → 13 · 500 → 9 · 400 → 1     (2 itens sem grupo de ICMS)
com ICMS já retido por ST (CST 10/30/60/70 · CSOSN 201/202/203/500) → 106 de 209 = 50,7%
CFOP de entrada desses 106 : 5929 (cupom) → 61 · 5405 → 44 · 5403 → 1
```

> ⚠️ **Correção de uma contagem que circulou na onda.** O briefing e o
> `PARAMETRIZACAO_FISCAL_REAL_2026-09-24.md` trazem «CST 60 → 97 · 00 → 74 · **53 → 13** ·
> **06 → 6** · 20 → 5 · 50 → 5 · 41 → 4 · **99 → 3**; 97 de 207 = 47%». Aquela leitura pegou o
> `<CST>` de **qualquer** imposto do item: **53 é CST de IPI**, **06 e 99 são de PIS/COFINS**.
> Restrita ao ICMS, a conta é a de cima: **106 de 209 = 50,7%**. O relatório da frente Z4 já
> tinha chegado a «106 dos 207 (51%)» — bate com esta medição. **A medição vence; fica
> registrado com o número**, e o item (d) do oráculo trava os dois valores.

Cruzando com o catálogo fiscal (`fin_produtos`, 95 linhas, todas nascidas das notas de entrada —
casamento por `codigo` = `cProd`: **95 de 95**):

| Como a mercadoria entrou | Produtos | O que a saída passa a ser |
|---|---|---|
| **ICMS já retido por ST** — CST 60 (37) + CSOSN 500 (6) | **43** | CFOP **5405** · CST **060** · ICMS **zero** |
| Tributada normal — CST 00 (32) + CSOSN 102 (11) | **43** | CFOP 5102 · CST 00 · 20% (como antes) |
| **Sem tratamento com fonte** — CST 20 (3), 50 (2), 41 (1), CSOSN 400 (1), sem grupo de ICMS (2) | **9** | **recusa**, com mensagem que ensina |

**Antes desta frente, os 95 saíam 5102 / CST 00 / 20%.** Ou seja: **43 produtos (45%) com o ICMS
cobrado duas vezes** e **9 (9%) com um CFOP escolhido sem base** — 52 de 95 errados, 55% do
catálogo. E não era erro de um NCM: era a régua inteira.

### 1.5 O fato é do PRODUTO, não do NCM — medido

- dos **147** `cProd` distintos das notas de entrada, **zero** têm entradas com CST de ICMS
  divergente entre si → o fato é estável por produto;
- **5 NCMs** têm entradas divergentes (`34054000`, `40151900`, `94032090`, **`85365090`**,
  `34052000`) — o mesmo NCM entrando com e sem ST. **NCM não serve de chave.** Note que
  `85365090` é justamente um dos seis da nota do dono.

---

## §2 — O que o DGX tem

`docs/dgx/lacunas/faturamento_financeiro.md` marca «CFOP / natureza → TEMOS». Medido pela frente
Z4: a tabela `cfops` tem **2 linhas**, ambas de serviço (5933/6933). A frente Z4 mediu «51% do que
a praça pratica é ST» e registrou como **decisão nº 1 para o contador**, ligada a CEST/MVA por
NCM — que continuam vazios nas 10.515 linhas de `ncms`. **Esta frente é a ponta solta daquela
medição**, resolvida por outro caminho: não por CEST/MVA (que a casa não tem), mas pelo **CST da
nota de entrada do próprio produto** (que a casa tem, guardado em `nfe_entradas.xml_raw` desde
sempre e nunca lido).

---

## §3 — O que foi feito

### 3.1 Onde o fato mora, e por que ali

**Duas colunas em `fin_produtos`**, o catálogo fiscal que já existe:
`icms_entrada_cst VARCHAR(4)` e `icms_entrada_fonte TEXT`. Três números decidiram:

1. `fin_produtos.codigo` **é** o `cProd` da nota de entrada (as 95 linhas nasceram de lá, por
   `produto_fiscal.semear`). Casamento medido: **95 de 95**. Tabela de ligação seria peso morto.
2. O fato é 1:1 com o produto e estável (0 de 147 divergem) — tabela própria não se justifica.
3. Derivar na hora foi descartado: `calcular_puro` é **puro e sem I/O** de propósito, e é o que o
   emissor chama **por item**; reler 51 XMLs por item seria trocar um defeito fiscal por um de
   desempenho.

A coluna fica ao lado do `cest` e do `origem`, que já vinham do **mesmo XML**, lidos pela **mesma
função** (`produto_fiscal._itens_do_xml`, estendida em 10 linhas para também devolver o CST de
ICMS e o CFOP do item). Reuso, não duplicação.

### 3.2 Arquivos

| Arquivo | O quê |
|---|---|
| `backend/modules/fiscal/services/icms_entrada.py` (**novo**, 250 linhas) | o FATO: DDL idempotente das 2 colunas, `sincronizar()` (lê os XMLs de entrada e preenche só o que está NULL), `do_produto()`, `enriquecer_itens()` (cola o fato nos itens da nota, **a partir do catálogo**), `registrar()` (a porta do humano, com fonte obrigatória), `resumo()` |
| `backend/modules/fiscal/services/tributacao_nfe.py` (**alterado**) | a RÉGUA: `classificar_entrada()` + o bloco «COMO A MERCADORIA ENTROU»; `calcular_puro` passa a depender de `produto["icms_entrada_cst"]` |
| `backend/modules/financial/services/produto_fiscal.py` (**+10 linhas**) | `_itens_do_xml` devolve também `icms_cst` e `cfop` do item — a leitura que já existia, ampliada |
| `backend/modules/fiscal_contabil/notas_fiscais/nfe/emissor.py` (**+8 linhas**) | `emitir()` chama `enriquecer_itens` ANTES da régua; `_tributar` repassa o fato |
| `backend/modules/financial/integrations/nfe_provider.py` (**+6 linhas**) | correção do total de IBS/CBS (§3.6) |
| `backend/modules/operacional/controllers/redesign_builders/_dgx_aa5_icms_st.py` (**novo**) | as 2 telas + a ação. Sem régua própria. |
| `backend/modules/operacional/controllers/redesign_builders/fiscal.py` (**+6 linhas**) | plug `# dgx aa5` |
| `backend/modules/operacional/controllers/redesign_builders/_dgx_z4_tributacao.py` (**alterado**) | o mapa ganha a coluna «Como a mercadoria entrou» (20 → 40 linhas) e o simulador ganha o campo |
| `backend/scripts/orq/test_oraculo_z4_tributacao_nfe.py` (**+2 linhas**) | o produto de teste declara que entrou tributado |
| `backend/scripts/orq/test_oraculo_aa5_icms_st.py` (**novo**) | o oráculo desta frente |

### 3.3 A regra, com norma em cada número

| Situação | CFOP | CST / CSOSN | ICMS | Norma |
|---|---|---|---|---|
| Entrou com ST · venda **interna** no AM · revenda · lucro real | **5405** | **60** | **zero**, BC zero | CFOP: Convênio SINIEF s/nº de 15/12/1970, Anexo (5405 = venda de mercadoria adquirida de terceiros, sujeita a ST, na condição de **contribuinte substituído**) · CST: MOC NF-e 4.00, grupo N, Tabela B |
| Entrou com ST · venda interna · revenda · **Simples** | **5405** | **CSOSN 500** | zero | Ajuste SINIEF 07/2005, Anexo, Tabela B |
| Entrou tributada (CST 00 / CSOSN 101-103) | 5102 / 6102 / … | 00 | 20% interno AM | como antes (régua Z4, inalterada) |
| Entrou com ST · **interestadual** ou **produção própria** | **—** | — | — | **recusa, «sem fonte»** (§3.5) |
| **Não se sabe como entrou** | **—** | — | — | **recusa que ensina** (§3.4) |

O que classifica como «entrou com ST»: CST **10, 30, 60, 70** e CSOSN **201, 202, 203, 500** —
todos os casos da Tabela B em que o ICMS foi retido antes. Como «entrou tributada»: CST **00** e
CSOSN **101, 102, 103**.

`classificar_entrada` aceita as duas grafias: a DANFE imprime **`060`** (origem + CST) e o XML traz
`0` e `60` separados. O CSOSN de 3 dígitos de verdade (`400`, `500`, …) é testado **antes** de
desmontar, senão «CSOSN 400» viraria «CST 00» — foi um defeito real, pego pelo autoteste.

### 3.4 A recusa que ensina (a regra nº 2 do briefing)

Produto sem entrada conhecida **não sai com CFOP chutado**. A régua devolve `cfop = None`,
`cst_ou_csosn = None`, `aliquota = None` e um bloqueio que o emissor transforma em recusa:

> Item 1: a régua fiscal recusou — **Não sei como esta mercadoria entrou** — produto
> «AA5-SEM-ENTRADA». Sem o CST de ICMS da NF-e de ENTRADA não dá para saber se o ICMS já foi
> retido por substituição tributária — e aí a saída é CFOP 5405 / CST 060 com ICMS ZERO, como saiu
> a nossa própria NF-e nº 10.026 — ou se é tributação normal, CFOP 5102 / CST 00 a 20%. Metade do
> que a casa compra entra com ICMS-ST (106 de 209 itens medidos), então chutar erra quase uma vez
> em duas. Registre a entrada em Fiscal → Notas fiscais → «Como a mercadoria entrou (ICMS-ST)», ou
> importe a NF-e de entrada do fornecedor. **Emitir com o CFOP errado é pior do que não emitir.**

E a porta existe: a tela **«Registrar como a mercadoria entrou»** grava o CST com a **fonte
obrigatória**, mais quem registrou e quando. Provado por HTTP:

```
CST 20 («redução de base»)      → 400 «CST/CSOSN «20» não tem tratamento de saída com fonte neste
                                      repositório. Com fonte estão 10, 201, 202, 203, 30, 500, 60,
                                      70 … e 00, 101, 102, 103 … não invente aqui.»
fonte vazia                     → 400 «Informe o produto, o CST/CSOSN de ICMS da entrada e a fonte
                                      (o documento que prova).»
CST 60 + fonte                  → 200 · gravado:
   «NF-e de saida no 10.026 serie 1, protocolo 113263811849419 — registrado por
    jjesus@conectamais.pro em 24/09/2026 21:28»
```

**O fato nunca vem do payload da emissão** — só do catálogo. Se viesse do payload, qualquer
chamada poderia declarar «entrou com ST» e ganhar ICMS zero sem documento nenhum por trás.

### 3.5 Os outros CST da entrada (a regra nº 3 do briefing)

| CST/CSOSN na entrada | Itens | Produtos | Tratamento de saída |
|---|---|---|---|
| **60** (ICMS cobrado antes por ST) | 97 | 37 | **5405 / 060 / zero** — com fonte (NF-e 10.026 + tabela de CFOP + Tabela B) |
| **500** (idem, Simples) | 9 | 6 | **5405 / CSOSN 500 / zero** — com fonte (Ajuste SINIEF 07/2005) |
| **00** (tributada integralmente) | 73 | 32 | 5102 / 00 / 20% — como antes |
| **102** (Simples, sem ST) | 13 | 11 | 5102 / CSOSN 102 — como antes |
| **20** (redução de base) | 5 | 3 | **«sem fonte» → decisão humana.** A redução vem de habilitação específica na SEFAZ-AM (Lei AM 2.826/2003, Lei AM 3.830/2012, Conv. 52/91) que a empresa pode não ter — copiar a do fornecedor seria inventar benefício alheio |
| **50** (suspensão) | 5 | 2 | **«sem fonte» → decisão humana.** Suspensão é da operação do fornecedor, não do produto |
| **41** (não tributada) | 4 | 1 | **«sem fonte» → decisão humana** |
| **CSOSN 400** (não tributada pelo Simples) | 1 | 1 | **«sem fonte» → decisão humana** |
| sem grupo de ICMS no XML | 2 | 2 (EPI-001, EPI-002) | **«sem fonte» → decisão humana** |

**Quatro com fonte, cinco declarados.** O CST **53** (diferimento) que o briefing cita **não
existe no ICMS das notas de entrada** — é CST de **IPI** (§1.4).

**Saída ST interestadual** também ficou declarada «sem fonte»: existe o CFOP 6404, mas o
tratamento do ICMS (ressarcimento ao estado de origem, Convênio ICMS 142/2018) não está no
repositório, e a empresa vende só em Manaus. A recusa nomeia o caso:

> A mercadoria entrou com ICMS já retido por ST (CST/CSOSN 60 na nota de entrada), mas esta
> operação — venda para outro estado, a contribuinte, revenda — não tem tratamento com fonte neste
> repositório. Só a venda INTERNA do Amazonas, em revenda, está provada (CFOP 5405 / CST 060 /
> ICMS zero — NF-e 10.026 série 1). … sem fonte — decisão do contador

### 3.6 Um defeito do emissor que só aparece com mais de um item

A primeira tentativa de emitir os seis itens voltou da SEFAZ-AM com
**`1080 · Rejeicao: Total de IBS UF difere da soma dos itens`**.

Causa: `nfe_provider.injetar_ibscbs()` escrevia **o valor arredondado em cada item** e somava
**o valor não arredondado** para o total. Com os seis itens da nota: a soma dos itens dá **2,53**
e o total saía **2,52**. Com nota de um item só — o único caso já testado — a diferença nunca
aparecia. Corrigido acumulando o valor já arredondado (é o que o MOC manda: o total é a **soma dos
valores dos itens**). Seis linhas, com o número medido no comentário. **Achado desta frente num
arquivo da Z2; a Z2 continua verde** (`TOTAL desvios: 0`).

### 3.7 DDL que `_ensure` aplica em produção no 1º acesso

```sql
ALTER TABLE fin_produtos ADD COLUMN IF NOT EXISTS icms_entrada_cst VARCHAR(4);
ALTER TABLE fin_produtos ADD COLUMN IF NOT EXISTS icms_entrada_fonte TEXT;
```

Mais o `sincronizar()`, que só faz `UPDATE … WHERE icms_entrada_cst IS NULL` — **nunca sobrescreve
o que uma pessoa registrou**. Nenhum DROP, nenhum DELETE, nenhuma tabela nova.

### 3.8 Telas (deep-link `/redesign/fiscal?t=<id>`, grupo «Notas fiscais»)

| id | Tela | Medido |
|---|---|---|
| `nfe-icms-entrada` | **Como a mercadoria entrou (ICMS-ST)** — os 95 produtos com o CST da entrada, o balde, como sai e a **fonte** | 95 linhas |
| `nfe-icms-entrada-registro` | **Registrar como a mercadoria entrou** — a porta do humano, fonte obrigatória | 3 campos |
| `nfe-tributacao-mapa` (Z4, ampliada) | ganhou a coluna «Como a mercadoria entrou» e o filtro | **20 → 40 linhas** |
| `nfe-tributacao-simulador` (Z4, ampliada) | ganhou o campo «Como a mercadoria ENTROU» | 9 → 10 campos |

Ação: `POST /api/v1/redesign/action/nfe-icms-entrada-registrar` (gate `module:fiscal`).

---

## §4 — A nota do dono, reproduzida e emitida em homologação

### 4.1 Pelo caminho do emissor, item a item (antes de ir à SEFAZ)

```
PRODUTO                            NCM       CFOP  CST        BC     ICMS      %
CABO LAN CAT5E 305M 100% COBRE     85444900  5405  60       0.00     0.00   0.00
CENTRAL FONTE SUSPENSA INTELBRAS   85044021  5405  60       0.00     0.00   0.00
BOTOEIRA PORTA                     85365090  5405  60       0.00     0.00   0.00
FECHADURA ELETRONICA PAPAIZ        83014000  5405  60       0.00     0.00   0.00
CONECTOR POWER BALUN               85369090  5405  60       0.00     0.00   0.00
CANALETA 10X10 COM FITA            39162000  5405  60       0.00     0.00   0.00
TOTAL DOS PRODUTOS: R$ 2518.00 · ICMS TOTAL: R$ 0.00
MENSAGEM FISCAL: Mercadoria com ICMS retido anteriormente por substituição tributária — CST 060,
sem novo destaque de ICMS nesta operação (MOC NF-e 4.00, grupo N, Tabela B — CST 60 …)
RECUSA (esperada): Item 1: a régua fiscal recusou — Não sei como esta mercadoria entrou —
produto «AA5-SEM-ENTRADA». …
```

### 4.2 Emitida em HOMOLOGAÇÃO e **AUTORIZADA**

`POST /api/v1/fiscal/nfe/emitir` na porta 8295, com os seis itens reais:

| | |
|---|---|
| **cStat** | **100** |
| **xMotivo** | **Autorizado o uso da NF-e** |
| **Protocolo** | **113260013553934** |
| **Chave** | **13260935710481000103550010000000131478016892** |
| tpAmb | **2 — homologação** |
| Número / série | 13 / 1 |
| XML guardado | `/app/uploads/nfe/35710481000103/2609/…-proc.xml` |

### 4.3 O XML autorizado × a DANFE do dono, item a item

```
ITEM                            NCM       CFOP  CST        BC    ICMS      %    vProd  == DANFE?
NOTA FISCAL EMITIDA EM AMBIENTE 85444900  5405  060      0.00    0.00   0.00   895.00  IGUAL
CENTRAL FONTE SUSPENSA INTELBRA 85044021  5405  060      0.00    0.00   0.00   365.00  IGUAL
BOTOEIRA PORTA                  85365090  5405  060      0.00    0.00   0.00   180.00  IGUAL
FECHADURA ELETRONICA PAPAIZ     83014000  5405  060      0.00    0.00   0.00   778.00  IGUAL
CONECTOR POWER BALUN            85369090  5405  060      0.00    0.00   0.00   210.00  IGUAL
CANALETA 10X10 COM FITA         39162000  5405  060      0.00    0.00   0.00    90.00  IGUAL
TOTAIS  vBC=0.00  vICMS=0.00  vProd=2518.00  vNF=2518.00
DANFE   vBC=0,00  vICMS=0,00  vProd=2518,00  vNF=2518,00
SEIS ITENS IGUAIS À DANFE 10.026: True
```

(A descrição do item 1 é substituída pelo texto obrigatório de homologação da SEFAZ — regra do
ambiente, não divergência.)

**Duas divergências que sobram, e que são do contador, não do código:**

1. **PIS/COFINS.** A nota real traz **vPIS 0,00 / vCOFINS 0,00**; a nossa traz **41,56 / 191,37**
   (1,65% e 7,60%, CST 01, regime não-cumulativo — Lei 10.637/2002 art. 2º e Lei 10.833/2003 art.
   2º, a régua da Z4, medida em 39 itens de fornecedores CRT=3). **Não mexi.** A ST do ICMS não
   zera PIS/COFINS; produto monofásico zeraria, mas não há fonte no repositório dizendo que estes
   seis são. Vai para o §7.
2. **Natureza da operação.** A nota real diz *«Venda de mercadoria, adquirida ou recebida de
   terceiros, sujeita a ST»*; a nossa diz *«VENDA DE MERCADORIA»*, porque é texto livre com
   default no schema do endpoint. Não afeta tributo. Ver §5.

---

## §5 — Oráculo

`backend/scripts/orq/test_oraculo_aa5_icms_st.py` — afirma (a) os seis itens da NF-e 10.026 item a
item contra a DANFE, somando os R$ 2.518,00 · (b) nenhum produto do catálogo que entrou com ST sai
com ICMS cobrado, varrendo `fin_produtos` inteiro · (c) produto sem entrada conhecida não sai com
CFOP chutado, e a recusa nomeia o produto e mostra as duas saídas possíveis · (d) recontagem dos
itens de entrada por **parser próprio**, restrito ao grupo `det/imposto/ICMS` · (e) as duas colunas
existem, todo CST gravado tem fonte escrita, e a tela mostra exatamente o que o banco tem.

```bash
WT=$(git rev-parse --show-toplevel)
ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\n' ' ')
docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" \
  -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env \
  -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \
  conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_aa5_icms_st.py
```

**VERMELHO** (código de antes da frente, `3e3158af9`, com o mesmo oráculo):

```
itens de NF-e de entrada relidos: 209 · com ICMS já retido por ST: 106
catálogo fiscal: 95 produtos — 0 com ST · 0 tributados · 95 sem fonte
sincronização do fato: {'(serviço ausente)': 0}
NF-e 10.026 conferida item a item: 6 itens, R$ 2518.00
FALHOU: serviço do fato «como a mercadoria entrou» não existe: cannot import name 'icms_entrada'…
FALHOU: a régua não sabe classificar como a mercadoria entrou … — ela decide o CFOP de saída sem
        olhar a entrada
FALHOU: NF 10.026 «CABO LAN CAT5E 305M 100% COB» (NCM 85444900): CFOP '5102', a nota real diz 5405
FALHOU: NF 10.026 «CABO LAN CAT5E 305M 100% COB»: CST '00', a nota real diz 060
FALHOU: NF 10.026 «CABO LAN CAT5E 305M 100% COB»: V.ICMS 179.0, a nota real diz 0,00
FALHOU: NF 10.026 «CABO LAN CAT5E 305M 100% COB»: BC ICMS 895.0, a nota real diz 0,00
FALHOU: NF 10.026 «CABO LAN CAT5E 305M 100% COB»: %ICMS 20.0, a nota real diz 0,00
… (os seis itens, cinco desvios cada; e 95 «produto X … a régua escolheu CFOP 5102 — isso é chute»)
FALHOU: tela «Como a mercadoria entrou (ICMS-ST)» não existe
TOTAL desvios AA5: 133
```

**VERDE** (depois):

```
itens de NF-e de entrada relidos: 209 · com ICMS já retido por ST: 106
catálogo fiscal: 95 produtos — 43 com ST · 43 tributados · 9 sem fonte
sincronização do fato: {'itens_com_cst_no_xml': 145, 'produtos_preenchidos': 0}
products (Bling): 867 — 857 sem nenhuma NF-e de entrada nossa
NF-e 10.026 conferida item a item: 6 itens, R$ 2518.00
OK ICMS-ST na saída: os 6 itens da NF-e 10.026 saem 5405/060/ICMS zero; nenhum produto que entrou
com ST é tributado de novo; produto sem entrada conhecida é recusado com mensagem que ensina; a
recontagem dos itens de entrada bate.
TOTAL desvios AA5: 0
```

O oráculo **não estoura no import** quando o serviço não existe: ele registra a falha e continua,
de propósito — um oráculo que só levanta `ImportError` não diz **qual número** está errado, e era
o número que precisava aparecer.

### Oráculos vizinhos, depois da mudança

| Oráculo | Resultado |
|---|---|
| `test_oraculo_aa5_icms_st.py` | **TOTAL desvios AA5: 0** |
| `test_oraculo_z4_tributacao_nfe.py` | **0** — «toda combinação com CFOP e CST/CSOSN ou «sem fonte» declarado…» |
| `test_oraculo_z2_emissor_nfe.py` | **TOTAL desvios: 0** (inclui a emissão real em homologação) |
| `test_oraculo_z1_produto_fiscal.py` | **0** |
| `test_oraculo_z5_orcamento_nota.py` | **0** |
| `python3 -m modules.fiscal.services.tributacao_nfe` (autoteste sem banco) | `demo tributacao_nfe: OK — 16 blocos, 30 combinações` |

**Fixtures:** 7 produtos `'FIXTURE DGX AA5'` criados no sandbox para o teste de emissão e
**apagados ao fim** (`DELETE 7`; a contagem no banco é 0, e o item final do oráculo varre isso).

---

## §6 — Como o Jordan testa amanhã

1. **Fiscal → Notas fiscais → «Como a mercadoria entrou (ICMS-ST)».** 95 linhas. Filtrar por
   *«ICMS já retido por ST…»*: **43 produtos**. Cada um mostra a **nota de entrada** que prova o
   fato, na coluna Fonte.
2. Filtrar por *«não se sabe como entrou»*: **9 produtos**. São os que a régua recusa. Um deles é
   `EPI-002 — CAPACETE DE SEGURANCA BRANCO`, o mesmo que a frente Z1 já tinha deixado inativo por
   NCM inexistente.
3. **Notas fiscais → Simulador de tributação da NF-e.** Empresa *Conecta Mais Eletrônica*,
   revenda, NCM `85444900`, valor `895`, quantidade `1`, UF `AM`, contribuinte `Não`, e no campo
   novo **«Como a mercadoria ENTROU» = «60 — ICMS já retido por ST»** → esperado **CFOP 5405 ·
   CST 060 · alíquota — · ICMS R$ 0,00**. É a primeira linha da nota 10.026.
4. **O teste que importa:** repetir deixando o campo em **«Não sei»**. Tem de **recusar**, com a
   mensagem do §3.4. Se sair 5102/20%, a frente falhou.
5. **Notas fiscais → Mapa da tributação (NF-e).** Agora 40 linhas. Filtrar «Como entrou» =
   *Entrou com ICMS-ST retido*: as 20 linhas mostram 5405/060 nas internas e **bloqueada** nas
   interestaduais — é o «sem fonte» declarado, não esquecimento.
6. **Registrar um produto:** Notas fiscais → «Registrar como a mercadoria entrou». Tentar CST
   `20` → recusa explicando. Tentar sem fonte → recusa. Com CST `60` + fonte → grava, e o produto
   sai da lista dos 9.
7. Mandar o **§1 e o §3.5 deste relatório ao contador** antes da primeira nota em produção.

---

## §7 — Decisões que só o dono (e o contador) podem tomar

| # | Decisão | Por quê agora | Custo de errar |
|---|---|---|---|
| **1** | **Os 857 itens de `products` sem tratamento.** `products` (catálogo do Bling) tem **867** linhas; só **10** casam por código com um produto do catálogo fiscal. **857 não têm nenhuma NF-e de entrada nossa** e, hoje, **não podem sair numa NF-e**. Outros **41** casariam por NCM — e eu **não** usei isso, porque 5 NCMs da casa têm entradas divergentes (§1.5); casar por NCM seria chute com outro nome. Caminhos: (a) importar as NF-e de entrada que faltam (o `nfe_entrada_sync_service` já sabe); (b) registrar produto a produto na tela nova; (c) unificar `products` e `fin_produtos` — que é a frente AA1. **Qual?** | é o número que mede quanto do catálogo real está emissível | não emitir (chato) ou emitir errado (multa) |
| **2** | **Os 9 produtos com CST 20/41/50/CSOSN 400 na entrada.** Redução de base, não tributada, suspensão. Cada um depende de **habilitação da empresa** na SEFAZ-AM (Lei AM 2.826/2003, Lei AM 3.830/2012, Conv. 52/91). Copiar o benefício do fornecedor seria usar incentivo alheio. **A empresa tem alguma dessas habilitações?** | são 9 produtos que hoje não emitem | usar benefício que não se tem = glosa + multa |
| **3** | 🚨 **Numeração de produção: a NF-e real da Eletrônica está no nº 10.026, série 1.** O contador do sistema nasce em 1 — a SEFAZ **rejeita 539 (duplicidade)** na primeira nota real. Antes de ligar produção é preciso gravar `nfe_numeracao` (`tp_amb='1'`, série 1) com **último ≥ 10.026**. Isso já era a decisão nº 3 do §7 da Z2; agora tem **o número**. | é bloqueio duro para a primeira nota real | toda emissão em produção rejeitada |
| **4** | **PIS/COFINS na nota de mercadoria.** A nota real do emissor de terceiro traz **zero**; a nossa traz 1,65% / 7,60% (lucro real, não-cumulativo, com norma). Ou o nfemais omite, ou estes produtos são **monofásicos** (Lei 10.485/2002 e afins) — **não há fonte no repositório** para decidir. **Confirmar com o contador.** | aparece em toda nota de mercadoria | PIS/COFINS a maior (ou a menor) em 100% das notas |
| **5** | **Saída interestadual de mercadoria já substituída.** Hoje recusada, «sem fonte». Se a empresa for vender fora do AM, é preciso normar ressarcimento e CFOP 6404. | a empresa vende só em Manaus hoje | recolher a menos / perder ressarcimento |
| **6** | **Alíquota interna do AM (20%)** continua sem o artigo do RICMS-AM (é a decisão nº 2 do §7 da Z4). Agora afeta **menos** notas — só as 43 que entraram tributadas —, mas continua de pé. | idem | notas internas erradas |
| **7** | **Natureza da operação.** A nota real diz «Venda de mercadoria, adquirida ou recebida de terceiros, sujeita a ST»; a nossa manda o default «VENDA DE MERCADORIA». Não muda tributo, mas é o que o cliente lê na DANFE. Uma linha: o default sair da designação oficial do CFOP. **Quer?** | cosmético, mas visível ao cliente | nenhum tributo |

---

## §8 — O que NÃO foi feito, e por quê

1. **Não semeei os seis produtos da nota 10.026 em produção.** Eles existem de verdade e a DANFE
   prova o CST, mas o código de produto teria de ser inventado (a DANFE numera os itens 1–6, não
   traz código de catálogo). Entrar no catálogo do dono com chave inventada é o tipo de «ajuda»
   que ninguém consegue desfazer depois. Foram criados **no sandbox**, como fixture marcada, e
   apagados. Em produção isso é o §7-1.
2. **Não usei NCM como chave de busca do fato.** Medido: 5 NCMs com entradas divergentes, e um
   deles (`85365090`) está na nota do dono. Casaria 41 produtos a mais e erraria uma parte deles
   sem avisar.
3. **Não mexi em CEST nem em MVA.** Continuam vazios nas 10.515 linhas de `ncms` (decisão nº 1 do
   §7 da Z4). Esta frente resolveu o mesmo problema por outro dado — o CST da entrada — que a casa
   já tinha. CEST/MVA continuam necessários para o dia em que a empresa for **substituta** (CFOP
   5403), o que hoje não acontece.
4. **Não toquei em NFS-e** (`nfse_emissao.py`, `_dgx_z7_nfse.py`, `nfse_nacional.py`): a frente
   AA4 está lá. Registro para ela: na **NFS-e 121** da Eletrônica (mesmo tomador, mesmo dia) há a
   frase *«NÃO HAVERÁ RETENÇÃO DE PIS E COFINS, CONFORME PROCESSO N° 1038495-94.2024.4.01.3200»* —
   é parâmetro fiscal com fonte (decisão judicial), e é da NFS-e, não da NF-e.
5. **Não mudei PIS/COFINS da NF-e de mercadoria** (§7-4). Mudar sem fonte seria trocar um erro
   medido por um erro chutado.
6. **Não implementei o CFOP 6404** nem o ressarcimento de ST interestadual (§7-5). Declarado.
7. **Não arrumei a natureza da operação** (§7-7). Cosmético, e mexer no schema do endpoint por
   isso não se paga hoje.
8. **Não fiz merge, bake, `docker cp` nem deploy.** Commit na branch e parei, como manda o
   contrato.
9. **Não apaguei as linhas 11 e 12 de `nfes` no sandbox** (as duas tentativas que falharam antes
   do fix do IBS). É o desenho da Z2: número reservado antes da SEFAZ nunca volta atrás, e a linha
   fica gravada com o motivo, senão vira buraco invisível na numeração.

---

## §9 — Nota de ambiente para o orquestrador

Durante o teste HTTP o sandbox ficou **21 minutos travado**: uma sessão `idle in transaction`
segurando `nfe_eventos` bloqueava um `ALTER TABLE nfes` do `_ensure` do emissor, que bloqueava
todo o resto — inclusive frentes vizinhas. Depois, sessões da frente de NFS-e (`nfse_manaus_historico`,
`periodo_competencia`) bloquearam `ALTER TABLE empresas` por mais alguns minutos. **Causa
estrutural:** vários `_ensure` com DDL disparando ao mesmo tempo, de agentes diferentes, no mesmo
banco. Não é defeito de nenhuma frente; é a onda inteira contra um sandbox só. Se o bake ficar
lento hoje, é isto. Diagnóstico rápido:

```sql
SELECT pid, pg_blocking_pids(pid), state, left(query,60) FROM pg_stat_activity
WHERE cardinality(pg_blocking_pids(pid)) > 0;
```

**Containers desta frente:** `teste-dgx-aa5` (porta 8295) — **removido**. Nenhum container meu em
execução.
