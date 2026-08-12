/**
 * Servico de API para Banco de Horas
 * Controle de horas extras e compensações
 */

import api from '@/lib/api';

// === Types ===

export type TimeBankEntryType = 'credito' | 'debito' | 'compensacao' | 'expiracao' | 'ajuste';
export type TimeBankStatus = 'pendente' | 'aprovado' | 'rejeitado' | 'compensado' | 'expirado';

export interface TimeBankEntry {
  id: string;
  employee_id: string;
  entry_type: TimeBankEntryType;
  status: TimeBankStatus;
  hours: number;
  balance_before: number;
  balance_after: number;
  reference_date: string;
  expiration_date?: string;
  shift_id?: string;
  post_id?: string;
  description?: string;
  reason?: string;
  approved_by?: string;
  approved_at?: string;
  rejection_reason?: string;
  compensated_at?: string;
  compensation_shift_id?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  // Computed
  is_credit: boolean;
  is_debit: boolean;
  is_expired: boolean;
  is_pending: boolean;
  signed_hours: number;
  days_until_expiration?: number;
  // Denormalized data
  employee_name?: string;
  post_name?: string;
}

export interface TimeBankCreate {
  employee_id: string;
  entry_type: TimeBankEntryType;
  hours: number;
  reference_date: string;
  description?: string;
  reason?: string;
  shift_id?: string;
  post_id?: string;
  expiration_date?: string;
}

export interface TimeBankUpdate {
  status?: TimeBankStatus;
  hours?: number;
  description?: string;
  reason?: string;
  expiration_date?: string;
  rejection_reason?: string;
  is_active?: boolean;
}

export interface TimeBankApprove {
  notes?: string;
}

export interface TimeBankReject {
  rejection_reason: string;
}

export interface TimeBankCompensate {
  hours: number;
  compensation_date: string;
  shift_id?: string;
  notes?: string;
}

export interface TimeBankSummary {
  employee_id: string;
  total_credit: number;
  total_debit: number;
  total_compensated: number;
  total_expired: number;
  current_balance: number;
  pending_approval: number;
  expiring_soon: number;
  entries_count: number;
}

export interface TimeBankMonthlySummary extends TimeBankSummary {
  month: number;
  year: number;
  entries: TimeBankEntry[];
}

export interface TimeBankStats {
  total_employees: number;
  total_credit_hours: number;
  total_debit_hours: number;
  total_compensated_hours: number;
  total_expired_hours: number;
  total_pending_hours: number;
  avg_balance: number;
  by_status: Record<string, number>;
  by_entry_type: Record<string, number>;
}

export interface TimeBankAlert {
  type: 'expiring' | 'high_balance' | 'negative_balance' | 'pending_approval';
  employee_id: string;
  employee_name: string;
  message: string;
  hours?: number;
  deadline?: string;
  severity: 'info' | 'warning' | 'critical';
}

export interface TimeBankRecommendation {
  employee_id: string;
  type: 'compensate' | 'register' | 'approve' | 'review';
  message: string;
  suggested_hours?: number;
  suggested_date?: string;
  priority: 'low' | 'medium' | 'high';
}

export interface TimeBankFilter {
  employee_id?: string;
  entry_type?: TimeBankEntryType;
  status?: TimeBankStatus;
  shift_id?: string;
  post_id?: string;
  start_date?: string;
  end_date?: string;
  is_expired?: boolean;
  is_pending?: boolean;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

const BASE_URL = '/api/v1/operacional/time-bank';

export const timeBankService = {
  /**
   * Lista entradas do banco de horas com paginação e filtros
   */
  async list(
    page = 1,
    pageSize = 20,
    filters?: TimeBankFilter
  ): Promise<PaginatedResponse<TimeBankEntry>> {
    const params: Record<string, unknown> = { page, page_size: pageSize, ...filters };

    const response = await api.get<PaginatedResponse<TimeBankEntry>>(`${BASE_URL}/`, { params });
    return response.data;
  },

  /**
   * Busca entrada por ID
   */
  async getById(id: string): Promise<TimeBankEntry> {
    const response = await api.get<TimeBankEntry>(`${BASE_URL}/${id}`);
    return response.data;
  },

  /**
   * Cria nova entrada no banco de horas
   */
  async create(data: TimeBankCreate): Promise<TimeBankEntry> {
    const response = await api.post<TimeBankEntry>(`${BASE_URL}/`, data);
    return response.data;
  },

  /**
   * Atualiza entrada
   */
  async update(id: string, data: TimeBankUpdate): Promise<TimeBankEntry> {
    const response = await api.patch<TimeBankEntry>(`${BASE_URL}/${id}`, data);
    return response.data;
  },

  /**
   * Obtém estatísticas gerais
   */
  async getStats(): Promise<TimeBankStats> {
    const response = await api.get<TimeBankStats>(`${BASE_URL}/stats`);
    return response.data;
  },

  /**
   * Lista entradas pendentes de aprovação
   */
  async getPending(): Promise<TimeBankEntry[]> {
    const response = await api.get<TimeBankEntry[]>(`${BASE_URL}/pending`);
    return response.data;
  },

  /**
   * Lista alertas (horas expirando, saldos altos, etc.)
   */
  async getAlerts(): Promise<TimeBankAlert[]> {
    const response = await api.get<TimeBankAlert[]>(`${BASE_URL}/alerts`);
    return response.data;
  },

  /**
   * Lista entradas com horas expirando em breve
   */
  async getExpiring(days = 30): Promise<TimeBankEntry[]> {
    const response = await api.get<TimeBankEntry[]>(`${BASE_URL}/expiring`, {
      params: { days }
    });
    return response.data;
  },

  /**
   * Obtém resumo do banco de horas de um funcionário
   */
  async getSummary(employeeId: string): Promise<TimeBankSummary> {
    const response = await api.get<TimeBankSummary>(`${BASE_URL}/summary/${employeeId}`);
    return response.data;
  },

  /**
   * Obtém resumo mensal do banco de horas de um funcionário
   */
  async getMonthlySummary(
    employeeId: string,
    month?: number,
    year?: number
  ): Promise<TimeBankMonthlySummary> {
    const params: Record<string, unknown> = {};
    if (month) params.month = month;
    if (year) params.year = year;

    const response = await api.get<TimeBankMonthlySummary>(
      `${BASE_URL}/monthly-summary/${employeeId}`,
      { params }
    );
    return response.data;
  },

  /**
   * Obtém recomendações de compensação via IA
   */
  async getRecommendations(employeeId: string): Promise<TimeBankRecommendation[]> {
    const response = await api.get<TimeBankRecommendation[]>(
      `${BASE_URL}/recommendations/${employeeId}`
    );
    return response.data;
  },

  /**
   * Aprova entrada do banco de horas
   */
  async approve(id: string, data?: TimeBankApprove): Promise<TimeBankEntry> {
    const response = await api.post<TimeBankEntry>(`${BASE_URL}/${id}/approve`, data || {});
    return response.data;
  },

  /**
   * Rejeita entrada do banco de horas
   */
  async reject(id: string, data: TimeBankReject): Promise<TimeBankEntry> {
    const response = await api.post<TimeBankEntry>(`${BASE_URL}/${id}/reject`, data);
    return response.data;
  },

  /**
   * Compensa horas do banco
   */
  async compensate(employeeId: string, data: TimeBankCompensate): Promise<TimeBankEntry> {
    const response = await api.post<TimeBankEntry>(
      `${BASE_URL}/compensate/${employeeId}`,
      data
    );
    return response.data;
  },
};

// Labels para exibição
export const TIME_BANK_ENTRY_TYPE_LABELS: Record<TimeBankEntryType, string> = {
  credito: 'Crédito (Hora Extra)',
  debito: 'Débito (Falta/Atraso)',
  compensacao: 'Compensação',
  expiracao: 'Expiração',
  ajuste: 'Ajuste Manual',
};

export const TIME_BANK_STATUS_LABELS: Record<TimeBankStatus, string> = {
  pendente: 'Pendente',
  aprovado: 'Aprovado',
  rejeitado: 'Rejeitado',
  compensado: 'Compensado',
  expirado: 'Expirado',
};

export const TIME_BANK_ENTRY_TYPE_COLORS: Record<TimeBankEntryType, string> = {
  credito: 'bg-green-500/10 text-green-500',
  debito: 'bg-red-500/10 text-red-500',
  compensacao: 'bg-blue-500/10 text-blue-500',
  expiracao: 'bg-gray-500/10 text-gray-500',
  ajuste: 'bg-purple-500/10 text-purple-500',
};

export const TIME_BANK_STATUS_COLORS: Record<TimeBankStatus, string> = {
  pendente: 'bg-yellow-500/10 text-yellow-500',
  aprovado: 'bg-green-500/10 text-green-500',
  rejeitado: 'bg-red-500/10 text-red-500',
  compensado: 'bg-blue-500/10 text-blue-500',
  expirado: 'bg-gray-500/10 text-gray-500',
};

export const ALERT_SEVERITY_COLORS: Record<string, string> = {
  info: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
  warning: 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20',
  critical: 'bg-red-500/10 text-red-500 border-red-500/20',
};

export default timeBankService;
