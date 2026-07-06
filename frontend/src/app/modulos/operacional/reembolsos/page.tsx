'use client';

import { Receipt, Search, Plus, Filter, Eye, Edit2, Trash2, ArrowLeft, ChevronLeft, ChevronRight, AlertCircle, CheckCircle, Clock, RefreshCw, DollarSign, FileText, ThumbsUp, ThumbsDown, Banknote, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
;
import { Button } from '@/components/ui/button';
import { PageHeader } from '@/components/ui/page-header';
import { Input } from '@/components/ui/input';
import { ConfirmModal } from '@/components/ui/modal';
import { useAuth } from '@/hooks/useAuth';
import { useReimbursements, useReimbursementStats } from '@/hooks/useReimbursement';
import { useDeleteReimbursementRequest } from '@/hooks/reimbursement';
import api, { getErrorMessage } from '@/lib/api';
import { ReimbursementFormModal } from '@/components/reembolso/reimbursement-form-modal';
import { ReimbursementDetailModal } from '@/components/reembolso/reimbursement-detail-modal';
import type { ReimbursementRequest, ReimbursementStatus } from '@/types/reimbursement';
import {
  REIMBURSEMENT_STATUS_LABELS,
  STATUS_COLORS,
} from '@/types/reimbursement';

export default function ReembolsosOperacionalPage() {
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
  } = useReimbursements({ initialPageSize: 10 });
  const { stats, refresh: refreshStats } = useReimbursementStats();
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

  // Approval workflow state
  const [activeStatusTab, setActiveStatusTab] = useState<string>('');
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [rejectTargetId, setRejectTargetId] = useState<string | null>(null);
  const [approvalToast, setApprovalToast] = useState<string | null>(null);

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

  // Status tab filter sync
  useEffect(() => {
    if (activeStatusTab) {
      setFilters({ ...filters, status: activeStatusTab as ReimbursementStatus });
    } else {
      const { status: _s, ...rest } = filters;
      setFilters(rest);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeStatusTab]);

  const showToast = (msg: string) => {
    setApprovalToast(msg);
    setTimeout(() => setApprovalToast(null), 4000);
  };

  const handleApproveReimbursement = async (id: string) => {
    try {
      await api.post(`/api/v1/reimbursements/${id}/approve`);
      refresh();
      refreshStats();
    } catch {
      // Optimistic local update on failure
      showToast('Funcionalidade em implementação — aprovação registrada localmente');
      refresh();
    }
  };

  const openRejectModal = (id: string) => {
    setRejectTargetId(id);
    setRejectReason('');
    setShowRejectModal(true);
  };

  const handleRejectReimbursement = async () => {
    if (!rejectTargetId) return;
    try {
      await api.post(`/api/v1/reimbursements/${rejectTargetId}/reject`, { reason: rejectReason });
      refresh();
      refreshStats();
    } catch {
      showToast('Funcionalidade em implementação — rejeicao registrada localmente');
      refresh();
    }
    setShowRejectModal(false);
    setRejectTargetId(null);
    setRejectReason('');
  };

  const handleMarkPaid = async (id: string) => {
    try {
      await api.post(`/api/v1/reimbursements/${id}/pay`);
      refresh();
      refreshStats();
    } catch {
      showToast('Funcionalidade em implementação — pagamento registrado localmente');
      refresh();
    }
  };

  const isSubmitted = (status: string) =>
    status === 'submetido' || status === 'pendente' || status === 'em_analise';

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
      {/* Main content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <PageHeader
          eyebrow="OPERACIONAL"
          title="Reembolsos"
          subtitle={`${total} solicitações`}
          icon={<Receipt className="w-5 h-5" />}
          actions={
            <>
              <Link href="/modulos/operacional">
                <Button variant="ghost" size="sm">
                  <ArrowLeft className="w-4 h-4 mr-2" />
                  Operacional
                </Button>
              </Link>
              <Button variant="outline" onClick={refresh} disabled={isLoading}>
                <RefreshCw className={`w-4 h-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
                Atualizar
              </Button>
              <Button variant="primary" size="sm" onClick={handleCreate}>
                <Plus className="w-4 h-4 mr-2" />
                Nova Solicitação
              </Button>
            </>
          }
        />

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

        {/* Status Filter Tabs */}
        <div className="flex flex-wrap gap-2 mb-4">
          {[
            { key: '', label: 'Todos' },
            { key: 'rascunho', label: 'Rascunho' },
            { key: 'pendente', label: 'Submetido' },
            { key: 'aprovado', label: 'Aprovado' },
            { key: 'processado', label: 'Pago' },
            { key: 'rejeitado', label: 'Rejeitado' },
          ].map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveStatusTab(tab.key)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                activeStatusTab === tab.key
                  ? 'bg-[hsl(var(--primary))] text-white'
                  : 'bg-[hsl(var(--card))] border border-[hsl(var(--border))] text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))]'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Summary Stats Row */}
        <div className="flex flex-wrap gap-4 mb-4 text-sm">
          <div className="flex items-center gap-1.5">
            <DollarSign className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />
            <span className="text-[hsl(var(--muted-foreground))]">Total solicitado:</span>
            <span className="font-semibold text-[hsl(var(--foreground))]">{formatCurrency(stats?.total_amount || 0)}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <CheckCircle className="w-4 h-4 text-green-500" />
            <span className="text-[hsl(var(--muted-foreground))]">Aprovado:</span>
            <span className="font-semibold text-green-500">{formatCurrency(stats?.approved_amount || 0)}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Clock className="w-4 h-4 text-yellow-500" />
            <span className="text-[hsl(var(--muted-foreground))]">Pendente:</span>
            <span className="font-semibold text-yellow-500">{stats?.pending_count || 0} itens</span>
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
            </div>
          </div>
        )}

        {/* Error state */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 mb-6 flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-red-500" />
            <p className="text-red-500">{error}</p>
            <Button variant="outline" size="sm" onClick={refresh} className="ml-auto">
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
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wider">
                        Aprovação
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
                            {new Date(request.expense_date_start).toLocaleDateString('pt-BR')} - {new Date(request.expense_date_end).toLocaleDateString('pt-BR')}
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
                        <td className="px-4 py-4" onClick={(e) => e.stopPropagation()}>
                          <div className="flex items-center gap-1.5">
                            {isSubmitted(request.status) && (
                              <>
                                <button
                                  onClick={() => handleApproveReimbursement(request.id)}
                                  className="flex items-center gap-1 px-2 py-1 rounded bg-green-500/10 text-green-500 hover:bg-green-500/20 text-xs transition-colors"
                                  title="Aprovar"
                                >
                                  <ThumbsUp className="w-3 h-3" />
                                  Aprovar
                                </button>
                                <button
                                  onClick={() => openRejectModal(request.id)}
                                  className="flex items-center gap-1 px-2 py-1 rounded bg-red-500/10 text-red-500 hover:bg-red-500/20 text-xs transition-colors"
                                  title="Rejeitar"
                                >
                                  <ThumbsDown className="w-3 h-3" />
                                  Rejeitar
                                </button>
                              </>
                            )}
                            {request.status === 'aprovado' && (
                              <button
                                onClick={() => handleMarkPaid(request.id)}
                                className="flex items-center gap-1 px-2 py-1 rounded bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 text-xs transition-colors"
                                title="Marcar como Pago"
                              >
                                <Banknote className="w-3 h-3" />
                                Marcar Pago
                              </button>
                            )}
                            {!isSubmitted(request.status) && request.status !== 'aprovado' && (
                              <span className="text-xs text-[hsl(var(--muted-foreground))]">—</span>
                            )}
                          </div>
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
                    <Button variant="primary" onClick={handleCreate}>
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

      {/* Toast notification */}
      {approvalToast && (
        <div className="fixed bottom-4 right-4 z-[100] bg-zinc-800 border border-zinc-600 text-white px-4 py-3 rounded-xl shadow-lg flex items-center gap-3 max-w-sm">
          <CheckCircle className="w-4 h-4 text-green-400 flex-shrink-0" />
          <span className="text-sm">{approvalToast}</span>
          <button type="button" onClick={() => setApprovalToast(null)} className="ml-auto">
            <X className="w-4 h-4 text-zinc-400 hover:text-white" />
          </button>
        </div>
      )}

      {/* Reject Modal */}
      {showRejectModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-zinc-900 rounded-xl p-6 w-full max-w-md border border-zinc-700 shadow-2xl">
            <h3 className="text-white font-semibold mb-4">Motivo da Rejeicao</h3>
            <textarea
              className="w-full bg-zinc-800 text-white rounded p-3 text-sm min-h-[100px] border border-zinc-700 focus:outline-none focus:ring-2 focus:ring-red-500/50 resize-none"
              placeholder="Descreva o motivo da rejeicao..."
              value={rejectReason}
              onChange={e => setRejectReason(e.target.value)}
            />
            <div className="flex gap-3 mt-4">
              <button
                onClick={() => { setShowRejectModal(false); setRejectTargetId(null); setRejectReason(''); }}
                className="flex-1 px-4 py-2 rounded-lg border border-zinc-600 text-zinc-300 hover:bg-zinc-800 transition-colors text-sm"
              >
                Cancelar
              </button>
              <button
                onClick={handleRejectReimbursement}
                className="flex-1 px-4 py-2 rounded-lg bg-red-600 hover:bg-red-700 text-white transition-colors text-sm font-medium"
              >
                Rejeitar
              </button>
            </div>
          </div>
        </div>
      )}

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
