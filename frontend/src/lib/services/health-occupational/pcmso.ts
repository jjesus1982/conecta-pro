/**
 * Service Layer - PCMSO (Programa de Controle Médico de Saúde Ocupacional)
 * NR-7 - Exames Médicos e ASO
 *
 * @module health-occupational/pcmso
 * @author Conecta PRO Team
 * @date 2026-01-28
 */

import api from '@/lib/api';

// =============================================================================
// TIPOS - EXAMES MÉDICOS
// =============================================================================

export type ExamType = 'admissional' | 'periodico' | 'retorno_trabalho' | 'mudanca_funcao' | 'demissional';
export type ExamStatus = 'agendado' | 'confirmado' | 'realizado' | 'cancelado' | 'faltou';
export type FitnessResult = 'apto' | 'inapto' | 'apto_com_restricoes';

export interface MedicalExam {
  id: string;
  tenant_id: string;
  funcionario_id: string;
  tipo_exame: ExamType;
  data_agendamento: string;
  data_realizacao: string | null;
  clinica: string | null;
  medico_responsavel: string | null;
  status: ExamStatus;
  exames_complementares: string[];
  observacoes: string | null;
  resultado: string | null;
  created_at: string;
  updated_at: string;
}

export interface MedicalExamCreate {
  funcionario_id: string;
  tipo_exame: ExamType;
  data_agendamento: string;
  clinica?: string;
  exames_complementares?: string[];
  observacoes?: string;
}

export interface MedicalExamUpdate {
  data_agendamento?: string;
  clinica?: string;
  medico_responsavel?: string;
  status?: ExamStatus;
  data_realizacao?: string;
  resultado?: string;
  observacoes?: string;
}

export interface MedicalExamListResponse {
  items: MedicalExam[];
  total: number;
  page: number;
  size: number;
}

// =============================================================================
// TIPOS - ASO (ATESTADO DE SAÚDE OCUPACIONAL)
// =============================================================================

export interface ASO {
  id: string;
  tenant_id: string;
  exame_id: string;
  funcionario_id: string;
  numero_aso: string;
  data_emissao: string;
  data_vencimento: string;
  resultado: FitnessResult;
  restricoes: string[] | null;
  medico_responsavel: string;
  crm: string;
  uf_crm: string;
  assinatura_funcionario: boolean;
  data_assinatura_funcionario: string | null;
  is_active: boolean;
  created_at: string;
}

export interface ASOCreate {
  exame_id: string;
  resultado: FitnessResult;
  restricoes?: string[];
  validade_dias?: number;
  medico_responsavel: string;
  crm: string;
  uf_crm?: string;
}

export interface ASOListResponse {
  items: ASO[];
  total: number;
}

export interface ExpiringASO {
  aso_id: string;
  numero_aso: string;
  funcionario_id: string;
  funcionario_nome: string;
  data_vencimento: string;
  dias_restantes: number;
}

// =============================================================================
// LABELS
// =============================================================================

export const EXAM_TYPE_LABELS: Record<ExamType, string> = {
  admissional: 'Admissional',
  periodico: 'Periódico',
  retorno_trabalho: 'Retorno ao Trabalho',
  mudanca_funcao: 'Mudança de Função',
  demissional: 'Demissional',
};

export const EXAM_STATUS_LABELS: Record<ExamStatus, string> = {
  agendado: 'Agendado',
  confirmado: 'Confirmado',
  realizado: 'Realizado',
  cancelado: 'Cancelado',
  faltou: 'Faltou',
};

export const FITNESS_RESULT_LABELS: Record<FitnessResult, string> = {
  apto: 'Apto',
  inapto: 'Inapto',
  apto_com_restricoes: 'Apto com Restrições',
};

// =============================================================================
// SERVICE - PCMSO
// =============================================================================

const BASE_URL = '/api/v1/health-occupational/pcmso';

export const pcmsoService = {
  // ===========================================================================
  // EXAMES MÉDICOS
  // ===========================================================================

  /**
   * Agenda exame médico ocupacional
   */
  async scheduleExam(data: MedicalExamCreate): Promise<{ success: boolean; exame_id: string }> {
    const response = await api.post(`${BASE_URL}/exames/agendar`, data);
    return response.data;
  },

  /**
   * Busca exame por ID
   */
  async getExam(exameId: string): Promise<MedicalExam> {
    const response = await api.get(`${BASE_URL}/exames/${exameId}`);
    return response.data.data;
  },

  /**
   * Atualiza exame médico
   */
  async updateExam(exameId: string, data: MedicalExamUpdate): Promise<void> {
    await api.patch(`${BASE_URL}/exames/${exameId}`, data);
  },

  /**
   * Lista exames de um funcionário
   */
  async listEmployeeExams(
    funcionarioId: string,
    filters?: {
      status?: ExamStatus;
      tipo?: ExamType;
      page?: number;
      size?: number;
    }
  ): Promise<MedicalExamListResponse> {
    const params = new URLSearchParams();
    if (filters?.status) params.append('status_filter', filters.status);
    if (filters?.tipo) params.append('tipo_filter', filters.tipo);
    if (filters?.page) params.append('page', String(filters.page));
    if (filters?.size) params.append('size', String(filters.size));

    const response = await api.get(
      `${BASE_URL}/exames/funcionario/${funcionarioId}?${params.toString()}`
    );
    return response.data.data;
  },

  /**
   * Confirma agendamento de exame
   */
  async confirmExam(exameId: string): Promise<void> {
    await api.post(`${BASE_URL}/exames/${exameId}/confirmar`);
  },

  /**
   * Marca exame como realizado
   */
  async completeExam(exameId: string): Promise<void> {
    await api.post(`${BASE_URL}/exames/${exameId}/realizar`);
  },

  // ===========================================================================
  // ASO (ATESTADO DE SAÚDE OCUPACIONAL)
  // ===========================================================================

  /**
   * Emite ASO (Atestado de Saúde Ocupacional)
   */
  async emitASO(data: ASOCreate): Promise<ASO> {
    const response = await api.post(`${BASE_URL}/aso/emitir`, data);
    return response.data.data;
  },

  /**
   * Busca ASO por ID
   */
  async getASO(asoId: string): Promise<ASO> {
    const response = await api.get(`${BASE_URL}/aso/${asoId}`);
    return response.data.data;
  },

  /**
   * Registra assinatura do funcionário no ASO
   */
  async signASO(asoId: string): Promise<void> {
    await api.post(`${BASE_URL}/aso/${asoId}/assinar`);
  },

  /**
   * Lista ASOs com vencimento próximo
   */
  async listExpiringASOs(days: number = 30): Promise<ExpiringASO[]> {
    const response = await api.get(`${BASE_URL}/vencimentos?dias=${days}`);
    return response.data.data.asos_vencendo;
  },

  /**
   * Retorna ASOs com vencimento próximo (alias direto do endpoint)
   */
  async getVencimentos(dias: number = 30): Promise<ExpiringASO[]> {
    const response = await api.get(`${BASE_URL}/vencimentos?dias=${dias}`);
    return response.data.data.asos_vencendo;
  },

  // ===========================================================================
  // ESTATÍSTICAS
  // ===========================================================================

  /**
   * Retorna estatísticas do PCMSO
   */
  async getStatistics(): Promise<{
    total_exames: number;
    exames_agendados: number;
    exames_realizados: number;
    total_asos_ativos: number;
    asos_vencendo: number;
    por_tipo: Record<string, number>;
    por_status: Record<string, number>;
  }> {
    const response = await api.get(`${BASE_URL}/estatisticas`);
    return response.data.data;
  },
};

export default pcmsoService;
