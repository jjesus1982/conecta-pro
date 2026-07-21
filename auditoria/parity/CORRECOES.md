# Log de Correções — P0 líquido (Tier 1 legal/dinheiro) no Redesign
Estratégia aprovada (2026-07-20): B+C — clássico segue operacional; corrijo só Tier 1 (risco legal/multa+dinheiro) no redesign. Regra: eSocial/OTP = trago VISIBILIDADE real + ação gated; NUNCA disparo transmissão/pagamento real em teste.

| # | Módulo | Finding P0 fechado | Como | Prova | Status |
|---|--------|--------------------|------|-------|--------|
| 1 | saude-ocupacional/gp | Central de Transmissão eSocial (status/protocolo/recibo S-2210/2220/2230/2240) sem visibilidade no redesign | tela `esocial` no `_build_saude` reusando `transmissao_central_service.acompanhamento` (READ real); nav em EXTRA_MENU | auditoria/prova_esocial.png (7 eventos, protocolo real, badge "dados reais") | ✅ FECHADO (visibilidade) — transmitir-lote segue gated |
| 2 | saude-ocupacional | CAT (S-2210) sem tela no redesign | tela `cat` real (gp_cats) no `_build_saude` | curl 3 linhas reais + browser badge "dados reais" | ✅ FECHADO |
| 3 | saude-ocupacional | Afastamentos (S-2230) sem tela | tela `afastamentos` real (sst_afastamentos) | auditoria/prova_afastamentos.png (8 reais, CID/estabilidade) | ✅ FECHADO |

**Commit:** f4874241. **Estado:** DEPLOYADO (blue-green pós-T2), VIVO e re-verificado no browser (auditoria/redeploy_esocial.png). Commit f4874241.
**Fila Tier 1 (commit-only até o deploy):** financeiro OTP-visibilidade · fiscal e-CAC/DCTFWeb/Reinf · ponto espelho Portaria 671 · portal/meu-espaço facial · LGPD segurança.
| 4 | gestao-de-pessoas (ponto) | Fechamento Mensal de Ponto / espelho (Portaria 671) sem tela | tela `ponto-espelho` (gp_monthly_closings, 50 reais) — preenche menu já existente | auditoria/prova_fechamento.png (50 fechamentos reais, status Fechado) | ✅ FECHADO + DEPLOYADO |
| 5 | financeiro | Fila de pagamentos Inter (money-out) sem visibilidade no redesign | tela `inter-pagamentos` (inter_payments, 32 reais) + coluna OTP; SEM botão de pagar | auditoria/prova_interpag.png (32 pagtos, OTP ✓ por linha) | ✅ FECHADO + DEPLOYADO |
| 6 | fiscal | DCTFWeb / EFD-Reinf sem tela (status/prazo) | telas `dctfweb`+`reinf` (fiscal_obligations por tipo, 4+4 reais) | auditoria/prova_dctfweb.png (06→01/2026, Cumprida) | ✅ FECHADO + DEPLOYADO |
| 7 | departamento-pessoal | Breakdown proventos/descontos do holerite sumiu (só bruto/líquido) | tela `folha-rubricas` (unnest JSON hr_payslips earnings/deductions, 400 rubricas reais) | auditoria/prova_rubricas.png (DIAS NORMAIS/HORAS FÉRIAS/INSS/VALE…) | ✅ FECHADO + DEPLOYADO |
| 8 | crm | Precificação perdeu a Tabela CCT (10 funções) — virou dashboard | tela `precificacao` (crm_pricing_funcoes, 10 reais) piso+adicionais | auditoria/prova_precif.png (R$1.670 + Sim/—) | ✅ FECHADO + DEPLOYADO |
| 9 | operacional | Comunicados sem tela (feed institucional) | tela `comunicados` (communication_announcements, 10 reais) título/tipo/prioridade/destinatários/status | auditoria/prova_comunicados.png (10 reais, prioridades coloridas) | ✅ FECHADO + DEPLOYADO |
| 10 | integracoes | Módulo 100% exemplo (sem builder) | NOVO _build_integracoes: visão + Sólides (solides_employees 44 reais, nome/email/CPF) | auditoria/prova_int_solides.png | ✅ FECHADO + DEPLOYADO |
| 11 | departamento-pessoal | Config CCT de benefícios sem tela | tela `beneficios-cct` (cct_beneficios 8 reais) valores + obrigatoriedade | auditoria/prova_bcct.png | ✅ FECHADO + DEPLOYADO |
| 12 | crm | Aba Atividades/Timeline perdida | tela `atividades` (crm_activities, 69 reais) assunto/tipo/cliente/agendada/concluída | auditoria/prova_ativ.png | ✅ FECHADO + DEPLOYADO |
| 13 | departamento-pessoal | Motor de verbas rescisórias ausente (calculadora) | ferramenta `calcular-rescisao` (reusa clt_calculator, COMPUTE puro, não gera rescisão) | auditoria/prova_resc.png (ADAILSON líquido R$5.927,94) | ✅ FECHADO + DEPLOYADO |
| 14 | crm | Precificação sem simulador (aba Simular/Parâmetros) | ferramenta `simular-preco` (reusa PricingEngine, COMPUTE puro, não gera proposta) | curl: portaria 10 postos → R$5.471/posto, mensal R$54.712, margem 21,69% | ✅ FECHADO + DEPLOYADO |
| 15 | departamento-pessoal | Sem calculadora de férias (verbas) | ferramenta `calcular-ferias` (reusa clt_calculator, COMPUTE puro, não solicita/paga) | curl: ADAILSON 30d → líquido R$2.050,58 | ✅ FECHADO + DEPLOYADO |
| 16 | fiscal | Guias FGTS invisíveis no redesign | tela `guias-fgts` (fgts_guias Onvio, colunas reais + PDF) | curl: 45 guias, 1ª=12.2025 Consignado PDF Pendente | ✅ FECHADO + DEPLOYADO |
| 17 | fiscal | Guias INSS invisíveis no redesign | tela `guias-inss` (inss_guias Onvio) | curl: 6 guias, 1ª=11.2025 PDF Pendente | ✅ FECHADO + DEPLOYADO |
| 18 | financeiro | Sem custeio de encargos CCT | ferramenta `custeio-cct` (compute PricingEngine, nada gravado) | curl: 10 colab → encargos R$146.512,44 detalhado | ✅ FECHADO + DEPLOYADO |
| 19 | departamento-pessoal | Saldo de férias invisível | tela `saldo-ferias` (employee_vacation_periods, 67 períodos) | curl: ANDREA 30d disponíveis, vence 31/12/2026 | ✅ FECHADO + DEPLOYADO |
| 20 | fiscal | Certidões CND fiscais invisíveis (screen "certidoes" era de licitações) | tela `certidoes-cnd` (ged_certidoes + cálculo situação p/ vencimento) | curl: 9 CNDs, Alvará=Vencida | ✅ FECHADO + DEPLOYADO |
| 21 | fiscal | NFS-e tomadas só num KPI | tela `nfse-tomadas` (nfse_tomadas_nacional) | curl: 292 notas, SOLIDES R$236 | ✅ FECHADO + DEPLOYADO |
| 22 | juridico | DET/comunicações trabalhistas invisíveis | tela `det-comunicacoes` (juridico_det_comunicacoes) | curl: 11 comunicações c/ prazo legal | ✅ FECHADO + DEPLOYADO |
| 23 | crm | Aditivos contratuais invisíveis | tela `aditivos` (contract_addendums, gotcha enum::text) | curl: 7 aditivos, CTR-2026-00008 | ✅ FECHADO + DEPLOYADO |
| 24 | juridico | Contratos jurídicos invisíveis | tela `contratos` (client_contracts, redesign_builders/juridico.py) | build(): 10 contratos, CTR-2026-00011 portaria_remota | ✅ FECHADO (via fundação) |
| 25 | juridico | Base de conhecimento jurídico invisível | tela `conhecimento` (juridico_conhecimento) | build(): 4 casos reais (Ermeson/Thais) | ✅ FECHADO (via fundação) |
| 26 | juridico | Análises de contrato invisíveis | tela `analise` (juridico_analises, resultado JSON→resumo) | build(): parecer crítico, risco 89 | ✅ FECHADO (via fundação) |
| 27 | juridico | Menu processos-det (DET) vazio | tela `processos-det` (juridico_det_comunicacoes) | build(): 11 comunicações | ✅ FECHADO (via fundação) |
| 28 | departamento-pessoal | 10 telas do menu sem wiring (admissao/aviso-previo/ponto/fechamento-ponto/licencas/reembolsos/contratos/documentos/certificacao/esocial) | `redesign_builders/departamento_pessoal.py` estende `_build_dp`; lê tabelas clássicas reais; aviso-previo=query real 0-linhas (honesto) | Deploy blue-green OK (hash imagem==host) + HTTP 200 autenticado: 10/10 telas, rows reais (admissao 3·ponto 300·fechamento 50·licencas 8·reembolsos 20·contratos 43·docs 32·certif 51·esocial 36) | ✅ FECHADO + DEPLOYADO (via fundação T3) |
| 28 | documentos | Kits de documentos invisíveis | tela `kits` (ged_document_kits, 58) | build(): 07/2026 31 docs 19% Em montagem | ✅ FECHADO (fundação) |
| 29 | documentos | Pastas GED invisíveis | tela `pastas` (ged_folders, 8) | build(): Contratos/Ativa | ✅ FECHADO (fundação) |
