/**
 * useServiceExecution - React Query Hooks para Service Execution
 *
 * Features:
 * - Lista de execuções
 * - CRUD de execuções
 * - Check-in/Check-out
 * - Pausar/Retomar
 * - Checklist
 * - Materiais
 * - Fotos/Evidências
 * - Assinaturas
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { serviceExecutionService, type ListServiceExecutionParams, type ServiceExecutionUpdate } from '@/lib/api/services/services';
import type {
  ServiceExecutionCreate
} from '@/types/generated/services/conectaPROServicesAPI.schemas';
import { serviceOrderKeys } from './useServiceOrder';

// Query Keys
export const serviceExecutionKeys = {
  all: ['service-execution'] as const,
  lists: () => [...serviceExecutionKeys.all, 'list'] as const,
  list: (params?: ListServiceExecutionParams) => [...serviceExecutionKeys.lists(), params] as const,
  details: () => [...serviceExecutionKeys.all, 'detail'] as const,
  detail: (id: string) => [...serviceExecutionKeys.details(), id] as const,
  byOrder: (orderId: string) => [...serviceExecutionKeys.all, 'by-order', orderId] as const,
};

/**
 * Lista execuções
 */
export function useServiceExecutionList(params?: ListServiceExecutionParams) {
  return useQuery({
    queryKey: serviceExecutionKeys.list(params),
    queryFn: () => serviceExecutionService.list(params),
  });
}

/**
 * Obtém detalhes de uma execução
 */
export function useServiceExecution(id: string) {
  return useQuery({
    queryKey: serviceExecutionKeys.detail(id),
    queryFn: () => serviceExecutionService.getById(id),
    enabled: !!id,
  });
}

/**
 * Lista execuções de uma ordem
 */
export function useServiceExecutionsByOrder(orderId: string) {
  return useQuery({
    queryKey: serviceExecutionKeys.byOrder(orderId),
    queryFn: () => serviceExecutionService.listByOrder(orderId),
    enabled: !!orderId,
  });
}

/**
 * Cria nova execução
 */
export function useCreateServiceExecution() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: ServiceExecutionCreate) => serviceExecutionService.create(data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: serviceExecutionKeys.lists() });
      queryClient.invalidateQueries({ queryKey: serviceExecutionKeys.byOrder(data.order_id) });
      queryClient.invalidateQueries({ queryKey: serviceOrderKeys.detail(data.order_id) });
    },
  });
}

/**
 * Atualiza execução
 */
export function useUpdateServiceExecution() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: ServiceExecutionUpdate }) =>
      serviceExecutionService.update(id, data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: serviceExecutionKeys.lists() });
      queryClient.invalidateQueries({ queryKey: serviceExecutionKeys.detail(data.id) });
      queryClient.invalidateQueries({ queryKey: serviceExecutionKeys.byOrder(data.order_id) });
    },
  });
}

/**
 * Check-in (iniciar execução)
 */
export function useCheckInExecution() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => serviceExecutionService.checkIn(id),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: serviceExecutionKeys.detail(data.id) });
      queryClient.invalidateQueries({ queryKey: serviceExecutionKeys.byOrder(data.order_id) });
      queryClient.invalidateQueries({ queryKey: serviceOrderKeys.detail(data.order_id) });
    },
  });
}

/**
 * Check-out (finalizar execução)
 */
export function useCheckOutExecution() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => serviceExecutionService.checkOut(id),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: serviceExecutionKeys.detail(data.id) });
      queryClient.invalidateQueries({ queryKey: serviceExecutionKeys.byOrder(data.order_id) });
      queryClient.invalidateQueries({ queryKey: serviceOrderKeys.detail(data.order_id) });
    },
  });
}

/**
 * Pausa execução
 */
export function usePauseExecution() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason?: string }) =>
      serviceExecutionService.pause(id, reason),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: serviceExecutionKeys.detail(data.id) });
      queryClient.invalidateQueries({ queryKey: serviceExecutionKeys.byOrder(data.order_id) });
    },
  });
}

/**
 * Retoma execução
 */
export function useResumeExecution() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => serviceExecutionService.resume(id),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: serviceExecutionKeys.detail(data.id) });
      queryClient.invalidateQueries({ queryKey: serviceExecutionKeys.byOrder(data.order_id) });
    },
  });
}

/**
 * Atualiza checklist
 */
export function useUpdateExecutionChecklist() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      id,
      checklist,
    }: {
      id: string;
      checklist: Array<{ item: string; checked: boolean; notes?: string }>;
    }) => serviceExecutionService.updateChecklist(id, checklist),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: serviceExecutionKeys.detail(data.id) });
    },
  });
}

/**
 * Adiciona material
 */
export function useAddExecutionMaterial() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: string;
      data: { name: string; quantity: number; unit: string; cost?: number };
    }) => serviceExecutionService.addMaterial(id, data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: serviceExecutionKeys.detail(data.id) });
    },
  });
}

/**
 * Adiciona foto
 */
export function useAddExecutionPhoto() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: string;
      data: { file: File; description?: string; category?: string };
    }) => serviceExecutionService.addPhoto(id, data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: serviceExecutionKeys.detail(data.id) });
    },
  });
}

/**
 * Adiciona assinatura
 */
export function useAddExecutionSignature() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: string;
      data: { signer_name: string; signer_role: string; signature_data: string };
    }) => serviceExecutionService.addSignature(id, data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: serviceExecutionKeys.detail(data.id) });
    },
  });
}
