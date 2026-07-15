'use client';

/**
 * Hooks React Query - SPED
 *
 * Hooks para SPED Fiscal, Contábil e EFD-Reinf
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { msgFromDetail } from '@/lib/string';
import { toast } from 'sonner';
import spedService, {
  type DocumentoFiscalParams,
  type InventarioParams,
  type LancamentoContabilParams,
} from '@/services/government/sped.service';
import type {
  DefinirBalancoRequest,
  DefinirDRERequest,
  GerarR1000Request,
  GerarR2010Request,
  GerarR2099Request,
  GerarR4010Request,
  GerarR4020Request,
  ImportarReinfRequest,
} from '@/types/generated/government';

const QUERY_KEYS = {
  all: ['government', 'sped'] as const,
  fiscal: () => [...QUERY_KEYS.all, 'fiscal'] as const,
  contabil: () => [...QUERY_KEYS.all, 'contabil'] as const,
  reinf: () => [...QUERY_KEYS.all, 'reinf'] as const,
};

/**
 * Hook para adicionar documento fiscal ao SPED
 */
export function useAdicionarDocumentoFiscal() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: DocumentoFiscalParams) =>
      spedService.adicionarDocumentoFiscal(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.fiscal() });
      toast.success('Documento fiscal adicionado ao SPED');
    },
    onError: (error: any) => {
      toast.error(
        error?.response?.msgFromDetail(data?.detail) || 'Erro ao adicionar documento fiscal'
      );
    },
  });
}

/**
 * Hook para adicionar inventário
 */
export function useAdicionarInventario() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: InventarioParams) =>
      spedService.adicionarInventario(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.fiscal() });
      toast.success('Inventário adicionado com sucesso');
    },
    onError: (error: any) => {
      toast.error(error?.response?.msgFromDetail(data?.detail) || 'Erro ao adicionar inventário');
    },
  });
}

/**
 * Hook para adicionar produto
 */
export function useAdicionarProduto() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: {
      codigo: string;
      descricao: string;
      ncm: string;
      unidade: string;
    }) => spedService.adicionarProduto(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.fiscal() });
      toast.success('Produto adicionado ao cadastro');
    },
    onError: (error: any) => {
      toast.error(error?.response?.msgFromDetail(data?.detail) || 'Erro ao adicionar produto');
    },
  });
}

/**
 * Hook para gerar arquivo SPED Fiscal
 */
export function useGerarArquivoSpedFiscal() {
  return useMutation({
    mutationFn: (params: { mes_referencia: string; ano_referencia: number }) =>
      spedService.gerarArquivoSpedFiscal(params),
    onSuccess: () => {
      toast.success('Arquivo SPED Fiscal gerado com sucesso');
    },
    onError: (error: any) => {
      toast.error(
        error?.response?.msgFromDetail(data?.detail) || 'Erro ao gerar arquivo SPED Fiscal'
      );
    },
  });
}

/**
 * Hook para adicionar conta contábil
 */
export function useAdicionarContaContabil() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: {
      codigo: string;
      nome: string;
      tipo: string;
      nivel: number;
    }) => spedService.adicionarContaContabil(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.contabil() });
      toast.success('Conta contábil adicionada');
    },
    onError: (error: any) => {
      toast.error(
        error?.response?.msgFromDetail(data?.detail) || 'Erro ao adicionar conta contábil'
      );
    },
  });
}

/**
 * Hook para adicionar lançamento contábil
 */
export function useAdicionarLancamento() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: LancamentoContabilParams) =>
      spedService.adicionarLancamento(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.contabil() });
      toast.success('Lançamento contábil adicionado');
    },
    onError: (error: any) => {
      toast.error(
        error?.response?.msgFromDetail(data?.detail) || 'Erro ao adicionar lançamento contábil'
      );
    },
  });
}

/**
 * Hook para definir balanço patrimonial
 */
export function useDefinirBalanco() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: DefinirBalancoRequest) =>
      spedService.definirBalanco(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.contabil() });
      toast.success('Balanço patrimonial definido');
    },
    onError: (error: any) => {
      toast.error(
        error?.response?.msgFromDetail(data?.detail) || 'Erro ao definir balanço patrimonial'
      );
    },
  });
}

/**
 * Hook para definir DRE
 */
export function useDefinirDRE() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: DefinirDRERequest) => spedService.definirDRE(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.contabil() });
      toast.success('DRE definida com sucesso');
    },
    onError: (error: any) => {
      toast.error(error?.response?.msgFromDetail(data?.detail) || 'Erro ao definir DRE');
    },
  });
}

/**
 * Hook para gerar arquivo SPED Contábil
 */
export function useGerarArquivoSpedContabil() {
  return useMutation({
    mutationFn: (params: { mes_referencia: string; ano_referencia: number }) =>
      spedService.gerarArquivoSpedContabil(params),
    onSuccess: () => {
      toast.success('Arquivo SPED Contábil gerado com sucesso');
    },
    onError: (error: any) => {
      toast.error(
        error?.response?.msgFromDetail(data?.detail) || 'Erro ao gerar arquivo SPED Contábil'
      );
    },
  });
}

/**
 * Hook para gerar evento R-1000 da EFD-Reinf
 */
export function useGerarR1000() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: GerarR1000Request) => spedService.gerarR1000(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.reinf() });
      toast.success('Evento R-1000 gerado com sucesso');
    },
    onError: (error: any) => {
      toast.error(error?.response?.msgFromDetail(data?.detail) || 'Erro ao gerar evento R-1000');
    },
  });
}

/**
 * Hook para gerar evento R-2010 da EFD-Reinf
 */
export function useGerarR2010() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: GerarR2010Request) => spedService.gerarR2010(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.reinf() });
      toast.success('Evento R-2010 gerado com sucesso');
    },
    onError: (error: any) => {
      toast.error(error?.response?.msgFromDetail(data?.detail) || 'Erro ao gerar evento R-2010');
    },
  });
}

/**
 * Hook para gerar evento R-2099 da EFD-Reinf
 */
export function useGerarR2099() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: GerarR2099Request) => spedService.gerarR2099(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.reinf() });
      toast.success('Evento R-2099 (Fechamento) gerado com sucesso');
    },
    onError: (error: any) => {
      toast.error(error?.response?.msgFromDetail(data?.detail) || 'Erro ao gerar evento R-2099');
    },
  });
}

/**
 * Hook para gerar evento R-4010 da EFD-Reinf
 */
export function useGerarR4010() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: GerarR4010Request) => spedService.gerarR4010(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.reinf() });
      toast.success('Evento R-4010 gerado com sucesso');
    },
    onError: (error: any) => {
      toast.error(error?.response?.msgFromDetail(data?.detail) || 'Erro ao gerar evento R-4010');
    },
  });
}

/**
 * Hook para gerar evento R-4020 da EFD-Reinf
 */
export function useGerarR4020() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: GerarR4020Request) => spedService.gerarR4020(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.reinf() });
      toast.success('Evento R-4020 gerado com sucesso');
    },
    onError: (error: any) => {
      toast.error(error?.response?.msgFromDetail(data?.detail) || 'Erro ao gerar evento R-4020');
    },
  });
}

/**
 * Hook para importar arquivo EFD-Reinf
 */
export function useImportarReinf() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: ImportarReinfRequest) =>
      spedService.importarReinf(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.reinf() });
      toast.success('Arquivo EFD-Reinf importado com sucesso');
    },
    onError: (error: any) => {
      toast.error(
        error?.response?.msgFromDetail(data?.detail) || 'Erro ao importar arquivo EFD-Reinf'
      );
    },
  });
}

/**
 * Hook para validar arquivo SPED
 */
export function useValidarSped() {
  return useMutation({
    mutationFn: (params: {
      tipo: 'fiscal' | 'contabil' | 'reinf';
      mes_referencia: string;
      ano_referencia: number;
    }) => spedService.validarSped(params),
    onSuccess: (data) => {
      if (data.success) {
        toast.success('Arquivo SPED validado com sucesso');
      } else {
        toast.warning('Arquivo SPED possui inconsistências');
      }
    },
    onError: (error: any) => {
      toast.error(error?.response?.msgFromDetail(data?.detail) || 'Erro ao validar arquivo SPED');
    },
  });
}
