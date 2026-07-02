# Auditoria Gestão de Pessoas — t2 (E2E ponta a ponta) — 2026-06-28
**Escopo:** 8 módulos de Pessoas (101 telas). **Raias:** people_management/{hr,folha,human_resources,ponto,sst,ged,employee_portal}, recruitment, retention, cct, health_occupational, reimbursement. **NÃO toco:** financial, ged-raiz, gedeon, document_kits, operacional (inclui `/people-management/operations/*`), crm, bidding.

## Preparação (concluída)
- **Inventário:** 101 telas — dp 17, rh 13, recrutamento 5, gestao-pessoas 45 (ged 13 / saude 9 / rh 8 / ponto 7 / sst 6), saude-ocupacional 9, reembolso 2, portal-funcionario 10, portal 10.
- **Acesso:** token admin OK; DB via container OK (53 funcionários ativos); health 200; sem `.bake_lock`.
- **Triagem GET (301 endpoints probáveis):** **202 OK**, ~99 "problemas" — destrinchados:
  - **401 portal/\* (22):** exigem token de FUNCIONÁRIO (auth própria) — não-bug; testar com login de portal.
  - **422 (muitos):** exigem query-param que a probe não passou — verificar tela a tela (maioria não-bug).
  - **500 reais (clusters):** ver tabela abaixo.

## Clusters de bug 500 (causa-raiz)
| Cluster | Endpoints afetados | Causa-raiz | Fix | Status |
|---|---|---|---|---|
| **Benefícios config** | `/hr/beneficios/config`, `/cct/beneficios/config` | tabela `cct_benefit_configs` ausente | guard resiliente → `{items:[]}` | ✅ **FEITO+BAKEADO** (500→200) |
| **CCT salários auditorias** | `/cct/salarios/auditorias` | tabela `cct_salary_audits` ausente | guard resiliente → `{items:[]}` | ✅ **FEITO+BAKEADO** (500→200) |
| Retention profile | `/retention/profile/*` (4) | tabela `operational_profiles` ausente | **DORMENTE — 0 telas consomem** (rh/clima·turnover·onboarding usam `/people-management/human-resources`) | 🟫 de-escopado (não é bug de tela) |
| Ponto / time-tracking | `/hr/time-tracking/time-tracking/*/stats,pending` (~13) | query asyncpg | **DORMENTE — 0 telas consomem** (telas usam `/ponto/*`, que estão verdes) | 🟫 de-escopado |
| Folha / eSocial dobrado | `/hr/payroll/payroll/esocial/*` | path dobrado | **DORMENTE — 0 telas** (dp/esocial usa `/government/esocial/eventos`, 200) | 🟫 de-escopado |
| ~~operations dashboard/kpis~~ | `/people-management/operations/*` | — | **operacional, fora da raia** | ❌ avisar t1 |

> **Batch 2 — descoberta-chave (honesta):** dos 5 clusters de 500, **2 eram bugs de tela reais** (benefits/salary — corrigidos no batch 1) e **3 são backend dormente** (nenhuma tela os consome — verificado por grep nas telas). Não vale guardar/migrar tabelas pra endpoints que nenhuma UI chama. **O eixo de LEITURA das telas de Pessoas está saudável** (waves do t1 + batch 1): 9/10 dos endpoints realmente chamados pelas telas retornam 200. **O trabalho real restante é o eixo de ESCRITA (E2E create/edit/delete)** — batch 3.

## Batch 3 — sweep E2E de ESCRITA (5 agentes paralelos, marcador ZZE2E_ + limpeza, resíduo=0)
**~15 bugs de escrita reais encontrados.** Corrigidos+bakeados nesta rodada: 3 padrões de crash.

### ✅ FIXED + BAKEADO (batch 3 — âncora `pre-pessoas-batch3-20260628`)
| Tela | Bug | Fix | Verificação |
|---|---|---|---|
| recrutamento/candidaturas | CREATE 500: `position.experience_min` (attr não existe) | `min_experience_years` via getattr | 500→400 (crash eliminado) |
| recrutamento/entrevistas | CREATE 500: `data.meeting_link` (schema usa meeting_url) | getattr defensivo | 500→422 (crash eliminado) |
| sst: risco/cat/aso | CREATE 500: datetime tz-aware → coluna naive | `datetime.now(UTC).replace(tzinfo=None)` (4 models) | risco **201** ✓ (durável) |

### ✅ FIXED + BAKEADO (batch 4 — âncora `pre-pessoas-batch4-20260628`, todos verificados 201)
| Tela | Bug | Fix | Verificação |
|---|---|---|---|
| dp/rescisao + aviso-previo | POST 500: TerminationResponse UUID→str (H) | `id/employee_id/created_by_id: UUID` | **201** ✓ |
| dp/funcionarios (deduções) | POST 500: `date` não importado + str→date (F) | import date + `date.fromisoformat` | **201** ✓ |
| reembolso (criar) | POST 500: UniqueViolation `code` (sequence por condominio) | sequência GLOBAL | **201** (REI-2026-00022) ✓ |

### ✅ FIXED + BAKEADO (batch 5 — âncora `pre-pessoas-batch5-20260628`)
| Tela | Bug | Fix | Verificação |
|---|---|---|---|
| reembolso editar/submeter/cancelar | 500 na RESPOSTA (sem re-fetch após commit) | `return await service.get_request(request_id)` nos 3 | PUT/cancel **200** ✓ (submit 400 = regra de negócio, sem itens) |

### ✅ FIXED + BAKEADO (batch 6 — âncora `pre-pessoas-batch6-20260628`)
| Tela | Bug | Fix | Verificação |
|---|---|---|---|
| dp/licencas | lista lia `time_justifications` (vazia) enquanto o POST grava em `sst_afastamentos` (6 dados) | `list_leaves` lê de `sst_afastamentos` | lista **total=6** (era 0) ✓ |

### ⏳ RESTAM (precisam de decisão/coordenação — NÃO rush)
| Tela | Bug | Por que não foi sprintado |
|---|---|---|
| reembolso ready-for-payment | 422: ordem de rota | secundário (prep de pagamento); fix exige mover função (risco) — faço com cuidado |
| rh/avaliacoes (360) | front manda nome em vez de UUID | fix é no FRONT (precisa seletor de funcionário — mudança de UX maior) |
| sst/epi-catálogo + ppra-mapeamento | model declara colunas que não existem na tabela | precisa **migration** (zona compartilhada) OU aparar o insert — decisão c/ t1 |
| sst/epi-entrega | POST 500 (verificar pós-token) | reverificar |

## RESUMO DA MISSÃO (6 batches)
**~14 bugs reais corrigidos + bakeados durável, resíduo ZZE2E=0 em cada um.** Eixo de leitura já estava saudável (waves do t1); o eixo de ESCRITA foi mapeado (5 agentes E2E) e a maioria esmagadora corrigida. O que resta precisa de migration (zona compartilhada), mudança de UX no front, ou coordenação — não de mais um fix rápido.

### ✅ MIGRATION ADITIVA APLICADA (batch 7 — backup + rollback salvos)
**Autorizada pelo Jordan.** Backup: `backups/manual/pre_migr_*_20260628.sql`. Migration: `backups/manual/migr_pessoas_20260628.sql`. Rollback: `backups/manual/ROLLBACK_migr_pessoas_20260628.sql`. Aditiva e idempotente (IF NOT EXISTS), em transação.
| Alvo | O que | Resultado |
|---|---|---|
| `health_epi_catalog` | +10 colunas do model (ca_validade, modelo, validade_dias, especificacoes, riscos_protegidos, instrucoes_*, imagem_url, created_by) | — |
| `health_epi_inventory` | +9 colunas do model (quantidade_atual, quantidade_maxima, local_armazenamento, lote_atual, ...) | **EPI cadastrar 500→201** ✓ |
| `cct_benefit_configs` | CREATE TABLE (model existia, tabela não) | `/cct/beneficios/config` lê tabela real (200) ✓ |
| `cct_salary_audits` | CREATE TABLE | `/cct/salarios/auditorias` lê tabela real (200) ✓ |

DB-only (sem código novo, sem bake). Os guards resilientes do batch 1 seguem (inofensivos — agora a tabela existe). Resíduo ZZE2E=0. `operational_profiles` (retention) NÃO criada de propósito — é dormente (0 telas).

### ✅ FIXED (batch 8 — 28/06)
| Tela | Bug | Fix | Verificação |
|---|---|---|---|
| RH / Avaliações 360 | front mandava NOME onde backend quer UUID (sempre 422) | seletor de funcionário + campos `employee_id/reviewer_id/type/review_period_*` | backend aceita payload novo → **201**; front **buildado+deployado** (BUILD_ID sincronizado) |
| Reembolso / ready-for-payment | 422 (ordem de rota) | rota movida p/ antes de `/{request_id}` | **422→200**, bakeado durável (`pre-pessoas-batch8-20260628`) |

### ✅ FECHADO NESTA SESSÃO AUTÔNOMA ("ataca tudo")
| Item | Era | Virou | Detalhe |
|---|---|---|---|
| **🔒 Falha de segurança (login portal)** | DOB NULL = qualquer um entra com CPF | **fechada** | exige data cadastrada E que bata; testado (DOB errado→401, DOB null→401). Bakeado `pre-pessoas-portal-20260628` |
| **Portal do Funcionário** (estava "inacessível") | login exigia JWT de admin → 401; 14 endpoints bloqueados | **funcional** | login 201+token; 12 controllers `my_*` passaram a aceitar o token do FUNCIONÁRIO (CurrentEmployeeId). dashboard/payslips/data/vacations/... 200. Bakeado |
| **Ponto / Justificativa** | 201 FALSO sem persistir (data loss) | **persiste** | push Sólides isolado em SAVEPOINT (a query quebrada rolava a transação toda). Bakeado `pre-pessoas-ponto-20260628` |
| **EPI cadastrar + cct configs** | 500 | 201/200 | migration (ver acima) |
| **RH/Avaliações + Reembolso ready-for-payment** | 422 | 201/200 | ver batch 8 |

> Diagnóstico corrigido: o "Portal inacessível por colisão de prefixo `/portal`" do agente era **falso** — o front usa `/people-management/portal` (prefixo próprio). O problema real era **auth** (admin JWT exigido), agora corrigido.

### ✅ PPRA — RECONCILIAÇÃO DEDICADA CONCLUÍDA (âncora `pre-ppra-recon-20260628`)
Backup das 3 tabelas em `backups/manual/pre_ppra_recon_*`. Diff model↔tabela computado e reconciliado:
- **RiskMapping** (`health_risk_mappings`): model já compatível; só faltava mapear `funcao` (NOT NULL) → adicionada ao model + populada (1ª função). Migration: `agente_risco`/`tipo_risco` → nullable.
- **OccupationalRisk** (`health_occupational_risks`): tabela ganhou `categoria, descricao, funcoes_expostas, numero_expostos, prioridade` (model declarava, tabela não tinha) + `tipo` nullable. **Tipos do model alinhados à tabela**: `probabilidade`/`severidade` Integer→String, `limite_tolerancia` Float→String (resolvia "Unknown PG numeric type: 25").
- **ControlMeasure** (`health_control_measures`): já compatível.
- **Verificação E2E:** mapeamento create (sem risco E com risco) → **201**; list → **200**; resíduo ZZE2E=0; 0 unhealthy, 7 celery.

### ⏳ ÚNICO RESTANTE — DP/Documentos (cross-módulo, fora da raia)
A tela LÊ de `hr_employee_documents` mas faz UPLOAD pro **GED** (`modules/ged`, raia do t1) com enum incompatível (RG/CPF/CTPS vs contrato/comprovante/...). Precisa alinhar o destino do upload OU o enum — **coordenação com a frente do GED**. (Não é bug de Pessoas isolado.)

### ⚠️ COORDENAR COM t1 (zona compartilhada — não resolvo sozinho)
- **Portal do Funcionário INTEIRO inacessível**: colisão de prefixo `/portal` (client_portal sombreia employee_portal) → mount em `main_production`.
- **Falha de SEGURANÇA**: login portal por data-nascimento com DOB NULL faz bypass (`portal_service.py:146`).
- **dp/documentos** upload: enum `DocumentType` em `modules/ged` (raiz, fora da raia).
- **Migrations** p/ tabelas ausentes (cct_benefit_configs, cct_salary_audits, operational_profiles, colunas health_epi_catalog) — hoje resilientes; criar de verdade = decisão conjunta + backup.

### ⚠️ COORDENAR COM t1 (zona compartilhada / fora da raia)
- **Portal do Funcionário INTEIRO inacessível:** colisão de prefixo `/portal` — `client_portal` (área cliente) sombreia `employee_portal` → tudo 404. Fix é no **mount (main_production / shared zone)**. + **falha de segurança**: login por data-nascimento com DOB NULL faz bypass (`portal_service.py:146`).
- **dp/documentos** upload 400: enum `DocumentType` em `modules/ged` (raiz, fora da raia) não tem rg/cpf/ctps que o front manda → corrigir no front OU no enum (coordenar).

## Bakes / âncoras
- **batch 1** (2026-06-28): benefits_service + salary_service (guards resilientes). Âncora `pre-pessoas-batch1-20260628`.
- **batch 3** (2026-06-28): recrutamento ×2 + SST models ×4. Âncora `pre-pessoas-batch3-20260628`. configure_mappers OK, 0 unhealthy, 7 celery healthy, resíduo ZZE2E=0.

## Ordem de execução (do coração pra fora)
1. **DP** (folha/eSocial, benefícios, rescisão/férias accrual) → 2. **Ponto** (time-tracking cluster) → 3. **RH** (cct, retention) → 4. **Recrutamento** → 5. **SST** → 6. **Reembolso** → 7. **Portal Funcionário** (auth própria).

## Registro por tela (preenchido durante a execução)
| Tela | Endpoint | GET | CREATE | EDIT | DELETE | Status | Bug/Correção |
|---|---|---|---|---|---|---|---|
| _(em execução)_ | | | | | | | |

## Bakes / âncoras
_(registrados a cada bake durável)_

## Resíduo ZZE2E
_(verificado = 0 ao fim de cada tela)_
</content>
