# REBUILD TRANSFER+TRIAGEM — Bloco 2A (swap + recreate backend)

- **Data:** 2026-06-09
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Promover a imagem nova a `:latest` e recriar o backend, bakando F-VISITA.2 + transferir_conversa + triagem.
- **Status:** ✅ **Bloco 2A OK.** Backend em produção na imagem nova `c4bde53`, fixes duráveis. POST `/campo/visitas/` = **201** (com auth). 4 tools ativas.

---

## 1. Etapas
| Etapa | Resultado |
|-------|-----------|
| Swap `:latest` | ✅ `:latest` → `c4bde53893fd` · rollback `pre-rebuild-transfer-20260609` = `b18575b9` preservado |
| Recreate backend | ✅ running na img `c4bde53`, **healthy** |
| Fixes persistem | ✅ transferir_conversa · email visita · assign_team · fix campo · SQLi |
| **Gates pós-healthy** | `/health` **200** · webhook token válido **200** · webhook token errado **401** |
| **POST `/campo/visitas/`** (com auth) | **201** (`VIS-2026-00001`) — fix campo bakado e durável |
| 4 tools na imagem | ✅ consultar_cnpj, buscar_cliente, agendar_visita, transferir_conversa |
| Limpeza | visita de teste deletada → `visitas` = **0** |

## 2. Prova de durabilidade
Backend recriado **a partir da imagem** (não docker cp): 4 tools carregam, POST visitas = 201 → todos os fixes (F-VISITA.2 + transferência + triagem + fix campo + SQLi) estão **bakados**. Recreate não reverte mais.

## 3. Incidentes honestos (bloco como enviado)
1. **Gates 502 transitórios:** medidos após `sleep 20` com `HEALTH=starting`; o POST visitas deu `000` (curl exit 7), parando a cadeia `&&` no passo 6. Após aguardar `healthy`, revalidei: health 200, webhook 200/401.
2. **Passo 6 do bloco** testava só "rota existe sem auth" (esperando 401/403) — deu `000` durante o boot. Refiz o teste **com autenticação** após healthy → **201** (prova real do fix).
3. **Warning de orphan containers** (celery/flower/staging): benigno (`--no-deps`); nada tocado — é o bloco 2B.

## 4. Estado atual
- **Backend:** imagem `c4bde53893fd` (tudo bakado), **healthy**, health 200, 4 tools.
- **Celery/flower (8 containers):** ainda na imagem antiga `b18575b9` (código via docker cp) — recriados no **bloco 2B**.
- **Rollback:** `pre-rebuild-transfer-20260609` (b18575b9) · banco `pre_rebuild_transfer_20260609_222719.dump`.
- `AGENT_ENABLED=true`, webhook secret inalterado, dados intactos.

## 5. Próximo passo (bloco 2B — sob seu comando)
Recreate dos celery/flower na imagem `c4bde53` para alinhar os 9 containers. **NÃO executado.**

---

## Resumo
- Swap + recreate backend na imagem `c4bde53` — fixes bakados e duráveis. ✅
- Gates pós-healthy 200/200/401; POST `/campo/visitas/` = 201 (com auth); 4 tools. ✅
- Honestidade: gates 502 foram só boot; passo 6 sem auth deu 000 → refiz com auth = 201. Cleanup feito. ✅
- Pendente: bloco 2B (celery/flower). Backend já na `c4bde53`. ⏸️

*Bloco 2A concluído. Celery/flower ainda não recriados.*
