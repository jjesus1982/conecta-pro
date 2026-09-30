/**
 * Serviço de API para Notificações e Alertas
 * @author Conecta PRO Team
 * @date 2026-01-28
 */

import api from '@/lib/api';

// =============================================================================
// TIPOS - NOTIFICAÇÕES
// =============================================================================

export type NotificationType = 'sistema' | 'operacional' | 'alerta' | 'comunicado' | 'tarefa' | 'lembrete';

export interface Notification {
  id: string;
  tenant_id: string;
  user_id: string;
  title: string;
  body: string;
  type: NotificationType;
  reference_type: string | null;
  reference_id: string | null;
  channels: string[];
  sent_at: string | null;
  read_at: string | null;
  clicked_at: string | null;
  action_url: string | null;
  extra_data: Record<string, unknown> | null;
  is_active: boolean;
  created_at: string;
  // Propriedades calculadas
  is_sent: boolean;
  is_read: boolean;
  is_clicked: boolean;
}

export interface NotificationFilter {
  type?: NotificationType;
  is_read?: boolean;
  reference_type?: string;
  created_after?: string;
  created_before?: string;
}

export interface NotificationListResponse {
  items: Notification[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface NotificationUnreadCount {
  total: number;
  by_type: Record<string, number>;
}

// =============================================================================
// TIPOS - ALERTAS
// =============================================================================

export type AlertType = 'sistema' | 'seguranca' | 'operacional' | 'manutencao' | 'emergencia';
export type AlertSeverity = 'info' | 'warning' | 'error' | 'critical';

export interface Alert {
  id: string;
  tenant_id: string;
  alert_type: AlertType;
  severity: AlertSeverity;
  title: string;
  message: string;
  reference_type: string | null;
  reference_id: string | null;
  target_users: string[] | null;
  target_roles: string[] | null;
  acknowledged_by: string[] | null;
  expires_at: string | null;
  is_active: boolean;
  created_at: string;
  // Propriedades calculadas
  is_critical: boolean;
  is_expired: boolean;
  acknowledgment_count: number;
  is_fully_acknowledged: boolean;
}

export interface AlertCreate {
  alert_type?: AlertType;
  severity?: AlertSeverity;
  title: string;
  message: string;
  reference_type?: string;
  reference_id?: string;
  target_users?: string[];
  target_roles?: string[];
  expires_in_minutes?: number;
}

export interface AlertListResponse {
  items: Alert[];
  total: number;
}

// Labels para exibição
export const NOTIFICATION_TYPE_LABELS: Record<NotificationType, string> = {
  sistema: 'Sistema',
  operacional: 'Operacional',
  alerta: 'Alerta',
  comunicado: 'Comunicado',
  tarefa: 'Tarefa',
  lembrete: 'Lembrete',
};

export const ALERT_TYPE_LABELS: Record<AlertType, string> = {
  sistema: 'Sistema',
  seguranca: 'Segurança',
  operacional: 'Operacional',
  manutencao: 'Manutenção',
  emergencia: 'Emergência',
};

export const ALERT_SEVERITY_LABELS: Record<AlertSeverity, string> = {
  info: 'Informação',
  warning: 'Aviso',
  error: 'Erro',
  critical: 'Crítico',
};

// =============================================================================
// SERVICE - NOTIFICAÇÕES
// =============================================================================

const NOTIFICATIONS_URL = '/api/v1/operacional/comunicacao/notificacoes';
const ALERTS_URL = '/api/v1/operacional/comunicacao/alertas';

export const notificationsService = {
  /**
   * Lista notificações com paginação e filtros
   */
  async list(
    page: number = 1,
    pageSize: number = 20,
    filters?: NotificationFilter
  ): Promise<NotificationListResponse> {
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

    const response = await api.get<NotificationListResponse>(
      `${NOTIFICATIONS_URL}?${params.toString()}`
    );
    return response.data;
  },

  /**
   * Obtém contagem de não lidas
   */
  async getUnreadCount(): Promise<NotificationUnreadCount> {
    const response = await api.get<NotificationUnreadCount>(
      `${NOTIFICATIONS_URL}/nao-lidas/count`
    );
    return response.data;
  },

  /**
   * Marca notificação como lida
   */
  async markAsRead(id: string): Promise<Notification> {
    const response = await api.post<Notification>(
      `${NOTIFICATIONS_URL}/${id}/lida`
    );
    return response.data;
  },

  /**
   * Registra que a pessoa FOI para a tela — distinto de lida.
   *
   * 🔴 30/09/2026: `clicked_at` estava vazio nas 11.029 notificações da tabela. A coluna
   * existia e ninguém nunca escreveu nela — e eu cheguei a afirmar «ninguém age sobre os
   * alertas» lendo esse zero. Campo que ninguém escreve não é medida de comportamento.
   *
   * ⚠️ Best-effort: nunca levanta. Se o registro falhar, a navegação segue — perder a
   * métrica é barato, travar quem ia resolver não é.
   */
  async markAsClicked(id: string): Promise<void> {
    try {
      await api.post(`${NOTIFICATIONS_URL}/${id}/clicada`);
    } catch {
      /* métrica não bloqueia navegação */
    }
  },

  /**
   * Marca todas notificações como lidas
   */
  async markAllAsRead(notificationIds?: string[]): Promise<{ success: boolean; count: number }> {
    const response = await api.post<{ success: boolean; count: number }>(
      `${NOTIFICATIONS_URL}/marcar-todas`,
      { notification_ids: notificationIds }
    );
    return response.data;
  },

  /**
   * Remove notificação
   */
  async delete(id: string): Promise<void> {
    await api.delete(`${NOTIFICATIONS_URL}/${id}`);
  },
};

// =============================================================================
// SERVICE - ALERTAS
// =============================================================================

export const alertsService = {
  /**
   * Lista alertas ativos
   */
  async listActive(filters?: {
    alert_type?: AlertType;
    severity?: AlertSeverity;
    reference_type?: string;
  }): Promise<AlertListResponse> {
    const params = new URLSearchParams();

    if (filters) {
      Object.entries(filters).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== '') {
          params.append(key, String(value));
        }
      });
    }

    const response = await api.get<AlertListResponse>(
      `${ALERTS_URL}?${params.toString()}`
    );
    return response.data;
  },

  /**
   * Lista alertas ativos do usuário
   */
  async listUserAlerts(): Promise<AlertListResponse> {
    const response = await api.get<AlertListResponse>(`${ALERTS_URL}/ativos`);
    return response.data;
  },

  /**
   * Confirma alerta
   */
  async acknowledge(id: string): Promise<Alert> {
    const response = await api.post<Alert>(`${ALERTS_URL}/${id}/acknowledge`);
    return response.data;
  },

  /**
   * Cria alerta
   */
  async create(data: AlertCreate): Promise<Alert> {
    const response = await api.post<Alert>(ALERTS_URL, data);
    return response.data;
  },
};

const notificationsApi = { notificationsService, alertsService };

export default notificationsApi;
