'use client';
import { Calendar, ArrowLeft, CheckCircle, Clock, User, RefreshCw, X, AlertTriangle, Plane, ExternalLink } from 'lucide-react';
import { useState, useMemo, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { PageHeader } from '@/components/ui/page-header';
import { useAuth } from '@/hooks/useAuth';
import api, { getErrorMessage } from '@/lib/api';

interface LeaveRequest {
  id: string;
  employeeId: string;
  employeeName: string;
  type: 'ferias' | 'afastamento' | 'licenca' | 'folga';
  startDate: string;
  endDate: string;
  reason: string;
  status: 'pendente' | 'aprovado' | 'rejeitado';
  createdAt: string;
}

const LEAVE_TYPE_LABELS: Record<LeaveRequest['type'], string> = {
  ferias: 'Férias',
  afastamento: 'Afastamento Médico',
  licenca: 'Licença',
  folga: 'Folga Compensatória',
};

const LEAVE_TYPE_COLORS: Record<LeaveRequest['type'], string> = {
  ferias: 'bg-blue-500/10 text-blue-500',
  afastamento: 'bg-orange-500/10 text-orange-500',
  licenca: 'bg-purple-500/10 text-purple-500',
  folga: 'bg-green-500/10 text-green-500',
};

const STATUS_COLORS: Record<LeaveRequest['status'], string> = {
  pendente: 'bg-yellow-500/10 text-yellow-500',
  aprovado: 'bg-green-500/10 text-green-500',
  rejeitado: 'bg-red-500/10 text-red-500',
};

export default function FeriasPage() {
  const router = useRouter();
  const { isAuthenticated, isLoading } = useAuth();

  const [requests, setRequests] = useState<LeaveRequest[]>([]);
  const [isFetching, setIsFetching] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);

  const [filterStatus, setFilterStatus] = useState<LeaveRequest['status'] | ''>('');
  const [filterType, setFilterType] = useState<LeaveRequest['type'] | ''>('');

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [isAuthenticated, isLoading, router]);

  const fetchLeaves = async () => {
    setIsFetching(true);
    setFetchError(null);
    try {
      const resp = await api.get('/api/v1/operacional/vacations');
      const data = resp.data;
      const mapped = (data.items || []).map((item: any) => ({
        id: item.id,
        employeeId: item.employee_id,
        employeeName: item.employee_name,
        type: item.leave_type as LeaveRequest['type'],
        startDate: item.start_date,
        endDate: item.end_date,
        reason: item.reason,
        status: item.status as LeaveRequest['status'],
        createdAt: item.created_at,
      }));
      setRequests(mapped);
    } catch (err) {
      setRequests([]);
      setFetchError(getErrorMessage(err));
    } finally {
      setIsFetching(false);
    }
  };

  useEffect(() => {
    if (isAuthenticated) {
      fetchLeaves();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated]);

  const filteredRequests = useMemo(() => requests.filter(r => {
    if (filterStatus && r.status !== filterStatus) return false;
    if (filterType && r.type !== filterType) return false;
    return true;
  }), [requests, filterStatus, filterType]);

  const stats = useMemo(() => ({
    total: requests.length,
    pendentes: requests.filter(r => r.status === 'pendente').length,
    aprovadas: requests.filter(r => r.status === 'aprovado').length,
    emFerias: requests.filter(r => {
      if (r.status !== 'aprovado') return false;
      const today = new Date().toISOString().split('T')[0] ?? '';
      return r.startDate <= today && r.endDate >= today;
    }).length,
  }), [requests]);

  const getDays = (start: string, end: string) => {
    const diff = new Date(end).getTime() - new Date(start).getTime();
    return Math.ceil(diff / (1000 * 60 * 60 * 24)) + 1;
  };

  const formatDate = (date: string) => {
    if (!date) return '—';
    const [year, month, day] = date.split('-');
    return `${day}/${month}/${year}`;
  };

  if (isLoading || (isFetching && requests.length === 0 && !fetchError)) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-6 h-6 animate-spin text-[hsl(var(--primary))]" />
      </div>
    );
  }

  return (
    <div className="p-4 md:p-6 space-y-6">
      {/* Header */}
      <PageHeader
        eyebrow="OPERACIONAL"
        title="Férias & Afastamentos"
        subtitle="Consulta de solicitações de ausência"
        icon={<Plane className="w-5 h-5" />}
        actions={
          <>
            <Link href="/modulos/operacional">
              <Button variant="ghost" size="icon" className="h-8 w-8">
                <ArrowLeft className="w-4 h-4" />
              </Button>
            </Link>
            <Button
              variant="outline"
              size="sm"
              onClick={fetchLeaves}
              disabled={isFetching}
              className="h-9"
            >
              <RefreshCw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} />
            </Button>
          </>
        }
      />

      {/* Aviso: gestão de férias é no módulo DP */}
      <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-blue-500/10 border border-blue-500/20">
        <AlertTriangle className="w-4 h-4 text-blue-500 flex-shrink-0" />
        <p className="text-sm text-blue-500">
          Esta tela é somente leitura. A gestão de férias (criar, aprovar e rejeitar) é feita no módulo DP.
        </p>
        <Link href="/modulos/dp/ferias" className="ml-auto flex-shrink-0">
          <Button variant="outline" size="sm" className="h-8 text-blue-500 border-blue-500/30">
            <ExternalLink className="w-3.5 h-3.5 mr-1.5" />
            Ir para DP → Férias
          </Button>
        </Link>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <Calendar className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />
            <span className="text-xs text-[hsl(var(--muted-foreground))]">Total</span>
          </div>
          <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">{stats.total}</p>
        </div>
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <Clock className="w-4 h-4 text-yellow-500" />
            <span className="text-xs text-[hsl(var(--muted-foreground))]">Pendentes</span>
          </div>
          <p className="font-data text-2xl font-semibold tabular-nums text-yellow-500">{stats.pendentes}</p>
        </div>
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <CheckCircle className="w-4 h-4 text-green-500" />
            <span className="text-xs text-[hsl(var(--muted-foreground))]">Aprovadas</span>
          </div>
          <p className="font-data text-2xl font-semibold tabular-nums text-green-500">{stats.aprovadas}</p>
        </div>
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <Plane className="w-4 h-4 text-blue-500" />
            <span className="text-xs text-[hsl(var(--muted-foreground))]">Em Férias Hoje</span>
          </div>
          <p className="font-data text-2xl font-semibold tabular-nums text-blue-500">{stats.emFerias}</p>
        </div>
      </div>

      {/* Filtros */}
      <div className="flex flex-wrap gap-3">
        <select
          value={filterStatus}
          onChange={e => setFilterStatus(e.target.value as LeaveRequest['status'] | '')}
          className="h-9 rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 text-sm text-[hsl(var(--foreground))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]"
        >
          <option value="">Todos os status</option>
          <option value="pendente">Pendente</option>
          <option value="aprovado">Aprovado</option>
          <option value="rejeitado">Rejeitado</option>
        </select>
        <select
          value={filterType}
          onChange={e => setFilterType(e.target.value as LeaveRequest['type'] | '')}
          className="h-9 rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 text-sm text-[hsl(var(--foreground))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]"
        >
          <option value="">Todos os tipos</option>
          <option value="ferias">Férias</option>
          <option value="afastamento">Afastamento Médico</option>
          <option value="licenca">Licença</option>
          <option value="folga">Folga Compensatória</option>
        </select>
        {(filterStatus || filterType) && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => { setFilterStatus(''); setFilterType(''); }}
            className="h-9 text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))]"
          >
            <X className="w-3 h-3 mr-1" />
            Limpar
          </Button>
        )}
      </div>

      {/* Erro de carregamento */}
      {fetchError && (
        <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/20">
          <AlertTriangle className="w-4 h-4 text-red-500 flex-shrink-0" />
          <p className="text-sm text-red-500">Erro ao carregar solicitações: {fetchError}</p>
          <Button
            variant="outline"
            size="sm"
            onClick={fetchLeaves}
            disabled={isFetching}
            className="ml-auto h-8 text-red-500 border-red-500/30"
          >
            Tentar novamente
          </Button>
        </div>
      )}

      {/* Tabela */}
      {!fetchError && (
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl overflow-hidden">
          {filteredRequests.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-[hsl(var(--muted-foreground))]">
              <Plane className="w-10 h-10 mb-3 opacity-30" />
              <p className="text-sm font-medium">
                {requests.length === 0
                  ? 'Nenhuma solicitação de férias registrada'
                  : 'Nenhuma solicitação encontrada com os filtros atuais'}
              </p>
              <p className="text-xs mt-1">
                {requests.length === 0
                  ? 'As solicitações são geridas no módulo DP → Férias'
                  : 'Ajuste os filtros para ver outras solicitações'}
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-[hsl(var(--border))]">
                    <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wider">
                      Colaborador
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wider hidden md:table-cell">
                      Tipo
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wider hidden sm:table-cell">
                      Período
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wider hidden lg:table-cell">
                      Dias
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wider hidden xl:table-cell">
                      Motivo
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wider">
                      Status
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[hsl(var(--border))]">
                  {filteredRequests.map(req => (
                    <tr key={req.id} className="hover:bg-[hsl(var(--muted))]/30 transition-colors">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div className="w-7 h-7 rounded-full bg-[hsl(var(--primary))]/10 flex items-center justify-center flex-shrink-0">
                            <User className="w-3.5 h-3.5 text-[hsl(var(--primary))]" />
                          </div>
                          <span className="text-sm font-medium text-[hsl(var(--foreground))] truncate max-w-[160px]">
                            {req.employeeName || 'Colaborador não identificado'}
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3 hidden md:table-cell">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${LEAVE_TYPE_COLORS[req.type] || 'bg-gray-500/10 text-gray-500'}`}>
                          {LEAVE_TYPE_LABELS[req.type] || req.type}
                        </span>
                      </td>
                      <td className="px-4 py-3 hidden sm:table-cell">
                        <span className="text-sm text-[hsl(var(--foreground))]">
                          {formatDate(req.startDate)} — {formatDate(req.endDate)}
                        </span>
                      </td>
                      <td className="px-4 py-3 hidden lg:table-cell">
                        <span className="text-sm font-medium text-[hsl(var(--foreground))]">
                          {req.startDate && req.endDate ? `${getDays(req.startDate, req.endDate)}d` : '—'}
                        </span>
                      </td>
                      <td className="px-4 py-3 hidden xl:table-cell">
                        <span className="text-sm text-[hsl(var(--muted-foreground))] truncate max-w-[180px] block">
                          {req.reason || '—'}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium capitalize ${STATUS_COLORS[req.status] || 'bg-gray-500/10 text-gray-500'}`}>
                          {req.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
