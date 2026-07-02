# Fix front — barra final nas chamadas de Propostas (404 → 200) ✅

- **Data:** 2026-06-10
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Status:** ✅ **Corrigido e deployado.** A tela de Propostas chamava `/api/v1/crm/proposals/` (com barra → 404); alinhada às telas-irmãs (sem barra → 200).
- **Arquivo:** `frontend/src/types/generated/crm/crm-propostas/crm-propostas.ts` (gerado por orval) · **Backup:** `crm-propostas.ts.bak-proposalslug-20260610-081643` + `.next.bak-proposalslug-*`
- **Commit:** **`50bd7a6d`** — `fix(crm-front): remove barra final das chamadas de proposals (alinha as telas-irmas, corrige 404)`
- **Backend NÃO tocado** (endurecimento é passo separado).

---

## 1. Diagnóstico (confirmado no código)
- **Propostas (BUG):** 3 chamadas "raiz" com barra final → `/api/v1/crm/proposals/`:
  1. **Listagem (GET)** `listProposalsApiV1CrmProposalsGet` (linha 144)
  2. **Create (POST)** `createProposalApiV1CrmProposalsPost` (linha 57)
  3. **QueryKey** (cache da listagem) (linha 154)
- **Telas-irmãs (corretas):** `/api/v1/crm/opportunities` e `/api/v1/crm/leads` — **sem** barra.
- As demais de proposals (`/from-opportunity`, `/stats`, `/${id}`, **`/${id}/send`**, `/submit`, etc.) têm segmento depois → **já corretas** (o `send` NÃO estava bugado; só listagem+create+querykey).

## 2. Fix (diff — 3 linhas)
```diff
-    url: `/api/v1/crm/proposals/`,   (POST create)
+    url: `/api/v1/crm/proposals`,
-    url: `/api/v1/crm/proposals/`,   (GET list)
+    url: `/api/v1/crm/proposals`,
-  return [`/api/v1/crm/proposals/`, ...(params...)]   (querykey)
+  return [`/api/v1/crm/proposals`, ...(params...)]
```
Segmentos (`/stats`, `/${id}/send`, etc.) **intactos** (replace cirúrgico, não global).

## 3. Build + deploy (padrão do front)
- **Onde o front roda em produção:** container Docker **`conecta-pro-frontend`** (`node server.js`, porta interna 3000 → host **3001**). nginx `erp`/`app` → upstream `frontend` = **127.0.0.1:3001** = esse container. (O processo **PM2 na :3000 NÃO é usado pelo nginx** — é secundário.)
- **Build:** `NODE_OPTIONS=--max-old-space-size=4096 npx next build` no host (serializado) — sucesso, novo `BUILD_ID conecta-pro-1781079677469`.
- **Deploy:** `docker cp` do artefato pro container (padrão do Dockerfile: `.next/standalone` → `/app`, `.next/static` → `/app/.next/static`). O `cp` faz **merge** → limpei o `static` antigo como root (`-u root rm -rf` + cp + chown) para não deixar chunks bugados. Restart do container.

## 4. Validação
| Check | Resultado |
|-------|-----------|
| Bundle: `crm/proposals/"` (bare COM barra) no container | **0** ✅ (bug removido) |
| Bundle: `crm/proposals"` (bare SEM barra) no container | **3** ✅ (list+create+querykey) |
| BUILD_ID host == container | `conecta-pro-1781079677469` ✅ |
| `GET /api/v1/crm/proposals` (sem barra, corrigida) | **200** ✅ |
| `GET /api/v1/crm/proposals/` (com barra, antiga) | **404** (prova que a barra era o bug) |
| Front container (3001) | **200**, status running/**healthy** |
| Front via nginx (`erp.conectamais.pro/`) | **200** |

➡️ A tela de Propostas agora chama o endpoint que responde **200** → carrega. (Lançamento fim-a-fim: listagem ✅, create ✅, send já estava ok.)

## 5. host==container
- BUILD_ID idêntico host↔container + chunk corrigido (0 bare-com-barra no container). Artefato deployado = build do host.

## 6. ⚠️ Durabilidade do front (importante)
- **Deploy via `docker cp` (NÃO baked):** o fix está no container vivo, **não na imagem** `conecta-pro-frontend`. Um `docker compose up`/recreate do front **reverteria** para a imagem antiga (com o bug).
  - **Para bakar:** rebuild da imagem do frontend (`docker build ./frontend` → tag swap → recreate) — o Dockerfile já faz `next build` + copia standalone/static. (Passo separado, como o rebuild do backend.)
  - Tag de rollback criada: `conecta-pro-frontend:pre-proposalslug-20260610`.
- **Fonte gerado (orval):** o arquivo é **gerado**. Uma regeneração do orval reverteria a edição. O fix DURÁVEL de origem seria: (a) ajustar o gerador/OpenAPI, ou (b) endurecer o backend (`redirect_slashes`/aceitar com e sem barra) — **passo separado** combinado.

---

## Resumo
- 3 chamadas de Propostas (listagem GET + create POST + querykey) tinham barra final (404) → corrigidas p/ sem barra (alinhadas a leads/oportunidades). `send` não estava bugado. ✅
- Build host + docker cp no container (3001, o que o nginx serve); chunk corrigido (0 bugado), BUILD_ID host==container. ✅
- Endpoints: sem-barra **200**, com-barra **404**; front **200**. Commit `50bd7a6d`. ✅
- **Durabilidade:** deploy não-baked → recreate reverte; bakar = rebuild imagem front. Backend não tocado (próximo passo).

*PAREI. Não toquei o backend. Não lancei propostas (você valida via CIC).*
