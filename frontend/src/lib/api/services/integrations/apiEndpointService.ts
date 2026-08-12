/**
 * Service: API Endpoint Management
 * Gerenciamento de endpoints de API
 */

import { getDashboardApiV1IntegrationsDashboardGet, healthCheckApiV1IntegrationsHealthGet, createEndpointApiV1IntegrationsEndpointsPost, listEndpointsApiV1IntegrationsEndpointsGet, getEndpointApiV1IntegrationsEndpointsEndpointIdGet, updateEndpointApiV1IntegrationsEndpointsEndpointIdPatch, deleteEndpointApiV1IntegrationsEndpointsEndpointIdDelete, deprecateEndpointApiV1IntegrationsEndpointsEndpointIdDeprecatePost } from '@/types/generated/integrations/integrações/integrações';

export const apiEndpointService = {
  /**
   * Dashboard de integrações
   */
  getDashboard: getDashboardApiV1IntegrationsDashboardGet,

  /**
   * Health check
   */
  healthCheck: healthCheckApiV1IntegrationsHealthGet,

  /**
   * Criar endpoint
   */
  createEndpoint: createEndpointApiV1IntegrationsEndpointsPost,

  /**
   * Listar endpoints
   */
  listEndpoints: listEndpointsApiV1IntegrationsEndpointsGet,

  /**
   * Obter endpoint por ID
   */
  getEndpoint: getEndpointApiV1IntegrationsEndpointsEndpointIdGet,

  /**
   * Atualizar endpoint
   */
  updateEndpoint: updateEndpointApiV1IntegrationsEndpointsEndpointIdPatch,

  /**
   * Deletar endpoint
   */
  deleteEndpoint: deleteEndpointApiV1IntegrationsEndpointsEndpointIdDelete,

  /**
   * Depreciar endpoint
   */
  deprecateEndpoint: deprecateEndpointApiV1IntegrationsEndpointsEndpointIdDeprecatePost,
};
