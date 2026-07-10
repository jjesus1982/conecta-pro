'use client';

import { AlertCircle, ArrowLeft, BarChart3, Filter, RefreshCw, FileSpreadsheet, FileText } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { PageHeader } from '@/components/ui/page-header';
import { useAuth } from '@/hooks/useAuth';
import { useEmployees } from '@/hooks/operacional/useEmployees';
import { usePosts } from '@/hooks/operacional/usePosts';
import { useCoverageReport, useHoursReport, useCostsReport } from '@/hooks/operacional/useReports';
import type {
  Employee,
  Post,
} from '@/types/operacional';
import {
  BarChart, Bar, AreaChart, Area, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';

const TIMEZONE = 'America/Manaus';

const formatDateInput = (value: Date) => {
  return new Intl.DateTimeFormat('en-CA', { timeZone: TIMEZONE }).format(value);
};

const formatCurrency = (value: number) =>
  new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(value);

const formatPercent = (value: number) => `${value.toFixed(1)}%`;

export default function RelatoriosPage() {
  const router = useRouter();
  const { isLoading: authLoading, isAuthenticated } = useAuth();
  const { data: postsData } = usePosts();
  const posts = useMemo(() => postsData?.items ?? [], [postsData?.items]);
  const { data: employeesData } = useEmployees();
  const employees = useMemo(() => employeesData?.items ?? [], [employeesData?.items]);

  const now = useMemo(() => new Date(), []);
  const [startDate, setStartDate] = useState(
    formatDateInput(new Date(now.getFullYear(), now.getMonth(), 1))
  );
  const [endDate, setEndDate] = useState(formatDateInput(now));
  const [postId, setPostId] = useState<string>('');
  const [employeeId, setEmployeeId] = useState<string>('');
  const [showFilters, setShowFilters] = useState(false);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [authLoading, isAuthenticated, router]);

  // Report hooks com params
  const coverageParams = useMemo(() => ({
    start_date: startDate,
    end_date: endDate,
    ...(postId ? { post_id: postId } : {}),
  }), [startDate, endDate, postId]);

  const hoursParams = useMemo(() => ({
    start_date: startDate,
    end_date: endDate,
    ...(employeeId ? { employee_id: employeeId } : {}),
  }), [startDate, endDate, employeeId]);

  const costsParams = useMemo(() => ({
    start_date: startDate,
    end_date: endDate,
    ...(postId ? { post_id: postId } : {}),
  }), [startDate, endDate, postId]);

  const {
    data: coverageReport,
    isLoading: coverageLoading,
    error: coverageError,
    refetch: refetchCoverage,
  } = useCoverageReport(coverageParams);

  const {
    data: hoursReport,
    isLoading: hoursLoading,
    error: hoursError,
    refetch: refetchHours,
  } = useHoursReport(hoursParams);

  const {
    data: costsReport,
    isLoading: costsLoading,
    error: costsError,
    refetch: refetchCosts,
  } = useCostsReport(costsParams);

  const isLoading = coverageLoading || hoursLoading || costsLoading;
  const error = coverageError || hoursError || costsError;

  const fetchReports = useCallback(() => {
    refetchCoverage();
    refetchHours();
    refetchCosts();
  }, [refetchCoverage, refetchHours, refetchCosts]);

  const postMap = useMemo(() => {
    return posts.reduce<Record<string, Post>>((acc, post) => {
      acc[post.id] = post as Post;
      return acc;
    }, {});
  }, [posts]);

  const employeeMap = useMemo(() => {
    return employees.reduce<Record<string, Employee>>((acc, employee) => {
      acc[employee.id] = employee;
      return acc;
    }, {});
  }, [employees]);

  // Privacidade: exibir sempre o NOME do funcionario — nunca e-mail nem UUID.
  const getEmployeeLabel = useCallback((id: string) => {
    const employee = employeeMap[id] as (Employee & { nome?: string; matricula?: string }) | undefined;
    return employee?.nome || employee?.full_name || employee?.name || employee?.matricula || employee?.registration || '\u2014';
  }, [employeeMap]);

  // Export to CSV/Excel
  const exportToCSV = useCallback(() => {
    if (!coverageReport && !hoursReport && !costsReport) return;

    const lines: string[] = [];

    // Header
    lines.push(`Relatorio Operacional - ${startDate} a ${endDate}`);
    lines.push('');

    // Cobertura
    if (coverageReport) {
      lines.push('COBERTURA POR POSTO');
      lines.push('Posto,Alocacoes Ativas,Quadro Ideal,Taxa Cobertura');
      coverageReport.items.forEach(item => {
        lines.push(`"${postMap[item.post_id]?.name || item.post_name}",${item.active_allocations},${(item as any).required_headcount ?? item.total_allocations},${item.coverage_rate.toFixed(1)}%`);
      });
      lines.push('');
    }

    // Horas
    if (hoursReport) {
      lines.push('HORAS POR FUNCIONARIO');
      lines.push('Funcionario,Turnos,Horas,Horas Extras');
      hoursReport.items.forEach(item => {
        lines.push(`"${(item as any).employee_name || getEmployeeLabel(item.employee_id)}",${item.total_shifts},${item.total_hours.toFixed(1)},${item.overtime_hours?.toFixed(1) || 0}`);
      });
      lines.push('');
    }

    // Custos
    if (costsReport) {
      lines.push('CUSTOS POR POSTO');
      lines.push('Posto,Turnos,Custo Total');
      costsReport.items.forEach(item => {
        lines.push(`"${postMap[item.post_id]?.name || item.post_name}",${item.total_shifts},${item.total_cost.toFixed(2)}`);
      });
    }

    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `relatorio-operacional-${startDate}-${endDate}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }, [coverageReport, hoursReport, costsReport, startDate, endDate, postMap, getEmployeeLabel]);

  // Export to PDF (simple HTML print)
  const exportToPDF = useCallback(() => {
    const printContent = document.getElementById('report-content');
    if (!printContent) return;

    const printWindow = window.open('', '_blank');
    if (!printWindow) return;

    printWindow.document.write(`
      <!DOCTYPE html>
      <html>
        <head>
          <title>Relatorio Operacional - ${startDate} a ${endDate}</title>
          <style>
            body { font-family: Arial, sans-serif; padding: 20px; }
            h1 { font-size: 18px; margin-bottom: 20px; }
            h2 { font-size: 14px; margin-top: 20px; margin-bottom: 10px; }
            table { width: 100%; border-collapse: collapse; margin-bottom: 20px; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: left; font-size: 12px; }
            th { background-color: #f5f5f5; }
            .summary { display: flex; gap: 20px; margin-bottom: 20px; }
            .summary-card { padding: 10px; border: 1px solid #ddd; border-radius: 4px; }
            @media print { body { print-color-adjust: exact; } }
          </style>
        </head>
        <body>
          <h1>Relatorio Operacional</h1>
          <p>Periodo: ${startDate} a ${endDate}</p>
          ${printContent.innerHTML}
        </body>
      </html>
    `);
    printWindow.document.close();
    printWindow.print();
  }, [startDate, endDate]);

  // Calculate max for simple bar visualization
  const maxHours = useMemo(() => {
    if (!hoursReport?.items.length) return 100;
    return Math.max(...hoursReport.items.map(i => i.total_hours));
  }, [hoursReport]);

  const maxCost = useMemo(() => {
    if (!costsReport?.items.length) return 1000;
    return Math.max(...costsReport.items.map(i => i.total_cost));
  }, [costsReport]);

  // Chart data derived from report data
  const coverageChartData = useMemo(() => {
    if (!coverageReport?.items?.length) return [];
    return coverageReport.items.map((item) => ({
      name: (postMap[item.post_id]?.name || item.post_name || '').slice(0, 12),
      coverage_rate: item.coverage_rate,
    }));
  }, [coverageReport, postMap]);

  const hoursChartData = useMemo(() => {
    if (!hoursReport?.items?.length) return [];
    return hoursReport.items.map((item) => ({
      name: ((item as any).employee_name || getEmployeeLabel(item.employee_id)).slice(0, 10),
      total_hours: item.total_hours,
    }));
  }, [hoursReport, getEmployeeLabel]);

  const costsChartData = useMemo(() => {
    if (!costsReport?.items?.length) return [];
    return costsReport.items.map((item) => ({
      name: (postMap[item.post_id]?.name || item.post_name || '').slice(0, 12),
      total_cost: item.total_cost,
    }));
  }, [costsReport, postMap]);

  const distributionChartData = useMemo(() => {
    if (!coverageReport?.items?.length) return [];
    let full = 0;
    let good = 0;
    let low = 0;
    coverageReport.items.forEach((item) => {
      if (item.coverage_rate >= 100) full++;
      else if (item.coverage_rate >= 80) good++;
      else low++;
    });
    return [
      { name: '≥100%', value: full, color: '#22c55e' },
      { name: '80-99%', value: good, color: '#f97707' },
      { name: '<80%', value: low, color: '#ef4444' },
    ].filter((seg) => seg.value > 0);
  }, [coverageReport]);

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))]">
        <div className="animate-pulse-slow text-[hsl(var(--primary))]">
          <BarChart3 className="w-12 h-12" />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-grid">
      <main id="report-content" className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        <PageHeader
          eyebrow="OPERACIONAL"
          title="Relatórios"
          subtitle="Cobertura, horas e custos operacionais"
          icon={<BarChart3 className="w-5 h-5" />}
          actions={
            <>
              <Link href="/modulos/operacional">
                <Button variant="ghost" size="sm">
                  <ArrowLeft className="w-4 h-4 mr-2" />
                  Operacional
                </Button>
              </Link>
              <Button
                variant="outline"
                onClick={() => setShowFilters(!showFilters)}
                className={showFilters ? 'border-[hsl(var(--primary))]' : ''}
              >
                <Filter className="w-4 h-4 mr-2" />
                Filtros
              </Button>
              <Button
                variant="outline"
                onClick={exportToCSV}
                disabled={!coverageReport && !hoursReport && !costsReport}
                title="Exportar Excel/CSV"
              >
                <FileSpreadsheet className="w-4 h-4" />
              </Button>
              <Button
                variant="outline"
                onClick={exportToPDF}
                disabled={!coverageReport && !hoursReport && !costsReport}
                title="Exportar PDF"
              >
                <FileText className="w-4 h-4" />
              </Button>
              <Button variant="outline" onClick={fetchReports} disabled={isLoading}>
                <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
              </Button>
            </>
          }
        />

        {showFilters && (
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <div>
                <label className="text-sm text-[hsl(var(--muted-foreground))] mb-1 block">
                  Posto
                </label>
                <select
                  className="w-full px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-sm"
                  value={postId}
                  onChange={(e) => setPostId(e.target.value)}
                >
                  <option value="">Todos</option>
                  {posts.map((post) => (
                    <option key={post.id} value={post.id}>
                      {post.name} ({post.code})
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-sm text-[hsl(var(--muted-foreground))] mb-1 block">
                  Funcionario
                </label>
                <select
                  className="w-full px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-sm"
                  value={employeeId}
                  onChange={(e) => setEmployeeId(e.target.value)}
                >
                  <option value="">Todos</option>
                  {employees.map((employee) => (
                    <option key={employee.id} value={employee.id}>
                      {getEmployeeLabel(employee.id)}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-sm text-[hsl(var(--muted-foreground))] mb-1 block">
                  Inicio
                </label>
                <Input
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                />
              </div>
              <div>
                <label className="text-sm text-[hsl(var(--muted-foreground))] mb-1 block">
                  Fim
                </label>
                <Input
                  type="date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                />
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-red-500" />
            <p className="text-red-500">{(error as any)?.message || 'Erro ao carregar relatórios'}</p>
            <Button variant="outline" size="sm" onClick={fetchReports} className="ml-auto">
              Tentar novamente
            </Button>
          </div>
        )}

        {/* Summary stats cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <p className="text-xs text-[hsl(var(--muted-foreground))]">Cobertura</p>
            <p className="text-2xl font-semibold text-[hsl(var(--foreground))]">
              {coverageReport ? formatPercent(coverageReport.coverage_rate) : '--'}
            </p>
            <p className="text-xs text-[hsl(var(--muted-foreground))] mt-1">
              {coverageReport
                ? `${coverageReport.active_allocations}/${coverageReport.total_allocations} alocacoes ativas`
                : 'Sem dados'}
            </p>
          </div>
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <p className="text-xs text-[hsl(var(--muted-foreground))]">Horas trabalhadas</p>
            <p className="text-2xl font-semibold text-[hsl(var(--foreground))]">
              {hoursReport ? hoursReport.total_hours.toFixed(1) : '--'}
            </p>
            <p className="text-xs text-[hsl(var(--muted-foreground))] mt-1">
              {hoursReport ? `${hoursReport.total_overtime.toFixed(1)}h extras` : 'Sem dados'}
            </p>
          </div>
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <p className="text-xs text-[hsl(var(--muted-foreground))]">Custo estimado</p>
            <p className="text-2xl font-semibold text-[hsl(var(--foreground))]">
              {costsReport ? formatCurrency(costsReport.total_cost) : '--'}
            </p>
            <p className="text-xs text-[hsl(var(--muted-foreground))] mt-1">
              {costsReport ? `${costsReport.total_posts} postos` : 'Sem dados'}
            </p>
          </div>
        </div>

        {/* Visualizações — charts section */}
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
          <h2 className="text-sm font-semibold text-[hsl(var(--foreground))] mb-4">
            Visualizações
          </h2>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

            {/* Chart 1 — Coverage BarChart */}
            <div>
              <p className="text-xs text-[hsl(var(--muted-foreground))] mb-2">Cobertura por posto (%)</p>
              {coverageChartData.length > 0 ? (
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={coverageChartData} margin={{ top: 4, right: 8, left: -20, bottom: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis
                      dataKey="name"
                      tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }}
                    />
                    <YAxis
                      domain={[0, 100]}
                      tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }}
                      tickFormatter={(v: number) => `${v}%`}
                    />
                    <Tooltip
                      formatter={((value: number) => [`${value.toFixed(1)}%`, 'Cobertura']) as any}
                      contentStyle={{
                        background: 'hsl(var(--card))',
                        border: '1px solid hsl(var(--border))',
                        borderRadius: '8px',
                        fontSize: '12px',
                      }}
                    />
                    <Bar dataKey="coverage_rate" radius={[4, 4, 0, 0]}>
                      {coverageChartData.map((entry, index) => (
                        <Cell
                          key={`coverage-cell-${index}`}
                          fill={entry.coverage_rate >= 80 ? '#22c55e' : '#f97707'}
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-[200px] flex items-center justify-center text-xs text-[hsl(var(--muted-foreground))]">
                  Sem dados de cobertura
                </div>
              )}
            </div>

            {/* Chart 2 — Hours BarChart */}
            <div>
              <p className="text-xs text-[hsl(var(--muted-foreground))] mb-2">Horas por funcionário</p>
              {hoursChartData.length > 0 ? (
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={hoursChartData} margin={{ top: 4, right: 8, left: -20, bottom: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis
                      dataKey="name"
                      tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }}
                    />
                    <YAxis
                      tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }}
                      tickFormatter={(v: number) => `${v}h`}
                    />
                    <Tooltip
                      formatter={((value: number) => [`${value.toFixed(1)}h`, 'Horas']) as any}
                      contentStyle={{
                        background: 'hsl(var(--card))',
                        border: '1px solid hsl(var(--border))',
                        borderRadius: '8px',
                        fontSize: '12px',
                      }}
                    />
                    <Bar dataKey="total_hours" fill="#1a47f5" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-[200px] flex items-center justify-center text-xs text-[hsl(var(--muted-foreground))]">
                  Sem dados de horas
                </div>
              )}
            </div>

            {/* Chart 3 — Costs AreaChart */}
            <div>
              <p className="text-xs text-[hsl(var(--muted-foreground))] mb-2">Custos por posto (R$)</p>
              {costsChartData.length > 0 ? (
                <ResponsiveContainer width="100%" height={200}>
                  <AreaChart data={costsChartData} margin={{ top: 4, right: 8, left: -4, bottom: 4 }}>
                    <defs>
                      <linearGradient id="costsGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#1a47f5" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#1a47f5" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis
                      dataKey="name"
                      tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }}
                    />
                    <YAxis
                      tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }}
                      tickFormatter={(v: number) =>
                        new Intl.NumberFormat('pt-BR', {
                          notation: 'compact',
                          style: 'currency',
                          currency: 'BRL',
                          maximumFractionDigits: 1,
                        }).format(v)
                      }
                    />
                    <Tooltip
                      formatter={((value: number) => [formatCurrency(value), 'Custo']) as any}
                      contentStyle={{
                        background: 'hsl(var(--card))',
                        border: '1px solid hsl(var(--border))',
                        borderRadius: '8px',
                        fontSize: '12px',
                      }}
                    />
                    <Area
                      type="monotone"
                      dataKey="total_cost"
                      stroke="#1a47f5"
                      strokeWidth={2}
                      fill="url(#costsGradient)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-[200px] flex items-center justify-center text-xs text-[hsl(var(--muted-foreground))]">
                  Sem dados de custos
                </div>
              )}
            </div>

            {/* Chart 4 — Distribution PieChart */}
            <div>
              <p className="text-xs text-[hsl(var(--muted-foreground))] mb-2">Distribuição de cobertura</p>
              {distributionChartData.length > 0 ? (
                <ResponsiveContainer width="100%" height={200}>
                  <PieChart>
                    <Pie
                      data={distributionChartData}
                      cx="50%"
                      cy="45%"
                      innerRadius={40}
                      outerRadius={70}
                      paddingAngle={3}
                      dataKey="value"
                    >
                      {distributionChartData.map((entry, index) => (
                        <Cell key={`dist-cell-${index}`} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip
                      formatter={((value: number, name: string) => [
                        `${value} posto${value !== 1 ? 's' : ''}`,
                        name,
                      ]) as any}
                      contentStyle={{
                        background: 'hsl(var(--card))',
                        border: '1px solid hsl(var(--border))',
                        borderRadius: '8px',
                        fontSize: '12px',
                      }}
                    />
                    <Legend
                      iconSize={10}
                      wrapperStyle={{ fontSize: '11px', paddingTop: '8px' }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-[200px] flex items-center justify-center text-xs text-[hsl(var(--muted-foreground))]">
                  Sem dados de distribuição
                </div>
              )}
            </div>

          </div>
        </div>

        {/* Tables section */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <h2 className="text-sm font-semibold text-[hsl(var(--foreground))] mb-3">
              Cobertura por posto
            </h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-[hsl(var(--muted-foreground))]">
                    <th className="pb-2">Posto</th>
                    <th className="pb-2">Efetivo/Ideal</th>
                    <th className="pb-2 w-48">Cobertura</th>
                  </tr>
                </thead>
                <tbody>
                  {coverageReport?.items.map((item) => (
                    <tr key={item.post_id} className="border-t border-[hsl(var(--border))]">
                      <td className="py-2">{postMap[item.post_id]?.name || item.post_name}</td>
                      <td className="py-2">
                        {/* ativos/quadro ideal (required_headcount do backend), não ativos/alocações */}
                        {item.active_allocations}/{(item as any).required_headcount ?? item.total_allocations}
                      </td>
                      <td className="py-2">
                        <div className="flex items-center gap-2">
                          <div className="flex-1 h-2 bg-[hsl(var(--muted))] rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all ${
                                item.coverage_rate >= 80 ? 'bg-green-500' :
                                item.coverage_rate >= 50 ? 'bg-yellow-500' : 'bg-red-500'
                              }`}
                              style={{ width: `${Math.min(item.coverage_rate, 100)}%` }}
                            />
                          </div>
                          <span className="text-xs w-12 text-right">{formatPercent(item.coverage_rate)}</span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!coverageReport?.items.length && (
                <p className="text-xs text-[hsl(var(--muted-foreground))] py-4">
                  Nenhum dado de cobertura encontrado.
                </p>
              )}
            </div>
          </div>

          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <h2 className="text-sm font-semibold text-[hsl(var(--foreground))] mb-3">
              Horas por funcionario
            </h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-[hsl(var(--muted-foreground))]">
                    <th className="pb-2">Funcionario</th>
                    <th className="pb-2">Turnos</th>
                    <th className="pb-2 w-48">Horas</th>
                  </tr>
                </thead>
                <tbody>
                  {hoursReport?.items.map((item) => (
                    <tr key={item.employee_id} className="border-t border-[hsl(var(--border))]">
                      <td className="py-2">{(item as any).employee_name || getEmployeeLabel(item.employee_id)}</td>
                      <td className="py-2">{item.total_shifts}</td>
                      <td className="py-2">
                        <div className="flex items-center gap-2">
                          <div className="flex-1 h-2 bg-[hsl(var(--muted))] rounded-full overflow-hidden">
                            <div
                              className="h-full bg-blue-500 rounded-full transition-all"
                              style={{ width: `${maxHours > 0 ? (item.total_hours / maxHours) * 100 : 0}%` }}
                            />
                          </div>
                          <span className="text-xs w-16 text-right">{item.total_hours.toFixed(1)}h</span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!hoursReport?.items.length && (
                <p className="text-xs text-[hsl(var(--muted-foreground))] py-4">
                  Nenhum dado de horas encontrado.
                </p>
              )}
            </div>
          </div>
        </div>

        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
          <h2 className="text-sm font-semibold text-[hsl(var(--foreground))] mb-3">
            Custos estimados por posto
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[hsl(var(--muted-foreground))]">
                  <th className="pb-2">Posto</th>
                  <th className="pb-2">Turnos</th>
                  <th className="pb-2 w-64">Custo</th>
                </tr>
              </thead>
              <tbody>
                {costsReport?.items.map((item) => (
                  <tr key={item.post_id} className="border-t border-[hsl(var(--border))]">
                    <td className="py-2">{postMap[item.post_id]?.name || item.post_name}</td>
                    <td className="py-2">{item.total_shifts}</td>
                    <td className="py-2">
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-2 bg-[hsl(var(--muted))] rounded-full overflow-hidden">
                          <div
                            className="h-full bg-emerald-500 rounded-full transition-all"
                            style={{ width: `${maxCost > 0 ? (item.total_cost / maxCost) * 100 : 0}%` }}
                          />
                        </div>
                        <span className="text-xs w-24 text-right">{formatCurrency(item.total_cost)}</span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!costsReport?.items.length && (
              <p className="text-xs text-[hsl(var(--muted-foreground))] py-4">
                Nenhum dado de custos encontrado.
              </p>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
