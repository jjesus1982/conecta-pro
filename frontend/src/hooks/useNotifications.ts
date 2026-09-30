/**
 * Hooks para o módulo de Notificações e Alertas
 * Migrado para usar customInstance (Orval transport layer)
 */

import { useState, useEffect, useCallback } from 'react';
import { customInstance } from '@/lib/api-client';
import type {
  Notification,
  NotificationFilter,
  NotificationUnreadCount,
  NotificationListResponse,
  Alert,
  AlertCreate,
  AlertType,
  AlertSeverity,
  AlertListResponse,
} from '@/lib/services/notifications';

const NOTIFICATIONS_URL = '/api/v1/operacional/comunicacao/notificacoes';
const ALERTS_URL = '/api/v1/operacional/comunicacao/alertas';

function buildParams(obj: Record<string, unknown>): string {
  const params = new URLSearchParams();
  Object.entries(obj).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      params.append(key, String(value));
    }
  });
  return params.toString();
}

interface UseNotificationsOptions {
  initialPageSize?: number;
  autoLoad?: boolean;
  initialFilters?: NotificationFilter;
  pollInterval?: number;
}

interface UseNotificationsReturn {
  notifications: Notification[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
  isLoading: boolean;
  error: string | null;
  filters: NotificationFilter;
  setFilters: (filters: NotificationFilter) => void;
  setPage: (page: number) => void;
  setPageSize: (size: number) => void;
  refresh: () => Promise<void>;
  markAsRead: (id: string) => Promise<boolean>;
  markAsClicked: (id: string) => Promise<void>;
  markAllAsRead: () => Promise<boolean>;
  deleteNotification: (id: string) => Promise<boolean>;
}

export function useNotifications(options: UseNotificationsOptions = {}): UseNotificationsReturn {
  const { initialPageSize = 20, autoLoad = true, initialFilters = {}, pollInterval = 0 } = options;

  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(initialPageSize);
  const [totalPages, setTotalPages] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFiltersState] = useState<NotificationFilter>(initialFilters);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const qs = buildParams({ page, page_size: pageSize, ...filters });
      const response = await customInstance<NotificationListResponse>({
        url: `${NOTIFICATIONS_URL}?${qs}`,
        method: 'GET',
      });
      setNotifications(response.items);
      setTotal(response.total);
      setTotalPages(response.total_pages);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao carregar notificações');
      setNotifications([]);
    } finally {
      setIsLoading(false);
    }
  }, [filters, page, pageSize]);

  useEffect(() => {
    if (autoLoad) {
      fetchData();
    }
  }, [fetchData, autoLoad]);

  // Polling interval
  useEffect(() => {
    if (pollInterval > 0) {
      const interval = setInterval(fetchData, pollInterval);
      return () => clearInterval(interval);
    }
  }, [pollInterval, fetchData]);

  const setFilters = useCallback((newFilters: NotificationFilter) => {
    setFiltersState(newFilters);
    setPage(1);
  }, []);

  /**
   * Registra que a pessoa FOI para a tela. ⭐ LIDA ≠ CLICADA.
   *
   * 🔴 30/09/2026: `clicked_at` estava vazio nas 11.029 notificações da tabela — a coluna
   * existia e ninguém nunca escreveu nela. Eu li esse zero como «ninguém age sobre os
   * alertas» e afirmei isso ao dono; era falso, e tive de retirar. Campo que ninguém
   * escreve não é medida de comportamento, é ausência de instrumento.
   *
   * Abrir o sino e passar o olho é LIDA (acontece por rolagem). Ir para a tela é CLICADA —
   * e é ela que separa «vi» de «fui tratar».
   *
   * ⚠️ Nunca levanta: a métrica não pode impedir a navegação de quem ia resolver.
   */
  const markAsClicked = useCallback(async (id: string): Promise<void> => {
    try {
      await customInstance<void>({ url: `${NOTIFICATIONS_URL}/${id}/clicada`, method: 'POST' });
    } catch {
      /* métrica não bloqueia navegação */
    }
  }, []);

  const markAsRead = useCallback(async (id: string): Promise<boolean> => {
    try {
      await customInstance<Notification>({
        url: `${NOTIFICATIONS_URL}/${id}/lida`,
        method: 'POST',
      });
      setNotifications(prev =>
        prev.map(n => n.id === id ? { ...n, is_read: true, read_at: new Date().toISOString() } : n)
      );
      return true;
    } catch {
      return false;
    }
  }, []);

  const markAllAsRead = useCallback(async (): Promise<boolean> => {
    try {
      await customInstance<{ success: boolean; count: number }>({
        url: `${NOTIFICATIONS_URL}/marcar-todas`,
        method: 'POST',
        data: {},
      });
      setNotifications(prev =>
        prev.map(n => ({ ...n, is_read: true, read_at: new Date().toISOString() }))
      );
      return true;
    } catch {
      return false;
    }
  }, []);

  const deleteNotification = useCallback(async (id: string): Promise<boolean> => {
    try {
      await customInstance<void>({
        url: `${NOTIFICATIONS_URL}/${id}`,
        method: 'DELETE',
      });
      setNotifications(prev => prev.filter(n => n.id !== id));
      setTotal(prev => prev - 1);
      return true;
    } catch {
      return false;
    }
  }, []);

  return {
    notifications,
    total,
    page,
    pageSize,
    totalPages,
    isLoading,
    error,
    filters,
    setFilters,
    setPage,
    setPageSize,
    refresh: fetchData,
    markAsRead,
    markAsClicked,
    markAllAsRead,
    deleteNotification,
  };
}

export function useUnreadCount(pollInterval: number = 30000) {
  const [count, setCount] = useState<NotificationUnreadCount | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchCount = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const data = await customInstance<NotificationUnreadCount>({
        url: `${NOTIFICATIONS_URL}/nao-lidas/count`,
        method: 'GET',
      });
      setCount(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao carregar contagem');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCount();

    if (pollInterval > 0) {
      const interval = setInterval(fetchCount, pollInterval);
      return () => clearInterval(interval);
    }
  }, [fetchCount, pollInterval]);

  return {
    count,
    total: count?.total ?? 0,
    byType: count?.by_type ?? {},
    isLoading,
    error,
    refresh: fetchCount,
  };
}

// =============================================================================
// ALERTAS
// =============================================================================

interface UseAlertsOptions {
  autoLoad?: boolean;
  pollInterval?: number;
  filters?: {
    alert_type?: AlertType;
    severity?: AlertSeverity;
    reference_type?: string;
  };
}

interface UseAlertsReturn {
  alerts: Alert[];
  total: number;
  isLoading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  acknowledge: (id: string) => Promise<boolean>;
  createAlert: (data: AlertCreate) => Promise<Alert | null>;
}

export function useAlerts(options: UseAlertsOptions = {}): UseAlertsReturn {
  const { autoLoad = true, pollInterval = 30000, filters } = options;

  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const qs = filters ? buildParams(filters as Record<string, unknown>) : '';
      const response = await customInstance<AlertListResponse>({
        url: `${ALERTS_URL}${qs ? `?${qs}` : ''}`,
        method: 'GET',
      });
      setAlerts(response.items);
      setTotal(response.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao carregar alertas');
      setAlerts([]);
    } finally {
      setIsLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    if (autoLoad) {
      fetchData();
    }
  }, [fetchData, autoLoad]);

  // Polling interval
  useEffect(() => {
    if (pollInterval > 0) {
      const interval = setInterval(fetchData, pollInterval);
      return () => clearInterval(interval);
    }
  }, [pollInterval, fetchData]);

  const acknowledge = useCallback(async (id: string): Promise<boolean> => {
    try {
      await customInstance<Alert>({
        url: `${ALERTS_URL}/${id}/acknowledge`,
        method: 'POST',
      });
      setAlerts(prev => prev.filter(a => a.id !== id));
      setTotal(prev => prev - 1);
      return true;
    } catch {
      return false;
    }
  }, []);

  const createAlert = useCallback(async (data: AlertCreate): Promise<Alert | null> => {
    try {
      const alert = await customInstance<Alert>({
        url: ALERTS_URL,
        method: 'POST',
        data,
      });
      setAlerts(prev => [alert, ...prev]);
      setTotal(prev => prev + 1);
      return alert;
    } catch {
      return null;
    }
  }, []);

  return {
    alerts,
    total,
    isLoading,
    error,
    refresh: fetchData,
    acknowledge,
    createAlert,
  };
}

export function useUserAlerts(pollInterval: number = 30000) {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await customInstance<AlertListResponse>({
        url: `${ALERTS_URL}/ativos`,
        method: 'GET',
      });
      setAlerts(response.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao carregar alertas');
      setAlerts([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();

    if (pollInterval > 0) {
      const interval = setInterval(fetchData, pollInterval);
      return () => clearInterval(interval);
    }
  }, [fetchData, pollInterval]);

  const acknowledge = useCallback(async (id: string): Promise<boolean> => {
    try {
      await customInstance<Alert>({
        url: `${ALERTS_URL}/${id}/acknowledge`,
        method: 'POST',
      });
      setAlerts(prev => prev.filter(a => a.id !== id));
      return true;
    } catch {
      return false;
    }
  }, []);

  return {
    alerts,
    total: alerts.length,
    criticalCount: alerts.filter(a => a.is_critical).length,
    isLoading,
    error,
    refresh: fetchData,
    acknowledge,
  };
}
