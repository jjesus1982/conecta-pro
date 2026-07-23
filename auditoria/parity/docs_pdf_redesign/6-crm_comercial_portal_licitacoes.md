# Inventário de Documentos — CRM / Comercial / Portal do Cliente / Licitações / Empresas / Clients / Marketing

**Escopo:** `/opt/conecta-pro/backend/modules/{crm,comercial,client_portal,bidding,empresas,clients,marketing}/`
**Objetivo redesign:** cada documento gerado precisa de botão "abrir HTML" + "baixar PDF".
**Data:** 2026-07-22 · READ-ONLY · âncoras arquivo:linha reais.

## Mapa de prefixos (produção = `main_production:app`, api_router base `/api/v1`)

| Router | Registro | Prefixo efetivo |
|---|---|---|
| crm proposal_controller | `/crm` + `/proposals` | `/api/v1/crm/proposals` |
| crm contract_controller | `/crm` + `/contracts` | `/api/v1/crm/contracts` |
| crm growth_controller | `/crm` + `/growth` | `/api/v1/crm/growth` |
| crm marketing_controller | (sem prefixo no registro) + `/marketing` | `/api/v1/marketing` |
| bidding (todos) | `/bidding` + prefixo do controller | `/api/v1/bidding/...` |
| client_portal (todos) | `/portal` + prefixo do controller | `/api/v1/portal/...` |
| empresas | `/empresas/...` (prefixo no próprio controller) | `/api/v1/empresas/...` |
| clients client_controller | `/clients` | `/api/v1/clients` |

> **`comercial`** é apenas AGREGADOR (re-exporta routers de crm+clients+bidding+services). Não tem rota própria. Subpastas (`propostas/`, `contratos/`, `leads/`, …) são stubs só com `__init__.py` vazio.
> **`marketing`** NÃO existe como diretório de módulo com arquivos; o "Marketing" é `crm/controllers/marketing_controller.py`.

---

## DOCUMENTOS COM ROTA HTTP (geram arquivo servido ao usuário)

| Documento | Método + Path completo | Formato(s) | Granularidade | Auth/gate | Arquivo:linha |
|---|---|---|---|---|---|
| **Proposta comercial / Orçamento** (proposta do CRM) | `GET /api/v1/crm/proposals/{proposal_id}/pdf` | PDF (inline). `?salvar=true` registra e devolve link público | POR-ITEM (`proposal_id`) | Usuário ativo (`CurrentActiveUser`) | crm/controllers/proposal_controller.py:37 |
| **Contrato** (contrato do CRM, padrão Conecta Mais c/ selo) | `GET /api/v1/crm/contracts/{contract_id}/pdf` | PDF (inline). `?salvar=true` → link público | POR-ITEM (`contract_id`) | Usuário ativo | crm/controllers/contract_controller.py:55 |
| **Documento registrado** (download público tokenizado de qualquer doc salvo no registro `crm_documents`) | `GET /api/v1/crm/growth/docs/download/{doc_id}?t=<token>` | PDF (inline) | POR-ITEM (`doc_id` + token) | PÚBLICO tokenizado (valida `token`, sem login) | crm/controllers/growth_controller.py:45 |
| **Lista de documentos gerados** (fornece `download_url` de cada doc) | `GET /api/v1/crm/growth/docs` | JSON c/ links de download | POR-TELA (lista) | Usuário ativo (db dep) | crm/controllers/growth_controller.py:67 |
| **Relatório Comercial** (MRR, clientes, pipeline, top deals) | `GET /api/v1/crm/growth/reports/comercial/pdf` | PDF (inline). `?salvar/teste/drive` | POR-TELA (snapshot do funil atual) | Usuário ativo | crm/controllers/growth_controller.py:1183 |
| **Recibo** de pagamento (padrão Conecta Mais c/ selo) | `POST /api/v1/crm/growth/docs/recibo/pdf` | PDF (inline). `?salvar/drive/teste` | POR-TELA (dados no body `ReciboIn`) | Usuário ativo | crm/controllers/growth_controller.py:1290 |
| **Ordem de Serviço** | `POST /api/v1/crm/growth/docs/ordem-servico/pdf` | PDF (inline). `?salvar/drive/teste` | POR-TELA (body `OrdemServicoIn`) | Usuário ativo | crm/controllers/growth_controller.py:1313 |
| **Termo Aditivo de contrato** (enriquece pelo contrato) | `POST /api/v1/crm/growth/docs/aditivo/pdf` | PDF (inline). `?salvar` (ref_tipo=contract) | POR-TELA (body `AditivoIn`; casa por `contrato_numero`) | Usuário ativo | crm/controllers/growth_controller.py:1362 |
| **Atestado de Capacidade Técnica** | `POST /api/v1/crm/growth/docs/atestado/pdf` | PDF (inline). `?salvar/drive/teste` | POR-TELA (body `AtestadoIn`) | Usuário ativo | crm/controllers/growth_controller.py:1404 |
| **Relatório de Visita** (técnica/comercial, c/ selo) | `POST /api/v1/crm/growth/visitas/pdf` | PDF (inline). `salvar=true` finaliza + registra | POR-ITEM (body `VisitaPdfIn.ref` → relatório existente) | Usuário ativo | crm/controllers/growth_controller.py:1740 |
| **Apresentação / Deck comercial** (padrão Conecta PRO) | `POST /api/v1/crm/growth/apresentacoes/gerar?formato=pptx\|pdf` | **PPTX** (attachment) ou **PDF** (inline). `salvar=true` (só pdf) → link | POR-TELA (body `ApresentacaoIn` com slides) | Usuário ativo | crm/controllers/growth_controller.py:1943 |
| **Apresentação de EXEMPLO** (proposta CFTV padrão) | `GET /api/v1/crm/growth/apresentacoes/exemplo` | PDF → devolve link público (via `_salvar_pdf`) | POR-TELA (fixo/demo) | db dep (sem login explícito) | crm/controllers/growth_controller.py:1981 |
| **Orçamento / Proposta pagamento único** (material/serviço, à vista ou parcelado, padrão-ouro) | `POST /api/v1/crm/growth/docs/orcamento/pdf` | PDF (inline). `?salvar/drive/teste` | POR-TELA (body `OrcamentoIn` c/ itens) | Usuário ativo | crm/controllers/growth_controller.py:2040 |
| **Documento de Kit (GED)** do Portal do Cliente | `GET /api/v1/portal/kits/{kit_id}/documents/{document_id}/download` | Arquivo binário (mime do doc — PDF/imagem/etc), anti-path-traversal `/app/uploads` | POR-ITEM (`kit_id` + `document_id`) | Cliente do portal (`get_current_portal_client`) | client_portal/controllers/kit_controller.py:140 |
| **Foto de checkpoint de ront/visita** (Raio-X da operação) | `GET /api/v1/portal/operacao/visitas/{round_id}/checkpoints/{checkpoint_id}/fotos/{nome}` | Imagem (FileResponse) | POR-ITEM (round+checkpoint+nome) | Cliente do portal | client_portal/controllers/operacao_controller.py:92 |
| **Plano de Contas (Domínio TOTVS)** — arquivo de importação contábil | `GET /api/v1/empresas/dominio/download/plano-contas/{empresa_slug}` | **TXT** (PlainTextResponse, attachment) | POR-ITEM (`empresa_slug`) | Usuário ativo | empresas/controllers/dominio_controller.py:63 |

---

## DOCUMENTOS/EXPORTAÇÕES QUE PRODUZEM CONTEÚDO MAS RETORNAM JSON (candidatos a botão HTML/PDF no redesign — hoje SEM download de arquivo)

| Documento | Método + Path | Formato atual | Granularidade | Auth | Arquivo:linha |
|---|---|---|---|---|---|
| **DRE** (Demonstração de Resultado) | `POST /api/v1/empresas/demonstrativos/dre` | JSON (dados do demonstrativo) | POR-TELA (body: empresa+período+dados) | Usuário ativo | empresas/controllers/statements_controller.py:40 |
| **Balanço Patrimonial** (sintético) | `POST /api/v1/empresas/demonstrativos/balanco` | JSON | POR-TELA | Usuário ativo | empresas/controllers/statements_controller.py:45 |
| **DFC** (Fluxo de Caixa indireto) | `POST /api/v1/empresas/demonstrativos/dfc` | JSON | POR-TELA | Usuário ativo | empresas/controllers/statements_controller.py:50 |
| **Consolidado do Grupo** (multi-CNPJ) | `POST /api/v1/empresas/demonstrativos/consolidado-grupo` | JSON | POR-TELA (lista de empresas) | Usuário ativo | empresas/controllers/statements_controller.py:55 |
| **Export Domínio — Plano de Contas** (JSON com `conteudo`+`nome_arquivo`) | `GET /api/v1/empresas/dominio/plano-contas/{empresa_slug}` | JSON (conteúdo TXT embutido) | POR-ITEM | Usuário ativo | empresas/controllers/dominio_controller.py:43 |
| **Export Domínio — Lançamentos contábeis** | `POST /api/v1/empresas/dominio/lancamentos` | JSON (conteúdo p/ Domínio) | POR-TELA (período+lançamentos) | Usuário ativo | empresas/controllers/dominio_controller.py:48 |
| **Export Domínio — Clientes** | `POST /api/v1/empresas/dominio/clientes` | JSON | POR-TELA | Usuário ativo | empresas/controllers/dominio_controller.py:53 |
| **Export Domínio — NFS-e** | `POST /api/v1/empresas/dominio/nfse` | JSON | POR-TELA (período+notas) | Usuário ativo | empresas/controllers/dominio_controller.py:58 |
| **Documentos do Edital** (lista/metadata do edital de licitação) | `GET /api/v1/bidding/tenders/{tender_id}/documentos` | JSON (metadata/links dos anexos do edital) | POR-ITEM (`tender_id`) | Usuário ativo | bidding/controllers/tender_controller.py:173 |
| **Portal — Notas Fiscais (NFS-e)** do cliente | `GET /api/v1/portal/financeiro/notas` | JSON (lista; PDFs/DANFSE vêm do módulo fiscal) | POR-TELA (cliente logado) | Cliente do portal | client_portal/controllers/financeiro_controller.py:20 |
| **Portal — Contrato** do cliente | `GET /api/v1/portal/financeiro/contrato` | JSON | POR-TELA | Cliente do portal | client_portal/controllers/financeiro_controller.py:25 |
| **Portal — Boletos** do cliente | `GET /api/v1/portal/financeiro/boletos` | JSON | POR-TELA | Cliente do portal | client_portal/controllers/financeiro_controller.py:30 |
| **Fatura de contrato público** (licitação → conta a receber) | `POST /api/v1/bidding/erp/fatura/{medicao_id}` | JSON (stub; NFS-e/financeiro pendente) | POR-ITEM (`medicao_id`) | Usuário ativo | bidding/controllers/erp_controller.py:157 |

---

## SEM ROTA HTTP (geram documento mas NÃO há endpoint que sirva o arquivo ao usuário)

| Documento | O que gera | Onde | Observação |
|---|---|---|---|
| **Documentos de proposta de licitação** (carta-proposta, planilha de custos, declarações, checklist de habilitação) | Agente Compiler renderiza PDFs reais (reportlab) e SALVA em disco `/opt/conecta-pro/backend/media/bidding/proposals/<edital>_<ts>/`; a rota só retorna metadata/paths, **não serve o PDF** | Rota: `POST /api/v1/bidding/agents/compiler/gerar` (bidding/controllers/agent_controller.py:744) → gera via bidding/agents/compiler_agent.py:451-462 (`render_pdf`/`save_pdf`) e bidding/agents/pdf_renderer.py:36 (`PDF_OUTPUT_DIR`) | **Falta rota de download** dos PDFs de licitação. Redesign precisa de endpoint FileResponse para esses arquivos. |
| **PDFs "salvar" registrados** | Todas as rotas CRM com `?salvar=true` chamam `docs_registry.salvar_pdf` → gravam arquivo + registro `crm_documents` e devolvem link; o link resolve por `GET /crm/growth/docs/download/{id}?t=` (já listado acima) | crm/services/docs_registry.py, crm/services/{proposal_pdf,contract_pdf,doc_pdf,report_pdf,presentation_builder}.py | Serviços de build de PDF (sem rota própria): `proposal_pdf.build_proposal_pdf`, `contract_pdf.build_contract_pdf`, `doc_pdf.build_{recibo,ordem_servico,aditivo,atestado,visit_report,orcamento}_pdf`, `report_pdf.build_commercial_report_pdf`, `presentation_builder.build_pptx/pptx_to_pdf`. |
| **Proposta anexada ao WhatsApp** (José Luís) | Gera PDF via `build_proposal_pdf` e envia como anexo pelo WhatsApp; não há download HTTP dedicado nesse fluxo | `POST /api/v1/crm/proposals/{id}/send-whatsapp` (proposal_controller.py:524) e `/send-completo` (proposal_controller.py:633) | O PDF só sai pelo WhatsApp; para download usar a rota `/{id}/pdf`. |

---

## NÃO são documentos (esclarecimento — descartados do escopo)

- `crm/controllers/marketing_controller.py` — copywriter/estrategista/conteúdo geram TEXTO em JSON (posts, planos), não arquivos.
- `crm/controllers/dashboard_controller.py`, `growth_controller` forecast/funil/relatorio-comercial (JSON), `consultor_cmo_controller.py` — respostas JSON de KPI/IA.
- `crm/controllers/proposal_controller.py:1005` — pixel de rastreio `image/gif` (tracking de abertura), não documento.
- `clients/controllers/client_controller.py`, `empresas/controllers/{empresa,obligations,dashboard,bookkeeper}_controller.py` — CRUD/JSON, sem geração de arquivo.
- bidding proposal/contract/dispute/sync/document controllers — CRUD/JSON; documentos de habilitação (`/bidding/documents`) são cadastro de metadados, não geração.

---

## RESUMO

- **Total de rotas que SERVEM arquivo ao usuário:** 16 (13 PDF/PPTX no CRM+growth; 1 binário Kit GED e 1 foto no Portal; 1 TXT Domínio).
- **Rotas que geram conteúdo mas retornam JSON** (candidatas fortes a ganhar botão HTML/PDF): 13 (4 demonstrativos financeiros DRE/Balanço/DFC/Consolidado, 4 exports Domínio, docs de edital, 3 do portal financeiro NFS-e/contrato/boleto, fatura licitação).
- **SEM rota de download** apesar de gerar PDF: documentos de proposta de licitação (Compiler agent → disco).

**Por formato:** PDF (dominante — propostas, contratos, recibo, OS, aditivo, atestado, orçamento, relatório, visita, apresentação, docs registrados), PPTX (apresentações), TXT (Domínio plano de contas), binário/imagem (Kit GED, fotos de checkpoint). Nenhum XLSX/CSV/XML servido diretamente por estes módulos (o XML/NFS-e é do fiscal; export Domínio é TXT).

**Por granularidade:**
- **POR-ITEM (com id):** proposta `/proposals/{id}/pdf`, contrato `/contracts/{id}/pdf`, doc registrado `/docs/download/{doc_id}`, visita `/visitas/pdf` (ref), Kit GED `{kit_id}/documents/{document_id}`, foto checkpoint, Domínio plano-contas `{empresa_slug}`, docs de edital `{tender_id}`, fatura `{medicao_id}`, aditivo (por `contrato_numero`).
- **POR-TELA (dados no body/snapshot):** relatório comercial, recibo, OS, atestado, orçamento, apresentação, DRE/Balanço/DFC/Consolidado, exports Domínio (lançamentos/clientes/nfse), portal financeiro.

**Gates:** CRM/empresas = usuário ERP ativo (`CurrentActiveUser`); Portal = token de cliente (`get_current_portal_client`); download de doc registrado (`/docs/download/{id}?t=`) = **público tokenizado** (sem login). Nenhum gate financeiro/OTP nestes documentos (são leitura/geração, não dinheiro-que-sai).
