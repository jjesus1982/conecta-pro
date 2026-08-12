/**
 * Service Execution Service - Gestão de Execuções de Serviço
 *
 * Features:
 * - Listar execuções
 * - Criar execução
 * - Atualizar execução
 * - Check-in/Check-out
 * - Checklist
 * - Materiais e custos
 * - Assinaturas
 */

import { apiClient } from '@/lib/api/client';
import type {
  ServiceExecutionCreate,
  ServiceExecutionResponse,
  ModulesServicesModelsServiceExecutionExecutionStatus as ExecutionStatus
} from '@/types/generated/services/conectaPROServicesAPI.schemas';

// ServiceExecutionUpdate não está no schema, usar Partial de ServiceExecutionCreate
export type ServiceExecutionUpdate = Partial<ServiceExecutionCreate>;

export interface ListServiceExecutionParams {
  order_id?: string;
  technician_id?: string;
  status?: ExecutionStatus;
  skip?: number;
  limit?: number;
}

export const serviceExecutionService = {
  /**
   * Lista execuções de serviço
   */
  async list(params?: ListServiceExecutionParams): Promise<ServiceExecutionResponse[]> {
    const response = await apiClient.get<ServiceExecutionResponse[]>(
      '/api/v1/services/executions',
      { params }
    );
    return response.data;
  },

  /**
   * Obtém detalhes de uma execução específica
   */
  async getById(id: string): Promise<ServiceExecutionResponse> {
    const response = await apiClient.get<ServiceExecutionResponse>(
      `/api/v1/services/executions/${id}`
    );
    return response.data;
  },

  /**
   * Lista execuções de uma ordem específica
   */
  async listByOrder(orderId: string): Promise<ServiceExecutionResponse[]> {
    const response = await apiClient.get<ServiceExecutionResponse[]>(
      `/api/v1/services/orders/${orderId}/executions`
    );
    return response.data;
  },

  /**
   * Cria nova execução de serviço
   */
  async create(data: ServiceExecutionCreate): Promise<ServiceExecutionResponse> {
    const response = await apiClient.post<ServiceExecutionResponse>(
      '/api/v1/services/executions',
      data
    );
    return response.data;
  },

  /**
   * Atualiza uma execução existente
   */
  async update(
    id: string,
    data: ServiceExecutionUpdate
  ): Promise<ServiceExecutionResponse> {
    const response = await apiClient.patch<ServiceExecutionResponse>(
      `/api/v1/services/executions/${id}`,
      data
    );
    return response.data;
  },

  /**
   * Check-in - Inicia execução
   */
  async checkIn(id: string): Promise<ServiceExecutionResponse> {
    const response = await apiClient.post<ServiceExecutionResponse>(
      `/api/v1/services/executions/${id}/check-in`
    );
    return response.data;
  },

  /**
   * Check-out - Finaliza execução
   */
  async checkOut(id: string): Promise<ServiceExecutionResponse> {
    const response = await apiClient.post<ServiceExecutionResponse>(
      `/api/v1/services/executions/${id}/check-out`
    );
    return response.data;
  },

  /**
   * Pausa execução
   */
  async pause(id: string, reason?: string): Promise<ServiceExecutionResponse> {
    const response = await apiClient.post<ServiceExecutionResponse>(
      `/api/v1/services/executions/${id}/pause`,
      { reason }
    );
    return response.data;
  },

  /**
   * Retoma execução pausada
   */
  async resume(id: string): Promise<ServiceExecutionResponse> {
    const response = await apiClient.post<ServiceExecutionResponse>(
      `/api/v1/services/executions/${id}/resume`
    );
    return response.data;
  },

  /**
   * Atualiza checklist da execução
   */
  async updateChecklist(
    id: string,
    checklist: Array<{
      item: string;
      checked: boolean;
      notes?: string;
    }>
  ): Promise<ServiceExecutionResponse> {
    const response = await apiClient.post<ServiceExecutionResponse>(
      `/api/v1/services/executions/${id}/checklist`,
      { checklist }
    );
    return response.data;
  },

  /**
   * Adiciona material usado na execução
   */
  async addMaterial(
    id: string,
    data: {
      name: string;
      quantity: number;
      unit: string;
      cost?: number;
    }
  ): Promise<ServiceExecutionResponse> {
    const response = await apiClient.post<ServiceExecutionResponse>(
      `/api/v1/services/executions/${id}/materials`,
      data
    );
    return response.data;
  },

  /**
   * Adiciona foto/evidência à execução
   */
  async addPhoto(
    id: string,
    data: {
      file: File;
      description?: string;
      category?: string;
    }
  ): Promise<ServiceExecutionResponse> {
    const formData = new FormData();
    formData.append('file', data.file);
    if (data.description) formData.append('description', data.description);
    if (data.category) formData.append('category', data.category);

    const response = await apiClient.post<ServiceExecutionResponse>(
      `/api/v1/services/executions/${id}/photos`,
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data'
        }
      }
    );
    return response.data;
  },

  /**
   * Adiciona assinatura à execução
   */
  async addSignature(
    id: string,
    data: {
      signer_name: string;
      signer_role: string;
      signature_data: string;
    }
  ): Promise<ServiceExecutionResponse> {
    const response = await apiClient.post<ServiceExecutionResponse>(
      `/api/v1/services/executions/${id}/signatures`,
      data
    );
    return response.data;
  }
};
