'use client';

/**
 * Hooks React Query - NFS-e
 *
 * Hooks para emissão, consulta e cancelamento de NFS-e
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { msgFromDetail } from '@/lib/string';
import { toast } from 'sonner';
import nfseService, {
  type EmissaoNFSeParams,
  type CancelamentoNFSeParams,
  type ConsultaNFSeParams,
} from '@/services/government/nfse.service';

const QUERY_KEYS = {
  all: ['government', 'nfse'] as const,
  list: (filters?: ConsultaNFSeParams) => [...QUERY_KEYS.all, 'list', filters] as const,
  rps: (numero: string, serie: string) =>
    [...QUERY_KEYS.all, 'rps', numero, serie] as const,
  lote: (numeroLote: string) => [...QUERY_KEYS.all, 'lote', numeroLote] as const,
};

/**
 * Hook para emitir NFS-e Padrão Nacional
 */
export function useEmitirNFSeNacional() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: EmissaoNFSeParams) =>
      nfseService.emitirNFSeNacional(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.all });
      toast.success('NFS-e Padrão Nacional emitida com sucesso');
    },
    onError: (error: any) => {
      toast.error(error?.response?.msgFromDetail(data?.detail) || 'Erro ao emitir NFS-e');
    },
  });
}

/**
 * Hook para emitir NFS-e Manaus
 */
export function useEmitirNFSeManaus() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: EmissaoNFSeParams) =>
      nfseService.emitirNFSeManaus(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.all });
      toast.success('NFS-e Manaus emitida com sucesso');
    },
    onError: (error: any) => {
      toast.error(error?.response?.msgFromDetail(data?.detail) || 'Erro ao emitir NFS-e Manaus');
    },
  });
}

/**
 * Hook para cancelar NFS-e Padrão Nacional
 */
export function useCancelarNFSeNacional() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: CancelamentoNFSeParams) =>
      nfseService.cancelarNFSeNacional(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.all });
      toast.success('NFS-e cancelada com sucesso');
    },
    onError: (error: any) => {
      toast.error(error?.response?.msgFromDetail(data?.detail) || 'Erro ao cancelar NFS-e');
    },
  });
}

/**
 * Hook para cancelar NFS-e Manaus
 */
export function useCancelarNFSeManaus() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: CancelamentoNFSeParams) =>
      nfseService.cancelarNFSeManaus(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.all });
      toast.success('NFS-e Manaus cancelada com sucesso');
    },
    onError: (error: any) => {
      toast.error(
        error?.response?.msgFromDetail(data?.detail) || 'Erro ao cancelar NFS-e Manaus'
      );
    },
  });
}

/**
 * Hook para consultar NFS-e por RPS
 */
export function useConsultarNFSePorRPS(
  params: { numero_rps: string; serie_rps: string },
  enabled = true
) {
  return useQuery({
    queryKey: QUERY_KEYS.rps(params.numero_rps, params.serie_rps),
    queryFn: () => nfseService.consultarNFSePorRPS(params),
    enabled: enabled && !!params.numero_rps,
    staleTime: 1000 * 60 * 5, // 5 minutos
  });
}

/**
 * Hook para consultar lote de NFS-e
 */
export function useConsultarLoteNFSe(
  params: { numero_lote: string },
  enabled = true
) {
  return useQuery({
    queryKey: QUERY_KEYS.lote(params.numero_lote),
    queryFn: () => nfseService.consultarLoteNFSe(params),
    enabled: enabled && !!params.numero_lote,
    staleTime: 1000 * 60 * 5, // 5 minutos
  });
}

/**
 * Hook para listar NFS-e com filtros
 */
export function useListarNFSe(params?: ConsultaNFSeParams, enabled = true) {
  return useQuery({
    queryKey: QUERY_KEYS.list(params),
    queryFn: () => nfseService.listarNFSe(params || {}),
    enabled,
    staleTime: 1000 * 60 * 5, // 5 minutos
  });
}

/**
 * Hook mutation para consultar NFS-e por RPS sob demanda
 */
export function useConsultarNFSePorRPSMutation() {
  return useMutation({
    mutationFn: (params: { numero_rps: string; serie_rps: string }) =>
      nfseService.consultarNFSePorRPS(params),
    onSuccess: () => {
      toast.success('NFS-e consultada com sucesso');
    },
    onError: (error: any) => {
      toast.error(error?.response?.msgFromDetail(data?.detail) || 'Erro ao consultar NFS-e');
    },
  });
}
