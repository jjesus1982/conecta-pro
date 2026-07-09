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
  type ASORetroativoPayload,
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
  rolloutAssinaturas: () => [...sstKeys.all, 'rollout-assinaturas'] as const,
  nr1Compliance: () => [...sstKeys.all, 'nr1-compliance'] as const,
  regularizacao: () => [...sstKeys.all, 'asos-regularizacao'] as const,
  semAso: () => [...sstKeys.all, 'sem-aso'] as const,
  treinamentos: () => [...sstKeys.all, 'treinamentos'] as const,
  prontuario: (employeeId: string) => [...sstKeys.all, 'prontuario', employeeId] as const,
  esteiraPCMSO: (horizonte: number) => [...sstKeys.all, 'esteira-pcmso', horizonte] as const,
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

/**
 * Hook para anexar o ASO digitalizado (PDF/JPG/PNG) a um ASO existente
 */
export function useUploadASOAnexo() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ asoId, file }: { asoId: string; file: File }) =>
      sstService.uploadASOAnexo(asoId, file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: sstKeys.asos() });
    },
  });
}

/**
 * Hook para a carga retroativa de ASO (exame em papel pré-sistema —
 * anexo obrigatório; cria gp_asos realizado + retroativo=true)
 */
export function useASORetroativo() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ payload, file }: { payload: ASORetroativoPayload; file: File }) =>
      sstService.criarASORetroativo(payload, file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: sstKeys.asos() });
      queryClient.invalidateQueries({ queryKey: sstKeys.semAso() });
      queryClient.invalidateQueries({ queryKey: sstKeys.regularizacao() });
      queryClient.invalidateQueries({ queryKey: sstKeys.nr1Compliance() });
      queryClient.invalidateQueries({ queryKey: sstKeys.dashboard() });
      queryClient.invalidateQueries({ queryKey: [...sstKeys.all, 'esteira-pcmso'] });
    },
  });
}

/**
 * Hook para o contador de funcionários ativos sem NENHUM ASO digitalizado
 * (fonte honesta da carga retroativa — documento não digitalizado ≠ exame não feito)
 */
export function useSemASO() {
  return useQuery({
    queryKey: sstKeys.semAso(),
    queryFn: () => sstService.listSemASO(),
    staleTime: 60 * 1000,
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
      queryClient.invalidateQueries({ queryKey: [...sstKeys.all, 'esteira-pcmso'] });
    },
  });
}

// =============================================================================
// ESTEIRA PCMSO PREVENTIVA
// =============================================================================

/**
 * Hook para a esteira preventiva do PCMSO (projeção ao vivo dos periódicos —
 * último ASO realizado + 12 meses; nada é gravado, fonte da verdade = gp_asos)
 */
export function useEsteiraPCMSO(horizonteMeses = 12) {
  return useQuery({
    queryKey: sstKeys.esteiraPCMSO(horizonteMeses),
    queryFn: () => sstService.getEsteiraPCMSO(horizonteMeses),
    staleTime: 60 * 1000,
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
// ROLLOUT DE ASSINATURAS (acesso ao Portal do Funcionario)
// =============================================================================

/**
 * Hook para o rollout das assinaturas de fichas de EPI
 * (acesso ao Portal por funcionario ativo, fichas pendentes, prontidao)
 */
export function useRolloutAssinaturas() {
  return useQuery({
    queryKey: sstKeys.rolloutAssinaturas(),
    queryFn: () => sstService.getRolloutAssinaturas(),
    staleTime: 60 * 1000,
  });
}

/**
 * Hook para ativar acessos ao Portal em massa (fluxo existente de
 * primeiro acesso: CPF + data de nascimento -> funcionario cria a senha)
 */
export function useAtivarAcessosPortal() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (employee_ids: string[]) => sstService.ativarAcessosPortal(employee_ids),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: sstKeys.rolloutAssinaturas() });
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

/**
 * Hook para o Prontuário SST 360 de um funcionário (dossiê completo)
 */
export function useProntuarioSST(employeeId: string | null) {
  return useQuery({
    queryKey: sstKeys.prontuario(employeeId ?? ''),
    queryFn: () => sstService.getProntuario(employeeId as string),
    enabled: !!employeeId,
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
