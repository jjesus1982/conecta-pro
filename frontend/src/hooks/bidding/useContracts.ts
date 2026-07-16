'use client';

/**
 * Hooks React Query - Contracts (Contratos Públicos)
 * Cobertura 100% dos 14 endpoints backend
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { msgFromDetail } from '@/lib/string';
import { toast } from 'sonner';
import contractsService, {
  type ListContractsParams,
  type AditivarParams,
  type CalcularReajusteParams,
  type CriarMedicaoParams,
} from '@/services/bidding/contracts.service';
import type {
  PublicContractCreate,
  PublicContractUpdate,
} from '@/types/generated/bidding';

const QUERY_KEYS = {
  all: ['bidding', 'contracts'] as const,
  lists: () => [...QUERY_KEYS.all, 'list'] as const,
  list: (params?: ListContractsParams) => [...QUERY_KEYS.lists(), params] as const,
  details: () => [...QUERY_KEYS.all, 'detail'] as const,
  detail: (id: string) => [...QUERY_KEYS.details(), id] as const,
  vigentes: (params?: unknown) => [...QUERY_KEYS.all, 'vigentes', params] as const,
  vencendo: (params?: unknown) => [...QUERY_KEYS.all, 'vencendo', params] as const,
  dashboard: (params?: unknown) => [...QUERY_KEYS.all, 'dashboard', params] as const,
  medicoes: (contractId: string) => [...QUERY_KEYS.detail(contractId), 'medicoes'] as const,
};

// GET /contracts/
export function useListarContratos(params?: ListContractsParams) {
  return useQuery({
    queryKey: QUERY_KEYS.list(params),
    queryFn: () => contractsService.listarContratos(params),
    staleTime: 1000 * 60 * 5,
  });
}

// GET /contracts/dashboard
export function useContractsDashboard(params?: { periodo_dias?: number }) {
  return useQuery({
    queryKey: QUERY_KEYS.dashboard(params),
    queryFn: () => contractsService.getDashboard(params),
    staleTime: 1000 * 60 * 10,
  });
}

// GET /contracts/vigentes
export function useListarContratosVigentes(params?: { page?: number; size?: number }) {
  return useQuery({
    queryKey: QUERY_KEYS.vigentes(params),
    queryFn: () => contractsService.listarContratosVigentes(params),
    staleTime: 1000 * 60 * 5,
  });
}

// GET /contracts/vencendo
export function useListarContratosVencendo(params?: { dias?: number; page?: number; size?: number }) {
  return useQuery({
    queryKey: QUERY_KEYS.vencendo(params),
    queryFn: () => contractsService.listarContratosVencendo(params),
    staleTime: 1000 * 60 * 5,
  });
}

// GET /contracts/{id}
export function useBuscarContrato(contractId: string, enabled = true) {
  return useQuery({
    queryKey: QUERY_KEYS.detail(contractId),
    queryFn: () => contractsService.buscarContratoPorId(contractId),
    enabled: enabled && !!contractId,
    staleTime: 1000 * 60 * 5,
  });
}

// POST /contracts/
export function useCriarContrato() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: PublicContractCreate) => contractsService.criarContrato(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.lists() });
      toast.success('Contrato criado com sucesso');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao criar contrato');
    },
  });
}

// PUT /contracts/{id}
export function useAtualizarContrato() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: PublicContractUpdate }) =>
      contractsService.atualizarContrato(id, data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.lists() });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.detail(data.id) });
      toast.success('Contrato atualizado com sucesso');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao atualizar contrato');
    },
  });
}

// DELETE /contracts/{id}
export function useRemoverContrato() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (contractId: string) => contractsService.removerContrato(contractId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.lists() });
      toast.success('Contrato removido com sucesso');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao remover contrato');
    },
  });
}

// POST /contracts/{id}/aditivo
export function useAditivar() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (params: AditivarParams) => contractsService.aditivar(params),
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.lists() });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.detail(variables.contract_id) });
      toast.success('Aditivo criado com sucesso');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao criar aditivo');
    },
  });
}

// POST /contracts/{id}/reajuste/calcular
export function useCalcularReajuste() {
  return useMutation({
    mutationFn: (params: CalcularReajusteParams) => contractsService.calcularReajuste(params),
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao calcular reajuste');
    },
  });
}

// POST /contracts/{id}/reajuste/aplicar
export function useAplicarReajuste() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (params: CalcularReajusteParams) => contractsService.aplicarReajuste(params),
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.lists() });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.detail(variables.contract_id) });
      toast.success('Reajuste aplicado com sucesso');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao aplicar reajuste');
    },
  });
}

// GET /contracts/{id}/medicoes
export function useListarMedicoes(contractId: string, params?: { status?: string }) {
  return useQuery({
    queryKey: QUERY_KEYS.medicoes(contractId),
    queryFn: () => contractsService.listarMedicoes(contractId, params),
    enabled: !!contractId,
    staleTime: 1000 * 60 * 5,
  });
}

// POST /contracts/{id}/medicoes
export function useCriarMedicao() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (params: CriarMedicaoParams) => contractsService.criarMedicao(params),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.medicoes(variables.contract_id) });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.detail(variables.contract_id) });
      toast.success('Medição criada com sucesso');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao criar medição');
    },
  });
}

// POST /medicoes/{measurement_id}/aprovar
export function useAprovarMedicao() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ measurementId, contractId, observacoes }: { measurementId: string; contractId: string; observacoes?: string }) =>
      contractsService.aprovarMedicao(measurementId, observacoes),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.medicoes(variables.contractId) });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.detail(variables.contractId) });
      toast.success('Medição aprovada com sucesso');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao aprovar medição');
    },
  });
}
