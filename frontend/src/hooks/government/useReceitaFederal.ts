'use client';

/**
 * Hooks React Query - Receita Federal
 *
 * Hooks para validação de documentos e consultas cadastrais
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { msgFromDetail } from '@/lib/string';
import { toast } from 'sonner';
import receitaFederalService, {
  type ValidacaoDocumentoParams,
  type ConsultaCPFParams,
  type ConsultaCNPJParams,
} from '@/services/government/receita-federal.service';

const QUERY_KEYS = {
  all: ['government', 'receita-federal'] as const,
  validacao: (documento: string) =>
    [...QUERY_KEYS.all, 'validacao', documento] as const,
  cpf: (cpf: string) => [...QUERY_KEYS.all, 'cpf', cpf] as const,
  cnpj: (cnpj: string) => [...QUERY_KEYS.all, 'cnpj', cnpj] as const,
};

/**
 * Hook para validar CPF ou CNPJ
 */
export function useValidarDocumento() {
  return useMutation({
    mutationFn: (params: ValidacaoDocumentoParams) =>
      receitaFederalService.validarDocumento(params),
    onSuccess: (data) => {
      if (data.success) {
        toast.success('Documento validado com sucesso');
      }
    },
    onError: (error: any) => {
      toast.error(error?.response?.msgFromDetail(data?.detail) || 'Erro ao validar documento');
    },
  });
}

/**
 * Hook para consultar situação cadastral de CPF
 */
export function useConsultarCPF(params: ConsultaCPFParams, enabled = true) {
  return useQuery({
    queryKey: QUERY_KEYS.cpf(params.cpf),
    queryFn: () => receitaFederalService.consultarCPF(params),
    enabled: enabled && !!params.cpf,
    staleTime: 1000 * 60 * 60, // 1 hora
    gcTime: 1000 * 60 * 60 * 24, // 24 horas
  });
}

/**
 * Hook mutation para consultar CPF sob demanda
 */
export function useConsultarCPFMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: ConsultaCPFParams) =>
      receitaFederalService.consultarCPF(params),
    onSuccess: (data, variables) => {
      queryClient.setQueryData(QUERY_KEYS.cpf(variables.cpf), data);
      toast.success('CPF consultado com sucesso');
    },
    onError: (error: any) => {
      toast.error(error?.response?.msgFromDetail(data?.detail) || 'Erro ao consultar CPF');
    },
  });
}

/**
 * Hook para consultar situação cadastral de CNPJ
 */
export function useConsultarCNPJ(params: ConsultaCNPJParams, enabled = true) {
  return useQuery({
    queryKey: QUERY_KEYS.cnpj(params.cnpj),
    queryFn: () => receitaFederalService.consultarCNPJ(params),
    enabled: enabled && !!params.cnpj,
    staleTime: 1000 * 60 * 60, // 1 hora
    gcTime: 1000 * 60 * 60 * 24, // 24 horas
  });
}

/**
 * Hook mutation para consultar CNPJ sob demanda
 */
export function useConsultarCNPJMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: ConsultaCNPJParams) =>
      receitaFederalService.consultarCNPJ(params),
    onSuccess: (data, variables) => {
      queryClient.setQueryData(QUERY_KEYS.cnpj(variables.cnpj), data);
      toast.success('CNPJ consultado com sucesso');
    },
    onError: (error: any) => {
      toast.error(error?.response?.msgFromDetail(data?.detail) || 'Erro ao consultar CNPJ');
    },
  });
}

/**
 * Hook para validar inscrição estadual
 */
export function useValidarInscricaoEstadual() {
  return useMutation({
    mutationFn: (params: { inscricao_estadual: string; uf: string }) =>
      receitaFederalService.validarInscricaoEstadual(params),
    onSuccess: (data) => {
      if (data.success) {
        toast.success('Inscrição Estadual validada com sucesso');
      }
    },
    onError: (error: any) => {
      toast.error(
        error?.response?.msgFromDetail(data?.detail) || 'Erro ao validar Inscrição Estadual'
      );
    },
  });
}
