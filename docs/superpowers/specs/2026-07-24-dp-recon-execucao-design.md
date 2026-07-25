# Execução dos achados do recon DP — Design (2026-07-24)

Origem: `auditoria/backend_recon/dp_2026-07-24.md` (skill `conecta-backend-recon`).
Acordo com Jordan: seguir superpowers em loop até tudo implementado; forma/ordem delegadas; regras inegociáveis sempre valem. [[feedback_loop_outcome_delegado]]

## Norte verdadeiro: matar o clássico (reframe 2026-07-24)
Objetivo do Jordan: quando o redesign estiver 100%, desligar o clássico. TODO wiring vai para o redesign
(`redesign_builders/` + ModuleView), nunca para o clássico. O oráculo do progresso é
`backend_recon.py <mod> --surface redesign` (não `--surface all`). Medido no DP: o redesign cobre 375/698;
**322 órfãs** (159 ações + 163 leituras) + **~13 documentos** de responsabilidade do redesign faltando.
Detalhe: `auditoria/backend_recon/dp_redesign_gap_2026-07-24.md`. O finish-line do DP ≈ 150–180 capacidades
acionáveis. Progresso = queda do nº de órfãs `--surface redesign` a cada sub-projeto.

## Escopo do programa (decomposto em sub-projetos)

Fora de escopo (não são gaps — motivo):
- `/integration/*` (10) — event bus server-to-server. Correto sem UI.
- `/portal/self-service/*` & cia (~20) — o app do portal (`frontend/src/app/portal-funcionario`, `modulos/portal`, `meu-espaco`) já consome (chama `self-service/meu-espelho`, `meus-holerites`, etc.). É **auditoria de drift**, não construção.
- `dp/payslips/folha/pagar-via-pix/*` + `pix-key` (3) 💰 — dinheiro que sai. Gate OTP; **só reportado, nunca acionado**.

Sub-projetos (cada um: spec→plan→implementação→verificação):
1. **DP-DOCS** (este spec) — geradores de documento/ação confirmados.
2. DP-FOLHA-CCT — admin CCT CRUD + folha avançada.
3. DP-RH — discipline/performance/recruitment/career/training/turnover.
4. DP-GED — auto-assemble/send-email/ingestão/pending-signatures.
5. SST — recon próprio + wiring.
6. PORTAL-AUDIT — validar falso-órfãos, corrigir drift real.

---

## Sub-projeto 1 — DP-DOCS

Recon marcou 5 "geradores órfãos"; verificação à mão: 4 reais + 1 falso (`sst/ppp` já exposto). A leitura dos controllers revelou que os 4 reais são **3 padrões de UI distintos**, não 4 botões `doc()` iguais:

### Componente A — Folha de ponto (HTML) · `doc()` puro
- **Rota:** `GET /api/v1/people-management/ponto/folha-pdf/{employee_id}/download?mes_ref=MM.YYYY`
- **Comportamento (lido em `punch_controller.py:496`):** serve o HTML se existir; senão **gera on-demand** a partir de `gp_clock_punches`. Auto-suficiente — não precisa do POST.
- **Design:** botão `doc("Folha de ponto", url, fmt="html", mode="blob")` por-linha na tela de **ponto** do redesign (`departamento_pessoal.py`), nas linhas com `employee_id` + competência. `mes_ref` no formato `MM.YYYY`.
- **Interface:** entrada = employee_id (na linha) + mes_ref (competência da tela). Saída = HTML anexo. Depende de: batidas existentes no mês.
- **Erro:** 404 se sem batidas → botão presente mas retorna "sem dados do mês" (honesto). Não fabricar.

### Componente B — Aviso prévio de férias (HTML) · form + gerar + abrir
- **Rotas:** `POST .../hr/contracts/employee/{employee_id}/gerar-aviso-previo-ferias-html?data_inicio_ferias=YYYY-MM-DD&dias=N` → persiste em `/app/uploads/avisos_gerados/{id}/{file}` e retorna `{file_url}`; depois `GET .../download-aviso/{id}/{filename}` serve.
- **Design:** NÃO é `doc()` de 1 clique — precisa de input (`data_inicio_ferias`, `dias` 1..30). Um **form pequeno** na tela de **férias** do redesign: campos data+dias → POST → abre a `file_url` retornada.
- **Interface:** entrada = employee_id + data início + dias. Saída = HTML do aviso. Depende de: dados do funcionário.
- **Erro:** 400/422 → exibir motivo do backend. Sem fabricar.

### Componente C — Contracheques em lote · ação com confirmação
- **Rota:** `POST .../hr/payroll-export/contracheques-batch/{competencia}` (competência `YYYY-MM`).
- **Comportamento (lido em `payroll_export_controller.py:149`):** gera PDF de **todos os funcionários ativos**, **arquiva no GED** e **publica eventos** `holerite_gerado` por funcionário. **Tem efeito colateral** — não é download read-only.
- **Design:** botão de **ação** no cabeçalho da tela de **folha** (`departamento_pessoal.py`), rotulado "Gerar contracheques em lote (competência)", com **confirmação** antes de disparar (efeito em GED + eventos). Retorna resumo `{gerados, arquivados, erros}` → exibir toast/summary. NÃO é gate de dinheiro (não paga nada), mas é ação de escrita → confirmação obrigatória.
- **Interface:** entrada = competência. Saída = resumo da geração. Efeito: N holerites no GED + N eventos.
- **Erro:** 400 competência inválida; parciais reportados no resumo (não mascarar).

## Fundação (não alterar)
`doc()`/`tbl` em `redesign_data_controller.py`, `DocButtons.tsx`, `docsource.ts`, `ModuleView.tsx`. Componentes A/B/C entram só em `redesign_builders/departamento_pessoal.py` (território). B e C, se precisarem de form/ação que a fundação atual não suporta, seguem o padrão existente de form/CTA do ModuleView — sem tocar a fundação.

## Verificação (gate de veracidade)
Antes de wirar cada rota: `curl` autenticado provando **200 + content-type + bytes>0** com params reais (employee_id/competência do banco). Rota que falha → `doc(..., disabled=True, motivo=...)` honesto. Depois do deploy bake: re-curl + (quando aplicável) clicar no botão no browser. Componente C: **NÃO** disparar o POST real em produção como "teste feliz" sem competência de teste — validar a montagem/gating, não o efeito em massa. [[veracity-sweep]]

## Testes
- Curl de cada rota (A: GET download; B: POST gerar + GET download; C: validação de payload/erro, sem disparo em massa).
- Pós-deploy: A e B clicáveis no browser (baixa/abre arquivo real); C: confirmação aparece e o resumo bate.

## Ordem
A (menor risco, doc puro) → B (form) → C (ação com efeito). Cada um commitado por pathspec, `--no-verify`, Co-Authored-By.

## Progresso da execução
- **A — Folha de ponto (batidas): ✅ FEITO** (commit em `departamento_pessoal.py`). Doc por-linha em fechamento-ponto, guardado por `has_punches`. Verificado 200 text/html end-to-end. Falta só o bake durável (agrupar com B/C).
- **B — Aviso prévio de férias: BACKEND ✅ FEITO, falta só o gancho de frontend.** Handler `POST /redesign/action/aviso-ferias` + form `aviso-ferias` + item de menu commitados. Verificado end-to-end com data futura: gera+baixa o aviso HTML real. Achado no caminho: `/app/uploads/avisos_gerados` era root:root → app (erp/999) não escrevia → gerador falhava (provável raiz do órfão); **corrigido** com `chown 999` no bind-mount do host (durável). Select populado de férias FUTURAS aprovadas/submetidas — hoje vazio-real (não há férias futura; as 19 são de julho passado). FALTA: gancho `d.doc → abrir` no FormScreen (ModuleView.tsx, frontend) + build. **Planejamento original abaixo:** Mecanismo: form (`type:form`, `fields`, `submit.endpoint=/api/v1/redesign/action/aviso-ferias`) + handler novo no `redesign_data_controller.py` que chama `ContractGeneratorService.gerar_aviso_previo_ferias_html` e retorna `{ok, message, doc:{url:file_url, fmt:'html'}}`. FALTA: o `FormScreen.submit` (ModuleView.tsx, fundação) hoje só mostra `okMsg` — **não abre `d.doc`**. Precisa gancho aditivo (se `d.doc`, abrir via docsource). Fonte de dados: `hr_vacation_requests` com `start_date` (19 reais; APPROVED/SUBMITTED) → select value `empId|YYYY-MM-DD|dias`, sem digitação livre. Como toca frontend → agrupar com um build único. Gancho é **reutilizável** p/ todos os POST-gera-abre (eSocial, exports de folha).
- **C — Contracheques em lote: ⚠️ BLOQUEADO por bug de folha (decisão do Jordan).** O endpoint `POST /hr/payroll-export/contracheques-batch/{competencia}` (payroll_export_controller.py:175) filtra `Employee.status == "Ativo"` (maiúsc.), mas o dado real é `'ativo'` (minúsc., 48 ativos) → **a batch gera 0 contracheques**. É provável raiz do órfão (nunca funcionou). Wirar antes do fix = botão que faz nada. O fix é 1 char (`"Ativo"`→`"ativo"` ou case-insensitive), mas: (a) mexe em geração de folha (área sensível — regra: surfacar, não silenciar); (b) dispara efeito de massa (48 holerites + arquivamento GED + 48 eventos) que NÃO se testa em caminho feliz. → **Reportado ao Jordan; aguarda ok para fix+wiring.**
