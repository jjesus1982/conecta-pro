/**
 * Tipos temporarios/placeholders - Mapeamento para tipos reais
 * Gerado automaticamente - NÃO EDITAR MANUALMENTE
 *
 * Este arquivo mapeia nomes simplificados para os tipos gerados pelo Orval
 * Os tipos reais estão em: src/types/generated/financial/
 */

// =====================================================================
// Financial Types - Re-exports dos tipos gerados
// =====================================================================

// Accounting - ListAccounts params
export type { ListAccountsApiV1FinancialAccountingAccountingAccountsGetParams as ListAccountsApiV1FinancialAccountingAccountsGetParams } from './generated/financial/financial-accounting/financial-accounting';

// Bank Transactions - ListTransactions params
export type { ListTransactionsApiV1FinancialBankTransactionsBankTransactionsGetParams as ListTransactionsApiV1FinancialBankTransactionsTransactionsGetParams } from './generated/financial/financial-bank-transactions/financial-bank-transactions';

// BI Dashboard - Create types
export type { DashboardCreate as FinancialDashboardCreate } from './generated/financial/models';
export type { WidgetCreate as FinancialWidgetCreate } from './generated/financial/models';
export type { KPICreate as FinancialKPICreate } from './generated/financial/models';
export type { ReportCreate as ScheduledReportCreate } from './generated/financial/models';

// Cashflow - Entry and Forecast params
export type { ListEntriesApiV1FinancialCashflowCashflowEntriesGetParams as GetEntriesApiV1FinancialCashflowEntriesGetParams } from './generated/financial/financial-cashflow/financial-cashflow';
export type { ListForecastsApiV1FinancialCashflowCashflowForecastsGetParams as GetForecastApiV1FinancialCashflowForecastGetParams } from './generated/financial/financial-cashflow/financial-cashflow';

// ABC Costing - ListDrivers params
export type { ListDriversApiV1FinancialCostingCostingDriversGetParams as ListDriversApiV1FinancialCostingDriversGetParams } from './generated/financial/financial-abc-costing/financial-abc-costing';

// Fiscal - ListNfes params
export type { ListarNfesApiV1FinancialFiscalFiscalNfeGetParams as ListNfesApiV1FinancialFiscalNfesGetParams } from './generated/financial/financial-fiscal/financial-fiscal';

// Inventory - ListWarehouses params
export type { ListWarehousesApiV1FinancialInventoryInventoryWarehousesGetParams as ListWarehousesApiV1FinancialInventoryWarehousesGetParams } from './generated/financial/financial-inventory/financial-inventory';

// Payables - ListPayables params
export type { ListAccountsApiV1FinancialPayablesPayablesGetParams as ListPayablesApiV1FinancialPayablesPayablesGetParams } from './generated/financial/financial-payables/financial-payables';

// Purchase - ListRequisitions params
export type { ListRequisitionsApiV1FinancialPurchasePurchasesRequisitionsGetParams as ListRequisitionsApiV1FinancialPurchaseRequisitionsGetParams } from './generated/financial/financial-purchase/financial-purchase';

// Receivables - ListReceivables params
export type { ListAccountsApiV1FinancialReceivablesReceivablesGetParams as ListReceivablesApiV1FinancialReceivablesReceivablesGetParams } from './generated/financial/financial-receivables/financial-receivables';

// =====================================================================
// Financial Types - Interfaces para tipos que nao existem nos gerados
// =====================================================================

/**
 * Configuracao de impostos
 * Usado para configurar regras fiscais por tipo de operacao
 */
export interface TaxConfigurationCreate {
  /** Nome da configuracao */
  name: string;
  /** Descricao */
  description?: string;
  /** Tipo de imposto: ISS, ICMS, PIS, COFINS, CSLL, IR, etc */
  tax_type: string;
  /** Aliquota em percentual */
  rate: number;
  /** Aplicavel a servicos */
  applies_to_services?: boolean;
  /** Aplicavel a produtos */
  applies_to_products?: boolean;
  /** Regime tributario: simples, lucro_real, lucro_presumido */
  tax_regime?: string;
  /** CFOP aplicavel */
  cfop_codes?: string[];
  /** Ativo */
  is_active?: boolean;
  /** Condominio ID */
  condominio_id: string;
}

/**
 * Obrigacao fiscal para criacao
 * Usado para cadastrar novas obrigacoes fiscais
 */
export interface FiscalObligationCreate {
  /** Nome da obrigacao */
  name: string;
  /** Descricao */
  description?: string;
  /** Tipo: SPED, DCTF, EFD, GIA, DIRF, etc */
  obligation_type: string;
  /** Periodicidade: mensal, trimestral, anual */
  periodicity: 'mensal' | 'trimestral' | 'anual';
  /** Dia de vencimento */
  due_day: number;
  /** Competencia (YYYY-MM) */
  competencia: string;
  /** Status: pendente, em_andamento, concluida, atrasada */
  status?: 'pendente' | 'em_andamento' | 'concluida' | 'atrasada';
  /** Responsavel */
  responsible_id?: string;
  /** Condominio ID */
  condominio_id: string;
}

/**
 * Item de estoque para criacao
 * Usado para cadastrar novos itens no estoque
 */
export interface StockItemCreate {
  /** Codigo SKU */
  sku: string;
  /** Nome do item */
  name: string;
  /** Descricao */
  description?: string;
  /** Categoria */
  category_id?: string;
  /** Unidade de medida */
  unit: string;
  /** Quantidade inicial */
  initial_quantity?: number;
  /** Estoque minimo */
  min_stock?: number;
  /** Estoque maximo */
  max_stock?: number;
  /** Custo unitario */
  unit_cost?: number;
  /** Armazem ID */
  warehouse_id: string;
  /** Localizacao no armazem */
  location?: string;
  /** Data de validade */
  expiration_date?: string;
  /** Lote */
  batch?: string;
  /** Condominio ID */
  condominio_id: string;
}

/**
 * Parcela de conta a pagar para criacao
 * Usado para criar parcelas de contas a pagar
 */
export interface PayableInstallmentCreate {
  /** Conta a pagar ID */
  payable_id: string;
  /** Numero da parcela */
  installment_number: number;
  /** Valor da parcela */
  amount: number;
  /** Data de vencimento */
  due_date: string;
  /** Desconto */
  discount?: number;
  /** Juros */
  interest?: number;
  /** Multa */
  penalty?: number;
  /** Observacoes */
  notes?: string;
}

/**
 * Requisicao de pagamento de conta a pagar
 * Usado para registrar pagamento de parcelas
 */
export interface PayablePaymentRequest {
  /** Parcela ID */
  installment_id: string;
  /** Valor pago */
  amount_paid: number;
  /** Data do pagamento */
  payment_date: string;
  /** Metodo de pagamento: pix, boleto, transferencia, dinheiro, cartao */
  payment_method: 'pix' | 'boleto' | 'transferencia' | 'dinheiro' | 'cartao';
  /** Conta bancaria ID */
  bank_account_id?: string;
  /** Numero do documento/comprovante */
  document_number?: string;
  /** Observacoes */
  notes?: string;
  /** ID da transacao bancaria para conciliacao */
  bank_transaction_id?: string;
}

/**
 * Parcela de conta a receber para criacao
 * Usado para criar parcelas de contas a receber
 */
export interface ReceivableInstallmentCreate {
  /** Conta a receber ID */
  receivable_id: string;
  /** Numero da parcela */
  installment_number: number;
  /** Valor da parcela */
  amount: number;
  /** Data de vencimento */
  due_date: string;
  /** Desconto para pagamento antecipado */
  early_payment_discount?: number;
  /** Dias para desconto */
  early_payment_days?: number;
  /** Juros por dia de atraso */
  daily_interest?: number;
  /** Multa por atraso */
  late_penalty?: number;
  /** Gerar boleto automaticamente */
  generate_boleto?: boolean;
  /** Observacoes */
  notes?: string;
}

/**
 * Requisicao de recebimento de conta a receber
 * Usado para registrar recebimento de parcelas
 */
export interface ReceivablePaymentRequest {
  /** Parcela ID */
  installment_id: string;
  /** Valor recebido */
  amount_received: number;
  /** Data do recebimento */
  payment_date: string;
  /** Metodo de pagamento: pix, boleto, transferencia, dinheiro, cartao, debito_automatico */
  payment_method: 'pix' | 'boleto' | 'transferencia' | 'dinheiro' | 'cartao' | 'debito_automatico';
  /** Conta bancaria ID */
  bank_account_id?: string;
  /** Numero do documento/comprovante */
  document_number?: string;
  /** Observacoes */
  notes?: string;
  /** ID da transacao bancaria para conciliacao */
  bank_transaction_id?: string;
  /** Desconto aplicado */
  discount_applied?: number;
  /** Juros cobrados */
  interest_charged?: number;
}

// =====================================================================
// HR Analytics Types - Interfaces (modulo HR nao existe ainda)
// =====================================================================

/**
 * Configuracao de dashboard HR Analytics
 * Usado para configurar dashboards de RH
 */
export interface DashboardConfigRequest {
  /** Nome do dashboard */
  name: string;
  /** Descricao */
  description?: string;
  /** Tipo: operacional, tatico, estrategico */
  type: 'operacional' | 'tatico' | 'estrategico';
  /** Layout: grid, flex, tabs */
  layout?: 'grid' | 'flex' | 'tabs';
  /** Periodo padrao: dia, semana, mes, trimestre, ano */
  default_period?: 'dia' | 'semana' | 'mes' | 'trimestre' | 'ano';
  /** Filtros padrao */
  default_filters?: Record<string, unknown>;
  /** Widgets IDs */
  widget_ids?: string[];
  /** Publico */
  is_public?: boolean;
  /** Favorito */
  is_favorite?: boolean;
  /** Condominio ID */
  condominio_id: string;
}

/**
 * Widget de dashboard HR Analytics
 * Usado para criar widgets de metricas de RH
 */
export interface DashboardWidgetRequest {
  /** Dashboard ID */
  dashboard_id: string;
  /** Titulo do widget */
  title: string;
  /** Tipo: kpi, chart, table, metric, alert */
  type: 'kpi' | 'chart' | 'table' | 'metric' | 'alert';
  /** Subtipo do grafico: line, bar, pie, area, donut */
  chart_type?: 'line' | 'bar' | 'pie' | 'area' | 'donut';
  /** Metrica ou KPI ID */
  metric_id?: string;
  /** Query de dados */
  data_query?: string;
  /** Posicao X no grid */
  position_x?: number;
  /** Posicao Y no grid */
  position_y?: number;
  /** Largura */
  width?: number;
  /** Altura */
  height?: number;
  /** Configuracoes visuais */
  visual_config?: Record<string, unknown>;
  /** Intervalo de atualizacao em segundos */
  refresh_interval?: number;
}

/**
 * Definicao de KPI HR Analytics
 * Usado para definir indicadores de desempenho de RH
 */
export interface KPIDefinitionRequest {
  /** Nome do KPI */
  name: string;
  /** Descricao */
  description?: string;
  /** Categoria: turnover, absenteismo, produtividade, custo, satisfacao */
  category: 'turnover' | 'absenteismo' | 'produtividade' | 'custo' | 'satisfacao';
  /** Formula de calculo */
  formula: string;
  /** Unidade: percentual, valor, quantidade, dias */
  unit: 'percentual' | 'valor' | 'quantidade' | 'dias';
  /** Meta */
  target?: number;
  /** Limite minimo aceitavel */
  min_threshold?: number;
  /** Limite maximo aceitavel */
  max_threshold?: number;
  /** Polaridade: higher_is_better, lower_is_better */
  polarity: 'higher_is_better' | 'lower_is_better';
  /** Frequencia de calculo: diario, semanal, mensal */
  frequency: 'diario' | 'semanal' | 'mensal';
  /** Ativo */
  is_active?: boolean;
  /** Condominio ID */
  condominio_id: string;
}

/**
 * Relatorio agendado HR Analytics
 * Usado para agendar relatorios periodicos de RH
 */
export interface ScheduledReportRequest {
  /** Nome do relatorio */
  name: string;
  /** Descricao */
  description?: string;
  /** Tipo: dashboard_snapshot, kpi_summary, detailed_analysis */
  report_type: 'dashboard_snapshot' | 'kpi_summary' | 'detailed_analysis';
  /** Dashboard ID (se snapshot) */
  dashboard_id?: string;
  /** KPIs incluidos */
  kpi_ids?: string[];
  /** Formato: pdf, excel, csv */
  format: 'pdf' | 'excel' | 'csv';
  /** Frequencia: diario, semanal, mensal */
  frequency: 'diario' | 'semanal' | 'mensal';
  /** Dia da semana (para semanal) */
  day_of_week?: number;
  /** Dia do mes (para mensal) */
  day_of_month?: number;
  /** Hora de execucao */
  execution_time?: string;
  /** Destinatarios (emails) */
  recipients: string[];
  /** Ativo */
  is_active?: boolean;
  /** Condominio ID */
  condominio_id: string;
}
