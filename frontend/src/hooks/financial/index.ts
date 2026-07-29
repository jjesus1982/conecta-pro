/**
 * Financial Hooks Index
 *
 * Exportação centralizada de todos os hooks do módulo FINANCIAL.
 * Cobertura: 483 endpoints em 15 submódulos.
 *
 * Uso:
 *   import { usePayables, useReceivables, useSuppliers } from '@/hooks/financial';
 */

// Export Suppliers hooks
export * from './useSuppliers';

// Export consolidado de todos os módulos
export * from './useFinancial';

// Re-export para compatibilidade
export {
  // Suppliers
  useSuppliers,
  useSupplier,
  useSupplierStats,
  useCreateSupplier,
  useUpdateSupplier,
  useDeleteSupplier,
  useQualifySupplier,
  useBlockSupplier,
  useUnblockSupplier,
  // Keys
  supplierKeys,
} from './useSuppliers';

export {
  // Payables
  usePayables,
  usePayable,
  usePayableDashboard,
  useCreatePayable,
  useUpdatePayable,
  useProcessPayment,
  payableKeys,
  // Customers
  useCustomers,
  useCustomer,
  useCustomerStats,
  useCreateCustomer,
  customerKeys,
  // Receivables
  useReceivables,
  useReceivable,
  useReceivableDashboard,
  useCreateReceivable,
  useGenerateBilling,
  receivableKeys,
  // Bank Accounts
  useBankAccounts,
  useBankAccount,
  useBankAccountBalance,
  useCreateBankAccount,
  bankAccountKeys,
  // Bank Transactions
  useBankTransactions,
  useCreateBankTransaction,
  useImportOFX,
  bankTransactionKeys,
  // Cashflow
  useCashflowEntries,
  useCashflowForecast,
  useCashflowProjection,
  useCashflowDashboard,
  useCreateCashflowEntry,
  cashflowKeys,
  // Purchase
  usePurchaseRequisitions,
  usePurchaseOrders,
  usePurchaseDashboard,
  useCreatePurchaseRequisition,
  useCreatePurchaseOrder,
  purchaseKeys,
  // Inventory
  useWarehouses,
  useInventoryItems,
  useInventoryItem,
  useStockBalance,
  useInventoryDashboard,
  useCreateStockMovement,
  inventoryKeys,
  // Accounting
  useAccountingAccounts,
  useCostCenters,
  useJournalEntries,
  useTrialBalance,
  useCreateJournalEntry,
  accountingKeys,
  // Fiscal
  useNFes,
  useNFe,
  useNFSes,
  useFiscalDashboard,
  useCreateNFe,
  useAuthorizeNFe,
  fiscalKeys,
  // Financial Overview (endpoint real /financial/dashboard)
  useFinancialOverview,
  // Costing
  useCostDrivers,
  useCostActivities,
  useCostPools,
  useCostObjects,
  useCostingDashboard,
  useCostAnalyses,
  useCreateCostDriver,
  costingKeys,
} from './useFinancial';

// Default consolidado não incluído para evitar exports duplicados
// Use os named exports acima
