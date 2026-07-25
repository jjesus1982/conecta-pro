# DP redesign — fechar paridade (grupo A + B-mine) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (ou subagent-driven-development). Steps usam checkbox `- [ ]`. **Este codebase NÃO tem pytest para builders/UI** — o oráculo é `curl` (rota real 200/201/422/404) + **browser** (botão/form aparece e abre). Sem "ok" sem prova.

**Goal:** ligar no DP redesign as capacidades secundárias que o clássico tem e o redesign não, reusando a fundação já baked, sem tocar money-out (é do T1).

**Architecture:** override em `redesign_builders/departamento_pessoal.py` (tabelas/forms/ações) + fundação `ModuleView.tsx` (per-row action + FormScreen multipart, já baked). Endpoints que usam query/path param (não JSON body) ganham um handler fino `rd_action_*` em `redesign_data_controller.py`.

**Tech Stack:** FastAPI (builder/handlers), Next.js/React (ModuleView), PostgreSQL. Deploy: docker cp (teste) + bake (durável). Auth: :8080 form-urlencoded, token localStorage.

## Global Constraints
- Só endpoint REAL; nunca inventar ação/dado (oráculo exibido==banco).
- **Money-out = T1** (em `financeiro.py`, gated OTP): folha CLT PIX, folha PJ, diaristas, boleto/pix/ted/darf/gps, e o **pagar** de rescisão/reembolso. NÃO tocar no meu builder. [[feedback_money_out_t1_boundary]]
- **Nunca happy-path que muta dado real** (reject/analyze/import/gerar-lote/prestador/fechar-mes/eSocial disparam efeito) → provar por 422/404 em payload/id inválido + browser (botão/form abre). Exceção: create reversível pode usar dado de TESTE óbvio e limpar depois — decidir por task.
- Commit por pathspec (`departamento_pessoal.py`, `ModuleView.tsx`, `redesign_data_controller.py`). NÃO tocar `_fin_*`/financial/banking (T1). Commit antes de deploy; coordenar bake com T1 no lock `/tmp/conecta_deploy.lock`; bake batched (OOM: blindar oom_score_adj=-1000, evitar `next build` supérfluo).
- eSocial SST = ato legal: **propor→aprovar, nunca auto-transmitir**.

---

## Task 0: Fundação — N ações por-linha (ModuleView)

**Files:**
- Modify: `frontend/src/components/redesign/ModuleView.tsx` (TableScreen: renderizar N botões de ação por-linha via `row.actions`)
- Modify: `backend/modules/operacional/controllers/redesign_data_controller.py` (`_helpers.tbl`: aceitar `actionsfn` → `row["actions"]`)

**Interfaces:**
- Produces (backend): `tbl(..., actionsfn=lambda r: [ {title,endpoint,method,btnLabel,btnStyle,submitLabel,okMsg,fields:[...]}, ... ])` → cada item vira um botão. `None` no item é filtrado (ação condicional por status). Retrocompatível: `editfn` (1 ação, `row.edit`) segue igual.
- Produces (frontend): TableScreen renderiza um `<button>` por item de `row.actions` (usa `btnLabel`/`btnStyle` de cada), `onClick` → `setEditRow(action)` (mesmo modal já existente). `row.edit` continua funcionando.

- [ ] **Step 1: backend `tbl` aceita `actionsfn`** — em `redesign_data_controller.py`, no `_helpers.tbl`, ao lado de `editfn`: `if actionsfn: acts=[a for a in (actionsfn(r) or []) if a]; if acts: row["actions"]=acts`. Assinatura vira `tbl(..., docsfn=None, editfn=None, actionsfn=None)`.
- [ ] **Step 2: frontend renderiza os botões** — em TableScreen, `hasRowActions = allRows.some(r=>Array.isArray(r.actions) && r.actions.length)`; incluir em `hasActions`. Na coluna de ações, além de `row.edit`, mapear `row.actions`:
```tsx
{Array.isArray(row.actions) && row.actions.map((a:any, k:number) => (
  <button key={k} type="button" className={`rd-btn ${a.btnStyle==='primary'?'rd-btn-primary':'rd-btn-outline'}`} style={{ padding:'5px 10px', fontSize:12 }}
    onClick={() => { setEditRow(a); const v:Record<string,any>={}; (a.fields||[]).forEach((f:any)=>{v[f.key]=f.value??'';}); setEditVals(v); setEditMsg(null); }}>
    {a.btnLabel || 'Ação'}
  </button>
))}
```
- [ ] **Step 3: build + deploy frontend** — `NODE_OPTIONS=--max-old-space-size=6144 npx next build` (background, checar `free -h`); purge static + docker cp (skill deploy-bake, seção frontend). BUILD_ID host==container.
- [ ] **Step 4: verificar retrocompat no browser** — abrir `/redesign/departamento-pessoal?t=ferias` (hoje usa editfn "Aprovar") → botão ainda aparece e abre. Sem regressão.
- [ ] **Step 5: commit** — `git commit --no-verify -- frontend/src/components/redesign/ModuleView.tsx backend/modules/operacional/controllers/redesign_data_controller.py`

---

## Task 1: férias — migrar p/ actionsfn (Aprovar + Rejeitar)

**Files:** Modify `departamento_pessoal.py` (bloco ferias no try do build); Modify `redesign_data_controller.py` (handler `rd_action_vacation_reject`).

**Interfaces:**
- Consumes: `POST /api/v1/people-management/hr/vacations/{id}/approve` (sem body); reject usa `POST /vacations/{id}/reject?reason=` (reason é **query**, não body) → por isso o handler fino.
- Produces: handler `POST /api/v1/redesign/action/vacation-reject` body `{vacation_id, reason}` → chama `VacationService.reject_vacation`.

- [ ] **Step 1: handler rd_action_vacation_reject** — em `redesign_data_controller.py`, ação que recebe `{vacation_id, reason}` (JSON), chama `VacationService(db).reject_vacation(vacation_id, rejected_by_id=user.id, reason=reason)`, `await db.commit()`, retorna `{ok:True, message:"Férias rejeitada"}`. (Espelha o approve; reason vira texto do motivo.)
- [ ] **Step 2: ferias vira actionsfn** — substituir o `editfn=_fer_edit` atual por `actionsfn=_fer_acts` que retorna, p/ status SUBMITTED, `[aprovar, rejeitar]`:
  - aprovar = o dict atual (POST `/vacations/{id}/approve`, fields:[], btnLabel "Aprovar", btnStyle primary).
  - rejeitar = `{title:f"Rejeitar férias de {nome}", endpoint:"/api/v1/redesign/action/vacation-reject", method:"POST", btnLabel:"Rejeitar", submitLabel:"Rejeitar", okMsg:"Férias rejeitada", fields:[{key:"vacation_id",type:"hidden"?...}]}` — **incluir vacation_id**. Nota: o modal manda `{...editVals}`; pré-preencher `vacation_id` via `value=r[0]` num field oculto OU embutir no endpoint. Decisão: field `{key:"vacation_id","value":str(r[0]),"type":"text","span":"span 2","label":"ID"}` visível-mas-fixo, ou adicionar suporte a `type:"hidden"` no FormScreen edit-modal (1 linha). **Recomendo type:"hidden"** (limpo) — adicionar no modal render (Task 0 pode incluir, ou aqui).
  - status ≠ SUBMITTED → `[]`.
- [ ] **Step 3: deploy backend** (docker cp + restart) + `curl`:
  - reject com id fake → handler responde erro controlado (não 500). approve fake id → 400 "não encontrada".
  - endpoint da tela: `ferias` linhas SUBMITTED têm `actions` com 2 itens.
- [ ] **Step 4: browser** — `?t=ferias`: cada pendente mostra **Aprovar + Rejeitar**; abrir Rejeitar → campo motivo; **cancelar** (não submeter — não rejeitar real). Confirmar banco SUBMITTED inalterado.
- [ ] **Step 5: commit** (pathspec).

---

## Task 2: certificação — actionsfn (Certificar + Rejeitar)

**Files:** Modify `departamento_pessoal.py` (bloco certificacao).

**Interfaces:** Consumes `PATCH /api/v1/people-management/certifications/{id}/reject` body `{observacao}` (obrigatório, JSON — **fits editfn direto**, sem handler).

- [ ] **Step 1: certificacao vira actionsfn** — p/ status pendente, retornar `[certificar, rejeitar]`:
  - certificar = dict atual (PATCH `/certifications/{id}/certify`, field observacao opcional).
  - rejeitar = `{title:f"Rejeitar certificação — {comp}", endpoint:f"/api/v1/people-management/certifications/{id}/reject", method:"PATCH", btnLabel:"Rejeitar", submitLabel:"Rejeitar", okMsg:"Certificação rejeitada", fields:[{key:"observacao","label":"Motivo (obrigatório)","type":"textarea","span":"span 2","value":""}]}`.
- [ ] **Step 2: deploy + curl** — reject fake id → 404 "não encontrada" (rota real). tela: pendentes têm 2 actions.
- [ ] **Step 3: browser** — abrir Rejeitar numa pendente → campo motivo → cancelar (não rejeitar real).
- [ ] **Step 4: commit.**

---

## Task 3: benefícios — actionsfn (Gerir + Remover) + form Adicionar

**Files:** Modify `departamento_pessoal.py` (bloco beneficios + novo form `nova-beneficio`).

**Interfaces:** Consumes `DELETE /api/v1/people-management/hr/benefits/{id}` (cancel_benefit); `POST /api/v1/people-management/hr/benefits` (BenefitCreate: employee_id* UUID, type* BenefitType{vale_transporte,vale_refeicao,vale_alimentacao,plano_saude,plano_odontologico,seguro_vida,auxilio_creche,gym_pass,other}, provider, plan_name, employee_contribution float, company_contribution float, start_date, end_date, card_number, notes).

- [ ] **Step 1: beneficios actionsfn** — trocar editfn por actionsfn retornando `[gerir, remover]`:
  - gerir = dict atual (PATCH status).
  - remover = `{title:f"Remover benefício — {nome}", endpoint:f"/api/v1/people-management/hr/benefits/{id}", method:"DELETE", btnLabel:"Remover", btnStyle:"outline", submitLabel:"Remover", okMsg:"Benefício removido", fields:[]}` (modal = confirmação; DELETE sem body).
- [ ] **Step 2: form Adicionar** — `out["nova-beneficio"]` (type=form, POST `/api/v1/people-management/hr/benefits`), fields: employee_id (select ativos, reusar `_eopts`), type (select 9 valores acima), provider, plan_name, company_contribution, employee_contribution, start_date, end_date, notes. CTA na tela beneficios: `out["beneficios"]["cta"]="Adicionar benefício"; ["ctaTo"]="nova-beneficio"`.
- [ ] **Step 3: deploy + curl** — DELETE fake id → 404. POST benefits com body inválido (sem employee_id/type) → 422.
- [ ] **Step 4: browser** — beneficios: cada linha tem Gerir + Remover; CTA "Adicionar" abre form (colaboradores + tipos reais). Abrir Remover → cancelar (não deletar real).
- [ ] **Step 5: commit.**

---

## Task 4: reembolsos — actionsfn (Aprovar + Analisar) + anexos

**Files:** Modify `departamento_pessoal.py` (bloco reembolsos: actionsfn + docsfn de anexos + form anexar).

**Interfaces:** Consumes `POST /api/v1/people-management/hr/reimbursements/{id}/analyze`; `GET /api/v1/people-management/hr/reimbursements/{id}/attachments` (lista); `GET /api/v1/people-management/hr/reimbursements/attachments/{aid}/download`; `POST /api/v1/people-management/hr/reimbursements/{id}/attachments` (multipart). **NÃO** o pagar (T1).

- [ ] **Step 1: actionsfn (Aprovar + Analisar)** — p/ status pendente: `[aprovar (dict atual), analisar]`. analisar = `{title:"Analisar reembolso {code}", endpoint:f".../reimbursements/{id}/analyze", method:"POST", btnLabel:"Analisar", btnStyle:"outline", okMsg:"Reembolso em análise", fields:[]}` (confirmar no Step 3 se analyze pede body).
- [ ] **Step 2: anexos por-linha** — `docsfn` que busca os anexos do request (via subquery/segunda chamada) e devolve `doc("Anexo", f".../attachments/{aid}/download", fmt="pdf", gate="dp")` por anexo. Se a listagem exigir chamada por request (N+1), fazer 1 query SQL nos attachments (tabela `reimbursement_attachments`) no build. **Step do plano: mapear a tabela/coluna dos anexos** (`grep -rn "reimbursement_attachments\|class ReimbursementAttachment" backend/modules/reimbursement/models/`).
- [ ] **Step 3: form Anexar** — `out["nova-anexo-reembolso"]`? Melhor: anexar é por-request (precisa do request_id). Como o form de tela não tem contexto de linha, modelar como ação por-linha `type:file` no modal: editfn/action com `fields:[{key:"file",type:"file"}]` + `submit.multipart`. **Requer o modal de ação suportar multipart** (hoje o edit-modal manda JSON). Decisão: estender o edit-modal p/ multipart quando a ação tem `multipart:true` (espelhar o que já fiz no FormScreen) OU deixar anexar via tela-form com select de request. **Recomendo: adiar o UPLOAD de anexo** (ver-anexos já entrega valor); anexar entra como sub-item se o modal-multipart valer a pena. Registrar decisão no Step.
- [ ] **Step 4: deploy + curl** — analyze fake id → 404/400; GET attachments de um request real → 200 (leitura, ok). 
- [ ] **Step 5: browser** — reembolsos: pendentes com Aprovar + Analisar; linhas com anexo mostram botão de download.
- [ ] **Step 6: commit.**

---

## Task 5: certificação gerar-lote + férias sync Sólides (forms/ações de tela)

**Files:** Modify `departamento_pessoal.py` (2 forms); Modify `redesign_data_controller.py` (handlers `rd_action_cert_gerar_folha`, `rd_action_vacation_sync`).

**Interfaces:** Consumes `POST /api/v1/people-management/certifications/gerar-folha/{competencia}` (competencia = **path**); `POST /api/v1/people-management/hr/vacations/sync-solides`. Ambos precisam de handler fino (path param / gatilho).

- [ ] **Step 1: handlers** — `rd_action_cert_gerar_folha` body `{competencia}` → chama o endpoint/serviço com a competência no path. `rd_action_vacation_sync` (sem body) → chama sync-solides.
- [ ] **Step 2: forms** — `out["gerar-certificacoes"]` (form, select de competências com folha — reusar query de `contracheques-lote`) submit→`/redesign/action/cert-gerar-folha` com `submit.confirm`. `out["sync-ferias-solides"]` (form de confirmação, submit→`/redesign/action/vacation-sync`, `submit.confirm`). CTAs nas telas certificacao/ferias (ou itens no EXTRA_MENU).
- [ ] **Step 3: deploy + curl** — gerar-folha com competência inexistente → resposta controlada; sync com credencial ausente → erro honesto (não 500).
- [ ] **Step 4: browser** — abrir os 2 forms; confirmar select/confirm aparece. **Não** submeter gerar-lote real (gera certificações). 
- [ ] **Step 5: commit.**

---

## Task 6: funcionários — Importar cadastro (multipart)

**Files:** Modify `departamento_pessoal.py` (form `importar-cadastro` + CTA na tela funcionarios).

**Interfaces:** Consumes `POST /api/v1/people-management/hr/employees/import-cadastro` multipart `file: UploadFile` (CSV do contador/Onvio). Reusa FormScreen `type:file` + `submit.multipart` (já baked).

- [ ] **Step 1: form** — `out["importar-cadastro"]` = form multipart: `submit:{endpoint:".../hr/employees/import-cadastro", multipart:True, titleFromFile:False, okMsg:"Cadastro importado"}`, fields `[{key:"file",label:"Planilha (CSV)*",type:"file",span:"span 2",accept:".csv"}]`. CTA em funcionarios: `["cta"]="Importar cadastro"; ["ctaTo"]="importar-cadastro"`.
- [ ] **Step 2: deploy + curl** — POST sem file → 422 (rota valida `file` obrigatório).
- [ ] **Step 3: browser** — CTA abre form com input de arquivo (accept .csv). **Não** subir arquivo real (cria/altera cadastros).
- [ ] **Step 4: commit.**

---

## Task 7: prestadores-pj — tela nova (Fase 2)

**Files:** Modify `departamento_pessoal.py` (tela `prestadores-pj` table + form + item de menu).

- [ ] **Step 1: MAPEAR endpoint/schema** — `grep -rn "prestadores-pj\|prestadores_pj\|PrestadorPJ" backend/modules/people_management/human_resources/` — achar controller (list/create/regenerar-link), schema de create, e a tabela/colunas p/ o SELECT da lista. Confirmar prefixo montado (`/api/v1/people-management/human-resources/prestadores-pj`).
- [ ] **Step 2: table** — `await safe("prestadores-pj", tbl("Prestadores PJ", ..., cols reais, SELECT da tabela, rowfn))` + item no EXTRA_MENU (id "prestadores-pj").
- [ ] **Step 3: form create** — `out["novo-prestador-pj"]` (POST create) com campos do schema mapeado; CTA na tela.
- [ ] **Step 4: ação regenerar-link** — actionsfn por-linha `POST .../{id}/regenerar-link` (fields:[]).
- [ ] **Step 5: deploy + curl** — list 200; create body inválido → 422; regenerar fake id → 404.
- [ ] **Step 6: browser** — tela aparece no menu, lista, CTA abre form, ação regenerar aparece.
- [ ] **Step 7: commit.**

---

## Task 8: ponto fechar-mês (gated, Fase 3)

**Files:** Modify `departamento_pessoal.py` (ação/form fechar-mês na tela fechamento-ponto); talvez handler.

- [ ] **Step 1: MAPEAR endpoint** — `grep -rn "fechar-mes\|fechar_mes\|fechamento" backend/modules/people_management/*/controllers/*ponto*.py` — achar rota, params (provável `{mes}/{ano}` path), e se dispara efeito. Respeitar TZ canônico (UTC no banco, [[project_ponto_tz_canonico]]).
- [ ] **Step 2: form/ação com confirm** — form `fechar-mes-ponto` (select mês/ano) → handler `rd_action_ponto_fechar` (path param) com `submit.confirm` (irreversível-avisado). CTA na tela fechamento-ponto.
- [ ] **Step 3: deploy + curl** — fechar mês já-fechado/ inexistente → resposta controlada (não 500).
- [ ] **Step 4: browser** — form abre, confirm aparece. **Não** fechar mês real.
- [ ] **Step 5: commit.**

---

## Task 9: eSocial SST propor→aprovar (gated, Fase 3)

**Files:** Modify `departamento_pessoal.py` (tela esocial: ação Propor + Aprovar/Transmitir); possivelmente handlers.

- [ ] **Step 1: MAPEAR endpoints** — `grep -rn "@router" backend/modules/people_management/sst/controllers/*esocial*.py` + `grep -rn "S-2220\|S-2230\|S-2240\|transmitir" backend/modules/people_management/sst/`. Descobrir: existe estado "proposta pendente" no backend, ou o gancho precisa ser criado? Se não existir, **esta task vira 2 sub-tasks** (backend do estado-proposta primeiro).
- [ ] **Step 2: ação Propor** — actionsfn/form que GRAVA proposta pendente (NÃO transmite). btnLabel "Propor evento".
- [ ] **Step 3: ação Aprovar/Transmitir** — segunda ação humana, só em propostas pendentes, que chama o transmitir real. `submit.confirm`. **Nunca auto** — as duas ações são atos humanos separados. [[project_esocial_duas_vias]] [[project_fase5.3_proativo]]
- [ ] **Step 4: deploy + curl** — propor/transmitir fake id → 404; confirmar que Propor NÃO transmite (checar estado no banco).
- [ ] **Step 5: browser** — Propor aparece; após propor (teste seguro?), Aprovar aparece. Se transmitir dispara gov real, **não** submeter — só verificar render + rota.
- [ ] **Step 6: commit.**

---

## Self-Review
- **Cobertura do spec:** Grupo 1 (rejeitar/remover/analisar)=Tasks 1,2,3,4 ✓; Grupo 2 (sync/gerar-lote/adicionar/importar)=Tasks 5,3,6 ✓; Grupo 3 (anexos)=Task 4 ✓; Grupo 4 (prestadores-pj)=Task 7 ✓; Grupo 5 (ponto/eSocial)=Tasks 8,9 ✓; fundação N-ações=Task 0 ✓.
- **Fronteira T1:** nenhuma task toca money-out (analyze/aprovar sim, pagar não). ✓
- **Placeholders:** Tasks 7-9 têm Step 1 "MAPEAR" explícito (grep concreto) — é o padrão aceito deste projeto (endpoints de Fase 2/3 se descobrem na task; Fase 1 tem contrato completo). Não é TODO vago — é o comando + o mecanismo.
- **Consistência:** `actionsfn`/`row.actions` definido em Task 0, consumido em 1,3,4,7. `rd_action_*` handlers (vacation-reject, cert-gerar-folha, vacation-sync, ponto-fechar) em `redesign_data_controller.py`.
- **Decisões abertas registradas:** field `type:hidden` no edit-modal (Task 1 Step 2); upload de anexo adiável (Task 4 Step 3); eSocial pode virar 2 sub-tasks (Task 9 Step 1).

## Ordem de execução
Task 0 → 1 → 2 → 3 → 4 → 5 → 6 (Fase 1, backend-only exceto Task 0) · depois 7 (Fase 2) · depois 8, 9 (Fase 3, gated). Deploy: docker cp por task; **bake batched** ao fim de cada fase (coordenar lock com T1).
