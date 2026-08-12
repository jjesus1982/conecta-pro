/**
 * useServiceOrder - React Query Hooks para Service Orders
 *
 * Features:
 * - Lista de ordens com filtros
 * - Estatísticas
 * - CRUD de ordens
 * - Workflow (aprovar, rejeitar, cancelar)
 * - Agendamento
 * - Execução (iniciar, completar)
 * - Avaliação
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { serviceOrderService, type ListServiceOrderParams } from '@/lib/api/services/services';
import type {
  ServiceOrderCreate,
  ServiceOrderUpdate
} from '@/types/generated/services/conectaPROServicesAPI.schemas';

// Query Keys
export const serviceOrderKeys = {
  all: ['service-order'] as const,
  lists: () => [...serviceOrderKeys.all, 'list'] as const,
  list: (params?: ListServiceOrderParams) => [...serviceOrderKeys.lists(), params] as const,
  details: () => [...serviceOrderKeys.all, 'detail'] as const,
  detail: (id: string) => [...serviceOrderKeys.details(), id] as const,
  stats: (params?: ListServiceOrderParams) => [...serviceOrderKeys.all, 'stats', params] as const,
};

/**
 * Lista ordens de serviço
 */
export function useServiceOrderList(params?: ListServiceOrderParams) {
  return useQuery({
    queryKey: serviceOrderKeys.list(params),
    queryFn: () => serviceOrderService.list(params),
  });
}

/**
 * Obtém estatísticas de ordens
 */
export function useServiceOrderStats(params?: ListServiceOrderParams) {
  return useQuery({
    queryKey: serviceOrderKeys.stats(params),
    queryFn: () => serviceOrderService.getStats(params),
  });
}

/**
 * Obtém detalhes de uma ordem
 */
export function useServiceOrder(id: string) {
  return useQuery({
    queryKey: serviceOrderKeys.detail(id),
    queryFn: () => serviceOrderService.getById(id),
    enabled: !!id,
  });
}

/**
 * Cria nova ordem
 */
export function useCreateServiceOrder() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: ServiceOrderCreate) => serviceOrderService.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: serviceOrderKeys.lists() });
      queryClient.invalidateQueries({ queryKey: serviceOrderKeys.all });
    },
  });
}

/**
 * Atualiza ordem
 */
export function useUpdateServiceOrder() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: ServiceOrderUpdate }) =>
      serviceOrderService.update(id, data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: serviceOrderKeys.lists() });
      queryClient.invalidateQueries({ queryKey: serviceOrderKeys.detail(data.id) });
    },
  });
}

/**
 * Cancela ordem
 */
export function useCancelServiceOrder() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason?: string }) =>
      serviceOrderService.cancel(id, reason),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: serviceOrderKeys.lists() });
      queryClient.invalidateQueries({ queryKey: serviceOrderKeys.detail(data.id) });
    },
  });
}

/**
 * Aprova ordem
 */
export function useApproveServiceOrder() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => serviceOrderService.approve(id),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: serviceOrderKeys.lists() });
      queryClient.invalidateQueries({ queryKey: serviceOrderKeys.detail(data.id) });
    },
  });
}

/**
 * Rejeita ordem
 */
export function useRejectServiceOrder() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      serviceOrderService.reject(id, reason),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: serviceOrderKeys.lists() });
      queryClient.invalidateQueries({ queryKey: serviceOrderKeys.detail(data.id) });
    },
  });
}

/**
 * Agenda ordem
 */
export function useScheduleServiceOrder() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: string;
      data: {
        scheduled_date: string;
        scheduled_time_start: string;
        scheduled_time_end?: string;
        technician_id?: string;
      };
    }) => serviceOrderService.schedule(id, data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: serviceOrderKeys.lists() });
      queryClient.invalidateQueries({ queryKey: serviceOrderKeys.detail(data.id) });
    },
  });
}

/**
 * Inicia execução
 */
export function useStartServiceOrder() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => serviceOrderService.start(id),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: serviceOrderKeys.lists() });
      queryClient.invalidateQueries({ queryKey: serviceOrderKeys.detail(data.id) });
    },
  });
}

/**
 * Completa ordem
 */
export function useCompleteServiceOrder() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => serviceOrderService.complete(id),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: serviceOrderKeys.lists() });
      queryClient.invalidateQueries({ queryKey: serviceOrderKeys.detail(data.id) });
    },
  });
}

/**
 * Atribui técnico
 */
export function useAssignTechnician() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, technicianId }: { id: string; technicianId: string }) =>
      serviceOrderService.assignTechnician(id, technicianId),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: serviceOrderKeys.lists() });
      queryClient.invalidateQueries({ queryKey: serviceOrderKeys.detail(data.id) });
    },
  });
}

/**
 * Adiciona avaliação
 */
export function useAddServiceOrderRating() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: string;
      data: { rating: number; feedback?: string };
    }) => serviceOrderService.addRating(id, data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: serviceOrderKeys.lists() });
      queryClient.invalidateQueries({ queryKey: serviceOrderKeys.detail(data.id) });
    },
  });
}
