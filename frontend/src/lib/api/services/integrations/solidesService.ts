/**
 * Service: Solides Integration
 * Integração com Sólides DP
 */

import { listSolidesEmployeesApiV1IntegrationsSolidesEmployeesGet, getIntegrationStatusApiV1IntegrationsSolidesStatusGet, configureIntegrationApiV1IntegrationsSolidesConfigPost, getConfigApiV1IntegrationsSolidesConfigGet, disableIntegrationApiV1IntegrationsSolidesConfigDelete, triggerSyncApiV1IntegrationsSolidesSyncTriggerPost, getSyncLogsApiV1IntegrationsSolidesLogsGet, getSyncLogDetailApiV1IntegrationsSolidesLogsLogIdGet, listConflictsApiV1IntegrationsSolidesConflictsGet, resolveConflictApiV1IntegrationsSolidesConflictsConflictIdResolvePost, ignoreConflictApiV1IntegrationsSolidesConflictsConflictIdIgnorePost, receiveWebhookApiV1IntegrationsSolidesWebhookPost } from '@/types/generated/integrations/solides-integration/solides-integration';

export const solidesService = {
  /**
   * Listar colaboradores sincronizados do Sólides
   */
  listEmployees: listSolidesEmployeesApiV1IntegrationsSolidesEmployeesGet,

  /**
   * Obter status da integração
   */
  getIntegrationStatus: getIntegrationStatusApiV1IntegrationsSolidesStatusGet,

  /**
   * Configurar integração
   */
  configureIntegration: configureIntegrationApiV1IntegrationsSolidesConfigPost,

  /**
   * Obter configuração da integração
   */
  getIntegrationConfig: getConfigApiV1IntegrationsSolidesConfigGet,

  /**
   * Desabilitar integração
   */
  disableIntegration: disableIntegrationApiV1IntegrationsSolidesConfigDelete,

  /**
   * Disparar sincronização manual
   */
  triggerSync: triggerSyncApiV1IntegrationsSolidesSyncTriggerPost,

  /**
   * Listar logs de sincronização
   */
  getSyncLogs: getSyncLogsApiV1IntegrationsSolidesLogsGet,

  /**
   * Obter detalhes de um log de sincronização
   */
  getSyncLogDetail: getSyncLogDetailApiV1IntegrationsSolidesLogsLogIdGet,

  /**
   * Listar conflitos de sincronização
   */
  listConflicts: listConflictsApiV1IntegrationsSolidesConflictsGet,

  /**
   * Resolver conflito
   */
  resolveConflict: resolveConflictApiV1IntegrationsSolidesConflictsConflictIdResolvePost,

  /**
   * Ignorar conflito
   */
  ignoreConflict: ignoreConflictApiV1IntegrationsSolidesConflictsConflictIdIgnorePost,

  /**
   * Receber webhook do Sólides (para uso interno)
   */
  receiveWebhook: receiveWebhookApiV1IntegrationsSolidesWebhookPost,
};
