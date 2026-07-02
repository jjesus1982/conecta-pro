# Rebuild da imagem do backend — CONCLUÍDO (stack inteiro na imagem nova)

- **Data:** 2026-06-08 ~15:52 UTC
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Bakar todo o código (que rodava só via `docker cp`) na imagem do backend e migrar os 9 containers — eliminando a fragilidade onde "qualquer recreate revertia tudo".
- **Resultado:** ✅ **SUCESSO. Os 9 containers backend-image rodam a imagem nova, healthy. Zero na velha. Sem perda de dados. Rollback pronto.**

---

## 1. Resultado final
```
conecta-pro-backend             running/healthy  img=47b3f70359a5 (NOVA)
conecta-pro-celery-beat         running/healthy  img=47b3f70359a5
conecta-pro-celery-operacional  running/healthy  img=47b3f70359a5
conecta-pro-celery-nfse         running/healthy  img=47b3f70359a5
conecta-pro-celery-sefaz        running/healthy  img=47b3f70359a5
conecta-pro-celery-batch        running/healthy  img=47b3f70359a5
conecta-pro-celery-priority     running/healthy  img=47b3f70359a5
conecta-pro-celery-integrations running/healthy  img=47b3f70359a5
conecta-pro-flower              running/healthy  img=47b3f70359a5
```
- **Containers na imagem velha (`bfa169a2`): 0.**
- 14 containers conecta-pro UP; frontend/postgres/redis intocados.

## 2. Como foi feito (3 blocos, com gates)
- **Bloco 1 (seguro, sem tocar produção):** backup do banco → tag de rollback `pre-rebuild-20260608` → `.dockerignore` blindando segredos → `docker build` (tag própria `rebuild-20260608`) → **validação efêmera** (`--network none`, imports críticos OK, md5 host==imagem, migrations presentes, segredos não bakados).
- **Bloco 2A (recreate do backend):** swap `:latest` → recreate só do backend → **todos os gates OK**.
- **Bloco 2B (recreate dos 8 celery + flower):** mesmo padrão → todos healthy na imagem nova.

## 3. Gates de produção validados (pós-rebuild completo)
| Gate | Resultado |
|------|-----------|
| `/health` (público) | **200** |
| webhook `?token=<ATIVO 8ab9e3>` | **200** |
| webhook sem token / token errado / token novo | **401** |
| `alembic current` | `sprint91_lead_email_nullable (head)` |
| chokepoint de envio | `base=chatwoot-fazerai:3000, enabled, has_token` |
| dados | `cwi_message_log=19`, `leads whatsapp=5` (intactos, cresceram com tráfego real) |

## 4. Mudança importante: secrets agora via ENV (não mais arquivo cp'ado)
- A imagem nova **não contém** `.whatsapp_webhook_secret`/`.chatwoot_token`. Ao recriar, esses arquivos **deixaram de existir** nos containers.
- O backend lê **tudo do env (compose → `/opt/conecta-pro/.env`)**: `WHATSAPP_WEBHOOK_SECRET` (=ANTIGO `8ab9e3`), `CHATWOOT_*`, `WHATSAPP_API_ENABLED`. Validado em produção (webhook 200, envio OK).
- **Implicação para a rotação T2:** o mecanismo mudou — agora é **env-based**. O segredo NOVO (`750af6`) segue preservado no host em `/opt/conecta-pro/.webhook_secret.new`. Para ativar: atualizar Chatwoot c/ token novo → `WHATSAPP_WEBHOOK_SECRET` no `.env` para o novo → `docker compose up -d --no-deps --no-build backend` (recreate, agora barato e seguro). Os arquivos `.new` que estavam nos containers foram descartados no recreate (não são mais o caminho).

## 5. 🔙 Rollback (disponível)
```bash
docker tag conecta-pro-backend:pre-rebuild-20260608 conecta-pro-backend:latest
docker compose up -d --no-deps --no-build backend
docker compose -f docker-compose.yml -f docker-compose.celery.yml up -d --no-deps --no-build \
  celery-beat celery-operacional celery-nfse celery-sefaz celery-batch celery-priority celery-integrations flower
```
- Imagem antiga `bfa169a24c06` intacta sob `:pre-rebuild-20260608`.
- Backup do banco: `backups/rebuild/pre_rebuild_20260608_150847.dump`.
- Sugestão: manter a tag de rollback por alguns dias; remover depois (`docker rmi conecta-pro-backend:pre-rebuild-20260608` + `:rebuild-20260608`) quando houver confiança.

## 6. Pendências (separadas do rebuild)
- **T1 — senders duplicados:** decisão de produto pendente (diaristas stub: ativar envio? portal legado WhatsApp→ticket+IA: matar/migrar/deixar?).
- **T2 — rotação do segredo:** parqueada; ativar quando quiser (agora via env, §4).
- **Banco (do rebuild antigo):** schema drift (alguns GETs 500 por migration faltante), warning OpenClaw não-fatal — não são da imagem; monitorar.
- O recreate emitiu warning de "orphan containers" (staging) — benigno.

---
*Rebuild executado com gates/pausas aprovados, recreate sancionado (imagem com código baked == host), produção validada, dados intactos, rollback pronto. Segredos não expostos. Stack 100% na imagem nova.*
