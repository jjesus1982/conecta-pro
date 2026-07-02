# Estado do env do copiloto WhatsApp — OFF, NÃO foi meu rebuild (READ-ONLY)

- **Data:** 2026-06-10 (gerado 2026-06-11)
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Token:** STEP-0-AGENT-ENV-RO
- **Modo:** 100% READ-ONLY — não toquei compose/.env/Dockerfile; nada rebuildado/reiniciado.
- **Veredito:** ✅ **Copiloto OFF agora.** ❌ **NÃO foi regressão dos rebuilds de hoje** — é fragilidade de **env-wiring pré-existente** (compose editado de manhã às 10:44; AGENT_ENABLED sempre foi runtime-only).

---

## a) Estado AGORA no backend
```
AGENT_ENABLED        = UNSET   →  agent_enabled() = FALSE (copiloto OFF)
CHATWOOT_API_TOKEN   = UNSET   →  _post_private_note aborta + sem download de áudio
CHATWOOT_BASE_URL    = UNSET
CHATWOOT_ACCOUNT_ID  = UNSET
WHATSAPP_WEBHOOK_SECRET = UNSET (webhook ainda funciona: 'if expected:' pula auth quando vazio)
OPENAI_API_KEY       = SET (164 chars)
```
- Celery (operacional/batch/beat): AGENT_ENABLED/CHATWOOT/OPENAI **todos UNSET** (só o backend recebe OPENAI). O copiloto roda como **BackgroundTask no backend** (não celery), então o relevante é o backend.
- `Config.Env` do container (docker inspect): só `WHATSAPP_API_ENABLED=true`, `OPENAI_API_KEY`, `WHATSAPP_INSTANCE_ID` — **nenhuma AGENT/CHATWOOT**.

## b) O compose injeta essas vars? → NÃO
- Backend usa **`environment:` explícito** (l.60), **sem `env_file`** (`env_file` = **0 ocorrências** no compose inteiro).
- O bloco lista OPENAI_API_KEY (por isso SET), mas **AGENT_ENABLED não aparece em compose algum**, e **CHATWOOT_API_TOKEN/CHATWOOT_BASE_URL não estão no backend** atual.
- As 4 ocorrências "CHATWOOT" no compose atual são de **outros serviços** (chatwoot container `SECRET_KEY_BASE`, evolution-api `CHATWOOT_ENABLED`), não do backend.

## c) As vars estão na IMAGEM (Dockerfile ENV)? → NÃO
- `backend/Dockerfile`: ENV só `PYTHONUNBUFFERED/PYTHONDONTWRITEBYTECODE/PORT`. **Nunca bakou AGENT/CHATWOOT.**
- Imagem ANTIGA `5a14e5db` (efêmero --network none): `AGENT_ENABLED=UNSET`, `CHATWOOT_API_TOKEN=UNSET`. **Sempre vieram de runtime.**

## d) Onde AGENT_ENABLED aparece em /opt/conecta-pro
- **Só em `.env:214` → `AGENT_ENABLED=true`.** Nenhum compose, override (não existe `docker-compose.override.yml`), Makefile ou script o referencia.
- `.env` também tem CHATWOOT_API_TOKEN, CHATWOOT_BASE_URL=http://chatwoot-fazerai:3000, CHATWOOT_ACCOUNT_ID=1, WHATSAPP_WEBHOOK_SECRET (todos presentes, mas **não puxados** p/ o backend por falta de env_file/listagem).

## e) VEREDITO: OFF, e NÃO foi meu rebuild
- **Copiloto está OFF agora** (evidência (a)).
- **`docker-compose.yml` mtime = 2026-06-10 10:44:58** (manhã). Meus rebuilds de hoje (backend ~20:44, frontend ~21-22h) **só rodaram `docker compose up`** — `up` **não modifica** o arquivo. Logo o compose já estava nesse estado **antes** do meu rebuild.
- **Fragilidade de env-wiring (não da imagem):**
  - `AGENT_ENABLED` **nunca esteve em compose** (nem no `.bak-agent` de 06-08) → no 06-08/09 veio de **runtime** (provável `--env-file .env` ou `-e` manual ao subir o container). **Qualquer recreate o perde.**
  - O bloco **CHATWOOT_*** estava no `docker-compose.yml.bak-agent-20260608_180428` (backend env: CHATWOOT_BASE_URL/ACCOUNT_ID/INBOX_ID/API_TOKEN + WHATSAPP_WEBHOOK_SECRET) mas **sumiu do compose atual** (editado 10:44 hoje).
- **Conclusão:** o copiloto caiu por **env não-durável** (AGENT_ENABLED runtime-only + bloco CHATWOOT removido do compose na edição das 10:44), **propagado pelos recreates** (followup rebuild de manhã + os meus). **Não é defeito dos meus rebuilds** — eles usaram um compose já deficiente. O agente parou de produzir output em **06-09 13:32**, antes de tudo hoje.

## f) Última vez que o agente rodou de fato
- `cwi_message_log` direction='drf' (rascunhos do agente): **7 drafts**, de **2026-06-08 16:58** a **2026-06-09 13:32:20**. **Nenhum depois.** Última nota/rascunho = **06-09 13:32**, **antes** do rebuild de hoje (20:44).
- **Sem mensagens incoming após 2026-06-10 20:00** → não dá pra observar o comportamento atual ao vivo (nenhum gatilho desde então).

## g) Restauração de menor risco (RECOMENDAÇÃO — NÃO executei; compose é forbidden zone)
**Tornar o env durável no compose** (sobrevive a recreates), espelhando o `.bak-agent` + adicionando AGENT_ENABLED — no bloco `environment:` do **backend** em `docker-compose.yml`:
```yaml
      AGENT_ENABLED: ${AGENT_ENABLED:-false}
      CHATWOOT_BASE_URL: ${CHATWOOT_BASE_URL:-http://chatwoot-fazerai:3000}
      CHATWOOT_ACCOUNT_ID: ${CHATWOOT_ACCOUNT_ID:-1}
      CHATWOOT_INBOX_ID: ${CHATWOOT_INBOX_ID:-1}
      CHATWOOT_API_TOKEN: ${CHATWOOT_API_TOKEN:-}
      WHATSAPP_WEBHOOK_SECRET: ${WHATSAPP_WEBHOOK_SECRET:-}
```
(Todas já existem no `.env` → interpolação resolve.) Depois `docker compose up -d --no-deps --force-recreate backend`.
- **Alternativa** (mais simples, menos controlada): `env_file: .env` no backend — injeta **tudo** do .env (pode trazer vars indesejadas; não recomendado).
- **Decisão do Jordan** (editar compose). Sem isso, **todo recreate volta a desligar** o copiloto — e a tool de áudio (que depende de AGENT_ENABLED + CHATWOOT_API_TOKEN p/ baixar o áudio) não tem como ser exercida.
- ⚠️ **NÃO mexer no `.env`/mailer** (memória) — só referenciar as vars no compose via `${...}`.

---

## Resumo
- **Copiloto OFF:** AGENT_ENABLED/CHATWOOT_API_TOKEN UNSET no backend; `agent_enabled()=FALSE`. OPENAI SET.
- **Causa = env-wiring, não imagem:** compose sem env_file e sem o bloco do agente (AGENT_ENABLED nunca esteve em compose; CHATWOOT removido na edição de 10:44 hoje). `.env` tem tudo, mas não é puxado.
- **NÃO foi meu rebuild:** compose mtime 10:44 (manhã); meus rebuilds (20:44+) só fizeram `up`. Agente parou 06-09, antes de hoje.
- **Fix (recomendado, p/ Jordan):** re-adicionar o bloco do agente ao `environment:` do backend (via `${VAR}` do .env) + recreate → durável. Pré-requisito do STT de áudio.

*Read-only: printenv/inspect dos containers, efêmero --network none da imagem antiga (removido), leitura de .env/compose/.bak/Dockerfile (mascarado), SELECT de drafts, stat de mtime. Nada editado/buildado/reiniciado.*
