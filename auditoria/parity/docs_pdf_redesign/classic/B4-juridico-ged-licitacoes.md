# B4 — Mineração do CLÁSSICO: Documentos abrir HTML + baixar PDF

Áreas: **JURÍDICO · GED · DOCUMENTOS · LICITAÇÕES · SEGURANÇA · EQUIPAMENTOS**
Fonte (spec viva): `/opt/conecta-pro/frontend/src/app/modulos/` (todas as `.tsx`).
Convenções:
- `abrirPdf(url,{download,nome})` = helper `src/lib/pdf.ts:5` → `fetch` com `Bearer` (localStorage) → `blob` → `window.open`/`<a download>`; anexa `?download=1` quando `download:true`.
- Alvo REDESIGN = rota unificada `/redesign/[modulo]` (dados via `backend/.../redesign_builders/<mod>.py`); GED do clássico vive dentro do módulo **gestao-de-pessoas**.
- **STUB** = botão sem handler / entrega só client-side / TODO.
- Endpoints ancorados na linha do `fetch`/`abrirPdf`; botão ancorado na linha do `onClick`/JSX.

---

## JURÍDICO → REDESIGN `/redesign/juridico`

| Documento | Tela clássica (rota) | Botão | Endpoint (método+path) | Formato | Módulo+tela REDESIGN | Arquivo:linha |
|---|---|---|---|---|---|---|
| Parecer jurídico (PDF) | `/modulos/juridico/pareceres` | "Baixar PDF" (ícone Download) | GET `/api/v1/juridico/pareceres/{id}/pdf` → `blob`→`window.open` | PDF (nova aba) | juridico / Pareceres | `juridico/pareceres/page.tsx:246` (btn) · `:95-102` (handler) · `:98` (fetch) |
| Comunicação/intimação DET → dossiê | `/modulos/juridico/det` | "Enviar PDF" (upload `.pdf,.txt`) | POST `/api/v1/juridico/det/comunicacao/upload` (multipart) | INGEST (entra PDF; saída = dossiê JSON, sem download) | juridico / DET | `juridico/det/page.tsx:102-103` (input) · `:45` (fetch) · `:113` (dossiê #id) |
| Petição/processo → análise | `/modulos/juridico/processos` | "Enviar PDF do processo" (upload) | POST `/api/v1/juridico/det/...` análise (texto/arquivo) | INGEST (sem download de saída) | juridico / Processos | `juridico/processos/page.tsx:145-146` |
| Contrato — assinatura pendente | `/modulos/juridico/contratos` | (apenas Badge "assinar", sem botão) | — (dashboard/list `/api/v1/juridico/contratos`) | Nenhuma afordância de download/assinar aqui | juridico / Central de Contratos | `juridico/contratos/page.tsx:141` |

> Subdirs sem afordância de doc: `juridico/{analise,riscos,conhecimento,consultor,escritorio}` (painéis/IA, sem abrir/baixar PDF).

---

## LICITAÇÕES → REDESIGN `/redesign/licitacoes`

| Documento | Tela clássica (rota) | Botão | Endpoint (método+path) | Formato | Módulo+tela REDESIGN | Arquivo:linha |
|---|---|---|---|---|---|---|
| Edital (portal externo) | `/modulos/licitacoes/editais/[id]` | "Ver Edital" (ícone Download) | `<a href={tenderData.link}>` alvo `_blank` | Link EXTERNO (PNCP/portal), não PDF interno | licitacoes / Editais · detalhe | `licitacoes/editais/[id]/page.tsx:181-183` |
| Certidão / CND (consultar emissor) | `/modulos/licitacoes/certidoes` | "Consultar" `<a>` + botão ExternalLink | `<a href={doc.url_consulta}>` · `window.open(doc.url_consulta)` | Link EXTERNO de consulta (não arquivo local) | licitacoes / Certidões | `licitacoes/certidoes/page.tsx:609` · `:651` |
| Oportunidade — portal | `/modulos/licitacoes/oportunidades` | "Ver no Portal" (ExternalLink) | `window.open(op.url_portal)` | Link EXTERNO | licitacoes / Oportunidades | `licitacoes/oportunidades/page.tsx:658` |
| Proposta (Carta Proposta / docs) | `/modulos/licitacoes/propostas/[id]` | "Gerar PDF" (Download) | **sem `onClick`** | **STUB** (README confirma "Exportação PDF" pendente) | licitacoes / Propostas · detalhe | `licitacoes/propostas/[id]/page.tsx:354-355` · `propostas/README.md:314` |
| Editais — Buscar/Sincronizar PNCP | `/modulos/licitacoes/editais` | ícones Download/CloudDownload | POST sync PNCP (`handleBuscarPNCP`/`handleSincronizarPNCP`) | Sync (não é download de documento) | licitacoes / Editais | `licitacoes/editais/page.tsx:187,196` |

> `licitacoes/{disputas,resultados,contratos}` e `contratos/[id]`: sem afordância abrir/baixar documento.

---

## DOCUMENTOS → REDESIGN `/redesign/documentos`

| Documento | Tela clássica (rota) | Botão | Endpoint (método+path) | Formato | Módulo+tela REDESIGN | Arquivo:linha |
|---|---|---|---|---|---|---|
| Visualizar arquivo GED | `/modulos/documentos/arquivos` | "Visualizar" (ícone Eye) | GET `/api/v1/ged/documents/{id}/view-url` → `window.open(url)` | HTML/inline (URL assinada, nova aba) | documentos / Arquivos | `documentos/arquivos/page.tsx:500` (btn) · `:298-299` (handler) |
| Download do arquivo GED | `/modulos/documentos/arquivos` | "Download" (ícone Download) | GET `/api/v1/ged/documents/{id}/download` (`responseType blob`) | Qualquer mime (blob→`<a download>`) | documentos / Arquivos | `documentos/arquivos/page.tsx:503` (btn) · `:311` · hook `hooks/ged/useGedDocuments.ts:40-46` |
| Assinar documento | `/modulos/documentos` (tab Assinaturas) | "Assinar" | abre `SignatureDialog` → mutation de assinatura | Assinatura (sem download de PDF) | documentos / (assinaturas) | `documentos/page.tsx:485-486` · `:83` (handleSign) |
| Kits de documentos | `/modulos/documentos/kits` | (Criar/Editar/Duplicar template) | `useDocumentKits` CRUD | Nenhum download (templates) | documentos / Kits | `documentos/kits/page.tsx:36-40` |

---

## GED (clássico `gestao-pessoas/ged/*`) → REDESIGN `/redesign/gestao-de-pessoas`

| Documento | Tela clássica (rota) | Botão | Endpoint (método+path) | Formato | Módulo+tela REDESIGN | Arquivo:linha |
|---|---|---|---|---|---|---|
| Kit completo em ZIP (todos os PDFs) | `/modulos/gestao-pessoas/ged/kits/[id]` | "ZIP" (Download) | GET `/api/v1/ged/kits/{kitId}/download-zip` → `blob` ZIP | ZIP de PDFs | gestao-de-pessoas / GED · Kit | `gestao-pessoas/ged/kits/[id]/page.tsx:366-368` (btn) · `:255-258` (handler) |
| Documento individual do kit | `/modulos/gestao-pessoas/ged/kits/[id]` | "Baixar documento" (ícone) | GET `/api/v1/people-management/ged/documents/{doc.id}/download` → `blob` | PDF/qualquer (blob→`<a download>`) | gestao-de-pessoas / GED · Kit | `gestao-pessoas/ged/kits/[id]/page.tsx:508` (btn) · `:280-283` (handler) |
| Relatório GED — exibir/baixar | `/modulos/gestao-pessoas/ged/relatorios` | "Gerar/Exibir" | GET `/api/v1/ged{/reports/monthly\|/by-client\|/compliance\|/signatures}` → `blob` | PDF **ou** XLSX (por `content-type`) | gestao-de-pessoas / GED · Relatórios | `gestao-pessoas/ged/relatorios/page.tsx:104` · defs `:51-83` |
| Relatório GED — download PDF | `/modulos/gestao-pessoas/ged/relatorios` | "Baixar PDF" | GET `/api/v1/ged{endpoint}/download?format=pdf` → `blob` | PDF | gestao-de-pessoas / GED · Relatórios | `gestao-pessoas/ged/relatorios/page.tsx:142` |
| CND coletada (arquivo) | `/modulos/gestao-pessoas/ged/certidoes` | ícone abrir (quando `file_url`) | `window.open(cert.file_url)` (Drive/arquivo) · coleta: POST `/api/v1/ged/coleta-automatica/cnds/run` | PDF (nova aba) · coleta assíncrona | gestao-de-pessoas / GED · Certidões | `gestao-pessoas/ged/certidoes/page.tsx:604-605` · `:155` (run) |
| Kit no Drive (webViewLink) | `/modulos/gestao-pessoas/ged` | link "kit" / anexo | `<a href={kit.drive_link}>` / `<a href={a.link}>` `_blank` | Link Drive (abre doc) | gestao-de-pessoas / GED · Painel | `gestao-pessoas/ged/page.tsx:207` · `:258` |
| Kit — Índice/capa + docs no Drive | `/modulos/gestao-pessoas/ged/kit` | "Índice/capa", links de docs | `<a href={indice_link}>` · `<a href={d.link}>` · `<a href={f.drive_link}>` | Links Drive (PDF capa/índice + docs) | gestao-de-pessoas / GED · Kit gestão | `gestao-pessoas/ged/kit/KitGestaoSecoes.tsx:141,229` · `kit/page.tsx:166,325` |
| Condomínio no Drive (montar) | `/modulos/gestao-pessoas/ged/montar-kit` | link Drive | `<a href={c.drive_link}>` `_blank` | Link Drive | gestao-de-pessoas / GED · Montar kit | `gestao-pessoas/ged/montar-kit/page.tsx:313` |
| Enviar kit ao cliente | `/modulos/gestao-pessoas/ged/envios` | "Enviar" / "Gerar link" | link cliente client-side `origin/area-cliente/kit/{id}`+clipboard; POST `/api/v1/document-kits/{id}/activate` | Entrega LEVE (marca ativo; link portal) — **STUB** vs Drive+email real | gestao-de-pessoas / GED · Envios | `gestao-pessoas/ged/envios/page.tsx:407-409` (btn) · `:181-198` (send) · `:215-217` (link) |
| Notificar kit/CND por WhatsApp | `/modulos/gestao-pessoas/ged/whatsapp` | "Enviar notificação/alerta/custom" | POST `/api/v1/whatsapp/send/{kit-notification\|certificate-alert\|custom}` | Envia link do kit / alerta CND | gestao-de-pessoas / GED · WhatsApp | `gestao-pessoas/ged/whatsapp/page.tsx:160,191,221` |
| Assinar documento do kit | `/modulos/gestao-pessoas/ged/assinaturas` | "Assinar" / "Recusar" | POST `/api/v1/ged/document-signatures/{id}/sign` · `/refuse` | Assinatura (sem download de PDF/comprovante aqui) | gestao-de-pessoas / GED · Assinaturas | `gestao-pessoas/ged/assinaturas/page.tsx:271` (btn) · `:155,185` |
| Solicitar assinaturas / enviar / aprovar kit | `/modulos/gestao-pessoas/ged/kits/[id]` | botões de ação | POST `/api/v1/ged/kits/{kitId}/{solicitar-assinaturas\|send\|approve}` | Ações de fluxo (não download) | gestao-de-pessoas / GED · Kit | `gestao-pessoas/ged/kits/[id]/page.tsx:184,234,249` |
| Anexar PDF/planilha ao consultor | `/modulos/gestao-pessoas/ged/consultor` | "Anexar (PDF/planilha)" | upload multipart (IA) | INGEST | gestao-de-pessoas / GED · Consultor | `gestao-pessoas/ged/consultor/page.tsx:526-527` |
| Upload documento GED | `/modulos/gestao-pessoas/ged/upload` | drop/seleção (PDF/img/Office ≤50MB) | POST upload GED | INGEST (auto-classifica certidão/CND) | gestao-de-pessoas / GED · Upload | `gestao-pessoas/ged/upload/page.tsx:56,66,223-225` |

---

## EQUIPAMENTOS → REDESIGN `/redesign/equipamentos`

| Documento | Tela clássica (rota) | Botão | Endpoint (método+path) | Formato | Módulo+tela REDESIGN | Arquivo:linha |
|---|---|---|---|---|---|---|
| Contrato de comodato (PDF) | `/modulos/equipamentos/comodatos` | "Baixar contrato" (menu) | `abrirPdf('/api/v1/comodatos/{id}/contract-pdf',{download:true})` → GET `...?download=1` | PDF (download) | equipamentos / Comodatos | `equipamentos/comodatos/page.tsx:395` · helper `:4` |
| Termo de entrega (PDF) | `/modulos/equipamentos/comodatos` | "Termo de entrega" (menu) | `abrirPdf('/api/v1/comodatos/{id}/delivery-term',{download:true})` | PDF (download) | equipamentos / Comodatos | `equipamentos/comodatos/page.tsx:399` |
| Assinar comodato | `/modulos/equipamentos/comodatos` | "Assinar" (+ modal) | mutation de assinatura | Assinatura (sem download aqui) | equipamentos / Comodatos | `equipamentos/comodatos/page.tsx:410` · modal `:520-522` |

> `equipamentos/{manutencoes,patrimonio}`: sem afordância de abrir/baixar documento.

---

## SEGURANÇA → REDESIGN `/redesign/seguranca`

**Nenhuma afordância de abrir HTML / baixar PDF encontrada.** Painéis LGPD read-only:
`seguranca/{page,criptografia,auditoria,consentimento,pia-dpia,esquecimento,mascaramento}`.
O rótulo "Exportação de Dados" em `auditoria/page.tsx:48` é um *tipo de evento de log*, não um botão de download.
DPIA/PIA (`pia-dpia`) e "direito ao esquecimento" (`esquecimento`) não geram/baixam relatório no clássico → **lacuna (candidato a novo doc), não migração**.
