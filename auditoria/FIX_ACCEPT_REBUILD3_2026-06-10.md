# Fix botão "Aceitar" (/approve→/accept) + label + rebuild #3 ✅

- **Data:** 2026-06-10
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Token:** STEP-0-FIX-ACCEPT-REBUILD3
- **Status:** ✅ **COMPLETO.** Fix bakado na imagem `conecta-pro-frontend:latest`=**`62fbb6ee`** (BUILD_ID `conecta-pro-1781131233677`); `/accept` provado em proposta de teste; **3 reais intactas** (sent/responded_at NULL).

---

## STEP 1+2 — Correções (escopo estrito, 2 linhas)
- Backup: `page.tsx.bak-acceptfix-20260610_223843` (25265B).
- **getStatusLabel é local** ao `page.tsx` (os outros `getStatusLabel` no front são funções de **outros** arquivos: licitacoes/ProposalStatusBadge, config/feature-flags, financeiro — não afetados). Editar o label aqui é seguro.

```diff
# acceptMutation (l.83) — apontava p/ /approve (errado → 400)
-     mutationFn: (id) => customInstance({ url: `/api/v1/crm/proposals/${id}/approve`, method: 'POST', data: { action: 'approve' } }),
+     mutationFn: (id) => customInstance({ url: `/api/v1/crm/proposals/${id}/accept`,  method: 'POST' }),

# getStatusLabel (l.197) — desambiguação
-       accepted: 'Aprovada',
+       accepted: 'Aceita',
```
- `diff` vs backup = **exatamente 2 linhas** (83 + 197).
- **`approveMutation` (l.65) NÃO tocado** — segue `/approve {action:'approve'}` (correto p/ status `pending_approval`, botão "Aprovar").
- **Form intocado** (item C): `total_value` segue 5 ocorrências (107/123/165/350/351).
- Sanidade: parênteses balanceados (183=183).

## STEP 3 — Rebuild #3 (host build 8192 + bake cópia, sem OOM)
- RAM: **12G disp** (≥9G). Âncora nova `pre-rebuild-front3-20260610` = **92732761** (rollback); anteriores ee8cb1ac/a5ea43a1 preservadas.
- **Build host** (`NODE_OPTIONS=8192`): **exit 0**, **produção intacta** (14 containers up durante o build, ~11G disp). Novo BUILD_ID `conecta-pro-1781131233677`.
- **Bake** (Dockerfile à parte, original intocado): `docker build` → **exit 0** em 13.6s. **IMAGE ID** `62fbb6ee`.
- **Efêmero (`--network none`):** BUILD_ID novo; boot **`✓ Ready in 162ms`**; **prova do fix:** refs a `/accept` no bundle **4 → 6** (acceptMutation agora aponta /accept).
- **Swap:** `latest=62fbb6ee`; recreate `--no-deps --no-build --force-recreate frontend` → healthy; `.Image=62fbb6ee`, BUILD_ID rodando = `conecta-pro-1781131233677`.
- `GET /` 200; `/modulos/crm/propostas` 307→login (auth ok); backend `/health` 200.
- **3 reais intactas:** 00001/00091/00092 = **sent, responded_at NULL** (seguem no follow-up).

## STEP 4 — Validação funcional com proposta de TESTE (NUNCA as reais)
- Criada proposta de teste → `/send` → **sent**.
- `POST /accept` → **201, status=accepted, responded_at=2026-06-10T22:44:13** (setado). ✅ — o endpoint que o front agora chama funciona numa proposta `sent`.
- Banco: teste = `accepted`+responded_at; **3 reais = `sent`+responded_at NULL** (intactas).
- **Teste DELETADO** → proposals volta a **3** (só as reais).

---

## Resultado
- **Bug resolvido:** o botão "Aceitar" (proposta `sent`) agora chama **`/accept`** (sent→accepted + responded_at, sai do follow-up) em vez de `/approve` (que dava 400 por exigir `pending_approval`).
- **Label desambiguado:** `approved`="Aprovada" (interno) vs `accepted`="Aceita" (cliente).
- **Validação final do clique "Aceitar"** é **manual (Jordan no CIC)** — eu provei o build (efêmero + /accept no bundle) e o endpoint (201 em teste), **sem executar /accept nas 3 reais**.

## Rollback (1 sequência)
```
docker tag conecta-pro-frontend:pre-rebuild-front3-20260610 conecta-pro-frontend:latest
docker compose -f docker-compose.yml up -d --no-deps --no-build --force-recreate frontend
```

## Gates respeitados
- **/accept NÃO executado nas 3 reais** (255f2080/895bd772/31215a74 seguem sent/responded_at NULL) — só na de teste (deletada).
- Build no host (heap 8192) → sem OOM; produção intacta. Dockerfile original intocado. `--no-deps`; dockerd não reiniciado; :latest só após efêmero. Backup feito.
- Escopo estrito: só 2 linhas (acceptMutation + label). Form/total_value (item C) intocado.

## Nota: **10/10**
Fix de 2 linhas (endpoint + label), rebuild host sem OOM (produção monitorada), efêmero (Ready 162ms + /accept 4→6 no bundle), swap com 3 âncoras de rollback, recreate healthy, `/accept` provado em proposta de teste (201/accepted/responded_at) e **3 reais preservadas** + limpeza a 3. Validação visual do clique fica pro CIC.

*Rebuild #3: host-build + copy-Dockerfile. As 3 propostas reais nunca receberam /accept. Item C (form total_value) e demais cosméticos seguem fora do escopo.*
