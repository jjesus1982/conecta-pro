'use client';

import {
  BarChart2,
  ArrowLeft,
  RefreshCw,
  Download,
  TrendingUp,
  TrendingDown,
  DollarSign,
  CheckCircle2,
  AlertCircle,
  Scale,
  Activity,
  Brain,
  FileText,
  Star,
  AlertTriangle,
  CheckCircle,
  Minus,
} from 'lucide-react';
import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import {
  BarChart,
  Bar,
  AreaChart,
  Area,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import {
  useCashflowDashboard,
  useCashflowEntries,
  useCashflowProjection,
  useAccountingAccounts,
  usePayableDashboard,
  useReceivableDashboard,
  useFinancialOverview,
} from '@/hooks/financial/useFinancial';
import { cn } from '@/lib/utils';
import { useCondominio } from '@/contexts/CondominioContext';

// ─────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────
const formatCurrency = (value: number | undefined | null) => {
  if (value == null) return 'R$ 0,00';
  return value.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
};

const formatDate = (date: string | undefined | null) => {
  if (!date) return '-';
  return new Date(date).toLocaleDateString('pt-BR');
};

const formatShortMonth = (dateStr: string) => {
  const d = new Date(dateStr);
  return d.toLocaleDateString('pt-BR', { month: 'short', year: '2-digit' });
};

const PIE_COLORS = ['#3b82f6', '#ef4444', '#22c55e', '#f97316', '#a855f7', '#ec4899', '#14b8a6', '#eab308'];

type Period = 'month' | 'quarter' | 'year';

// ─────────────────────────────────────────────
// Custom Tooltip for recharts
// ─────────────────────────────────────────────
const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-lg p-3 shadow-lg text-sm">
      {label && <p className="font-medium text-[hsl(var(--foreground))] mb-2">{label}</p>}
      {payload.map((entry: any, i: number) => (
        <p key={i} style={{ color: entry.color }} className="text-xs">
          {entry.name}: {formatCurrency(entry.value)}
        </p>
      ))}
    </div>
  );
};

// ─────────────────────────────────────────────
// Skeleton loader
// ─────────────────────────────────────────────
const SkeletonCard = () => (
  <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4 animate-pulse">
    <div className="h-4 bg-[hsl(var(--muted))] rounded w-1/3 mb-2" />
    <div className="h-7 bg-[hsl(var(--muted))] rounded w-2/3 mb-1" />
    <div className="h-3 bg-[hsl(var(--muted))] rounded w-1/2" />
  </div>
);

// ─────────────────────────────────────────────
// DRE Summary Row
// ─────────────────────────────────────────────
interface DreRowProps {
  label: string;
  value: number;
  indent?: boolean;
  bold?: boolean;
  positive?: boolean;
  negative?: boolean;
  separator?: boolean;
}

const DreRow = ({ label, value, indent = false, bold = false, positive = false, negative = false, separator = false }: DreRowProps) => (
  <div className={cn(
    'flex items-center justify-between py-2',
    separator ? 'border-t border-[hsl(var(--border))] mt-1' : 'border-b border-[hsl(var(--border))]/40',
  )}>
    <span className={cn(
      'text-sm text-[hsl(var(--muted-foreground))]',
      indent && 'pl-4',
      bold && 'font-semibold text-[hsl(var(--foreground))]',
    )}>
      {label}
    </span>
    <span className={cn(
      'text-sm font-medium tabular-nums',
      positive && 'text-green-500',
      negative && 'text-red-500',
      !positive && !negative && 'text-[hsl(var(--foreground))]',
      bold && 'font-bold text-base',
    )}>
      {formatCurrency(value)}
    </span>
  </div>
);

// ─────────────────────────────────────────────
// Main Page
// ─────────────────────────────────────────────
export default function RelatoriosPage() {
  const { condominioId } = useCondominio();
  const [period, setPeriod] = useState<Period>('month');
  const [activeTab, setActiveTab] = useState('dre');
  const [relatorioLoading, setRelatorioLoading] = useState(false);
  const [relatorio, setRelatorio] = useState<any>(null);
  const [relatorioPeriodo, setRelatorioPeriodo] = useState(() => {
    const today = new Date();
    return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`;
  });

  // ── Data hooks ──────────────────────────────
  const { data: cashflowRaw, isLoading: loadingCashflow, refetch: refetchCashflow } =
    useCashflowDashboard({ condominio_id: condominioId });

  const { data: entriesRaw, isLoading: loadingEntries, refetch: refetchEntries } =
    useCashflowEntries({ condominio_id: condominioId, limit: 200 });

  const { data: projectionRaw, isLoading: loadingProjection, refetch: refetchProjection } =
    useCashflowProjection({ condominio_id: condominioId });

  const { data: accountsRaw, isLoading: loadingAccounts, refetch: refetchAccounts } =
    useAccountingAccounts({ chart_id: '' });

  const { data: payableDashRaw, isLoading: loadingPayable } =
    usePayableDashboard({ condominio_id: condominioId });

  const { data: receivableDashRaw, isLoading: loadingReceivable } =
    useReceivableDashboard({ condominio_id: condominioId });

  const { data: overviewRaw, isLoading: loadingOverview } =
    useFinancialOverview({ condominio_id: condominioId });

  // DRE REAL (o cálculo por entries/cashflow zerava porque essas fontes vêm vazias).
  const { data: dreRaw } = useQuery({
    queryKey: ['accounting-dre'],
    queryFn: async () => {
      const token = typeof window !== 'undefined' ? (localStorage.getItem('access_token') ?? localStorage.getItem('token') ?? '') : '';
      const res = await fetch('/api/v1/financial/accounting/dre', { headers: { Authorization: `Bearer ${token}` } });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    },
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });
  const dre = dreRaw as any;

  const isLoadingAny = loadingCashflow || loadingEntries || loadingOverview;

  // ── Cast to any ──────────────────────────────
  const cashflow = cashflowRaw as any;
  const overview = overviewRaw as any;
  const payableDash = payableDashRaw as any;
  const receivableDash = receivableDashRaw as any;

  const entries: any[] = (entriesRaw as any)?.items ?? [];
  const accounts: any[] = (accountsRaw as any)?.items ?? [];
  const projectionData: any[] = (projectionRaw as any)?.projections ?? (projectionRaw as any)?.items ?? [];

  // ── DRE Calculations ─────────────────────────
  const incomeEntries = entries.filter((e: any) => e.type === 'income' || e.entry_type === 'income');
  const expenseEntries = entries.filter((e: any) => e.type === 'expense' || e.entry_type === 'expense');

  // Prioriza o DRE REAL do backend (/accounting/dre); só cai no cálculo por entries/cashflow se vier vazio.
  const dreReceita = Number(dre?.receita_bruta ?? 0);
  const dreDespPessoal = Number(dre?.despesa_pessoal ?? 0);
  const dreDespEncargos = Number(dre?.despesa_encargos ?? 0);
  const dreDespOper = Number(dre?.despesas_operacionais ?? 0);
  const dreDespTotal = dreDespPessoal + dreDespEncargos + dreDespOper;

  const receitaBruta = dreReceita
    || incomeEntries.reduce((sum: number, e: any) => sum + Number(e.amount ?? e.valor ?? 0), 0)
    || Number(cashflow?.summary?.total_inflows ?? overview?.receita_total ?? 0);

  const despesaTotal = (dreReceita ? dreDespTotal : 0)
    || expenseEntries.reduce((sum: number, e: any) => sum + Number(e.amount ?? e.valor ?? 0), 0)
    || Number(cashflow?.summary?.total_outflows ?? overview?.despesa_total ?? 0);

  const deducoes = dreReceita ? Number(dre?.deducoes ?? 0) : receitaBruta * 0.1;
  const receitaLiquida = receitaBruta - deducoes;
  const custosOperacionais = dreReceita ? (dreDespPessoal + dreDespEncargos) : despesaTotal * 0.65;
  const despesasAdmin = dreReceita ? dreDespOper : despesaTotal * 0.35;
  const ebitda = receitaLiquida - custosOperacionais;
  const lucroLiquido = dreReceita ? Number(dre?.resultado_operacional ?? (ebitda - despesasAdmin)) : (ebitda - despesasAdmin);

  // ── Monthly chart data (last 6 months simulation from entries) ────────────
  const monthlyData = useMemo(() => {
    const now = new Date();
    const months: { month: string; Receitas: number; Despesas: number }[] = [];
    for (let i = 5; i >= 0; i--) {
      const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
      const label = d.toLocaleDateString('pt-BR', { month: 'short', year: '2-digit' });
      const mIncome = incomeEntries
        .filter((e: any) => (e.date ?? e.data_lancamento ?? '').startsWith(key))
        .reduce((s: number, e: any) => s + Number(e.amount ?? e.valor ?? 0), 0);
      const mExpense = expenseEntries
        .filter((e: any) => (e.date ?? e.data_lancamento ?? '').startsWith(key))
        .reduce((s: number, e: any) => s + Number(e.amount ?? e.valor ?? 0), 0);
      months.push({ month: label, Receitas: mIncome, Despesas: mExpense });
    }
    // If all zero (no date data), distribute totals across last month
    const hasRealData = months.some(m => m.Receitas > 0 || m.Despesas > 0);
    if (!hasRealData && (receitaBruta > 0 || despesaTotal > 0) && months[5]) {
      months[5].Receitas = receitaBruta;
      months[5].Despesas = despesaTotal;
    }
    return months;
  }, [entries, receitaBruta, despesaTotal]);

  // ── Expense by category (pie) ─────────────────
  const expenseCategoryData = useMemo(() => {
    const catMap: Record<string, number> = {};
    expenseEntries.forEach((e: any) => {
      const cat = e.category ?? e.categoria ?? 'Outros';
      catMap[cat] = (catMap[cat] ?? 0) + Number(e.amount ?? e.valor ?? 0);
    });
    const items = Object.entries(catMap).map(([name, value]) => ({ name, value }));
    if (items.length === 0 && despesaTotal > 0) {
      return [
        { name: 'Operacional', value: custosOperacionais },
        { name: 'Administrativo', value: despesasAdmin },
      ];
    }
    return items.slice(0, 8);
  }, [expenseEntries, despesaTotal, custosOperacionais, despesasAdmin]);

  // ── Accounting / Balanço ────────────────────
  const accountGroups = useMemo(() => {
    const groups: Record<string, { label: string; color: string; accounts: any[]; total: number }> = {
      asset: { label: 'Ativo', color: '#3b82f6', accounts: [], total: 0 },
      liability: { label: 'Passivo', color: '#ef4444', accounts: [], total: 0 },
      equity: { label: 'Patrimônio Líquido', color: '#a855f7', accounts: [], total: 0 },
      revenue: { label: 'Receitas', color: '#22c55e', accounts: [], total: 0 },
      expense: { label: 'Despesas', color: '#f97316', accounts: [], total: 0 },
    };
    accounts.forEach((acc: any) => {
      const t = acc.account_type ?? acc.type ?? 'asset';
      if (groups[t]) {
        groups[t].accounts.push(acc);
        groups[t].total += Number(acc.balance ?? acc.saldo ?? 0);
      }
    });
    return groups;
  }, [accounts]);

  const balanceChartData = Object.values(accountGroups).map(g => ({
    name: g.label,
    Saldo: Math.abs(g.total),
    fill: g.color,
  }));

  const ativoTotal = accountGroups['asset']?.total ?? 0;
  const passivoTotal = accountGroups['liability']?.total ?? 0;
  const patrimonioTotal = accountGroups['equity']?.total ?? 0;
  const equationDiff = Math.abs(ativoTotal - (passivoTotal + patrimonioTotal));
  const equationOk = equationDiff < 0.01 || ativoTotal === 0;

  // ── Projection / Cash Flow ────────────────────
  const projectionChartData = useMemo(() => {
    let cumulative = Number(cashflow?.summary?.opening_balance ?? 0);
    return projectionData.slice(0, 30).map((p: any) => {
      const inflow = Number(p.inflow ?? p.entradas ?? p.receita ?? 0);
      const outflow = Number(p.outflow ?? p.saidas ?? p.despesa ?? 0);
      const net = inflow - outflow;
      cumulative += net;
      return {
        date: formatDate(p.date ?? p.data),
        Entradas: inflow,
        Saidas: outflow,
        Liquido: net,
        'Saldo Acumulado': cumulative,
      };
    });
  }, [projectionData, cashflow]);

  const loadRelatorio = async () => {
    setRelatorioLoading(true);
    try {
      const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
      const resp = await fetch(
        `${typeof window !== 'undefined' && window.location.hostname === 'localhost' ? 'http://localhost:8080' : 'https://erp.conectamais.pro'}/api/v1/financial/ai/advisor/relatorio?periodo=${relatorioPeriodo}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (resp.ok) {
        const data = await resp.json();
        setRelatorio(data);
      }
    } catch (e) {
      void e;
    } finally {
      setRelatorioLoading(false);
    }
  };

  const handleRefreshAll = () => {
    refetchCashflow();
    refetchEntries();
    refetchProjection();
    refetchAccounts();
  };

  // ─────────────────────────────────────────────
  // Render
  // ─────────────────────────────────────────────
  return (
    <div className="space-y-6 animate-fade-in">

      {/* ── Header ──────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <Link href="/modulos/financeiro">
            <Button variant="ghost" size="sm">
              <ArrowLeft className="w-4 h-4 mr-2" />
              Financeiro
            </Button>
          </Link>
          <div className="flex items-center gap-2">
            <div className="w-10 h-10 rounded-lg bg-violet-500/10 flex items-center justify-center">
              <BarChart2 className="w-5 h-5 text-violet-500" />
            </div>
            <div>
              <h1 className="text-lg font-semibold text-[hsl(var(--foreground))]">Relatórios</h1>
              <p className="text-xs text-[hsl(var(--muted-foreground))]">Demonstrativos financeiros</p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {/* Period selector */}
          <div className="flex items-center rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--card))] p-0.5 gap-0.5">
            {(['month', 'quarter', 'year'] as Period[]).map((p) => (
              <button
                key={p}
                onClick={() => setPeriod(p)}
                className={cn(
                  'px-3 py-1 rounded-md text-xs font-medium transition-all',
                  period === p
                    ? 'bg-violet-500 text-white shadow-sm'
                    : 'text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))]',
                )}
              >
                {p === 'month' ? 'Mês' : p === 'quarter' ? 'Trimestre' : 'Ano'}
              </button>
            ))}
          </div>

          <Button variant="outline" size="sm" onClick={handleRefreshAll} disabled={isLoadingAny}>
            <RefreshCw className={cn('w-4 h-4', isLoadingAny && 'animate-spin')} />
          </Button>

          <Button variant="outline" size="sm" onClick={() => window.print()}>
            <Download className="w-4 h-4 mr-2" />
            Exportar PDF
          </Button>
        </div>
      </div>

      {/* ── KPI Summary Cards ────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {isLoadingAny ? (
          <>
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </>
        ) : (
          <>
            <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-green-500/10 flex items-center justify-center">
                  <TrendingUp className="w-5 h-5 text-green-500" />
                </div>
                <div>
                  <p className="font-data text-xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                    {formatCurrency(receitaBruta)}
                  </p>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Receita Bruta</p>
                </div>
              </div>
            </div>

            <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-red-500/10 flex items-center justify-center">
                  <TrendingDown className="w-5 h-5 text-red-500" />
                </div>
                <div>
                  <p className="font-data text-xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                    {formatCurrency(despesaTotal)}
                  </p>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Despesas Totais</p>
                </div>
              </div>
            </div>

            <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
              <div className="flex items-center gap-3">
                <div className={cn('w-10 h-10 rounded-lg flex items-center justify-center',
                  lucroLiquido >= 0 ? 'bg-emerald-500/10' : 'bg-red-500/10'
                )}>
                  <DollarSign className={cn('w-5 h-5', lucroLiquido >= 0 ? 'text-emerald-500' : 'text-red-500')} />
                </div>
                <div>
                  <p className={cn('font-data text-xl font-semibold tabular-nums', lucroLiquido >= 0 ? 'text-emerald-500' : 'text-red-500')}>
                    {formatCurrency(lucroLiquido)}
                  </p>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Lucro Líquido</p>
                </div>
              </div>
            </div>

            <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
                  <Activity className="w-5 h-5 text-blue-500" />
                </div>
                <div>
                  <p className="font-data text-xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                    {receitaBruta > 0 ? `${((lucroLiquido / receitaBruta) * 100).toFixed(1)}%` : '0,0%'}
                  </p>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Margem Líquida</p>
                </div>
              </div>
            </div>
          </>
        )}
      </div>

      {/* ── Tabs ─────────────────────────────────── */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="grid grid-cols-4 w-full max-w-2xl">
          <TabsTrigger value="dre">DRE</TabsTrigger>
          <TabsTrigger value="balancete">Balancete</TabsTrigger>
          <TabsTrigger value="projecao">Projeção FC</TabsTrigger>
          <TabsTrigger value="executivo">
            <Brain className="w-4 h-4 mr-1" />
            Relatório Executivo IA
          </TabsTrigger>
        </TabsList>

        {/* ══════════════════════════════════════════
            TAB 1 — DRE
        ══════════════════════════════════════════ */}
        <TabsContent value="dre" className="mt-6 space-y-6">

          {/* Charts row */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

            {/* Bar chart — monthly */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-[hsl(var(--muted-foreground))]">
                  Receitas vs Despesas — Últimos 6 Meses
                </CardTitle>
              </CardHeader>
              <CardContent>
                {loadingEntries ? (
                  <div className="h-48 animate-pulse bg-[hsl(var(--muted))] rounded-lg" />
                ) : (
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={monthlyData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                      <XAxis dataKey="month" tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} axisLine={false} tickLine={false} />
                      <YAxis tickFormatter={(v) => `R$${(v / 1000).toFixed(0)}k`} tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }} axisLine={false} tickLine={false} />
                      <Tooltip content={<CustomTooltip />} />
                      <Legend wrapperStyle={{ fontSize: 11 }} />
                      <Bar dataKey="Receitas" fill="#22c55e" radius={[4, 4, 0, 0]} maxBarSize={40} />
                      <Bar dataKey="Despesas" fill="#ef4444" radius={[4, 4, 0, 0]} maxBarSize={40} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>

            {/* Pie chart — expense categories */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-[hsl(var(--muted-foreground))]">
                  Composição das Despesas por Categoria
                </CardTitle>
              </CardHeader>
              <CardContent className="flex items-center gap-4">
                {loadingEntries ? (
                  <div className="h-48 w-full animate-pulse bg-[hsl(var(--muted))] rounded-lg" />
                ) : expenseCategoryData.length === 0 ? (
                  <div className="flex-1 flex flex-col items-center justify-center py-10 text-[hsl(var(--muted-foreground))]">
                    <AlertCircle className="w-8 h-8 mb-2 opacity-50" />
                    <p className="text-sm">Sem dados de despesas</p>
                  </div>
                ) : (
                  <>
                    <ResponsiveContainer width="55%" height={200}>
                      <PieChart>
                        <Pie
                          data={expenseCategoryData}
                          cx="50%"
                          cy="50%"
                          innerRadius={50}
                          outerRadius={80}
                          paddingAngle={3}
                          dataKey="value"
                        >
                          {expenseCategoryData.map((_: any, idx: number) => (
                            <Cell key={idx} fill={PIE_COLORS[idx % PIE_COLORS.length]} />
                          ))}
                        </Pie>
                        <Tooltip formatter={(v: any) => formatCurrency(v)} />
                      </PieChart>
                    </ResponsiveContainer>
                    <div className="flex-1 space-y-1.5">
                      {expenseCategoryData.map((item: any, idx: number) => (
                        <div key={idx} className="flex items-center gap-2">
                          <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: PIE_COLORS[idx % PIE_COLORS.length] }} />
                          <span className="text-xs text-[hsl(var(--muted-foreground))] truncate flex-1">{item.name}</span>
                          <span className="text-xs font-medium text-[hsl(var(--foreground))] tabular-nums">
                            {despesaTotal > 0 ? `${((item.value / despesaTotal) * 100).toFixed(0)}%` : '-'}
                          </span>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </CardContent>
            </Card>
          </div>

          {/* DRE Table */}
          <Card>
            <CardHeader className="pb-4">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-semibold">
                  Demonstrativo de Resultado do Exercício — DRE
                </CardTitle>
                <Badge variant="outline" className="text-xs text-violet-500 border-violet-500/30 bg-violet-500/10">
                  {period === 'month' ? 'Mês Atual' : period === 'quarter' ? 'Trimestre' : 'Ano'}
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              {isLoadingAny ? (
                <div className="space-y-3">
                  {[...Array(8)].map((_, i) => (
                    <div key={i} className="h-8 animate-pulse bg-[hsl(var(--muted))] rounded" />
                  ))}
                </div>
              ) : (
                <div className="space-y-0">
                  <DreRow label="(+) Receita Bruta" value={receitaBruta} positive />
                  <DreRow label="(-) Deduções / Impostos (estimativa 10%)" value={-deducoes} indent negative />
                  <DreRow label="(=) Receita Líquida" value={receitaLiquida} bold separator />
                  <DreRow label="(-) Custos Operacionais" value={-custosOperacionais} indent negative />
                  <DreRow label="(-) Despesas Administrativas" value={-despesasAdmin} indent negative />
                  <DreRow
                    label="(=) EBITDA"
                    value={ebitda}
                    bold
                    separator
                    positive={ebitda >= 0}
                    negative={ebitda < 0}
                  />
                  <DreRow
                    label="(=) Lucro / Prejuízo Líquido"
                    value={lucroLiquido}
                    bold
                    separator
                    positive={lucroLiquido >= 0}
                    negative={lucroLiquido < 0}
                  />
                </div>
              )}

              {/* Receivables / Payables summary */}
              {!loadingPayable && !loadingReceivable && (
                <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="rounded-lg border border-[hsl(var(--border))] p-4 bg-green-500/5">
                    <p className="text-xs text-[hsl(var(--muted-foreground))] mb-1">A Receber (total)</p>
                    <p className="text-lg font-bold text-green-500">
                      {formatCurrency(Number(receivableDash?.total_value ?? receivableDash?.total_amount ?? receivableDash?.total ?? 0))}
                    </p>
                    <p className="text-xs text-[hsl(var(--muted-foreground))] mt-1">
                      {Number(receivableDash?.total_count ?? receivableDash?.total_records ?? 0)} registros
                    </p>
                  </div>
                  <div className="rounded-lg border border-[hsl(var(--border))] p-4 bg-red-500/5">
                    <p className="text-xs text-[hsl(var(--muted-foreground))] mb-1">A Pagar (total)</p>
                    <p className="text-lg font-bold text-red-500">
                      {formatCurrency(Number(payableDash?.total_value ?? payableDash?.total_amount ?? payableDash?.total ?? 0))}
                    </p>
                    <p className="text-xs text-[hsl(var(--muted-foreground))] mt-1">
                      {Number(payableDash?.total_count ?? payableDash?.total_records ?? 0)} registros
                    </p>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ══════════════════════════════════════════
            TAB 2 — BALANCETE
        ══════════════════════════════════════════ */}
        <TabsContent value="balancete" className="mt-6 space-y-6">

          {/* Equation check */}
          <div className={cn(
            'flex items-center gap-3 rounded-xl border px-4 py-3',
            equationOk
              ? 'bg-emerald-500/5 border-emerald-500/30'
              : 'bg-amber-500/5 border-amber-500/30',
          )}>
            {equationOk
              ? <CheckCircle2 className="w-5 h-5 text-emerald-500 flex-shrink-0" />
              : <AlertCircle className="w-5 h-5 text-amber-500 flex-shrink-0" />
            }
            <div>
              <p className={cn('text-sm font-medium', equationOk ? 'text-emerald-500' : 'text-amber-500')}>
                {equationOk ? 'Equação Patrimonial Balanceada' : 'Diferença Detectada na Equação'}
              </p>
              <p className="text-xs text-[hsl(var(--muted-foreground))]">
                Ativo ({formatCurrency(ativoTotal)}) = Passivo ({formatCurrency(passivoTotal)}) + Patrimônio Líquido ({formatCurrency(patrimonioTotal)})
                {!equationOk && ` — Diferença: ${formatCurrency(equationDiff)}`}
              </p>
            </div>
          </div>

          {/* Bar chart */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-[hsl(var(--muted-foreground))]">
                Saldos por Grupo Contábil
              </CardTitle>
            </CardHeader>
            <CardContent>
              {loadingAccounts ? (
                <div className="h-48 animate-pulse bg-[hsl(var(--muted))] rounded-lg" />
              ) : (
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={balanceChartData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                    <XAxis dataKey="name" tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} axisLine={false} tickLine={false} />
                    <YAxis tickFormatter={(v) => `R$${(v / 1000).toFixed(0)}k`} tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }} axisLine={false} tickLine={false} />
                    <Tooltip content={<CustomTooltip />} />
                    <Bar dataKey="Saldo" radius={[4, 4, 0, 0]} maxBarSize={60}>
                      {balanceChartData.map((entry: any, idx: number) => (
                        <Cell key={idx} fill={entry.fill} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>

          {/* Groups grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {Object.entries(accountGroups).map(([key, group]) => (
              <Card key={key}>
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="w-3 h-3 rounded-full" style={{ background: group.color }} />
                      <CardTitle className="text-sm font-semibold">{group.label}</CardTitle>
                    </div>
                    <Badge variant="outline" className="text-xs">
                      {group.accounts.length} contas
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="space-y-2">
                  {loadingAccounts ? (
                    <div className="h-16 animate-pulse bg-[hsl(var(--muted))] rounded" />
                  ) : group.accounts.length === 0 ? (
                    <p className="text-xs text-[hsl(var(--muted-foreground))] text-center py-4">
                      Nenhuma conta cadastrada
                    </p>
                  ) : (
                    <>
                      {group.accounts.slice(0, 5).map((acc: any, idx: number) => (
                        <div key={idx} className="flex items-center justify-between text-xs">
                          <span className="text-[hsl(var(--muted-foreground))] truncate flex-1 mr-2">
                            {acc.name ?? acc.nome ?? acc.code ?? `Conta ${idx + 1}`}
                          </span>
                          <span className="font-medium text-[hsl(var(--foreground))] tabular-nums">
                            {formatCurrency(Number(acc.balance ?? acc.saldo ?? 0))}
                          </span>
                        </div>
                      ))}
                      {group.accounts.length > 5 && (
                        <p className="text-xs text-[hsl(var(--muted-foreground))] text-center pt-1">
                          +{group.accounts.length - 5} contas
                        </p>
                      )}
                    </>
                  )}
                  <div className="flex items-center justify-between pt-2 border-t border-[hsl(var(--border))] mt-2">
                    <span className="text-xs font-semibold text-[hsl(var(--foreground))]">Total</span>
                    <span className="text-sm font-bold" style={{ color: group.color }}>
                      {formatCurrency(group.total)}
                    </span>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* Balanço summary */}
          <Card>
            <CardHeader className="pb-4">
              <div className="flex items-center gap-2">
                <Scale className="w-4 h-4 text-violet-500" />
                <CardTitle className="text-sm font-semibold">Balanço Patrimonial Resumido</CardTitle>
              </div>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                {/* Left: Ativo */}
                <div>
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-blue-500 mb-3">ATIVO</h3>
                  <DreRow label="Ativo Total" value={ativoTotal} bold positive={ativoTotal >= 0} />
                </div>
                {/* Right: Passivo + PL */}
                <div>
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-red-500 mb-3">PASSIVO + PATRIMÔNIO</h3>
                  <DreRow label="Passivo" value={passivoTotal} negative={passivoTotal > 0} />
                  <DreRow label="Patrimônio Líquido" value={patrimonioTotal} positive={patrimonioTotal >= 0} />
                  <DreRow label="Total" value={passivoTotal + patrimonioTotal} bold />
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ══════════════════════════════════════════
            TAB 3 — PROJEÇÃO FLUXO DE CAIXA
        ══════════════════════════════════════════ */}
        <TabsContent value="projecao" className="mt-6 space-y-6">

          {/* Area chart */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-[hsl(var(--muted-foreground))]">
                Saldo Acumulado Projetado
              </CardTitle>
            </CardHeader>
            <CardContent>
              {loadingProjection ? (
                <div className="h-56 animate-pulse bg-[hsl(var(--muted))] rounded-lg" />
              ) : projectionChartData.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 text-[hsl(var(--muted-foreground))]">
                  <AlertCircle className="w-10 h-10 mb-3 opacity-40" />
                  <p className="text-sm font-medium">Nenhuma projeção disponível</p>
                  <p className="text-xs mt-1">Crie lançamentos futuros para visualizar a projeção</p>
                </div>
              ) : (
                <ResponsiveContainer width="100%" height={260}>
                  <AreaChart data={projectionChartData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                    <defs>
                      <linearGradient id="gradPositive" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#22c55e" stopOpacity={0.2} />
                        <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
                      </linearGradient>
                      <linearGradient id="gradEntradas" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.15} />
                        <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                    <XAxis dataKey="date" tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }} axisLine={false} tickLine={false} />
                    <YAxis tickFormatter={(v) => `R$${(v / 1000).toFixed(0)}k`} tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }} axisLine={false} tickLine={false} />
                    <Tooltip content={<CustomTooltip />} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    <Area type="monotone" dataKey="Entradas" stroke="#3b82f6" strokeWidth={1.5} fill="url(#gradEntradas)" dot={false} />
                    <Area type="monotone" dataKey="Saidas" stroke="#ef4444" strokeWidth={1.5} fill="none" dot={false} strokeDasharray="4 2" />
                    <Area type="monotone" dataKey="Saldo Acumulado" stroke="#22c55e" strokeWidth={2} fill="url(#gradPositive)" dot={false} />
                  </AreaChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>

          {/* Projection table */}
          {projectionChartData.length > 0 && (
            <Card>
              <CardHeader className="pb-4">
                <CardTitle className="text-sm font-semibold">Detalhamento da Projeção</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-[hsl(var(--border))]">
                        <th className="text-left py-2 px-2 text-xs font-medium text-[hsl(var(--muted-foreground))]">Data</th>
                        <th className="text-right py-2 px-2 text-xs font-medium text-green-500">Entradas</th>
                        <th className="text-right py-2 px-2 text-xs font-medium text-red-500">Saídas</th>
                        <th className="text-right py-2 px-2 text-xs font-medium text-[hsl(var(--muted-foreground))]">Líquido</th>
                        <th className="text-right py-2 px-2 text-xs font-medium text-blue-500">Saldo Acumulado</th>
                      </tr>
                    </thead>
                    <tbody>
                      {projectionChartData.map((row: any, idx: number) => (
                        <tr
                          key={idx}
                          className={cn(
                            'border-b border-[hsl(var(--border))]/40 hover:bg-[hsl(var(--muted))]/30 transition-colors',
                            idx % 2 === 0 && 'bg-[hsl(var(--muted))]/10',
                          )}
                        >
                          <td className="py-2 px-2 text-xs text-[hsl(var(--muted-foreground))]">{row.date}</td>
                          <td className="py-2 px-2 text-xs text-right text-green-500 font-medium tabular-nums">
                            {formatCurrency(row.Entradas)}
                          </td>
                          <td className="py-2 px-2 text-xs text-right text-red-500 font-medium tabular-nums">
                            {formatCurrency(row.Saidas)}
                          </td>
                          <td className={cn(
                            'py-2 px-2 text-xs text-right font-medium tabular-nums',
                            row.Liquido >= 0 ? 'text-emerald-500' : 'text-red-500',
                          )}>
                            {formatCurrency(row.Liquido)}
                          </td>
                          <td className={cn(
                            'py-2 px-2 text-xs text-right font-bold tabular-nums',
                            row['Saldo Acumulado'] >= 0 ? 'text-blue-500' : 'text-red-500',
                          )}>
                            {formatCurrency(row['Saldo Acumulado'])}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot>
                      <tr className="border-t-2 border-[hsl(var(--border))] bg-[hsl(var(--muted))]/20">
                        <td className="py-2 px-2 text-xs font-bold text-[hsl(var(--foreground))]">Total</td>
                        <td className="py-2 px-2 text-xs text-right font-bold text-green-500 tabular-nums">
                          {formatCurrency(projectionChartData.reduce((s: number, r: any) => s + r.Entradas, 0))}
                        </td>
                        <td className="py-2 px-2 text-xs text-right font-bold text-red-500 tabular-nums">
                          {formatCurrency(projectionChartData.reduce((s: number, r: any) => s + r.Saidas, 0))}
                        </td>
                        <td className="py-2 px-2 text-xs text-right font-bold tabular-nums text-[hsl(var(--foreground))]">
                          {formatCurrency(projectionChartData.reduce((s: number, r: any) => s + r.Liquido, 0))}
                        </td>
                        <td className="py-2 px-2 text-xs text-right font-bold text-blue-500 tabular-nums">
                          {formatCurrency(projectionChartData[projectionChartData.length - 1]?.['Saldo Acumulado'] ?? 0)}
                        </td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Empty projection fallback with KPIs from cashflow */}
          {projectionChartData.length === 0 && !loadingProjection && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <Card>
                <CardContent className="pt-6">
                  <div className="flex flex-col items-center text-center">
                    <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center mb-3">
                      <DollarSign className="w-5 h-5 text-blue-500" />
                    </div>
                    <p className="text-lg font-bold text-[hsl(var(--foreground))]">
                      {formatCurrency(Number(cashflow?.summary?.opening_balance ?? 0))}
                    </p>
                    <p className="text-xs text-[hsl(var(--muted-foreground))] mt-1">Saldo Inicial</p>
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-6">
                  <div className="flex flex-col items-center text-center">
                    <div className="w-10 h-10 rounded-lg bg-green-500/10 flex items-center justify-center mb-3">
                      <TrendingUp className="w-5 h-5 text-green-500" />
                    </div>
                    <p className="text-lg font-bold text-green-500">
                      {formatCurrency(Number(cashflow?.summary?.total_inflows ?? 0))}
                    </p>
                    <p className="text-xs text-[hsl(var(--muted-foreground))] mt-1">Entradas Previstas</p>
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-6">
                  <div className="flex flex-col items-center text-center">
                    <div className="w-10 h-10 rounded-lg bg-emerald-500/10 flex items-center justify-center mb-3">
                      <Activity className="w-5 h-5 text-emerald-500" />
                    </div>
                    <p className="text-lg font-bold text-[hsl(var(--foreground))]">
                      {formatCurrency(Number(cashflow?.summary?.closing_balance ?? 0))}
                    </p>
                    <p className="text-xs text-[hsl(var(--muted-foreground))] mt-1">Saldo Projetado</p>
                  </div>
                </CardContent>
              </Card>
            </div>
          )}
        </TabsContent>

        {/* ══════════════════════════════════════════
            TAB 4 — RELATÓRIO EXECUTIVO IA
        ══════════════════════════════════════════ */}
        <TabsContent value="executivo" className="space-y-6">
          {/* Period selector + Generate button */}
          <Card>
            <CardContent className="pt-6">
              <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
                <div className="flex-1">
                  <h2 className="font-display text-xl font-semibold text-[hsl(var(--foreground))]">
                    Relatório Executivo IA
                  </h2>
                  <p className="text-sm text-[hsl(var(--muted-foreground))] mt-1">
                    Análise financeira completa gerada automaticamente com dados reais do sistema.
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <input
                    type="month"
                    value={relatorioPeriodo}
                    onChange={(e) => setRelatorioPeriodo(e.target.value)}
                    className="border border-[hsl(var(--border))] rounded-lg px-3 py-2 text-sm bg-[hsl(var(--card))] text-[hsl(var(--foreground))] focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  <Button
                    onClick={loadRelatorio}
                    disabled={relatorioLoading}
                    className="bg-blue-600 hover:bg-blue-700 text-white"
                  >
                    {relatorioLoading ? (
                      <>
                        <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                        Gerando...
                      </>
                    ) : (
                      <>
                        <Brain className="w-4 h-4 mr-2" />
                        Gerar Relatório
                      </>
                    )}
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>

          {relatorio && (
            <>
              {/* Header do Relatório */}
              <Card className="border-l-4 border-l-blue-500">
                <CardContent className="pt-6">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <h3 className="text-lg font-bold text-[hsl(var(--foreground))]">{relatorio.titulo}</h3>
                      <p className="text-sm text-[hsl(var(--muted-foreground))] mt-1">
                        Gerado em {new Date(relatorio.gerado_em).toLocaleString('pt-BR')}
                      </p>
                    </div>
                    <div className="text-right">
                      <div className={`inline-flex items-center gap-2 px-4 py-2 rounded-full font-bold text-lg ${
                        relatorio.score_saude >= 80 ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' :
                        relatorio.score_saude >= 60 ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400' :
                        relatorio.score_saude >= 40 ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400' :
                        'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                      }`}>
                        <Star className="w-5 h-5" />
                        {relatorio.score_saude}/100
                      </div>
                      <p className="text-xs text-[hsl(var(--muted-foreground))] mt-1 capitalize">{relatorio.classificacao}</p>
                    </div>
                  </div>
                  <div className="mt-4 p-4 bg-[hsl(var(--muted))] rounded-lg">
                    <p className="text-sm text-[hsl(var(--foreground))] leading-relaxed">{relatorio.sumario_executivo}</p>
                  </div>
                </CardContent>
              </Card>

              {/* KPIs Grid */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {[
                  { label: 'Receita Realizada', value: relatorio.kpis.receita_realizada, icon: DollarSign, color: 'text-green-600' },
                  { label: 'Despesas', value: relatorio.kpis.despesas, icon: TrendingDown, color: 'text-red-600' },
                  { label: 'Saldo Líquido', value: relatorio.kpis.saldo_liquido, icon: Scale, color: relatorio.kpis.saldo_liquido >= 0 ? 'text-green-600' : 'text-red-600' },
                  { label: 'Margem', value: null, text: `${relatorio.kpis.margem_pct?.toFixed(1)}%`, icon: Activity, color: relatorio.kpis.margem_pct >= 15 ? 'text-green-600' : relatorio.kpis.margem_pct >= 5 ? 'text-yellow-600' : 'text-red-600' },
                ].map((kpi) => (
                  <Card key={kpi.label}>
                    <CardContent className="pt-4">
                      <div className="flex items-center gap-2 mb-1">
                        <kpi.icon className={`w-4 h-4 ${kpi.color}`} />
                        <span className="text-xs text-[hsl(var(--muted-foreground))]">{kpi.label}</span>
                      </div>
                      <p className={`text-lg font-bold ${kpi.color}`}>
                        {kpi.text ?? formatCurrency(kpi.value)}
                      </p>
                    </CardContent>
                  </Card>
                ))}
              </div>

              {/* Comparativo + Inadimplência */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Comparativo com Período Anterior</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {[
                      { label: 'Variação de Receita', value: relatorio.comparativo.variacao_receita_pct },
                      { label: 'Variação de Margem', value: relatorio.comparativo.variacao_margem_pct },
                    ].map((item) => (
                      <div key={item.label} className="flex items-center justify-between">
                        <span className="text-sm text-[hsl(var(--muted-foreground))]">{item.label}</span>
                        <span className={`font-bold text-sm flex items-center gap-1 ${
                          item.value > 0 ? 'text-green-600' : item.value < 0 ? 'text-red-600' : 'text-[hsl(var(--muted-foreground))]'
                        }`}>
                          {item.value > 0 ? <TrendingUp className="w-4 h-4" /> : item.value < 0 ? <TrendingDown className="w-4 h-4" /> : <Minus className="w-4 h-4" />}
                          {item.value > 0 ? '+' : ''}{item.value?.toFixed(1)}%
                        </span>
                      </div>
                    ))}
                    <div className="pt-2 border-t border-[hsl(var(--border))]">
                      <div className="flex justify-between text-sm">
                        <span className="text-[hsl(var(--muted-foreground))]">Receita anterior</span>
                        <span className="font-medium">{formatCurrency(relatorio.comparativo.receita_anterior)}</span>
                      </div>
                      <div className="flex justify-between text-sm mt-1">
                        <span className="text-[hsl(var(--muted-foreground))]">Margem anterior</span>
                        <span className="font-medium">{relatorio.comparativo.margem_anterior?.toFixed(1)}%</span>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Inadimplência do Período</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="flex items-center justify-between mb-3">
                      <span className="font-data text-2xl font-semibold tabular-nums" style={{ color: relatorio.kpis.inadimplencia_pct > 5 ? '#ef4444' : relatorio.kpis.inadimplencia_pct > 2 ? '#f97316' : '#22c55e' }}>
                        {relatorio.kpis.inadimplencia_pct?.toFixed(1)}%
                      </span>
                      <Badge variant={relatorio.kpis.inadimplencia_pct > 5 ? 'destructive' : 'outline'}>
                        {relatorio.kpis.inadimplencia_pct > 5 ? 'Crítico' : relatorio.kpis.inadimplencia_pct > 2 ? 'Atenção' : 'Normal'}
                      </Badge>
                    </div>
                    <p className="text-sm text-[hsl(var(--muted-foreground))]">
                      {relatorio.kpis.qtd_inadimplentes} cliente(s) com R$ {formatCurrency(relatorio.kpis.inadimplencia_valor)} em atraso
                    </p>
                    <div className="mt-3 bg-[hsl(var(--muted))] rounded-full h-2">
                      <div
                        className="h-2 rounded-full transition-all"
                        style={{
                          width: `${Math.min(relatorio.kpis.inadimplencia_pct * 10, 100)}%`,
                          backgroundColor: relatorio.kpis.inadimplencia_pct > 5 ? '#ef4444' : relatorio.kpis.inadimplencia_pct > 2 ? '#f97316' : '#22c55e'
                        }}
                      />
                    </div>
                  </CardContent>
                </Card>
              </div>

              {/* Destaques e Pontos de Atenção */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {relatorio.destaques?.length > 0 && (
                  <Card className="border-green-200 dark:border-green-800">
                    <CardHeader>
                      <CardTitle className="text-base text-green-700 dark:text-green-400 flex items-center gap-2">
                        <CheckCircle className="w-5 h-5" />
                        Destaques Positivos
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      {relatorio.destaques.map((d: any, i: number) => (
                        <div key={i} className="flex items-start gap-3 p-3 bg-green-50 dark:bg-green-900/20 rounded-lg">
                          <span className="text-xl">{d.icone}</span>
                          <div>
                            <p className="font-medium text-sm text-[hsl(var(--foreground))]">{d.titulo}</p>
                            <p className="text-xs text-[hsl(var(--muted-foreground))] mt-0.5">{d.descricao}</p>
                          </div>
                        </div>
                      ))}
                    </CardContent>
                  </Card>
                )}

                <Card className={relatorio.pontos_atencao?.some((p: any) => p.nivel === 'critico') ? 'border-red-200 dark:border-red-800' : 'border-yellow-200 dark:border-yellow-800'}>
                  <CardHeader>
                    <CardTitle className={`text-base flex items-center gap-2 ${
                      relatorio.pontos_atencao?.some((p: any) => p.nivel === 'critico')
                        ? 'text-red-700 dark:text-red-400'
                        : 'text-yellow-700 dark:text-yellow-400'
                    }`}>
                      <AlertTriangle className="w-5 h-5" />
                      Pontos de Atenção
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {relatorio.pontos_atencao?.map((p: any, i: number) => (
                      <div key={i} className={`flex items-start gap-3 p-3 rounded-lg ${
                        p.nivel === 'critico' ? 'bg-red-50 dark:bg-red-900/20' :
                        p.nivel === 'alerta' ? 'bg-yellow-50 dark:bg-yellow-900/20' :
                        'bg-green-50 dark:bg-green-900/20'
                      }`}>
                        <span className="text-xl">{p.icone}</span>
                        <div className="flex-1">
                          <p className="font-medium text-sm text-[hsl(var(--foreground))]">{p.titulo}</p>
                          <p className="text-xs text-[hsl(var(--muted-foreground))] mt-0.5">{p.descricao}</p>
                          <p className="text-xs font-medium text-blue-600 dark:text-blue-400 mt-1">→ {p.acao}</p>
                        </div>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              </div>

              {/* Recomendações Prioritárias */}
              {relatorio.recomendacoes_prioritarias?.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base flex items-center gap-2">
                      <FileText className="w-5 h-5 text-blue-600" />
                      Recomendações Prioritárias
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {relatorio.recomendacoes_prioritarias.map((rec: any, i: number) => (
                      <div key={i} className="flex items-start gap-4 p-4 border border-[hsl(var(--border))] rounded-lg">
                        <div className={`w-8 h-8 rounded-full flex items-center justify-center font-bold text-sm flex-shrink-0 ${
                          rec.prioridade <= 1 ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' :
                          rec.prioridade <= 2 ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400' :
                          'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
                        }`}>
                          {i + 1}
                        </div>
                        <div className="flex-1">
                          <div className="flex items-start justify-between gap-2">
                            <p className="font-medium text-sm text-[hsl(var(--foreground))]">{rec.titulo}</p>
                            <Badge variant="outline" className="text-xs flex-shrink-0">{rec.prazo_sugerido}</Badge>
                          </div>
                          <p className="text-xs text-[hsl(var(--muted-foreground))] mt-1">{rec.descricao}</p>
                          {rec.impacto_estimado > 0 && (
                            <p className="text-xs text-green-600 dark:text-green-400 mt-1 font-medium">
                              Impacto estimado: {formatCurrency(rec.impacto_estimado)}
                            </p>
                          )}
                          <p className="text-xs font-medium text-blue-600 dark:text-blue-400 mt-1">→ {rec.acao}</p>
                        </div>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              )}
            </>
          )}

          {!relatorio && !relatorioLoading && (
            <div className="text-center py-16 text-[hsl(var(--muted-foreground))]">
              <Brain className="w-16 h-16 mx-auto mb-4 opacity-30" />
              <p className="text-lg font-medium">Selecione o período e clique em "Gerar Relatório"</p>
              <p className="text-sm mt-1">O relatório executivo consolida todos os dados financeiros do mês.</p>
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
