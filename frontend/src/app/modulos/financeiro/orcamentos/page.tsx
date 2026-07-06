'use client';

import {
  Target,
  ArrowLeft,
  Download,
  TrendingUp,
  TrendingDown,
  Minus,
  Pencil,
  Check,
  X,
  DollarSign,
  BarChart2,
  PieChart as PieChartIcon,
  CalendarDays,
} from 'lucide-react';
import { useState, useEffect, useCallback, useRef } from 'react';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
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
  useCashflowEntries,
  useFinancialOverview,
  useCashflowForecast,
} from '@/hooks/financial/useFinancial';
import { CashFlowEntryType } from '@/types/generated/financial/models/cashFlowEntryType';
import { useCondominio } from '@/contexts/CondominioContext';

// ─── Constants ────────────────────────────────────────────────────────────────

const MONTHS = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];

const CHART_COLORS = [
  '#6366f1', '#f97707', '#10b981', '#3b82f6', '#f59e0b',
  '#ec4899', '#8b5cf6', '#14b8a6', '#ef4444', '#84cc16',
];

// ─── Helpers ──────────────────────────────────────────────────────────────────

const formatCurrency = (value: number | undefined | null) => {
  if (value == null) return 'R$ 0,00';
  return value.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
};

const formatPct = (value: number) => {
  if (!isFinite(value)) return '—';
  return `${value.toFixed(1)}%`;
};

// ─── Custom Tooltip for recharts ──────────────────────────────────────────────

const CurrencyTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg shadow-lg p-3 text-sm">
      <p className="font-semibold text-slate-700 dark:text-slate-300 mb-1">{label}</p>
      {payload.map((entry: any, i: number) => (
        <p key={i} style={{ color: entry.color }} className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full inline-block" style={{ background: entry.color }} />
          {entry.name}: {formatCurrency(entry.value)}
        </p>
      ))}
    </div>
  );
};

// ─── Inline editable cell ─────────────────────────────────────────────────────

interface EditableCellProps {
  value: number;
  onSave: (val: number) => void;
}

function EditableCell({ value, onSave }: EditableCellProps) {
  const [editing, setEditing] = useState(false);
  const [inputVal, setInputVal] = useState(String(value));
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing) {
      setInputVal(String(value));
      setTimeout(() => inputRef.current?.select(), 30);
    }
  }, [editing, value]);

  const commit = () => {
    const num = parseFloat(inputVal.replace(',', '.'));
    if (!isNaN(num) && num >= 0) onSave(num);
    setEditing(false);
  };

  const cancel = () => setEditing(false);

  if (editing) {
    return (
      <div className="flex items-center gap-1">
        <Input
          ref={inputRef}
          value={inputVal}
          onChange={e => setInputVal(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter') commit();
            if (e.key === 'Escape') cancel();
          }}
          onBlur={commit}
          className="h-7 w-32 text-right text-sm py-0 px-2"
        />
        <button type="button" onClick={commit} className="text-green-500 hover:text-green-600"><Check size={14} /></button>
        <button type="button" onClick={cancel} className="text-red-400 hover:text-red-500"><X size={14} /></button>
      </div>
    );
  }

  return (
    <button
      onClick={() => setEditing(true)}
      className="group flex items-center gap-1 hover:text-indigo-600 transition-colors"
    >
      <span>{formatCurrency(value)}</span>
      <Pencil size={12} className="opacity-0 group-hover:opacity-60 transition-opacity" />
    </button>
  );
}

// ─── Status badge helper ───────────────────────────────────────────────────────

function BudgetStatusBadge({ pct }: { pct: number }) {
  if (pct > 100) return <Badge className="bg-red-500/10 text-red-500 border-red-500/20 border text-xs">Acima</Badge>;
  if (pct > 80) return <Badge className="bg-yellow-500/10 text-yellow-500 border-yellow-500/20 border text-xs">Atenção</Badge>;
  return <Badge className="bg-green-500/10 text-green-500 border-green-500/20 border text-xs">No orçamento</Badge>;
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function OrcamentosPage() {
  const { condominioId } = useCondominio();
  // ── Budget state persisted to localStorage ──────────────────────────────────
  const [budgets, setBudgets] = useState<Record<string, number>>(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('financeiro_budgets');
      return saved ? JSON.parse(saved) : {};
    }
    return {};
  });

  const saveBudget = useCallback((key: string, value: number) => {
    setBudgets(prev => {
      const next = { ...prev, [key]: value };
      if (typeof window !== 'undefined') {
        localStorage.setItem('financeiro_budgets', JSON.stringify(next));
      }
      return next;
    });
  }, []);

  // ── Data hooks ──────────────────────────────────────────────────────────────
  const { data: expensesRaw, isLoading: loadingExpenses } = useCashflowEntries({
    condominio_id: condominioId,
    limit: 200,
    entry_type: CashFlowEntryType.saida,
  });
  const { data: incomeRaw, isLoading: loadingIncome } = useCashflowEntries({
    condominio_id: condominioId,
    limit: 200,
    entry_type: CashFlowEntryType.entrada,
  });
  const { data: overviewRaw, isLoading: loadingOverview } = useFinancialOverview({ condominio_id: condominioId });
  const { data: forecastsRaw } = useCashflowForecast({ condominio_id: condominioId, limit: 12 });

  const isLoading = loadingExpenses || loadingIncome || loadingOverview;

  const expenses: any[] = (expensesRaw as any)?.items ?? [];
  const incomes: any[] = (incomeRaw as any)?.items ?? [];
  const overview = overviewRaw as any;
  const forecasts: any[] = Array.isArray(forecastsRaw) ? forecastsRaw : (forecastsRaw as any)?.items ?? [];

  // ── Current year ────────────────────────────────────────────────────────────
  const currentYear = new Date().getFullYear();
  const currentMonthIdx = new Date().getMonth(); // 0-based

  // ── Monthly actual expenses ──────────────────────────────────────────────────
  const monthlyActual = MONTHS.map((_, idx) => {
    return expenses
      .filter(e => {
        const d = new Date(e.entry_date ?? e.date ?? e.created_at ?? '');
        return d.getFullYear() === currentYear && d.getMonth() === idx;
      })
      .reduce((sum: number, e: any) => sum + (Number(e.expected_amount ?? e.amount) || 0), 0);
  });

  const monthlyIncome = MONTHS.map((_, idx) => {
    return incomes
      .filter(e => {
        const d = new Date(e.entry_date ?? e.date ?? e.created_at ?? '');
        return d.getFullYear() === currentYear && d.getMonth() === idx;
      })
      .reduce((sum: number, e: any) => sum + (Number(e.expected_amount ?? e.amount) || 0), 0);
  });

  // ── Budget for each month (forecasts.expected_inflows → localStorage → auto-estimate) ──
  const getForecastForMonth = (monthIdx: number) => {
    const f = forecasts.find((fc: any) => {
      const d = new Date(fc.period_start ?? fc.forecast_date ?? '');
      return d.getFullYear() === currentYear && d.getMonth() === monthIdx;
    });
    return f ? Number(f.expected_inflows ?? 0) : null;
  };

  const getBudgetForMonth = (monthIdx: number) => {
    const key = `month_${currentYear}_${monthIdx}`;
    if (budgets[key] != null) return budgets[key];
    const forecastVal = getForecastForMonth(monthIdx);
    if (forecastVal != null && forecastVal > 0) return forecastVal;
    // Default: avg of last 3 months or 0
    if (monthIdx === 0) return (monthlyActual[0] ?? 0) * 1.1 || 0;
    const prevAvg =
      monthlyActual.slice(Math.max(0, monthIdx - 3), monthIdx).reduce((s, v) => s + v, 0) /
      Math.min(3, monthIdx);
    return Math.round(prevAvg * 1.1);
  };

  // ── Annual chart data ────────────────────────────────────────────────────────
  let cumulativeVariance = 0;
  const annualData = MONTHS.map((month, idx) => {
    const budgeted = getBudgetForMonth(idx);
    const actual = monthlyActual[idx] ?? 0;
    const variance = budgeted - actual;
    cumulativeVariance += variance;
    const execPct = budgeted > 0 ? (actual / budgeted) * 100 : 0;
    return { month, budgeted, actual, variance, cumulativeVariance, execPct };
  });

  // ── KPI totals ───────────────────────────────────────────────────────────────
  const totalBudgeted = annualData.reduce((s, r) => s + (r.budgeted ?? 0), 0);
  const totalActual = annualData.reduce((s, r) => s + (r.actual ?? 0), 0);
  const totalVariance = totalBudgeted - totalActual;
  const totalExecPct = totalBudgeted > 0 ? (totalActual / totalBudgeted) * 100 : 0;

  // ── Category breakdown ───────────────────────────────────────────────────────
  const categoryMap: Record<string, number> = {};
  expenses.forEach((e: any) => {
    const cat = e.category || e.category_name || 'Sem categoria';
    categoryMap[cat] = (categoryMap[cat] || 0) + (Number(e.expected_amount ?? e.amount) || 0);
  });

  const categoryData = Object.entries(categoryMap)
    .sort(([, a], [, b]) => b - a)
    .map(([name, actual], idx) => {
      const key = `cat_${name}`;
      const budgeted = budgets[key] ?? Math.round(actual * 1.2);
      const variance = budgeted - actual;
      const pct = budgeted > 0 ? (actual / budgeted) * 100 : 0;
      return { name, actual, budgeted, variance, pct, colorIdx: idx };
    });

  // ── Projection data (next 6 months) ─────────────────────────────────────────
  const last3Avg =
    monthlyActual.slice(Math.max(0, currentMonthIdx - 2), currentMonthIdx + 1).reduce((s, v) => s + v, 0) /
    3;

  const last6Avg =
    monthlyActual.slice(Math.max(0, currentMonthIdx - 5), currentMonthIdx + 1).reduce((s, v) => s + v, 0) /
    6;

  const trend = last3Avg > last6Avg * 1.05 ? 'up' : last3Avg < last6Avg * 0.95 ? 'down' : 'stable';

  const projectionData = MONTHS.map((month, idx) => {
    if (idx <= currentMonthIdx) {
      return {
        month,
        actual: monthlyActual[idx],
        projetado: null,
        receita: monthlyIncome[idx],
      };
    }
    const monthsAhead = idx - currentMonthIdx;
    const growth = trend === 'up' ? 1.03 : trend === 'down' ? 0.97 : 1.0;
    const projected = last3Avg * Math.pow(growth, monthsAhead);
    return {
      month,
      actual: null,
      projetado: Math.round(projected),
      receita: null,
    };
  });

  // ── Export handler (placeholder) ─────────────────────────────────────────────
  const handleExport = () => {
    const rows = [
      ['Mês', 'Orçado', 'Realizado', 'Variação', '% Exec'],
      ...annualData.map(r => [
        r.month,
        (r.budgeted ?? 0).toFixed(2),
        (r.actual ?? 0).toFixed(2),
        (r.variance ?? 0).toFixed(2),
        (r.execPct ?? 0).toFixed(1) + '%',
      ]),
    ];
    const csv = rows.map(r => r.join(';')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `orcamentos_${currentYear}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // ── Trend icon ───────────────────────────────────────────────────────────────
  const TrendIcon = trend === 'up'
    ? <TrendingUp size={16} className="text-red-500" />
    : trend === 'down'
    ? <TrendingDown size={16} className="text-green-500" />
    : <Minus size={16} className="text-slate-400" />;

  // ── Loading skeleton ─────────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-50 dark:bg-slate-900">
        <div className="h-16 bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 animate-pulse" />
        <div className="p-6 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-28 bg-white dark:bg-slate-800 rounded-xl animate-pulse" />
          ))}
        </div>
        <div className="px-6">
          <div className="h-96 bg-white dark:bg-slate-800 rounded-xl animate-pulse" />
        </div>
      </div>
    );
  }

  // ────────────────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900">
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-50 bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 shadow-sm">
        <div className="flex items-center justify-between px-4 sm:px-6 h-16">
          <div className="flex items-center gap-3">
            <Link
              href="/modulos/financeiro"
              className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 transition-colors"
            >
              <ArrowLeft size={18} />
            </Link>
            <div className="flex items-center gap-2">
              <div className="p-2 rounded-lg bg-indigo-500/10">
                <Target size={20} className="text-indigo-500" />
              </div>
              <div>
                <h1 className="text-base font-semibold text-slate-800 dark:text-slate-100 leading-tight">
                  Orçamentos
                </h1>
                <p className="text-xs text-slate-500 dark:text-slate-400 leading-tight hidden sm:block">
                  Planejamento e controle orçamentário
                </p>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={handleExport} className="gap-2">
              <Download size={15} />
              <span className="hidden sm:inline">Exportar</span>
            </Button>
          </div>
        </div>
      </header>

      <div className="p-4 sm:p-6 space-y-6">
        {/* ── KPI Cards ──────────────────────────────────────────────────────── */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Orçado Total */}
          <Card className="border-0 shadow-sm bg-white dark:bg-slate-800">
            <CardContent className="p-4 sm:p-5">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">Orçado Total</p>
                  <p className="font-data text-xl sm:text-2xl font-semibold tabular-nums text-slate-800 dark:text-slate-100">
                    {formatCurrency(totalBudgeted)}
                  </p>
                  <p className="text-xs text-slate-400 mt-1">{currentYear}</p>
                </div>
                <div className="p-2 rounded-lg bg-indigo-500/10">
                  <DollarSign size={18} className="text-indigo-500" />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Realizado */}
          <Card className="border-0 shadow-sm bg-white dark:bg-slate-800">
            <CardContent className="p-4 sm:p-5">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">Realizado</p>
                  <p className="font-data text-xl sm:text-2xl font-semibold tabular-nums text-slate-800 dark:text-slate-100">
                    {formatCurrency(totalActual)}
                  </p>
                  <p className="text-xs text-slate-400 mt-1">Despesas acumuladas</p>
                </div>
                <div className="p-2 rounded-lg bg-orange-500/10">
                  <BarChart2 size={18} className="text-orange-500" />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Variação */}
          <Card className="border-0 shadow-sm bg-white dark:bg-slate-800">
            <CardContent className="p-4 sm:p-5">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">Variação</p>
                  <p className={`font-data text-xl sm:text-2xl font-semibold tabular-nums ${totalVariance >= 0 ? 'text-green-600' : 'text-red-500'}`}>
                    {formatCurrency(Math.abs(totalVariance))}
                  </p>
                  <p className={`text-xs mt-1 font-medium ${totalVariance >= 0 ? 'text-green-500' : 'text-red-400'}`}>
                    {totalVariance >= 0 ? '▼ Abaixo do orçamento' : '▲ Acima do orçamento'}
                  </p>
                </div>
                <div className={`p-2 rounded-lg ${totalVariance >= 0 ? 'bg-green-500/10' : 'bg-red-500/10'}`}>
                  {totalVariance >= 0
                    ? <TrendingDown size={18} className="text-green-500" />
                    : <TrendingUp size={18} className="text-red-500" />}
                </div>
              </div>
            </CardContent>
          </Card>

          {/* % Execução */}
          <Card className="border-0 shadow-sm bg-white dark:bg-slate-800">
            <CardContent className="p-4 sm:p-5">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">% Execução</p>
                  <p className={`font-data text-xl sm:text-2xl font-semibold tabular-nums ${totalExecPct > 100 ? 'text-red-500' : totalExecPct > 80 ? 'text-yellow-500' : 'text-green-600'}`}>
                    {formatPct(totalExecPct)}
                  </p>
                  <div className="mt-2 h-1.5 w-full bg-slate-100 dark:bg-slate-700 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${totalExecPct > 100 ? 'bg-red-500' : totalExecPct > 80 ? 'bg-yellow-500' : 'bg-green-500'}`}
                      style={{ width: `${Math.min(totalExecPct, 100)}%` }}
                    />
                  </div>
                </div>
                <div className="p-2 rounded-lg bg-blue-500/10">
                  <Target size={18} className="text-blue-500" />
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* ── Tabs ───────────────────────────────────────────────────────────── */}
        <Tabs defaultValue="anual" className="space-y-4">
          <TabsList className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 p-1 h-auto flex-wrap gap-1">
            <TabsTrigger value="anual" className="gap-2 text-sm data-[state=active]:bg-indigo-500 data-[state=active]:text-white">
              <CalendarDays size={15} />
              Resumo Anual
            </TabsTrigger>
            <TabsTrigger value="categoria" className="gap-2 text-sm data-[state=active]:bg-indigo-500 data-[state=active]:text-white">
              <PieChartIcon size={15} />
              Por Categoria
            </TabsTrigger>
            <TabsTrigger value="projecao" className="gap-2 text-sm data-[state=active]:bg-indigo-500 data-[state=active]:text-white">
              <TrendingUp size={15} />
              Projeção
            </TabsTrigger>
          </TabsList>

          {/* ─── Tab 1: Resumo Anual ──────────────────────────────────────────── */}
          <TabsContent value="anual" className="space-y-4">
            <Card className="border-0 shadow-sm bg-white dark:bg-slate-800">
              <CardHeader className="pb-2 pt-4 px-5">
                <CardTitle className="text-sm font-semibold text-slate-700 dark:text-slate-300 flex items-center gap-2">
                  <BarChart2 size={16} className="text-indigo-500" />
                  Orçado vs. Realizado — {currentYear}
                </CardTitle>
                <p className="text-xs text-slate-400">Clique nos valores orçados para editar</p>
              </CardHeader>
              <CardContent className="px-2 pb-4">
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={annualData} margin={{ top: 8, right: 20, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                    <YAxis
                      tick={{ fontSize: 11 }}
                      tickFormatter={v => `${(v / 1000).toFixed(0)}k`}
                      width={48}
                    />
                    <Tooltip content={<CurrencyTooltip />} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Bar dataKey="budgeted" name="Orçado" fill="#6366f1" radius={[3, 3, 0, 0]} />
                    <Bar dataKey="actual" name="Realizado" fill="#f97707" radius={[3, 3, 0, 0]} />
                    <Bar dataKey="cumulativeVariance" name="Variação Acum." fill="#10b981" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            <Card className="border-0 shadow-sm bg-white dark:bg-slate-800">
              <CardContent className="p-0">
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow className="border-slate-100 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/80">
                        <TableHead className="text-xs font-semibold text-slate-600 dark:text-slate-400 w-16">Mês</TableHead>
                        <TableHead className="text-xs font-semibold text-slate-600 dark:text-slate-400">Orçado</TableHead>
                        <TableHead className="text-xs font-semibold text-slate-600 dark:text-slate-400">Realizado</TableHead>
                        <TableHead className="text-xs font-semibold text-slate-600 dark:text-slate-400">Variação</TableHead>
                        <TableHead className="text-xs font-semibold text-slate-600 dark:text-slate-400 w-24">% Exec</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {annualData.map((row, idx) => {
                        const isFuture = idx > currentMonthIdx;
                        const isCurrent = idx === currentMonthIdx;
                        return (
                          <TableRow
                            key={row.month}
                            className={`border-slate-100 dark:border-slate-700 transition-colors ${isCurrent ? 'bg-indigo-50/60 dark:bg-indigo-900/20' : 'hover:bg-slate-50 dark:hover:bg-slate-700/40'}`}
                          >
                            <TableCell className="py-2.5">
                              <div className="flex items-center gap-1.5">
                                <span className="text-sm font-medium text-slate-700 dark:text-slate-300">{row.month}</span>
                                {isCurrent && (
                                  <span className="text-[10px] font-semibold text-indigo-500 bg-indigo-100 dark:bg-indigo-900/40 px-1.5 py-0.5 rounded">atual</span>
                                )}
                              </div>
                            </TableCell>
                            <TableCell className="py-2.5">
                              <EditableCell
                                value={getBudgetForMonth(idx)}
                                onSave={val => saveBudget(`month_${currentYear}_${idx}`, val)}
                              />
                            </TableCell>
                            <TableCell className={`py-2.5 text-sm ${isFuture ? 'text-slate-300 dark:text-slate-600' : 'text-slate-700 dark:text-slate-300'}`}>
                              {isFuture ? '—' : formatCurrency(row.actual)}
                            </TableCell>
                            <TableCell className={`py-2.5 text-sm font-medium ${row.variance >= 0 ? 'text-green-600' : 'text-red-500'}`}>
                              {isFuture ? '—' : (row.variance >= 0 ? '+' : '') + formatCurrency(row.variance)}
                            </TableCell>
                            <TableCell className="py-2.5">
                              {isFuture ? (
                                <span className="text-slate-300 dark:text-slate-600 text-sm">—</span>
                              ) : (
                                <div className="flex items-center gap-2">
                                  <div className="flex-1 h-1.5 bg-slate-100 dark:bg-slate-700 rounded-full overflow-hidden min-w-[40px]">
                                    <div
                                      className={`h-full rounded-full ${row.execPct > 100 ? 'bg-red-500' : row.execPct > 80 ? 'bg-yellow-400' : 'bg-green-500'}`}
                                      style={{ width: `${Math.min(row.execPct, 100)}%` }}
                                    />
                                  </div>
                                  <span className={`text-xs font-medium w-10 text-right ${row.execPct > 100 ? 'text-red-500' : row.execPct > 80 ? 'text-yellow-500' : 'text-green-600'}`}>
                                    {formatPct(row.execPct)}
                                  </span>
                                </div>
                              )}
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* ─── Tab 2: Por Categoria ─────────────────────────────────────────── */}
          <TabsContent value="categoria" className="space-y-4">
            {categoryData.length === 0 ? (
              <Card className="border-0 shadow-sm bg-white dark:bg-slate-800">
                <CardContent className="py-16 text-center">
                  <PieChartIcon size={40} className="mx-auto text-slate-300 dark:text-slate-600 mb-3" />
                  <p className="text-slate-500 dark:text-slate-400 text-sm">
                    Nenhum lançamento de despesa encontrado para categorizar.
                  </p>
                </CardContent>
              </Card>
            ) : (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Pie Chart */}
                <Card className="border-0 shadow-sm bg-white dark:bg-slate-800">
                  <CardHeader className="pb-2 pt-4 px-5">
                    <CardTitle className="text-sm font-semibold text-slate-700 dark:text-slate-300 flex items-center gap-2">
                      <PieChartIcon size={16} className="text-indigo-500" />
                      Distribuição por Categoria
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="pb-4">
                    <ResponsiveContainer width="100%" height={280}>
                      <PieChart>
                        <Pie
                          data={categoryData}
                          dataKey="actual"
                          nameKey="name"
                          cx="50%"
                          cy="50%"
                          outerRadius={100}
                          innerRadius={50}
                          paddingAngle={2}
                          label={({ name, percent }: { name?: string; percent?: number }) =>
                            (percent ?? 0) > 0.05 ? `${(name ?? '').split(' ')[0]} ${((percent ?? 0) * 100).toFixed(0)}%` : ''
                          }
                          labelLine={false}
                        >
                          {categoryData.map((entry, i) => (
                            <Cell key={`cell-${i}`} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                          ))}
                        </Pie>
                        <Tooltip
                          formatter={(value: any) => formatCurrency(value)}
                        />
                        <Legend wrapperStyle={{ fontSize: 11 }} />
                      </PieChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>

                {/* Category Table */}
                <Card className="border-0 shadow-sm bg-white dark:bg-slate-800">
                  <CardHeader className="pb-2 pt-4 px-5">
                    <CardTitle className="text-sm font-semibold text-slate-700 dark:text-slate-300 flex items-center gap-2">
                      <BarChart2 size={16} className="text-indigo-500" />
                      Controle por Categoria
                    </CardTitle>
                    <p className="text-xs text-slate-400">Clique nos valores orçados para editar</p>
                  </CardHeader>
                  <CardContent className="p-0">
                    <div className="overflow-x-auto max-h-72 overflow-y-auto">
                      <Table>
                        <TableHeader>
                          <TableRow className="border-slate-100 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/80 sticky top-0">
                            <TableHead className="text-xs font-semibold text-slate-600 dark:text-slate-400">Categoria</TableHead>
                            <TableHead className="text-xs font-semibold text-slate-600 dark:text-slate-400">Orçado</TableHead>
                            <TableHead className="text-xs font-semibold text-slate-600 dark:text-slate-400">Realizado</TableHead>
                            <TableHead className="text-xs font-semibold text-slate-600 dark:text-slate-400 text-center">Status</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {categoryData.map((cat) => (
                            <TableRow
                              key={cat.name}
                              className="border-slate-100 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700/40 transition-colors"
                            >
                              <TableCell className="py-2.5">
                                <div className="flex items-center gap-2">
                                  <span
                                    className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                                    style={{ background: CHART_COLORS[cat.colorIdx % CHART_COLORS.length] }}
                                  />
                                  <span className="text-sm text-slate-700 dark:text-slate-300 truncate max-w-[120px]">
                                    {cat.name}
                                  </span>
                                </div>
                              </TableCell>
                              <TableCell className="py-2.5">
                                <EditableCell
                                  value={cat.budgeted}
                                  onSave={val => saveBudget(`cat_${cat.name}`, val)}
                                />
                              </TableCell>
                              <TableCell className="py-2.5 text-sm text-slate-700 dark:text-slate-300">
                                {formatCurrency(cat.actual)}
                              </TableCell>
                              <TableCell className="py-2.5 text-center">
                                <BudgetStatusBadge pct={cat.pct} />
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  </CardContent>
                </Card>
              </div>
            )}
          </TabsContent>

          {/* ─── Tab 3: Projeção ──────────────────────────────────────────────── */}
          <TabsContent value="projecao" className="space-y-4">
            {/* Trend summary */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <Card className="border-0 shadow-sm bg-white dark:bg-slate-800">
                <CardContent className="p-4 flex items-center gap-3">
                  <div className="p-2.5 rounded-lg bg-blue-500/10">
                    <BarChart2 size={18} className="text-blue-500" />
                  </div>
                  <div>
                    <p className="text-xs text-slate-500 dark:text-slate-400">Média últimos 3 meses</p>
                    <p className="text-lg font-bold text-slate-800 dark:text-slate-100">{formatCurrency(last3Avg)}</p>
                  </div>
                </CardContent>
              </Card>
              <Card className="border-0 shadow-sm bg-white dark:bg-slate-800">
                <CardContent className="p-4 flex items-center gap-3">
                  <div className="p-2.5 rounded-lg bg-purple-500/10">
                    <CalendarDays size={18} className="text-purple-500" />
                  </div>
                  <div>
                    <p className="text-xs text-slate-500 dark:text-slate-400">Média últimos 6 meses</p>
                    <p className="text-lg font-bold text-slate-800 dark:text-slate-100">{formatCurrency(last6Avg)}</p>
                  </div>
                </CardContent>
              </Card>
              <Card className="border-0 shadow-sm bg-white dark:bg-slate-800">
                <CardContent className="p-4 flex items-center gap-3">
                  <div className={`p-2.5 rounded-lg ${trend === 'up' ? 'bg-red-500/10' : trend === 'down' ? 'bg-green-500/10' : 'bg-slate-200/60'}`}>
                    {TrendIcon}
                  </div>
                  <div>
                    <p className="text-xs text-slate-500 dark:text-slate-400">Tendência</p>
                    <p className={`text-lg font-bold ${trend === 'up' ? 'text-red-500' : trend === 'down' ? 'text-green-600' : 'text-slate-500'}`}>
                      {trend === 'up' ? 'Crescente' : trend === 'down' ? 'Decrescente' : 'Estável'}
                    </p>
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Area chart */}
            <Card className="border-0 shadow-sm bg-white dark:bg-slate-800">
              <CardHeader className="pb-2 pt-4 px-5">
                <CardTitle className="text-sm font-semibold text-slate-700 dark:text-slate-300 flex items-center gap-2">
                  <TrendingUp size={16} className="text-indigo-500" />
                  Despesas Realizadas + Projeção — {currentYear}
                </CardTitle>
                <p className="text-xs text-slate-400">
                  Área sólida = realizado · Área pontilhada = projeção baseada nos últimos 3 meses
                </p>
              </CardHeader>
              <CardContent className="px-2 pb-4">
                <ResponsiveContainer width="100%" height={300}>
                  <AreaChart data={projectionData} margin={{ top: 8, right: 20, left: 0, bottom: 0 }}>
                    <defs>
                      <linearGradient id="actualGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                      </linearGradient>
                      <linearGradient id="projGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#f97707" stopOpacity={0.2} />
                        <stop offset="95%" stopColor="#f97707" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                    <YAxis
                      tick={{ fontSize: 11 }}
                      tickFormatter={v => `${(v / 1000).toFixed(0)}k`}
                      width={48}
                    />
                    <Tooltip content={<CurrencyTooltip />} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Area
                      type="monotone"
                      dataKey="actual"
                      name="Realizado"
                      stroke="#6366f1"
                      strokeWidth={2}
                      fill="url(#actualGrad)"
                      connectNulls={false}
                      dot={{ r: 3, fill: '#6366f1' }}
                    />
                    <Area
                      type="monotone"
                      dataKey="projetado"
                      name="Projetado"
                      stroke="#f97707"
                      strokeWidth={2}
                      strokeDasharray="5 3"
                      fill="url(#projGrad)"
                      connectNulls={false}
                      dot={{ r: 3, fill: '#f97707' }}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            {/* Projection table */}
            <Card className="border-0 shadow-sm bg-white dark:bg-slate-800">
              <CardHeader className="pb-2 pt-4 px-5">
                <CardTitle className="text-sm font-semibold text-slate-700 dark:text-slate-300">
                  Detalhamento Mensal
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow className="border-slate-100 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/80">
                        <TableHead className="text-xs font-semibold text-slate-600 dark:text-slate-400 w-16">Mês</TableHead>
                        <TableHead className="text-xs font-semibold text-slate-600 dark:text-slate-400">Realizado</TableHead>
                        <TableHead className="text-xs font-semibold text-slate-600 dark:text-slate-400">Projetado</TableHead>
                        <TableHead className="text-xs font-semibold text-slate-600 dark:text-slate-400 text-center">Tendência</TableHead>
                        <TableHead className="text-xs font-semibold text-slate-600 dark:text-slate-400">Tipo</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {projectionData.map((row, idx) => {
                        const isFuture = idx > currentMonthIdx;
                        const isCurrent = idx === currentMonthIdx;
                        const prevActual = idx > 0 ? monthlyActual[idx - 1] : null;
                        const thisVal = row.actual ?? row.projetado ?? 0;
                        const rowTrend = prevActual == null
                          ? 'stable'
                          : thisVal > prevActual * 1.03
                          ? 'up'
                          : thisVal < prevActual * 0.97
                          ? 'down'
                          : 'stable';

                        return (
                          <TableRow
                            key={row.month}
                            className={`border-slate-100 dark:border-slate-700 transition-colors ${isCurrent ? 'bg-indigo-50/60 dark:bg-indigo-900/20' : 'hover:bg-slate-50 dark:hover:bg-slate-700/40'}`}
                          >
                            <TableCell className="py-2.5">
                              <div className="flex items-center gap-1.5">
                                <span className="text-sm font-medium text-slate-700 dark:text-slate-300">{row.month}</span>
                                {isCurrent && (
                                  <span className="text-[10px] font-semibold text-indigo-500 bg-indigo-100 dark:bg-indigo-900/40 px-1.5 py-0.5 rounded">atual</span>
                                )}
                              </div>
                            </TableCell>
                            <TableCell className="py-2.5 text-sm text-slate-700 dark:text-slate-300">
                              {row.actual != null ? formatCurrency(row.actual) : <span className="text-slate-300 dark:text-slate-600">—</span>}
                            </TableCell>
                            <TableCell className="py-2.5 text-sm text-orange-600 dark:text-orange-400 font-medium">
                              {row.projetado != null ? formatCurrency(row.projetado) : <span className="text-slate-300 dark:text-slate-600">—</span>}
                            </TableCell>
                            <TableCell className="py-2.5 text-center">
                              {rowTrend === 'up' ? (
                                <span className="inline-flex items-center gap-0.5 text-red-500 text-xs font-semibold">
                                  <TrendingUp size={13} /> Subindo
                                </span>
                              ) : rowTrend === 'down' ? (
                                <span className="inline-flex items-center gap-0.5 text-green-600 text-xs font-semibold">
                                  <TrendingDown size={13} /> Caindo
                                </span>
                              ) : (
                                <span className="inline-flex items-center gap-0.5 text-slate-400 text-xs font-semibold">
                                  <Minus size={13} /> Estável
                                </span>
                              )}
                            </TableCell>
                            <TableCell className="py-2.5">
                              {isFuture ? (
                                <Badge className="bg-orange-500/10 text-orange-500 border-orange-500/20 border text-xs">Projetado</Badge>
                              ) : (
                                <Badge className="bg-indigo-500/10 text-indigo-500 border-indigo-500/20 border text-xs">Realizado</Badge>
                              )}
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
