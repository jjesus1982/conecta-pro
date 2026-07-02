# Re-rebuild da imagem (com o agente) — Bloco 1 (build + validação efêmera)

- **Data:** 2026-06-08 ~18:26 UTC
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Bakar o agente (Fase A) na imagem do backend — eliminar a fragilidade (recreate reverte o agente).
- **Resultado:** ✅ **Imagem nova construída e validada (agente presente).** Produção intocada. Aguardando OK para o Bloco 2 (swap + recreate).

---

## 1. Por que (recap)
A imagem `47b3f7` (de 15:08) tinha tudo da Fase 2, **mas não o agente** (criado depois, via `docker cp`). Na Parte B (ligar o agente) o recreate reverteu o agente → corrigido por re-cp. Este re-rebuild **baka o agente** para que o recreate deixe de ser perigoso.

## 2. O que foi feito (Bloco 1 — não toca produção)
| # | Passo | Resultado |
|---|-------|-----------|
| 1 | Backup do banco | `backups/rebuild/pre_rerebuild_20260608_1825.dump` (3.8M) |
| 2 | Tag de rollback | `conecta-pro-backend:pre-rerebuild-20260608` → `47b3f70359a5` |
| 3 | Build (tag própria) | `conecta-pro-backend:rebuild-20260608b` = **`f0ee38d1a48a`** (não toca `:latest`) |
| 4 | Validação efêmera | container isolado (`--network none`) |

## 3. Validação da imagem nova
- `agent_service.py` **PRESENTE** na imagem ✅ (era o que faltava).
- Imports OK: `agent_service` (enabled_default=False — sem env no efêmero), `controller` (com o hook do agente), `service`.
- **Prompt v2 (catálogo real) PRESENTE** ✅.
- **md5 host == imagem nova** em `agent_service.py` e `controller.py` ✅.
- Produção: `conecta-pro-backend` segue rodando `47b3f70359a5` (intocada) ✅.

## 4. Estado das imagens
```
:rebuild-20260608b      f0ee38d1a48a  (NOVA, com agente — validada, fora de produção)
:latest                 47b3f70359a5  (PRODUÇÃO atual — sem agente baked)
:pre-rerebuild-20260608 47b3f70359a5  (ROLLBACK desta operação)
:pre-rebuild-20260608   bfa169a24c06  (rollback do rebuild anterior, 30/mai)
```

## 5. 🚦 GATE — Bloco 2 (swap + recreate) aguardando aprovação
Quando aprovado (compose intocado, via tag):
1. `docker tag conecta-pro-backend:rebuild-20260608b conecta-pro-backend:latest`
2. `docker compose up -d --no-deps --no-build backend` → recreate do backend.
3. Idem para os 8 celery + flower.
4. **Validar:** `/health` 200; webhook `?token=<ANTIGO 8ab9e3>` → 200 (entrada não quebra — o `.env` está no segredo antigo); `agent_enabled()=True` (do `.env`); chave OpenAI nova ativa; um teste real do agente (sugestão vira nota privada, sem ir ao cliente); dados intactos.

### Por que o recreate do Bloco 2 é seguro AGORA
- O agente está **baked** na imagem nova → recreate **não o reverte** (resolve a regressão da Parte B).
- `.env` no **segredo do webhook antigo** (`8ab9e3`) = o que o Chatwoot usa → entrada não quebra.
- `AGENT_ENABLED=true` no `.env` → agente continua ligado após o recreate.
- Chave OpenAI **nova (válida)** no `.env` → ativa no container após recreate.

## 6. 🔙 Rollback
```bash
docker tag conecta-pro-backend:pre-rerebuild-20260608 conecta-pro-backend:latest
docker compose up -d --no-deps --no-build backend
```
A imagem `47b3f7` fica intacta sob `:pre-rerebuild-20260608`. Backup do banco do bloco salvo.

---
*Bloco 1: backup + tag rollback + build (tag própria, agente baked) + validação efêmera. Produção (`:latest`) NÃO tocada. Nenhum recreate.*
