'use client';

/**
 * Hooks React Query - eSocial
 *
 * Hooks para eventos eSocial e folha de pagamento
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { msgFromDetail } from '@/lib/string';
import { toast } from 'sonner';
import esocialService, {
  type EventoESocialParams,
  type ConfiguracaoEmpresaParams,
  type CalculoFolhaParams,
} from '@/services/government/esocial.service';

const QUERY_KEYS = {
  all: ['government', 'esocial'] as const,
  eventos: (filters?: any) => [...QUERY_KEYS.all, 'eventos', filters] as const,
  evento: (id: string) => [...QUERY_KEYS.all, 'evento', id] as const,
  tabelaEventos: () => [...QUERY_KEYS.all, 'tabela-eventos'] as const,
};

/**
 * Hook para enviar evento eSocial
 */
export function useEnviarEvento() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: EventoESocialParams) =>
      esocialService.enviarEvento(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.all });
      toast.success('Evento eSocial enviado com sucesso');
    },
    onError: (error: any) => {
      toast.error(
        msgFromDetail(error?.response?.data?.detail) || 'Erro ao enviar evento eSocial'
      );
    },
  });
}

/**
 * Hook para consultar evento eSocial específico
 */
export function useConsultarEvento(
  params: { evento_id: string },
  enabled = true
) {
  return useQuery({
    queryKey: QUERY_KEYS.evento(params.evento_id),
    queryFn: () => esocialService.consultarEvento(params),
    enabled: enabled && !!params.evento_id,
    staleTime: 1000 * 60 * 5, // 5 minutos
    refetchInterval: 1000 * 30, // Atualiza a cada 30s (para acompanhar status)
  });
}

/**
 * Hook para listar eventos eSocial
 */
export function useListarEventos(
  params?: {
    tipo_evento?: string;
    data_inicial?: string;
    data_final?: string;
    status?: string;
  },
  enabled = true
) {
  return useQuery({
    queryKey: QUERY_KEYS.eventos(params),
    queryFn: () => esocialService.listarEventos(params),
    enabled,
    staleTime: 1000 * 60 * 5, // 5 minutos
  });
}

/**
 * Hook para configurar empresa no eSocial (S-1000)
 */
export function useConfigurarEmpresa() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: ConfiguracaoEmpresaParams) =>
      esocialService.configurarEmpresa(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.all });
      toast.success('Empresa configurada no eSocial com sucesso');
    },
    onError: (error: any) => {
      toast.error(
        msgFromDetail(error?.response?.data?.detail) || 'Erro ao configurar empresa no eSocial'
      );
    },
  });
}

/**
 * Hook para calcular folha de pagamento
 */
export function useCalcularFolha() {
  return useMutation({
    mutationFn: (params: CalculoFolhaParams) =>
      esocialService.calcularFolha(params),
    onSuccess: () => {
      toast.success('Folha de pagamento calculada com sucesso');
    },
    onError: (error: any) => {
      toast.error(
        msgFromDetail(error?.response?.data?.detail) || 'Erro ao calcular folha de pagamento'
      );
    },
  });
}

/**
 * Hook para validar evento eSocial antes de enviar
 */
export function useValidarEvento() {
  return useMutation({
    mutationFn: (params: {
      tipo_evento: string;
      dados_evento: Record<string, any>;
    }) => esocialService.validarEvento(params),
    onSuccess: (data) => {
      if (data.success) {
        toast.success('Evento validado com sucesso');
      } else {
        toast.warning('Evento possui inconsistências');
      }
    },
    onError: (error: any) => {
      toast.error(
        msgFromDetail(error?.response?.data?.detail) || 'Erro ao validar evento eSocial'
      );
    },
  });
}

/**
 * Hook para consultar tabela de eventos eSocial
 */
export function useConsultarTabelaEventos(enabled = true) {
  return useQuery({
    queryKey: QUERY_KEYS.tabelaEventos(),
    queryFn: () => esocialService.consultarTabelaEventos(),
    enabled,
    staleTime: 1000 * 60 * 60 * 24, // 24 horas (não muda com frequência)
  });
}

/**
 * Hook para gerar lote de eventos
 */
export function useGerarLoteEventos() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: { eventos: EventoESocialParams[] }) =>
      esocialService.gerarLoteEventos(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.all });
      toast.success('Lote de eventos gerado com sucesso');
    },
    onError: (error: any) => {
      toast.error(
        msgFromDetail(error?.response?.data?.detail) || 'Erro ao gerar lote de eventos'
      );
    },
  });
}
