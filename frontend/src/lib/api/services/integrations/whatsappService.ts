/**
 * Service: WhatsApp Integration
 * Automações e chatbot WhatsApp
 *
 * Nota: Este módulo atualmente opera via service layer Python direto.
 * Futuros endpoints REST serão adicionados aqui quando disponíveis.
 */

// Placeholder para futuras integrações REST de WhatsApp
export const whatsappService = {
  /**
   * Placeholder - Enviar mensagem WhatsApp
   * TODO: Implementar quando endpoint REST estiver disponível
   */
  sendMessage: async (to: string, message: string) => {
    throw new Error('WhatsApp REST API não implementada ainda. Use service layer Python.');
  },

  /**
   * Placeholder - Listar templates
   * TODO: Implementar quando endpoint REST estiver disponível
   */
  listTemplates: async () => {
    throw new Error('WhatsApp REST API não implementada ainda. Use service layer Python.');
  },

  /**
   * Placeholder - Obter fila de mensagens
   * TODO: Implementar quando endpoint REST estiver disponível
   */
  getMessageQueue: async () => {
    throw new Error('WhatsApp REST API não implementada ainda. Use service layer Python.');
  },

  /**
   * Placeholder - Chatbot
   * TODO: Implementar quando endpoint REST estiver disponível
   */
  processChatbotMessage: async (message: string) => {
    throw new Error('WhatsApp REST API não implementada ainda. Use service layer Python.');
  },
};
