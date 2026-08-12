/**
 * Serviço de API para Comunicados
 * @author Conecta PRO Team
 * @date 2026-01-28
 */

import api from '@/lib/api';

// =============================================================================
// TIPOS
// =============================================================================

export type AnnouncementStatus = 'rascunho' | 'agendado' | 'publicado' | 'arquivado';
export type AnnouncementPriority = 'baixa' | 'normal' | 'alta' | 'urgente';
export type AnnouncementCategory = 'informativo' | 'operacional' | 'rh' | 'seguranca' | 'treinamento' | 'outro';
export type AnnouncementTargetType = 'all' | 'roles' | 'users' | 'posts';

export interface AnnouncementAttachment {
  url: string;
  name: string;
  type: string;
  size: number;
}

export interface Announcement {
  id: string;
  tenant_id: string;
  target_type: AnnouncementTargetType;
  target_ids: string[] | null;
  target_roles: string[] | null;
  title: string;
  content: string;
  priority: AnnouncementPriority;
  category: AnnouncementCategory;
  publish_at: string | null;
  expires_at: string | null;
  requires_acknowledgment: boolean;
  attachments: AnnouncementAttachment[] | null;
  status: AnnouncementStatus;
  published_by: string | null;
  published_at: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  created_by: string | null;
  // Propriedades calculadas
  is_published: boolean;
  is_expired: boolean;
  is_scheduled: boolean;
  read_count: number;
  acknowledgment_count: number;
  read_percentage: number;
}

export interface AnnouncementCreate {
  title: string;
  content: string;
  target_type?: AnnouncementTargetType;
  target_ids?: string[];
  target_roles?: string[];
  priority?: AnnouncementPriority;
  category?: AnnouncementCategory;
  requires_acknowledgment?: boolean;
  publish_at?: string;
  expires_at?: string;
  attachments?: AnnouncementAttachment[];
}

export interface AnnouncementUpdate {
  title?: string;
  content?: string;
  target_type?: AnnouncementTargetType;
  target_ids?: string[];
  target_roles?: string[];
  priority?: AnnouncementPriority;
  category?: AnnouncementCategory;
  publish_at?: string;
  expires_at?: string;
  requires_acknowledgment?: boolean;
  attachments?: AnnouncementAttachment[];
  is_active?: boolean;
}

export interface AnnouncementFilter {
  status?: AnnouncementStatus;
  priority?: AnnouncementPriority;
  category?: AnnouncementCategory;
  target_type?: AnnouncementTargetType;
  requires_acknowledgment?: boolean;
  search?: string;
  created_after?: string;
  created_before?: string;
}

export interface AnnouncementListResponse {
  items: Announcement[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface AnnouncementReadResponse {
  id: string;
  announcement_id: string;
  user_id: string;
  read_at: string;
  acknowledged_at: string | null;
  is_acknowledged: boolean;
}

export interface AnnouncementReadStats {
  total_recipients: number;
  total_reads: number;
  total_acknowledgments: number;
  read_percentage: number;
  acknowledgment_percentage: number;
  reads: AnnouncementReadResponse[];
}

// Labels para exibição
export const ANNOUNCEMENT_STATUS_LABELS: Record<AnnouncementStatus, string> = {
  rascunho: 'Rascunho',
  agendado: 'Agendado',
  publicado: 'Publicado',
  arquivado: 'Arquivado',
};

export const ANNOUNCEMENT_PRIORITY_LABELS: Record<AnnouncementPriority, string> = {
  baixa: 'Baixa',
  normal: 'Normal',
  alta: 'Alta',
  urgente: 'Urgente',
};

export const ANNOUNCEMENT_CATEGORY_LABELS: Record<AnnouncementCategory, string> = {
  informativo: 'Informativo',
  operacional: 'Operacional',
  rh: 'RH',
  seguranca: 'Segurança',
  treinamento: 'Treinamento',
  outro: 'Outro',
};

export const ANNOUNCEMENT_TARGET_TYPE_LABELS: Record<AnnouncementTargetType, string> = {
  all: 'Todos',
  roles: 'Por Função',
  users: 'Usuários Específicos',
  posts: 'Por Posto',
};

// =============================================================================
// SERVICE
// =============================================================================

const BASE_URL = '/api/v1/operacional/comunicacao/comunicados';

export const announcementsService = {
  /**
   * Lista comunicados com paginação e filtros
   */
  async list(
    page: number = 1,
    pageSize: number = 20,
    filters?: AnnouncementFilter
  ): Promise<AnnouncementListResponse> {
    const params = new URLSearchParams();
    params.append('page', String(page));
    params.append('page_size', String(pageSize));

    if (filters) {
      Object.entries(filters).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== '') {
          params.append(key, String(value));
        }
      });
    }

    const response = await api.get<AnnouncementListResponse>(
      `${BASE_URL}?${params.toString()}`
    );
    return response.data;
  },

  /**
   * Lista comunicados não lidos
   */
  async listUnread(
    page: number = 1,
    pageSize: number = 20
  ): Promise<AnnouncementListResponse> {
    const params = new URLSearchParams();
    params.append('page', String(page));
    params.append('page_size', String(pageSize));

    const response = await api.get<AnnouncementListResponse>(
      `${BASE_URL}/nao-lidos?${params.toString()}`
    );
    return response.data;
  },

  /**
   * Busca comunicado por ID
   */
  async getById(id: string): Promise<Announcement> {
    const response = await api.get<Announcement>(`${BASE_URL}/${id}`);
    return response.data;
  },

  /**
   * Cria novo comunicado
   */
  async create(data: AnnouncementCreate): Promise<Announcement> {
    const response = await api.post<Announcement>(BASE_URL, data);
    return response.data;
  },

  /**
   * Atualiza comunicado
   */
  async update(id: string, data: AnnouncementUpdate): Promise<Announcement> {
    const response = await api.patch<Announcement>(`${BASE_URL}/${id}`, data);
    return response.data;
  },

  /**
   * Deleta comunicado (soft delete)
   */
  async delete(id: string): Promise<void> {
    await api.delete(`${BASE_URL}/${id}`);
  },

  /**
   * Publica comunicado
   */
  async publish(id: string, scheduleAt?: string): Promise<Announcement> {
    const response = await api.post<Announcement>(
      `${BASE_URL}/${id}/publicar`,
      { schedule_at: scheduleAt }
    );
    return response.data;
  },

  /**
   * Confirma leitura de comunicado
   */
  async acknowledge(id: string): Promise<{ success: boolean; acknowledged_at: string }> {
    const response = await api.post<{ success: boolean; acknowledged_at: string }>(
      `${BASE_URL}/${id}/confirmar`,
      {}
    );
    return response.data;
  },

  /**
   * Obtém estatísticas de leitura
   */
  async getReadStats(id: string): Promise<AnnouncementReadStats> {
    const response = await api.get<AnnouncementReadStats>(
      `${BASE_URL}/${id}/leituras`
    );
    return response.data;
  },
};

export default announcementsService;
