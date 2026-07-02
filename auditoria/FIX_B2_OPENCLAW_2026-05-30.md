# FIX B2 — `modules.ai.openclaw` referenciado mas inexistente

**Data:** 2026-05-30
**Status:** ⛔ **DIAGNOSTICADO — NÃO CORRIGIDO** (a correção toca zona proibida `main_production.py`; per regra, parei e reporto).
**Escopo:** somente OpenClaw. Schema/migrations/Celery não tocados.

> Nenhum arquivo foi editado. Único arquivo escrito: este relatório.

---

## 1. O que era o OpenClaw (diagnóstico — caso "a": existiu e foi perdido)

**Sistema real de multi-agentes de resposta a alertas de infraestrutura**, com memória persistente e aprendizado contínuo. Não é planejamento vazio nem copy-paste morto.

Evidência (git history):
- `537bfc81 feat(multi-agent): sistema completo de agentes autonomos OpenClaw`
- `98a45436 feat(openclaw): memoria persistente e aprendizado continuo`
- `d90974fe feat: sessão 2026-04-01 — Skills 01-10 + sistema agentes 24h`
- `32a4ae85 fix(openclaw): handler PM2ExcessiveRestarts + throttle Telegram`
- `dbefddff fix(infra): 5 melhorias estabilidade — ... OpenClaw`

**7 arquivos existiam em `modules/ai/openclaw/`** (recuperáveis do git, ex. commit `d90974fe`):
```
__init__.py  controller.py  memory_service.py  models.py
remediation_service.py  schemas.py  telegram_service.py
```
Funções: webhook de alertas (Alertmanager), remediação automática (ex.: PM2ExcessiveRestarts), notificação/throttle via Telegram, memória de intervenções com aprendizado.

**Hoje:** diretório **ausente no host E na imagem em produção** (`ls modules/ai/openclaw` → No such file or directory, idem `/app/...`).

## 2. Os 3 vestígios que permaneceram (e o que indicam)

| Vestígio | Local | Zona |
|---|---|---|
| **Import órfão** `from modules.ai.openclaw.controller import router` + `include_router(..., prefix="/ai")` | `main_production.py:886-893` (dentro de `try/except`) | 🔴 **PROIBIDA** |
| **2 migrations** | `alembic/versions/sprint77_openclaw_interventions.py` e `sprint77_openclaw_memory_tables.py` | 🔴 **PROIBIDA** |
| **3 tabelas no banco** (live) | `openclaw_interventions`, `openclaw_patterns`, `openclaw_knowledge_base` | banco (não tocar) |

**Bloco exato (main_production.py:886-893) — apenas para referência, NÃO editado:**
```python
# OpenClaw — Multi-Agent alert response system
try:
    from modules.ai.openclaw.controller import router as openclaw_router
    api_router.include_router(openclaw_router, prefix="/ai", tags=["AI - OpenClaw Alert Response"])
    logger.info("Modulo OpenClaw: OK (Alert webhook + Remediation)")
except Exception as e:
    logger.warning(f"Modulo OpenClaw: {e}")   # <- gera o warning no startup
```

**Leitura honesta:** o fato de o import, as migrations **e** as tabelas terem ficado todos no lugar indica que o módulo foi **perdido acidentalmente** (provável acidente de movimentação de arquivos — mesmo padrão do diretório-artefato `gedeon/` corrigido hoje), **não removido de propósito**. Uma remoção deliberada teria limpado o import também.

## 3. Impacto real

- **Cosmético / não-fatal.** O `try/except` captura o `ModuleNotFoundError` e só loga `WARNING: Modulo OpenClaw: No module named 'modules.ai.openclaw'`. O app sobe normal (3520 rotas, /health 200).
- **Funcional:** o ERP não perde nada do core. O que está inativo é a **auto-remediação de infra via agentes** (resposta automática a alertas Alertmanager/PM2 + Telegram). Se isso era usado para auto-cura do servidor, está **desligado** desde a perda do módulo.

## 4. Por que NÃO apliquei correção

A única via que faz o warning sumir **mantendo o feature removido** é editar `main_production.py:886-893` — **zona proibida**. A regra da missão é explícita: *"Se o import de openclaw estiver DENTRO de uma zona proibida, PARE e reporte — não edite, só documente."* As migrations também estão em zona proibida. **Parei.**

- **Diff aplicado:** nenhum.
- **Via de deploy usada:** nenhuma (não aplicado).
- **Backup `.bak-b2`:** não criado (nada editado).

## 5. Opções para o Jordan decidir

| Opção | Ação | Zona proibida? | Efeito |
|---|---|---|---|
| **A — Restaurar o feature** *(recomendada se OpenClaw é desejado)* | `git checkout d90974fe -- modules/ai/openclaw/` no host (restaura os 7 arquivos) → entra no **próximo rebuild** | **NÃO** toca zona proibida (`modules/ai/openclaw/` é livre). Resolve o import **sem editar `main_production.py`**. Tabelas/migrations já existem. | Warning some; **feature de auto-remediação volta** (é um agente autônomo que age em infra/PM2/Telegram — confirmar se quer reativar) |
| **B — Remover o órfão** | Comentar/remover o bloco `main_production.py:886-893` | 🔴 **SIM** — exige seu OK explícito; depois `docker cp` ou próximo rebuild | Warning some; feature permanece desligado |
| **C — Deixar como está** | Nada | — | Warning cosmético persiste; sem risco |

**Recomendação:** como a evidência aponta perda **acidental** e os vestígios (import + migrations + tabelas) já sustentam o módulo, a **Opção A** é a mais limpa e a única que **não toca zona proibida** — desde que você queira reativar o sistema de agentes autônomos do OpenClaw. Se NÃO quiser o feature de volta, **Opção B** (com seu OK para editar `main_production.py`). Em ambas, posso executar quando você autorizar.

## 6. Confirmação de estado

- Warning `No module named 'modules.ai.openclaw'` no startup: **ainda presente** (não corrigido — parei por zona proibida).
- Backend: **/health 200, 3520 rotas, healthy** (inalterado — nada foi mexido).
- Regressão: **nenhuma** (nenhuma alteração feita).
