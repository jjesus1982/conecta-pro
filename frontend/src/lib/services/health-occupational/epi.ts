/**
 * Service Layer - EPI (Equipamentos de Proteção Individual)
 * NR-6 - Gestão de EPIs
 *
 * @module health-occupational/epi
 * @author Conecta PRO Team
 * @date 2026-01-28
 */

import api from '@/lib/api';

// =============================================================================
// TIPOS - EPI
// =============================================================================

export type EPICategory =
  | 'protecao_cabeca'
  | 'protecao_olhos_face'
  | 'protecao_auditiva'
  | 'protecao_respiratoria'
  | 'protecao_maos_bracos'
  | 'protecao_pes_pernas'
  | 'protecao_tronco'
  | 'protecao_corpo_inteiro'
  | 'protecao_quedas';

export type EPIStatus = 'ativo' | 'descontinuado' | 'vencido';
export type DeliveryReason = 'admissao' | 'desgaste' | 'perda' | 'vencimento' | 'troca_funcao';

export interface EPI {
  id: string;
  tenant_id: string;
  nome: string;
  categoria: EPICategory;
  ca_number: string;
  fabricante: string;
  descricao: string | null;
  validade_dias: number;
  status: EPIStatus;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface EPICreate {
  nome: string;
  categoria: EPICategory;
  ca_number: string;
  fabricante: string;
  descricao?: string;
  validade_dias?: number;
}

export interface EPIUpdate {
  nome?: string;
  descricao?: string;
  fabricante?: string;
  status?: EPIStatus;
  validade_dias?: number;
}

export interface EPIListResponse {
  items: EPI[];
  total: number;
  page: number;
  size: number;
}

// =============================================================================
// TIPOS - ENTREGA DE EPI
// =============================================================================

export interface EPIDelivery {
  id: string;
  tenant_id: string;
  funcionario_id: string;
  epi_id: string;
  quantidade: number;
  ca_number: string;
  data_entrega: string;
  data_validade: string | null;
  motivo: DeliveryReason;
  assinatura_funcionario: boolean;
  data_assinatura: string | null;
  devolvido: boolean;
  data_devolucao: string | null;
  motivo_devolucao: string | null;
  condicao_devolucao: string | null;
  observacoes: string | null;
  created_at: string;
}

export interface EPIDeliveryCreate {
  funcionario_id: string;
  epi_id: string;
  quantidade: number;
  ca_number: string;
  motivo: DeliveryReason;
  observacoes?: string;
}

export interface EPIDeliveryRecord {
  funcionario_id: string;
  entregas: EPIDelivery[];
  total_entregas: number;
  epis_ativos: string[];
  epis_vencidos: string[];
  epis_devolvidos: string[];
}

// =============================================================================
// TIPOS - ESTOQUE
// =============================================================================

export interface EPIInventory {
  id: string;
  tenant_id: string;
  epi_id: string;
  quantidade_atual: number;
  quantidade_minima: number;
  quantidade_reservada: number;
  lote_atual: string | null;
  data_ultima_entrada: string | null;
  data_ultima_saida: string | null;
  updated_at: string;
  // Computed
  disponivel: number;
  estoque_baixo: boolean;
}

export interface EPIInventoryUpdate {
  quantidade_minima?: number;
}

// =============================================================================
// LABELS
// =============================================================================

export const EPI_CATEGORY_LABELS: Record<EPICategory, string> = {
  protecao_cabeca: 'Proteção da Cabeça',
  protecao_olhos_face: 'Proteção dos Olhos e Face',
  protecao_auditiva: 'Proteção Auditiva',
  protecao_respiratoria: 'Proteção Respiratória',
  protecao_maos_bracos: 'Proteção das Mãos e Braços',
  protecao_pes_pernas: 'Proteção dos Pés e Pernas',
  protecao_tronco: 'Proteção do Tronco',
  protecao_corpo_inteiro: 'Proteção do Corpo Inteiro',
  protecao_quedas: 'Proteção contra Quedas',
};

export const DELIVERY_REASON_LABELS: Record<DeliveryReason, string> = {
  admissao: 'Admissão',
  desgaste: 'Desgaste',
  perda: 'Perda',
  vencimento: 'Vencimento',
  troca_funcao: 'Troca de Função',
};

// =============================================================================
// SERVICE - EPI
// =============================================================================

const BASE_URL = '/api/v1/health-occupational/epi';

export const epiService = {
  // ===========================================================================
  // CATÁLOGO DE EPIs
  // ===========================================================================

  /**
   * Cadastra novo EPI
   */
  async createEPI(data: EPICreate): Promise<{ success: boolean; epi_id: string }> {
    const response = await api.post(`${BASE_URL}/cadastrar`, data);
    return response.data;
  },

  /**
   * Busca EPI por ID
   */
  async getEPI(epiId: string): Promise<EPI> {
    const response = await api.get(`${BASE_URL}/${epiId}`);
    return response.data.data;
  },

  /**
   * Atualiza EPI
   */
  async updateEPI(epiId: string, data: EPIUpdate): Promise<void> {
    await api.patch(`${BASE_URL}/${epiId}`, data);
  },

  /**
   * Lista EPIs cadastrados
   */
  async listEPIs(filters?: {
    categoria?: EPICategory;
    ativo?: boolean;
    page?: number;
    size?: number;
  }): Promise<EPIListResponse> {
    const params = new URLSearchParams();
    if (filters?.categoria) params.append('categoria', filters.categoria);
    if (filters?.ativo !== undefined) params.append('ativo', String(filters.ativo));
    if (filters?.page) params.append('page', String(filters.page));
    if (filters?.size) params.append('size', String(filters.size));

    const response = await api.get(`${BASE_URL}?${params.toString()}`);
    return response.data.data;
  },

  /**
   * Desativa EPI (soft delete)
   */
  async deactivateEPI(epiId: string): Promise<void> {
    await api.delete(`${BASE_URL}/${epiId}`);
  },

  /**
   * Lista categorias de EPI (NR-6)
   */
  async getCategories(): Promise<Array<{ value: string; label: string; descricao: string }>> {
    const response = await api.get(`${BASE_URL}/categorias`);
    return response.data.data.categorias;
  },

  // ===========================================================================
  // ENTREGA DE EPIs
  // ===========================================================================

  /**
   * Registra entrega de EPI para funcionário
   */
  async deliverEPI(data: EPIDeliveryCreate): Promise<{ success: boolean; delivery_id: string }> {
    const response = await api.post(`${BASE_URL}/entregar`, data);
    return response.data;
  },

  /**
   * Busca entrega por ID
   */
  async getDelivery(deliveryId: string): Promise<EPIDelivery> {
    const response = await api.get(`${BASE_URL}/entrega/${deliveryId}`);
    return response.data.data;
  },

  /**
   * Registra devolução de EPI
   */
  async returnEPI(deliveryId: string, motivo: string, condicao: string): Promise<void> {
    await api.post(`${BASE_URL}/entrega/${deliveryId}/devolver?motivo=${motivo}&condicao=${condicao}`);
  },

  /**
   * Registra assinatura do funcionário na entrega
   */
  async signDelivery(deliveryId: string): Promise<void> {
    await api.post(`${BASE_URL}/entrega/${deliveryId}/assinar`);
  },

  /**
   * Consulta ficha de EPI do funcionário
   */
  async getEmployeeRecord(funcionarioId: string): Promise<EPIDeliveryRecord> {
    const response = await api.get(`${BASE_URL}/ficha/${funcionarioId}`);
    return response.data.data;
  },

  // ===========================================================================
  // ESTOQUE
  // ===========================================================================

  /**
   * Consulta estoque de EPIs
   */
  async getInventory(filters?: {
    categoria?: EPICategory;
    baixo_estoque?: boolean;
  }): Promise<EPIInventory[]> {
    const params = new URLSearchParams();
    if (filters?.categoria) params.append('categoria', filters.categoria);
    if (filters?.baixo_estoque) params.append('baixo_estoque', 'true');

    const response = await api.get(`${BASE_URL}/estoque?${params.toString()}`);
    return response.data.data.itens;
  },

  /**
   * Atualiza estoque de EPI
   */
  async updateInventory(epiId: string, data: EPIInventoryUpdate): Promise<EPIInventory> {
    const response = await api.patch(`${BASE_URL}/estoque/${epiId}`, data);
    return response.data.data;
  },

  /**
   * Registra entrada de estoque
   */
  async addToInventory(epiId: string, quantidade: number, lote?: string): Promise<void> {
    const params = new URLSearchParams();
    params.append('quantidade', String(quantidade));
    if (lote) params.append('lote', lote);

    await api.post(`${BASE_URL}/estoque/${epiId}/entrada?${params.toString()}`);
  },

  // ===========================================================================
  // ESTATÍSTICAS
  // ===========================================================================

  /**
   * Retorna estatísticas de EPI (shape REAL do backend epi_service.get_statistics).
   * cas_vencendo = CAs do CATÁLOGO (health_epi_catalog.ca_validade) vencidos ou
   * a vencer em 90 dias — nunca entregas pendentes de assinatura.
   */
  async getStatistics(): Promise<{
    total_epis_ativos: number;
    entregas_ano: number;
    itens_baixo_estoque: number;
    assinaturas_pendentes: number;
    cas_vencendo: number;
    cas_vencidos: number;
    cas_sem_validade: number;
  }> {
    const response = await api.get(`${BASE_URL}/estatisticas`);
    return response.data.data;
  },
};

export default epiService;
