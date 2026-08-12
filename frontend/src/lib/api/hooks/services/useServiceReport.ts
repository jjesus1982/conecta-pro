/**
 * useServiceReport - React Query Hooks para Service Reports
 *
 * Features:
 * - Lista de relatórios
 * - CRUD de relatórios
 * - Geração automática
 * - Workflow (finalizar, aprovar, rejeitar)
 * - Geração de PDF
 * - Envio ao cliente
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { serviceReportService, type ListServiceReportParams } from '@/lib/api/services/services';
import type {
  ServiceReportCreate,
  ServiceReportUpdate
} from '@/types/generated/services/conectaPROServicesAPI.schemas';
import { serviceOrderKeys } from './useServiceOrder';

// Query Keys
export const serviceReportKeys = {
  all: ['service-report'] as const,
  lists: () => [...serviceReportKeys.all, 'list'] as const,
  list: (params?: ListServiceReportParams) => [...serviceReportKeys.lists(), params] as const,
  details: () => [...serviceReportKeys.all, 'detail'] as const,
  detail: (id: string) => [...serviceReportKeys.details(), id] as const,
  byOrder: (orderId: string) => [...serviceReportKeys.all, 'by-order', orderId] as const,
};

/**
 * Lista relatórios
 */
export function useServiceReportList(params?: ListServiceReportParams) {
  return useQuery({
    queryKey: serviceReportKeys.list(params),
    queryFn: () => serviceReportService.list(params),
  });
}

/**
 * Obtém detalhes de um relatório
 */
export function useServiceReport(id: string) {
  return useQuery({
    queryKey: serviceReportKeys.detail(id),
    queryFn: () => serviceReportService.getById(id),
    enabled: !!id,
  });
}

/**
 * Lista relatórios de uma ordem
 */
export function useServiceReportsByOrder(orderId: string) {
  return useQuery({
    queryKey: serviceReportKeys.byOrder(orderId),
    queryFn: () => serviceReportService.listByOrder(orderId),
    enabled: !!orderId,
  });
}

/**
 * Cria novo relatório
 */
export function useCreateServiceReport() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: ServiceReportCreate) => serviceReportService.create(data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: serviceReportKeys.lists() });
      queryClient.invalidateQueries({ queryKey: serviceReportKeys.byOrder(data.order_id) });
      queryClient.invalidateQueries({ queryKey: serviceOrderKeys.detail(data.order_id) });
    },
  });
}

/**
 * Atualiza relatório
 */
export function useUpdateServiceReport() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: ServiceReportUpdate }) =>
      serviceReportService.update(id, data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: serviceReportKeys.lists() });
      queryClient.invalidateQueries({ queryKey: serviceReportKeys.detail(data.id) });
      queryClient.invalidateQueries({ queryKey: serviceReportKeys.byOrder(data.order_id) });
    },
  });
}

/**
 * Gera relatório automaticamente
 */
export function useGenerateServiceReport() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (orderId: string) => serviceReportService.generate(orderId),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: serviceReportKeys.lists() });
      queryClient.invalidateQueries({ queryKey: serviceReportKeys.byOrder(data.order_id) });
      queryClient.invalidateQueries({ queryKey: serviceOrderKeys.detail(data.order_id) });
    },
  });
}

/**
 * Finaliza relatório (remove modo draft)
 */
export function useFinalizeServiceReport() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => serviceReportService.finalize(id),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: serviceReportKeys.lists() });
      queryClient.invalidateQueries({ queryKey: serviceReportKeys.detail(data.id) });
    },
  });
}

/**
 * Submete para revisão
 */
export function useSubmitReportForReview() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => serviceReportService.submitForReview(id),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: serviceReportKeys.lists() });
      queryClient.invalidateQueries({ queryKey: serviceReportKeys.detail(data.id) });
    },
  });
}

/**
 * Aprova relatório
 */
export function useApproveServiceReport() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => serviceReportService.approve(id),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: serviceReportKeys.lists() });
      queryClient.invalidateQueries({ queryKey: serviceReportKeys.detail(data.id) });
    },
  });
}

/**
 * Rejeita relatório
 */
export function useRejectServiceReport() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      serviceReportService.reject(id, reason),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: serviceReportKeys.lists() });
      queryClient.invalidateQueries({ queryKey: serviceReportKeys.detail(data.id) });
    },
  });
}

/**
 * Gera PDF do relatório
 */
export function useGenerateReportPDF() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => serviceReportService.generatePDF(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: serviceReportKeys.detail(id) });
    },
  });
}

/**
 * Envia relatório ao cliente
 */
export function useSendServiceReport() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: string;
      data: { recipients: string[]; subject?: string; message?: string };
    }) => serviceReportService.send(id, data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: serviceReportKeys.lists() });
      queryClient.invalidateQueries({ queryKey: serviceReportKeys.detail(data.id) });
    },
  });
}

/**
 * Download do PDF
 */
export function useDownloadReportPDF() {
  return useMutation({
    mutationFn: (id: string) => serviceReportService.downloadPDF(id),
  });
}
