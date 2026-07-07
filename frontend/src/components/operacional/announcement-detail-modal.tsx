'use client';

import { X, Megaphone, Edit2, Send, Clock, CheckCircle, Users, Calendar, FileText, Eye, BarChart3 } from 'lucide-react';
import { useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { useAnnouncementReadStats } from '@/hooks/useAnnouncements';
import type { Announcement } from '@/lib/services/announcements';
import {
  ANNOUNCEMENT_CATEGORY_LABELS,
  ANNOUNCEMENT_STATUS_LABELS,
  ANNOUNCEMENT_PRIORITY_LABELS,
  ANNOUNCEMENT_TARGET_TYPE_LABELS,
} from '@/lib/services/announcements';

interface AnnouncementDetailModalProps {
  isOpen: boolean;
  onClose: () => void;
  announcement: Announcement | null;
  onEdit?: (announcement: Announcement) => void;
  onPublish?: (announcement: Announcement) => void;
}

const STATUS_COLORS: Record<string, string> = {
  rascunho: 'bg-gray-500/10 text-gray-500',
  agendado: 'bg-blue-500/10 text-blue-500',
  publicado: 'bg-green-500/10 text-green-500',
  arquivado: 'bg-purple-500/10 text-purple-500',
};

const PRIORITY_COLORS: Record<string, string> = {
  baixa: 'bg-gray-500/10 text-gray-500',
  normal: 'bg-blue-500/10 text-blue-500',
  alta: 'bg-orange-500/10 text-orange-500',
  urgente: 'bg-red-500/10 text-red-500',
};

export function AnnouncementDetailModal({
  isOpen,
  onClose,
  announcement,
  onEdit,
  onPublish,
}: AnnouncementDetailModalProps) {
  const { stats, isLoading: statsLoading, refresh: refreshStats } = useAnnouncementReadStats(
    announcement?.id || null
  );

  useEffect(() => {
    if (isOpen && announcement?.id) {
      refreshStats();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- Intentional deps
  }, [isOpen, announcement?.id]);

  if (!isOpen || !announcement) return null;

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-3xl max-h-[90vh] overflow-y-auto bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl shadow-xl m-4">
        {/* Header */}
        <div className="sticky top-0 z-10 flex items-center justify-between p-4 border-b border-[hsl(var(--border))] bg-[hsl(var(--card))]">
          <div className="flex items-center gap-2">
            <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
              <Megaphone className="w-5 h-5 text-blue-500" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-[hsl(var(--foreground))]">
                Detalhes do Comunicado
              </h2>
              <p className="text-xs text-[hsl(var(--muted-foreground))]">
                {ANNOUNCEMENT_CATEGORY_LABELS[announcement.category]}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {announcement.status === 'rascunho' && (
              <>
                {onEdit && (
                  <Button variant="outline" size="sm" onClick={() => onEdit(announcement)}>
                    <Edit2 className="w-4 h-4 mr-2" />
                    Editar
                  </Button>
                )}
                {onPublish && (
                  <Button variant="primary" size="sm" onClick={() => onPublish(announcement)}>
                    <Send className="w-4 h-4 mr-2" />
                    Publicar
                  </Button>
                )}
              </>
            )}
            <Button variant="ghost" size="sm" onClick={onClose}>
              <X className="w-4 h-4" />
            </Button>
          </div>
        </div>

        {/* Content */}
        <div className="p-4 space-y-6">
          {/* Status and Priority */}
          <div className="flex items-center gap-3 flex-wrap">
            <span
              className={`inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm font-medium ${
                STATUS_COLORS[announcement.status]
              }`}
            >
              {announcement.status === 'publicado' ? (
                <CheckCircle className="w-4 h-4" />
              ) : announcement.status === 'agendado' ? (
                <Clock className="w-4 h-4" />
              ) : (
                <FileText className="w-4 h-4" />
              )}
              {ANNOUNCEMENT_STATUS_LABELS[announcement.status]}
            </span>
            <span
              className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${
                PRIORITY_COLORS[announcement.priority]
              }`}
            >
              {ANNOUNCEMENT_PRIORITY_LABELS[announcement.priority]}
            </span>
            {announcement.requires_acknowledgment && (
              <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm font-medium bg-yellow-500/10 text-yellow-500">
                <CheckCircle className="w-4 h-4" />
                Requer Confirmacao
              </span>
            )}
          </div>

          {/* Title */}
          <div>
            <h3 className="text-xl font-semibold text-[hsl(var(--foreground))]">
              {announcement.title}
            </h3>
          </div>

          {/* Content */}
          <div className="bg-[hsl(var(--muted))] rounded-lg p-4">
            <p className="text-[hsl(var(--foreground))] whitespace-pre-wrap">
              {announcement.content}
            </p>
          </div>

          {/* Info Grid */}
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <div className="bg-[hsl(var(--muted))] rounded-lg p-3">
              <div className="flex items-center gap-2 mb-1">
                <Users className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />
                <span className="text-xs text-[hsl(var(--muted-foreground))]">Destinatarios</span>
              </div>
              <p className="text-sm font-medium text-[hsl(var(--foreground))]">
                {ANNOUNCEMENT_TARGET_TYPE_LABELS[announcement.target_type]}
              </p>
            </div>

            <div className="bg-[hsl(var(--muted))] rounded-lg p-3">
              <div className="flex items-center gap-2 mb-1">
                <Calendar className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />
                <span className="text-xs text-[hsl(var(--muted-foreground))]">Criado em</span>
              </div>
              <p className="text-sm font-medium text-[hsl(var(--foreground))]">
                {formatDate(announcement.created_at)}
              </p>
            </div>

            {announcement.published_at && (
              <div className="bg-[hsl(var(--muted))] rounded-lg p-3">
                <div className="flex items-center gap-2 mb-1">
                  <Send className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />
                  <span className="text-xs text-[hsl(var(--muted-foreground))]">Publicado em</span>
                </div>
                <p className="text-sm font-medium text-[hsl(var(--foreground))]">
                  {formatDate(announcement.published_at)}
                </p>
              </div>
            )}

            {announcement.publish_at && !announcement.published_at && (
              <div className="bg-[hsl(var(--muted))] rounded-lg p-3">
                <div className="flex items-center gap-2 mb-1">
                  <Clock className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />
                  <span className="text-xs text-[hsl(var(--muted-foreground))]">Agendado para</span>
                </div>
                <p className="text-sm font-medium text-[hsl(var(--foreground))]">
                  {formatDate(announcement.publish_at)}
                </p>
              </div>
            )}

            {announcement.expires_at && (
              <div className="bg-[hsl(var(--muted))] rounded-lg p-3">
                <div className="flex items-center gap-2 mb-1">
                  <Calendar className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />
                  <span className="text-xs text-[hsl(var(--muted-foreground))]">Expira em</span>
                </div>
                <p className="text-sm font-medium text-[hsl(var(--foreground))]">
                  {formatDate(announcement.expires_at)}
                </p>
              </div>
            )}
          </div>

          {/* Read Stats */}
          {announcement.is_published && (
            <div className="border border-[hsl(var(--border))] rounded-lg p-4">
              <div className="flex items-center gap-2 mb-4">
                <BarChart3 className="w-5 h-5 text-[hsl(var(--primary))]" />
                <h4 className="font-medium text-[hsl(var(--foreground))]">
                  Estatisticas de Leitura
                </h4>
              </div>

              {statsLoading ? (
                <div className="text-center py-4">
                  <p className="text-sm text-[hsl(var(--muted-foreground))]">Carregando...</p>
                </div>
              ) : stats ? (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="text-center">
                    <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                      {stats.total_recipients}
                    </p>
                    <p className="text-xs text-[hsl(var(--muted-foreground))]">Destinatarios</p>
                  </div>
                  <div className="text-center">
                    <p className="font-data text-2xl font-semibold tabular-nums text-blue-500">{stats.total_reads}</p>
                    <p className="text-xs text-[hsl(var(--muted-foreground))]">Leituras</p>
                  </div>
                  <div className="text-center">
                    <p className="font-data text-2xl font-semibold tabular-nums text-green-500">
                      {stats.read_percentage.toFixed(0)}%
                    </p>
                    <p className="text-xs text-[hsl(var(--muted-foreground))]">Taxa de Leitura</p>
                  </div>
                  {announcement.requires_acknowledgment && (
                    <div className="text-center">
                      <p className="font-data text-2xl font-semibold tabular-nums text-purple-500">
                        {stats.total_acknowledgments}
                      </p>
                      <p className="text-xs text-[hsl(var(--muted-foreground))]">Confirmacoes</p>
                    </div>
                  )}
                </div>
              ) : (
                <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                  <div className="text-center">
                    <p className="font-data text-2xl font-semibold tabular-nums text-blue-500">{announcement.read_count}</p>
                    <p className="text-xs text-[hsl(var(--muted-foreground))]">Leituras</p>
                  </div>
                  <div className="text-center">
                    <p className="font-data text-2xl font-semibold tabular-nums text-green-500">
                      {announcement.read_percentage.toFixed(0)}%
                    </p>
                    <p className="text-xs text-[hsl(var(--muted-foreground))]">Taxa de Leitura</p>
                  </div>
                  {announcement.requires_acknowledgment && (
                    <div className="text-center">
                      <p className="font-data text-2xl font-semibold tabular-nums text-purple-500">
                        {announcement.acknowledgment_count}
                      </p>
                      <p className="text-xs text-[hsl(var(--muted-foreground))]">Confirmacoes</p>
                    </div>
                  )}
                </div>
              )}

              {/* Progress Bar */}
              <div className="mt-4">
                <div className="flex items-center justify-between text-xs text-[hsl(var(--muted-foreground))] mb-1">
                  <span>Progresso de Leitura</span>
                  <span>{announcement.read_percentage.toFixed(0)}%</span>
                </div>
                <div className="h-2 bg-[hsl(var(--muted))] rounded-full overflow-hidden">
                  <div
                    className="h-full bg-[hsl(var(--primary))] transition-all duration-500"
                    style={{ width: `${announcement.read_percentage}%` }}
                  />
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
