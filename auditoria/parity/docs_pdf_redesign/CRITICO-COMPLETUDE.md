# CRÍTICO DE COMPLETUDE — o que ficou de fora do mapeamento docs+PDF do redesign

**Data:** 2026-07-22 · **Método:** varredura READ-ONLY, ancorada em arquivo:linha e comandos reais, cruzando o dossiê (`0-INVENTARIO`, `1-7-*`, `A-BANCO`, `D-STORAGE`, `SUMARIO`, `MATRIZ-MESTRE`, `classic/B1-B5`) contra o código vivo em `/opt/conecta-pro`.

> **Nota de contexto importante:** o dossiê evoluiu durante a auditoria. Existe um `MATRIZ-MESTRE-REDESIGN.md` (criado 23:45, **posterior** aos B1-B5 de 23:42) que consolida tudo numa visão redesign-cêntrica e **fecha boa parte dos buracos dos B-files**. Este crítico separa o que é buraco REAL (não está em lugar nenhum) do que era buraco só na lente clássica (B) mas já coberto pela MATRIZ.

---

## 1. Backend não coberto

Rodei por-módulo:
```
cd backend/modules && grep -rlnE "FileResponse|StreamingResponse|reportlab|weasyprint|openpyxl|csv.writer|xlsxwriter|BytesIO|media_type=|render_to_string"
```
21 módulos têm gerador/stream. **20 estão cobertos** pelos arquivos 1-7 do dossiê (people_management, financial, crm, hr, gedeon, juridico, government_integrations, ged, bidding, integrations, client_portal, signatures, reimbursement, operacional, mobile, gdrive, fiscal_contabil, campo + reports/intelligent).

**ÓRFÃO REAL — não está no dossiê:**
- 🔴 **`ai/report_generator/`** — motor de relatório COMPLETO e separado do `reports/intelligent_reports` (esse último o SUMARIO já cita como "não montado").
  - `ai/report_generator/services/report_exporter.py` gera **PDF / XLSX / CSV / JSON / HTML** reais (`_export_pdf:72`, `_export_excel:102` grava `.xlsx` real, `_export_csv:176`, `_export_html:235`).
  - `ai/report_generator/controllers/report_controller.py:192 POST /{report_id}/export` + CRUD de templates/schedules.
  - **NÃO montado** em `main_production.py` (grep `report_generator` = 0 hits) e **zero menção no dossiê inteiro** (grep `report_exporter`/`report_generator` no dossiê = 0). Precisa de decisão: morto (remover) ou reviver (e então inventariar). Hoje é ponto cego total.

**Falsos-positivos verificados (NÃO são geradores — corretamente fora):**
- `ai/conversation/controllers/chat_controller.py:410` → `StreamingResponse media_type="text/event-stream"` = SSE de chat, não documento.
- `documents/services/document_scanner.py` → OCR/ingestão (`scan_file`, `_save_file`, `_validate_file`); só **recebe** arquivo. Tabela `documents` = 0 linhas. Sem rota de download.

---

## 2. Frontend clássico não coberto

```
grep -rlnE "abrirPdf|baixarArquivoAutenticado|ExportButton|exportTo(Excel|PDF|CSV)|.blob()|createObjectURL|window.open|<a download|/pdf|/download|/export" src/app/modulos
→ 58 arquivos, 57 route-dirs com afordância-documento
```
Os **B1-B5 mapearam explicitamente ~13 arquivos .tsx**. Ou seja, a lente clássica sozinha deixou ~44 dirs sem citação nominal. **PORÉM** o `MATRIZ-MESTRE` cobre os principais no nível redesign (financeiro/fiscal etc.).

**Buraco só na lente B (mas COBERTO pela MATRIZ) — data-quality, não bloqueante:**
- financeiro/contas-pagar, contas-receber, inter/pagamentos, nfse-entrada, orcamentos, relatorios; fiscal/certidoes, ecac, guias, nfse. Todos com `abrirPdf`/`/pdf`/`.blob()` reais (verificado), **zero hit nos B-files** por keyword — mas presentes na MATRIZ.

**Residual — em NENHUM dos dois com detalhe (gap real, menor):**
- `meu-espaco` — tem `/download` (l.1725) + `window.open` (l.778,1374,1732): autoatendimento do colaborador. MATRIZ só cita "meu-espaco (3)" no catch-all, sem linhas de documento.
- `gestao-pessoas/dp/components` — componente compartilhado usando `baixarArquivoAutenticado` (helper distinto do `abrirPdf`) em 4+ pontos.
- `gestao-pessoas/saude-ocupacional/epi/rollout-assinaturas.tsx` — `window.open` (l.159), rollout de assinatura de EPI.
- `operacional/ronda-mobile` — afordância fraca, provavelmente redundante com rondas.
- Ruído a ignorar: `*.tsx.bak`, `*.corrupted`.

**Helper esquecido na fundação:** a MATRIZ §Fundação cita `abrirPdf` + `exportTo*`, mas existe um **segundo helper `frontend/src/utils/baixarArquivoAutenticado.ts`** (usado em 6 telas clássicas) que precisa ser portado/considerado junto.

---

## 3. Formatos além de PDF/HTML

Dossiê declara: PDF, HTML, XLSX, CSV, XML, TXT, ZIP, PPTX. Verificação:
- **DOCX** — SEM geração. Os hits (`financial/cfo_controller.py:148`, `juridico/consultor_controller.py:88`, `human_resources/resume_parser_service.py`) só **leem** .docx anexado (`from docx import Document` para extrair texto). Nenhum gera .docx. Sem gap.
- **ICS / calendar / iCalendar** — grep `.ics|text/calendar|VCALENDAR|BEGIN:VEVENT` = **0**. Não há geração de calendário. Sem gap.
- **XLSX/CSV client-side** — `src/components/ui/export-button.tsx` (`ExportFormat = excel|pdf|csv`, usa `@/utils/export`) usado em ~11 telas. **Coberto** (citado em B3, B5 e na MATRIZ §Fundação como `<ExportMenu>`).
- ZIP/PPTX/XML/TXT — cobertos.

**Conclusão #3: nada faltando em formatos.** (DOCX e ICS confirmados inexistentes como saída.)

---

## 4. Documentos "puxados/inseridos" (A-BANCO) sem rota de download

Cruzei tabelas populadas (>0 linhas) de `A-BANCO` com endpoints reais:

| Tabela | Linhas | Coluna-doc | Situação | Veredito |
|---|---:|---|---|---|
| **sig_signature_requests** | 1160 | signed_document_path | `signatures/` e `ai/signature/` têm **0** rotas de download (grep FileResponse/download = vazio). Dossiê (`4-*.md:135`) assume que o binário assinado sai via GED `/ged/documents/{id}/download`. **Assunção NÃO verificada** para as 1160 linhas. | 🔴 **GAP** — validar se todo `signed_document_path` está espelhado no GED; se não, não há caminho de download. |
| **onvio_documents** | 803 | nome_arquivo, doc_scope | `gedeon/controllers/onvio_controller.py` só tem `GET /stats /status /historico /documentos` (lista) — **nenhuma rota de download/abrir**. Sem menção de botão no dossiê. | 🟡 **GAP** — pode ser referência externa Onvio (Portte); confirmar se há binário a servir ou é só link. |
| nfse_tomadas_nacional | 293 | xml_raw | XML bruto armazenado, sem rota de preview/download mapeada. | 🟡 menor — "ver XML da nota tomada". |
| nfe_entradas | 52 | xml_raw | `fiscal_contabil/.../nfe/entrada_controller.py` é **upload**-XML; sem download do xml_raw guardado. | 🟡 menor — preview do XML da NF-e recebida. |
| crm_documents | 37 | arquivo | **Coberto** via `crm/growth` token (`/crm/growth/docs/download/{id}?t=`). | ✅ |
| reimbursement_requests/attachments | 22 | attachments | **Coberto** — `2-*.md:30` mapeia `GET /reimbursements/attachments/{id}/download` (`reimbursement_controller.py:519`). | ✅ |

Demais tabelas com "coluna-documento" são majoritariamente `*_reason` (motivo textual), `hourly_rate`, `foto_url`, `boleto_*` (URL de 3º) ou tabelas de 0 linhas — não são documento-para-baixar.

---

## 5. Redesign — mecanismo (confirmação)

- ✅ **CONFIRMADO: `ModuleView.tsx` (420 linhas) NÃO tem suporte a botão de documento.** grep `abrirPdf|DocButton|docs|pdf|download|blob` = 0. Suporta só `scr.type` ∈ {kpis, panels, table(cols/rows), cards, list, form}. O `FormScreen` tem `scr.submit.gated` (aviso money/gov) mas nenhum campo de documento. Bate com MATRIZ §Fundação ("mecanismo a construir").
- ✅ **CONFIRMADO: nenhum builder em `redesign_builders/*.py` emite campo de documento/pdf/download.** Os únicos hits são **colunas de dado**, não botões: `gestao_de_pessoas.py:150 ponto-espelho` (espelho = tabela de ponto), `departamento_pessoal.py:504 esocial_eventos_espelho`, `marketing.py:87 downloads` (contador de downloads de asset). Nenhum monta `scr.docs`/`row.docs`.
- Fundação (DocButtons + ExportMenu + contrato `scr.docs`/`row.docs` no `redesign_data_controller`) está **100% por construir** — a MATRIZ já descreve isso corretamente.

---

## 6. Endpoints órfãos famosos — TODOS presentes no dossiê

Checado no `SUMARIO §4` e `MATRIZ §checklist de segurança`:
1. ✅ `/campo/visitas/{id}/pdf` **sem auth** — SUMARIO item 1 + MATRIZ item 1.
2. ✅ DANFE / XML NFC-e **placeholder** — SUMARIO item 2 + MATRIZ item 2.
3. ✅ SPED `/sped/gerar` **stub** — SUMARIO item 3 + MATRIZ item 3.
4. ✅ PDFs de licitação em `media/bidding/proposals/` **sem rota** — SUMARIO item 6 + MATRIZ item 6.
5. ✅ eSocial **S-2210/2220/2230/2240** XML sem rota de preview — SUMARIO item 7 + MATRIZ item 8.
6. ✅ (extras já capturados) DCTFWeb/EFD-Reinf gera-mas-não-baixa, comodato contract-pdf simulado, empresas export Domínio hardcoded, "Exportar Agora"/"Gerar PDF" sem onClick.

**Nada faltando na verificação #6.**

---

## LACUNAS A FECHAR ANTES DE DECLARAR COMPLETO (priorizado)

1. **🔴 `ai/report_generator` — inventariar ou enterrar.** Motor de export PDF/XLSX/CSV/HTML real, não montado, **ausente do dossiê**. Decidir morto×revivo; se revivo, não tem rota de download servindo bytes (retorna metadata). Ponto cego total hoje.
2. **🔴 Cadeia do documento ASSINADO (1160 `sig_signature_requests.signed_document_path`).** O dossiê aposta que o PDF assinado sai via GED, mas isso não foi provado para as 1160 linhas. Provar o link sig↔GED; se houver assinado sem espelho no GED, não existe botão de download possível.
3. **🟡 `onvio_documents` (803 linhas) sem rota de abrir/baixar.** `onvio_controller` só lista. Confirmar se é binário servível ou link externo Portte; se servível, criar rota + botão.
4. **🟡 Telas residuais sem detalhe de documento:** `meu-espaco` (autoatendimento, tem /download+window.open), `gestao-pessoas/dp/components` (usa `baixarArquivoAutenticado`), `epi/rollout-assinaturas`. Detalhar afordâncias na matriz.
5. **🟡 XML bruto de notas recebidas** (`nfe_entradas` 52, `nfse_tomadas_nacional` 293) — sem preview/download do `xml_raw` guardado. Decidir se entra como "ver XML".

**Data-quality (não bloqueia, mas registrar):** a lente clássica B1-B5 mapeou nominalmente só ~13 de 57 route-dirs com afordância; a completude prática depende do `MATRIZ-MESTRE`. E a fundação precisa portar **dois** helpers (`abrirPdf` **e** `baixarArquivoAutenticado`), não só um.
