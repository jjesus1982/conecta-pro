# Paridade CRUD do DP redesign — Implementation Plan

> **For agentic workers:** implementar task-a-task. Steps usam checkbox (`- [ ]`). **Verificação = curl (rota real 200/201) + browser (clicar e ver acontecer)** — este codebase não tem pytest para builders/UI (o oráculo é a rota+tela, não teste unitário).

**Goal:** dar ao redesign do DP as mesmas capacidades do clássico (criar/ver/editar/admitir/agir), tela por tela, usando endpoints reais.

**Architecture:** builder `redesign_builders/departamento_pessoal.py` define as telas (tabelas + forms). FormScreen posta `{...vals}` direto no endpoint (Bearer). Fundação nova: `editfn(r)` no `tbl` → botão "Editar" por-linha que abre form pré-preenchido → PATCH. Deploy: docker cp (teste) + bake coordenado (durável).

**Tech Stack:** FastAPI (backend builder/handlers), Next.js/React (ModuleView.tsx foundation), PostgreSQL.

## Global Constraints
- Só endpoints REAIS; nunca inventar ação/dado (oráculo: exibido==banco).
- Dinheiro/OTP e operacional intocáveis; folha sensível.
- Commit por pathspec, SÓ meus arquivos (`departamento_pessoal.py`, `ModuleView.tsx`, handlers em `redesign_data_controller.py`). NÃO tocar `_fin_*`, financial, banking (T1).
- Commit ANTES de deploy; coordenar bake com T1; bracket-trick p/ checar deploy.
- Cada tarefa termina com verificação (curl + browser) — sem "ok" sem prova.

---

### Task 1: Fundação — mecanismo per-row Editar (ModuleView)

**Files:**
- Modify: `frontend/src/components/redesign/ModuleView.tsx` (TableScreen — adicionar botão "Editar" por-linha + form inline pré-preenchido)
- Modify: `backend/modules/operacional/controllers/redesign_data_controller.py` (helper `edit(endpoint, fields)` ao lado de `doc()`, opcional — ou o builder monta o dict direto)

**Interfaces:**
- Produces: no builder, `tbl(..., editfn=lambda r: {"endpoint": "/api/v1/.../{id}", "method":"PATCH", "fields":[{"key","label","type","value"}]})`. ModuleView: se `row.edit` presente, renderiza botão "Editar" que abre um form pré-preenchido com `field.value`, submete PATCH `{...vals}`, mostra msg.

- [ ] **Step 1: tbl aceita editfn** — em `redesign_data_controller.py`, no `_helpers`/`tbl`, aceitar `editfn=None`; se presente, `row["edit"]=editfn(r)` (como `docsfn`→`row["docs"]`). Retrocompatível.
- [ ] **Step 2: ModuleView renderiza o botão + form** — em TableScreen, se `row.edit`, adicionar botão "Editar" (na coluna Documento ou nova). onClick abre um painel/modal com os `fields` pré-preenchidos (`value`), submit → `fetch(edit.endpoint, {method: edit.method||'PATCH', body: JSON.stringify(vals)})` com Bearer; sucesso→toast + refetch da tela.
- [ ] **Step 3: build + deploy** — `npx next build` (frontend) + docker cp; builder via docker cp backend. BUILD_ID host==container.
- [ ] **Step 4: verificar no browser** — numa tela com editfn de teste, clicar "Editar", alterar um campo, salvar → confirmar PATCH 200 + dado mudou no banco (query).
- [ ] **Step 5: commit** — `git commit --no-verify -- frontend/src/components/redesign/ModuleView.tsx backend/modules/operacional/controllers/redesign_data_controller.py`

### Task 2: Admissão — form nova-admissao + religar CTAs

**Files:**
- Modify: `backend/modules/operacional/controllers/redesign_builders/departamento_pessoal.py` (EXTRA_MENU + form `nova-admissao` + `ctaTo` em visao/funcionarios/admissao) — *já prototipado*

**Interfaces:**
- Consumes: `POST /api/v1/people-management/hr/admissions` (candidate_name*, cpf*, position*, department, salary_proposed, expected_start_date, contract_type, birth_date, pis_pasep, notes).

- [ ] **Step 1: form + menu + ctaTo** — (feito no protótipo) confirmar `out["nova-admissao"]` (type=form, fields, submit→/hr/admissions), EXTRA_MENU item, `ctaTo="nova-admissao"` nos 3.
- [ ] **Step 2: deploy builder** — docker cp + restart backend.
- [ ] **Step 3: curl-verificar create** — `POST /hr/admissions` com candidato de TESTE (nome/cpf fake claramente de teste) → 201; depois DELETE/limpar o teste (não sujar dado real). OU validar só o 422/409 (payload inválido) sem criar — decidir p/ não poluir.
- [ ] **Step 4: browser** — /redesign/departamento-pessoal?t=funcionarios → botão "Nova admissão" agora navega pro form; preencher obrigatórios → "Abrir admissão" → 201/toast.
- [ ] **Step 5: commit** — pathspec do builder.

### Task 3: funcionarios — Ver/Editar por-linha

**Files:**
- Modify: `departamento_pessoal.py` (tela `funcionarios`: `editfn` → PATCH /hr/employees/{id} com campos editáveis: nome, cargo, cpf, status, etc.)

**Interfaces:**
- Consumes: `PATCH /api/v1/people-management/hr/employees/{employee_id}`. Verificar schema (quais campos aceita) antes.

- [ ] **Step 1: mapear PATCH /hr/employees schema** — ler o controller/schema (campos editáveis).
- [ ] **Step 2: editfn na tela funcionarios** — `editfn=lambda r: {"endpoint": f"/api/v1/people-management/hr/employees/{r[id]}", "method":"PATCH", "fields":[{"key":"nome","value":r[nome],...},...]}`. Incluir employee_id no SELECT.
- [ ] **Step 3: deploy + curl** — PATCH um employee de teste (mudar um campo inócuo, ex.: observação) → 200 + reverter.
- [ ] **Step 4: browser** — clicar "Editar" numa linha de funcionário → form pré-preenchido → alterar → salvar → 200.
- [ ] **Step 5: commit.**

### Task 4: Religar CTAs mortos das demais telas

- [ ] **Step 1:** varrer /data/departamento-pessoal por telas com `cta` e `ctaTo=None`.
- [ ] **Step 2:** para cada, apontar `ctaTo` pro form/ação certo (criar o form se não existir, via endpoint real).
- [ ] **Step 3:** browser: cada CTA navega/age.
- [ ] **Step 4: commit.**

### Task 5: aviso-previo + telas restantes (loop)

Para cada tela restante (aviso-previo, beneficios, certificacao, contratos, documentos, esocial, licencas, reembolsos, folha-rubricas, ...):
- [ ] mapear a capacidade do clássico → endpoint real;
- [ ] wirar (form de tela / per-row doc/edit / CTA);
- [ ] curl + browser;
- [ ] commit por tela.
Medir progresso: telas com capacidade real / total.

---

## Self-Review
- **Cobertura do spec:** fundação per-row-edit (Task 1) ✓; admissão (Task 2) ✓; funcionarios editar (Task 3) ✓; CTAs mortos (Task 4) ✓; demais telas (Task 5) ✓. Todas as seções do spec têm task.
- **Placeholders:** Task 5 é um loop por tela (não placeholder — é o padrão repetido; cada iteração mapeia clássico→endpoint→wira→verifica). Os endpoints exatos por tela se descobrem na iteração (não dá pra listar 15 telas × endpoints aqui sem investigar cada — isso é o trabalho da task).
- **Consistência:** `editfn`/`row.edit` usado igual em Task 1 (define) e Task 3 (consome).
