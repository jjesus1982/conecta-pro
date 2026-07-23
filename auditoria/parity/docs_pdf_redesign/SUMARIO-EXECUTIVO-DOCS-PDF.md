# Sumário Executivo — Botões de Documento (abrir HTML + baixar PDF) no REDESIGN

**Data:** 2026-07-22 · **Missão:** toda tela do redesign que gera/exibe documento, relatório, guia, extrato, comprovante, certidão, holerite, espelho, dossiê → botão **abrir (HTML)** + **baixar (PDF)**. Foco: **redesign** (esquecer o clássico agora).

Busca profunda feita por 7 agentes em paralelo varrendo os ~20 módulos backend que geram documento (132 arquivos) + inventário das 258 telas do redesign. Tabelas por-endpoint nos arquivos `1..7-*.md`; telas em `0-INVENTARIO-TELAS-REDESIGN.md`.

---

## 1. Números gerais

- **258 telas** no redesign (31 módulos).
- **~84 endpoints já SERVEM arquivo real hoje** (plug-and-play: só ligar o botão com `abrirPdf`).
- **~100+ endpoints geram doc-dado mas retornam só JSON** → precisam de rota `/pdf` gêmea OU render client-side (HTML) no redesign.
- **Formato dominante: PDF.** Também HTML, XLSX/CSV, XML (eSocial/NF-e), TXT (SPED/Domínio), ZIP (kit), PPTX (apresentação).

### Estado da fundação (bloqueia tudo)
- ✅ Helper `frontend/src/lib/pdf.ts abrirPdf(url,{download,nome})` existe (fetch com Bearer, abre/baixa blob, mostra erro real do servidor). **Nenhuma tela usa ainda.**
- ❌ `ModuleView.tsx` só tem o `cta` decorativo — **não há mecanismo de botões de documento** (nem por-tela nem por-linha). **Fundação a construir primeiro.**

---

## 2. Ready-to-wire — endpoints que JÁ servem arquivo (≈84)

| Cluster | Qtd | Destaques (rota → tela redesign) |
|---|---|---|
| people_management | **33** | holerite/contracheque, folha consolidada, recibo VT/VR, TRCT, aviso prévio, **espelho de ponto (Portaria 671)**, ficha EPI, PPP, NR-1, contrato, kit GED, anexo ASO, dossiê KYC · (22 PDF, 4 HTML, 2 XML eSocial, 1 TXT Domínio, 1 ZIP, 3 FileResponse) |
| hr/reembolso/operacional | **13** | relatório de visita, relatório de ronda, holerite, relatório RH (PDF/EXCEL/CSV/HTML), export folha (TXT/CSV/XLSX/XML/SEFIP), **AFD ponto (.txt Portaria 671)** |
| financeiro/fiscal | **8** (+5 emissão) | **DRE, Balancete, Fluxo de Caixa, Aging Receber, Aging Pagar** (5 PDF via `gerar_relatorio_pdf`), DANFSe emitida/recebida, guia fiscal PDF (Drive) |
| CRM/comercial/portal/licitações | **16** | proposta, contrato, recibo, OS, aditivo, atestado, relatório de visita, **apresentação (PPTX/PDF)**, orçamento, doc de kit + foto do portal, plano de contas Domínio (TXT) |
| governo/integrações | **8** | **comprovante Inter** (gate correto), guia-drive Portte, boletos (URL 3º), SPED fiscal/contábil (TXT), CT-e/MDF-e (XML) |
| GED/gedeon/assinaturas | **3 binário** | download de documento GED, **ZIP do kit**, PDF de CND — (+~62 rotas geram→JSON ou enviam via link Drive) |
| jurídico/equip/outros | **3** | parecer (PDF), DET comunicação (PDF), export LGPD (JSON) |

---

## 3. Backlog — geram dado mas só JSON (≈100+) → precisam de renderizador

Padrão a seguir: **criar rota `/pdf` gêmea reusando o gerador padrão-ouro** (`gerar_relatorio_pdf` no financeiro, `pdf_branding` no CRM), OU render HTML client-side no redesign.

- **Operacional (buraco maior):** cobertura, horas, custos, diárias/resumos, fechamento de diaristas, retenções, passagem de turno, instruções de posto, ocorrências, avaliação de equipe, presença, banco de horas, escala/grade, espelho, OS — **todos só JSON hoje**.
- **Financeiro/fiscal (~25):** DRE/Balancete/Fluxo/Balanço/Apuração Lucro Real/DAS/retenções/painéis/CFO IA/Consultor Fiscal.
- **Governo (~19):** DAS/PGDAS-D, GRFGTS/GRRF, DARFs DCTFWeb, situação/débitos/certidão/parcelamentos e-CAC, listas de sync.
- **CRM/empresas (13):** DRE/Balanço/DFC/Consolidado-grupo, exports Domínio (plano-contas/lançamentos/clientes/nfse), docs de edital, portal financeiro.
- **Jurídico (~18):** dossiês, ASO/ficha-EPI/PPRA-PGR, relatórios de serviço/SLA.
- **people_management (12):** PPP dados, prontuário, dossiê KYC índice, holerite/resumo/conferência da folha, termos de consentimento.

---

## 4. Armadilhas / correções ANTES de ligar botão (não ignorar)

1. 🔴 **`GET /campo/visitas/{id}/pdf` está SEM autenticação** (só `get_service`) — corrigir antes de expor.
2. ⚠️ **DANFE e XML de NFC-e são PLACEHOLDER** (conteúdo fake, TODO) — **não ligar botão**.
3. ⚠️ **SPED `/sped/gerar` é STUB** (TODO, só cria registro).
4. ⚠️ **`intelligent_reports_controller` NÃO está montado em `main_production`** — export simulado, não ligar.
5. ⚠️ **3 submódulos hr** (`employee_portal`, `rep_integration`, `analytics_dashboard`) não montados em produção — a rota viva de holerite é a de `people_management`. Confirmar path real antes de fiar.
6. ⚠️ **PDFs de proposta de LICITAÇÃO** são renderizados e salvos em `media/bidding/proposals/` mas **não há rota que sirva** — criar rota de download.
7. ⚠️ **eSocial S-2210/2220/2230/2240**: XML gerado + transmitido, mas **sem rota que devolva ao usuário** — criar rota de preview se quiser "ver XML enviado".
8. 📄 **Documento fiscal/gov JAMAIS diz "transmitido/autorizado" sem transmissão real** (eSocial/NFS-e/CT-e/MDF-e/DAS/DARFs) — respeitar sinalização honesta.
9. 💰 **Dinheiro-que-sai** (preparar-pagamento, faturar) = OTP humano, fora do inventário de leitura.
10. 🎯 **Padrão-ouro divergente:** `my_payslips_controller._generate_payslip_pdf:147` monta contracheque inline (reportlab) fora do serviço `pdf_branding` — consolidar.
11. 🔗 **Pares gerar→baixar (2 chamadas):** contrato, aviso prévio férias, cartão-ponto — o front encadeia.

---

## 5. Fundação a construir (1ª etapa, desbloqueia todos)

No `ModuleView.tsx` (+ contrato de dados do `redesign_data_controller`):
- **Botões por-TELA:** `scr.docs = [{label, url, pdf?:bool, gate?}]` → renderiza `<DocButtons>` que chama `abrirPdf(url)` (ver) e `abrirPdf(url,{download:true,nome})` (baixar).
- **Botões por-LINHA:** coluna de ação na `TableScreen` para docs por-item (holerite por colaborador, DANFSe por nota, comprovante por pagamento) — usa o `{id}` da linha.
- **Estados honestos:** placeholder/stub/sem-transmissão → botão desabilitado com tooltip ("aguardando…"), nunca 200 fake.
- Reusar `abrirPdf` (já mostra o erro real do servidor).

---

## 6. Proposta de divisão (3 terminais — Jordan valida)

| Terminal | Clusters | Ready-to-wire | Backlog renderizador |
|---|---|---|---|
| **Fundação (T1 primeiro)** | ModuleView doc-buttons + `<DocButtons>` + convenção backend | — | desbloqueia todos |
| **T1** | operacional · campo · saúde-ocup · jurídico · relatórios · documentos/GED | ~20 | operacional (grande) + jurídico |
| **T2** | people_management · departamento-pessoal · rh · portal-do-funcionário · homologação | ~40 | folha/eSocial/PPP + operacional-RH |
| **T4** | financeiro · fiscal · empresas · CRM · comercial · licitações · governo/integrações | ~30 | fin/fiscal/gov (~60) + licitação (criar rotas) |

> Regras herdadas: deploy blue-green serializado (lock), `git add` só do próprio módulo, dinheiro/gov gated, nunca fabricar, verificar pela rota da tela. Ver [[project_docs_pdf_sweep]] [[project_paridade_t4_financeiro_comercial]].
