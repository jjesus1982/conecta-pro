'use client';

/**
 * Hooks React Query - SEFAZ
 *
 * Hooks para NF-e, CT-e, MDF-e e documentos fiscais
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { msgFromDetail } from '@/lib/string';
import { toast } from 'sonner';
import sefazService, {
  type EmissaoNFeParams,
  type ConsultaNFeParams,
  type CancelamentoNFeParams,
} from '@/services/government/sefaz.service';
import type {
  CriarCTeRequest,
  CriarMDFeRequest,
  EncerrarMDFeRequest,
  IncluirCondutorRequest,
} from '@/types/generated/government';

const QUERY_KEYS = {
  all: ['government', 'sefaz'] as const,
  nfe: (chave: string) => [...QUERY_KEYS.all, 'nfe', chave] as const,
  status: (uf?: string) => [...QUERY_KEYS.all, 'status', uf] as const,
  dfe: (filters?: any) => [...QUERY_KEYS.all, 'dfe', filters] as const,
};

/**
 * Hook para emitir NF-e
 */
export function useEmitirNFe() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: EmissaoNFeParams) => sefazService.emitirNFe(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.all });
      toast.success('NF-e emitida com sucesso');
    },
    onError: (error: any) => {
      toast.error(error?.response?.msgFromDetail(data?.detail) || 'Erro ao emitir NF-e');
    },
  });
}

/**
 * Hook para consultar NF-e
 */
export function useConsultarNFe(params: ConsultaNFeParams, enabled = true) {
  return useQuery({
    queryKey: QUERY_KEYS.nfe(params.chave_acesso),
    queryFn: () => sefazService.consultarNFe(params),
    enabled: enabled && !!params.chave_acesso,
    staleTime: 1000 * 60 * 10, // 10 minutos
  });
}

/**
 * Hook para cancelar NF-e
 */
export function useCancelarNFe() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: CancelamentoNFeParams) =>
      sefazService.cancelarNFe(params),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: QUERY_KEYS.nfe(variables.chave_acesso),
      });
      toast.success('NF-e cancelada com sucesso');
    },
    onError: (error: any) => {
      toast.error(error?.response?.msgFromDetail(data?.detail) || 'Erro ao cancelar NF-e');
    },
  });
}

/**
 * Hook para emitir carta de correção
 */
export function useEmitirCartaCorrecao() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: { chave_acesso: string; correcao: string }) =>
      sefazService.emitirCartaCorrecao(params),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: QUERY_KEYS.nfe(variables.chave_acesso),
      });
      toast.success('Carta de Correção emitida com sucesso');
    },
    onError: (error: any) => {
      toast.error(
        error?.response?.msgFromDetail(data?.detail) || 'Erro ao emitir Carta de Correção'
      );
    },
  });
}

/**
 * Hook para inutilizar numeração de NF-e
 */
export function useInutilizarNumeracao() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: {
      serie: string;
      numero_inicial: number;
      numero_final: number;
      justificativa: string;
    }) => sefazService.inutilizarNumeracao(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.all });
      toast.success('Numeração inutilizada com sucesso');
    },
    onError: (error: any) => {
      toast.error(
        error?.response?.msgFromDetail(data?.detail) || 'Erro ao inutilizar numeração'
      );
    },
  });
}

/**
 * Hook para emitir CT-e
 */
export function useEmitirCTe() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: CriarCTeRequest) => sefazService.emitirCTe(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.all });
      toast.success('CT-e emitido com sucesso');
    },
    onError: (error: any) => {
      toast.error(error?.response?.msgFromDetail(data?.detail) || 'Erro ao emitir CT-e');
    },
  });
}

/**
 * Hook para cancelar CT-e
 */
export function useCancelarCTe() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: { chave_acesso: string; justificativa: string }) =>
      sefazService.cancelarCTe(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.all });
      toast.success('CT-e cancelado com sucesso');
    },
    onError: (error: any) => {
      toast.error(error?.response?.msgFromDetail(data?.detail) || 'Erro ao cancelar CT-e');
    },
  });
}

/**
 * Hook para emitir MDF-e
 */
export function useEmitirMDFe() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: CriarMDFeRequest) => sefazService.emitirMDFe(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.all });
      toast.success('MDF-e emitido com sucesso');
    },
    onError: (error: any) => {
      toast.error(error?.response?.msgFromDetail(data?.detail) || 'Erro ao emitir MDF-e');
    },
  });
}

/**
 * Hook para encerrar MDF-e
 */
export function useEncerrarMDFe() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: EncerrarMDFeRequest) =>
      sefazService.encerrarMDFe(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.all });
      toast.success('MDF-e encerrado com sucesso');
    },
    onError: (error: any) => {
      toast.error(error?.response?.msgFromDetail(data?.detail) || 'Erro ao encerrar MDF-e');
    },
  });
}

/**
 * Hook para incluir condutor em MDF-e
 */
export function useIncluirCondutor() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: IncluirCondutorRequest) =>
      sefazService.incluirCondutor(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.all });
      toast.success('Condutor incluído com sucesso');
    },
    onError: (error: any) => {
      toast.error(error?.response?.msgFromDetail(data?.detail) || 'Erro ao incluir condutor');
    },
  });
}

/**
 * Hook para consultar status do serviço SEFAZ
 */
export function useConsultarStatusServico(params?: { uf?: string }) {
  return useQuery({
    queryKey: QUERY_KEYS.status(params?.uf),
    queryFn: () => sefazService.consultarStatusServico(params),
    staleTime: 1000 * 60 * 5, // 5 minutos
    refetchInterval: 1000 * 60 * 5, // Atualiza a cada 5 minutos
  });
}

/**
 * Hook para consultar DFe destinadas
 */
export function useConsultarDFeDestinadas(
  params?: {
    data_inicial?: string;
    data_final?: string;
    nsu?: number;
  },
  enabled = true
) {
  return useQuery({
    queryKey: QUERY_KEYS.dfe(params),
    queryFn: () => sefazService.consultarDFeDestinadas(params),
    enabled,
    staleTime: 1000 * 60 * 10, // 10 minutos
  });
}

/**
 * Hook para gerar DANFE
 */
export function useGerarDANFE() {
  return useMutation({
    mutationFn: (params: { chave_acesso: string; formato?: 'pdf' | 'xml' }) =>
      sefazService.gerarDANFE(params),
    onSuccess: () => {
      toast.success('DANFE gerado com sucesso');
    },
    onError: (error: any) => {
      toast.error(error?.response?.msgFromDetail(data?.detail) || 'Erro ao gerar DANFE');
    },
  });
}

/**
 * Hook para gerar DANFE NFC-e
 */
export function useGerarDANFENFCe() {
  return useMutation({
    mutationFn: (params: { chave_acesso: string }) =>
      sefazService.gerarDANFENFCe(params),
    onSuccess: () => {
      toast.success('DANFE NFC-e gerado com sucesso');
    },
    onError: (error: any) => {
      toast.error(error?.response?.msgFromDetail(data?.detail) || 'Erro ao gerar DANFE NFC-e');
    },
  });
}
