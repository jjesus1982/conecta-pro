# Fix SQL Injection — `contact_controller.py` (bind params)

- **Data:** 2026-06-09
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Escopo:** Cirúrgico — corrigir **exatamente 2** SQL injections (filtro `client_id` por interpolação de string). Nada além disso.
- **Arquivo:** `backend/modules/crm/controllers/contact_controller.py`
- **Commit:** `417d1a75` — `fix(crm): corrige SQL injection em contact_controller (bind params)`
- **Veredito:** ✅ Injeção eliminada nos 2 pontos. Valor do usuário agora vai **bindado** (`$1`), nunca entra na string SQL.

---

## 1. Diff das 2 linhas (antes → depois)

**Ponto 1 — `listar_contatos` (`GET /api/v1/crm/contacts/`):**
```diff
-        where = f"WHERE cc.client_id = '{client_id}'"
+        where = "WHERE cc.client_id = :client_id"
+        params = {"client_id": client_id}
```

**Ponto 2 — `listar_atividades` (`GET /api/v1/crm/activities/`):**
```diff
-        where = f"WHERE a.client_id = '{client_id}'"
+        where = "WHERE a.client_id = :client_id"
+        params["client_id"] = client_id
```

Mesmo padrão dos outros 13 queries já seguros do arquivo (`text(...)` + dict de params).
O `{where}` segue no f-string, mas agora contém **só literais fixos** — zero valor de usuário.
`git diff --stat`: **1 file, 9 insertions(+), 4 deletions(-)**.

## 2. Resultado dos 4 testes (em produção, pós-deploy)

| Teste | Endpoint | Resultado | Status |
|-------|----------|-----------|--------|
| **a** | contacts `?client_id=<uuid real>` | **200** (total=0, tabela vazia) | ✅ |
| **b** | contacts **sem** `client_id` (no-filter) | **200** (total=0) | ✅ não quebrou |
| **c** | contacts `?client_id=' OR '1'='1` | **500** (cast UUID) — **não retornou tudo, não injetou** | ✅ |
| **d** | activities (real / sem filtro / ataque) | **200 / 200 / 500** | ✅ |

> `client_id real` usado: `9bac5ff5-...` (1º cliente). `crm_contacts`/`crm_activities` estão **vazias** → total=0 é o esperado.

## 3. Prova de que o 500 é rejeição de tipo, NÃO injeção

Log do backend para o vetor de ataque:
```
WHERE a.client_id = $1
[parameters: ("' OR '1'='1", 20)]
asyncpg DataError: invalid input for query argument $1: "' OR '1'='1"
  (invalid UUID "' OR '1'='1": length must be between 32..36 characters, got 11)
```
- A query usa **placeholder `$1`** — o payload **não** virou estrutura SQL.
- A string maliciosa chegou ao banco como **valor de parâmetro** e foi rejeitada no **bind de tipo** (coluna é UUID).
- **Impossível "quebrar" a query** (sem `OR '1'='1'` ativo). Antes do fix, isso seria interpolado direto no WHERE.
- O 500 é um erro de **tipo gracioso** (UUID inválido), não vazamento de dados. Comportamento aceitável e seguro; opcionalmente poderia virar 422 no futuro (fora do escopo desta tarefa cirúrgica).

## 4. Deploy e integridade

- `docker cp` do arquivo corrigido → **9 containers** da imagem do backend + `docker restart conecta-pro-backend` (healthy).
- **host == container:** `md5 = 7155781bd9e86e93415a90d77cc3a075` (idêntico, antes e depois do commit).
- `py_compile`: OK. Pre-commit: passou sem reformatar.

## 5. ⚠️ Durabilidade (igual às outras correções desta stack)

Esta correção está **viva via `docker cp`** e **commitada no git**, mas a **imagem Docker ainda não foi reconstruída**. Um `docker compose up`/recreate que recrie o container a partir da imagem atual **reverteria** o `contact_controller.py` para a versão vulnerável.
➜ **Permanente só após o PRÓXIMO rebuild da imagem do backend.** Conforme combinado, **NÃO reconstruí agora** (tarefa à parte). Até lá, não recriar esse container do zero.

---

## Resumo
- 2 SQLi corrigidas com bind params, mesmo padrão da casa. ✅
- 4 testes: a/b/d-real/d-sem = 200; ataque (c/d) = 500 por cast de UUID, **sem injeção** (provado no log: `$1` parametrizado). ✅
- host==container, commit `417d1a75`. ✅
- Pendente para durabilidade: rebuild da imagem (não feito — fora do escopo). ⏸️

*Tarefa encerrada aqui (PARAR). Não avancei para F-CRM nem para o agente.*
