'use client';

/**
 * Hooks React Query - FGTS e Simples Nacional
 *
 * Hooks para FGTS Digital, DCTFWeb e Simples Nacional
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { msgFromDetail } from '@/lib/string';
import { toast } from 'sonner';
import fgtsSimplesService, {
  type CalculoFGTSParams,
  type CalculoINSSParams,
  type EmissaoDPSParams,
} from '@/services/government/fgts-simples.service';

const QUERY_KEYS = {
  all: ['government', 'fgts-simples'] as const,
  debitosFGTS: (cnpj: string) => [...QUERY_KEYS.all, 'debitos-fgts', cnpj] as const,
  situacaoSimples: (cnpj: string) =>
    [...QUERY_KEYS.all, 'situacao-simples', cnpj] as const,
};

/**
 * Hook para calcular FGTS
 */
export function useCalcularFGTS() {
  return useMutation({
    mutationFn: (params: CalculoFGTSParams) =>
      fgtsSimplesService.calcularFGTS(params),
    onSuccess: () => {
      toast.success('FGTS calculado com sucesso');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao calcular FGTS');
    },
  });
}

/**
 * Hook para calcular INSS
 */
export function useCalcularINSS() {
  return useMutation({
    mutationFn: (params: CalculoINSSParams) =>
      fgtsSimplesService.calcularINSS(params),
    onSuccess: () => {
      toast.success('INSS calculado com sucesso');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao calcular INSS');
    },
  });
}

/**
 * Hook para emitir DPS (Declaração Previdenciária e Social)
 */
export function useEmitirDPS() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: EmissaoDPSParams) =>
      fgtsSimplesService.emitirDPS(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.all });
      toast.success('DPS emitida com sucesso');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao emitir DPS');
    },
  });
}

/**
 * Hook para consultar extrato FGTS
 */
export function useConsultarExtrato() {
  return useMutation({
    mutationFn: (params: {
      cpf: string;
      periodo_inicial: string;
      periodo_final: string;
    }) => fgtsSimplesService.consultarExtrato(params),
    onSuccess: () => {
      toast.success('Extrato FGTS consultado com sucesso');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao consultar extrato FGTS');
    },
  });
}

/**
 * Hook para gerar guia mensal FGTS
 */
export function useGerarGuiaMensal() {
  return useMutation({
    mutationFn: (params: { mes_referencia: string; ano_referencia: number }) =>
      fgtsSimplesService.gerarGuiaMensal(params),
    onSuccess: () => {
      toast.success('Guia mensal FGTS gerada com sucesso');
    },
    onError: (error: any) => {
      toast.error(
        msgFromDetail(error?.response?.data?.detail) || 'Erro ao gerar guia mensal FGTS'
      );
    },
  });
}

/**
 * Hook para calcular apuração do Simples Nacional
 */
export function useCalcularApuracaoSimples() {
  return useMutation({
    mutationFn: (params: {
      mes_referencia: string;
      ano_referencia: number;
      receita_bruta: number;
      anexo: string;
    }) => fgtsSimplesService.calcularApuracaoSimples(params),
    onSuccess: () => {
      toast.success('Apuração do Simples Nacional calculada');
    },
    onError: (error: any) => {
      toast.error(
        msgFromDetail(error?.response?.data?.detail) || 'Erro ao calcular apuração Simples Nacional'
      );
    },
  });
}

/**
 * Hook para calcular PGDAS-D
 */
export function useCalcularPGDASD() {
  return useMutation({
    mutationFn: (params: {
      mes_referencia: string;
      ano_referencia: number;
      receitas: Array<{ tipo: string; valor: number }>;
    }) => fgtsSimplesService.calcularPGDASD(params),
    onSuccess: () => {
      toast.success('PGDAS-D calculado com sucesso');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao calcular PGDAS-D');
    },
  });
}

/**
 * Hook para gerar DAS
 */
export function useGerarDAS() {
  return useMutation({
    mutationFn: (params: { mes_referencia: string; ano_referencia: number }) =>
      fgtsSimplesService.gerarDAS(params),
    onSuccess: () => {
      toast.success('DAS gerado com sucesso');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao gerar DAS');
    },
  });
}

/**
 * Hook para gerar DARFs
 */
export function useGerarDARFs() {
  return useMutation({
    mutationFn: (params: {
      mes_referencia: string;
      ano_referencia: number;
      impostos: Array<{ codigo_receita: string; valor: number }>;
    }) => fgtsSimplesService.gerarDARFs(params),
    onSuccess: () => {
      toast.success('DARFs geradas com sucesso');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao gerar DARFs');
    },
  });
}

/**
 * Hook para calcular Fator R
 */
export function useCalcularFatorR() {
  return useMutation({
    mutationFn: (params: {
      receita_bruta: number;
      folha_salarios: number;
      periodo_meses: number;
    }) => fgtsSimplesService.calcularFatorR(params),
    onSuccess: () => {
      toast.success('Fator R calculado com sucesso');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao calcular Fator R');
    },
  });
}

/**
 * Hook para consultar débitos FGTS
 */
export function useConsultarDebitosFGTS(
  params: { cnpj: string },
  enabled = true
) {
  return useQuery({
    queryKey: QUERY_KEYS.debitosFGTS(params.cnpj),
    queryFn: () => fgtsSimplesService.consultarDebitosFGTS(params),
    enabled: enabled && !!params.cnpj,
    staleTime: 1000 * 60 * 15, // 15 minutos
  });
}

/**
 * Hook para consultar situação no Simples Nacional
 */
export function useConsultarSituacaoSimples(
  params: { cnpj: string },
  enabled = true
) {
  return useQuery({
    queryKey: QUERY_KEYS.situacaoSimples(params.cnpj),
    queryFn: () => fgtsSimplesService.consultarSituacaoSimples(params),
    enabled: enabled && !!params.cnpj,
    staleTime: 1000 * 60 * 60, // 1 hora
  });
}
