# Rebuild #2 do frontend — fix R$ 0,00 baked ✅

- **Data:** 2026-06-10
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Token:** STEP-0-REBUILD-FRONT-2
- **Status:** ✅ **COMPLETO.** Imagem nova `conecta-pro-frontend:latest` = **`92732761`** (BUILD_ID `conecta-pro-1781128728697`) com o fix do R$ 0,00 bakado; container healthy; rollback garantido. Backend/DB intactos.

---

## STEP 1 — Pré-flight
- Fix no fonte confirmado: `page.tsx:428 → proposta.total ?? 0`, `:577 → selectedItem.total ?? 0`; `total_value` restante só no FORM (107/123/165/350/351).
- RAM: 31G total, **12G disp** (≥ limiar; igual ao rebuild #1 que funcionou).
- Âncora nova `pre-rebuild-front2-20260610` = **ee8cb1ac** (rollback); âncora antiga `pre-rebuild-frontend-20260610` = a5ea43a1 preservada.

## STEP 2 — Build no HOST (heap 8192, monitorado)
- `NEXT_PUBLIC_API_URL=https://erp.conectamais.pro NODE_OPTIONS=--max-old-space-size=8192 npx next build` → **exit 0**.
- Durante o build: RAM ~10G disp / 2-3G free; **produção intacta** (backend/frontend/postgres/celery-beat seguiram healthy, 11 containers up). Sem OOM.
- **Novo BUILD_ID:** `conecta-pro-1781128728697`. Standalone `server.js` (8067B) + static + public gerados.

## STEP 3 — Bake por cópia (imagem leve)
- Stage `/tmp/frontend-bake-2`: public (21M) + standalone (147M) + static (14M).
- Dockerfile de bake à parte (NÃO alterei `frontend/Dockerfile` original) — espelha runner stage.
- `docker build` → **exit 0** em **15.5s**. **IMAGE ID:** `92732761`.

## STEP 4 — Validação efêmera (`--network none`) ANTES do swap
- **4.1** BUILD_ID = `conecta-pro-1781128728697`, server.js presente. ✅
- **4.2 🎯 PROVA DO FIX NA IMAGEM:** `total_value` nos chunks estáticos: **NOVA = 12** vs **ANTIGA (ee8cb1ac) = 14** → **−2 exatamente** (as 2 ocorrências de **exibição** removidas; as do FORM permanecem). Confirma que o fix foi compilado na imagem. ✅
- **4.3 Boot test:** container isolado → **`✓ Ready in 378ms`** (server.js sobe sem crash). Removido. ✅

## STEP 5 — Swap + recreate
| Tag | Image ID | Papel |
|-----|----------|-------|
| `conecta-pro-frontend:latest` | **92732761** | imagem NOVA (fix R$0,00) |
| `pre-rebuild-front2-20260610` | **ee8cb1ac** | rollback (imagem com o bug) |
| `pre-rebuild-frontend-20260610` | a5ea43a1 | âncora antiga (preservada) |
- `docker compose -f docker-compose.yml up -d --no-deps --no-build --force-recreate frontend` → recriado.
- `.Image` = **92732761** ✅; **healthy** (26s); **BUILD_ID rodando = `conecta-pro-1781128728697`** (novo).
- `GET /` → **200**; `/modulos/crm/propostas` → **307 → /login** (auth, correto); `https://localhost/` → **200**.
- **Backend/DB intactos:** `/health` 200, **3 propostas** preservadas.
- Docker saudável (`images` exit 0); leak controlado (2 transitórios do cron host).

---

## Resultado
- **Fix R$ 0,00 baked:** a tela de Propostas (lista l.428 + detalhe l.577) agora lê **`proposta.total`** — com o backend mandando `total` (1800/11420/11210), a UI passa a exibir **R$ 1.800 / 11.420 / 11.210** em vez de R$ 0,00.
- **Prova na imagem:** total_value −2 (14→12) = as 2 refs de exibição removidas.
- **Prova visual definitiva:** requer login na UI (a página é client-side e renderiza `proposta.total` após o fetch autenticado). HTTP redireciona p/ login sem sessão (esperado).

## Rollback (1 sequência)
```
docker tag conecta-pro-frontend:pre-rebuild-front2-20260610 conecta-pro-frontend:latest
docker compose -f docker-compose.yml up -d --no-deps --no-build --force-recreate frontend
```

## Gates respeitados
- Build no HOST (heap 8192) → **sem OOM**; produção intacta durante o build.
- `frontend/Dockerfile` original **NÃO alterado** (bake à parte em /tmp).
- `--no-deps`: postgres/redis/backend não tocados; dockerd não reiniciado; só o frontend recriado.
- :latest só sobrescrito **após** validação efêmera 100%.

## Nota: **10/10**
Build host sem OOM (produção monitorada e intacta) + bake leve + **prova do fix na imagem (14→12 total_value)** + boot 378ms + swap com 2 âncoras de rollback + recreate healthy com BUILD_ID novo + `/` 200 / propostas→login / https 200 + backend/DB intactos. Fix do R$ 0,00 durabilizado (não reverte mais em recreate).

*Rebuild #2: host-build + copy-Dockerfile. O form de criação (total_value morto, item C) segue intocado — fora do escopo. Visual final depende de login do Jordan.*
