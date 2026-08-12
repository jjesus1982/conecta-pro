/**
 * Service Order Service - Gestão de Ordens de Serviço
 *
 * Features:
 * - Listar ordens de serviço
 * - Criar nova ordem
 * - Atualizar ordem
 * - Obter detalhes da ordem
 * - Estatísticas de ordens
 * - Workflow de aprovação
 * - Agendamento
 */

import { apiClient } from '@/lib/api/client';
import type {
  ServiceOrderCreate,
  ServiceOrderUpdate,
  ServiceOrderResponse,
  ServiceOrderListResponse,
  ServiceOrderStats,
  ModulesServicesModelsServiceOrderOrderStatus as OrderStatus,
  ModulesServicesModelsServiceOrderOrderPriority as OrderPriority
} from '@/types/generated/services/conectaPROServicesAPI.schemas';

export interface ListServiceOrderParams {
  status?: OrderStatus;
  priority?: OrderPriority;
  client_id?: string;
  condominium_id?: string;
  service_id?: string;
  technician_id?: string;
  scheduled_date_from?: string;
  scheduled_date_to?: string;
  is_overdue?: boolean;
  search?: string;
  skip?: number;
  limit?: number;
}

export const serviceOrderService = {
  /**
   * Lista ordens de serviço com filtros
   */
  async list(params?: ListServiceOrderParams): Promise<ServiceOrderListResponse[]> {
    const response = await apiClient.get<ServiceOrderListResponse[]>(
      '/api/v1/services/orders',
      { params }
    );
    return response.data;
  },

  /**
   * Obtém estatísticas de ordens de serviço
   */
  async getStats(params?: ListServiceOrderParams): Promise<ServiceOrderStats> {
    const response = await apiClient.get<ServiceOrderStats>(
      '/api/v1/services/orders/stats',
      { params }
    );
    return response.data;
  },

  /**
   * Obtém detalhes de uma ordem específica
   */
  async getById(id: string): Promise<ServiceOrderResponse> {
    const response = await apiClient.get<ServiceOrderResponse>(
      `/api/v1/services/orders/${id}`
    );
    return response.data;
  },

  /**
   * Cria nova ordem de serviço
   */
  async create(data: ServiceOrderCreate): Promise<ServiceOrderResponse> {
    const response = await apiClient.post<ServiceOrderResponse>(
      '/api/v1/services/orders',
      data
    );
    return response.data;
  },

  /**
   * Atualiza uma ordem existente
   */
  async update(
    id: string,
    data: ServiceOrderUpdate
  ): Promise<ServiceOrderResponse> {
    const response = await apiClient.patch<ServiceOrderResponse>(
      `/api/v1/services/orders/${id}`,
      data
    );
    return response.data;
  },

  /**
   * Cancela uma ordem de serviço
   */
  async cancel(id: string, reason?: string): Promise<ServiceOrderResponse> {
    const response = await apiClient.post<ServiceOrderResponse>(
      `/api/v1/services/orders/${id}/cancel`,
      { reason }
    );
    return response.data;
  },

  /**
   * Aprova uma ordem de serviço
   */
  async approve(id: string): Promise<ServiceOrderResponse> {
    const response = await apiClient.post<ServiceOrderResponse>(
      `/api/v1/services/orders/${id}/approve`
    );
    return response.data;
  },

  /**
   * Rejeita uma ordem de serviço
   */
  async reject(id: string, reason: string): Promise<ServiceOrderResponse> {
    const response = await apiClient.post<ServiceOrderResponse>(
      `/api/v1/services/orders/${id}/reject`,
      { reason }
    );
    return response.data;
  },

  /**
   * Agenda uma ordem de serviço
   */
  async schedule(
    id: string,
    data: {
      scheduled_date: string;
      scheduled_time_start: string;
      scheduled_time_end?: string;
      technician_id?: string;
    }
  ): Promise<ServiceOrderResponse> {
    const response = await apiClient.post<ServiceOrderResponse>(
      `/api/v1/services/orders/${id}/schedule`,
      data
    );
    return response.data;
  },

  /**
   * Inicia execução de uma ordem
   */
  async start(id: string): Promise<ServiceOrderResponse> {
    const response = await apiClient.post<ServiceOrderResponse>(
      `/api/v1/services/orders/${id}/start`
    );
    return response.data;
  },

  /**
   * Completa uma ordem de serviço
   */
  async complete(id: string): Promise<ServiceOrderResponse> {
    const response = await apiClient.post<ServiceOrderResponse>(
      `/api/v1/services/orders/${id}/complete`
    );
    return response.data;
  },

  /**
   * Atribui técnico a uma ordem
   */
  async assignTechnician(
    id: string,
    technicianId: string
  ): Promise<ServiceOrderResponse> {
    const response = await apiClient.post<ServiceOrderResponse>(
      `/api/v1/services/orders/${id}/assign-technician`,
      { technician_id: technicianId }
    );
    return response.data;
  },

  /**
   * Adiciona avaliação a uma ordem
   */
  async addRating(
    id: string,
    data: {
      rating: number;
      feedback?: string;
    }
  ): Promise<ServiceOrderResponse> {
    const response = await apiClient.post<ServiceOrderResponse>(
      `/api/v1/services/orders/${id}/rating`,
      data
    );
    return response.data;
  }
};
