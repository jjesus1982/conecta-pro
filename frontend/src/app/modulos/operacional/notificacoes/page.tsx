'use client';

import { Bell, Search, ArrowLeft, ChevronLeft, ChevronRight, RefreshCw, CheckCircle, CheckCheck, Trash2, AlertTriangle, Clock, Eye, Info, AlertCircle, XCircle, Zap } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
;
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { PageHeader } from '@/components/ui/page-header';
import { useAuth } from '@/hooks/useAuth';
import { useNotifications, useUnreadCount, useAlerts, useUserAlerts } from '@/hooks/useNotifications';
import {
  type Notification,
  type NotificationType,
  type Alert,
  type AlertSeverity,
  NOTIFICATION_TYPE_LABELS,
  ALERT_SEVERITY_LABELS,
} from '@/lib/services/notifications';

// Cores dos tipos de notificacao
const NOTIFICATION_TYPE_COLORS: Record<NotificationType, string> = {
  sistema: 'bg-blue-500/10 text-blue-500',
  operacional: 'bg-green-500/10 text-green-500',
  alerta: 'bg-red-500/10 text-red-500',
  comunicado: 'bg-purple-500/10 text-purple-500',
  tarefa: 'bg-orange-500/10 text-orange-500',
  lembrete: 'bg-yellow-500/10 text-yellow-500',
};

// Cores de severidade de alertas
const ALERT_SEVERITY_COLORS: Record<AlertSeverity, string> = {
  info: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
  warning: 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20',
  error: 'bg-red-500/10 text-red-500 border-red-500/20',
  critical: 'bg-red-600/20 text-red-600 border-red-600/30',
};

// Icone de severidade
const getSeverityIcon = (severity: AlertSeverity) => {
  switch (severity) {
    case 'info':
      return <Info className="w-5 h-5" />;
    case 'warning':
      return <AlertTriangle className="w-5 h-5" />;
    case 'error':
      return <XCircle className="w-5 h-5" />;
    case 'critical':
      return <Zap className="w-5 h-5" />;
    default:
      return <Info className="w-5 h-5" />;
  }
};

export default function NotificacoesPage() {
  const router = useRouter();
  const { isLoading: authLoading, isAuthenticated } = useAuth();

  // Notificações
  const {
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
    refresh,
    markAsRead,
    markAllAsRead,
    deleteNotification,
  } = useNotifications({ initialPageSize: 20, pollInterval: 60000 });

  // Contagem de nao lidas
  const { total: unreadTotal, byType, refresh: refreshCount } = useUnreadCount(30000);

  // Alertas ativos
  const { alerts, acknowledge: acknowledgeAlert, refresh: refreshAlerts } = useUserAlerts(30000);

  const [searchTerm, setSearchTerm] = useState('');
  const [selectedType, setSelectedType] = useState<NotificationType | ''>('');
  const [showOnlyUnread, setShowOnlyUnread] = useState(false);
  const [activeTab, setActiveTab] = useState<'notifications' | 'alerts'>('notifications');

  // Contagem do SINO no topo — MESMA fonte do NotificationBell (/api/v1/notifications/push).
  // Exibida como linha discreta abaixo do contador desta central para explicar as duas
  // contagens lado a lado. Se o fetch falhar, a linha simplesmente não aparece (null).
  const [pushUnread, setPushUnread] = useState<number | null>(null);
  useEffect(() => {
    if (process.env.NEXT_PUBLIC_ENABLE_PUSH_NOTIFICATIONS === 'false') return;
    const headers: Record<string, string> = {};
    if (typeof window !== 'undefined') {
      const token = localStorage.getItem('access_token');
      if (token) headers['Authorization'] = `Bearer ${token}`;
    }
    fetch('/api/v1/notifications/push', { headers, credentials: 'include' })
      .then((resp) => (resp.ok ? resp.json() : null))
      .then((data) => {
        if (data) setPushUnread(data.unread_count ?? 0);
      })
      .catch(() => {
        /* falha silenciosa — linha não é exibida */
      });
  }, []);

  // Redirecionar se nao autenticado
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [authLoading, isAuthenticated, router]);

  // Debounce search e filtros
  useEffect(() => {
    const timer = setTimeout(() => {
      setFilters({
        ...filters,
        type: selectedType || undefined,
        is_read: showOnlyUnread ? false : undefined,
      });
    }, 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- debounce filter sync
  }, [selectedType, showOnlyUnread]);

  const handleRefresh = () => {
    refresh();
    refreshCount();
    refreshAlerts();
  };

  const handleMarkAsRead = async (notification: Notification) => {
    if (!notification.is_read) {
      await markAsRead(notification.id);
      refreshCount();
    }
  };

  const handleMarkAllAsRead = async () => {
    await markAllAsRead();
    refreshCount();
    refresh();
  };

  const handleDelete = async (notification: Notification) => {
    await deleteNotification(notification.id);
    refreshCount();
  };

  const handleAcknowledgeAlert = async (alert: Alert) => {
    await acknowledgeAlert(alert.id);
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);

    if (minutes < 1) return 'Agora';
    if (minutes < 60) return `${minutes}min atras`;
    if (hours < 24) return `${hours}h atras`;
    if (days < 7) return `${days}d atras`;

    return date.toLocaleDateString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    });
  };

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))]">
        <div className="animate-pulse-slow text-[hsl(var(--primary))]">
          <Bell className="w-12 h-12" />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-grid">
      {/* Main content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <PageHeader
          eyebrow="OPERACIONAL"
          title="Notificações"
          subtitle={`${unreadTotal} nao lidas`}
          icon={
            <span className="relative flex items-center justify-center">
              <Bell className="w-5 h-5" />
              {unreadTotal > 0 && (
                <span className="absolute -top-2 -right-2 w-5 h-5 rounded-full bg-red-500 text-white text-xs flex items-center justify-center">
                  {unreadTotal > 99 ? '99+' : unreadTotal}
                </span>
              )}
            </span>
          }
          actions={
            <>
              <Link href="/modulos/operacional">
                <Button variant="ghost" size="sm">
                  <ArrowLeft className="w-4 h-4 mr-2" />
                  Operacional
                </Button>
              </Link>
              <Button variant="outline" onClick={handleRefresh} disabled={isLoading}>
                <RefreshCw className={`w-4 h-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
                Atualizar
              </Button>
              {unreadTotal > 0 && (
                <Button variant="outline" onClick={handleMarkAllAsRead}>
                  <CheckCheck className="w-4 h-4 mr-2" />
                  Marcar todas como lidas
                </Button>
              )}
            </>
          }
        />

        {/* Coerência sino × central: contagem do sino do topo, mesma fonte do NotificationBell */}
        {pushUnread !== null && (
          <p className="text-xs text-[hsl(var(--muted-foreground))] mb-6">
            Notificações push do app: {pushUnread} (a contagem do sino no topo)
          </p>
        )}

        {/* Alertas Ativos */}
        {alerts.length > 0 && (
          <div className="mb-6 space-y-3">
            <h2 className="text-sm font-medium text-[hsl(var(--foreground))] flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-yellow-500" />
              Alertas Ativos ({alerts.length})
            </h2>
            {alerts.map((alert) => (
              <div
                key={alert.id}
                className={`border rounded-xl p-4 ${ALERT_SEVERITY_COLORS[alert.severity]}`}
              >
                <div className="flex items-start gap-3">
                  {getSeverityIcon(alert.severity)}
                  <div className="flex-1">
                    <div className="flex items-center justify-between">
                      <h3 className="font-medium">{alert.title}</h3>
                      <span className="text-xs">{formatDate(alert.created_at)}</span>
                    </div>
                    <p className="text-sm mt-1 opacity-80">{alert.message}</p>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleAcknowledgeAlert(alert)}
                    className="shrink-0"
                  >
                    <CheckCircle className="w-4 h-4 mr-1" />
                    Confirmar
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Stats Cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-purple-500/10 flex items-center justify-center">
                <Bell className="w-5 h-5 text-purple-500" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">{total}</p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Total</p>
              </div>
            </div>
          </div>

          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-red-500/10 flex items-center justify-center">
                <Clock className="w-5 h-5 text-red-500" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">{unreadTotal}</p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Nao Lidas</p>
              </div>
            </div>
          </div>

          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-yellow-500/10 flex items-center justify-center">
                <AlertTriangle className="w-5 h-5 text-yellow-500" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">{alerts.length}</p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Alertas</p>
              </div>
            </div>
          </div>

          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-green-500/10 flex items-center justify-center">
                <CheckCircle className="w-5 h-5 text-green-500" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                  {total - unreadTotal}
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Lidas</p>
              </div>
            </div>
          </div>
        </div>

        {/* Filters */}
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4 mb-6">
          <div className="flex flex-col lg:flex-row gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[hsl(var(--muted-foreground))]" />
              <Input
                placeholder="Buscar notificacoes..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-10"
              />
            </div>
            <div className="flex flex-wrap gap-2">
              <select
                value={selectedType}
                onChange={(e) => setSelectedType(e.target.value as NotificationType | '')}
                className="px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))] text-sm"
              >
                <option value="">Todos os Tipos</option>
                {Object.entries(NOTIFICATION_TYPE_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
              <Button
                variant={showOnlyUnread ? 'primary' : 'outline'}
                size="sm"
                onClick={() => setShowOnlyUnread(!showOnlyUnread)}
              >
                <Eye className="w-4 h-4 mr-2" />
                {showOnlyUnread ? 'Mostrando nao lidas' : 'Mostrar apenas nao lidas'}
              </Button>
            </div>
          </div>
        </div>

        {/* Error state */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 mb-6 flex items-center gap-3">
            <AlertTriangle className="w-5 h-5 text-red-500" />
            <p className="text-red-500">{error}</p>
            <Button variant="outline" size="sm" onClick={handleRefresh} className="ml-auto">
              Tentar novamente
            </Button>
          </div>
        )}

        {/* Loading state */}
        {isLoading && (
          <div className="flex items-center justify-center py-12">
            <div className="animate-pulse-slow text-[hsl(var(--primary))]">
              <Bell className="w-8 h-8" />
            </div>
          </div>
        )}

        {/* Notifications List */}
        {!isLoading && !error && (
          <>
            <div className="space-y-2">
              {notifications.map((notification) => (
                <div
                  key={notification.id}
                  className={`bg-[hsl(var(--card))] border rounded-xl p-4 transition-colors ${
                    notification.is_read
                      ? 'border-[hsl(var(--border))] opacity-75'
                      : 'border-[hsl(var(--primary))]/30 bg-[hsl(var(--primary))]/5'
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <div
                      className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${
                        NOTIFICATION_TYPE_COLORS[notification.type]
                      }`}
                    >
                      <Bell className="w-5 h-5" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2">
                        <h3
                          className={`font-medium text-[hsl(var(--foreground))] ${
                            !notification.is_read ? 'font-semibold' : ''
                          }`}
                        >
                          {notification.title}
                        </h3>
                        <span className="text-xs text-[hsl(var(--muted-foreground))] shrink-0">
                          {formatDate(notification.created_at)}
                        </span>
                      </div>
                      <p className="text-sm text-[hsl(var(--muted-foreground))] mt-1">
                        {notification.body}
                      </p>
                      <div className="flex items-center gap-2 mt-2">
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                            NOTIFICATION_TYPE_COLORS[notification.type]
                          }`}
                        >
                          {NOTIFICATION_TYPE_LABELS[notification.type]}
                        </span>
                        {notification.reference_type && (
                          <span className="text-xs text-[hsl(var(--muted-foreground))]">
                            {notification.reference_type}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      {!notification.is_read && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleMarkAsRead(notification)}
                          title="Marcar como lida"
                        >
                          <CheckCircle className="w-4 h-4" />
                        </Button>
                      )}
                      {notification.action_url && (
                        <Link href={notification.action_url}>
                          <Button variant="ghost" size="sm" title="Ver detalhes">
                            <Eye className="w-4 h-4" />
                          </Button>
                        </Link>
                      )}
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDelete(notification)}
                        className="text-red-500 hover:text-red-600"
                        title="Excluir"
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* Empty state */}
            {notifications.length === 0 && !isLoading && (
              <div className="text-center py-12 bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl mt-4">
                <Bell className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
                <h3 className="text-lg font-medium text-[hsl(var(--foreground))]">
                  Nenhuma notificacao encontrada
                </h3>
                <p className="text-[hsl(var(--muted-foreground))] mt-1">
                  Ajuste os filtros ou aguarde novas notificacoes
                </p>
              </div>
            )}

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-4">
                <p className="text-sm text-[hsl(var(--muted-foreground))]">
                  Mostrando {(page - 1) * pageSize + 1} a{' '}
                  {Math.min(page * pageSize, total)} de {total} registros
                </p>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage(page - 1)}
                    disabled={page <= 1}
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </Button>
                  <span className="text-sm text-[hsl(var(--foreground))]">
                    Pagina {page} de {totalPages}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage(page + 1)}
                    disabled={page >= totalPages}
                  >
                    <ChevronRight className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
