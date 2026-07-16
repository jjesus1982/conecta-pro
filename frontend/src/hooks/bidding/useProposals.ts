'use client';

/**
 * Hooks React Query - Proposals (Propostas)
 * Cobertura 100% dos 13 endpoints backend
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { msgFromDetail } from '@/lib/string';
import { toast } from 'sonner';
import proposalsService, {
  type ListProposalsParams,
  type BiddingProposalCreate,
  type BiddingProposalUpdate,
  type RegistrarResultadoParams,
  type RegistrarLanceParams,
  type CalcularBDIParams,
} from '@/services/bidding/proposals.service';

const QUERY_KEYS = {
  all: ['bidding', 'proposals'] as const,
  lists: () => [...QUERY_KEYS.all, 'list'] as const,
  list: (params?: ListProposalsParams) => [...QUERY_KEYS.lists(), params] as const,
  details: () => [...QUERY_KEYS.all, 'detail'] as const,
  detail: (id: string) => [...QUERY_KEYS.details(), id] as const,
  tender: (tenderId: string, params?: unknown) => [...QUERY_KEYS.all, 'tender', tenderId, params] as const,
  estatisticas: () => [...QUERY_KEYS.all, 'estatisticas'] as const,
  vencedoras: (params?: unknown) => [...QUERY_KEYS.all, 'vencedoras', params] as const,
};

// GET /proposals/
export function useListarPropostas(params?: ListProposalsParams) {
  return useQuery({
    queryKey: QUERY_KEYS.list(params),
    queryFn: () => proposalsService.listarPropostas(params),
    staleTime: 1000 * 60 * 5,
  });
}

// GET /proposals/estatisticas
export function useEstatisticasPropostas() {
  return useQuery({
    queryKey: QUERY_KEYS.estatisticas(),
    queryFn: () => proposalsService.getEstatisticas(),
    staleTime: 1000 * 60 * 10,
  });
}

// GET /proposals/vencedoras
export function useListarVencedoras(params?: { page?: number; size?: number }) {
  return useQuery({
    queryKey: QUERY_KEYS.vencedoras(params),
    queryFn: () => proposalsService.listarVencedoras(params),
    staleTime: 1000 * 60 * 10,
  });
}

// GET /proposals/tender/{tender_id}
export function useListarPropostasPorEdital(tenderId: string, params?: { page?: number; size?: number }) {
  return useQuery({
    queryKey: QUERY_KEYS.tender(tenderId, params),
    queryFn: () => proposalsService.listarPropostasPorEdital(tenderId, params),
    enabled: !!tenderId,
    staleTime: 1000 * 60 * 5,
  });
}

// GET /proposals/{id}
export function useBuscarProposta(proposalId: string, enabled = true) {
  return useQuery({
    queryKey: QUERY_KEYS.detail(proposalId),
    queryFn: () => proposalsService.buscarPropostaPorId(proposalId),
    enabled: enabled && !!proposalId,
    staleTime: 1000 * 60 * 5,
  });
}

// POST /proposals/
export function useCriarProposta() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: BiddingProposalCreate) => proposalsService.criarProposta(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.lists() });
      toast.success('Proposta criada com sucesso');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao criar proposta');
    },
  });
}

// PUT /proposals/{id}
export function useAtualizarProposta() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: BiddingProposalUpdate }) =>
      proposalsService.atualizarProposta(id, data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.lists() });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.detail(data.id) });
      toast.success('Proposta atualizada com sucesso');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao atualizar proposta');
    },
  });
}

// DELETE /proposals/{id}
export function useRemoverProposta() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (proposalId: string) => proposalsService.removerProposta(proposalId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.lists() });
      toast.success('Proposta removida com sucesso');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao remover proposta');
    },
  });
}

// POST /proposals/{id}/pronta
export function useMarcarPronta() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ proposalId, observacoes }: { proposalId: string; observacoes?: string }) =>
      proposalsService.marcarPronta(proposalId, observacoes),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.lists() });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.detail(data.id) });
      toast.success('Proposta marcada como pronta');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao marcar proposta como pronta');
    },
  });
}

// POST /proposals/{id}/enviar
export function useEnviarProposta() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ proposalId, observacoes }: { proposalId: string; observacoes?: string }) =>
      proposalsService.enviarProposta(proposalId, observacoes),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.lists() });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.detail(data.id) });
      toast.success('Proposta enviada com sucesso');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao enviar proposta');
    },
  });
}

// POST /proposals/{id}/resultado
export function useRegistrarResultado() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (params: RegistrarResultadoParams) => proposalsService.registrarResultado(params),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.lists() });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.detail(data.id) });
      toast.success('Resultado registrado com sucesso');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao registrar resultado');
    },
  });
}

// POST /proposals/{id}/lance
export function useRegistrarLance() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (params: RegistrarLanceParams) => proposalsService.registrarLance(params),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.lists() });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.detail(data.id) });
      toast.success('Lance registrado com sucesso');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao registrar lance');
    },
  });
}

// POST /proposals/calcular-bdi
export function useCalcularBDI() {
  return useMutation({
    mutationFn: (params: CalcularBDIParams) => proposalsService.calcularBDI(params),
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao calcular BDI');
    },
  });
}
