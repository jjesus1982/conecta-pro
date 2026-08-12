/**
 * Services - Integrations Module
 * Módulo de Integrações, Webhooks, Conectores, Banking, WhatsApp, Email
 */

// Core Integrations
export { apiEndpointService } from './apiEndpointService';
export { apiKeyService } from './apiKeyService';
export { webhookService } from './webhookService';
export { integrationLogService } from './integrationLogService';
export { syncQueueService } from './syncQueueService';

// Connectors
export { connectorService } from './connectorService';
export { integrationAccountService } from './integrationAccountService';
export { syncRunService } from './syncRunService';
export { solidesService } from './solidesService';

// Submodules (Placeholder - não implementados via REST ainda)
export { bankingService } from './bankingService';
export { whatsappService } from './whatsappService';
export { emailService } from './emailService';
