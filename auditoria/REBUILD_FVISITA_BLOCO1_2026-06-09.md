# REBUILD F-VISITA — Bloco 1 (backup + tag + build + validação efêmera)

- **Data:** 2026-06-09
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Bakar na imagem do backend os fixes que rodavam só via docker cp: fix do model `campo` (`4a1296e3` — FK + enum + tipos) + tool `agendar_visita` (`87f0def9`).
- **Status:** ✅ **Bloco 1 OK.** Imagem nova construída e validada (efêmera). **Produção NÃO tocada** — `:latest` segue `5958168f`, container backend confirmado rodando `5958168f`.

---

## 1. Etapas
| Etapa | Resultado |
|-------|-----------|
| Backup do banco | ✅ 2 dumps de hoje em `backups/rebuild/`: `pre_rebuild_fvisita_20260609_142441.dump` e `pre_rebuild_fvisita_20260609_1444.dump` (3.8M cada) |
| Tag de rollback | ✅ `conecta-pro-backend:pre-rebuild-fvisita-20260609` = `5958168f7f82` (= `:latest` atual) |
| Build imagem nova | ✅ `conecta-pro-backend:rebuild-fvisita-20260609` = **`b18575b9c65e`** — `:latest` intocado |
| Validação efêmera | ✅ `docker run --network none` — todos os checks PRESENTE OK |

## 2. Validação efêmera (`--network none`, não toca produção)
Os fixes confirmados na imagem nova `b18575b9`:
- **tool `agendar_visita`** — PRESENTE (3 tools: `consultar_cnpj`, `buscar_cliente`, `agendar_visita`).
- **fix campo** — FK cross-schema **removida** · enum `native_enum=False` **presente** · (tipos alinhados).
- **preservados** — `consultar_cnpj` (F-B.1) · SQLi fix `WHERE cc.client_id = :client_id` (contact_controller).
- **imports** — `agent_service` OK · `model Visita` OK → **VALIDAÇÃO EFÊMERA OK**.

## 3. Histórico de execução (2 disparos)
- **1º disparo (14:21):** falhou no **passo 1** — o bloco avalia `$(date +%H%M)` **duas vezes** (pg_dump `-f` e docker cp); o minuto virou entre as duas → docker cp procurou nome de arquivo divergente:
  `Could not find the file /tmp/pre_rebuild_fvisita_20260609_1422.dump`.
  A cadeia `&&` parou ali → **nenhuma tag/build/efeito em produção** (falha segura). Refiz com timestamp fixo (gerou imagem `73c873f6`).
- **2º disparo (14:44, re-run do bloco original):** desta vez o minuto **não** virou entre os dois `$(date)` → passou limpo. Backup + tag + build + validação OK. Gerou novo manifest **`b18575b9`** (conteúdo idêntico ao `73c873f6`, só re-empacotado). A tag `rebuild-fvisita-20260609` agora aponta para `b18575b9`.
- **Observação:** o bug do timestamp duplo permanece no bloco como escrito — pode falhar de novo em re-execuções (1-em-60 perto da virada de minuto). Recomendo capturar o TS uma vez em variável.

## 4. Estado e rollback
- **Produção:** `:latest` = `5958168f7f82` (inalterada). Container backend confirmado em `5958168f`. Os fixes ainda rodam via docker cp.
- **Imagem nova pronta:** `rebuild-fvisita-20260609` = `b18575b9c65e` (com os fixes bakados), importa limpo, isolada da rede.
- **Rollback de imagem:** `pre-rebuild-fvisita-20260609` (5958168f) · `pre-rerebuild2-20260609` (f0ee38d1) · `pre-rerebuild-20260608` (47b3f7).
- **Backup do banco:** 2 dumps de hoje (`_142441`, `_1444`).

## 5. Próximo passo (bloco 2 — sob seu comando)
- Swap `:latest` → `b18575b9c65e` (ou via tag `rebuild-fvisita-20260609`) + `docker compose up -d --no-deps --no-build backend` + recreate dos celery/flower.
- Verificação pós-swap: backend na imagem nova, healthy, `/health` 200, webhook token válido 200 / errado 401, **POST `/campo/visitas/` 201** (prova o fix bakado).
- **NÃO executado ainda.**

---

## Resumo
- Backup + tag rollback + build da imagem nova **`b18575b9`** (fixes bakados: campo `4a1296e3` + tool `87f0def9`, preservados F-B.1 + SQLi) + validação efêmera **OK**. ✅
- 1º disparo falhou no backup (bug de timestamp duplo) → falha segura, refeito; 2º disparo passou limpo. ✅
- Produção intocada (`:latest` = `5958168f`, container em `5958168f`). Aguardando bloco 2 (swap/recreate). ⏸️

*Bloco 1 concluído. Produção não recriada.*
