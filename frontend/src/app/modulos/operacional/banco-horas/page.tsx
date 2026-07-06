'use client';

import { Clock, Search, Plus, Eye, Check, X, ArrowLeft, ChevronLeft, ChevronRight, RefreshCw, AlertTriangle, CheckCircle, XCircle, Calendar, User, TrendingUp, TrendingDown, Bell, ArrowUpRight, ArrowDownRight, Timer, Sparkles } from 'lucide-react';
import { useEffect, useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { PageHeader } from '@/components/ui/page-header';
import { Input } from '@/components/ui/input';
import { Modal, ModalFooter } from '@/components/ui/modal';
import { useAuth } from '@/hooks/useAuth';
import {
  useTimeBankEntries,
  usePendingEntries,
  useExpirationAlerts,
  useTimeBankStats,
  useApproveTimeBankEntry,
  useRejectTimeBankEntry,
} from '@/hooks/operacional/useTimeBank';
import {
  type TimeBankEntry,
  type TimeBankStatus,
  type TimeBankEntryType,
  type TimeBankStats,
  type TimeBankAlert,
  TIME_BANK_ENTRY_TYPE_LABELS,
  TIME_BANK_STATUS_LABELS,
  TIME_BANK_ENTRY_TYPE_COLORS,
  TIME_BANK_STATUS_COLORS,
  ALERT_SEVERITY_COLORS,
} from '@/lib/services/time-bank';
import dynamic from 'next/dynamic';
import { Skeleton } from '@/components/ui/skeleton';

// Lazy load recharts — reduz chunk inicial em ~200KB
const BalanceChart = dynamic(() => import('./balance-chart'), {
  ssr: false,
  loading: () => <Skeleton className="w-full h-[200px]" />,
});

export default function BancoHorasPage() {
  const router = useRouter();
  const { isLoading: authLoading, isAuthenticated } = useAuth();

  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [selectedStatus, setSelectedStatus] = useState<TimeBankStatus | ''>('');
  const [selectedType, setSelectedType] = useState<TimeBankEntryType | ''>('');
  const [selectedDate, setSelectedDate] = useState('');

  // Cast needed: local types use PT values, generated hook expects EN values
  const { data: entriesData, isLoading, error: entriesError, refetch } = useTimeBankEntries({
    page,
    page_size: pageSize,
    ...(selectedStatus ? { status: selectedStatus as unknown as string } : {}),
    ...(selectedType ? { entry_type: selectedType as unknown as string } : {}),
  } as Parameters<typeof useTimeBankEntries>[0]);
  const entriesAny = entriesData as unknown as Record<string, unknown> | undefined;
  const entriesRaw = entriesAny?.items;
  const entries = (Array.isArray(entriesRaw) ? entriesRaw : Array.isArray(entriesData) ? entriesData : []) as TimeBankEntry[];
  const total = (entriesAny?.total as number) ?? entries.length;
  const totalPages = (entriesAny?.total_pages as number) ?? Math.ceil(total / pageSize);
  const error = entriesError ? 'Erro ao carregar banco de horas' : null;

  const { data: pendingData = [] } = usePendingEntries();
  const pendingEntries = pendingData as TimeBankEntry[];
  const { data: alertsRaw = [] } = useExpirationAlerts();
  const alerts = alertsRaw as unknown as TimeBankAlert[];
  const { data: stats = null } = useTimeBankStats();
  const approveMutation = useApproveTimeBankEntry();
  const rejectMutation = useRejectTimeBankEntry();

  // Modal states — Approve
  const [showApproveModal, setShowApproveModal] = useState(false);
  const [selectedEntry, setSelectedEntry] = useState<TimeBankEntry | null>(null);
  const [approving, setApproving] = useState(false);

  // Modal states — Reject
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [rejectTarget, setRejectTarget] = useState<TimeBankEntry | null>(null);
  const [rejectReason, setRejectReason] = useState('');
  const [isRejecting, setIsRejecting] = useState(false);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [authLoading, isAuthenticated, router]);

  const handleApprove = async () => {
    if (!selectedEntry) return;

    setApproving(true);
    try {
      await approveMutation.mutateAsync({ entryId: selectedEntry.id, data: {} });
      setShowApproveModal(false);
      refetch();
    } catch (err) {
    } finally {
      setApproving(false);
    }
  };

  const handleReject = (entry: TimeBankEntry) => {
    setRejectTarget(entry);
    setRejectReason('');
    setShowRejectModal(true);
  };

  const handleConfirmReject = async () => {
    if (!rejectTarget || !rejectReason.trim()) return;
    setIsRejecting(true);
    try {
      await rejectMutation.mutateAsync({ entryId: rejectTarget.id, data: { rejection_reason: rejectReason.trim() } });
      setShowRejectModal(false);
      setRejectTarget(null);
      refetch();
    } catch (err) {
    } finally {
      setIsRejecting(false);
    }
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    });
  };

  const formatHours = (hours: number) => {
    const sign = hours >= 0 ? '+' : '';
    const absHours = Math.abs(hours);
    const h = Math.floor(absHours);
    const m = Math.round((absHours - h) * 60);
    return `${sign}${h}h${m > 0 ? `${m}min` : ''}`;
  };

  const getEntryIcon = (type: TimeBankEntryType) => {
    switch (type) {
      case 'credito':
        return <ArrowUpRight className="w-4 h-4 text-green-500" />;
      case 'debito':
        return <ArrowDownRight className="w-4 h-4 text-red-500" />;
      case 'compensacao':
        return <RefreshCw className="w-4 h-4 text-blue-500" />;
      case 'expiracao':
        return <Timer className="w-4 h-4 text-gray-500" />;
      case 'ajuste':
        return <Sparkles className="w-4 h-4 text-purple-500" />;
      default:
        return <Clock className="w-4 h-4" />;
    }
  };

  // Compute top 8 employees by absolute balance from entries
  const balanceChartData = useMemo(() => {
    const byEmployee: Record<string, { name: string; balance: number }> = {};
    entries.forEach(e => {
      const name = e.employee_name || 'N/A';
      if (!byEmployee[name]) byEmployee[name] = { name: name.split(' ')[0] ?? name, balance: 0 };
      byEmployee[name].balance += e.hours;
    });
    return Object.values(byEmployee)
      .sort((a, b) => Math.abs(b.balance) - Math.abs(a.balance))
      .slice(0, 8);
  }, [entries]);

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))]">
        <div className="animate-pulse-slow text-[hsl(var(--primary))]">
          <Clock className="w-12 h-12" />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-grid">
      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <PageHeader
          eyebrow="OPERACIONAL"
          title="Banco de Horas"
          subtitle={`${total} lancamentos | ${pendingEntries.length} pendentes`}
          icon={<Clock className="w-5 h-5" />}
          actions={
            <>
              <Link href="/modulos/operacional">
                <Button variant="ghost" size="sm">
                  <ArrowLeft className="w-4 h-4 mr-2" />
                  Operacional
                </Button>
              </Link>
              <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isLoading}>
                <RefreshCw className={`w-4 h-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
                Atualizar
              </Button>
              <Button variant="primary" size="sm">
                <Plus className="w-4 h-4 mr-2" />
                Novo Lancamento
              </Button>
            </>
          }
        />

        {/* Alerts */}
        {alerts.length > 0 && (
          <div className="space-y-2 mb-6">
            {alerts.slice(0, 3).map((alert, index) => (
              <div
                key={index}
                className={`flex items-center gap-3 p-3 rounded-lg border ${ALERT_SEVERITY_COLORS[alert.severity] ?? ''}`}
              >
                <Bell className="w-5 h-5 flex-shrink-0" />
                <div className="flex-1">
                  <p className="font-medium">{String(alert.employee_name ?? '')}</p>
                  <p className="text-sm opacity-80">{String(alert.message ?? '')}</p>
                </div>
                {alert.hours != null && (
                  <span className="font-semibold">{formatHours(Number(alert.hours))}</span>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Stats */}
        <div className="grid grid-cols-2 lg:grid-cols-6 gap-4 mb-6">
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
                <User className="w-5 h-5 text-blue-500" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                  {stats?.total_employees || 0}
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Funcionarios</p>
              </div>
            </div>
          </div>

          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-green-500/10 flex items-center justify-center">
                <TrendingUp className="w-5 h-5 text-green-500" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-green-500">
                  +{(stats?.total_credit_hours || 0).toFixed(0)}h
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Creditos</p>
              </div>
            </div>
          </div>

          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-red-500/10 flex items-center justify-center">
                <TrendingDown className="w-5 h-5 text-red-500" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-red-500">
                  -{(stats?.total_debit_hours || 0).toFixed(0)}h
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Debitos</p>
              </div>
            </div>
          </div>

          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
                <RefreshCw className="w-5 h-5 text-blue-500" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                  {(stats?.total_compensated_hours || 0).toFixed(0)}h
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Compensadas</p>
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
                  {(stats?.total_pending_hours || 0).toFixed(0)}h
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Pendentes</p>
              </div>
            </div>
          </div>

          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-purple-500/10 flex items-center justify-center">
                <Timer className="w-5 h-5 text-purple-500" />
              </div>
              <div>
                <p className={`font-data text-2xl font-semibold tabular-nums ${(stats?.avg_balance || 0) >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                  {formatHours(stats?.avg_balance || 0)}
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Media Saldo</p>
              </div>
            </div>
          </div>
        </div>

        {/* Balance Chart */}
        {balanceChartData.length > 0 && (
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4 mb-6">
            <h2 className="text-sm font-semibold text-[hsl(var(--foreground))] mb-4">Saldo por Colaborador</h2>
            <BalanceChart data={balanceChartData} />
          </div>
        )}

        {/* Pending Section */}
        {pendingEntries.length > 0 && (
          <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-xl p-4 mb-6">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-5 h-5 text-yellow-500" />
                <h3 className="font-semibold text-yellow-500">
                  {pendingEntries.length} Lancamentos Pendentes de Aprovação
                </h3>
              </div>
            </div>
            <div className="space-y-2">
              {pendingEntries.slice(0, 5).map((entry) => (
                <div
                  key={entry.id}
                  className="flex items-center justify-between bg-[hsl(var(--background))]/50 p-3 rounded-lg"
                >
                  <div className="flex items-center gap-3">
                    {getEntryIcon(entry.entry_type as TimeBankEntryType)}
                    <div>
                      <p className="text-sm font-medium text-[hsl(var(--foreground))]">
                        {(entry as TimeBankEntry).employee_name || 'Funcionario'}
                      </p>
                      <p className="text-xs text-[hsl(var(--muted-foreground))]">
                        {formatDate(entry.reference_date)} • {entry.description || (TIME_BANK_ENTRY_TYPE_LABELS[entry.entry_type as TimeBankEntryType] ?? '')}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className={`font-semibold ${entry.hours >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                      {formatHours(entry.hours)}
                    </span>
                    <div className="flex gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setSelectedEntry(entry as TimeBankEntry);
                          setShowApproveModal(true);
                        }}
                        className="text-green-500 hover:text-green-600"
                      >
                        <Check className="w-4 h-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleReject(entry as TimeBankEntry)}
                        className="text-red-500 hover:text-red-600"
                      >
                        <X className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Filters */}
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4 mb-6">
          <div className="flex flex-col lg:flex-row gap-4">
            <div className="flex flex-wrap gap-2 flex-1">
              <select
                value={selectedStatus}
                onChange={(e) => setSelectedStatus(e.target.value as TimeBankStatus | '')}
                className="px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))] text-sm"
              >
                <option value="">Todos os Status</option>
                {Object.entries(TIME_BANK_STATUS_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
              <select
                value={selectedType}
                onChange={(e) => setSelectedType(e.target.value as TimeBankEntryType | '')}
                className="px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))] text-sm"
              >
                <option value="">Todos os Tipos</option>
                {Object.entries(TIME_BANK_ENTRY_TYPE_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
              <Input
                type="date"
                value={selectedDate}
                onChange={(e) => setSelectedDate(e.target.value)}
                className="w-auto"
              />
            </div>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 mb-6 flex items-center gap-3">
            <XCircle className="w-5 h-5 text-red-500" />
            <p className="text-red-500">{error}</p>
            <Button variant="outline" size="sm" onClick={() => refetch()} className="ml-auto">
              Tentar novamente
            </Button>
          </div>
        )}

        {/* Loading */}
        {isLoading && (
          <div className="flex items-center justify-center py-12">
            <div className="animate-pulse-slow text-[hsl(var(--primary))]">
              <Clock className="w-8 h-8" />
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
                        Data
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                        Funcionario
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                        Tipo
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                        Horas
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                        Saldo Apos
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                        Status
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                        Expira em
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                        Ações
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[hsl(var(--border))]">
                    {entries.map((entry) => (
                      <tr
                        key={entry.id}
                        className="hover:bg-[hsl(var(--muted))]/50 transition-colors"
                      >
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <Calendar className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />
                            <span className="text-sm text-[hsl(var(--foreground))]">
                              {formatDate(entry.reference_date)}
                            </span>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-purple-500 to-blue-600 flex items-center justify-center text-white text-xs font-medium">
                              {(entry.employee_name || 'U').charAt(0)}
                            </div>
                            <span className="text-sm font-medium text-[hsl(var(--foreground))]">
                              {entry.employee_name || 'N/A'}
                            </span>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            {getEntryIcon(entry.entry_type)}
                            <span className={`text-sm px-2 py-0.5 rounded-full ${TIME_BANK_ENTRY_TYPE_COLORS[entry.entry_type]}`}>
                              {TIME_BANK_ENTRY_TYPE_LABELS[entry.entry_type]}
                            </span>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <span className={`text-sm font-semibold ${entry.hours >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                            {formatHours(entry.hours)}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span className={`text-sm ${entry.balance_after >= 0 ? 'text-[hsl(var(--foreground))]' : 'text-red-500'}`}>
                            {formatHours(entry.balance_after)}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${TIME_BANK_STATUS_COLORS[entry.status]}`}>
                            {TIME_BANK_STATUS_LABELS[entry.status]}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          {entry.expiration_date ? (
                            <div className="flex items-center gap-1">
                              {entry.days_until_expiration !== undefined && entry.days_until_expiration <= 30 ? (
                                <AlertTriangle className="w-4 h-4 text-yellow-500" />
                              ) : null}
                              <span className={`text-sm ${
                                entry.days_until_expiration !== undefined && entry.days_until_expiration <= 30
                                  ? 'text-yellow-500'
                                  : 'text-[hsl(var(--muted-foreground))]'
                              }`}>
                                {entry.days_until_expiration !== undefined
                                  ? `${entry.days_until_expiration} dias`
                                  : formatDate(entry.expiration_date)}
                              </span>
                            </div>
                          ) : (
                            <span className="text-sm text-[hsl(var(--muted-foreground))]">-</span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center justify-end gap-1">
                            <Button variant="ghost" size="sm" title="Ver Detalhes">
                              <Eye className="w-4 h-4" />
                            </Button>
                            {entry.status === 'pendente' && (
                              <>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => {
                                    setSelectedEntry(entry);
                                    setShowApproveModal(true);
                                  }}
                                  className="text-green-500 hover:text-green-600"
                                  title="Aprovar"
                                >
                                  <Check className="w-4 h-4" />
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleReject(entry)}
                                  className="text-red-500 hover:text-red-600"
                                  title="Rejeitar"
                                >
                                  <X className="w-4 h-4" />
                                </Button>
                              </>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Empty State */}
            {entries.length === 0 && (
              <div className="text-center py-12 bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl mt-4">
                <Clock className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
                <h3 className="text-lg font-medium text-[hsl(var(--foreground))]">
                  Nenhum lancamento encontrado
                </h3>
                <p className="text-[hsl(var(--muted-foreground))] mt-1">
                  Ajuste os filtros ou registre um novo lancamento
                </p>
              </div>
            )}

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-6">
                <p className="text-sm text-[hsl(var(--muted-foreground))]">
                  Mostrando {(page - 1) * pageSize + 1} a {Math.min(page * pageSize, total)} de {total}
                </p>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage(p => p - 1)}
                    disabled={page <= 1}
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </Button>
                  <span className="text-sm text-[hsl(var(--foreground))]">
                    {page} de {totalPages}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage(p => p + 1)}
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

      {/* Approve Modal */}
      <Modal
        isOpen={showApproveModal}
        onClose={() => setShowApproveModal(false)}
        title="Aprovar Lancamento"
        description="Confirme a aprovação deste lancamento no banco de horas"
        size="sm"
      >
        {selectedEntry && (
          <div className="space-y-4">
            <div className="bg-[hsl(var(--muted))] rounded-lg p-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Funcionario</p>
                  <p className="text-sm font-medium text-[hsl(var(--foreground))]">
                    {selectedEntry.employee_name || 'N/A'}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Data</p>
                  <p className="text-sm font-medium text-[hsl(var(--foreground))]">
                    {formatDate(selectedEntry.reference_date)}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Tipo</p>
                  <p className="text-sm font-medium text-[hsl(var(--foreground))]">
                    {TIME_BANK_ENTRY_TYPE_LABELS[selectedEntry.entry_type]}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Horas</p>
                  <p className={`text-sm font-semibold ${selectedEntry.hours >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                    {formatHours(selectedEntry.hours)}
                  </p>
                </div>
              </div>
              {selectedEntry.description && (
                <div className="mt-3 pt-3 border-t border-[hsl(var(--border))]">
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Descricao</p>
                  <p className="text-sm text-[hsl(var(--foreground))]">{selectedEntry.description}</p>
                </div>
              )}
            </div>
          </div>
        )}

        <ModalFooter>
          <Button variant="outline" onClick={() => setShowApproveModal(false)} disabled={approving}>
            Cancelar
          </Button>
          <Button variant="primary" onClick={handleApprove} disabled={approving}>
            {approving ? (
              <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <Check className="w-4 h-4 mr-2" />
            )}
            Aprovar
          </Button>
        </ModalFooter>
      </Modal>

      {/* Reject Modal */}
      <Modal
        isOpen={showRejectModal}
        onClose={() => { setShowRejectModal(false); setRejectTarget(null); setRejectReason(''); }}
        title="Rejeitar Lancamento"
        description="Informe o motivo da rejeicao"
        size="sm"
      >
        <div className="space-y-3">
          <div>
            <p className="text-sm text-[hsl(var(--muted-foreground))]">
              {rejectTarget?.employee_name} — {formatHours(rejectTarget?.hours ?? 0)}
            </p>
          </div>
          <div>
            <label className="text-sm font-medium block mb-1">Motivo <span className="text-red-500">*</span></label>
            <textarea
              value={rejectReason}
              onChange={e => setRejectReason(e.target.value)}
              rows={3}
              className="w-full px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-sm resize-none focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]/20"
              placeholder="Descreva o motivo..."
            />
          </div>
        </div>
        <ModalFooter>
          <Button variant="outline" onClick={() => setShowRejectModal(false)} disabled={isRejecting}>Cancelar</Button>
          <Button
            onClick={handleConfirmReject}
            disabled={!rejectReason.trim() || isRejecting}
            className="bg-red-500 hover:bg-red-600 text-white border-red-500"
          >
            {isRejecting ? 'Rejeitando...' : 'Confirmar Rejeicao'}
          </Button>
        </ModalFooter>
      </Modal>
    </div>
  );
}
