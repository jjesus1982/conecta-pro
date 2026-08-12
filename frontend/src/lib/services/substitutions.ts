/**
 * Servico de API para Substituições de Funcionários
 * Gestão completa de substituições com sugestões via IA
 */

import api from '@/lib/api';

// === Types ===

export type SubstitutionReason =
  | 'falta'
  | 'ferias'
  | 'atestado'
  | 'licenca'
  | 'folga'
  | 'demissao'
  | 'remanejamento'
  | 'emergencia'
  | 'outros';

export type SubstitutionStatus =
  | 'pendente'
  | 'confirmada'
  | 'em_andamento'
  | 'concluida'
  | 'cancelada'
  | 'rejeitada';

export interface Substitution {
  id: string;
  shift_id: string;
  post_id: string;
  original_employee_id: string;
  substitute_employee_id?: string;
  reason: SubstitutionReason;
  status: SubstitutionStatus;
  substitution_date: string;
  requested_at: string;
  confirmed_at?: string;
  completed_at?: string;
  additional_cost: number;
  overtime_hours: number;
  is_overtime: boolean;
  notes?: string;
  reason_details?: string;
  rejection_reason?: string;
  notification_sent: boolean;
  notification_sent_at?: string;
  requested_by?: string;
  approved_by?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  // Computed
  is_pending: boolean;
  is_confirmed: boolean;
  has_substitute: boolean;
  response_time_hours?: number;
  // Denormalized data
  original_employee_name?: string;
  substitute_employee_name?: string;
  post_name?: string;
  shift_date?: string;
  shift_time?: string;
}

export interface SubstitutionCreate {
  shift_id: string;
  post_id: string;
  original_employee_id: string;
  substitute_employee_id?: string;
  reason: SubstitutionReason;
  substitution_date: string;
  reason_details?: string;
  notes?: string;
}

export interface SubstitutionUpdate {
  substitute_employee_id?: string;
  status?: SubstitutionStatus;
  reason?: SubstitutionReason;
  reason_details?: string;
  notes?: string;
  rejection_reason?: string;
  is_active?: boolean;
}

export interface SubstitutionConfirm {
  substitute_employee_id: string;
  notes?: string;
}

export interface SubstitutionReject {
  rejection_reason: string;
}

export interface SubstituteSuggestion {
  employee_id: string;
  employee_name: string;
  score: number;
  reasons: string[];
  is_overtime: boolean;
  estimated_cost: number;
  distance_km?: number;
  availability: string;
}

export interface SubstitutionFilter {
  shift_id?: string;
  post_id?: string;
  original_employee_id?: string;
  substitute_employee_id?: string;
  status?: SubstitutionStatus;
  reason?: SubstitutionReason;
  start_date?: string;
  end_date?: string;
  is_pending?: boolean;
  has_substitute?: boolean;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

const BASE_URL = '/api/v1/operacional/substitutions';

export const substitutionsService = {
  /**
   * Lista substituições com paginação e filtros
   */
  async list(
    page = 1,
    pageSize = 20,
    filters?: SubstitutionFilter
  ): Promise<PaginatedResponse<Substitution>> {
    const params: Record<string, unknown> = { page, page_size: pageSize, ...filters };

    const response = await api.get<PaginatedResponse<Substitution>>(`${BASE_URL}/`, { params });
    return response.data;
  },

  /**
   * Busca substituição por ID
   */
  async getById(id: string): Promise<Substitution> {
    const response = await api.get<Substitution>(`${BASE_URL}/${id}`);
    return response.data;
  },

  /**
   * Cria nova substituição
   */
  async create(data: SubstitutionCreate): Promise<Substitution> {
    const response = await api.post<Substitution>(`${BASE_URL}/`, data);
    return response.data;
  },

  /**
   * Atualiza substituição
   */
  async update(id: string, data: SubstitutionUpdate): Promise<Substitution> {
    const response = await api.patch<Substitution>(`${BASE_URL}/${id}`, data);
    return response.data;
  },

  /**
   * Lista substituições pendentes
   */
  async getPending(): Promise<Substitution[]> {
    const response = await api.get<Substitution[]>(`${BASE_URL}/pending`);
    return response.data;
  },

  /**
   * Lista substituições por data
   */
  async getByDate(date: string): Promise<Substitution[]> {
    const response = await api.get<Substitution[]>(`${BASE_URL}/by-date/${date}`);
    return response.data;
  },

  /**
   * Confirma substituição com substituto
   */
  async confirm(id: string, data: SubstitutionConfirm): Promise<Substitution> {
    const response = await api.post<Substitution>(`${BASE_URL}/${id}/confirm`, data);
    return response.data;
  },

  /**
   * Rejeita substituição
   */
  async reject(id: string, data: SubstitutionReject): Promise<Substitution> {
    const response = await api.post<Substitution>(`${BASE_URL}/${id}/reject`, data);
    return response.data;
  },

  /**
   * Marca substituição como concluída
   */
  async complete(id: string, notes?: string): Promise<Substitution> {
    const response = await api.post<Substitution>(`${BASE_URL}/${id}/complete`, { notes });
    return response.data;
  },

  /**
   * Obtém sugestões de substitutos via IA
   */
  async getSuggestions(data: {
    shift_id: string;
    max_suggestions?: number;
    prefer_same_post?: boolean;
    consider_distance?: boolean;
    max_distance_km?: number;
  }): Promise<SubstituteSuggestion[]> {
    const response = await api.post<SubstituteSuggestion[]>(`${BASE_URL}/suggest`, data);
    return response.data;
  },
};

// Labels para exibição
export const SUBSTITUTION_REASON_LABELS: Record<SubstitutionReason, string> = {
  falta: 'Falta',
  ferias: 'Férias',
  atestado: 'Atestado Médico',
  licenca: 'Licença',
  folga: 'Folga',
  demissao: 'Demissão',
  remanejamento: 'Remanejamento',
  emergencia: 'Emergência',
  outros: 'Outros',
};

export const SUBSTITUTION_STATUS_LABELS: Record<SubstitutionStatus, string> = {
  pendente: 'Pendente',
  confirmada: 'Confirmada',
  em_andamento: 'Em Andamento',
  concluida: 'Concluída',
  cancelada: 'Cancelada',
  rejeitada: 'Rejeitada',
};

export const SUBSTITUTION_STATUS_COLORS: Record<SubstitutionStatus, string> = {
  pendente: 'bg-yellow-500/10 text-yellow-500',
  confirmada: 'bg-blue-500/10 text-blue-500',
  em_andamento: 'bg-purple-500/10 text-purple-500',
  concluida: 'bg-green-500/10 text-green-500',
  cancelada: 'bg-gray-500/10 text-gray-500',
  rejeitada: 'bg-red-500/10 text-red-500',
};

export const SUBSTITUTION_REASON_COLORS: Record<SubstitutionReason, string> = {
  falta: 'bg-red-500/10 text-red-500',
  ferias: 'bg-blue-500/10 text-blue-500',
  atestado: 'bg-orange-500/10 text-orange-500',
  licenca: 'bg-purple-500/10 text-purple-500',
  folga: 'bg-green-500/10 text-green-500',
  demissao: 'bg-gray-500/10 text-gray-500',
  remanejamento: 'bg-cyan-500/10 text-cyan-500',
  emergencia: 'bg-red-500/10 text-red-500',
  outros: 'bg-gray-500/10 text-gray-500',
};

export default substitutionsService;
