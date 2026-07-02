# CHECAGEM GERAL DE CÓDIGO — CONECTA PRO

**Data:** 2026-05-30
**Tipo:** RAIO-X READ-ONLY (diagnóstico — **nada foi corrigido/modificado no código**)
**Método:** orquestração de 4 subauditorias paralelas (imports/imagem, endpoints, bugs, duplicação) + `tsc --noEmit` completo + verificação manual do achado-manchete.
**Baseline comparativa:** `DIAGNOSTICO_FASE1_2026-05-29.md` (nota 6.0/10). O servidor foi mexido desde então (containers recriados via `docker compose up`).

> ⚠️ Único arquivo escrito: este relatório. Zonas protegidas (`financial/`, `government_integrations/`, `alembic/versions/`, `main_production.py`, `docker-compose*`, `.env*`, `credentials/`) foram **lidas para diagnóstico**, nunca propostas para alteração.

---

## 1. SUMÁRIO EXECUTIVO — NOTA DE SAÚDE: **4.5 / 10** ⬇️ (era 6.0)

A nota **caiu** porque o que a Fase 1 tratou como dívida latente agora se confirma como **quebra funcional real em produção**: módulos inteiros e toda a cadeia de **Departamento Pessoal (DP)** estão **offline no sistema em execução**, e ~27% dos endpoints amostrados retornam **500**.

**Ponto crucial — o código do HOST está majoritariamente OK; o que está quebrado é o DEPLOY:**
- O backend roda com **código assado na imagem Docker** (não montado). A imagem está **defasada**: **98 arquivos `.py` existem no host mas faltam na imagem**.
- Um único diretório ausente na imagem — `modules/operacional/ai/` (existe no host) — derruba, em cascata via `try/except` amplo, **10 módulos de negócio + 15 routers de DP**. O app sobe "healthy" porém com essas rotas **inexistentes** (falha silenciosa).

**O que melhorou desde a Fase 1:**
- ✅ Containers **healthy** (Fase 1: quase todos `unhealthy`). Celery rc=0, backend `/health` 200.
- ✅ `erp-grafana` religado (sessão anterior).
- ✅ **`tsc --noEmit` finalmente rodou** (havia RAM): **apenas 7 erros de tipo** em todo o frontend, com `strict: true`. A dívida de tipagem do frontend é **muito menor** que o temido.

**O que derruba a nota:**
- 🔴 **10 módulos com 0 rotas** no app vivo (operacional, campo, crm, bidding, services, equipment, document-kits, empresas, fiscal, government).
- 🔴 **Cadeia de DP inteira offline** (admissão→rescisão→férias→folha→ponto→eSocial): 15 routers não registrados.
- 🟠 **Schema drift**: ~25 de 91 GETs amostrados retornam **500** porque models referenciam colunas/tabelas/enums que o banco não tem (migrations não aplicadas).
- 🟠 Bugs da Fase 1 **persistem inalterados** (mock forecast, 208 enums sem `values_callable`, kit_mensal SQL raw).
- 🟠 Erros funcionais de Celery (tasks não registradas, Redis em `localhost`, enum inválido).

**Veredito honesto:** o **repositório (host)** vale ~6.5; o **sistema em execução** vale ~4.5 por causa do descompasso imagem↔código e do schema drift. A correção principal **não é reescrever código** — é **rebuild/redeploy da imagem** + **aplicar migrations**. Há risco real de que funcionalidades dadas como "aprovadas" em sessões anteriores (DP 25/25, eSocial, folha) estejam **no ar apenas no host, não no container de produção**.

### Limitações honestas desta auditoria
- Endpoints: amostra de **91 GETs (~11% dos 838 GETs)**. Há provavelmente mais 500 nas famílias afetadas não testados individualmente.
- Serialização real de `Decimal` (risco `.toFixed`) não verificada em runtime — risco depende de string vs float emitido.
- Não foi feito cross-check exaustivo `requirements.txt`/`package.json` × imports (dependências não usadas) — pendente.
- `condominio_id None→IS NULL` e `client_name` vs `customer_name`: continuam exigindo revisão manual (não quantificável automaticamente).

---

## 2. 🔴 BLOQUEADORES (impedem o sistema de funcionar AGORA)

### B1 — Imagem Docker defasada: `modules/operacional/ai/` ausente derruba 10 módulos + DP — **CONFIANÇA ALTA, confirmado AGORA**
- **Evidência direta (verificada manualmente):**
  - Host: `/opt/conecta-pro/backend/modules/operacional/ai/` → `__init__.py, controller.py, stubs.py` ✅ existe.
  - Imagem: `docker exec conecta-pro-backend ls /app/modules/operacional/ai/` → **`No such file or directory`** ❌.
  - `main_production.py:429` importa `operacional_ai_router`; `:475` faz `include_router(..., prefix="/operacional")`. O import está num **bloco único** — a falha de um nome derruba o bloco inteiro.
- **Impacto medido no app vivo (1671 rotas, 14 módulos):** os seguintes módulos têm **0 rotas**:
  `operacional, campo, crm, bidding, services, equipment, document-kits, empresas, fiscal, government`.
- **DP (Departamento Pessoal) — 15 routers NÃO registrados** (log de startup, verbatim): `employee, admission, termination, benefits, vacation, discipline, time_tracking, payroll, reimbursement, payroll_export, esocial, time_record, leave, document, reports` — todos com `No module named 'modules.operacional.ai'`.
  - ⚠️ Nuance honesta: `people-management` mantém **300 rotas vivas** (lado RH/recruitment/retention/portal). O que caiu é a **cadeia DP** que depende transitivamente de `operacional`. Não é "people_management inteiro offline" — é a parte de DP.
- **Causa raiz:** imagem construída de snapshot anterior. **98 `.py` do host faltam na imagem** (ex.: `modules/juridico/**` inteiro, `modules/integrations/inter/**`, `modules/gedeon/onvio/**`, ~26 controllers/services de `financial/`).
- **Correção (FORA do escopo read-only):** rebuild + redeploy da imagem do backend a partir do host atual. **Não tocar** em `financial/`/`government_integrations/` no processo — apenas reconstruir a imagem.

### B2 — `modules.ai.openclaw` referenciado mas inexistente (host E imagem) — **CONFIANÇA ALTA**
- No startup: `Modulo OpenClaw: No module named 'modules.ai.openclaw'`. Não é divergência de imagem; o código referencia um módulo que não existe em lugar nenhum. Bloco capturado por `try/except` → degradação silenciosa. Verificar quem importa `modules.ai.openclaw`.

### B3 — Schema drift: ~25/91 GETs amostrados retornam 500 (models ≠ banco) — **CONFIANÇA ALTA (tracebacks reais capturados via `docker logs`)**
Migrations aplicadas no banco estão **atrás** dos models. Famílias afetadas (traceback real):
| Endpoint | Causa raiz (traceback) |
|---|---|
| `/api/v1/audit/access` | `UndefinedColumnError: column access_history.extra_metadata does not exist` |
| `/api/v1/audit/compliance/overview` | `type "rulestatus" does not exist` (enum PG ausente) |
| `/api/v1/reports/kpis`, `/reports/templates` | `column ...tenant_id does not exist` |
| `/api/v1/config/tenants` | `LookupError: 'active' not among enum tenantstatus (ATIVO/INATIVO)` (case mismatch) |
| `/api/v1/monitoring/health`, `/monitoring/alerts` | `invalid input value for enum alertstatus: "ACTIVE"` |
| `/api/v1/integrations/integrations/sync` | `column sync_queue.extra_metadata does not exist` |
| `/api/v1/retention/profile/questionnaire` | `relation "profile_questions" does not exist` |
| `/api/v1/mobile/dashboard` | `TypeError: 'User' object is not subscriptable` (código trata ORM como dict) |
| `/api/v1/notifications/channels` | `AttributeError: 'AsyncSession' object has no attribute 'query'` (código sync em sessão async) |
| `/api/v1/users/`, `/users/pending` | `pydantic ValidationError for UserResponse` (schema ≠ dados) |
| `/api/v1/health-occupational/epi` | `ValidationError: ca_number/validade_dias... Field required` |
- **Padrões:** (1) schema drift (colunas/tabelas/enums faltando: `extra_metadata`, `tenant_id`, `profile_questions`, `rulestatus`); (2) enums case-mismatch (`ACTIVE/active` vs `ATIVO`); (3) código legado sync em sessão async (`.query`, `user['...']`).
- **Correção:** maior parte é **aplicar migrations pendentes** (toca `alembic/versions/` → zona protegida, exige validação CIC) + ajustes pontuais de código (mobile/notifications/users — fora de zona protegida).

### B4 — Celery: erros funcionais ativos (processos saudáveis, tarefas falhando) — **CONFIANÇA ALTA**
- `celery-nfse`: `Received unregistered task 'government_integrations.tasks.sync.sincronizar_nfse_entrada'` → `KeyError` (recorrente).
- `celery-sefaz`: `... sincronizar_nfe_entrada` não registrada (recorrente 11h/13h).
- `celery-batch`: `KeyError: 'gedeon.risk_monitor'` + dezenas de `Erro ao publicar evento: [Errno 111] Connect ... ('127.0.0.1', 6379)` — **worker tenta Redis em `localhost` em vez de `conecta-pro-redis`** (bug de config de conexão).
- `celery-operacional`: `sqlalchemy.exc.DataError: invalid input value for enum tenant_status: "ATIVO"`.
- Tasks não registradas batem com o **código de tasks faltando na imagem (B1)**. `celery-integrations`/`priority`/`beat`: limpos.

---

## 3. 🟠 BUGS CONFIRMADOS (revalidados vs Fase 1)

| Sev | Local (arquivo:linha) | Descrição | vs Fase 1 | Confiança |
|-----|----------------------|-----------|-----------|-----------|
| 🟠 ALTO | `modules/ai/inventory_forecast/controllers/forecast_controller.py:69,75,230` | Endpoints `POST /forecasts` e `/patterns/analyze` retornam **dados MOCK (`import random`)**, nunca tocam o DB. `product_info` hardcoded ("Produto de Teste"). | **IGUAL** | Alta |
| 🟠 ALTO | Modelos — **208** `Column(Enum)` sem `values_callable` (227 total / 19 com) | Risco de divergência grava/lê enum por *name* vs *value* Python↔Postgres. Ex.: `operacional/diaristas/models/documento_fiscal.py:107,108,216,248,249`. | **IGUAL** (227/19/208) | Alta |
| 🟠 ALTO | `modules/ged/controllers/kit_real_controller.py:990,1148` | `kit_mensal` ainda em **SQL raw** (`WHERE ... kit_mensal = true`, `SELECT kit_mensal ... FROM contracts`). Migração p/ `portaria_presencial` incompleta no GED. | **IGUAL** | Alta |
| 🟠 ALTO | `/api/v1/financial/suppliers/list` → 422 | `list` casa com `/{supplier_id}` (UUID parse falha). Classe "UUID shadowing". *(Zona protegida — só documentado.)* Correto: `/financial/suppliers?condominio_id=<uuid>` → 200. | **IGUAL** | Alta |
| 🟠 ALTO | UUID shadowing (mesma classe) | `/api/v1/ged/document-tags/most-used` → 500; `/api/v1/monitoring/alerts/statistics` → 422. Sub-rota literal capturada por rota `/{uuid}`. | **NOVO** | Alta |
| 🟡 MÉDIO | Backend — **1104** `B904` (raise sem `from e`) | 708 fora das zonas protegidas + 396 dentro. Perde cadeia de exceção → mascara debug de 500. Ex.: `modules/ai/conversation/controllers/chat_controller.py:98,147,369`. | Fase 1: 708 → **1104 total** (708 fora de zona) | Alta |
| 🟡 MÉDIO | Frontend — **164** `.toFixed(` (157 sem `Number()`) | `.toFixed()` sobre valor de API sem coerção → `TypeError` se Decimal vier string. Ex.: `operacional/escalas/page.tsx:201,389`, `gestao-pessoas/rh/desempenho/page.tsx:69`, `operacional/substituicoes/page.tsx:633,653`. | **IGUAL** (164) | Média |
| 🟡 MÉDIO | Código sync em sessão async | `notifications/channels` (`AsyncSession.query`), `mobile/dashboard` (`User` como dict). | **NOVO** | Alta |
| 🟢 BAIXO | Frontend — **7 erros de tipo** (`tsc --noEmit`, strict:true) | `dp/contratos/page.tsx:374`, `fiscal/certidoes/page.tsx:480` (prop `title` em ícone Lucide), `ged/configuracoes/page.tsx:263` (módulo `croniter` ausente), `ged/onvio-sync/types.ts:40` (`FgtsPorTipo` não exportado), `components/gedeon/KitDetalheModal.tsx:51,52,65`. | **NOVO — antes não mensurável (OOM)** | Alta |

**Runtime menores observados:** `Permission denied: '/app/data/models'` (diretório de modelos não criável no container); warning pydantic V2 (`schema_extra`→`json_schema_extra`).

---

## 4. 🟡 DUPLICAÇÃO / CÓDIGO MORTO (mapeado — NADA removido)

| Item | Veredito | Evidência | Confiança |
|------|----------|-----------|-----------|
| `modules/hr/` (172py) vs `modules/people_management/hr/` (60py) | **AMBOS EM USO** — `modules/hr` **NÃO é dead-code** | `people_management.hr` importa `modules.hr.*` em runtime (`time_tracking_controller.py:32`, `payroll_controller.py:29`, services). Corrige hipótese da Fase 1. | Alta |
| Submódulos `hr/{analytics_dashboard, mobile_time_clock, rep_integration}` | **Candidatos a auditoria** (só via `api/v1` inativo + testes) | Não alcançados por `main_production`; sem uso runtime comprovado. | Média |
| `main.py`, `main_debug.py`, `main_lite.py`, `main_minimal.py`, `main_simple.py.bak` | **ÓRFÃOS** | 0 referências em qualquer `docker-compose*`, `Dockerfile`, `.sh`, `.service`. Ativo: só `main_production.py` (`Dockerfile:78`). `main.py` é o único que carrega `api/v1` (inativo). | Alta |
| `modules/fase5/` (23py) | **ÓRFÃO** no runtime de produção | Não montado por `main_production`; só `api/v1/__init__.py` (inativo) + script. | Alta |
| `modules/search/` (2py) | **Possível carga transitiva** via `monitoring/__init__.py:41` (try) | Não montado direto; `monitoring` é montado → pode importar `search` no try. Não confirmado se router é incluído. | Média |
| Subdirs PT-BR scaffolding (`comercial/atividades`, `operacoes/escalas`, etc.) | **Dead-code estrutural** (só `__init__.py` vazio) | Não montados, não importados. Inofensivos. | Alta |
| Agregadores 8/9 (`comercial, operacoes, tecnico, inteligencia, gestao, financeiro, pessoas`) | **RE-EXPORT puro** (não são dead-code) | `main_production` importa dos agregadores. `fiscal_contabil/` é misto (tem impl. própria em `notas_fiscais/nfe`). | Alta |
| 30 arquivos `.bak/.backup` de código | **Rastreados no git** → candidatos a limpeza | `git ls-files "*.bak"` confirma. Ex.: 7 `.bak` em `frontend/src/services/government/`, vários `operacional/*/page.tsx.bak`. | Alta |
| Prefixos/rotas duplicados | **Sem colisão real** | `notification_router` aparece 2x mas com fontes/prefixos distintos (`/operacional` vs raiz). | Alta (amostral) |

---

## 5. PLANO DE CORREÇÃO PROPOSTO (ordenado: impede-funcionar → bug → limpeza)

> Classificação: **[CIC]** = exige validação humana (Jordan); **[AUTÔNOMO]** = mecânico/baixo risco; **[ZONA PROTEGIDA]** = fora de escopo de correção (só Jordan decide).

| # | Ação | Classe | Bloco |
|---|------|--------|-------|
| 1 | **Rebuild + redeploy da imagem do backend** a partir do host (resolve B1: `operacional/ai` + 98 `.py` faltando → restaura operacional, campo, crm, bidding, equipment, empresas, fiscal, government, DP). | **[CIC]** (toca deploy/imagem; validar que não quebra o que está no ar) | 🔴 |
| 2 | Investigar/criar `modules.ai.openclaw` ou remover sua importação (B2). | **[CIC]** | 🔴 |
| 3 | **Aplicar migrations pendentes** (B3: `extra_metadata`, `tenant_id`, `profile_questions`, `rulestatus`, enums). | **[ZONA PROTEGIDA]** `alembic/versions/` — só Jordan | 🔴 |
| 4 | Corrigir conexão Redis do `celery-batch` (`localhost`→`conecta-pro-redis`) e registrar tasks `gedeon.risk_monitor`/`nfse`/`nfe` (B4). | **[CIC]** (config + depende de #1) | 🔴 |
| 5 | Normalizar dados/enum `tenant_status`/`tenantstatus`/`alertstatus` (case `ATIVO`/`active`/`ACTIVE`) no banco e/ou no mapeamento (B3/B4). | **[CIC]** | 🟠 |
| 6 | `forecast_controller.py` → consultar DB real em vez de mock. | **[CIC]** (lógica de negócio) | 🟠 |
| 7 | Padronizar `values_callable` nos 208 `Column(Enum)` fora de zona protegida. | **[CIC]** (toca modelos → migration + teste) | 🟠 |
| 8 | Completar migração `kit_mensal → portaria_presencial` (`kit_real_controller.py`). | **[CIC]** (SQL raw sobre `contracts`) | 🟠 |
| 9 | Corrigir UUID shadowing: declarar sub-rotas literais antes de `/{id}` (`document-tags/most-used`, `alerts/statistics`). NÃO mexer em `suppliers/list` (zona protegida). | **[AUTÔNOMO]** fora de `financial/` | 🟠 |
| 10 | Corrigir código sync-em-async: `notifications/channels` (`.query`), `mobile/dashboard` (`User` dict). | **[CIC]** | 🟠 |
| 11 | Adicionar `from e` nos 708 `B904` fora de zona protegida (mecânico). | **[AUTÔNOMO]** | 🟡 |
| 12 | Envolver `.toFixed()` de fonte-API com `Number(... ?? 0)` (amostra de ~10 casos sem guarda). | **[CIC]** caso a caso | 🟡 |
| 13 | Corrigir os 7 erros de `tsc` (croniter type, export `FgtsPorTipo`, optional chaining em KitDetalheModal, prop `title` de ícone). | **[AUTÔNOMO]** | 🟡 |
| 14 | Limpeza: `main_*.py` órfãos, `modules/fase5`, 30 `.bak` (só após confirmar #1 estável). | **[CIC]** (confirmar zero uso) | 🟢 |

**Zonas protegidas tocadas (FORA de escopo de correção autônoma):** #3 (`alembic/versions/`), parte de #1 (não reconstruir `financial/`/`government_integrations/` manualmente — apenas re-bake), `suppliers/list` (`financial/`).

---

## 6. O QUE MUDOU vs DIAGNÓSTICO_FASE1 (servidor foi mexido)

| Aspecto | Fase 1 (29/05) | Agora (30/05) | Delta |
|--------|----------------|---------------|-------|
| Containers | quase todos `unhealthy`; `erp-grafana` Exited(255) | **healthy**; grafana religado (:3002) | ✅ melhorou |
| `tsc --noEmit` | **não rodou** (OOM, RAM saturada) | rodou: **7 erros** (strict:true) | ✅ mensurado — dívida de tipo baixa |
| Quebra funcional | "não encontrei evidência de quebra crítica" | **10 módulos + DP offline** na imagem | 🔴 **piorou** (revelado) |
| 500 em endpoints | não testado (curl não priorizado) | **~25/91 GETs = 500** (schema drift) | 🔴 **revelado** |
| `modules/hr` dead-code? | "possível legado" | **EM USO** (dep. transitiva) | ✏️ corrigido |
| B904 | 708 | 1104 total (708 fora de zona) | ➖ reconciliado |
| forecast mock / enums / kit_mensal | reportados | **idênticos** — nada corrigido | ➖ inalterado |
| Imagem vs host | não avaliado | **98 `.py` divergentes** (imagem defasada) | 🔴 **revelado — causa raiz central** |

**Conclusão do delta:** a recriação dos containers via `docker compose up` **estabilizou a infra** (healthy) mas **expôs/consolidou** o problema central: a **imagem de produção não reflete o código do host**. As funcionalidades de DP, operacional, comercial e fiscal existem no repositório mas **não estão servindo**. A próxima fase (correção) deve começar por **#1 (re-bake da imagem)** e **#3 (migrations)** — ambos **[CIC]/zona protegida**, exigindo decisão de Jordan antes de executar.

---

### Nota de confiança global
Achados 🔴 (B1, B3, B4) e bugs revalidados: **confiança ALTA** — tracebacks reais e introspecção direta do app vivo, verificados nesta sessão. Itens marcados "Média" (toFixed em runtime, `modules/search` transitivo, submódulos `hr`) **não foram fechados** e estão sinalizados como tal. Amostra de endpoints = ~11% dos GETs (honesto: há mais 500 prováveis não testados). **Nada foi inventado; nada foi corrigido.**
