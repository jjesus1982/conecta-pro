'use client';

import dynamic from 'next/dynamic';
import { AlertTriangle, Search, Plus, Eye, Edit2, Trash2, ArrowLeft, ChevronLeft, ChevronRight, AlertCircle, CheckCircle, RefreshCw, Clock, Shield, XCircle, CheckSquare } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
;
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ConfirmModal } from '@/components/ui/modal';
import { PageHeader } from '@/components/ui/page-header';
import { useAuth } from '@/hooks/useAuth';
import { useOccurrences, useOccurrenceStats, useOccurrenceMutations } from '@/hooks/useOccurrences';
import { useEmployees } from '@/hooks/operacional/useEmployees';
import type {
  Occurrence,
  OccurrenceStatus,
  OccurrenceSeverity,
  OccurrenceType,
  OccurrenceCategory,
} from '@/types/operacional';
import {
  OCCURRENCE_TYPE_LABELS,
  OCCURRENCE_STATUS_LABELS,
  OCCURRENCE_SEVERITY_LABELS,
  OCCURRENCE_CATEGORY_LABELS,
} from '@/types/operacional';
const OccurrenceFormModal = dynamic(() => import('@/components/operacional/occurrence-form-modal').then(m => m.OccurrenceFormModal), { ssr: false });
const OccurrenceDetailModal = dynamic(() => import('@/components/operacional/occurrence-detail-modal').then(m => m.OccurrenceDetailModal), { ssr: false });
const OccurrenceResolveModal = dynamic(() => import('@/components/operacional/occurrence-resolve-modal').then(m => m.OccurrenceResolveModal), { ssr: false });
import { ExportButton } from '@/components/ui/export-button';
import { OccurrenceAIPanel } from '@/components/operacional/OccurrenceAIPanel';

// Cores dos status
const STATUS_COLORS: Record<OccurrenceStatus, string> = {
  aberta: 'bg-red-500/10 text-red-500',
  em_analise: 'bg-yellow-500/10 text-yellow-500',
  resolvida: 'bg-green-500/10 text-green-500',
  encerrada: 'bg-blue-500/10 text-blue-500',
  cancelada: 'bg-gray-500/10 text-gray-500',
};

// Cores das severidades
const SEVERITY_COLORS: Record<OccurrenceSeverity, string> = {
  leve: 'bg-blue-500/10 text-blue-500',
  moderada: 'bg-yellow-500/10 text-yellow-500',
  grave: 'bg-orange-500/10 text-orange-500',
  gravissima: 'bg-red-500/10 text-red-500',
};

// Cores das categorias
const CATEGORY_COLORS: Record<OccurrenceCategory, string> = {
  disciplinar: 'bg-orange-500/10 text-orange-500',
  seguranca: 'bg-red-500/10 text-red-500',
  operacional: 'bg-blue-500/10 text-blue-500',
  administrativa: 'bg-purple-500/10 text-purple-500',
  tecnica: 'bg-cyan-500/10 text-cyan-500',
};

export default function OcorrenciasPage() {
  const router = useRouter();
  const { isLoading: authLoading, isAuthenticated } = useAuth();
  const {
    occurrences,
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
  } = useOccurrences({ initialPageSize: 10 });
  const { stats, refresh: refreshStats } = useOccurrenceStats();
  const { deleteOccurrence, isLoading: isMutating } = useOccurrenceMutations();

  // A API /occurrences/stats retorna open/in_analysis/resolved (totais) —
  // não existe "resolvidas no mês" no backend; os cards usam os campos reais.
  const statsApi = stats as unknown as {
    open?: number;
    in_analysis?: number;
    resolved?: number;
  } | null;

  // Mapa employee_id → nome para resolver o funcionário quando a API
  // não envia employee_name (mesma fonte usada nas outras telas)
  const { data: employeesData } = useEmployees({ page: 1, page_size: 500 } as any);
  const employeeNameById = useMemo(() => {
    const items: any[] = (employeesData as any)?.items ?? [];
    const map: Record<string, string> = {};
    for (const e of items) {
      if (e?.id != null && e?.nome) map[String(e.id)] = e.nome;
    }
    return map;
  }, [employeesData]);

  const resolveEmployeeName = (occ: Occurrence): string => {
    if (occ.employee_name) return occ.employee_name;
    if (occ.employee_id) return employeeNameById[String(occ.employee_id)] ?? '—';
    return '—';
  };

  const [searchTerm, setSearchTerm] = useState('');
  const [selectedStatus, setSelectedStatus] = useState<OccurrenceStatus | ''>('');
  const [selectedSeverity, setSelectedSeverity] = useState<OccurrenceSeverity | ''>('');
  const [selectedCategory, setSelectedCategory] = useState<OccurrenceCategory | ''>('');

  // Modal states
  const [selectedOccurrence, setSelectedOccurrence] = useState<Occurrence | null>(null);
  const [showFormModal, setShowFormModal] = useState(false);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [showResolveModal, setShowResolveModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [editOccurrence, setEditOccurrence] = useState<Occurrence | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // Redirecionar se nao autenticado
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [authLoading, isAuthenticated, router]);

  // Debounce search
  useEffect(() => {
    const timer = setTimeout(() => {
      setFilters({
        ...filters,
        search: searchTerm || undefined,
        status: selectedStatus || undefined,
        severity: selectedSeverity || undefined,
        category: selectedCategory || undefined,
      });
    }, 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- debounce filter sync
  }, [searchTerm, selectedStatus, selectedSeverity, selectedCategory]);

  // Handlers
  const handleNew = () => {
    setEditOccurrence(null);
    setShowFormModal(true);
  };

  const handleView = (occurrence: Occurrence) => {
    setSelectedOccurrence(occurrence);
    setShowDetailModal(true);
  };

  const handleEdit = (occurrence: Occurrence) => {
    setEditOccurrence(occurrence);
    setShowFormModal(true);
  };

  const handleResolve = (occurrence: Occurrence) => {
    setSelectedOccurrence(occurrence);
    setShowResolveModal(true);
  };

  const handleDelete = async () => {
    if (!selectedOccurrence) return;

    setIsDeleting(true);
    setDeleteError(null);

    const success = await deleteOccurrence(selectedOccurrence.id);

    if (success) {
      setShowDeleteModal(false);
      setSelectedOccurrence(null);
      handleRefresh();
    } else {
      setDeleteError('Erro ao excluir ocorrencia');
    }

    setIsDeleting(false);
  };

  const confirmDelete = (occurrence: Occurrence) => {
    setSelectedOccurrence(occurrence);
    setShowDeleteModal(true);
  };

  const handleRefresh = () => {
    refresh();
    refreshStats();
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const getStatusIcon = (status: OccurrenceStatus) => {
    switch (status) {
      case 'aberta':
        return <AlertCircle className="w-4 h-4" />;
      case 'em_analise':
        return <Clock className="w-4 h-4" />;
      case 'resolvida':
        return <CheckCircle className="w-4 h-4" />;
      case 'encerrada':
        return <CheckSquare className="w-4 h-4" />;
      case 'cancelada':
        return <XCircle className="w-4 h-4" />;
      default:
        return <AlertCircle className="w-4 h-4" />;
    }
  };

  // Preparar dados para exportação
  const exportData = occurrences.map((occ) => ({
    'Código': occ.code || '-',
    'Tipo': OCCURRENCE_TYPE_LABELS[occ.occurrence_type as OccurrenceType] || occ.occurrence_type,
    'Categoria': OCCURRENCE_CATEGORY_LABELS[occ.category as OccurrenceCategory] || occ.category,
    'Gravidade': OCCURRENCE_SEVERITY_LABELS[occ.severity as OccurrenceSeverity] || occ.severity,
    'Status': OCCURRENCE_STATUS_LABELS[occ.status as OccurrenceStatus] || occ.status,
    'Título': occ.title,
    'Descrição': occ.description?.substring(0, 100) || '-',
    'Colaborador': resolveEmployeeName(occ),
    'Inspetor': occ.inspector_name || '-',
    'Posto': occ.post_name || '-',
    'Data Ocorrência': new Date(occ.occurred_at).toLocaleDateString('pt-BR'),
    'Data Criação': new Date(occ.created_at).toLocaleDateString('pt-BR'),
  }));

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))]">
        <div className="animate-pulse-slow text-[hsl(var(--primary))]">
          <AlertTriangle className="w-12 h-12" />
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
          title="Ocorrências"
          subtitle={`${total} registros`}
          icon={<AlertTriangle className="w-5 h-5" />}
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
                filename="ocorrencias"
                pdfTitle="Relatório de Ocorrências Disciplinares"
                formats={['excel', 'pdf', 'csv']}
                size="sm"
                variant="outline"
                buttonText="Exportar"
              />
              <Button variant="outline" onClick={handleRefresh} disabled={isLoading}>
                <RefreshCw className={`w-4 h-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
                Atualizar
              </Button>
              <Button variant="primary" onClick={handleNew}>
                <Plus className="w-4 h-4 mr-2" />
                Nova Ocorrencia
              </Button>
            </>
          }
        />

        <div className="lg:grid lg:grid-cols-[1fr_320px] lg:gap-6">
          <div className="min-w-0">
            {/* Stats Cards */}
            <div className="grid grid-cols-2 lg:grid-cols-5 gap-4 mb-6">
              <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
                    <AlertTriangle className="w-5 h-5 text-blue-500" />
                  </div>
                  <div>
                    <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                      {stats?.total || 0}
                    </p>
                    <p className="text-xs text-[hsl(var(--muted-foreground))]">Total</p>
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
                      {(statsApi?.open ?? 0) + (statsApi?.in_analysis ?? 0)}
                    </p>
                    <p className="text-xs text-[hsl(var(--muted-foreground))]">Pendentes</p>
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
                      {statsApi?.resolved ?? 0}
                    </p>
                    <p className="text-xs text-[hsl(var(--muted-foreground))]">Resolvidas (total)</p>
                  </div>
                </div>
              </div>

              <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-orange-500/10 flex items-center justify-center">
                    <Shield className="w-5 h-5 text-orange-500" />
                  </div>
                  <div>
                    <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                      {stats?.by_severity?.grave || 0}
                    </p>
                    <p className="text-xs text-[hsl(var(--muted-foreground))]">Graves</p>
                  </div>
                </div>
              </div>

              <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-purple-500/10 flex items-center justify-center">
                    <Clock className="w-5 h-5 text-purple-500" />
                  </div>
                  <div>
                    <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                      {stats?.avg_resolution_time_hours ? `${Math.round(stats.avg_resolution_time_hours)}h` : '-'}
                    </p>
                    <p className="text-xs text-[hsl(var(--muted-foreground))]">Tempo medio</p>
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
                    placeholder="Buscar por funcionario, codigo, descricao..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="pl-10"
                  />
                </div>
                <div className="flex flex-wrap gap-2">
                  <select
                    value={selectedStatus}
                    onChange={(e) => setSelectedStatus(e.target.value as OccurrenceStatus | '')}
                    className="px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))] text-sm"
                  >
                    <option value="">Todos os Status</option>
                    {Object.entries(OCCURRENCE_STATUS_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                  <select
                    value={selectedSeverity}
                    onChange={(e) => setSelectedSeverity(e.target.value as OccurrenceSeverity | '')}
                    className="px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))] text-sm"
                  >
                    <option value="">Todas Severidades</option>
                    {Object.entries(OCCURRENCE_SEVERITY_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label.split(' (')[0]}
                      </option>
                    ))}
                  </select>
                  <select
                    value={selectedCategory}
                    onChange={(e) => setSelectedCategory(e.target.value as OccurrenceCategory | '')}
                    className="px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))] text-sm"
                  >
                    <option value="">Todas Categorias</option>
                    {Object.entries(OCCURRENCE_CATEGORY_LABELS).map(([value, label]) => (
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
                  <AlertTriangle className="w-8 h-8" />
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
                            Codigo
                          </th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                            Funcionario
                          </th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                            Tipo
                          </th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                            Severidade
                          </th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                            Data
                          </th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                            Status
                          </th>
                          <th className="px-4 py-3 text-right text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                            Ações
                          </th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[hsl(var(--border))]">
                        {occurrences.map((occurrence) => (
                          <tr
                            key={occurrence.id}
                            className="hover:bg-[hsl(var(--muted))]/50 transition-colors cursor-pointer"
                            onClick={() => handleView(occurrence)}
                          >
                            <td className="px-4 py-3">
                              <span className="text-sm font-mono text-[hsl(var(--foreground))]">
                                {occurrence.code}
                              </span>
                            </td>
                            <td className="px-4 py-3">
                              <div>
                                <p className="text-sm font-medium text-[hsl(var(--foreground))]">
                                  {resolveEmployeeName(occurrence)}
                                </p>
                                {occurrence.post_name && (
                                  <p className="text-xs text-[hsl(var(--muted-foreground))]">
                                    {occurrence.post_name}
                                  </p>
                                )}
                              </div>
                            </td>
                            <td className="px-4 py-3">
                              <span className="text-sm text-[hsl(var(--muted-foreground))]">
                                {OCCURRENCE_TYPE_LABELS[occurrence.occurrence_type]}
                              </span>
                            </td>
                            <td className="px-4 py-3">
                              <span
                                className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${
                                  SEVERITY_COLORS[occurrence.severity] || 'bg-gray-500/10 text-gray-500'
                                }`}
                              >
                                {OCCURRENCE_SEVERITY_LABELS[occurrence.severity]?.split(' (')[0]}
                              </span>
                            </td>
                            <td className="px-4 py-3">
                              <span className="text-sm text-[hsl(var(--foreground))]">
                                {formatDate(occurrence.occurred_at)}
                              </span>
                            </td>
                            <td className="px-4 py-3">
                              <span
                                className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${
                                  STATUS_COLORS[occurrence.status] || 'bg-gray-500/10 text-gray-500'
                                }`}
                              >
                                {getStatusIcon(occurrence.status)}
                                {OCCURRENCE_STATUS_LABELS[occurrence.status]}
                              </span>
                            </td>
                            <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                              <div className="flex items-center justify-end gap-1">
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleView(occurrence)}
                                  title="Ver Detalhes"
                                >
                                  <Eye className="w-4 h-4" />
                                </Button>
                                {(occurrence.status === 'aberta' || occurrence.status === 'em_analise') && (
                                  <>
                                    <Button
                                      variant="ghost"
                                      size="sm"
                                      onClick={() => handleEdit(occurrence)}
                                      title="Editar"
                                    >
                                      <Edit2 className="w-4 h-4" />
                                    </Button>
                                    <Button
                                      variant="ghost"
                                      size="sm"
                                      onClick={() => handleResolve(occurrence)}
                                      title="Resolver"
                                      className="text-green-500 hover:text-green-600"
                                    >
                                      <CheckCircle className="w-4 h-4" />
                                    </Button>
                                  </>
                                )}
                                {occurrence.status === 'aberta' && (
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => confirmDelete(occurrence)}
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
                {occurrences.length === 0 && !isLoading && (
                  <div className="text-center py-12 bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl mt-4">
                    <AlertTriangle className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
                    <h3 className="text-lg font-medium text-[hsl(var(--foreground))]">
                      Nenhuma ocorrencia encontrada
                    </h3>
                    <p className="text-[hsl(var(--muted-foreground))] mt-1">
                      Ajuste os filtros ou registre uma nova ocorrencia
                    </p>
                    <Button variant="primary" className="mt-4" onClick={handleNew}>
                      <Plus className="w-4 h-4 mr-2" />
                      Nova Ocorrencia
                    </Button>
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
          </div>

          {/* AI Panel sidebar */}
          <aside className="hidden lg:block">
            <div className="sticky top-20">
              <OccurrenceAIPanel stats={stats as any} occurrences={occurrences as any} />
            </div>
          </aside>
        </div>
      </main>

      {/* Form Modal */}
      <OccurrenceFormModal
        isOpen={showFormModal}
        onClose={() => {
          setShowFormModal(false);
          setEditOccurrence(null);
        }}
        onSuccess={handleRefresh}
        editData={editOccurrence}
      />

      {/* Detail Modal */}
      <OccurrenceDetailModal
        isOpen={showDetailModal}
        onClose={() => {
          setShowDetailModal(false);
          setSelectedOccurrence(null);
        }}
        occurrence={selectedOccurrence}
        onResolve={handleResolve}
        onEdit={handleEdit}
      />

      {/* Resolve Modal */}
      <OccurrenceResolveModal
        isOpen={showResolveModal}
        onClose={() => {
          setShowResolveModal(false);
          setSelectedOccurrence(null);
        }}
        onSuccess={handleRefresh}
        occurrence={selectedOccurrence}
      />

      {/* Delete Modal */}
      <ConfirmModal
        isOpen={showDeleteModal}
        onClose={() => {
          setShowDeleteModal(false);
          setSelectedOccurrence(null);
          setDeleteError(null);
        }}
        onConfirm={handleDelete}
        title="Excluir Ocorrencia"
        message={`Tem certeza que deseja excluir a ocorrencia ${selectedOccurrence?.code}? Esta acao nao pode ser desfeita.${deleteError ? ` Erro: ${deleteError}` : ''}`}
        confirmText="Excluir"
        isLoading={isDeleting}
        variant="danger"
      />
    </div>
  );
}
