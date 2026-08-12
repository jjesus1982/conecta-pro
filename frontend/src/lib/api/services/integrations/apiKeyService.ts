/**
 * Service: API Key Management
 * Gerenciamento de API Keys
 */

import { createApiKeyApiV1IntegrationsApiKeysPost, listApiKeysApiV1IntegrationsApiKeysGet, getApiKeyApiV1IntegrationsApiKeysKeyIdGet, updateApiKeyApiV1IntegrationsApiKeysKeyIdPatch, revokeApiKeyApiV1IntegrationsApiKeysKeyIdRevokePost, verifyApiKeyApiV1IntegrationsApiKeysVerifyPost } from '@/types/generated/integrations/integrações/integrações';

export const apiKeyService = {
  /**
   * Criar API Key
   */
  createApiKey: createApiKeyApiV1IntegrationsApiKeysPost,

  /**
   * Listar API Keys
   */
  listApiKeys: listApiKeysApiV1IntegrationsApiKeysGet,

  /**
   * Obter API Key por ID
   */
  getApiKey: getApiKeyApiV1IntegrationsApiKeysKeyIdGet,

  /**
   * Atualizar API Key
   */
  updateApiKey: updateApiKeyApiV1IntegrationsApiKeysKeyIdPatch,

  /**
   * Revogar API Key
   */
  revokeApiKey: revokeApiKeyApiV1IntegrationsApiKeysKeyIdRevokePost,

  /**
   * Verificar API Key
   */
  verifyApiKey: verifyApiKeyApiV1IntegrationsApiKeysVerifyPost,
};
