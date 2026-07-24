# Peça 3 — Consultores IA escopados por perfil (RBAC/LGPD na camada cognitiva)
**Data:** 2026-07-24 · Antecede: peças 1+2 (Orquestrador Executivo no redesign, deployado). Régua: [[project_consultores_ia_rbac]]. Investigação: `.superpowers/sdd/investig-rbac-chat.md`.

## Objetivo (uma frase)
Dar a cada usuário um chat de IA cujo alcance é **exatamente** o que o RBAC + escopo do próprio perfil já permitem — enforçado na FONTE (token do usuário), nunca por prompt — do dono (cross-domínio) ao CLT (só sobre si, com justificar-ponto→DP).

## Princípio inegociável (a decisão de arquitetura)
**O chat SEMPRE roda com a identidade/token do próprio usuário.** O que ele enxerga = o que as camadas de enforcement que já existem permitem. **O LLM NUNCA é a fronteira de segurança** — um modelo instruído a "não olhar X" pode ser contornado; a fronteira é o RBAC no endpoint + o escopo na query. Fora do escopo = "aguardando dado" honesto, JAMAIS vazamento de outro posto/colaborador/módulo.

Três camadas de escopo que **empilham** naturalmente (o token carrega tudo):
- **Módulo** — `require_permission("module:X")` sobre `users.permissions[]`.
- **Posto** (líder) — `backend/modules/operacional/scope.py` (`users.employee_id` + `posts.leader_id`).
- **Self** (CLT) — `self:portal` / `employee_id` (endpoints do Portal já self-scoped).

## Matriz (gradiente ADITIVO sobre a base CLT)
Líder NÃO é classe à parte — é CLT + privilégio. Privilégios empilham:

| Perfil | Chat vê | Fonte de dado (já escopada) | Enforcement |
|---|---|---|---|
| **Diretoria** (jjesus, pjesus) | Orquestrador cross-domínio, **todas** as tools | panoramas globais | `role=admin` (bypass) |
| **Gestores** (Gonzaga, supervisor Paiva) | Orquestrador cross-domínio **FILTRADO** aos seus módulos (operacional, dp/RH, sst/SO, ged; +portal/ponto) | panoramas dos módulos permitidos | tools filtradas + `require_permission` na execução |
| **DEVs/Suporte** | Orquestrador cross-domínio **FILTRADO** a todos **exceto** financeiro/fiscal/contábil | idem | tools filtradas + `require_permission` |
| **Líderes** (Walcicley, Erika, Ediwilson) | Orquestrador escopado ao **SEU posto** (operacional/ponto) + base CLT | endpoints operacionais **posto-scoped** (scope.py) + portal self | tools filtradas + posto-scope + self |
| **CLT** (demais) | Orquestrador escopado a **SI**: própria escala, próprio ponto, portal; **justificar ajuste de ponto → DP aprova** | endpoints do Portal **self-scoped** (employee_id) | tools filtradas + self-scope |
| **CLIENTE** (condomínio, EXTERNO — Área do Cliente) | Orquestrador escopado ao **SEU condomínio**: contratos, notas fiscais, funcionários alocados; **buscar+entregar nota/boleto** | endpoints da Área do Cliente **condomínio-scoped** (`condominio_id`) | tools filtradas + condomínio-scope |

## Arquitetura — UM orquestrador escopado por usuário (todos os tiers, cross-domínio filtrado)
Decisão do dono (2026-07-24): **todos** ganham um cérebro cross-domínio — mas o alcance de cada um é filtrado. O modelo unifica em **um orquestrador escopado**, com DUAS travas por usuário:
1. **Conjunto de tools filtrado** — o LLM só recebe as tools cujos módulos ∈ `user_modules(user)` (gestor não vê tool de financeiro; líder só as posto-scoped; CLT só as self). O modelo nem pode *tentar* o que não tem.
2. **Execução com a identidade do usuário** — cada tool executa contra o endpoint interno **com o token/contexto do próprio usuário**, então `require_permission` (módulo) + `scope.py` (posto) + self (employee_id) barram na FONTE. Defesa em profundidade: filtro (belt) + RBAC na execução (suspenders).

**Achado runtime (investigação):** o Hermes hoje chama tools como UMA conta de serviço (`mcp-service`, admin) — sem identidade do usuário. Logo o Hermes-como-serviço só serve a **diretoria** (que vê tudo mesmo). Para os demais, a orquestração precisa carregar a identidade do usuário na execução das tools. Caminho recomendado:

- **Diretoria → Orquestrador Executivo via Hermes** (já deployado, todas as tools). Sem mudança.
- **Demais → ORQUESTRADOR ESCOPADO no backend** (novo componente): um loop de function-calling (LLM gpt-5) sobre as tools filtradas por `user_modules`, onde cada chamada de tool é executada pelo backend contra o endpoint/serviço interno **com o contexto de auth do próprio usuário** (não `mcp-service`). Reusa as DEFINIÇÕES de tool + a camada de garantia (groundedness/auditoria) + os endpoints existentes (que já aplicam RBAC/posto/self). NÃO depende do Hermes propagar identidade (o gap runtime) — a orquestração roda in-backend com a identidade real.
  - **Gestor/DEV:** tools dos seus módulos → panoramas org-wide DENTRO dos módulos permitidos.
  - **Líder:** tools operacionais/ponto **posto-scoped** (scope.py) + base CLT (self). A query já filtra pro posto dele — o LLM nunca recebe dado de outro posto.
  - **CLT:** tools **self-scoped** (Portal, employee_id) + a ação justificar-ponto. O LLM só vê o próprio dado.
  - **CLIENTE (externo, Área do Cliente):** tier EXTERNO — auth própria (email + senha = CNPJ do condomínio), identidade carrega `condominio_id`. Tools **condomínio-scoped**: contratos, NFS-e, funcionários alocados (todos filtrados por `condominio_id`, nunca outro condomínio) + a capacidade **buscar+entregar documento** (nota/boleto do próprio condomínio). Mesmo motor (orquestrador escopado), superfície externa.

**Ponto-chave de segurança:** o escopo é aplicado ANTES e DURANTE — o LLM só recebe no contexto o que os endpoints escopados retornam (posto/self/módulo), e nunca tem tool nem token para sair disso.

**Futuro (fora desta peça):** unificar tudo no Hermes propagando a identidade do usuário até o conector (aí diretoria e escopados usam o mesmo agente). Hoje: Hermes p/ diretoria + orquestrador escopado in-backend p/ os demais.

## Componentes

### 1. `user_modules(user) -> set[str]` — REUSAR+ADAPTAR (~15 linhas)
Novo helper (ex. `backend/core/auth/module_scope.py`). Reusa `users.role`+`users.permissions[]`:
- `role == "admin"` OU `"*"`/`"all"` em permissions → **TODOS** os módulos canônicos.
- senão → `{ p.split("module:")[1] for p in permissions if p.startswith("module:") }`.
Módulos canônicos (de `main_production.py:321-328`): financeiro, fiscal, dp, ged, juridico, crm, operacional, sst, dev. (dev/suporte já NÃO têm financeiro/fiscal → a régua "exceto 3 sensíveis" cai fora naturalmente das permissions; sem hardcode.)

### 2. `TOOL_MODULE: dict[str, str]` — CRIAR (fail-closed, padrão de `TOOL_RISK`)
Em `mcp-server/tool_risk_manifest.py`: mapa `nome_da_tool -> módulo`. Tool sem módulo declarado = **não aparece** (fail-closed, igual ao risco). Tools cross-domínio (briefing_executivo, consultar_viabilidade_contratacao, consultor_ceo, runway…) → módulo especial **`"diretoria"`** (só admin). Teste no manifesto: TODA tool tem módulo (espelha `test_toda_tool_esta_classificada`).
Allowlist efetiva por usuário = `tools_include()` (risco) ∩ `{ tool : TOOL_MODULE[tool] ∈ user_modules(user) ∪ {"diretoria" se admin} }`.

### 3. Orquestrador escopado no backend — CRIAR (o componente central)
Um endpoint user-facing (ex. `/consultores/chat/consultar {pergunta}`), `Depends(get_current_active_user)` (token do usuário, NÃO `_MCP_ALLOWED`):
- **admin** → delega ao Orquestrador Executivo (Hermes, todas tools) — já existe.
- **demais** → loop de function-calling in-backend: (a) `tools = tools_include() ∩ {t : TOOL_MODULE[t] ∈ user_modules(user)}`; (b) chama o LLM (gpt-5, via `consultor_hub`) com essas tools; (c) para cada tool-call, executa o **handler interno com o contexto de auth do próprio usuário** (o mesmo que os endpoints usam — `require_permission`/scope.py/self aplicam); (d) devolve o resultado ao LLM; itera com teto de iteração + budget; (e) síntese final passa pelo groundedness + auditoria (garantia 5.2a).
- Reusa: as definições de tool (as mesmas do conector), os handlers dos endpoints (que já enforçam), a garantia. NÃO reimplementa lógica de negócio.

### 3b. Auditar+completar os leitores escopados — CONFIRMAR/CRIAR
Antes de ligar líder/CLT: auditar se os endpoints operacionais (posto-scoped, scope.py) e do Portal (self-scoped) já entregam TUDO que o assistente do líder/CLT precisa (escala do posto, ponto do posto/self, justificativas). Onde faltar, **criar o leitor escopado** (dentro do escopo combinado — posto p/ líder, self p/ CLT; nunca além). Cada leitor novo herda o enforcement (scope.py/self), nunca retorna fora do escopo.

### 3c. Tier CLIENTE (externo) + capacidade buscar+entregar documento — CONFIRMAR/CRIAR
- **Auth:** auditar a Área do Cliente — como o cliente/condomínio autentica hoje (email + senha=CNPJ) e como a identidade carrega o `condominio_id`. O chat do cliente roda com ESSA identidade.
- **Leitores condomínio-scoped:** contratos, NFS-e, funcionários alocados — todos filtrados por `condominio_id` na fonte (auditar cobertura; criar o que faltar, dentro do escopo — nunca outro condomínio).
- **Capacidade buscar+entregar documento** (nota/boleto): tool que localiza o documento EXISTENTE do próprio condomínio (reusa geração/DocButtons — abrir-HTML/baixar-PDF) e o entrega no chat (link/anexo; e-mail/WhatsApp = opção futura). **Sem gate humano**: é o documento do próprio cliente, escopado, e boleto/nota = dinheiro que ENTRA (não sai). **EMITIR documento novo** (fiscal) fica FORA (seria ação interna/gated) — aqui só BUSCA o já existente.

### 4. Ação: justificar ajuste de ponto → DP aprova — padrão 🟡 propor→aprovar
CLT descreve a justificativa no chat → cria um registro **pendente** de ajuste/justificativa (status 'pendente'), roteado ao DP para aprovação (reusa o padrão `propor_*` do `consultor_mcp_controller`: grava pendente, NUNCA aplica). Só após aprovação do DP reflete em ponto/folha/RH. Idempotência + auditoria. NUNCA auto-aplica na folha.

### 5. Frontend (redesign) — reusa ChatScreen (peça 2)
- O módulo/card do chat aparece conforme o perfil (esconder card ≠ segurança, mas melhora UX; a fronteira real é o backend).
- ChatScreen já é genérico (endpoint+field configuráveis) → aponta pro endpoint escopado.
- Diretoria continua com o Orquestrador Executivo; demais recebem o módulo "Consultor IA" apontando ao endpoint escopado.

## Global Constraints (herdadas, inegociáveis)
- Token do próprio usuário sempre; enforcement na fonte; LLM nunca é a fronteira.
- Dinheiro que SAI / ato legal / folha = propor→aprovar+humano (justificar-ponto vai pro DP; nada auto).
- Operacional READ para o agente; escopo de posto/self barra outro posto/colaborador.
- Nunca fabricar; fora do escopo = "aguardando dado".
- Deploy: backend blue-green + baked; conector rebuild p/ TOOL_MODULE (fail-closed lint roda).

## Testabilidade / oráculos (o que PROVA a fronteira)
- **Gestor**: chat NUNCA retorna número de financeiro/fiscal — testar pergunta de caixa → "aguardando dado"/recusa, nunca o valor.
- **Líder**: pergunta sobre OUTRO posto → não retorna dado do outro posto (só o seu).
- **CLT**: pergunta sobre OUTRO colaborador → recusa/self only; a própria escala/ponto → retorna.
- **CLT ação**: justificar ponto → cria pendente 'pendente' p/ DP; NÃO altera ponto/folha até aprovação.
- Verificar pela ROTA da tela, com o TOKEN de cada perfil real (jjesus, gonzaga, um líder, um CLT), em bancada isolada (nunca in-process :8080).
- `TOOL_MODULE` fail-closed: tool nova sem módulo → não aparece (teste do manifesto).

## Fora de escopo (nomeado p/ não virar retalho)
- **Unificar tudo no Hermes** (propagar identidade do usuário do chat até o conector, p/ diretoria e escopados usarem o mesmo agente) — depois. Nesta peça: Hermes p/ diretoria + orquestrador escopado in-backend p/ os demais.
- Limpeza das contas Paiva `@conectamais` inativas (uma é admin inativo) — hygiene opcional.
- Sino real (peça 4).

## Riscos abertos
- **O loop de function-calling in-backend** (executar tool-handler com o contexto de auth do usuário) é o maior build novo — como injetar a identidade do usuário na execução do handler reusando o mesmo caminho dos endpoints (evitar duplicar lógica). Provável spike no início do plano.
- **Cobertura dos leitores escopados** (3b): auditar operacional/portal antes de ligar líder/CLT; pode faltar leitor posto/self.
- **Gestor org-wide dentro do módulo**: confirmar que gestor PODE ver org-wide no seu módulo (sim, não é posto-scoped); líder/CLT usam só os escopados.
- Latência do loop cross-domínio (múltiplas tools) — reusar o timeout de 180s já posto no nginx p/ `/consultores/`; considerar streaming futuro.
- **Tier CLIENTE (3c):** auditar a auth da Área do Cliente (email+senha=CNPJ→`condominio_id`) e a cobertura dos leitores condomínio-scoped ANTES de ligar; a tool de entrega de documento reusa a geração existente (nunca emite novo).

## Testes-oráculo adicionais (tier cliente)
- Cliente pergunta sobre OUTRO condomínio → nada (só o seu). Pede a própria nota/boleto → recebe o documento; pede documento de outro condomínio → recusa. Buscar≠emitir (nunca gera nota nova).

## Resumo de 1 linha
Um orquestrador cross-domínio por usuário, com tools filtradas por `user_modules` e executadas com a identidade do próprio usuário; o alcance = RBAC + posto + self + **condomínio (cliente externo)** que já existem, enforçado na fonte (belt+suspenders); diretoria via Hermes, demais via orquestrador escopado in-backend; ações (justificar-ponto→DP; buscar+entregar documento ao cliente) — fronteira no dado, nunca no LLM.
