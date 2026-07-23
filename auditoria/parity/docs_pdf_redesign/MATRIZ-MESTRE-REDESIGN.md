# MATRIZ MESTRE — Botões de Documento no REDESIGN (redesign-cêntrica)

**Missão:** toda tela do redesign que gera/puxa/insere documento → botão **abrir (HTML)** + **baixar (PDF/formato nativo)**. Foco 100% redesign; clássico = só a especificação de referência.

**Fontes cruzadas:** 258 telas redesign (0-INVENTARIO) · 137 afordâncias no clássico (classic/B1-B5) · 50 endpoints-stream + geradores backend (1-7) · 285 tabelas c/ coluna-documento (A-BANCO) · 917 arquivos físicos em uploads/ (D-STORAGE).

## Números
- **137 afordâncias** de documento identificadas (spec viva do clássico).
- **84 com rota backend real** (ready-to-wire) · **31 rotas backend únicas** · **11 STUBs** (não ligar até corrigir).
- **~53 documentos-dado** que hoje só retornam JSON → precisam de rota `/pdf` gêmea ou render HTML.
- Formatos: **PDF** (dominante), HTML, XLSX, CSV, XML (eSocial/NF-e), TXT (SPED/Domínio), ZIP (kit), PPTX.

---

## FUNDAÇÃO (etapa 0 — desbloqueia tudo, sem ela nenhum botão existe)

O redesign NÃO tem mecanismo de botão-documento hoje. O `ModuleView.tsx` só tem `cta` decorativo. Construir:

1. **`<DocButtons>`** (componente): recebe `{label, url, formato, gate}` → renderiza "Abrir" (`abrirPdf(url)`) + "Baixar" (`abrirPdf(url,{download:true,nome})`). Reusa `src/lib/pdf.ts abrirPdf` (já existe, Bearer+blob+erro-real).
2. **`<ExportMenu>`** (dropdown Excel/PDF/CSV): equivalente ao `<ExportButton>` do clássico (7 telas operacionais usam). Geração client-side via util `exportToExcel/PDF/CSV` (xlsx + jspdf-autotable) — portar `utils/export.ts` do clássico.
3. **Contrato de dados**: `redesign_data_controller` passa por tela `scr.docs=[{label,url,formato,gate,disabled?,motivo?}]` (nível tela) e por linha `row.docs=[...]` (nível item, ex. holerite por colaborador). O `ModuleView` (dash/table/cards/list) renderiza.
4. **Estados honestos**: STUB/placeholder/sem-transmissão → botão desabilitado + tooltip ("aguardando emissão real"), nunca 200 fake.

---

## MATRIZ POR MÓDULO REDESIGN

Legenda status: ✅ rota real (ready) · 🔨 só-JSON (criar rota/render) · ⛔ STUB/placeholder (corrigir antes) · 🔗 link externo · 💰 dinheiro · 🏛️ gov · ⚖️ legal · 🔒 gate perfil

### departamento-pessoal (17 telas) — cluster mais denso
| Tela | Documento | Rota | Fmt | Status |
|---|---|---|---|---|
| folha-de-pagamento / folha | Holerite/contracheque por colaborador | `/people-management/.../payslip-pdf` (por employee) | PDF | ✅ 💰🔒 por-linha |
| folha | Folha consolidada (mês) | `/people-management/folha/{mes}/{ano}/pdf` | PDF | ✅ 💰🔒 por-tela |
| folha | Export Domínio (contabilidade) | `/people-management/.../dominio` | TXT | ✅ 💰🔒 |
| rescisao | TRCT | `/people-management/.../trct/pdf` | PDF | ✅ ⚖️ por-linha |
| aviso-previo | Aviso prévio | `/people-management/.../aviso-previo/pdf` | PDF+HTML | ✅ ⚖️ (par gerar→baixar) |
| ponto / fechamento-ponto | Espelho de ponto (Portaria 671) | `/people-management/hr/ponto/espelho/{emp}/{mes}/{ano}/pdf` | PDF | ✅ ⚖️ por-linha |
| ponto | AFD (arquivo fiscal 671) | `/rep/afd/export/{device}/download` | TXT | ✅ ⚖️ |
| contratos | Contrato CLT | `/people-management/.../contrato` | PDF+HTML | ✅ ⚖️ (par) |
| eSocial | Evento S-2200/S-2299 XML | `/people-management/esocial/.../{id}/xml` | XML | ✅ 🏛️ |
| documentos | Documento do funcionário (upload) | `/people-management/hr/documents/{id}/download` | blob | ✅ por-linha |
| ferias | Aviso/recibo de férias | `/people-management/.../ferias/pdf` | PDF+HTML | ✅ ⚖️ |
| admissao | Ficha admissão | `/people-management/.../admissao/pdf` | PDF | ✅ |

### gestao-de-pessoas (15) — GED + ponto + saúde
| Tela | Documento | Rota | Fmt | Status |
|---|---|---|---|---|
| GED — Documentos | Download de documento | `/ged/documents/{id}/download` | blob | ✅ por-linha |
| GED — Documentos | Ver inline (HTML) | `/ged/documents/{id}/view-url` | HTML | ✅ por-linha |
| GED — Kits | ZIP do kit | `/ged/kits/{id}/download-zip` | ZIP | ✅ por-linha |
| GED — relatórios | Relatório GED (4 tipos) | `/modulos/gestao-pessoas/ged/relatorio` | PDF/XLSX | ✅ |
| Certidões | CND por tipo | `/gedeon/cnd/pdf/{type}` · `/ged/coleta-automatica/cnd` | PDF | ✅ 🏛️ |
| Espelho (ponto) | Espelho | (mesma rota 671) | PDF | ✅ ⚖️ |
| Saúde — Exames | Anexo ASO | `/people-management/sst/aso/...` | PDF | ✅ 🏛️ por-linha |
| SST | Ficha EPI | `/sst/epi/fichas/{id}/pdf` | PDF | ✅ 🏛️ |
| SST | NR-1 compliance | `/sst/nr1/compliance/pdf` | PDF | ✅ 🏛️ |
| SST | PPP | `/people-management/sst/ppp/...` | PDF | ✅ 🏛️ por-linha |
| RH — relatórios | Relatório RH (headcount) | `/modulos/gestao-pessoas/rh/relatorio` | PDF/CSV | ✅ |

### financeiro (28)
| Tela | Documento | Rota | Fmt | Status |
|---|---|---|---|---|
| relatorios | DRE, Balancete, Fluxo de Caixa | `/financial/relatorio?tipo=...` | PDF | ✅ 🔒 por-tela |
| contas-a-receber | Aging Receber | `/financial/receivables/aging/pdf` | PDF | ✅ 🔒 |
| contas-a-pagar | Aging Pagar | `/financial/payables/aging/pdf` | PDF | ✅ 🔒 |
| nfs-e-entrada | DANFSe recebida | `/financial/nfse-entrada/{chave}/pdf` | PDF | ✅ 🏛️ por-linha |
| boletos | Boleto emitido | `/financial/.../boleto` (Inter URL) | PDF | ✅ 💰 por-linha |
| cobrancas | Cobrança/boleto | idem | PDF | ✅ 💰 por-linha |
| inter / pagamentos | Comprovante Inter | `/financeiro/inter/payments/{id}/comprovante` | PDF | ✅ 💰 por-linha (gate: só pago) |
| orcamentos | Orçamento | client-side | CSV | ✅ |
| fiscal (aba) | DANFSe emitida | `/financial/fiscal/nfse/{id}/danfse` | PDF | ✅ 🏛️ por-linha |
| dashboard/dre/balanco/dfc | DRE/Balanço/DFC | só-JSON | — | 🔨 criar `/pdf` |
| contabilidade / custos / custeio | demonstrativos | só-JSON | — | 🔨 |

### fiscal (11)
| Tela | Documento | Rota | Fmt | Status |
|---|---|---|---|---|
| guias | Guia fiscal (Drive) | `/fiscal/guias-drive/pdf/{id}` | PDF | ✅ 🏛️ por-linha |
| e-CAC | Guia eCAC | `/fiscal/ecac/.../pdf` | PDF | ✅ 🏛️ |
| nfs-e | DANFSe | (mesma do financeiro) | PDF | ✅ 🏛️ |
| certidoes | CND | `/gedeon/cnd/pdf` | PDF | ✅ 🏛️ |
| DCTFWeb | Guia DCTFWeb | gera Blob mas NÃO baixa | — | ⛔ STUB |
| SPED (fiscal/contábil) | Arquivo SPED | gera, sem download UI | TXT | ⛔ STUB |
| EFD-Reinf | Evento Reinf | sem PDF/XML na tela | — | ⛔ |
| eSocial (fiscal) | Evento | sem PDF/XML na tela | — | ⛔ |
| nfs-e-multi | XML NFS-e | só preview textarea | XML | ⛔ |

### operacional (37)
| Tela | Documento | Rota | Fmt | Status |
|---|---|---|---|---|
| rondas | Relatório de ronda (por ronda) | `/operacional/rondas/{id}/relatorio/pdf` | PDF | ✅ por-linha |
| ocorrencias, turnos, colaboradores, escalas, alocacoes, rondas, postos | Export da lista | client-side `<ExportMenu>` | XLSX/PDF/CSV | ✅ (7 telas) |
| relatorios | Relatórios operacionais | client-side (CSV/print) | CSV/PDF | ✅ |
| campo (aba) / rondas | Relatório de visita | `/campo/visitas/{id}/pdf` | PDF | ⛔ **SEM AUTH — corrigir** |
| cobertura, horas, custos, diárias, fechamento, passagem-turno, instruções, presença, banco-horas, grade, OS, avaliação | relatórios | só-JSON hoje | — | 🔨 criar rota/render (buraco grande) |

### crm (12) / comercial
| Tela | Documento | Rota | Fmt | Status |
|---|---|---|---|---|
| propostas | Proposta comercial | `/crm/proposals/{id}/pdf` | PDF | ✅ por-linha |
| contratos | Contrato | `/crm/contracts/{id}/pdf` | PDF | ✅ por-linha |
| growth | Doc registrado (token) | `/crm/growth/docs/download/{id}?t=` | PDF | ✅ |
| (crm docs) | Apresentação | `/crm/.../apresentacao` | PPTX/PDF | ✅ |
| propostas/OS/recibo/aditivo/atestado | vários | `/crm/.../pdf` | PDF | ✅ por-linha |

### licitacoes (10)
| Tela | Documento | Rota | Fmt | Status |
|---|---|---|---|---|
| editais | Edital (link externo) | `tenderData.link` | 🔗 | ✅ 🔗 |
| certidoes | Certidão licitação | `bidding_certificates.arquivo_url` | PDF | ✅ por-linha |
| propostas | Carta-proposta/planilha/declarações | media/bidding/proposals/ (disco) | PDF | ⛔ **SEM ROTA — criar download** |
| propostas | "Gerar PDF" | botão sem onClick | — | ⛔ STUB |

### empresas (7)
| Tela | Documento | Rota | Fmt | Status |
|---|---|---|---|---|
| migrador | Plano de contas Domínio | `/empresas/dominio/plano-contas` | TXT | ✅ |
| demonstrativos | DRE/Balanço/DFC/Consolidado | só-JSON (render tela) | — | 🔨 criar export |
| demonstrativos | Exports Domínio (lançamentos/clientes/nfse) | payload HARDCODED | TXT | ⛔ corrigir (dados exemplo) |
| dashboard | "Exportar Agora" | botão sem onClick | — | ⛔ STUB |

### juridico (10)
| Tela | Documento | Rota | Fmt | Status |
|---|---|---|---|---|
| pareceres | Parecer | `/juridico/pareceres/{id}/pdf` | PDF | ✅ por-linha |
| det | Comunicação DET | `/juridico/det/comunicacoes/{id}/pdf` | PDF | ✅ por-linha |
| processos, análise, dossiês, riscos | dossiê/relatório | só-JSON | — | 🔨 |

### equipamentos (4)
| Tela | Documento | Rota | Fmt | Status |
|---|---|---|---|---|
| comodatos | Contrato de comodato | `/comodatos/{id}/contract-pdf` | PDF | ⛔ STUB (URL simulada, sem bytes) |
| comodatos | Termo de entrega/devolução | `/comodatos/{id}/delivery-term` etc | PDF | ⛔ STUB |

### portal-do-funcionario (9)
| Tela | Documento | Rota | Fmt | Status |
|---|---|---|---|---|
| contracheque | Holerite | `/people-management/portal/payslips/{id}/download` | PDF | ✅ 💰 por-linha |
| meus-documentos | Documento do funcionário | `/people-management/portal/documents/{id}` | blob | ✅ por-linha |
| meu-ponto | Espelho | (671) | PDF | ✅ ⚖️ |

### documentos (4) / relatorios (5) / bi (1) / area-do-cliente (6) / rh (14) / saude-ocupacional (9) / recrutamento (5) / meu-espaco (3) / governo (via integrações)
| Tela | Documento | Rota | Fmt | Status |
|---|---|---|---|---|
| documentos/arquivos | Download GED | `/ged/documents/{id}/download` | blob | ✅ |
| relatorios/central | 6 relatórios PDF | `/modulos/.../relatorio` | PDF | ✅ |
| bi/dashboard | Dashboard | client-side | PDF/XLSX | ✅ |
| rh | headcount, certificados, avaliações | parte só-JSON | PDF/CSV | 🔨/✅ misto |
| saude-ocupacional | ASO/EPI/NR-1/PPP | sst.ts | PDF | ✅ 🏛️ |
| governo (integrações) | Comprovante Inter, guia Portte, SPED, CT-e/MDF-e | vários | PDF/TXT/XML | ✅ misto |
| governo | DAS/PGDAS/GRFGTS/DARF/e-CAC/certidão | só-JSON | — | 🔨 (~19) |

---

## ⛔ CORRIGIR ANTES DE LIGAR BOTÃO (checklist de segurança)
1. 🔴 `/campo/visitas/{id}/pdf` **SEM autenticação** — adicionar `CurrentActiveUser`.
2. ⛔ DANFE e XML NFC-e = **placeholder fake** (não ligar).
3. ⛔ SPED `/sped/gerar` = stub.
4. ⛔ DCTFWeb/EFD-Reinf/eSocial (aba fiscal) — geram mas sem download na tela.
5. ⛔ Comodato contract-pdf/delivery/return = URL simulada sem bytes.
6. ⛔ Licitação propostas — PDFs em `media/bidding/proposals/` **sem rota** (criar).
7. ⛔ Empresas exports Domínio (lançamentos/nfse) = payload hardcoded; "Exportar Agora" e "Gerar PDF" licitação = botões sem onClick.
8. ⚠️ eSocial S-2210/2220/2230/2240 XML gerado+transmitido mas **sem rota de preview** (criar se quiser "ver XML enviado").
9. 🎯 Consolidar geradores de PDF divergentes (`my_payslips_controller._generate_payslip_pdf` inline vs `pdf_branding`).
10. 📄 Nunca afirmar "transmitido/autorizado" sem transmissão real (eSocial/NFS-e/CT-e/DAS).

---

## LACUNAS achadas pelo crítico de completude (provadas na fonte, fechadas aqui)

Estas NÃO apareceram nas lentes A-D e teriam sido surpresa depois. Verificadas no banco/código:

| # | Lacuna | Prova | Ação |
|---|---|---|---|
| L1 | **`ai/report_generator/`** — motor de export PDF/XLSX/CSV/HTML completo e funcional (`report_exporter.py`, `report_controller.py:192 POST /export`) **NÃO montado em produção** (0 refs em main_production) | pasta existe, sem include | Decidir: reviver (montar + usar como render genérico do redesign) ou marcar morto. **Candidato a virar o motor de export client-agnóstico.** |
| L2 | **Documento assinado sem rota** — `sig_signature_requests.signed_document_path` aponta p/ `/app/uploads/signed/*.pdf`, mas `signatures/` tem **0 rotas de download** | 1160 linhas na tabela, **2** com path real (ICP) | Criar `GET /signatures/{id}/signed/download` (FileResponse). Telas: documentos/assinaturas, crm/contratos, dp/contratos. ⚖️ |
| L3 | **`onvio_documents` (803 linhas) sem abrir/baixar** — `onvio_controller` só LISTA (`nome_arquivo`), sem FileResponse | 803 docs Portte/Onvio (guias FGTS/INSS/DAS) | Confirmar se binário está em `uploads/onvio/` (373 arqs) e criar rota de download. Tela: fiscal/guias, dp/folha. 🏛️ |
| L4 | **XML bruto de notas sem preview/download** — `xml_raw` guardado, **zero endpoint** | **1.175 notas**: nfse_manaus 831 + nfse_tomadas 293 + nfe_entradas 51 | Criar `GET /.../{id}/xml` (devolve xml_raw). Botão "Baixar XML" nas telas fiscal/nfs-e, nfs-e-entrada. 🏛️ |
| L5 | **Telas residuais** — `meu-espaco` (autoatendimento `/download`+window.open), `gestao-pessoas/dp/components` (BotaoGerarContrato/AvisoPrevio via `baixarArquivoAutenticado`), `epi/rollout-assinaturas` (CSV) | grep clássico | Incluir na fundação/território (já cobertas parcialmente). |

**Correção na FUNDAÇÃO (o crítico pegou):** portar **DOIS** helpers, não um — `abrirPdf` (canônico) **E** `baixarArquivoAutenticado` (fallback Content-Disposition). Consolidar num único `<DocButtons>` que cobre ambos os comportamentos.

**Confirmados SEM gap** pelo crítico: ModuleView não tem suporte a doc (correto, fundação a fazer); nenhum builder redesign emite pdf hoje; os 6 órfãos famosos (visitas sem auth, licitação disco, DANFE/NFC-e placeholder, SPED stub, S-22xx sem preview) todos já na matriz; DOCX só input; ICS inexistente; reimbursement/crm_documents já têm rota.

### 2ª passada do crítico (convergência) — +5 lacunas, todas provadas na fonte:

| # | Lacuna | Prova | Ação |
|---|---|---|---|
| L6 | **Recibo VT/VR PDF** — gerador padrão-ouro real, rota live, ausente da matriz | `GET /people-management/folha/recibo-vt-vr/{emp}/{mes}/{ano}/pdf` (`folha_controller.py:193` + `recibo_vt_vr_pdf.py:35`) | ✅ ready. Telas: dp/folha, operacional/diaristas-fechamento. 💰 por-linha |
| L7 | **Candidato: documentos + dossiê KYC** — download pronto; KYC só-JSON | `/human-resources/candidatos/{id}/documento/{doc_id}` (✅ blob) · dossiê Infosimples 🔨 render PDF | Telas recrutamento/candidatos, rh/candidatos (faltavam na matriz). |
| L8 | **CRM relatório comercial + relatório de visita PDF** — rotas reais só parcialmente cobertas | `/crm/growth/reports/comercial/pdf`, `/crm/.../relatorio-comercial`, `/crm/.../visitas/pdf` | ✅ ready. Telas crm/dashboard, crm/atividades. |
| L9 | **Conciliação bancária export** — ⚠️ **armadilha**: CSV vem embrulhado em JSON `{content,filename}`, NÃO serve o `abrirPdf` padrão | `/financial/bank-reconciliations/{id}/export` (`bank_reconciliation_controller.py:576/619`) | Precisa handler blob próprio no `<DocButtons>` (decodificar `content`→Blob). Tela financeiro/conciliacao. CSV |
| L10 | **HR scheduled reports** — stub "Download não implementado", router `analytics_dashboard` não montado em produção | classe L1 | Decidir reviver/matar junto com L1. |

**Impacto na FUNDAÇÃO (L9):** o `<DocButtons>` precisa suportar **3 modos** de fonte: (a) blob direto via `abrirPdf` (maioria), (b) fallback `baixarArquivoAutenticado` (Content-Disposition), (c) **payload JSON `{content,filename}`** → decodificar client-side p/ Blob (conciliação e possivelmente outros exports Domínio).

**CONVERGÊNCIA:** 2 passadas do crítico → 10 lacunas achadas e fechadas (L1-L10). A 2ª confirmou SEM gap novo em: notificações/anexos (só deep-link), checklists/justificativa-ponto/OS (não geram PDF), DOCX (só input), ICS (inexistente), fotos de ronda (mídia, não documento), e as 8 rotas ✅ amostradas todas existem e montadas (zero fantasmas). Telas legitimamente sem documento: agendador, automacoes, analytics, assistente, marketing, seguranca, suprimentos, servicos, integracoes, configuracoes, homologacao.

---

## Divisão proposta (3 terminais + fundação) — a validar com Jordan
- **Etapa 0 (fundação, T1 primeiro):** `<DocButtons>` + `<ExportMenu>` + `exportTo*` client-side + contrato `scr.docs`/`row.docs` no ModuleView e redesign_data_controller.
- **T1:** operacional (37, buraco grande) · campo · saúde-ocup · jurídico · relatorios · documentos/GED · bi.
- **T2:** departamento-pessoal (17) · gestao-de-pessoas (15) · portal-do-funcionario · rh · recrutamento · homologação.
- **T4:** financeiro (28) · fiscal · empresas · crm · comercial · licitações · governo/integrações · area-do-cliente.

> Regras herdadas: deploy blue-green serializado (lock), `git add` só do próprio módulo, dinheiro/gov gated, nunca fabricar, verificar pela rota da tela, acumular 2-3 telas/deploy.
