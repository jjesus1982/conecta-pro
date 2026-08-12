/**
 * useServiceCatalog - React Query Hooks para Service Catalog
 *
 * Features:
 * - Lista de serviços com filtros
 * - Estatísticas do catálogo
 * - CRUD de serviços
 * - Ativação/desativação
 * - Duplicação
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { serviceCatalogService, type ListServiceCatalogParams } from '@/lib/api/services/services';
import type {
  ServiceCatalogCreate,
  ServiceCatalogUpdate,
  ServiceCatalogResponse
} from '@/types/generated/services/conectaPROServicesAPI.schemas';

// Query Keys
export const serviceCatalogKeys = {
  all: ['service-catalog'] as const,
  lists: () => [...serviceCatalogKeys.all, 'list'] as const,
  list: (params?: ListServiceCatalogParams) => [...serviceCatalogKeys.lists(), params] as const,
  details: () => [...serviceCatalogKeys.all, 'detail'] as const,
  detail: (id: string) => [...serviceCatalogKeys.details(), id] as const,
  stats: () => [...serviceCatalogKeys.all, 'stats'] as const,
};

/**
 * Lista serviços do catálogo
 */
export function useServiceCatalogList(params?: ListServiceCatalogParams) {
  return useQuery({
    queryKey: serviceCatalogKeys.list(params),
    queryFn: () => serviceCatalogService.list(params),
  });
}

/**
 * Obtém estatísticas do catálogo
 */
export function useServiceCatalogStats() {
  return useQuery({
    queryKey: serviceCatalogKeys.stats(),
    queryFn: () => serviceCatalogService.getStats(),
  });
}

/**
 * Obtém detalhes de um serviço
 */
export function useServiceCatalog(id: string) {
  return useQuery({
    queryKey: serviceCatalogKeys.detail(id),
    queryFn: () => serviceCatalogService.getById(id),
    enabled: !!id,
  });
}

/**
 * Cria novo serviço
 */
export function useCreateServiceCatalog() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: ServiceCatalogCreate) => serviceCatalogService.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: serviceCatalogKeys.lists() });
      queryClient.invalidateQueries({ queryKey: serviceCatalogKeys.stats() });
    },
  });
}

/**
 * Atualiza serviço existente
 */
export function useUpdateServiceCatalog() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: ServiceCatalogUpdate }) =>
      serviceCatalogService.update(id, data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: serviceCatalogKeys.lists() });
      queryClient.invalidateQueries({ queryKey: serviceCatalogKeys.detail(data.id) });
      queryClient.invalidateQueries({ queryKey: serviceCatalogKeys.stats() });
    },
  });
}

/**
 * Remove serviço
 */
export function useDeleteServiceCatalog() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => serviceCatalogService.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: serviceCatalogKeys.lists() });
      queryClient.invalidateQueries({ queryKey: serviceCatalogKeys.stats() });
    },
  });
}

/**
 * Ativa serviço
 */
export function useActivateServiceCatalog() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => serviceCatalogService.activate(id),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: serviceCatalogKeys.lists() });
      queryClient.invalidateQueries({ queryKey: serviceCatalogKeys.detail(data.id) });
      queryClient.invalidateQueries({ queryKey: serviceCatalogKeys.stats() });
    },
  });
}

/**
 * Desativa serviço
 */
export function useDeactivateServiceCatalog() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => serviceCatalogService.deactivate(id),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: serviceCatalogKeys.lists() });
      queryClient.invalidateQueries({ queryKey: serviceCatalogKeys.detail(data.id) });
      queryClient.invalidateQueries({ queryKey: serviceCatalogKeys.stats() });
    },
  });
}

/**
 * Duplica serviço
 */
export function useDuplicateServiceCatalog() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => serviceCatalogService.duplicate(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: serviceCatalogKeys.lists() });
      queryClient.invalidateQueries({ queryKey: serviceCatalogKeys.stats() });
    },
  });
}
