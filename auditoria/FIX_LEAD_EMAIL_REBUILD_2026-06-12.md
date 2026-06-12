# FIX LEAD EMAIL — LeadResponse.email opcional + rebuild backend ✅

- **Token:** STEP-0-FIX-LEAD-EMAIL
- **Data:** 2026-06-12
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Bug:** `GET /api/v1/crm/leads` → **500** quando lead tem `email=NULL` (leads de WhatsApp nascem sem e-mail). `pydantic ValidationError: email Input should be a valid string, input_value=None` em `lead_controller.py:97 list_leads`.
- **Precedente:** sprint93 — `ProposalResponse.client_email str → str|None` (commit `9dfc96dd`).
- **Status:** ✅ Fix bakado na imagem, swap 2A/2B completo, 9/9 healthy.

---

## 1. Diagnóstico
- `LeadResponse.email: str` (non-Optional) em `backend/modules/crm/schemas/lead.py:70`.
- **Banco (`\d leads`):** coluna `email` JÁ É nullable (drift vs model Python `nullable=False` — sem migration necessária, bug só no schema de RESPONSE, como previsto).
- **Dados:** 18 leads, **7 com `email IS NULL`** (todos `source=whatsapp`). `name`/`phone`: 0 NULLs.
- **Varredura família:** todos os demais campos nullable do DDL (`phone, company, position, company_size, industry, notes, assigned_to_id, last_contact_at, next_contact_at`) já eram `| None` no `LeadResponse`. **Único divergente: `email`.**

## 2. Diff (commit `f7cfcc6b`)
```diff
--- a/backend/modules/crm/schemas/lead.py
+++ b/backend/modules/crm/schemas/lead.py
@@ -67,7 +67,7 @@ class LeadResponse(BaseModel):
     id: str
     name: str
-    email: str
+    email: str | None = None
     phone: str | None
```
- `str | None` (não `EmailStr | None`) no response: serializa do banco — `EmailStr` poderia dar 500 com valores legados fora de formato (mesma decisão do sprint93). `LeadCreate` segue exigindo `EmailStr`.
- Backup: `lead.py.bak-leadfix-2026-06-12`. `py_compile` OK.

## 3. Validação ANTES do rebuild (hot copy)
| Momento | `GET /api/v1/crm/leads` (com JWT) |
|---|---|
| **ANTES** | **HTTP 500** — `ValidationError ... LeadResponse email` (log do backend) |
| **DEPOIS** (docker cp + restart) | **HTTP 200** — 18 leads, **7 WhatsApp com `email: null` listados** (Junior Feitoza, Jordan Jesus, Gerente Operacional, Ruan, Rafa-el 🦇...) |

## 4. Rebuild (procedimento provado — 4º consecutivo)
| Etapa | Resultado |
|---|---|
| Âncora rollback | ✅ `conecta-pro-backend:pre-rebuild-leadfix-20260612` = `b7ca396d` (= `:latest` no momento; o `0c36d8c6` citado na missão já tinha sido superado por rebuilds de hoje) |
| Dump banco | ✅ `backups/rebuild/pre_rebuild_leadfix_20260612_185543.dump` (3.8M, TS fixo) |
| Build | ✅ `conecta-pro-backend:rebuild-leadfix-20260612` = `6706bb4f` — exit 0, 36.6s, `:latest` intocado até o efêmero |
| Efêmero `--network none` | ✅ fix presente (linha 70) + `LeadResponse.email` não-required (default=None) + `modules.crm.schemas` importa limpo |
| Swap 2A (backend) | ✅ `:latest` → `6706bb4f`, recreate `--no-deps --no-build --force-recreate`, healthy, `/health` 200 em ~10s |
| Swap 2B (celery/flower) | ✅ 8 containers recriados (beat, operacional, nfse, sefaz, batch, priority, integrations, flower) |

## 5. Gates pós-swap
| Gate | Resultado |
|---|---|
| `/health` | ✅ 200 |
| `GET /leads` | ✅ 200 — 18 leads, 7 com email null |
| Proposals | ⚠️ API lista **3** (não 4): a 4ª (`30498bf3`, draft) está `is_active=false` desde **2026-06-11 02:21** — ANTERIOR a este rebuild. DB tem 4 linhas; API lista as 3 ativas. **Não é regressão** (fix tocou só `LeadResponse.email`). |
| `AGENT_ENABLED` | ✅ `true` |
| Rede `chatwoot-fazerai-net` | ✅ presente, backend + baileys-api conectados (**4º rebuild consecutivo durável**) |
| Containers | ✅ **9/9 healthy** (backend + 7 celery + flower) |

## 6. Rollback (disponível)
```bash
docker tag conecta-pro-backend:pre-rebuild-leadfix-20260612 conecta-pro-backend:latest
docker compose up -d --no-deps --no-build --force-recreate backend
docker compose -f docker-compose.yml -f docker-compose.celery.yml up -d --no-deps --no-build --force-recreate \
  celery-beat celery-operacional celery-nfse celery-sefaz celery-batch celery-priority celery-integrations flower
```
- Banco: `pg_restore` do dump `pre_rebuild_leadfix_20260612_185543.dump` (não necessário — zero mudança de schema/dados).

## Resumo
Fix de 1 linha espelhando sprint93, validado em 3 camadas (py_compile → hot copy curl 500→200 → efêmero na imagem), bakado via procedimento provado com âncora + dump, swap 2A/2B sem incidente, 9/9 healthy, rede e env duráveis. Único desvio do gate (proposals 3 vs 4) investigado e explicado: soft-delete pré-existente de ontem.

## Nota: 10/10
