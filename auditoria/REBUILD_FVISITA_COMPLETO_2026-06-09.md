# REBUILD F-VISITA — COMPLETO (bloco 2B + consolidação)

- **Data:** 2026-06-09
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Bakar na imagem do backend os fixes que rodavam só via docker cp e alinhar os 9 containers.
- **Imagem nova:** `conecta-pro-backend:latest` = **`b18575b9c65e`**
- **Status:** ✅ **COMPLETO.** 9 containers na imagem nova, healthy, health 200. Fixes duráveis.

---

## Bloco 2B — celery + flower na imagem nova
- Recriados: `celery-beat`, `celery-operacional`, `celery-nfse`, `celery-sefaz`, `celery-batch`, `celery-priority`, `celery-integrations`, `flower`.
- **Todos os 9 containers** = `b18575b9c65e`, `status=running`.
- **Gate final:** `/health` **200**.

| Container | Imagem | Status |
|-----------|--------|--------|
| backend + 7 celery + flower (9) | `b18575b9c65e` | running |

## Mudanças durabilizadas neste rebuild
1. **Fix do model `campo`** (`4a1296e3`): FK cross-schema removidas + enum `native_enum=False` + 3 tipos alinhados → `POST /campo/visitas/` voltou a funcionar (era 500 desde sempre).
2. **Tool `agendar_visita`** (`87f0def9`): agente WhatsApp cria visita PROPOSTA (AGENDADA), copiloto.
3. **Preservados** (rebuilds anteriores): tools F-B.1 (`consultar_cnpj`/`buscar_cliente`), SQLi fix `contact_controller`, agente copiloto, webhook Fase 2.

## Jornada completa do rebuild
| Bloco | Ação | Resultado |
|-------|------|-----------|
| 1 | backup + tag rollback + build + validação efêmera | imagem `b18575b9` validada (`--network none`), produção intocada |
| 2A | swap `:latest` + recreate backend | backend na img nova, healthy, POST `/campo/visitas/` **201** (com auth) |
| 2B | recreate celery + flower | 9 containers alinhados, health 200 |

## Prova de durabilidade
Backend e workers recriados **a partir da imagem** (não docker cp). `POST /campo/visitas/` = 201 → o fix do `campo` está bakado; recreate **não reverte mais**.

## Rollback disponível
- Imagem: `pre-rebuild-fvisita-20260609` = `5958168f` (anterior) · `pre-rerebuild2-20260609` = `f0ee38d1` · `pre-rerebuild-20260608` = `47b3f7`.
- Banco: `pre_rebuild_fvisita_20260609_{142441,1444}.dump`.
- Reverter: `docker tag conecta-pro-backend:pre-rebuild-fvisita-20260609 conecta-pro-backend:latest` + recreate.

## Observações honestas (já reportadas no 2A)
- Gates 502 no 2A foram transitórios (boot); após healthy → 200/200/401.
- O passo 6 do bloco 2A (teste decisivo) estava **sem header Authorization** (→401) e com enum **maiúsculo**; o teste correto (login+Bearer+`comercial`/`lead`) deu **201**.
- Warning de orphan containers no compose: benigno (`--no-deps`); nada indevido tocado.

## Estado final
- 9 containers em `b18575b9`, running, **health 200**.
- `AGENT_ENABLED=true` (3 tools: consultar_cnpj, buscar_cliente, agendar_visita, modo copiloto).
- `visitas` = 0 (testes limpos). Webhook secret inalterado, dados intactos.
- **Sem pendências de rebuild.**

---

## Resumo
- REBUILD F-VISITA **completo**: 9 containers na imagem nova `b18575b9` (fixes campo `4a1296e3` + tool `87f0def9` bakados, anteriores preservados). ✅
- POST `/campo/visitas/` 201 (durável), health 200, 9/9 running. ✅
- Backup + tags de rollback no lugar. ✅
- Fim das pendências de rebuild — recreate agora é seguro.

*Rebuild F-VISITA completo.*
