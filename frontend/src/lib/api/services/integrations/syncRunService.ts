/**
 * Service: Sync Run Management
 * Gerenciamento de execuções de sincronização
 */

import { startSyncApiV1IntegrationsIntegrationsConnectorsSyncRunPost, listSyncRunsApiV1IntegrationsIntegrationsConnectorsSyncRunsGet, getSyncRunApiV1IntegrationsIntegrationsConnectorsSyncRunsRunIdGet } from '@/types/generated/integrations/conectores-externos/conectores-externos';

export const syncRunService = {
  /**
   * Iniciar sincronização
   */
  startSync: startSyncApiV1IntegrationsIntegrationsConnectorsSyncRunPost,

  /**
   * Listar execuções de sincronização
   */
  listSyncRuns: listSyncRunsApiV1IntegrationsIntegrationsConnectorsSyncRunsGet,

  /**
   * Obter execução por ID
   */
  getSyncRun: getSyncRunApiV1IntegrationsIntegrationsConnectorsSyncRunsRunIdGet,
};
