/**
 * Servico de API para Diaristas
 * Sistema completo de gestão de diaristas com IA
 */

import api from '@/lib/api';

// === Types ===

export type DiaristType = 'limpeza' | 'portaria' | 'manutencao' | 'jardinagem' | 'outros';
export type DiaristStatus = 'ativo' | 'inativo' | 'bloqueado' | 'em_avaliacao';
export type AssignmentType = 'avulso' | 'fixo' | 'temporario';
export type AssignmentStatus = 'agendado' | 'em_andamento' | 'concluido' | 'cancelado';
export type ScheduleStatus = 'agendado' | 'confirmado' | 'em_andamento' | 'concluido' | 'falta' | 'cancelado';
export type PaymentStatus = 'pendente' | 'aprovado' | 'pago' | 'cancelado';
export type PaymentMethod = 'pix' | 'transferencia' | 'dinheiro' | 'cheque';

export interface Diarist {
  id: string;
  condominio_id: string;
  codigo: string;
  nome: string;
  nome_social?: string;
  cpf: string;
  rg?: string;
  data_nascimento?: string;
  genero?: string;
  nacionalidade?: string;
  estado_civil?: string;
  email?: string;
  telefone?: string;
  celular?: string;
  whatsapp?: string;
  cep?: string;
  logradouro?: string;
  numero?: string;
  complemento?: string;
  bairro?: string;
  cidade?: string;
  estado?: string;
  tipo: DiaristType;
  especialidades: string[];
  experiencia_anos: number;
  dias_disponiveis: string[];
  horario_inicio?: string;
  horario_fim?: string;
  carga_horaria_max: number;
  aceita_hora_extra: boolean;
  valor_diaria: number;
  valor_hora_extra?: number;
  forma_pagamento_preferida?: PaymentMethod;
  status: DiaristStatus;
  is_blocked: boolean;
  data_admissao?: string;
  total_diarias: number;
  total_horas: number;
  total_recebido: number;
  media_avaliacao: number;
  total_avaliacoes: number;
  taxa_comparecimento: number;
  taxa_pontualidade: number;
  ultima_diaria?: string;
  proxima_diaria?: string;
  score_confiabilidade: number;
  score_qualidade: number;
  tags: string[];
  foto_url?: string;
  created_at: string;
  updated_at?: string;
}

export interface DiaristCreate {
  condominio_id: string;
  nome: string;
  cpf: string;
  tipo: DiaristType;
  valor_diaria: number;
  email?: string;
  telefone?: string;
  celular?: string;
  whatsapp?: string;
  cep?: string;
  logradouro?: string;
  numero?: string;
  bairro?: string;
  cidade?: string;
  estado?: string;
  especialidades?: string[];
  dias_disponiveis?: string[];
  horario_inicio?: string;
  horario_fim?: string;
  forma_pagamento_preferida?: PaymentMethod;
}

export interface DiaristUpdate {
  nome?: string;
  email?: string;
  telefone?: string;
  celular?: string;
  whatsapp?: string;
  tipo?: DiaristType;
  valor_diaria?: number;
  valor_hora_extra?: number;
  especialidades?: string[];
  dias_disponiveis?: string[];
  horario_inicio?: string;
  horario_fim?: string;
  forma_pagamento_preferida?: PaymentMethod;
  cep?: string;
  logradouro?: string;
  numero?: string;
  bairro?: string;
  cidade?: string;
  estado?: string;
  tags?: string[];
  observacoes?: string;
}

export interface DiaristAssignment {
  id: string;
  condominio_id: string;
  diarist_id: string;
  tipo: AssignmentType;
  status: AssignmentStatus;
  servico_tipo: string;
  servico_descricao?: string;
  local_servico?: string;
  data_inicio: string;
  data_fim?: string;
  horario_inicio?: string;
  horario_fim?: string;
  carga_horaria: number;
  recorrencia: string;
  dias_semana: string[];
  total_ocorrencias?: number;
  ocorrencias_realizadas: number;
  valor_acordado: number;
  valor_adicional: number;
  desconto: number;
  valor_total?: number;
  forma_pagamento?: string;
  contratante_nome?: string;
  instrucoes?: string;
  observacoes?: string;
  created_at: string;
}

export interface DiaristSchedule {
  id: string;
  condominio_id: string;
  diarist_id: string;
  assignment_id?: string;
  data: string;
  horario_inicio_previsto: string;
  horario_fim_previsto: string;
  carga_horaria_prevista: number;
  checkin_at?: string;
  checkout_at?: string;
  horas_trabalhadas: number;
  horas_extras: number;
  status: ScheduleStatus;
  is_feriado: boolean;
  is_fim_semana: boolean;
  servico_tipo?: string;
  servico_descricao?: string;
  local_servico?: string;
  tarefas: string[];
  tarefas_concluidas: string[];
  avaliacao_nota?: number;
  avaliacao_comentario?: string;
  valor_base?: number;
  valor_hora_extra: number;
  valor_adicional: number;
  valor_desconto: number;
  valor_total?: number;
  observacoes?: string;
  created_at: string;
}

export interface DiaristPayment {
  id: string;
  condominio_id: string;
  diarist_id: string;
  assignment_id?: string;
  periodo_inicio: string;
  periodo_fim: string;
  competencia?: string;
  valor_diarias: number;
  quantidade_diarias: number;
  valor_horas_extras: number;
  quantidade_horas_extras: number;
  valor_adicional: number;
  valor_desconto: number;
  valor_bruto?: number;
  valor_liquido?: number;
  inss_retido: number;
  iss_retido: number;
  irrf_retido: number;
  outras_retencoes: number;
  status: PaymentStatus;
  forma_pagamento?: string;
  data_vencimento?: string;
  data_pagamento?: string;
  comprovante_url?: string;
  observacoes?: string;
  created_at: string;
}

export interface DiaristEvaluation {
  id: string;
  condominio_id: string;
  diarist_id: string;
  schedule_id?: string;
  avaliador_nome?: string;
  avaliador_tipo?: string;
  nota_geral: number;
  nota_pontualidade?: number;
  nota_qualidade?: number;
  nota_profissionalismo?: number;
  nota_comunicacao?: number;
  nota_cuidado?: number;
  comentario?: string;
  pontos_positivos: string[];
  pontos_melhorar: string[];
  recomendaria: boolean;
  contrataria_novamente: boolean;
  servico_tipo?: string;
  data_servico?: string;
  is_publicada: boolean;
  is_anonima: boolean;
  resposta?: string;
  resposta_at?: string;
  created_at: string;
}

export interface DiaristStats {
  total: number;
  ativos: number;
  inativos: number;
  bloqueados: number;
  por_tipo: Record<string, number>;
  media_avaliacao_geral: number;
  total_diarias_mes: number;
  total_valor_mes: number;
}

export interface DiaristSuggestion {
  diarist_id: string;
  diarist_nome: string;
  diarist_tipo: string;
  score: number;
  motivo: string;
  disponivel: boolean;
  valor_diaria: number;
  media_avaliacao: number;
  total_diarias: number;
}

export interface BatchScheduleItem {
  diarist_id: string;
  horario_inicio?: string;
  horario_fim?: string;
  servico_tipo?: string;
  servico_descricao?: string;
  local_servico?: string;
  observacoes?: string;
}

export interface BatchScheduleCreate {
  condominio_id: string;
  data: string;
  items: BatchScheduleItem[];
}

export interface BatchScheduleResponse {
  total_criados: number;
  total_erros: number;
  erros: string[];
  schedules: DiaristSchedule[];
}

export interface PayrollDiaristItem {
  diarist_id: string;
  diarist_nome: string;
  cpf: string;
  quantidade_diarias: number;
  total_horas: number;
  valor_diaria: number;
  valor_bruto: number;
  inss_retido: number;
  valor_liquido: number;
  pix?: string;
  banco?: string;
  agencia?: string;
  conta?: string;
}

export interface PayrollReport {
  competencia: string;
  periodo_inicio: string;
  periodo_fim: string;
  total_diaristas: number;
  total_diarias: number;
  valor_bruto_total: number;
  inss_total: number;
  valor_liquido_total: number;
  items: PayrollDiaristItem[];
}

export interface PayrollGenerateRequest {
  condominio_id: string;
  competencia: string;
  diarist_ids?: string[];
  forma_pagamento?: string;
}

export interface PayrollGenerateResponse {
  competencia: string;
  total_gerados: number;
  total_erros: number;
  erros: string[];
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

const BASE_URL = '/api/v1/operacional/diaristas';

// Interface para resposta do backend (diferente do frontend)
interface BackendDiarist {
  id: string;
  created_at: string;
  updated_at?: string;
  ativo: boolean;
  nome: string;
  cpf: string;
  rg?: string;
  data_nascimento?: string;
  telefone?: string;
  telefone_emergencia?: string;
  email?: string;
  foto_url?: string;
  endereco?: string;
  cidade?: string;
  estado?: string;
  cep?: string;
  tipos_servico: string[];
  especialidades: string[];
  experiencia_anos: number;
  dias_disponiveis: string[];
  hora_inicio_disponivel?: string;
  hora_fim_disponivel?: string;
  aceita_hora_extra: boolean;
  valor_hora?: number;
  valor_diaria: number;
  valor_hora_extra?: number;
  banco?: string;
  agencia?: string;
  conta?: string;
  tipo_conta?: string;
  pix?: string;
  status: string;
  avaliacao_media: number;
  total_avaliacoes: number;
  total_servicos: number;
}

// Adapter para converter backend -> frontend
function adaptDiarist(backend: BackendDiarist): Diarist {
  return {
    id: backend.id,
    condominio_id: '',
    codigo: '',
    nome: backend.nome,
    cpf: backend.cpf,
    rg: backend.rg,
    data_nascimento: backend.data_nascimento,
    email: backend.email,
    telefone: backend.telefone,
    celular: backend.telefone,
    whatsapp: backend.telefone,
    cep: backend.cep,
    logradouro: backend.endereco,
    cidade: backend.cidade,
    estado: backend.estado,
    tipo: (backend.tipos_servico?.[0] as DiaristType) || 'outros',
    especialidades: backend.especialidades || [],
    experiencia_anos: backend.experiencia_anos || 0,
    dias_disponiveis: backend.dias_disponiveis || [],
    horario_inicio: backend.hora_inicio_disponivel,
    horario_fim: backend.hora_fim_disponivel,
    carga_horaria_max: 8,
    aceita_hora_extra: backend.aceita_hora_extra,
    valor_diaria: backend.valor_diaria,
    valor_hora_extra: backend.valor_hora_extra,
    status: (backend.status as DiaristStatus) || 'ativo',
    is_blocked: backend.status === 'bloqueado',
    total_diarias: backend.total_servicos || 0,
    total_horas: 0,
    total_recebido: 0,
    media_avaliacao: Number(backend.avaliacao_media) || 0,
    total_avaliacoes: backend.total_avaliacoes || 0,
    taxa_comparecimento: 100,
    taxa_pontualidade: 100,
    score_confiabilidade: 100,
    score_qualidade: 100,
    tags: [],
    foto_url: backend.foto_url,
    created_at: backend.created_at,
    updated_at: backend.updated_at,
  };
}

export const diaristsService = {
  // === Diaristas CRUD ===

  async list(
    page = 1,
    pageSize = 20,
    status?: DiaristStatus,
    tipo?: DiaristType,
    search?: string
  ): Promise<PaginatedResponse<Diarist>> {
    const params: Record<string, unknown> = { page, page_size: pageSize };
    if (status) params.status = status;
    if (tipo) params.tipo = tipo;
    if (search) params.search = search;

    const response = await api.get<{ items: BackendDiarist[]; total: number; page: number; page_size: number; pages: number }>(`${BASE_URL}/`, { params });

    return {
      items: response.data.items.map(adaptDiarist),
      total: response.data.total,
      page: response.data.page,
      page_size: response.data.page_size,
      pages: response.data.pages,
    };
  },

  async getById(id: string): Promise<Diarist> {
    const response = await api.get<Diarist>(`${BASE_URL}/${id}`);
    return response.data;
  },

  async create(data: DiaristCreate): Promise<Diarist> {
    const response = await api.post<Diarist>(`${BASE_URL}/`, data);
    return response.data;
  },

  async update(id: string, data: DiaristUpdate): Promise<Diarist> {
    const response = await api.patch<Diarist>(`${BASE_URL}/${id}`, data);
    return response.data;
  },

  async activate(id: string): Promise<Diarist> {
    const response = await api.post<Diarist>(`${BASE_URL}/${id}/activate`);
    return response.data;
  },

  async deactivate(id: string): Promise<Diarist> {
    const response = await api.post<Diarist>(`${BASE_URL}/${id}/deactivate`);
    return response.data;
  },

  async getMetrics(id: string): Promise<{ metrics: Record<string, unknown> }> {
    const response = await api.get(`${BASE_URL}/${id}/metrics`);
    return response.data;
  },

  async getAvailable(date?: string, tipo?: DiaristType): Promise<Diarist[]> {
    const params: Record<string, unknown> = {};
    if (date) params.date = date;
    if (tipo) params.tipo = tipo;

    const response = await api.get<Diarist[]>(`${BASE_URL}/available`, { params });
    return response.data;
  },

  // === Assignments (Alocações) ===

  async listAssignments(
    diaristId?: string,
    status?: AssignmentStatus
  ): Promise<DiaristAssignment[]> {
    const params: Record<string, unknown> = {};
    if (diaristId) params.diarist_id = diaristId;
    if (status) params.status = status;

    const response = await api.get<DiaristAssignment[]>(`${BASE_URL}/assignments`, { params });
    return response.data;
  },

  async createAssignment(data: Partial<DiaristAssignment>): Promise<DiaristAssignment> {
    const response = await api.post<DiaristAssignment>(`${BASE_URL}/assignments`, data);
    return response.data;
  },

  async cancelAssignment(id: string): Promise<DiaristAssignment> {
    const response = await api.post<DiaristAssignment>(`${BASE_URL}/assignments/${id}/cancel`);
    return response.data;
  },

  // === Schedules (Agenda) ===

  async listSchedules(
    diaristId?: string,
    date?: string,
    status?: ScheduleStatus
  ): Promise<DiaristSchedule[]> {
    const params: Record<string, unknown> = {};
    if (diaristId) params.diarist_id = diaristId;
    if (date) params.date = date;
    if (status) params.status = status;

    const response = await api.get<DiaristSchedule[]>(`${BASE_URL}/schedules`, { params });
    return response.data;
  },

  async getTodaySchedules(): Promise<DiaristSchedule[]> {
    const response = await api.get<DiaristSchedule[]>(`${BASE_URL}/schedules/today`);
    return response.data;
  },

  async createSchedule(data: Partial<DiaristSchedule>): Promise<DiaristSchedule> {
    const response = await api.post<DiaristSchedule>(`${BASE_URL}/schedules`, data);
    return response.data;
  },

  async confirmSchedule(id: string): Promise<DiaristSchedule> {
    const response = await api.post<DiaristSchedule>(`${BASE_URL}/schedules/${id}/confirm`);
    return response.data;
  },

  async cancelSchedule(id: string): Promise<DiaristSchedule> {
    const response = await api.post<DiaristSchedule>(`${BASE_URL}/schedules/${id}/cancel`);
    return response.data;
  },

  async checkin(data: { latitude?: number; longitude?: number; foto_url?: string }): Promise<DiaristSchedule> {
    const response = await api.post<DiaristSchedule>(`${BASE_URL}/schedules/checkin`, data);
    return response.data;
  },

  async checkout(data: {
    latitude?: number;
    longitude?: number;
    foto_url?: string;
    tarefas_concluidas?: string[];
  }): Promise<DiaristSchedule> {
    const response = await api.post<DiaristSchedule>(`${BASE_URL}/schedules/checkout`, data);
    return response.data;
  },

  // === Payments (Pagamentos) ===

  async listPayments(
    diaristId?: string,
    status?: PaymentStatus
  ): Promise<DiaristPayment[]> {
    const params: Record<string, unknown> = {};
    if (diaristId) params.diarist_id = diaristId;
    if (status) params.status = status;

    const response = await api.get<DiaristPayment[]>(`${BASE_URL}/payments`, { params });
    return response.data;
  },

  async getPendingPayments(): Promise<DiaristPayment[]> {
    const response = await api.get<DiaristPayment[]>(`${BASE_URL}/payments/pending`);
    return response.data;
  },

  async generatePayments(data: {
    diarist_id: string;
    periodo_inicio: string;
    periodo_fim: string;
  }): Promise<DiaristPayment> {
    const response = await api.post<DiaristPayment>(`${BASE_URL}/payments/generate`, data);
    return response.data;
  },

  async processPayment(id: string, data: {
    forma_pagamento: PaymentMethod;
    comprovante_url?: string;
  }): Promise<DiaristPayment> {
    const response = await api.post<DiaristPayment>(`${BASE_URL}/payments/${id}/process`, data);
    return response.data;
  },

  // === Evaluations (Avaliações) ===

  async listEvaluations(diaristId?: string): Promise<DiaristEvaluation[]> {
    const params: Record<string, unknown> = {};
    if (diaristId) params.diarist_id = diaristId;

    const response = await api.get<DiaristEvaluation[]>(`${BASE_URL}/evaluations`, { params });
    return response.data;
  },

  async createEvaluation(data: Partial<DiaristEvaluation>): Promise<DiaristEvaluation> {
    const response = await api.post<DiaristEvaluation>(`${BASE_URL}/evaluations`, data);
    return response.data;
  },

  // === AI Features ===

  async getSuggestions(data: {
    servico_tipo: string;
    data: string;
    horario_inicio?: string;
    horario_fim?: string;
  }): Promise<DiaristSuggestion[]> {
    const response = await api.get<DiaristSuggestion[]>(`${BASE_URL}/ai/suggest`, { params: data });
    return response.data;
  },

  async checkAvailability(diaristId: string, date: string): Promise<{
    diarist_id: string;
    diarist_nome: string;
    data: string;
    disponivel: boolean;
    motivo?: string;
  }> {
    const response = await api.get(`${BASE_URL}/ai/availability`, {
      params: { diarist_id: diaristId, date }
    });
    return response.data;
  },

  async getPerformance(diaristId: string): Promise<{
    diarist_id: string;
    diarist_nome: string;
    periodo: string;
    total_diarias: number;
    total_horas: number;
    taxa_comparecimento: number;
    taxa_pontualidade: number;
    media_avaliacao: number;
    total_recebido: number;
    tendencia: string;
    recomendacoes: string[];
  }> {
    const response = await api.get(`${BASE_URL}/ai/performance/${diaristId}`);
    return response.data;
  },

  async optimizeSchedule(date: string): Promise<{
    data: string;
    sugestoes: Array<Record<string, unknown>>;
    conflitos: Array<Record<string, unknown>>;
    recomendacoes: string[];
  }> {
    const response = await api.get(`${BASE_URL}/ai/optimize`, { params: { date } });
    return response.data;
  },

  // === Statistics ===

  // === Batch Schedule (Escala Diaria) ===

  async createBatchSchedules(data: BatchScheduleCreate): Promise<BatchScheduleResponse> {
    const response = await api.post<BatchScheduleResponse>(`${BASE_URL}/schedules/batch`, data);
    return response.data;
  },

  // === Payroll (Fechamento de Folha) ===

  async getPayrollReport(competencia: string, condominioId?: string): Promise<PayrollReport> {
    const params: Record<string, unknown> = { competencia };
    if (condominioId) params.condominio_id = condominioId;
    const response = await api.get<PayrollReport>(`${BASE_URL}/payments/payroll-report`, { params });
    return response.data;
  },

  async generatePayrollPayments(data: PayrollGenerateRequest): Promise<PayrollGenerateResponse> {
    const response = await api.post<PayrollGenerateResponse>(`${BASE_URL}/payments/payroll-generate`, data);
    return response.data;
  },

  // === Statistics ===

  async getStatsByCondominio(condominioId: string): Promise<DiaristStats> {
    const response = await api.get<DiaristStats>(`${BASE_URL}/statistics/condominio/${condominioId}`);
    return response.data;
  },

  async getRanking(): Promise<Array<{
    diarist_id: string;
    diarist_nome: string;
    score: number;
    media_avaliacao: number;
    total_diarias: number;
  }>> {
    const response = await api.get(`${BASE_URL}/statistics/ranking`);
    return response.data;
  },
};

// Labels para exibição
export const DIARIST_TYPE_LABELS: Record<DiaristType, string> = {
  limpeza: 'Limpeza',
  portaria: 'Portaria',
  manutencao: 'Manutenção',
  jardinagem: 'Jardinagem',
  outros: 'Outros',
};

export const DIARIST_STATUS_LABELS: Record<DiaristStatus, string> = {
  ativo: 'Ativo',
  inativo: 'Inativo',
  bloqueado: 'Bloqueado',
  em_avaliacao: 'Em Avaliação',
};

export const SCHEDULE_STATUS_LABELS: Record<ScheduleStatus, string> = {
  agendado: 'Agendado',
  confirmado: 'Confirmado',
  em_andamento: 'Em Andamento',
  concluido: 'Concluído',
  falta: 'Falta',
  cancelado: 'Cancelado',
};

export const PAYMENT_STATUS_LABELS: Record<PaymentStatus, string> = {
  pendente: 'Pendente',
  aprovado: 'Aprovado',
  pago: 'Pago',
  cancelado: 'Cancelado',
};

export default diaristsService;
