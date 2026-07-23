# B2 — Afordâncias de Documento (abrir HTML / baixar PDF / exportar) — CLÁSSICO
## Áreas: FINANCEIRO · FISCAL · EMPRESAS (contábil/Domínio)

Minerado READ-ONLY de `/opt/conecta-pro/frontend/src/app/modulos/{financeiro,fiscal,empresas}`.
Helper central de PDF: `frontend/src/lib/pdf.ts` → `abrirPdf(url, {download, nome})` — faz `fetch` com Bearer (token vive em `localStorage.access_token`, o `<a href>` não carrega), abre/baixa o **blob**, mostra o `detail` real do erro. `?download=1` força download.

Legenda: 💰 = dinheiro (Inter/boleto/comprovante) · 🏛️ = documento de governo (guia/DAS/DARF/DANFSe/CND/SPED/Reinf) · **STUB** = simulado/desabilitado/sem handler/dado hardcoded.
Todas as rotas de tela são sob `/modulos/…`. Todos os endpoints são prefixo `/api/v1`.

---

### FINANCEIRO — documentos ATIVOS (com afordância real)

| Documento | Tela clássica (rota) | Botão | Endpoint (método+path) | Formato | Módulo+tela REDESIGN | Arquivo:linha |
|---|---|---|---|---|---|---|
| Aging Contas a Receber | financeiro/contas-receber | "Download aging" (`abrirPdf` download) | GET `/financial/receivables/aging/pdf?download=1` | PDF | financeiro › Contas a Receber | financeiro/contas-receber/page.tsx:166 |
| Aging Contas a Pagar | financeiro/contas-pagar | Download aging (`abrirPdf` download) | GET `/financial/payables/aging/pdf?download=1` | PDF | financeiro › Contas a Pagar | financeiro/contas-pagar/page.tsx:172 |
| DRE (anual) | financeiro/relatorios (tab `dre`) | "Exportar PDF" | GET `/financial/relatorios/dre/pdf?ano={ano}` | PDF | financeiro › Relatórios/DRE | financeiro/relatorios/page.tsx:407,413 |
| Balancete | financeiro/relatorios (tab `balancete`) | "Exportar PDF" | GET `/financial/relatorios/balancete/pdf?ano={ano}` | PDF | financeiro › Relatórios/Balancete | financeiro/relatorios/page.tsx:408,413 |
| Fluxo de Caixa (projeção) | financeiro/relatorios (tab `projecao`) | "Exportar PDF" | GET `/financial/relatorios/fluxo-caixa/pdf?ano={ano}` | PDF | financeiro › Relatórios/Fluxo | financeiro/relatorios/page.tsx:409,413 |
| NFS-e de Entrada — Ver | financeiro/nfse-entrada | "Ver PDF" (ícone) | GET `/financial/nfse-entrada/{chave_acesso}/pdf` | PDF 🏛️ | financeiro › NFS-e Entrada | financeiro/nfse-entrada/page.tsx:141 |
| NFS-e de Entrada — Baixar | financeiro/nfse-entrada | "Baixar PDF" (ícone) | GET `/financial/nfse-entrada/{chave_acesso}/pdf?download=1` | PDF 🏛️ | financeiro › NFS-e Entrada | financeiro/nfse-entrada/page.tsx:142 |
| Orçamentos (planilha) | financeiro/orcamentos | "Exportar" | client-side CSV blob (dados de `/orcamentos`) | CSV | financeiro › Orçamentos | financeiro/orcamentos/page.tsx:319-324,383 |
| Boleto emitido — PDF | financeiro/boletos | "Baixar PDF" (`<a href={resultado.pdf_url}>`) | POST `/integrations/banking/boleto/generate` → `pdf_url` | PDF 💰 | financeiro › Boletos | financeiro/boletos/page.tsx:380-384 |
| Boleto (lista histórico) — PDF | financeiro/boletos | `<a href={b.pdf_url}>` | GET `/integrations/banking/boleto/list` → `pdf_url` | PDF 💰 | financeiro › Boletos | financeiro/boletos/page.tsx:644-645 |
| Cobrança/Boleto emitido — PDF | financeiro/cobrancas | "Baixar PDF" (`<a href={resultado.pdf_url}>`) | POST `/integrations/banking/boleto/generate` → `pdf_url` (svc `bankingService.emitirBoleto`) | PDF 💰 | financeiro › Cobranças | financeiro/cobrancas/page.tsx:444-447 |
| Cobrança (lista) — Ver PDF | financeiro/cobrancas | "Ver PDF" (`<a href={b.pdf_url}>`) | lista de cobranças → `pdf_url` | PDF 💰 | financeiro › Cobranças | financeiro/cobrancas/page.tsx:849-850 |
| Comprovante de pagamento Inter | financeiro/inter/pagamentos | "Comprovante" (fetch→blob→`window.open`) | GET `/financeiro/inter/payments/{id}/comprovante` | PDF 💰 | financeiro › Inter/Pagamentos | financeiro/inter/pagamentos/page.tsx:1044-1052 |

---

### FISCAL — documentos ATIVOS

| Documento | Tela clássica (rota) | Botão | Endpoint (método+path) | Formato | Módulo+tela REDESIGN | Arquivo:linha |
|---|---|---|---|---|---|---|
| Guia do mês (INSS/FGTS/RFB…) — Ver | fiscal/guias | "Ver PDF da guia" (`abrirPdf(g.pdf_url)`) | `g.pdf_url` de GET `/financial/relatorios/guias-do-mes?competencia=` | PDF 🏛️ | fiscal › Guias/Parcelamentos | fiscal/guias/page.tsx:112 |
| Guia do mês — Baixar | fiscal/guias | "Baixar PDF da guia" | `g.pdf_url` + `?download=1` | PDF 🏛️ | fiscal › Guias/Parcelamentos | fiscal/guias/page.tsx:114 |
| Guia eCAC/Drive — Ver | fiscal/ecac | "Ver" (`abrirGuiaPdf(d.pdf_url,false)`) | `d.pdf_url` de `/fiscal/guias-drive` (via `/government/ecac/debitos`) | PDF 🏛️ | fiscal › eCAC | fiscal/ecac/page.tsx:26-37,205-207 |
| Guia eCAC/Drive — Baixar | fiscal/ecac | ícone download (`abrirGuiaPdf(d.pdf_url,true)`) | `d.pdf_url?download=1` | PDF 🏛️ | fiscal › eCAC | fiscal/ecac/page.tsx:207 |
| DANFSe (NFS-e emitida) | fiscal/nfse | "Baixar DANFSe (PDF)" (`abrirPdf` download) | GET `/financial/fiscal/nfse/{id}/danfse?download=1` | PDF 🏛️ | fiscal › NFS-e | fiscal/nfse/page.tsx:336-337 |
| CND / Certidão (por tipo) | fiscal/certidoes/emitir | "Baixar" (`abrirPdfCnd(dt)`) | GET `/gedeon/cnd/pdf/{documentType}` (blob) | PDF 🏛️ | fiscal › Certidões/Emitir | certidoes/emitir/page.tsx:70,154,204 · svc gedeon/cndService.ts:46 |
| Certidão — portal oficial (Federal/FGTS manual) | fiscal/certidoes | "Buscar" → `window.open(m.url)` | URL externa do portal gov (manual-assistido) | link ext. 🏛️ | fiscal › Certidões | fiscal/certidoes/page.tsx:281-286 |

---

### FISCAL — geração de arquivo/evento SEM afordância de download (STUB / a completar)

| Documento | Tela clássica (rota) | Botão | Endpoint (método+path) | Formato | Situação | Arquivo:linha |
|---|---|---|---|---|---|---|
| Guia DCTFWeb (FGTS mensal) | fiscal/dctfweb | "Gerar Guia" (`useGerarGuiaMensal`) | POST `/government/fgts-digital/guia-mensal` (responseType blob) | PDF 🏛️ | **STUB** — mutation retorna Blob mas o `onSuccess` só marca status `'enviada'`; **o PDF nunca é aberto/baixado** | dctfweb/page.tsx:131-153 · hook useFGTSSimples.ts:98 · svc fgts-simples.service.ts:114-127 |
| SPED Fiscal — arquivo | fiscal/sped | "Gerar Arquivo" | POST `/government/sped-fiscal/gerar` | TXT 🏛️ | **STUB** — gera, mas tabela só tem "Ver detalhes"/"Validar"; modal (sped-detail-modal.tsx) **não tem download** | sped/page.tsx:316,324 · svc sped.service.ts:126 |
| SPED Contábil (ECD) — arquivo | fiscal/sped | "Gerar Arquivo" | POST `/government/sped-contabil/gerar` | TXT 🏛️ | **STUB** — idem SPED Fiscal (sem download na UI) | sped/page.tsx:343,351 · svc sped.service.ts:213 |
| Validação SPED | fiscal/sped | "Validar" | POST `/government/sped/validar` | — 🏛️ | ação (não é doc) | sped/page.tsx:72 · svc sped.service.ts:310 |
| NFS-e (ABRASF) — XML | fiscal/nfse-multi | textarea readonly `resultado.xml_gerado`; botão "Emitir" **disabled** | (preview only) | XML 🏛️ | **STUB** — XML só é exibido (expandir/recolher), **sem baixar**; emissão desabilitada | nfse-multi/page.tsx:507-534,538+ |
| EFD-Reinf R-1000/2010/2099/4010/4020 | fiscal/reinf | "R-1000"…"R-4020" (`useGerarR*`) | hooks de geração de evento | — 🏛️ | gera eventos, **sem PDF/XML para download** na tela | reinf/page.tsx:11-15,86-90,300-315 |
| eSocial — eventos (S-2200/2230/2299…) | fiscal/esocial | "Reenviar" / "Validar" (`useEnviarEvento`/`useValidarEvento`) | envio/validação | — 🏛️ | transmite/valida, **sem download de recibo/PDF** na tela | esocial/page.tsx:55-56,309 |

---

### EMPRESAS — exportação contábil (Domínio/TOTVS) e demonstrativos

| Documento | Tela clássica (rota) | Botão | Endpoint (método+path) | Formato | Situação / REDESIGN | Arquivo:linha |
|---|---|---|---|---|---|---|
| Domínio — Plano de Contas | empresas/demonstrativos (tab "Exportar Domínio TOTVS") | "Exportar" → `downloadTxt` | GET `/empresas/dominio/plano-contas/{slug}` → `conteudo`/`nome_arquivo` | TXT | ATIVO (dado real) · empresas › Demonstrativos | demonstrativos/page.tsx:658,768,784 |
| Domínio — Lançamentos | empresas/demonstrativos | "Exportar" → `downloadTxt` | POST `/empresas/dominio/lancamentos` | TXT | **STUB** — payload de lançamentos é **hardcoded** (exemplo "Receita de Serviços — março") | demonstrativos/page.tsx:670-687,806,823 |
| Domínio — NFS-e | empresas/demonstrativos | "Exportar" → `downloadTxt` | POST `/empresas/dominio/nfse` | TXT | **STUB** — payload de notas é **hardcoded** ("Cliente Exemplo Ltda") | demonstrativos/page.tsx:695-712,845,861 |
| "Exportar Agora" (para contador) | empresas/dashboard | botão "Exportar Agora" | — | — | **STUB** — botão **sem `onClick`** (só visual) | empresas/dashboard/page.tsx:632-638 |
| `downloadTxt` helper (blob text/plain) | empresas/demonstrativos | — | client-side Blob→`a.download` | TXT | mecanismo comum das 3 exportações Domínio | demonstrativos/page.tsx:722-729 |

---

### Telas SEM afordância de documento (varridas, nada a portar)
`financeiro/`: banking (saldo/extrato/boleto/pix/darf — extrato só exibido, sem export), dashboard, conciliacao (importa OFX = **upload**, não gera doc), fluxo-caixa, custos, custeio (extrato Inter só exibido), pagamentos-diaristas, pagamentos-pj, agentes, clientes, compras, contabilidade, contratos, estoque, faturamento, fornecedores, precificacao, raio-x, orcamentos(exceto CSV acima), cfo (anexa PDF = upload p/ IA), fiscal(hub).
`fiscal/`: painel, consultor (anexa guia/nota = upload p/ IA), nfse-multi(exceto XML STUB), certidoes/* (subpáginas de status por órgão — o PDF sai em `certidoes/emitir`).
`empresas/`: liminares, obrigacoes, rentabilidade, migrador, page(hub).

---

### Notas de mapeamento REDESIGN
- Builders do redesign: `backend/modules/operacional/controllers/redesign_builders/{financeiro.py, fiscal.py, empresas.py}` (override aditivo por tela). O redesign vive na rota isolada `/redesign`.
- `financeiro.py` já declara menu-extra com telas do clássico (saldos, cora, pagamentos-pj, pagar-folha-pj, pagar-diaristas) — as afordâncias de PDF/comprovante acima ainda **não** foram portadas para lá.
- Reutilizar SEMPRE o helper `lib/pdf.ts abrirPdf` (Bearer + blob) no redesign; para guias/CND que já vêm com `pdf_url`/blob dedicado, replicar o padrão Ver+Baixar.
- Sensíveis 💰 (Inter/boleto/comprovante) e 🏛️ (guia/DANFSe/CND/SPED/Reinf/eSocial): portar apenas a **visibilidade/abertura** do documento; nenhuma dessas afordâncias movimenta dinheiro (o gate OTP de pagamento é separado, ex.: eCAC "Pagar" e inter/pagamentos).
