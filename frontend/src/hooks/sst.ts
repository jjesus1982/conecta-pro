/**
 * Hooks React Query - SST (Saude e Seguranca do Trabalho)
 * Afastamentos, CAT, Estabilidade, Ajuda Medicamento
 *
 * @module hooks/sst
 * @author Conecta PRO Team
 * @date 2026-03-16
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  sstService,
  type AfastamentoCreate,
  type ASOAgendarLoteItem,
  type ASOResultadoPayload,
  type CATCreate,
  type EPIEntregaCreate,
  type FichaEPIGerarPayload,
  type FichaEPIStatus,
  type LTCATUpdatePayload,
  type TreinamentoNRCreate,
} from '@/lib/services/sst';

// =============================================================================
// QUERY KEYS
// =============================================================================

export const sstKeys = {
  all: ['sst'] as const,
  dashboard: () => [...sstKeys.all, 'dashboard'] as const,
  afastamentos: () => [...sstKeys.all, 'afastamentos'] as const,
  afastamento: (id: string) => [...sstKeys.afastamentos(), id] as const,
  cats: () => [...sstKeys.all, 'cats'] as const,
  taxaAcidente: () => [...sstKeys.all, 'taxa-acidente'] as const,
  estabilidade: () => [...sstKeys.all, 'estabilidade'] as const,
  ajudaMedicamento: () => [...sstKeys.all, 'ajuda-medicamento'] as const,
  ltcat: () => [...sstKeys.all, 'ltcat'] as const,
  asos: () => [...sstKeys.all, 'asos'] as const,
  entregasEPI: () => [...sstKeys.all, 'entregas-epi'] as const,
  fichasEPI: () => [...sstKeys.all, 'fichas-epi'] as const,
  nr1Compliance: () => [...sstKeys.all, 'nr1-compliance'] as const,
  regularizacao: () => [...sstKeys.all, 'asos-regularizacao'] as const,
  treinamentos: () => [...sstKeys.all, 'treinamentos'] as const,
};

// =============================================================================
// DASHBOARD
// =============================================================================

/**
 * Hook para dashboard SST
 */
export function useSSTDashboard() {
  return useQuery({
    queryKey: sstKeys.dashboard(),
    queryFn: () => sstService.getDashboard(),
    staleTime: 5 * 60 * 1000,
  });
}

// =============================================================================
// AFASTAMENTOS - QUERIES
// =============================================================================

/**
 * Hook para listar afastamentos
 */
export function useAfastamentos(status?: string) {
  return useQuery({
    queryKey: [...sstKeys.afastamentos(), status],
    queryFn: () => sstService.listAfastamentos(status),
    staleTime: 2 * 60 * 1000,
  });
}

/**
 * Hook para buscar afastamento por ID
 */
export function useAfastamento(id: string | null) {
  return useQuery({
    queryKey: sstKeys.afastamento(id!),
    queryFn: () => sstService.getAfastamento(id!),
    enabled: !!id,
    staleTime: 5 * 60 * 1000,
  });
}

// =============================================================================
// AFASTAMENTOS - MUTATIONS
// =============================================================================

/**
 * Hook para criar afastamento
 */
export function useCreateAfastamento() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: AfastamentoCreate) =>
      sstService.createAfastamento(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: sstKeys.afastamentos() });
      queryClient.invalidateQueries({ queryKey: sstKeys.dashboard() });
      queryClient.invalidateQueries({ queryKey: sstKeys.ajudaMedicamento() });
      queryClient.invalidateQueries({ queryKey: sstKeys.estabilidade() });
    },
  });
}

/**
 * Hook para registrar retorno de afastamento
 */
export function useRegistrarRetorno() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data_retorno }: { id: string; data_retorno: string }) =>
      sstService.registrarRetorno(id, data_retorno),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: sstKeys.afastamento(id) });
      queryClient.invalidateQueries({ queryKey: sstKeys.afastamentos() });
      queryClient.invalidateQueries({ queryKey: sstKeys.dashboard() });
      queryClient.invalidateQueries({ queryKey: sstKeys.estabilidade() });
    },
  });
}

// =============================================================================
// CAT - QUERIES
// =============================================================================

/**
 * Hook para listar CATs
 */
export function useCATs(employee_id?: string) {
  return useQuery({
    queryKey: [...sstKeys.cats(), employee_id],
    queryFn: () => sstService.listCATs(employee_id),
    staleTime: 2 * 60 * 1000,
  });
}

/**
 * Hook para taxa de acidente
 */
export function useTaxaAcidente() {
  return useQuery({
    queryKey: sstKeys.taxaAcidente(),
    queryFn: () => sstService.getTaxaAcidente(),
    staleTime: 10 * 60 * 1000,
  });
}

// =============================================================================
// CAT - MUTATIONS
// =============================================================================

/**
 * Hook para criar CAT
 */
export function useCreateCAT() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CATCreate) => sstService.createCAT(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: sstKeys.cats() });
      queryClient.invalidateQueries({ queryKey: sstKeys.taxaAcidente() });
      queryClient.invalidateQueries({ queryKey: sstKeys.dashboard() });
    },
  });
}

/**
 * Hook para transmitir CAT ao eSocial (S-2210)
 */
export function useTransmitirCAT() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (catId: string) => sstService.transmitirCAT(catId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: sstKeys.cats() });
    },
  });
}

// =============================================================================
// ASO (eSocial S-2220)
// =============================================================================

/**
 * Hook para listar ASOs com status eSocial
 */
export function useASOs() {
  return useQuery({
    queryKey: sstKeys.asos(),
    queryFn: () => sstService.listASOs(),
    staleTime: 2 * 60 * 1000,
  });
}

/**
 * Hook para registrar o resultado de um ASO realizado (gatilho eSocial S-2220)
 */
export function useRegistrarResultadoASO() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ asoId, data }: { asoId: string; data: ASOResultadoPayload }) =>
      sstService.registrarResultadoASO(asoId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: sstKeys.asos() });
      queryClient.invalidateQueries({ queryKey: sstKeys.dashboard() });
      queryClient.invalidateQueries({ queryKey: sstKeys.nr1Compliance() });
    },
  });
}

// =============================================================================
// REGULARIZAÇÃO DE ASOs VENCIDAS
// =============================================================================

/**
 * Hook para o plano de regularização das ASOs vencidas (lista priorizada)
 */
export function useASOsRegularizacao() {
  return useQuery({
    queryKey: sstKeys.regularizacao(),
    queryFn: () => sstService.getASOsRegularizacao(),
    staleTime: 60 * 1000,
  });
}

/**
 * Hook para agendar ASOs em lote (regularização em massa)
 */
export function useAgendarASOsLote() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (itens: ASOAgendarLoteItem[]) => sstService.agendarASOsLote(itens),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: sstKeys.regularizacao() });
      queryClient.invalidateQueries({ queryKey: sstKeys.asos() });
      queryClient.invalidateQueries({ queryKey: sstKeys.dashboard() });
    },
  });
}

// =============================================================================
// TREINAMENTOS NR (sst_treinamentos)
// =============================================================================

/**
 * Hook para listar treinamentos NR
 */
export function useTreinamentos(filters?: {
  employee_id?: string;
  norma?: string;
  vencendo_em_dias?: number;
}) {
  return useQuery({
    queryKey: [...sstKeys.treinamentos(), filters],
    queryFn: () => sstService.listTreinamentos(filters),
    staleTime: 60 * 1000,
  });
}

/**
 * Hook para registrar treinamento NR realizado
 */
export function useCriarTreinamento() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: TreinamentoNRCreate) => sstService.criarTreinamento(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: sstKeys.treinamentos() });
      queryClient.invalidateQueries({ queryKey: sstKeys.nr1Compliance() });
    },
  });
}

/**
 * Hook para excluir registro de treinamento (correção de lançamento)
 */
export function useExcluirTreinamento() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => sstService.excluirTreinamento(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: sstKeys.treinamentos() });
      queryClient.invalidateQueries({ queryKey: sstKeys.nr1Compliance() });
    },
  });
}

// =============================================================================
// ENTREGAS DE EPI
// =============================================================================

/**
 * Hook para listar entregas de EPI (com status da ficha vinculada)
 */
export function useEntregasEPI(employee_id?: string) {
  return useQuery({
    queryKey: [...sstKeys.entregasEPI(), employee_id],
    queryFn: () => sstService.listEntregasEPI(employee_id),
    staleTime: 2 * 60 * 1000,
  });
}

/**
 * Hook para registrar entrega de EPI (gera a ficha pendente de assinatura)
 */
export function useRegistrarEntregaEPI() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: EPIEntregaCreate) => sstService.registrarEntregaEPI(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: sstKeys.entregasEPI() });
      queryClient.invalidateQueries({ queryKey: sstKeys.fichasEPI() });
      queryClient.invalidateQueries({ queryKey: sstKeys.nr1Compliance() });
    },
  });
}

// =============================================================================
// FICHAS DE EPI
// =============================================================================

/**
 * Hook para listar fichas de EPI
 */
export function useFichasEPI(status?: FichaEPIStatus) {
  return useQuery({
    queryKey: [...sstKeys.fichasEPI(), status],
    queryFn: () => sstService.listFichasEPI(status),
    staleTime: 2 * 60 * 1000,
  });
}

/**
 * Hook para gerar ficha de EPI consolidando entregas sem ficha
 */
export function useGerarFichaEPI() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: FichaEPIGerarPayload) => sstService.gerarFichaEPI(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: sstKeys.fichasEPI() });
    },
  });
}

// =============================================================================
// COMPLIANCE NR-1
// =============================================================================

/**
 * Hook para o painel de compliance NR-1 (calcado por funcionario)
 */
export function useNR1Compliance() {
  return useQuery({
    queryKey: sstKeys.nr1Compliance(),
    queryFn: () => sstService.getNR1Compliance(),
    staleTime: 2 * 60 * 1000,
  });
}

// =============================================================================
// ESTABILIDADE
// =============================================================================

/**
 * Hook para listar colaboradores em estabilidade
 */
export function useEstabilidade() {
  return useQuery({
    queryKey: sstKeys.estabilidade(),
    queryFn: () => sstService.listEstabilidade(),
    staleTime: 5 * 60 * 1000,
  });
}

// =============================================================================
// AJUDA MEDICAMENTO
// =============================================================================

/**
 * Hook para listar colaboradores com ajuda medicamento
 */
export function useAjudaMedicamento() {
  return useQuery({
    queryKey: sstKeys.ajudaMedicamento(),
    queryFn: () => sstService.listAjudaMedicamento(),
    staleTime: 5 * 60 * 1000,
  });
}

// =============================================================================
// LTCAT
// =============================================================================

/**
 * Hook para status do LTCAT
 */
export function useLTCATStatus() {
  return useQuery({
    queryKey: sstKeys.ltcat(),
    queryFn: () => sstService.getLTCATStatus(),
    staleTime: 30 * 1000,
  });
}

/**
 * Hook para atualizar o registro do LTCAT
 */
export function useUpdateLTCAT() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: LTCATUpdatePayload) => sstService.updateLTCAT(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: sstKeys.ltcat() });
    },
  });
}
