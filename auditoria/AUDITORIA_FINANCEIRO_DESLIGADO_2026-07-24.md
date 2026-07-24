# Auditoria profunda — Financeiro: REAL / DESLIGADO / CASCA / AUSENTE
Data: 2026-07-24 · Método: 6 agentes read-only varrendo `/opt/conecta-pro/backend` · Produção roda `main_production:app`

## Tese
A maioria do que "os grandes têm e o meu não" **JÁ EXISTE no backend**. Pouca coisa é realmente AUSENTE.
O gap é: **DESLIGADO** (falta agendador/wiring/re-apontar) ou **CASCA** (calcula mas não persiste/transmite).
Ótimo pro CFO do T3: há muito motor pronto pra orquestrar.

Legenda: 🟢 REAL/ligado · 🟡 DESLIGADO (existe, falta ligar) · 🟠 CASCA (parcial, falta completar) · 🔴 AUSENTE

---

## 🟢 REAL — já funciona (às vezes só não exposto na tela)
| Capacidade | Prova |
|---|---|
| Conciliação bancária automática (3 estratégias valor/CNPJ/data) | `reconciliation_service.py:155,448` · `POST /financial/conciliar/auto` — **não exposto no redesign** |
| Contabilização automática (folha, receita/ISS NFS-e, despesas; batch diário 05:00) | `ledger_auto_service.py` · beat `celery_app.py:311` |
| DRE por competência + PDF · DFC método direto + PDF | `relatorios_controller.py:661,1108,1267` · `fluxo_caixa_service.py:243` |
| EBITDA / margens · 6 KPIs auto-recalc hourly | `financial_dashboard_controller.py:447` · `kpi_recalc_service.py:236` |
| Score de crédito do cliente (histórico real de pagamento) | `receivable_ai_service.py:106` · `/financial/receivables/.../risk` |
| Detecção de anomalia (cashflow + contas a pagar, com dedup antifraude) | `cashflow_ai_service.py:601` · `payable_ai_service.py:37` |
| Forecast ML de verdade (série temporal sobre inter_transactions) | `analytics/.../sales_forecaster.py` — **não plugado nas telas fin** |
| NF-e e NFS-e emissão (SEFAZ real, PyNFe/mTLS; default homologação) | `nfe_provider.py:359` · `nfse_nacional.py:409` |
| SPED ECD · EFD-ICMS/IPI · EFD-Contribuições (geração de arquivo) | `sped_contabil.py:266` · `sped_fiscal.py:242` · `sped_manager.py:117` |
| Apuração IRPJ/CSLL (Lucro Real, do razão) · DAS · PIS/COFINS/ISS · retenções | `apuracao_lucro_real_service.py:51` · `tax_calculator.py` · `cfop_ncm.py:300` |
| eSocial SST (S-2200/2230/2299, mTLS real; default produção restrita) | `esocial_transmitter.py:906` |
| Renegociar parcela · Categorização de fornecedores por regra · Orçamento manual (KV) | `receivable_service.py:401` · `fornecedor_categoria_service.py:30` · `relatorios_controller.py:64` |

## 🟡 DESLIGADO — existe e funciona, falta só LIGAR (quick wins)
| Capacidade | O que falta | Prova |
|---|---|---|
| **⭐⭐ Insights financeiros (tela vazia)** | Bug de wiring: tela chama `identificar_riscos`, método real é `_identify_risks`; `hasattr`=False→vazio. Corrigir nome + condominio_id | `_fin_visao.py:55-57` vs `cashflow_ai_service.py:447,504` |
| **⭐ Cobrança recorrente mensal** | Motor real (gera PIX/boleto Inter/Cora, insere em receivable_accounts); falta 1 beat `crontab(day_of_month="1")` | `recurring_billing_service.py:131` · `POST /financial/billing/cobrar-recorrente` |
| **⭐ Balanço Patrimonial** | Serviço completo, lê razão VAZIO (`fin_journal_entries`); re-apontar p/ `accounting_entries` | `balance_sheet_service.py:328` · rota `:816` |
| **⭐ Orçado × Realizado (variância + alerta estouro)** | Motor completo, lê razão vazio; re-apontar + ligar à tabela KV | `budget_service.py:306` · `budget_forecast_service.py:53` |
| Fechamento contábil (apuração de resultado→PL) | `PeriodClosingService` órfão; controller usa só flip de status. Trocar + implementar `_generate_provisions` | `period_closing_service.py:165` vs `accounting_repository.py:786` |
| Fraude DB-backed (regras/perfil no banco) | Existe, não registrada em `main_production.py` (só em dev) | `modules/ai/fraud_detection/` · `api/v1/__init__.py:302` |
| EFD-Reinf (R-2010/4010/4020/2099) | Gera XML; só R-1000 transmite. Implementar POST real em `enviar_lote` + cert | `efd_reinf_service.py:424` · `efd_reinf.py:500` |
| NF-e / eSocial em PRODUÇÃO | Flag de ambiente: `ambiente="1"` (NF-e) · `ESOCIAL_AMBIENTE=producao` | `settings.py:82` |

## 🟠 CASCA — calcula/parcial, não persiste/transmite (falta completar)
| Capacidade | Estado | Prova |
|---|---|---|
| Régua de cobrança escalonada (dispara sozinha) | Gera só o TEXTO; `send_billing_reminder` órfão; sem loop de envio | `collection_negotiator.py:68` · `whatsapp_service.py:254` |
| `billing_rules` generate/process-all | `return "pending_implementation"` | `billing_rule_controller.py:281,298` |
| Import OFX | Parser ok, gravação quebra (`TransactionCategory.OUTROS` + `statement_reference` inexistentes) | `bank_transaction_controller.py:580,584` |
| Provisões férias/13º | Calcula os pares D/C, retorna JSON, nunca posta no razão | `bookkeeper_auto.py:80-114` |
| Depreciação de ativo | Calcula no cadastro de equipamento, zero integração contábil | `equipment.py:355` |
| Rateio de centro de custo (ABC) | Motor real gerencial; `journal_entry_id` nunca preenchido; sem beat | `costing/services/allocation_service.py` |
| DCTFWeb | Apura folha real, mas `transmitir()` fabrica recibo local (sem XML/WS) | `dctfweb_service.py:91` · `core/dctfweb.py:418` |
| eSocial Folha (S-1200) | Simula transmissão (PORTTE — **não ligar**) | `payroll_integration/.../esocial_service.py:399` |
| Fraude ML (IsolationForest) | Treina com `np.random` (dados sintéticos) | `analytics/models/fraud/fraud_detector.py:693` |
| Acordo/parcelamento dívida do cliente | Endpoint aceita e retorna conta inalterada (`# Implementar`) | `receivable_controller.py:785` |
| Consolidação de grupo | Soma lado-a-lado (`caixa_por_cnpj`), sem eliminação intercompany | `caixa_service.py:147` |
| Forecast das telas fin | Heurística determinística (fator 0.95, cenários fixos) | `cashflow_ai_service.py:255` |
| NFS-e cancelamento · SPED via `/financial/sped/*` · SEFAZManager | TODO/stub | `fiscal_controller.py:981,1076` · `sefaz_manager.py:1028` |

## 🔴 AUSENTE — não existe, teria que construir
Open Finance/agregação (Pluggy/Belvo) · CNAB retorno · Negativação Serasa/SPC/protesto ·
Antecipação de recebíveis/desconto de duplicata · DSO/DPO/ciclo de caixa/giro ·
Liquidez/endividamento de dado real · DRE por regime de caixa · SPED ECF (gerador) ·
Regras de conciliação configuráveis · Categorização por ML · Eliminação intercompany.

---

## Top quick-wins (maior retorno × menor esforço)
1. **Insights (tela vazia)** — corrigir nome de método em `_fin_visao.py` → motor já pronto. Minutos.
2. **Balanço Patrimonial + Orçado×Realizado** — re-apontar serviços de `fin_journal_entries` → `accounting_entries` (truque que o DRE fallback já usa).
3. **Cobrança recorrente mensal** — adicionar 1 beat `crontab(day_of_month="1")` chamando `gerar_cobrancas_mensais`.
4. **Expor conciliação automática no redesign** + corrigir bug 500 `pending-reconciliation` (falta `end_date`, `bank_transaction_controller.py:149`).
5. **Import OFX** — corrigir 2 bugs (`TransactionCategory.OUTROS`, `statement_reference`).

## Nota de método
Nenhum dado editado. "Desligado" aqui é por **ausência de agendador** ou **wiring errado**, não por feature-flag.
"Casca" é **simulação/stub explícito** (código presente que finge em vez de executar). Prova em `arquivo:linha` acima.
