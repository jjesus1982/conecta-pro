/**
 * useSLA - React Query Hooks para SLA Management
 *
 * Features:
 * - Lista de SLAs
 * - CRUD de SLAs
 * - Ativação/desativação
 * - Compliance tracking
 * - Estatísticas
 * - Histórico de breaches
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { slaService, type ListSLAParams } from '@/lib/api/services/services';
import type {
  SLAConfigCreate,
  SLAConfigUpdate
} from '@/types/generated/services/conectaPROServicesAPI.schemas';

// Query Keys
export const slaKeys = {
  all: ['sla'] as const,
  lists: () => [...slaKeys.all, 'list'] as const,
  list: (params?: ListSLAParams) => [...slaKeys.lists(), params] as const,
  details: () => [...slaKeys.all, 'detail'] as const,
  detail: (id: string) => [...slaKeys.details(), id] as const,
  compliance: (id: string) => [...slaKeys.all, 'compliance', id] as const,
  defaultForService: (serviceId: string) => [...slaKeys.all, 'default-service', serviceId] as const,
  breachHistory: (id: string, params?: any) => [...slaKeys.all, 'breaches', id, params] as const,
};

/**
 * Lista SLAs
 */
export function useSLAList(params?: ListSLAParams) {
  return useQuery({
    queryKey: slaKeys.list(params),
    queryFn: () => slaService.list(params),
  });
}

/**
 * Obtém detalhes de um SLA
 */
export function useSLA(id: string) {
  return useQuery({
    queryKey: slaKeys.detail(id),
    queryFn: () => slaService.getById(id),
    enabled: !!id,
  });
}

/**
 * Obtém compliance de um SLA
 */
export function useSLACompliance(id: string) {
  return useQuery({
    queryKey: slaKeys.compliance(id),
    queryFn: () => slaService.getCompliance(id),
    enabled: !!id,
  });
}

/**
 * Cria novo SLA
 */
export function useCreateSLA() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: SLAConfigCreate) => slaService.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: slaKeys.lists() });
    },
  });
}

/**
 * Atualiza SLA
 */
export function useUpdateSLA() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: SLAConfigUpdate }) =>
      slaService.update(id, data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: slaKeys.lists() });
      queryClient.invalidateQueries({ queryKey: slaKeys.detail(data.id) });
      queryClient.invalidateQueries({ queryKey: slaKeys.compliance(data.id) });
    },
  });
}

/**
 * Ativa SLA
 */
export function useActivateSLA() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => slaService.activate(id),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: slaKeys.lists() });
      queryClient.invalidateQueries({ queryKey: slaKeys.detail(data.id) });
    },
  });
}

/**
 * Desativa SLA
 */
export function useDeactivateSLA() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => slaService.deactivate(id),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: slaKeys.lists() });
      queryClient.invalidateQueries({ queryKey: slaKeys.detail(data.id) });
    },
  });
}

/**
 * Define como padrão
 */
export function useSetSLAAsDefault() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => slaService.setAsDefault(id),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: slaKeys.lists() });
      queryClient.invalidateQueries({ queryKey: slaKeys.detail(data.id) });
      if (data.service_id) {
        queryClient.invalidateQueries({ queryKey: slaKeys.defaultForService(data.service_id) });
      }
    },
  });
}

