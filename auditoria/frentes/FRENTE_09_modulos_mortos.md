# FRENTE 9 — Módulos mortos: medir de verdade, decidir por escrito, e preparar (não ligar)

**Data:** 12→13/09/2026 · **Branch:** `frente/09-modulos-mortos` (a partir de `30be528a3`) · **Sessão:** tmux-agente-09 · **Módulo editado:** qa
**Onde mediu:** `conecta-pro-backend-staging` (imagem de 11/09 16:55; os 20 commits de backend posteriores não tocam nenhum dos módulos aqui) + `conecta_pro_staging` + `/var/log/nginx/access.log*` do host (só leitura, ≈15 dias de produção).
**O que esta frente NÃO fez, por contrato:** não ligou módulo, não apagou arquivo, não tocou frontend, não tocou `checar_regressao.py`.

## 0. A premissa da frente estava errada — e isso muda a decisão

O pré-mortem (PARTE 0.5 e FRENTE 9) e o benchmark (9.1) tratam bidding / health_occupational / retention / document_kits como **módulos esquecidos com código e zero rotas**. Medido em `app.routes`, a história é outra:

- Eles **foram aposentados de propósito, por escrito, em 08/09/2026**, pela sessão `tmux-fase5`, com revisor e prova de banco:
  - `1ccb469a9` — bidding: 97 rotas apagadas, 3 entradas do beat, botões ERP que criavam conta a receber/lead/posto REAIS a partir de seed, sino com 108 notificações de certidões inventadas. Revisor: `auditoria/qa/revisao_20260908/bidding.md` (MORTA 88/88; 14 defeitos, 5 deles em dinheiro).
  - `a20a84d73` — retention (70), document_kits (54), scheduler (26), services (63): "nenhum chamador no redesign/MCP/agentes; tabelas inexistentes ou vazias".
  - `e08874170` — health_occupational: "duplica /people-management/sst; ORM ≠ banco; task diária falhando".
- A poda apagou **só os handlers** (decorator + função). Ficou o resto do pacote: `router = APIRouter(...)` vazio, models, schemas, services, repositories, tasks, agents. `main_production.py` continua chamando `include_router` nesses routers vazios — por isso o boot diz `Modulo Comercial: OK (CRM + Clients + Bidding + Services)` e monta **0** rotas. Não é `safe_import` engolindo falha (risco 1 do pré-mortem): é montagem de casca.
- Consequência: "LIGAR" não é "montar o router" — é **restaurar 97 handlers de `1ccb469a9^` e reabrir 14 defeitos revisados**. A pergunta certa para o dono não é "ligar ou apagar", é "**terminar a aposentadoria (apagar o pacote) ou reverter uma decisão de 08/09**".

## 1. Estado antes — medição correta, por módulo

Fonte: `scratchpad/medir_container.py` (no container: `app.routes` por `endpoint.__module__`, `APIRouter(` por regex, `@task` por regex, `__tablename__` × `information_schema` × `count(*)`) + `medir_host.py` (repositório inteiro: imports `from/import modules.<m>` inclusive tardios; `git log -1`).

Colunas: **py** arquivos `.py` (repo = container, conferido) · **routers** `APIRouter(` declarados · **rotas** montadas em `app.routes` · **imp** arquivos fora do módulo que o importam (repo inteiro, inclui tests/api-v1; a coluna `uso` do caçador é a versão só-produção) · **celery** entradas em `include=[]` do `celery_app.py` · **@task** decoradores · **tab** tabelas declaradas / existentes no staging / com ≥1 linha · último commit.

| módulo | py | routers | rotas | imp | celery | @task | tab decl/exist/dado | último commit | classe |
|---|---:|---:|---:|---:|---:|---:|---|---|---|
| people_management | 344 | 4 | 331 | 97 | 2 | 13 | 40/40/31 | 2026-09-11 | VIVO |
| operacional | 232 | 11 | 338 | 109 | 1 | 12 | 32/32/21 | 2026-09-11 | VIVO |
| financial | 207 | 2 | 155 | 82 | 1 | 24 | 74/60/29 | 2026-09-08 | VIVO |
| government_integrations | 178 | 1 | 40 | 34 | 2 | 16 | 33/**0**/0 | 2026-09-11 | VIVO (33 tabelas fantasma — já contadas por `checar_tabela_fantasma`) |
| **hr** | 172 | 1 | **0** | 32 | 0 | 0 | 29/25/7 | 2026-09-08 | **DESLIGADO** — biblioteca da folha |
| ai | 127 | 1 | 22 | 110 | 1 | 1 | 15/14/4 | 2026-09-12 | VIVO |
| integrations | 113 | 1 | 53 | 97 | 2 | 20 | 24/16/10 | 2026-09-11 | VIVO |
| **bidding** | 101 | 1 | **0** | 15 | 1 | 11 | 15/15/15 | 2026-09-08 | **DESLIGADO** — aposentado 08/09; clientes de CND vivem dentro |
| gedeon | 80 | 1 | 41 | 41 | 2 | 7 | 4/4/4 | 2026-09-10 | VIVO |
| crm | 79 | 2 | 180 | 118 | 1 | 11 | 33/33/19 | 2026-09-12 | VIVO |
| notifications | 74 | 1 | 6 | 53 | 3 | 5 | 19/8/1 | 2026-09-09 | VIVO |
| ged | 55 | 1 | 38 | 13 | 1 | 1 | 7/6/3 | 2026-09-09 | VIVO |
| **retention** | 47 | 1 | **0** | 8 | 0 | 0 | 14/7/1 | 2026-09-08 | **DESLIGADO** — aposentado 08/09; models importados em try/except |
| client_portal | 42 | 1 | 43 | 5 | 1 | 2 | 4/4/4 | 2026-09-10 | VIVO |
| campo | 39 | 1 | 14 | 12 | 0 | 0 | 9/5/1 | 2026-09-08 | VIVO |
| security_lgpd | 35 | 2 | 5 | 5 | 0 | 0 | 4/4/1 | 2026-09-08 | VIVO |
| cct | 33 | 1 | 15 | 9 | 0 | 0 | 3/2/0 | 2026-09-08 | VIVO |
| recruitment | 33 | 1 | 15 | 10 | 0 | 0 | 7/7/**0** | 2026-09-08 | VIVO sem dado (fora desta frente; revisão pendente do Jordan) |
| **health_occupational** | 33 | 1 | **0** | 9 | 1 | 3 | 12/7/4 | 2026-09-08 | **DESLIGADO** — aposentado 08/09; `health_asos` (97) e `publishers` ainda usados |
| empresas | 26 | 1 | 11 | 17 | 0 | 0 | 2/2/2 | 2026-09-08 | VIVO |
| juridico | 25 | 1 | 35 | 4 | 0 | 0 | 0/0/0 | 2026-09-08 | VIVO |
| **fase5** | 23 | 1 | **0** | 5 | 0 | 0 | 0/0/0 | 2026-07-01 | **MORTO** |
| pessoas | 20 | 0 | 0 | 2 | 0 | 0 | — | 2026-03-28 | AGREGADOR |
| reimbursement | 19 | 1 | 26 | 10 | 0 | 0 | 4/4/2 | 2026-09-08 | VIVO |
| clients | 17 | 2 | 13 | 12 | 0 | 0 | 5/5/3 | 2026-09-09 | VIVO |
| config | 17 | 1 | 2 | 7 | 0 | 0 | 5/5/2 | 2026-09-08 | VIVO |
| **document_kits** | 16 | 1 | **0** | 3 | 0 | 0 | 4/3/**0** | 2026-09-08 | **MORTO** |
| fiscal_contabil | 16 | 1 | 6 | 4 | 1 | 2 | 0/0/0 | 2026-09-08 | VIVO |
| **scheduler** | 16 | 1 | **0** | 5 | 0 | 0 | 7/5/0 | 2026-09-08 | **DESLIGADO** — só o model `ScheduledTask` é importado (tardio) por `gov_sync_jobs.py` |
| **services** | 16 | 1 | **0** | 3 | 0 | 0 | 5/5/1 | 2026-09-08 | **MORTO** (só um oráculo o importa) |
| signatures | 13 | 1 | 12 | 25 | 1 | 1 | 0/0/0 | 2026-09-11 | VIVO |
| operacoes | 10 | 0 | 0 | 2 | 0 | 0 | — | 2026-07-09 | AGREGADOR |
| comercial | 9 | 0 | 0 | 2 | 0 | 0 | — | 2026-03-12 | AGREGADOR |
| fiscal | 8 | 1 | 3 | 8 | 0 | 0 | 0/0/0 | 2026-09-08 | VIVO |
| gdrive | 8 | 1 | 7 | 29 | 0 | 0 | 0/0/0 | 2026-09-08 | VIVO |
| tecnico | 8 | 4 (vazios) | 0 | 2 | 0 | 0 | — | 2026-09-06 | AGREGADOR |
| inteligencia | 7 | 4 (vazios) | 0 | 2 | 0 | 0 | — | 2026-09-07 | AGREGADOR (monta `search`) |
| analytics | 4 | 0 | 0 | 1 | 1 | 1 | 0/0/0 | 2026-09-07 | DESLIGADO — task `analytics.recalcular_kpis` no beat + import tardio do redesign |
| **lgpd** | 3 | 1 | **0** | 1 | 0 | 0 | 0/0/0 | 2026-03-20 | **MORTO** (só `main.py`, que não é produção) |
| search | 2 | 1 | 1 | 1 | 0 | 0 | 0/0/0 | 2026-04-01 | VIVO (vazio de código; abaixo do teto de 3 .py) |
| gestao | 1 | 3 (vazios) | 0 | 2 | 0 | 0 | — | 2026-09-06 | AGREGADOR |
| financeiro | 1 | 0 | 0 | 2 | 0 | 0 | — | 2026-07-29 | AGREGADOR |
| hr/rep_integration | 27 | — | 0 | — | — | — | — | — | **fora — frente 1** |

Boot do staging: um único WARNING (`Modulo OpenClaw: No module named 'modules.ai.openclaw'` — apagado em 06/09, `main_production.py` ainda tenta; zona proibida, fica registrado).

### Uso HTTP real (nginx, ≈15 dias, produção — só leitura)

| prefixo | req | o que é |
|---|---:|---|
| `/api/v1/bidding/certificates` | 887 | **60–100×/dia, 404 desde 08/09** — ver §5 |
| `/api/v1/document-kits/stats` | 897 | **60–100×/dia, 404 desde 08/09** — ver §5 |
| `/api/v1/health-occupational/*/estatisticas` | 32 | tudo em 07/09 (antes da aposentadoria); zero depois |
| `/api/v1/scheduler` | 7 | — |
| retention/onboarding/climate/turnover/services/lgpd/fase5/hr | **0** | ninguém chamou em 15 dias |

## 2. Classificação e matriz de decisão — para o Jordan marcar

Regra usada (a mesma do caçador): **rotas montadas = 0** → DESLIGADO se alguém de produção importa (modules/, core/, celery include, scripts operacionais) ou há task no beat; MORTO se nada disso. Agregador, `main_production.py`, `api/v1` (só `main.py`) e `tests/` **não contam como uso**: montar um router vazio não é usar.

| módulo | classe | proposta | por que (medido) | custo de LIGAR | risco de APAGAR (quem quebra) | **Decisão do dono** |
|---|---|---|---|---|---|---|
| **bidding** (101 py) | DESLIGADO | **APOSENTAR o produto; MANTER `integrations/receita_federal/` como biblioteca** (mover para `people_management/ged/` ou `fiscal_contabil/`) | 15 tabelas, **tudo seed de 12/03** (tenders 11, opportunities 20, sync_jobs 332 = 298 jobs "completed" com 0 registros); PNCP batia em URL 404 12×/dia por 26 dias; botões ERP criavam receita/lead/posto REAIS de dado fictício; 14 defeitos no revisor, 5 em dinheiro (medição somada 2×, reajuste que não altera valor, retenção nunca aplicada). Depois de 08/09: 0 req. | Restaurar 97 handlers de `1ccb469a9^` (todos têm `CurrentActiveUser` — auth ok, §3); consertar 5 colunas de drift (§3); corrigir os 14 defeitos; reescrever o client PNCP (BASE_URL inexistente); re-entrar 3 beats. **Não é "ligar", é reconstruir.** | `people_management/ged/tasks/cnd_sync_task.py` (import tardio, 6 pontos) usa `bidding.integrations.receita_federal.{infosimples_cnd_service, cnd_client, cndt_client, crf_client, sefaz_am_client, prefeitura_manaus_client}` — **é o sync diário de CNDs do GED (vivo)**. `fiscal_contabil/__init__.py` re-exporta `certificate_router` (vazio). Celery `include` tem `modules.bidding.tasks` (11 tasks sem beat). 3 oráculos (`test_oraculo_cnd_nao_fabrica`, `_licitacao_crm`, `_portais_nao_chutam`) e 7 tests. Redesign `licitacoes.json` (10 telas) lê `bidding_*` por SQL direto — some junto se as tabelas forem. Frontend clássico: `/dashboard` e `/modulos/meu-espaco` ainda chamam `/bidding/certificates` (§5). | ☐ LIGAR ☐ APOSENTAR ☐ BIBLIOTECA |
| **health_occupational** (33 py) | DESLIGADO | **APOSENTAR** (o SST vivo é `people_management/sst`: `gp_asos`, `gp_cats`, `sst_fichas_epi`, `sst_afastamentos`…) | Duplica o SST; 5 de 12 tabelas não existem; `health_epi_deliveries` com 14 colunas só no model; tasks `sst.verificar_*` fora do beat desde 08/09. `health_asos` tem 97 linhas (16/03→08/09) que ninguém mais lê: o redesign `saude-ocupacional.json` (9 telas) lê `gp_asos`/`sst_*`. Depois de 08/09: 0 req. | Recriar 5 tabelas + 14 colunas; decidir qual ASO é o oficial (97 em `health_asos` × os de `gp_asos`); duplicar o que o SST já faz. **Sem sentido.** | `people_management/human_resources/controllers/training_controller.py:19` importa `health_occupational.publishers.publish_treinamento_concluido` (e `training` está montado: `/people-management/human-resources/training/*`) — **mover o publisher antes de apagar**. Celery `include` tem `modules.health_occupational.tasks`. `notifications/anti_procrastination/.../module_integrator.py` cita `health_asos` em SQL. 5 tests. MCP `estoque_epi/status_pcmso/status_ppra` já apontam para o SST (08/09). | ☐ LIGAR ☐ APOSENTAR ☐ BIBLIOTECA |
| **retention** (47 py) | DESLIGADO | **APOSENTAR** | 7 de 14 tabelas não existem; as 7 que existem têm 0 linhas (só `turnover_audit_logs` = 5); pesquisa de clima nunca foi implantada (MCP `dashboard_clima` já responde isso); 0 req em 15 dias. | Criar 7 tabelas (onboarding_*, climate_scores, profile_questions, turnover_risk_*), restaurar 70 handlers de `a20a84d73^`, e um processo de RH que não existe na empresa. | `people_management/human_resources/models/__init__.py:49-59` e `services/{climate,onboarding}_service.py:8` importam em `try/except` (somem calados — é a classe 🔇 do `checar_import_orfao`); esses dois services do `human_resources` só são importados pelo próprio `services/__init__.py`. 2 migrations alembic citam (não se edita). 2 tests. | ☐ LIGAR ☐ APOSENTAR ☐ BIBLIOTECA |
| **hr** (172 py, 145 fora de rep_integration) | DESLIGADO | **MANTER COMO BIBLIOTECA** e, quando a frente 1 fechar, apagar só os subpacotes sem importador | 0 rotas, mas `hr_payslips` = **888 linhas**, `time_sheets` 237, `employee_vacation_periods` 104, `geofence_zones` 31. Importado em produção por 11 arquivos: folha (`payroll_service`, `espelho_service`, `time_tracking_service`, `vacation_service`, `people_management/hr/aggregator.py`), portal (`dp_payslips_controller`, `payslip_*_service`), Hermes (`tools_rh_doc.py`), redesign (`VacationType`), `scripts/virada_folha.py`, 2 oráculos. | — (não é para ligar; a folha já o usa) | Subpacotes **usados**: `employee_portal` (PaySlip — 888 holerites), `time_tracking`, `payroll_integration`. **Sem importador de produção**: `analytics_dashboard` (69 refs, todas em tests/api-v1/extract), `mobile_time_clock` (59, idem; `geofence_zones` 31 linhas — conferir quem escreve), `rep_integration` (frente 1). | ☐ BIBLIOTECA ☐ PODAR subpacotes: ☐ analytics_dashboard ☐ mobile_time_clock |
| **scheduler** (16 py) | DESLIGADO | **MANTER só `models/scheduled_task.py`** (mover para `government_integrations/jobs/`), apagar o resto | 5 tabelas existem, todas com 0 linhas; 2 não existem; 7 req em 15 dias (todas antes de 08/09). O único uso é `gov_sync_jobs.py:343,390,460` importando `ScheduledTask/TaskCategory/TaskType` **tardio, dentro de função** — o grep de topo não veria. | Restaurar 26 handlers de `a20a84d73^` para um agendador que o Celery beat já faz. | `government_integrations/jobs/gov_sync_jobs.py` (import tardio). `scripts/extract_openapi_scheduler.py` (dev). | ☐ LIGAR ☐ APOSENTAR ☐ BIBLIOTECA |
| **document_kits** (16 py) | **MORTO** | **APOSENTAR** | 4 tabelas: 3 existem com **0 linhas**, `document_kit_item_statuses` não existe; `document_kits.extra_metadata` é o drift conhecido do `backend/CLAUDE.md`. O kit documental vivo é `ged_kit_documents` (redesign `documentos.json` lê só ele; Hermes `tools_read_ged` idem). Ninguém de produção importa. | Restaurar 54 handlers, criar 1 tabela, e competir com o GED vivo. | Só `main_production.py` (monta 2 routers vazios: `document_kit_router` via `tecnico`, `operational_router`) e `tests/test_document_kits.py`. `/dashboard` clássico chama `/document-kits/stats` (§5). | ☐ LIGAR ☐ APOSENTAR |
| **services** (16 py) | **MORTO** | **APOSENTAR** (junto com `scripts/orq/test_oraculo_servicos.py`, que hoje vigia um módulo sem rota) | `service_catalog` = 1 linha, o resto 0; 0 req em 15 dias; o redesign `servicos.json` (4 telas) lê `diarist_schedules`/`contracts`, não `service_*`. | Restaurar 63 handlers de `a20a84d73^`. | `comercial/__init__.py` re-exporta o router vazio; `scripts/orq/test_oraculo_servicos.py` importa schemas/services (**vai junto**); `tests/test_services_model.py`. | ☐ LIGAR ☐ APOSENTAR |
| **fase5** (23 py) | **MORTO** | **APOSENTAR** | Último commit 01/07; 11 decoradores de rota num router que só `api/v1/__init__.py` (caminho morto do `main.py`) monta; 0 tabelas; `cct_compliance` chumba `TABELA_PISOS_SINDCOND_2026` no código (o CCT vivo está em `modules/cct` + banco); `frontend/src/hooks/fase5/*` existe e nenhuma página usa. | Montar em `main_production.py` (zona proibida) um "Grand Finale" de julho. | `api/v1/__init__.py`, `extract_openapi_fase5.py`, 3 tests. | ☐ LIGAR ☐ APOSENTAR |
| **lgpd** (3 py) | **MORTO** | **APOSENTAR** | Router `/api/v1/me` (GET/POST/DELETE "delete-me") só montado por `main.py` (dev). O LGPD vivo é `security_lgpd` (5 rotas, direito ao esquecimento incluído). Último commit 20/03. | Montar em `main_production.py`. | `main.py` (dev). | ☐ LIGAR ☐ APOSENTAR |
| analytics (4 py) | DESLIGADO | MANTER (task) | `analytics.recalcular_kpis` no beat (hourly/daily) + import tardio no redesign. Não é morto. | — | `celery_app.py`, `redesign_data_controller.py:5276`. | — |
| agregadores (7) | AGREGADOR | — | Só re-exportam; `tecnico`/`gestao`/`inteligencia` carregam routers **vazios** para `main_production.py` não quebrar (documentado no próprio `__init__`). | — | — | — |

**Se o dono marcar APOSENTAR nos 4 mortos + retention + document_kits:** some ~120 arquivos (`document_kits` 16, `services` 16, `fase5` 23, `lgpd` 3, `retention` 47) e 0 rotas — a única fiação é remover os `include_router` vazios de `main_production.py` (zona proibida; linhas 469-475 bidding, 625/638 document_kits, 675-678 retention, 477 services, 774-776 health) e os `include` de `celery_app.py` (linhas 30 e 33) — **na mesma entrega**, senão `checar_import_orfao` acusa coluna 0 e o boot cai (bake 1 de 07/09).

## 3. bidding — o custo de ligar, rota por rota

Fonte: `git show 1ccb469a9^:backend/modules/bidding/controllers/*.py` (estado imediatamente antes da aposentadoria), `scratchpad/bidding_antes.py`.

**97 rotas existiriam** (tender 15 · document 11 · proposal 13 · contract 14 · certificate 11 · agent 13 · sync 5 · erp 6 · opportunity 4 · dispute 5). **Auth: 97/97** têm `current_user: CurrentActiveUser` na assinatura (o alias `Annotated` de `core.auth.dependencies` — a primeira leitura, por `Depends(get_current_active_user)` literal, deu 0/97 e estava errada; fica o aviso para quem for auditar auth por grep). O risco 3 do pré-mortem (rota sem auth) **não se aplica ao bidding**; aplica-se ao ponto, que é outra frente.

<details><summary>as 97 rotas (método · path · auth)</summary>

```
tender_controller.py  prefix=/tenders
  GET    /api/v1/bidding/tenders · dashboard · abertos · participando · segmento/{segmento} · {tender_id} · {tender_id}/documentos · pncp/status · pncp/buscar
  POST   /api/v1/bidding/tenders · {tender_id}/participar · {tender_id}/status · sync-pncp
  PUT    /api/v1/bidding/tenders/{tender_id}      DELETE /api/v1/bidding/tenders/{tender_id}
document_controller.py  prefix=/documents
  GET    documents · expiring · status · habilitacao (500: itera tupla) · tipos · tipo/{tipo} (500: MultipleResultsFound) · {document_id}
  POST   documents · atualizar-status        PUT/DELETE {document_id}
proposal_controller.py  prefix=/proposals
  GET    proposals · estatisticas · vencedoras · tender/{tender_id} · {proposal_id}
  POST   proposals · {id}/pronta · {id}/enviar · {id}/resultado · {id}/lance · calcular-bdi     PUT/DELETE {proposal_id}
contract_controller.py  prefix=/contracts
  GET    contracts · dashboard · vigentes · vencendo · {contract_id} · {contract_id}/medicoes
  POST   contracts · {id}/aditivo · {id}/reajuste/calcular · {id}/reajuste/aplicar (não altera valor) · {id}/medicoes (retenção nunca aplicada) · medicoes/{id}/aprovar (soma 2× se aprovado 2×)
  PUT/DELETE {contract_id}
certificate_controller.py  prefix=/certificates
  GET    certificates · status/{cnpj} · tipos · pendentes-renovacao · {certificate_id} · cnpj/{cnpj}/tipo/{tipo}
  POST   certificates · renovar · atualizar-status        PUT/DELETE {certificate_id}
agent_controller.py  prefix=/agents
  GET    status · scout/portais · sentinel/tipos · sentinel/alertas · warrior/status
  POST   scout/buscar · analyst/analisar · assessor/avaliar · pricer/calcular · pipeline · sentinel/verificar · warrior/simular · compiler/gerar
sync_controller.py  prefix=/sync        POST pncp/trigger · precos/trigger (kwargs que a task não aceita → TypeError)   GET jobs · jobs/{job_id} · status
erp_controller.py  prefix=/erp          GET status/{contract_id}   POST converter/{contract_id} · medicao/{contract_id} · fatura/{medicao_id} · lead/{opportunity_id} · crm/{contract_id}   ← criam receita/lead/posto REAIS sem idempotência
opportunity_controller.py  prefix=/opportunities   GET opportunities · statistics · {opportunity_id}   POST search
dispute_controller.py  prefix=/disputes            GET disputes · {dispute_id}   POST simulate · {dispute_id}/lance   PATCH {dispute_id}/status
TOTAL rotas que existiriam: 97 · sem auth na assinatura: 0
```
</details>

**Tabelas (staging, `information_schema` × model SQLAlchemy):** as 15 existem; 5 têm coluna no model que o banco não tem — `bidding_assessments.raw_assessment`, `bidding_pricing.assessment_id, raw_pricing`, `bidding_disputes.updated_at`, `bidding_price_history.metadata_extra`, `bidding_analyses.opportunity_id`. Qualquer rota que carregue esses models por ORM dá `UndefinedColumn` 500 no primeiro SELECT. Linhas: analyses 5, assessments 5, certificates 8, company_documents 6, disputes 2, measurements 6, opportunities 20, price_history 10, pricing 3, proposal_items 10, proposals 5, public_contracts 3, sync_jobs 332, tender_documents 8, tenders 11 — **seed de 12/03 + 332 jobs vazios**. Nenhuma linha de negócio.

**Beat (removido em 08/09):** `bidding-sync-pncp-2h`, `bidding-sync-precos`, `bidding-check-certidoes-6h`. O `include=["modules.bidding.tasks"]` ficou (11 `@shared_task` carregadas em todo worker, nenhuma agendada).

## 4. O que foi feito — arquivo por arquivo

- `backend/scripts/qa/checar_modulo_morto.py` (**novo**, 152 linhas, ruff limpo). Roda no container. Enumera `/app/modules/*` com `__init__.py`; conta `.py`; atribui cada `APIRoute` de `app.routes` ao módulo por `endpoint.__module__`; varre imports (`from modules.X` / `import modules.X`, **qualquer coluna** — tardio conta) em `modules/**`, `core/**`, `celery_app.py`, `scripts/**` (exceto `extract_*`); separa `uso` (produção) de `vigia` (`scripts/orq`, `scripts/qa`); ignora agregadores (lista fixa `AGREGADORES`), `main_production.py`, `api/`, `tests/`; lê o `include=[]` do `celery_app.py`. Excluído por construção: `hr/rep_integration` (`IGNORAR_SUBARVORES`, frente 1). Veredito puro em `veredito()` com `--self-check`. `--todos` lista os VIVOS também. Linha canônica `TOTAL módulos mortos: N`, exit 1 se N>0.
- `auditoria/frentes/FRENTE_09_modulos_mortos.md` (este arquivo).
- Scripts de medição ficaram no scratchpad da sessão (`medir_container.py`, `medir_host.py`, `drift.py`, `bidding_antes.py`) — descartáveis; o que precisa repetir está no caçador.

## 5. Estado depois — o caçador no staging (nasce VERMELHO, de propósito)

Este é um caçador de dívida contada, não um conserto: o "vermelho" É a entrega. Ele só fica verde quando o dono decidir e o integrador apagar. Copiado para `/tmp` do container (`/app/scripts` do staging é volume só-leitura).

```
$ docker exec -e PYTHONPATH=/app conecta-pro-backend-staging python3 /tmp/checar_modulo_morto.py
módulos de /app/modules medidos em 2026-09-13 por app.routes · endpoint.__module__ (agregadores fora: comercial, financeiro, gestao, inteligencia, operacoes, pessoas, tecnico; fora também: hr/rep_integration)
   módulo                     py  rotas  uso  vigia  celery  veredito
   analytics                   4      0    1      0     sim  DESLIGADO  ← modules/operacional/controllers/redesign_data_controller.py
   bidding                   101      0    2      3     sim  DESLIGADO  ← modules/fiscal_contabil/__init__.py, modules/people_management/ged/tasks/cnd_sync_task.py
   document_kits              16      0    0      0       —  MORTO
   fase5                      23      0    0      0       —  MORTO
   health_occupational        33      0    1      0     sim  DESLIGADO  ← modules/people_management/human_resources/controllers/training_controller.py
   hr                        145      0   11      2       —  DESLIGADO  ← modules/ai/conversation/services/orquestrador/tools_rh_doc.py, modules/operacional/controllers/redesign_data_controller.py, modules/people_management/employee_portal/controllers/dp_payslips_controller.py
   lgpd                        3      0    0      0       —  MORTO
   retention                  47      0    3      0       —  DESLIGADO  ← modules/people_management/human_resources/models/__init__.py, modules/people_management/human_resources/services/climate_service.py, modules/people_management/human_resources/services/onboarding_service.py
   scheduler                  16      0    1      0       —  DESLIGADO  ← modules/government_integrations/jobs/gov_sync_jobs.py
   services                   16      0    0      1       —  MORTO
   search                      2      1    0      0       —  VAZIO

TOTAL módulos mortos: 4 — document_kits, fase5, lgpd, services
exit=1
```

`--self-check` no host: `OK checar_modulo_morto --self-check`. Sem `/app`: `RECUSO: roda DENTRO do container` (exit 2 — NÃO VERIFICADO, nunca verde por caminho errado).

**Prova de que ele mede o que diz:** `hr` = 145 (172 − 27 do `rep_integration`), `bidding` uso = 2 e os dois nomeados batem com o grep manual do repositório inteiro; `search` (1 rota, 2 .py) cai em VAZIO e não infla a conta.

### Achado colateral que o dono precisa ver (não corrigido — frontend fora do escopo)

A aposentadoria de 08/09 deixou o **painel principal chamando duas rotas mortas a cada abertura**: `frontend/src/services/dashboard/dashboardStatsService.ts:237` (`GET /api/v1/bidding/certificates`) e `:262` (`GET /api/v1/document-kits/stats`), usados por `/dashboard` (957 req) e `/modulos/meu-espaco` (808 req) — ~60–100 × 404/dia desde 08/09, engolidos por `catch { /* silencioso */ }`. Efeito: o card "Kits" mostra 0/0/0/0 e o alerta de **certificado digital A1** (o único dado de `bidding_certificates` que o dashboard usava, "Decisão A2") sumiu calado. `checar_botao_morto` não viu porque só cobre telas do redesign; `checar_rotas_frontend` conta como "só clássico". Também `frontend/src/app/modulos/relatorios/central/page.tsx:116,175,264-265` e `modulos/gestao-pessoas/ged/whatsapp/page.tsx:123`.

## 6. Fiação pendente para o integrador

**`backend/scripts/qa/checar_regressao.py`** — dicionário `CACADORES` (roda no container), depois de `checar_botao_morto.py`:
```python
    # Módulo com código, 0 rotas em app.routes, 0 imports de produção, 0 task no include: morto.
    # 4 na estreia (12/09/2026): document_kits, fase5, lgpd, services. Agregadores e
    # hr/rep_integration (frente 1) ficam fora por construção. ~40 s (monta o app).
    "checar_modulo_morto.py": lambda s: _n(r"^TOTAL módulos mortos:\s*(\d+)", s, "TOTAL módulos mortos: 0"),
```
E `python3 backend/scripts/qa/checar_regressao.py --gravar` para a base nascer em 4 (decisão vai na mensagem do commit).

**`docs/ARSENAL_OPERACAO.md`** — linha na tabela dos contados:
```
| `checar_modulo_morto.py` | container (~40 s) | `TOTAL módulos mortos: N` | módulo com código e 0 rotas montadas, 0 imports de produção, 0 task? (linha de base; agregadores e `hr/rep_integration` fora) |
```

**Frontend (§5, achado colateral — decisão do dono junto com a matriz):** se `bidding`/`document_kits` forem APOSENTADOS, remover as duas chamadas em `dashboardStatsService.ts:237,262` (e o card "Kits" passa a ler `ged_kit_documents` ou some) e as de `relatorios/central/page.tsx` e `ged/whatsapp/page.tsx`. Se forem LIGADOS, nada a fazer no front.

**`celery_app.py` / `main_production.py`:** nada agora. Só quando o dono marcar APOSENTAR — e aí as linhas listadas no fim do §2, na mesma entrega que apaga os pacotes.

**DDL:** nenhum. Esta frente não criou nem alterou tabela.

## 7. O que NÃO foi feito e por quê

- **Não liguei módulo nenhum.** Motivo medido: os quatro do pré-mortem foram aposentados por escrito em 08/09 com prova de banco; ligar = reverter uma decisão de 4 dias atrás, e no caso do bidding = reconstruir 97 handlers com 14 defeitos revisados. Isso é do dono (trava 1 da FRENTE 9: "decidir antes de ligar").
- **Não apaguei nada.** Contrato + pré-mortem 9.4. E a poda tem 4 amarras que o integrador precisa fazer junto: `main_production.py`, `celery_app.py`, o publisher do `health_occupational` usado pelo `training_controller`, e os clientes de CND dentro do `bidding`.
- **Não mexi no frontend** (achado §5). Fora do escopo declarado (só 2 arquivos).
- **Não registrei o caçador no `checar_regressao.py` nem no `ARSENAL_OPERACAO.md`** — zona proibida; linhas exatas no §6.
- **Não medi `hr/rep_integration`** (frente 1). O caçador o ignora por constante; quando a frente 1 fechar, tirar `"hr/rep_integration"` de `IGNORAR_SUBARVORES`.
- **Oráculo VERMELHO→VERDE (regra 0 do contrato):** não se aplica à letra — não há conserto aqui, há medição. O caçador nasce vermelho (4) e fica; o verde vem da decisão do dono, não de código meu. Se o dono quiser um oráculo por módulo ligado (pré-mortem "Como vamos saber"), ele nasce na frente que ligar.
- **Não confirmei quem escreve `geofence_zones` (31 linhas, model em `hr/mobile_time_clock`)** antes de propor a poda desse subpacote — fica como pergunta na matriz.

## 8. Como o Jordan testa amanhã

1. Rodar o caçador (produção, só leitura, ~40 s):
   ```bash
   docker cp /opt/conecta-pro/backend/scripts/qa/checar_modulo_morto.py conecta-pro-backend:/tmp/ && \
   docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /tmp/checar_modulo_morto.py --todos
   ```
   Esperado: `TOTAL módulos mortos: 4 — document_kits, fase5, lgpd, services`, e a linha de `hr` com `uso 11`.
2. Ver o 404 do painel: abrir `https://erp.conectamais.pro/dashboard` com a aba Rede do navegador → duas linhas vermelhas `bidding/certificates` e `document-kits/stats`. Ou: `grep -c "document-kits/stats" /var/log/nginx/access.log`.
3. Marcar a coluna **Decisão do dono** no §2. Com isso o integrador tem, para cada módulo, a lista de quem quebra e as linhas a mexer.
4. Se quiser ver o que "ligar o bidding" significa: `git show 1ccb469a9 --stat` (1.877 linhas apagadas) e `auditoria/qa/revisao_20260908/bidding.md` (os 14 defeitos).

## 9. Riscos residuais do pré-mortem que continuam

- **9.1 (montar sem `app.routes`):** continua possível para quem ligar — o caçador agora acusa o inverso (código sem rota), não rota sem código. Quem ligar prova com `app.routes`, como o contrato §4 manda.
- **9.2 (schema de outra época):** confirmado e quantificado — 5 colunas no bidding, 5 tabelas + 14 colunas no health, 7 tabelas no retention, 2 no scheduler, 1 no document_kits. Nada foi criado.
- **9.3 (rota sem auth):** não é do bidding (97/97 com auth). O grep por `Depends(get_current_active_user)` literal dá **falso negativo** nesta casa porque o padrão é `CurrentActiveUser` (Annotated) — quem auditar auth por grep vai concluir "0 com auth" e estará errado. Vale um caçador próprio; não é desta frente.
- **9.4 (ressuscitar o que deve morrer):** é exatamente o que a matriz tenta evitar. Risco novo: o `include` do Celery ainda carrega `modules.bidding.tasks` e `modules.health_occupational.tasks` em todo worker — se alguém enfileirar uma dessas tasks por nome, ela roda contra seed/tabela inexistente. Some quando o integrador tirar as duas linhas.
- **9.5 (`checar_nao_vigiado` cresce):** não cresceu — nenhuma tela nasceu. As 10+9+4+4+3 telas do redesign de licitações/saúde/serviços/documentos/agendador **já existem** e leem tabelas por SQL; as de licitações leem seed. Se o bidding for aposentado, `licitacoes.json` vira tela de tabela vazia — decisão do dono se some junto.
- **0.3 (`docker cp` não publica):** o caçador está só no git e no `/tmp` do staging. Entra na imagem no próximo bake; até lá `checar_oraculos_no_container` vai acusar 1 instrumento fora do container — esperado.
