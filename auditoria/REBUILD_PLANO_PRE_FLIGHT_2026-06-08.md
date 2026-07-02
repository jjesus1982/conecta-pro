# Rebuild da imagem do backend — Plano + pré-flight (READ-ONLY, NÃO buildei)

- **Data:** 2026-06-08
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Bakar no `conecta-pro-backend:latest` todo o código que hoje roda só via `docker cp`, eliminando a fragilidade (qualquer recreate reverte tudo).
- **Status:** 🔵 **Plano pronto, NADA executado.** Aguardando aprovação + o gate do segredo (T2).

---

## 1. Procedimento já validado (doc `REBUILD_IMAGEM_2026-05-30.md`)
O rebuild de 30/mai foi bem-sucedido com este fluxo (sem editar compose):
1. `docker build` da imagem nova com **tag própria** (ex.: `rebuild-20260608`).
2. **Validar em container EFÊMERO** na **rede de staging** (`conecta-staging-network`) — **nunca** em produção: o `lifespan` sobe consumidor de EventBus + GEDEON, que no Redis de produção roubaria/processaria eventos reais.
3. **Swap por TAG** (compose intocado): `docker tag …:latest …:pre-rebuild-<data>` (âncora de rollback) → `docker tag rebuild-<data> …:latest`.
4. `docker compose up -d --no-deps --no-build backend` (e os 8 celery + flower).
5. Validar `/health`, contagem de rotas, imports, DP, GEDEON.
6. **Rollback a 1 sequência** (re-tag da antiga → up).

> O Dockerfile (`COPY --chown=erp:erp . .`) é não-seletivo → captura `modules/` e `alembic/`. **Não tem defeito; a imagem só está velha.**

## 2. Pré-flight (estado atual — verificado)
| Item | Estado |
|------|--------|
| Imagem rodando | `bfa169a24c06` (`conecta-pro-backend:latest`, 30/mai) |
| host == container (base do build) | ✅ confirmado (61 arquivos, DRIFT=0; ex.: service.py md5 `61e8bb…`) |
| Disco (`/var/lib/docker`) | **321G livres** (18% usado) — suficiente |
| Divergência a bakar | **61 .py** (51 models/controllers/services + 10 migrations) |
| Segredos no contexto do host | ❌ ausentes (`.whatsapp_webhook_secret`, `.chatwoot_token`) → **não serão baked** (bom) |
| Secrets pós-rebuild | vêm do **env do compose** (`/opt/conecta-pro/.env` tem CHATWOOT_BASE_URL/ACCOUNT_ID/INBOX_ID/API_TOKEN + WHATSAPP_WEBHOOK_SECRET) |

## 3. ⚠️ Acoplamento crítico com a rotação do segredo (T2)
- O rebuild faz **recreate**; o container novo recebe `WHATSAPP_WEBHOOK_SECRET` do `.env` (que **já está no NOVO** `750af6…`) via compose → **o rebuild ATIVA o segredo novo automaticamente**.
- **Portanto:** a URL do webhook no **Chatwoot precisa estar com o token NOVO ANTES** do rebuild. Caso contrário, após o recreate o webhook exige o NOVO e o Chatwoot manda o ANTIGO → **401 → entrada quebra**.
- **Ordem obrigatória:** (1) atualizar Chatwoot c/ token novo → (2) rebuild/recreate. (Assim T2 e T3 fecham juntos: o próprio recreate ativa o novo segredo, dispensando o swap do arquivo.)

## 4. Por que o recreate aqui é SEGURO (exceção à regra "nunca recriar")
- A regra "nunca recriar" existe porque a imagem velha **não tem** o código `docker cp`'ado → recriar reverteria.
- **O rebuild resolve exatamente isso:** a imagem nova **baka os 61 arquivos** (host==container verificado). Recriar a partir dela **não reverte nada** — é o passo que **elimina** a fragilidade.

## 5. Plano passo a passo (PROPOSTA — sob aprovação)
**Pré:**
- a) **Gate T2:** confirmar que o Chatwoot já usa o token NOVO.
- b) **Backup do banco** (`pg_dump -Fc`).
- c) Adicionar ao `.dockerignore`: `.whatsapp_webhook_secret*`, `.chatwoot_token` (defesa; evita bakar segredo se criado no host).
- d) `docker tag conecta-pro-backend:latest conecta-pro-backend:pre-rebuild-20260608` (âncora de rollback).

**Build + validação efêmera:**
- e) `docker compose -f docker-compose.yml build backend` (ou `docker build -t conecta-pro-backend:rebuild-20260608 ./backend`).
- f) Subir **container efêmero** na rede de staging, validar: `import` dos módulos novos (whatsapp service/controller, lead), `/health`, contagem de rotas, sem erro de import.

**Deploy por tag (compose intocado):**
- g) `docker tag conecta-pro-backend:rebuild-20260608 conecta-pro-backend:latest`.
- h) `docker compose up -d --no-deps --no-build backend` → recreate do backend a partir da nova imagem.
- i) Repetir para os 8 celery + flower (mesma imagem).

**Validação pós-deploy:**
- j) `/health` 200; webhook `POST ?token=<NOVO>` → 200, `?token=<ANTIGO>` → 401; envio (chokepoint) OK; `cwi_message_log`/leads intactos; `alembic current` = `sprint91…`.
- k) Confirmar que `.whatsapp_webhook_secret`/`.chatwoot_token` **não** existem mais (agora via env) — ou mantê-los como fallback.

**Rollback (sempre pronto):**
- l) `docker tag conecta-pro-backend:pre-rebuild-20260608 conecta-pro-backend:latest` → `docker compose up -d --no-deps --no-build backend` (+ celery). A imagem antiga `bfa169a2` fica intacta sob a tag.

## 6. Riscos / observações
- O rebuild de 30/mai listou pendências que **continuam** (não são da imagem): schema drift B3 (alguns GETs 500 por coluna/migration faltante), warning OpenClaw não-fatal, celery-batch/Redis intermitente. O rebuild **não** as resolve.
- Migrations sprint90/sprint91 já estão **aplicadas no banco** e os arquivos serão baked — sem reaplicar (DB já no head).
- `backend/.env` tem 2/3 das vars Chatwoot/secret; **o que importa é o `.env` do compose** (tem as 3). Alinhar `backend/.env` é higiene opcional.

## 7. 🚦 GATE
**Não rodei `docker build`, não recriei nada, não troquei tag.** Aguardo: (1) confirmação do gate T2 (Chatwoot c/ token novo) e (2) seu "pode buildar" para executar o plano §5 passo a passo, com pausas.

---
*Read-only: leitura do roteiro, `docker inspect/images`, `md5sum`, `df`, `grep` no `.env`. Nenhum build/tag/recreate.*
