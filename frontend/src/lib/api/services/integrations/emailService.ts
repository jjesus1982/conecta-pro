/**
 * Service: Email Integration
 * Automações e campanhas de email
 *
 * Nota: Este módulo atualmente opera via service layer Python direto.
 * Futuros endpoints REST serão adicionados aqui quando disponíveis.
 */

// Placeholder para futuras integrações REST de Email
export const emailService = {
  /**
   * Placeholder - Enviar email
   * TODO: Implementar quando endpoint REST estiver disponível
   */
  sendEmail: async (to: string, subject: string, body: string) => {
    throw new Error('Email REST API não implementada ainda. Use service layer Python.');
  },

  /**
   * Placeholder - Listar templates de email
   * TODO: Implementar quando endpoint REST estiver disponível
   */
  listTemplates: async () => {
    throw new Error('Email REST API não implementada ainda. Use service layer Python.');
  },

  /**
   * Placeholder - Criar campanha de email
   * TODO: Implementar quando endpoint REST estiver disponível
   */
  createCampaign: async (campaignData: any) => {
    throw new Error('Email REST API não implementada ainda. Use service layer Python.');
  },

  /**
   * Placeholder - Obter fila de emails
   * TODO: Implementar quando endpoint REST estiver disponível
   */
  getEmailQueue: async () => {
    throw new Error('Email REST API não implementada ainda. Use service layer Python.');
  },
};
