'use client';

import dynamic from 'next/dynamic';
import { Shield, Calendar, ArrowLeft, Search, Plus, Filter, ChevronLeft, ChevronRight, Eye, CheckCircle, Send, Clock, AlertCircle, Trash2, CalendarDays, FileText, RefreshCw, Loader2 } from 'lucide-react';
import { useState, useEffect } from 'react';
import { toast } from 'sonner';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
;
import { Button } from '@/components/ui/button';
import { PageHeader } from '@/components/ui/page-header';
import { Input } from '@/components/ui/input';
import { PermissionGuard } from '@/components/ui/permission-guard';
import { useAuth } from '@/hooks/useAuth';
import { usePermission, Permission } from '@/hooks/usePermission';
import { useScales, useScaleOperations } from '@/hooks/useScales';
import { usePosts } from '@/hooks/usePosts';
import { ConfirmModal, Modal } from '@/components/ui/modal';
const ScaleGenerateModal = dynamic(() => import('@/components/operacional/scale-generate-modal').then(m => m.ScaleGenerateModal), { ssr: false });
import { TemplateManager } from '@/features/escalas/components/TemplateManager';
import { ExportButton } from '@/components/ui/export-button';
import type { Scale, ScaleStatus, ScaleType, Post } from '@/types/operacional';
import { SCALE_TYPE_LABELS, SCALE_STATUS_LABELS } from '@/types/operacional';

const API_PONTO = '/api/v1/people-management/ponto';

function getAuthHeaders() {
  const token = typeof window !== 'undefined' ? (localStorage.getItem('access_token') || localStorage.getItem('token')) : null;
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export default function EscalasPage() {
  const router = useRouter();
  const { user, isLoading: authLoading, isAuthenticated } = useAuth();
  const { canManageScales, canApproveScales, hasPermission } = usePermission();
  const {
    scales,
    total,
    page,
    pageSize,
    totalPages,
    isLoading: scalesLoading,
    setPage,
    setFilters,
    refresh,
  } = useScales(1, 10);
  const { posts } = usePosts({ initialPageSize: 100 });
  const { deleteScale, submitForApproval, approveScale, publishScale, isLoading: operationLoading } = useScaleOperations();

  const [syncingEscalas, setSyncingEscalas] = useState(false);

  const handleSyncEscalas = async () => {
    setSyncingEscalas(true);
    try {
      const res = await fetch(`${API_PONTO}/sync-escalas`, {
        method: 'POST',
        headers: getAuthHeaders(),
      });
      const data = await res.json().catch(() => null);
      if (res.ok) {
        const updated = data?.total_atualizados ?? data?.updated ?? 0;
        toast.success(`Escalas Sólides: ${updated} colaboradores atualizados`, { duration: 5000 });
        refresh();
      } else {
        toast.error(data?.detail || 'Erro ao sincronizar escalas do Sólides', { duration: 5000 });
      }
    } catch {
      toast.error('Erro de conexão ao sincronizar escalas', { duration: 5000 });
    } finally {
      setSyncingEscalas(false);
    }
  };

  // Modal states
  const [showGenerateModal, setShowGenerateModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [showTemplatesModal, setShowTemplatesModal] = useState(false);
  const [selectedScale, setSelectedScale] = useState<Scale | null>(null);

  // Filter states
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<ScaleStatus | ''>('');
  const [monthFilter, setMonthFilter] = useState<number | ''>('');
  const [yearFilter, setYearFilter] = useState<number>(new Date().getFullYear());

  // Auth check
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [authLoading, isAuthenticated, router]);

  // Apply filters with debounce for search
  useEffect(() => {
    const timer = setTimeout(() => {
      const filters: Record<string, string | number | boolean | undefined> = {};
      if (searchTerm) filters.search = searchTerm;
      if (statusFilter) filters.status = statusFilter;
      if (monthFilter) filters.month = monthFilter;
      if (yearFilter) filters.year = yearFilter;
      setFilters(Object.keys(filters).length > 0 ? filters : undefined);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchTerm, statusFilter, monthFilter, yearFilter, setFilters]);

  // Helper to get post name
  const getPostName = (postId: string): string => {
    const post = posts.find((p: Post) => p.id === postId);
    return post?.name || 'Posto desconhecido';
  };

  // Status badge colors
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

  // Status icon
  const getStatusIcon = (status: ScaleStatus) => {
    switch (status) {
      case 'draft':
        return <Clock className="w-3 h-3 mr-1" />;
      case 'pending_approval':
        return <AlertCircle className="w-3 h-3 mr-1" />;
      case 'approved':
      case 'completed':
        return <CheckCircle className="w-3 h-3 mr-1" />;
      case 'published':
      case 'in_progress':
        return <Send className="w-3 h-3 mr-1" />;
      default:
        return null;
    }
  };

  // Month names
  const monthNames = [
    'Janeiro', 'Fevereiro', 'Marco', 'Abril', 'Maio', 'Junho',
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
  ];

  // Handle delete
  const handleDelete = async () => {
    if (!selectedScale) return;
    const success = await deleteScale(selectedScale.id);
    if (success) {
      setShowDeleteModal(false);
      setSelectedScale(null);
      refresh();
    }
  };

  // Handle submit for approval
  const handleSubmitForApproval = async (scale: Scale) => {
    const result = await submitForApproval(scale.id);
    if (result) refresh();
  };

  // Handle approve
  const handleApprove = async (scale: Scale) => {
    const result = await approveScale(scale.id);
    if (result) refresh();
  };

  // Handle publish
  const handlePublish = async (scale: Scale) => {
    const result = await publishScale(scale.id, true);
    if (result) refresh();
  };

  // Preparar dados para exportação
  const exportData = scales.map((scale) => ({
    'Nome': scale.name || '-',
    'Mês': monthNames[scale.month - 1] || '-',
    'Ano': scale.year,
    'Tipo': SCALE_TYPE_LABELS[scale.scale_type as ScaleType] || scale.scale_type,
    'Status': SCALE_STATUS_LABELS[scale.status as ScaleStatus] || scale.status,
    'Posto': getPostName(scale.post_id),
    'Total de Turnos': scale.total_shifts,
    'Turnos Preenchidos': scale.filled_shifts,
    'Total de Horas': scale.total_hours,
    'Horas Extras': scale.overtime_hours,
    'Custo Estimado': `R$ ${scale.estimated_cost.toFixed(2)}`,
    'Criado em': new Date(scale.created_at).toLocaleDateString('pt-BR'),
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
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <PageHeader
          eyebrow="OPERACIONAL"
          title="Escalas"
          subtitle={`${total} escalas cadastradas`}
          icon={<Calendar className="w-5 h-5" />}
          actions={
            <>
              <Link href="/modulos/operacional">
                <Button variant="ghost" size="sm">
                  <ArrowLeft className="w-4 h-4 mr-2" />
                  Voltar
                </Button>
              </Link>
              <ExportButton
                data={exportData}
                filename="escalas"
                pdfTitle="Relatório de Escalas"
                formats={['excel', 'pdf', 'csv']}
                size="sm"
                variant="outline"
                buttonText="Exportar"
              />
              <Button
                variant="outline"
                onClick={handleSyncEscalas}
                disabled={syncingEscalas}
              >
                {syncingEscalas ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <RefreshCw className="w-4 h-4 mr-2" />}
                Sync Sólides
              </Button>
              <Button
                variant="outline"
                onClick={() => setShowTemplatesModal(true)}
              >
                <FileText className="w-4 h-4 mr-2" />
                Templates
              </Button>
              <Button aria-label="Nova Escala" onClick={() => setShowGenerateModal(true)}>
                <Plus className="w-4 h-4 mr-2" />
                Nova Escala
              </Button>
            </>
          }
        />

        {/* Filters */}
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4 mb-6">
          <div className="flex flex-col sm:flex-row gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[hsl(var(--muted-foreground))]" />
              <Input
                placeholder="Buscar escala..."
                className="pl-9"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </div>
            <div className="flex gap-2">
              <select
                className="h-10 px-3 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-sm"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value as ScaleStatus | '')}
              >
                <option value="">Todos Status</option>
                {Object.entries(SCALE_STATUS_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
              <select
                className="h-10 px-3 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-sm"
                value={monthFilter}
                onChange={(e) => setMonthFilter(e.target.value ? Number(e.target.value) : '')}
              >
                <option value="">Todos Meses</option>
                {monthNames.map((name, index) => (
                  <option key={index} value={index + 1}>{name}</option>
                ))}
              </select>
              <select
                className="h-10 px-3 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-sm"
                value={yearFilter}
                onChange={(e) => setYearFilter(Number(e.target.value))}
              >
                {[2024, 2025, 2026, 2027].map((year) => (
                  <option key={year} value={year}>{year}</option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {/* Scales List */}
        {scalesLoading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-pulse-slow text-[hsl(var(--primary))]">
              <Calendar className="w-8 h-8" />
            </div>
          </div>
        ) : scales.length === 0 ? (
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-12 text-center">
            <CalendarDays className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
            <h3 className="text-lg font-medium text-[hsl(var(--foreground))] mb-2">
              Nenhuma escala encontrada
            </h3>
            <p className="text-sm text-[hsl(var(--muted-foreground))] mb-4">
              Gere uma nova escala para comecar
            </p>
            <Button onClick={() => setShowGenerateModal(true)}>
              <Plus className="w-4 h-4 mr-2" />
              Gerar Escala
            </Button>
          </div>
        ) : (
          <>
            {/* Scales Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
              {scales.map((scale) => (
                <div
                  key={scale.id}
                  className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4 hover:border-[hsl(var(--primary))] transition-colors"
                >
                  {/* Header */}
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <h3 className="font-medium text-[hsl(var(--foreground))]">
                        {monthNames[scale.month - 1]} {scale.year}
                      </h3>
                      <p className="text-xs text-[hsl(var(--muted-foreground))]">
                        {getPostName(scale.post_id)}
                      </p>
                    </div>
                    <span
                      className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium border ${getStatusColor(
                        scale.status as ScaleStatus
                      )}`}
                    >
                      {getStatusIcon(scale.status as ScaleStatus)}
                      {SCALE_STATUS_LABELS[scale.status as ScaleStatus] || scale.status}
                    </span>
                  </div>

                  {/* Scale Type */}
                  <div className="text-sm text-[hsl(var(--muted-foreground))] mb-3">
                    {SCALE_TYPE_LABELS[scale.scale_type as ScaleType] || scale.scale_type}
                  </div>

                  {/* Metrics */}
                  <div className="grid grid-cols-3 gap-2 mb-4 text-center">
                    <div className="bg-[hsl(var(--muted))]/50 rounded-lg p-2">
                      <p className="text-lg font-bold text-[hsl(var(--foreground))]">
                        {scale.total_shifts}
                      </p>
                      <p className="text-xs text-[hsl(var(--muted-foreground))]">Turnos</p>
                    </div>
                    <div className="bg-[hsl(var(--muted))]/50 rounded-lg p-2">
                      <p className="text-lg font-bold text-[hsl(var(--foreground))]">
                        {scale.total_hours.toFixed(0)}h
                      </p>
                      <p className="text-xs text-[hsl(var(--muted-foreground))]">Horas</p>
                    </div>
                    <div className="bg-[hsl(var(--muted))]/50 rounded-lg p-2">
                      <p className="text-lg font-bold text-[hsl(var(--foreground))]">
                        {scale.fill_rate?.toFixed(0) || 0}%
                      </p>
                      <p className="text-xs text-[hsl(var(--muted-foreground))]">Preenchido</p>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      className="flex-1"
                      onClick={() => router.push(`/modulos/operacional/escalas/${scale.id}`)}
                    >
                      <Eye className="w-3 h-3 mr-1" />
                      Ver
                    </Button>

                    {scale.status === 'draft' && (
                      <>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleSubmitForApproval(scale)}
                          disabled={operationLoading}
                        >
                          <Send className="w-3 h-3" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-red-500 hover:text-red-600"
                          onClick={() => {
                            setSelectedScale(scale);
                            setShowDeleteModal(true);
                          }}
                        >
                          <Trash2 className="w-3 h-3" />
                        </Button>
                      </>
                    )}

                    {scale.status === 'pending_approval' && (
                      <Button
                        variant="outline"
                        size="sm"
                        className="text-green-500"
                        onClick={() => handleApprove(scale)}
                        disabled={operationLoading}
                      >
                        <CheckCircle className="w-3 h-3 mr-1" />
                        Aprovar
                      </Button>
                    )}

                    {scale.status === 'approved' && (
                      <Button
                        variant="outline"
                        size="sm"
                        className="text-blue-500"
                        onClick={() => handlePublish(scale)}
                        disabled={operationLoading}
                      >
                        <Send className="w-3 h-3 mr-1" />
                        Publicar
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between">
                <p className="text-sm text-[hsl(var(--muted-foreground))]">
                  Mostrando {((page - 1) * pageSize) + 1} a {Math.min(page * pageSize, total)} de {total}
                </p>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage(page - 1)}
                    disabled={page === 1}
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </Button>
                  <span className="text-sm text-[hsl(var(--foreground))]">
                    {page} / {totalPages}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage(page + 1)}
                    disabled={page === totalPages}
                  >
                    <ChevronRight className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </main>

      {/* Generate Modal */}
      <ScaleGenerateModal
        isOpen={showGenerateModal}
        onClose={() => setShowGenerateModal(false)}
        posts={posts}
        onSuccess={() => {
          setShowGenerateModal(false);
          refresh();
        }}
      />

      {/* Delete Modal */}
      <ConfirmModal
        isOpen={showDeleteModal}
        onClose={() => {
          setShowDeleteModal(false);
          setSelectedScale(null);
        }}
        onConfirm={handleDelete}
        title="Excluir Escala"
        message={`Tem certeza que deseja excluir a escala de ${selectedScale ? monthNames[selectedScale.month - 1] + '/' + selectedScale.year : ''}? Esta acao nao pode ser desfeita.`}
        confirmText="Excluir"
        variant="danger"
        isLoading={operationLoading}
      />

      {/* Templates Modal */}
      <Modal
        isOpen={showTemplatesModal}
        onClose={() => setShowTemplatesModal(false)}
        title=""
        size="full"
        showCloseButton={true}
      >
        <TemplateManager />
      </Modal>
    </div>
  );
}
