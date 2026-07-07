'use client';

import { CheckCircle2, Search, RefreshCw, Plus, MoreHorizontal, Eye, XCircle, AlertCircle, ChevronLeft, ChevronRight, Clock, ShieldOff } from 'lucide-react';
import { useState, useEffect, useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { ConfirmModal } from '@/components/ui/modal';
;
import { useConsents, useRegisterConsent, useRevokeConsent } from '@/hooks/security-lgpd';
import { ConsentFormModal } from '@/components/seguranca/consent-form-modal';
import { ConsentDetailModal } from '@/components/seguranca/consent-detail-modal';

const PAGE_SIZE = 20;

/** Shape dos dados internos retornados em StandardResponse.data para consents */
interface ConsentsData {
  consents?: unknown[];
  [key: string]: unknown;
}

// Labels de finalidade
const PURPOSE_LABELS: Record<string, string> = {
  marketing: 'Marketing e Publicidade',
  analytics: 'Analise e Estatisticas',
  data_sharing: 'Compartilhamento de Dados',
  profiling: 'Perfilamento',
  service_provision: 'Prestacao de Servicos',
  communication: 'Comunicacao',
};

// Labels de base legal
const LEGAL_BASIS_LABELS: Record<string, string> = {
  consent: 'Consentimento do Titular',
  legitimate_interest: 'Interesse Legitimo',
  contract: 'Execucao de Contrato',
  legal_obligation: 'Obrigacao Legal',
};

// Cores de status
const STATUS_BADGE_COLORS: Record<string, string> = {
  active: 'bg-green-500/10 text-green-500 border-green-500/20',
  revoked: 'bg-red-500/10 text-red-500 border-red-500/20',
  expired: 'bg-gray-500/10 text-gray-500 border-gray-500/20',
};

const STATUS_LABELS: Record<string, string> = {
  active: 'Ativo',
  revoked: 'Revogado',
  expired: 'Expirado',
};

;

export default function ConsentimentoPage() {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedStatus, setSelectedStatus] = useState<string>('all');
  const [page, setPage] = useState(1);

  // Modal states
  const [showFormModal, setShowFormModal] = useState(false);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [showRevokeModal, setShowRevokeModal] = useState(false);
  const [selectedConsent, setSelectedConsent] = useState<any>(null);
  const [isRevoking, setIsRevoking] = useState(false);

  // Hooks de dados - usando titular generico para listar todos
  const { data: consentsResponse, isLoading, refetch } = useConsents('all', true);
  const registerConsent = useRegisterConsent();
  const revokeConsent = useRevokeConsent();

  // Extrair dados - cast data para shape esperado
  const responseData = consentsResponse?.data as ConsentsData | undefined;
  const allConsents = useMemo(() => {
    const rawConsents = responseData?.consents || (Array.isArray(responseData) ? responseData : []);
    return Array.isArray(rawConsents) ? rawConsents : [];
  }, [responseData]);

  // Filtrar localmente
  const filteredConsents = useMemo(() => {
    let result = [...allConsents];

    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      result = result.filter(
        (c: any) =>
          (c.holder_name || '').toLowerCase().includes(term) ||
          (c.purpose || '').toLowerCase().includes(term) ||
          (c.legal_basis || '').toLowerCase().includes(term)
      );
    }

    if (selectedStatus && selectedStatus !== 'all') {
      result = result.filter((c: any) => c.status === selectedStatus);
    }

    return result;
  }, [allConsents, searchTerm, selectedStatus]);

  // Paginacao
  const total = filteredConsents.length;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const paginatedConsents = filteredConsents.slice(
    (page - 1) * PAGE_SIZE,
    page * PAGE_SIZE
  );

  // Stats
  const stats = useMemo(() => {
    const activeCount = allConsents.filter((c: any) => c.status === 'active').length;
    const revokedCount = allConsents.filter((c: any) => c.status === 'revoked').length;

    const now = new Date();
    const thirtyDays = 30 * 24 * 60 * 60 * 1000;
    const expiringCount = allConsents.filter((c: any) => {
      if (c.status !== 'active' || !c.valid_until) return false;
      const validUntil = new Date(c.valid_until);
      return validUntil.getTime() - now.getTime() <= thirtyDays && validUntil > now;
    }).length;

    return { activeCount, revokedCount, expiringCount };
  }, [allConsents]);

  // Reset pagina ao alterar filtros
  useEffect(() => {
    setPage(1);
  }, [searchTerm, selectedStatus]);

  const handleRefresh = () => {
    refetch();
  };

  const handleView = (consent: any) => {
    setSelectedConsent(consent);
    setShowDetailModal(true);
  };

  const handleRevokeClick = (consent: any) => {
    setSelectedConsent(consent);
    setShowRevokeModal(true);
  };

  const handleRevokeConfirm = async () => {
    if (!selectedConsent) return;

    setIsRevoking(true);
    try {
      await revokeConsent.mutateAsync({
        consentId: selectedConsent.id,
        reason: 'Revogado pelo administrador via painel LGPD',
      });
      setShowRevokeModal(false);
      setSelectedConsent(null);
      handleRefresh();
    } catch (error) {
    } finally {
      setIsRevoking(false);
    }
  };

  const handleFormSubmit = async (formData: any) => {
    try {
      await registerConsent.mutateAsync(formData);
      setShowFormModal(false);
      handleRefresh();
    } catch (error) {
    }
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    });
  };

  const getStatusBadge = (status: string) => {
    const colorClass = STATUS_BADGE_COLORS[status] || 'bg-gray-500/10 text-gray-500 border-gray-500/20';
    const label = STATUS_LABELS[status] || status;
    return (
      <span
        className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium border ${colorClass}`}
      >
        {label}
      </span>
    );
  };

  return (
    <div className="min-h-screen bg-grid">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-[hsl(var(--background))]/80 backdrop-blur-xl border-b border-[hsl(var(--border))]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-green-500/10 flex items-center justify-center">
                <CheckCircle2 className="w-5 h-5 text-green-500" />
              </div>
              <div>
                <h1 className="text-lg font-semibold text-[hsl(var(--foreground))]">
                  Consentimento
                </h1>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">
                  Gestao de consentimentos LGPD
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="outline" onClick={handleRefresh} disabled={isLoading}>
                <RefreshCw className={`w-4 h-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
                Atualizar
              </Button>
              <Button variant="primary" onClick={() => setShowFormModal(true)}>
                <Plus className="w-4 h-4 mr-2" />
                Registrar Consentimento
              </Button>
            </div>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-green-500/10 flex items-center justify-center">
                <CheckCircle2 className="w-5 h-5 text-green-500" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                  {stats.activeCount}
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Ativos</p>
              </div>
            </div>
          </div>

          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-red-500/10 flex items-center justify-center">
                <ShieldOff className="w-5 h-5 text-red-500" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                  {stats.revokedCount}
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Revogados</p>
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
                  {stats.expiringCount}
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Expirando</p>
              </div>
            </div>
          </div>
        </div>

        {/* Filters */}
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4 mb-6">
          <div className="flex flex-col lg:flex-row gap-4">
            {/* Search */}
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[hsl(var(--muted-foreground))]" />
              <Input
                placeholder="Buscar por titular, finalidade, base legal..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-10"
              />
            </div>

            {/* Status filter */}
            <div className="w-full lg:w-48">
              <Select value={selectedStatus} onValueChange={setSelectedStatus} aria-label="Selected Status">
                <SelectTrigger>
                  <SelectValue placeholder="Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todos os Status</SelectItem>
                  <SelectItem value="active">Ativo</SelectItem>
                  <SelectItem value="revoked">Revogado</SelectItem>
                  <SelectItem value="expired">Expirado</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {(selectedStatus !== 'all' || searchTerm) && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setSearchTerm('');
                  setSelectedStatus('all');
                }}
              >
                Limpar filtros
              </Button>
            )}
          </div>
        </div>

        {/* Loading state */}
        {isLoading && (
          <div className="flex items-center justify-center py-12">
            <div className="animate-pulse-slow text-[hsl(var(--primary))]">
              <CheckCircle2 className="w-8 h-8" />
            </div>
          </div>
        )}

        {/* Table */}
        {!isLoading && (
          <>
            <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-[hsl(var(--border))] bg-[hsl(var(--muted))]">
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                        Titular
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                        Finalidade
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                        Base Legal
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                        Status
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                        Validade
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                        Ações
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[hsl(var(--border))]">
                    {paginatedConsents.map((consent: any) => (
                      <tr
                        key={consent.id}
                        className="hover:bg-[hsl(var(--muted))]/50 transition-colors"
                      >
                        <td className="px-4 py-3">
                          <span className="text-sm font-medium text-[hsl(var(--foreground))]">
                            {consent.holder_name || '-'}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span className="text-sm text-[hsl(var(--foreground))]">
                            {PURPOSE_LABELS[consent.purpose] || consent.purpose || '-'}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span className="text-sm text-[hsl(var(--muted-foreground))]">
                            {LEGAL_BASIS_LABELS[consent.legal_basis] || consent.legal_basis || '-'}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          {getStatusBadge(consent.status)}
                        </td>
                        <td className="px-4 py-3">
                          <span className="text-sm text-[hsl(var(--foreground))]">
                            {formatDate(consent.valid_until)}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center justify-end">
                            <DropdownMenu>
                              <DropdownMenuTrigger asChild>
                                <Button variant="ghost" size="sm">
                                  <MoreHorizontal className="w-4 h-4" />
                                </Button>
                              </DropdownMenuTrigger>
                              <DropdownMenuContent align="end">
                                <DropdownMenuItem onClick={() => handleView(consent)}>
                                  <Eye className="w-4 h-4 mr-2" />
                                  Ver detalhes
                                </DropdownMenuItem>
                                {consent.status === 'active' && (
                                  <>
                                    <DropdownMenuSeparator />
                                    <DropdownMenuItem
                                      onClick={() => handleRevokeClick(consent)}
                                      className="text-red-500 focus:text-red-500"
                                    >
                                      <XCircle className="w-4 h-4 mr-2" />
                                      Revogar
                                    </DropdownMenuItem>
                                  </>
                                )}
                              </DropdownMenuContent>
                            </DropdownMenu>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Empty state */}
            {paginatedConsents.length === 0 && (
              <div className="text-center py-12 bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl mt-4">
                <CheckCircle2 className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
                <h3 className="text-lg font-medium text-[hsl(var(--foreground))]">
                  Nenhum consentimento encontrado
                </h3>
                <p className="text-[hsl(var(--muted-foreground))] mt-1">
                  Ajuste os filtros ou registre um novo consentimento
                </p>
                <Button variant="primary" className="mt-4" onClick={() => setShowFormModal(true)}>
                  <Plus className="w-4 h-4 mr-2" />
                  Registrar Consentimento
                </Button>
              </div>
            )}

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-4">
                <p className="text-sm text-[hsl(var(--muted-foreground))]">
                  Mostrando {(page - 1) * PAGE_SIZE + 1} a{' '}
                  {Math.min(page * PAGE_SIZE, total)} de {total} registros
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
      <ConsentFormModal
        isOpen={showFormModal}
        onClose={() => setShowFormModal(false)}
        onSubmit={handleFormSubmit}
        isLoading={registerConsent.isPending}
      />

      {/* Detail Modal */}
      <ConsentDetailModal
        isOpen={showDetailModal}
        onClose={() => {
          setShowDetailModal(false);
          setSelectedConsent(null);
        }}
        consent={selectedConsent}
      />

      {/* Revoke Confirm Modal */}
      <ConfirmModal
        isOpen={showRevokeModal}
        onClose={() => {
          setShowRevokeModal(false);
          setSelectedConsent(null);
        }}
        onConfirm={handleRevokeConfirm}
        title="Revogar Consentimento"
        message={`Tem certeza que deseja revogar o consentimento de "${selectedConsent?.holder_name || ''}"? O titular sera notificado sobre a revogacao conforme Art. 8 da LGPD.`}
        confirmText="Revogar"
        isLoading={isRevoking}
        variant="danger"
      />
    </div>
  );
}
