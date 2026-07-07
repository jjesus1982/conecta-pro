# Auditoria + Correção E2E — Módulo OPERACIONAL — 2026-07-07

Missão: todo valor exibido == fato no banco (oráculo curl vs SQL). Loop finder→fixer→verificador
(veracity-sweep), 7 subagentes fixers, orquestrador deployou/provou. Convivência com t1 respeitada
(lock `/tmp/conecta_deploy.lock`, zero git destrutivo, módulos do t1 intocados).
Deploy durável: blue/green zero-downtime (`scripts/deploy_backend_bluegreen.sh`).

## Resultado geral

| Métrica | ANTES | DEPOIS |
|---|---|---|
| Sweep GET (207 rotas, 2 mounts) | 157×200, 23×404, 18×422, **9×500** | **165×200, 24×404, 18×422, 0×500** |
| 422 restantes | — | todos = falta de query param obrigatório (provados 200 com params) |
| 404 restantes | — | todos honestos ("não encontrado" com UUID inexistente) |

Auth E2E: mcp-service@conectamais.pro (form-urlencoded, :8080). Fatos do banco em 2026-07-07:
posts=12 (9 ativos), allocations=58 (45 ativas+is_active), employees=71 (50 status ativo),
diarists=14 (5 ativos), shifts=180 (todos 2026-04), scales=3 draft, inspection_rounds=3,
diarist_schedules=6, occurrences/time_bank/substitutions/diarist_assignments=0 (vazios reais).
`pg_stat.n_live_tup` estava PODRE pós-reboot (dizia posts=2) — sempre COUNT(*).

## Achados → correções → provas

### A. SCHEMA-DRIFT código→model (500s) — integration_service.py leituras
- `get_dashboard_unificado/get_metricas_periodo/get_ocupacao_postos/sugerir_diarista_posto/_gerar_alertas`
  usavam `self.db.query` (sync) sobre AsyncSession + colunas defuntas (`Diarist.is_active/full_name/
  average_rating/skills`, `DiaristStatus.ACTIVE/ON_ASSIGNMENT/SUSPENDED`, `DiaristAssignment.post_id/
  start_date/end_date`, `DiaristSchedule.date/actual_check_in/scheduled_start/hours_worked`,
  `Shift.start_time`, `status=="active"/"confirmed"`).
- Reescritos async com SQL raw + casts (`status::text='ATIVO'`), padrão dos writes já corrigidos.
- Rotas provadas (ANTES 500 → DEPOIS 200): `/operations/{dashboard,kpis,kpi-trends,ocupacao,resumo-dia,
  metricas,sugerir-diarista/{id}}`. Dashboard: alocacoes_ativas=45 == SQL; diaristas 5/5 == SQL.
- Honestidade: "diaristas por posto" NÃO derivável (assignment é por condominio_id) → 0 + nota;
  capacidade = SUM(required_headcount) real (fim do `postos*3` chutado); ON_ASSIGNMENT → schedules
  EM_ANDAMENTO na data.

### B. WRONG-MATH/WRONG-SOURCE em stats
- **posts/stats**: `total_allocated` vinha de `SUM(posts.current_headcount)` DESNORMALIZADO=51;
  real = 45 alocações ativas (provado 45 == SQL). `total` escondia inativos (9→12 com by_status completo).
- **dashboard `/operacional/dashboard/` + kpi-trends**: `total_colaboradores` usava `employees.is_active`
  (flag PODRE: inclui 4 demitidos, 3 inativos, 1 suspenso; 13 ativos NULL) → trocado por `status='ativo'`
  (47→**50** == SQL). Flag is_active de employees segue inconsistente no banco (pendência DP).
- **kpi_trends_controller**: `Scale.status=='active'` (status inexistente) → in_(approved/published/
  in_progress); série declara em `nota` que é foto-atual retroprojetada (sem histórico no banco).
- **taxa_ocupacao 409%**: matemática honesta (45 alocados / 11 required_headcount) — problema é CADASTRO:
  required_headcount dos postos subdimensionado. Resposta agora carrega `nota` explicando. **Pendência
  Jordan/Gonzaga: cadastrar required_headcount real dos 12 postos.**

### C. FANTASMA — Férias
- `/operacional/vacations` lia `vacation_requests` (10, espelho DEPRECATED); canônica é
  `hr_vacation_requests` (15 — faltavam FER-2026-001..005 SUBMITTED de 01/07).
- GET agora lê a canônica via SQL (JOIN employees p/ nome; status EN→PT). Provado: 15 itens.
- POST/PATCH/approve/reject/DELETE → **501 honesto** ("férias são geridas no módulo DP") — escrever no
  espelho criava workflow fantasma que o DP nunca via.

### D. Diaristas AI + fiscal (500s)
- AI: assinaturas controller↔service desalinhadas (condominio_id obrigatório) + ~10 awaits faltando +
  atributos defuntos; response_models errados. Corrigido; estimativas fabricadas ("economia 10%")
  REMOVIDAS. Provas: suggest/availability/optimize/performance 200 com dados reais dos 14 diarists.
- Fiscal: 11 `.query` sync → async; `full_name`→`nome`; **CNPJ placeholder "00.000.000/0001-00"
  ELIMINADO** → busca real na tabela `empresas` (CONECTAMAIS ELETRONICA LTDA 35.710.481/0001-03),
  sem empresa → 422; alíquotas SÓ do banco (fallbacks chumbados removidos).
- `simular/1000` provado: INSS autônomo 20%=R$200, ISS 5%=R$50, IRRF 0 (abaixo isenção 2.428,80) ✓.

### E. DRIFT model→banco (tabelas ausentes) — balde 2 aplicado
- `documentos_fiscais_diaristas`, `retencoes_fiscais_diaristas`, `eventos_esocial_diaristas` não
  existiam. Criadas VAZIAS (5 CREATE TYPE + 3 CREATE TABLE sem FK), rito completo:
  backup `backups/postgresql/conecta_pro_PRE_FISCAL_DIARISTAS_20260707_201033.dump` (validado) →
  staging `conecta_pro_drift_check` → produção. Dado intacto provado (diarists=14, employees=71,
  allocations=58, nfse_hist=831). SQLs: `auditoria/FORWARD_fiscal_diaristas_2026-07-07.sql` +
  `REVERSAO_fiscal_diaristas_2026-07-07.sql` (⚠️ reversão só com tabelas vazias).
- `tabela_inss/tabela_irrf`: model `is_active` vs coluna real `is_ativo` → mapeado no model.

### F. DADO fiscal 2026 (achado grave)
- As vigências "2026" cadastradas continham a tabela de **2024** (mínimo 1.412, teto 7.786,02) e
  estavam `is_ativo=false` (desativação CORRETA). **Não ativei dado errado.**
- Seed novo a partir da fonte interna certificada `people_management/common/utils/clt_calculator.py`
  (INSS 2026 oficial Portaria MPS/MF nº 13; IRRF 2026 Lei 15.191/2025; dedução dep. 189,59; nota:
  redutor Lei 15.270/2025 é só folha mensal, não embutido). Linhas 2024 mantidas inativas p/ auditoria.

### G. Bugs pontuais
- `allocations/available-employees`: args trocados (post_id entrava como data → "date <= varchar");
  depois, semântica INVERTIDA (devolvia os JÁ alocados, como strings, quebrando response_model).
  Reescrito: ativos SEM alocação vigente na data, shape {id,nome,cargo}. Provado: 13 == SQL.
- `rondas/minhas-rondas`: `get_rounds_by_inspector` não existia no service → implementado (repo.list).
- `notificacao_service.py` + `notificacao_controller.py` (diaristas): atributos defuntos + 12 calls
  sem await + `db: Session` → corrigidos.
- `diarist_repository.get_diarist_metrics`: `s.horas_trabalhadas` inexistente → `duracao_minutos/60`.
- `diaristas/statistics/general`: total_diaristas 0→5 (filtro defunto; == SQL).

### H. HARDCODED/mock — backend reports + celery
- `reports/services/{coverage,overtime,disciplinary}_report.py`: loaders com dados FAKE ("Posto
  Central", "Joao Silva", 176h, "Cliente A") → consultas reais (shifts/disciplinary_actions/clients);
  custo HE real = overtime_pay+night_bonus (fim do rate 25,0 chumbado). Export Excel/PDF stub → warning
  honesto. Task celery `daily_coverage_report` → ReportsRepository (mesma fonte das rotas HTTP).

### I. FRONTEND (editado, commitado — build/deploy do frontend NÃO rodado, fora do escopo)
- `ferias/page.tsx`: **16 pedidos DEMO fabricados REMOVIDOS** (mostravam-se em erro/vazio como reais);
  tela agora é somente-leitura honesta com banner → gestão no módulo DP.
- `colaboradores/[id]`: aba Documentos fabricava CNH/CREA/ASO no localStorage → empty-state honesto
  ("integração GED pendente"); chave legada contaminada é limpa.
- `page.tsx`: `change={5}` chumbado → delta real da série de cobertura.
- `comunicados`: endpoints inexistentes (`/confirmar-leitura`, `/announcements/{id}/read`) → `/confirmar`
  real; contagem de leituras fabricada por seed do ID e fallback `?? 44` removidos.
- `reembolsos`: `/pay` (inexistente) → `/process`; catch que mentia "registrado localmente" corrigido.
- `escalas`: botão sync chamava `/ponto/sync-escalas` (inexistente); endpoint real existente é
  incompatível (1 turno por vez) → botão desabilitado com tooltip honesto.

## Pendências de DADO (para Jordan — nada disso é código)
1. `required_headcount` dos 12 postos subdimensionado (soma=11 vs 45 alocados) → taxa de ocupação >100%
   com nota. Cadastrar o headcount real por posto.
2. `employees.is_active` inconsistente (13 ativos NULL, 4 demitidos true) — operacional já não a usa;
   alinhar a flag no DP ou aposentá-la.
3. Diarists de TESTE no banco ("Ana Silva - Diarista Teste", "Maria Diarista Atualizada", CPF
   12345678901) — expurgar ou completar cadastro real (CPF/PIX).
4. `shifts` só tem dados de abril/2026 (180) — "turnos hoje"=0 é honesto; gerar escalas/turnos correntes.
5. `scales` 3 draft; escalas em andamento=0 honesto.
6. IRRF de RPA usa tabela progressiva pura (redutor Lei 15.270 não aplicado — conferir com contador se
   deve valer p/ autônomos).
7. Frontend corrigido precisa de BUILD+deploy (proibido nesta missão) — dashboards antigos seguem no ar
   até o próximo build.

## Arquivos alterados (commit desta missão)
Backend (22): integration_service, dashboard_controller, kpi_trends_controller, reports_controller,
allocation_controller, allocation_repository, post_repository, vacations/controller, tasks,
inspection_rounds (controller+service), reports/services×3, diaristas: diarist_controller,
fiscal_controller+service, notificacao_controller+service, diarist_ai_service, diarist_repository,
models/documento_fiscal.
Frontend (6): operacional/{page,ferias,colaboradores/[id],comunicados,reembolsos,escalas}/page.tsx.
