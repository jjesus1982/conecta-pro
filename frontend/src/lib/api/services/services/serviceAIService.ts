/**
 * Service AI Service - Análises de IA para Serviços
 *
 * Features:
 * - Análise de performance de serviços
 * - Recomendações inteligentes
 * - Análise de SLA
 * - Previsões e insights
 */

import { apiClient } from '@/lib/api/client';
import type {
  ServiceAnalysis,
  ServiceRecommendation,
  SLAAnalysis
} from '@/types/generated/services/conectaPROServicesAPI.schemas';

export const serviceAIService = {
  /**
   * Análise de performance de um serviço específico
   */
  async analyzeService(serviceId: string): Promise<ServiceAnalysis> {
    const response = await apiClient.post<ServiceAnalysis>(
      `/api/v1/services/catalog/${serviceId}/analyze`
    );
    return response.data;
  },

  /**
   * Recomendações para otimização de serviços
   */
  async getRecommendations(params?: {
    category?: string;
    min_confidence?: number;
    limit?: number;
  }): Promise<ServiceRecommendation[]> {
    const response = await apiClient.get<ServiceRecommendation[]>(
      '/api/v1/services/ai/recommendations',
      { params }
    );
    return response.data;
  },

  /**
   * Análise de compliance de SLA
   */
  async analyzeSLA(slaId: string): Promise<SLAAnalysis> {
    const response = await apiClient.post<SLAAnalysis>(
      `/api/v1/services/sla/${slaId}/analyze`
    );
    return response.data;
  },

  /**
   * Previsão de demanda para um serviço
   */
  async predictDemand(
    serviceId: string,
    params?: {
      start_date?: string;
      end_date?: string;
      granularity?: 'daily' | 'weekly' | 'monthly';
    }
  ): Promise<{
    service_id: string;
    predictions: Array<{
      date: string;
      predicted_orders: number;
      confidence: number;
    }>;
    insights: string[];
  }> {
    const response = await apiClient.post(
      `/api/v1/services/catalog/${serviceId}/predict-demand`,
      params
    );
    return response.data;
  },

  /**
   * Otimização de preços baseada em IA
   */
  async optimizePricing(
    serviceId: string
  ): Promise<{
    current_price: number;
    recommended_price: number;
    reason: string;
    expected_impact: {
      revenue_change_percent: number;
      demand_change_percent: number;
    };
  }> {
    const response = await apiClient.post(
      `/api/v1/services/catalog/${serviceId}/optimize-pricing`
    );
    return response.data;
  },

  /**
   * Sugestão de serviços similares/complementares
   */
  async getSimilarServices(
    serviceId: string,
    limit?: number
  ): Promise<Array<{
    service_id: string;
    service_name: string;
    similarity_score: number;
    reason: string;
  }>> {
    const response = await apiClient.get(
      `/api/v1/services/catalog/${serviceId}/similar`,
      { params: { limit } }
    );
    return response.data;
  },

  /**
   * Análise de satisfação do cliente
   */
  async analyzeSatisfaction(params?: {
    service_id?: string;
    client_id?: string;
    start_date?: string;
    end_date?: string;
  }): Promise<{
    overall_satisfaction: number;
    ratings_distribution: Record<number, number>;
    common_complaints: Array<{
      topic: string;
      frequency: number;
      severity: 'low' | 'medium' | 'high';
    }>;
    improvement_suggestions: string[];
  }> {
    const response = await apiClient.post(
      '/api/v1/services/ai/analyze-satisfaction',
      params
    );
    return response.data;
  },

  /**
   * Previsão de breach de SLA
   */
  async predictSLABreach(
    orderId: string
  ): Promise<{
    order_id: string;
    breach_risk: 'low' | 'medium' | 'high';
    probability: number;
    estimated_completion: string;
    recommendations: string[];
  }> {
    const response = await apiClient.post(
      `/api/v1/services/orders/${orderId}/predict-sla-breach`
    );
    return response.data;
  },

  /**
   * Alocação otimizada de técnicos
   */
  async optimizeAllocation(params: {
    date: string;
    orders: string[];
    technicians: string[];
  }): Promise<{
    allocations: Array<{
      order_id: string;
      technician_id: string;
      confidence: number;
      reason: string;
    }>;
    unassigned_orders: string[];
    optimization_score: number;
  }> {
    const response = await apiClient.post(
      '/api/v1/services/ai/optimize-allocation',
      params
    );
    return response.data;
  },

  /**
   * Geração automática de descrição de serviço
   */
  async generateDescription(
    serviceId: string,
    context?: string
  ): Promise<{
    short_description: string;
    long_description: string;
    tags: string[];
  }> {
    const response = await apiClient.post(
      `/api/v1/services/catalog/${serviceId}/generate-description`,
      { context }
    );
    return response.data;
  }
};
