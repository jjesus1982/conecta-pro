'use client';

import dynamic from 'next/dynamic';
import { Shield, Search, Plus, Eye, Edit2, Trash2, ArrowLeft, ChevronLeft, ChevronRight, AlertCircle, CheckCircle, RefreshCw, Clock, Play, Pause, CheckSquare, XCircle, MapPin, Users } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
;
import { Button } from '@/components/ui/button';
import { PageHeader } from '@/components/ui/page-header';
import { Input } from '@/components/ui/input';
import { ConfirmModal } from '@/components/ui/modal';
import { useAuth } from '@/hooks/useAuth';
import {
  usePatrolRounds,
  usePatrolRoundStats,
  usePatrolRoundMutations,
} from '@/hooks/usePatrolRounds';
import type {
  PatrolRound,
  PatrolRoundStatus,
  InspectorRole,
} from '@/types/operacional';
import {
  PATROL_ROUND_STATUS_LABELS,
  INSPECTOR_ROLE_LABELS,
} from '@/types/operacional';
const PatrolRoundDetailModal = dynamic(() => import('@/components/operacional/patrol-round-detail-modal').then(m => m.PatrolRoundDetailModal), { ssr: false });
import { ExportButton } from '@/components/ui/export-button';
import { RondaMonitorCard } from '@/components/operacional/RondaMonitorCard';

// Cores dos status
const STATUS_COLORS: Record<PatrolRoundStatus, string> = {
  agendada: 'bg-blue-500/10 text-blue-500',
  em_andamento: 'bg-green-500/10 text-green-500',
  pausada: 'bg-yellow-500/10 text-yellow-500',
  concluida: 'bg-gray-500/10 text-gray-500',
  cancelada: 'bg-red-500/10 text-red-500',
};

export default function RondasPage() {
  const router = useRouter();
  const { isLoading: authLoading, isAuthenticated } = useAuth();
  const {
    patrolRounds,
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
  } = usePatrolRounds({ initialPageSize: 10 });
  const { stats, refresh: refreshStats } = usePatrolRoundStats();
  const { deletePatrolRound, isLoading: isMutating } = usePatrolRoundMutations();

  const [searchTerm, setSearchTerm] = useState('');
  const [selectedStatus, setSelectedStatus] = useState<PatrolRoundStatus | ''>('');
  const [selectedRole, setSelectedRole] = useState<InspectorRole | ''>('');

  // Modal states
  const [selectedRound, setSelectedRound] = useState<PatrolRound | null>(null);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // Redirecionar se não autenticado
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [authLoading, isAuthenticated, router]);

  // Auto-refresh every 30 seconds for live monitoring
  useEffect(() => {
    if (!isAuthenticated) return;
    const interval = setInterval(() => {
      refresh();
    }, 30_000);
    return () => clearInterval(interval);
  }, [isAuthenticated, refresh]);

  // Debounce search
  useEffect(() => {
    const timer = setTimeout(() => {
      setFilters({
        ...filters,
        status: selectedStatus || undefined,
        inspector_role: selectedRole || undefined,
      });
    }, 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- debounce filter sync
  }, [searchTerm, selectedStatus, selectedRole]);

  // Handlers
  const handleView = (round: PatrolRound) => {
    setSelectedRound(round);
    setShowDetailModal(true);
  };

  const handleDelete = async () => {
    if (!selectedRound) return;

    setIsDeleting(true);
    setDeleteError(null);

    const success = await deletePatrolRound(selectedRound.id);

    if (success) {
      setShowDeleteModal(false);
      setSelectedRound(null);
      handleRefresh();
    } else {
      setDeleteError('Erro ao excluir ronda');
    }

    setIsDeleting(false);
  };

  const confirmDelete = (round: PatrolRound) => {
    setSelectedRound(round);
    setShowDeleteModal(true);
  };

  const handleRefresh = () => {
    refresh();
    refreshStats();
  };

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

  const formatDuration = (minutes: number | null) => {
    if (!minutes) return '-';
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return hours > 0 ? `${hours}h ${mins}min` : `${mins}min`;
  };

  const getStatusIcon = (status: PatrolRoundStatus) => {
    switch (status) {
      case 'agendada':
        return <Clock className="w-4 h-4" />;
      case 'em_andamento':
        return <Play className="w-4 h-4" />;
      case 'pausada':
        return <Pause className="w-4 h-4" />;
      case 'concluida':
        return <CheckSquare className="w-4 h-4" />;
      case 'cancelada':
        return <XCircle className="w-4 h-4" />;
      default:
        return <Clock className="w-4 h-4" />;
    }
  };

  const activeRounds = patrolRounds.filter(r => r.status === 'em_andamento' || r.status === 'pausada');

  // Preparar dados para exportação
  const exportData = patrolRounds.map((round) => ({
    'Código': round.code || '-',
    'Status': PATROL_ROUND_STATUS_LABELS[round.status as PatrolRoundStatus] || round.status,
    'Inspetor': round.inspector_name || '-',
    'Função': INSPECTOR_ROLE_LABELS[round.inspector_role as InspectorRole] || round.inspector_role,
    'Data Agendada': round.scheduled_date ? new Date(round.scheduled_date).toLocaleDateString('pt-BR') : '-',
    'Início': round.started_at ? new Date(round.started_at).toLocaleString('pt-BR') : '-',
    'Conclusão': round.completed_at ? new Date(round.completed_at).toLocaleString('pt-BR') : '-',
    'Duração (min)': round.duration_minutes || '-',
    'Checkpoints': round.total_checkpoints,
    'Ocorrências': round.total_occurrences,
    'Ações Disciplinares': round.total_disciplinary_actions,
    'Colaboradores': round.total_employees_checked,
    'Progresso': `${round.progress_percentage}%`,
  }));

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))]">
        <div className="animate-pulse-slow text-[hsl(var(--primary))]">
          <Shield className="w-12 h-12" />
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
          title="Rondas de Inspeção"
          subtitle={`${total} registros`}
          icon={<Shield className="w-5 h-5" />}
          actions={
            <>
              <Link href="/modulos/operacional">
                <Button variant="ghost" size="sm">
                  <ArrowLeft className="w-4 h-4 mr-2" />
                  Operacional
                </Button>
              </Link>
              <ExportButton
                data={exportData}
                filename="rondas"
                pdfTitle="Relatório de Rondas de Inspeção"
                formats={['excel', 'pdf', 'csv']}
                size="sm"
                variant="outline"
                buttonText="Exportar"
              />
              <Button variant="outline" onClick={handleRefresh} disabled={isLoading}>
                <RefreshCw className={`w-4 h-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
                Atualizar
              </Button>
            </>
          }
        />

        {/* Stats Cards */}
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-4 mb-6">
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
                <Shield className="w-5 h-5 text-blue-500" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                  {stats?.total_rounds || 0}
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Total</p>
              </div>
            </div>
          </div>

          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-green-500/10 flex items-center justify-center">
                <Play className="w-5 h-5 text-green-500" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                  {stats?.rounds_in_progress || 0}
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Em Andamento</p>
              </div>
            </div>
          </div>

          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-gray-500/10 flex items-center justify-center">
                <CheckSquare className="w-5 h-5 text-gray-500" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                  {stats?.rounds_completed || 0}
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Concluídas</p>
              </div>
            </div>
          </div>

          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-red-500/10 flex items-center justify-center">
                <AlertCircle className="w-5 h-5 text-red-500" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                  {stats?.total_occurrences || 0}
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Ocorrências</p>
              </div>
            </div>
          </div>

          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-orange-500/10 flex items-center justify-center">
                <Users className="w-5 h-5 text-orange-500" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                  {stats?.total_disciplinary_actions || 0}
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Medidas Discip.</p>
              </div>
            </div>
          </div>
        </div>

        {/* Monitor ao Vivo */}
        {activeRounds.length > 0 && (
          <div className="mb-6">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <span className="inline-block w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                <h2 className="text-sm font-semibold text-[hsl(var(--foreground))]">Monitor ao Vivo</h2>
                <span className="text-xs text-[hsl(var(--muted-foreground))]">{activeRounds.length} ronda(s) ativa(s)</span>
              </div>
              <span className="text-xs text-[hsl(var(--muted-foreground))]">Atualiza a cada 30s</span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {activeRounds.map(round => (
                <RondaMonitorCard
                  key={round.id}
                  round={round as any}
                  onClick={() => handleView(round)}
                />
              ))}
            </div>
          </div>
        )}

        {/* Filters */}
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4 mb-6">
          <div className="flex flex-col lg:flex-row gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[hsl(var(--muted-foreground))]" />
              <Input
                placeholder="Buscar por código, inspetor..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-10"
              />
            </div>
            <div className="flex flex-wrap gap-2">
              <select
                value={selectedStatus}
                onChange={(e) => setSelectedStatus(e.target.value as PatrolRoundStatus | '')}
                className="px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))] text-sm"
              >
                <option value="">Todos os Status</option>
                {Object.entries(PATROL_ROUND_STATUS_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
              <select
                value={selectedRole}
                onChange={(e) => setSelectedRole(e.target.value as InspectorRole | '')}
                className="px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))] text-sm"
              >
                <option value="">Todos os Cargos</option>
                {Object.entries(INSPECTOR_ROLE_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {/* Error state */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 mb-6 flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-red-500" />
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
              <Shield className="w-8 h-8" />
            </div>
          </div>
        )}

        {/* Table */}
        {!isLoading && !error && (
          <>
            <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-[hsl(var(--border))] bg-[hsl(var(--muted))]">
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                        Código
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                        Inspetor
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                        Status
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                        Data Início
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                        Duração
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                        Checkpoints
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                        Ocorrências
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                        Ações
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[hsl(var(--border))]">
                    {patrolRounds.map((round) => (
                      <tr
                        key={round.id}
                        className="hover:bg-[hsl(var(--muted))]/50 transition-colors cursor-pointer"
                        onClick={() => handleView(round)}
                      >
                        <td className="px-4 py-3">
                          <span className="text-sm font-mono text-[hsl(var(--foreground))]">
                            {round.code}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <div>
                            <p className="text-sm font-medium text-[hsl(var(--foreground))]">
                              {round.inspector_name}
                            </p>
                            <p className="text-xs text-[hsl(var(--muted-foreground))]">
                              {INSPECTOR_ROLE_LABELS[round.inspector_role]}
                            </p>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${
                              STATUS_COLORS[round.status] || 'bg-gray-500/10 text-gray-500'
                            }`}
                          >
                            {getStatusIcon(round.status)}
                            {PATROL_ROUND_STATUS_LABELS[round.status]}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span className="text-sm text-[hsl(var(--foreground))]">
                            {formatDate(round.started_at || round.scheduled_date)}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span className="text-sm text-[hsl(var(--foreground))]">
                            {formatDuration(round.duration_minutes)}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span className="text-sm text-[hsl(var(--foreground))]">
                            {round.total_checkpoints}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span className="text-sm text-[hsl(var(--foreground))]">
                            {round.total_occurrences}
                          </span>
                        </td>
                        <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                          <div className="flex items-center justify-end gap-1">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleView(round)}
                              title="Ver Detalhes"
                            >
                              <Eye className="w-4 h-4" />
                            </Button>
                            {round.status === 'agendada' && (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => confirmDelete(round)}
                                className="text-red-500 hover:text-red-600"
                                title="Excluir"
                              >
                                <Trash2 className="w-4 h-4" />
                              </Button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Empty state */}
            {patrolRounds.length === 0 && !isLoading && (
              <div className="text-center py-12 bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl mt-4">
                <Shield className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
                <h3 className="text-lg font-medium text-[hsl(var(--foreground))]">
                  Nenhuma ronda encontrada
                </h3>
                <p className="text-[hsl(var(--muted-foreground))] mt-1">
                  Ajuste os filtros ou aguarde novas rondas
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
                    Página {page} de {totalPages}
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

      {/* Detail Modal */}
      <PatrolRoundDetailModal
        isOpen={showDetailModal}
        onClose={() => {
          setShowDetailModal(false);
          setSelectedRound(null);
        }}
        patrolRound={selectedRound}
      />

      {/* Delete Modal */}
      <ConfirmModal
        isOpen={showDeleteModal}
        onClose={() => {
          setShowDeleteModal(false);
          setSelectedRound(null);
          setDeleteError(null);
        }}
        onConfirm={handleDelete}
        title="Excluir Ronda"
        message={`Tem certeza que deseja excluir a ronda ${selectedRound?.code}? Esta ação não pode ser desfeita.${deleteError ? ` Erro: ${deleteError}` : ''}`}
        confirmText="Excluir"
        isLoading={isDeleting}
        variant="danger"
      />
    </div>
  );
}
