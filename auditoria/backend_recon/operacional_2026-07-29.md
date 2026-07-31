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

### Lote 3 (2026-07-29) — ESCRITAS via gate (reuso controllers), commitado; bake pendente (lock disputado)
- ✅ passagem-turno (create_passagem_turno), instrucao-posto (atualizar_instrucoes_posto, só gestor), banco-horas (create_entry) — via op_write + OperationalScope gestor. Forms em EXTRA_MENU (passagem-turno-nova, instrucao-posto-editar, banco-horas-lancar). Oráculo `scripts/orq/test_acao_op_escritas_redesign.py` cria+confere+limpa (net-new) — 3/3 verde. Rotas 401 montadas. Live no container (docker cp); BAKE pendente (lock ocupado por sessão paralela) → consolidar no próximo tick.
- FALTA p/ 100%: rondas GESTÃO (iniciar/pausar/checkpoints/registrar-ocorrência — multi-step), escalas (reconciliar Sólides), allocations (verificar leitura; escrita FORA), consultor operacional (chat), analytics (kpi-trends/reports/ai-command-center). + BAKE consolidado final.

### Lote 4 (2026-07-30) — Nova ronda + mapa da fila restante
- ✅ nova-ronda (InspectionRoundService.create via gate) — leitura de rondas já era real; ciclo de campo (iniciar/checkpoints/fotos) fica no mobile. commit. Oráculo `test_acao_nova_ronda_redesign.py` verde.
- ACHADO A (reportar, não corrigir cego): `inspection_rounds` code é GLOBAL-unique mas `get_next_sequence` é PER-TENANT → 2 tenants colidem code. No single-tenant real não morde; meu teste com tenant fake colidiu. Clássico tem o mesmo risco.
- ACHADO B (sharp edge do gate): `op_write` grava o marcador de idempotência ANTES do real_write e não faz rollback em falha → write que falha deixa marcador-poison bloqueando retry com mesma chave. Mitigo validando ANTES do op_write; gate merece fix separado.
- build() serve 29 screens REAIS. **Fila read-fix restante (18 ids servidos do estático, vários fabricados):**
  - Backend real claro (read-fix rápido): substituicoes, avaliacao-equipe (operacional_avaliacoes_equipe), escalas-templates (scale_template), escalas-grade (shifts×employees), triagem, diaristas-escala, diaristas-fechamento.
  - Pesados (dash/IA/campo): kpi (kpi-trends), cobertura (reports/coverage), relatorios, mapa, consultor (consultor_coo IA→chat), agentes, ai-command-center, ronda-mobile, escalas-visual.
  - allocations: `alocacoes` já servido por build (leitura); escrita FORA (regra intocável).
- Bake: sessões paralelas bakeiam com frequência (do source) → meus commits entram na imagem sem eu competir pelo lock.

### Lote 5 (2026-07-30) — 6 read-fixes com tabela real, commitado
- ✅ substituicoes(substitutions,0)/escalas-templates(scale_templates,4)/escalas-grade(shifts→53 pessoas)/avaliacao-equipe(operacional_avaliacoes_equipe,0 ativas)/diaristas-escala(diarist_schedules,0)/diaristas-fechamento(diarist_payments,0). ::text em enum/date antes de coalesce (senão PG aborta tx e polui build). Oráculo `test_oraculo_op_readfix2_redesign.py` verde.
- BALANÇO: núcleo de DADOS operacional agora real (leituras) + escritas-chave (medidas/passagem/instrucao/banco-horas/nova-ronda). Restante em 3 baldes:
  - (A) DASHBOARDS c/ backend real (doável, próximo): kpi (kpi-trends), cobertura (reports/coverage), relatorios. São type=dash (kpis/panels), mais trabalho por tela.
  - (B) IA / camada cognitiva (PROGRAMA SEPARADO Fase5/6): consultor (consultor_coo→chat), agentes, ai-command-center. Não é read-fix; é integrar o chat/consultor.
  - (C) campo/geo/sem-tabela (deferir): mapa, ronda-mobile, escalas-visual, campo (tem _build_campo próprio), triagem (SEM tabela — não fabricar).

### Lote 6 (2026-07-31) — Balde A dashboards reais, LOOP ENCERRADO
- ✅ cobertura (ReportsRepository.get_coverage → 9 postos, taxa 77,8% real), kpi (postos/ocorrências abertas/rondas mês/substituições mês), relatorios (ocorrências/medidas/passagens/colaboradores do mês). type=dash. Oráculo `test_oraculo_op_dashboards_redesign.py` 3/3.
- SWEEP regressão: 13 checagens (medidas 1 + leituras 3 + readfix2 6 + dashboards 3) todas verdes. Sem regressão.
- **SWEEP DE PARIDADE DE DADOS OPERACIONAL: CONCLUÍDO.** build() serve as telas de dados reais + escritas-chave humano-gated. Durável via source commitado (deploys paralelos bakeiam do source).
- RESTA (fora deste sweep, decisão do Jordan): Balde B IA (consultor/agentes/ai-command-center = camada cognitiva Fase 5/6, programa separado); Balde C campo/geo/sem-tabela (mapa/ronda-mobile/escalas-visual/campo/triagem-sem-tabela). Achados abertos p/ fix separado: code global-unique×sequence per-tenant (inspection_rounds); op_write poison-marker on failure.

### Lote 7 (2026-07-31) — Balde B camada cognitiva (Fase 5/6), REAL e verificado
- MEDIÇÃO (não de memória): backend cognitivo do operacional é REAL/honesto — consultor_coo panorama (fotografia real) + perguntar (LLM Hermes, "indisponível" honesto se não configurado); ai/controller command-center + performance-overview (contagens reais, risco derivado "placeholder honesto sem inventar evento").
- ✅ Reuso puro (chama funções reais no builder): ai-command-center + agentes ← command_center; consultor ← consultor_coo_service.panorama. type=dash. Oráculo `test_oraculo_op_cognitivo_redesign.py` prova exibido==função-real.
- Verificado no navegador (Playwright, login mcp-service): ai-command-center (52 efetivo, 77,8%, risco Médio), agentes (52/0/52), consultor (9 postos, 54 alocações, 77,8%, panorama completo). Screenshots op-*.png.
- DECISÕES honestas: consultor=dashboard do panorama real (perguntas analíticas seguem no CHAT interno onde vive o perguntar/LLM); agentes=situação do efetivo (agentes de portaria), não roster de IA (não há backend honesto p/ isso, não fabriquei).
- SWEEP total: 16 checagens (6 oráculos) verdes, zero regressão.
- **BALDES A+B CONCLUÍDOS.** Resta só balde C (campo/geo/sem-tabela: mapa/ronda-mobile/escalas-visual/triagem-sem-tabela) — deferido.
