# DGX Z1 — Cadastro fiscal do produto (sem ele a NF-e é rejeitada)

**Onda 8 · 24/09/2026 · branch `dgx/z1-produto-fiscal` · módulo `fiscal`**
**Pedido do dono:** *«preciso urgente emitir notas fiscais»* e, no meio do trabalho,
*«o nosso sistema já pesquisar o NCM do produto pela descrição, isso nos economiza muito tempo»*.

---

## §1 — Estado antes (medido no sandbox, cópia de produção de 23/09)

| Fato | Número |
|---|---|
| NF-e de **saída** no sistema | **2**, ambas de 11/04/2026, **ambas rejeitadas** |
| Motivo da nota 2 | **«Rejeição: Informado NCM inexistente [nItem: 1]»** |
| Motivo da nota 1 | «Lote processado» (sem retorno útil) |
| `fin_produtos` / `fin_produto_tributacao` | **não existiam** |
| Validação de NCM no código | **nenhuma** — `fiscal_controller.py` tem a seção «NCM Endpoints» **vazia** (linha 46) |
| Tabela oficial de NCM (`ncms`) | **já carregada: 10.515 códigos vigentes** (Portal Único Siscomex, 27/08/2026) |
| `nfe_compras_estoque` | 147 itens, **95 NCMs distintos**, todos vindos de NF-e reais de fornecedores |

### Os dois números que o brief pediu

- **Dos 95 NCMs das compras, 94 passam na validação oficial** (existem em `ncms` e estão vigentes
  hoje). **1 não existe: `65119000`** — «CAPACETE DE SEGURANCA BRANCO». O fornecedor errou na nota
  dele: o capítulo 65 da nomenclatura termina em 6507, e capacete de segurança hoje é **6506.10.10
  ou 6506.10.90** (desdobramento vigente desde **01/02/2026** — provado contra a própria tabela).
  Esse produto nasce **inativo, com o motivo escrito**, e **não foi corrigido por inferência**:
  escolher entre .10 e .90 é classificar, e classificar é trabalho de gente.
- **Produtos «prontos para emitir»: 0 de 95**, nas duas empresas. E isso não é defeito da entrega —
  é a medição do problema: **CFOP e CST/CSOSN não existem em lugar nenhum da casa**, e é por isso
  que as duas NF-e de abril morreram. O cadastro agora diz, linha a linha, exatamente o que falta.

### Sugestão de NCM pela descrição — a taxa REAL

| Estratégia | Acerto (NCM certo entre os 5 primeiros, 147 itens, ignorando o próprio item) |
|---|---|
| A · só a nota do fornecedor (`nfe_compras_estoque`) | 68/147 — **46%** |
| A + B · + catálogo próprio já classificado (`products`) | 82/147 — **56%** |
| **A + B + C · + tabela oficial (entregue)** | **89/147 — 61%** |
| C · só a tabela oficial | 10/147 — 7% |
| C **antes** dos casamentos fracos de A (tentado) | 35/147 — 24% |
| A com os 209 itens dos XMLs em vez das 147 linhas | 68/147 — 46% (mesmos itens) |

**A meta pedida era 70%; o medido é 61%, e o teto é estrutural, não de algoritmo:**
**71 dos 95 NCMs aparecem UMA única vez em toda a casa.** Tirando o próprio item, não existe um
segundo documento que os mencione. Só 76 dos 147 itens têm irmão de mesmo NCM; mais 13 são
alcançáveis pelo catálogo do Bling → **teto documental de 89**, que é exatamente o que a ordem
A→B→C entrega. Chegar aos 70% exigiria a tabela oficial acertar ~28 dos 58 restantes, e ela acerta
7% sozinha — porque **vocabulário fiscal não é vocabulário comercial** («bota» não aparece no
capítulo 64, que fala em «calçados»). O oráculo trava em **55%** (regressão), imprime a taxa real
e explica por que 70% seria alarme falso diário.

---

## §2 — O que o DGX tem

O DGX trata produto como cadastro fiscal completo (NCM, CEST, origem, unidade comercial e
tributável, GTIN, pesos, CFOP padrão) **e a tributação separada por empresa**. Este é o pedaço que
faltava aqui: a nossa casa tinha `products` (catálogo de compra) e `nfe_compras_estoque` (estoque),
mas nada que respondesse *«este item pode sair numa NF-e desta empresa?»*.

---

## §3 — O que foi feito

### Arquivos

| Arquivo | O quê |
|---|---|
| `backend/modules/financial/services/produto_fiscal.py` **(novo, 964 linhas)** | Regra: DDL, validação de NCM, seed, «o que falta para emitir», sugestão pela descrição, padrão do regime |
| `backend/modules/operacional/controllers/redesign_builders/_dgx_z1_produto_fiscal.py` **(novo)** | 7 telas + 5 ações |
| `backend/modules/operacional/controllers/redesign_builders/fiscal.py` | +6 linhas: `router`, `MENU`, `telas(db, out)` |
| `backend/scripts/orq/test_oraculo_z1_produto_fiscal.py` **(novo)** | Oráculo (9 blocos, a→i) |

### DDL que `_ensure` aplica em produção no 1º acesso (idempotente, nada de alembic)

- `fin_produtos` — `codigo` (único), `descricao`, `ncm`, `cest`, `origem` (0-8, tabela A do CST),
  `unidade_comercial`, `unidade_tributavel`, `ean`, `peso_liquido`, `peso_bruto`,
  `cfop_padrao_dentro_uf`, `cfop_padrao_fora_uf`, `ativo`, `motivo_inativo`, `origem_cadastro`,
  `observacao`, `criado_em`, `atualizado_em` + índice em `ncm`.
- `fin_produto_tributacao` — `produto_id` → `fin_produtos`, `empresa_cnpj`, `cst_icms`, `csosn`,
  `aliquota_icms`, `cst_pis`, `aliquota_pis`, `cst_cofins`, `aliquota_cofins`, `cst_ipi`,
  `aliquota_ipi`, **`origem_regra TEXT NOT NULL`**, `atualizado_em`, único `(produto_id, cnpj)`.
- `fin_ncm_busca` — materialização do `tsvector` da nomenclatura (10.515 linhas) com índice GIN.
  Sem ela, cada sugestão recomputava os 10.515 vetores (~0,8 s por consulta; o script de 27/08
  estourou 590 s fazendo isso 736 vezes).

**Seed** (`ON CONFLICT DO NOTHING`, no 1º acesso): **95 produtos**, um por NCM distinto das
compras, com descrição, unidade comercial/tributável, **GTIN, origem da mercadoria e CEST lidos do
XML da nota de entrada** (93/95 com origem, 67 com GTIN real, 23 com CEST), `origem_cadastro =
'nfe_entrada'`; + **190 linhas de tributação** (95 × 2 empresas) com `origem_regra` dizendo de onde
veio o regime e que **nada foi preenchido por inferência**. CFOP e CST nascem **NULL**.

### Telas (grupo «Notas fiscais» do Fiscal) — deep-link `/redesign/fiscal?t=<id>`

| id | O que mostra |
|---|---|
| `produtos-fiscais` | 95 linhas · coluna **«Pronto para emitir?»** + **«O que falta»** por empresa; editar e ativar/inativar na linha; botão «Sugerir NCM» |
| `produto-fiscal-novo` | Cadastro novo — NCM validado contra a tabela oficial |
| `produto-tributacao` | 190 linhas (produto × CNPJ), filtro por empresa, CST/CSOSN conforme o regime, coluna «De onde veio a regra» |
| `produto-tributacao-lote` | Aplicar o padrão do regime **só onde está vazio**, com confirmação e fundamento gravado |
| `ncm-consulta` | Os 95 NCMs das compras × a nomenclatura oficial — quem existe e quem não |
| `ncm-sugerir` | Descrição → candidatos **com a fonte de cada um** |
| `ncm-aplicar` | Gravar o NCM escolhido: `origem_cadastro='sugerido'` + fonte na observação |

### Por que no módulo **Fiscal** e não em Suprimentos

O cadastro existe para **emitir**, e quem emite mora no Fiscal: o grupo «Notas fiscais» já tem
«NFS-e nacional — emitir DPS», «Importar XML de NF-e de compra» e «NFS-e emitidas». Em Suprimentos
o mesmo item aparece como **estoque** (`materiais`/`almoxarifado`, da F9) — outra pergunta. O elo é
o `codigo`, que é o mesmo `nfe_compras_estoque.item_code`, e a tela diz isso.

### A decisão que orienta tudo: **nada nasce preenchido**

O seed grava só o que veio de documento fiscal. CFOP e CST ficam NULL e a tela acusa. Preencher em
lote existe, mas é **ato de uma pessoa**: grava em `origem_regra` quem, quando e a lei
(Lei 10.637/2002 e 10.833/2003 no lucro real; CSOSN 102 / CST 49 da LC 123/2006 no Simples), e
**não toca o ICMS** — a alíquota depende da UF de destino e do benefício ZFM/SUFRAMA. É o mesmo
princípio do `sugerir_ncm_produtos.py` (27/08): «o sistema achou» ≠ «alguém classificou».

---

## §4 — Oráculo

`backend/scripts/orq/test_oraculo_z1_produto_fiscal.py` — afirma (a) todo produto **ativo** tem NCM
de 8 dígitos que **existe e está vigente** na tabela oficial; (b) ninguém é «pronto para emitir»
sem CFOP, CST/CSOSN e unidade, **reconferido por SQL próprio**; (c) tributação nas **duas** empresas
com `origem_regra`; (d) o seed reproduz **exatamente** os NCMs das compras; (e) NCM de 7 dígitos,
NCM inexistente e ativar produto com NCM inexistente → **422**; (f) CFOP 5xxx/6xxx no campo errado
→ 422; (g) fiação no `fiscal.py`; (h) a régua também diz **sim** quando é sim (fixture completa
fica pronta nas duas empresas e deixa de ficar ao perder o CFOP); (i) taxa de acerto da sugestão.

### Vermelho (antes — serviço ainda não existia)

```
$ .../oraculo.sh
  File "/app/scripts/orq/test_oraculo_z1_produto_fiscal.py", line 74, in main
    from modules.financial.services import produto_fiscal as pf
ImportError: cannot import name 'produto_fiscal' from 'modules.financial.services'
```

### Verde (depois)

```
95 NCM(s) distintos nas compras · 94 existem na tabela oficial (10515 códigos carregados) ·
95 produto(s) cadastrados, 94 ativo(s) · prontos para emitir nas DUAS empresas: 0 ·
35.710.481/0001-03: 0 pronto(s) · 66.014.833/0001-10: 0 pronto(s) ·
pares (produto, empresa) declarados prontos e reconferidos por SQL: 2 ·
sugestão de NCM pela descrição: 89/147 (61%) com o NCM certo entre os 5 primeiros
(meta pedida 70%, teto documental 89/147 = 61%), 1 sem candidato nenhum
TOTAL desvios: 0
OK cadastro fiscal: todo produto ativo tem NCM que EXISTE na nomenclatura vigente, ninguém é
«pronto para emitir» sem CFOP/CST/unidade, as duas empresas têm tributação com origem_regra,
o seed reproduz exatamente os NCMs das compras e NCM/CFOP inválidos são recusados com 422
```

### Prova por HTTP (container `teste-dgx-z1`, porta 8281 — já parado)

- `GET /api/v1/redesign/data/fiscal` → **200**, 40 telas, as 7 da Z1 presentes com dado real
  (95 produtos, 190 tributações, 95 NCMs) e as 7 no `extraMenu`, grupo «Notas fiscais».
- `POST /action/produto-fiscal-salvar` com NCM `65119000` → **422**
  *«Rejeição: Informado NCM inexistente [nItem: 1] — «65119000» não consta na nomenclatura vigente
  (10515 códigos).»*
- CFOP `6102` no campo «dentro do estado» → **422** *«CFOP dentro do estado tem 4 dígitos e começa
  em 5.»*
- `POST /action/produto-tributacao-salvar` sem `origem_regra` → **422** *«CST sem fundamento escrito
  é chute, e chute vira multa.»*
- `POST /action/ncm-sugerir` «BOTA DE SEGURANCA COM BICO PVC N42» → 1º candidato **64039190**
  «[nota do fornecedor] usado em «BOTA S/CADARCO COM BICO PVC USAFE/BRAVO N42», NF-e 42063 de
  L J GUERRA E CIA LTDA — semelhança 0.80».
- `POST /action/produto-ncm-aplicar` no capacete: `65061000` → **422** (código não vigente);
  `65061010` → **200**, produto vira `origem_cadastro='sugerido'` com a fonte na observação, e só
  então **ativa**. *Fixtures apagadas; sandbox devolvido ao estado semeado.*

### Dois defeitos que só a prova por HTTP pegou (o oráculo estava verde)

1. **Toda sugestão saía rotulada «[tabela oficial]»** na mensagem da ação, inclusive as que vinham
   da nota do fornecedor — o rótulo comparava com o nome antigo da fonte. Sugestão com a
   procedência errada é pior que sugestão nenhuma. Corrigido (`_ROTULO_FONTE`).
2. **A descrição oficial exibida era «Outro».** O docstring de `carregar_tabela_ncm.py` afirma que
   `descricao_resumida` guarda o caminho hierárquico; **no banco é o contrário** — o caminho está
   em `ncms.descricao` e `descricao_resumida` é a folha («Outro», «Outras» em milhares de linhas).
   Trocado em toda a frente (exibição e peso A do `tsvector`). A documentação do carregador segue
   desatualizada — fica registrado para quem mexer nele.

---

## §5 — O que NÃO foi feito, e por quê

1. **Não liguei o cadastro na emissão da NF-e.** `fiscal_contabil/notas_fiscais/nfe/` e
   `financial/integrations/nfe_provider.py` não foram tocados — é a frente **Z2**. Enquanto o elo
   não existir, este cadastro **não muda nenhum XML** que sai hoje.
2. **Não inventei CFOP nem CST para ninguém.** 0 de 95 produtos prontos é a medição honesta. Um
   cadastro cheio de CSOSN chutado emitiria notas — e cada uma seria uma autuação futura.
3. **Não corrigi o NCM `65119000`.** Existe a resposta certa (6506.10.10 ou 6506.10.90) e o sistema
   já aceita gravá-la; escolher entre as duas é classificação, e classificação é do contador.
4. **Não uni `fin_produtos` com `products`** (867 do Bling, 193 com NCM). São catálogos diferentes:
   `products` é compra de eletrônica, sem tributação por CNPJ, sem unidade tributável nem CFOP por
   UF. Unir é decisão do dono (§7). O catálogo já é **usado como fonte B** da sugestão.
5. **`produto-fiscal-editar` virou edição na linha** (`editfn`), que é o idioma da casa (V5 faz
   assim) — menos tela, mesmo resultado.
6. **Não criei `fin_ncm`**: a tabela oficial já existe (`ncms`, 10.515 linhas). Criar uma segunda
   seria a tabela-irmã morta que a V5 documentou.
7. **`_toks`/`_sim` foram copiados** (10 linhas) de `scripts/orq/sugerir_ncm_produtos.py` em vez de
   importados: aquilo é um CLI com `sys.path` próprio, e serviço não importa script. O corte 0,80
   segue sendo o medido lá em 27/08.
8. **Não atingi os 70% de acerto da sugestão** — 61%, com o teto medido e publicado (§1).
9. `fin_ncm_busca` só recarrega quando a **contagem** de `ncms` muda. Recarga do Siscomex com
   exatamente o mesmo número de códigos não seria percebida — improvável, e o conserto é
   `DROP TABLE fin_ncm_busca`.

---

## §6 — Como o Jordan testa amanhã

1. **Fiscal → Notas fiscais → «Produtos fiscais (NF-e)»** — 95 produtos vindos das suas compras
   reais. Olhe a coluna **«O que falta»**: é a lista do que impede cada um de sair numa nota.
2. Filtre **«NCM oficial = não»** → aparece o capacete. A coluna diz que a SEFAZ rejeitaria.
3. **«Sugerir NCM pela descrição»** → escreva *bota de segurança com bico* → **Buscar candidatos**.
   Cada linha diz de onde veio («nota do fornecedor, NF-e 42063 de L J GUERRA»).
4. **«Aplicar NCM sugerido»** → escolha o produto, cole o NCM e a fonte → o produto passa a
   `sugerido` e fica auditável.
5. **«Tributação por empresa (CNPJ)»** → filtre por Eletrônica e por Patrimonial: a mesma
   mercadoria, duas regras. Edite uma linha — **«De onde veio a regra» é obrigatório**.
6. **«Tributação — padrão do regime»** → escolha a empresa → confirma → preenche o que está vazio
   com a lei gravada. Depois volte ao item 1: a coluna «O que falta» encolhe.
7. Tente criar um produto com um NCM inventado (ex.: `99999999`): a tela recusa com a **mesma
   frase que a SEFAZ te deu em abril**.

---

## §7 — Decisões que só o dono pode tomar

1. **Qual CFOP de saída a Conecta usa para mercadoria?** 5102/6102 (venda de mercadoria adquirida
   de terceiros) é o caso comum, mas há 5949/6949 (outra saída), 5915/6915 (remessa para conserto),
   5551 (ativo). **Enquanto não houver essa resposta, nenhum produto fica pronto para emitir.**
   É o item nº 1 do «preciso emitir urgente».
2. **CST/CSOSN por mercadoria, com o contador.** O botão de lote aplica o padrão do regime e grava
   o fundamento; ele **não substitui** a conferência item a item, e o **ICMS continua vazio**
   (alíquota depende da UF de destino e do benefício ZFM/SUFRAMA da Eletrônica — SUFRAMA 210140500).
3. **O capacete (`EPI-002`)**: 6506.10.10 ou 6506.10.90? A nomenclatura desdobrou em 01/02/2026.
4. **Unir `products` (Bling, 867) com `fin_produtos`?** Hoje são dois catálogos com propósitos
   diferentes. Se a Conecta for **vender** o que está no Bling, eles têm que virar um só — e aí
   736 produtos sem NCM entram nesta fila.
5. **A nota 1 de 11/04/2026** ficou «rejeitada / Lote processado», sem motivo legível. Se houver
   intenção de reemitir aquelas duas notas, alguém precisa buscar o retorno da SEFAZ.
6. A sugestão pela descrição acerta **61%** com fontes documentais. Subir disso exige uma fonte
   nova — por exemplo, **classificar uma vez** os itens que compramos com frequência: cada item
   classificado vira fonte para os próximos. Não há atalho técnico honesto.
