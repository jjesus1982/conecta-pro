# REBUILD FOLLOWUP — COMPLETO (bloco 2B + consolidação)

- **Data:** 2026-06-10
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Imagem nova:** `conecta-pro-backend:latest` = **`5a14e5dbe456`**
- **Status:** ✅ **COMPLETO.** 9 containers na imagem nova, running, health 200. Rotina followup ATIVA no beat (gate LGPD desligado).

---

## Bloco 2B — celery + flower na imagem nova
- Recriados: `celery-beat`, `celery-operacional`, `celery-nfse`, `celery-sefaz`, `celery-batch`, `celery-priority`, `celery-integrations`, `flower`.
- **Todos os 9 containers** = `5a14e5dbe456`, `status=running`.
- **Rotina followup ATIVA:** `crm-followup-proposals-0830` presente no `beat_schedule` do **celery-beat** (8:30 diário, fila gov.batch).
- **Flag confirmada nos workers:** `FOLLOWUP_AUTO_SEND = False` (gate LGPD) no celery-batch.
- **Gate final:** `/health` **200**.

| Container | Imagem | Status |
|-----------|--------|--------|
| backend + 7 celery + flower (9) | `5a14e5dbe456` | running |

## Mudanças durabilizadas neste rebuild
1. **Fix create de proposta** (`eb60ea82`) — atômico, sem lazy-load async.
2. **Migration `proposal_followups`** (`dd57f47b`) — arquivo bakado (banco já estava no head sprint92).
3. **Rotina `crm.followup_proposals`** (`38baa711`) — task + beat_schedule (8:30) + include; **gate LGPD `FOLLOWUP_AUTO_SEND=False`** (só gera lista→Telegram, NÃO contata cliente).
4. **Preservados:** 4 tools WhatsApp (incl. transferir_conversa), e-mail de visita, triagem, fix campo Visita, SQLi fix.

## Jornada
| Bloco | Ação | Resultado |
|-------|------|-----------|
| 1 | backup + tag + build + validação efêmera | `5a14e5db` validada, produção intocada |
| 2A | swap + recreate backend | backend na img nova, healthy, POST `/campo/visitas/` 201, alembic head sprint92 |
| 2B | recreate celery + flower | 9 containers alinhados, **rotina followup ativa no beat**, flag FALSE, health 200 |

## Prova de durabilidade
Containers recriados **a partir da imagem**; a rotina followup aparece no `beat_schedule` do celery-beat e a task está nos workers — o agendamento 8:30 agora roda bakado. Recreate não reverte mais.

## Comportamento em produção (a partir de agora)
- **Todo dia às 08:30**, o `crm.followup_proposals` roda no celery-batch: seleciona propostas vencidas (status='sent' AND responded_at IS NULL, cadência 2d/7d), registra em `proposal_followups`, e **envia a lista ao Jordan via Telegram**. **NÃO contata o cliente** (`FOLLOWUP_AUTO_SEND=False`).
- Como `proposals` está vazia hoje, a 1ª execução tende a mandar "nenhuma proposta vencida" — passa a listar quando houver propostas reais enviadas (`/send`).

## Rollback disponível
- Imagem: `pre-rebuild-followup-20260610` = `c4bde53` (anterior) · `pre-rebuild-transfer-20260609` = `b18575b9` · `pre-rebuild-fvisita-20260609` = `5958168f`.
- Banco: `pre_rebuild_followup_20260610_072754.dump`.
- Reverter: `docker tag conecta-pro-backend:pre-rebuild-followup-20260610 conecta-pro-backend:latest` + recreate.

## Observações honestas (já no 2A)
- Gates 502 no 2A foram transitórios (boot); após healthy → 200/200/401, POST visitas 201.
- Warning de orphan containers: benigno (`--no-deps`).

## Estado final
- 9 containers em `5a14e5db`, running, **health 200**.
- `AGENT_ENABLED=true` (4 tools), `FOLLOWUP_AUTO_SEND=False` (gate LGPD), alembic head `sprint92`.
- **Sem pendências de rebuild.**

---

## Resumo
- REBUILD completo: 9 containers na `5a14e5db` (fix create + migration + rotina followup bakados, anteriores preservados). ✅
- Rotina followup **ativa no beat (8:30)**, flag LGPD desligada, health 200. ✅
- Backup + tags de rollback no lugar. ✅
- Fim das pendências de rebuild. A rotina passa a rodar automática (só lista, sem contatar cliente).

*Rebuild FOLLOWUP completo.*
