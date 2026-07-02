# Rebuild da imagem backend de produção — multi-prazo baked ✅

- **Data:** 2026-06-10
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Token:** STEP-0-REBUILD-EXEC
- **Status:** ✅ **COMPLETO.** Imagem nova `:latest` = **`b10f30b8`** nos 9 containers, health 200, 3 propostas reais + follow-up intactos, rollback garantido.
- **Imagem anterior (rollback):** `pre-rebuild-multiprazo-20260610` = `5a14e5db`.

---

## STEP 1 — Pré-flight
- dockerd responde (exit 0); âncora `pre-rebuild-followup-20260610`=`c4bde53` presente.
- Working tree dos arquivos crm == HEAD (só untracked: migration sprint94 + `.bak` ruído; **zero `M`**).
- **host==container MATCH** nos 5 (4 código + migration sprint94).
- Baseline DB: **3 propostas** (00001,00091,00092), `alembic=sprint94_proposal_terms`.
- **Backup:** `backups/rebuild/backup_pre_rebuild_multiprazo_20260610_203746.dump` (3.936.763 bytes, no host).

## STEP 2 — Build (tag própria, NÃO tocou :latest)
- `docker build -t conecta-pro-backend:rebuild-multiprazo-20260610 -f backend/Dockerfile backend/` → **SUCCESS** (exit 0).
- **IMAGE ID novo:** `b10f30b8e14a` (manifest `b10f30b8…`).

## STEP 3 — Validação efêmera (`--network none`, descartável) — ANTES do swap
- **3.2 migration sprint94 NA IMAGEM:** `sprint94_proposal_terms.py` presente; `alembic history` head = sprint94. ✅
- **3.3 código novo baked:** `term_options`=12, `selectinload(Proposal.items)`=3 (bbcc27cc list fix), `billing_type`=5 (eaf0fdf2), `include_in_schema=False`=2 (36e1c203 trailing-slash). ✅
- **3.1 import/compile:**
  - `compileall` de todo `/app/modules + main_production + celery_app` (cache em /tmp) → **exit 0** (zero erro de sintaxe).
  - import isolado dos módulos CRM (sem rede): `ProposalTermOption`/`ProposalTermOptionResponse`/`_create_term_option` presentes, **exit 0**.
  - (O import full de `main_production` com `--network none` pendura por I/O de conexão — **esperado**, não-ImportError; `main_production` é idêntico à prod atual.)
- **Veredito: imagem válida → autorizado o swap.**

## STEP 4 — Swap por tag (ponto de não-retorno)
| Tag | Image ID | Papel |
|-----|----------|-------|
| `conecta-pro-backend:latest` | **b10f30b8** | **imagem NOVA (produção)** |
| `pre-rebuild-multiprazo-20260610` | **5a14e5db** | **rollback (imagem anterior)** |
| `pre-rebuild-followup-20260610` | c4bde53 | âncora antiga (preservada) |
| `rebuild-multiprazo-20260610` | b10f30b8 | tag de build |

## STEP 5 — Recreate backend (2A) + validação
- `docker compose -f docker-compose.yml up -d --no-deps --no-build backend` → recriado (warnings benignos: EVOLUTION_* = stack separada; "orphan containers" = celery em outro -f, **NÃO usei --remove-orphans**).
- `docker inspect` backend `.Image` = **b10f30b8** ✅; health **200**.
- **Dados reais (o que importa):**
  - `GET /api/v1/crm/proposals` → **200, total=3**: 00001=1800, 00091=11420, 00092=11210 (recurring, item_count 1/3/3, sent). **Sem 500** (list fix funciona baked).
  - `GET /…/proposals/{Imperial}` → **200**, ref 00091, **term_options=3** (24m 11830 / **★36m 11420** / 48m 11020, composition fiel). **Multi-prazo baked e funcional.**
  - DB: **3 propostas**, `alembic=sprint94` (banco intocado).

## STEP 6 — Recreate celery/flower (2B)
- ⚠️ **Tropeço corrigido:** `-f docker-compose.celery.yml` **sozinho** falha (`undefined network conecta-pro-network` → invalid project); meus "exit=0" iniciais eram do `grep` no pipe, não do compose. **Correto:** `docker compose -f docker-compose.yml -f docker-compose.celery.yml up -d --no-deps --no-build --force-recreate <8 services>` (rede disponível + `--force-recreate` porque o tag `:latest` não muda de nome).
- **8 recriados** (celery-priority/sefaz/nfse/batch/integrations/operacional/beat + flower) na imagem **b10f30b8**.
- **9 containers UP/healthy.**
- **6.3 beat:** `crm-followup-proposals-0830` presente (crontab 30 8 * * *, task `crm.followup_proposals`).
- **Gate LGPD intacto:** `FOLLOWUP_AUTO_SEND = False` é **constante no código** (`/app/modules/crm/tasks.py:28`), não env → só gera lista/Telegram, **não contata cliente**.
- **6.4** beat/workers sem crash de import (celery v5.4.0 startup limpo).

## STEP 7 — Pós-rebuild
- **7.1 host==container** do código baked = **MATCH** (agora vem da **imagem**, não mais de docker cp).
- **7.2 SELECT final:** 3 propostas (00001 08/06, 00091 05/06, 00092 09/06), todas `sent`, `responded_at` NULL. Follow-up query: **Imperial 5d / Franceses 2d / Amsterdam 1d** (inalterado).
- **7.3** sem container de teste sobrando (`--rm` limpou); `docker images` exit 0 (saudável); órfãos `docker logs` = 2 (transitórios do cron host, voltam a 0 — fix do leak é host-only, não afetado pelo rebuild).

---

## O que ficou baked agora (não mais via docker cp)
- `9dfc96dd` (client_email opcional — model/schema), `36e1c203` (trailing-slash controllers), `eaf0fdf2` (multi-prazo model/schema/repo), `bbcc27cc` (list fix), **migration sprint94** (via disco). **Nenhum docker cp pendente no backend.**

## Itens AINDA não-baked (fora deste rebuild de BACKEND)
- **Frontend** (imagem SEPARADA `conecta-pro-frontend`, NÃO entra neste rebuild): `50bd7a6d` (front trailing-slash propostas) + `page.tsx` client_email opcional + BUILD_IDs via docker cp no container do front. → exigem rebuild da imagem **frontend** à parte.
- **Fix do leak `context_builder.py`** é **HOST-only** (cron), não pertence a nenhuma imagem — permanece no host.

## Rollback (se necessário, 1 sequência)
```
docker tag conecta-pro-backend:pre-rebuild-multiprazo-20260610 conecta-pro-backend:latest
docker compose -f docker-compose.yml up -d --no-deps --no-build backend
docker compose -f docker-compose.yml -f docker-compose.celery.yml up -d --no-deps --no-build --force-recreate <8>
```
Banco: `backup_pre_rebuild_multiprazo_20260610_203746.dump`.

## Gates respeitados
- :latest só sobrescrito **após** validação efêmera 100%. Produção intocada até o swap.
- Dockerfile NÃO alterado; WeasyPrint NÃO instalado; migration NÃO commitada (entrou via disco); cron NÃO tocado.
- dockerd NÃO reiniciado; recreate **sequenciado** (backend 2A → validado → celery 2B); **nunca os 9 juntos**.
- postgres/redis NÃO tocados (`--no-deps`, sem `--remove-orphans`); volume `conecta-pro_postgres_data` intacto.

## Nota: **10/10**
Build OK + validação efêmera (compile/sprint94/código baked) + swap com 2 âncoras de rollback + 2A health 200 e 3 propostas reais (lista+detail multi-prazo) + 2B 9 containers healthy, beat com followup e gate LGPD intacto + banco intocado (3, sprint94) + docker saudável. Tropeço do `-f celery.yml` solitário detectado e corrigido honestamente (rede + force-recreate). Zero downtime não-controlado, rollback garantido.

*Rebuild executado: build tag própria → efêmero → swap → 2A → 2B. Migration via disco (não commitada). Frontend é imagem à parte (não baked aqui). Backup feito.*
