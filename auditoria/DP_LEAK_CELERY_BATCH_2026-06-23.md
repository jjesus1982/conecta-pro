# Investigação do leak de conexões do celery-batch — causa-raiz encontrada

**Data:** 2026-06-23 · **Escopo (§13.3):** investigação read-only (nenhuma alteração). **Princípios:** §13.1 (causa antes do fix), §13.4 (falsificação), §13.5 (medir real).

---

## CAUSA-RAIZ (confirmada)
As tasks de `government_integrations` (fila `gov.batch`, rodada pelo celery-batch) executam corrotinas async via um helper `run_async()` que **cria um event loop novo por task e o fecha SEM dispor o engine async**:

```python
# jobs/sync_tasks.py:23-30  E  jobs/monitoring_tasks.py:30-38 (idêntico)
def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()          # ← fecha o loop sem await engine.dispose()
```

**Mecanismo do vazamento:**
1. O engine async é **singleton módulo-level** (`core/database/session.py:15`, `pool_size=3`, `pool_recycle=1800`).
2. Conexões **asyncpg ficam ligadas ao event loop** que as criou.
3. `run_async` fecha o loop **sem `engine.dispose()`** → as conexões daquele pool ficam órfãs (o loop morreu), e o pool não consegue fechá-las corretamente.
4. No PG elas permanecem como **`idle`** até timeout. A cada task nova, novo loop → novas conexões → as antigas não são reaproveitadas (loop errado) → **acumulam**.
5. `monitoring_tasks` roda com frequência (beat) → ao longo de horas chegou a **~130 conexões idle** → estourou `max_connections=150`.

**Por que confirma:** o leak era **lento/por-execução** (não reacumulou em 55min de uptime baixo), consistente com "acumula por task ao longo do tempo". E o padrão `new_event_loop + loop.close()` sem dispose é o leak clássico asyncpg+Celery.

## EVIDÊNCIA DE QUE É ANOMALIA (não o padrão do projeto)
- O codebase **já tem o engine SÍNCRONO certo para Celery** (`sync_engine` + `SyncSessionLocal`, `session.py:80-94`, comentado "Sessão Síncrona para Celery Tasks").
- **Outros módulos usam o sync corretamente:** `operacional/tasks.py`, `financial/tasks.py`, `health_occupational/tasks/*` → `SyncSessionLocal`/`sync_engine`.
- **Só as tasks `government_integrations` (sync_tasks.py + monitoring_tasks.py)** fogem do padrão: usam engine **async** + event loop por task. São a fonte única do leak.

## ESTADO ATUAL (pós-restart de hoje)
- celery-batch: 7 conexões (saudável). Total 32/150. Não reacumulou ainda (uptime baixo).
- ⚠️ **Vai reacumular** conforme as tasks gov rodarem (beat/cron). O restart só zerou; a causa persiste no código.

---

## OPÇÕES DE FIX (decisão do Jordan — nada aplicado)

### Fix A — mínimo/cirúrgico (RECOMENDADO)
Dispor o engine async no loop antes de fechá-lo, nos 2 helpers `run_async`:
```python
from core.database import engine  # async singleton
def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        try:
            loop.run_until_complete(engine.dispose())   # fecha o pool no MESMO loop
        finally:
            loop.close()
```
- **Prós:** ~3 linhas × 2 arquivos; resolve a causa; baixo risco; sem refatorar a cadeia async de extração.
- **Contras:** dispõe o pool a cada task (leve overhead de reconectar na próxima — irrelevante p/ tasks gov infrequentes).
- **Deploy:** hot-copy `sync_celery_workers.sh government_integrations` (B.4). Não é zona proibida.

### Fix B — arquiteturalmente correto (maior, futuro)
Converter as tasks gov para `SyncSessionLocal`/`sync_engine` como os demais módulos Celery.
- **Prós:** elimina event-loop-por-task de vez; alinha ao padrão do projeto.
- **Contras:** a cadeia de extração (`extractors/orchestrator`) é toda async → refatoração grande e arriscada. Tech-debt para depois.

## RECOMENDAÇÃO
**Fix A agora** (estanca o leak, baixo risco) + registrar **Fix B** como tech-debt. Sem Fix A, o leak reacumula e volta a estourar o teto de conexões em algumas horas/dias.

## Pendência relacionada
- Vale checar se há **idle timeout** no Postgres (`idle_in_transaction_session_timeout` / um reaper de conexões idle) como defesa-em-profundidade — hoje não há, por isso conexões órfãs ficam para sempre.
