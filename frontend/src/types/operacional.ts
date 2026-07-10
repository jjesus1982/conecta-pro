/**
 * Tipos para o módulo Operacional
 */

// Enums
export type PostType =
  | 'vigilante'
  | 'porteiro'
  | 'recepcionista'
  | 'controlador_acesso'
  | 'supervisor'
  | 'lider'
  | 'rondante'
  | 'monitoramento'
  | 'manutencao'
  | 'servicos_gerais'
  | 'jardinagem'
  | 'portaria';

export type PostStatus = 'active' | 'inactive' | 'temporary' | 'suspended';

export type ShiftType =
  | 'diurno'
  | 'noturno'
  | 'manha'
  | 'tarde'
  | 'noite'
  | 'administrativo'
  | 'integral'
  | '12x36';

// Post (Posto de Trabalho)
export interface Post {
  id: string;
  code: string;
  name: string;
  description: string | null;
  post_type: PostType;
  status: PostStatus;
  shift_type: ShiftType;
  contract_id: string | null;
  client_id: string | null;
  address: string | null;
  city: string | null;
  state: string | null;
  zip_code: string | null;
  latitude: number | null;
  longitude: number | null;
  shift_start_time: string | null;
  shift_end_time: string | null;
  break_duration_minutes: number;
  night_shift_bonus_percent: number;
  hazard_pay_percent: number;
  required_certifications: Record<string, unknown> | null;
  required_headcount: number;
  current_headcount: number;
  requires_experience_months: number;
  hourly_rate: number;
  monthly_cost: number;
  requires_armed: boolean;
  requires_vehicle: boolean;
  supervisor_name: string | null;
  supervisor_phone: string | null;
  emergency_contact: string | null;
  emergency_phone: string | null;
  notes: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  // Computed properties
  is_filled: boolean;
  vacancy_count: number;
  daily_hours: number;
}

export interface PostCreate {
  name: string;
  description?: string;
  post_type: PostType;
  shift_type: ShiftType;
  contract_id?: string;
  client_id?: string;
  address?: string;
  city?: string;
  state?: string;
  zip_code?: string;
  latitude?: number;
  longitude?: number;
  shift_start_time?: string;
  shift_end_time?: string;
  break_duration_minutes?: number;
  night_shift_bonus_percent?: number;
  hazard_pay_percent?: number;
  required_certifications?: Record<string, unknown>;
  required_headcount?: number;
  requires_experience_months?: number;
  hourly_rate?: number;
  monthly_cost?: number;
  requires_armed?: boolean;
  requires_vehicle?: boolean;
  supervisor_name?: string;
  supervisor_phone?: string;
  emergency_contact?: string;
  emergency_phone?: string;
  notes?: string;
}

export interface PostUpdate extends Partial<PostCreate> {
  status?: PostStatus;
  is_active?: boolean;
}

export interface PostFilter {
  post_type?: PostType;
  status?: PostStatus;
  shift_type?: ShiftType;
  contract_id?: string;
  client_id?: string;
  city?: string;
  state?: string;
  requires_armed?: boolean;
  requires_vehicle?: boolean;
  has_vacancy?: boolean;
  search?: string;
}

export interface PostStats {
  total: number;
  by_status: Record<string, number>;
  by_type: Record<string, number>;
  by_shift: Record<string, number>;
  filled: number;
  with_vacancy: number;
  total_headcount: number;
  total_allocated: number;
  total_monthly_cost: number;
}

// Allocation (Alocação)
export type AllocationStatus =
  | 'active'
  | 'inactive'
  | 'pending'
  | 'suspended'
  | 'terminated';

export interface Allocation {
  id: string;
  post_id: string;
  employee_id: string;
  status: AllocationStatus;
  start_date: string;
  end_date: string | null;
  is_primary: boolean;
  is_temporary: boolean;
  hourly_rate: number;
  monthly_salary: number;
  additional_benefits: number;
  role: string | null;
  qualifications: Record<string, unknown> | null;
  notes: string | null;
  termination_reason: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  // Computed
  is_current: boolean;
  days_allocated: number;
  total_monthly_cost: number;
  // Dados denormalizados do funcionário
  employee_name?: string | null;
  employee_matricula?: string | null;
  employee_cargo?: string | null;
  // Dados denormalizados do posto
  post_name?: string | null;
  post_code?: string | null;
}

export interface AllocationCreate {
  post_id: string;
  employee_id: string;
  start_date: string;
  end_date?: string | null;
  is_primary?: boolean;
  is_temporary?: boolean;
  hourly_rate?: number;
  monthly_salary?: number;
  additional_benefits?: number;
  role?: string;
  qualifications?: Record<string, unknown>;
  notes?: string;
}

export interface AllocationUpdate {
  status?: AllocationStatus;
  end_date?: string | null;
  is_primary?: boolean;
  is_temporary?: boolean;
  hourly_rate?: number;
  monthly_salary?: number;
  additional_benefits?: number;
  role?: string;
  qualifications?: Record<string, unknown>;
  notes?: string;
  termination_reason?: string;
  is_active?: boolean;
}

export interface AllocationTerminate {
  end_date: string;
  termination_reason: string;
  notes?: string;
}

export interface AllocationFilter {
  post_id?: string;
  employee_id?: string;
  status?: AllocationStatus;
  is_primary?: boolean;
  is_temporary?: boolean;
  is_current?: boolean;
  start_date_from?: string;
  start_date_to?: string;
}

// Shift (Turnos)
export type ShiftStatus =
  | 'scheduled'
  | 'in_progress'
  | 'completed'
  | 'missed'
  | 'partial'
  | 'substituted'
  | 'cancelled'
  | 'off_day';

export interface Shift {
  id: string;
  scale_id: string;
  employee_id: string | null;
  post_id: string;
  shift_date: string;
  planned_start_time: string;
  planned_end_time: string;
  planned_break_minutes: number;
  actual_start_time: string | null;
  actual_end_time: string | null;
  actual_break_minutes: number | null;
  status: ShiftStatus;
  is_holiday: boolean;
  is_night_shift: boolean;
  is_overtime: boolean;
  is_off_day: boolean;
  needs_substitution: boolean;
  planned_hours: number;
  actual_hours: number;
  overtime_hours: number;
  night_hours: number;
  base_pay: number;
  overtime_pay: number;
  night_bonus: number;
  holiday_bonus: number;
  total_pay: number;
  notes: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  // Computed
  is_future: boolean;
  is_today: boolean;
  is_filled: boolean;
  was_worked: boolean;
}

export interface ShiftCreate {
  scale_id: string;
  employee_id?: string | null;
  post_id: string;
  shift_date: string;
  planned_start_time: string;
  planned_end_time: string;
  planned_break_minutes?: number;
  is_off_day?: boolean;
  notes?: string | null;
  is_holiday?: boolean;
  is_night_shift?: boolean;
  is_overtime?: boolean;
  planned_hours?: number;
}

export interface ShiftUpdate {
  employee_id?: string | null;
  planned_start_time?: string;
  planned_end_time?: string;
  planned_break_minutes?: number;
  actual_start_time?: string | null;
  actual_end_time?: string | null;
  actual_break_minutes?: number | null;
  status?: ShiftStatus;
  is_off_day?: boolean;
  is_overtime?: boolean;
  needs_substitution?: boolean;
  actual_hours?: number;
  overtime_hours?: number;
  notes?: string | null;
  is_active?: boolean;
}

export interface ShiftFilter {
  scale_id?: string;
  employee_id?: string;
  post_id?: string;
  status?: ShiftStatus;
  start_date?: string;
  end_date?: string;
  is_holiday?: boolean;
  is_night_shift?: boolean;
  is_off_day?: boolean;
  is_filled?: boolean;
  needs_substitution?: boolean;
}

export interface ShiftCheckIn {
  actual_start_time: string;
  notes?: string;
}

export interface ShiftCheckOut {
  actual_end_time: string;
  actual_break_minutes?: number;
  notes?: string;
}

// Reports (Relatorios)
export interface CoverageReportItem {
  post_id: string;
  post_name: string;
  total_allocations: number;
  active_allocations: number;
  coverage_rate: number;
}

export interface CoverageReportResponse {
  start_date: string;
  end_date: string;
  total_posts: number;
  total_allocations: number;
  active_allocations: number;
  coverage_rate: number;
  items: CoverageReportItem[];
}

export interface HoursReportItem {
  employee_id: string;
  total_shifts: number;
  total_hours: number;
  overtime_hours: number;
}

export interface HoursReportResponse {
  start_date: string;
  end_date: string;
  total_employees: number;
  total_hours: number;
  total_overtime: number;
  items: HoursReportItem[];
}

export interface CostsReportItem {
  post_id: string;
  post_name: string;
  total_shifts: number;
  total_cost: number;
}

export interface CostsReportResponse {
  start_date: string;
  end_date: string;
  total_posts: number;
  total_cost: number;
  items: CostsReportItem[];
}

// Employee (funcionário) - usado em Operacional
export interface Employee {
  id: string;
  full_name?: string | null;
  name?: string | null;
  email?: string | null;
  registration?: string | null;
  status?: string | null;
}

// Pagination
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// Labels para display
export const POST_TYPE_LABELS: Record<PostType, string> = {
  vigilante: 'Agente de Portaria',
  porteiro: 'Porteiro',
  recepcionista: 'Recepcionista',
  controlador_acesso: 'Controlador de Acesso',
  supervisor: 'Supervisor',
  lider: 'Líder',
  rondante: 'Rondante',
  monitoramento: 'Monitoramento',
  manutencao: 'Manutenção',
  servicos_gerais: 'Serviços Gerais',
  jardinagem: 'Jardinagem',
  portaria: 'Portaria',
};

export const POST_STATUS_LABELS: Record<PostStatus, string> = {
  active: 'Ativo',
  inactive: 'Inativo',
  temporary: 'Temporário',
  suspended: 'Suspenso',
};

export const SHIFT_STATUS_LABELS: Record<ShiftStatus, string> = {
  scheduled: 'Agendado',
  in_progress: 'Em andamento',
  completed: 'Concluido',
  missed: 'Falta',
  partial: 'Parcial',
  substituted: 'Substituido',
  cancelled: 'Cancelado',
  off_day: 'Folga',
};

export const ALLOCATION_STATUS_LABELS: Record<AllocationStatus, string> = {
  active: 'Ativa',
  inactive: 'Inativa',
  pending: 'Pendente',
  suspended: 'Suspensa',
  terminated: 'Encerrada',
};

export const SHIFT_TYPE_LABELS: Record<ShiftType, string> = {
  diurno: 'Diurno (07h-19h)',
  noturno: 'Noturno (19h-07h)',
  manha: 'Manhã (06h-14h)',
  tarde: 'Tarde (14h-22h)',
  noite: 'Noite (22h-06h)',
  administrativo: 'Administrativo (08h-18h)',
  integral: 'Integral (24h)',
  '12x36': '12x36',
};

// Scale Types
export type ScaleType =
  | '12x36'
  | '6x1'
  | '5x2'
  | '5x1'
  | '4x2'
  | 'turno_revezamento'
  | 'administrativo'
  | 'personalizado';

export type ScaleStatus =
  | 'draft'
  | 'pending_approval'
  | 'approved'
  | 'published'
  | 'in_progress'
  | 'completed'
  | 'cancelled';

// Scale (Escala de Trabalho)
export interface Scale {
  id: string;
  post_id: string;
  scale_type: ScaleType;
  status: ScaleStatus;
  month: number;
  year: number;
  name: string | null;
  description: string | null;
  start_date: string | null;
  end_date: string | null;
  total_shifts: number;
  filled_shifts: number;
  total_hours: number;
  overtime_hours: number;
  estimated_cost: number;
  config: Record<string, unknown> | null;
  notes: string | null;
  approved_by: string | null;
  approved_at: string | null;
  approval_notes: string | null;
  published_by: string | null;
  published_at: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  created_by: string | null;
  // Computed
  is_current_month: boolean;
  is_published: boolean;
  can_edit: boolean;
  fill_rate: number;
}

export interface ScaleCreate {
  post_id: string;
  scale_type?: ScaleType;
  month: number;
  year: number;
  notes?: string;
  config?: Record<string, unknown>;
}

export interface ScaleUpdate {
  scale_type?: ScaleType;
  status?: ScaleStatus;
  notes?: string;
  config?: Record<string, unknown>;
  is_active?: boolean;
}

export interface ScaleFilter {
  post_id?: string;
  scale_type?: ScaleType;
  status?: ScaleStatus;
  month?: number;
  year?: number;
  is_current_month?: boolean;
}

export interface ScaleGenerateRequest {
  post_id: string;
  month: number;
  year: number;
  scale_type: ScaleType;
  employee_ids: string[];
  config?: {
    consider_holidays?: boolean;
    balance_night_shifts?: boolean;
    max_consecutive_days?: number;
    min_rest_hours?: number;
  };
}

export interface ScaleStats {
  total: number;
  by_status: Record<string, number>;
  by_type: Record<string, number>;
  total_hours: number;
  total_overtime_hours: number;
  total_estimated_cost: number;
  avg_fill_rate: number;
}

export const SCALE_TYPE_LABELS: Record<ScaleType, string> = {
  '12x36': '12x36 (12h trabalho, 36h descanso)',
  '6x1': '6x1 (6 dias trabalho, 1 folga)',
  '5x2': '5x2 (Segunda a Sexta)',
  '5x1': '5x1 (5 dias trabalho, 1 folga)',
  '4x2': '4x2 (4 dias trabalho, 2 folgas)',
  turno_revezamento: 'Revezamento (Manhã/Tarde/Noite)',
  administrativo: 'Administrativo',
  personalizado: 'Personalizado',
};

export const SCALE_STATUS_LABELS: Record<ScaleStatus, string> = {
  draft: 'Rascunho',
  pending_approval: 'Aguardando Aprovação',
  approved: 'Aprovada',
  published: 'Publicada',
  in_progress: 'Em Andamento',
  completed: 'Concluída',
  cancelled: 'Cancelada',
};

// ===========================
// Occurrences (Ocorrências Disciplinares)
// ===========================

export type OccurrenceType =
  | 'abandono_posto'
  | 'falta_uniforme'
  | 'falta_epi'
  | 'dormindo_servico'
  | 'uso_celular'
  | 'falta_limpeza'
  | 'postura_inadequada'
  | 'atraso'
  | 'falta_injustificada'
  | 'nao_conformidade_documental'
  | 'embriaguez'
  | 'desrespeito'
  | 'negligencia'
  | 'insubordinacao'
  | 'outros';

export type OccurrenceSeverity = 'leve' | 'moderada' | 'grave' | 'gravissima';

export type OccurrenceCategory =
  | 'disciplinar'
  | 'seguranca'
  | 'operacional'
  | 'administrativa'
  | 'tecnica';

export type OccurrenceStatus =
  | 'aberta'
  | 'em_analise'
  | 'resolvida'
  | 'encerrada'
  | 'cancelada';

export interface Occurrence {
  id: string;
  code: string;
  title: string;
  description: string;
  occurrence_type: OccurrenceType;
  severity: OccurrenceSeverity;
  category: OccurrenceCategory;
  status: OccurrenceStatus;
  // Envolvidos
  employee_id: string;
  employee_name?: string;
  inspector_id: string;
  inspector_name?: string;
  post_id: string;
  post_name?: string;
  patrol_round_id: string | null;
  // Datas
  occurred_at: string;
  resolved_at: string | null;
  created_at: string;
  updated_at: string;
  // Resolução
  resolved_by_id: string | null;
  resolved_by_name?: string | null;
  resolution_notes: string | null;
  corrective_action: string | null;
  // Anexos e evidências
  attachments: OccurrenceAttachment[];
  witnesses: string | null;
  // Flags
  is_active: boolean;
}

export interface OccurrenceAttachment {
  type: 'photo' | 'video' | 'document' | 'audio';
  url: string;
  name?: string;
  size?: number;
  uploaded_at?: string;
}

export interface OccurrenceCreate {
  title: string;
  description: string;
  occurrence_type: OccurrenceType;
  severity: OccurrenceSeverity;
  category: OccurrenceCategory;
  employee_id: string;
  post_id: string;
  patrol_round_id?: string | null;
  occurred_at?: string;
  witnesses?: string | null;
}

export interface OccurrenceUpdate {
  title?: string;
  description?: string;
  occurrence_type?: OccurrenceType;
  severity?: OccurrenceSeverity;
  category?: OccurrenceCategory;
  status?: OccurrenceStatus;
  witnesses?: string | null;
}

export interface OccurrenceResolve {
  resolution_notes: string;
  corrective_action?: string;
}

export interface OccurrenceFilter {
  occurrence_type?: OccurrenceType;
  severity?: OccurrenceSeverity;
  category?: OccurrenceCategory;
  status?: OccurrenceStatus;
  employee_id?: string;
  inspector_id?: string;
  post_id?: string;
  patrol_round_id?: string;
  date_from?: string;
  date_to?: string;
  search?: string;
}

export interface OccurrenceStats {
  total: number;
  by_status: Record<string, number>;
  by_severity: Record<string, number>;
  by_category: Record<string, number>;
  by_type: Record<string, number>;
  pending_resolution: number;
  resolved_this_month: number;
  avg_resolution_time_hours: number;
}

// Labels para display
export const OCCURRENCE_TYPE_LABELS: Record<OccurrenceType, string> = {
  abandono_posto: 'Abandono de Posto',
  falta_uniforme: 'Falta de Uniforme',
  falta_epi: 'Falta de EPI',
  dormindo_servico: 'Dormindo em Serviço',
  uso_celular: 'Uso Indevido de Celular',
  falta_limpeza: 'Falta de Limpeza',
  postura_inadequada: 'Postura Inadequada',
  atraso: 'Atraso',
  falta_injustificada: 'Falta Injustificada',
  nao_conformidade_documental: 'Não Conformidade Documental',
  embriaguez: 'Embriaguez',
  desrespeito: 'Desrespeito',
  negligencia: 'Negligência',
  insubordinacao: 'Insubordinação',
  outros: 'Outros',
};

export const OCCURRENCE_SEVERITY_LABELS: Record<OccurrenceSeverity, string> = {
  leve: 'Leve (Advertência Verbal)',
  moderada: 'Moderada (Advertência Escrita)',
  grave: 'Grave (Suspensão)',
  gravissima: 'Gravíssima (Demissão)',
};

export const OCCURRENCE_CATEGORY_LABELS: Record<OccurrenceCategory, string> = {
  disciplinar: 'Disciplinar',
  seguranca: 'Segurança',
  operacional: 'Operacional',
  administrativa: 'Administrativa',
  tecnica: 'Técnica',
};

export const OCCURRENCE_STATUS_LABELS: Record<OccurrenceStatus, string> = {
  aberta: 'Aberta',
  em_analise: 'Em Análise',
  resolvida: 'Resolvida',
  encerrada: 'Encerrada',
  cancelada: 'Cancelada',
};

// ===========================
// Patrol Rounds (Rondas de Inspeção)
// ===========================

export type PatrolRoundStatus =
  | 'agendada'
  | 'em_andamento'
  | 'pausada'
  | 'concluida'
  | 'cancelada';

export type InspectorRole =
  | 'gerente_operacional'
  | 'supervisor_operacional'
  | 'inspetor_operacional'
  | 'lider_servico';

export type CheckpointType =
  | 'verificacao_posto'
  | 'verificacao_funcionario'
  | 'registro_ocorrencia'
  | 'medida_disciplinar'
  | 'observacao_geral'
  | 'foto_evidencia'
  | 'checkin_condominio'
  | 'checkout_condominio'
  | 'reuniao'
  | 'alteracao_operacional';

/**
 * Foto anexada a um checkpoint (upload via POST /{round}/checkpoints/{cp}/fotos).
 * Type alias (não interface) para manter compatibilidade estrutural com o
 * schema gerado `{ [key: string]: unknown }`.
 */
export type CheckpointPhoto = {
  arquivo?: string;
  url?: string;
  tamanho_bytes?: number;
  enviada_em?: string;
  // Campos legados (fotos antigas gravadas como metadado livre)
  type?: string;
  name?: string;
};

export type CheckpointStatus =
  | 'conforme'
  | 'nao_conforme'
  | 'pendente'
  | 'com_ocorrencia';

export interface PatrolCheckpoint {
  id: string;
  inspection_round_id: string;
  post_id: string | null;
  post_name: string | null;
  client_id: string | null;
  client_name: string | null;
  checkpoint_type: CheckpointType;
  status: CheckpointStatus;
  employee_id: string | null;
  employee_name: string | null;
  employee_cpf: string | null;
  employee_position: string | null;
  occurrence_id: string | null;
  occurrence_code: string | null;
  disciplinary_action_id: string | null;
  disciplinary_action_code: string | null;
  disciplinary_action_type: string | null;
  title: string | null;
  description: string | null;
  observations: string | null;
  infraction_category: string | null;
  infraction_severity: string | null;
  photos: CheckpointPhoto[] | null;
  latitude: number | null;
  longitude: number | null;
  sequence: number;
  created_at: string;
}

export interface PatrolRound {
  id: string;
  code: string;
  tenant_id: string;
  inspector_id: string;
  inspector_name: string;
  inspector_role: InspectorRole;
  status: PatrolRoundStatus;
  scheduled_date: string | null;
  started_at: string | null;
  completed_at: string | null;
  duration_minutes: number | null;
  posts_to_visit: string[] | null;
  posts_visited: string[] | null;
  total_checkpoints: number;
  total_occurrences: number;
  total_disciplinary_actions: number;
  total_employees_checked: number;
  observations: string | null;
  summary: string | null;
  start_latitude: number | null;
  start_longitude: number | null;
  end_latitude: number | null;
  end_longitude: number | null;
  total_distance_km: number | null;
  progress_percentage: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  checkpoints?: PatrolCheckpoint[];
}

export interface PatrolRoundCreate {
  tenant_id: string;
  inspector_id: string;
  inspector_name: string;
  inspector_role?: InspectorRole;
  scheduled_date?: string;
  posts_to_visit?: string[];
  observations?: string;
}

export interface PatrolRoundUpdate {
  scheduled_date?: string;
  posts_to_visit?: string[];
  observations?: string;
  summary?: string;
}

export interface PatrolRoundFilter {
  inspector_id?: string;
  inspector_role?: InspectorRole;
  status?: PatrolRoundStatus;
  post_id?: string;
  start_date?: string;
  end_date?: string;
  has_occurrences?: boolean;
  has_disciplinary_actions?: boolean;
}

export interface PatrolRoundStats {
  total_rounds: number;
  rounds_in_progress: number;
  rounds_completed: number;
  rounds_scheduled: number;
  total_occurrences: number;
  occurrences_pending: number;
  occurrences_resolved: number;
  total_disciplinary_actions: number;
  warnings_count: number;
  suspensions_count: number;
  rounds_today: number;
  rounds_this_week: number;
  rounds_this_month: number;
}

export interface CheckpointCreate {
  post_id?: string | null;
  post_name?: string | null;
  client_id?: string | null;
  client_name?: string | null;
  checkpoint_type?: CheckpointType;
  status?: CheckpointStatus;
  employee_id?: string | null;
  employee_name?: string | null;
  employee_cpf?: string | null;
  employee_position?: string | null;
  title?: string | null;
  description?: string | null;
  observations?: string | null;
  infraction_category?: string | null;
  infraction_severity?: string | null;
  photos?: CheckpointPhoto[] | null;
  latitude?: number | null;
  longitude?: number | null;
}

// Labels para display
export const PATROL_ROUND_STATUS_LABELS: Record<PatrolRoundStatus, string> = {
  agendada: 'Agendada',
  em_andamento: 'Em Andamento',
  pausada: 'Pausada',
  concluida: 'Concluída',
  cancelada: 'Cancelada',
};

export const INSPECTOR_ROLE_LABELS: Record<InspectorRole, string> = {
  gerente_operacional: 'Gerente Operacional',
  supervisor_operacional: 'Supervisor Operacional',
  inspetor_operacional: 'Inspetor Operacional',
  lider_servico: 'Líder de Serviço',
};

export const CHECKPOINT_TYPE_LABELS: Record<CheckpointType, string> = {
  verificacao_posto: 'Verificação de Posto',
  verificacao_funcionario: 'Verificação de Funcionário',
  registro_ocorrencia: 'Registro de Ocorrência',
  medida_disciplinar: 'Medida Disciplinar',
  observacao_geral: 'Observação Geral',
  foto_evidencia: 'Foto/Evidência',
  checkin_condominio: 'Check-in no condomínio',
  checkout_condominio: 'Check-out do condomínio',
  reuniao: 'Reunião',
  alteracao_operacional: 'Alteração operacional',
};

export const CHECKPOINT_STATUS_LABELS: Record<CheckpointStatus, string> = {
  conforme: 'Conforme',
  nao_conforme: 'Não Conforme',
  pendente: 'Pendente',
  com_ocorrencia: 'Com Ocorrência',
};

// ===========================
// Scale Templates (Templates de Escalas)
// ===========================

export interface ScaleTemplate {
  id: string;
  tenant_id: string;
  name: string;
  description: string | null;
  scale_type: ScaleType;
  post_id: string | null;
  post_name?: string | null;
  source_scale_id: string;
  // Metadados
  total_employees: number;
  coverage_percentage: number;
  pattern_days: number;
  // Estatísticas de uso
  times_used: number;
  last_used_at: string | null;
  // Audit
  created_by: string | null;
  created_by_name?: string | null;
  created_at: string;
  updated_at: string;
  is_active: boolean;
}

export interface ScaleTemplateCreate {
  name: string;
  description?: string | null;
  source_scale_id: string;
}

export interface ScaleTemplateUpdate {
  name?: string;
  description?: string | null;
  is_active?: boolean;
}

export interface ScaleTemplateApply {
  month: number;
  year: number;
  post_id?: string | null;
  employee_substitutions?: Record<string, string>;
}

export interface ScaleTemplateFilter {
  scale_type?: ScaleType;
  post_id?: string;
  search?: string;
}
