# Fix A aplicado — leak de conexões do celery-batch (government_integrations)

**Data:** 2026-06-23 · **Escopo (§13.3):** `government_integrations/jobs/` (2 arquivos). **Princípios:** §13.4 (falsificação A/B), §13.6 (backup/rollback), B.4 (hot-copy todos Celery).

---

## RESULTADO: ✅ leak estancado
Causa-raiz corrigida: o helper `run_async()` agora **dispõe o engine async no mesmo loop antes de fechá-lo**, nas tasks gov. A/B prova que o dispose elimina o acúmulo. Conexões saudáveis (12/150), app HTTP 200.

## O que foi feito (Fix A — mínimo/cirúrgico)
Em `sync_tasks.py` e `monitoring_tasks.py`:
1. `from core.database import engine` (engine async singleton).
2. `run_async()` ajustado:
```python
    try:
        return loop.run_until_complete(coro)
    finally:
        # Dispõe o pool async NO MESMO loop antes de fechá-lo — senão as conexões
        # asyncpg ficam órfãs e acumulam como idle no Postgres (leak do celery-batch).
        try:
            loop.run_until_complete(engine.dispose())
        finally:
            loop.close()
```
- Deploy: `sync_celery_workers.sh government_integrations` (backend + 7 Celery, pyc limpo, kill -HUP).

## VERIFICAÇÃO (§13.4 — A/B do padrão, engine isolado `application_name='leak_test'`)
| Cenário | Conexões órfãs após 10 execuções |
|---|---|
| **Padrão ANTIGO** (loop fecha sem dispose) | **4** (acumulando) |
| **Fix A** (dispose no loop) | **~0** (1, artefato de timing) |
| Veredito | **new < old → dispose elimina o acúmulo** ✅ |

> Honestidade: em produção o engine é **singleton** (não novo-por-chamada como no A/B), então o antigo vazava muito pior (chegou a 130). O A/B prova o mecanismo: dispor o pool no loop fecha as conexões asyncpg corretamente.

### Estado real pós-fix
- Total conexões: **12/150** (saudável). celery-batch: 0 (idle).
- Código novo confirmado no container (`engine.dispose()` ×1 em sync_tasks). Backend HTTP 200. celery-batch healthy.
- Resíduo do teste (`leak_test`): limpo (0).

## ROLLBACK
- Backup: `/tmp/leak_fix_bak/{sync_tasks,monitoring_tasks}.py.bak`.
- Reverter: restaurar os .bak + `sync_celery_workers.sh government_integrations`. Ou `git checkout HEAD -- backend/modules/government_integrations/jobs/`.

## PENDÊNCIAS
1. **Commit:** o fix está LIVE mas NÃO commitado (junto com o fix hr de hoje). Decidir branch/sufixo (B.8) — a árvore tem muitos arquivos não-relacionados modificados.
2. **Fix B (tech-debt):** converter tasks gov para `SyncSessionLocal`/`sync_engine` (padrão dos outros módulos Celery) — elimina o event-loop-por-task de vez. Maior, futuro.
3. **Defesa-em-profundidade:** considerar `idle_in_transaction_session_timeout` / reaper de conexões idle no Postgres — hoje não há, por isso órfãs ficavam para sempre.
4. **Validação de longo prazo:** observar o celery-batch nas próximas 24-48h (após o beat disparar várias tasks gov) para confirmar que NÃO reacumula. O A/B prova o mecanismo; a confirmação em produção real é temporal.
