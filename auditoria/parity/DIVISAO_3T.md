# DIVISÃO 3 TERMINAIS — Paridade Redesign (fonte da verdade)

> Documento OFICIAL de coordenação. Orquestrador = **T1**. Duas análises independentes
> (T1 e T3) convergiram na mesma arquitetura → desenho travado. Atualizado 2026-07-21.

## Objetivo da FASE 1
Ligar (wire) ao DADO REAL do clássico as **161 telas não-wired** do redesign, em 3 terminais
**sem conflito**. Cobertura atual: **128 wired / 258 no menu (≈37%)**. Ação legal/dinheiro
(transmitir eSocial, pagar, OTP) fica SEMPRE **GATED** — nunca disparada em teste.
Fase 2 (reconstrução das ~611 capacidades de escrita) vem depois, com outro placar.

## Identidades (TRAVADAS — não confundir) — atualizado 2026-07-21
| Terminal | Papel | tmux |
|---|---|---|
| **T1** | Orquestrador + fundação (feita) + seus módulos | (sessão que fez telas 1-24) |
| ~~T2~~ | **Realocado p/ outra missão crítica** — seus módulos foram p/ T4 | — |
| **T3** | Trabalhador — cluster pessoas | já com diagnóstico na mão |
| **T4** | Trabalhador — cluster financeiro/comercial (assumiu o do T2) | sessão nova |
| **T5** | Monitor (NÃO codifica) — observa T1/T3/T4 | sessão nova |

## Divisão por módulo (cada módulo pertence a EXATAMENTE um terminal)
| Terminal | Módulos (gap = telas não-wired) | ~telas |
|---|---|---|
| **T1** | operacional(28) · saude-ocupacional(3) · fiscal(6) · juridico(8) · integracoes(5) · campo(2) · documentos(2) · relatorios(1) · meu-espaco(0) · suprimentos(1) · homologacao(1) | **~57** |
| **T4** | financeiro(21) · gestao-de-pessoas(9) · crm(3) · empresas(4) · seguranca(5) · recrutamento(1) · servicos(2) · agendador(3) · assistente(2) · bi(0) · analytics(0) | **~50** |
| **T3** | departamento-pessoal(10) · rh(10) · marketing(7) · area-do-cliente(6) · portal-do-funcionario(5) · licitacoes(3) · configuracoes(6) · equipamentos(4) · automacoes(3) | **~54** |

Denominador = **telas wireable** (não P0 cru: P0 mede o buraco total, inclui escrita GATED que
ninguém faz em paralelo agora).

## As 4 REGRAS INVIOLÁVEIS (quebrou = conflito / perda de trabalho)
1. **Propriedade de arquivo.** Cada terminal edita SÓ `backend/modules/operacional/controllers/redesign_builders/<seu_módulo>.py`. NUNCA o registry (`redesign_data_controller.py`), NUNCA `_shared.py`, NUNCA módulo alheio.
2. **Commit antes de deploy.** O blue-green assa a árvore git inteira → commite seu arquivo antes de subir. Arquivos disjuntos → `git pull --rebase` nunca conflita → deploy de um carrega o commitado de todos (aditivo).
3. **Deploy serializa pelo lock** `/tmp/conecta_deploy.lock`. Use retry-loop se ocupado. 1 imagem por vez; builds ~2-3 min enfileiram.
4. **Checklist ao vivo.** Marque a tela que pegou aqui embaixo ANTES de começar (evita 2 pegarem a mesma).

## Padrão de cada tela (ver CORRECOES.md p/ exemplos)
1. Achar menu-id não-wired no `_modules/<slug>.json`.
2. No SEU `redesign_builders/<mod>.py`: `await safe("<id>", tbl(...))` lendo a MESMA tabela do clássico.
3. Coluna enum/json → `::text` / `->>'k'` no coalesce (senão `safe()` engole a tela e ela some).
4. Deploy blue-green → grep container → `curl /redesign/data/<slug>` prova dado real → commit atômico + linha no CORRECOES.md.
5. Ação de escrita legal (transmitir/pagar) = form GATED, NUNCA dispara.

## STATUS DA FUNDAÇÃO — ✅ PRONTA (2026-07-21, commit 941f8ab9)
- [x] T1: registry aditivo `_discover_module_builders()` (override + merge + router). Helpers ficaram no monólito (importados pelos módulos) — mais seguro que mover. Não usei `_shared.py`; os módulos importam de `redesign_data_controller`.
- [x] T1: **128 telas wired IDÊNTICAS** ao `BASELINE_PRE_REFACTOR.json` (0 divergência, 8080 healthy).
- [x] T1: deploy + commit `941f8ab9`.
- **✅ FUNDAÇÃO PRONTA — T2 e T3 podem começar.** Como escrever seu módulo: copie `redesign_builders/_TEMPLATE.py` → `<seu_modulo>.py`, defina `SLUG`, copie o corpo do `_build_<mod>` atual do monólito como ponto de partida e adicione telas.
- [x] T1: **caminho de override PROVADO end-to-end** (teste no container, sem deploy): arquivo de módulo real → sem import circular no boot, `BUILDERS[slug]` vira o override, `EXTRA_MENU` mescla, `build()` roda. O mecanismo está battle-tested; pode confiar.

## GOTCHA DE DEPLOY (aprendido no refactor)
- Deploy blue-green leva **~7 min** (build+green+recria primário). **NÃO use timeout < 600s** — cortar no meio deixa o nginx apontado pro green e pode servir código stale. Se cortar: `sed -i "0,/server 127.0.0.1:80../s//server 127.0.0.1:8080;/" /etc/nginx/sites-available/erp.conectamais.pro && nginx -t && systemctl reload nginx` volta pro primário; depois `docker rm -f conecta-pro-backend-green`.
- SEMPRE `grep container` + curl no domínio público pós-deploy (não só localhost:8080).

## CHECKLIST AO VIVO (marque `[x] <terminal> <tela>` quando fechar)
<!-- ex.: - [x] T1 fiscal/certidoes-cnd (curl 9 CNDs) commit abc123 -->
- [x] T1 juridico: 1º módulo via fundação — contratos·conhecimento·analise·processos-det (+visao/processos/det). escritorio=probe→honesto vazio. build() 7 telas provado no container.
- [x] T3 departamento-pessoal (10/10): admissao(admission_processes 3)·aviso-previo(employees, 0=honesto)·ponto(gp_clock_punches 300)·fechamento-ponto(gp_monthly_closings 50)·licencas(sst_afastamentos 8)·reembolsos(reimbursement_requests 20)·contratos(employment_contracts 43)·documentos(hr_employee_documents 32)·certificacao(hr_certifications 51)·esocial(esocial_eventos_espelho 36). build() estende _build_dp. Deploy blue-green OK + HTTP 200 autenticado provado. commit na branch.
- [x] T3 rh (10/10): vagas(job_positions 10)·candidaturas(applications 8)·onboarding(admission_processes 3)·treinamentos(trainings 5)·cursos(training_courses 9)·avaliacoes(operacional_avaliacoes_equipe 3)·carreira(career_plans 11)·clima(climate_surveys 3)·turnover(turnover_audit_logs 5)·ia(rh_consultas 4). Gotchas: enum status/category→::text, competencia DATE→to_char. Deploy+HTTP200 provado.
- [x] T3 marketing (7/7, módulo era 100% mock): funil(leads 14 reais)·campanhas·lead-magnet·biblioteca·copywriter·estrategista·brand-voice (marketing_campaigns/assets/content_drafts reais, hoje 0=honesto). Deploy+HTTP200 provado.

> ⚠️ **CONSOLIDAÇÃO DE LEAD — T5 assumiu CRM + WhatsApp (2026-08-09, autorizado pelo Jordan).**
> Escopo: `crm/repositories/lead_repository.py`, `crm/services/`, e os 10 pontos que criam lead
> em `crm/controllers/`, `integrations/connectors/whatsapp/`, `ai/.../tools_acao_crm.py`,
> `operacional/.../redesign_data_controller.py` (só a função `rd_action_lead`).
> **T4 (CRM) e quem mantém o WhatsApp: falem com o Jordan antes de mexer nesses arquivos.**
> Plano: `~/.claude/plans/quando-concluirmos-o-marketing-zesty-finch.md`.
> Regra decidida pelo Jordan: **mesmo telefone = mesmo lead**. Impacto medido em produção
> (2026-08-09): 28 leads, 1 par de duplicata — e é artefato de teste nosso. Risco retroativo ≈ 0.
> ⚠️ NÃO mexo em `redesign_data_controller.py` além de `rd_action_lead` — é o registry
> compartilhado da paridade (regra 1).

> 🔴 **PENDÊNCIA ABERTA — 10 caminhos concorrentes criam LEAD.**
> _(Revisado 2026-08-07 por leitura função-a-função. A versão anterior dizia "8" e estava
> ERRADA: eu inferi semântica dos rótulos do grafo sem abrir as funções. O grafo mostra
> proximidade, não o que cada função faz.)_
> Não há um serviço comum de criação de lead. Dez pontos de escrita em `leads`, em 4 módulos:
> ```
> create_lead()                 crm/controllers/lead_controller.py:33      dedup: email
> converter_lead_para_crm()     crm/controllers/marketing_controller.py:223  dedup: NENHUM
> converter_licitacao_para_crm() crm/controllers/marketing_controller.py:330 dedup: NENHUM
> registrar_lead_da_visita()    crm/services/visit_reports.py:191          dedup: telefone
> _criar_lead_para_conversa()   whatsapp/agent_service.py:817              dedup: telefone
> _match_or_create_lead()       whatsapp/controller.py:202                 dedup: telefone+ativo
> _propor_criar_lead()          ai/.../tools_acao_crm.py:35                dedup: nome+fone+email
> rd_action_lead()              operacional/.../redesign_data_controller.py:2252  dedup: email
> public_form_submit()   🔴     crm/controllers/growth_controller.py:640   dedup: NENHUM · SEM AUTH
> public_booking_create() 🔴    crm/controllers/growth_controller.py:772   dedup: NENHUM · SEM AUTH
> ```
> **NÃO são pontos de criação** (constavam errado antes): `visita_registrar_lead` (wrapper HTTP
> de registrar_lead_da_visita) · `_tool_registrar_lead` (só UPDATE; cria via auto-cura) ·
> `criar_mkt_lead` (escreve em `marketing_leads`, NUNCA em `leads`).
>
> 🔴 **Dois endpoints PÚBLICOS sem auth e sem dedup** — superfície aberta de flood de lead.
> 🔴 **`probability` em escalas incompatíveis EM PRODUÇÃO**: `0.3`/`0.6` (marketing) vs `50`
> (visitas) vs `0–100` (ORM). Coluna Float sem constraint, e `weighted_value`/`is_hot` leem
> esse campo → métrica de pipeline mistura fração com percentual hoje.
> 🟡 Scoring só em 3 dos 10; o resto grava constante. `SOURCE_SCORES` não conhece as 5 fontes
> novas (lead de landing pontua como "other"). Dois motores concorrentes: `create_lead` chama
> o `LeadScoringEngine` e o `recompute_lead_score` sobrescreve em seguida.
> ✅ **Já existe o que falta:** `crm/services/phone.py` → `match_key_br()` (DDD + 8 últimos
> dígitos, resolve nono dígito e DDI) e `pipeline_sync._lead_id_for_proposal` (casa por
> telefone OU email, devolve None se ambíguo). Não escrever dedup novo.
> **Consequência já materializada:** a atribuição de origem (`leads.source`, commits `bbf18868`
> + `65abeeed`) cobre só **2 dos 8**. Lead criado por visita/growth/lead_controller continua sem
> origem correta → MRR por canal fica incompleto. Cada caminho reimplementa dedup, origem e
> scoring à sua maneira.
> **Contexto do grafo:** `Lead` é o nó mais conectado de todo o subsistema (grau 76, vs 37 do
> 2º) — vizinhos fortes: DashboardService, LeadScoringEngine, LeadService. Mexer em `Lead`
> reverbera em dashboard e scoring. Foi por isso que o enum fechado `LeadSource` derrubou o
> caminho principal em 05/08.
> **Proposta (NÃO executada — precisa de decisão do Jordan):** consolidar num único
> `LeadService.criar()` que centralize dedup + origem + scoring. É refactor de módulo alheio
> (CRM = T4; WhatsApp = sem dono definido) e de alcance grande — merece tarefa própria, não
> emenda. Grafo em `/tmp/mkt_graph/graphify-out/` (recorte isolado; NÃO sobrescreve o grafo
> fiscal em `/opt/conecta-pro/graphify-out/`).

> ⚠️ **`ModuleView.tsx` — T5 assumiu (2026-08-05, autorizado pelo Jordan).**
> `frontend/src/components/redesign/ModuleView.tsx` é INFRA COMPARTILHADA (renderiza todas as
> telas do redesign e o modal de ~100 rotas `/redesign/action/*`, incluindo as de dinheiro).
> Não tinha dono na divisão — que cobre só os builders. Commit `ce01b99a`: modal fecha e
> recarrega após sucesso + erro 422 legível. **Quem for mexer aí: fale com o Jordan antes.**

> ⚠️ **TRANSFERÊNCIA DE PROPRIEDADE — `marketing` T3 → T5 (2026-08-05, autorizada pelo Jordan).**
> Motivo: Fase 1 (leitura) do marketing foi concluída pelo T3 em 22/07 e o T3 seguiu para folha.
> O T5 assume o arquivo `redesign_builders/marketing.py` para executar a **Fase 2 (ações de
> escrita)**: ligar as 12 rotas que o clássico já consome e o redesign não chama nenhuma.
> **T3: não edite `marketing.py` sem falar com o Jordan.** Backend não muda (as 20 rotas de
> `crm/controllers/marketing_controller.py` já existem); nenhum arquivo compartilhado é tocado.
- [x] T1 documentos: kits(58 ged_document_kits) + pastas(8 ged_folders). campo pulado (monitoramento/comunicados sem tabela → honesto vazio).
- [x] T4 financeiro (21/21): fluxo-caixa·conciliacao·boletos·cobrancas·banking·inter·compras·estoque·faturamento·fiscal·nfse-entrada·orcamentos·precificacao·custos·contabilidade·contratos·raio-x·cfo·agentes·relatorios·custeio. `redesign_builders/financeiro.py` estende `_build_financeiro`. HTTP 200 8080+público, rows reais. commit c74072a8. Dinheiro que SAI = gated.
- [x] T4 gestao-de-pessoas (9/9): ged-kits(58)·ged-envios(49)·ged-assinaturas(200)·ponto-banco(0 honesto)·rh(66)·rh-treinamentos(0 honesto)·rh-cargos(51)·saude(96)·consultor(4). commit c74072a8.
- [x] T4 crm (3/3): clientes(20)·growth(6)·consultor(69). commit c74072a8.
- [x] T4 empresas (4/4): demonstrativos(7)·rentabilidade(20)·liminares(3)·migrador(4, só visibilidade). commit c74072a8.
- [x] T4 seguranca/LGPD (5/5): consentimento(5)·esquecimento(1)·mascaramento/criptografia/pia-dpia(0 honesto). só visibilidade. commit c74072a8.
- [x] T4 recrutamento (1/1): candidaturas(10). commit c74072a8.
- [x] T4 servicos (2/2): contratos(12)·agendamentos(0 honesto). commit c74072a8.
- [x] T4 agendador (3/3 NOVO): visao(dash)·tarefas(0)·execucoes(0). commit c74072a8.
- [x] T4 assistente (2/2 NOVO): chat(3)·historico(1). commit c74072a8.
- ⚠️ T4: 50 telas VIVAS no primário via cp (volátil). BAKE pendente — árvore suja com WIP não-commitado de people_management (outro terminal); blue-green assa a árvore inteira. Próximo deploy com árvore limpa torna durável (arquivos já commitados).
- [x] T1 saude-ocupacional: estabilidade(1 real, CINTIA) + alertas(88 ASOs vencidos). Padrão delegar+estender (build() chama _build_saude e adiciona). ajuda-medicamento pulado (sem tabela).
- ✅ T4 BAKE CONCLUÍDO (2026-07-21 11:56, blue-green RC=0, zero downtime): imagem baked 881747… contém os 9 arquivos; 50 telas DURÁVEIS. Verificado no domínio público pós-recreate: financeiro 26 c/dados·gp 12·crm 12·empresas 5·seguranca 2·recrutamento 3·servicos 2·assistente 2 (+ honestas-vazias). Oráculo raio-x=financial_kpis batendo (Saldo Inter R$67.757,29 == banco). commits c74072a8 (build) + a627bfcd (docs).
- [x] T1 operacional: presenca(200 batidas)·escalas(20)·turnos(200)·reembolsos(22) — TUDO leitura (curadoria do Jordan respeitada). disciplinar pulado (RBAC-sensível); escalas-grade/visual/rondas/AI = capacidade, não wireáveis.
- [x] T3 area-do-cliente (6/6, era 100% mock): dashboard(clients 20)·operacao(inspection_rounds 3)·chamados(occurrences 4)·financeiro(receivable_accounts 21)·kits(ged_document_kits 58)·analytics(agregado). Deploy+HTTP200.
- [x] T3 portal-do-funcionario (5/5): ponto(gp_clock_punches)·beneficios(employee_benefits 159)·escalas(shifts)·treinamentos(trainings)·dados-pessoais(employees 52). Estende _build_portal_funcionario. Deploy+HTTP200.
- [x] T3 licitacoes (3/3): disputas(bidding_tenders 9)·documentos(bidding_tender_documents 8)·resultados(bidding_tenders). Estende _build_licitacoes. ia sem tabela→não fabricado. Deploy+HTTP200.
- [x] T3 configuracoes (6/6): tenants(1)·integracoes(integration_logs 81)·templates-notificacao·feature-flags·configuracoes-sistema(limites/uso tenant)·consultor(consultor_memorias 24). Estende _build_configuracoes. Deploy+HTTP200.
- [x] T3 equipamentos (4/4, NOVO): visao·patrimonio·comodatos·manutencoes (equipment* reais, hoje 0=honesto). Deploy+HTTP200.
- [x] T3 automacoes (3/3, NOVO): visao(resumo 3 métricas)·workflows·execucoes (crm_workflow* reais). Deploy+HTTP200.
- ✅ **T3 CLUSTER PESSOAS 100% — 9 módulos / 54 telas ligadas, deployadas e provadas por HTTP 200 autenticado.**
- [x] T1 integracoes: logs(81 integration_logs) + sync(solides_sync_log). conectores/webhooks/api-keys sem tabela → honesto vazio.
- [x] T1 fiscal(certidoes alias)·homologacao(visao NOVO). suprimentos pulado (inventory_items=seed). relatorios/dashboards sem tabela. MEUS MÓDULOS FASE 1: essencialmente completos.
