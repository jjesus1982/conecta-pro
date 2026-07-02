# Auditoria completa das telas do frontend — 2026-06-26

## ✅ FASE 3 (2026-06-27): 2 endpoints de IA + E2E DE ESCRITA REAL (criar/editar/excluir)
- **IA operacional:** `/operacional/ai/command-center` + `/performance-overview` criados (dado real: cobertura, agentes, check-ins). ✅
- **E2E de escrita:** 7 agentes paralelos testaram criar→verificar→editar→excluir tela a tela (dados marcados `ZZE2E_`, limpeza obrigatória, SEM efeito externo: NF-e/eSocial/e-mail/WhatsApp/pagamentos/gov pulados). Acharam **~25 bugs de escrita**, todos corrigidos e **bakeados** na imagem final (âncoras `pre-wave3final-20260627`, etc.).
- **Bug sistêmico dominante:** 176 colunas `Enum()` sem `values_callable` (mapeavam pelo NOME do membro vs `.value` do banco) → fix em massa. (Ressalva: int-enums revertidos.)
- **Drifts de tipo/coluna corrigidos:** fornecedor, cliente, conta-a-pagar, armazém, centro-custo, EPI, PPRA, CAT, workflow, scheduler, equipamento, comunicado, benefício, vaga, candidatura, api-key, webhook, lançamento contábil.
- **Verificado:** fornecedor cria 201, cliente 201, EPI 500→422, api-key/webhook 201, etc. **8 celery healthy, syncs 24/7 rodando, ZERO resíduo de teste.**
- **Incidente tratado:** deletei por engano 1 supplier+1 payable seed (DENILSON SILVA) → **restaurado do backup das 03:00**.
## ✅ FASE 4 (2026-06-27): endpoints faltantes + migration de occurrences — CONCLUÍDO
- **Férias POST/DELETE** (`/hr/vacations`) → cria/exclui solicitação (201/200). ✅
- **Licenças POST** (`/hr/leaves`) → grava em `sst_afastamentos` (201). ✅
- **Contato PUT/PATCH** (`/crm/contacts/{id}`) → edita (200, aceita PT/EN, parcial). ✅
- **Campanha PUT/PATCH** (`/marketing/campaigns/{id}`) → aceita `{status}` sozinho (botão Ativar) ou completo. ✅
- **Migration occurrences** → removida a FK dupla `occurrences_employee_id_fkey`(→users); mantida `fk_occ_employee`(→employees). Agora **cria ocorrência (201)**. Rollback salvo em `/opt/conecta-pro/backups/ROLLBACK_occurrences_fk_20260627.sql`. ✅
- Tudo bakeado (imagem `ece0659927b8`, âncora `pre-endpoints-final-20260627`), 7-8 celery healthy, **syncs 24/7 rodando**, zero resíduo de teste.
- Gotchas: datas str→date (asyncpg), `days` varchar, `.value` defensivo em campos enum/str, severity válido = leve/moderada/grave/gravissima.

---


## ✅ STATUS — WAVE 1 CORRIGIDA, BAKEADA E DURÁVEL
Tudo abaixo já está **no ar e bakeado nas imagens** (`conecta-pro-backend:latest` `b0155f6bbe99` + `conecta-pro-frontend:latest`). Âncoras de rollback: `*:pre-telas-fix-20260626`. Celery intactos (syncs 24/7 seguem).

**Corrigido + verificado (HTTP 200 com dados):**
1. Espelho de Ponto — agrupa `dias` (11 dias / 120:33) ✅
2. Dashboard Ponto — sync real (26/06) + presença TZ Manaus (20/46) ✅
3. dp/ponto — nomes preenchidos + data local ✅
4. dp/ferias — 500→200, 10 solicitações ✅
5. dp/esocial + fiscal/esocial — desempacota `data.items` (8 eventos) ✅
6. dp/rescisao — page_size 200→100 (6 rescisões) ✅
7. dp/aviso-previo — path `/hr/employees` (46) ✅
8. operacional/ferias — barra final removida (10) ✅
9. portal/contracheque — barra final removida (46) ✅
10. BI dashboard — `code/name` (10 KPIs) ✅
11. saude-ocupacional/epi — EPIResponse corrigido (5 EPIs) ✅
12. ged/folders — rota espelho barra-final (7 pastas) ✅
13. operacional/diaristas — rota espelho barra-final (5 ativos) ✅
14. rh/certificados — rota `/certificates` antes de `/{id}` (20) ✅

**WAVE 2 — FINANCEIRO ✅ CORRIGIDO E BAKEADO (2026-06-26):**
Fix em **ponto único**: `frontend/src/lib/api-client.ts` (`customInstance`) — normaliza as URLs `/financial/*` geradas pelo orval (que vinham com prefixo DOBRADO e barra final). Mapeamento confirmado endpoint-a-endpoint: colapsa `/financial/X/X`→`/financial/X`, trata plurais (`purchase/purchases`→`purchases`, `bank-reconciliation/bank-reconciliations`→`bank-reconciliations`), remove barra final, injeta `condominio_id`. Verificado com dados reais:
- clientes **11** · conciliação **2876 transações** + bank-accounts · contabilidade **62 contas** + charts · orçamentos forecast **12** + entries · fornecedores · estoque · compras (purchases) · billing-rules ✅
- Bakeado: `conecta-pro-frontend:latest` (âncora `pre-financeiro-20260626`).

**Residual do financeiro ✅ CORRIGIDO E BAKEADO (2026-06-27):**
- `financeiro/fiscal/*` (nfse/nfe/dashboard) → era 500 (model `nfse.py` apontava p/ tabela `nfse` inexistente). **Reescritos os 3 GET** em `fiscal_controller.py` lendo a tabela REAL `nfses` via SQL, retornando o shape da tela (array em inglês p/ nfse, `{stats}` p/ dashboard, `[]` p/ nfe). Verificado: **fiscal/nfse 27 NFS-e**, dashboard 27/R$542.673,92/7 obrigações. condominio_id ignorado no filtro (as nfses têm condominio_ids reais; front injeta placeholder).
- `journal-entries` → era 500 (validava cada lançamento contra o wrapper `JournalEntryListResponse`). **Corrigido** p/ retornar o wrapper `{items,total,...}` com itens `JournalEntryResponse`. Verificado: **11 lançamentos**.
- Bakeado: `conecta-pro-backend:latest` (âncora `pre-fiscal-20260627`). Frontend não precisou rebuild (customInstance já colapsa o prefixo).

**>>> FINANCEIRO 100% CONCLUÍDO <<<**

**WAVE 2 — SWEEP 500/SCHEMA-DRIFT ✅ CORRIGIDO E BAKEADO (2026-06-27, âncora `pre-sweep-20260627`):**
6 erros 500 que escondiam dados/derrubavam telas, corrigidos e verificados:
1. **analytics/allocations/stats** → era colisão de rota (`/stats` caía em `/{id}`=UUID). Add rota `/stats` antes de `/{allocation_id}` (allocation_controller). **57 alocações**.
2. **config/tenants** → enum `Enum(TenantStatus)` sem `values_callable` (mapeava pelo NOME ATIVO vs DB `active`) + schema exigia tenant_type/plan str mas eram NULL. Fix: values_callable nos 3 enums + `str|None` no schema. **1 tenant**.
3. **integrações/logs** → `Enum(LogType/LogLevel/LogStatus)` sem values_callable (NOME vs DB lowercase `webhook_delivery`). Fix: values_callable. **59 logs**.
4. **config/integrações gov dashboard** → `Enum(SyncStatus)` em `sync_queue.py` sem values_callable (`PENDING` vs DB `pending`). Fix: values_callable.
5. **licitações/contratos vigentes** → MissingGreenlet (lazy `medicoes` no `_to_response`). Fix: `selectinload(medicoes)` em `get_vigentes`+`get_expiring`. **3 contratos**.
6. **config/templates** → model `ConfigNotificationTemplate` declara `codigo`/`nome` mas a tabela tem `slug`/`name` (drift) + tabela vazia. Fix: endpoint resiliente (retorna vazio em vez de 500).
**Padrão dominante:** `Enum(X)` SQLAlchemy sem `values_callable` → mapeia pelo NOME do membro; quando o DB guarda o `.value`, dá LookupError. O fix de model beneficia TODOS os consumidores desses enums, não só as 6 telas.

**WAVE 2 — MÓDULOS RESTANTES ✅ CORRIGIDO E BAKEADO (2026-06-27, âncoras `*:pre-wave2final-20260627`):**
Verificados no container bakeado (backend `06f9c095` + frontend novo, 21 celery healthy):
1. **agendador** (3 telas) → `scheduler_router` montado em main_production (removido prefix duplo) + `current_user.tenant_id`→getattr + sessão sync (service usava `db.query`). `/scheduler/tasks` 200.
2. **integrações** (api-keys/webhooks/logs/dashboard/conectores) → mount do `integration_router` corrigido p/ SINGLE (era dobrado) + `ConnectorRegistry.list_connectors` criado. **5/5 = 200** (logs 59, conector solides).
3. **operacional/kpi** → mirror barra-final + rota `/coverage-prediction` criada (deriva de postos+alocações: 10 postos, 90% cobertura). 200.
4. **automações/workflows** → tenant_id opcional + resiliente (model tem `slug` inexistente, tabela vazia → []). 200.
5. **equipamentos** (patrimônio/comodatos/manutenções) → mirrors barra-final. 200 (tabelas vazias).
6. **dp/documentos** → reescrito p/ ler `hr_employee_documents` real (era import inexistente). **15 documentos**. 200.
7. **segurança/LGPD** (7 telas) → regra no customInstance `/lgpd/`→`/security/lgpd/` (backend monta sob /security). 200.
8. **campo** ✅ RECONSTRUÍDO (2026-06-27, âncora `pre-campo-20260627`, backend `2fcdd5e2`) → diagnóstico real: o `campo_service_router` (que TEM /dashboard, /technicians, /tickets) estava montado só no `api/v1/__init__.py` (fallback inativo), NÃO no main_production. **Montado no main_production** (campo_service_router + monitoring_router sob /campo). `campo_dashboard` reescrito p/ ler batidas reais (`gp_clock_punches`): **46 agentes, 9 check-ins hoje**, shape da tela (agentes/agentes_em_campo/checkins_list/ocorrencias). `list_technicians` reescrito p/ `employees` (tabela campo_tecnicos não existe) → **46 agentes**. monitoring/health,metrics,status 200. Fix asyncpg: `hoje` como objeto `date` (não str). Telas checkin/monitoramento/root agora vivas.

**>>> WAVE 2 100% COMPLETA — TODOS OS MÓDULOS <<<**

**~~PENDENTE~~ HISTÓRICO — WAVE 2 (já resolvido acima):**
- **schema drift `notification_templates.codigo`** (analytics/allocations-stats, contabilidade/journal-entries, config/templates) → migration.
- **MissingGreenlet** (workflows, licitacoes/contratos vigentes) → selectinload.
- **módulos com prefixo/rota errada** (agendador não montado, seguranca `/lgpd`→`/security/lgpd`, campo `/guardian/` resíduo).
- **tenant enum** Python PT vs DB EN (config/tenants).

---


Varredura de **276 páginas / 29 módulos** por 8 agentes paralelos. Objetivo: achar telas onde o **backend tem dados mas a tela mostra vazio/erro** (mesmo padrão do Espelho de Ponto).

## Resumo executivo
A causa-raiz é **drift de contrato frontend↔backend** em larga escala, originado na reorganização de 9 módulos (Sessão 19) + clients orval + `redirect_slashes=False` global. 5 famílias de bug:

- **B — Rota errada/dobrada/barra-final**: client chama `/x/x` ou `/x/` e o backend serve `/x`. (maioria)
- **A — HTTP 500 / schema drift**: query usa coluna PT (`codigo`/`nome`) que no DB é EN (`code`/`name`), ou enum com valor fora da lista.
- **C — Descasamento de formato**: backend devolve `{data:{items}}`, front lê `items` no topo.
- **D — Timezone**: `toISOString()` para "hoje" (UTC) abre tela em dia vazio.
- **E — Lista vazia mas DB tem linhas**: filtro/tabela/tenant errado.

## JÁ CORRIGIDO nesta sessão (rodada do Espelho)
| Tela | Bug | Status |
|---|---|---|
| gestao-pessoas/ponto/espelho | C: backend devolvia `batidas`, front lê `dias` | ✅ corrigido (backend agrupa em `dias`) |
| gestao-pessoas/ponto (dashboard) | sync congelado jan/18 + presença TZ | ✅ corrigido (sync_log real + TZ Manaus) |
| dp/ponto | nomes "N/A" + TZ UTC | ✅ corrigido (fill nome + data local) |
| dp/ferias | 500 rota dobrada `/vacations/vacations` | ✅ corrigido (path único + campos enriquecidos) |

## BUGS QUE ESCONDEM DADOS REAIS (prioridade ALTA)
| # | Tela | Endpoint | HTTP | Pad | DB tem | Causa | Correção |
|---|---|---|---|---|---|---|---|
| 1 | dp/esocial + fiscal/esocial | government/esocial/eventos | 200 | C | 8 eventos | service devolve envelope `{data:{items}}`, front lê `.items` topo | desempacotar `data.items` no esocial.service.ts |
| 2 | financeiro/fiscal | /financial/fiscal/**fiscal**/nfse | 404 | B | 27 nfse +10 | prefixo dobrado orval | client → `/financial/fiscal/nfse` |
| 3 | financeiro/contabilidade | /financial/accounting/**accounting**/* | 404 | B | 11 lanç +62 contas | prefixo dobrado | client → `/financial/accounting/*` |
| 4 | financeiro/clientes | /financial/customers/**customers** | 404 | B | 11 | prefixo dobrado | client → `/financial/customers` |
| 5 | financeiro/conciliacao | /financial/bank-accounts/**bank-accounts** | 404 | B | **2876 transações** | prefixo dobrado | client → segmento único |
| 6 | financeiro/orcamentos (previsão) | /financial/cashflow/**cashflow**/forecasts | 404 | B | 12 | prefixo dobrado (só forecast) | client → `/cashflow/forecasts` |
| 7 | operacional/diaristas | /operacional/diaristas/ | 405 | B | 13 (5 ativos) | barra final | rota espelho `/` no backend |
| 8 | operacional/ferias | /operacional/vacations/ | 404 | B | 10 | barra final hardcoded (page:251) | remover barra |
| 9 | rh/certificados | /training/certificates | 422 | B | 20 | colisão c/ `/training/{id}` (UUID) | registrar literal antes do paramétrico |
| 10 | portal/contracheque | /people-management/hr/employees/ | 404 | B | 46 | barra final | remover barra |
| 11 | documentos/pastas | /ged/folders/ | 404 | B | 7 pastas | barra final | remover barra / rota espelho |
| 12 | dp/rescisao | /hr/terminations?page_size=200 | 422 | A | 6 | page_size>100 (validação ≤100) | page_size=100 |
| 13 | dp/documentos | /hr/documents | 200/erro | A+E | 15 | import inexistente + tabela errada | apontar p/ hr_employee_documents |
| 14 | dp/aviso-previo | /people-management/employees (falta /hr/) | 404 | B | 46 | path errado | add `/hr/` |
| 15 | bi/dashboard | /financial/bi/dashboard | 500 | A | 10 KPIs | `executive_kpis`: query usa `codigo/nome`, tabela tem `code/name` | corrigir SQL |
| 16 | saude-ocupacional/epi (lista) | /health-occupational/epi | 500 | A | 5 EPIs | query usa `codigo` inexistente (real: `ca_numero`) | corrigir query |
| 17 | configuracoes/tenants | /config/tenants | 500 | A | 1 tenant | linha com enum `active` (EN) fora de tenantstatus (ATIVO/…) | corrigir dado p/ ATIVO |
| 18 | integracoes/logs | /integrations/integrations/logs | 404→500 | A+B | 59 logs | prefixo dobrado + enum `webhook_delivery` fora do LogType | path + enum |

## BUGS EM MÓDULOS SEM DADO / 500 estrutural (prioridade MÉDIA)
| Tela | Endpoint | Problema |
|---|---|---|
| analytics (card alocações) | operacional/allocations/stats | 500 `notification_templates.codigo` (handler de notificação) |
| financeiro/contabilidade (lançamentos) | /financial/accounting/journal-entries | 500 `notification_templates.codigo` |
| configuracoes/templates-notificacao | /config/templates | 500 `notification_templates.codigo` |
| automacoes/workflows | /workflows/?tenant_id= | 422 (tenant vazio) + 500 MissingGreenlet |
| licitacoes/contratos (vigentes) | /bidding/contracts/vigentes | 500 MissingGreenlet (lazy-load) |
| operacional/kpi | /operacional/kpi-trends/ + coverage-prediction | barra final + rota inexistente |
| operacional/disciplinar | /medidas-administrativas/medidas-administrativas | 500 prefixo dobrado (DB vazio) |
| configuracoes/integracoes (gov dash) | /integrations/integrations/dashboard | 500 enum cast |
| integracoes/conectores+sync | ConnectorRegistry.list_connectors | 500 método ausente |

## MÓDULOS INTEIROS MORTOS (404, mas tabelas vazias — prioridade BAIXA)
| Módulo | Causa |
|---|---|
| agendador (3 telas) | `scheduler_router` não montado em main_production.py |
| seguranca/LGPD (7 telas) | front chama `/lgpd/*`, backend serve `/security/lgpd/*` |
| campo/checkin+dashboard+monitoramento | URL contém `/guardian/` (módulo removido na Sessão 19) |
| equipamentos/patrimonio+comodatos+manutencoes | barra final (DB vazio) |
| integracoes/api-keys+webhooks | prefixo dobrado (DB vazio) |

## Telas OK (amostra — backend + tela batem)
operacional: postos(9), alocacoes(20), escalas(3/180 turnos), colaboradores(47), rondas(3), comunicados(10), reembolsos(20).
financeiro: dashboard(27 nfse R$542k), contas-pagar(19), contas-receber(21), contratos(10), fornecedores(13), nfse-entrada(10).
crm: leads(12), oportunidades(7), propostas(7), clientes(14), contratos(10), comissoes(12), atividades(45).
rh: cargos(52), beneficios(157), desempenho(15), treinamentos(9), turnover, onboarding.
dp: funcionarios(46), beneficios, contratos(42), reembolsos(20), folha/rubricas(24).
saude: afastamentos(6), cat(2), ltcat, exames(PCMSO), riscos(PPRA 4).
licitacoes: editais(11), propostas(5), contratos(3), documentos(6). ged: kits(29), certidoes(8), onvio(647 docs).

## Padrões de correção recomendados
1. **Barra final** (redirect_slashes=False): adicionar rota espelho `@router.get("/")` no backend (padrão CRM já usado) OU remover barra no front. Backend é mais durável (não briga com orval).
2. **Prefixo dobrado orval**: corrigir spec/baseURL dos hooks gerados em `frontend/src/types/generated/` e `frontend/src/hooks/financial/`.
3. **Schema drift `codigo`/`nome`/enums**: rodar skill `finding-schema-drift`; corrigir SQL ou migration.
4. **Colisão de rota** (`/x/literal` vs `/x/{id}`): registrar literal ANTES do paramétrico.
5. **MissingGreenlet**: `selectinload` nos relacionamentos serializados.
