/**
 * Service Layer - Data Erasure (LGPD Art. 18)
 *
 * Direito ao esquecimento:
 * - Solicitação de exclusão de dados
 * - Consulta de status de solicitações
 *
 * @module security-lgpd/services/erasureService
 */

import axios from 'axios';
import type {
  ErasureRequestSchema,
  StandardResponse,
} from '@/types/generated/security-lgpd/conectaPROLGPDSecurityAPI.schemas';

const BASE_PATH = '/lgpd/erasure';

export type ErasureScope = 'all' | 'personal' | 'transactional';
export type ErasureStatus = 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled';

export interface ErasureRequest {
  request_id: string;
  titular_id: string;
  titular_email: string;
  reason: string;
  scope: ErasureScope;
  status: ErasureStatus;
  requested_at: string;
  completed_at?: string;
  progress?: number;
  affected_systems?: string[];
}

/**
 * Solicita exclusão de dados (Art. 18 LGPD)
 */
export const requestDataErasure = async (
  titularId: string,
  titularEmail: string,
  reason: string,
  scope: ErasureScope = 'all'
): Promise<ErasureRequest> => {
  const payload: ErasureRequestSchema = {
    titular_id: titularId,
    titular_email: titularEmail,
    reason,
    scope,
  };

  const response = await axios.post<StandardResponse>(`${BASE_PATH}/request`, payload);

  if (!response.data.success) {
    throw new Error(response.data.message || 'Erro ao solicitar exclusão de dados');
  }

  return response.data.data as unknown as ErasureRequest;
};

/**
 * Consulta status de solicitação de exclusão
 */
export const getErasureStatus = async (requestId: string): Promise<ErasureRequest> => {
  const response = await axios.get<StandardResponse>(`${BASE_PATH}/${requestId}/status`);

  if (!response.data.success) {
    throw new Error(response.data.message || 'Erro ao consultar status de exclusão');
  }

  return response.data.data as unknown as ErasureRequest;
};

/**
 * Verifica se solicitação foi concluída
 */
export const isErasureCompleted = (request: ErasureRequest): boolean => {
  return request.status === 'completed';
};

/**
 * Calcula dias até o prazo legal (15 dias úteis)
 */
export const getDaysUntilDeadline = (request: ErasureRequest): number => {
  const requestDate = new Date(request.requested_at);
  const deadlineDate = new Date(requestDate);
  deadlineDate.setDate(deadlineDate.getDate() + 15); // 15 dias úteis

  const today = new Date();
  const diffTime = deadlineDate.getTime() - today.getTime();
  const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

  return diffDays;
};

const erasureServiceApi = {
  requestDataErasure,
  getErasureStatus,
  isErasureCompleted,
  getDaysUntilDeadline,
};

export default erasureServiceApi;
