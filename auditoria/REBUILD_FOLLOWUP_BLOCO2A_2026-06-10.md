# REBUILD FOLLOWUP — Bloco 2A (swap + recreate backend)

- **Data:** 2026-06-10
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Promover a imagem nova a `:latest` e recriar o backend (baka fix create + migration + rotina followup).
- **Status:** ✅ **Bloco 2A OK.** Backend na imagem nova `5a14e5db`, fixes duráveis, alembic chain íntegra, gates 200/200/401, POST `/campo/visitas/` 201.

---

## 1. Etapas
| Etapa | Resultado |
|-------|-----------|
| Swap `:latest` | ✅ `5a14e5dbe456` · rollback `pre-rebuild-followup-20260610` = `c4bde53` preservado |
| Recreate backend | ✅ running na img `5a14e5db`, **healthy** |
| Fixes persistem | ✅ fix create · tasks.py · flag `FOLLOWUP_AUTO_SEND=False` · migration sprint92 · transferir_conversa |
| Alembic chain | ✅ `current` = `sprint92_proposal_followups (head)` · `heads` = 1 (íntegra) |
| **Gates pós-healthy** | `/health` **200** · webhook token válido **200** · webhook token errado **401** |
| **POST `/campo/visitas/`** (com auth) | **201** (fix campo bakado) |
| 4 tools | ✅ consultar_cnpj, buscar_cliente, agendar_visita, transferir_conversa |
| Limpeza | visita de teste deletada → `visitas` = **0** |

## 2. Prova de durabilidade
Backend recriado **a partir da imagem** (não docker cp): fix create + rotina followup (flag OFF) + migration presentes, 4 tools, POST visitas 201, alembic no head sprint92. Recreate não reverte mais.

## 3. Incidentes honestos (bloco como enviado)
- **Gates 502 transitórios:** medidos após `sleep 20` com `HEALTH=starting`; após `healthy` → 200/200/401.
- **Warning de orphan containers** (celery/flower/staging): benigno (`--no-deps`); nada tocado — é o bloco 2B.

## 4. Estado atual
- **Backend:** `5a14e5dbe456` (tudo bakado), healthy, health 200, 4 tools.
- **Celery/flower (8 containers):** ainda na imagem antiga `c4bde53` — **importante recriá-los no 2B**, pois a rotina `crm.followup_proposals` roda no **celery-beat** (schedule 8:30) + **celery-batch** (fila gov.batch). Até o 2B, o agendamento bakado não está ativo nos workers.
- **Rollback:** `pre-rebuild-followup-20260610` (c4bde53) · banco `pre_rebuild_followup_20260610_072754.dump`.
- `FOLLOWUP_AUTO_SEND=False` (gate LGPD inalterado) · `AGENT_ENABLED=true`.

## 5. Próximo passo (bloco 2B — sob seu comando)
Recreate dos celery/flower na imagem `5a14e5db` → alinha os 9 containers e ativa a rotina followup bakada no beat/batch. **NÃO executado.**

---

## Resumo
- Swap + recreate backend na `5a14e5db` — fixes bakados e duráveis, alembic íntegra. ✅
- Gates 200/200/401, POST visitas 201, 4 tools. ✅
- Honestidade: 502 só no boot; orphans warning benigno. ✅
- Pendente: bloco 2B (celery/flower — onde a rotina realmente roda). ⏸️

*Bloco 2A concluído. Celery/flower ainda não recriados.*
