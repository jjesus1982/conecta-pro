/**
 * Service: Connector Management
 * Gerenciamento de conectores externos
 */

import { listConnectorsApiV1IntegrationsIntegrationsConnectorsGet, getConnectorApiV1IntegrationsIntegrationsConnectorsConnectorNameGet, healthCheckAccountApiV1IntegrationsIntegrationsConnectorsAccountsAccountIdHealthGet } from '@/types/generated/integrations/conectores-externos/conectores-externos';

export const connectorService = {
  /**
   * Listar conectores disponíveis
   */
  listConnectors: listConnectorsApiV1IntegrationsIntegrationsConnectorsGet,

  /**
   * Obter detalhes de um conector
   */
  getConnector: getConnectorApiV1IntegrationsIntegrationsConnectorsConnectorNameGet,

  /**
   * Health check de account (não há health check direto de connector)
   */
  healthCheckAccount: healthCheckAccountApiV1IntegrationsIntegrationsConnectorsAccountsAccountIdHealthGet,
};
