# Pré-flight de rebuild do backend — levantamento READ-ONLY ✅

- **Data:** 2026-06-10
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Token:** STEP-0-REBUILD-RO
- **Modo:** 100% READ-ONLY — zero build/commit/cp/restart/recreate/alembic. Só leitura.
- **Objetivo:** provar exatamente o que precisa entrar na imagem nova e o que acontece no boot.

---

## a) Git: o que está sujo/untracked — e a MIGRATION
- **Working tree sujo (resumo):** `3 M` + `30 D` + `140 ??`.
  - **3 M** = arquivos de cron: `agents/cto/predicao/{enviados,metricas,state}.json` (mexidos por rotina — causa do pre-commit flaky).
  - **30 D** = snapshots antigos `agents/cto/memory/snapshots/*.json` (deletados por housekeeping).
  - **140 ??** = `auditoria/`, dezenas de `.bak*`, e **várias migrations untracked**.
- **`git diff HEAD --stat` = SÓ arquivos de cron/snapshot** (8 ins / 878 del, todos `agents/cto`). **Zero resíduo de código** — working tree == HEAD nos arquivos de proposta (sem sobra de `--no-verify`/ruff).
- 🔴 **A migration `sprint94_proposal_terms.py` está UNTRACKED** (`??`; `git ls-files` vazio). Em disco: `backend/alembic/versions/sprint94_proposal_terms.py` (3090 bytes, 10/jun 15:02).
  - Comparação: `sprint92_proposal_followups.py` e `sprint93_client_email_nullable.py` **estão tracked** (commitadas em `dd57f47b` e `9dfc96dd`). **Só a sprint94 ficou de fora.**
  - Outras migrations **untracked** em disco: `camada3_{benchmarks,exec_kpis,financial_kpis,report_schedules,report_templates}.py`, `drop_openclaw_tables.py`, `findp_b1b2_20260601.py`, `frente2_renames_20260530.py`, `sprint90_cwi_message_log.py`, `sprint91_lead_email_nullable.py`.
- **Commits-chave (todos no branch `feature/people-management-reorganization`):**
  | Commit | Arquivos |
  |--------|----------|
  | `9dfc96dd` | sprint93 migration **(tracked)** + models/proposal.py + schemas/proposal.py + frontend page.tsx |
  | `36e1c203` | lead_controller.py + opportunity_controller.py + proposal_controller.py |
  | `eaf0fdf2` | models/proposal.py + repositories/proposal_repository.py + schemas/proposal.py |
  | `bbcc27cc` | repositories/proposal_repository.py |
- **Decisão de commit (registrar, não executar):** a sprint94 (e idealmente sprint90/91) deveriam ser **commitadas** antes de um build a partir de `git clone`. Para um build **a partir deste disco**, ela já está presente (ver item "g").

## b) BOOT roda alembic? → **NÃO**
- `backend/Dockerfile`: **sem ENTRYPOINT**; `CMD ["uvicorn","main_production:app","--host","0.0.0.0","--port","8080","--timeout-graceful-shutdown","25"]`.
- `main_production.py`: grep `alembic|upgrade head|migrat` = **vazio** (lifespan sobe Redis/EventBus/SOPHIA/GEDEON/GDrive — **nenhum alembic**).
- Nenhum `entrypoint.sh`/`start.sh` roda `alembic upgrade`.
- **Consequência:** o boot **não** aplica migrations nem falha por ausência delas. A imagem nova só precisa que o **código** combine com o schema do banco (que já está no head `sprint94`). A migration commitada é desejável por **reprodutibilidade/clone**, **não** por boot.

## c) Os 9 containers compartilham a mesma imagem? → **SIM**
- **Todos os 9** (`backend` + `flower` + 7 `celery-*`) rodam **`sha256:5a14e5dbe456`** (`conecta-pro-backend` == `conecta-pro-backend:latest`). **Um único rebuild serve aos 9.**
- Os **commands diferem** e vêm do **compose** (não da imagem): backend = `uvicorn main_production:app ...`; flower = `celery -A celery_app flower --port=5555 ...`; beat = `celery -A celery_app beat ...`; workers = `celery -A celery_app worker --queues=<fila> ...` (nfse/priority/sefaz/batch/integrations/operacional).
- `Dockerfile.celery` (`FROM conecta-pro-backend:latest`) **não está em uso** pelos containers atuais — os celery rodam a própria `:latest` com command sobrescrito pelo compose.

## d) host==container nos arquivos-chave → **TODOS MATCH, zero DIFF**
| Arquivo | host md5 | status |
|---------|----------|--------|
| modules/crm/models/proposal.py | `f6b1d42b…` | **MATCH** |
| modules/crm/schemas/proposal.py | `81a1ced7…` | **MATCH** |
| modules/crm/repositories/proposal_repository.py | `c21560b1…` | **MATCH** |
| modules/crm/controllers/proposal_controller.py | `f2beef3f…` | **MATCH** |
| modules/crm/controllers/lead_controller.py | `71c33faa…` | **MATCH** |
| modules/crm/controllers/opportunity_controller.py | `4b277664…` | **MATCH** |
| alembic/versions/sprint94_proposal_terms.py | `a8b657ec…` | **MATCH** (presente no container) |
- O container **backend** já tem o código novo (via `docker cp`) idêntico ao disco. A **imagem** `5a14e5db`, porém, **é velha**: foi buildada no "rebuild followup" com head `sprint92`, bakando `eb60ea82/dd57f47b/38baa711` — **NÃO contém** 9dfc96dd/36e1c203/eaf0fdf2/bbcc27cc nem sprint93/94. **É por isso que recreate hoje reverteria** e o rebuild é necessário.
- alembic no container: chain íntegra, head `sprint94_proposal_terms`; arquivo sprint94 presente em `/app/alembic/versions/`.

## e) Procedimento/script de rebuild documentado → **SIM**
- **Makefile** `rebuild` target: `make rebuild SVC=backend` → `docker compose build backend --no-cache && docker compose up -d backend`.
- **Fluxo seguro documentado** (`REBUILD_IMAGEM_2026-05-30.md`, `REBUILD_PLANO_PRE_FLIGHT_2026-06-08.md`, `REBUILD_FOLLOWUP_COMPLETO_2026-06-10.md`):
  1. `docker build` com **tag própria** (ex.: `rebuild-<data>`).
  2. **Validar em container EFÊMERO** em rede de **staging** (`--network none`/staging) — nunca em produção (lifespan sobe consumidor de EventBus/GEDEON que processaria eventos reais do Redis prod).
  3. **Swap por TAG** (compose intocado): `docker tag :latest :pre-rebuild-<data>` (âncora rollback) → `docker tag rebuild-<data> :latest`.
  4. `docker compose up -d --no-deps --no-build backend` (+ os 8 celery + flower).
  5. Validar `/health` 200, rotas, imports, alembic.
  6. **Rollback a 1 sequência:** re-tag da `pre-rebuild-*` → `up`.
- Backups/dumps são feitos antes de cada rebuild (ex.: `pre_rebuild_followup_20260610_072754.dump`).

## f) Banco persiste em volume separado? → **SIM. proposals=3 confirmado.**
- Postgres (`conecta-pro-postgres`) monta **volume nomeado `conecta-pro_postgres_data`** (`/var/lib/docker/volumes/conecta-pro_postgres_data/_data` → `/var/lib/postgresql/data`). + bind read-only do `init-db.sql` (só roda em volume vazio).
- **Recreate/rebuild do backend NÃO toca o volume do postgres** — dados preservados.
- `proposals = 3`: `00001`(sent, 1800) / `00091`(sent, 11420) / `00092`(sent, 11210). `alembic_version` (no banco) = **`sprint94_proposal_terms`** (= head do container).

## g) O que EXATAMENTE precisa entrar na imagem nova (== produção-validada)
**Código (já em disco = HEAD, host==container):**
1. `modules/crm/models/proposal.py` (9dfc96dd + eaf0fdf2)
2. `modules/crm/schemas/proposal.py` (9dfc96dd + eaf0fdf2)
3. `modules/crm/repositories/proposal_repository.py` (eaf0fdf2 + bbcc27cc)
4. `modules/crm/controllers/proposal_controller.py` (36e1c203)
5. `modules/crm/controllers/lead_controller.py` (36e1c203)
6. `modules/crm/controllers/opportunity_controller.py` (36e1c203)

**Migration (em disco, untracked):**
7. `alembic/versions/sprint94_proposal_terms.py`

> Como o `Dockerfile` faz `COPY --chown=erp:erp . .` (contexto = **disco**, não git), **todos os 7 entram automaticamente** num build a partir deste host — inclusive a sprint94 untracked. O `.dockerignore` exclui `.git/`, `.env`, `*.bak`, `backups/`, `*.md`, `docker-compose*.yml`, `__pycache__` — **não exclui** `alembic/versions/*.py` (bom: a migration entra).

---

## ⚠️ Riscos/inconsistências encontrados (reportados, NÃO corrigidos)
1. 🔴 **`docker images` e `docker image inspect` TRAVAM** (timeout/Terminated) agora; `docker inspect <container>`/`exec`/`ps` funcionam. O **image store está irresponsivo** → **`docker build`/`docker tag` podem travar**. **Resolver isso ANTES do rebuild** (verificar containerd/lock/disk; o rebuild de hoje funcionou, então pode ser transitório). Não consegui enumerar tags/âncoras de rollback ao vivo por causa disso — elas constam dos docs (`pre-rebuild-followup-20260610=c4bde53`, etc.).
2. **`*.bak*` não excluídos pelo `.dockerignore`:** o padrão `*.bak` **não** casa `*.py.bak-proposalfix-...` (não terminam em `.bak`) → **79 arquivos `.bak*` entrariam na imagem** (ruído inócuo, não importados). Contexto `backend/` ≈ 1.5G; `uploads/` também não está no `.dockerignore`.
3. **sprint94 (e sprint90/91) untracked:** build-a-partir-do-disco OK; build-a-partir-de-`git clone` **perderia** essas migrations. Decisão de commit pendente (fora do escopo deste RO).
4. **Acoplamento de segredo (do pré-flight 2026-06-08):** o recreate injeta `WHATSAPP_WEBHOOK_SECRET` do `.env`; o token no **Chatwoot precisa casar** antes do recreate, senão a entrada do webhook quebra (401). Verificar alinhamento atual antes de recriar.

## Resumo factual
- **Boot não roda alembic** (CMD uvicorn puro) → migration não é pré-requisito de boot, só de reprodutibilidade.
- **9 containers = 1 imagem `5a14e5db`** → 1 rebuild serve todos; commands vêm do compose.
- **host==container = MATCH** em 6 código + 1 migration; a **imagem é que está velha** (não tem o código cp'ado).
- **DB em volume nomeado** separado, `proposals=3`, head `sprint94` — rebuild/recreate não ameaça os dados.
- **Procedimento documentado** (Makefile + docs REBUILD_*): build tag própria → validação efêmera → swap por tag → up --no-deps --no-build → rollback por re-tag.
- **7 itens** a bakar (6 código + sprint94) — todos já em disco; entram via `COPY . .`.
- **Bloqueador a tratar antes:** image store do Docker travando (`docker images`/`image inspect`).

*Read-only: git status/diff/log/show/ls-files, cat Dockerfile/.dockerignore/Makefile/docs, docker inspect (containers), md5sum host+container, SELECT. Nenhum build/commit/cp/restart/recreate/alembic. Nada alterado.*
