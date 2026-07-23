# B5 — Resto do Clássico + Helpers de Documento (mineração)

Escopo: módulos NÃO cobertos pelos outros agentes (integracoes, configuracoes, relatorios,
analytics, bi, automacoes, agendador, assistente, saude/SST, documentos, empresas, equipamentos,
licitacoes, marketing, + demais dirs soltos) **E** o mapa completo dos helpers/utilitários de
documento compartilhados. READ-ONLY. Ancorado em arquivo:linha. Base:
`/opt/conecta-pro/frontend/src`.

---

## 1. TABELA DE AFORDÂNCIAS — TELAS RESTANTES

Formato: Documento | Tela (rota) | Botão | Endpoint | Formato | Redesign | Arquivo:linha

| Documento | Tela | Botão | Endpoint | Formato | Redesign? | Arquivo:linha |
|---|---|---|---|---|---|---|
| Status de Certidões | relatorios/central | "Gerar PDF" | client jsPDF; dados `GET /api/v1/bidding/certificates` | PDF (client) | Não | app/modulos/relatorios/central/page.tsx:90,116,393 |
| Headcount por Cliente | relatorios/central | "Gerar PDF" | client jsPDF; `GET /api/v1/operacional/employees/?page_size=200` | PDF (client) | Não | relatorios/central/page.tsx:143,393 |
| Resumo GED | relatorios/central | "Gerar PDF" | client jsPDF; `GET /api/v1/ged/documents/stats/summary` + `/document-kits/stats` + `/ged/document-signatures/stats/summary` | PDF (client) | Não | relatorios/central/page.tsx:174-176 |
| Integrações Governamentais | relatorios/central | "Gerar PDF" | client jsPDF; `GET /api/v1/government/dashboard/status` | PDF (client) | Não | relatorios/central/page.tsx:207 |
| Kits Documentais | relatorios/central | "Gerar PDF" | client jsPDF; `GET /api/v1/document-kits` | PDF (client) | Não | relatorios/central/page.tsx:236 |
| Resumo Financeiro | relatorios/central | "Gerar PDF" | client jsPDF; `GET /document-kits/stats` + `/bidding/certificates` + `/ged/documents/stats/summary` | PDF (client) | Não | relatorios/central/page.tsx:264-266,303 |
| BI Dashboard | bi/dashboard | "PDF" | client jsPDF (landscape); `GET /api/v1/financial/bi/dashboard`,`/nfse/dashboard`,`/headcount` | PDF (client) | Não | app/modulos/bi/dashboard/page.tsx:206,289,391 |
| BI Dashboard | bi/dashboard | "Excel" | client XLSX (múltiplas abas: KPIs/Cliente/Serviço/Headcount/Fiscal) | .xlsx (client) | Não | bi/dashboard/page.tsx:302-335,394 |
| Arquivo GED (qualquer) | documentos/arquivos | ícone/menu "Download" | `GET /api/v1/ged/documents/{id}/download` (via `downloadDocumentFile`) | blob (formato original) | Não | app/modulos/documentos/arquivos/page.tsx:309,503,517 |
| Visualizar arquivo GED | documentos/arquivos | "Visualizar" (Eye) | `window.open(viewData.url)` (URL assinada) | view externo | Não | documentos/arquivos/page.tsx:299 |
| Contrato de comodato | equipamentos/comodatos | "Contrato (PDF)" | `abrirPdf('/api/v1/comodatos/{id}/contract-pdf', {download})` | PDF | Não | app/modulos/equipamentos/comodatos/page.tsx:395 |
| Termo de entrega | equipamentos/comodatos | "Termo de entrega (PDF)" | `abrirPdf('/api/v1/comodatos/{id}/delivery-term', {download})` | PDF | Não | equipamentos/comodatos/page.tsx:399 |
| Plano de contas Domínio/TOTVS | empresas/demonstrativos (aba "Exportar Domínio TOTVS") | "Baixar" (Download) | `GET /api/v1/empresas/dominio/plano-contas/{empresaSlug}` → `downloadTxt` | .txt | Não | app/modulos/empresas/demonstrativos/page.tsx:661,722,768,784 |
| Lançamentos Domínio/TOTVS | empresas/demonstrativos | "Baixar" | `POST /api/v1/empresas/dominio/lancamentos` → `downloadTxt` | .txt | Não | empresas/demonstrativos/page.tsx:673,806,823 |
| NFS-e Domínio/TOTVS | empresas/demonstrativos | "Baixar" | `POST /api/v1/empresas/dominio/nfse` → `downloadTxt` | .txt | Não | empresas/demonstrativos/page.tsx:698,845,861 |
| ASO (anexo digitalizado) | gestao-pessoas/saude-ocupacional/exames | ícone Download | `sstService.downloadASOAnexo` → `GET /api/v1/people-management/sst/aso/{id}/anexo` | blob (PDF/JPG/PNG) | Não | app/modulos/gestao-pessoas/saude-ocupacional/exames/page.tsx:215,1170 |
| Ficha de EPI | gestao-pessoas/saude-ocupacional/epi | ícone "Baixar PDF da ficha" | `downloadFichaEPIPdf` → `GET .../sst/epi/fichas/{id}/pdf` | PDF | Não | app/modulos/gestao-pessoas/saude-ocupacional/epi/page.tsx:142,774 |
| Relatório Compliance NR-1 | gestao-pessoas/saude-ocupacional/compliance-nr1 | "Exportar relatório PDF" | `downloadNR1CompliancePdf` → `GET .../sst/nr1/compliance/pdf` | PDF | Não | app/modulos/gestao-pessoas/saude-ocupacional/compliance-nr1/page.tsx:133,177 |
| PPP (Perfil Profissiográfico) | compliance-nr1 + prontuario/[employeeId] | "PPP PDF" | `downloadPPPPdf` → `GET .../sst/ppp/{employeeId}/pdf` | PDF | Não | compliance-nr1/page.tsx:143,333 ; prontuario/[employeeId]/page.tsx:129,249 |
| Ficha de EPI | prontuario/[employeeId] | "Ficha EPI PDF" | `downloadFichaEPIPdf` → `GET .../sst/epi/fichas/{id}/pdf` | PDF | Não | prontuario/[employeeId]/page.tsx:146,489 |

### Botões-fantasma / STUBS (sem onClick — afordância prometida mas morta)
| Item | Tela | Situação | Arquivo:linha |
|---|---|---|---|
| "Exportar Agora" (Exportação para Contador / Domínio) | empresas/dashboard | Botão estilizado SEM handler onClick | app/modulos/empresas/dashboard/page.tsx:636-638 |
| "Gerar PDF" (Documentos da Proposta) | licitacoes/propostas/[id] | Botão SEM onClick; README lista "[ ] Exportação para PDF" | app/modulos/licitacoes/propostas/[id]/page.tsx:353 ; licitacoes/propostas/README.md:314 |
| "Ver Edital" | licitacoes/editais/[id] | `<a href={tenderData.link}>` externo (PNCP), NÃO gera documento | app/modulos/licitacoes/editais/[id]/page.tsx:180 |
| Lead magnets "PDF/Planilha" | marketing/lead-magnet | Apenas texto descritivo; ícone Download é decorativo de StatCard | app/modulos/marketing/lead-magnet/page.tsx:38,46 |

### DRE/Balanço/DFC/Consolidado (empresas/demonstrativos)
As abas DRE, Balanço, DFC e Consolidado fazem `POST /api/v1/empresas/demonstrativos/{dre|balanco|dfc|consolidado-grupo}`
mas renderizam o resultado NA TELA — **não há botão de download PDF/Excel** para esses demonstrativos
(demonstrativos/page.tsx:116,299,421,544). Só a aba "Exportar Domínio TOTVS" baixa arquivo (.txt).
Candidato claro para ganhar "abrir HTML + baixar PDF" no redesign.

### Módulos de escopo SEM nenhuma afordância de documento (confirmado por grep amplo)
`integracoes`, `configuracoes` (só upload de anexo em consultor/page.tsx:279), `analytics`,
`automacoes`, `agendador`, `assistente`, `saude-ocupacional` (top-level, vazio — o SST real
está sob gestao-pessoas/saude-ocupacional), `area-cliente`, `servicos`, `seguranca`,
`suprimentos`, `recrutamento`, `reembolso`, `campo`, `homologacao`. Nenhum jsPDF/XLSX/blob/
abrirPdf/print/`/download`/`-pdf`.

---

## 2. HELPERS DE DOCUMENTO (o padrão a replicar no redesign)

Existem **3 famílias distintas** de download autenticado (fetch Bearer→blob) + 2 de geração
client-side + componentes/wrappers. Não há UM helper único: `abrirPdf` é o mais usado, mas
convivem duplicatas. Isto é o mapa do padrão a unificar/portar.

### 2.1 `abrirPdf(url, opts)` — HELPER PRINCIPAL
- **Assinatura:** `abrirPdf(url: string, opts: { download?: boolean; nome?: string } = {}): Promise<void>`
- **Arquivo:** `src/lib/pdf.ts:5`
- **O que faz:** lê token de `localStorage(access_token||token)`, `fetch(url)` com `Authorization: Bearer`,
  se `download` acrescenta `&download=1`; em erro faz `alert()` com o `detail` REAL do servidor
  (ex.: "espelho ainda não calculado"); sucesso → blob → `URL.createObjectURL` →
  `window.open(_blank)` ou `<a download>`; revoga em 60s.
- **Usos: 22 call sites em 13 arquivos:**
  crm/contratos, dp/documentos, **equipamentos/comodatos** (escopo B5), financeiro/contas-pagar,
  financeiro/contas-receber, financeiro/nfse-entrada, financeiro/relatorios, fiscal/certidoes/emitir,
  fiscal/guias, fiscal/nfse, gestao-pessoas/ponto/espelho, operacional/rondas, rh/candidatos.

### 2.2 `baixarArquivoAutenticado(fileUrl, filename?)` — DUPLICATA (foco em `<a download>`)
- **Assinatura:** `baixarArquivoAutenticado(fileUrl: string, filename?: string): Promise<void>`
- **Arquivo:** `src/utils/baixarArquivoAutenticado.ts:13`
- **O que faz:** mesma ideia do abrirPdf (fetch Bearer→blob→`<a download>`), mas SEM param `download=1`,
  com fallback de nome via `Content-Disposition`, e lança `Error(detail)` em vez de `alert`.
- **Usos: 5 arquivos:** dp/rescisao, dp/folha, dp/aviso-previo,
  gestao-pessoas/dp/components/BotaoGerarContrato.tsx, gestao-pessoas/dp/components/BotaoAvisoPrevioFerias.tsx.

### 2.3 `downloadDocumentFile(documentId, fileName)` — GED
- **Assinatura:** `downloadDocumentFile(documentId: string, fileName: string): Promise<void>`
- **Arquivo:** `src/hooks/ged/useGedDocuments.ts:40`
- **O que faz:** `customInstance<Blob>({url:'/api/v1/ged/documents/{id}/download', responseType:'blob'})` →
  `createObjectURL` → `<a download>` → revoke.
- **Usos:** documentos/arquivos/page.tsx (handleDownload).

### 2.4 `sstService.download*` — família SST (axios responseType blob)
- **Arquivo:** `src/lib/services/sst.ts` (BASE=`/api/v1/people-management/sst`, linha 1062)
- **Membros:**
  - `downloadASOAnexo(asoId)` → `GET {BASE}/aso/{id}/anexo` — sst.ts:1121
  - `downloadFichaEPIPdf(fichaId)` → `GET {BASE}/epi/fichas/{id}/pdf` — sst.ts:1205
  - `downloadNR1CompliancePdf()` → `GET {BASE}/nr1/compliance/pdf` — sst.ts:1236
  - `downloadPPPPdf(employeeId)` → `GET {BASE}/ppp/{employeeId}/pdf` — sst.ts:1242
- **Retornam Blob cru** (a tela faz o objectURL/open). Usos: exames, epi, compliance-nr1, prontuario.

### 2.5 `ExportButton` — COMPONENTE reutilizável (Excel/PDF/CSV dropdown)
- **Assinatura (props):** `ExportButton({ data: any[]; filename: string; formats?: ('excel'|'pdf'|'csv')[];
  pdfTitle?; size?; variant?; buttonText?; disabled?; onExportSuccess?; onExportError? })`
- **Arquivo:** `src/components/ui/export-button.tsx:89`
- **O que faz:** dropdown com Excel/PDF/CSV; delega a `exportToExcel/exportToPDF/exportToCSV`;
  toasts de sucesso/erro; desabilita se `data` vazio.
- **Usos: 7 telas (todas operacional):** alocacoes, rondas, postos, ocorrencias, colaboradores,
  turnos, escalas (+ .bak/.corrupted ignorados).

### 2.6 `exportToExcel / exportToPDF / exportToCSV / formatDataForExport` — GERAÇÃO CLIENT-SIDE
- **Arquivo:** `src/utils/export.ts`
  - `exportToExcel(data: any[], filename: string)` — export.ts:21 — lazy `import('xlsx')`, auto-largura, `writeFile *_YYYYMMDD.xlsx`
  - `exportToPDF(data: any[], filename: string, title?: string)` — export.ts:61 — lazy `jspdf`+`jspdf-autotable`
  - `exportToCSV(data: any[], filename: string)` — export.ts:166 — xlsx `sheet_to_csv`, BOM UTF-8, `<a download>`
  - `formatDataForExport(data, fieldMapping)` — export.ts:206 — renomeia/filtra campos p/ export
- **Usos diretos (fora do ExportButton):** operacional/turnos, operacional/relatorios, operacional/postos.

### 2.7 Wrappers de geração de documento (botões-componente)
- `BotaoGerarContrato.tsx` (gestao-pessoas/dp/components) — usa `useGerarContratoTrabalho` + `baixarArquivoAutenticado(result.file_url)` — linha 22.
- `BotaoAvisoPrevioFerias.tsx` (gestao-pessoas/dp/components) — usa `useGerarAvisoPrevioFerias` + `baixarArquivoAutenticado`.
- **Consumidos por:** app/modulos/dp/funcionarios/page.tsx.
- Hooks correlatos: `src/hooks/useGerarContratoTrabalho.ts`, `src/hooks/useGerarAvisoPrevioFerias.ts`.

### 2.8 Helpers locais (inline, duplicados — anti-padrão a consolidar)
- `baixarBlob(blob, nomeArquivo)` — DUPLICADO em: compliance-nr1/page.tsx:31 e prontuario/[employeeId]/page.tsx:59.
- `downloadTxt(conteudo, nomeArquivo)` — inline em empresas/demonstrativos/page.tsx:722.
- `handleDownloadFichaPdf` (epi/page.tsx:142) e `handleDownload` (documentos/arquivos:309) — wrappers locais.

### 2.9 NÃO são afordância (registrado p/ evitar falso-positivo)
- `src/utils/file-helpers.ts` — só `formatFileSize(bytes)` (l.5) e `getFileIcon(filename)` (l.13). Sem download.
- `components/ged/DocumentShareDialog.tsx` / `DocumentVersionHistory.tsx` — falam de `max_downloads`/`download_count` (metadados), não baixam.

**Conclusão de padrão:** o redesign deve padronizar em `abrirPdf` (lib/pdf.ts) como helper canônico
para PDF autenticado, e `ExportButton`+`utils/export` para export tabular multi-formato. Hoje há
**3 implementações paralelas** do mesmo fetch-Bearer→blob (abrirPdf, baixarArquivoAutenticado,
downloadDocumentFile) + 2 helpers inline (baixarBlob×2, downloadTxt) — todas com a MESMA razão de
existir (o `<a href>` não carrega o Bearer do localStorage).

---

## 3. CENSO — afordâncias-documento por módulo clássico

Contagem via `grep -rn "abrirPdf|abrirDocumento|\.blob()|createObjectURL|/pdf|/download|<a download>"`
por módulo em `src/app/modulos/`. **Total do sistema = 101 ocorrências** (piso — a régua abaixo NÃO
captura geração client-side por jsPDF/XLSX nem `sstService.download*` por axios blob; ver nota).

| # | Módulo | Ocorrências |
|---|---|---|
| 1 | gestao-pessoas | 24 |
| 2 | dp | 19 |
| 3 | financeiro | 14 |
| 4 | meu-espaco | 12 |
| 5 | fiscal | 10 |
| 6 | rh | 5 |
| 7 | operacional | 4 |
| 8 | crm | 4 |
| 9 | juridico | 3 |
| 10 | equipamentos | 3 |
| 11 | portal | 2 |
| 12 | empresas | 1 |
| — | suprimentos, servicos, saude-ocupacional(top), relatorios, reembolso, recrutamento, marketing, licitacoes, integracoes, homologacao, documentos, configuracoes, campo, bi, automacoes, assistente, area-cliente, analytics, agendador | 0 cada |
| | **TOTAL SISTEMA (régua estreita)** | **101** |

### Nota — subcontagem da régua (afordâncias reais que a régua NÃO conta)
A régua marcou 0 em módulos que **têm** afordância via geração client-side ou axios-blob:
- **relatorios/central** — 6 relatórios × "Gerar PDF" (jsPDF), não contados.
- **bi/dashboard** — "PDF" (jsPDF) + "Excel" (XLSX), não contados.
- **empresas/demonstrativos** — 3 downloads .txt (Domínio) — parcialmente pega `createObjectURL` só no módulo empresas (contou 1).
- **gestao-pessoas/saude-ocupacional** — ~6 botões PDF via `sstService.download*` (axios `responseType:'blob'`) — contados dentro de gestao-pessoas mas não isoláveis como SST.
- **operacional** — `ExportButton` (Excel/PDF/CSV) em 7 telas usa `utils/export`, invisível à régua (só contou 4 de abrirPdf/rondas).

**Estimativa de piso REAL** somando as afordâncias client-side/axios-blob mineradas nesta B5
(~19 novas afordâncias de documento fora da régua): **≈120+ botões-documento no sistema.**
Os **101** são o número defensável e reproduzível pela régua pedida; os **~120+** incluem geração
client-side. Recomenda-se, para paridade total no redesign, portar TODAS as 19 afordãncias da
Seção 1 + os 3 stubs mortos (empresas/dashboard, licitacoes/propostas).
