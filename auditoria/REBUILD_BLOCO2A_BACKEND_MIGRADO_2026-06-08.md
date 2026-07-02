# Rebuild — Bloco 2A: backend migrado para a imagem nova (validado)

- **Data:** 2026-06-08 ~15:43 UTC
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Trocar o `:latest` para a imagem nova e **recriar o backend** (recreate sancionado — imagem bakou todo o código).
- **Resultado:** ✅ **Backend rodando na imagem nova, healthy, todos os gates OK. Sem perda de dados.** Celery/flower seguem na imagem velha (próximo gate).

---

## 1. O que foi feito
1. **Swap de tag:** `docker tag conecta-pro-backend:rebuild-20260608 conecta-pro-backend:latest` → `:latest` = `47b3f70359a5`.
2. **Recreate só do backend:** `docker compose up -d --no-deps --no-build backend` (compose intocado).
   - Warning "orphan containers" (celery/staging) é **benigno** — esses serviços estão no `docker-compose.celery.yml`, não foram tocados.
3. Backend agora em `IMAGE=47b3f70359a5` (NOVA), `running/healthy`, `RestartCount=0`.

## 2. Gates de produção (todos ✅)
| Gate | Resultado |
|------|-----------|
| `/health` (público `erp.`) | **200** |
| webhook `POST` sem token | **401** |
| webhook `POST ?token=<ATIVO 8ab9e3>` (JSON válido) | **200** |
| webhook `POST ?token=<errado>` | **401** |
| webhook `POST ?token=<novo 750af6 parqueado>` | **401** (rotação adiada — correto) |
| `alembic current` | `sprint91_lead_email_nullable (head)` |
| chokepoint de envio | `base=chatwoot-fazerai:3000, enabled=True, has_token=True` |
| `cwi_message_log` | **19** (intacto, cresceu c/ tráfego real) |
| `leads source=whatsapp` | **5** (intacto) |

> O `400` que apareceu no 1º teste do token ativo foi **artefato de escaping** do JSON no curl; com JSON válido deu **200**.

## 3. Fragilidade do `docker cp` ELIMINADA (para o backend)
- A imagem nova **não tem** os arquivos de segredo (`.whatsapp_webhook_secret`, `.chatwoot_token`).
- O backend novo lê **tudo do env (compose)**: `WHATSAPP_WEBHOOK_SECRET` (=ANTIGO `8ab9e3`, pois revertemos o `.env`), `CHATWOOT_BASE_URL/ACCOUNT_ID/INBOX_ID/API_TOKEN`.
- Prova: webhook valida o token ativo via env, e o chokepoint lê `base`/`token` do Chatwoot — tudo do env. **Recreate não reverteu nada** (código baked == host).

## 4. Estado das imagens / stack
```
:latest                 = 47b3f70359a5 (NOVA) — backend rodando nela
:rebuild-20260608       = 47b3f70359a5 (NOVA)
:pre-rebuild-20260608   = bfa169a24c06 (ROLLBACK)
backend                 -> 47b3f7 (NOVA) ✅
8 celery + flower       -> bfa169a2 (VELHA, com código cp'ado) — intactos, rodando
14 containers conecta-pro UP, nenhum fora do ar
```

## 5. 🚦 GATE — Bloco 2B (celery + flower) aguardando aprovação
Recriar os 8 celery + flower na imagem nova (mesmo padrão, via `docker-compose.yml` + `docker-compose.celery.yml`):
```bash
docker compose -f docker-compose.yml -f docker-compose.celery.yml up -d --no-deps --no-build \
  celery-beat celery-operacional celery-nfse celery-sefaz celery-batch celery-priority celery-integrations flower
```
- **Seguro:** os workers têm o mesmo código cp'ado (== host == imagem nova); recriar não reverte nada e elimina a fragilidade deles também.
- Validar pós: workers `healthy`, Celery processando, Flower no ar.
- **Não executado** — parei para revisão dos gates do backend.

## 6. 🔙 Rollback (sempre pronto)
```bash
docker tag conecta-pro-backend:pre-rebuild-20260608 conecta-pro-backend:latest
docker compose up -d --no-deps --no-build backend
```
A imagem antiga `bfa169a2` está intacta sob `:pre-rebuild-20260608`. Backup do banco: `backups/rebuild/pre_rebuild_20260608_150847.dump`.

## 7. Pendências (lembrete)
- **Rotação do segredo (T2)** segue **parqueada** (novo `750af6` staged); ativar depois (atualizar Chatwoot + alinhar `.env`/env).
- **T1 senders duplicados** — decisão de produto pendente.
- Pendências de banco do rebuild antigo (schema drift, OpenClaw warning) não são da imagem.

---
*Bloco 2A: swap de tag + recreate do backend (recreate sancionado, imagem com código baked). Gates validados, dados intactos. Celery/flower não tocados (próximo gate). Rollback pronto.*
