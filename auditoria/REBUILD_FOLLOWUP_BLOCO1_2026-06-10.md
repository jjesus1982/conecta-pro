# REBUILD FOLLOWUP — Bloco 1 (backup + tag + build + validação efêmera)

- **Data:** 2026-06-10
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Bakar na imagem os 3 itens que rodavam só via docker cp: fix create proposta (`eb60ea82`) + migration `proposal_followups` (`dd57f47b`) + rotina `followup_proposals` (`38baa711`).
- **Status:** ✅ **Bloco 1 OK.** Imagem nova construída e validada (efêmera). **Produção NÃO tocada** — `:latest` segue `c4bde53`.

---

## 1. Etapas
| Etapa | Resultado |
|-------|-----------|
| Backup do banco | ✅ `backups/rebuild/pre_rebuild_followup_20260610_072754.dump` (3.8M) — TS fixo em variável |
| Tag de rollback | ✅ `conecta-pro-backend:pre-rebuild-followup-20260610` = `c4bde53893fd` (= `:latest` atual) |
| Build imagem nova | ✅ `conecta-pro-backend:rebuild-followup-20260610` = **`5a14e5dbe456`** — `:latest` intocado |
| Validação efêmera | ✅ `docker run --network none` — todos PRESENTE OK |

## 2. Validação efêmera (`--network none`, não toca produção)
Confirmado na imagem nova `5a14e5db`:
- **Novos:**
  - fix create proposta atômico (`calculate_totals` + `rollback` em `proposal_repository.py`) ✅
  - migration `sprint92` (arquivo em `alembic/versions/`) ✅
  - rotina `modules/crm/tasks.py` com `crm.followup_proposals` ✅
  - **flag `FOLLOWUP_AUTO_SEND = False`** (gate LGPD) ✅
  - `beat_schedule` entry `crm-followup-proposals` em `celery_app.py` ✅
- **Anteriores preservados:** `transferir_conversa` · SQLi fix `WHERE cc.client_id = :client_id`.
- **Imports:** `crm.tasks` (AUTO_SEND=False, task=crm.followup_proposals) · `proposal_repository` · `celery_app` → **VALIDAÇÃO EFÊMERA OK**.

## 3. Estado e rollback
- **Produção:** `:latest` = `c4bde53893fd` (inalterada). Os 3 itens ainda rodam via docker cp.
- **Imagem nova pronta:** `rebuild-followup-20260610` = `5a14e5dbe456` (tudo bakado), importa limpo, isolada da rede.
- **Rollback de imagem:** `pre-rebuild-followup-20260610` (c4bde53) · `pre-rebuild-transfer-20260609` (b18575b9) · `pre-rebuild-fvisita-20260609` (5958168f).
- **Backup do banco:** `pre_rebuild_followup_20260610_072754.dump`.

## 4. Próximo passo (bloco 2A/2B — sob seu comando)
- **2A:** swap `:latest` → `5a14e5dbe456` + recreate backend + verificação (healthy, `/health` 200, webhook 200/401, POST `/campo/visitas/` 201, 4 tools).
- **2B (importante aqui):** recreate dos celery/flower — a **rotina followup roda no celery-beat (schedule) + celery-batch (fila gov.batch)**, então alinhar os workers à imagem nova é necessário para a rotina entrar no ar bakada.
- **NÃO executado ainda.**

---

## Resumo
- Backup + tag rollback + build da imagem `5a14e5db` (3 novos + anteriores bakados) + validação efêmera **OK**. ✅
- TS fixo (sem bug de timestamp). Produção intocada (`:latest` = `c4bde53`). ⏸️
- Aguardando bloco 2A (swap backend) e 2B (celery/flower — onde a rotina realmente roda).

*Bloco 1 concluído. Produção não recriada.*
