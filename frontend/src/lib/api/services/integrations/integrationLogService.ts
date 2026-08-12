/**
 * Service: Integration Logs
 * Logs de integrações
 */

import { listLogsApiV1IntegrationsLogsGet, getLogApiV1IntegrationsLogsLogIdGet } from '@/types/generated/integrations/integrações/integrações';

export const integrationLogService = {
  /**
   * Listar logs
   */
  listLogs: listLogsApiV1IntegrationsLogsGet,

  /**
   * Obter log por ID
   */
  getLog: getLogApiV1IntegrationsLogsLogIdGet,
};
