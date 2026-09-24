# DGX V5 — Fiscal/Financeiro: cadastro fiscal do serviço, formas de pagamento, limite por condição, centros de custo em árvore e relatórios PDF/Excel

**Data:** 24/09/2026 · **Branch:** `dgx/v5-fiscal-relatorios` · **Módulo:** financeiro
**Base medida:** sandbox `conecta_pro_staging` (cópia de produção de 23/09) · container `teste-dgx-v5`, porta 8245

---

## §1 — Estado antes (medido, não suposto)

| O que | Medida no sandbox (24/09) |
|---|---|
| `fin_codigos_servico` | 8 códigos semeados pela F11 (LC 116 + cTribNac + alíquota ISS). **Sem NBS, CST, classificação tributária, IBS/CBS.** |
| `fin_condicoes_pagamento` | 4 condições semeadas. **Sem `limite_valor`** — conta de qualquer valor passava em qualquer condição. |
| Forma de pagamento | `payment_methods` **existe** (modelo `financial/models/payment_method.py`) com `code, name, payment_type, bank_account_id, ativo` e **0 linhas**. `payable_accounts.payment_method_id`, `payable_payments.payment_method_id`, `receivable_payments.payment_method_id` e `suppliers.default_payment_method_id` já apontavam para ela — **sem nada para apontar e sem tela**. |
| Valores de forma de pagamento REALMENTE em uso | `inter_payments.payment_type`: `pix` (31), `boleto` (16). `payable_payments.payment_method_name`: NULL em 6/6. `receivable_payments.payment_method_name`: NULL em 10/10. `commission_payments.payment_method`: 0 linhas. **Total de valores distintos: 2.** |
| `fin_cost_centers` | **0 linhas**, mas a tabela já tinha `parent_id`, `level` e `full_path`. Sem tela. |
| Centro de custo "de fato" | `bank_transactions.category` — 20 categorias distintas nas saídas (Diaristas VT+VR 1517, folha_pagamento 797, Folha 720, Fornecedor 409, Impostos 104…). `payable_accounts.cost_center` NULL em 369/369. |
| `orcamento-vs-realizado` (F11) | Só falava por categoria do extrato; `filterCol: 1` (Mês). |
| Relatórios financeiros | `relatorios.py` → `/api/v1/financial/relatorios/{dre,balancete,fluxo-caixa}/pdf` (timbrado via `relatorio_financeiro_pdf.gerar_relatorio_pdf`). **Nenhum relatório de contas a pagar/receber/fixas, nenhum agrupamento, nenhum Excel.** |
| `openpyxl` no container | 3.1.5 ✅ · `reportlab` ✅ (confirmado por `docker run … python3 -c "import openpyxl, reportlab"`). |
| Emissão de NFS-e | `nfse_nacional._build_dps_xml` monta `<cNBS>120032900</cNBS>` e `<cTribMun>100</cTribMun>` **FIXOS**; o `cTribNac` vem de `dps.servico.codigo_tributacao_nacional` (do chamador). `nfse_manaus` usa `nfse.servico.codigo_servico`. **Nenhum dos dois lê `fin_codigos_servico`.** |

## §2 — O que o DGX tem (linhas do `lacunas/faturamento_financeiro.md`)

- «Tipos de serviço com NBS, CST, CST PIS/COFINS, classificação tributária, **incidência IBS**» (`/Servicos`) → TEMOS PARCIAL.
- «Centros de custo hierárquicos (pai/filho, descendentes)» (`/CentrosCusto`) → TEMOS PARCIAL.
- «Condições de pagamento com **limite de valor**» (`/CondicoesPagamento`) — o servidor do trial **recusa conta a receber acima do limite da condição** → TEMOS PARCIAL.
- «Formas de pagamento (`boleto` bool, forma de lançamento)» (`/FormasPagamento`) → TEMOS PARCIAL.
- «Relatórios: contas a pagar (6 agrupamentos), a receber (3), fluxo de caixa (4 modelos, PDF/Excel/Word), centro de custo, plano de contas, contas fixas» → TEMOS PARCIAL.

## §3 — O que foi feito

### Decisões de reuso (a parte mais importante desta frente)

Três coisas que o brief mandava **criar** já existiam. Criar de novo teria feito tabela-irmã morta:

1. **`fin_formas_pagamento` NÃO foi criada.** `payment_methods` é exatamente esse cadastro, e os `payment_method_id` do módulo inteiro já apontam para ela. A lacuna era a **porta**, não a tabela. `gera_boleto` do brief = `payment_type = 'boleto'` (não virou coluna).
2. **`fin_cost_centers.pai_id` NÃO foi criada.** A tabela já tem `parent_id` (+ `level`, `full_path`). Uma segunda coluna para a mesma coisa é como se perde a árvore.
3. **NBS/CST/IBS/CBS não foram ligados à emissão.** O XML nacional carrega `cNBS` fixo; ligar o cadastro **mudaria a nota mandada ao fisco**. É decisão do dono (§7). O oráculo trava exatamente isso.

### Arquivos

| Arquivo | O que |
|---|---|
| `backend/modules/operacional/controllers/redesign_builders/_dgx_v5_fiscal_relatorios.py` | **novo** — DDL, 6 telas, 4 ações, endpoint GET de relatório, PDF/Excel, regras puras (`ancestrais`, `arvore_valida`, `dados_relatorio`, `relatorio_pdf`, `relatorio_xlsx`). |
| `_dgx_f11_financeiro.py` | campos fiscais em `codigos-servico` (+ exigência de `origem_regra`), `limite_valor` em `condicoes-pagamento` (+ **422** em `payable-condicao`/`receivable-condicao`), select de forma de pagamento gravado no título, `agrupar_por_centro()` e o seletor «Por categoria \| Por centro» em `orcamento-vs-realizado`. `_ensure` chama o `_ensure` da V5 **no fim** (garante a ordem CREATE → ALTER). |
| `_fin_grupos.py` | 6 abas novas, **no FIM** de cada grupo. |
| `financeiro.py` | plug: `await _v5.telas(db, out)` antes de `montar_grupos` + `router.include_router(_v5r.router)`. |
| `backend/scripts/orq/test_oraculo_v5_fiscal_relatorios.py` | **novo** — oráculo (22 checagens). |

### DDL que o `_ensure` aplica em produção no 1º acesso (tudo idempotente)

```sql
ALTER TABLE fin_codigos_servico ADD COLUMN IF NOT EXISTS nbs text;
ALTER TABLE fin_codigos_servico ADD COLUMN IF NOT EXISTS cst_iss text;
ALTER TABLE fin_codigos_servico ADD COLUMN IF NOT EXISTS cst_pis text;
ALTER TABLE fin_codigos_servico ADD COLUMN IF NOT EXISTS cst_cofins text;
ALTER TABLE fin_codigos_servico ADD COLUMN IF NOT EXISTS classificacao_tributaria text;
ALTER TABLE fin_codigos_servico ADD COLUMN IF NOT EXISTS incide_ibs boolean;
ALTER TABLE fin_codigos_servico ADD COLUMN IF NOT EXISTS incide_cbs boolean;
ALTER TABLE fin_codigos_servico ADD COLUMN IF NOT EXISTS aliquota_ibs numeric(5,2);
ALTER TABLE fin_codigos_servico ADD COLUMN IF NOT EXISTS aliquota_cbs numeric(5,2);
ALTER TABLE fin_codigos_servico ADD COLUMN IF NOT EXISTS origem_regra text;
ALTER TABLE fin_condicoes_pagamento ADD COLUMN IF NOT EXISTS limite_valor numeric(14,2);
CREATE TABLE IF NOT EXISTS fin_cost_center_categorias (
    cost_center_id uuid NOT NULL, categoria text NOT NULL PRIMARY KEY,
    created_at timestamptz DEFAULT now());
CREATE INDEX IF NOT EXISTS ix_cc_categorias_centro ON fin_cost_center_categorias (cost_center_id);
ALTER TABLE receivable_accounts ADD COLUMN IF NOT EXISTS payment_method_id uuid;
```

Seed: 9 linhas em `payment_methods` (`pix, boleto, ted, dinheiro, cartao_credito, cartao_debito, debito_automatico, transferencia, outro`) por `WHERE NOT EXISTS (… code …)` — nunca duplica, nunca sobrescreve o que o Jordan editar.
**Nenhum valor fiscal é semeado**: NBS/CST/IBS/CBS nascem NULL porque não há fonte. Inventar 0/false num campo fiscal é pior que deixar vazio.

### Telas (deep-link `/redesign/financeiro?t=<grupo>` → aba)

| id | grupo | o que |
|---|---|---|
| `formas-pagamento` | `g-cadastros` | tabela sobre `payment_methods` com «em uso» (quantos títulos/baixas apontam), editar e inativar. |
| `forma-pagamento-nova` | `g-cadastros` | form. |
| `centros-custo` | `g-custos` | árvore (indentada por `level`), categorias ligadas, nº de filhos. |
| `centro-custo-novo` | `g-custos` | form com select de pai; recusa pai inexistente e profundidade > 8. |
| `centro-custo-categoria` | `g-custos` | liga/desliga categoria do extrato ↔ centro. |
| `relatorio-financeiro` | `g-visao` | form (tipo, período, agrupamento, PDF/Excel) + 5 `doc` de atalho do mês corrente. |

Telas **estendidas** (mesmo id, sem tela nova): `codigos-servico` (3 colunas novas + 10 campos no form), `condicoes-pagamento` (coluna e campo «Limite»), `orcamento-vs-realizado` (filtro «Visão: Por categoria \| Por centro»), `registrar-conta-pagar` / `registrar-conta-receber` (select «Forma de pagamento»).

### Endpoint

`GET /api/v1/redesign/relatorio-financeiro/{tipo}?de=&ate=&agrupar=&fmt=pdf|xlsx` (gate `module:financeiro`)

| tipo | agrupamentos |
|---|---|
| `contas-pagar` | `fornecedor` · `vencimento` · `centro` · `categoria` |
| `contas-receber` | `cliente` · `vencimento` · `status` |
| `fluxo-caixa` | `dia` · `semana` · `mes` |
| `contas-fixas` | `categoria` |

PDF = `relatorio_financeiro_pdf.gerar_relatorio_pdf` (o timbrado que a casa já usa em DRE/balancete — **não** um segundo gerador). Excel = `openpyxl`, uma linha por lançamento + subtotal por grupo + total, coluna de valor com `#,##0.00`.

## §4 — Oráculo

```bash
docker run --rm --network conecta-staging-network \
  -v "$WT/backend:/app:ro" -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 \
  --env-file /opt/conecta-pro/.env -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \
  conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_v5_fiscal_relatorios.py
```

**VERMELHO** (árvore em `HEAD`, sem o módulo — `git archive HEAD backend` + só o oráculo por cima):

```
(a) XML da NFS-e: OK — byte-idêntico
FALHOU: módulo _dgx_v5_fiscal_relatorios não importa: cannot import name '_dgx_v5_fiscal_relatorios'
        from 'modules.operacional.controllers.redesign_builders'
TOTAL v5_fiscal_relatorios: 1 checagens · 1 falha(s)
```

(O bloco (a) — a trava do XML — **nasce verde de propósito**: ele existe para provar que a frente NÃO mudou a nota.)

**VERDE** (esta branch):

```
TOTAL v5_fiscal_relatorios: 23 checagens · 0 falha(s)
```

**Vizinhos, na mesma árvore:**

```
TOTAL financeiro_cadastros: 28 checagens · 0 falha(s)
TOTAL t4_faturamento_financeiro: 19 checagens · 0 falha(s)
```

O que o oráculo afirma: (a) XML da NFS-e de uma nota de teste byte-idêntico e sem nenhum campo do cadastro vazado; (b) 100% dos valores distintos de forma de pagamento já gravados no banco têm cadastro; (c) conta acima do limite da condição → **422**, abaixo → cria; (d) ciclo e órfão acusados, árvore real sadia, porta recusa pai inexistente, filho nasce no nível 2; (e) total e contagem do relatório de contas a pagar == SQL próprio escrito no oráculo, PDF começa com `%PDF`, Excel com `PK`, rollup por centro soma certo; (f) toda tela tem aba.

Fixtures `'FIXTURE DGX V5'` / código `fixv5*` apagadas no `finally` (inclusive em falha).

### Prova por HTTP (container `teste-dgx-v5`, porta 8245 — **parado e removido**)

```
GET  /api/v1/redesign/data/financeiro                                   → 200, 9.123.853 bytes
     g-cadastros › formas-pagamento    = table «Formas de pagamento» · 9 linhas
     g-custos    › centros-custo       = table «Centros de custo (árvore)»
     g-custos    › centro-custo-categoria = form
     g-visao     › relatorio-financeiro   = form + 5 docs
     g-fiscal    › codigos-servico     = cols [… NBS, CST PIS/COFINS, Reforma …] · 16 campos no form
     g-cadastros › condicoes-pagamento = cols [… Limite …]
     g-custos    › orcamento-vs-realizado = filtros [Visão, Mês] · 95 linhas «Por categoria»
                                             + 17 «Por centro» (com 1 categoria ligada)
     registrar-conta-pagar  → payable-condicao   · campos [… condicao_id, forma_pagamento_id]
     registrar-conta-receber → receivable-fonte  · idem (a F12 delega ao _conta_com_condicao)

GET  …/relatorio-financeiro/contas-pagar?de=2026-01-01&ate=2026-12-31&agrupar=fornecedor&fmt=pdf
     → 200 · application/pdf · 60.764 bytes · começa com %PDF
GET  …/relatorio-financeiro/contas-receber?…&agrupar=cliente&fmt=xlsx
     → 200 · …spreadsheetml.sheet · 7.134 bytes · zip válido (9 entradas)

POST /action/relatorio-financeiro {contas-pagar, categoria, 01/01–31/12/2026, xlsx}
     → 200 · "306 lançamento(s) em 3 grupo(s) · total R$ 1.181.879,32"
     SQL próprio no psql:  306 | 1181879.32     ← igual, casa dos centavos

POST /action/payable-condicao  valor 1.500,00, condição com teto 1.000,00
     → 422 "Valor R$ 1.500,00 acima do limite da condição «…» (R$ 1.000,00)…"
POST /action/payable-condicao  valor 900,00 + forma_pagamento_id=pix
     → 200, 1 título · no banco: payable_accounts.payment_method_id → code 'pix'

POST /action/centro-custo-salvar  raiz            → "criado no nível 1"
POST /action/centro-custo-salvar  filho com pai   → "criado no nível 2"
POST /action/centro-custo-categoria «Folha» → raiz → "«Folha» agora pertence a …"
```

Um defeito real foi pego por esta prova e corrigido: o `UPDATE … WHERE id = ANY(CAST(:ids AS uuid[]))`
com o array em forma textual `'{uuid}'` dava **500** no asyncpg («a sized iterable container expected»).
Virou `id::text = ANY(:ids)` com lista Python — e o oráculo ganhou a checagem que trava isso (23ª).

## §5 — O que NÃO foi feito, e por quê

1. **NBS/CST/IBS/CBS não foram ligados à emissão de NFS-e.** O `<cNBS>` do XML nacional é constante (`120032900`) e o `<cTribMun>` também (`100`). Trocar por um valor de cadastro muda o documento que vai ao fisco — o mandato desta frente é *não tocar em emissão além de leitura*, e o oráculo prova byte a byte que não toquei. Fica cadastro para 2027.
2. **Nenhum valor fiscal foi semeado.** Não achei fonte defensável para o CST/NBS/classificação de cada item LC 116 desta operação. Por isso `origem_regra` é **obrigatória** quando qualquer campo da reforma é preenchido: campo fiscal sem procedência é o mesmo erro do cTribNac chutado que o fisco devolvia com E0310.
3. **Word não foi gerado** (o DGX tem PDF/Excel/Word). Ninguém aqui pediu .docx e `python-docx` não está no container; PDF e Excel cobrem o uso.
4. **O select de forma de pagamento só grava nos títulos criados pelos forms de «Registrar conta»** (`payable-condicao`/`receivable-condicao`). As telas de **baixa** (`baixar-pagavel`/`baixar-recebivel`) não ganharam o campo: mexer no corpo dessas ações é caminho de dinheiro e não estava no brief.
5. **Nenhum lançamento foi migrado para centro de custo.** `payable_accounts.cost_center` continua NULL em 369/369 e o extrato continua classificado por categoria. O centro é uma **leitura por cima** do vínculo categoria→centro; ligar 0 categorias mantém tudo exatamente como está hoje.
6. **`fluxo-caixa` do relatório lê `bank_transactions`** (o extrato real, passado) — não é projeção de vencimentos. A agenda de vencimentos futura já existe: `fluxo-caixa-agenda` (dgx t4).

## §6 — Como o Jordan testa amanhã

1. **Financeiro → Cadastros & Suprimentos → «Formas de pagamento»** — devem aparecer 9 linhas (PIX, Boleto, TED…). Clique em **Editar** numa, mude o nome, salve, recarregue. Clique em **Inativar** e veja o selo virar.
2. **Financeiro → Cadastros → «Condições de pagamento»** — Editar «30/60», preencha **Limite de valor** `1.000,00`, salve.
   Vá em **Pagar → «Registrar conta»**, descrição qualquer, valor `1.500,00`, condição «30/60» → tem de **recusar** dizendo o limite. Troque para `900,00` → passa e cria as 2 parcelas.
3. **Pagar → «Registrar conta»** — o form agora tem **Forma de pagamento**; escolha PIX e registre. A conta nasce com a forma amarrada.
4. **Fiscal & Contábil → «Códigos de serviço»** — Editar `11.02`. Os campos novos (NBS, CST ISS/PIS/COFINS, classificação, incide IBS/CBS, alíquotas) estão lá. Preencha **só o NBS** e salve **sem** origem: tem de recusar pedindo a origem da regra. Preencha a origem → salva.
5. **Custos & Orçamento → «Novo centro de custo»** — crie `01 / Pessoal` (raiz) e depois `01.01 / Portaria` com pai `01`. Abra **«Centros de custo (árvore)»**: o filho aparece indentado, o pai com 1 filho.
6. **Custos → «Ligar categoria a um centro»** — ligue `Folha` a `01 · Pessoal`. Abra **«Análise orçamentária»**: o seletor **Visão** no topo alterna «Por categoria» e «Por centro».
7. **Visão Geral → «Relatórios em PDF/Excel»** — os 5 botões do topo abrem o mês corrente. No form, escolha «Contas a pagar», agrupar por «fornecedor», período do ano, formato Excel → baixa a planilha com subtotal por fornecedor e total geral.

## §7 — Decisões que só o dono pode tomar

1. **Ligar NBS/CST/cClassTrib na emissão da NFS-e?** Hoje o XML vai com `cNBS 120032900` e `cTribMun 100` fixos para **toda** nota. Trocar por cadastro muda o documento fiscal — precisa do contador dizendo qual NBS e qual CST valem por item LC 116, e de uma emissão de homologação antes de qualquer nota real.
2. **Quem preenche os campos da reforma?** São 8 códigos de serviço × 9 campos. O sistema recusa preenchimento sem `origem_regra` de propósito. Isso é trabalho do contador, não de chute.
3. **Alíquotas IBS/CBS do ano-teste 2026** não foram semeadas — nem mesmo as do período de transição. Quando o contador der o número e a fonte, entra pela tela em minutos.
4. **A casa vai adotar centro de custo formal?** A tela existe e a árvore funciona, mas `fin_cost_centers` continua com os centros que o Jordan criar. Enquanto ninguém criar, a análise orçamentária segue falando por categoria do extrato — que é o que funciona hoje. **Não migre nada até decidir a lista de centros.**
5. **Limite por condição: qual teto, em qual condição?** Nenhum foi definido — todas continuam sem limite (comportamento idêntico ao de hoje).
6. **Relatório em Word** — se a contabilidade pedir .docx, é adicionar `python-docx` ao container. Não foi feito por ninguém ter pedido.
