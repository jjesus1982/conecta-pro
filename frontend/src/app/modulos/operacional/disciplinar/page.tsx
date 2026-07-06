'use client';

import dynamic from 'next/dynamic';
import { FileWarning, Search, Plus, Eye, Edit2, Trash2, ArrowLeft, ChevronLeft, ChevronRight, AlertCircle, CheckCircle, RefreshCw, Clock, FileSignature, AlertTriangle, XCircle } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
;
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ConfirmModal } from '@/components/ui/modal';
import { PageHeader } from '@/components/ui/page-header';
import { useAuth } from '@/hooks/useAuth';
import { useDisciplinary, useDisciplinaryStats } from '@/hooks/useDisciplinary';
import { useDeleteDisciplinaryAction } from '@/hooks/operacional/useDisciplinary';
import { getErrorMessage } from '@/lib/api';
const DisciplinaryFormModal = dynamic(() => import('@/components/operacional/disciplinary-form-modal').then(m => m.DisciplinaryFormModal), { ssr: false });
const DisciplinaryDetailModal = dynamic(() => import('@/components/operacional/disciplinary-detail-modal').then(m => m.DisciplinaryDetailModal), { ssr: false });
const DisciplinarySignatureModal = dynamic(() => import('@/components/operacional/disciplinary-signature-modal').then(m => m.DisciplinarySignatureModal), { ssr: false });
import type {
  DisciplinaryAction,
  DisciplinaryActionStatus,
  DisciplinaryActionType,
} from '@/types/disciplinary';
import {
  ACTION_TYPE_LABELS,
  STATUS_LABELS,
  STATUS_COLORS,
  ACTION_TYPE_COLORS,
  REASON_CATEGORY_LABELS,
} from '@/types/disciplinary';

export default function DisciplinarPage() {
  const router = useRouter();
  const { isLoading: authLoading, isAuthenticated } = useAuth();
  const {
    actions,
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
  } = useDisciplinary({ initialPageSize: 10 });
  const { stats, refresh: refreshStats } = useDisciplinaryStats();
  const deleteDisciplinaryMutation = useDeleteDisciplinaryAction();

  const [searchTerm, setSearchTerm] = useState('');
  const [selectedStatus, setSelectedStatus] = useState<DisciplinaryActionStatus | ''>('');
  const [selectedType, setSelectedType] = useState<DisciplinaryActionType | ''>('');

  // Modal states
  const [selectedAction, setSelectedAction] = useState<DisciplinaryAction | null>(null);
  const [showFormModal, setShowFormModal] = useState(false);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [showSignatureModal, setShowSignatureModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [editAction, setEditAction] = useState<DisciplinaryAction | null>(null);
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
        action_type: selectedType || undefined,
      });
    }, 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- debounce filter sync
  }, [searchTerm, selectedStatus, selectedType]);

  // Handlers
  const handleNew = () => {
    setEditAction(null);
    setShowFormModal(true);
  };

  const handleView = (action: DisciplinaryAction) => {
    setSelectedAction(action);
    setShowDetailModal(true);
  };

  const handleEdit = (action: DisciplinaryAction) => {
    setEditAction(action);
    setShowFormModal(true);
  };

  const handleOpenSignature = (action: DisciplinaryAction) => {
    setSelectedAction(action);
    setShowSignatureModal(true);
  };

  const handleDelete = async () => {
    if (!selectedAction) return;

    setIsDeleting(true);
    setDeleteError(null);

    try {
      await deleteDisciplinaryMutation.mutateAsync({ actionId: selectedAction.id });
      setShowDeleteModal(false);
      setSelectedAction(null);
      handleRefresh();
    } catch (err) {
      setDeleteError(getErrorMessage(err));
    } finally {
      setIsDeleting(false);
    }
  };

  const confirmDelete = (action: DisciplinaryAction) => {
    setSelectedAction(action);
    setShowDeleteModal(true);
  };

  const handleRefresh = () => {
    refresh();
    refreshStats();
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('pt-BR');
  };

  const getStatusIcon = (status: DisciplinaryActionStatus) => {
    switch (status) {
      case 'rascunho':
        return <Edit2 className="w-4 h-4" />;
      case 'pendente_aprovacao':
        return <Clock className="w-4 h-4" />;
      case 'aprovada':
        return <CheckCircle className="w-4 h-4" />;
      case 'rejeitada':
        return <XCircle className="w-4 h-4" />;
      case 'pendente_assinatura':
        return <FileSignature className="w-4 h-4" />;
      case 'assinada':
        return <CheckCircle className="w-4 h-4" />;
      case 'aplicada':
        return <CheckCircle className="w-4 h-4" />;
      case 'cancelada':
        return <XCircle className="w-4 h-4" />;
      default:
        return <AlertCircle className="w-4 h-4" />;
    }
  };

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))]">
        <div className="animate-pulse-slow text-[hsl(var(--primary))]">
          <FileWarning className="w-12 h-12" />
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
          title="Processos Disciplinares"
          subtitle={`${total} registros`}
          icon={<FileWarning className="w-5 h-5" />}
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
              <Button variant="primary" onClick={handleNew}>
                <Plus className="w-4 h-4 mr-2" />
                Novo Processo
              </Button>
            </>
          }
        />

        {/* Stats Cards */}
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-4 mb-6">
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
                <FileWarning className="w-5 h-5 text-blue-500" />
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
              <div className="w-10 h-10 rounded-lg bg-yellow-500/10 flex items-center justify-center">
                <Clock className="w-5 h-5 text-yellow-500" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                  {stats?.pending_approval || 0}
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Pend. Aprovação</p>
              </div>
            </div>
          </div>

          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-orange-500/10 flex items-center justify-center">
                <FileSignature className="w-5 h-5 text-orange-500" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                  {stats?.pending_signature || 0}
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Pend. Assinatura</p>
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
                  {stats?.this_month || 0}
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Este Mes</p>
              </div>
            </div>
          </div>

          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-purple-500/10 flex items-center justify-center">
                <AlertTriangle className="w-5 h-5 text-purple-500" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                  {stats?.this_year || 0}
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Este Ano</p>
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
                placeholder="Buscar por funcionario, codigo..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-10"
              />
            </div>
            <div className="flex gap-2">
              <select
                value={selectedStatus}
                onChange={(e) => setSelectedStatus(e.target.value as DisciplinaryActionStatus | '')}
                className="px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))] text-sm"
              >
                <option value="">Todos os Status</option>
                {Object.entries(STATUS_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
              <select
                value={selectedType}
                onChange={(e) => setSelectedType(e.target.value as DisciplinaryActionType | '')}
                className="px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))] text-sm"
              >
                <option value="">Todos os Tipos</option>
                {Object.entries(ACTION_TYPE_LABELS).map(([value, label]) => (
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
              <FileWarning className="w-8 h-8" />
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
                        Motivo
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
                    {actions.map((action) => (
                      <tr
                        key={action.id}
                        className="hover:bg-[hsl(var(--muted))]/50 transition-colors cursor-pointer"
                        onClick={() => handleView(action)}
                      >
                        <td className="px-4 py-3">
                          <span className="text-sm font-mono text-[hsl(var(--foreground))]">
                            {action.code}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <div>
                            <p className="text-sm font-medium text-[hsl(var(--foreground))]">
                              {action.employee_name}
                            </p>
                            {action.employee_position && (
                              <p className="text-xs text-[hsl(var(--muted-foreground))]">
                                {action.employee_position}
                              </p>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${
                              ACTION_TYPE_COLORS[action.action_type] || 'bg-gray-500/10 text-gray-500'
                            }`}
                          >
                            {ACTION_TYPE_LABELS[action.action_type]}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span className="text-sm text-[hsl(var(--muted-foreground))]">
                            {REASON_CATEGORY_LABELS[action.reason_category]?.split(' (')[0] || action.reason_category}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span className="text-sm text-[hsl(var(--foreground))]">
                            {formatDate(action.incident_date)}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${
                              STATUS_COLORS[action.status] || 'bg-gray-500/10 text-gray-500'
                            }`}
                          >
                            {getStatusIcon(action.status)}
                            {STATUS_LABELS[action.status]}
                          </span>
                        </td>
                        <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                          <div className="flex items-center justify-end gap-1">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleView(action)}
                              title="Ver Detalhes"
                            >
                              <Eye className="w-4 h-4" />
                            </Button>
                            {action.status === 'rascunho' && (
                              <>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleEdit(action)}
                                  title="Editar"
                                >
                                  <Edit2 className="w-4 h-4" />
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => confirmDelete(action)}
                                  className="text-red-500 hover:text-red-600"
                                  title="Excluir"
                                >
                                  <Trash2 className="w-4 h-4" />
                                </Button>
                              </>
                            )}
                            {(action.status === 'pendente_assinatura' || action.status === 'aprovada') && (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleOpenSignature(action)}
                                title="Assinar"
                                className="text-orange-500 hover:text-orange-600"
                              >
                                <FileSignature className="w-4 h-4" />
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
            {actions.length === 0 && !isLoading && (
              <div className="text-center py-12 bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl mt-4">
                <FileWarning className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
                <h3 className="text-lg font-medium text-[hsl(var(--foreground))]">
                  Nenhum processo encontrado
                </h3>
                <p className="text-[hsl(var(--muted-foreground))] mt-1">
                  Ajuste os filtros ou crie um novo processo
                </p>
                <Button variant="primary" className="mt-4" onClick={handleNew}>
                  <Plus className="w-4 h-4 mr-2" />
                  Novo Processo
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
      </main>

      {/* Form Modal */}
      <DisciplinaryFormModal
        isOpen={showFormModal}
        onClose={() => {
          setShowFormModal(false);
          setEditAction(null);
        }}
        onSuccess={handleRefresh}
        editData={editAction}
      />

      {/* Detail Modal */}
      <DisciplinaryDetailModal
        isOpen={showDetailModal}
        onClose={() => {
          setShowDetailModal(false);
          setSelectedAction(null);
        }}
        onSuccess={handleRefresh}
        action={selectedAction}
        onOpenSignature={handleOpenSignature}
      />

      {/* Signature Modal */}
      <DisciplinarySignatureModal
        isOpen={showSignatureModal}
        onClose={() => {
          setShowSignatureModal(false);
          setSelectedAction(null);
        }}
        onSuccess={handleRefresh}
        action={selectedAction}
      />

      {/* Delete Modal */}
      <ConfirmModal
        isOpen={showDeleteModal}
        onClose={() => {
          setShowDeleteModal(false);
          setSelectedAction(null);
          setDeleteError(null);
        }}
        onConfirm={handleDelete}
        title="Excluir Processo"
        message={`Tem certeza que deseja excluir o processo ${selectedAction?.code}? Esta ação não pode ser desfeita.${deleteError ? ` Erro: ${deleteError}` : ''}`}
        confirmText="Excluir"
        isLoading={isDeleting}
        variant="danger"
      />
    </div>
  );
}
