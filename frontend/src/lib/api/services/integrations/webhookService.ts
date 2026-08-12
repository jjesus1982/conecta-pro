/**
 * Service: Webhook Management
 * Gerenciamento de Webhooks
 */

import { createWebhookApiV1IntegrationsWebhooksPost, listWebhooksApiV1IntegrationsWebhooksGet, getWebhookApiV1IntegrationsWebhooksWebhookIdGet, updateWebhookApiV1IntegrationsWebhooksWebhookIdPatch, testWebhookApiV1IntegrationsWebhooksWebhookIdTestPost, getWebhookStatsApiV1IntegrationsWebhooksWebhookIdStatsGet, regenerateWebhookSecretApiV1IntegrationsWebhooksWebhookIdRegenerateSecretPost, triggerWebhookEventApiV1IntegrationsWebhooksTriggerPost } from '@/types/generated/integrations/integrações/integrações';

export const webhookService = {
  /**
   * Criar webhook
   */
  createWebhook: createWebhookApiV1IntegrationsWebhooksPost,

  /**
   * Listar webhooks
   */
  listWebhooks: listWebhooksApiV1IntegrationsWebhooksGet,

  /**
   * Obter webhook por ID
   */
  getWebhook: getWebhookApiV1IntegrationsWebhooksWebhookIdGet,

  /**
   * Atualizar webhook
   */
  updateWebhook: updateWebhookApiV1IntegrationsWebhooksWebhookIdPatch,

  /**
   * Testar webhook
   */
  testWebhook: testWebhookApiV1IntegrationsWebhooksWebhookIdTestPost,

  /**
   * Obter estatísticas do webhook
   */
  getWebhookStats: getWebhookStatsApiV1IntegrationsWebhooksWebhookIdStatsGet,

  /**
   * Regenerar secret do webhook
   */
  regenerateSecret: regenerateWebhookSecretApiV1IntegrationsWebhooksWebhookIdRegenerateSecretPost,

  /**
   * Disparar evento de webhook
   */
  triggerWebhookEvent: triggerWebhookEventApiV1IntegrationsWebhooksTriggerPost,
};
