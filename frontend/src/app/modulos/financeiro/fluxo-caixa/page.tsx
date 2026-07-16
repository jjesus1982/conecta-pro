'use client';

import { Activity, Search, RefreshCw, Plus, TrendingUp, TrendingDown, DollarSign, AlertCircle, ArrowLeft, ChevronLeft, ChevronRight, Brain, AlertTriangle, Lightbulb } from 'lucide-react';
import { useState, useEffect, useRef } from 'react';
import Link from 'next/link';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useCondominio } from '@/contexts/CondominioContext';
import { useCashflowEntries, useCashflowDashboard, useCreateCashflowEntry, useCashflowProjection } from '@/hooks/financial/useFinancial';
import type { CashFlowEntryResponse } from '@/types/generated/financial/models/cashFlowEntryResponse';
import { CashflowFormModal } from '@/components/financeiro/cashflow-form-modal';
import type { CashFlowEntryCreate } from '@/types/generated/financial/models/cashFlowEntryCreate';
import { cn, formatCurrency, formatDate } from '@/lib/utils';
import {
  BarChart, Bar, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import axios from 'axios';

export default function FluxoCaixaPage() {
  const { condominioId } = useCondominio();
  const [search, setSearch] = useState('');
  const [entryType, setEntryType] = useState<string | undefined>(undefined);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [showFormModal, setShowFormModal] = useState(false);

  // Hooks de dados
  const {
    data: entriesData,
    isLoading,
    isError,
    error,
    refetch,
  } = useCashflowEntries({
    condominio_id: condominioId,
    skip: (page - 1) * pageSize,
    limit: pageSize,
  });

  const { data: dashboardRaw, refetch: refetchDashboard } = useCashflowDashboard({ condominio_id: condominioId });
  const dashboard = dashboardRaw as any;
  const createEntry = useCreateCashflowEntry();

  // Projection hook for chart
  const { data: projectionRaw } = useCashflowProjection({ condominio_id: condominioId });
  const projectionData: any[] = Array.isArray(projectionRaw) ? projectionRaw : (projectionRaw as any)?.items ?? [];

  // AI Insights state
  const [aiRisks, setAiRisks] = useState<any[]>([]);
  const [aiOpportunities, setAiOpportunities] = useState<any[]>([]);
  const [aiLoading, setAiLoading] = useState(true);
  const [aiError, setAiError] = useState(false);

  // finApi axios instance (no redirect on 401)
  const finApi = axios.create({ timeout: 8000 });
  finApi.interceptors.request.use((config) => {
    config.baseURL =
      typeof window !== 'undefined' && window.location.hostname === 'localhost'
        ? 'http://localhost:8080'
        : 'https://erp.conectamais.pro';
    const token =
      typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
    if (token) config.headers = { ...config.headers, Authorization: `Bearer ${token}` } as any;
    return config;
  });

  // Fetch AI insights on mount
  useEffect(() => {
    let cancelled = false;
    setAiLoading(true);
    setAiError(false);
    Promise.all([
      finApi.get(`/api/v1/financial/cashflow/ai/risks?condominio_id=${condominioId}`),
      finApi.get(`/api/v1/financial/cashflow/ai/opportunities?condominio_id=${condominioId}`),
    ])
      .then(([risksRes, oppsRes]) => {
        if (cancelled) return;
        const risks = Array.isArray(risksRes.data) ? risksRes.data : (risksRes.data?.items ?? []);
        const opps = Array.isArray(oppsRes.data) ? oppsRes.data : (oppsRes.data?.items ?? []);
        setAiRisks(risks);
        setAiOpportunities(opps);
        setAiLoading(false);
      })
      .catch(() => {
        if (!cancelled) { setAiError(true); setAiLoading(false); }
      });
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // FIN-01: o endpoint /cashflow/entries devolve uma LISTA pura; tratar array
  // além de {items}. Antes lia só .items → lista/gráfico ficavam vazios mesmo com
  // dados no backend.
  const entries: any[] = Array.isArray(entriesData)
    ? (entriesData as any[])
    : ((entriesData as any)?.items ?? []);
  const total = (entriesData as any)?.total ?? entries.length;
  const totalPages = Math.ceil(total / pageSize);

  // Debounce search
  const lastSearchRef = useRef<string | undefined>(undefined);
  useEffect(() => {
    const newSearch = search || undefined;
    if (lastSearchRef.current === newSearch) return;

    const timer = setTimeout(() => {
      lastSearchRef.current = newSearch;
      setPage(1);
    }, 300);

    return () => clearTimeout(timer);
  }, [search]);

  const handleCreateEntry = async (data: any) => {
    try {
      await createEntry.mutateAsync({ data });
      setShowFormModal(false);
      // refetch() removido - mutation já invalida queries automaticamente
    } catch (err) {
      throw err;
    }
  };

  const getEntryTypeColor = (type: string) => {
    switch (type) {
      case 'income':
        return 'bg-green-500/10 text-green-500 border-green-500/30';
      case 'expense':
        return 'bg-red-500/10 text-red-500 border-red-500/30';
      default:
        return 'bg-gray-500/10 text-gray-500 border-gray-500/30';
    }
  };

  const getEntryTypeLabel = (type: string) => {
    switch (type) {
      case 'income':
        return 'Entrada';
      case 'expense':
        return 'Saida';
      default:
        return type;
    }
  };

  // Filtrar localmente por search se necessario
  const filteredEntries = search
    ? entries.filter((entry: any) =>
        entry.description?.toLowerCase().includes(search.toLowerCase()) ||
        entry.memo?.toLowerCase().includes(search.toLowerCase())
      )
    : entries;

  // Build last-6-months bar chart data from entries
  const monthLabels: string[] = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
  const barChartData = (() => {
    const now = new Date();
    const months: { month: string; Receitas: number; Despesas: number }[] = [];
    for (let i = 5; i >= 0; i--) {
      const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
      months.push({ month: monthLabels[d.getMonth()] ?? '', Receitas: 0, Despesas: 0 });
    }
    entries.forEach((e: any) => {
      if (!e.entry_date) return;
      const d = new Date(e.entry_date);
      const diffMonths = (now.getFullYear() - d.getFullYear()) * 12 + now.getMonth() - d.getMonth();
      if (diffMonths < 0 || diffMonths > 5) return;
      const idx = 5 - diffMonths;
      const bucket = months[idx];
      if (!bucket) return;
      const val = Math.abs(parseFloat(e.expected_amount || e.amount || 0));
      if (e.entry_type === 'income') bucket.Receitas += val;
      else bucket.Despesas += val;
    });
    return months;
  })();

  // Projection area chart data
  const areaChartData = projectionData.slice(0, 30).map((p: any) => ({
    date: p.date ? String(p.date).slice(5) : '',
    Saldo: Number(p.cumulative_balance ?? p.balance ?? 0),
  }));

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <Link href="/modulos/financeiro">
            <Button variant="ghost" size="sm">
              <ArrowLeft className="w-4 h-4 mr-2" />
              Financeiro
            </Button>
          </Link>
          <div className="flex items-center gap-2">
            <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
              <Activity className="w-5 h-5 text-blue-500" />
            </div>
            <div>
              <h1 className="text-lg font-semibold text-[hsl(var(--foreground))]">
                Fluxo de Caixa
              </h1>
              <p className="text-xs text-[hsl(var(--muted-foreground))]">
                {total} lancamentos registrados
              </p>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => { refetch(); refetchDashboard(); }}
            disabled={isLoading}
          >
            <RefreshCw className={cn('w-4 h-4', isLoading && 'animate-spin')} />
          </Button>
          <Button variant="primary" size="sm" onClick={() => setShowFormModal(true)}>
            <Plus className="w-4 h-4 mr-2" />
            Novo Lancamento
          </Button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-green-500/10 flex items-center justify-center">
              <TrendingUp className="w-5 h-5 text-green-500" />
            </div>
            <div>
              <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                {isLoading ? '...' : formatCurrency(Number(dashboard?.summary?.total_inflows ?? 0))}
              </p>
              <p className="text-xs text-[hsl(var(--muted-foreground))]">Entradas</p>
            </div>
          </div>
        </div>

        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-red-500/10 flex items-center justify-center">
              <TrendingDown className="w-5 h-5 text-red-500" />
            </div>
            <div>
              <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                {isLoading ? '...' : formatCurrency(Number(dashboard?.summary?.total_outflows ?? 0))}
              </p>
              <p className="text-xs text-[hsl(var(--muted-foreground))]">Saidas</p>
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
                {isLoading ? '...' : formatCurrency(Number(dashboard?.summary?.closing_balance ?? 0))}
              </p>
              <p className="text-xs text-[hsl(var(--muted-foreground))]">Saldo Atual</p>
            </div>
          </div>
        </div>

        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-purple-500/10 flex items-center justify-center">
              <Activity className="w-5 h-5 text-purple-500" />
            </div>
            <div>
              <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                {isLoading ? '...' : formatCurrency(Number(dashboard?.upcoming_receivables ?? 0) - Number(dashboard?.upcoming_payables ?? 0))}
              </p>
              <p className="text-xs text-[hsl(var(--muted-foreground))]">Projecao 30d</p>
            </div>
          </div>
        </div>
      </div>

      {/* Visualização — Charts */}
      <div className="space-y-2">
        <h2 className="text-sm font-semibold text-[hsl(var(--muted-foreground))] uppercase tracking-wide px-1">
          Visualização
        </h2>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Bar Chart: Receitas vs Despesas */}
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <p className="text-sm font-medium text-[hsl(var(--foreground))] mb-4">
              Receitas vs Despesas (6 meses)
            </p>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={barChartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis
                  dataKey="month"
                  tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(v: any) => `${(Number(v) / 1000).toFixed(0)}k`}
                  width={40}
                />
                <Tooltip
                  formatter={(value: any) => formatCurrency(Number(value))}
                  contentStyle={{
                    background: 'hsl(var(--card))',
                    border: '1px solid hsl(var(--border))',
                    borderRadius: '8px',
                    fontSize: 12,
                  }}
                />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="Receitas" fill="#22c55e" radius={[4, 4, 0, 0]} />
                <Bar dataKey="Despesas" fill="#ef4444" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Area Chart: Projeção de Saldo */}
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <p className="text-sm font-medium text-[hsl(var(--foreground))] mb-4">
              Projeção de Saldo
            </p>
            {areaChartData.length === 0 ? (
              <div className="h-[220px] flex items-center justify-center">
                <p className="text-sm text-[hsl(var(--muted-foreground))]">Sem dados de projeção</p>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart data={areaChartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="gradSaldo" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#22c55e" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }}
                    axisLine={false}
                    tickLine={false}
                    interval="preserveStartEnd"
                  />
                  <YAxis
                    tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }}
                    axisLine={false}
                    tickLine={false}
                    tickFormatter={(v: any) => `${(Number(v) / 1000).toFixed(0)}k`}
                    width={40}
                  />
                  <Tooltip
                    formatter={(value: any) => formatCurrency(Number(value))}
                    contentStyle={{
                      background: 'hsl(var(--card))',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: '8px',
                      fontSize: 12,
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="Saldo"
                    stroke="#22c55e"
                    strokeWidth={2}
                    fill="url(#gradSaldo)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      </div>

      {/* AI Insights Panel */}
      <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-5 space-y-4">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-purple-500/10 flex items-center justify-center">
            <Brain className="w-4 h-4 text-purple-500" />
          </div>
          <h2 className="text-sm font-semibold text-[hsl(var(--foreground))]">Insights Financeiros</h2>
          {aiLoading && (
            <span className="text-xs text-[hsl(var(--muted-foreground))] ml-2 animate-pulse">
              Analisando...
            </span>
          )}
        </div>

        {aiLoading ? (
          <div className="space-y-2">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="h-10 rounded-lg bg-[hsl(var(--secondary))] animate-shimmer" />
            ))}
          </div>
        ) : aiError ? (
          <p className="text-sm text-[hsl(var(--muted-foreground))]">
            Análise IA temporariamente indisponível. Tente novamente mais tarde.
          </p>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Riscos */}
            <div className="space-y-2">
              <p className="text-xs font-semibold text-[hsl(var(--muted-foreground))] uppercase tracking-wide flex items-center gap-1">
                <AlertTriangle className="w-3 h-3 text-orange-400" />
                Riscos Identificados
              </p>
              {aiRisks.length === 0 ? (
                <p className="text-sm text-[hsl(var(--muted-foreground))] italic">Nenhum risco identificado.</p>
              ) : (
                aiRisks.map((risk: any, i: number) => (
                  <div
                    key={i}
                    className="flex items-start gap-2 p-3 rounded-lg bg-orange-500/10 border border-orange-500/20"
                  >
                    <AlertTriangle className="w-4 h-4 text-orange-400 mt-0.5 shrink-0" />
                    <p className="text-sm text-[hsl(var(--foreground))]">
                      {typeof risk === 'string' ? risk : (risk.description ?? risk.message ?? JSON.stringify(risk))}
                    </p>
                  </div>
                ))
              )}
            </div>

            {/* Oportunidades */}
            <div className="space-y-2">
              <p className="text-xs font-semibold text-[hsl(var(--muted-foreground))] uppercase tracking-wide flex items-center gap-1">
                <Lightbulb className="w-3 h-3 text-green-400" />
                Oportunidades
              </p>
              {aiOpportunities.length === 0 ? (
                <p className="text-sm text-[hsl(var(--muted-foreground))] italic">Nenhuma oportunidade detectada.</p>
              ) : (
                aiOpportunities.map((opp: any, i: number) => (
                  <div
                    key={i}
                    className="flex items-start gap-2 p-3 rounded-lg bg-green-500/10 border border-green-500/20"
                  >
                    <Lightbulb className="w-4 h-4 text-green-400 mt-0.5 shrink-0" />
                    <p className="text-sm text-[hsl(var(--foreground))]">
                      {typeof opp === 'string' ? opp : (opp.description ?? opp.message ?? JSON.stringify(opp))}
                    </p>
                  </div>
                ))
              )}
            </div>
          </div>
        )}
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4">
        <div className="flex-1">
          <Input
            type="search"
            placeholder="Buscar por descricao ou categoria..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            icon={<Search className="w-4 h-4" />}
          />
        </div>
        <div className="flex gap-2 flex-wrap">
          <Button
            variant={entryType === undefined ? 'primary' : 'secondary'}
            size="sm"
            onClick={() => { setEntryType(undefined); setPage(1); }}
          >
            Todos
          </Button>
          <Button
            variant={entryType === 'income' ? 'primary' : 'secondary'}
            size="sm"
            onClick={() => { setEntryType('income'); setPage(1); }}
          >
            Entradas
          </Button>
          <Button
            variant={entryType === 'expense' ? 'primary' : 'secondary'}
            size="sm"
            onClick={() => { setEntryType('expense'); setPage(1); }}
          >
            Saidas
          </Button>
        </div>
      </div>

      {/* Error */}
      {isError && (
        <div className="flex items-center gap-3 p-4 rounded-lg bg-[hsl(var(--destructive))]/10 border border-[hsl(var(--destructive))]/30">
          <AlertCircle className="w-5 h-5 text-[hsl(var(--destructive))]" />
          <div>
            <p className="font-medium text-[hsl(var(--destructive))]">Erro ao carregar lancamentos</p>
            <p className="text-sm text-[hsl(var(--muted-foreground))]">
              {(error as Error)?.message || 'Tente novamente em alguns instantes'}
            </p>
          </div>
          <Button variant="secondary" size="sm" onClick={() => refetch()} className="ml-auto">
            Tentar novamente
          </Button>
        </div>
      )}

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="divide-y divide-[hsl(var(--border))]">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="p-4 flex items-center gap-4">
                  <div className="flex-1 space-y-2">
                    <div className="h-4 w-48 bg-[hsl(var(--secondary))] rounded animate-shimmer" />
                    <div className="h-3 w-32 bg-[hsl(var(--secondary))] rounded animate-shimmer" />
                  </div>
                  <div className="h-6 w-20 bg-[hsl(var(--secondary))] rounded animate-shimmer" />
                  <div className="h-4 w-24 bg-[hsl(var(--secondary))] rounded animate-shimmer" />
                </div>
              ))}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-[hsl(var(--border))]">
                    <th className="text-left p-4 text-sm font-medium text-[hsl(var(--muted-foreground))]">
                      Data
                    </th>
                    <th className="text-left p-4 text-sm font-medium text-[hsl(var(--muted-foreground))]">
                      Descricao
                    </th>
                    <th className="text-left p-4 text-sm font-medium text-[hsl(var(--muted-foreground))]">
                      Tipo
                    </th>
                    <th className="text-right p-4 text-sm font-medium text-[hsl(var(--muted-foreground))]">
                      Valor
                    </th>
                    <th className="text-right p-4 text-sm font-medium text-[hsl(var(--muted-foreground))]">
                      Saldo Acumulado
                    </th>
                    <th className="text-left p-4 text-sm font-medium text-[hsl(var(--muted-foreground))] hidden md:table-cell">
                      Categoria
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[hsl(var(--border))]">
                  {filteredEntries.map((entry: any) => (
                    <tr
                      key={entry.id}
                      className="hover:bg-[hsl(var(--secondary))]/50 transition-colors"
                    >
                      <td className="p-4">
                        <span className="text-sm text-[hsl(var(--foreground))]">
                          {entry.entry_date ? formatDate(entry.entry_date) : '-'}
                        </span>
                      </td>
                      <td className="p-4">
                        <p className="font-medium text-[hsl(var(--foreground))]">
                          {entry.description || '-'}
                        </p>
                      </td>
                      <td className="p-4">
                        <span
                          className={cn(
                            'inline-flex px-2 py-1 text-xs font-medium rounded-full border',
                            getEntryTypeColor(entry.entry_type)
                          )}
                        >
                          {getEntryTypeLabel(entry.entry_type)}
                        </span>
                      </td>
                      <td className="p-4 text-right">
                        <span
                          className={cn(
                            'font-mono text-sm font-medium',
                            entry.entry_type === 'income'
                              ? 'text-green-500'
                              : 'text-red-500'
                          )}
                        >
                          {entry.entry_type === 'income' ? '+' : '-'}
                          {formatCurrency(Math.abs(parseFloat(entry.expected_amount || entry.amount || 0)))}
                        </span>
                      </td>
                      <td className="p-4 text-right">
                        <span className="font-mono text-sm text-[hsl(var(--foreground))]">
                          {formatCurrency(parseFloat(entry.realized_amount ?? entry.balance ?? 0))}
                        </span>
                      </td>
                      <td className="p-4 hidden md:table-cell">
                        <span className="text-sm text-[hsl(var(--muted-foreground))]">
                          {entry.memo || entry.category || '-'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Empty state */}
          {!isLoading && filteredEntries.length === 0 && (
            <div className="text-center py-12">
              <Activity className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
              <h3 className="text-lg font-medium text-[hsl(var(--foreground))]">
                Nenhum lancamento encontrado
              </h3>
              <p className="text-[hsl(var(--muted-foreground))] mt-1">
                {search || entryType
                  ? 'Tente ajustar os filtros de busca'
                  : 'Comece adicionando seu primeiro lancamento'}
              </p>
              {!search && !entryType && (
                <Button className="mt-4" onClick={() => setShowFormModal(true)}>
                  <Plus className="w-4 h-4 mr-2" />
                  Novo Lancamento
                </Button>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-[hsl(var(--muted-foreground))]">
            Mostrando {(page - 1) * pageSize + 1} a{' '}
            {Math.min(page * pageSize, total)} de {total} lancamentos
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

      {/* Modal */}
      <CashflowFormModal
        isOpen={showFormModal}
        onClose={() => setShowFormModal(false)}
        onSubmit={handleCreateEntry}
        isLoading={createEntry.isPending}
      />
    </div>
  );
}
