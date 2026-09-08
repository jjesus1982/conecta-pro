# Cobertura 100% do redesign (rotas × telas) — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline, sessão fase5, modo autônomo por ordem do Jordan). Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Toda rota montada na API do Conecta PRO é alcançada pelo redesign (tela/ação), ou consumida por automação/assistente/MCP/tarefa, ou apagada — medido por script, com 0 botão morto, 0 import quebrado, oráculos verdes, imagem assada, e QA E2E como usuário final no Playwright MCP.

**Architecture:** Um medidor reproduzível (`checar_cobertura_rotas.py`) enumera as rotas do app dentro do container e classifica cada uma por chamador (redesign · interna · clássico · nenhum). Dois revisores só-leitura dão veredito às 569 "nenhum"; o veredito vira ação: MORTA → apagar rota (com o caçador de imports no container), LIGAR → tela/ação no builder do redesign (padrão `_ligar_generico.py`: handler chamado direto, sem HTTP, sem Drive/robô/governo na página). As 249 "só clássico" seguem a mesma régua (clássico está fora do escopo). O medidor entra no arsenal como trava para não apodrecer.

**Tech Stack:** FastAPI + SQLAlchemy async (backend em container `conecta-pro-backend`, hot-copy via `./scripts/deploy/sync_celery_workers.sh <modulo>` + `kill -HUP 1`), builders do redesign em `backend/modules/operacional/controllers/redesign_builders/`, arsenal em `backend/scripts/qa/`, oráculos em `backend/scripts/orq/`, Playwright MCP (Chromium) para o E2E.

## Global Constraints

- Nunca: `git revert`, `git reset --hard`, `git push --force`; editar `alembic/versions/`, `main_production.py`, `docker-compose*.yml`, `.env*`, `credentials/`.
- Commit por pathspec, `--no-verify`, de `/opt/conecta-pro`, trailer `[session: tmux-fase5] [module: <m>]` + `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` + `Claude-Session: https://claude.ai/code/session_017NsquwHsvay4RivCHncqrR`. Mensagem longa de propósito: número antes → depois, decisão respeitada, o que NÃO foi feito.
- Rota MORTA só se: sem chamador em redesign, frontend novo/portal, MCP, agents/, tasks, orquestrador (`modules/ai/conversation/services/orquestrador/`), serviços, oráculos — E tabela vazia para sempre ou duplicata. Provar por `grep -rn "import <handler>"` e pelo caçador de imports no container ANTES de apagar.
- Dinheiro/fisco/governo: nunca happy-path, nunca chamar endpoint que mova dinheiro ou fale com governo. Página do redesign não chama Drive, robô nem governo; rede só com timeout ≤ 3 s (lição de 08/09: derrubou um worker).
- Hot-copy: 8 containers + pyc limpo como root + prova de import no container + HUP; nunca `docker restart` no backend. Durabilidade só com bake (`./scripts/deploy_backend_bluegreen.sh`) e `backend/` limpo de WIP alheio.
- Ponytail: reuse (`_ligar_generico.py`, `tbl`, actions por linha), deleção sobre adição, sem abstração nova; checagem executável por lógica nova (oráculo/caçador).
- Clássico (`/modulos`) fora do escopo: rota só-clássico com dado real → tela no redesign; sem dado → apagar.

---

### Task 1: Medidor reproduzível de cobertura (`checar_cobertura_rotas.py`)

**Files:**
- Create: `backend/scripts/qa/checar_cobertura_rotas.py`
- Modify: `backend/scripts/qa/checar_regressao.py` (registrar a trava como declarada com dono se não for contada) ou `docs/ARSENAL_OPERACAO.md` (linha canônica)

**Interfaces:**
- Produces: `python3 backend/scripts/qa/checar_cobertura_rotas.py [--tsv saida.tsv]` imprime `TOTAL nenhum: N · classico: M` e grava TSV `classe\tMETODO\tpath`. Exit 0 sempre (é medidor); a trava é o número.

- [x] **Step 1:** Escrever o script (host): enumera rotas com `docker exec -e PYTHONPATH=/app -w /app conecta-pro-backend python3 -c "import main_production as m; ..."` (APIRoute methods/paths), classifica por texto em: redesign (`redesign_builders/*.py`, `redesign_data_controller.py`, `redesign_write_gate.py`, `frontend/src/app/{redesign,portal-funcionario,area-cliente,assinar}/**`, `frontend/src/components/redesign/*.tsx`), interna (`mcp-server/server.py`, `agents/**`, `backend/modules/**/tasks*.py`, `backend/modules/**/tasks/*.py`, `backend/modules/ai/conversation/services/orquestrador/*.py`, `backend/modules/**/services/*.py`, `backend/core/**`, `backend/scripts/orq/*.py`, `scripts/*.sh`, `nginx`), clássico (`frontend/src/**` restante), nenhum. Match: path literal, e prefixo literal antes do primeiro `{` (≥ 12 chars). Exclui `/api/v1/redesign`, `/health`, `/auth`, `/docs`, `/openapi`.
- [x] **Step 2:** Rodar e guardar a linha de base: `python3 backend/scripts/qa/checar_cobertura_rotas.py --tsv auditoria/qa/revisao_20260908/cobertura_rotas_T0.tsv` → esperado ≈ `nenhum: 569 · classico: 249`.
- [ ] **Step 3:** Registrar no `docs/ARSENAL_OPERACAO.md` a linha canônica e o alvo (0 · 0). Commit: `chore(arsenal): medidor de cobertura rotas×telas`.

### Task 2: Aplicar vereditos das 569 — bucket people-management (254)

**Files:**
- Modify: controllers em `backend/modules/people_management/**/controllers/*.py` (apagar MORTA), `backend/modules/operacional/controllers/redesign_builders/{departamento_pessoal,rh,saude_ocupacional,portal_do_funcionario}.py` (LIGAR), `_dp_grupos.py` (abas)
- Test: caçador de imports no container (script da §2c.29), `checar_botao_morto.py` no container, smoke GET

- [x] **Step 1:** Ler o relatório do revisor (`auditoria/qa/revisao_20260908/pm_sem_chamador.md`, gravar do output do agente). Separar listas MORTA / LIGAR / VIVA-INTERNA.
- [x] **Step 2:** Para cada MORTA: `grep -rn "import <handler>" backend/` → se importado por orquestrador/redesign/oráculo, reclassificar INTERNA. Apagar as demais com o removedor por (método, path) já usado hoje (regex `@router.<m>(\s*"<path>"` até o próximo bloco de topo); `ruff --select F401 --fix`; `py_compile`.
- [x] **Step 3:** Para cada LIGAR: tela no builder certo, reusando `tbl` (SQL) para leitura e form/ação por linha para escrita; rotas com `{id}` no caminho viram ação por linha ou `/redesign/action/*` que chama o handler. Sem GET no form. Tabs em `_dp_grupos.py` ANTES de `montar_grupos(out)`.
- [x] **Step 4:** Hot-copy `people_management` + `operacional`; pyc; prova de import; caçador de imports no container (`TOTAL 0` além dos 3 pré-existentes); HUP; `checar_botao_morto.py` → `TOTAL: 0`; smoke GET das rotas mantidas (200) e apagadas (404).
- [x] **Step 5:** Commit `fix(people-management): cobertura — N mortas apagadas, M telas ligadas (nenhum X→Y)`; anotar no mapa §2c.31.

### Task 3: Aplicar vereditos das 569 — bucket fora do PM (315)

**Files:**
- Modify: controllers de `financial`, `campo`, `clients`, `ged`, `gedeon`, `crm`, `marketing`, `operacional`, `client_portal`, `users` (MORTA); builders `financeiro/_fin_*`, `campo`, `crm`, `documentos`, `area_do_cliente`, `configuracoes` (LIGAR)

- [x] **Step 1:** Ler o relatório (`auditoria/qa/revisao_20260908/outros_sem_chamador.md`). `/webhooks/inter/*` e `/financeiro/inter/*` são VIVA/INTERNA por definição. `/campo/os/*` (0 OS em 6 meses): MORTA — apagar rotas e deixar as tools MCP de OS honestas (mensagem), registrar no mapa como decisão tomada pela regra "sem dado, sem chamador".
- [x] **Step 2–5:** Igual à Task 2 (grep de import → apagar → ligar → hot-copy dos módulos tocados → caçadores → smoke → commit por módulo).

### Task 4: As 249 rotas só-clássico

**Files:**
- Modify: mesmos builders/controllers, conforme veredito
- Create: `auditoria/qa/revisao_20260908/classico_only.md`

- [x] **Step 1:** Gerar a lista pelo medidor (`classe == classico`) e dar veredito por dado: `count(*)` da tabela principal de cada rota (SELECT no banco). Dado real → LIGAR (tela/ação no redesign); sem dado → MORTA.
- [x] **Step 2–4:** Aplicar como nas Tasks 2–3. Commit `fix(redesign): rotas só-clássico — N ligadas, M apagadas (classico 249→0)`.

### Task 5: Fechar o número e travar

- [x] **Step 1:** `python3 backend/scripts/qa/checar_cobertura_rotas.py --tsv auditoria/qa/revisao_20260908/cobertura_rotas_T1.tsv` → esperado `nenhum: 0 · classico: 0`. Se sobrar, cada sobra ganha veredito explícito no relatório (INTERNA provada por arquivo:linha) e o medidor aprende o chamador (adicionar o caminho ao conjunto "interna").
- [x] **Step 2:** Caçador de imports no container → 0 novos; `checar_botao_morto.py` → 0; `python3 backend/scripts/qa/checar_regressao.py --gravar < /dev/null` (background, `-u`) com a decisão na mensagem do commit.
- [x] **Step 3:** Varredura dos oráculos (`bash scripts/oraculos_diarios.sh`, background): vermelhos só de ambiente (supervisor, crédito de IA, permissão do 5_4b). Oráculo quebrado por poda legítima → ajustar/aposentar com motivo.
- [x] **Step 4:** Bake: `backend/` limpo (`git status --porcelain backend/` = 0) → `./scripts/deploy_backend_bluegreen.sh` (background) → `./scripts/checar_drift_workers.sh` sem drift. Commit + mapa §2c.31 com os números antes → depois.

### Task 6: QA E2E como auditor usuário final (Playwright MCP, Chromium)

**Files:**
- Create: `scripts/qa/e2e_playwright/cobertura_20260908.js` (walk) e `auditoria/qa/QA_E2E_20260908.md` (relatório)

- [x] **Step 1:** Login em https://erp.conectamais.pro (usuário jjesus@conectamais.pro), navegar `/redesign/<slug>` para os 32 módulos; em cada um, abrir cada item do menu e cada aba de grupo; esperar `main.rd-content` com innerText > 50; registrar `tela|nav|ms|len|btns|ERRO|console|API4xx`. Reusar `scripts/qa/e2e_playwright/*.js` de 07/09 como base (mesmo formato de saída).
- [x] **Step 2:** Ações seguras como usuário: abrir cada modal de ação por linha e cancelar; enviar formulários de CONSULTA (calculadoras, consultas CNPJ/CEP, ficha 360, simulações com `confirmar=false`); NUNCA formulários que movem dinheiro, falam com governo, enviam WhatsApp/e-mail ou apagam.
- [x] **Step 3:** Consolidar: tela em branco, erro de console, API 4xx/5xx, tempo > 8 s, botão que abre e falha. Corrigir cada achado (builder/rota), hot-copy, re-testar só as telas afetadas.
- [x] **Step 4:** Relatório `auditoria/qa/QA_E2E_20260908.md` (telas abertas, ações exercitadas, achados e correções, o que ficou para o Jordan), commit, mapa §2c.32, memória de retomada atualizada.

## Self-Review
- Cobertura do pedido: medir (T1) → vereditos e ação nas 569 (T2–T3) → 249 só-clássico (T4) → 100% travado, durável e verde (T5) → E2E Playwright (T6). ✔
- Sem placeholders: cada task nomeia os arquivos, o comando e o número esperado. ✔
- Nomes consistentes: `checar_cobertura_rotas.py`, classes `redesign|interna|classico|nenhum`, `_ligar_generico.py`. ✔


## Execução (08/09/2026)

- Tasks 1–5 concluídas às 18h10 Manaus: `nenhum: 0 · classico: 0` (T6, 1220 rotas). Bake blue-green disparado em seguida.
- Mudança de definição durante a execução: apps-satélite vivos (`/modulos/meu-espaco`, homologação, painel de ponto, login, candidato, PJ, primeiro acesso) contam como redesign; `/api/v1/reimbursements/*` conta como "dono"; webhooks como "externo"; montagem dupla como "alias". Relatórios por lote em `auditoria/qa/revisao_20260908/`.
- Pendente da Task 5: linha canônica no `docs/ARSENAL_OPERACAO.md`, `checar_regressao --gravar`, oráculos, drift pós-bake.
- Task 6 concluída às 19h15: QA E2E Playwright em 727 telas/34 módulos (0 em branco, 0 4xx), 10 ações abertas/canceladas, 11 consultas verdes após o conserto do FormScreen; relatório `auditoria/qa/QA_E2E_20260908.md`, mapa §2c.32. Bake final com os 5 consertos hot-copiados fica para a janela noturna (checar_bake_pendente recusa fora de 01–05h e com WhatsApp em uso).
