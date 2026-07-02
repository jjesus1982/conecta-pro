# REBUILD F-VISITA — Bloco 2A (swap + recreate backend)

- **Data:** 2026-06-09
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Promover a imagem nova a `:latest` e recriar o backend, bakando os fixes (campo `4a1296e3` + tool `agendar_visita` `87f0def9`).
- **Status:** ✅ **Bloco 2A OK.** Backend em produção na imagem nova `b18575b9`, fixes duráveis (recreate não reverte). POST `/campo/visitas/` = **201**.

---

## 1. Etapas
| Etapa | Resultado |
|-------|-----------|
| Swap `:latest` | ✅ `:latest` → `b18575b9c65e` · rollback `pre-rebuild-fvisita-20260609` = `5958168f` preservado |
| Recreate backend | ✅ `up -d --no-deps --no-build backend` → running na img `b18575b9`, **healthy** |
| Fixes persistem no container | ✅ `agendar_visita` OK · fix campo enum OK · SQLi fix preservado OK |
| **Gates pós-healthy** | `/health` **200** · webhook token válido **200** · webhook token errado **401** |
| **TESTE DECISIVO** POST `/campo/visitas/` | **201** (`VIS-2026-00001`, `agendada`) — com autenticação |
| Limpeza | visita de teste deletada → `visitas` = **0** |

## 2. Prova de durabilidade
O backend foi **recriado a partir da imagem** (não docker cp) e o `POST /campo/visitas/` retornou **201** → o fix do model `campo` (FK + enum + tipos) está **bakado**. Um recreate **não reverte mais** (antes, recreate voltaria ao model quebrado).

## 3. Incidentes honestos no bloco 2A (como enviado)
1. **Gates 502 transitórios:** o bloco mede os gates após `sleep 20`, mas o backend ainda estava `HEALTH=starting` → 502 (health/webhook) e o POST deu `000` (curl exit 7), o que **parou a cadeia `&&` no passo 6** (o passo 7/cleanup não rodou). Após aguardar `healthy`, **revalidei**: health 200, webhook 200/401.
2. **Passo 6 (TESTE DECISIVO) sem autenticação:** o curl do passo 6 **não envia header `Authorization`**, e o endpoint exige JWT → retornaria **401** ("Token não fornecido"), nunca 201. Além disso usava enum **maiúsculo** (`tipo:COMERCIAL`, `origem:LEAD`), enquanto os valores válidos são minúsculos (`comercial`/`lead`).
   - **Teste correto que fiz:** login (Bearer) + enum minúsculo → **HTTP 201** (`VIS-2026-00001`). Prova real do fix bakado.
3. **Cleanup:** como o passo 7 não rodou, removi eu mesmo a(s) visita(s) de teste → `visitas` = 0.
4. **Warning de orphan containers** (celery/flower/staging): benigno (efeito de `--no-deps`); nenhum tocado — é o bloco 2B.

## 4. Estado atual
- **Backend:** imagem `b18575b9c65e` (fixes bakados), **healthy**, health 200.
- **Celery/flower (8 containers):** ainda na imagem antiga `5958168f` (com código via docker cp) — serão recriados no **bloco 2B**.
- **Rollback:** imagem `pre-rebuild-fvisita-20260609` (5958168f) · banco: `pre_rebuild_fvisita_20260609_{142441,1444}.dump`.
- `AGENT_ENABLED=true`, webhook secret inalterado, dados intactos.

## 5. Próximo passo (bloco 2B — sob seu comando)
Recreate dos celery/flower na imagem nova `b18575b9` para alinhar os 9 containers. **NÃO executado.**

---

## Resumo
- Swap + recreate backend na imagem nova `b18575b9` — **fixes bakados e duráveis**. ✅
- Gates pós-healthy: health 200, webhook 200/401. ✅
- POST `/campo/visitas/` = **201** (testado com auth correta). ✅
- Honestidade: passo 6 do bloco estava sem Authorization (e enum maiúsculo) → 401; refiz correto. Gates 502 foram só boot. Cleanup feito manualmente (passo 7 não rodou). ✅
- Pendente: bloco 2B (celery/flower). Produção backend na `b18575b9`. ⏸️

*Bloco 2A concluído. Celery/flower ainda não recriados.*
