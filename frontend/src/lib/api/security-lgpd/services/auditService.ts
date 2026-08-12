/**
 * Service Layer - Audit Trail (LGPD Art. 46)
 *
 * Trilha de auditoria com hash chain para garantir integridade:
 * - Registro de eventos
 * - Consulta de logs com filtros
 * - Listagem de ações e tipos de recurso
 *
 * @module security-lgpd/services/auditService
 */

import axios from 'axios';
import type {
  AuditLogRequest,
  StandardResponse,
} from '@/types/generated/security-lgpd/conectaPROLGPDSecurityAPI.schemas';

const BASE_PATH = '/lgpd/audit';

export type SeverityLevel = 'low' | 'medium' | 'high' | 'critical';

export interface AuditLog {
  log_id: string;
  action: string;
  resource_type: string;
  resource_id: string;
  user_id: string;
  details?: Record<string, any>;
  severity: SeverityLevel;
  timestamp: string;
  hash: string;
  previous_hash?: string;
}

export interface AuditLogsResponse {
  logs: AuditLog[];
  total: number;
  limit: number;
  offset: number;
}

export interface AuditFilters {
  resource_type?: string;
  user_id?: string;
  start_date?: string;
  end_date?: string;
  limit?: number;
  offset?: number;
}

/**
 * Registra evento de auditoria
 */
export const logAuditEvent = async (
  action: string,
  resourceType: string,
  resourceId: string,
  userId: string,
  details?: Record<string, any>,
  severity: SeverityLevel = 'medium'
): Promise<AuditLog> => {
  const payload: AuditLogRequest = {
    action,
    resource_type: resourceType,
    resource_id: resourceId,
    user_id: userId,
    details,
    severity,
  };

  const response = await axios.post<StandardResponse>(`${BASE_PATH}/log`, payload);

  if (!response.data.success) {
    throw new Error(response.data.message || 'Erro ao registrar evento de auditoria');
  }

  return response.data.data as unknown as AuditLog;
};

/**
 * Lista eventos de auditoria com filtros
 */
export const listAuditLogs = async (
  filters?: AuditFilters
): Promise<AuditLogsResponse> => {
  const response = await axios.get<StandardResponse>(`${BASE_PATH}/logs`, {
    params: filters,
  });

  if (!response.data.success) {
    throw new Error(response.data.message || 'Erro ao listar logs de auditoria');
  }

  return response.data.data as unknown as unknown as AuditLogsResponse;
};

/**
 * Lista ações de auditoria disponíveis
 */
export const listActions = async (): Promise<string[]> => {
  const response = await axios.get<StandardResponse>(`${BASE_PATH}/actions/list`);

  if (!response.data.success) {
    throw new Error(response.data.message || 'Erro ao listar ações');
  }

  return (response.data.data as unknown as { actions: string[] }).actions;
};

/**
 * Lista tipos de recurso auditados
 */
export const listResourceTypes = async (): Promise<string[]> => {
  const response = await axios.get<StandardResponse>(`${BASE_PATH}/resource-types/list`);

  if (!response.data.success) {
    throw new Error(response.data.message || 'Erro ao listar tipos de recurso');
  }

  return (response.data.data as unknown as { resource_types: string[] }).resource_types;
};

/**
 * Filtra logs por usuário
 */
export const getLogsByUser = async (userId: string): Promise<AuditLog[]> => {
  const response = await listAuditLogs({ user_id: userId });
  return response.logs;
};

/**
 * Filtra logs por tipo de recurso
 */
export const getLogsByResourceType = async (resourceType: string): Promise<AuditLog[]> => {
  const response = await listAuditLogs({ resource_type: resourceType });
  return response.logs;
};

/**
 * Filtra logs por período
 */
export const getLogsByDateRange = async (
  startDate: string,
  endDate: string
): Promise<AuditLog[]> => {
  const response = await listAuditLogs({ start_date: startDate, end_date: endDate });
  return response.logs;
};

/**
 * Verifica integridade da hash chain
 */
export const verifyHashChain = (logs: AuditLog[]): boolean => {
  for (let i = 1; i < logs.length; i++) {
    if (logs[i]!.previous_hash !== logs[i - 1]!.hash) {
      return false;
    }
  }
  return true;
};

const auditServiceApi = {
  logAuditEvent,
  listAuditLogs,
  listActions,
  listResourceTypes,
  getLogsByUser,
  getLogsByResourceType,
  getLogsByDateRange,
  verifyHashChain,
};

export default auditServiceApi;
