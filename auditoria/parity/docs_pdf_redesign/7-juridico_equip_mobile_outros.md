# Inventário de Documentos Gerados — Bloco 7

Módulos: `juridico`, `equipment_management`, `mobile`, `recruitment`, `pessoas`, `health_occupational`, `cct`, `services`, `security_lgpd`, `lgpd`, `retention`

Objetivo: mapear TODO documento voltado ao usuário (PDF/HTML/XLSX/CSV/XML/JSON-download) para o redesign anexar botões "abrir HTML" + "baixar PDF".

Método: READ-ONLY. Rotas mapeadas contra `main_production.py` (app de PRODUÇÃO = `main_production:app`), que monta cada router sob o prefixo `/api/v1` + o prefixo próprio do router. `main.py` (dev) monta um subconjunto diferente — anotado quando relevante.

---

## A. Endpoints que EMITEM um arquivo real (byte stream) — os que o redesign JÁ pode ligar

| Documento | Método + Path completo | Formato(s) | Granularidade | Auth/gate | Arquivo:linha |
|---|---|---|---|---|---|
| Parecer jurídico IA (padrão-ouro) | `GET /api/v1/juridico/pareceres/{id}/pdf` | PDF (reportlab, `Content-Disposition: inline`) | POR-ITEM (`id` do parecer) | `CurrentUser` (opcional — sem gate de permissão; controller sem `_JURIDICO_GATE`) | `juridico/documentos_controller.py:69` (gera em `juridico/parecer_service.py:415` `gerar_pdf_parecer`) |
| Comunicação DET (inteiro-teor, padrão-ouro) | `GET /api/v1/juridico/det/comunicacoes/{comunicacao_id}/pdf` | PDF (reportlab, `inline`) | POR-ITEM (`comunicacao_id`, int) | `get_current_active_user` | `juridico/det_controller.py:81` (gera em `juridico/det_service.py:304` `gerar_pdf_comunicacao`) |
| Portabilidade LGPD — export de dados pessoais (Art. 18 II) | `GET /api/v1/me/export` | JSON download (`Content-Disposition: attachment; filename=lgpd_export_{user_id}.json`) | POR-TELA / por usuário autenticado (self) | `get_current_user` (dados do próprio titular) | `lgpd/routes/delete_me.py:338` (router prefix `/api/v1/me`, montado direto no app em `main.py:132`) |

Observações:
- Os dois PDFs jurídicos usam reportlab de verdade (imports `reportlab.platypus`/`SimpleDocTemplate`). Saída `inline` = já servem para "abrir HTML/visualizar" e "baixar" no mesmo blob.
- O router de `documentos_controller` e `det_controller` NÃO recebe `_JURIDICO_GATE` (só o `consultor_controller` recebe — ver `main_production.py:1312`). Auth = apenas usuário logado.

---

## B. Endpoints que "geram documento" mas são STUB (retornam URL simulada, sem bytes) — redesign NÃO tem arquivo real

| Documento | Método + Path completo | Formato(s) | Granularidade | Auth/gate | Arquivo:linha |
|---|---|---|---|---|---|
| Contrato de comodato (termo) | `POST /api/v1/comodatos/{comodato_id}/contract-pdf` | retorna `{"pdf_url": "/api/v1/comodatos/{id}/contract.pdf"}` — URL FALSA, rota `.pdf` NÃO existe | POR-ITEM (`comodato_id`) | `CurrentActiveUser` | `equipment_management/controllers/comodato_controller.py:384` (serviço `comodato_service.py:277`) |
| Termo de entrega de equipamento | `POST /api/v1/comodatos/{comodato_id}/delivery-term` | `{"pdf_url": ".../delivery_term.pdf"}` — STUB, sem bytes | POR-ITEM | `CurrentActiveUser` | `equipment_management/controllers/comodato_controller.py:400` (serviço `comodato_service.py:293`) |
| Termo de devolução de equipamento | `POST /api/v1/comodatos/{comodato_id}/return-term` | `{"pdf_url": ".../return_term.pdf"}` — STUB, sem bytes | POR-ITEM | `CurrentActiveUser` | `equipment_management/controllers/comodato_controller.py:416` (serviço `comodato_service.py:307`) |

Comentário no código é explícito: `# Aqui seria gerado o PDF real / Por enquanto retorna URL simulada` (`comodato_service.py:283-285`, `299`, `313`). Grava a URL em `contract_pdf_url`/`delivery_term_url`/`return_term_url` do comodato mas nenhuma rota serve o arquivo. **Gap para o redesign: precisa de gerador real + rota GET do PDF.**

---

## C. "Documentos" que HOJE só existem como JSON on-screen (sem rota de arquivo) — o redesign quer botão HTML+PDF e NÃO há

Estes são recursos claramente documentais (dossiê, atestado legal, ficha, termo) servidos apenas como JSON. Não emitem PDF/HTML/XLSX. São o principal backlog de geração de documento do bloco.

### Jurídico — Dossiês / Discovery cross-módulo (JSON)

| Documento | Método + Path completo | Formato | Granularidade | Auth/gate | Arquivo:linha |
|---|---|---|---|---|---|
| Dossiê probatório de funcionário (DP+folha+ponto+férias+rescisão+SST+GED) | `GET /api/v1/juridico/contexto/funcionario/{identificador}` | JSON | POR-ITEM (id/CPF/matrícula/nome) | `get_current_active_user` | `juridico/context_controller.py:17` (motor `context_engine.py:126`) |
| Dossiê de pessoa (empregado OU PJ/fornecedor/cliente) | `GET /api/v1/juridico/contexto/pessoa?nome=&cpf=&cnpj=` | JSON | POR-ITEM (chave de busca) | `get_current_active_user` | `juridico/context_controller.py:30` (`context_engine.py:310`) |
| Dossiê de contrato | `GET /api/v1/juridico/contexto/contrato/{contrato_id}` | JSON | POR-ITEM | `get_current_active_user` | `juridico/context_controller.py:45` (`context_engine.py:407`) |
| Dossiê de cliente | `GET /api/v1/juridico/contexto/cliente/{cliente_id}` | JSON | POR-ITEM | `get_current_active_user` | `juridico/context_controller.py:58` (`context_engine.py:437`) |
| Panorama jurídico da empresa (regime, quadro, certidões, obrigações) | `GET /api/v1/juridico/contexto/panorama` | JSON | POR-TELA | `get_current_active_user` | `juridico/context_controller.py:71` |
| Comunicação DET (leitura on-screen, inteiro-teor) | `GET /api/v1/juridico/det/comunicacoes/{comunicacao_id}` | JSON (tem PDF irmão — ver seção A) | POR-ITEM | `get_current_active_user` | `juridico/det_controller.py:68` |
| Parecer jurídico (detalhe on-screen; flag `tem_pdf`) | `GET /api/v1/juridico/pareceres/{id}` | JSON (PDF irmão em `/pdf`) | POR-ITEM | `CurrentUser` | `juridico/documentos_controller.py:57` |
| Análise de contrato cláusula-a-cláusula (IA) | `GET /api/v1/juridico/analises` (lista) | JSON | POR-TELA | `CurrentUser` | `juridico/documentos_controller.py:102` |

### Health Occupational (SST) — documentos legais servidos só como JSON

| Documento | Método + Path completo | Formato | Granularidade | Auth/gate | Arquivo:linha |
|---|---|---|---|---|---|
| ASO — Atestado de Saúde Ocupacional (emissão) | `POST /api/v1/pcmso/{...}/aso` (prefix `/pcmso`) | JSON — sem PDF | POR-ITEM (exame/funcionário) | ver controller (router montado em `main_production.py:738`, sem gate explícito no include) | `health_occupational/controllers/pcmso_controller.py:306` |
| ASO — busca por ID | `GET /api/v1/pcmso/aso/{...}` | JSON | POR-ITEM | idem | `health_occupational/controllers/pcmso_controller.py:383` |
| ASO — assinatura do funcionário | `POST /api/v1/pcmso/aso/{...}/assinatura` | JSON | POR-ITEM | idem | `health_occupational/controllers/pcmso_controller.py:453` |
| Ficha de EPI do funcionário (histórico de entregas) | `GET /api/v1/epi/.../ficha` (prefix `/epi`) | JSON | POR-ITEM (funcionário) | idem | `health_occupational/controllers/epi_controller.py:266` |
| Termo/registro de entrega de EPI (+ assinatura NR-6) | `POST /api/v1/epi/entrega` / `.../assinatura` | JSON | POR-ITEM | idem | `health_occupational/controllers/epi_controller.py:310`, `:464` |
| Mapa/PPRA-PGR de riscos ocupacionais (NR-9) | `GET /api/v1/ppra/{...}` (prefix `/ppra`) | JSON | POR-ITEM / POR-SETOR / POR-FUNÇÃO | idem | `health_occupational/controllers/ppra_controller.py:122`, `:245`, `:280` |

> Nenhum endpoint de `health_occupational` emite PDF/HTML/XLSX (grep de `StreamingResponse`/`FileResponse`/`application/pdf`/`reportlab`/`openpyxl` = 0 hits no módulo). ASO e Ficha de EPI são exatamente os documentos que a NR exige em papel assinado — hoje só JSON.

### Services — Relatórios de serviço (JSON, com campo `pdf_url` órfão)

| Documento | Método + Path completo | Formato | Granularidade | Auth/gate | Arquivo:linha |
|---|---|---|---|---|---|
| Relatório de serviço (obter) | `GET /api/v1/services/reports/{report_id}` | JSON | POR-ITEM | (sem gate no include, `main_production.py:439`) | `services/controllers/service_controller.py:636` |
| Relatório de serviço (listar) | `GET /api/v1/services/reports` | JSON | POR-TELA | idem | `services/controllers/service_controller.py:620` |
| Relatório de compliance de SLA | `GET /api/v1/services/sla-configs/{sla_id}/compliance-report` | JSON (dict) | POR-ITEM (SLA) | idem | `services/controllers/service_controller.py:824` |

> O modelo `ServiceReport` tem `pdf_url` + `set_pdf_url()` + `pdf_generated_at` (`services/models/service_report.py:110,173`), mas NÃO há endpoint que gere ou sirva esse PDF — campo órfão. Gap para o redesign.

### Retention / Recruitment / CCT / Mobile

- `retention` (onboarding/profile/climate/turnover): nenhum endpoint emite arquivo; tudo JSON. Grep de emissores de arquivo = 0.
- `recruitment` (candidates/applications/interviews/job-positions): nenhum endpoint de currículo/KYC/dossiê em PDF/HTML. Tudo JSON. **Gap: dossiê de candidato / KYC não tem geração documental neste módulo** (a integração Infosimples/KYC vive fora deste diretório).
- `cct` (compliance/salarios/jornadas/rescisao/beneficios/feriados, prefixo real `/api/v1/people-management/hr`): nenhum endpoint emite arquivo — cálculos e tabelas em JSON.
- `mobile`: nenhuma geração de documento. Única referência a "download" é uma URL de update do app (`mobile/controllers/mobile_controller.py:109`); `gateway/compression.py` só repassa `media_type` de respostas (não gera doc).

---

## D. SEM ROTA HTTP (em produção)

| Item | Situação | Arquivo:linha |
|---|---|---|
| `pessoas/` | Pacote-fachada: só arquivos `__init__.py` re-exportando subpacotes. ZERO controllers/routers próprios (0 `APIRouter`, 0 `*controller*.py`). Nenhum documento é gerado a partir deste diretório — DP/RH/folha/ponto vivem em `departamento_pessoal`/`recursos_humanos` como subpacotes sem router aqui. | `pessoas/**/__init__.py` |
| `security_lgpd/` (consent, erasure, pia, masking, encryption, audit, status) | Router `security_lgpd_router` (prefix `/lgpd`) só é montado via `api/v1/__init__.py:345` (`prefix="/security"` → `/security/lgpd/...`). **`main_production.py` NÃO inclui o router de `api/v1` — logo estes endpoints NÃO estão no app de produção.** Além disso são todos JSON (registro/consulta de consentimento, solicitação/status de esquecimento, PIA) — nenhum emite Termo de Consentimento/Certidão de Exclusão em PDF/HTML. | `security_lgpd/__init__.py:37-46`; controllers `security_lgpd/controllers/*.py` |
| `equipment_management` — instalação/manutenção/RFID | Sem geração de documento (laudo/OS em PDF). Apenas o comodato tem os 3 stubs da seção B. | `equipment_management/services/*` |
| `lgpd/routes/delete_me.py` — `POST /api/v1/me/anonymize`, `DELETE /api/v1/me` | Não são documentos (ações de anonimização/exclusão, retornam JSON de status). Só o `/export` (seção A) é download. | `lgpd/routes/delete_me.py:376,414` |

---

## Resumo executivo

- **Total de endpoints que emitem ARQUIVO real hoje: 3** — 2 PDFs jurídicos (parecer, comunicação DET) + 1 export JSON LGPD (`/me/export`). Todos os 3 já serviriam botão "abrir/baixar" no redesign.
- **3 stubs de PDF** (comodato: contract/delivery/return-term) que retornam URL falsa sem gerar bytes → precisam de gerador real + rota GET.
- **~18 recursos documentais servidos só como JSON** que o redesign deveria oferecer em HTML+PDF e não há geração: dossiês jurídicos (5), leituras DET/parecer/análise (3), SST (ASO, ficha/termo EPI, PPRA — ~6 rotas), relatórios de serviço + compliance SLA (3). Campo `pdf_url` órfão em `ServiceReport`.
- **Formatos observados:** PDF (só jurídico, reportlab), JSON (todo o resto; 1 como download). **Nenhum XLSX/CSV/XML** gerado em nenhum dos 11 módulos.
- **Granularidade:** predominantemente POR-ITEM (com id na rota). POR-TELA: panorama jurídico, listas (pareceres/análises/reports), `/me/export` (self).
- **Gates:** jurídico e services sem gate de permissão no include (só usuário logado); comodato/health = `CurrentActiveUser`/logado; `security_lgpd` inteiro fora do app de produção; `pessoas` sem rota.
