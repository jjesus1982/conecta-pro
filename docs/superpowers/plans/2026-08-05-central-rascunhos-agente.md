# Central de Rascunhos do Agente Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tornar o chat realmente funcional — o agente CRIA tudo como rascunho inerte, que cai numa tela ÚNICA de aprovação onde o humano revisa e aprova; aprovar é que efetiva (OTP para dinheiro/eSocial).

**Architecture:** Uma tabela genérica `agent_drafts` guarda todo rascunho criado pelo agente (tipo, payload executável, status, gate). A primitiva `criar_rascunho()` grava o rascunho + toca o sino + audita — com **propositor = AGENTE** (não o usuário), o que dissolve o fail-closed de aprovador único e casa com "o agente cria, eu aprovo". Um **registry de executores** (`registrar_executor(tipo, fn)`) mapeia cada tipo → o serviço de domínio REAL que roda **só na aprovação**. Uma tela /redesign "Central de Aprovações" lista os rascunhos e os aprova/rejeita via endpoints genéricos; dinheiro/eSocial exigem OTP no aprovar.

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic + PostgreSQL (jsonb) + Next.js redesign data-driven (builder + `_modules/*.json` + `/redesign/data` + `/redesign/action/*`).

## Global Constraints

- **LLM NUNCA executa/efetiva.** `criar_rascunho` só grava rascunho INERTE + sino + audit. A execução real do serviço de domínio acontece EXCLUSIVAMENTE no endpoint de aprovação, disparada por humano. Copiado verbatim da parede: "LLM nunca executa (só propor→humano aprova)".
- **Dinheiro que SAI + eSocial = SEMPRE gate OTP humano** no aprovar. `requires_otp=true` bloqueia a execução sem OTP válido. Teto pagamento `CONECTA_LIMITE_DIARIO_PAGAMENTOS`=R$100.000 continua valendo no serviço de pagamento.
- **Operacional (postos/alocações) = READ-ONLY para agentes** até o Jordan liberar explicitamente. Não registrar executor/rascunho que mute escala/alocação sem ok dele.
- **Propositor = AGENTE**; aprovador = humano com role. Não reintroduzir "propositor≠aprovador humano" no caminho de agent_drafts — o controle é rascunho+revisão+OTP-para-dinheiro. (Corrige o fail-closed de admin único.)
- **NUNCA fabricar**: rascunho reflete o que o usuário pediu; execução usa serviço real; vazio real = "aguardando dado".
- **RBAC pela identidade real** de quem aprova (nunca conta de serviço). Aprovar checa `roles_aprovador` do rascunho contra o usuário.
- **Foco 100% redesign**: a tela de aprovação é /redesign data-driven (builder + json), sem .tsx novo se der. Não gatear/alterar endpoints clássicos compartilhados.
- Commits `--no-verify`, `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. `git add` só os arquivos próprios (git índice compartilhado, peer-churn). Bench throwaway NUNCA :8080. Deploy backend blue-green (lock `/tmp/conecta_deploy.lock`); frontend = container `conecta-pro-frontend` via docker-compose.yml.

---

## File Structure

- **Migration** `backend/alembic/versions/<rev>_agent_drafts.py` — cria `agent_drafts`.
- **Model** `backend/modules/ai/conversation/models/agent_draft.py` — ORM `AgentDraft` (novo model; se o módulo não tiver `models/`, criar).
- **Primitiva + registry** `backend/modules/ai/conversation/services/orquestrador/acoes/rascunho.py` — `criar_rascunho()`, `registrar_executor()`, `EXECUTORES`, `executar_rascunho()`.
- **Endpoints de aprovação** `backend/modules/ai/conversation/controllers/aprovacoes_controller.py` — `GET /aprovacoes`, `POST /aprovacoes/{id}/aprovar`, `POST /aprovacoes/{id}/rejeitar` (montado sob `/api/v1`). (Ou dentro do redesign_data_controller como /redesign/action/* — decidir na Task 4 conforme o padrão vigente.)
- **Builder da tela** `backend/modules/operacional/controllers/redesign_builders/aprovacoes.py` — dados da Central.
- **Config do módulo** `frontend/src/app/redesign/_modules/aprovacoes.json` — layout data-driven.
- **Executores por tipo** — dentro dos `tools_acao_*.py` existentes (cada domínio registra seu executor perto do handler).
- **Reduzir recusas** `backend/modules/ai/conversation/services/orquestrador/engine.py` (catch-all) e `consultor_escopado_controller.py` (system prompt).

---

## Task 1: Migration + model `agent_drafts`

**Files:**
- Create: `backend/alembic/versions/<rev>_agent_drafts.py`
- Create: `backend/modules/ai/conversation/models/agent_draft.py`
- Test: bench throwaway (query DDL)

**Interfaces:**
- Produces: tabela `agent_drafts` e model `AgentDraft` com colunas: `id uuid pk`, `tipo text not null`, `modulo text not null`, `titulo text not null`, `resumo text`, `payload jsonb not null default '{}'`, `status text not null default 'rascunho'` (rascunho|aprovado|rejeitado|executado|falha), `gate text not null default '🔵'`, `requires_otp boolean not null default false`, `roles_aprovador text[] not null`, `criado_por_agente boolean not null default true`, `solicitado_por uuid` (o user que pediu no chat, p/ trilha — NÃO é aprovador-excludente), `solicitado_por_nome text`, `empresa_id uuid`, `entity_ref text`, `erro_execucao text`, `decidido_por uuid`, `decidido_em timestamptz`, `created_at timestamptz not null default now()`. Índice em `(status, created_at)` e em `empresa_id`.

- [ ] **Step 1:** Descobrir o head atual do alembic (`alembic heads` no container ou olhar `alembic/versions`), e o padrão de migration do projeto (revisão, imports). Escrever a migration criando a tabela + índices, `down_revision` = head atual.
- [ ] **Step 2:** Escrever o model `AgentDraft` seguindo o padrão ORM do projeto (Base, tipos). Colunas exatamente como acima.
- [ ] **Step 3:** Aplicar migration no banco real (`alembic upgrade heads` no container backend — passo MANUAL pós-bake, ver regra). Verificar via bench: `\d agent_drafts` (colunas + índices).
- [ ] **Step 4:** Commit (`git add` migration + model).

## Task 2: Primitiva `criar_rascunho` + registry de executores

**Files:**
- Create: `backend/modules/ai/conversation/services/orquestrador/acoes/rascunho.py`
- Test: `backend/scripts/orq/test_rascunho.py` (bench throwaway)

**Interfaces:**
- Consumes: `AgentDraft` (Task 1); `agent_audit` e `entrega` (sino) do mesmo jeito que `acoes/base.py` usa.
- Produces:
  - `async def criar_rascunho(db, user, *, tipo, modulo, titulo, resumo, payload, gate, requires_otp, roles_aprovador, empresa_id=None, idempotency_key=None) -> dict` — insere `AgentDraft` (status='rascunho', solicitado_por=user.id), audita, toca o sino aos usuários com `roles_aprovador` (reusar `entrega`/`base` helpers) com `action_url="/redesign/aprovacoes"` e `reference_type="agent_draft"`, `reference_id=draft.id`. Idempotência por `idempotency_key` (não duplica rascunho vivo). Retorna `{"status":"rascunho","draft_id":..,"tipo":..,"titulo":..,"mensagem":"Criei o rascunho — aprove na Central de Aprovações."}`. NUNCA executa. NÃO exclui o solicitante dos aprovadores (propositor=agente).
  - `def registrar_executor(tipo, fn)` — registra `fn` no dict `EXECUTORES`. `fn(db, aprovador_user, payload) -> str (entity_ref)`; roda o serviço de domínio REAL.
  - `async def executar_rascunho(db, aprovador_user, draft) -> AgentDraft` — chama `EXECUTORES[draft.tipo]`, seta status/entity_ref/erro. NÃO valida OTP aqui (o controller faz).
- [ ] **Step 1:** Escrever teste bench: `criar_rascunho(...)` grava 1 `AgentDraft` status='rascunho', NÃO chama nenhum executor (monkeypatch-boom num executor sentinela nunca dispara), toca o sino (1 notificação p/ o aprovador), idempotente (2ª com mesma key → não duplica). Sentinela + cleanup finally + 0 resíduo.
- [ ] **Step 2:** Rodar → falha (módulo não existe).
- [ ] **Step 3:** Implementar `rascunho.py` reusando os helpers de sino/audit do `acoes/base.py` (importar, não copiar). `EXECUTORES: dict[str, Callable]`.
- [ ] **Step 4:** Rodar teste → passa. Provar que executor sentinela nunca disparou.
- [ ] **Step 5:** Commit.

## Task 3: Endpoints aprovar / rejeitar / listar (com OTP p/ dinheiro)

**Files:**
- Create: `backend/modules/ai/conversation/controllers/aprovacoes_controller.py`
- Modify: registrar o router no app (onde os controllers são incluídos — seguir padrão).
- Test: `backend/scripts/orq/test_aprovacoes_endpoint.py` (bench, chamada in-process do handler)

**Interfaces:**
- Consumes: `executar_rascunho`, `AgentDraft` (Tasks 1-2).
- Produces:
  - `GET /api/v1/aprovacoes?status=rascunho` — lista rascunhos que o usuário PODE aprovar (role ∈ roles_aprovador), escopado por empresa se aplicável. Campos p/ a tela.
  - `POST /api/v1/aprovacoes/{id}/aprovar` — valida: usuário tem role ∈ roles_aprovador (senão 403); se `requires_otp` → exige `otp` no body e valida pelo mesmo mecanismo de OTP de pagamento existente (descobrir e reusar; sem OTP válido → 428/403, NÃO executa). Então `executar_rascunho`. Seta status='executado'/'falha', decidido_por/em. Retorna resultado + entity_ref.
  - `POST /api/v1/aprovacoes/{id}/rejeitar` — status='rejeitado', decidido_por/em. Não executa.
- [ ] **Step 1:** Descobrir o mecanismo de OTP de pagamento vigente (grep `otp`, `CONECTA_LIMITE`, propor_lote_pagamento/inter). Reusar. Descobrir como routers são montados.
- [ ] **Step 2:** Teste bench: (a) aprovar rascunho 🔵 sem otp → executa (executor sentinela REVERSÍVEL dispara, entity_ref setado); (b) aprovar rascunho requires_otp SEM otp → NÃO executa (boom-executor nunca dispara), retorno pede OTP; (c) aprovar sem role → 403; (d) rejeitar → status rejeitado, não executa. Sentinela + cleanup + 0 resíduo; NUNCA aprovar dinheiro real.
- [ ] **Step 3:** Rodar → falha.
- [ ] **Step 4:** Implementar o controller. Executar só via `executar_rascunho`. OTP obrigatório quando `requires_otp`.
- [ ] **Step 5:** Rodar → passa.
- [ ] **Step 6:** Commit.

## Task 4: Tela "Central de Aprovações" no /redesign

**Files:**
- Create: `backend/modules/operacional/controllers/redesign_builders/aprovacoes.py`
- Create: `frontend/src/app/redesign/_modules/aprovacoes.json`
- Modify: registrar o slug `aprovacoes` no dispatcher do /redesign/data (seguir padrão dos outros builders) e no menu/nav do redesign.
- Modify: `frontend/src/components/redesign/RdBell.tsx` só se `action_url="/redesign/aprovacoes"` não resolver (validar rota).

**Interfaces:**
- Consumes: `GET /api/v1/aprovacoes` (Task 3) — o builder chama o service/repo direto (in-process) OU a tela consome o endpoint; seguir o padrão dos builders existentes (ex.: `redesign_builders/crm.py`).
- Produces: tela lista rascunhos (colunas: tipo, título, resumo, gate, solicitado por, data) com row-actions **Aprovar** e **Rejeitar** → POST nos endpoints da Task 3. Aprovar de item `requires_otp` abre campo de OTP (form). Vazio real → "Nenhum rascunho aguardando aprovação".
- [ ] **Step 1:** Ler `redesign_builders/crm.py` + `departamento_pessoal.py` (folha-gerar) + `ModuleView.tsx` (row-action/form/ctaTo) p/ o molde exato de row-action→POST e form com campo (OTP).
- [ ] **Step 2:** Escrever o builder `aprovacoes.py` (lê os rascunhos que o usuário pode aprovar) + o `aprovacoes.json` (tabela + row-actions Aprovar/Rejeitar; Aprovar-com-OTP = form quando requires_otp).
- [ ] **Step 3:** Registrar o slug no dispatcher /redesign/data + item de menu.
- [ ] **Step 4:** Validar `action_url="/redesign/aprovacoes"` resolve (rota existe). Se não, ajustar o slug/rota.
- [ ] **Step 5:** Deploy (backend blue-green + frontend rebuild) e verificar NA TELA (browser) que a Central aparece e lista.
- [ ] **Step 6:** Commit.

## Task 5: Ligar 3 tipos piloto ponta-a-ponta (comunicado, proposta_comercial, contrato)

**Files:**
- Modify: `backend/modules/ai/conversation/services/orquestrador/tools_acao_crm.py` (proposta_comercial, contrato — converter os no-op `criar_contrato`/`enviar_proposta` + a proposta p/ `criar_rascunho` + registrar executor real)
- Create/Modify: um tipo `comunicado` (novo `agir` ou reusar `propor_comunicado` existente) → `criar_rascunho` + executor.
- Test: `backend/scripts/orq/test_tipos_piloto.py` (bench)

**Interfaces:**
- Consumes: `criar_rascunho`, `registrar_executor` (Task 2); os SERVICES reais de domínio (ProposalService/ContractService, comunicado service) — os MESMOS dos endpoints clássicos.
- Produces: 3 tipos com o ciclo completo: chat cria rascunho → Central lista → aprovar chama o service real → entity_ref. `enviar_proposta`/`ativar_contrato` = `requires_otp`? Não (não é dinheiro) mas gate 🔴 e externo/LGPD → confirmar no corpo; contrato ativar = irreversível-ish, sem OTP mas gate alto.
- [ ] **Step 1:** Teste bench por tipo: criar rascunho (não executa) → aprovar via executor REVERSÍVEL sentinela → entity_ref criado no domínio → cleanup. Provar que criar NÃO cria o entity (só aprovar cria).
- [ ] **Step 2:** Rodar → falha.
- [ ] **Step 3:** Implementar: converter os handlers para `criar_rascunho(tipo=...)` e `registrar_executor(tipo, fn_que_chama_service_real)`.
- [ ] **Step 4:** Rodar → passa.
- [ ] **Step 5:** Commit.

## Task 6: Reduzir recusas (system prompt + catch-all)

**Files:**
- Modify: `backend/modules/ai/conversation/controllers/consultor_escopado_controller.py` (`_SYSTEM_BASE`)
- Modify: `backend/modules/ai/conversation/services/orquestrador/engine.py` (catch-all `:141-143`)
- Test: n/a (mudança de prompt) + smoke E2E manual.

**Interfaces:**
- Produces: `_SYSTEM_BASE` reescrito: o padrão é **CRIAR RASCUNHO** para qualquer pedido acionável ("eu crio o rascunho e você aprova na Central"), recusando só para paredes reais (dinheiro sem OTP na hora certa, operacional read-only, dado inexistente). O catch-all do engine passa a distinguir erro de execução (logar + mensagem honesta "tive um erro técnico, não é falta de permissão") de recusa de escopo, para não mascarar bug como trava.
- [ ] **Step 1:** Reescrever `_SYSTEM_BASE` (default = criar rascunho; menos "não posso").
- [ ] **Step 2:** Ajustar o catch-all p/ mensagem que separa erro técnico de escopo (e logar com nome da tool).
- [ ] **Step 3:** Deploy + smoke: pedir no chat "cria um comunicado avisando X" → deve criar rascunho e aparecer na Central.
- [ ] **Step 4:** Commit.

---

## Fase 2 (depois — não neste plano): largura
Converter os no-op restantes (calcular_folha, fechar_folha, concluir_admissao, registrar_evento_kit) + ampliar ações/leituras por módulo + revisar todos os `action_url` divergentes. Cada um = mesmo molde: `criar_rascunho(tipo)` + `registrar_executor`. Operacional só se o Jordan liberar.

## Self-Review
- Cobertura: cria (Task 2/5) ✓, tela única (Task 4) ✓, aprovar efetiva (Task 3) ✓, OTP dinheiro (Task 3) ✓, menos travas (Task 6) ✓, fail-closed admin único resolvido (propositor=agente, Task 2) ✓.
- Sem placeholder: cada task tem arquivos, interfaces e teste bench concreto.
- Consistência de tipos: `criar_rascunho`/`registrar_executor`/`executar_rascunho`/`EXECUTORES` usados igual em Tasks 2,3,5.
