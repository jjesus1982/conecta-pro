# B3 — Mineração do CLÁSSICO: botões "abrir HTML / baixar PDF / exportar" — OPERACIONAL + COMERCIAL

Fonte: `/opt/conecta-pro/frontend/src/app/modulos/` (READ-ONLY).
Áreas cobertas: `operacional`, `campo`, `crm`, `servicos`, `marketing`. (`comercial` existe mas está **vazio** — sem arquivos; `operacoes` não existe, o módulo é `operacional`.)

O clássico é a especificação viva. Cada linha = uma afordância de documento real que o redesign deve reproduzir. Arquivo:linha ancorado no código.

## Como o clássico gera/baixa documento (3 mecanismos reais)

1. **`<ExportButton>`** (`src/components/ui/export-button.tsx`) — export **client-side** de um array de dados via `exportToExcel/exportToPDF/exportToCSV` de `@/utils/export`. Gera **Excel (.xlsx) + PDF + CSV** no browser (jsPDF/SheetJS), sem endpoint de backend. Props: `data`, `filename`, `pdfTitle`, `formats`.
2. **`abrirPdf(url,{download,nome})`** (`src/lib/pdf.ts`) — `fetch` autenticado (Bearer do `localStorage`) → `blob` → `window.open`/download. **PDF gerado no backend.**
3. **Custom inline** — `URL.createObjectURL(blob)` (CSV montado à mão) ou `window.open('')+print()` (PDF via impressão do HTML), ou `api.get(...,{responseType:'blob'})`.

## Tabela de afordâncias

| Documento | Tela clássica (rota) | Botão | Endpoint (método+path) | Formato | Módulo+tela REDESIGN correspondente | Arquivo:linha |
|---|---|---|---|---|---|---|
| Relatório de Ocorrências Disciplinares | `/modulos/operacional/ocorrencias` | `<ExportButton buttonText="Exportar">` | client-side (`exportToExcel/PDF/CSV`), sem endpoint; `filename="ocorrencias"` | Excel + PDF + CSV | Redesign OPERACIONAL › Ocorrências | `operacional/ocorrencias/page.tsx:263` (import :32) |
| Relatório de Turnos | `/modulos/operacional/turnos` | `<ExportButton buttonText="Exportar">` | client-side; `filename="turnos"`, dados via `formatDataForExport(shifts,…)` | Excel + PDF + CSV | Redesign OPERACIONAL › Turnos | `operacional/turnos/page.tsx:270` (filename :281; import :22) |
| Relatório de Colaboradores | `/modulos/operacional/colaboradores` | `<ExportButton buttonText="Exportar">` | client-side; `filename="colaboradores"` | Excel + PDF + CSV | Redesign OPERACIONAL › Colaboradores | `operacional/colaboradores/page.tsx:293` (import :41) |
| Relatório de Escalas | `/modulos/operacional/escalas` | `<ExportButton buttonText="Exportar">` | client-side; `filename="escalas"` | Excel + PDF + CSV | Redesign OPERACIONAL › Escalas | `operacional/escalas/page.tsx:233` (import :20) |
| Relatório de Alocações | `/modulos/operacional/alocacoes` | `<ExportButton buttonText="Exportar">` | client-side; `filename="alocacoes"` | Excel + PDF + CSV | Redesign OPERACIONAL › Alocações | `operacional/alocacoes/page.tsx:314` (import :19) |
| Relatório de Rondas de Inspeção (lista) | `/modulos/operacional/rondas` | `<ExportButton buttonText="Exportar">` | client-side; `filename="rondas"` | Excel + PDF + CSV | Redesign OPERACIONAL › Rondas | `operacional/rondas/page.tsx:225` (import :30) |
| Relatório da Ronda (por ronda, PDF backend) | `/modulos/operacional/rondas` | Botão ícone "Baixar relatório da ronda (PDF)" → `abrirPdf(...)` | **GET** `/api/v1/operacional/rondas/{id}/relatorio/pdf?download=1` | PDF (backend) | Redesign OPERACIONAL › Rondas (ação por linha) | `operacional/rondas/page.tsx:513` (title :514; import :5) |
| Relatório de Postos de Trabalho | `/modulos/operacional/postos` | `<ExportButton>` | client-side; `filename="postos"`, dados via `formatDataForExport(posts,…)` | Excel + PDF + CSV | Redesign OPERACIONAL › Postos | `operacional/postos/page.tsx:293` (filename :306; import :20) |
| Relatório Operacional (cobertura/horas/custos) — CSV | `/modulos/operacional/relatorios` | Botão ícone `FileSpreadsheet` "Exportar Excel/CSV" → `exportToCSV()` | client-side; monta CSV → `URL.createObjectURL` → download `relatorio-operacional-{ini}-{fim}.csv` | CSV | Redesign OPERACIONAL › Relatórios | `operacional/relatorios/page.tsx:299` (fn :127; title :301) |
| Relatório Operacional (cobertura/horas/custos) — PDF | `/modulos/operacional/relatorios` | Botão ícone `FileText` "Exportar PDF" → `exportToPDF()` | client-side; `window.open('','_blank')` + injeta `#report-content` + `print()` | PDF (impressão HTML) | Redesign OPERACIONAL › Relatórios | `operacional/relatorios/page.tsx:307` (fn :175; `window.open` :179; `.print()` :207) |
| Contrato (PDF) | `/modulos/crm/contratos` | Item "Baixar PDF" → `abrirPdf(...)` | **GET** `/api/v1/crm/contracts/{id}/pdf?download=1` | PDF (backend) | Redesign CRM/COMERCIAL › Contratos (ação por linha) | `crm/contratos/page.tsx:492` (label :495; import :25) |
| Proposta/Orçamento (PDF) — dropdown | `/modulos/crm/propostas` | `DropdownMenuItem` "Gerar PDF" → `gerarPdf(p)` | **GET** `/api/v1/crm/proposals/{id}/pdf` (`responseType:'blob'`), lê header `X-Signature-Public-Token`; baixa `orcamento_{number}.pdf` + `window.open` | PDF (backend) | Redesign CRM/COMERCIAL › Propostas | `crm/propostas/page.tsx:525` (fn :263) |
| Proposta/Orçamento (PDF) — detalhe | `/modulos/crm/propostas` (drawer/detalhe) | `<Button>` "Gerar PDF" → `gerarPdf(selectedItem)` | **GET** `/api/v1/crm/proposals/{id}/pdf` (mesmo fluxo acima) | PDF (backend) | Redesign CRM/COMERCIAL › Propostas (detalhe) | `crm/propostas/page.tsx:562` (fn :263) |

## Afordâncias correlatas (não são download de documento, mas fluxo de proposta/assinatura — anexar ao redesign)

| Item | Tela | Ação | Endpoint | Arquivo:linha |
|---|---|---|---|---|
| Copiar link de assinatura do cliente (gera PDF antes se preciso) | `/modulos/crm/propostas` | `copiarLinkCliente(p)` → depende de `gerarPdf` p/ obter token | link público `{base}/api/v1/signatures/public/{token}` | `crm/propostas/page.tsx:249` |
| Links públicos de formulário/agendamento (growth) | `/modulos/crm/growth` | `<a target=_blank>` p/ `{PUBLIC_BASE}/form/{slug}` e `/agendar/{slug}` | rotas públicas (não PDF) | `crm/growth/page.tsx:240,272` |

## Telas SEM afordância de documento (varridas, nada a portar)

- OPERACIONAL: agentes, ai-command-center, avaliacao-equipe, banco-horas, campo, cobertura, colaboradores/[id], comunicados, consultor, diarias, diaristas (+escala/fechamento), disciplinar, escalas/[id]·grade·templates·visual, ferias, instrucoes-posto, kpi, mapa, medidas-administrativas, notificacoes, ocorrencia-rapida, passagem-turno, presenca, reembolsos, ronda-mobile, substituicoes, triagem. (Nenhum botão de PDF/Excel/impressão; só `refetch`/navegação.)
- CAMPO: checkin, comunicados, monitoramento, ordens-servico, page. (Nenhuma afordância de documento.)
- CRM: atividades, clientes(+/[id]), comissoes, consultor, contatos, contratos/[id], leads, oportunidades, precificacao (só `fetch` de dados, sem download), page.
- SERVICOS: agendamentos, contratos (usa `ContratoDetailModal`/`ContratoFormModal` — sem PDF), ordens, page.
- MARKETING: biblioteca, brand-voice, campanhas, copywriter, estrategista, funil, lead-magnet. (Nenhuma afordância de documento.)

## Observações

- **Nenhum STUB encontrado**: todos os 13 botões-documento têm handler real (onClick/ExportButton wired). Nenhum `TODO`/simulado/botão morto nas afordâncias de documento.
- Só **2 endpoints de PDF de backend** no escopo operacional/comercial: `/api/v1/operacional/rondas/{id}/relatorio/pdf` e os dois de CRM (`/crm/contracts/{id}/pdf`, `/crm/proposals/{id}/pdf`). Todo o resto é export client-side (ExportButton com Excel+PDF+CSV, ou CSV/print inline em `relatorios`).
- Arquivos ignorados (não são a tela viva): `*.bak`, `*.corrupted` (ex.: `operacional/turnos/page.tsx.bak`, `operacional/colaboradores/page.tsx.bak`, `operacional/postos/page.tsx.{bak,corrupted}`) — cada um repete um `<ExportButton>`, mas não estão em produção.
