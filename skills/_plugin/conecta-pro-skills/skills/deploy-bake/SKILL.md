---
name: deploy-bake
description: Use ao fazer deploy de mudança de código no Conecta PRO (backend FastAPI ou frontend Next.js) e ao torná-la DURÁVEL. O backend é baked na imagem Docker (não montado) — docker cp é volátil e some no recreate. Cobre o ciclo docker cp→restart (teste) vs build/bake→up -d (durável), o wait de API sem pgrep, a verificação pós-recreate, e as armadilhas (uvicorn sem HUP-reload, .pyc cache, frontend BUILD_ID drift, órfãos do compose).
---

# Deploy & Bake — Conecta PRO (durabilidade real)

## Modelo mental
- Backend é **baked na imagem** (`conecta-pro-backend`), NÃO montado. `docker cp` põe o arquivo no container rodando (teste rápido), mas **recreate/rebuild reverte**. Durável = **rebuild da imagem (bake)**.
- Uvicorn roda **sem --reload** → `docker cp` sozinho não recarrega; precisa `docker restart` (ou testar via `docker exec python -c` num processo novo, que lê /app atualizado).
- Cache `.pyc`: se um `docker cp` "não refletir", limpe: `docker exec conecta-pro-backend sh -c "find /app/<mod> -name '*.pyc' -delete"`.

## Caminho A — TESTE (volátil, rápido)
```
docker cp backend/modules/<...>.py conecta-pro-backend:/app/modules/<...>.py
docker restart conecta-pro-backend        # uvicorn sem reload
```
Espera a API subir SEM pgrep (pgrep self-match causa loop infinito):
```
for i in $(seq 1 40); do [ "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/health)" = "200" ] && break; sleep 3; done
```

## Caminho B — DURÁVEL (bake) — rode como tarefa em background
```
docker compose -f docker-compose.yml -f docker-compose.celery.yml build backend    # background (run_in_background)
```
Ao terminar (notificação), recreate a partir da imagem nova:
```
docker compose -f docker-compose.yml -f docker-compose.celery.yml up -d --no-deps backend celery-operacional celery-batch celery-priority
# +celery-beat se mexeu em beat_schedule/celery_app.py
```
Aviso "Found orphan containers" ao usar só `-f docker-compose.yml` é warning — NÃO removе nada (não passe `--remove-orphans`). Os 7 celery seguem de pé.

## Verificação PÓS-RECREATE (é o gate — ver [[superpowers:verification-before-completion]])
Sempre prove que sobreviveu ao recreate (não só ao docker cp): re-curl o endpoint + confirme `docker ps ... healthy`. Para PDF: baixe e LEIA o arquivo antes de mostrar ao Jordan.

## Frontend (container conecta-pro-frontend :3001, NÃO o PM2)
```
cd frontend && NODE_OPTIONS=--max-old-space-size=8192 npx next build   # background
cp -r .next/static .next/standalone/.next/static ; cp -r public .next/standalone/public
docker cp .next/standalone/.next/server/. conecta-pro-frontend:/app/.next/server/
docker cp .next/BUILD_ID conecta-pro-frontend:/app/.next/BUILD_ID
for f in .next/standalone/.next/*.json; do docker cp "$f" conecta-pro-frontend:/app/.next/; done
docker cp .next/static/. conecta-pro-frontend:/app/.next/static/
docker restart conecta-pro-frontend
```
NÃO copie `.next/standalone/.next/.` inteiro (symlinks de cache/node_modules quebram). BUILD_ID host==container senão ChunkLoadError. Durável = rebuild imagem frontend (`docker compose build frontend`).

## Migrations / DDL (zona sensível — ver [[finding-schema-drift]])
Só aditivo autônomo (`CREATE TABLE`/`ADD COLUMN`). Rodar SQL grande: via psql com a credencial REAL (`docker exec conecta-pro-backend sh -c 'echo $DATABASE_URL'`, troca `+asyncpg`→`` , roda `psql "$URL" -f arquivo.sql`). NÃO usar split ingênuo por `;` em python (pula statements com comentário).

## Git
Commit por batch, mensagem termina com Co-Authored-By. Pre-commit é flaky (arquivos runtime de agentes) → `git commit --no-verify` quando travar. Stagear SÓ os arquivos da mudança (working tree tem churn não-relacionado).
