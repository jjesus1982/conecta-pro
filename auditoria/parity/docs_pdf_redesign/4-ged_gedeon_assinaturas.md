# Inventário — Documentos gerados/entregues: GED · GEDEON · Documents · Document Kits · Signatures · GDrive

Escopo: `/opt/conecta-pro/backend/modules/{gedeon,ged,documents,document_kits,signatures,gdrive}/`
App em produção: `main_production.py` (`main.py` é DEV). Prefixo base do `api_router` = **`/api/v1`** (`main_production.py:336`, montado em `:1385`).

Convenções de gate:
- **GED module** (`/api/v1/ged/*`): `get_current_user` / `CurrentActiveUser` (autenticado). `ged_integration_router` e `ged_certidoes_router` incluídos sob flags try/except.
- **GEDEON module**: TODAS as rotas recebem gate `require_permission("module:ged")` injetado em runtime por `_gatear_rotas_ged()` (`gedeon/controllers/__init__.py:16-43`). `gedeon_consultor_router` leva `_GED_GATE` extra (`main_production.py:1201`).
- **nfse_router / fin_overview_router** (do módulo `ged`, mas montados em `/api/v1/financial`): `_FIN_GATE = require_permission` financeiro (`main_production.py:691,700`).
- **Onvio**: dois routers, ambos prefix `/onvio` → `/api/v1/onvio`. `onvio_router` = `gedeon/onvio/controllers/onvio_controller.py` (guias/documentos); `onvio_stats_router` = `gedeon/controllers/onvio_controller.py` (stats/sync).

---

## 1. ENTREGA DIRETA DE ARQUIVO (FileResponse / StreamingResponse / blob) — prioridade máxima p/ botões HTML+PDF

| Documento | Método + Path completo | Formato(s) | Granularidade | Auth/gate | Arquivo:linha |
|---|---|---|---|---|---|
| Download de arquivo de documento GED (o binário armazenado) | GET `/api/v1/ged/documents/{document_id}/download` | `FileResponse` — `document.mime_type` (PDF/imagem/qualquer) | POR-ITEM (`document_id` UUID) | current_user | `ged/controllers/document_controller.py:568` |
| ZIP do kit com TODOS os PDFs (contracheque, VA/VT/VR, folha ponto, escala, comp. salário…) | GET `/api/v1/ged/kits/{kit_id}/download-zip` | `StreamingResponse` — ZIP de PDFs (`application/zip`) | POR-ITEM (`kit_id` = kit por condomínio/competência) | current_user | `ged/controllers/kit_pdf_controller.py:547` |
| Baixar PDF da CND emitida (Federal/FGTS/Estadual/Municipal/Trab.) | GET `/api/v1/gedeon/cnd/pdf/{document_type}` | `FileResponse` — `application/pdf` | POR-ITEM (`document_type`: federal/fgts/…) | module:ged | `gedeon/controllers/cnd_controller.py:248` |

## 2. GERAÇÃO DE PDFs / KITS (produz arquivos, retorna JSON de status; download via §1)

| Documento | Método + Path completo | Formato(s) | Granularidade | Auth/gate | Arquivo:linha |
|---|---|---|---|---|---|
| Gerar PDFs reais de todos os docs de UM kit | POST `/api/v1/ged/kits/{kit_id}/generate-pdfs` | Gera PDFs (padrão-ouro) → JSON contagem | POR-ITEM (`kit_id`) | current_user | `ged/controllers/kit_pdf_controller.py:308` |
| Gerar PDFs de TODOS os kits (lote) | POST `/api/v1/ged/kits/generate-all-pdfs` | PDFs em lote → JSON | POR-TELA (agregado) | current_user | `ged/controllers/kit_pdf_controller.py:389` |
| Anexar NFS-e (PDF) ao kit | POST `/api/v1/ged/kits/{kit_id}/add-nfse` | Anexa PDF de NFS-e ao kit | POR-ITEM (`kit_id`) | current_user | `ged/controllers/kit_pdf_controller.py:479` |
| Gerar Kit Real de 1 condomínio | POST `/api/v1/ged/kit-real/{kit_id}/gerar` | Monta kit (docs reais) → JSON | POR-ITEM (`kit_id`) | current_user | `ged/controllers/kit_real_controller.py:863` |
| Gerar Kit Real de TODOS | POST `/api/v1/ged/kit-real/gerar-todos` | Kits em lote → JSON | POR-TELA | current_user | `ged/controllers/kit_real_controller.py:873` |
| Checklist do Kit Real (o que tem/falta) | GET `/api/v1/ged/kit-real/{kit_id}/checklist` | JSON (checklist — renderizável HTML/PDF) | POR-ITEM (`kit_id`) | current_user | `ged/controllers/kit_real_controller.py:907` |
| Montar kit (auto-assemble genérico) | POST `/api/v1/ged/kits/montar` · `/kits` · POST `/auto-assemble` | Monta kits → JSON | POR-TELA / POR-ITEM | current_user | `ged/controllers/auto_assemble_controller.py:569,301,24` |
| Detalhe do kit (docs + assinaturas) | GET `/api/v1/ged/kits/{kit_id}` | JSON (visão do kit) | POR-ITEM (`kit_id`) | current_user | `ged/controllers/auto_assemble_controller.py:183` |
| Assinaturas do kit | GET `/api/v1/ged/kits/{kit_id}/assinaturas` | JSON | POR-ITEM (`kit_id`) | current_user | `ged/controllers/auto_assemble_controller.py:249` |

## 3. ENVIO DE KIT AO CLIENTE (entrega por Drive + e-mail)

| Documento | Método + Path completo | Formato(s) | Granularidade | Auth/gate | Arquivo:linha |
|---|---|---|---|---|---|
| Enviar kit (GDrive + Email atômico, exige 100%) | POST `/api/v1/ged/kits/{kit_id}/enviar` | Entrega docs ao cliente (Drive+email) | POR-ITEM (`kit_id`) | current_user | `ged/controllers/auto_assemble_controller.py:403` |
| Enviar kit (variante `send`) | POST `/api/v1/ged/kits/{kit_id}/send` | Envio → JSON | POR-ITEM (`kit_id`) | current_user | `ged/controllers/auto_assemble_controller.py:349` |
| Solicitar assinaturas do kit | POST `/api/v1/ged/kits/{kit_id}/solicitar-assinaturas` | Cria pedidos de assinatura | POR-ITEM (`kit_id`) | current_user | `ged/controllers/auto_assemble_controller.py:267` |
| Montar E enviar kit ao cliente (Drive) | POST `/api/v1/gdrive/kits/{cliente_id}/{competencia}/montar-e-enviar` | Monta no Drive + envia → links | POR-ITEM (`cliente_id`+`competencia`) | current_user | `gdrive/controllers/gdrive_controller.py:177` |
| Enviar kit por e-mail (Drive) | POST `/api/v1/gdrive/kits/{client_id}/{competencia}/enviar-email` | Email c/ link do kit | POR-ITEM (`client_id`+`competencia`) | current_user | `gdrive/controllers/gdrive_controller.py:288` |
| Montar kit no Drive (sem enviar) | POST `/api/v1/gdrive/kits/{client_id}/{competencia}/montar` | Monta pasta/docs no Drive | POR-ITEM (`client_id`+`competencia`) | current_user | `gdrive/controllers/gdrive_controller.py:329` |
| Obter link do kit montado no Drive | GET `/api/v1/gdrive/kits/{client_id}/{competencia}/link` | `{share_link}` (webViewLink Drive) | POR-ITEM (`client_id`+`competencia`) | current_user | `gdrive/controllers/gdrive_controller.py:359` |
| Portal do cliente — histórico 24 meses de kits + share_link | GET `/api/v1/gdrive/portal/{client_id}/kits` | JSON lista {competencia, share_link} | POR-TELA (por cliente, N kits) | current_user | `gdrive/controllers/gdrive_controller.py:374` |
| Listar kits no Drive | GET `/api/v1/gdrive/kits` | JSON lista | POR-TELA | current_user | `gdrive/controllers/gdrive_controller.py:126` |

## 4. GEDEON — Orquestrador de kits (fichas, entrega, faturamento, painéis) — `/api/v1/gedeon/kits`

| Documento | Método + Path completo | Formato(s) | Granularidade | Auth/gate | Arquivo:linha |
|---|---|---|---|---|---|
| Ficha individualizada do kit de 1 condomínio (montagem ponto-a-ponto) | GET `/api/v1/gedeon/kits/ficha?condominio=&competencia=` | JSON ficha (renderizável HTML/PDF) | POR-ITEM (`condominio`+`competencia`) | module:ged | `gedeon/controllers/orquestrador_controller.py:255` |
| Visão por funcionário (todos os docs de 1 pessoa) | GET `/api/v1/gedeon/kits/funcionario` | JSON dossiê por funcionário | POR-ITEM (funcionário) | module:ged | `gedeon/controllers/orquestrador_controller.py:411` |
| Funcionários da folha do condomínio | GET `/api/v1/gedeon/kits/funcionarios` | JSON lista | POR-TELA (por condomínio) | module:ged | `gedeon/controllers/orquestrador_controller.py:400` |
| Preparar entrega do kit (gera CAPA/ÍNDICE + selo ATLAS, sobe no Drive) | POST `/api/v1/gedeon/kits/entrega/preparar?condominio=&competencia=` | Gera PDF de capa/índice → Drive | POR-ITEM (`condominio`+`competencia`) | module:ged | `gedeon/controllers/orquestrador_controller.py:423` |
| Marcar kit como entregue | POST `/api/v1/gedeon/kits/entrega/marcar` | JSON status | POR-ITEM | module:ged | `gedeon/controllers/orquestrador_controller.py:446` |
| Status de entrega do kit | GET `/api/v1/gedeon/kits/entrega/status` | JSON | POR-ITEM | module:ged | `gedeon/controllers/orquestrador_controller.py:456` |
| Faturar kit — emitir NFS-e e/ou boleto (preview se confirmar=false) | POST `/api/v1/gedeon/kits/faturar` | Gera NFS-e (XML) + boleto Inter (PDF) | POR-ITEM (kit/condomínio) | module:ged (dinheiro-que-sai: `confirmar`) | `gedeon/controllers/orquestrador_controller.py:365` |
| Conferência automática do kit (selo ATLAS) | GET `/api/v1/gedeon/kits/conferir` | JSON selo | POR-ITEM (`condominio`) | module:ged | `gedeon/controllers/orquestrador_controller.py:285` |
| Selo de conferência de TODOS (dashboard) | GET `/api/v1/gedeon/kits/conferir-lote` | JSON | POR-TELA | module:ged | `gedeon/controllers/orquestrador_controller.py:319` |
| Completude REAL dos kits + checklist (lê o Drive) | GET `/api/v1/gedeon/kits/completude` | JSON % por condomínio | POR-TELA | module:ged | `gedeon/controllers/orquestrador_controller.py:524` |
| Painel de completude (contagem por subpasta + link Drive) | GET `/api/v1/gedeon/kits/painel?competencia=` | JSON + links Drive | POR-TELA | module:ged | `gedeon/controllers/orquestrador_controller.py:659` |
| Cronograma do mês (quando cada doc deve estar pronto) | GET `/api/v1/gedeon/kits/cronograma` | JSON cronograma | POR-TELA | module:ged | `gedeon/controllers/orquestrador_controller.py:589` |
| Pendências de assinatura (VT/VR não assinado no Sólides) | GET `/api/v1/gedeon/kits/assinaturas` | JSON | POR-TELA/ITEM | module:ged | `gedeon/controllers/orquestrador_controller.py:467` |
| Alinhamento DP (folha do kit × Sólides + afastamentos) | GET `/api/v1/gedeon/kits/dp/alinhamento` | JSON | POR-ITEM | module:ged | `gedeon/controllers/orquestrador_controller.py:382` |
| Anexar arquivo ao kit (upload manual) | POST `/api/v1/gedeon/kits/upload` | Upload → Drive | POR-ITEM (condomínio) | module:ged | `gedeon/controllers/orquestrador_controller.py:147` |
| Excluir arquivo do kit (lixeira) | DELETE `/api/v1/gedeon/kits/arquivo` | — | POR-ITEM | module:ged | `gedeon/controllers/orquestrador_controller.py:203` |
| Disparar montagem do kit do mês (assíncrono) | POST `/api/v1/gedeon/kits/montagem` | task → JSON | POR-TELA/ITEM | module:ged | `gedeon/controllers/orquestrador_controller.py:40` |
| Status da montagem | GET `/api/v1/gedeon/kits/montagem/{task_id}` | JSON | POR-ITEM (`task_id`) | module:ged | `gedeon/controllers/orquestrador_controller.py:79` |

## 5. GEDEON — Kit builder / contexto / CND / consultor / colaborador — `/api/v1/gedeon`

| Documento | Método + Path completo | Formato(s) | Granularidade | Auth/gate | Arquivo:linha |
|---|---|---|---|---|---|
| Completude do kit documental de 1 condomínio | GET `/api/v1/gedeon/kits/completude/{condominio_id}?mes_ref=` | JSON (docs presentes/faltantes) | POR-ITEM (`condominio_id`) | module:ged | `gedeon/controllers/kit_controller.py:38` |
| Completude dos kits em lote | GET `/api/v1/gedeon/kits/lote` | JSON | POR-TELA | module:ged | `gedeon/controllers/kit_controller.py:67` |
| Enviar kit GEDEON | POST `/api/v1/gedeon/kits/{condominio_id}/enviar` | Envio | POR-ITEM (`condominio_id`) | module:ged | `gedeon/controllers/kit_controller.py:92` |
| Contexto/kit do cliente na competência | GET `/api/v1/gedeon/context/{cliente_id}/{competencia}` (+ `/tipo2`) | JSON contexto | POR-ITEM | module:ged | `gedeon/controllers/gedeon_controller.py:43,65` |
| Conformidade documental do cliente | GET `/api/v1/gedeon/conformidade/{cliente_id}/{competencia}` | JSON | POR-ITEM | module:ged | `gedeon/controllers/gedeon_controller.py:131` |
| Status/config dos kits (visão geral) | GET `/api/v1/gedeon/kits/status` · `/kits/config` | JSON | POR-TELA | module:ged | `gedeon/controllers/gedeon_controller.py:159,204` |
| Pagamentos do colaborador (comprovantes Inter por nome) | GET `/api/v1/gedeon/colaborador/{nome}/pagamentos?mes_ref=` | JSON resumo (comprovantes PIX Inter) | POR-ITEM (`nome`) | module:ged | `gedeon/controllers/gedeon_controller.py:405` |
| Emitir CNDs (dispara robô assíncrono) | POST `/api/v1/gedeon/cnd/emitir` | Emite → gera PDFs de CND | POR-TELA (todas)/ITEM | module:ged | `gedeon/controllers/cnd_controller.py:58` |
| Status das CNDs + registradas | GET `/api/v1/gedeon/cnd/status` | JSON | POR-TELA | module:ged | `gedeon/controllers/cnd_controller.py:74` |
| Upload manual do PDF de CND | POST `/api/v1/gedeon/cnd/upload` | Recebe PDF | POR-ITEM (`document_type`) | module:ged | `gedeon/controllers/cnd_controller.py:150` |
| Consultor GED — analisar anexo enviado (PDF/DOCX/TXT/CSV) | POST `/api/v1/gedeon/consultor/perguntar-arquivo` | Recebe arquivo → resposta IA | POR-ITEM (upload) | module:ged + `_GED_GATE` | `gedeon/controllers/consultor_controller.py:73` |
| Consultor GED — panorama / perguntar / histórico | GET `/panorama` · POST `/perguntar` · GET `/historico` (base `/api/v1/gedeon/consultor`) | JSON | POR-TELA | module:ged + `_GED_GATE` | `gedeon/controllers/consultor_controller.py:48,57,104` |

## 6. GEDEON — Onvio (guias fiscais / documentos contábeis) — `/api/v1/onvio`

| Documento | Método + Path completo | Formato(s) | Granularidade | Auth/gate | Arquivo:linha |
|---|---|---|---|---|---|
| Documentos sincronizados do Onvio (contábeis) | GET `/api/v1/onvio/documentos` | JSON lista {nome_arquivo…} | POR-TELA | current_user | `gedeon/onvio/controllers/onvio_controller.py:127` |
| Guias FGTS (com `arquivo_pdf`) | GET `/api/v1/onvio/guias/fgts?mes_ref=` | JSON lista c/ caminho PDF | POR-TELA (lista) | current_user | `gedeon/onvio/controllers/onvio_controller.py:309` |
| Guias INSS (com `arquivo_pdf`) | GET `/api/v1/onvio/guias/inss?mes_ref=` | JSON lista c/ caminho PDF | POR-TELA (lista) | current_user | `gedeon/onvio/controllers/onvio_controller.py:343` |
| Resumo de valores fiscais | GET `/api/v1/onvio/valores-fiscais-resumo` | JSON | POR-TELA | current_user | `gedeon/onvio/controllers/onvio_controller.py:394` |
| Extrair valores das guias | POST `/api/v1/onvio/extrair-valores` | JSON | POR-TELA | current_user | `gedeon/onvio/controllers/onvio_controller.py:279` |
| Onvio (2º router) — documentos/stats/historico | GET `/api/v1/onvio/documentos` · `/stats` · `/historico` | JSON | POR-TELA | current_user | `gedeon/controllers/onvio_controller.py:164,33,138` |

> Nota: as guias FGTS/INSS expõem `arquivo_pdf` (caminho), mas **NÃO há rota FileResponse dedicada** para servir esse PDF nos módulos do escopo — servido estático ou via GED. Botão "baixar PDF" precisa de rota nova ou apontar ao caminho.

## 7. GED — Documentos individuais (visualização / preview / versões)

| Documento | Método + Path completo | Formato(s) | Granularidade | Auth/gate | Arquivo:linha |
|---|---|---|---|---|---|
| URL de preview do documento | GET `/api/v1/ged/documents/{document_id}/preview` | JSON `{url}` (aponta p/ download) | POR-ITEM (`document_id`) | current_user | `ged/controllers/document_controller.py:594` |
| URL de visualização (registra view) | GET `/api/v1/ged/documents/{document_id}/view-url` | JSON `{url}` | POR-ITEM (`document_id`) | current_user | `ged/controllers/document_controller.py:614` |
| Registrar download (contador) | POST `/api/v1/ged/documents/{document_id}/download` | JSON | POR-ITEM (`document_id`) | current_user | `ged/controllers/document_controller.py:554` |
| Documento por ID / por código | GET `/api/v1/ged/documents/{document_id}` · `/code/{code}` | JSON metadados | POR-ITEM | current_user | `ged/controllers/document_controller.py:292,306` |
| Documentos por pasta / pendentes / expirados | GET `/api/v1/ged/documents/folder/{folder_id}` · `/pending/approval` · `/pending/signature` · `/expired/list` · `/expiring/soon` | JSON listas | POR-TELA | current_user | `ged/controllers/document_controller.py:379,392,405,419,432` |
| Versão de documento (por id / atual / do documento) | GET `/api/v1/ged/document-versions/{version_id}` · `/document/{document_id}/current` · `/document/{document_id}` | JSON | POR-ITEM | current_user | `ged/controllers/document_version_controller.py:24,50,38` |

## 8. GED — Assinaturas eletrônicas (documento assinado, certificado, comprovante) — `/api/v1/ged/document-signatures`

| Documento | Método + Path completo | Formato(s) | Granularidade | Auth/gate | Arquivo:linha |
|---|---|---|---|---|---|
| Certificado de assinatura (comprovante) | GET `/api/v1/ged/document-signatures/{signature_id}/certificate` | JSON certificado (renderizável HTML/PDF) | POR-ITEM (`signature_id`) | current_user | `ged/controllers/document_signature_controller.py:417` |
| Verificar autenticidade da assinatura | POST `/api/v1/ged/document-signatures/{signature_id}/verify` | JSON verificação | POR-ITEM | current_user | `ged/controllers/document_signature_controller.py:261` |
| Assinatura por token (link de assinatura) | GET `/api/v1/ged/document-signatures/token/{token}` | JSON | POR-ITEM (`token`) | público (token) | `ged/controllers/document_signature_controller.py:100` |
| Documento totalmente assinado? / próximo signatário | GET `/api/v1/ged/document-signatures/document/{document_id}/fully-signed` · `/next` | JSON | POR-ITEM (`document_id`) | current_user | `ged/controllers/document_signature_controller.py:361,350` |
| Assinaturas de 1 documento / pendentes | GET `/api/v1/ged/document-signatures/document/{document_id}` · `/pending` | JSON | POR-ITEM | current_user | `ged/controllers/document_signature_controller.py:146,158` |

## 9. SIGNATURES — Assinatura Universal (multi-documento) — `/api/v1/signatures`

| Documento | Método + Path completo | Formato(s) | Granularidade | Auth/gate | Arquivo:linha |
|---|---|---|---|---|---|
| Criar solicitação de assinatura | POST `/api/v1/signatures/requests` | JSON | POR-ITEM | current_user | `signatures/controllers/signature_controller.py:76` |
| Status de assinatura por documento (tipo+id) | GET `/api/v1/signatures/document/{document_type}/{document_id}` | JSON status | POR-ITEM (`document_type`+`document_id`) | current_user | `signatures/controllers/signature_controller.py:134` |
| Meus documentos pendentes de assinatura (self-service) | GET `/api/v1/signatures/meus-pendentes` | JSON lista | POR-TELA (por usuário) | current_user | `signatures/controllers/signature_controller.py:151` |
| Assinar (individual / lote) | POST `/api/v1/signatures/{request_id}/sign` · `/assinar-lote` | JSON | POR-ITEM / lote | current_user | `signatures/controllers/signature_controller.py:224,190` |
| Verificar assinatura por hash | GET `/api/v1/signatures/verify/{signature_hash}` | JSON verificação | POR-ITEM (`hash`) | público | `signatures/controllers/signature_controller.py:338` |
| Página pública de assinatura (info + assinar) | GET/POST `/api/v1/signatures/public/{token}` | JSON info / assina | POR-ITEM (`token`) | público (token) | `signatures/controllers/signature_controller.py:356,386` |

> `signatures` gerencia o ciclo de assinatura; **não serve o PDF assinado por si** — o binário final é baixado via GED (§1 `/ged/documents/{id}/download`).

## 10. DOCUMENT KITS — kits/atribuições/checklist de documentos — `/api/v1/document-kits`

| Documento | Método + Path completo | Formato(s) | Granularidade | Auth/gate | Arquivo:linha |
|---|---|---|---|---|---|
| Kit (definição) por id / itens | GET `/api/v1/document-kits/{kit_id}` · `/{kit_id}/items` | JSON | POR-ITEM (`kit_id`) | current_user | `document_kits/controllers/kit_controller.py:142,279` |
| Atribuição de kit (assignment) / pendentes / atrasados | GET `/api/v1/document-kits/assignments/{assignment_id}` · `/pending` · `/overdue` | JSON | POR-ITEM / POR-TELA | current_user | `document_kits/controllers/kit_controller.py:433,403,418` |
| Status por item do kit (checklist: enviar/aprovar/rejeitar) | GET `/api/v1/document-kits/item-statuses/{status_id}` + POST `/submit`·`/approve`·`/reject` | JSON checklist + upload | POR-ITEM (`status_id`) | current_user | `document_kits/controllers/kit_controller.py:582,597,619,636` |
| Docs expirando / conformidade (IA) | GET `/api/v1/document-kits/ai/expiring` · `/ai/compliance/{entity_type}/{entity_id}` | JSON | POR-TELA / POR-ITEM | current_user | `document_kits/controllers/kit_controller.py:747,695` |
| Gerar kits mensais / em lote (operacional) | POST `/api/v1/document-kits-operational/generate/monthly` · `/generate/batch` | Gera kits → JSON | POR-TELA | current_user | `document_kits/controllers/operational_controller.py:239,301` |
| Funcionários/condomínios elegíveis a kit | GET `/api/v1/document-kits-operational/employees` · `/condominiums` | JSON | POR-TELA | current_user | `document_kits/controllers/operational_controller.py:33,147` |

## 11. GED — Certidões (CNDs) / Integração RH / Relatórios / NFS-e

| Documento | Método + Path completo | Formato(s) | Granularidade | Auth/gate | Arquivo:linha |
|---|---|---|---|---|---|
| Certidões (lista / por id) | GET `/api/v1/ged/certidoes` · `/certidoes/{certidao_id}` | JSON | POR-TELA / POR-ITEM | current_user (flag) | `ged/controllers/ged_certidoes_controller.py:97,317` |
| Sincronizar certidões | POST `/api/v1/ged/certidoes/sync` · `/sync/{param}` | JSON | POR-TELA / POR-ITEM | current_user | `ged/controllers/ged_certidoes_controller.py:188,212` |
| Contracheques do funcionário (agregação de docs) | GET `/api/v1/ged/ged-integration/contracheques/{employee_id}` | JSON lista de docs/links | POR-ITEM (`employee_id`) | current_user (flag) | `ged/controllers/ged_integration_controller.py:83` |
| Onboarding / SST (ASO) do funcionário | GET `/api/v1/ged/ged-integration/onboarding/{employee_id}` · `/sst/{employee_id}` | JSON docs | POR-ITEM (`employee_id`) | current_user | `ged/controllers/ged_integration_controller.py:31,140` |
| ASOs vencendo | GET `/api/v1/ged/ged-integration/sst/asos/vencendo` | JSON | POR-TELA | current_user | `ged/controllers/ged_integration_controller.py:184` |
| Institucional: CCT / comunicados | GET `/api/v1/ged/ged-integration/institucional/cct` · `/comunicados` | JSON docs | POR-TELA | current_user | `ged/controllers/ged_integration_controller.py:226,268` |
| Relatórios GED (por cliente / compliance / assinaturas / mensal) | GET `/api/v1/ged/reports/by-client` · `/reports/compliance` · `/reports/signatures` · `/reports/monthly` | JSON (SEM export CSV/PDF) | POR-TELA | current_user | `ged/controllers/ged_config_controller.py:79,115,154,292` |
| Estatísticas GED | GET `/api/v1/ged/stats` | JSON | POR-TELA | current_user | `ged/controllers/ged_stats_controller.py:22` |
| Emitir NFS-e (fatura) — gera XML/nota | POST `/api/v1/financial/nfse/emitir` | Gera XML NFS-e + código verificação | POR-ITEM (contrato/nota) | `_FIN_GATE` | `ged/controllers/nfse_controller.py:79` |
| NFS-e (lista / dashboard) | GET `/api/v1/financial/nfse` · `/nfse/dashboard` | JSON | POR-TELA | `_FIN_GATE` | `ged/controllers/nfse_controller.py:277,358` |

> **NFS-e**: `nfse_controller.py` está fisicamente em `ged/` mas é montado em `/api/v1/financial` e é o motor de faturamento. Emite XML; o **DANFSE (PDF) / XML download** propriamente ditos vivem no módulo fiscal (fora do escopo destes 6 módulos).

---

## SEM ROTA HTTP (geração de documento sem endpoint dedicado de entrega)

- **`documents/` (Document Intelligence)** — SEM rota de entrega de documento. Todo o controller (`documents/controllers/document_controller.py`) é ingestão/OCR/classificação/extração/templates (upload, run-ocr, classify, extract-data, process, list/get/create/delete template). Nenhum `FileResponse`/`StreamingResponse`/download. `get_template` (`:480`) devolve JSON, não arquivo.
- **Geração de PDF em serviços (sem rota própria)**: capa/índice do kit em `gedeon/services/kit_entrega_service.py:176` (exposto só via `POST /gedeon/kits/entrega/preparar`); montagem de PDFs padrão-ouro chamada por `kit_pdf_controller`. Branding centralizado (`pdf_branding.py`) — sem endpoint.
- **Guias FGTS/INSS (Onvio)**: expõem `arquivo_pdf` (caminho) em JSON mas **sem rota FileResponse** para servir o binário nos módulos do escopo (§6).
- **Drive (webViewLink)**: `gdrive/services/gdrive_service.py:364,387` e `kit_drive_service.py:189,207` retornam `webViewLink` do Google Drive — o arquivo em si é servido pelo Google, não por endpoint próprio; o backend só entrega o link (§3).
