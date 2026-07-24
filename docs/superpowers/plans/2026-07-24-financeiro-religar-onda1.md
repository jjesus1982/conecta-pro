# Financeiro Onda 1 "RELIGAR" — Implementation Plan

> **Execução:** inline (executing-plans), solo T1. Verificação = ORÁCULO (curl da rota vs query no banco) + browser E2E. Projeto NÃO usa pytest.

**Goal:** Religar 6 capacidades financeiras que já existem no backend mas estão desligadas por wiring/agendador/re-apontamento.

**Architecture:** Editar host → deploy blue-green (backend) / rebuild (frontend) → verificar pela rota da tela (curl vs query) → commit por item. Padronizar leitura no razão `accounting_entries` (populado), não `fin_journal_entries` (vazio).

**Tech Stack:** FastAPI + SQLAlchemy + Postgres + Next.js redesign (`_fin_*` builders + ModuleView).

## Global Constraints (verbatim da spec)
- Nunca fabricar dado: oráculo = exibido == banco. Vazio real = "aguardando dado".
- Dinheiro que SAI = gate OTP. Cobrança que fatura cliente = gate humano. Nunca testar caminho feliz.
- Deploy backend blue-green; frontend rebuild+purge static; verificar pela rota da tela, cache-bust.
- Mexer só no que serve a Onda 1.

---

## File map
- `modules/financial/services/cashflow_ai_service.py` — wrappers públicos de risco/oportunidade (Task 1)
- `modules/operacional/controllers/redesign_builders/_fin_visao.py` — consumir wrappers certos (Task 1)
- `modules/financial/controllers/bank_transaction_controller.py` + `repositories/cashflow_repository.py` — fix 500 (Task 2)
- `modules/operacional/controllers/redesign_builders/_fin_bancos.py` — expor conciliação + upload OFX (Task 2, 3)
- `modules/financial/controllers/bank_transaction_controller.py` — fix OFX enum/coluna (Task 3)
- `modules/financial/services/balance_sheet_service.py` (ou novo caminho) + `_fin_contabil.py` — Balanço do razão certo (Task 4)
- `modules/financial/services/budget_service.py` + `_fin_custos.py` — Orçado×Realizado (Task 5)
- `_fin_receber.py` + ação gated — cobrança recorrente preview+confirm (Task 6)

---

## Task 1: Insights (fix wiring) — risco baixo, primeiro
**Files:** `cashflow_ai_service.py` (add wrappers), `_fin_visao.py:55-57` (usar wrappers + escopo real)
**Interfaces produz:** `CashFlowAIService.identificar_riscos(empresa_id=None, horizonte_dias=90) -> list`, `identificar_oportunidades(...) -> list`.
- [ ] Ler `cashflow_ai_service.py:447 _identify_risks` e `:504 _identify_opportunities` — assinatura real + o que filtram (condominio_id?).
- [ ] Add wrappers públicos que chamam os privados com escopo empresa/global (não condomínio).
- [ ] Corrigir `_fin_visao.py:55-57` para chamar os wrappers com escopo certo.
- [ ] Deploy blue-green.
- [ ] **Oráculo:** curl `/redesign/data/financeiro` → grupo Visão tem riscos/oportunidades reais; provar que vêm de query (inadimplência/vencimento), não vazio nem hardcoded.
- [ ] Browser E2E: painel Visão mostra os cards.
- [ ] Commit.

## Task 2: Conciliação automática exposta + bug 500
**Files:** `bank_transaction_controller.py:149` + `cashflow_repository.py:277` (assinatura), `_fin_bancos.py` (tela)
- [ ] Grep callers de `get_pending_reconciliation` (não quebrar outro).
- [ ] Alinhar assinatura: controller passa datas OU repo aceita `limit` opcional. Escolher o menor blast radius.
- [ ] Deploy; **oráculo:** `GET /financial/bank-transactions/pending-reconciliation` → 200; nº pendentes == query `bank_transactions where reconciliation_status='pendente'`.
- [ ] Expor no `_fin_bancos.py` tela "Conciliação": lista pendentes + botão auto-match (`/conciliar/auto`) + justificar.
- [ ] Deploy + rebuild frontend; browser E2E; provar nº conciliados==query.
- [ ] Commit.

## Task 3: Import OFX (2 bugs) + upload
**Files:** `bank_transaction_controller.py:580,584,507,516` (enum/coluna), `_fin_bancos.py` (upload)
- [ ] Trocar `TransactionCategory.OUTROS`→ por sinal (crédito→OUTRAS_RECEITAS, débito→OUTRAS_DESPESAS); `statement_reference`→`reference` nas 2 rotas.
- [ ] Deploy; **oráculo:** subir OFX de teste (arquivo isolado, NÃO produção) → 200; linhas gravadas == linhas do arquivo (query).
- [ ] Expor upload OFX na tela Bancos.
- [ ] Commit.

## Task 4: Balanço Patrimonial (re-apontar razão)
**Files:** caminho que lê `accounting_entries` (espelhar `_dre_simplificado`), `_fin_contabil.py` (aba)
- [ ] Implementar agregação Ativo/Passivo/PL por natureza da conta a partir de `accounting_entries`.
- [ ] Expor aba "Balanço Patrimonial" no grupo Fiscal & Contábil.
- [ ] Deploy + rebuild; **oráculo:** Ativo == Passivo+PL (fecha); valores == soma do razão via query. Se não fechar, exibir "não fechado" honesto.
- [ ] Browser E2E; commit.

## Task 5: Orçado × Realizado
**Files:** `budget_service.py` (realizado←accounting_entries; orçado←financial_orcamentos), `_fin_custos.py` (aba)
- [ ] Mapear chave `financial_orcamentos` (KV) ↔ conta/categoria do razão.
- [ ] Realizado por categoria/período do razão; comparar com orçado (variância, %, sinal, alerta estouro).
- [ ] Expor aba no grupo Custos & Orçamento.
- [ ] Deploy + rebuild; **oráculo:** realizado==query razão; orçado==valor KV. Sem orçamento → "sem orçamento" honesto.
- [ ] Browser E2E; commit.

## Task 6: Cobrança recorrente — ação GATED (preview + confirm)
**Files:** `_fin_receber.py` (tela preview + ação), ação gated no builder
- [ ] Expor `/preview` (read-only) mostrando clientes/valores/banco credor do mês.
- [ ] Ação "Gerar cobranças do mês" com CONFIRMAÇÃO humana obrigatória → POST real `recurring_billing`. Sem OTP (não é dinheiro que sai) mas confirm claro "emite cobranças reais aos clientes".
- [ ] Deploy + rebuild; **oráculo: SÓ o /preview** (preview==query clientes ativos/MRR). **NUNCA** executar o POST real (fatura clientes).
- [ ] Browser E2E do preview + do fluxo de confirmação (parar antes de confirmar). Commit.

---

## Self-review (spec coverage)
Spec item 1↔Task 1 · item 4↔Task 2 · item 5↔Task 3 · item 2↔Task 4 · item 3↔Task 5 · item 6↔Task 6. Todos cobertos. Ordem por risco crescente. Sem placeholders (cada task tem arquivo:linha + método de verificação real do projeto). Cobrança recorrente nunca testada no caminho feliz (constraint respeitada).
