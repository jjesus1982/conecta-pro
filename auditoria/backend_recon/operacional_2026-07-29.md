# Backend Recon — Operacional (2026-07-29)

Objetivo: garantir que o **redesign** cobre tudo que o **backend** codou, sem recodar o que já existe.
Fluxo Jordan: `/conecta-backend-recon` → `/graphify` → `/writing-plans` → `/ponytail`.

## Números (READ-ONLY, rotas montadas em `main_production:app`)
- **304 rotas** montadas com prefixo `operacional`.
- Superfície **all** (clássico+redesign): **296 expostas · 8 órfãs de verdade**.
- Superfície **redesign** (oráculo do progresso): **184 expostas · 120 órfãs**.
- **Geradores de documento órfãos: 0** (nenhum PDF/XML sem botão em ambas as superfícies) ✅

## Gap de paridade (o que falta no redesign p/ desligar o clássico)
~**112 rotas** o clássico cobre e o redesign não (120 − 8). Ressalva: parte é **falso-órfã**
(builders leem o banco direto por SQL → cobrem GET sem citar a rota). Gap **acionável** = escrita/ação.

### 120 órfãs redesign por método
| Método | Qtd |
|---|---|
| GET | 60 (muitos falso-órfãos via builder-SQL) |
| POST | 47 |
| PATCH | 7 |
| DELETE | 5 |
| PUT | 1 |
→ **~60 rotas de escrita/ação** = o núcleo do gap acionável.

### Por subsistema (órfãs redesign)
| Subsistema | Órfãs | Natureza |
|---|---|---|
| diaristas | 20 | day-workers: assignments, evaluations, fiscal/RPA, payments/payroll, statistics, activate |
| medidas-administrativas | 13 | disciplinar: CRUD + IA (recomendar/validar/proporcionalidade) + assinar/submeter/gerar-doc |
| rondas | 12 | patrulha: checkpoints CRUD+fotos, iniciar/pausar/retomar, registrar-ocorrência, medida-disciplinar |
| time-bank | 10 | banco de horas: CRUD + compensate/expiring/summary/recommendations |
| allocations | 9 | ⚠️ CURADO À MÃO por Jordan — READ-ONLY p/ agentes; só reportar |
| scales | 8 | escalas: CRUD + auto-generate + templates |
| unificado | 6 | alocar/desalocar diarista, kpi-trends, métricas, resumo-dia, sugerir-diarista |
| kpi-trends | 5 | tendências/coverage-prediction/performance-scores |
| comunicacao + comunicados | 8 | acknowledge, não-lidos, leituras, publicar, marcar-todas |
| shifts | 3 | bulk PATCH, scale/{id}, mark-missed |
| instrucoes-posto | 3 | GET/PUT instruções do posto |
| consultor | 3 | panorama, perguntar, perguntar-arquivo (consultor operacional IA) |
| scale-optimizer | 2 | otimizar / otimizar-mes |
| reports | 2 | costs / coverage |
| passagem-turno | 2 | POST/GET passagem de turno |
| diarias | 2 | resumo-diarista / resumo-gerencial |
| ai | 2 | command-center / performance-overview (clássico tem página, redesign não) |
| outros | substitutions, scale-templates, presenca/checkin-manual, posts/definir-localizacao, occurrences/by-post, notificacoes/marcar-todas, grade, banco-horas, assinaturas/verificar, alertas/acknowledge |

## 8 rotas VERDADEIRAMENTE órfãs (nem clássico nem redesign chamam)
Candidatas a integração interna / capacidade nunca ligada. **Verificar à mão antes de qualquer ação.**
```
GET   /api/v1/operacional/diarias/resumo-gerencial
POST  /api/v1/operacional/diaristas/fiscal/rpa
GET   /api/v1/operacional/rondas/gestao/resumo-inspetores
POST  /api/v1/operacional/scale-optimizer/otimizar-mes
GET   /api/v1/operacional/scale-templates/
POST  /api/v1/operacional/unificado/alocar-diarista
POST  /api/v1/operacional/unificado/desalocar-diarista/{assignment_id}
GET   /api/v1/operacional/unificado/sugerir-diarista/{post_id}
```

## Próximos passos (fluxo)
1. ✅ Skill 1 recon — este relatório.
2. ⏳ Skill 2 `/graphify` — grafo do operacional (backend+builders+front) p/ mapear o que cada órfã acionável
   representa e o que a suporta, sem recriar. Distinguir falso-órfã (GET coberto por builder-SQL) de gap real.
3. ⏳ Skill 3 `/writing-plans` — plano só do gap real.
4. ⏳ Skill 4 `/ponytail` — codar só o que falta.

Arquivos brutos: `operacional_redesign_20260729.txt`, `operacional_all_20260729.txt`.

---

## Skill 2 (/graphify) — grafo + síntese de cobertura REAL (2026-07-29)

Grafo do backend operacional: **4617 nós, 9977 edges, 171 comunidades** (só-código/AST + 1 doc).
Saídas: `backend/modules/operacional/graphify-out/{graph.html,GRAPH_REPORT.md,graph.json}`.
Health: 1060 dangling / 504 collapsed = chamadas a outros módulos (fronteira do módulo), não corrupção.

### Correção da recon: o gap era SUPERcontado
O redesign cobre escrita via **action-gate**: o front chama `/redesign/action/<slug>` e o
`redesign_data_controller.py` **importa+chama a função do subsistema internamente** (não a rota HTTP).
A recon (token-match de `/api/v1/operacional/...` no front) **não vê** essas ações → falso-órfãs.

Slugs de escrita JÁ no redesign: client-note, custeio-cct, diaria, diarista, epi-delivery, falta,
ferias-calc, job-position, justificativa-ponto, lead, occurrence, occurrence-comment, occurrence-resolve,
opportunity-stage, payable, proposal, receivable, reembolso, rescisao-calc, simular-preco,
substituir-diarista, task, vacation-request.

**COBERTO no redesign (não é gap):** occurrences (CRUD+resolve), presence, diaristas (diária/substituir),
falta/substituto, avaliações (rh.py lê operacional_avaliacoes_equipe), férias.

### GAPS REAIS (backend codou, clássico expõe, redesign ZERO/parcial) — verificado por import
| Subsistema | Pacote backend | Rotas | Redesign hoje | Trabalho |
|---|---|---|---|---|
| medidas-administrativas | `disciplinary/` | 13 | ZERO | CRUD+IA(recomendar/validar/proporc.)+assinar/submeter/recusar+gerar-doc |
| rondas | `inspection_rounds/` | 12 | só link PDF | checkpoints+fotos, iniciar/pausar/retomar, registrar-ocorrência, medida-disc. |
| banco-horas | `time_bank/` | 10 | leitura parcial | CRUD + compensate/expiring/summary/recommendations |
| passagem-turno | `shift_handover/` | 2 | ZERO | criar/listar |
| instrucoes-posto | `post_orders/` | 3 | ZERO | GET/PUT instruções do posto |
| consultor operacional | `consultor_coo_*` | 3 | não wired em orquestrador | panorama/perguntar (verificar se cabe no chat) |
| escalas | `scale_*` | 11 | via **Sólides (externo)** | DECISÃO Jordan: externo fica ou traz p/ redesign? |
| allocations | `allocation_*` | 9 | leitura exposta | ⚠️ CURADO À MÃO — escrita só reporto (regra intocável) |
| analytics | kpi_trends/reports/ai | ~9 | parcial | kpi-trends, reports/costs+coverage, ai command-center |

Núcleo acionável limpo (subsistemas completos, redesign sem superfície): **medidas-administrativas,
rondas (gestão), banco-horas, passagem-turno, instrucoes-posto**. Todos com service+model+repo REAIS no
backend → redesign só precisa builder (leitura) + ações via write-gate (`redesign_write_gate.py`). NÃO recodar serviço.

---

## Skill 4 (/ponytail) — PILOTO executado: medidas-administrativas FABRICADO → REAL (2026-07-29)
- ✅ Task 1: `operacional.py build()` lê `disciplinary_actions` → tela `medidas-administrativas` real (oráculo exibido==banco=5; sem "Carlos Batista"). commit.
- ✅ Task 2: `router` + `POST /api/v1/redesign/action/medida-administrativa` reusa `DisciplinaryService.create` via `op_write`; form `disciplinar`. Nome/CPF resolvidos do `employee_id` (nunca fabricado); CPF ausente=erro honesto. Teste criou `ADV-2026-00001` real (NAILSON GARCIA GOMES). commit.
- ✅ Rotas montadas (401 sem token; não 404). Dado de teste limpo (volta a 5). ⏳ bake blue-green em curso.
- RECEITA VALIDADA. Próximo: rondas gestão (inspection_rounds) pelo mesmo molde.

### Lote 2 (2026-07-29) — 3 leituras fabricadas → reais, BAKED
- ✅ banco-horas (time_bank, 0=vazio honesto), passagem-turno (operacional_passagens_turno), instrucoes-posto (operacional_post_orders×posts, 9 postos c/ situação). Oráculo combinado `scripts/orq/test_oraculo_op_leituras_redesign.py` verde. Blue-green baked.
- rondas LEITURA já era real (operacional.py lê inspection_rounds). 
- FALTA p/ 100%: ESCRITAS (rondas gestão, banco-horas lançar, passagem-turno nova, instrucoes-posto editar — via OperationalScope+gate); escalas (reconciliar Sólides); allocations (só leitura, regra intocável); consultor operacional (wire chat); analytics (kpi-trends/reports/ai-command-center).
