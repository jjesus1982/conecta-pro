# DGX AA2 — o item do orçamento vem do catálogo (24/09/2026)

**Branch:** `dgx/aa2-orcamento-catalogo` · **Módulo:** CRM · **Porta de teste:** 8292

> «na hora de fazer o orçamento, fazemos pelo crm, já estará lá com toda a descrição,
> **só seleciona o item e as quantidades**» — Jordan, 24/09/2026
>
> «nos produtos cadastrados, deixem sem valor, quando eu for fazer os orçamentos eu edito o
> preço, por que os preços variam muito, tem muitas constantes, então quando eu orçar pego o
> **preço do dia** e edito na hora» — Jordan, 24/09/2026

---

## ⚠️ PREMISSA DESTA FRENTE (leia antes de fazer merge)

**Escolhi `products` (867 linhas, Bling) como catálogo, conforme o briefing.** O elo novo é
`proposal_items.produto_id uuid → products.id`.

**Mas o que eu medi contradiz em parte a premissa do briefing** («`products` … é o que o CRM usa»):

| Medição em produção (24/09/2026) | Resultado |
|---|---|
| itens de orçamento cujo `name` casa com `crm_products.name` | **161 de 177** |
| itens de orçamento cujo `name` casa com `products.name` | **1 de 177** |

Existe um **TERCEIRO catálogo** que nem o plano nem o briefing citam: **`crm_products`, 115
linhas**, já ligado à aba do CRM «Produtos (catálogo)» (`crm.py:2425`, subtítulo literal *"base
dos itens de proposta"*), com **`sku` em 115/115** e **`unit_price` > 0 em 107/115**. Foi semeado
do histórico de propostas do Jordan e depois complementado pelo importador
`scripts/orq/importar_catalogo_bling.py` — que também escreve nele, **não** em `products`.

Ou seja: a casa tem **quatro** cadastros de produto, e eles quase não se tocam.

| Tabela | Linhas | Preço? | NCM? | Quem usa |
|---|---|---|---|---|
| `products` | 867 | **6 colunas, todas NULAS** | 193 | estoque/compras · **o catálogo desta frente** |
| `crm_products` | 115 | `unit_price` em 107 | não tem coluna | aba «Produtos (catálogo)» do CRM · 161/177 itens reais |
| `fin_produtos` | 95 | não tem coluna (Z1 acertou) | 95 | fiscal (Z5 casa o item da nota aqui) · **`id` é `integer`, não uuid** |
| `nfe_compras_estoque` | 147 | `unit_cost` em 147 | sim | itens das notas de compra |

Cruzamentos medidos: `crm_products.sku` × `products.code` = **0**; `crm_products.name` ×
`products.name` = **1**; `fin_produtos.codigo` × `products.code` = **10**;
`nfe_compras_estoque.item_code` × `products.code` = **16**.

**Consequência prática:** a tela que entreguei serve o fluxo que o dono descreveu (material da
Conecta Eletrônica, vindo das notas de compra). Os itens de **serviço/mão de obra** que ele mais
orça hoje (AGP, ASG, artífice, locação) vivem em `crm_products` e **não aparecem** nesta tela —
o subtítulo da tela diz isso com todas as letras. Unificar é a frente **AA1**; se ela decidir
outra fonte, o conserto é `UPDATE`/`ALTER` sobre uma coluna só.

---

## 1. Estado ANTES (medido em produção, 24/09/2026)

* `proposal_items`: **177 linhas**, 36 propostas, **`code` vazio em 177/177** — item é texto
  livre digitado, e **não havia coluna nenhuma de elo com produto**. É por isso que a frente Z5
  (orçamento aprovado → rascunho de nota) casa item com produto **pela descrição**.
* `products`: **867 linhas** (todas `ativo`), **193 com NCM**, **854 códigos numéricos puros**,
  **174 sem unidade**, só 13 com `description` (o `name` É a descrição).
  As seis colunas de preço (`reference_price`, `last_purchase_price`, `average_price`,
  `min_price`, `max_price`, `price_history`) estão **zeradas nas 867**.
* `proposals.subtotal` × Σ itens: **0 divergências**. `item.total` × qtd×unit×(1−desc):
  **0 divergências**. (A régua já fechava — e tinha de continuar fechando.)
* Dois defeitos que só apareceram ao exercitar o caminho (ver §3.4 e §3.5):
  **a tela «Novo item de proposta» devolvia HTTP 500 em toda tentativa**, e
  **`ProposalRepository.add_item` não atualizava o total da proposta**.

## 2. O que o DGX / o plano pedem

`docs/dgx/PLANO_IMPLEMENTACAO.md`, §RADAR, itens 3, 4 e 5:

* o catálogo nasce **sem preço de venda** e o item do orçamento **não herda valor** — só código,
  descrição, unidade e NCM;
* o item do orçamento passa a vir do catálogo em vez de texto livre;
* *«o elo que falta é o item da proposta carregar o `produto_id`»* — literalmente o nome usado
  no plano, e por isso o nome que escolhi (a frente **AA3** lê o mesmo documento).

## 3. O que foi feito

### 3.1 `backend/modules/crm/services/item_do_catalogo.py` (novo) — a regra

`adicionar_item_do_catalogo(db, *, proposal_id, produto_id, empresa_id, quantidade,
preco_digitado, desconto_percent=None, observacao=None, opcional=False)`.

* **`preco_digitado` vazio levanta `ValueError`.** Não é zero, não é default: zero seria um item
  de graça dentro do orçamento do cliente. A assinatura recebe o valor **como veio do
  formulário** de propósito — um `preco: float = 0.0` seria exatamente o preenchimento
  automático que o dono cancelou, escrito de um jeito que ninguém pega na revisão.
* `code`, `name`, `unit` e a descrição saem do produto; **nenhuma coluna de preço de `products`
  é lida** (o oráculo confere por AST).
* Reusa `ProposalRepository.add_item` — é ele que recalcula `proposals.subtotal/total` e recusa
  proposta já enviada. O elo é gravado por `UPDATE` depois.

**DDL idempotente** (`garantir_coluna`, roda no 1º acesso à tela e em cada ação):

```sql
ALTER TABLE proposal_items ADD COLUMN IF NOT EXISTS produto_id uuid;
CREATE INDEX IF NOT EXISTS ix_proposal_items_produto_id ON proposal_items (produto_id);
COMMENT ON COLUMN proposal_items.produto_id IS 'Produto do catálogo (products.id) …';
```

> **A coluna NÃO entra no model SQLAlchemy de propósito.** `ProposalItem` é lido por dezenas de
> caminhos (CRM clássico, PDF da proposta, Z5); uma coluna no ORM antes da coluna no banco
> derrubaria todos eles no primeiro boot depois do bake.

### 3.2 `redesign_builders/_dgx_aa2_orcamento_catalogo.py` (novo) — a tela

Tela **`orcamento-catalogo`** — «Catálogo → item do orçamento», grupo **«Propostas & orçamento»**
do CRM. Deep-link: `/redesign/crm?t=orcamento-catalogo`.

Colunas: `Código · Descrição (é por aqui que se busca) · Unidade · NCM · Marca · Já usado`.
Cada linha tem o botão **«Usar no orçamento»**, que abre um formulário com **só o que é do
humano**:

| campo | origem |
|---|---|
| Proposta (rascunho/aprovada) | escolha |
| CNPJ que emite este item | escolha (NOT NULL no banco) |
| Quantidade (na unidade do produto) | digitado, começa em 1 |
| **Preço do dia (R$)** | **digitado, chega VAZIO** |
| Desconto (%) | digitado, opcional |
| Observação | digitado, opcional |

Código, descrição, unidade e NCM **não são redigitados**: vêm do produto pelo `produto_id`, que
viaja em `fixed` (corpo da requisição) e não como campo na tela — campo `hidden` no modal de
ação por-linha apareceria como uma caixa de texto editável com um UUID dentro.

**A busca por descrição.** O campo «Buscar…» do topo já filtra por **qualquer célula** da linha
(`ModuleView.tsx:208`), então serve para código e para descrição sem nenhum código novo.
Medido nas 867 linhas reais:

| termo digitado | linhas achadas |
|---|---|
| `cabo` | 62 |
| `sensor` | 43 |
| `fonte` | 32 |
| `cancela` | 28 |
| `switch` | 24 |
| `rack` | 20 |
| `conector` | 20 |
| `motor` | 17 |
| `nobreak` | 15 |

**860 dos 867 produtos** têm no nome pelo menos uma palavra de 4+ letras por onde ser achado.

**⚠️ O que a busca NÃO acerta:** ela é literal, sem dobra de acento. O catálogo tem **«câmera»
em 36 linhas e «camera» em 28** — os dois jeitos de escrever a mesma palavra, herdados do Bling.
Quem digita `camera` acha 28 e perde 36; quem digita `câmera` acha 36 e perde 28. Isso é defeito
do **catálogo**, não da tela (§7).

### 3.3 `redesign_builders/crm.py` — a fiação e a coluna «Catálogo»

* import do `router` + `include_router` (ações), `EXTRA_MENU.extend(MENU)` (a aba), e
  `await _telas_aa2(db, out)` no fim do `build()`;
* `await _aa2_elo(db)` **antes** de `_ligar_20260908` — a tela `proposta-itens` passou a ler
  `i.produto_id` e uma coluna inexistente faria a tela inteira sumir (o `tbl` está dentro de um
  `try/except` que engole);
* **`proposta-itens` ganhou a coluna «Catálogo»**, com `LEFT JOIN products`: mostra
  `código · NCM` em verde quando o item vem do catálogo e **«digitado à mão»** em cinza quando
  não vem. Os 177 itens de hoje aparecem como «digitado à mão» — com honestidade, não fingindo.

Saída real do sandbox:

```
cols: ['Proposta','Item','Catálogo','Qtd','Unitário','Desc. %','Total','Opcional']
['PROP-2026-00124','50M de cabo UTP cat 5E blindado','719 · NCM 85444900','3.0','R$ 1.234,56','0.0','R$ 3.703,68','—']
['PROP-2026-00124','Servico de teste - prova do funil','digitado à mão','1.0','R$ 9,90','0.0','R$ 9,90','—']
```

### 3.4 Defeito encontrado e corrigido: «Novo item de proposta» dava HTTP 500

`proposal_items.empresa_id` é **NOT NULL** desde a migration de 28/08/2026, e a ação
`/action/proposta-item-novo` **nunca mandou o campo** — o `ProposalItemCreate` ia com
`empresa_id=None` e o insert estourava. Medido pela porta 8292: **HTTP 500 em toda tentativa**.
Provavelmente nunca funcionou desde 28/08.

Corrigido: o formulário ganhou o select «CNPJ que emite este item*» e a ação recusa com **400 e
frase** quando ele falta. Depois: `{"ok":true,...}` HTTP 200.

### 3.5 Defeito encontrado e corrigido: `add_item` não atualizava o total da proposta

`ProposalRepository.add_item` chamava `proposal.calculate_totals()` **sem** o
`refresh(proposal, ["items"])` que o `remove_item` logo abaixo sempre teve. A coleção lida era a
de **antes** do insert: item de R$ 2.501 entrou e o `subtotal` ficou em R$ 0,00 (medido no
sandbox). Ninguém tinha visto porque as 177 linhas de produção nasceram por
`create()`/`replace_items`, que calculam em memória — e porque o único caminho que usa `add_item`
era o do §3.4, que morria antes de chegar lá.

Uma linha, no repositório por onde **todos** os chamadores passam. Depois do fix, no sandbox:
`PROP-2026-00124 · subtotal 3713.58 · total 3713.58 · Σ itens 3713.58`.

## 4. Oráculo

`backend/scripts/orq/test_oraculo_aa2_orcamento_catalogo.py`

```bash
ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\n' ' ')
docker run --rm --network conecta-staging-network -v "$PWD/backend:/app:ro" -e PYTHONPATH=/app \
  -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env -e SMTP_HOST= -e SMTP_USERNAME= \
  -e SMTP_PASSWORD= $ENVS conecta-pro-backend:latest \
  python3 /app/scripts/orq/test_oraculo_aa2_orcamento_catalogo.py
```

Afirma, recontando por SQL próprio: (1) o elo existe com índice; (2) o preço nunca vem do
catálogo — **por AST** (nenhuma constante de string do serviço ou do builder cita coluna de
preço de `products` nem `crm_products.unit_price`; o campo de preço do formulário não tem
`value`) **e por comportamento** (preço vazio → `ValueError`, três variantes); (3) item ligado ao
catálogo tem `code`/`name`/`unit` **iguais** ao produto e NCM alcançável pelo elo; (4) item sem
catálogo continua válido e a tela o marca; (5) a conta fecha ao centavo, item e proposta.

**ANTES (vermelho):**

```
FALHOU: serviço crm/services/item_do_catalogo.py não importa:
        cannot import name 'item_do_catalogo' from 'modules.crm.services'
exit=1
```

**DEPOIS (verde):**

```
itens de orçamento: 180 · ligados ao catálogo: 2 (sem NCM no produto: 0) · digitados à mão: 178 · catálogo: 867 produtos
OK orçamento×catálogo: elo gravado, descrição/unidade/NCM do catálogo, preço só do humano, conta fecha
exit=0
```

Houve um **vermelho intermediário que valeu a frente inteira** — `FALHOU: 1 proposta(s) com
subtotal ≠ Σ dos itens`. Foi ele que revelou o defeito do §3.5.

### Provas por HTTP (porta 8292, contra o sandbox)

```
POST /api/v1/redesign/action/orcamento-item-catalogo   (preco_digitado: "")
  → 400 {"detail":"Digite o preço do dia (o catálogo não sugere preço)."}

POST /api/v1/redesign/action/orcamento-item-catalogo   (preco_digitado: "1.234,56")
  → 200 {"ok":true,"message":"719 · 50M de cabo UTP cat 5E blindado · NCM 85444900
                              — 3 MT × R$ 1.234,56 = R$ 3.703,68"}

POST /api/v1/redesign/action/proposta-item-novo        (sem empresa_id)
  → 400 {"detail":"Escolha qual CNPJ emite este item."}      (era 500)
POST /api/v1/redesign/action/proposta-item-novo        (com empresa_id)
  → 200 — e o item nasce com produto_id NULO, marcado «digitado à mão»
```

## 5. O que NÃO foi feito (e por quê)

1. **Nenhuma coluna `ncm` em `proposal_items`.** O NCM chega pelo elo (`JOIN products`). Coluna
   duplicada é coluna que diverge, e o oráculo não teria como distinguir «divergiu» de
   «o catálogo mudou depois». Se a frente AA3 precisar do NCM **congelado no momento do
   orçamento** (argumento legítimo: proposta é documento de data fixa), isso é um `ALTER` de uma
   linha — mas é decisão dela, não minha.
2. **Não mostrei custo de compra ao lado do preço.** O plano permite; os dados não sustentam:
   as seis colunas de preço de `products` estão **zeradas nas 867**, e `nfe_compras_estoque`
   (147 itens, custo em todos) só casa com `products.code` em **16**. Uma coluna com 851 traços
   é ruído. Ligar isso é trabalho do importador compra→catálogo (RADAR item 2), não daqui.
3. **Não unifiquei catálogo nenhum, não mexi em `crm_products`, `fin_produtos` nem
   `nfe_compras_estoque`.** É a frente AA1 e ela está rodando em paralelo.
4. **Não importei produto de nota de compra.** RADAR item 2 — frente separada.
5. **Não mexi no fiscal** (`fiscal.py`, `_dgx_z*`, `dgx_z5_orcamento_nota.py`) — território das
   frentes Z7/AA3. A Z5 continua casando por descrição **até** passar a ler `produto_id`; é uma
   mudança de uma linha lá dentro, e é da AA3.
6. **Não resolvi a dobra de acento na busca.** Não posso tocar `frontend/`. Veja §7 — há uma
   correção de uma linha, e ela é do orquestrador.
7. **Edição de item já lançado** continua como estava (só Remover). Trocar o produto de um item
   existente ninguém pediu.

## 6. Como o Jordan testa amanhã

1. CRM → grupo **«Propostas & orçamento»** → aba **«Catálogo → item do orçamento»**
   (`/redesign/crm?t=orcamento-catalogo`). Devem aparecer **867 produtos**.
2. No campo **Buscar…** do topo digite `cabo` — 62 linhas. Digite `nobreak` — 15. Digite `719` —
   acha pelo código. É a busca por descrição do dia a dia.
3. Na linha escolhida, botão **«Usar no orçamento»**. Repare: o código, a descrição, a unidade e
   o NCM **não aparecem para digitar** — já são do item. O campo **«Preço do dia (R$)»** está
   **vazio**, e continuará vazio toda vez.
4. Tente **Adicionar sem digitar o preço**: tem de recusar com *«Digite o preço do dia (o
   catálogo não sugere preço)»*. É a sua regra de 24/09 virada em trava.
5. Escolha a proposta, o CNPJ, a quantidade, digite o preço de hoje, adicione.
6. Vá para a aba **«Itens de proposta»**: o item novo aparece com a coluna **«Catálogo»** em
   verde (`código · NCM`); os itens antigos aparecem como **«digitado à mão»** — é a verdade,
   eles não têm produto.
7. Confira o **valor total da proposta**: ele agora soma o item novo (antes não somava — §3.5).

## 7. Decisões que só o dono pode tomar

1. **Qual catálogo é o catálogo?** Hoje são quatro (§Premissa). O dono orça **serviço** por
   `crm_products` (161/177 dos itens reais) e vai orçar **material** por `products` (867). Se
   forem para sempre dois mundos, a tela precisa de duas abas; se for um só, alguém tem de
   decidir quem manda no código e no NCM. **Essa decisão trava a AA1, a AA3 e esta frente.**
2. **`crm_products` tem preço de venda em 107 de 115 linhas** — e a regra de 24/09 diz *«deixem
   sem valor»*. Esses preços são do histórico de propostas dele. Ficam como referência histórica,
   ou saem do cadastro? Enquanto estiverem lá, alguém vai querer copiá-los para o orçamento.
3. **«câmera» e «camera» no mesmo catálogo** (36 e 28 linhas). Duas saídas:
   (a) **padronizar o catálogo** — trabalho da AA1, mexe em dado do cliente, precisa do aval dele;
   (b) **dobrar o acento na busca do front** — uma linha em
   `frontend/src/components/redesign/ModuleView.tsx:208`, aplicando
   `.normalize('NFD').replace(/\p{Diacritic}/gu,'')` nos dois lados da comparação. **Não posso
   tocar `frontend/`; fica para o orquestrador.** A (b) conserta a busca de *todas* as tabelas do
   sistema, não só desta tela.
4. **174 dos 867 produtos não têm unidade** e **674 não têm NCM.** O item herda `un` quando a
   unidade falta, e sai sem NCM quando o produto não tem — e a nota vai precisar dele. Quem
   preenche, e a partir de qual fonte (XML das compras? Bling?)?
5. **Congelar o NCM no item do orçamento** (§5.1) — proposta é documento de data fixa; catálogo
   muda. Se o dono quiser o NCM que valia no dia do orçamento, é uma coluna a mais.
6. **Nenhum dos 867 produtos tem `cfop_out`.** Sem CFOP de saída não há nota — é o mesmo bloqueio
   já listado no fim do RADAR, e reaparece inteiro aqui.

---

### Para o orquestrador — resumo de merge

* **Coluna do elo (a AA3 depende dela): `proposal_items.produto_id uuid → products.id`**, com
  índice `ix_proposal_items_produto_id` e `COMMENT`. NULO = item digitado à mão.
* **DDL que `_ensure` aplica em produção no 1º acesso:** os 3 comandos do §3.1 — todos
  `IF NOT EXISTS`, nenhum DROP/DELETE/UPDATE em dado existente.
* **Arquivos:** `modules/crm/services/item_do_catalogo.py` (novo),
  `redesign_builders/_dgx_aa2_orcamento_catalogo.py` (novo),
  `scripts/orq/test_oraculo_aa2_orcamento_catalogo.py` (novo),
  `redesign_builders/crm.py` (fiação + coluna «Catálogo» + fix do 500),
  `modules/crm/repositories/proposal_repository.py` (1 linha, fix do total).
* **Tela:** `orcamento-catalogo`, grupo «Propostas & orçamento» do CRM.
* **Container parado:** `teste-dgx-aa2` (porta 8292).
* **Fixture deixada no sandbox:** proposta `notes = 'FIXTURE DGX AA2'` e seus itens (o oráculo
  recria a dele a cada corrida), mais 2 itens de teste nas propostas `PROP-2026-00123/00124` do
  staging. **Nada foi escrito em produção.**
