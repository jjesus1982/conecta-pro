# Extrato Inter unificado — Plano

> Execução inline, oráculo (curl/query vs banco). Bookkeeping — não move dinheiro.

**Goal:** `bank_transactions` vira fonte única e fresca do Inter (bridge de `inter_transactions`) + re-sync em janelas.

## Task 1 — Bridge `espelhar_inter_em_bank_transactions()` (núcleo)
**File:** `modules/integrations/inter/inter_sync_service.py`
- [ ] Snapshot antes: `count(*)` e `max(transaction_date)` de créditos Inter em bank_transactions.
- [ ] Add método: INSERT…SELECT de `inter_transactions` → `bank_transactions`, dedup por `external_id`=it.id (NOT EXISTS) E também por (transaction_date, amount, description) p/ não duplicar a carga antiga sem external_id. type C→credit/D→debit, amount=abs(valor), bank_account_id=conta 077.
- [ ] Rodar no container (docker cp + import). Oráculo: créditos recentes (15/07 R$55.467,62) agora em bank_transactions; rodar 2x → 0 novos na 2ª (idempotência).

## Task 2 — Re-sync em janelas `sincronizar_extrato_periodo(inicio, fim)`
**File:** mesmo service
- [ ] Refatorar `sincronizar_extrato` p/ aceitar `(start,end)` OU add helper que fatia em 30d e chama a lógica existente.
- [ ] `sincronizar_extrato_periodo(2026-01-01, hoje)` em blocos de 30d → depois Task 1 (bridge).
- [ ] Oráculo: bank_transactions Inter cobre jan-jul, último = hoje.

## Task 3 — Gatilho redesign (gated) + tela
**File:** `redesign_builders/financeiro.py` (ação) + `_fin_bancos.py` (tela) + `_fin_grupos.py` (menu)
- [ ] Ação `/action/sincronizar-extrato` → `sincronizar_extrato_periodo` + bridge. Confirm leve (leitura do banco).
- [ ] Tela "Sincronizar extrato" (form) no grupo Bancos.
- [ ] Deploy + verificar na rota.

## Task 4 — Simplificar conciliação (fonte única)
**File:** `conciliacao_liquido_service.py`
- [ ] SÓ depois do oráculo provar bank_transactions completo: remover a união com inter_transactions; Inter lê só bank_transactions; persist do Inter volta.
- [ ] Oráculo: % casado igual ou maior; persist do Inter funciona.

## Self-review
Cobre spec: bridge (T1), janelas (T2), gatilho (T3), simplificação (T4). Ordem por risco: bridge provado antes de simplificar. Idempotência testada rodando 2x.
