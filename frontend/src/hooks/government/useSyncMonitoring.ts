'use client';

/**
 * Hooks React Query - Sync e Monitoring
 *
 * Hooks para sincronização de dados, certificados digitais e monitoramento
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { msgFromDetail } from '@/lib/string';
import { toast } from 'sonner';
import syncCertificatesService, {
  type IniciarExtracaoParams,
  type AgendamentoSyncParams,
  type UploadCertificadoParams,
  type JobExecutionParams,
} from '@/services/government/sync-certificates.service';

const QUERY_KEYS = {
  all: ['government', 'sync-monitoring'] as const,
  extracao: (id: string) => [...QUERY_KEYS.all, 'extracao', id] as const,
  historico: (filters?: any) => [...QUERY_KEYS.all, 'historico', filters] as const,
  agendamentos: () => [...QUERY_KEYS.all, 'agendamentos'] as const,
  certificados: () => [...QUERY_KEYS.all, 'certificados'] as const,
  certificado: (id: string) => [...QUERY_KEYS.all, 'certificado', id] as const,
  alertasCertificados: () => [...QUERY_KEYS.all, 'alertas-certificados'] as const,
  jobs: () => [...QUERY_KEYS.all, 'jobs'] as const,
  jobHistorico: (tipo: string) =>
    [...QUERY_KEYS.all, 'job-historico', tipo] as const,
  dashboard: () => [...QUERY_KEYS.all, 'dashboard'] as const,
  eventosRecentes: (limite?: number) =>
    [...QUERY_KEYS.all, 'eventos-recentes', limite] as const,
  health: () => [...QUERY_KEYS.all, 'health'] as const,
};

/**
 * Hook para iniciar extração de dados
 */
export function useIniciarExtracao() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: IniciarExtracaoParams) =>
      syncCertificatesService.iniciarExtracao(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.historico() });
      toast.success('Extração iniciada com sucesso');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao iniciar extração');
    },
  });
}

/**
 * Hook para sincronizar NF-e rapidamente
 */
export function useSincronizarNFeRapido() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params?: { periodo_dias?: number }) =>
      syncCertificatesService.sincronizarNFeRapido(params || {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.all });
      toast.success('Sincronização de NF-e iniciada');
    },
    onError: (error: any) => {
      toast.error(
        msgFromDetail(error?.response?.data?.detail) || 'Erro ao sincronizar NF-e'
      );
    },
  });
}

/**
 * Hook para sincronizar FGTS rapidamente
 */
export function useSincronizarFGTSRapido() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params?: { periodo_meses?: number }) =>
      syncCertificatesService.sincronizarFGTSRapido(params || {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.all });
      toast.success('Sincronização de FGTS iniciada');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao sincronizar FGTS');
    },
  });
}

/**
 * Hook para sincronizar todos os serviços
 */
export function useSincronizarTodosRapido() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => syncCertificatesService.sincronizarTodosRapido(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.all });
      toast.success('Sincronização completa iniciada');
    },
    onError: (error: any) => {
      toast.error(
        msgFromDetail(error?.response?.data?.detail) || 'Erro ao sincronizar todos os serviços'
      );
    },
  });
}

/**
 * Hook para consultar status de extração
 */
export function useConsultarStatusExtracao(
  params: { extracao_id: string },
  enabled = true
) {
  return useQuery({
    queryKey: QUERY_KEYS.extracao(params.extracao_id),
    queryFn: () => syncCertificatesService.consultarStatusExtracao(params),
    enabled: enabled && !!params.extracao_id,
    staleTime: 1000 * 10, // 10 segundos
    refetchInterval: 1000 * 30, // Atualiza a cada 30s enquanto em andamento
  });
}

/**
 * Hook para consultar histórico de extrações
 */
export function useConsultarHistoricoExtracoes(
  params?: { servico?: string; data_inicial?: string; data_final?: string },
  enabled = true
) {
  return useQuery({
    queryKey: QUERY_KEYS.historico(params),
    queryFn: () => syncCertificatesService.consultarHistoricoExtracoes(params),
    enabled,
    staleTime: 1000 * 60 * 5, // 5 minutos
  });
}

/**
 * Hook para agendar sincronização
 */
export function useAgendarSincronizacao() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: AgendamentoSyncParams) =>
      syncCertificatesService.agendarSincronizacao(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.agendamentos() });
      toast.success('Sincronização agendada com sucesso');
    },
    onError: (error: any) => {
      toast.error(
        msgFromDetail(error?.response?.data?.detail) || 'Erro ao agendar sincronização'
      );
    },
  });
}

/**
 * Hook para listar agendamentos
 */
export function useListarAgendamentos(enabled = true) {
  return useQuery({
    queryKey: QUERY_KEYS.agendamentos(),
    queryFn: () => syncCertificatesService.listarAgendamentos(),
    enabled,
    staleTime: 1000 * 60 * 5, // 5 minutos
  });
}

/**
 * Hook para executar sincronização em background
 */
export function useExecutarSyncBackground() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: { servico: string }) =>
      syncCertificatesService.executarSyncBackground(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.all });
      toast.success('Sincronização em background iniciada');
    },
    onError: (error: any) => {
      toast.error(
        msgFromDetail(error?.response?.data?.detail) || 'Erro ao executar sincronização'
      );
    },
  });
}

/**
 * Hook para upload de certificado digital
 */
export function useUploadCertificado() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: UploadCertificadoParams) =>
      syncCertificatesService.uploadCertificado(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.certificados() });
      toast.success('Certificado enviado com sucesso');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao enviar certificado');
    },
  });
}

/**
 * Hook para validar certificado digital
 */
export function useValidarCertificado() {
  return useMutation({
    mutationFn: (params: { arquivo: File; senha: string }) =>
      syncCertificatesService.validarCertificado(params),
    onSuccess: (data) => {
      if (data.is_valid) {
        toast.success('Certificado válido');
      } else {
        toast.warning('Certificado inválido ou expirado');
      }
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao validar certificado');
    },
  });
}

/**
 * Hook para listar certificados
 */
export function useListarCertificados(enabled = true) {
  return useQuery({
    queryKey: QUERY_KEYS.certificados(),
    queryFn: () => syncCertificatesService.listarCertificados(),
    enabled,
    staleTime: 1000 * 60 * 5, // 5 minutos
  });
}

/**
 * Hook para obter informações de certificado
 */
export function useObterInfoCertificado(
  params: { certificate_id: string },
  enabled = true
) {
  return useQuery({
    queryKey: QUERY_KEYS.certificado(params.certificate_id),
    queryFn: () => syncCertificatesService.obterInfoCertificado(params),
    enabled: enabled && !!params.certificate_id,
    staleTime: 1000 * 60 * 10, // 10 minutos
  });
}

/**
 * Hook para remover certificado
 */
export function useRemoverCertificado() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: { certificate_id: string }) =>
      syncCertificatesService.removerCertificado(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.certificados() });
      toast.success('Certificado removido com sucesso');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao remover certificado');
    },
  });
}

/**
 * Hook para testar assinatura com certificado
 */
export function useTestarAssinaturaCertificado() {
  return useMutation({
    mutationFn: (params: { certificate_id: string; texto: string }) =>
      syncCertificatesService.testarAssinaturaCertificado(params),
    onSuccess: (data) => {
      if (data.success) {
        toast.success('Assinatura testada com sucesso');
      }
    },
    onError: (error: any) => {
      toast.error(
        msgFromDetail(error?.response?.data?.detail) || 'Erro ao testar assinatura'
      );
    },
  });
}

/**
 * Hook para listar alertas de certificados
 */
export function useListarAlertasCertificados(enabled = true) {
  return useQuery({
    queryKey: QUERY_KEYS.alertasCertificados(),
    queryFn: () => syncCertificatesService.listarAlertasCertificados(),
    enabled,
    staleTime: 1000 * 60 * 30, // 30 minutos
    refetchInterval: 1000 * 60 * 60, // Atualiza a cada hora
  });
}

/**
 * Hook para listar jobs disponíveis
 */
export function useListarJobs(enabled = true) {
  return useQuery({
    queryKey: QUERY_KEYS.jobs(),
    queryFn: () => syncCertificatesService.listarJobs(),
    enabled,
    staleTime: 1000 * 60 * 10, // 10 minutos
  });
}

/**
 * Hook para executar job agora
 */
export function useExecutarJobAgora() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: { tipo: string }) =>
      syncCertificatesService.executarJobAgora(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.all });
      toast.success('Job executado com sucesso');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao executar job');
    },
  });
}

/**
 * Hook para consultar histórico de job
 */
export function useConsultarHistoricoJob(
  params: { tipo: string },
  enabled = true
) {
  return useQuery({
    queryKey: QUERY_KEYS.jobHistorico(params.tipo),
    queryFn: () => syncCertificatesService.consultarHistoricoJob(params),
    enabled: enabled && !!params.tipo,
    staleTime: 1000 * 60 * 5, // 5 minutos
  });
}

/**
 * Hook para obter dashboard de monitoramento
 */
export function useObterDashboardMonitoramento(enabled = true) {
  return useQuery({
    queryKey: QUERY_KEYS.dashboard(),
    queryFn: () => syncCertificatesService.obterDashboardMonitoramento(),
    enabled,
    staleTime: 1000 * 60, // 1 minuto
    refetchInterval: 1000 * 60 * 2, // Atualiza a cada 2 minutos
  });
}

/**
 * Hook para listar eventos recentes
 */
export function useListarEventosRecentes(
  params?: { limite?: number },
  enabled = true
) {
  return useQuery({
    queryKey: QUERY_KEYS.eventosRecentes(params?.limite),
    queryFn: () => syncCertificatesService.listarEventosRecentes(params),
    enabled,
    staleTime: 1000 * 30, // 30 segundos
    refetchInterval: 1000 * 60, // Atualiza a cada minuto
  });
}

/**
 * Hook para health check
 */
export function useHealthCheck(enabled = true) {
  return useQuery({
    queryKey: QUERY_KEYS.health(),
    queryFn: () => syncCertificatesService.healthCheck(),
    enabled,
    staleTime: 1000 * 60, // 1 minuto
    refetchInterval: 1000 * 60 * 5, // Atualiza a cada 5 minutos
  });
}
