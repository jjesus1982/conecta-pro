'use client';

import { LogIn, Search, RefreshCw, Clock, MapPin, Eye, AlertCircle, Users, ArrowLeft } from 'lucide-react';
import { useState, useMemo } from 'react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { PageHeader } from '@/components/ui/page-header';
import { StatCard } from '@/components/ui/stat-card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
;
import { CheckinDetailModal } from '@/components/campo/checkin-detail-modal';
import { useCampoDashboard } from '@/hooks/campo/useCampo';

export default function CheckinPage() {
  const { data: dashboardRaw, isLoading, isError, refetch } = useCampoDashboard();
  const dashboard = dashboardRaw as any;

  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [dateFilter, setDateFilter] = useState('');
  const [page, setPage] = useState(1);
  const [selectedCheckin, setSelectedCheckin] = useState<any>(null);
  const [detailOpen, setDetailOpen] = useState(false);

  const ITEMS_PER_PAGE = 10;

  // Extrair checkins do dashboard ou usar array vazio
  const rawCheckins: any[] = useMemo(() => dashboard?.checkins_list ?? dashboard?.registros ?? [], [dashboard?.checkins_list, dashboard?.registros]);

  // Filtros
  const filteredCheckins = useMemo(() => {
    let results = [...rawCheckins];

    if (search) {
      const term = search.toLowerCase();
      results = results.filter(
        (c) =>
          (c.colaborador || c.nome || '').toLowerCase().includes(term) ||
          (c.posto || c.local || '').toLowerCase().includes(term)
      );
    }

    if (statusFilter !== 'all') {
      results = results.filter((c) => c.status === statusFilter);
    }

    if (dateFilter) {
      results = results.filter((c) => {
        const checkinDate = (c.data_checkin || c.checkin_at || '').substring(0, 10);
        return checkinDate === dateFilter;
      });
    }

    return results;
  }, [rawCheckins, search, statusFilter, dateFilter]);

  // Paginacao
  const totalPages = Math.max(1, Math.ceil(filteredCheckins.length / ITEMS_PER_PAGE));
  const paginatedCheckins = filteredCheckins.slice(
    (page - 1) * ITEMS_PER_PAGE,
    page * ITEMS_PER_PAGE
  );

  // Stats
  const stats = {
    checkinsHoje: rawCheckins.filter((c) => c.status === 'ativo').length || dashboard?.checkins_hoje || 0,
    checkoutsHoje: rawCheckins.filter((c) => c.status === 'finalizado').length || 0,
    pendentes: rawCheckins.filter((c) => c.status === 'pendente').length || 0,
  };

  const formatDateTime = (date: string | null | undefined) => {
    if (!date) return '-';
    return new Date(date).toLocaleString('pt-BR');
  };

  const getStatusBadge = (status: string) => {
    const statusMap: Record<string, { label: string; className: string }> = {
      ativo: { label: 'Ativo', className: 'bg-green-100 text-green-800' },
      finalizado: { label: 'Finalizado', className: 'bg-blue-100 text-blue-800' },
      pendente: { label: 'Pendente', className: 'bg-yellow-100 text-yellow-800' },
    };
    const config = statusMap[status] || { label: status || '-', className: 'bg-gray-100 text-gray-800' };
    return <Badge className={config.className}>{config.label}</Badge>;
  };

  const handleViewDetail = (checkin: any) => {
    setSelectedCheckin(checkin);
    setDetailOpen(true);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-grid">
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <PageHeader
          eyebrow="CAMPO"
          title="Check-in / Check-out"
          subtitle="Registros de presenca em campo"
          icon={<LogIn className="w-5 h-5" />}
          actions={
            <>
              <Link href="/modulos/campo">
                <Button variant="ghost" size="sm">
                  <ArrowLeft className="w-4 h-4 mr-2" />
                  Campo
                </Button>
              </Link>
              <Button variant="outline" size="sm" onClick={() => refetch()}>
                <RefreshCw className="w-4 h-4 mr-2" />
                Atualizar
              </Button>
            </>
          }
        />

        {/* Error State */}
        {isError && (
          <div className="bg-destructive/10 border border-destructive/20 rounded-xl p-4 mb-6 flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-destructive flex-shrink-0" />
            <p className="text-destructive text-sm">Erro ao carregar dados de check-in. Tente novamente.</p>
          </div>
        )}

        {/* Stats Cards */}
        <div className="grid grid-cols-3 gap-4 mb-6">
          <StatCard
            icon={<LogIn className="w-4 h-4" />}
            color="#22c55e"
            label="Check-ins Hoje"
            value={stats.checkinsHoje}
          />
          <StatCard
            icon={<Clock className="w-4 h-4" />}
            color="#3b82f6"
            label="Check-outs"
            value={stats.checkoutsHoje}
          />
          <StatCard
            icon={<Users className="w-4 h-4" />}
            color="#eab308"
            label="Pendentes"
            value={stats.pendentes}
          />
        </div>

        {/* Filters */}
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4 mb-6">
          <div className="flex flex-wrap items-center gap-4">
            <div className="relative flex-1 min-w-[200px]">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[hsl(var(--muted-foreground))]" />
              <Input
                placeholder="Buscar por colaborador ou posto..."
                value={search}
                onChange={(e) => { setSearch(e.target.value); setPage(1); }}
                className="pl-9"
              />
            </div>
            <div className="w-[180px]">
              <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v); setPage(1); }}>
                <SelectTrigger>
                  <SelectValue placeholder="Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todos</SelectItem>
                  <SelectItem value="ativo">Ativo</SelectItem>
                  <SelectItem value="finalizado">Finalizado</SelectItem>
                  <SelectItem value="pendente">Pendente</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="w-[180px]">
              <Input
                type="date"
                value={dateFilter}
                onChange={(e) => { setDateFilter(e.target.value); setPage(1); }}
              />
            </div>
          </div>
        </div>

        {/* Table */}
        {paginatedCheckins.length > 0 ? (
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl overflow-hidden mb-6">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-[hsl(var(--border))] bg-[hsl(var(--muted))]/30">
                    <th className="text-left px-4 py-3 text-xs font-semibold text-[hsl(var(--muted-foreground))] uppercase">Colaborador</th>
                    <th className="text-left px-4 py-3 text-xs font-semibold text-[hsl(var(--muted-foreground))] uppercase">Posto</th>
                    <th className="text-left px-4 py-3 text-xs font-semibold text-[hsl(var(--muted-foreground))] uppercase">Check-in</th>
                    <th className="text-left px-4 py-3 text-xs font-semibold text-[hsl(var(--muted-foreground))] uppercase">Check-out</th>
                    <th className="text-center px-4 py-3 text-xs font-semibold text-[hsl(var(--muted-foreground))] uppercase">Status</th>
                    <th className="text-center px-4 py-3 text-xs font-semibold text-[hsl(var(--muted-foreground))] uppercase">Ações</th>
                  </tr>
                </thead>
                <tbody>
                  {paginatedCheckins.map((checkin, index) => (
                    <tr
                      key={checkin.id || index}
                      className={`border-b border-[hsl(var(--border))]/50 hover:bg-[hsl(var(--muted))]/20 transition-colors ${
                        index % 2 === 0 ? '' : 'bg-[hsl(var(--muted))]/10'
                      }`}
                    >
                      <td className="px-4 py-3 text-sm font-medium text-[hsl(var(--foreground))]">
                        {checkin.colaborador || checkin.nome || '-'}
                      </td>
                      <td className="px-4 py-3 text-sm text-[hsl(var(--muted-foreground))]">
                        <div className="flex items-center gap-1">
                          <MapPin className="w-3 h-3" />
                          {checkin.posto || checkin.local || '-'}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-sm text-[hsl(var(--foreground))]">
                        {formatDateTime(checkin.data_checkin || checkin.checkin_at)}
                      </td>
                      <td className="px-4 py-3 text-sm text-[hsl(var(--foreground))]">
                        {formatDateTime(checkin.data_checkout || checkin.checkout_at)}
                      </td>
                      <td className="px-4 py-3 text-center">
                        {getStatusBadge(checkin.status)}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleViewDetail(checkin)}
                        >
                          <Eye className="w-4 h-4" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between px-4 py-3 border-t border-[hsl(var(--border))]">
                <p className="text-sm text-[hsl(var(--muted-foreground))]">
                  Mostrando {(page - 1) * ITEMS_PER_PAGE + 1} a{' '}
                  {Math.min(page * ITEMS_PER_PAGE, filteredCheckins.length)} de{' '}
                  {filteredCheckins.length} registros
                </p>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page === 1}
                  >
                    Anterior
                  </Button>
                  <span className="text-sm text-[hsl(var(--foreground))]">
                    {page} / {totalPages}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    disabled={page === totalPages}
                  >
                    Proximo
                  </Button>
                </div>
              </div>
            )}
          </div>
        ) : (
          /* Empty State */
          <div className="text-center py-12 bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl">
            <LogIn className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
            <h3 className="text-lg font-medium text-[hsl(var(--foreground))]">
              Nenhum registro encontrado
            </h3>
            <p className="text-[hsl(var(--muted-foreground))] mt-1">
              {search || statusFilter !== 'all' || dateFilter
                ? 'Nenhum check-in corresponde aos filtros aplicados.'
                : 'Nenhum registro de check-in disponivel no momento.'}
            </p>
            {(search || statusFilter !== 'all' || dateFilter) && (
              <Button
                variant="outline"
                size="sm"
                className="mt-4"
                onClick={() => {
                  setSearch('');
                  setStatusFilter('all');
                  setDateFilter('');
                  setPage(1);
                }}
              >
                Limpar Filtros
              </Button>
            )}
          </div>
        )}
      </main>

      {/* Detail Modal */}
      <CheckinDetailModal
        isOpen={detailOpen}
        onClose={() => { setDetailOpen(false); setSelectedCheckin(null); }}
        checkin={selectedCheckin}
      />
    </div>
  );
}
