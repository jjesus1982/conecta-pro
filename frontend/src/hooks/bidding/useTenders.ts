'use client';

/**
 * Hooks React Query - Tenders (Editais)
 * Cobertura 100% dos 15 endpoints backend
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { msgFromDetail } from '@/lib/string';
import { toast } from 'sonner';
import tendersService, {
  type ListTendersParams,
  type PNCPBuscarParams,
  type MarcarParticipacaoParams,
  type AlterarStatusParams,
} from '@/services/bidding/tenders.service';
import type {
  TenderCreate,
  TenderUpdate,
} from '@/types/generated/bidding';

const QUERY_KEYS = {
  all: ['bidding', 'tenders'] as const,
  lists: () => [...QUERY_KEYS.all, 'list'] as const,
  list: (params?: ListTendersParams) => [...QUERY_KEYS.lists(), params] as const,
  details: () => [...QUERY_KEYS.all, 'detail'] as const,
  detail: (id: string) => [...QUERY_KEYS.details(), id] as const,
  abertos: (params?: unknown) => [...QUERY_KEYS.all, 'abertos', params] as const,
  participando: (params?: unknown) => [...QUERY_KEYS.all, 'participando', params] as const,
  segmento: (segmento: string, params?: unknown) => [...QUERY_KEYS.all, 'segmento', segmento, params] as const,
  documentos: (tenderId: string) => [...QUERY_KEYS.detail(tenderId), 'documentos'] as const,
  pncp: (params?: PNCPBuscarParams) => [...QUERY_KEYS.all, 'pncp', params] as const,
  pncpStatus: () => [...QUERY_KEYS.all, 'pncp-status'] as const,
  dashboard: (params?: unknown) => [...QUERY_KEYS.all, 'dashboard', params] as const,
};

// GET /tenders/
export function useListarEditais(params?: ListTendersParams) {
  return useQuery({
    queryKey: QUERY_KEYS.list(params),
    queryFn: () => tendersService.listarEditais(params),
    staleTime: 1000 * 60 * 5,
  });
}

// GET /tenders/{id}
export function useBuscarEdital(tenderId: string, enabled = true) {
  return useQuery({
    queryKey: QUERY_KEYS.detail(tenderId),
    queryFn: () => tendersService.buscarEditalPorId(tenderId),
    enabled: enabled && !!tenderId,
    staleTime: 1000 * 60 * 5,
  });
}

// GET /tenders/dashboard
export function useTendersDashboard(params?: { uf?: string; periodo_dias?: number }) {
  return useQuery({
    queryKey: QUERY_KEYS.dashboard(params),
    queryFn: () => tendersService.getDashboard(params),
    staleTime: 1000 * 60 * 10,
  });
}

// GET /tenders/abertos
export function useListarEditaisAbertos(params?: { uf?: string; segmento?: string; page?: number; size?: number }) {
  return useQuery({
    queryKey: QUERY_KEYS.abertos(params),
    queryFn: () => tendersService.listarEditaisAbertos(params),
    staleTime: 1000 * 60 * 5,
  });
}

// GET /tenders/participando
export function useListarEditaisParticipando(params?: { page?: number; size?: number }) {
  return useQuery({
    queryKey: QUERY_KEYS.participando(params),
    queryFn: () => tendersService.listarEditaisParticipando(params),
    staleTime: 1000 * 60 * 5,
  });
}

// GET /tenders/segmento/{segmento}
export function useListarEditaisPorSegmento(segmento: string, params?: { page?: number; size?: number }) {
  return useQuery({
    queryKey: QUERY_KEYS.segmento(segmento, params),
    queryFn: () => tendersService.listarEditaisPorSegmento(segmento, params),
    enabled: !!segmento,
    staleTime: 1000 * 60 * 5,
  });
}

// GET /tenders/{id}/documentos
export function useListarDocumentosEdital(tenderId: string, enabled = true) {
  return useQuery({
    queryKey: QUERY_KEYS.documentos(tenderId),
    queryFn: () => tendersService.listarDocumentosEdital(tenderId),
    enabled: enabled && !!tenderId,
    staleTime: 1000 * 60 * 5,
  });
}

// GET /tenders/pncp/status
export function useVerificarStatusPNCP(enabled = true) {
  return useQuery({
    queryKey: QUERY_KEYS.pncpStatus(),
    queryFn: () => tendersService.verificarStatusPNCP(),
    enabled,
    staleTime: 1000 * 60 * 30,
  });
}

// GET /tenders/pncp/buscar
export function useBuscarPNCP(params?: PNCPBuscarParams, enabled = false) {
  return useQuery({
    queryKey: QUERY_KEYS.pncp(params),
    queryFn: () => tendersService.buscarPNCP(params || {}),
    enabled,
    staleTime: 1000 * 60 * 10,
  });
}

// POST /tenders/
export function useCriarEdital() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: TenderCreate) => tendersService.criarEdital(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.lists() });
      toast.success('Edital criado com sucesso');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao criar edital');
    },
  });
}

// PUT /tenders/{id}
export function useAtualizarEdital() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: TenderUpdate }) =>
      tendersService.atualizarEdital(id, data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.lists() });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.detail(data.id) });
      toast.success('Edital atualizado com sucesso');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao atualizar edital');
    },
  });
}

// DELETE /tenders/{id}
export function useRemoverEdital() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (tenderId: string) => tendersService.removerEdital(tenderId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.lists() });
      toast.success('Edital removido com sucesso');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao remover edital');
    },
  });
}

// POST /tenders/{id}/participar
export function useMarcarParticipacao() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (params: MarcarParticipacaoParams) => tendersService.marcarParticipacao(params),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.lists() });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.detail(variables.tender_id) });
      toast.success('Participação registrada com sucesso');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao registrar participação');
    },
  });
}

// POST /tenders/{id}/status
export function useAlterarStatusEdital() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (params: AlterarStatusParams) => tendersService.alterarStatus(params),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.lists() });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.detail(variables.tender_id) });
      toast.success('Status alterado com sucesso');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao alterar status');
    },
  });
}

// POST /tenders/pncp/buscar (mutation)
export function useBuscarPNCPMutation() {
  return useMutation({
    mutationFn: (params: PNCPBuscarParams) => tendersService.buscarPNCP(params),
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao buscar no PNCP');
    },
  });
}

// POST /tenders/sync-pncp
export function useSincronizarPNCP() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (params?: { uf?: string; dias_retroativos?: number }) => tendersService.sincronizarPNCP(params),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.lists() });
      toast.success(`${data.total_sincronizado} editais sincronizados`);
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao sincronizar PNCP');
    },
  });
}
