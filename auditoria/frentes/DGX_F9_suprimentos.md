# DGX F9 — Suprimentos (24/09/2026)

Branch `dgx/f9-suprimentos` · módulo `suprimentos` (`/redesign/suprimentos`) · agente `agent-f9`.
Solicitação → pedido de compra → NF de entrada; materiais com mínimo/máximo e movimentação;
fornecedores; comunicações móveis e rastreadores como equipamento controlado; kit de uniforme por função.

## §1 — Estado antes (medido no sandbox = cópia de produção de 23/09) e QUEM escreve em cada tabela

| Tabela | Linhas | Quem escreve (grep no repositório) | Veredito |
|---|---|---|---|
| `nfe_compras_estoque` | **147** | `government_integrations/services/nfe_entrada_sync_service.processar_xml_nfe` (entrada por item da NF-e, custo médio ponderado); `financial/services/estoque_real_service.registrar_saida` (baixa + COGS `5.1.1.06/1.1.4.01`); lida por `inventory_controller` (`/inventory/real/*`), `fiscal_dashboard_service`, builders `financeiro`/`_fin_ligar4` e o `_build_suprimentos` do monólito | **ESTOQUE VIVO.** Não tinha mínimo/máximo/grupo. `item_code` = `cProd` do fornecedor (UNIQUE) |
| `nfe_estoque_movimentos` | 1 | `estoque_real_service.registrar_saida` — só SAÍDAS eram registradas; entradas do sync não deixavam trilha | vivo, incompleto |
| `nfe_entradas` | 84 (51 com XML e processadas · **32 só resumo, sem XML** · 1 resumo processada) | `nfe_entrada_sync_service` (distribuição DF-e) | vivo; as 32 sem XML nunca entraram no estoque (§7) |
| `fin_stock_items` / `fin_stock_movements` / `fin_stock_inventories` | 2 / 0 / 0 (12/04/2026) | só `financial/models/stock_*` — **nenhum serviço grava**; `_fin_cadastros` lê | semente sem escritor |
| `inventory_items` | 2 | só `financial/models/stock_inventory.py` | cópia de `fin_stock_items`, sem escritor |
| `products` | 867 (27–29/08) | `purchase_repository` (catálogo VTV-… de câmeras para propostas/growth) | catálogo comercial, não almoxarifado |
| `purchase_requisitions/_items`, `purchase_orders/_items`, `goods_receipts/_items` | 0 | models, schemas e `purchase_repository` — **sem controller, sem rota**; `_fin_cadastros` conta | prontas, nunca usadas |
| `purchase_quotations/_items` | 4 / 26 | `integrations/connectors/whatsapp/agent_service` (cotação pedida por WhatsApp; totais 0) | vivo, fora desta frente |
| `suppliers` | **60** (60 CNPJs distintos, 0 sem CNPJ; 26 `material`, 12 sem categoria) | `fornecedor_categoria_service` (emitentes reais das notas), `payable_auto_service._get_or_create_supplier` (NFS-e → conta a pagar), `supplier_repository`, `whatsapp/agent_service` | **FORNECEDOR VIVO** (tenant `a1b2c3d4-…`) |
| `financial_fornecedores` | 12 | `integrations/inter/inter_sync_service` (seed + `padrao_match` para etiquetar saídas do extrato como «Fornecedor») | padrão de conciliação bancária, não cadastro |
| `equipamentos_controlados` (+`_alocacoes`) | 0 / 0 | frente 05 (`hr/services/conformidade_vigilante`): `cadastrar_equipamento`, `entregar`, `devolver`; CHECK `tipo IN (armamento, colete)`; índice único parcial `ux_equip_aloc_aberta` | vivo, só arma/colete |
| `sst_uniforme_grade` / `_entregas` | 0 / 0 | frente 10 (`_frente_10.py`): SKU normalizado, entrega em lote por posto/CPF | vivo, sem noção de kit |
| `health_epi_catalog` / `_inventory` | 5 / 0 · `gp_epi_deliveries` 220 | `health_occupational/services/epi_service`, `sst_service` | fora desta frente (frente 10 já decidiu) |
| `fin_condicoes_pagamento` | 4 (F11) | `_dgx_f11_financeiro` | reusada no pedido |

Telas do módulo antes: `visao` e `almoxarifado` (monólito); `requisicoes` no JSON do menu nunca ligada (mock).
Nenhuma porta para compras, mínimo/máximo, fornecedores, rádio/rastreador ou kit.

## §2 — O que o DGX tem (docs/dgx/00 e 02)

Compras: NF de entrada · Pedidos · Solicitações. Equipamentos: Armamentos · Coletes · Comunicações Móveis ·
Rastreadores. Fornecedores · Grupos Materiais/Uniformes. Materiais: Cadastro (código, descrição, mínimo,
máximo, unidade % CT CX KG M m2 m3 ML PC T UN, origem, grupo) · Estoque (6 status) · Solicitação.
Uniformes/EPI: Cadastro · Entrega · Estoque · Kit (por função). Rótulos: Produto Suprimentos, Tamanho do
Produto, Tipo do Equipamento, Valor Comercial, Valor de Retorno, Tipo do Armamento, Nº de Pedido.

## §3 — O que foi feito

Arquivos (3, todos novos — nenhum existente editado):
- `backend/modules/operacional/controllers/redesign_builders/_dgx_f9_suprimentos.py` — telas, DDL, ações.
- `backend/modules/operacional/controllers/redesign_builders/suprimentos.py` — builder do módulo
  (`SLUG="suprimentos"`, `EXTRA_MENU`, `router`; `build()` chama `_build_suprimentos` do monólito e estende).
- `backend/scripts/orq/test_oraculo_suprimentos_cadeia.py` — oráculo.

DDL que `_ensure` aplica em produção no 1º acesso (idempotente):
```
nfe_compras_estoque      ADD grupo varchar(20), minimo numeric, maximo numeric, ativo bool DEFAULT true, origem varchar(10) DEFAULT 'nfe'
nfe_estoque_movimentos   ADD ref_chave varchar(60), created_by varchar(120); UNIQUE INDEX ux_nfe_estoque_mov_entrada (ref_chave, item_code) WHERE tipo='entrada' AND ref_chave IS NOT NULL
purchase_requisitions    ADD post_id uuid · purchase_requisition_items ADD item_code · purchase_order_items ADD item_code · purchase_orders ADD condicao_pagamento_id int
goods_receipts           ADD nfe_entrada_id int; UNIQUE INDEX ux_goods_receipts_invoice_key (invoice_key) WHERE invoice_key IS NOT NULL
equipamentos_controlados ADD imei, numero_linha, operadora, plano_mensal numeric, post_id uuid; CHECK tipo IN (armamento, colete, radio, celular, rastreador)  [DROP+ADD do CHECK, como a F10 fez em frota_leituras]
CREATE TABLE sst_uniforme_kits (funcao, grade_id → sst_uniforme_grade, quantidade > 0, ativo, UNIQUE (funcao, grade_id))
```

Telas (17 novas + `requisicoes` ligada; deep-link `/redesign/suprimentos?t=<id>`), grupos do `EXTRA_MENU`:
- **Compras**: `solicitacoes-compra` (=`requisicoes`; Aprovar/Negar por linha), `solicitacao-compra-nova`
  (título, posto, urgência, itens `código|qtd|justificativa`), `pedidos-compra` (Enviar / Receber manual /
  Cancelar), `pedido-compra-novo` (solicitação aprovada → itens copiados, ou avulso; fornecedor de
  `suppliers`; condição de `fin_condicoes_pagamento`; previsão), `nf-entrada` (84 NF-e da SEFAZ + conferência;
  «Conferir recebimento» sugere o pedido aberto do mesmo CNPJ e mesmo valor).
- **Materiais & estoque**: `materiais` (147; Editar mín/máx/grupo, Inativar), `material-novo`, `estoque`
  (6 status do DGX + legenda com contagem), `estoque-movimentar` (entrada | saída | ajuste por contagem, `confirm`).
- **Fornecedores**: `fornecedores` (60 `suppliers` + 8 padrões de extrato sem cadastro = 68, coluna origem,
  últimas compras a partir das NF-e), `fornecedor-novo` (grava em `suppliers`).
- **Equipamentos controlados**: `comunicacoes-moveis` (rádio/celular; Entregar/Devolver = `cv.entregar/devolver`
  da frente 05; painel «Custo mensal dos planos», só leitura), `rastreadores`, `equipamento-movel-novo`.
- **Kits**: `kit-uniforme`, `kit-uniforme-novo`, `kit-uniforme-entregar` (chama `uniforme_entrega_lote` da
  frente 10 uma vez por item do kit, para os ativos da função — opcionalmente só os alocados no posto).

Regras que valem em código:
- **Entrada única.** Movimento de entrada tem `ref_chave` (chave da NF-e ou nº do pedido) e índice único
  por (ref, item). NF-e `processada` já teve o saldo somado pelo sync SEFAZ → conferir só REGISTRA o
  movimento (`ajusta_saldo=False`), não soma de novo. Recebimento manual soma com custo médio ponderado
  (mesma conta do sync). Saída = `EstoqueRealService.registrar_saida` (COGS no razão, mesmo caminho das
  baixas por serviço). Ajuste recebe a contagem e grava o delta.
- **Pedido copia a solicitação** (item a item, `requisition_item_id`); itens digitados com preço casam
  por código/descrição e mantêm o vínculo. Solicitação com pedido fica `atendida`.
- **Posse única** de rádio/celular/rastreador = índice parcial da frente 05; série única entre TODOS os
  equipamentos controlados.
- «Próximo do mínimo» = saldo até 20 % acima do mínimo (`MARGEM_PROXIMO`; o DGX não publica a régua).

## §4 — Oráculo

```bash
docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" --tmpfs /app/logs:rw,mode=1777 --tmpfs /app/uploads:rw,mode=1777 \
  -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env $ENVS conecta-pro-backend:latest \
  python3 /app/scripts/orq/test_oraculo_suprimentos_cadeia.py
```
ANTES (árvore do HEAD `b06669677` via `git archive`, sem a frente):
```
FALHOU: frente F9 não existe (cannot import name '_dgx_f9_suprimentos' ...) — não há cadeia de compras, estoque com mínimo/máximo nem kit
mecanismo ausente
exit=1
```
DEPOIS:
```
cadeia: Σsol=5.0000 Σped=5.0000 · recebimento manual 2 mov · NF-e 2 mov, 1 conferência · materiais conferidos na régua: 149 · rastreador posse única ok · kit JARDINEIRO: 2 × 2 = 4
TOTAL desvios: 0
OK suprimentos: solicitação→pedido→NF fecha, entrada única por chave, status == régua, posse única, kit entrega N itens
exit=0
```
Fixtures `'FIXTURE DGX F9'` (materiais `FIXF9-*`, fornecedor CNPJ 99999999000191, NF-e chave `FIXF9…`,
rastreador `FIXTURE-DGX-F9-R1`, grade/kit/entregas, COGS da saída) apagadas ao fim — sandbox conferido
com 0 sobras, `nfe_estoque_movimentos` = 1 e `nfe_compras_estoque` = 147 como antes.

Outros oráculos: `test_oraculo_vigilante_apto.py` (frente 05) **verde** (29 escalados, 0 armas sem controle).
`test_oraculo_sku_unico.py` **vermelho pré-existente** — 5 itens do `health_epi_catalog` sem linha de grade
(`sst_uniforme_grade` está vazia no sandbox); rodado também na árvore anterior: mesmo vermelho. Não é regressão.

Prova HTTP (container `teste-dgx-f9`, porta 8209, parado ao fim): `GET /api/v1/redesign/data/suprimentos`
→ 20 telas, 0 sem porta. Smoke `POST /action/*`: fornecedor → material (saldo inicial 20) → solicitação →
aprovar → pedido (30/60) → enviar → receber (entrou 3) → receber de novo **409** → saída 2 (COGS R$ 25,00,
restam 21) → ajuste → celular cadastrado → remover kit inexistente **404**. Tudo apagado pelo oráculo.

## §5 — O que NÃO foi feito e por quê

- **Não migrei** `fin_stock_items`/`inventory_items` (2 linhas de abril, sem escritor) nem `products` (867,
  catálogo comercial) para o estoque vivo. Decisão do dono (§7).
- **Não unifiquei** `suppliers` × `financial_fornecedores`: a tela mostra as duas com origem; unificar é
  migrar dado (§7).
- **NF-e sem XML (32 resumos)**: conferir baixa o pedido mas não move estoque — não há itens sem o XML.
  Manifestação (ciência/confirmação) já existe no sync; não a chamei daqui (é chamada SEFAZ, fora do escopo).
- **Custo dos planos de celular/rádio** aparece só na tela `comunicacoes-moveis` (painel), não na tela de
  Custos do Financeiro: colocar lá exigiria editar `_fin_custos.py` (outro módulo) ou criar linha em
  `financial_custos_recorrentes` — o que, pela F11, geraria título. O brief pede sem título.
- **Frente 10 intocada**: «entregar kit da função» é uma tela nova que chama `uniforme_entrega_lote`; o
  formulário original de lote não ganhou o seletor de função.
- **Sem NCM/CFOP/impostos no pedido**; sem cotação (as `purchase_quotations` do WhatsApp seguem à parte).
- **Sem Solicitação de Materiais** (retirada de almoxarifado por posto) do DGX — «Movimentar estoque → saída
  com destino» cobre o caso hoje.
- `requisicoes` (JSON) virou alias da solicitação; menu do módulo ainda diz «Requisições». JSON proposto (§7).

## §6 — Como o Jordan testa amanhã

1. `/redesign/suprimentos` → grupo **Materiais & estoque → Estoque**: 147 materiais; a legenda conta os
   6 status (hoje todos «Mínimo não informado»). Em **Materiais**, clique Editar numa linha, informe mín/máx
   → Estoque muda de status.
2. **Fornecedores → Novo fornecedor** (ou use um dos 60). **Compras → Nova solicitação**: título, posto,
   itens `78225 | 2 | reposição`. Em **Solicitações** → Aprovar.
3. **Compras → Novo pedido**: escolha a solicitação aprovada, fornecedor, condição 30/60 → **Pedidos** → Enviar.
4. **Compras → Notas fiscais de entrada**: numa NF-e «completo/lançado» do mesmo fornecedor → Conferir
   recebimento (o pedido de mesmo valor vem sugerido). Conferir de novo → recusa. Ou em **Pedidos** → Receber
   (manual): os itens com código entram no estoque.
5. **Movimentar estoque**: saída de 1 unidade de um material com saldo → a baixa aparece em
   Financeiro → «Estoque — movimentos» e o COGS no razão.
6. **Equipamentos controlados → Novo rádio/celular/rastreador** → em **Comunicações móveis** Entregar a
   alguém → tentar entregar de novo → recusa (posse única) → Devolver.
7. **Kits → Adicionar item ao kit** (função + SKU da grade da frente 10) → **Entregar kit da função** →
   Gestão de Pessoas → Uniforme/EPI → Entregas mostra N solicitações por pessoa.

## §7 — Decisões que só o dono pode tomar

1. **Unificar fornecedores**: `financial_fornecedores` (12 padrões de extrato) → coluna em `suppliers`
   (8 deles não têm cadastro: PPA Amazonas, Wide, Eletrônica Melo, WMG, Futura, Amazonas Energia, Ambar,
   Águas de Manaus/do Amazonas, Sólides — alguns são concessionárias, não fornecedores de material).
2. **Aposentar** `fin_stock_items`/`fin_stock_movements`/`fin_stock_inventories`/`inventory_items`
   (semente de 12/04 sem escritor) e as abas do Financeiro que as leem, ou migrar as 2 linhas.
3. **32 NF-e só em resumo** (R$ 13.4 mil, abr–set/2026; Maraitt Locadora 8, OCSEG 5, L J Guerra 4, B A
   Elétrica 3…): manifestar ciência para baixar o XML e entrar no estoque? Hoje o sync só processa XML completo.
4. **Régua «Próximo do mínimo»**: 20 % acima do mínimo (chute da casa). Trocar por valor absoluto ou %.
5. **Mínimo/máximo dos 147 materiais**: todos «Mínimo não informado». Quem preenche, e para quais grupos.
6. **Custo dos planos de celular/rádio**: aparecer também em Financeiro → Custos (leitura) exige tocar
   `_fin_custos.py`; ou entrar como conta fixa da F11 (gera título — hoje proibido pelo brief).
7. **JSON de menu** (`frontend/src/app/redesign/_modules/suprimentos.json`) proposto — o orquestrador aplica:
   ```json
   {"menu":[
     {"id":"visao","label":"Visão geral","icon":"M3 3h7v7H3zM14 3h7v5h-7zM14 12h7v9h-7zM3 16h7v5H3z"},
     {"id":"solicitacoes-compra","label":"Solicitações de compra","icon":"M6 6h15l-1.5 9h-12zM6 6 5 2H2"},
     {"id":"pedidos-compra","label":"Pedidos de compra","icon":"M3 3v18h18"},
     {"id":"nf-entrada","label":"Notas fiscais de entrada","icon":"M3 3v18h18"},
     {"id":"materiais","label":"Materiais","icon":"M21 8 12 3 3 8v8l9 5 9-5zM3 8l9 5 9-5M12 13v8"},
     {"id":"estoque","label":"Estoque","icon":"M21 8 12 3 3 8v8l9 5 9-5zM3 8l9 5 9-5M12 13v8"},
     {"id":"fornecedores","label":"Fornecedores","icon":"M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M9 3a4 4 0 1 1 0 8 4 4 0 0 1 0-8"},
     {"id":"comunicacoes-moveis","label":"Comunicações móveis","icon":"M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"},
     {"id":"rastreadores","label":"Rastreadores","icon":"M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"},
     {"id":"kit-uniforme","label":"Kit de uniforme","icon":"M21 8 12 3 3 8v8l9 5 9-5zM3 8l9 5 9-5M12 13v8"}
   ],"mod":{"icon":"M21 8 12 3 3 8v8l9 5 9-5zM3 8l9 5 9-5M12 13v8","name":"Suprimentos","desc":"Compras, materiais, fornecedores e equipamentos"}}
   ```
   (`requisicoes` e `almoxarifado` saem: viraram `solicitacoes-compra` e `materiais`/`estoque`; os forms
   continuam no `EXTRA_MENU`.) Enquanto isso, o `EXTRA_MENU` já dá porta a todas as 17 telas.
