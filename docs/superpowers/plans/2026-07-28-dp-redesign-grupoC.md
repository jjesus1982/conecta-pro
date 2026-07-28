# DP redesign — grupo C (ações secundárias, tela DP 100%) — Plan

> **For agentic workers:** subagent-driven-development. Oráculo = curl (200/422/404) + browser. **NUNCA happy-path que muta/gera dado real** — provar por 422/404. Money-out, ponto/time-tracking, folha-engine (Frente C), eSocial-folha, outros módulos (recrutamento/RH/SST/GED) = FORA. Só a tela DP.

**Goal:** ligar as ~15 ações secundárias que o clássico do DP tem e o redesign ainda não, deixando a tela `departamento-pessoal` realmente 100%.

**Architecture:** mesmo padrão do grupo A+B — `departamento_pessoal.py` (actionsfn/forms/docsfn) + fundação `ModuleView` já baked (actionsfn, edit.fixed, multipart, edit.okMsg). Endpoints path/query → handler `rd_action_*`. Controlador (eu) deploya/verifica; implementer escreve código.

## Global Constraints
- Só endpoint REAL; nunca inventar; oráculo exibido==banco.
- Commit por pathspec (`departamento_pessoal.py`, `redesign_data_controller.py`, `ModuleView.tsx`); NÃO tocar money-out/`_fin_*`/ponto-engine/folha-engine.
- Verificar SEMPRE curl(200/422/404)+browser; nunca disparar geração/mutação real.
- Bake batched por fase; lock `/tmp/conecta_deploy.lock`; **NÃO blindar claude/node com -1000** (só tmux/sshd).

---

### Task C1: Rescisão — Calcular verbas + Concluir por-linha
- `POST /api/v1/people-management/hr/terminations/{id}/calculate` (calcula verbas) + `POST /{id}/complete` (conclui).
- actionsfn na tela `rescisao`: por-linha `[Calcular, Concluir]` conforme status (Calcular se não calculada; Concluir se calculada e não concluída). SELECT já tem tid (r do rescisao). Verificar body de complete (grep handler); se exigir dados, form-modal com fields; senão fields:[].
- curl: calculate/complete fake id → 400/404. browser: botões aparecem, modal abre. Commit.

### Task C2: Admissão — Editar por-linha (PATCH) + anexar documento
- `PATCH /api/v1/people-management/hr/admissions/{id}` (AdmissionProcessUpdate: candidate_name,cpf,position,department,salary_proposed,expected_start_date,contract_type,notes) — editfn/action pré-preenchido.
- (opcional) `POST /admissions/{id}/documents` upload — adiar se multipart-per-row complexo; decidir na task.
- Adicionar id + campos ao SELECT admissao. curl PATCH fake→404, corpo inválido→422. browser. Commit.

### Task C3: Contratos — Gerar contrato + Gerar aviso-prévio-férias (documentos) ⭐ alto valor
- `POST /api/v1/people-management/hr/contracts/employee/{employee_id}/gerar-contrato-html` → gera HTML (salva /uploads/contratos_gerados/), retorna doc ref; idem `/gerar-aviso-previo-ferias-html`.
- Padrão: actionsfn por-linha na tela `contratos` (que já lista por colaborador) → `[Gerar contrato, Gerar aviso férias]` (POST /employee/{employee_id}/...). employee_id no SELECT de contratos. A resposta traz o doc; usar o gancho de doc se disponível (FormScreen d.doc) OU mostrar mensagem + o download já existe via docsfn.
- **Mapear na task:** o SELECT de contratos tem employee_id? o retorno do gerar tem url pra abrir? Se o modal de ação não abre doc, mostrar msg de sucesso (doc fica no GED/download). curl: gerar fake employee → 404/400 (NÃO gerar real). browser. Commit.

### Task C4: Reembolso — Rejeitar + Cancelar por-linha
- `POST /reimbursements/{id}/reject` + `/{id}/cancel`. Adicionar às actionsfn do reembolsos (hoje Aprovar+Analisar) → p/ pendente: +Rejeitar; Cancelar conforme status. reject exige motivo? (grep). curl fake→404. browser. Commit.

### Task C5: Certificação — Criar avulsa (form)
- `POST /api/v1/people-management/certifications` (CertificationCreate: tipo_calculo*{folha_mensal|rescisao|esocial_s2210|...}, referencia_id, referencia_tipo, competencia, employee_id, cliente_id).
- Form `nova-certificacao` (select tipo_calculo, competencia, employee opcional) → CTA/EXTRA_MENU. curl POST vazio→422. browser. Commit.

### Task C6: Férias — Gerar aviso-prévio por-linha + Cancelar
- `POST /vacations/{id}/aviso-previo` (gera doc do aviso) + `DELETE /vacations/{id}` (cancela). Já tem Aprovar/Rejeitar na ferias; +Gerar aviso (doc) e Cancelar conforme status. curl fake→404. browser (NÃO gerar/cancelar real). Commit.

---

## Fora de escopo (registrado)
- rubricas/deductions (Jordan="só visual"); folha-engine/payroll periods-events-exports (Frente C/C1); eSocial-folha S-2200/2299 (C2); integration webhooks (server-to-server); ponto/time-tracking (38 rotas, TZ-sensível); disciplinar; portal; money-out (T1); outros módulos (recrutamento/RH/SST/GED — telas próprias).

## Ordem
C3 (alto valor) → C1 → C4 → C6 → C2 → C5. Bake ao fim. Ledger em `.superpowers/sdd/progress.md`.
