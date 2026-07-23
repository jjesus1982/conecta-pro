# Inventário de Documentos — Governo & Integrações

Módulos varridos: `government_integrations`, `integrations`, `monitoring`, `audit` + lado gov de `fiscal` / `fiscal_contabil`.
Prefixo global: `/api/v1`. Router gov agrega sub-routers sob `/government/<sub>` (ver `government_integrations/controllers/__init__.py:52`).

> READ-ONLY. Paths ancorados em arquivo:linha reais. "Documento fiscal/gov depende de transmissão real" está sinalizado na coluna **Gate**. Nada marcado como transmitido/autorizado sem transmissão efetiva.

---

## A) Documentos RENDERIZADOS de verdade (endpoint devolve arquivo: PDF/HTML/XML/TXT)

| Documento | Método + Path completo | Formato(s) | Granularidade | Auth/gate | Arquivo:linha |
|---|---|---|---|---|---|
| Comprovante de pagamento PIX/TED/Boleto/DARF/GPS (PDF timbrado padrão-ouro) | GET `/api/v1/financeiro/inter/payments/{payment_id}/comprovante` | PDF (inline) | POR-ITEM `payment_id` | Auth + `_FIN_GATE`; **só emite se pagamento REAL concluído no Inter** (exige `inter_payment_id`; 409 se status preparado/aprovado/cancelado/erro) — depende de transmissão bancária real | integrations/inter/payment_controller.py:606 |
| PDF real da guia (DARF/GPS/FGTS/DAS) sincronizada do Drive Portte/Onvio | GET `/api/v1/fiscal/guias-drive/pdf/{obligacao_id}?download=0\|1` | PDF (inline ou attachment) | POR-ITEM `obligacao_id` | Auth; arquivo real do Drive (baixa por `drive_file_id`) — sem fabricação | fiscal_contabil/obrigacoes/guias_drive_controller.py:75 |
| PDF do boleto Inter (link/URL vindo da API Inter) | GET `/api/v1/financeiro/inter/cobrancas/{cobranca_id}/pdf` | JSON `{pdf_url}` (URL do PDF no Inter) | POR-ITEM `cobranca_id` | Auth + `_FIN_GATE`; consulta API Inter real (404 se sem PDF) | integrations/inter/inter_controller.py:459 |
| Boleto — código de barras + linha digitável + link PDF | GET `/api/v1/integrations/banking/boleto/{boleto_id}` | JSON (barcode/linha/pdf link do adapter) | POR-ITEM `boleto_id` | Auth + `_FIN_GATE`; adapter Inter real (erro se banco não configurado) | integrations/banking/controllers/banking_controller.py:824 |
| Arquivo SPED Fiscal (EFD ICMS/IPI) — download | POST `/api/v1/government/sped-fiscal/gerar/download` | TXT (`text/plain`, attachment `SPED_<ini>_<fim>.txt`) | POR-TELA (período; sem id persistido) | Auth | government_integrations/controllers/sped_fiscal_controller.py:321 |
| Arquivo SPED Contábil (ECD) — download | POST `/api/v1/government/sped-contabil/gerar/download` | TXT (`text/plain`, attachment `ECD_<ano>.txt`) | POR-TELA (período) | Auth | government_integrations/controllers/sped_contabil_controller.py:318 |
| XML do CT-e — download | POST `/api/v1/government/cte/gerar-xml/download` | XML (`application/xml`, attachment `CTe_<n>_<serie>.xml`) | POR-TELA (payload; sem id) | Auth; **XML gerado, NÃO transmitido/autorizado na SEFAZ** | government_integrations/controllers/cte_controller.py:171 |
| XML do MDF-e — download | POST `/api/v1/government/mdfe/gerar-xml/download` | XML (`application/xml`, attachment `MDFe_<n>.xml`) | POR-ITEM `mdfe_id` (no body) | Auth; **XML gerado, NÃO transmitido/autorizado** | government_integrations/controllers/mdfe_controller.py:125 |

---

## B) PLACEHOLDERS / não-implementado (rota existe mas conteúdo é fake — NÃO ligar ao botão sem corrigir)

| Documento | Método + Path completo | Formato(s) | Granularidade | Auth/gate | Arquivo:linha |
|---|---|---|---|---|---|
| DANFE NFC-e (cupom fiscal) | GET `/api/v1/government/nfce/danfe/{chave_acesso}?formato=pdf\|html\|escpos` | PDF/HTML/ESC-POS | POR-ITEM `chave_acesso` | Auth; **PLACEHOLDER** — PDF = `b"PDF_PLACEHOLDER"`, HTML estático, `# TODO: Gerar DANFE real` | government_integrations/controllers/nfce_controller.py:429 |
| XML autorizado NFC-e — download | GET `/api/v1/government/nfce/xml/{chave_acesso}` | XML | POR-ITEM `chave_acesso` | Auth; **PLACEHOLDER** — XML hardcoded `# TODO: Buscar XML do banco/storage`; diz "Autorizado" sem transmissão real | government_integrations/controllers/nfce_controller.py:492 |

---

## C) "Documento-DADO" — endpoint devolve JSON estruturado do documento (guia/DAS/DARF/certidão/situação). Precisa de renderização HTML/PDF no redesign; HOJE não há endpoint de arquivo

| Documento | Método + Path completo | Formato(s) | Granularidade | Auth/gate | Arquivo:linha |
|---|---|---|---|---|---|
| DAS Simples Nacional (guia de pagamento) | POST `/api/v1/government/simples-nacional/das` | JSON (`StandardResponse.data.das`: valor, PIX/barcode) | POR-TELA (competência+receitas) | Auth; guia calculada, **não transmitida ao PGDAS/gov** | government_integrations/controllers/simples_nacional_controller.py:254 |
| PGDAS-D (declaração) | POST `/api/v1/government/simples-nacional/pgdasd` | JSON | POR-TELA | Auth; não transmitido | government_integrations/controllers/simples_nacional_controller.py:190 (região dos POSTs) |
| GRFGTS — guia mensal FGTS (com PIX) | POST `/api/v1/government/fgts-digital/guia-mensal` | JSON (`data.guia`: valor_total, PIX) | POR-TELA (competência+trabalhadores) | Auth; guia calculada, **não transmitida** | government_integrations/controllers/fgts_digital_controller.py:163 |
| GRRF — guia rescisória FGTS (com PIX) | POST `/api/v1/government/fgts-digital/guia-rescisoria` | JSON (`data.guia`) | POR-ITEM (rescisão) | Auth; não transmitida | government_integrations/controllers/fgts_digital_controller.py:195 |
| Relatório mensal FGTS | POST `/api/v1/government/fgts-digital/relatorio-mensal` | JSON | POR-TELA (competência) | Auth | government_integrations/controllers/fgts_digital_controller.py:307 |
| DARFs DCTFWeb (guias de recolhimento) | POST `/api/v1/government/dctfweb/gerar-darfs` | JSON (`data`: N DARFs) | POR-TELA (período apuração) | Auth; DARFs calculados, **não transmitidos** | government_integrations/controllers/dctfweb_controller.py:245 |
| Situação fiscal e-CAC | GET `/api/v1/government/ecac/situacao-fiscal?cpf_cnpj=` | JSON | POR-TELA (contribuinte) | Auth; e-CAC (scraping cav.receita) | government_integrations/controllers/ecac_controller.py:58 |
| Débitos fiscais e-CAC | GET `/api/v1/government/ecac/debitos` | JSON (inclui `pdf_url` p/ guias com PDF no Drive quando existente) | POR-TELA (filtros) | Auth | government_integrations/controllers/ecac_controller.py:89; pdf_url em services/ecac_service.py:76 |
| Declarações transmitidas e-CAC | GET `/api/v1/government/ecac/declaracoes` | JSON | POR-TELA (tipo+exercício) | Auth | government_integrations/controllers/ecac_controller.py:119 |
| Certidão fiscal CND/CPEN (e-CAC) — emitir | POST `/api/v1/government/ecac/certidao` | JSON (`data`: tipo, numero, codigo_controle) | POR-TELA (finalidade+cpf_cnpj) | Auth; **emissão via e-CAC — depende de consulta real; não gera PDF de certidão hoje** | government_integrations/controllers/ecac_controller.py:160 |
| Validação de certidão | POST `/api/v1/government/ecac/validar-certidao` | JSON (`valida` bool) | POR-ITEM (numero+codigo_controle) | Auth | government_integrations/controllers/ecac_controller.py:191 |
| Parcelamentos ativos e-CAC | GET `/api/v1/government/ecac/parcelamentos` | JSON | POR-TELA | Auth | government_integrations/controllers/ecac_controller.py:221 |
| Simulação de parcelamento | POST `/api/v1/government/ecac/simular-parcelamento` | JSON | POR-TELA | Auth; simulação (log "Parcelamento simulado") | government_integrations/controllers/ecac_controller.py:248 |
| Processos e-Processo e-CAC | GET `/api/v1/government/ecac/processos` | JSON | POR-TELA | Auth | government_integrations/controllers/ecac_controller.py:275 |
| Certidões sincronizadas (CND/CNDT/CRF) — lista | GET `/api/v1/government/sync/dados/certidoes/{cnpj}` | JSON (id, tipo, numero, validade, situacao) | POR-TELA (cnpj); itens têm `id` | Auth; espelho de certidões sincronizadas (sem arquivo servido) | government_integrations/controllers/sync_controller.py:1005 |
| Guias de recolhimento sincronizadas (DARF/GPS/FGTS) — lista | GET `/api/v1/government/sync/dados/guias/{cnpj}` | JSON | POR-TELA (cnpj) | Auth; vazio-honesto se tabela não provisionada | government_integrations/controllers/sync_controller.py:1051 |
| Documentos fiscais sincronizados (NF-e/CT-e/NFS-e) — lista | GET `/api/v1/government/sync/dados/documentos/{cnpj}` | JSON | POR-TELA (cnpj) | Auth | government_integrations/controllers/sync_controller.py:860 |
| Guias FGTS (lista) | GET `/api/v1/government/fgts/guias` | JSON | POR-TELA | Auth | government_integrations/controllers/fgts_inss_controller.py:129 |
| Guias INSS (lista) | GET `/api/v1/government/inss/guias` | JSON | POR-TELA | Auth | government_integrations/controllers/fgts_inss_controller.py:173 |

---

## D) eSocial — eventos, recibos, protocolos, espelho oficial

| Documento | Método + Path completo | Formato(s) | Granularidade | Auth/gate | Arquivo:linha |
|---|---|---|---|---|---|
| Transmitir evento eSocial (S-2200/2299/2220…) | POST `/api/v1/government/esocial/evento` | JSON | POR-ITEM (evento) | Auth; **TRANSMISSÃO REAL ao eSocial** (dinheiro-que-não-sai mas obrigação legal — depende de cert /transmissão) | government_integrations/controllers/esocial_controller.py:69 |
| Status/recibo de evento por protocolo | GET `/api/v1/government/esocial/consultar/{protocolo}` | JSON (status, recibo) | POR-ITEM `protocolo` | Auth; reflete transmissão real | government_integrations/controllers/esocial_controller.py:116 |
| Histórico de eventos transmitidos (com protocolo/recibo) | GET `/api/v1/government/esocial/eventos` | JSON (fonte real `eventos_esocial`; vazio-real se sem transmissão) | POR-TELA (filtros); itens têm `id`/protocolo/recibo | Auth; **só transmissões efetivas** — nunca catálogo disfarçado | government_integrations/controllers/esocial_controller.py:173 |
| Eventos suportados (catálogo) | GET `/api/v1/government/esocial/eventos-suportados` | JSON | POR-TELA (estático) | Auth | government_integrations/controllers/esocial_controller.py:157 |
| Espelho oficial eSocial — resumo (por tipo/ano) | GET `/api/v1/government/esocial/espelho/resumo` | JSON | POR-TELA | Auth | government_integrations/controllers/esocial_espelho_controller.py:72 |
| Timeline do funcionário no eSocial (eventos no gov) | GET `/api/v1/government/esocial/espelho/timeline/{cpf}` | JSON | POR-ITEM `cpf` | Auth; espelho enumerado (10 acessos/dia), vazio-honesto | government_integrations/controllers/esocial_espelho_controller.py:80 |
| Sincronizar espelho eSocial (task Celery) | POST `/api/v1/government/esocial/espelho/sincronizar` | JSON (dispara task) | POR-TELA | Auth | government_integrations/controllers/esocial_espelho_controller.py:44 |

---

## E) NFS-e (lado gov) — Manaus / Nacional

| Documento | Método + Path completo | Formato(s) | Granularidade | Auth/gate | Arquivo:linha |
|---|---|---|---|---|---|
| Emitir NFS-e Manaus (ABRASF 2.04) | POST `/api/v1/government/nfse-manaus/emitir` | JSON (dados NFS-e; **sem endpoint de DANFSE/PDF**) | POR-ITEM (RPS) | Auth; depende de transmissão à Prefeitura | government_integrations/controllers/nfse_manaus_controller.py:31 |
| Consultar NFS-e por RPS / número | GET `/api/v1/government/nfse-manaus/consultar-*` | JSON | POR-ITEM | Auth | government_integrations/controllers/nfse_manaus_controller.py:100,150 |
| Cancelar NFS-e Manaus | POST `/api/v1/government/nfse-manaus/cancelar` | JSON | POR-ITEM | Auth | government_integrations/controllers/nfse_manaus_controller.py:194 |
| NFS-e Padrão Nacional (DPS/emitir/consultar/cancelar) | rotas sob `/api/v1/government/nfse-nacional/…` | JSON | POR-ITEM | Auth; migração 2026 | government_integrations/controllers/nfse_nacional_controller.py:33 |
| NFS-e Multi-Empresa | rotas sob `/api/v1/fiscal/nfse-multi/…` | JSON | POR-ITEM | Auth (`_FISCAL_GATE` no mount) | fiscal/controllers/nfse_multi_controller.py:21 |

> Nenhum destes serve DANFSE em PDF/HTML — o redesign precisaria de um gerador de DANFSE dedicado.

---

## SEM ROTA HTTP (data-only; nenhum documento/arquivo é servido)

- **Auditoria / LGPD** (`audit/controllers/audit_controller.py`): TODAS as rotas devolvem JSON tipado — logs (`/audit/logs`, l.78), stats, regras de compliance, verificações, retenção de dados, histórico de acessos, dashboards (`/audit/dashboard` l.578; `/audit/compliance/overview` l.586; `/audit/security/overview` l.594). **Nenhum export CSV/XLSX/PDF de relatório de auditoria ou dossiê LGPD.** → relatório de auditoria/LGPD exportável = **INEXISTENTE** (candidato a criar).
- **Monitoring** (`monitoring/controllers/*.py`): `/api/v1/monitoring/dashboard`, `/api/v1/realtime/dashboard`, `/api/v1/realtime/anomalies/summary` — só JSON. Nenhum `media_type`/`FileResponse`/export.
- **Sólides (integração RH/DP)** (`integrations/controllers/solides_controller.py`): logs de sincronização `/api/v1/integrations/solides/logs` (l.770) e `/logs/{id}` (l.818), status (l.516), conflitos — **JSON, sem export de relatório de sync**. Idem Tangerino/GED (webhooks/tasks, sem doc de saída).
- **Dashboard integrações gov** (`government_integrations/controllers/dashboard_controller.py`): status/métricas/eventos/alertas de certificado — JSON.
- **Certificados A1** (`certificate_controller.py`): upload/validar/listar/obter/remover/chave-pública/testar-assinatura — **não há download do .pfx** (correto: segredo). Chave pública (l.376) devolve texto, não é doc de usuário.
- **Gov.br / DET** (`govbr_controller.py`): apenas fluxo OAuth (URL de autorização, callback, refresh token, dados usuário, empresas vinculadas). **Nenhum documento DET (caixa postal/intimação) é gerado ou baixado aqui.**
- **KYC Infosimples (dossiê RH)**: NÃO reside nestes módulos (fora de escopo — módulo `pessoas`).
- **`gerar_xml` (sem `/download`)** de CT-e/MDF-e (cte_controller.py:115, mdfe_controller.py:101) e `gerar`/`gerar_arquivo` sem `/download` de SPED (sped_fiscal:282, sped_contabil:278): devolvem o conteúdo dentro de `StandardResponse.data` (JSON), não como arquivo — o arquivo real está nas variantes `/download` da Seção A.

---

## Resumo executivo
- **Total de itens inventariados:** ~40 endpoints voltados a documento.
- **Arquivos renderizados de verdade (Seção A): 8** — 2 PDF reais gerados (comprovante Inter, guia-drive Portte/Onvio), 2 PDF via URL de terceiro (boleto Inter/banking), 2 TXT SPED, 2 XML (CT-e/MDF-e, gerados mas NÃO transmitidos).
- **Placeholders (Seção B): 2** — DANFE e XML de NFC-e (fake `PDF_PLACEHOLDER`/XML hardcoded; NÃO ligar botão sem corrigir).
- **Documento-dado sem arquivo (Seção C): ~19** — DAS/PGDAS-D, GRFGTS/GRRF, DARFs DCTFWeb, situação/débitos/certidão/parcelamentos e-CAC, listas de certidões/guias/documentos sincronizados. Precisam de renderizador HTML/PDF (hoje só JSON).
- **eSocial (Seção D): 8** — eventos/recibos/protocolos/espelho (transmissão real sinalizada; recibo é dado, sem PDF de recibo).
- **NFS-e gov (Seção E): 5** — JSON, sem DANFSE.
- **Por granularidade:** POR-ITEM (com id): comprovante Inter, guia-drive PDF, boletos, MDF-e, DANFE/XML NFC-e, timeline eSocial por CPF, eventos/consulta por protocolo, emissões/consultas NFS-e. POR-TELA (período/filtro, sem id persistido): SPED (fiscal/contábil), CT-e, DAS/PGDAS/GRFGTS/DARFs, situação/débitos/parcelamentos e-CAC, listas de sync, dashboards.
- **Depende de transmissão real (não afirmar "autorizado/transmitido" sem ela):** eSocial evento/consulta/eventos; NFS-e Manaus/Nacional; CT-e e MDF-e (XML gerado ≠ autorizado); NFC-e (placeholder); DAS/DARFs/GRFGTS (calculados ≠ transmitidos). Comprovante Inter JÁ tem o gate correto (só emite após pagamento concluído).
- **Lacunas notáveis (nada a inventariar, candidatos a criar):** relatório de auditoria/LGPD exportável, dossiê KYC (fora destes módulos), relatório de sync Sólides/Tangerino/Inter exportável, DANFSE PDF de NFS-e, PDF de certidão CND/CNDT/CRF, PDF de recibo eSocial.
