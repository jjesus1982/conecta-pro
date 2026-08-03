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

### Lote 8 (2026-07-31) — Balde C real, SWEEP OPERACIONAL COMPLETO
- MEDIÇÃO: todas as 5 tinham backend real — mapa (posts latitude/longitude, 8/9), ronda-mobile (inspection_rounds em andamento), escalas-visual (scales, 19), campo (visitas, 2), triagem (triage_controller sub-funções _ocorrencias/_escalas/_avaliacoes_semana derivam de tabelas reais — NÃO era casca sem-tabela como eu temia).
- ✅ 5 telas reais (mapa/ronda-mobile/escalas-visual/campo=tabela; triagem=dash derivado). ::text em enums. Oráculo `test_oraculo_op_baldeC_redesign.py` 5/5.
- Verificado navegador: mapa (8/9 georreferenciados, coords GPS reais Manaus; Conecta Base "sem localização" honesto), triagem (0 occ / 1 sem escala / 10 rascunhos). Screenshots op-mapa/op-*.png.
- **SWEEP TOTAL: 21 checagens (7 oráculos) verdes, zero regressão. BALDES A+B+C CONCLUÍDOS.** Módulo operacional do redesign: dados reais + escritas humano-gated + dashboards + cognitivo + campo/geo/triagem — tudo ligado, provado banco→oráculo→API→navegador.
- Achados abertos p/ fix separado (compartilhados c/ clássico, não corrigidos cego): inspection_rounds code global-unique×sequence per-tenant; op_write poison-marker on failure.

## PROGRAMA DE PARIDADE DE AÇÃO (desligar o clássico) — iniciado 2026-07-31
- Skill1 recon: gap = 147 escritas backend, ~15 ligadas. Skill2 graphify (grafo existente): reuso confirmado, NADA a recriar (cada ação tem controller/service pronto; vacations=DP DESABILITADO, allocations=curadoria). Skill3 planos: `docs/superpowers/plans/2026-07-31-operacional-paridade-acao-INDEX.md` (7 planos) + piloto medidas.
- ✅ PILOTO medidas fluxo aprovação: submeter/aprovar/rejeitar/gerar-documento via `DisciplinaryService`+op_write. Fluxo real rascunho→pendente→**pendente_assinatura** (medida exige assinatura após aprovar). Oráculo `test_acao_medida_fluxo_redesign.py` verde (create+submit+approve+doc). Regressão 21 checagens ok.
- LIÇÃO reconfirmada (testes): user fake deve usar TENANT REAL (templates/sequences são per-tenant; DEFAULT_TENANT não acha template/coliso code). E limpar `idem:medida%` no início (poison-marker do op_write em falha).
- FILA (mesmo molde): scales(ciclo), rondas(campo), time-bank(aprovar/compensar), substitutions/shifts, diaristas(gestão), comunicacao. FORA: allocations, vacations. Money/gov só com OTP.

### Programa ação — lotes 2-3 (2026-07-31)
- ✅ scales CICLO (submeter/aprovar/rejeitar/publicar) via ScaleRepository+op_write; geração/otimização ADIADA (guard-rail Sólides=fonte-verdade). Oráculo cria escala descartável 2099.
- ✅ time-bank aprovar/rejeitar via TimeBankRepository. compensate adiado (workflow c/ validação). Oráculo lançamento descartável.
- MOLDE ação-sobre-registro consolidado: `_scale_action`/`_entry_gate` (valida id→op_write→status real; None=estado inválido). Teste: criar registro descartável, rodar, deletar.

### Programa ação — lote 4 (2026-07-31): substitutions + comunicação + diaristas
- ✅ substituições confirmar/rejeitar (SubstitutionRepository.confirm/reject; confirm resolve substituto do registro). ✅ comunicação: comunicado-publicar (publish_announcement) + alerta-ack (acknowledge_alert). ✅ diaristas ativar/desativar (DiaristService.activate/deactivate_diarist) + avaliar (create_evaluation, condomínio resolvido do diarist_schedules).
- Prova: diarista desativar→reativar (real, estado restaurado), alerta-ack real, build carrega 7 forms; substituições/comunicado/avaliar sem dado agora → forms honestos vazios, mesmo molde reusado. 7 rotas 401.
- FORA (money/gov OTP): pagamentos/fiscal de diarista. Mobile: rondas checkpoints. Sólides: geração de escala.

### Programa ação — lote 5 (2026-07-31): fechamento de diaristas
- ACHADO: pagamento de diarista (money-out PIX) JÁ estava gated OTP no financeiro (/action/pagar-diaristas, gerar_otp_lote/executar_lote). NÃO dupliquei nem disparei.
- ✅ Ligado o elo que faltava: /action/diarista-fechamento (op_write, SEM dinheiro) reusa generate_payroll_payments → cria DiaristPayment PENDENTE. Fluxo: operacional gera fechamento → financeiro paga gated. Oráculo 2099-12=0 gerados (seguro).

## TESTE E2E CROSS-MÓDULO por PERFIL (2026-08-01) — Eliziel Gonzaga × Orlailson Paiva
- **Orlailson Paiva: BLOQUEADO** — 2 contas INATIVAS (opaiva=gerente_operacional, epaiva=admin, is_active=false). Backend retorna 403 "Usuario inativo" em tudo (auth/me, redesign/data). Não faz NADA até reativar.
- **Eliziel Gonzaga: gerente_operacional ATIVO.** permissions=[module:operacional,dp,ged,sst, gestao:disciplinar_comunicados]. Token minta e /auth/me retorna ele certo.
- RBAC backend (autoritativo, por token):
  - ✓ operacional (medida-aprovar/fechamento) alcançável (400 validação, não 403).
  - ✓ admin-only bloqueado: /users/me → 403.
  - ⚠️ GAP: /redesign/data/<qualquer módulo> → 200 (financeiro inclusive) SEM checar module-permission. Eliziel lê dados de módulos fora do perfil.
  - ⚠️ GAP: /action/pagar-diaristas (money-out) → 400 validação, SEM gate de role antes do OTP. Só o OTP (e-mail Jordan) barra o pagamento real; a INICIAÇÃO não é role-restrita.
- FRONTEND: injeção de token no localStorage NÃO troca a identidade da UI (segue "Jordan Jesus/admin", 31 módulos). Launcher do redesign não bootstrapa identidade só do token → teste UI "como Eliziel" exige login real (senha). RBAC de UI não verificável por injeção.
- RECOMENDAÇÃO: (1) reativar Orlailson se deve operar; (2) gate de module-permission no /redesign/data e role-gate no money-out; (3) launcher refletir usuário/RBAC.

## SWEEP DP (2026-08-01) — 1ª passada
- VERACIDADE: DP lê dado REAL (29 FROM tabelas; exibido==banco provado em funcionarios/folha/ferias/reembolsos/contratos/documentos/rescisao/beneficios). DP NÃO tem casca.
- AÇÕES: 15 forms já ligados a endpoints reais (admissão/férias/rescisão/benefícios/licenças/certificações/ponto-fechamento/eSocial/import/prestadores-PJ). Backend DP tem 341 escritas — mas maioria é função RH-especialista (recrutamento 47, folha 25, treinamento), não gerente/supervisor operacional.
- ESCOPO REAL Eliziel/Orlailson na folha (Jordan): VER não conformidades + fazer APONTAMENTOS (não fecham; quem fecha=Jordan/Pyetra).
  - ✅ Ligado: tela `folha-nao-conformidades` (folhas com contest_reason) + ação `folha-apontamento` (reusa contest_reason/contested_at, autor prefixado, SEM mudar status→não interfere no fechamento; não fecha nem paga). Oráculo em draft real, verifica+limpa. Eliziel(module:dp) alcança.
- FALTA medir/decidir no DP: o resto das 341 (recrutamento/folha-ops/treinamento) — só ligar o que o perfil deles faz.

## FRAGILIDADES DE SERVIÇO RESOLVIDAS (2026-08-03) — commit
- ✅ op_write poison-marker: marcador de idempotência gravado SÓ após real_write suceder (falha não deixa poison; dup-check preserva a idempotência real). Teste test_op_write_poison_fix 3/3.
- ✅ code-gen global-unique: disciplinary._generate_code e inspection_rounds.get_next_sequence usam MAX GLOBAL do sufixo numérico (era COUNT per-tenant) — code é UNIQUE global, então per-tenant colidia entre tenants e com gaps de deleção. Compartilhado com o clássico; regressão medida/ronda/escopo verde (escopo agora 3/3).

## SWEEP DP — continuação (2026-08-03)
- LEITURAS: TODAS reais (exibido==banco) — +licenças(8)/certificação(51)/eSocial(36)/prestadores-PJ(9)/folha-rubricas(399) além das 8 antes. DP sem casca em leitura.
- ✅ vacation-reject também ESCOPADO à equipe operacional (era aberto; simétrico ao approve). Testado por chamada direta: supervisor→não-operacional=403.
- GAP ABERTO (decisão Jordan): reembolso approve/reject/analyze — endpoint clássico `/reimbursements/{id}/approve` usa SÓ CurrentActiveUser (sem permissão, sem escopo); wired como row-action no DP. Eliziel poderia aprovar QUALQUER reembolso. Decisão: é papel deles? Se sim → escopar à equipe (como férias/medida); se não → gate de permissão. NÃO citado na lista do perfil (folha-apontamento/férias/medida).
- Ações DP do perfil COBERTAS: folha-apontamento, aprovar/rejeitar férias (escopado), aplicar medida (escopado), ponto-ajuste. Demais forms (admissão/rescisão/benefícios/licenças/certificações/prestadores-PJ/eSocial/import) wired.

## GAP reembolso RESOLVIDO (2026-08-03)
- Decisão: gate `require_permission("module:dp")` em analyze/approve/reject (reimbursement_controller.py). Team-scoping inviável (requester_id→user, sem link employee). Fecha "qualquer autenticado". Eliziel (module:dp literal) mantém função; admin bypassa. Commit aplicado. FALTA: bakear durável.

## SWEEP RH + PORTAL DO FUNCIONÁRIO (2026-08-03)
- **RH** (slug `rh` → gate `module:dp` já no mapa): leituras reais; 0 rotas de escrita próprias (forms apontam a endpoints já gateados). LIMPO.
- **🔴 PORTAL DO FUNCIONÁRIO — vazamento LGPD CONFIRMADO ao vivo e CORRIGIDO**: `/redesign/data/portal-do-funcionario` sem gate + `build(db)` sem usuário → mostrava holerite/ponto/benefícios/férias/documentos/dados-pessoais de TODOS (celiane só-`self:portal` via 16 pessoas / 403× R$). Era "visão admin/preview" exposta. Fix: dispatcher passa `current_user`; builder escopa TODA tela por `employee_id=<logado>` (resolve users.employee_id→email, UUID validado), não usa mais a base agregada; sem vínculo→vazio. Testado: celiane→só ela; anon→0.
- **🔴 MEU-ESPAÇO — mesma classe, também CORRIGIDO**: `_build_meu_espaco` listava notificações (com nomes/mensagens=PII)+tarefas de todos. Fix: notif por `employee_id`, tarefas por `assigned_to/created_by`, reembolsos por `requester`. celiane 28 notif→1; anon→0.
- Mecanismo reusável: builders self-scoped declaram `current_user` na assinatura → dispatcher injeta (retrocompatível). FALTA: bakear durável.
- Não-escopo desta rodada: `area-do-cliente` (parede é por cliente, não por funcionário) — verificar em sweep separado se pedido.

## SWEEP AREA-DO-CLIENTE (2026-08-03)
- Verdade: NÃO é portal de cliente externo — 0 usuários-cliente, users sem link client_id. É visão INTERNA 360 de TODOS os clientes (dashboard/operacao/chamados/financeiro/kits/analytics).
- 🔴 Estava SEM gate → qualquer autenticado interno (celiane só-self:portal) via 21 clientes+MRR+21 faturas. Parede correta=gate de módulo (não self-scope, pois não há conceito per-cliente p/ user interno).
- Fix: `area-do-cliente → crm` em _SLUG_MODULO_CANONICO. celiane user_has_module(crm)=False→403; admin/crm passam. FALTA bakear.

## SWEEP bi / relatorios / configuracoes / empresas (2026-08-03)
- Todos os 4 estavam SEM gate → qualquer autenticado interno via dado sensível.
- **bi** → module:financeiro (bank_transactions/DRE).
- **configuracoes** → ADMIN-ONLY (lista todos users+roles, tenants, feature_flags, integration_logs, config sistema). Crítico.
- **empresas** → ADMIN-ONLY (estrutura CNPJ1/CNPJ2, demonstrativos, rentabilidade, liminares fiscais, migrador CNPJ1→CNPJ2).
- **relatorios** → ADMIN-ONLY (KPIs executivos consolidados: folha líquida, AR/AP, MRR, holerites). PDFs já eram gated financeiro nos botões.
- **empresas /action/nova-liminar** (op_write sem gate) → require_permission(module:fiscal).
- Mecanismo novo: `_SLUG_ADMIN_ONLY` + `_is_admin_user` (admin/super_admin/administrador ou */all) checado no dispatcher ANTES do gate de módulo. celiane 403 nos 4; admin/Pyetra passam. FALTA bakear.

## SWEEP FINAL — 8 slugs restantes (2026-08-03) — INVENTÁRIO 31/31 FECHADO
- automacoes→crm · equipamentos→operacional · suprimentos→financeiro · agendador→dev · integracoes→dev (module gates).
- analytics→admin-only (KPIs exec cross-módulo: punches/nfse/inter/proposals) · seguranca→admin-only (LGPD: candidate_consents/lgpd_audit_logs/erasure_requests).
- assistente→SELF-SCOPE por user_id (assistant_conversations pode ter consulta sensível; celiane via 3 de terceiros→0).
- ESTADO FINAL /redesign/data: 31/31 slugs com parede → 23 module (18+5), 5 admin-only (configuracoes/empresas/relatorios/analytics/seguranca), 3 self-scoped (portal-do-funcionario/meu-espaco/assistente). Nenhum slug aberto.
