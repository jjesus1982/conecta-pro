/**
 * Service: Banking / Open Banking
 * Integrações com bancos (BB, Itaú, Bradesco)
 *
 * Nota: Este módulo atualmente opera via service layer Python direto.
 * Futuros endpoints REST serão adicionados aqui quando disponíveis.
 */

// Placeholder para futuras integrações REST de Open Banking
export const bankingService = {
  /**
   * Placeholder - Saldo de conta bancária
   * TODO: Implementar quando endpoint REST estiver disponível
   */
  getAccountBalance: async (accountId: string) => {
    throw new Error('Banking REST API não implementada ainda. Use service layer Python.');
  },

  /**
   * Placeholder - Extrato bancário
   * TODO: Implementar quando endpoint REST estiver disponível
   */
  getBankStatement: async (accountId: string, startDate: string, endDate: string) => {
    throw new Error('Banking REST API não implementada ainda. Use service layer Python.');
  },

  /**
   * Placeholder - Pagamento PIX
   * TODO: Implementar quando endpoint REST estiver disponível
   */
  createPixPayment: async (paymentData: any) => {
    throw new Error('Banking REST API não implementada ainda. Use service layer Python.');
  },
};
