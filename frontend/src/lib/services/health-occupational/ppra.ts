/**
 * Service Layer - PPRA/PGR (Programa de Prevenção de Riscos Ambientais)
 * NR-9 - Mapeamento de Riscos Ocupacionais
 *
 * @module health-occupational/ppra
 * @author Conecta PRO Team
 * @date 2026-01-28
 */

import api from '@/lib/api';

// =============================================================================
// TIPOS - RISCOS OCUPACIONAIS
// =============================================================================

export type RiskCategory = 'fisico' | 'quimico' | 'biologico' | 'ergonomico' | 'acidente';
export type RiskLevel = 'baixo' | 'medio' | 'alto' | 'muito_alto';
export type RiskAgent =
  | 'ruido'
  | 'vibracao'
  | 'radiacao'
  | 'temperatura'
  | 'pressao'
  | 'umidade'
  | 'poeira'
  | 'gases'
  | 'vapores'
  | 'bacterias'
  | 'virus'
  | 'fungos'
  | 'parasitas'
  | 'postura'
  | 'repeticao'
  | 'levantamento_peso'
  | 'jornada'
  | 'maquinas'
  | 'eletricidade'
  | 'incendio'
  | 'queda'
  | 'corte'
  | 'outro';

export interface OccupationalRisk {
  id: string;
  categoria: RiskCategory;
  agente: RiskAgent;
  descricao: string;
  nivel: RiskLevel;
  fonte_geradora: string | null;
  meios_propagacao: string | null;
  medidas_controle_existentes: string[];
  epis_recomendados: string[];
}

export interface RiskMapping {
  id: string;
  tenant_id: string;
  setor: string;
  funcoes: string[];
  data_avaliacao: string;
  avaliador: string;
  versao: number;
  nivel_risco_geral: RiskLevel;
  riscos: OccupationalRisk[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface RiskMappingCreate {
  setor: string;
  funcoes: string[];
  avaliador: string;
  riscos: Array<{
    categoria: RiskCategory;
    agente: RiskAgent;
    descricao: string;
    nivel: RiskLevel;
    fonte_geradora?: string;
    meios_propagacao?: string;
    medidas_controle_existentes?: string[];
    epis_recomendados?: string[];
  }>;
}

export interface RiskMappingUpdate {
  setor?: string;
  funcoes?: string[];
  avaliador?: string;
  is_active?: boolean;
}

export interface RiskMappingListResponse {
  items: RiskMapping[];
  total: number;
  page: number;
  size: number;
}

// =============================================================================
// TIPOS - MEDIDAS DE CONTROLE
// =============================================================================

export type ControlMeasureType =
  | 'eliminacao'
  | 'substituicao'
  | 'controle_engenharia'
  | 'sinalizacao'
  | 'controle_administrativo'
  | 'epi'
  | 'epc';

export type ControlMeasureStatus = 'planejada' | 'em_andamento' | 'implementada' | 'cancelada';

export interface ControlMeasure {
  id: string;
  tenant_id: string;
  mapeamento_id: string;
  tipo: ControlMeasureType;
  descricao: string;
  riscos_controlados: string[];
  responsavel: string | null;
  data_prevista: string | null;
  data_implementacao: string | null;
  status: ControlMeasureStatus;
  eficaz: boolean | null;
  data_verificacao: string | null;
  observacoes: string | null;
  custo_estimado: number | null;
  created_at: string;
  updated_at: string;
}

export interface ControlMeasureCreate {
  mapeamento_id: string;
  tipo: ControlMeasureType;
  descricao: string;
  riscos_controlados?: string[];
  responsavel?: string;
  data_prevista?: string;
  custo_estimado?: number;
}

export interface ControlMeasureUpdate {
  descricao?: string;
  status?: ControlMeasureStatus;
  responsavel?: string;
  data_prevista?: string;
  data_implementacao?: string;
  eficaz?: boolean;
  data_verificacao?: string;
  observacoes?: string;
  custo_estimado?: number;
}

// =============================================================================
// LABELS
// =============================================================================

export const RISK_CATEGORY_LABELS: Record<RiskCategory, string> = {
  fisico: 'Físico',
  quimico: 'Químico',
  biologico: 'Biológico',
  ergonomico: 'Ergonômico',
  acidente: 'Acidente',
};

export const RISK_LEVEL_LABELS: Record<RiskLevel, string> = {
  baixo: 'Baixo',
  medio: 'Médio',
  alto: 'Alto',
  muito_alto: 'Muito Alto',
};

export const CONTROL_MEASURE_TYPE_LABELS: Record<ControlMeasureType, string> = {
  eliminacao: 'Eliminação',
  substituicao: 'Substituição',
  controle_engenharia: 'Controle de Engenharia',
  sinalizacao: 'Sinalização',
  controle_administrativo: 'Controle Administrativo',
  epi: 'EPI',
  epc: 'EPC',
};

export const CONTROL_MEASURE_STATUS_LABELS: Record<ControlMeasureStatus, string> = {
  planejada: 'Planejada',
  em_andamento: 'Em Andamento',
  implementada: 'Implementada',
  cancelada: 'Cancelada',
};

// =============================================================================
// SERVICE - PPRA/PGR
// =============================================================================

const BASE_URL = '/api/v1/health-occupational/ppra';

export const ppraService = {
  // ===========================================================================
  // MAPEAMENTO DE RISCOS
  // ===========================================================================

  /**
   * Cria mapeamento de riscos ocupacionais
   */
  async createMapping(data: RiskMappingCreate): Promise<{ success: boolean; mapping_id: string }> {
    const response = await api.post(`${BASE_URL}/mapeamento`, data);
    return response.data;
  },

  /**
   * Busca mapeamento por ID
   */
  async getMapping(mappingId: string): Promise<RiskMapping> {
    const response = await api.get(`${BASE_URL}/mapeamento/${mappingId}`);
    return response.data.data;
  },

  /**
   * Atualiza mapeamento de riscos
   */
  async updateMapping(mappingId: string, data: RiskMappingUpdate): Promise<void> {
    await api.patch(`${BASE_URL}/mapeamento/${mappingId}`, data);
  },

  /**
   * Lista mapeamentos de risco
   */
  async listMappings(filters?: {
    setor?: string;
    ativo?: boolean;
    page?: number;
    size?: number;
  }): Promise<RiskMappingListResponse> {
    const params = new URLSearchParams();
    if (filters?.setor) params.append('setor', filters.setor);
    if (filters?.ativo !== undefined) params.append('ativo', String(filters.ativo));
    if (filters?.page) params.append('page', String(filters.page));
    if (filters?.size) params.append('size', String(filters.size));

    const response = await api.get(`${BASE_URL}/mapeamentos?${params.toString()}`);
    const data = response.data.data ?? {};
    // Backend responde sob a chave "mapeamentos" (não "items") — normaliza.
    return {
      items: data.items ?? data.mapeamentos ?? [],
      total: data.total ?? 0,
      page: data.page ?? 1,
      size: data.size ?? 20,
    };
  },

  // ===========================================================================
  // CONSULTA DE RISCOS
  // ===========================================================================

  /**
   * Consulta riscos de um setor
   */
  async getSectorRisks(setor: string): Promise<{
    setor: string;
    riscos: OccupationalRisk[];
    total: number;
    nivel_geral: RiskLevel;
  }> {
    const response = await api.get(`${BASE_URL}/riscos/${setor}`);
    return response.data.data;
  },

  /**
   * Consulta riscos de uma função
   */
  async getFunctionRisks(funcao: string): Promise<{
    funcao: string;
    riscos: OccupationalRisk[];
    total: number;
    epis_recomendados: string[];
  }> {
    const response = await api.get(`${BASE_URL}/riscos/funcao/${funcao}`);
    return response.data.data;
  },

  /**
   * Lista categorias de risco (NR-9)
   */
  async getRiskCategories(): Promise<
    Array<{
      categoria: string;
      nome: string;
      descricao: string;
      cor_identificacao: string;
      agentes: Array<{ value: string; label: string }>;
    }>
  > {
    const response = await api.get(`${BASE_URL}/categorias`);
    return response.data.data.categorias;
  },

  // ===========================================================================
  // MEDIDAS DE CONTROLE
  // ===========================================================================

  /**
   * Adiciona medida de controle
   */
  async addControlMeasure(data: ControlMeasureCreate): Promise<{ success: boolean; measure_id: string }> {
    const response = await api.post(`${BASE_URL}/medidas-controle`, data);
    return response.data;
  },

  /**
   * Atualiza medida de controle
   */
  async updateControlMeasure(measureId: string, data: ControlMeasureUpdate): Promise<ControlMeasure> {
    const response = await api.patch(`${BASE_URL}/medidas-controle/${measureId}`, data);
    return response.data.data;
  },

  /**
   * Lista medidas de controle de um mapeamento
   */
  async listControlMeasures(mappingId: string, status?: ControlMeasureStatus): Promise<ControlMeasure[]> {
    const params = new URLSearchParams();
    if (status) params.append('status_filter', status);

    const response = await api.get(
      `${BASE_URL}/mapeamento/${mappingId}/medidas-controle?${params.toString()}`
    );
    return response.data.data.medidas;
  },

  // ===========================================================================
  // ESTATÍSTICAS
  // ===========================================================================

  /**
   * Retorna estatísticas do PPRA
   */
  async getStatistics(): Promise<{
    total_mapeamentos: number;
    mapeamentos_ativos: number;
    total_riscos_identificados: number;
    total_medidas_controle: number;
    medidas_implementadas: number;
    por_categoria: Record<string, number>;
    por_nivel: Record<string, number>;
    setores_mapeados: string[];
  }> {
    const response = await api.get(`${BASE_URL}/estatisticas`);
    return response.data.data;
  },
};

export default ppraService;
