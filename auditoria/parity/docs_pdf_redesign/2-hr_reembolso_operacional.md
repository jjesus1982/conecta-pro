# Inventário de geradores de documento — hr / reimbursement / operacional / operacoes / campo / tecnico

Auditoria para o redesign (adicionar botões "abrir HTML" + "baixar PDF" por documento).
Base READ-ONLY. Escopo: `backend/modules/{hr,reimbursement,operacional,operacoes,campo,tecnico}/`.
Prefixo base da API em produção: **`/api/v1`** (`main_production.py:336`).

Legenda:
- **Sensível** 💰 = dinheiro / 📄 legal-trabalhista (holerite, AFD, eSocial, folha).
- Granularidade: **POR-ITEM** = precisa de um `{id}` (uma linha/registro); **POR-TELA** = agregado/lista.
- "Formato" = o que o backend REALMENTE devolve hoje (não o que a tela poderia renderizar).

---

## 1. Geradores de documento COM rota HTTP (arquivo real: PDF / XML / TXT / CSV / arquivo salvo)

| Documento | Método + Path | Formato(s) | Granularidade | Auth/gate | Arquivo:linha |
|---|---|---|---|---|---|
| Relatório da visita técnica/comercial (branded Conecta) | `GET /api/v1/campo/visitas/{visita_id}/pdf?download=` | PDF (inline ou attachment) | POR-ITEM (`visita_id`) | ⚠️ **SEM auth** — endpoint só depende de `get_service`, sem `CurrentActiveUser` (os demais endpoints do arquivo exigem) | `campo/controllers/visita_controller.py:447` (gerador `crm.services.doc_pdf.build_visit_report_pdf`) |
| Relatório da ronda de inspeção (dados+checkpoints+resumo, branded) | `GET /api/v1/operacional/rondas/{round_id}/relatorio/pdf?download=` (espelho: `/api/v1/people-management/operations/rondas/...`) | PDF (inline/attachment) | POR-ITEM (`round_id`) | `get_current_active_user` (dep. global do router) | `operacional/inspection_rounds/controllers/inspection_round_controller.py:773` (gerador `financial.services.relatorio_financeiro_pdf.gerar_relatorio_pdf`); mount `operacional/__init__.py:290` / `main_production.py:509` |
| Foto de checkpoint de ronda (arquivo armazenado) | `GET /api/v1/operacional/rondas/{round_id}/checkpoints/{checkpoint_id}/fotos/{nome}` | binário (imagem, `FileResponse`) | POR-ITEM | `get_current_active_user` | `operacional/inspection_rounds/controllers/inspection_round_controller.py:758` |
| 📄💰 Holerite / contracheque (PDF padrão-ouro, regera na hora + cria assinatura) | `GET /portal/payslips/{payslip_id}/download` | PDF (`FileResponse`) | POR-ITEM (`payslip_id`) | `get_current_user`; escopo por `employee_id` do token | `hr/employee_portal/controllers/payslip_controller.py:99` ⚠️ **submódulo NÃO montado no main_production** (ver §4) |
| Documento do funcionário (arquivo armazenado: atestado, contrato, etc.) | `GET /portal/documents/{document_id}/download` | binário conforme `mime_type` (default PDF) | POR-ITEM (`document_id`) | `get_current_user`; escopo por `employee_id` | `hr/employee_portal/controllers/document_controller.py:127` ⚠️ **submódulo NÃO montado** (§4) |
| 📄💰 Arquivo de exportação de folha (download) | `GET .../payroll/exports/{export_id}/file` | **TXT / CSV / XLSX / XML / JSON / eSocial-XML / SEFIP** (`StreamingResponse`, content-type dinâmico) | POR-ITEM (`export_id`) | `require_permissions(["payroll:export"])` | `hr/payroll_integration/controllers/payroll_export_controller.py:233` (formatos: `models/payroll_export.py:13`); montado via wrapper `people_management/hr/controllers/payroll_controller.py:24` |
| 📄💰 Processar/gerar exportação de folha (gera o arquivo) | `POST .../payroll/exports/{export_id}/process` | dispara geração (retorna metadata JSON) | POR-ITEM | `require_permissions(["payroll:export"])` | `hr/payroll_integration/controllers/payroll_export_controller.py:145`; service `payroll_integration/services/payroll_export_service.py` |
| 📄💰 Info de download da exportação | `GET .../payroll/exports/{export_id}/download-info` | JSON (nome/content-type/tamanho) | POR-ITEM | `payroll:export` | `hr/payroll_integration/controllers/payroll_export_controller.py:203` |
| 📄 AFD — Arquivo Fonte de Dados (Portaria 671, ponto eletrônico) | `GET /rep/afd/export/{device_id}/download` | **TXT** (`text/plain`, `FileResponse`) | POR-ITEM (`device_id` + período) | `get_current_user` | `hr/rep_integration/controllers/afd_controller.py:114` (service `afd_service.export_afd`) ⚠️ **submódulo NÃO montado** (§4) |
| 📄 AFD — exportar (gera arquivo, sem stream) | `POST /rep/afd/export` | metadata JSON (path do arquivo) | POR-TELA (por período/empresa) | `get_current_user` | `hr/rep_integration/controllers/afd_controller.py:87` ⚠️ **submódulo NÃO montado** (§4) |
| Relatório agendado de RH (executar → gera arquivo) | `POST /analytics/reports/{report_id}/run?output_format=` | **PDF (reportlab branded) / EXCEL / CSV / HTML / JSON** — gerado e salvo | POR-ITEM (`report_id`) | `get_current_user` | `hr/analytics_dashboard/controllers/report_controller.py:158`; gerador `services/report_generator_service.py:247` (PDF em `:296`/`:309`) ⚠️ **submódulo NÃO montado** (§4) + **dados mock** (`_collect_report_data` usa `random`, `:232`) |
| Relatório agendado de RH — download do arquivo gerado | `GET /analytics/reports/{report_id}/download/{run_id}` | **STUB** — retorna JSON `"Download não implementado nesta versão"` | POR-ITEM | `get_current_user` + escopo `condominio_id` | `hr/analytics_dashboard/controllers/report_controller.py:268` ⚠️ não implementado |
| Comprovante/anexo de reembolso (arquivo armazenado, ex. nota/cupom) | `GET /reimbursements/attachments/{attachment_id}/download` | binário conforme `mime_type` (PDF/JPEG/PNG/…) | POR-ITEM (`attachment_id`) | `CurrentActiveUser` | `reimbursement/controllers/reimbursement_controller.py:519`; upload em `:432` |

---

## 2. Endpoints de RELATÓRIO que hoje devolvem só DADOS (JSON) — candidatos naturais a ganhar PDF/HTML no redesign

Nenhum destes gera arquivo hoje; retornam `response_model` Pydantic. São exatamente as telas onde o redesign quer o botão "abrir HTML / baixar PDF", mas o backend ainda **não tem gerador** — precisará de um (ou renderização client-side).

| Relatório | Método + Path | Formato hoje | Granularidade | Auth/gate | Arquivo:linha |
|---|---|---|---|---|---|
| Cobertura de postos (coverage) | `GET /api/v1/operacional/reports/coverage` | JSON | POR-TELA (período) | router operacional | `operacional/controllers/reports_controller.py:39` (service `reports/services/coverage_report.py:104`) |
| Horas trabalhadas | `GET /api/v1/operacional/reports/hours` | JSON | POR-TELA | idem | `operacional/controllers/reports_controller.py:90` |
| Horas extras (overtime) | `GET /api/v1/operacional/reports/overtime` | JSON | POR-TELA | idem | `operacional/controllers/reports_controller.py:130` (service `reports/services/overtime_report.py`) |
| Custos operacionais | `GET /api/v1/operacional/reports/costs` | JSON | POR-TELA | idem | `operacional/controllers/reports_controller.py:146` |
| Relatório disciplinar | (service sem rota dedicada; ver §3) | — | — | — | `operacional/reports/services/disciplinary_report.py` |
| 💰 Diárias — resumo por diarista (lista de pagamento dia 15) | `GET /api/v1/operacional/diarias/resumo-diarista?mes=&ano=` | JSON | POR-TELA (mês) | `get_current_active_user` | `operacional/diaristas/diarias_controller.py:70` |
| 💰 Diárias — resumo gerencial (por posto/função, BI) | `GET /api/v1/operacional/diarias/resumo-gerencial?mes=&ano=` | JSON | POR-TELA | idem | `operacional/diaristas/diarias_controller.py:76` |
| 💰 Diaristas — fechamento de folha (payroll report) | `GET /api/v1/operacional/diaristas/payments/payroll-report?competencia=` | JSON (`PayrollReportResponse`) | POR-TELA (competência) | `require_roles(admin/…/supervisor)` | `operacional/diaristas/controllers/diarist_controller.py:509` (service `diaristas/services/diarist_service.py`) |
| 💰📄 Diaristas — retenções fiscais (INSS/ISS) | rotas em `fiscal_controller` (JSON `RelatorioRetencoesResponse`) | JSON | POR-TELA | router diaristas | `operacional/diaristas/controllers/fiscal_controller.py:99` (service `diaristas/services/fiscal_service.py`) |
| Passagem de turno (shift handover) | `GET /api/v1/operacional/...passagens` | JSON | POR-ITEM / POR-TELA | `get_current_active_user` | `operacional/shift_handover/controllers/shift_handover_controller.py:66,160,237` |
| Instruções do posto (post orders) | `GET /api/v1/operacional/...` | JSON | POR-ITEM / POR-TELA | router operacional | `operacional/post_orders/controllers/post_orders_controller.py:105,135` |
| Ocorrências (occurrences) | `GET /api/v1/operacional/ocorrencias/...` | JSON | POR-ITEM / POR-TELA | router operacional | `operacional/occurrences/controllers/occurrence_controller.py:268` |
| Avaliação de equipe (team evaluation) | `GET /api/v1/operacional/...avaliacoes` | JSON | POR-ITEM / POR-TELA | router operacional | `operacional/team_evaluations/controllers/team_evaluation_controller.py:259,387` |
| Presença/cobertura ao vivo | `GET /api/v1/operacional/...presenca` | JSON | POR-TELA | router operacional | `operacional/presence/controllers/presence_controller.py` |
| Banco de horas | `GET /api/v1/operacional/banco-horas/...` | JSON | POR-ITEM / POR-TELA | router operacional | `operacional/controllers/time_bank_controller.py:116` |
| Escala / grade | `GET /api/v1/operacional/escalas`, `/grade` | JSON | POR-TELA | router operacional | `operacional/controllers/scale_controller.py:204`, `grade_controller.py` |
| KPIs / trends operacionais | `GET /api/v1/operacional/reports-kpi-trends`, `/dashboard` | JSON | POR-TELA | router operacional | `operacional/controllers/kpi_trends_controller.py:151`, `reports_controller.py:189` |
| Espelho de ponto / folha de ponto (time-sheet) | `GET .../time-tracking/time-sheets/...` | JSON | POR-ITEM / POR-TELA | `get_current_user` | `hr/time_tracking/controllers/time_sheet_controller.py`, `services/report_service.py`, `services/time_sheet_service.py` — **sem geração de arquivo** |
| Ordem de serviço (campo/técnico) | `GET /api/v1/campo/os/{id}`, `tecnico/ordens_servico/...` | JSON | POR-ITEM | router campo/tecnico | `campo/controllers/ordem_servico_controller.py`, `campo/services/ordem_servico_service.py` — **NÃO gera PDF hoje** (só a visita gera) |

> Nota: a justificativa de ponto (`hr/time_tracking/controllers/justification_controller.py:520`) e o upload de comprovante de reembolso (`reimbursement_controller.py:432`) apenas **recebem** arquivos (`UploadFile`, lista de `content_type` permitidos inclui `application/pdf`/`docx`) — **não são geradores**. Não confundir com download.

---

## 3. SEM ROTA HTTP (geradores/serviços de documento não expostos diretamente)

| Gerador | O que produz | Onde é usado | Arquivo:linha |
|---|---|---|---|
| `report_generator_service._render_pdf_branded` / `_generate_csv` / `_generate_excel` | PDF (reportlab)/CSV/Excel de relatório agendado | chamado por `POST /analytics/reports/{id}/run`, mas o **download é STUB** e o submódulo não está montado | `hr/analytics_dashboard/services/report_generator_service.py:247,269,289,296,309` |
| `payroll_export_service` (geradores TXT/CSV/XLSX/XML/eSocial/SEFIP) | arquivos de folha | chamado por `/exports/{id}/process` + `/file` | `hr/payroll_integration/services/payroll_export_service.py` |
| `afd_service.export_afd` | arquivo AFD `.txt` | chamado por rotas AFD (submódulo não montado) | `hr/rep_integration/services/afd_service.py` |
| `CoverageReportService` / `OvertimeReportService` / `DisciplinaryReportService` | dataclasses de relatório (dados, sem serialização de arquivo) | alimentam os endpoints JSON do §2 | `operacional/reports/services/{coverage_report,overtime_report,disciplinary_report}.py` |
| `esocial_service.generate_event` / `check_receipt` | XML eSocial (armazenado como export) / recibo | rotas `/esocial/*` retornam **JSON**, não o XML direto — o XML sai via `/exports/{id}/file` | `hr/payroll_integration/controllers/esocial_controller.py:119,176`; `services/esocial_service.py` |

---

## 4. ⚠️ Achado crítico de montagem (impacta o redesign)

Três submódulos de `modules/hr/` **não estão montados no `main_production.py`** (o `__init__.py` de `modules/hr` está vazio e ninguém importa seus routers) — logo, seus endpoints de documento **não respondem em produção** pelos paths acima:

- `hr/employee_portal` → holerite PDF (`payslip_controller.py:99`) e download de documento (`document_controller.py:127`).
- `hr/rep_integration` → download AFD (`afd_controller.py:114`).
- `hr/analytics_dashboard` → relatórios agendados (`report_controller.py`).

Somente `hr/payroll_integration` e `hr/time_tracking` estão wired, via wrappers `people_management/hr/controllers/{payroll_controller.py,time_tracking_controller.py}` (path efetivo com prefixo duplicado, ex. `.../hr/payroll/exports/...` e `.../hr/time-tracking/...`). A rota **viva** de holerite PDF está em `people_management` (`dp_payslips_controller`, fora deste escopo — `main_production.py:1135`). Antes de fiar botões no redesign, confirmar qual endpoint de holerite/AFD está de fato no ar.

---

## 5. Sensíveis (dinheiro / legal) — exigem gate reforçado no redesign

- 💰📄 Holerite/contracheque, exportação de folha (todos os formatos), diárias/fechamento, retenções fiscais, AFD, eSocial-XML. Botão de download deve respeitar o gate já existente (`payroll:export`, `require_roles`, escopo por `employee_id`/`condominio_id`) e **nunca** expandir visibilidade.
- ⚠️ `GET /campo/visitas/{id}/pdf` está **sem autenticação** — corrigir antes de expor botão público.
