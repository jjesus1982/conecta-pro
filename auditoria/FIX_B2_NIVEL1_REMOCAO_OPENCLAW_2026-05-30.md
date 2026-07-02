# FIX B2 — NÍVEL 1: Remoção do import órfão do OpenClaw

**Data:** 2026-05-30
**Status:** ✅ **CONCLUÍDO** — bloco órfão removido, warning eliminado, sem regressão.
**Autorização:** Jordan autorizou editar `main_production.py` **somente** para remover o bloco do OpenClaw. Nenhuma outra linha tocada.

> Banco **não tocado** (3 tabelas `openclaw_*` + 2 migrations `sprint77_openclaw_*` ficam para o Nível 2). Demais zonas proibidas intactas.

---

## 1. Diff aplicado em `main_production.py`

Removidas as 9 linhas do bloco OpenClaw (886-894), incluindo comentário, `try/except` completo e a linha em branco subsequente:

```diff
     logger.warning(f"Modulo Inteligencia: {e}")

-# OpenClaw — Multi-Agent alert response system
-try:
-    from modules.ai.openclaw.controller import router as openclaw_router
-
-    api_router.include_router(openclaw_router, prefix="/ai", tags=["AI - OpenClaw Alert Response"])
-    logger.info("Modulo OpenClaw: OK (Alert webhook + Remediation)")
-except Exception as e:
-    logger.warning(f"Modulo OpenClaw: {e}")
-

 # =============================================================================
 # 8. GESTÃO (config + audit + notifications + mobile + workflows + integrations)
```

- Nenhum import pendurado nem `include_router` órfão restou.
- `grep -c openclaw main_production.py` → **0** (host **e** container).
- Espaçamento original preservado (2 linhas em branco antes do separador `# ===`).

## 2. Backup criado

```
/opt/conecta-pro/backend/main_production.py.bak-openclaw-20260530_160708
```
(sha256 do arquivo pré-edição: `bbab4e00…d8fdfe7`)

## 3. Validação de sintaxe

- `python3 -m py_compile main_production.py` → **OK** (sem erro).
- `ast.parse` dentro da imagem (Python 3.12) → **OK**.

## 4. Via de deploy usada

O backend roda do **código assado na imagem** (`conecta-pro-backend:rebuild-20260530b` / `bfa169a2`), então editar só o host não bastaria. Aplicado via:
1. `docker cp main_production.py conecta-pro-backend:/app/main_production.py`
2. `docker restart conecta-pro-backend`

## ⚠️ 5. LEMBRETE CRÍTICO — entrar no próximo rebuild

Esta edição existe **no host** (`/opt/conecta-pro/backend/main_production.py`) e foi replicada no **container atual** via `docker cp`. Como o backend roda da imagem, **um futuro rebuild de imagem reconstrói a partir do host** — que já contém a correção. ✅ Portanto o próximo rebuild **preserva** a remoção (não reintroduz o bloco), desde que o rebuild use o código do host atual. Não há ação extra necessária, apenas ciência de que a fonte-de-verdade (host) já está corrigida.

## 6. Confirmação — warning sumiu, sem regressão

| Verificação | Antes | Depois |
|---|---|---|
| Warning `No module named 'modules.ai.openclaw'` / `Modulo OpenClaw:` | presente no startup | **0 ocorrências** ✅ |
| Erros de import no startup | só OpenClaw | **nenhum** ✅ |
| `/health` | 200 | **200** ✅ |
| Rotas vivas | 3520 | **3520** (mantido — OpenClaw não tinha rotas ativas) ✅ |
| Backend | healthy | **Up healthy, rc=0** ✅ |
| Startup banner | Inteligencia → OpenClaw(warn) → Gestao | **Inteligencia → Gestao** (limpo) ✅ |

## 7. Pendência registrada — NÍVEL 2 (operação de banco, futura)

Ficam para a operação de banco do **B3** (com backup fresco antes), **fora do escopo desta tarefa**:
- **3 tabelas órfãs:** `openclaw_interventions`, `openclaw_patterns`, `openclaw_knowledge_base` (ainda no banco de produção).
- **2 migrations órfãs:** `alembic/versions/sprint77_openclaw_interventions.py` e `sprint77_openclaw_memory_tables.py` (zona proibida `alembic/versions/`).
- Decisão de drop/limpeza dessas tabelas deve acompanhar a operação de migrations do schema drift (B3), nunca isolada e sempre com dump fresco.
