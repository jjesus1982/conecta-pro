/**
 * useServiceAI - React Query Hooks para Service AI Analytics
 *
 * Features:
 * - Análise de performance
 * - Recomendações inteligentes
 * - Análise de SLA
 * - Previsão de demanda
 * - Otimização de preços
 * - Serviços similares
 * - Análise de satisfação
 * - Previsão de breach
 * - Alocação otimizada
 * - Geração de descrições
 */

import { useMutation, useQuery } from '@tanstack/react-query';
import { serviceAIService } from '@/lib/api/services/services';

// Query Keys
export const serviceAIKeys = {
  all: ['service-ai'] as const,
  analyzeService: (serviceId: string) => [...serviceAIKeys.all, 'analyze-service', serviceId] as const,
  recommendations: (params?: any) => [...serviceAIKeys.all, 'recommendations', params] as const,
  analyzeSLA: (slaId: string) => [...serviceAIKeys.all, 'analyze-sla', slaId] as const,
  predictDemand: (serviceId: string, params?: any) => [...serviceAIKeys.all, 'predict-demand', serviceId, params] as const,
  similarServices: (serviceId: string, limit?: number) => [...serviceAIKeys.all, 'similar', serviceId, limit] as const,
};

/**
 * Análise de performance de serviço
 */
export function useAnalyzeService(serviceId: string) {
  return useQuery({
    queryKey: serviceAIKeys.analyzeService(serviceId),
    queryFn: () => serviceAIService.analyzeService(serviceId),
    enabled: !!serviceId,
  });
}

/**
 * Recomendações de otimização
 */
export function useServiceRecommendations(params?: {
  category?: string;
  min_confidence?: number;
  limit?: number;
}) {
  return useQuery({
    queryKey: serviceAIKeys.recommendations(params),
    queryFn: () => serviceAIService.getRecommendations(params),
  });
}

/**
 * Análise de SLA
 */
export function useAnalyzeSLA(slaId: string) {
  return useQuery({
    queryKey: serviceAIKeys.analyzeSLA(slaId),
    queryFn: () => serviceAIService.analyzeSLA(slaId),
    enabled: !!slaId,
  });
}

/**
 * Previsão de demanda
 */
export function usePredictDemand(
  serviceId: string,
  params?: {
    start_date?: string;
    end_date?: string;
    granularity?: 'daily' | 'weekly' | 'monthly';
  }
) {
  return useQuery({
    queryKey: serviceAIKeys.predictDemand(serviceId, params),
    queryFn: () => serviceAIService.predictDemand(serviceId, params),
    enabled: !!serviceId,
  });
}

/**
 * Serviços similares
 */
export function useSimilarServices(serviceId: string, limit?: number) {
  return useQuery({
    queryKey: serviceAIKeys.similarServices(serviceId, limit),
    queryFn: () => serviceAIService.getSimilarServices(serviceId, limit),
    enabled: !!serviceId,
  });
}

/**
 * Otimização de preços
 */
export function useOptimizePricing() {
  return useMutation({
    mutationFn: (serviceId: string) => serviceAIService.optimizePricing(serviceId),
  });
}

/**
 * Análise de satisfação
 */
export function useAnalyzeSatisfaction() {
  return useMutation({
    mutationFn: (params?: {
      service_id?: string;
      client_id?: string;
      start_date?: string;
      end_date?: string;
    }) => serviceAIService.analyzeSatisfaction(params),
  });
}

/**
 * Previsão de breach de SLA
 */
export function usePredictSLABreach() {
  return useMutation({
    mutationFn: (orderId: string) => serviceAIService.predictSLABreach(orderId),
  });
}

/**
 * Alocação otimizada de técnicos
 */
export function useOptimizeAllocation() {
  return useMutation({
    mutationFn: (params: {
      date: string;
      orders: string[];
      technicians: string[];
    }) => serviceAIService.optimizeAllocation(params),
  });
}

/**
 * Geração de descrição
 */
export function useGenerateServiceDescription() {
  return useMutation({
    mutationFn: ({ serviceId, context }: { serviceId: string; context?: string }) =>
      serviceAIService.generateDescription(serviceId, context),
  });
}
