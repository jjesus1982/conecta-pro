# REBUILD TRANSFER+TRIAGEM — Bloco 1 (backup + tag + build + validação efêmera)

- **Data:** 2026-06-09
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Bakar na imagem os 3 itens que rodavam só via docker cp: F-VISITA.2 (`983378bb`) + transferir_conversa (`026f6f85`) + triagem (`31b8195f`).
- **Status:** ✅ **Bloco 1 OK.** Imagem nova construída e validada (efêmera). **Produção NÃO tocada** — `:latest` segue `b18575b9`.

---

## 1. Etapas
| Etapa | Resultado |
|-------|-----------|
| Backup do banco | ✅ `backups/rebuild/pre_rebuild_transfer_20260609_222719.dump` (3.8M) — TS fixo em variável (sem o bug do `$(date)` duplo) |
| Tag de rollback | ✅ `conecta-pro-backend:pre-rebuild-transfer-20260609` = `b18575b9c65e` (= `:latest` atual) |
| Build imagem nova | ✅ `conecta-pro-backend:rebuild-transfer-20260609` = **`c4bde53893fd`** — `:latest` intocado |
| Validação efêmera | ✅ `docker run --network none` — todos PRESENTE OK |

## 2. Validação efêmera (`--network none`, não toca produção)
Confirmado na imagem nova `c4bde53`:
- **Novos:** `_enviar_emails_visita` (F-VISITA.2) · `transferir_conversa` (tool) · `def assign_team` (service) · `Triagem antes de transferir` (prompt).
- **Preservados:** `agendar_visita` · fix campo `native_enum=False` · SQLi fix `WHERE cc.client_id = :client_id`.
- **Imports:** agent_service (**4 tools**: consultar_cnpj, buscar_cliente, agendar_visita, transferir_conversa) · service (`assign_team=True`) · model Visita → **VALIDAÇÃO EFÊMERA OK**.

## 3. Estado e rollback
- **Produção:** `:latest` = `b18575b9c65e` (inalterada). Os 3 itens ainda rodam via docker cp.
- **Imagem nova pronta:** `rebuild-transfer-20260609` = `c4bde53893fd` (tudo bakado), importa limpo, isolada da rede.
- **Rollback de imagem:** `pre-rebuild-transfer-20260609` (b18575b9) · `pre-rebuild-fvisita-20260609` (5958168f) · `pre-rerebuild2-20260609` (f0ee38d1).
- **Backup do banco:** `pre_rebuild_transfer_20260609_222719.dump`.

## 4. Próximo passo (bloco 2A — sob seu comando)
- Swap `:latest` → `c4bde53893fd` + `docker compose up -d --no-deps --no-build backend` + verificação pós-swap (healthy, `/health` 200, webhook 200/401, POST `/campo/visitas/` 201 com auth, 4 tools).
- Depois 2B (celery/flower). **NÃO executado ainda.**

---

## Resumo
- Backup + tag rollback + build da imagem `c4bde53` (3 itens novos + 4 anteriores bakados) + validação efêmera **OK**. ✅
- TS fixo evitou o bug de timestamp duplo dos rebuilds anteriores. ✅
- Produção intocada (`:latest` = `b18575b9`). Aguardando bloco 2A. ⏸️

*Bloco 1 concluído. Produção não recriada.*
