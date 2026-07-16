# Execução Fases 0–3 — Liberação do Módulo Financeiro
**Conecta PRO ERP · 16/07/2026 · dev → QA (CIC) para re-teste**
Referências: `ALINHAMENTO_DEV_QA_FINANCEIRO_2026-07-16.md` (plano acordado) e devolutiva do CIC
(FIN-05 valor>0 = P1; guard-rail anti-regressão do Decimal; saldo por tolerância).

---

## 1. Status: FASES 0, 1, 2 e 3 CONCLUÍDAS — deployadas duráveis e verificadas

| Fase | Conteúdo | Status |
|---|---|---|
| 0 | Raiz Decimal + FIN-01 + FIN-02 | ✅ no ar (blue/green + build frontend) |
| 1 | FIN-03, FIN-04, FIN-05, FIN-10 | ✅ no ar |
| 2 | FIN-06, FIN-08, FIN-09 (FIN-07 diferido, ver §4) | ✅ no ar |
| 3 | pytest 16/16 + guard-rail anti-regressão | ✅ verde na imagem baked |
| 4 | Gate humano (PIX R$0,01 + emissão fiscal c/ OTP do Jordan) | ⏳ aguarda Jordan |

Deploys: 2 blue/green de backend (zero-downtime, health 200) + rebuild da imagem do
frontend (container :3001 healthy, BUILD_ID íntegro). Nenhuma alteração vive só em
`docker cp` — tudo baked.

---

## 2. O que foi corrigido (com a prova de cada um)

### RAIZ — Decimal serializado como string (a causa da família soma-string/R$0)
- **Fix:** tipo `Money`/`MoneyOpt` (`backend/modules/financial/schemas/_money.py`):
  `Annotated[Decimal, PlainSerializer(float)]` — Decimal interno (precisão e `gt=0`
  preservados), **número nativo no JSON**. Aplicado nos **13 arquivos de schema**
  do financeiro (payable, receivable, cashflow, accounting, fiscal, purchase_*,
  inventory, product, goods_receipt). Zero anotações `: Decimal` cruas restantes.
- **Prova:** `/payables/stats` → `total_value: 208630.47` (float); `/receivables/stats`
  → `529069.58` (float). Antes: `"208630.47"` (string).

### FIN-01 — Fluxo de Caixa: KPI ok, lista/gráfico vazios ✅
- **Causa dupla:** (a) backend: `CashFlowEntryRepository.list/count` aplicavam
  `condominio_id == None` → `= NULL` no SQL → 0 linhas (o summary agrega tudo);
  (b) frontend: a tela lia `entriesData.items`, mas o endpoint devolve lista pura.
- **Fix:** backend agrega tudo quando condominio None (igual summary); frontend
  trata array puro.
- **Prova:** `GET /cashflow/entries` → itens reais (`count(None)=4720`), tela recebe a lista.

### FIN-02 — Cards DRE "A Receber/A Pagar" R$0 ✅
- **Fix:** cards leem `total_value` (campo real, que agora chega como número pela raiz).
- **Prova:** A Receber ~R$529k / A Pagar ~R$208k, batendo com as telas de contas.

### FIN-03 — Fornecedor não persistia ✅ (solução: coluna denormalizada)
- **Descoberta na execução:** não era só o create — **a coluna Fornecedor estava vazia
  para TODAS as 71 contas** (o schema de lista esperava `supplier_name`, que não existia
  nem como coluna nem como property). E criar Supplier fake era inviável:
  `suppliers.cpf_cnpj` é NOT NULL + único — **não fabricamos CNPJ** (regra da casa).
- **Fix:** coluna denormalizada `payable_accounts.supplier_name` (ADD COLUMN, aditivo)
  espelhando `receivable_accounts.customer_name` + **backfill das 70 contas** com o nome
  real do Supplier vinculado + create grava o nome digitado + Response/List expõem.
  Receivable: `customer_name` agora aceito no create e gravado.
- **Prova:** lista mostra `"supplier_name":"SOLIDES TECNOLOGIA SA"`; POST com
  `supplier_name` persiste e aparece na busca (teste FIN-03 da suíte).

### FIN-04 — Projeção 30d incoerente (−R$67) ✅
- **Causa real:** projetava só **parcelas** de pagar (18 de 71 contas têm parcela) e
  partia de saldo 0, ignorando recebíveis.
- **Fix:** projeta pelas **contas em aberto** (saldo aberto por vencimento), **duas
  pontas** (pagáveis − / recebíveis +), partindo do **saldo bancário real**.
- **Prova:** projeção 30d = saldo R$67.757,29 → acumulado final R$66.021,15
  (pagáveis a vencer R$1.737,14). Coerente e explicável.

### FIN-05 — Validação de gravação ✅ (valor>0 = P1, conforme devolutiva)
- Backend: `gross_value: Field(..., gt=0)` **já rejeitava** (422) — confirmado por teste
  (0 e −10 → 422). Frontend: validação amigável `valor > 0` adicionada nos dois modais
  (erro claro antes do POST). Categoria continua opcional (por design, aceito como P2).

### FIN-06 — Enum 'pago'/'paga' ✅
- **Fix:** writer não-canônico corrigido (`nfse_entrada_controller` gravava 'pago');
  filtros do raio-x agora cobrem as duas grafias; **4 linhas normalizadas** no banco
  ('pago'→'paga'; ids registrados p/ reversão). Banco: 13 `paga`, 0 `pago`.

### FIN-08 — Faturamento regras R$0 ✅
- **Fix:** tela lê `base_value` e `value_type` ('fixo'/'percentual' PT, com tolerância a
  EN) — antes filtrava `type==='fixed'` (não existia) e somava `value/amount` (idem).
- **Prova:** Valor Fixo Total = soma real dos `base_value` (~R$65.842/regra ativa).

### FIN-09 — MCP "R$36k" hardcoded ✅
- Removido da descrição da tool `get_cashflow_status` (agora descreve "saldo ao vivo").

### FIN-10 — Registros TESTE QA ✅
- 2 registros removidos (payable "TESTE QA - nao pagar" + receivable "TESTE QA -
  nao receber", R$1 cada). Zero restantes (verificado por teste).

---

## 3. Fase 3 — Suíte de regressão (16/16 PASS na imagem de produção)

`backend/tests/financial_release/` — roda com
`docker exec -e PYTHONPATH=/app conecta-pro-backend python3 -m pytest /app/tests/financial_release/ -q`

**Guard-rail anti-regressão do Decimal (o que o CIC pediu):**
- `test_no_bare_decimal_annotations_in_financial_schemas` — **lint que FALHA** se
  qualquer schema financeiro voltar a anotar campo como `Decimal` cru (aponta
  arquivo:linha e manda usar `Money`).
- 3 testes funcionais: stats/list/projection serializam money como número no JSON.
- 1 teste garantindo que o `Money` **não afrouxou** o `gt=0` (FIN-05).

**Regressões FIN (contra a API real):** FIN-01 (lista agrega sem condominio, valores
float), FIN-02 (stats número >0, payables e receivables), FIN-03 (cria com fornecedor →
persiste → aparece na lista → limpa), FIN-04 (acumulado parte do saldo real **por
tolerância** de R$5k, nunca ao centavo — duas pontas presentes), FIN-05 (0 e −10 → 422),
FIN-06 (zero 'pago' no banco), FIN-09 (sem 'R$36k' no fonte), FIN-10 (zero TESTE QA).

---

## 4. Pendências conhecidas (não bloqueiam o re-teste)

- **FIN-07 (React #418)** — cosmético, aceito como dívida P2 pelo próprio CIC no
  prompt de re-teste ("aviso React #418 no console (cosmético)"). Não tratado nesta rodada.
- **Categoria opcional no create** — comportamento por design (P2, conforme alinhamento).

## 5. Fase 4 — o gate humano (pronto para o Jordan)

Tudo preparado; conclusão é humana por regra da casa (dinheiro que sai = OTP):
1. **PIX real simbólico R$0,01** — Pagamentos & Transferências → beneficiário conhecido
   → preparar → **Jordan digita o OTP** → comprovante PDF gera e concilia no extrato.
2. **Emissão fiscal de homologação** — 1 NFS-e de teste com aprovação do Jordan.

## 6. Instrução de re-teste para o CIC

Re-rodar o prompt `CIC_RETESTE_FINANCEIRO_2026-07-16.md` + verificar especificamente:
- Fluxo de Caixa: lista e gráfico POPULADOS (não "0 lançamentos") com KPIs consistentes.
- Relatórios/DRE: cards A Receber ~R$529k / A Pagar ~R$208k (bater com telas de contas).
- Contas a Pagar: coluna Fornecedor preenchida (ex.: SOLIDES TECNOLOGIA SA); criar conta
  com fornecedor novo → nome persiste após refresh; valor 0 → erro amigável.
- Projeção: valor coerente com saldo (~R$66k em 30d), não mais −R$67.
- Faturamento: Valor Fixo Total > 0 e valores por regra.
- Saldo-âncora: **mesma fonte, por tolerância** (Inter é live; 67–68k no momento da escrita).
- Hard refresh (Ctrl+Shift+R) antes de cada tela — houve deploy novo.

---
*Suíte: 16/16 PASS · Deploys: blue/green ×2 (zero downtime) + frontend image rebuild ·
Dados alterados no banco: backfill supplier_name (70), normalização status (4, ids
registrados), remoção TESTE QA (2). Nenhum dado financeiro real alterado.*
