'use client';

import { UserX, Search, Plus, Eye, Check, X, ArrowLeft, ChevronLeft, ChevronRight, RefreshCw, Clock, AlertTriangle, CheckCircle, XCircle, Calendar, User, MapPin, Sparkles, ArrowRight, DollarSign } from 'lucide-react';
import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { PageHeader } from '@/components/ui/page-header';
import { Input } from '@/components/ui/input';
import { Modal, ModalFooter } from '@/components/ui/modal';
import { useAuth } from '@/hooks/useAuth';
import {
  useSubstitutions,
  usePendingSubstitutions,
  useSuggestSubstitutes,
  useConfirmSubstitution,
  useRejectSubstitution,
} from '@/hooks/operacional/useSubstitutions';
import {
  type SubstitutionStatus,
  type SubstitutionReason,
  SUBSTITUTION_STATUS_LABELS,
  SUBSTITUTION_REASON_LABELS,
  SUBSTITUTION_STATUS_COLORS,
  SUBSTITUTION_REASON_COLORS,
} from '@/lib/services/substitutions';
import type {
  SubstitutionResponse,
  SubstituteSuggestion,
} from '@/types/generated/operacional/conectaPROMóduloOPERACIONAL.schemas';

/** Extensão do SubstitutionResponse com campos denormalizados retornados pelo backend */
interface SubstitutionWithDenormalized extends SubstitutionResponse {
  original_employee_name?: string;
  substitute_employee_name?: string;
  post_name?: string;
  shift_date?: string;
  shift_time?: string;
}

export default function SubstituicoesPage() {
  const router = useRouter();
  const { isLoading: authLoading, isAuthenticated } = useAuth();

  const { data: substitutionsData, isLoading, error, refetch } = useSubstitutions();
  const substitutions = (substitutionsData?.items ?? []) as SubstitutionWithDenormalized[];
  const { data: pendingSubstitutions = [] } = usePendingSubstitutions();
  const suggestMutation = useSuggestSubstitutes();
  const confirmMutation = useConfirmSubstitution();
  const rejectMutation = useRejectSubstitution();
  const total = substitutions.length;
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const totalPages = Math.ceil(total / pageSize);

  const [searchTerm, setSearchTerm] = useState('');
  const [debouncedSearchTerm, setDebouncedSearchTerm] = useState('');
  const [selectedStatus, setSelectedStatus] = useState<SubstitutionStatus | ''>('');
  const [selectedReason, setSelectedReason] = useState<SubstitutionReason | ''>('');
  const [selectedDate, setSelectedDate] = useState('');

  // Modal states
  const [showSuggestionsModal, setShowSuggestionsModal] = useState(false);
  const [selectedSubstitution, setSelectedSubstitution] = useState<SubstitutionWithDenormalized | null>(null);
  const [suggestions, setSuggestions] = useState<SubstituteSuggestion[]>([]);
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);

  // Rejection modal states
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [rejectTarget, setRejectTarget] = useState<SubstitutionWithDenormalized | null>(null);
  const [rejectReason, setRejectReason] = useState('');
  const [isRejecting, setIsRejecting] = useState(false);

  const loadPending = useCallback(() => {
    // Dados pendentes agora vêm do hook usePendingSubstitutions
  }, []);

  // Debounce search
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearchTerm(searchTerm);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchTerm]);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [authLoading, isAuthenticated, router]);

  useEffect(() => {
    if (isAuthenticated) {
      refetch();
      loadPending();
    }
  }, [isAuthenticated, refetch, loadPending]);

  const handleGetSuggestions = async (substitution: SubstitutionWithDenormalized) => {
    setSelectedSubstitution(substitution);
    setShowSuggestionsModal(true);
    setLoadingSuggestions(true);

    try {
      const result = await suggestMutation.mutateAsync({
        data: {
          shift_id: substitution.shift_id,
          max_suggestions: 5,
          prefer_same_post: true,
          consider_distance: true,
        },
      });
      setSuggestions(result ?? []);
    } catch {
      setSuggestions([]);
    } finally {
      setLoadingSuggestions(false);
    }
  };

  const handleConfirm = async (substitution: SubstitutionWithDenormalized, employeeId: string) => {
    try {
      await confirmMutation.mutateAsync({
        substitutionId: substitution.id,
        data: { substitute_employee_id: employeeId },
      });
      setShowSuggestionsModal(false);
      refetch();
    } catch {
      // silenced
    }
  };

  const handleReject = (substitution: SubstitutionWithDenormalized) => {
    setRejectTarget(substitution);
    setRejectReason('');
    setShowRejectModal(true);
  };

  const handleConfirmReject = async () => {
    if (!rejectTarget || !rejectReason.trim()) return;
    setIsRejecting(true);
    try {
      await rejectMutation.mutateAsync({
        substitutionId: rejectTarget.id,
        data: { rejection_reason: rejectReason.trim() },
      });
      setShowRejectModal(false);
      setRejectTarget(null);
      setRejectReason('');
      refetch();
    } catch {
      // silenced
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

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL',
    }).format(value);
  };

  const getStatusIcon = (status: SubstitutionStatus) => {
    switch (status) {
      case 'pendente':
        return <Clock className="w-4 h-4" />;
      case 'confirmada':
        return <CheckCircle className="w-4 h-4" />;
      case 'em_andamento':
        return <RefreshCw className="w-4 h-4" />;
      case 'concluida':
        return <Check className="w-4 h-4" />;
      case 'cancelada':
        return <X className="w-4 h-4" />;
      case 'rejeitada':
        return <XCircle className="w-4 h-4" />;
      default:
        return <AlertTriangle className="w-4 h-4" />;
    }
  };

  // Filtrar substituições localmente
  const filteredSubstitutions = substitutions.filter((sub) => {
    // Filtro de busca
    if (debouncedSearchTerm) {
      const searchLower = debouncedSearchTerm.toLowerCase();
      const matchesSearch =
        sub.original_employee_name?.toLowerCase().includes(searchLower) ||
        sub.substitute_employee_name?.toLowerCase().includes(searchLower) ||
        sub.post_name?.toLowerCase().includes(searchLower);
      if (!matchesSearch) return false;
    }
    // Filtro de status
    if (selectedStatus && sub.status !== selectedStatus) return false;
    // Filtro de motivo
    if (selectedReason && sub.reason !== selectedReason) return false;
    // Filtro de data
    if (selectedDate) {
      const subDate = new Date(sub.shift_date ?? sub.substitution_date).toISOString().split('T')[0];
      if (subDate !== selectedDate) return false;
    }
    return true;
  });

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))]">
        <div className="animate-pulse-slow text-[hsl(var(--primary))]">
          <UserX className="w-12 h-12" />
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
          title="Substituicoes"
          subtitle={`${total} registradas | ${pendingSubstitutions.length} pendentes`}
          icon={<UserX className="w-5 h-5" />}
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
                Nova Substituicao
              </Button>
            </>
          }
        />

        {/* Pending Alert */}
        {pendingSubstitutions.length > 0 && (
          <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-xl p-4 mb-6">
            <div className="flex items-center gap-3">
              <AlertTriangle className="w-5 h-5 text-yellow-500 flex-shrink-0" />
              <div className="flex-1">
                <p className="font-medium text-yellow-500">
                  {pendingSubstitutions.length} substituicoes pendentes
                </p>
                <p className="text-sm text-yellow-500/80">
                  {pendingSubstitutions.slice(0, 3).map((s: any) => s.original_employee_name || 'N/A').join(', ')}
                  {pendingSubstitutions.length > 3 ? ` e mais ${pendingSubstitutions.length - 3}` : ''}
                  {' '}— Clique em &quot;Sugerir IA&quot; para obter recomendacoes
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Stats */}
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-4 mb-6">
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
                <UserX className="w-5 h-5 text-blue-500" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">{total}</p>
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
                  {pendingSubstitutions.length}
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
                  {substitutions.filter(s => s.status === 'concluida').length}
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Concluidas</p>
              </div>
            </div>
          </div>

          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-red-500/10 flex items-center justify-center">
                <XCircle className="w-5 h-5 text-red-500" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                  {substitutions.filter(s => s.reason === 'falta').length}
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Por Falta</p>
              </div>
            </div>
          </div>

          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-purple-500/10 flex items-center justify-center">
                <DollarSign className="w-5 h-5 text-purple-500" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                  {formatCurrency(substitutions.reduce((acc, s) => acc + s.additional_cost, 0))}
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Custo Adicional</p>
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
                placeholder="Buscar por funcionario, posto..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-10"
              />
            </div>
            <div className="flex flex-wrap gap-2">
              <select
                value={selectedStatus}
                onChange={(e) => setSelectedStatus(e.target.value as SubstitutionStatus | '')}
                className="px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))] text-sm"
              >
                <option value="">Todos os Status</option>
                {Object.entries(SUBSTITUTION_STATUS_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
              <select
                value={selectedReason}
                onChange={(e) => setSelectedReason(e.target.value as SubstitutionReason | '')}
                className="px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))] text-sm"
              >
                <option value="">Todos os Motivos</option>
                {Object.entries(SUBSTITUTION_REASON_LABELS).map(([value, label]) => (
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
            <p className="text-red-500">{error.detail?.[0]?.msg ?? 'Erro ao carregar substituições'}</p>
            <Button variant="outline" size="sm" onClick={() => refetch()} className="ml-auto">
              Tentar novamente
            </Button>
          </div>
        )}

        {/* Loading */}
        {isLoading && (
          <div className="flex items-center justify-center py-12">
            <div className="animate-pulse-slow text-[hsl(var(--primary))]">
              <UserX className="w-8 h-8" />
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
                        Funcionario Original
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                        Substituto
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                        Motivo
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                        Status
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                        Custo
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                        Ações
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[hsl(var(--border))]">
                    {filteredSubstitutions.map((sub) => (
                      <tr
                        key={sub.id}
                        className="hover:bg-[hsl(var(--muted))]/50 transition-colors"
                      >
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <Calendar className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />
                            <span className="text-sm text-[hsl(var(--foreground))]">
                              {formatDate(sub.substitution_date)}
                            </span>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <div className="w-8 h-8 rounded-full bg-red-500/10 flex items-center justify-center">
                              <User className="w-4 h-4 text-red-500" />
                            </div>
                            <div>
                              <p className="text-sm font-medium text-[hsl(var(--foreground))]">
                                {sub.original_employee_name || 'N/A'}
                              </p>
                              <p className="text-xs text-[hsl(var(--muted-foreground))]">
                                {sub.post_name || 'Posto N/A'}
                              </p>
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          {sub.substitute_employee_id ? (
                            <div className="flex items-center gap-2">
                              <div className="w-8 h-8 rounded-full bg-green-500/10 flex items-center justify-center">
                                <User className="w-4 h-4 text-green-500" />
                              </div>
                              <span className="text-sm text-[hsl(var(--foreground))]">
                                {sub.substitute_employee_name || 'Definido'}
                              </span>
                            </div>
                          ) : (
                            <span className="text-sm text-[hsl(var(--muted-foreground))] italic">
                              Nao definido
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${SUBSTITUTION_REASON_COLORS[sub.reason as SubstitutionReason]}`}>
                            {SUBSTITUTION_REASON_LABELS[sub.reason as SubstitutionReason]}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${SUBSTITUTION_STATUS_COLORS[sub.status as SubstitutionStatus]}`}>
                            {getStatusIcon(sub.status as SubstitutionStatus)}
                            {SUBSTITUTION_STATUS_LABELS[sub.status as SubstitutionStatus]}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span className="text-sm text-[hsl(var(--foreground))]">
                            {sub.additional_cost > 0 ? formatCurrency(sub.additional_cost) : '-'}
                          </span>
                          {sub.is_overtime && (
                            <span className="ml-1 text-xs text-orange-500">(HE)</span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center justify-end gap-1">
                            <Button variant="ghost" size="sm" title="Ver Detalhes">
                              <Eye className="w-4 h-4" />
                            </Button>
                            {sub.status === 'pendente' && (
                              <>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleGetSuggestions(sub)}
                                  title="Sugerir Substituto (IA)"
                                  className="text-purple-500 hover:text-purple-600"
                                >
                                  <Sparkles className="w-4 h-4" />
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleReject(sub)}
                                  title="Rejeitar"
                                  className="text-red-500 hover:text-red-600"
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
            {substitutions.length === 0 && (
              <div className="text-center py-12 bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl mt-4">
                <UserX className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
                <h3 className="text-lg font-medium text-[hsl(var(--foreground))]">
                  Nenhuma substituicao encontrada
                </h3>
                <p className="text-[hsl(var(--muted-foreground))] mt-1">
                  Ajuste os filtros ou registre uma nova substituicao
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

      {/* Suggestions Modal */}
      <Modal
        isOpen={showSuggestionsModal}
        onClose={() => setShowSuggestionsModal(false)}
        title="Sugestoes de Substitutos (IA)"
        description="Substitutos recomendados baseados em disponibilidade, distancia e historico"
        size="lg"
      >
        {loadingSuggestions ? (
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin text-[hsl(var(--primary))]">
              <Sparkles className="w-8 h-8" />
            </div>
          </div>
        ) : suggestions.length > 0 ? (
          <div className="space-y-3">
            {suggestions.map((suggestion, index) => (
              <div
                key={suggestion.employee_id}
                className="flex items-center justify-between p-4 rounded-lg border border-[hsl(var(--border))] hover:border-[hsl(var(--primary))]/50 transition-colors"
              >
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 rounded-full bg-gradient-to-br from-purple-500 to-blue-600 flex items-center justify-center text-white font-semibold">
                    {index + 1}
                  </div>
                  <div>
                    <p className="font-medium text-[hsl(var(--foreground))]">
                      {suggestion.employee_name}
                    </p>
                    <div className="flex items-center gap-2 mt-1">
                      <span className={`text-xs ${suggestion.is_overtime ? 'text-orange-500' : 'text-green-500'}`}>
                        {suggestion.is_overtime ? 'Hora Extra' : 'Horario Normal'}
                      </span>
                      {suggestion.distance_km && (
                        <span className="text-xs text-[hsl(var(--muted-foreground))]">
                          {suggestion.distance_km.toFixed(1)} km
                        </span>
                      )}
                    </div>
                    {/* Score bar */}
                    <div className="mt-2 flex items-center gap-2">
                      <div className="flex-1 h-1.5 bg-[hsl(var(--muted))] rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all"
                          style={{
                            width: `${Math.min(suggestion.score, 100)}%`,
                            background: suggestion.score >= 70
                              ? '#22c55e'
                              : suggestion.score >= 40
                              ? '#f97707'
                              : '#ef4444',
                          }}
                        />
                      </div>
                      <span className="text-xs text-[hsl(var(--muted-foreground))] w-10 text-right">
                        {suggestion.score.toFixed(0)}pts
                      </span>
                    </div>
                    <p className="text-xs text-[hsl(var(--muted-foreground))] mt-1">
                      {suggestion.reasons.join(' • ')}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <div className="text-right">
                    <p className="text-sm font-medium text-[hsl(var(--foreground))]">
                      {formatCurrency(suggestion.estimated_cost)}
                    </p>
                    <p className="text-xs text-[hsl(var(--muted-foreground))]">
                      Custo estimado
                    </p>
                  </div>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => selectedSubstitution && handleConfirm(selectedSubstitution, suggestion.employee_id)}
                  >
                    <Check className="w-4 h-4 mr-1" />
                    Selecionar
                  </Button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-8">
            <XCircle className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
            <p className="text-[hsl(var(--foreground))]">Nenhum substituto disponivel</p>
            <p className="text-sm text-[hsl(var(--muted-foreground))] mt-1">
              Tente ajustar os criterios ou buscar manualmente
            </p>
          </div>
        )}

        <ModalFooter>
          <Button variant="outline" onClick={() => setShowSuggestionsModal(false)}>
            Fechar
          </Button>
        </ModalFooter>
      </Modal>

      {/* Rejection Modal */}
      <Modal
        isOpen={showRejectModal}
        onClose={() => {
          setShowRejectModal(false);
          setRejectTarget(null);
          setRejectReason('');
        }}
        title="Rejeitar Substituição"
        description="Informe o motivo da rejeição para registrar no histórico"
        size="md"
      >
        <div className="space-y-4">
          <div>
            <label className="text-sm font-medium text-[hsl(var(--foreground))] block mb-1">
              Funcionário original
            </label>
            <p className="text-sm text-[hsl(var(--muted-foreground))]">
              {rejectTarget?.original_employee_name || 'N/A'} — {rejectTarget?.post_name || 'Posto N/A'}
            </p>
          </div>
          <div>
            <label className="text-sm font-medium text-[hsl(var(--foreground))] block mb-1">
              Motivo da rejeição <span className="text-red-500">*</span>
            </label>
            <textarea
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="Descreva o motivo da rejeição..."
              rows={3}
              className="w-full px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))] text-sm resize-none focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]/20"
            />
          </div>
        </div>
        <ModalFooter>
          <Button
            variant="outline"
            onClick={() => {
              setShowRejectModal(false);
              setRejectTarget(null);
              setRejectReason('');
            }}
            disabled={isRejecting}
          >
            Cancelar
          </Button>
          <Button
            variant="primary"
            onClick={handleConfirmReject}
            disabled={!rejectReason.trim() || isRejecting}
            className="bg-red-500 hover:bg-red-600 text-white border-red-500"
          >
            {isRejecting ? 'Rejeitando...' : 'Confirmar Rejeição'}
          </Button>
        </ModalFooter>
      </Modal>
    </div>
  );
}
