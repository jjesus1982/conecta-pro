# Rebuild da imagem do backend — Bloco 1 (build + validação efêmera) CONCLUÍDO

- **Data:** 2026-06-08 ~15:10 UTC
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Construir e validar a imagem nova do backend (com todo o código baked) **sem tocar produção**.
- **Resultado:** ✅ **Imagem nova construída e validada.** Produção segue na imagem velha, intocada. Aguardando aprovação para o Bloco 2 (swap + recreate).

---

## 1. O que foi feito (Bloco 1 — seguro, não toca produção)
| # | Passo | Resultado |
|---|-------|-----------|
| 1 | **Backup do banco** | `backups/rebuild/pre_rebuild_20260608_150847.dump` (3.8M) |
| 2 | **Tag de rollback** | `conecta-pro-backend:pre-rebuild-20260608` → `bfa169a24c06` (imagem velha preservada) |
| 3 | **`.dockerignore`** | adicionados `.whatsapp_webhook_secret*` e `.chatwoot_token` (segredos não bakam) |
| 4 | **Build** | `conecta-pro-backend:rebuild-20260608` = `47b3f70359a5` (2.16GB) — **tag própria, não toca `:latest`** |
| 5 | **Validação efêmera** | container isolado (`--network none`, sem lifespan/EventBus) |

## 2. Validação da imagem nova (efêmera + spot-check)
**Imports críticos (OK):**
- `whatsapp.service` → `base=http://chatwoot-fazerai:3000` (código Chatwoot baked)
- `whatsapp.controller` (webhook)
- `crm.models.lead` → `LeadSource.WHATSAPP=whatsapp` (enum + email nullable baked)
- `crm.schemas.lead`, `crm.services.lead_service` (fix do score), `alembic`

**Spot-check de integridade:**
- **md5 host == imagem nova** em `service.py`, `controller.py`, `lead.py`, `lead_service.py` → o build capturou o código atual ✅
- Migrations presentes: `sprint90_cwi_message_log`, `sprint91_lead_email_nullable`, `findp_b1b2_20260601`, `drop_openclaw_tables` ✅
- Segredos **ausentes** na imagem (`.whatsapp_webhook_secret*`, `.chatwoot_token`) ✅
- **Produção intocada:** `conecta-pro-backend` (rodando) ainda em `bfa169a24c06` (imagem velha) ✅

## 3. Estado das imagens
```
conecta-pro-backend:rebuild-20260608    47b3f70359a5   (NOVA, validada, fora de produção)
conecta-pro-backend:latest              bfa169a24c06   (PRODUÇÃO atual — intocada)
conecta-pro-backend:pre-rebuild-20260608 bfa169a24c06  (ROLLBACK anchor)
```

## 4. 🚦 GATE — Bloco 2 (swap + recreate) aguardando aprovação
**Não executado.** Quando aprovado, o Bloco 2 fará (compose intocado, via tag):
1. `docker tag conecta-pro-backend:rebuild-20260608 conecta-pro-backend:latest`
2. `docker compose up -d --no-deps --no-build backend` → **recreate do backend** a partir da imagem nova.
3. Repetir para os 8 celery + flower.
4. **Validar:** `/health` 200; webhook `?token=<ATIVO 8ab9e3>` → 200 (o `.env` foi revertido ao segredo ANTIGO, então o recreate **não** quebra a entrada); envio (chokepoint) OK; `cwi_message_log`/leads intactos; `alembic current=sprint91`.
5. **Rollback** (se preciso): `docker tag conecta-pro-backend:pre-rebuild-20260608 conecta-pro-backend:latest` → `up -d --no-deps --no-build backend`.

### Por que o recreate do Bloco 2 é seguro
- A imagem nova **baka os 61 arquivos** (host==container verificado) → recriar **não reverte nada** — é o passo que elimina a fragilidade do `docker cp`.
- O `.env` foi alinhado ao **segredo ANTIGO ativo** (`8ab9e3`), igual ao que o Chatwoot usa → o recreate injeta o segredo certo, **entrada não quebra**. (A rotação T2 para o novo segredo `750af6` segue parqueada/staged para depois.)

## 5. Observações
- Pendências NÃO resolvidas pelo rebuild (são de banco/código, não da imagem): schema drift (alguns GETs 500 por migration faltante), warning OpenClaw não-fatal, celery-batch/Redis intermitente. Monitorar pós-deploy.
- `DeprecationWarning` nos imports (`modules.integrations/crm` → `gestao/comercial`) são pré-existentes e benignos.

---
*Bloco 1: backup + tag rollback + `.dockerignore` + build (tag própria) + validação efêmera isolada. Produção (`:latest`) NÃO tocada. Nenhum recreate. Segredos não expostos.*
