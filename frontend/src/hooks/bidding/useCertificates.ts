'use client';

/**
 * Hooks React Query - Certificates (Certidões)
 *
 * Hooks para gestão de certidões negativas (federal, estadual, municipal, trabalhista)
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { msgFromDetail } from '@/lib/string';
import { toast } from 'sonner';
import certificatesService, {
  type ListCertificatesParams,
  type RenovarCertidoesParams,
  type AtualizarStatusParams,
} from '@/services/bidding/certificates.service';
import type {
  CertificateCreate,
  CertificateUpdate,
} from '@/types/generated/bidding';

const QUERY_KEYS = {
  all: ['bidding', 'certificates'] as const,
  lists: () => [...QUERY_KEYS.all, 'list'] as const,
  list: (params?: ListCertificatesParams) =>
    [...QUERY_KEYS.lists(), params] as const,
  details: () => [...QUERY_KEYS.all, 'detail'] as const,
  detail: (id: string) => [...QUERY_KEYS.details(), id] as const,
  statusByCnpj: (cnpj: string) => [...QUERY_KEYS.all, 'status', cnpj] as const,
  byCnpjType: (cnpj: string, tipo: string) =>
    [...QUERY_KEYS.all, 'cnpj', cnpj, tipo] as const,
  tipos: () => [...QUERY_KEYS.all, 'tipos'] as const,
  pendentes: (params?: any) => [...QUERY_KEYS.all, 'pendentes', params] as const,
};

/**
 * Hook para listar certidões com filtros
 */
export function useListarCertidoes(params?: ListCertificatesParams) {
  return useQuery({
    queryKey: QUERY_KEYS.list(params),
    queryFn: () => certificatesService.listarCertidoes(params),
    staleTime: 1000 * 60 * 5,
  });
}

/**
 * Hook para buscar certidão por ID
 */
export function useBuscarCertidao(certificateId: string, enabled = true) {
  return useQuery({
    queryKey: QUERY_KEYS.detail(certificateId),
    queryFn: () => certificatesService.buscarCertidaoPorId(certificateId),
    enabled: enabled && !!certificateId,
    staleTime: 1000 * 60 * 5,
  });
}

/**
 * Hook para criar nova certidão (upload manual)
 */
export function useCriarCertidao() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: CertificateCreate) =>
      certificatesService.criarCertidao(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.lists() });
      toast.success('Certidão criada com sucesso');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao criar certidão');
    },
  });
}

/**
 * Hook para atualizar certidão
 */
export function useAtualizarCertidao() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: CertificateUpdate }) =>
      certificatesService.atualizarCertidao(id, data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.lists() });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.detail(data.id) });
      toast.success('Certidão atualizada com sucesso');
    },
    onError: (error: any) => {
      toast.error(
        msgFromDetail(error?.response?.data?.detail) || 'Erro ao atualizar certidão'
      );
    },
  });
}

/**
 * Hook para remover certidão
 */
export function useRemoverCertidao() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (certificateId: string) =>
      certificatesService.removerCertidao(certificateId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.lists() });
      toast.success('Certidão removida com sucesso');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao remover certidão');
    },
  });
}

/**
 * Hook para buscar certidão específica por CNPJ e tipo
 */
export function useBuscarCertidaoPorCNPJeTipo(
  cnpj: string,
  tipo: string,
  enabled = true
) {
  return useQuery({
    queryKey: QUERY_KEYS.byCnpjType(cnpj, tipo),
    queryFn: () => certificatesService.buscarCertidaoPorCNPJeTipo(cnpj, tipo),
    enabled: enabled && !!cnpj && !!tipo,
    staleTime: 1000 * 60 * 5,
  });
}

/**
 * Hook para verificar status de todas as certidões de um CNPJ
 */
export function useVerificarStatusPorCNPJ(cnpj: string, enabled = true) {
  return useQuery({
    queryKey: QUERY_KEYS.statusByCnpj(cnpj),
    queryFn: () => certificatesService.verificarStatusPorCNPJ(cnpj),
    enabled: enabled && !!cnpj,
    staleTime: 1000 * 60 * 10,
  });
}

/**
 * Hook para listar tipos de certidões disponíveis
 */
export function useListarTipos() {
  return useQuery({
    queryKey: QUERY_KEYS.tipos(),
    queryFn: () => certificatesService.listarTipos(),
    staleTime: 1000 * 60 * 60, // 1 hora (raramente muda)
  });
}

/**
 * Hook para listar certidões pendentes de renovação
 */
export function useListarPendentesRenovacao(params?: {
  dias?: number;
  page?: number;
  size?: number;
}) {
  return useQuery({
    queryKey: QUERY_KEYS.pendentes(params),
    queryFn: () => certificatesService.listarPendentesRenovacao(params),
    staleTime: 1000 * 60 * 5,
  });
}

/**
 * Hook para renovar certidões automaticamente
 */
export function useRenovarCertidoes() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: RenovarCertidoesParams) =>
      certificatesService.renovarCertidoes(params),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.lists() });
      toast.success(data.message || 'Certidão renovada com sucesso');
    },
    onError: (error: any) => {
      toast.error(
        msgFromDetail(error?.response?.data?.detail) || 'Erro ao renovar certidões'
      );
    },
  });
}

/**
 * Hook para atualizar status de certidões em lote
 */
export function useAtualizarStatusEmLote() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: AtualizarStatusParams) =>
      certificatesService.atualizarStatusEmLote(params),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.lists() });
      toast.success(`${data.atualizados} certidões atualizadas com sucesso`);
    },
    onError: (error: any) => {
      toast.error(
        msgFromDetail(error?.response?.data?.detail) || 'Erro ao atualizar status em lote'
      );
    },
  });
}
