/**
 * Service: Sync Queue Management
 * Gerenciamento de fila de sincronização
 */

import { queueSyncApiV1IntegrationsSyncPost, queueSyncBatchApiV1IntegrationsSyncBatchPost, listSyncItemsApiV1IntegrationsSyncGet, getSyncItemApiV1IntegrationsSyncItemIdGet, cancelSyncItemApiV1IntegrationsSyncItemIdCancelPost, getSyncStatsApiV1IntegrationsSyncStatsGet } from '@/types/generated/integrations/integrações/integrações';

export const syncQueueService = {
  /**
   * Criar item na fila
   */
  createSyncItem: queueSyncApiV1IntegrationsSyncPost,

  /**
   * Criar múltiplos itens na fila
   */
  createSyncBatch: queueSyncBatchApiV1IntegrationsSyncBatchPost,

  /**
   * Listar itens da fila
   */
  listSyncItems: listSyncItemsApiV1IntegrationsSyncGet,

  /**
   * Obter item por ID
   */
  getSyncItem: getSyncItemApiV1IntegrationsSyncItemIdGet,

  /**
   * Cancelar item
   */
  cancelSyncItem: cancelSyncItemApiV1IntegrationsSyncItemIdCancelPost,

  /**
   * Obter estatísticas da fila
   */
  getSyncStats: getSyncStatsApiV1IntegrationsSyncStatsGet,
};
