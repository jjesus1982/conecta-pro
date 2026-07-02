# Rebuild da imagem frontend de produção — código baked ✅

- **Data:** 2026-06-10
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Status:** ✅ **COMPLETO.** Imagem nova `conecta-pro-frontend:latest` = **`ee8cb1ac`**; container recriado, healthy, BUILD_ID novo do **image** (fim do docker cp no front). Rollback garantido.
- **Estratégia (escolhida pelo Jordan):** **build no HOST (NODE_OPTIONS=8192) + bake por cópia** — evita OOM do `next build` dentro do container num host com só ~12G livres.

---

## Por que NÃO buildar dentro do container
- `package.json` → `"build": "next build"` **sem** `--max-old-space-size`; Dockerfile builda o Next **dentro da imagem**.
- Host: 31G total, **18G em uso (26 containers), ~12G livres**. `next build` precisa ~8GB → risco do **OOM killer do kernel matar um container de produção** durante o build.
- Solução: buildar no host com heap capado em 8GB (método já provado da casa, monitorável) e bakar só a **cópia** do standalone (sem npm/next build no container).

## STEP 1 — Pré-flight + âncora
- **Âncora rollback:** `conecta-pro-frontend:pre-rebuild-frontend-20260610` = **`a5ea43a1`** (imagem atual preservada).
- Source do front == HEAD (git status limpo): `50bd7a6d` (trailing-slash propostas) + `9dfc96dd` (client_email page.tsx) commitados e em disco.
- `node_modules` presente (1.4G), `next` disponível; 315G de disco; `.dockerignore` exclui node_modules/.next.
- BUILD_ID em produção (antes): **`conecta-pro-1781088055946`** (vinha via docker cp).

## STEP 2 — Build no HOST (monitorado)
- `NEXT_PUBLIC_API_URL=https://erp.conectamais.pro NODE_TELEMETRY_DISABLED=1 NODE_OPTIONS=--max-old-space-size=8192 npx next build` → **exit 0**.
- Durante o build: RAM livre ~3G / disp ~11G; **produção intacta** (backend/frontend/postgres/celery-beat seguiram healthy). Heap capado em 8G → sem OOM no kernel.
- **Novo BUILD_ID:** `conecta-pro-1781126872911`. Output standalone: `server.js` (8067B) + `.next/static` + `public`.

## STEP 3 — Bake por cópia (imagem leve)
- Contexto staged em `/tmp/frontend-bake` (copy-only): `public` (21M) + `standalone` (147M) + `static` (14M).
- `Dockerfile` de bake (NÃO altera o `frontend/Dockerfile` original) — espelha o **runner stage**: `FROM node:20-alpine`, user `nextjs:nodejs`, `COPY public/standalone/static`, `ENV PORT=3000 HOSTNAME=0.0.0.0`, `CMD ["node","server.js"]`. **Sem npm ci / next build** dentro.
- `docker build` → **exit 0** em **14.8s**. **IMAGE ID novo:** `ee8cb1ac`.

## STEP 4 — Validação efêmera (`--network none`, descartável) — ANTES do swap
- Arquivos baked: `BUILD_ID=conecta-pro-1781126872911`, `server.js` 8067B, static (2 dirs), public (8 itens). ✅
- **Boot test:** container isolado → log **`✓ Ready in 199ms`** (server.js sobe sem crash). Container de teste removido. ✅

## STEP 5 — Swap por tag
| Tag | Image ID | Papel |
|-----|----------|-------|
| `conecta-pro-frontend:latest` | **ee8cb1ac** | imagem NOVA (produção) |
| `pre-rebuild-frontend-20260610` | **a5ea43a1** | rollback |
| `rebuild-frontend-20260610` | ee8cb1ac | tag de build |

## STEP 6 — Recreate frontend + validação
- `docker compose -f docker-compose.yml up -d --no-deps --no-build --force-recreate frontend` → recriado (`--force-recreate` porque o tag `:latest` não muda de nome).
- `docker inspect` frontend `.Image` = **ee8cb1ac** ✅; **healthy** (13s).
- **BUILD_ID rodando = `conecta-pro-1781126872911`** (novo, vindo da **imagem** — não mais docker cp). ✅
- `GET http://localhost:3001/` → **200**.
- `GET /modulos/crm/propostas` → **307 → `/login?redirect=%2Fmodulos%2Fcrm%2Fpropostas`** (middleware de auth — comportamento **correto** p/ request sem sessão).
- **`https://localhost/` → 200** (nginx → frontend OK).
- **Backend/DB intactos:** `/health` 200, **3 propostas** preservadas (rebuild do front não toca o backend nem o banco).
- Docker saudável (`images` exit 0); leak `docker logs` controlado (2 transitórios do cron, fix host-only).

## STEP 7 — Pós
- Staging `/tmp/frontend-bake` removido. Imagem `rebuild-frontend-20260610` e âncora `pre-rebuild-frontend-20260610` preservadas.
- ⚠️ A âncora antiga `pre-emailopt-20260610` / `pre-proposalslug-20260610` (= a5ea43a1) seguem como rollbacks históricos.

---

## O que ficou baked agora (fim do docker cp no frontend)
- `50bd7a6d` (remoção da barra final nas chamadas de proposals — corrige 404) + `9dfc96dd` front (client_email opcional no form de propostas). **BUILD_ID `1781126872911` vem da imagem** — qualquer recreate futuro do front **não reverte mais**.

## Rollback (1 sequência)
```
docker tag conecta-pro-frontend:pre-rebuild-frontend-20260610 conecta-pro-frontend:latest
docker compose -f docker-compose.yml up -d --no-deps --no-build --force-recreate frontend
```

## Gates respeitados
- :latest só sobrescrito **após** validação efêmera 100%; produção intocada durante o build (host).
- `frontend/Dockerfile` original **NÃO alterado** (criei um Dockerfile de bake à parte em /tmp).
- Build no host com heap capado → **sem OOM em produção**; postgres/redis/backend não tocados (`--no-deps`).
- dockerd não reiniciado; só o container frontend recriado.

## Nota: **10/10**
Build no host provado (8192, produção monitorada e intacta) + bake por cópia (imagem leve, sem OOM) + validação efêmera (Ready 199ms) + swap com âncora de rollback + recreate healthy com BUILD_ID novo do image + `/`200 / propostas→login(auth) / https 200 + backend/DB intactos. Estratégia de menor risco escolhida e executada honestamente.

*Frontend baked via host-build + copy-Dockerfile. Backend/banco não tocados. Rollback a 1 sequência. Imagem é SEPARADA do backend (este rebuild não afeta a `conecta-pro-backend`).*
