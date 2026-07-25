# Extrato Inter unificado em bank_transactions + re-sync em janelas — Design (spec)

**Data:** 2026-07-25 · **Onda 2 "COMPLETAR", sub-projeto 1 (infra de banco)** · Aprovação: Jordan aceitou ("monte a spec da próxima onda e siga no loop")

## Goal
Fazer `bank_transactions` ser a **fonte única e fresca** do extrato Inter — como já é do Cora — consertando a defasagem (Inter parado em 08/07) que trava a conciliação e as telas de banco. Hoje o sync do Inter escreve em `inter_transactions` (raw) e `cashflow_entries` (fluxo), mas **não** em `bank_transactions`; o Inter lá veio de carga antiga.

## Fato que funda o design (investigado)
- `inter_transactions`: extrato Inter raw, FRESCO (2.633 linhas até hoje). Colunas: `id, data_lancamento, valor, tipo_operacao (C/D), descricao, tipo_transacao`.
- `cashflow_entries`: alimentado por `sincronizar_cashflow_do_extrato` (bridge existente, mas para o fluxo de caixa — não é bank_transactions).
- `bank_transactions`: fonte da conciliação e das telas de banco; Inter defasado em 08/07 (sem bridge). Cora (403) escreve aqui direto via `cora_sync_service`.
- Inter API limita a janela do extrato (~30 dias/req; 90 deu HTTP 400).

## Global Constraints (inegociáveis)
- Bookkeeping — **não move dinheiro**. Nunca fabricar dado; idempotente (sem duplicar).
- Deploy blue-green (lock `/tmp/conecta_deploy.lock` — sessões paralelas: esperar liberar). Verificar pelo oráculo (contagem/soma exibida == banco). Sempre planejar com superpowers.

## Arquitetura (2 unidades + 1 simplificação)

### Unidade 1 — Bridge `espelhar_inter_em_bank_transactions()` (nova, em `inter_sync_service`)
Espelha `inter_transactions` → `bank_transactions`, **idempotente** por `external_id` (= id da inter_transaction), no padrão do `cora_sync_service._registrar`:
- `bank_account_id` = conta Inter (bank_code '077').
- `transaction_type` = 'credit' se `tipo_operacao='C'` senão 'debit'.
- `amount` = `abs(valor)` (sinal já no type).
- `description` = `descricao`; `transaction_date` = `data_lancamento`.
- `reconciliation_status` = 'pendente'; `external_id` = inter_tx id (dedup: `NOT EXISTS ... WHERE external_id = it.id::text`).
- `origin`='api', `source_type`='inter_extrato', `status`='confirmado'.
- Retorna `{inseridos}`. SQL puro (INSERT…SELECT), como o cashflow bridge.

### Unidade 2 — Re-sync em janelas `sincronizar_extrato_periodo(inicio, fim)` (nova)
Cobre um período longo chamando `sincronizar_extrato` em blocos de 30 dias (a API cai em 90). Loop: `d=inicio; while d<fim: sincronizar_extrato_intervalo(d, min(d+30, fim)); d+=30`. Reusa a lógica de `sincronizar_extrato` mas com `(start,end)` explícitos (hoje ela só aceita `dias`). Depois chama a Unidade 1. Idempotente.

### Simplificação — conciliação volta a ler fonte única
Com o Inter completo em `bank_transactions`, o `conciliacao_liquido_service` pode ler Inter **só de bank_transactions** (remover a união com inter_transactions — hack da Fase 2). Persist do Inter volta a funcionar (bank_transactions tem `reconciliation_status`). Fazer **só depois** de provar que o bridge deixou bank_transactions completo (oráculo).

### Gatilho
- Ação redesign `/action/sincronizar-extrato` (gated leve, confirm) + tela em Bancos "Sincronizar extrato" (Inter janelas + Cora). Sem beat automático nesta fase (evita surpresa); Jordan dispara.
- Opcional (fase seguinte): beat diário chamando o período recente.

## Data flow
Inter API → `sincronizar_extrato` → `inter_transactions` → **bridge (nova)** → `bank_transactions` → conciliação/telas de banco. Cora → `cora_sync_service` → `bank_transactions` (inalterado).

## Error handling
- API Inter 400 em janela grande → chunk de 30 dias (Unidade 2 já fatia).
- Bridge idempotente → rodar 2x não duplica (dedup por external_id).
- Falha parcial de um chunk não aborta os demais; relatório do que sincronizou.

## Testing / Oráculo
1. Antes: contar Inter credits em bank_transactions (119, último 08/07).
2. Rodar bridge → contar de novo; provar que os créditos recentes de `inter_transactions` (ex.: 15/07 R$55.467,62 IDEAL FLORES) agora estão em bank_transactions (curl/query).
3. Re-rodar conciliação: os "sem crédito" recentes caem. Comparar antes/depois.
4. **Não** mexer em valores; só espelhar. Bookkeeping.

## Pré-mortem
- **A.** Bridge duplica transações. *Mit.:* dedup por `external_id` (NOT EXISTS); testar rodando 2x → 0 novos na 2ª.
- **B.** Sinal errado (C/D) → crédito vira débito. *Mit.:* mapear por `tipo_operacao` (fonte da verdade, como o próprio sync faz); conferir soma de créditos.
- **C.** Conta Inter errada (bank_account_id). *Mit.:* resolver por `bank_code='077'`; abortar se não achar.
- **D.** Deduplicação entre bridge e a carga antiga (mesma tx em bank_transactions sem external_id) → duplicata. *Mit.:* dedup também por (data, valor, descrição) quando `external_id` ausente na carga antiga.
- **E.** Deploy no lock (sessões paralelas). *Mit.:* esperar liberar + retry (já padrão).
- **F.** Simplificar a conciliação cedo demais (antes do bridge estar completo) → perde matches. *Mit.:* só remover a união após o oráculo provar bank_transactions completo.

## Escopo / fora
- **Nesta spec:** bridge Inter→bank_transactions, re-sync em janelas, gatilho gated, simplificação da conciliação.
- **Fora (próximas):** UI de upload OFX; beat automático; **régua de cobrança ativa** (sub-projeto próprio — dinheiro/comunicação, spec dedicada); Onda 3.
