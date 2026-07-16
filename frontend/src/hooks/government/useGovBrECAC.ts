'use client';

/**
 * Hooks React Query - Gov.br e e-CAC
 *
 * Hooks para autenticação Gov.br e consultas e-CAC
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { msgFromDetail } from '@/lib/string';
import { toast } from 'sonner';
import govbrEcacService, {
  type AutenticacaoGovBrParams,
  type CallbackGovBrParams,
  type ConsultaDebitosParams,
  type EmissaoCertidaoParams,
} from '@/services/government/govbr-ecac.service';

const QUERY_KEYS = {
  all: ['government', 'govbr-ecac'] as const,
  usuario: () => [...QUERY_KEYS.all, 'usuario'] as const,
  debitos: (filters?: ConsultaDebitosParams) =>
    [...QUERY_KEYS.all, 'debitos', filters] as const,
  declaracoes: (filters?: any) => [...QUERY_KEYS.all, 'declaracoes', filters] as const,
  parcelamentos: (filters?: any) =>
    [...QUERY_KEYS.all, 'parcelamentos', filters] as const,
  processos: (filters?: any) => [...QUERY_KEYS.all, 'processos', filters] as const,
  situacaoFiscal: (cpfCnpj?: string) =>
    [...QUERY_KEYS.all, 'situacao-fiscal', cpfCnpj] as const,
  malhaFiscal: (cpf: string, exercicio: number) =>
    [...QUERY_KEYS.all, 'malha-fiscal', cpf, exercicio] as const,
  restituicao: (cpf: string, exercicio: number) =>
    [...QUERY_KEYS.all, 'restituicao', cpf, exercicio] as const,
};

/**
 * Hook para gerar URL de autorização Gov.br
 */
export function useGerarUrlAutorizacao() {
  return useMutation({
    mutationFn: (params: AutenticacaoGovBrParams) =>
      govbrEcacService.gerarUrlAutorizacao(params),
    onSuccess: (data) => {
      // Redireciona para URL de autorização
      window.location.href = data.url;
    },
    onError: (error: any) => {
      toast.error(
        msgFromDetail(error?.response?.data?.detail) || 'Erro ao gerar URL de autorização Gov.br'
      );
    },
  });
}

/**
 * Hook para processar callback de autenticação
 */
export function useProcessarCallback() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: CallbackGovBrParams) =>
      govbrEcacService.processarCallback(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.usuario() });
      toast.success('Autenticação Gov.br realizada com sucesso');
    },
    onError: (error: any) => {
      toast.error(
        msgFromDetail(error?.response?.data?.detail) || 'Erro ao processar autenticação Gov.br'
      );
    },
  });
}

/**
 * Hook para gerar URL de logout
 */
export function useGerarUrlLogout() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: { post_logout_redirect_uri: string }) =>
      govbrEcacService.gerarUrlLogout(params),
    onSuccess: (data) => {
      queryClient.clear();
      window.location.href = data.url;
    },
    onError: (error: any) => {
      toast.error(
        msgFromDetail(error?.response?.data?.detail) || 'Erro ao gerar URL de logout Gov.br'
      );
    },
  });
}

/**
 * Hook para obter dados do usuário autenticado
 */
export function useObterDadosUsuario(enabled = true) {
  return useQuery({
    queryKey: QUERY_KEYS.usuario(),
    queryFn: () => govbrEcacService.obterDadosUsuario(),
    enabled,
    staleTime: 1000 * 60 * 30, // 30 minutos
  });
}

/**
 * Hook para consultar débitos
 */
export function useConsultarDebitos(
  params?: ConsultaDebitosParams,
  enabled = true
) {
  return useQuery({
    queryKey: QUERY_KEYS.debitos(params),
    queryFn: () => govbrEcacService.consultarDebitos(params),
    enabled,
    staleTime: 1000 * 60 * 15, // 15 minutos
  });
}

/**
 * Hook para consultar declarações
 */
export function useConsultarDeclaracoes(
  params?: { exercicio?: number; tipo?: string },
  enabled = true
) {
  return useQuery({
    queryKey: QUERY_KEYS.declaracoes(params),
    queryFn: () => govbrEcacService.consultarDeclaracoes(params),
    enabled,
    staleTime: 1000 * 60 * 30, // 30 minutos
  });
}

/**
 * Hook para consultar parcelamentos
 */
export function useConsultarParcelamentos(
  params?: { situacao?: 'ativo' | 'quitado' | 'cancelado' },
  enabled = true
) {
  return useQuery({
    queryKey: QUERY_KEYS.parcelamentos(params),
    queryFn: () => govbrEcacService.consultarParcelamentos(params),
    enabled,
    staleTime: 1000 * 60 * 15, // 15 minutos
  });
}

/**
 * Hook para consultar processos
 */
export function useConsultarProcessos(
  params?: { tipo?: string; situacao?: string },
  enabled = true
) {
  return useQuery({
    queryKey: QUERY_KEYS.processos(params),
    queryFn: () => govbrEcacService.consultarProcessos(params),
    enabled,
    staleTime: 1000 * 60 * 15, // 15 minutos
  });
}

/**
 * Hook para consultar situação fiscal
 */
export function useConsultarSituacaoFiscal(
  params?: { cpf_cnpj?: string },
  enabled = true
) {
  return useQuery({
    queryKey: QUERY_KEYS.situacaoFiscal(params?.cpf_cnpj),
    queryFn: () => govbrEcacService.consultarSituacaoFiscal(params),
    enabled,
    staleTime: 1000 * 60 * 15, // 15 minutos
  });
}

/**
 * Hook para emitir certidão
 */
export function useEmitirCertidao() {
  return useMutation({
    mutationFn: (params: EmissaoCertidaoParams) =>
      govbrEcacService.emitirCertidao(params),
    onSuccess: () => {
      toast.success('Certidão emitida com sucesso');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao emitir certidão');
    },
  });
}

/**
 * Hook para validar certidão
 */
export function useValidarCertidao() {
  return useMutation({
    mutationFn: (params: { codigo_validacao: string; cpf_cnpj: string }) =>
      govbrEcacService.validarCertidao(params),
    onSuccess: (data) => {
      if (data.success) {
        toast.success('Certidão validada com sucesso');
      } else {
        toast.warning('Certidão inválida ou expirada');
      }
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao validar certidão');
    },
  });
}

/**
 * Hook para consultar malha fiscal (IRPF)
 */
export function useConsultarMalhaFiscal(
  params: { cpf: string; exercicio: number },
  enabled = true
) {
  return useQuery({
    queryKey: QUERY_KEYS.malhaFiscal(params.cpf, params.exercicio),
    queryFn: () => govbrEcacService.consultarMalhaFiscal(params),
    enabled: enabled && !!params.cpf,
    staleTime: 1000 * 60 * 60, // 1 hora
  });
}

/**
 * Hook para consultar restituição IRPF
 */
export function useConsultarRestituicao(
  params: { cpf: string; exercicio: number },
  enabled = true
) {
  return useQuery({
    queryKey: QUERY_KEYS.restituicao(params.cpf, params.exercicio),
    queryFn: () => govbrEcacService.consultarRestituicao(params),
    enabled: enabled && !!params.cpf,
    staleTime: 1000 * 60 * 60, // 1 hora
  });
}
