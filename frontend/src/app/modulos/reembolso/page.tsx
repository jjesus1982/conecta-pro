'use client';

import { Receipt, Search, Plus, Filter, Eye, Edit2, Trash2, ArrowLeft, ChevronLeft, ChevronRight, AlertCircle, CheckCircle, Clock, RefreshCw, Send, DollarSign, FileText, XCircle } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
;
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ConfirmModal } from '@/components/ui/modal';
import { useAuth } from '@/hooks/useAuth';
import { useReimbursements, useReimbursementStats } from '@/hooks/useReimbursement';
import { useDeleteReimbursementRequest } from '@/hooks/reimbursement';
import { getErrorMessage } from '@/lib/api';
import { ReimbursementFormModal } from '@/components/reembolso/reimbursement-form-modal';
import { ReimbursementDetailModal } from '@/components/reembolso/reimbursement-detail-modal';
import type { ReimbursementRequest, ReimbursementStatus } from '@/types/reimbursement';
import {
  REIMBURSEMENT_STATUS_LABELS,
  STATUS_COLORS,
} from '@/types/reimbursement';

export default function ReembolsoPage() {
  const router = useRouter();
  const { isLoading: authLoading, isAuthenticated } = useAuth();
  const {
    requests,
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
  } = useReimbursements({ initialPageSize: 10, myOnly: true });
  const { stats, refresh: refreshStats } = useReimbursementStats({ myOnly: true });
  const deleteReimbursementMutation = useDeleteReimbursementRequest();

  const [searchTerm, setSearchTerm] = useState('');
  const [showFilters, setShowFilters] = useState(false);

  // Modal states
  const [selectedRequest, setSelectedRequest] = useState<ReimbursementRequest | null>(null);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [showFormModal, setShowFormModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
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
      setFilters({ ...filters, search: searchTerm || undefined });
    }, 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- debounce filter sync
  }, [searchTerm]);

  // Handlers
  const handleView = (request: ReimbursementRequest) => {
    setSelectedRequest(request);
    setShowDetailModal(true);
  };

  const handleEdit = (request: ReimbursementRequest) => {
    setSelectedRequest(request);
    setShowFormModal(true);
    setShowDetailModal(false);
  };

  const handleCreate = () => {
    setSelectedRequest(null);
    setShowFormModal(true);
  };

  const handleDelete = (request: ReimbursementRequest) => {
    setSelectedRequest(request);
    setDeleteError(null);
    setShowDeleteModal(true);
  };

  const confirmDelete = async () => {
    if (!selectedRequest) return;

    setIsDeleting(true);
    setDeleteError(null);

    try {
      await deleteReimbursementMutation.mutateAsync(selectedRequest.id);
      setShowDeleteModal(false);
      setSelectedRequest(null);
      refresh();
      refreshStats();
    } catch (err) {
      setDeleteError(getErrorMessage(err));
    } finally {
      setIsDeleting(false);
    }
  };

  const handleFormSuccess = () => {
    refresh();
    refreshStats();
  };

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL',
    }).format(value);
  };

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))]">
        <div className="animate-pulse-slow text-[hsl(var(--primary))]">
          <Receipt className="w-12 h-12" />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-grid">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-[hsl(var(--background))]/80 backdrop-blur-xl border-b border-[hsl(var(--border))]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-4">
              <Link href="/modulos">
                <Button variant="ghost" size="sm">
                  <ArrowLeft className="w-4 h-4 mr-2" />
                  Modulos
                </Button>
              </Link>
              <div className="flex items-center gap-2">
                <div className="w-10 h-10 rounded-lg bg-emerald-500/10 flex items-center justify-center">
                  <Receipt className="w-5 h-5 text-emerald-500" />
                </div>
                <div>
                  <h1 className="text-lg font-semibold text-[hsl(var(--foreground))]">
                    Reembolsos
                  </h1>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">
                    {total} solicitações
                  </p>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Link href="/modulos/reembolso/aprovacoes">
                <Button variant="outline" size="sm">
                  <CheckCircle className="w-4 h-4 mr-2" />
                  Aprovações
                </Button>
              </Link>
              <Button type="button" variant="primary" size="sm" onClick={handleCreate}>
                <Plus className="w-4 h-4 mr-2" />
                Nova Solicitação
              </Button>
            </div>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Stats Cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-emerald-500/10 flex items-center justify-center">
                <Receipt className="w-5 h-5 text-emerald-500" />
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
                  {stats?.pending_count || 0}
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
                  {stats?.approved_count || 0}
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Aprovados</p>
              </div>
            </div>
          </div>

          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
                <DollarSign className="w-5 h-5 text-blue-500" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                  {formatCurrency(stats?.total_amount || 0)}
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Valor Total</p>
              </div>
            </div>
          </div>
        </div>

        {/* Search and Filters */}
        <div className="flex flex-col sm:flex-row gap-4 mb-6">
          <div className="flex-1">
            <Input
              type="search"
              placeholder="Buscar por codigo, titulo..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              icon={<Search className="w-4 h-4" />}
            />
          </div>
          <Button
            variant="outline"
            onClick={() => setShowFilters(!showFilters)}
            className={showFilters ? 'border-[hsl(var(--primary))]' : ''}
          >
            <Filter className="w-4 h-4 mr-2" />
            Filtros
          </Button>
          <Button type="button" variant="outline" onClick={refresh} disabled={isLoading}>
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          </Button>
        </div>

        {/* Filters Panel */}
        {showFilters && (
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4 mb-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-medium text-[hsl(var(--foreground))]">Filtros</h3>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setFilters({});
                  setSearchTerm('');
                }}
              >
                Limpar filtros
              </Button>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              <div>
                <label className="text-sm text-[hsl(var(--muted-foreground))] mb-1 block">
                  Status
                </label>
                <select
                  className="w-full px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))]"
                  value={filters.status || ''}
                  onChange={(e) =>
                    setFilters({ ...filters, status: e.target.value as ReimbursementStatus || undefined })
                  }
                >
                  <option value="">Todos</option>
                  {Object.entries(REIMBURSEMENT_STATUS_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-sm text-[hsl(var(--muted-foreground))] mb-1 block">
                  Centro de Custo
                </label>
                <Input
                  placeholder="Centro de custo"
                  value={filters.cost_center || ''}
                  onChange={(e) =>
                    setFilters({ ...filters, cost_center: e.target.value || undefined })
                  }
                />
              </div>
              <div>
                <label className="text-sm text-[hsl(var(--muted-foreground))] mb-1 block">
                  Projeto
                </label>
                <Input
                  placeholder="Projeto"
                  value={filters.project || ''}
                  onChange={(e) =>
                    setFilters({ ...filters, project: e.target.value || undefined })
                  }
                />
              </div>
            </div>
          </div>
        )}

        {/* Error state */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 mb-6 flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-red-500" />
            <p className="text-red-500">{error}</p>
            <Button type="button" variant="outline" size="sm" onClick={refresh} className="ml-auto">
              Tentar novamente
            </Button>
          </div>
        )}

        {/* Loading state */}
        {isLoading && (
          <div className="flex items-center justify-center py-12">
            <div className="animate-pulse-slow text-[hsl(var(--primary))]">
              <Receipt className="w-8 h-8" />
            </div>
          </div>
        )}

        {/* Requests Table */}
        {!isLoading && !error && (
          <>
            <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-[hsl(var(--muted))]">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wider">
                        Solicitação
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wider">
                        Periodo
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wider">
                        Valor
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wider">
                        Itens
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wider">
                        Status
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wider">
                        Ações
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[hsl(var(--border))]">
                    {requests.map((request) => (
                      <tr
                        key={request.id}
                        className="hover:bg-[hsl(var(--muted))]/50 transition-colors cursor-pointer"
                        onClick={() => handleView(request)}
                      >
                        <td className="px-4 py-4">
                          <div className="flex items-center gap-3">
                            <div className="w-10 h-10 rounded-lg bg-emerald-500/10 flex items-center justify-center flex-shrink-0">
                              <Receipt className="w-5 h-5 text-emerald-500" />
                            </div>
                            <div>
                              <p className="font-medium text-[hsl(var(--foreground))]">
                                {request.title}
                              </p>
                              <p className="text-xs text-[hsl(var(--muted-foreground))]">
                                {request.code}
                              </p>
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-4">
                          <span className="text-sm text-[hsl(var(--foreground))]">
                            {new Date(request.expense_date_start).toLocaleDateString('pt-BR')} -{' '}
                            {new Date(request.expense_date_end).toLocaleDateString('pt-BR')}
                          </span>
                        </td>
                        <td className="px-4 py-4">
                          <span className="text-sm font-medium text-[hsl(var(--foreground))]">
                            {formatCurrency(request.total_amount)}
                          </span>
                        </td>
                        <td className="px-4 py-4">
                          <div className="flex items-center gap-2">
                            <FileText className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />
                            <span className="text-sm text-[hsl(var(--foreground))]">
                              {request.items_count}
                            </span>
                          </div>
                        </td>
                        <td className="px-4 py-4">
                          <span
                            className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${
                              STATUS_COLORS[request.status as ReimbursementStatus] || 'bg-gray-500/10 text-gray-500'
                            }`}
                          >
                            {REIMBURSEMENT_STATUS_LABELS[request.status as ReimbursementStatus] || request.status}
                          </span>
                        </td>
                        <td className="px-4 py-4 text-right" onClick={(e) => e.stopPropagation()}>
                          <div className="flex items-center justify-end gap-1">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleView(request)}
                              title="Visualizar"
                            >
                              <Eye className="w-4 h-4" />
                            </Button>
                            {request.can_edit && (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleEdit(request)}
                                title="Editar"
                              >
                                <Edit2 className="w-4 h-4" />
                              </Button>
                            )}
                            {request.can_edit && (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleDelete(request)}
                                title="Excluir"
                                className="text-red-500 hover:text-red-600 hover:bg-red-500/10"
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

              {/* Empty state */}
              {requests.length === 0 && !isLoading && (
                <div className="text-center py-12">
                  <Receipt className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
                  <h3 className="text-lg font-medium text-[hsl(var(--foreground))]">
                    Nenhuma solicitação encontrada
                  </h3>
                  <p className="text-[hsl(var(--muted-foreground))] mt-1 mb-4">
                    {searchTerm || Object.keys(filters).length > 0
                      ? 'Tente ajustar os filtros de busca'
                      : 'Comece criando uma nova solicitação de reembolso'}
                  </p>
                  {!searchTerm && Object.keys(filters).length === 0 && (
                    <Button type="button" variant="primary" onClick={handleCreate}>
                      <Plus className="w-4 h-4 mr-2" />
                      Criar Primeira Solicitação
                    </Button>
                  )}
                </div>
              )}
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-4">
                <p className="text-sm text-[hsl(var(--muted-foreground))]">
                  Mostrando {(page - 1) * pageSize + 1} a{' '}
                  {Math.min(page * pageSize, total)} de {total} solicitações
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

      {/* Modals */}
      <ReimbursementDetailModal
        request={selectedRequest}
        isOpen={showDetailModal}
        onClose={() => {
          setShowDetailModal(false);
          setSelectedRequest(null);
        }}
        onEdit={() => selectedRequest && handleEdit(selectedRequest)}
        onRefresh={() => {
          refresh();
          refreshStats();
        }}
      />

      <ReimbursementFormModal
        request={selectedRequest}
        isOpen={showFormModal}
        onClose={() => {
          setShowFormModal(false);
          setSelectedRequest(null);
        }}
        onSuccess={handleFormSuccess}
      />

      <ConfirmModal
        isOpen={showDeleteModal}
        onClose={() => {
          setShowDeleteModal(false);
          setSelectedRequest(null);
          setDeleteError(null);
        }}
        onConfirm={confirmDelete}
        title="Excluir Solicitação"
        message={
          deleteError
            ? deleteError
            : `Tem certeza que deseja excluir a solicitação "${selectedRequest?.code}"? Esta ação não pode ser desfeita.`
        }
        confirmText="Excluir"
        cancelText="Cancelar"
        variant="danger"
        isLoading={isDeleting}
      />
    </div>
  );
}
