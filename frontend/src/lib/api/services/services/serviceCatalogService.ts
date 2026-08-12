/**
 * Service Catalog Service - Gestão de Catálogo de Serviços
 *
 * Features:
 * - Listar serviços do catálogo
 * - Criar novo serviço
 * - Atualizar serviço
 * - Obter detalhes do serviço
 * - Estatísticas do catálogo
 * - Filtros e busca
 */

import { apiClient } from '@/lib/api/client';
import type {
  ServiceCatalogCreate,
  ServiceCatalogUpdate,
  ServiceCatalogResponse,
  ServiceCatalogListResponse,
  ServiceCatalogStats,
  ServiceCategory,
  ModulesServicesModelsServiceCatalogServiceType as ServiceType,
  ModulesServicesModelsServiceCatalogServiceStatus as ServiceStatus
} from '@/types/generated/services/conectaPROServicesAPI.schemas';

export interface ListServiceCatalogParams {
  category?: ServiceCategory;
  service_type?: ServiceType;
  service_status?: ServiceStatus;
  is_available?: boolean;
  search?: string;
  skip?: number;
  limit?: number;
}

export const serviceCatalogService = {
  /**
   * Lista serviços do catálogo com filtros
   */
  async list(params?: ListServiceCatalogParams): Promise<ServiceCatalogListResponse[]> {
    const response = await apiClient.get<ServiceCatalogListResponse[]>(
      '/api/v1/services/catalog',
      { params }
    );
    return response.data;
  },

  /**
   * Obtém estatísticas do catálogo de serviços
   */
  async getStats(): Promise<ServiceCatalogStats> {
    const response = await apiClient.get<ServiceCatalogStats>(
      '/api/v1/services/catalog/stats'
    );
    return response.data;
  },

  /**
   * Obtém detalhes de um serviço específico
   */
  async getById(id: string): Promise<ServiceCatalogResponse> {
    const response = await apiClient.get<ServiceCatalogResponse>(
      `/api/v1/services/catalog/${id}`
    );
    return response.data;
  },

  /**
   * Cria novo serviço no catálogo
   */
  async create(data: ServiceCatalogCreate): Promise<ServiceCatalogResponse> {
    const response = await apiClient.post<ServiceCatalogResponse>(
      '/api/v1/services/catalog',
      data
    );
    return response.data;
  },

  /**
   * Atualiza um serviço existente
   */
  async update(
    id: string,
    data: ServiceCatalogUpdate
  ): Promise<ServiceCatalogResponse> {
    const response = await apiClient.patch<ServiceCatalogResponse>(
      `/api/v1/services/catalog/${id}`,
      data
    );
    return response.data;
  },

  /**
   * Remove um serviço do catálogo (soft delete)
   */
  async delete(id: string): Promise<void> {
    await apiClient.delete(`/api/v1/services/catalog/${id}`);
  },

  /**
   * Ativa um serviço
   */
  async activate(id: string): Promise<ServiceCatalogResponse> {
    const response = await apiClient.post<ServiceCatalogResponse>(
      `/api/v1/services/catalog/${id}/activate`
    );
    return response.data;
  },

  /**
   * Desativa um serviço
   */
  async deactivate(id: string): Promise<ServiceCatalogResponse> {
    const response = await apiClient.post<ServiceCatalogResponse>(
      `/api/v1/services/catalog/${id}/deactivate`
    );
    return response.data;
  },

  /**
   * Duplica um serviço existente
   */
  async duplicate(id: string): Promise<ServiceCatalogResponse> {
    const response = await apiClient.post<ServiceCatalogResponse>(
      `/api/v1/services/catalog/${id}/duplicate`
    );
    return response.data;
  }
};
