'use client';

import { ArrowLeft, Calendar, Clock, MapPin, Shield, Users, AlertCircle, CheckCircle, RefreshCw, User } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useRouter, useParams } from 'next/navigation';
import Link from 'next/link';
;
import { Button } from '@/components/ui/button';
import { PageHeader } from '@/components/ui/page-header';
import { useAuth } from '@/hooks/useAuth';
import { usePermission, Permission } from '@/hooks/usePermission';
import { useScale, useScaleOperations } from '@/hooks/useScales';
import { useShifts } from '@/hooks/useShifts';
import { useEmployees } from '@/hooks/useEmployees';
import { usePosts } from '@/hooks/usePosts';
import { ScaleEditor } from '@/components/operacional/scale-editor';
import type { ScaleStatus, ShiftStatus } from '@/types/operacional';
import {
  SCALE_TYPE_LABELS,
  SCALE_STATUS_LABELS,
  SHIFT_STATUS_LABELS,
} from '@/types/operacional';

export default function ScaleDetailPage() {
  const router = useRouter();
  const params = useParams();
  const scaleId = params?.id as string;

  const { isLoading: authLoading, isAuthenticated } = useAuth();
  const { scale, isLoading: scaleLoading, error: scaleError, refresh: refreshScale } = useScale(scaleId);
  const { shifts, isLoading: shiftsLoading, error: shiftsError, refresh: refreshShifts } = useShifts({
    autoLoad: true,
    initialPageSize: 500,
    initialFilters: { scale_id: scaleId },
  });
  const { employees, isLoading: employeesLoading } = useEmployees({ initialPageSize: 200 });
  const { posts } = usePosts({ initialPageSize: 100 });
  const { submitForApproval, approveScale, publishScale, getLastError, isLoading: operationLoading } = useScaleOperations();
  const { canManageScales, canApproveScales, hasPermission } = usePermission();
  const canPublishScales = hasPermission(Permission.SCALES_PUBLISH);

  // Feedback visível das transições (a página não tem toast global)
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // Auth check
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [authLoading, isAuthenticated, router]);

  // Helper functions
  const getPostName = (postId: string): string => {
    const post = posts.find((p) => p.id === postId);
    return post?.name || 'Desconhecido';
  };

  const getStatusColor = (status: ScaleStatus) => {
    switch (status) {
      case 'draft':
        return 'bg-gray-500/10 text-gray-500 border-gray-500/20';
      case 'pending_approval':
        return 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20';
      case 'approved':
        return 'bg-green-500/10 text-green-500 border-green-500/20';
      case 'published':
        return 'bg-blue-500/10 text-blue-500 border-blue-500/20';
      case 'in_progress':
        return 'bg-cyan-500/10 text-cyan-500 border-cyan-500/20';
      case 'completed':
        return 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20';
      case 'cancelled':
        return 'bg-red-500/10 text-red-500 border-red-500/20';
      default:
        return 'bg-gray-500/10 text-gray-500 border-gray-500/20';
    }
  };

  const getShiftStatusColor = (status: ShiftStatus) => {
    switch (status) {
      case 'scheduled':
        return 'bg-blue-500/10 text-blue-500';
      case 'in_progress':
        return 'bg-cyan-500/10 text-cyan-500';
      case 'completed':
        return 'bg-green-500/10 text-green-500';
      case 'missed':
        return 'bg-red-500/10 text-red-500';
      case 'partial':
        return 'bg-orange-500/10 text-orange-500';
      case 'substituted':
        return 'bg-purple-500/10 text-purple-500';
      case 'cancelled':
        return 'bg-gray-500/10 text-gray-500';
      case 'off_day':
        return 'bg-gray-500/10 text-gray-500';
      default:
        return 'bg-gray-500/10 text-gray-500';
    }
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    });
  };

  const formatTime = (timeStr: string) => {
    return timeStr.substring(0, 5); // HH:MM
  };

  const monthNames = [
    'Janeiro', 'Fevereiro', 'Marco', 'Abril', 'Maio', 'Junho',
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
  ];

  const handleRefresh = () => {
    refreshScale();
    refreshShifts();
  };

  // Mensagem de erro visível a partir do último erro da operação (com status HTTP)
  const feedbackFromError = (fallback: string): string => {
    const opError = getLastError();
    if (opError?.status === 403) return 'Você não tem permissão para esta ação';
    return opError?.message || fallback;
  };

  // Status operations
  const handleSubmitForApproval = async () => {
    if (!scale) return;
    setFeedback(null);
    const result = await submitForApproval(scale.id);
    if (result) {
      setFeedback({ type: 'success', message: 'Escala enviada para aprovação' });
      handleRefresh();
    } else {
      setFeedback({ type: 'error', message: feedbackFromError('Erro ao enviar para aprovação') });
    }
  };

  const handleApprove = async () => {
    if (!scale) return;
    setFeedback(null);
    const result = await approveScale(scale.id);
    if (result) {
      setFeedback({ type: 'success', message: 'Escala aprovada' });
      handleRefresh();
    } else {
      setFeedback({ type: 'error', message: feedbackFromError('Erro ao aprovar escala') });
    }
  };

  const handlePublish = async () => {
    if (!scale) return;
    setFeedback(null);
    const result = await publishScale(scale.id, true);
    if (result) {
      setFeedback({ type: 'success', message: 'Escala publicada' });
      handleRefresh();
    } else {
      setFeedback({ type: 'error', message: feedbackFromError('Erro ao publicar escala') });
    }
  };

  // Loading state
  if (authLoading || scaleLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))]">
        <div className="animate-pulse-slow text-[hsl(var(--primary))]">
          <Calendar className="w-12 h-12" />
        </div>
      </div>
    );
  }

  // Error state
  if (scaleError || !scale) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))]">
        <div className="text-center">
          <AlertCircle className="w-12 h-12 text-red-500 mx-auto mb-4" />
          <h2 className="text-xl font-semibold text-[hsl(var(--foreground))] mb-2">
            Erro ao carregar escala
          </h2>
          <p className="text-[hsl(var(--muted-foreground))] mb-4">
            {scaleError || 'Escala nao encontrada'}
          </p>
          <Link href="/modulos/operacional/escalas">
            <Button>
              <ArrowLeft className="w-4 h-4 mr-2" />
              Voltar para Escalas
            </Button>
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-grid">
      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <PageHeader
          eyebrow="OPERACIONAL · ESCALAS"
          title={`Escala: ${monthNames[scale.month - 1]} ${scale.year}`}
          subtitle={getPostName(scale.post_id)}
          icon={<Calendar className="w-5 h-5" />}
          actions={
            <>
              <Link href="/modulos/operacional/escalas">
                <Button variant="ghost" size="sm">
                  <ArrowLeft className="w-4 h-4 mr-2" />
                  Voltar
                </Button>
              </Link>
              {/* Status Badge */}
              <span
                className={`inline-flex items-center px-3 py-1.5 rounded-full text-xs font-medium border ${getStatusColor(
                  scale.status as ScaleStatus
                )}`}
              >
                {SCALE_STATUS_LABELS[scale.status as ScaleStatus] || scale.status}
              </span>

              {/* Action Buttons */}
              {scale.status === 'draft' && canManageScales && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleSubmitForApproval}
                  disabled={operationLoading}
                >
                  <CheckCircle className="w-4 h-4 mr-2" />
                  Enviar para Aprovação
                </Button>
              )}

              {scale.status === 'pending_approval' && canApproveScales && (
                <Button
                  variant="outline"
                  size="sm"
                  className="text-green-500 border-green-500/20 hover:bg-green-500/10"
                  onClick={handleApprove}
                  disabled={operationLoading}
                >
                  <CheckCircle className="w-4 h-4 mr-2" />
                  Aprovar
                </Button>
              )}

              {scale.status === 'approved' && canPublishScales && (
                <Button
                  variant="outline"
                  size="sm"
                  className="text-blue-500 border-blue-500/20 hover:bg-blue-500/10"
                  onClick={handlePublish}
                  disabled={operationLoading}
                >
                  <CheckCircle className="w-4 h-4 mr-2" />
                  Publicar
                </Button>
              )}

              <Button variant="outline" size="sm" onClick={handleRefresh} disabled={scaleLoading || shiftsLoading}>
                <RefreshCw className={`w-4 h-4 mr-2 ${(scaleLoading || shiftsLoading) ? 'animate-spin' : ''}`} />
                Atualizar
              </Button>
            </>
          }
        />

        {/* Feedback banner das transições de status */}
        {feedback && (
          <div
            role="alert"
            className={`flex items-center justify-between gap-3 rounded-xl border p-4 mb-6 text-sm ${
              feedback.type === 'error'
                ? 'bg-red-500/10 text-red-500 border-red-500/20'
                : 'bg-green-500/10 text-green-500 border-green-500/20'
            }`}
          >
            <div className="flex items-center gap-2">
              {feedback.type === 'error' ? (
                <AlertCircle className="w-4 h-4 shrink-0" />
              ) : (
                <CheckCircle className="w-4 h-4 shrink-0" />
              )}
              <span>{feedback.message}</span>
            </div>
            <button
              type="button"
              className="text-xs underline opacity-80 hover:opacity-100"
              onClick={() => setFeedback(null)}
            >
              Fechar
            </button>
          </div>
        )}

        {/* Scale Info Card */}
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-6 mb-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Left Column */}
            <div>
              <h2 className="text-sm font-medium text-[hsl(var(--muted-foreground))] mb-4">
                Informações da Escala
              </h2>

              <div className="space-y-3">
                <div className="flex items-start gap-3">
                  <Calendar className="w-5 h-5 text-[hsl(var(--muted-foreground))] mt-0.5" />
                  <div>
                    <p className="text-sm text-[hsl(var(--muted-foreground))]">Periodo</p>
                    <p className="text-base font-medium text-[hsl(var(--foreground))]">
                      {monthNames[scale.month - 1]} {scale.year}
                    </p>
                    {scale.start_date && scale.end_date && (
                      <p className="text-xs text-[hsl(var(--muted-foreground))]">
                        {formatDate(scale.start_date)} - {formatDate(scale.end_date)}
                      </p>
                    )}
                  </div>
                </div>

                <div className="flex items-start gap-3">
                  <MapPin className="w-5 h-5 text-[hsl(var(--muted-foreground))] mt-0.5" />
                  <div>
                    <p className="text-sm text-[hsl(var(--muted-foreground))]">Posto</p>
                    <p className="text-base font-medium text-[hsl(var(--foreground))]">
                      {getPostName(scale.post_id)}
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-3">
                  <Clock className="w-5 h-5 text-[hsl(var(--muted-foreground))] mt-0.5" />
                  <div>
                    <p className="text-sm text-[hsl(var(--muted-foreground))]">Tipo de Escala</p>
                    <p className="text-base font-medium text-[hsl(var(--foreground))]">
                      {SCALE_TYPE_LABELS[scale.scale_type] || scale.scale_type}
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-3">
                  <Shield className="w-5 h-5 text-[hsl(var(--muted-foreground))] mt-0.5" />
                  <div>
                    <p className="text-sm text-[hsl(var(--muted-foreground))]">Status</p>
                    <span
                      className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium border mt-1 ${getStatusColor(
                        scale.status as ScaleStatus
                      )}`}
                    >
                      {SCALE_STATUS_LABELS[scale.status as ScaleStatus] || scale.status}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* Right Column - Statistics */}
            <div>
              <h2 className="text-sm font-medium text-[hsl(var(--muted-foreground))] mb-4">
                Estatisticas
              </h2>

              <div className="grid grid-cols-2 gap-4">
                <div className="bg-[hsl(var(--muted))]/50 rounded-lg p-4">
                  <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                    {scale.total_shifts}
                  </p>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Total de Turnos</p>
                </div>

                <div className="bg-[hsl(var(--muted))]/50 rounded-lg p-4">
                  <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                    {scale.filled_shifts}
                  </p>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Turnos Preenchidos</p>
                </div>

                <div className="bg-[hsl(var(--muted))]/50 rounded-lg p-4">
                  <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                    {scale.total_hours.toFixed(0)}h
                  </p>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Total de Horas</p>
                </div>

                <div className="bg-[hsl(var(--muted))]/50 rounded-lg p-4">
                  <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                    {scale.fill_rate?.toFixed(0) || 0}%
                  </p>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Taxa de Preenchimento</p>
                </div>

                {scale.overtime_hours > 0 && (
                  <div className="bg-[hsl(var(--muted))]/50 rounded-lg p-4">
                    <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                      {scale.overtime_hours.toFixed(0)}h
                    </p>
                    <p className="text-xs text-[hsl(var(--muted-foreground))]">Horas Extras</p>
                  </div>
                )}

                {scale.estimated_cost > 0 && (
                  <div className="bg-[hsl(var(--muted))]/50 rounded-lg p-4">
                    <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                      R$ {scale.estimated_cost.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                    </p>
                    <p className="text-xs text-[hsl(var(--muted-foreground))]">Custo Estimado</p>
                  </div>
                )}
              </div>

              {scale.notes && (
                <div className="mt-4 p-3 bg-[hsl(var(--muted))]/30 rounded-lg">
                  <p className="text-xs text-[hsl(var(--muted-foreground))] mb-1">Observações</p>
                  <p className="text-sm text-[hsl(var(--foreground))]">{scale.notes}</p>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Scale Editor Section */}
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-6">
          {shiftsLoading || employeesLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-pulse-slow text-[hsl(var(--primary))]">
                <Clock className="w-8 h-8" />
              </div>
            </div>
          ) : shiftsError ? (
            <div className="p-6 text-center">
              <AlertCircle className="w-8 h-8 text-red-500 mx-auto mb-2" />
              <p className="text-sm text-red-500">{shiftsError}</p>
            </div>
          ) : (
            <ScaleEditor
              scale={scale}
              shifts={shifts}
              employees={employees}
              onRefresh={handleRefresh}
            />
          )}
        </div>
      </main>
    </div>
  );
}
