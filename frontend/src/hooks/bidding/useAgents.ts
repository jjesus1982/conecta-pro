'use client';

/**
 * Hooks React Query - AI Agents (Agentes IA de Licitações)
 * 7 agentes especializados para automação de licitações
 */

import { useQuery, useMutation } from '@tanstack/react-query';
import { msgFromDetail } from '@/lib/string';
import { toast } from 'sonner';
import agentsService, {
  type ScoutRequest,
  type AnalystRequest,
  type AssessorRequest,
  type PricerRequest,
  type PipelineRequest,
} from '@/services/bidding/agents.service';

const QUERY_KEYS = {
  all: ['bidding', 'agents'] as const,
  status: () => [...QUERY_KEYS.all, 'status'] as const,
  portais: () => [...QUERY_KEYS.all, 'portais'] as const,
  sentinelTipos: () => [...QUERY_KEYS.all, 'sentinel', 'tipos'] as const,
  warriorStatus: () => [...QUERY_KEYS.all, 'warrior', 'status'] as const,
};

// GET /agents/status
export function useAgentsStatus(enabled = true) {
  return useQuery({
    queryKey: QUERY_KEYS.status(),
    queryFn: () => agentsService.getStatus(),
    enabled,
    staleTime: 1000 * 60 * 5,
  });
}

// GET /agents/scout/portais
export function useScoutPortais(enabled = true) {
  return useQuery({
    queryKey: QUERY_KEYS.portais(),
    queryFn: () => agentsService.scoutPortais(),
    enabled,
    staleTime: 1000 * 60 * 30,
  });
}

// POST /agents/scout/buscar
export function useScoutBuscar() {
  return useMutation({
    mutationFn: (params: ScoutRequest) => agentsService.scoutBuscar(params),
    onSuccess: (data) => {
      toast.success(`${data.total_encontrados} oportunidades encontradas`);
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro na busca do Scout');
    },
  });
}

// POST /agents/analyst/analisar
export function useAnalystAnalisar() {
  return useMutation({
    mutationFn: (params: AnalystRequest) => agentsService.analystAnalisar(params),
    onSuccess: () => {
      toast.success('Analise concluida com sucesso');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro na analise do Analyst');
    },
  });
}

// POST /agents/assessor/avaliar
export function useAssessorAvaliar() {
  return useMutation({
    mutationFn: (params: AssessorRequest) => agentsService.assessorAvaliar(params),
    onSuccess: (data) => {
      const msg =
        data.recomendacao === 'GO'
          ? 'Recomendado participar!'
          : data.recomendacao === 'NO_GO'
          ? 'Nao recomendado participar'
          : 'Participacao condicional';
      toast.info(msg);
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro na avaliacao do Assessor');
    },
  });
}

// POST /agents/pricer/calcular
export function usePricerCalcular() {
  return useMutation({
    mutationFn: (params: PricerRequest) => agentsService.pricerCalcular(params),
    onSuccess: () => {
      toast.success('Precificacao calculada com sucesso');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro no calculo do Pricer');
    },
  });
}

// POST /agents/pipeline
export function usePipelineCompleto() {
  return useMutation({
    mutationFn: (params: PipelineRequest) => agentsService.pipeline(params),
    onSuccess: (data) => {
      if (data.recomendacao === 'GO') {
        toast.success('Pipeline concluido - Participacao RECOMENDADA!');
      } else if (data.recomendacao === 'NO_GO') {
        toast.warning('Pipeline concluido - Participacao NAO recomendada');
      } else {
        toast.info(`Pipeline concluido - ${data.status}`);
      }
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro no pipeline');
    },
  });
}

// GET /agents/sentinel/tipos
export function useSentinelTipos(enabled = true) {
  return useQuery({
    queryKey: QUERY_KEYS.sentinelTipos(),
    queryFn: () => agentsService.sentinelTipos(),
    enabled,
    staleTime: 1000 * 60 * 60, // 1 hora
  });
}

// POST /agents/sentinel/verificar
export function useSentinelVerificar() {
  return useMutation({
    mutationFn: (cnpj?: string) => agentsService.sentinelVerificar(cnpj),
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao verificar certidoes');
    },
  });
}

// POST /agents/sentinel/alertas
export function useSentinelAlertas() {
  return useMutation({
    mutationFn: ({ cnpj, dias }: { cnpj?: string; dias?: number }) =>
      agentsService.sentinelAlertas(cnpj, dias),
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao gerar alertas');
    },
  });
}

// GET /agents/warrior/status
export function useWarriorStatus(enabled = true) {
  return useQuery({
    queryKey: QUERY_KEYS.warriorStatus(),
    queryFn: () => agentsService.warriorStatus(),
    enabled,
    staleTime: 1000 * 30, // 30 seconds
  });
}
