# Ponto — Pull de batidas do Tangerino → gp_clock_punches (CONCLUÍDO)

**Data:** 2026-06-23 · **Escopo:** integrations/solides + beat. **§13.4/§13.5/§13.6.** Feature nova, aplicada staging→prod, agendada 24/7.

---

## RESULTADO: ✅ ponto sincronizando do Tangerino
A API do Tangerino estava acessível pelo próprio token (Swagger `/v2/api-docs`) — **não precisei de nada externo**. Construí, testei e ativei o pull de batidas. O ponto do Conecta volta a refletir o Tangerino, atualizado de hora em hora.

## O que foi construído
- **Task `sync_punches_from_tangerino`** (`connectors/solides/tasks.py`): para cada employee ativo com `solides_id` → `GET /external/api/v1/payssego/punches/{employeeId}` (auth Basic, datas `dd/MM/yyyy`, pageSize 500) → mapeia o resumo diário em **entrada (`startDateTimestamp`) + saída (`endDateTimestamp`)** → **upsert idempotente** em `gp_clock_punches` por `punch_id` determinístico (`tang-{sid}-{ts}-{tipo}`), `device_type='tangerino'`.
- **100% síncrono** (httpx.Client + create_engine) — sem event loop, **sem o leak** do padrão anterior.
- **#3b resolvido junto:** mapeamento `solides_id → employee_id` usa `employees` (fonte única, já fresca) — não depende do espelho `solides_employees` stale.
- **Agendado no beat:** `solides-sync-punches`, **de hora em hora**, `days_back=2` (pega recentes + correções).

## Validação (§13.4)
| Etapa | Resultado |
|---|---|
| Staging RUN1 | created=**1577**, errors=0, 46 funcionários |
| Staging RUN2 (idempotência) | created=**0**, updated=1578, errors=0 → **idempotente** |
| Prod backfill (90d) | created=**1758** (mai-jun), 1 erro (1/46) |
| Prod E2E via Celery | task registrada, `status=completed`, updated=123, 19s |
| Estado final | `gp_clock_punches` total=**3610** (tangerino=**1780** + nativo 1830), recente=**2026-06-23** |
| Backend / containers | HTTP 200 · 21 healthy |

## Backup / reversão
- Backup: `backups/postgresql/PRE_PUNCHES_*.dump` (gp_clock_punches pré).
- Reverter: `DELETE FROM gp_clock_punches WHERE device_type='tangerino'` (as nativas ficam intactas) + remover a entrada do beat.
- Commit `a1a7bb53` (pushado). Enum: `ALTER TYPE solides_sync_type ADD VALUE 'punches'` (aditivo, p/ o sync_log registrar).

## Achados / pendências
1. **Gap de ABRIL:** nem nativo (parou 30/mar) nem Tangerino (começa em mai) têm batidas de abril — período de transição. **Não há fonte para preencher.**
2. **⚠️ BUG no `sync_celery_workers.sh`:** `docker cp backend/modules/$MODULO/ container:/app/modules/$MODULO/` **aninha** (`integrations/integrations/`) quando o dir existe. Deploy correto desta sessão foi por **cópia de arquivo direta**. Os fixes anteriores (hr, government) foram verificados **sem aninhamento** e no path real. **Corrigir o script** (usar `/.` ou copiar arquivo) — vale uma rodada à parte.
3. **Granularidade:** o endpoint dá resumo diário (entrada/saída/horas), não batidas individuais (almoço etc.) — é o que o Tangerino expõe. Suficiente p/ folha/espelho.
4. **1 erro no backfill** (1 funcionário) — investigar pontualmente (provável dado atípico).

## Estado do DP ao fim (ponto fechado)
- **Funcionários:** sync Sólides→Conecta 24/7 (cria+atualiza+updated_at+log honesto).
- **Ponto:** **pull do Tangerino ativo 24/7** → `gp_clock_punches` atual.
- Tudo commitado/pushado.

---

## REBUILD (durabilidade B.7) — 2026-06-24
Código bakeado na imagem (não mais docker-cp). Procedimento B.3.3:
- Âncora: `conecta-pro-backend:pre-punchpull-20260623` (rollback).
- Backup DB: `PRE_REBUILD_PUNCHPULL_2238.dump`.
- Build: `conecta-pro-backend:rebuild-punchpull-20260623` (c4c3a7bdf11f), retag `:latest`.
- Teste efêmero (--network none): task bakeada + imports OK.
- Swap: recreate backend + 7 celery + flower (compose canônico docker-compose.yml + .celery.yml).
- **Validado:** 21 healthy, /health 200, AGENT_ENABLED=true, chatwoot-fazerai-net presente, task registrada no worker, gp_clock_punches tangerino crescendo.
- **Durabilidade PROVADA:** a task sobreviveu ao force-recreate (veio da imagem). Sobrevive a qualquer rebuild/recreate futuro. Fixes da sessão (hr FK, gov leak, solides) também bakeados, sem regressão.

---

## VALIDAÇÃO AUTENTICADA + FIX DO ESPELHO + REBUILD #2 (2026-06-24)
Com login real (`jjesus@conectamais.pro`, autorizado pelo Jordan), validação §13.5 na tela:
- **Funcionários (DP):** endpoint autenticado retorna 46 ativos. ✅
- **Bug PRÉ-EXISTENTE achado:** espelho/batidas davam **500** (`operator does not exist: uuid = character varying`). O model `clock_punch.py` declarava `employee_id=String(36)` mas a coluna é `uuid` → query `uuid = varchar`. Quebrava o espelho de TODAS as batidas (nativas e Tangerino) — a tela nunca tinha funcionado.
- **Fix:** `employee_id` → `UUID(as_uuid=False)`. Commit `8bc75640`. Validado autenticado: espelho 200, JONILSON 41 batidas, nativo 42.
- **Rebuild #2 (durabilidade):** âncora `pre-espelho-20260624`, backup `PRE_REBUILD_ESPELHO_*.dump`, build `rebuild-espelho-20260624` (ca7658292213), teste efêmero (employee_id type=UUID), swap backend+celery, validado: 21 healthy, espelho 200 da imagem bakeada, AGENT_ENABLED=true, chatwoot-net presente.
- **Durabilidade PROVADA:** fix sobreviveu ao force-recreate. Ponto 100% funcional e durável.
