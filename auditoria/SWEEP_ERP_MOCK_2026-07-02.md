# SWEEP MOCK — ERP INTEIRO (2026-07-02) — achados fora de GP (fila p/ depois)
*Jordan redirecionou o foco pros 8 módulos de GP. Estes achados do ERP ficam registrados pra tratar quando ele pedir.*

## 🔴 FINANCEIRO
- `/financial/bi/profitability`: revenue/costs/margin = 0 (SQL usa coluna `amount` inexistente em cashflow_entries; real=`realized_amount`). except engole erro.
- `/financial/bi/overview` DRE: margem/EBITDA/lucro = 100% fabricado (receita cai p/ fallback MRR mas custo fica 0 no mês corrente).
- `/cashflow/dashboard` (front): receivables/payables/trends/projections chumbados em 0 (real em receivable_accounts=22/payable_accounts=20).
- `BIService` inteiro stub (`_get_empty_data`→[]): widgets/kpis/summary = 0. bi_service.py:80-102.
- `/financial/bi/kpis`: financial_kpis stale (Saldo Inter 36.476 vs live 54.688; congelado desde mar).
- fallbacks hardcoded dormentes MRR 272086.96 / saldo 36476.27.

## 🔴 BI/ANALYTICS (o pior — dashboard executivo)
- `/analytics/executive/dashboard`: TUDO fabricado — Receita R$2,85M (real MRR 270k), trends fixas, alertas/insights inventados. executive_dashboard_service.py:167 "# Simulação". Real=`executive_kpis`(10).
- `/analytics/{churn,forecast,fraud,leads}`: features/forecast em np.random (feature_store.py:433, sales_forecaster.py:370). `/forecast/accuracy` = 87.5/12.5/1250 hardcoded.
- `/ai/reports/generate`: números por random.randint (report_generator.py:300). PDF/Excel = bytes vazios.
- código morto (não montado, não religar sem fix): intelligent_reporting_service, realtime_analytics_service.
- executive_kpis/financial_kpis: dado REAL porém stale (last_calculated_at=2026-03-23; sem job recalculando).

## 🔴 FISCAL/GOV
- NFC-e (todos endpoints): autorização SEFAZ FABRICADA (protocolo por timestamp, "Autorizado", success=True sem transmitir). nfce_controller.py:163. Mitigante: empresa não emite NFC-e.
- eSocial `gerar_lote`: protocolo/status "enviado" fabricado (esocial_controller.py:363). Contraste: S-1000 transmite de verdade.
- Dashboard gov "16/17 online": 15 de 16 status hardcoded "online" (dashboard_controller.py:266,408). SEFAZ NF-e é real.
- dead code fabricando regularidade: fgts_inss_manager emitir_crf/cnd (NEGATIVA fake), ecac validar_certidao (valida=True).
- LIMPO/honesto: e-CAC situação (nao_sincronizado), FGTS/INSS cálculo local (fonte marcada), dashboards multi-empresa, NFS-e Manaus.

## 🟢 COMERCIAL/CRM (quase limpo)
- `/crm/forecast` + Relatório Comercial PDF: contam oportunidades soft-deleted (falta `is_active`) → R$280.811 vs R$193.167 real dos KPIs. growth_controller.py:1119,1174,1206,1226. (lixo ZZE2E incluso)
- dead code: crm_360_service.py (random/demo, não servido) → deletar.
- resto REAL.

## 🟢 GED/ÁREA CLIENTE (residuais já corrigidos + stored-stale)
- `/ged/stats`,`/documents/stats/summary`,`/documents/ai/dashboard`: JÁ REAL (repoint p/ ged_kit_documents=2046).
- kit `total_documents`/`documents_signed`/`completion_percentage` STORED-STALE (31/38 divergem; ex kit mostra 0, real 204). Afeta GP-GED + portal cliente. → recalcular do COUNT.
- portal `/analytics/overview`: janela 30d quebrada (`.replace(day=day-30)`), `documentos_baixados`=assinados (mislabel; real em ged_kit_access_logs downloaded).
- `/ged/stats` active_documents==total (tabela não tem status arquivamento).

---
## ✅ CORRIGIDOS (2026-07-02, commit 3f35e65d) — provados curl vs banco + bake
- **BI executive dashboard**: R$2,85M fabricado → executive_kpis REAL (Receita 270.586,96 / Folha 95.950 / 10 KPIs); alertas de alert_level+ged_certidoes; insights fabricados removidos; trends = previous→current real.
- **Forecast/predictive**: np.random → inter_transactions real (série diária); /forecast/accuracy 87.5 fixo → measurable:false honesto; feature_store random → clients.created_at real + resto honesto; AI report random → fontes reais (contracts/inter/clients/commissions/hr_payslips) + PDF/Excel reais.
- **Financeiro**: /bi/profitability amount→realized_amount (erro sumiu; 0=vazio-real do período, real em 365d=1.13M); DRE 100% → honesta ("sem lançamentos no mês"); /cashflow/dashboard zeros → receivable_accounts(316.904 pend)/payable_accounts(138.175); BIService stub → queries reais; fallbacks 36476/272086 removidos.
- **Fiscal/Gov**: NFC-e (5 endpoints) + eSocial gerar_lote → HTTP 501 honesto (não fabricam protocolo/autorização); dashboard gov status ← gov_sync_logs real (não "16/17 online" fixo); CRF/CND/ecac dead-code → NotImplementedError/valida=false.
- **Comercial**: /crm/forecast + relatório PDF + by-seller → +is_active (280.811 → 193.167,92 real, bate com KPIs).
- PENDENTE menor: crm_360_service.py (dead-code random) — não removido (importado por 5 testes); financial_kpis/executive_kpis stale (last_calculated_at NULL — precisa job recalc); /ged/stats active==total mislabel.

---
## ✅ VARREDURA FINAL (2026-07-02) — módulos restantes
Fixers paralelos (finder≠fixer≠verificador). Corrigidos:
- **Área Cliente** `/analytics/overview`: janela 30d (timedelta) + documentos_baixados (ged_kit_access_logs downloaded real). [precisa token portal p/ curl]
- **Facilities** campo/tickets: FANTASMA "Cliente Exemplo" → 404/501 honesto (não há tabela).
- **Gestão** notifications/intelligent/analytics: 1250/5000/45-30-10 hardcoded → notification_logs real (0 honesto, tabelas vazias); mobile/dashboard 150/45/125k → leads=17/clients=14/R$270k reais; mobile/batch "success" fabricado → 501 honesto.
- **Licitações**: Sentinel lê bidding_certificates=8 reais (não catálogo fixo NAO_POSSUI); Assessor carrega bidding_analyses real (não ValueError); PricerAgent CompanyProfile literais → None honesto + colaboradores(employees)/docs(certificates) reais.
- **LGPD** (security_lgpd): consent/pia/audit/erasure eram FANTASMA em-memória → agora persistem em lgpd_* (tabelas CRIADAS via models, checkfirst); erasure não fabrica mais success (status honesto pendente/in_progress). ATENÇÃO: tabelas criadas direto (sem migration file) — adicionar migration p/ reprodutibilidade; erasure exclusão real de PII ainda pendente (gate humano).

## 🟡 ISSUES NÃO-MOCK descobertos (schema drift, não fabricação — fila separada)
- **services/catalog + orders/stats + orders/at-risk = 500**: schema drift — model define `service_catalog.currency` e `service_orders.latitude` que NÃO existem no banco. Não é mock (500 honesto, não mostra dado falso). Fix = migration (add colunas) ou remover do model. service_controller já corrigido p/ sessão síncrona (repo é sync).
- crm_360_service.py dead-code random (importado por testes).
- executive_kpis/financial_kpis reais mas last_calculated_at NULL (falta job recalc).
