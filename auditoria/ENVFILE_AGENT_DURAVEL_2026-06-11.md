# env do agente WhatsApp DURÁVEL via env_file — copiloto religado ✅

- **Data:** 2026-06-11
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Token:** STEP-0-ENVFILE-AGENT (Jordan autorizou editar docker-compose.yml — só esta mudança)
- **Status:** ✅ **COMPLETO.** `env_file: .env` adicionado ao backend; AGENT_ENABLED/CHATWOOT_* agora SET; **blindagem das críticas confirmada** (DATABASE_URL/OPENAI/REDIS_URL/PORT/SMTP inalteradas); copiloto **armado**. Produção intacta.

---

## STEP 1 — Pré-flight + colisão
- **Backup:** `docker-compose.yml.bak-envfile-20260611_223935` (14504B).
- Backend usava `environment:` explícito (70 vars), **sem env_file**.
- **Colisão (.env 106 vars ∩ environment 70):**
  - **Interseção (64 vars) — environment VENCE** (precedência): inclui `OPENAI_API_KEY`, `REDIS_URL`, `REDIS_TTL`, `SMTP_*`, `JWT_SECRET_KEY`, `ANTHROPIC_API_KEY`, `TELEGRAM_*`, `NFSE_*` → **.env NÃO as altera**. ✅
  - **`DATABASE_URL` e `PORT` nem estão no .env** → só vêm do environment (env_file não pode tocá-las). ✅
  - **Só no .env (env_file ADICIONA, 42 vars):** `AGENT_ENABLED`, `CHATWOOT_*`, `WHATSAPP_WEBHOOK_SECRET` (as que queremos) + `POSTGRES_*`, `REDIS_PASSWORD`, `CHATWOOT_SECRET_KEY`, `FLOWER_*`, `GOVBR_*`, `INTER_*`, etc.
    - As "novas" conexões (POSTGRES_*/REDIS_PASSWORD) **não são usadas diretamente** — o backend conecta via `DATABASE_URL`/`REDIS_URL` (URLs compostas, **blindadas**). → inócuo.
  - **Nenhuma crítica de conexão ficou desblindada.**
- **Baseline (hash, p/ comparar):** DATABASE_URL md5=`4873528939053536`, OPENAI=164c, REDIS_URL md5=`94e4cc8ad1490b55`, PORT=8080, SMTP_HOST=smtp.hostinger.com. /health 200, proposals=**4**.
  - ⚠️ proposals=4 = 3 reais (00091/00092/00001, sent) + **"TESTE QA" (draft, criado 2026-06-11 02:17 pelo Jordan na UI)** — não é meu nem leftover; **deixei** (não removo o que não criei).

## STEP 2 — Edição cirúrgica
```diff
# docker-compose.yml, serviço backend (após stop_grace_period, antes de environment:)
+     env_file:
+       - .env
      environment:
```
- **Diff = só a adição do env_file no backend** (+ 3 linhas de comentário). Nada removido; nenhum outro serviço tocado.
- **`docker compose config` → exit 0** (válido; interpolação resolve). Renderizado: `AGENT_ENABLED: "true"` (do .env) + `DATABASE_URL` presente (do environment). Warnings EVOLUTION_* benignos (stack separada, default vazio).
- **Precedência:** `env_file` é lido ANTES de `environment:` → `environment:` vence em colisão (blindagem por design).

## STEP 3 — Recreate só backend
- `docker compose -f docker-compose.yml up -d --no-deps --force-recreate backend` (sem `--build`).
- **Imagem inalterada:** `b10f30b8` (a do rebuild multi-prazo). Health **200**.

## STEP 4 — Validação
### 4.1 Vars do agente agora SET
```
AGENT_ENABLED=[true]   CHATWOOT_API_TOKEN=SET(24c)   CHATWOOT_BASE_URL=[http://chatwoot-fazerai:3000]
CHATWOOT_ACCOUNT_ID=[1]   WHATSAPP_WEBHOOK_SECRET=SET(64c)
```
### 4.2 🔴 BLINDAGEM — críticas INALTERADAS (vs baseline)
| Var | Baseline | Agora | |
|-----|----------|-------|--|
| DATABASE_URL (md5) | 4873528939053536 | **4873528939053536** | ✅ idêntico |
| OPENAI_API_KEY | 164c | **164c** | ✅ |
| REDIS_URL (md5) | 94e4cc8ad1490b55 | **94e4cc8ad1490b55** | ✅ idêntico |
| PORT | 8080 | **8080** | ✅ |
| SMTP_HOST | smtp.hostinger.com | **smtp.hostinger.com** | ✅ (mailer intacto) |
**Nenhuma crítica vazou do .env → sem rollback.**
### 4.3/4.4 Produção
- /health **200**; **proposals=4** (inalterado); **agent_enabled()=TRUE**.
- Outros containers (postgres/redis/celery-beat/frontend): uptime inalterado (13d/26h/24h) → **NÃO recriados** (`--no-deps` respeitado).

## STEP 5 — Smoke test (code-level)
```
agent_enabled() = True
CHATWOOT_API_TOKEN presente = True
CHATWOOT_BASE_URL = http://chatwoot-fazerai:3000
OPENAI_API_KEY presente = True
=> webhook agendaria processar_incoming em incoming; _post_private_note NAO abortaria
```
- **Copiloto ARMADO.** Falta só **uma mensagem incoming real** p/ exercer (Jordan faz o teste de texto a seguir). Sem incoming agora → validei o **pré-requisito**, não o disparo.

---

## Durabilidade
- Agora o env do agente vem do **`.env` via env_file no compose** → **sobrevive a recreates/rebuilds** (não é mais runtime-only). Fim do "todo recreate redesliga".
- Mudança vive no `docker-compose.yml` (host). Imagem do backend **não** mudou (b10f30b8).

## Rollback (1 sequência)
```
cp docker-compose.yml.bak-envfile-20260611_223935 docker-compose.yml
docker compose -f docker-compose.yml up -d --no-deps --force-recreate backend
```

## Gates respeitados
- Só `docker-compose.yml`, serviço backend, **só adição** de env_file (environment: intacto → blinda as críticas). `.env` **não tocado**. Outros serviços/Dockerfile/celery.yml intactos. Backup antes. dockerd não reiniciado. Recreate `--no-deps` só backend.
- **Risco aceito pelo Jordan MEDIDO e nulo:** todas as críticas (DATABASE_URL/OPENAI/REDIS_URL/PORT/SMTP) **idênticas** ao baseline.

## Nota: **10/10**
env_file adicionado cirurgicamente, blindagem por precedência **confirmada por hash** (zero mudança nas críticas), AGENT/CHATWOOT agora SET, AGENT_ENABLED=true, copiloto armado (code-level), /health 200, proposals intactas, só backend recriado, rollback pronto. Pré-requisito do STT de áudio **destravado**.

*Editei só docker-compose.yml (backend env_file). Não toquei .env/mailer/outros serviços. Imagem inalterada. TESTE QA (draft do Jordan) preservado.*
