'use client';

import { Receipt, Search, ArrowLeft, ChevronLeft, ChevronRight, AlertCircle, CheckCircle, Clock, RefreshCw, DollarSign, Eye, XCircle, RotateCcw } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
;
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useAuth } from '@/hooks/useAuth';
import { usePendingApprovals, useReimbursementStats } from '@/hooks/useReimbursement';
import { useApproveReimbursement, useRejectReimbursement } from '@/hooks/reimbursement';
import { getErrorMessage } from '@/lib/api';
import { ReimbursementApprovalModal } from '@/components/reembolso/reimbursement-approval-modal';
import { ReimbursementDetailModal } from '@/components/reembolso/reimbursement-detail-modal';
import type { ReimbursementRequest, ApprovalLevel } from '@/types/reimbursement';
import {
  REIMBURSEMENT_STATUS_LABELS,
  APPROVAL_LEVEL_LABELS,
  STATUS_COLORS,
} from '@/types/reimbursement';

export default function AprovacoesPage() {
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
    approvalLevel,
    setApprovalLevel,
    setPage,
    refresh,
  } = usePendingApprovals({ initialPageSize: 10 });
  const { stats, refresh: refreshStats } = useReimbursementStats();
  const approveMutation = useApproveReimbursement();
  const rejectMutation = useRejectReimbursement();

  // Modal states
  const [selectedRequest, setSelectedRequest] = useState<ReimbursementRequest | null>(null);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [showApprovalModal, setShowApprovalModal] = useState(false);
  const [isApproving, setIsApproving] = useState(false);
  const [approvalError, setApprovalError] = useState<string | null>(null);

  // Redirecionar se nao autenticado
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [authLoading, isAuthenticated, router]);

  // Handlers
  const handleView = (request: ReimbursementRequest) => {
    setSelectedRequest(request);
    setShowDetailModal(true);
  };

  const handleApprove = (request: ReimbursementRequest) => {
    setSelectedRequest(request);
    setShowApprovalModal(true);
  };

  const handleQuickApprove = async (request: ReimbursementRequest) => {
    setIsApproving(true);
    setApprovalError(null);

    try {
      await approveMutation.mutateAsync({ requestId: request.id });
      refresh();
      refreshStats();
    } catch (err) {
      setApprovalError(getErrorMessage(err));
    } finally {
      setIsApproving(false);
    }
  };

  const handleQuickReject = async (request: ReimbursementRequest, reason: string) => {
    setIsApproving(true);
    setApprovalError(null);

    try {
      await rejectMutation.mutateAsync({ requestId: request.id, data: { reason } });
      refresh();
      refreshStats();
    } catch (err) {
      setApprovalError(getErrorMessage(err));
    } finally {
      setIsApproving(false);
    }
  };

  const handleApprovalSuccess = () => {
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
          <CheckCircle className="w-12 h-12" />
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
              <Link href="/modulos/reembolso">
                <Button variant="ghost" size="sm">
                  <ArrowLeft className="w-4 h-4 mr-2" />
                  Reembolsos
                </Button>
              </Link>
              <div className="flex items-center gap-2">
                <div className="w-10 h-10 rounded-lg bg-yellow-500/10 flex items-center justify-center">
                  <CheckCircle className="w-5 h-5 text-yellow-500" />
                </div>
                <div>
                  <h1 className="text-lg font-semibold text-[hsl(var(--foreground))]">
                    Aprovações Pendentes
                  </h1>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">
                    {total} solicitações aguardando
                  </p>
                </div>
              </div>
            </div>
            <Button type="button" variant="outline" onClick={refresh} disabled={isLoading}>
              <RefreshCw className={`w-4 h-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
              Atualizar
            </Button>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Stats Cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
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
              <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
                <DollarSign className="w-5 h-5 text-blue-500" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                  {formatCurrency(stats?.pending_amount || 0)}
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Valor Pendente</p>
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
              <div className="w-10 h-10 rounded-lg bg-emerald-500/10 flex items-center justify-center">
                <DollarSign className="w-5 h-5 text-emerald-500" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                  {formatCurrency(stats?.approved_amount || 0)}
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Valor Aprovado</p>
              </div>
            </div>
          </div>
        </div>

        {/* Filtro por nivel */}
        <div className="flex flex-wrap gap-2 mb-6">
          <Button
            variant={!approvalLevel ? 'primary' : 'outline'}
            size="sm"
            onClick={() => setApprovalLevel(undefined)}
          >
            Todos
          </Button>
          {Object.entries(APPROVAL_LEVEL_LABELS).map(([value, label]) => (
            <Button
              key={value}
              variant={approvalLevel === value ? 'primary' : 'outline'}
              size="sm"
              onClick={() => setApprovalLevel(value)}
            >
              {label.split(' (')[0]}
            </Button>
          ))}
        </div>

        {/* Error state */}
        {(error || approvalError) && (
          <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 mb-6 flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-red-500" />
            <p className="text-red-500">{error || approvalError}</p>
            <Button type="button" variant="outline" size="sm" onClick={refresh} className="ml-auto">
              Tentar novamente
            </Button>
          </div>
        )}

        {/* Loading state */}
        {isLoading && (
          <div className="flex items-center justify-center py-12">
            <div className="animate-pulse-slow text-[hsl(var(--primary))]">
              <CheckCircle className="w-8 h-8" />
            </div>
          </div>
        )}

        {/* Requests Cards */}
        {!isLoading && !error && (
          <>
            <div className="space-y-4">
              {requests.map((request) => (
                <div
                  key={request.id}
                  className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex items-start gap-4 flex-1">
                      <div className="w-12 h-12 rounded-lg bg-emerald-500/10 flex items-center justify-center flex-shrink-0">
                        <Receipt className="w-6 h-6 text-emerald-500" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <h3 className="font-medium text-[hsl(var(--foreground))] truncate">
                            {request.title}
                          </h3>
                          <span className="text-xs text-[hsl(var(--muted-foreground))]">
                            {request.code}
                          </span>
                        </div>
                        <div className="flex flex-wrap items-center gap-4 text-sm text-[hsl(var(--muted-foreground))]">
                          <span>
                            {new Date(request.expense_date_start).toLocaleDateString('pt-BR')} -{' '}
                            {new Date(request.expense_date_end).toLocaleDateString('pt-BR')}
                          </span>
                          <span>{request.items_count} itens</span>
                          {request.approval_level && (
                            <span className="text-xs px-2 py-0.5 rounded bg-yellow-500/10 text-yellow-500">
                              {APPROVAL_LEVEL_LABELS[request.approval_level].split(' (')[0]}
                            </span>
                          )}
                        </div>
                        {request.description && (
                          <p className="text-sm text-[hsl(var(--muted-foreground))] mt-2 line-clamp-2">
                            {request.description}
                          </p>
                        )}
                      </div>
                    </div>

                    <div className="flex flex-col items-end gap-3">
                      <p className="text-xl font-bold text-[hsl(var(--foreground))]">
                        {formatCurrency(request.total_amount)}
                      </p>
                      <div className="flex items-center gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleView(request)}
                          title="Ver Detalhes"
                        >
                          <Eye className="w-4 h-4" />
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleApprove(request)}
                          className="text-green-500 border-green-500/30 hover:bg-green-500/10"
                        >
                          <CheckCircle className="w-4 h-4 mr-1" />
                          Aprovar
                        </Button>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* Empty state */}
            {requests.length === 0 && !isLoading && (
              <div className="text-center py-12 bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl">
                <CheckCircle className="w-12 h-12 text-green-500 mx-auto mb-4" />
                <h3 className="text-lg font-medium text-[hsl(var(--foreground))]">
                  Nenhuma aprovação pendente
                </h3>
                <p className="text-[hsl(var(--muted-foreground))] mt-1">
                  Todas as solicitações foram processadas
                </p>
              </div>
            )}

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
        onEdit={() => {}}
        onRefresh={() => {
          refresh();
          refreshStats();
        }}
      />

      <ReimbursementApprovalModal
        request={selectedRequest}
        isOpen={showApprovalModal}
        onClose={() => {
          setShowApprovalModal(false);
          setSelectedRequest(null);
        }}
        onSuccess={handleApprovalSuccess}
      />
    </div>
  );
}
