/**
 * Service Report Service - Gestão de Relatórios de Serviço
 *
 * Features:
 * - Listar relatórios
 * - Criar relatório
 * - Atualizar relatório
 * - Workflow de aprovação
 * - Geração de PDF
 * - Envio ao cliente
 */

import { apiClient } from '@/lib/api/client';
import type {
  ServiceReportCreate,
  ServiceReportUpdate,
  ServiceReportResponse,
  ModulesServicesModelsServiceReportReportType as ReportType
} from '@/types/generated/services/conectaPROServicesAPI.schemas';

export interface ListServiceReportParams {
  order_id?: string;
  report_type?: ReportType;
  author_id?: string;
  is_draft?: boolean;
  is_approved?: boolean;
  is_sent?: boolean;
  skip?: number;
  limit?: number;
}

export const serviceReportService = {
  /**
   * Lista relatórios de serviço
   */
  async list(params?: ListServiceReportParams): Promise<ServiceReportResponse[]> {
    const response = await apiClient.get<ServiceReportResponse[]>(
      '/api/v1/services/reports',
      { params }
    );
    return response.data;
  },

  /**
   * Obtém detalhes de um relatório específico
   */
  async getById(id: string): Promise<ServiceReportResponse> {
    const response = await apiClient.get<ServiceReportResponse>(
      `/api/v1/services/reports/${id}`
    );
    return response.data;
  },

  /**
   * Lista relatórios de uma ordem específica
   */
  async listByOrder(orderId: string): Promise<ServiceReportResponse[]> {
    const response = await apiClient.get<ServiceReportResponse[]>(
      `/api/v1/services/orders/${orderId}/reports`
    );
    return response.data;
  },

  /**
   * Cria novo relatório
   */
  async create(data: ServiceReportCreate): Promise<ServiceReportResponse> {
    const response = await apiClient.post<ServiceReportResponse>(
      '/api/v1/services/reports',
      data
    );
    return response.data;
  },

  /**
   * Atualiza um relatório existente
   */
  async update(
    id: string,
    data: ServiceReportUpdate
  ): Promise<ServiceReportResponse> {
    const response = await apiClient.patch<ServiceReportResponse>(
      `/api/v1/services/reports/${id}`,
      data
    );
    return response.data;
  },

  /**
   * Gera relatório automaticamente a partir da execução
   */
  async generate(orderId: string): Promise<ServiceReportResponse> {
    const response = await apiClient.post<ServiceReportResponse>(
      `/api/v1/services/orders/${orderId}/generate-report`
    );
    return response.data;
  },

  /**
   * Finaliza edição do relatório (remove modo draft)
   */
  async finalize(id: string): Promise<ServiceReportResponse> {
    const response = await apiClient.post<ServiceReportResponse>(
      `/api/v1/services/reports/${id}/finalize`
    );
    return response.data;
  },

  /**
   * Submete relatório para revisão
   */
  async submitForReview(id: string): Promise<ServiceReportResponse> {
    const response = await apiClient.post<ServiceReportResponse>(
      `/api/v1/services/reports/${id}/submit-review`
    );
    return response.data;
  },

  /**
   * Aprova relatório
   */
  async approve(id: string): Promise<ServiceReportResponse> {
    const response = await apiClient.post<ServiceReportResponse>(
      `/api/v1/services/reports/${id}/approve`
    );
    return response.data;
  },

  /**
   * Rejeita relatório
   */
  async reject(id: string, reason: string): Promise<ServiceReportResponse> {
    const response = await apiClient.post<ServiceReportResponse>(
      `/api/v1/services/reports/${id}/reject`,
      { reason }
    );
    return response.data;
  },

  /**
   * Gera PDF do relatório
   */
  async generatePDF(id: string): Promise<{ url: string }> {
    const response = await apiClient.post<{ url: string }>(
      `/api/v1/services/reports/${id}/generate-pdf`
    );
    return response.data;
  },

  /**
   * Envia relatório ao cliente
   */
  async send(
    id: string,
    data: {
      recipients: string[];
      subject?: string;
      message?: string;
    }
  ): Promise<ServiceReportResponse> {
    const response = await apiClient.post<ServiceReportResponse>(
      `/api/v1/services/reports/${id}/send`,
      data
    );
    return response.data;
  },

  /**
   * Download do PDF do relatório
   */
  async downloadPDF(id: string): Promise<Blob> {
    const response = await apiClient.get<Blob>(
      `/api/v1/services/reports/${id}/pdf`,
      { responseType: 'blob' }
    );
    return response.data;
  }
};
