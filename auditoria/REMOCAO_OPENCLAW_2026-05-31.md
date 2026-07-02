# Remoção do OpenClaw — Opção 2 (motor + tabelas) — APLICADO

**Data:** 2026-05-31 · **Decisão do Jordan:** Opção 2 — remover o OpenClaw de vez, manter só o dashboard de métricas vivas.
**Status:** ✅ **CONCLUÍDO** — auto-remediação aposentada, dashboard vivo preservado, backend saudável.

## Backups (antes de qualquer remoção)
- Tabelas openclaw (schema+dados): `backups/openclaw_tables_PRE_DROP_20260531_131728.dump` (20K, 3 tabelas).
- Crontab: `backups/crontab_PRE_OPENCLAW_REMOVAL_20260531_131728.txt`.
- dashboard_api.py: `agents/dashboard_api.py.bak-openclaw-20260531_131728`.

## O que foi removido
1. **Crons do motor** (header `=== OPENCLAW MULTI-AGENT SYSTEM ===` + 2 jobs):
   - `*/15 * * * * run_preventive_action.sh` (o motor de remediação que rodava mas executava 0 ações)
   - `0 3 * * * run_pattern_learner.sh` (o aprendiz de padrões)
   - → **0 crons do motor restantes.**
2. **3 tabelas dropadas** (atômico, CASCADE): `openclaw_interventions`, `openclaw_patterns`, `openclaw_knowledge_base` → **NENHUMA** restante.
3. **alembic** avançado para `drop_openclaw_tables` + migration registrada (`backend/alembic/versions/drop_openclaw_tables.py`).
4. **Código limpo** (sem quebrar o dashboard vivo):
   - `dashboard_api.py`: queries de interventions/patterns → `[]`.
   - `context_builder.py`: `collect_interventions`, `collect_patterns`, `collect_recent_events` → `[]`.

## O que foi PRESERVADO (dashboard de métricas vivas)
- **Crons do orchestrator** (4): regeneram o `dashboard_data.json` com métricas AO VIVO (containers, RAM, swap, agentes, tickets).
- **Grafana/Prometheus** (stack de observabilidade, intocado).
- Dashboard `/agents/dashboard` segue funcionando — agora **sem os blocos OpenClaw** (interventions/patterns vazios).

## Validação
- Dashboard regenera **limpo** após o DROP: Containers 25/31, RAM 57.7%, Tickets 100 — **sem erro de "relation does not exist"**.
- `context_builder.py` roda com **0 erros**.
- Backend **health 200**, 14/14 containers conecta-pro healthy.
- `py_compile` OK nos editados; **ZERO query ativa** em tabelas openclaw em dashboard_api/context_builder.

## Pendências / notas honestas
- **Migrations órfãs** (zona protegida `alembic/versions/`, NÃO removidas): `sprint77_openclaw_interventions.py`, `sprint77_openclaw_memory_tables.py` — a nova `drop_openclaw_tables` registra a remoção; as antigas ficam como histórico.
- **telegram_assistant.py** (linha 366): tem uma ferramenta "listar intervenções OpenClaw" com **fallback gracioso** ("Nenhuma intervenção registrada") — degrada sem quebrar; deixada como está (limpeza opcional).
- **Scripts do motor** (`preventive_action.py`, `pattern_learner.py`, etc.) permanecem no disco mas **desconectados** (sem cron) — código morto, pode ser arquivado depois.
- **dashboard.html** (estático, Abr 1) ainda tem os rótulos de seção "Intervenções/Padrões OpenClaw" — aparecerão **vazios**. Limpeza cosmética opcional se quiser tirar os títulos.

## Rollback
- Restaurar tabelas: `pg_restore -d conecta_pro backups/openclaw_tables_PRE_DROP_20260531_131728.dump`.
- Restaurar crons: `crontab backups/crontab_PRE_OPENCLAW_REMOVAL_20260531_131728.txt`.
- Restaurar código: `.bak-openclaw-20260531_131728` + git.
