# BRIEFING — TERMINAL 4 (T4) · Financeiro + Fiscal + Empresas + CRM + Comercial + Licitações + Governo + Área do Cliente

> Missão: ligar botões **abrir HTML + baixar PDF** em TODO documento do seu território no **redesign**.
> Trabalhe em **LOOP** até fechar o checklist. **NÃO faça deploy** (release único pelo orquestrador).
> Leia antes: `CONTRATO-FUNDACAO.md`, `MATRIZ-MESTRE-REDESIGN.md`, `PRE-MORTEM.md`.

## Seu território (edite SÓ estes builders)
`redesign_builders/`: **financeiro.py · fiscal.py · empresas.py · crm.py · comercial.py · licitacoes.py · integracoes.py · area_do_cliente.py**
Módulos redesign: financeiro (28), fiscal (11), empresas (7), crm (12), comercial, licitacoes (10), integracoes (governo), area-do-cliente (6).

> **NUNCA** edite fora da lista nem a fundação. Caso novo → orquestrador. Você tem o maior volume (~30 ready + ~60 só-JSON) — priorize os ✅ ready primeiro.

## Documentos a ligar (rota EXATA — muitos gated)
**✅ ready:**
- financeiro/relatorios → **DRE, Balancete, Fluxo de Caixa** `/api/v1/financial/relatorio?tipo=...` (por-tela, 🔒 financeiro).
- financeiro/contas-a-receber → **Aging Receber** `/api/v1/financial/receivables/aging/pdf` (🔒).
- financeiro/contas-a-pagar → **Aging Pagar** `/api/v1/financial/payables/aging/pdf` (🔒).
- financeiro/conciliacao → **Export** `/api/v1/financial/bank-reconciliations/{id}/export?export_format=csv` — **modo `json`** (L9, `{content,filename}`) — **provado 200** na piloto. Por-linha.
- financeiro/nfs-e-entrada → **DANFSe recebida** `/api/v1/financial/nfse-entrada/{chave}/pdf` (🏛️ por-linha).
- financeiro/boletos + cobrancas → **Boleto** (Inter URL, 💰 por-linha).
- financeiro/inter|pagamentos → **Comprovante Inter** `/api/v1/financeiro/inter/payments/{id}/comprovante` (💰, gate: só após pago — por-linha).
- fiscal/nfs-e → **DANFSe emitida** `/api/v1/financial/fiscal/nfse/{id}/danfse` (🏛️ por-linha).
- fiscal/guias → **Guia fiscal (Drive)** `/api/v1/fiscal/guias-drive/pdf/{id}` (🏛️ por-linha).
- fiscal/certidoes → **CND** `/api/v1/gedeon/cnd/pdf/{type}` (🏛️).
- fiscal → **XML de nota** `xml_raw` (L4: **1.175 notas** sem endpoint → criar `/.../{id}/xml`; sinalize ao backend).
- crm/propostas → `/api/v1/crm/proposals/{id}/pdf` (por-linha).
- crm/contratos → `/api/v1/crm/contracts/{id}/pdf` (por-linha).
- crm → **relatório comercial** `/api/v1/crm/growth/reports/comercial/pdf`, **relatório de visita** `/api/v1/crm/.../visitas/pdf` (L8).
- crm/growth → doc registrado `/api/v1/crm/growth/docs/download/{id}?t=`.
- empresas/migrador → **Plano de contas Domínio** (TXT).
- governo (integracoes) → **comprovante Inter, guia Portte, SPED (TXT), CT-e/MDF-e (XML)**.
- area-do-cliente/documentos → doc do portal.

**🔨 criar rota/render (só-JSON, ~60):**
- financeiro/fiscal: DRE/Balancete/Fluxo/Balanço/Apuração Lucro Real/DAS/retenções/painéis (peça `/pdf` gêmea ao backend, reusa `gerar_relatorio_pdf`).
- governo: DAS/PGDAS/GRFGTS/DARF/e-CAC/certidão (~19, só-JSON).
- empresas/demonstrativos: DRE/Balanço/DFC/Consolidado.
- **onvio_documents (803 arquivos)** — L3: sem rota de download → sinalize ao backend.
- **ai/report_generator** — L1: motor de export completo NÃO montado em produção → decidir com orquestrador (reviver como render genérico ou marcar morto).

**⛔ NÃO ligar (corrigir/desabilitar honesto):**
- **DANFE e XML NFC-e** = placeholder fake → `disabled`.
- **SPED `/sped/gerar`** = stub → `disabled`.
- fiscal/DCTFWeb, EFD-Reinf, eSocial (aba fiscal) — geram mas sem download na tela → `disabled` até haver rota.
- **empresas** "Exportar Agora" (sem onClick) e exports Domínio lançamentos/nfse (**payload hardcoded**) → não ligar/`disabled`.
- **licitacoes/propostas** — PDFs em `media/bidding/proposals/` **sem rota** (L do crítico) + "Gerar PDF" sem onClick → `disabled` até criar rota de download.
- **conciliação**: use `mode="json"` (NÃO blob) senão abre JSON como PDF.

## Cuidado especial (do pré-mortem)
- 🔒 financeiro = só Jordan+Pyetra; fiscal idem. **Gate no backend** — o QA vai chamar com perfil sem permissão e esperar 403. Documento financeiro/fiscal vazando = LGPD.
- Documento fiscal/gov **jamais** diz "transmitido/autorizado" sem transmissão real.
- Dinheiro-que-sai (pagar/faturar) = OTP — mas comprovante/boleto é LEITURA (seguro).

## Fluxo do loop
Igual: rota real (montada em `main_production.py`) → `scr.docs`/`docsfn` (`mode="json"` onde aplicável) → py_compile → oráculo → `git add` só do seu builder → commit por etapa → checklist. **Sem deploy.**
