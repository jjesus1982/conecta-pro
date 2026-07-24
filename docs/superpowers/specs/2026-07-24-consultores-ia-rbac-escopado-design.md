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
| **Diretoria** (jjesus, pjesus) | Orquestrador cross-domínio (Hermes, todas tools) | panoramas globais | `role=admin` (bypass) |
| **Gestores** (Gonzaga, supervisor Paiva) | Consultores dos seus módulos (operacional, dp/RH, sst/SO, ged; +portal/ponto) | panoramas dos módulos permitidos | `require_permission` |
| **DEVs/Suporte** | Consultores de todos os módulos **exceto** financeiro/fiscal/contábil | idem | `require_permission` (não têm as 3 perms sensíveis) |
| **Líderes** (Walcicley, Erika, Ediwilson) | base CLT **+** operacional/ponto do **SEU posto** | endpoints operacionais **posto-scoped** (scope.py) + portal self | posto-scope + self |
| **CLT** (demais) | Só **sobre si**: própria escala, próprio ponto, portal; **justificar ajuste de ponto → DP aprova** | endpoints do Portal **self-scoped** (employee_id) | self-scope |

## Arquitetura — surfaces diferentes por tier, todas token-enforçadas
Achado runtime (investigação): o Hermes chama tools como UMA conta de serviço (`mcp-service`, admin) — **sem identidade do usuário do chat**. Logo, a única superfície que pode usar o Hermes-como-serviço é a **diretoria** (que vê tudo mesmo). Todos os demais rodam **direct=True, com o token do próprio usuário**, atravessando o RBAC real:

- **Diretoria → Orquestrador Executivo** (já deployado): `gerar(origem="executivo", direct=False)` → Hermes → tools. Sem mudança.
- **Gestor/DEV → consultores de domínio** (`consultor_hub`, direct=True) só dos módulos que `user_modules(user)` retorna. Cada consultor gated por `require_permission` do seu módulo. Dado = panorama do módulo (org-wide dentro do módulo — gestor não é posto-scoped).
- **Líder → assistente do posto**: LLM sobre os endpoints operacionais/ponto **já posto-scoped** (scope.py, com o token do líder) + a base CLT (self). O LLM só recebe no contexto o dado do posto dele — nunca de outro posto, porque a query já filtra.
- **CLT → assistente pessoal**: LLM sobre os endpoints do Portal **já self-scoped** (employee_id) — própria escala/ponto/holerite. + ação **justificar ponto**.

**Ponto-chave de segurança:** para líder/CLT o LLM só vê no contexto o dado que os endpoints escopados retornam (posto/self). Escopo é aplicado ANTES do LLM, na query — o modelo nunca tem em mãos o que não pode ver.

## Componentes

### 1. `user_modules(user) -> set[str]` — REUSAR+ADAPTAR (~15 linhas)
Novo helper (ex. `backend/core/auth/module_scope.py`). Reusa `users.role`+`users.permissions[]`:
- `role == "admin"` OU `"*"`/`"all"` em permissions → **TODOS** os módulos canônicos.
- senão → `{ p.split("module:")[1] for p in permissions if p.startswith("module:") }`.
Módulos canônicos (de `main_production.py:321-328`): financeiro, fiscal, dp, ged, juridico, crm, operacional, sst, dev. (dev/suporte já NÃO têm financeiro/fiscal → a régua "exceto 3 sensíveis" cai fora naturalmente das permissions; sem hardcode.)

### 2. `TOOL_MODULE: dict[str, str]` — CRIAR (fail-closed, padrão de `TOOL_RISK`)
Em `mcp-server/tool_risk_manifest.py`: mapa `nome_da_tool -> módulo`. Tool sem módulo declarado = **não aparece** (fail-closed, igual ao risco). Tools cross-domínio (briefing_executivo, consultar_viabilidade_contratacao, consultor_ceo, runway…) → módulo especial **`"diretoria"`** (só admin). Teste no manifesto: TODA tool tem módulo (espelha `test_toda_tool_esta_classificada`).
Allowlist efetiva por usuário = `tools_include()` (risco) ∩ `{ tool : TOOL_MODULE[tool] ∈ user_modules(user) ∪ {"diretoria" se admin} }`.

### 3. Superfície de chat escopada — o endpoint
Um endpoint user-facing (ex. `/consultores/chat/consultar {pergunta}`), `Depends(get_current_active_user)` (token do usuário, NÃO `_MCP_ALLOWED`). Roteia por tier:
- admin → delega ao Orquestrador Executivo (Hermes).
- gestor/dev → consultor(es) de domínio (direct=True) dos módulos permitidos; a pergunta é roteada ao consultor do domínio pertinente (reusa personas do `consultor_mcp_controller`), com `require_permission` guardando cada um.
- líder → assistente posto-scoped (busca via endpoints operacionais scope.py) .
- clt → assistente self-scoped (busca via Portal endpoints) + ação de ponto.
Groundedness/auditoria (garantia 5.2a) valem em todos.

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
- **Hermes-orchestration escopado para gestores** (cérebro cross-domínio porém filtrado por usuário) — exige propagar a identidade do chat até o conector (o gap runtime). Fica p/ depois; hoje gestor = consultores de domínio.
- Limpeza das contas Paiva `@conectamais` inativas (uma é admin inativo) — hygiene opcional.
- Sino real (peça 4).

## Riscos abertos
- Roteamento pergunta→consultor de domínio (qual persona) p/ gestor: heurística vs classificador — provável reuso do roteamento existente.
- Endpoints operacionais/portal já retornam TUDO que o líder/CLT precisa via scope.py/self? Auditar cobertura antes (pode faltar um leitor posto-scoped p/ o assistente do líder).
- Consultor de domínio (panorama) é org-wide dentro do módulo — confirmar que gestor PODE ver org-wide no seu módulo (sim, gestor não é posto-scoped) mas líder/CLT NÃO usam esses panoramas (usam os escopados).

## Resumo de 1 linha
Um chat por usuário, rodando com o token dele; o alcance é o RBAC+posto+self que já existem, enforçado na fonte; diretoria=orquestrador, gestor/dev=consultores de domínio, líder=posto, CLT=self+justificar-ponto→DP — fronteira de segurança no dado, nunca no LLM.
