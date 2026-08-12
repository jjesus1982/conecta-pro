/**
 * SLA Service - Gestão de SLAs (Service Level Agreements)
 *
 * Features:
 * - Listar SLAs
 * - Criar SLA
 * - Atualizar SLA
 * - Tracking de compliance
 * - Métricas e estatísticas
 */

import { apiClient } from '@/lib/api/client';
import type {
  SLAConfigCreate,
  SLAConfigUpdate,
  SLAConfigResponse,
  SLAMetricType
} from '@/types/generated/services/conectaPROServicesAPI.schemas';

export interface ListSLAParams {
  service_id?: string;
  client_id?: string;
  contract_id?: string;
  metric_type?: SLAMetricType;
  is_active?: boolean;
  is_default?: boolean;
  skip?: number;
  limit?: number;
}

export interface SLAComplianceStats {
  total_orders: number;
  orders_within_sla: number;
  orders_breached: number;
  compliance_percent: number;
  avg_response_time_minutes: number;
  avg_resolution_time_minutes: number;
  breach_rate: number;
}

// As rotas reais do backend sao /api/v1/services/sla-configs (nao /sla). Este cliente
// pedia /sla nas 9 chamadas — 9 de 9 devolviam 404, e nenhuma tela usava, entao ninguem viu.
// Removidos daqui: delete (o backend nao tem DELETE; a baixa e POST .../deactivate),
// getDefaultForService, calculatePenalty e getBreachHistory — o backend NAO tem essas
// rotas. Metodo de cliente que sempre 404 e armadilha para quem for montar a tela.
export const slaService = {
  /**
   * Lista SLAs configurados
   */
  async list(params?: ListSLAParams): Promise<SLAConfigResponse[]> {
    const response = await apiClient.get<SLAConfigResponse[]>(
      '/api/v1/services/sla-configs',
      { params }
    );
    return response.data;
  },

  /**
   * Obtém detalhes de um SLA específico
   */
  async getById(id: string): Promise<SLAConfigResponse> {
    const response = await apiClient.get<SLAConfigResponse>(
      `/api/v1/services/sla-configs/${id}`
    );
    return response.data;
  },

  /**
   * Cria novo SLA
   */
  async create(data: SLAConfigCreate): Promise<SLAConfigResponse> {
    const response = await apiClient.post<SLAConfigResponse>(
      '/api/v1/services/sla-configs',
      data
    );
    return response.data;
  },

  /**
   * Atualiza um SLA existente
   */
  async update(
    id: string,
    data: SLAConfigUpdate
  ): Promise<SLAConfigResponse> {
    const response = await apiClient.put<SLAConfigResponse>(
      `/api/v1/services/sla-configs/${id}`,
      data
    );
    return response.data;
  },


  /**
   * Ativa um SLA
   */
  async activate(id: string): Promise<SLAConfigResponse> {
    const response = await apiClient.post<SLAConfigResponse>(
      `/api/v1/services/sla-configs/${id}/activate`
    );
    return response.data;
  },

  /**
   * Desativa um SLA
   */
  async deactivate(id: string): Promise<SLAConfigResponse> {
    const response = await apiClient.post<SLAConfigResponse>(
      `/api/v1/services/sla-configs/${id}/deactivate`
    );
    return response.data;
  },

  /**
   * Obtém estatísticas de compliance de um SLA
   */
  async getCompliance(id: string): Promise<SLAComplianceStats> {
    const response = await apiClient.get<SLAComplianceStats>(
      `/api/v1/services/sla-configs/${id}/compliance-report`
    );
    return response.data;
  },


  /**
   * Define SLA como padrão
   */
  async setAsDefault(id: string): Promise<SLAConfigResponse> {
    const response = await apiClient.post<SLAConfigResponse>(
      `/api/v1/services/sla-configs/${id}/set-default`
    );
    return response.data;
  },


};
