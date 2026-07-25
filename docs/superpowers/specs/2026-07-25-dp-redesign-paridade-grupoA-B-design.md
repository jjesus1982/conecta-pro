# DP redesign — fechar paridade (grupo A + B-mine) — Design

> Continuação de `2026-07-25-dp-redesign-paridade-crud-design.md` (Tasks 1-5 já entregues). Aqui fecha o que o recon `people-management --surface redesign` apontou que o **clássico tem e o redesign não** — a parte que é minha (T2/DP), com a fronteira money-out do T1 travada.

## Objetivo
Ligar no DP redesign as capacidades secundárias do clássico que ainda faltam, reusando a fundação já baked (`ModuleView` editfn-ação + FormScreen multipart), **sem tocar money-out** (é do T1, em `financeiro.py`, gated OTP).

## Fronteira T1×T2 (inegociável — confirmado pelo T1 25/07)
- **Money-out = T1**, sempre em `redesign_builders/financeiro.py`, gated OTP. Inclui folha CLT PIX (`/folha/pagar-via-pix/*`, T1 fazendo AGORA p/ folha julho), folha PJ, diaristas, boleto/pix/ted/darf/gps, e o **pagar** de rescisão/reembolso.
- **Analisar/aprovar = T2 (eu)**, em `departamento_pessoal.py`. Nunca ligar pagamento no meu builder.
- Ver `[[feedback_money_out_t1_boundary]]`.

## Princípios (herdados, inegociáveis)
- Só endpoint REAL (oráculo exibido==banco); nunca inventar ação/dado.
- **Nunca testar happy-path que cria/muda dado real** (reject/analyze/import/gerar-lote/prestador disparam efeito) — provar rota por 422/404 em payload/id inválido + browser (botão/form abre).
- Commit por pathspec (só `departamento_pessoal.py` + `ModuleView.tsx` se precisar); commit antes de deploy; bake batched (OOM: swap alto, blindar oom_score_adj=-1000, evitar `next build` desnecessário).
- Ação por-linha só aparece no status certo (editfn retorna None senão).

## Componentes (unidades isoladas, cada uma verificável sozinha)

### Grupo 1 — ações por-linha (editfn, backend-only, reusa fundação)
Mecanismo: `editfn=lambda r: {...}` no `tbl`, com `method`, `btnLabel`, `btnStyle`, `fields`. Fundação já suporta POST/PATCH/DELETE e campos.
1. **férias Rejeitar** — `POST /api/v1/people-management/hr/vacations/{id}/reject`, body `{reason}`; editfn com campo *motivo* (textarea obrigatório), só linhas SUBMITTED. Convive com o Aprovar já existente? → editfn é UMA ação/linha; decisão: botão "Rejeitar" como ação alternativa OU incluir seletor. **Resolver no plano** (ver Questões).
2. **certificação Rejeitar** — `PATCH /api/v1/people-management/certifications/{id}/reject`, body `{motivo/observacao}`; só status pendente. Mesma questão de coexistir com Certificar.
3. **benefícios Remover** — `DELETE /api/v1/people-management/hr/benefits/{id}` (cancel_benefit); editfn method=DELETE + confirm; coexiste com "Gerir status" já existente.
4. **reembolso Analisar** — `POST /api/v1/people-management/hr/reimbursements/{id}/analyze`; só pendente; coexiste com Aprovar (o pagar é do T1).

### Grupo 2 — forms de tela (create/ação)
Mecanismo: `out["<chave>"] = {type:"form", submit:{endpoint,...}, fields:[...]}` + CTA na tela-mãe (`ctaTo`).
5. **férias sync Sólides** — `POST /api/v1/people-management/hr/vacations/sync-solides` (sem body / gatilho). Form de confirmação (submit.confirm) na tela férias.
6. **certificação gerar-lote** — `POST /api/v1/people-management/certifications/gerar-folha/{competencia}`. Form com select de competência (das que têm folha).
7. **benefícios Adicionar** — `POST /api/v1/people-management/hr/benefits` (BenefitCreate). Form: colaborador (select ativos), tipo, operadora, plano, contrib. empresa/colaborador, vigência. **Schema exato a confirmar no plano.**
8. **funcionários Importar cadastro** — `POST /api/v1/people-management/hr/employees/import-cadastro`. Form multipart (arquivo) reusando FormScreen `type:file`+`multipart`. **Confirmar formato (planilha? colunas?) no plano.**

### Grupo 3 — anexos de reembolso
9. **ver/baixar anexo** — `docsfn` per-row → `GET /api/v1/people-management/hr/reimbursements/attachments/{id}/download`. Precisa listar anexos por request (endpoint de listagem a confirmar).
10. **anexar** — `POST /api/v1/people-management/hr/reimbursements/{id}/attachments` multipart (reusa FormScreen file). *Pagar = T1, fora daqui.*

### Grupo 4 — tela nova `prestadores-pj`
11. **Prestadores PJ** — tela nova (não existe no DP redesign). `table` (lista `GET /human-resources/prestadores-pj`) + form create (`POST /human-resources/prestadores-pj`) + ação `POST /human-resources/prestadores-pj/{id}/regenerar-link`. Maior esforço; PJ≠CLT (ver `[[project_autocadastro_pj]]`). **Schema/campos a mapear no plano.**

### Grupo 5 — sensível, gated (B)
12. **ponto fechar-mês** — `POST /.../ponto/fechar-mes` (ou `/hr/ponto/fechar-mes`), respeitando TZ canônico (UTC no banco, `[[project_ponto_tz_canonico]]`). `submit.confirm` obrigatório (irreversível-avisado). **Confirmar endpoint/params exatos no plano.**
13. **eSocial SST propor→aprovar** (S-2220/2230/2240) 🏛️ — **NUNCA auto-transmitir**. Fluxo 2 atos humanos: *Propor evento* (grava proposta pendente) → *Aprovar/Transmitir* (segunda ação, humano diferente idealmente). Ato legal. Padrão Fase 5.4 (`[[project_fase5.3_proativo]]`, `[[project_esocial_duas_vias]]`). **Maior complexidade; candidato a 2ª leva.**

## Fora de escopo (decisões registradas)
- Money-out (folha/rescisão/reembolso→pagar) = **T1**.
- `folha-rubricas`/deductions = **só visual** (decisão Jordan).
- `portal do funcionário` (meus-holerites/meu-espelho) = **outro módulo** (`portal_do_funcionario.py`).

## Verificação (oráculo)
Por item: `curl` na rota real (200/201 em caso válido de TESTE não-poluente OU 422/404 em inválido — **nunca** happy-path que muta) + browser (botão/form aparece, abre, campos reais). Deploy coordenado no lock `/tmp/conecta_deploy.lock`; bake batched.

## Questões a resolver no plano (não bloqueiam o design)
- **Coexistência de ações por-linha:** a fundação editfn hoje = 1 ação/linha. Rejeitar precisa coexistir com Aprovar (férias/cert) e Remover com Gerir (benefícios). Opções: (a) pequena extensão do ModuleView p/ N ações por-linha (frontend, 1 build); (b) modal único com seletor de ação; (c) uma ação "gerir" que abre form com todas as opções. **Recomendo (a)** — destrava N-ações genérico p/ sempre. Decidir no plano.
- Schemas exatos: BenefitCreate, import-cadastro (formato do arquivo), prestadores-pj, analyze body, ponto fechar-mes params — mapear no plano (como fiz no Task 5).
- eSocial SST: confirmar se o backend já tem o estado "proposta pendente" ou se precisa do gancho (pode virar 2ª leva).

## Faseamento sugerido
- **Fase 1 (rápida, backend-only, reusa tudo):** Grupo 1 (rejeitar/remover/analisar) + Grupo 2 (sync/gerar-lote/adicionar/importar) + Grupo 3 (anexos). Precisa decidir coexistência de ações (talvez 1 build de frontend).
- **Fase 2:** Grupo 4 `prestadores-pj` (tela nova).
- **Fase 3:** Grupo 5 (ponto fechar-mês + eSocial SST gated) — mais sensível, pode fatiar.
