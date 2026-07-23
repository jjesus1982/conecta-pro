# Inventário de Geradores de Documentos — Módulo `people_management`

> Escopo: `/opt/conecta-pro/backend/modules/people_management/`
> Objetivo: mapear TODO endpoint/função que produz documento visualizável/baixável (PDF/HTML/XLSX/CSV/XML/TXT/ZIP)
> para o redesign do frontend ganhar botões **"abrir HTML"** + **"baixar PDF"** em cada um.
> READ-ONLY. Gerado em 2026-07-22.

## Convenção de prefixos (URL completa)

Prefixo base da API: **`/api/v1`**
Prefixo do módulo (em `__init__.py:16`): **`/people-management`**

Sub-agregadores:
- `hr/aggregator.py:20` → `/hr` (controllers somam o próprio prefix: `/payroll`, `/contracts`, `/terminations`, `/vacations`, `/ponto`, `/esocial`, `/payroll-export`, `/documents`, `/admissions`, `/reports`)
- `employee_portal/aggregator.py:38` → `/portal` (my_payslips **sem prefix próprio** → herda `/portal`; self_service → `/portal/self-service`; candidato → `/portal/candidato`; autocadastro-pj → `/portal/autocadastro-pj`)
- `ged/aggregator.py:14` → `/ged` (controllers somam `/documents`, `/kits`)
- `folha_controller.py:24` → `/folha` (montado direto no módulo)
- `ponto` (`punch_controller.py:41`) → `/ponto`
- `sst` (`sst_controller.py:75`) → `/sst`
- `human_resources/aggregator.py:31` → `/human-resources` (candidatos → `/candidatos`)
- **dp_payslips**: montado à parte em `main_production.py:1142` com `prefix="/people-management"` → `/dp/payslips`

Logo, a URL completa = `/api/v1/people-management` + `<sub>` + `<rota>`.
Na coluna "Path completo" abaixo o prefixo `/api/v1/people-management` está **implícito** (mostro a partir do sub-agregador).

---

## Tabela — Documentos COM rota HTTP exposta

| Documento | Método + Path (após `/api/v1/people-management`) | Formato(s) | Granularidade | Auth/gate | Arquivo:linha |
|---|---|---|---|---|---|
| **Holerite / contracheque PDF (padrão-ouro Conecta Mais)** | `GET /folha/holerite/{employee_id}/{mes}/{ano}/pdf` | PDF | POR-ITEM (employee_id + mês/ano) | token (CurrentActiveUser) · 💰 dinheiro | `folha/controllers/folha_controller.py:65` |
| **Folha CONSOLIDADA PDF (resumo + detalhamento por colaborador)** | `GET /folha/{mes:int}/{ano:int}/pdf` | PDF | POR-TELA (competência agregada) | token · 💰 dinheiro | `folha/controllers/folha_controller.py:154` |
| **Recibo de VT e VR PDF (padrão-ouro)** | `GET /folha/recibo-vt-vr/{employee_id}/{mes}/{ano}/pdf` | PDF | POR-ITEM | token · 💰 dinheiro | `folha/controllers/folha_controller.py:189` |
| **Holerite PDF (download DP)** | `GET /dp/payslips/{payslip_id}/pdf` | PDF | POR-ITEM (payslip_id) | token · 💰 dinheiro | `employee_portal/controllers/dp_payslips_controller.py:147` |
| **Contracheque PDF (portal do funcionário)** | `GET /portal/my-payslips/{month}/{year}/pdf` | PDF | POR-ITEM (funcionário logado + mês/ano) | token do próprio funcionário · 💰 | `employee_portal/controllers/my_payslips_controller.py:74` |
| **Meu holerite PDF (self-service)** | `GET /portal/self-service/meus-holerites/{month}/{year}/pdf` | PDF | POR-ITEM (self) | token do próprio funcionário · 💰 | `employee_portal/controllers/self_service_controller.py:125` |
| **Meu espelho de ponto PDF (Portaria 671)** | `GET /portal/self-service/meu-espelho/{mes}/{ano}/pdf` | PDF | POR-ITEM (self + mês/ano) | token do próprio funcionário · ⚖️ legal | `employee_portal/controllers/self_service_controller.py:175` |
| **Baixar meu documento (GED do portal)** | `GET /portal/self-service/meus-documentos/{...}` (`baixar_meu_documento`) | PDF (FileResponse) | POR-ITEM (documento do self) | token do próprio funcionário | `employee_portal/controllers/self_service_controller.py:554` |
| **Contracheque PDF (folha DP)** | `GET /hr/payroll/employee/{employee_id}/payslip-pdf` | PDF | POR-ITEM | token · 💰 dinheiro | `hr/controllers/payroll_controller.py:153` |
| **Exportação da folha p/ Domínio (arquivo importável)** | `GET /hr/payroll-export/dominio/{competencia}` | TXT (`text/plain; charset=latin-1`) | POR-TELA (competência) | token · 💰 dinheiro | `hr/controllers/payroll_export_controller.py:26` |
| **Contracheque PDF (export)** | `GET /hr/payroll-export/contracheque/{employee_id}/{competencia}` | PDF | POR-ITEM | token · 💰 dinheiro | `hr/controllers/payroll_export_controller.py:99` |
| **Contracheques em LOTE (batch)** | `POST /hr/payroll-export/contracheques-batch/{competencia}` | PDF (lote) | POR-TELA (competência) | token · 💰 dinheiro | `hr/controllers/payroll_export_controller.py:149` |
| **Espelho de ponto PDF (padrão-ouro, Portaria 671)** | `GET /hr/ponto/espelho/{employee_id}/{mes}/{ano}/pdf` | PDF | POR-ITEM | token · ⚖️ legal | `hr/controllers/espelho_ponto_controller.py:169` |
| **eSocial S-2200 (Admissão) — XML** | `POST /hr/esocial/s2200/gerar` | XML | POR-ITEM (admissão/employee) | token · 🏛️ gov | `hr/controllers/esocial_controller.py:112` |
| **eSocial S-2299 (Desligamento) — XML** | `POST /hr/esocial/s2299/gerar` | XML | POR-ITEM (rescisão) | token · 🏛️ gov | `hr/controllers/esocial_controller.py:169` |
| **Aviso Prévio (rescisão) PDF** | `GET /hr/terminations/{termination_id}/aviso-previo/pdf` | PDF | POR-ITEM (termination_id) | token · ⚖️ legal | `hr/controllers/termination_controller.py:363` |
| **TRCT (Termo de Rescisão) PDF** | `GET /hr/terminations/{termination_id}/trct/pdf` | PDF | POR-ITEM | token · ⚖️ legal · 💰 verbas | `hr/controllers/termination_controller.py:448` |
| **Aviso Prévio de Férias PDF** | `POST /hr/vacations/{vacation_id}/aviso-previo` | PDF | POR-ITEM (vacation_id) | token · ⚖️ legal | `hr/controllers/vacation_controller.py:316` |
| **Contrato de Trabalho — gerar HTML** | `POST /hr/contracts/employee/{employee_id}/gerar-contrato-html` | HTML | POR-ITEM (employee_id) | token · ⚖️ legal | `hr/controllers/contract_controller.py:214` |
| **Contrato gerado — download** | `GET /hr/contracts/employee/{employee_id}/download/{filename}` | HTML (`text/html`) | POR-ITEM | token · ⚖️ legal | `hr/controllers/contract_controller.py:248` |
| **Aviso Prévio de Férias — gerar HTML** | `POST /hr/contracts/employee/{employee_id}/gerar-aviso-previo-ferias-html` | HTML | POR-ITEM | token · ⚖️ legal | `hr/controllers/contract_controller.py:273` |
| **Aviso Prévio de Férias gerado — download** | `GET /hr/contracts/employee/{employee_id}/download-aviso/{filename}` | HTML (`text/html`) | POR-ITEM | token · ⚖️ legal | `hr/controllers/contract_controller.py:313` |
| **Contrato PDF** | `GET /hr/contracts/{contract_id}/pdf` | PDF | POR-ITEM (contract_id) | token · ⚖️ legal | `hr/controllers/contract_controller.py:338` |
| **Documento do funcionário — download/visualizar** | `GET /hr/documents/{doc_id}/download` | mime original (default PDF, FileResponse) | POR-ITEM (doc_id) | token | `hr/controllers/document_controller.py:33` |
| **GED — documento — download** | `GET /ged/documents/{document_id}/download` | PDF (FileResponse) | POR-ITEM (document_id) | token | `ged/controllers/document_controller.py:258` |
| **GED — Kit documental — export ZIP** | `GET /ged/kits/{kit_id}/export/zip` | ZIP (FileResponse) | POR-ITEM (kit_id) | token | `ged/controllers/kit_controller.py:525` |
| **GED — Kit documental — export PDF consolidado** | `GET /ged/kits/{kit_id}/export/pdf` | PDF (ou TXT fallback) | POR-ITEM (kit_id) | token | `ged/controllers/kit_controller.py:563` |
| **Folha de ponto (cartão-ponto) — gerar HTML** | `POST /ponto/folha-pdf/{employee_id}` | HTML (retorna dict com conteúdo) | POR-ITEM (employee_id + mês) | token · ⚖️ legal | `ponto/controllers/punch_controller.py:477` |
| **Folha de ponto (cartão-ponto) — download** | `GET /ponto/folha-pdf/{employee_id}/download` | HTML (`text/html`, FileResponse) | POR-ITEM | token · ⚖️ legal | `ponto/controllers/punch_controller.py:496` |
| **SST — NR-1 Compliance PDF** | `GET /sst/nr1/compliance/pdf` | PDF | POR-TELA (compliance da empresa) | token · 🏛️ gov | `sst/controllers/sst_controller.py:295` |
| **SST — Anexo do ASO — download** | `GET /sst/aso/{aso_id}/anexo` | PDF/imagem (mime por extensão) | POR-ITEM (aso_id) | token · 🏛️ gov | `sst/controllers/sst_controller.py:1054` |
| **SST — Ficha de EPI PDF** | `GET /sst/epi/fichas/{ficha_id}/pdf` | PDF | POR-ITEM (ficha_id) | token · ⚖️ legal (assinatura) | `sst/controllers/sst_controller.py:1239` |
| **SST — PPP (Perfil Profissiográfico) PDF** | `GET /sst/ppp/{employee_id}/pdf` | PDF | POR-ITEM (employee_id) | token · 🏛️ gov · ⚖️ legal | `sst/controllers/sst_controller.py:1794` |
| **KYC — dossiê do candidato — download documento** | `GET /human-resources/candidatos/{candidato_id}/documento/{doc_id}` | PDF (FileResponse) | POR-ITEM (candidato + doc) | token | `human_resources/controllers/candidatos_esteira_controller.py:353` |

---

## Documentos "quase" — payloads JSON prontos p/ render (não são arquivo, mas alimentam tela imprimível)

Estes retornam **JSON estruturado** (não PDF/HTML), mas são a fonte de documento que a tela pode renderizar/imprimir. Úteis para o par "abrir HTML" quando o backend ainda não emite arquivo:

| "Documento" | Método + Path | Retorno | Granularidade | Arquivo:linha |
|---|---|---|---|---|
| PPP (dados, sem PDF) | `GET /sst/ppp/{employee_id}` | JSON (dict do PPP) | POR-ITEM | `sst/controllers/sst_controller.py:1687` |
| Prontuário SST | `GET /sst/prontuario/{employee_id}` | JSON | POR-ITEM | `sst/controllers/sst_controller.py:1665` |
| Contrato — gerar documento (metadados) | `POST /hr/contracts/{contract_id}/document` | JSON (document) — o PDF real é `/{contract_id}/pdf` | POR-ITEM | `hr/controllers/contract_controller.py:179` |
| Dossiê KYC do candidato (índice) | `GET /human-resources/candidatos/{candidato_id}/dossie` | JSON (lista de docs KYC/Infosimples) — cada doc baixa por `/documento/{doc_id}` | POR-ITEM | `human_resources/controllers/candidatos_esteira_controller.py:314` |
| Espelho mensal de ponto (dados) | `GET /ponto/espelho/{employee_id}` | JSON | POR-ITEM | `ponto/controllers/punch_controller.py:201` |
| Holerite final (dados) | `GET /folha/holerite/{employee_id}/{mes}/{ano}` | JSON (HoleriteResponse) | POR-ITEM | `folha/controllers/folha_controller.py:306` |
| Resumo/totalizador da folha | `GET /folha/resumo/{mes}/{ano}` | JSON | POR-TELA | `folha/controllers/folha_controller.py:324` |
| Conferência folha (Conecta vs Alterdata) | `GET /folha/conferencia/{mes}/{ano}` | JSON | POR-TELA | `folha/controllers/folha_controller.py:394` |
| Relatório de inconsistências CCT (ponto) | `GET /ponto/relatorio/inconsistencias` | JSON | POR-TELA | `ponto/controllers/punch_controller.py:392` |
| Relatório de Headcount | `GET /hr/reports/headcount` | JSON | POR-TELA | `hr/controllers/reports_controller.py:22` |
| Calculadora rescisória (CCT) | `POST /portal/my-cct/calculadora` | JSON | POR-ITEM | `employee_portal/controllers/my_cct_controller.py:138` |
| Termo de consentimento (candidato) | `GET /portal/candidato/termo` | JSON `{texto,versao,hash}` | POR-TELA | `employee_portal/controllers/candidato_controller.py:237` |
| Termo PJ (autocadastro) | `GET /portal/autocadastro-pj/termo` | JSON `{texto}` | POR-TELA | `employee_portal/controllers/pj_autocadastro_controller.py:105` |

---

## SEM ROTA HTTP (geradores internos — sem download voltado ao usuário)

Geradores de documento que existem como serviço/função mas **não** têm endpoint HTTP que devolva o arquivo ao usuário (uso interno, transmissão a gov via Celery, ou consumidos por outra rota que já está na tabela acima):

| Gerador | O que produz | Onde é consumido | Arquivo:linha |
|---|---|---|---|
| `EsocialService.gerar_s2210` | XML S-2210 (CAT) | Transmitido ao gov via Celery (`sst/tasks/esocial_tasks.py:154`), **sem** rota de download | `hr/services/esocial_service.py:382` |
| `EsocialService.gerar_s2220` | XML S-2220 (ASO) | Fila/transmissão `transmissao_central_service.py:130`, sem download | `hr/services/esocial_service.py:499` |
| `EsocialService.gerar_s2230` | XML S-2230 (Afastamento) | Celery `esocial_tasks.py:166` + fila `transmissao_central_service.py:172`, sem download | `hr/services/esocial_service.py:583` |
| `EsocialService.gerar_s2240` | XML S-2240 (Condições Ambientais/Riscos) | Fila `transmissao_central_service.py:241` (S-2240 ASG no GATE humano MB), sem download | `hr/services/esocial_service.py:643` |
| `montar_xml_evento_sst` | Monta XML de evento SST (dispatcher) | Interno (transmissão) | `hr/services/esocial_service.py:895` |
| `folha_pdf_parser.FolhaPDFParser` | Faz PARSE de PDF de folha (extração, não geração) | `dp_payslips_controller.py:511` (upload) | `services/folha_pdf_parser.py` |

> Observação: os builders XML S-2210/2220/2230/2240 **são emitidos e transmitidos**, mas nenhuma rota devolve o XML para o usuário visualizar/baixar. Se o redesign quiser expor "ver XML enviado", falta endpoint (candidato a nova rota de preview/download por evento).

---

## Notas para o redesign

1. **Sensíveis (exigem gate)** — marcar antes de qualquer botão de "gerar/reenviar":
   - 💰 **Dinheiro**: todos os holerites/contracheques, folha consolidada, recibo VT/VR, TRCT (verbas), export Domínio. Geração é leitura (OK), mas **pagamento** derivado é OTP humano (fora deste inventário).
   - 🏛️ **Gov**: eSocial (S-2200/2299 XML + S-2210/2220/2230/2240 internos), PPP, NR-1 compliance, anexo/transmissão ASO/CAT. Transmissão real = certificado + gate; **gerar/baixar o arquivo** é seguro.
   - ⚖️ **Legal**: contrato, aviso prévio (rescisão e férias), TRCT, espelho de ponto (Portaria 671), cartão-ponto, ficha EPI (assinatura).

2. **Padrão de resposta** varia — o redesign precisa tratar 3 formas:
   - `Response(content=..., media_type="application/pdf", headers=Content-Disposition)` — maioria dos PDFs.
   - `StreamingResponse(BytesIO(...), media_type="application/pdf")` — `my_payslips`, `payroll_controller`.
   - `FileResponse(path=..., media_type=...)` — GED docs/kits, documentos do funcionário, anexo ASO, cartão-ponto (HTML), KYC.
   - `Content-Disposition: inline` (abrir HTML) vs `attachment` (baixar) já varia por rota (ex.: `meu_espelho` usa `inline`).

3. **Pares "gerar → baixar"** (2 rotas): Contrato (`gerar-contrato-html` + `download/{filename}`), Aviso Prévio Férias (`gerar-...-html` + `download-aviso/{filename}`), Cartão-ponto (`POST /ponto/folha-pdf/{id}` + `GET .../download`). O redesign deve encadear as duas.

4. **Serviços de geração PDF centralizados** (padrão-ouro, todos já wired):
   `folha/services/{holerite_pdf,folha_pdf,recibo_vt_vr_pdf}.py` · `hr/services/{aviso_previo_pdf,trct_pdf,espelho_ponto_pdf}.py` · `sst/services/{ficha_epi_pdf,nr1_compliance_pdf,ppp_pdf}.py` · `ponto/services/folha_pdf_service.py` · `employee_portal/services/payslip_pdf_service.py` · `hr/services/{payroll_export_service,contract_service,esocial_service}.py`.
   Branding: `pdf_branding.py` (fora do módulo) — ver skill `gold-standard-pdf`.

5. **Exceção observada**: `my_payslips_controller._generate_payslip_pdf` (`:147`) monta o contracheque com reportlab **inline no controller** (não usa o serviço padrão-ouro) — divergência de padrão visual a considerar no redesign.
