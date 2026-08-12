/**
 * Service: Integration Account Management
 * Gerenciamento de contas de integração
 */

import { createAccountApiV1IntegrationsIntegrationsConnectorsAccountsPost, listAccountsApiV1IntegrationsIntegrationsConnectorsAccountsGet, getAccountApiV1IntegrationsIntegrationsConnectorsAccountsAccountIdGet, updateAccountApiV1IntegrationsIntegrationsConnectorsAccountsAccountIdPatch, deleteAccountApiV1IntegrationsIntegrationsConnectorsAccountsAccountIdDelete, healthCheckAccountApiV1IntegrationsIntegrationsConnectorsAccountsAccountIdHealthGet } from '@/types/generated/integrations/conectores-externos/conectores-externos';

export const integrationAccountService = {
  /**
   * Criar conta de integração
   */
  createAccount: createAccountApiV1IntegrationsIntegrationsConnectorsAccountsPost,

  /**
   * Listar contas de integração
   */
  listAccounts: listAccountsApiV1IntegrationsIntegrationsConnectorsAccountsGet,

  /**
   * Obter conta por ID
   */
  getAccount: getAccountApiV1IntegrationsIntegrationsConnectorsAccountsAccountIdGet,

  /**
   * Atualizar conta
   */
  updateAccount: updateAccountApiV1IntegrationsIntegrationsConnectorsAccountsAccountIdPatch,

  /**
   * Deletar conta
   */
  deleteAccount: deleteAccountApiV1IntegrationsIntegrationsConnectorsAccountsAccountIdDelete,

  /**
   * Health check da conexão (equivalente a test connection)
   */
  healthCheck: healthCheckAccountApiV1IntegrationsIntegrationsConnectorsAccountsAccountIdHealthGet,
};
