# BRIEFING — TERMINAL 1 (T1) · Financeiro + Fiscal + Empresas + CRM + Comercial + Licitações + Governo (PESADO/CRÍTICO)

> Missão: ligar botões **abrir HTML + baixar PDF** em TODO documento do seu território no **redesign**.
> Trabalhe em **LOOP** até fechar o checklist. **NÃO faça deploy nem use o browser** (release + E2E são do orquestrador).
> Leia antes: `REGRAS-SESSAO.md`, `CONTRATO-FUNDACAO.md`, `MATRIZ-MESTRE-REDESIGN.md`, `PRE-MORTEM.md`.
> **Commit por etapa com PATHSPEC**: `git commit --no-verify -- <seu_builder.py>` (retry 2s se `index.lock`).

## Seu território (edite SÓ estes builders) — MAIOR VOLUME, muitos gated 💰🏛️
`redesign_builders/`: **financeiro.py · fiscal.py · empresas.py · crm.py · comercial.py · licitacoes.py · integracoes.py · area_do_cliente.py**
Módulos redesign: financeiro (28), fiscal (11), empresas (7), crm (12), comercial, licitacoes (10), integracoes (governo), area-do-cliente (6). Priorize os ✅ ready primeiro; os 🔨 só-JSON sinalize ao orquestrador.

> **NUNCA** edite fora da lista nem a fundação. Caso novo → orquestrador.

## Documentos a ligar (rota EXATA — curl-verifique 200+type antes; muitos gated)
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
- fiscal → **XML de nota** `xml_raw` (L4: **1.175 notas** sem endpoint → criar `/.../{id}/xml`; sinalize).
- crm/propostas → `/api/v1/crm/proposals/{id}/pdf` (por-linha).
- crm/contratos → `/api/v1/crm/contracts/{id}/pdf` (por-linha).
- crm → **relatório comercial** `/api/v1/crm/growth/reports/comercial/pdf`, **relatório de visita** `/api/v1/crm/.../visitas/pdf` (L8).
- crm/growth → doc registrado `/api/v1/crm/growth/docs/download/{id}?t=`.
- empresas/migrador → **Plano de contas Domínio** (TXT).
- governo (integracoes) → **comprovante Inter, guia Portte, SPED (TXT), CT-e/MDF-e (XML)**.
- area-do-cliente/documentos → doc do portal.

**🔨 criar rota/render (só-JSON, ~60 — sinalize ao orquestrador):**
- financeiro/fiscal: DRE/Balancete/Fluxo/Balanço/Apuração Lucro Real/DAS/retenções/painéis (peça `/pdf` gêmea reusando `gerar_relatorio_pdf`).
- governo: DAS/PGDAS/GRFGTS/DARF/e-CAC/certidão (~19).
- empresas/demonstrativos: DRE/Balanço/DFC/Consolidado.
- **onvio_documents (803 arquivos)** — L3: sem rota de download → sinalize.
- **ai/report_generator** — L1: motor de export completo NÃO montado em produção → decidir com orquestrador.

**⛔ NÃO ligar (disabled honesto):**
- **DANFE e XML NFC-e** = placeholder fake. **SPED `/sped/gerar`** = stub. fiscal/DCTFWeb/EFD-Reinf/eSocial — sem download na tela.
- **empresas** "Exportar Agora" (sem onClick) e exports Domínio lançamentos/nfse (**payload hardcoded**).
- **licitacoes/propostas** — PDFs em `media/bidding/proposals/` **sem rota** + "Gerar PDF" sem onClick.
- **conciliação**: use `mode="json"` (NÃO blob).

## Cuidado especial (pré-mortem)
🔒 financeiro = só Jordan+Pyetra; fiscal idem — **gate no backend** (QA chama com perfil sem permissão → espera 403). Documento fiscal/gov jamais diz "transmitido" sem transmissão real. Comprovante/boleto é LEITURA (seguro); pagar/faturar = OTP (não é seu escopo).

## Fluxo do loop
rota real (montada em `main_production.py`) + curl 200 → `scr.docs`/`docsfn` (`mode="json"` onde aplicável) → py_compile → `git commit -- financeiro.py` (só o seu) → checklist. **Sem deploy, sem browser.** Ao terminar, reporte o checklist ao orquestrador.
