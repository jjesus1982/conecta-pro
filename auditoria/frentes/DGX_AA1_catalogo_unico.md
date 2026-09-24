# DGX AA1 — Catálogo único: a compra vira produto, sem preço e sem fusão no escuro

**Onda 9 · 24/09/2026 · branch `dgx/aa1-catalogo-unico` · módulo `financeiro` (telas em Suprimentos)**

**Pedido do dono:** *«baseado nas notas fiscais de compra da Conecta Eletrônica cadastrar os
produtos, ter cuidado com duplicidades, pois aí na hora de fazer o orçamento fazemos pelo CRM, já
estará lá com toda a descrição, só seleciona o item e as quantidades, e se aprovado a gente marca
lá, porque se foi aprovado vai gerar nota fiscal.»*
E, no mesmo dia, a regra que **cancela** qualquer preço automático: *«nos produtos cadastrados
deixem sem valor, quando eu for fazer os orçamentos eu edito o preço, porque os preços variam
muito, tem muitas constantes, então quando eu orçar pego o preço do dia e edito na hora.»*

---

## §1 — Estado antes (medido no sandbox, cópia de produção de 23/09)

| Fato | Número |
|---|---|
| `products` (catálogo comercial, importado do Bling em 27/08) | **867** linhas · 193 com NCM · **0 com `cfop_out`** |
| Colunas de preço de `products` preenchidas | **0 em 867**, nas seis (`reference_price`, `last_purchase_price`, `average_price`, `min_price`, `max_price`, `price_history` = `[]`) |
| `crm_products` (preço praticado, semeado de 33 propostas) | 115 |
| `fin_produtos` (cadastro fiscal da Z1) | **95** — **um por NCM distinto** das compras, não um por produto |
| `nfe_compras_estoque` (a fonte da compra) | **147** itens, 95 NCMs distintos |
| `proposal_items` (o destino) | 177 |
| Elo entre o catálogo comercial e o fiscal | **não existia** — `fin_produtos.product_id` não era coluna |
| «casam» por `code` = `codigo` | 10 pares — **e 8 deles são produtos diferentes** (ver §2) |

---

## §2 — A decisão da fonte única, e o número que a sustenta

### `products` é o catálogo. `fin_produtos` é a face fiscal dele. O elo é UMA coluna.

**O número que decide:** `modules/crm/services/catalogo.py` — o catálogo que o orçamento do CRM
**já** lê — faz `UNION` de `crm_products` (115, com preço praticado) com **`products`** (867, com
NCM/CEST/unidade). Quem entra em `products` aparece no orçamento **sem mais uma linha de código**.
`fin_produtos` não é candidato a catálogo: **as 10 botas em 10 tamanhos são UMA linha lá**, porque
a Z1 semeou um registro por NCM distinto, e um catálogo de orçamento precisa do produto, não do
NCM. Logo: a terceira tabela não nasce — nasce a coluna `fin_produtos.product_id`.

Direção do elo: o filho aponta para o pai. `fin_produtos` (95) é a face de `products` (867), tem
`UNIQUE(codigo)` e cobre 11 % do catálogo; pôr a coluna no lado grande para servir o pequeno seria
ao contrário. Índice único parcial garante um comercial ↔ no máximo um fiscal.

### O elo **não** é o código — medido, e é o achado que reorienta a frente

Das **16** linhas de compra cujo `item_code` existe como `products.code`, **9 são produtos
diferentes**:

| Código | O que a nota de compra diz | O que o catálogo do Bling diz |
|---|---|---|
| 297 | ENXADA LARGA 30CM OK!BRASIL | Desempeno das portas |
| 9 | AREIA EM SACO | Controle remoto xac 4000 smart |
| 45 | COLHER PEDREIRO N10 TRAMONTINA | DVR 16 portas |
| 33 | VALVULA 414 - 414RC | Central de choque JFL ERC18-PLUS |
| 138 | PEDRA BRITA SACO COM 1 LATA | Câmera 1120 B |
| 140 | CABO PARA ENXADA | Coroa central da cancela |
| 166 | LUSTRA MOVEIS 200ML BUTTERFLY | Câmera 3220 mini D |
| 118 / 119 | REAGENTE A PH / B CLORO — MARAITT | Placa 16 ramais / Placa tronco-ramal |

Só os códigos que carregam o espaço do fornecedor (`VTV-*`) são verdadeiros — 7 de 7.
**Conclusão gravada no código:** o código é **evidência, nunca prova**. Sozinho ele não funde nada;
com descrição concordando ≥ 0,30 ele casa; colidindo ele vira aviso escrito na linha.

### Quando `products.ncm` e a nota divergem, quem vence

**A nota de entrada vence como PROPOSTA; o catálogo nunca é sobrescrito em silêncio.**
Fundamento: o NCM da nota foi declarado pelo fornecedor num documento que já produziu efeito
fiscal; a classificação do Bling é **medidamente falível** — o docstring da Z1 registra «Placa de
motor portão» classificada como 8704.60.00 («veículos para transporte de mercadorias»).
Mas NCM errado é multa e glosa de crédito, então a regra implementada é:

- produto **novo** nasce com o NCM da nota — **só se ele existir na nomenclatura vigente** (`ncms`,
  10.515 códigos); se não existir, nasce **sem NCM** e a linha diz por quê (é o caso do `65119000`,
  «CAPACETE DE SEGURANCA BRANCO», que a Z1 já tinha provado errado);
- produto **já existente** com NCM vazio → é **enriquecido** com o da nota;
- produto **já existente** com NCM diferente → **nada é sobrescrito**; a divergência é devolvida
  na mensagem da ação e fica para uma pessoa decidir.

Divergência real medida na aprovação: **VTV-119 «SMART FITA LED WI-FI RGB» — a nota diz `94054900`
(luminárias, cap. 94), o catálogo diz `85395200` (lâmpadas LED, cap. 85).** Não foi escolhido por
mim: está no §7, é decisão do dono/contador.

---

## §3 — O que foi feito

### Arquivos

| Arquivo | O quê |
|---|---|
| `backend/modules/financial/services/catalogo_compra.py` **(novo)** | A regra: DDL, régua de agrupamento, classificação, aprovação, elo fiscal |
| `backend/modules/operacional/controllers/redesign_builders/_dgx_aa1_catalogo.py` **(novo)** | 3 telas + 4 ações |
| `backend/modules/operacional/controllers/redesign_builders/suprimentos.py` | +13 linhas: `router`, `EXTRA_MENU`, `telas(db, out)` |
| `backend/scripts/orq/test_oraculo_aa1_catalogo.py` **(novo)** | Oráculo (8 blocos, a→h) |

### DDL que `_ensure` aplica em produção no 1º acesso (idempotente, nada de alembic)

- `fin_catalogo_candidatos` — `item_code` (único), `descricao`, `ncm`, `unidade`,
  **`custo_unitario`** (o custo da nota; *nunca* preço de venda), `classe`, `score`, `motivo`,
  `alvo_product_id`, `alvo_item_code`, `traco`, `status`, `product_id`, `decidido_por`,
  `decidido_em`, `criado_em` + índice `(status, classe)`.
- `ALTER TABLE IF EXISTS fin_produtos ADD COLUMN IF NOT EXISTS product_id UUID` + índice único
  parcial `ux_fin_produtos_product`. (`IF EXISTS` porque a tabela é da Z1 e a ordem de merge não é
  garantida — se a Z1 não estiver aplicada, a AA1 sobe igual e o elo nasce depois.)

**Nenhuma coluna de preço é criada, lida para escrita, ou escrita.**

### A régua de agrupamento — o que ela afirma e o que ela recusa

Reusa `_toks` / `_sim` / `_CORTE_FORTE = 0,80` de `produto_fiscal.py` (o corte foi medido lá: em
0,70 «Cabo de rede 4PX0,5 bobina 300MT» casou com «TESTADOR DE CABO DE REDE»). Em cima disso,
duas coisas medidas **nesta** frente:

1. **Dígito solitário conta.** `_toks` descarta token de 1 caractere, e isso fundia produto:
   «BUCHA NYLON S- **6** C/ ABA» saía com semelhança **1,00** contra «Bucha nylon S- **8** c/ aba».
   São bitolas diferentes. Guardar o dígito derruba para 0,75 e a fusão não acontece
   (`_toks_cat`).
2. **Sobra de um lado ≠ sobra dos dois.** Quando o que difere sobra **só de um lado**, a nota é
   mais detalhada que o catálogo (ou o contrário) — pode fundir. Quando sobra **dos dois**, cada
   descrição nega a outra — não funde. Medido: «LIMPADOR PERF **AMEIXA** DOURADA 120ML COALA» ×
   «LIMPADOR PERF **ROMA** 120ML COALA» tem semelhança 0,80 e uma cor no meio, mas sobra AMEIXA de
   um lado e ROMA do outro: **dois perfumes, dois produtos**. Já as 10 botas sobram só «USAFE» de
   um lado — a marca escrita de dois jeitos.

Ordem: **descrição limpa → código do fornecedor → novo**. `novo` é o **padrão seguro**: fundir é o
ato perigoso, então exige sinal limpo; o parecido fica gravado em `alvo_product_id` e a tela
oferece o botão «é este produto» — é assim que o humano confirma o que a régua não soube, sem ter
de duplicar para corrigir.

### O resultado nas 147 linhas reais

| Classe | Quantas | O que a aprovação faz |
|---|---|---|
| **novo** | **125** | cria a linha em `products` (código, descrição, unidade, NCM). **Zero preço.** |
| **igual** | **12** | não cria nada; enriquece o NCM **só se estiver vazio**; grava o elo |
| **variação** | **10** | não cria nada; a linha fica ligada ao produto-pai (o tamanho continua na grade `sst_uniforme_grade`, da frente 10) |

As 10 botas (NCM 64039190) deram **1 representante + 9 variações** (traço N36…N45).
Os 9 itens de NCM 34025000 (detergente, lava-roupas, limpa-vidros, multiuso, sabão em pó de três
marcas) deram **9 candidatos distintos, 0 variação**. As 9 colisões de código saíram **`novo` com
o aviso escrito na linha**, nenhuma como `igual`.

### Telas — grupo «Materiais & estoque» do Suprimentos · `/redesign/suprimentos?t=<id>`

| id | O que mostra |
|---|---|
| `catalogo-candidatos` | as 147 linhas da proposta, com classe, semelhança, NCM, unidade, **custo da nota** (rotulado como custo) e **o porquê por extenso**; por linha: Aprovar · Descartar · «É este produto» / «É novo mesmo» |
| `catalogo-aprovar-lote` | aprovar todos os pendentes de uma classe (`novo`, `igual`, ou tudo), com confirmação |
| `catalogo-produtos` | o catálogo que nasceu daqui: código, produto, unidade, NCM, item na nota, como entrou, nº de variações, **face fiscal ligada?**, quem aprovou |

A proposta **nasce sozinha** no primeiro acesso e se refaz quando chega nota nova
(`classificar_se_houver_novidade`, comparação de contagem — 147×867 conjuntos é caro demais para
rodar a cada abertura). Nada decidido por gente é reclassificado.

### O que as frentes irmãs consomem

**`products`** — código, descrição, unidade, NCM. Sem preço. A AA2 (item do orçamento vindo do
catálogo) já tem o caminho pronto: `crm/services/catalogo.py` lê `products`. A AA3 (o item carregar
o `produto_id` até a nota) tem o elo fiscal em `fin_produtos.product_id`.

---

## §4 — Oráculo

`backend/scripts/orq/test_oraculo_aa1_catalogo.py` — 8 blocos: (a) preço: nada · (b) NCM só o que
existe na nomenclatura · (c) nenhuma fusão sem quem/quando · (d) elo íntegro dos dois lados ·
(e) a régua separa variação de produto distinto **nas duas direções** · (f) código não casa sozinho
· (g) fiação · (h) o caminho de aprovação funciona e recusa quando tem de recusar.

```bash
WT=/opt/conecta-pro/.claude/worktrees/agent-aa1
ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\n' ' ')
docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" -e PYTHONPATH=/app \
  --env-file /opt/conecta-pro/.env -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \
  conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_aa1_catalogo.py
```

### Vermelho 1 — a frente não existe (serviço substituído por arquivo vazio, tabelas derrubadas)

```
  File "/app/scripts/orq/test_oraculo_aa1_catalogo.py", line 95, in main
    await cc._ensure(db)
AttributeError: module 'modules.financial.services.catalogo_compra' has no attribute '_ensure'
```

### Vermelho 2 — a frente a meio caminho, com a régua ainda frouxa (o vermelho útil)

```
147 linha(s) de nota de compra classificadas · novo: 119 · igual: 15 · variação: 13 · catálogo
`products`: 867 produto(s) · face fiscal `fin_produtos`: 95, com elo: 0 · botas NCM 64039190:
{'novo': 1, 'variacao': 9} · itens NCM 34025000 tratados como variação: 1 (tem de ser 0)
FALHOU: (a) o catálogo tem 867 linha(s) com preço — eram 0 em 24/09/2026; se foi o dono, esta
        trava muda; se foi código, é o defeito que ela existe para pegar
FALHOU: (e) 1 dos 9 itens de NCM 34025000 viraram variação um do outro — detergente, lava-roupas
        e sabão em pó são produtos DIFERENTES com o mesmo NCM
FALHOU: (g) suprimentos.py não importa o router nem chama telas() da AA1 — tela sem porta
FALHOU: (h) o produto criado pela fixture nasceu com preço
TOTAL desvios: 4
4 desvio(s) no catálogo único
```

Esse vermelho pegou três defeitos reais: a régua fundindo «LIMPADOR PERF AMEIXA» com «LIMPADOR
PERF ROMA», a fiação ausente, e o próprio SQL do bloco (a) — `price_history` é `'[]'`, não `NULL`,
e a trava estava acusando as 867 linhas limpas. (A régua frouxa também fundia «BUCHA NYLON S-6»
com «Bucha nylon S-8», que o bloco (e) não cobria e a leitura das linhas pegou.)

### Verde — depois

```
147 linha(s) de nota de compra classificadas · novo: 125 · igual: 12 · variação: 10 · catálogo
`products`: 867 produto(s), 0 com preço (decisão do dono 24/09) · face fiscal `fin_produtos`: 95,
com elo: 0 · botas NCM 64039190: {'novo': 1, 'variacao': 9} · itens NCM 34025000 tratados como
variação: 0 (tem de ser 0)
TOTAL desvios: 0
OK catálogo único: nenhum produto do importador tem preço, nenhum NCM inventado, toda fusão tem
quem/quando/por quê, o elo comercial↔fiscal fecha dos dois lados, as 10 botas viram 1 produto + 9
variações e os 9 produtos de mesmo NCM continuam 9
```

### Provado também por HTTP (container efêmero, porta 8291, parado ao fim)

```
GET /api/v1/redesign/data/suprimentos
  catalogo-candidatos  -> table, 147 linhas, «125 novo(s), 12 já existe(m), 10 variação(ões)»
  catalogo-aprovar-lote-> form
  catalogo-produtos    -> table
  menu: 3 abas no grupo «Materiais & estoque»

POST /action/catalogo-aprovar  ids=<bota: 1 novo + 9 variações>
  {"criados":1,"elos_fiscais":1,"divergencias":[],"total":10}
POST /action/catalogo-aprovar  ids=<VTV-119, classe «igual»>
  {"criados":0,"elos_fiscais":1,
   "divergencias":["VTV-119: nota diz 94054900, catálogo diz 85395200"],"total":1}
POST /action/catalogo-reclassificar {"id":…,"classe":"igual"}  -> «Candidato 9791899 agora é «igual»»
POST /action/catalogo-rejeitar     -> 1 descartado
SELECT … produtos do importador com qualquer preço  -> 0
```

Os produtos criados nesse ensaio foram **apagados do sandbox** ao fim (eram meus), e o sandbox
voltou às 867 linhas e 0 elos — para não sujar a medição das frentes irmãs.

---

## §5 — O que NÃO foi feito, e por quê

1. **Nada foi aprovado em produção.** A frente entrega a proposta; quem cadastra é o Jordan, na
   tela. Aprovar 125 produtos por mim seria exatamente a fusão no escuro que o oráculo proíbe.
2. **Nenhum preço, em lugar nenhum** — nem sugestão, nem margem, nem cópia do custo para campo de
   venda. Decisão explícita do dono em 24/09. O custo aparece **rotulado como custo** na tela da
   proposta e em nenhum outro lugar.
3. **Os 85 fiscais «sem par» não viraram 85 linhas em `products` por um INSERT largo.** Eles são
   um subconjunto das 147 linhas de compra, e entram pelo mesmo caminho auditado — senão eu
   estaria cadastrando 85 produtos com o critério «casar por código», que esta frente mediu como
   falso em 9 de 16 casos.
4. **Nada foi apagado.** As 867 linhas do Bling e as 95 da Z1 são dado real; nenhum DROP, DELETE
   ou UPDATE largo. Duplicata que exista **dentro** de `products` (867 linhas do Bling, nunca
   auditadas entre si) não foi tocada — ver §7.
5. **Tamanho de uma letra (P/M/G/GG) não é reconhecido como variação**: `_toks` descarta token de
   1 caractere e mexer nisso mudaria a taxa de sugestão de NCM da Z1, que é medida. Nos 147 itens
   reais não apareceu nenhum caso; se aparecer, a linha cai em `novo` (seguro) e a tela permite
   corrigir.
6. **Não toquei o módulo fiscal** (`redesign_builders/fiscal.py`, `_dgx_z*`) — a Z7 está lá. A
   tela `produtos-fiscais` da Z1 **não** ganhou a coluna do elo; isso é uma linha lá e fica para o
   orquestrador ou para a próxima onda.
7. **Não toquei o CRM nem a nota.** Ligar o item do orçamento ao catálogo é a AA2; carregar o
   `produto_id` até a nota é a AA3.
8. **Sem `attributes`/`price_history`/categoria**: produto novo nasce com o mínimo que a nota
   prova (código, descrição, unidade, NCM) + `notes` com a procedência. Categoria, marca e
   fornecedor padrão não vêm da nota de compra de forma confiável.

---

## §6 — Como o Jordan testa amanhã

1. `/redesign/suprimentos` → grupo **«Materiais & estoque»** → aba **«Compra → catálogo (aprovar)»**.
2. Deve ver **147 linhas**, ordenadas «já existe» → «variação» → «novo», com a coluna **«Por quê»**
   explicando cada uma (ex.: *«variação de "BOTA S/CADARCO COM BICO PVC BRAVO N36 BRACOL" — muda só
   N36 / N38»*; *«o código 297 já existe no catálogo como "Desempeno das portas" e as descrições não
   se parecem»*).
3. Procurar por **`BOTA`**: uma linha «Novo» e nove «Variação» — o orçamento vai ter **uma** bota,
   e o tamanho continua na grade de uniforme.
4. Procurar por **`SABAO`** / **`DETERGENTE`**: todos «Novo», nenhum fundido — mesmo NCM, produtos
   diferentes.
5. Numa linha «Novo» que na verdade já existe, clicar **«É este produto»**; numa linha «Já existe»
   que não é, clicar **«É novo mesmo»**.
6. Aba **«Aprovar em lote»** → *«Só os JÁ EXISTENTES»* → confirmar. A mensagem diz quantos elos
   foram criados e **lista as divergências de NCM que NÃO foram sobrescritas**.
7. Aba **«Catálogo vindo da compra»**: o que entrou, quem aprovou, e se a face fiscal ficou ligada.
8. Conferir no CRM: o item aprovado aparece na busca do orçamento **sem preço** — o preço do dia é
   digitado na hora.

---

## §7 — Decisões que só o dono pode tomar

1. **VTV-119 «SMART FITA LED»: `94054900` (nota do fornecedor) ou `85395200` (catálogo do Bling)?**
   Fita de LED como luminária (cap. 94) ou como lâmpada LED (cap. 85). Nada foi sobrescrito.
   É a única divergência de NCM entre as duas fontes nos itens que se encontram.
2. **`65119000` — «CAPACETE DE SEGURANCA BRANCO».** O NCM da nota não existe na nomenclatura; a
   Z1 já apontou que o correto é **6506.10.10 ou 6506.10.90**, e escolher entre os dois é
   classificar. O produto nasce **sem NCM** até alguém decidir.
3. **Os 9 códigos que colidem** (297, 9, 45, 33, 138, 140, 166, 118, 119). Hoje entram como
   produtos novos com código `NFE-<código>`. Se o senhor preferir outro padrão de código para o
   que vem de nota de compra, é uma linha.
4. **Duplicata dentro do próprio `products`.** As 867 linhas do Bling nunca foram auditadas entre
   si. Esta frente não mexeu nelas. Vale rodar a mesma régua do catálogo contra ele mesmo?
   (Seria o mesmo serviço, comparando `products` × `products` — não foi feito porque significa
   propor fusão de dado que ninguém pediu para mexer.)
5. **`crm_products` (115) continua uma terceira lista**, com o preço praticado das 33 propostas.
   `catalogo.py` já une as duas na leitura. Mantém as duas, ou o preço praticado vira histórico
   dentro de `products`? (Fundir destrói informação — ver o docstring do `catalogo.py`.)
6. **As 147 linhas são só da Conecta Eletrônica?** A classificação rodou sobre tudo que está em
   `nfe_compras_estoque`. Se o catálogo comercial tiver de ser por empresa, falta essa coluna —
   `products.condominio_id` hoje tem um valor único para as 867 linhas.
7. **A tela `produtos-fiscais` (Z1) deveria mostrar o elo com o produto comercial?** É uma coluna
   lá; não mexi porque a Z7 está no módulo fiscal agora.
