'use client';

import {
  TrendingUp,
  TrendingDown,
  BarChart3,
  ArrowLeft,
  RefreshCw,
  Activity,
  Users,
  Shield,
  AlertTriangle,
  Calendar,
  Target,
} from 'lucide-react';
import { useMemo, useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/hooks/useAuth';
import { useKPITrends } from '@/hooks/operacional/useKPITrends';
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';

export default function KPITendenciasPage() {
  const router = useRouter();
  const { user } = useAuth();
  const [selectedPeriod, setSelectedPeriod] = useState<'7d' | '30d' | '90d'>('30d');

  const [coveragePrediction, setCoveragePrediction] = useState<any>(null);
  const [predLoading, setPredLoading] = useState(false);
  const [performanceData, setPerformanceData] = useState<any>(null);
  const [perfLoading, setPerfLoading] = useState(false);

  const { data: kpiData, isLoading, refetch } = useKPITrends(
    { period: selectedPeriod as any },
  );

  const chartData = useMemo(() => {
    const data = (kpiData as any)?.data;
    if (!data) return [];
    const days = (kpiData as any)?.days || 30;
    const cobertura = data.cobertura_percentual || [];
    const ocorrencias = data.ocorrencias_mes || [];
    const colaboradores = data.colaboradores_ativos || [];
    const escalas = data.escalas_em_andamento || [];

    const len = Math.max(cobertura.length, ocorrencias.length, 1);
    return Array.from({ length: len }, (_, i) => {
      const daysAgo = len - 1 - i;
      const date = new Date();
      date.setDate(date.getDate() - daysAgo);
      return {
        data: date.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' }),
        cobertura: cobertura[i] ?? null,
        ocorrencias: ocorrencias[i] ?? null,
        colaboradores: colaboradores[i] ?? null,
        escalas: escalas[i] ?? null,
      };
    });
  }, [kpiData]);

  const absencePrediction = useMemo(() => {
    const data = (kpiData as any)?.data;
    if (!data?.ocorrencias_mes?.length) return null;

    const ocorrencias = data.ocorrencias_mes as number[];
    const avg = ocorrencias.reduce((a: number, b: number) => a + b, 0) / ocorrencias.length;
    const last = ocorrencias[ocorrencias.length - 1] ?? 0;
    const trend = last > avg * 1.2 ? 'alta' : last < avg * 0.8 ? 'baixa' : 'normal';
    const riskLevel = trend === 'alta' ? 'alto' : trend === 'baixa' ? 'baixo' : 'moderado';

    return {
      riskLevel,
      trend,
      avg: avg.toFixed(1),
      last,
      recommendation:
        riskLevel === 'alto'
          ? 'Aumento de ocorrências detectado. Reforce comunicação com equipe e verifique escala.'
          : riskLevel === 'baixo'
          ? 'Baixo índice de ocorrências. Mantenha as boas práticas atuais.'
          : 'Índice de ocorrências dentro do normal. Monitoramento contínuo recomendado.',
    };
  }, [kpiData]);

  // Summary card values from latest data point
  const summaryData = useMemo(() => {
    const data = (kpiData as any)?.data;
    if (!data) return { cobertura: null, colaboradores: null, escalas: null, ocorrencias: null, postos: null };
    const last = (arr: number[] | undefined) =>
      arr && arr.length > 0 ? arr[arr.length - 1] : null;
    return {
      cobertura: last(data.cobertura_percentual),
      colaboradores: last(data.colaboradores_ativos),
      escalas: last(data.escalas_em_andamento),
      ocorrencias: last(data.ocorrencias_mes),
      // Postos ATIVOS (by_status.active) — série kpi-trends é a fonte correta (8, não 12)
      postos: last(data.postos_ativos),
    };
  }, [kpiData]);

  useEffect(() => {
    const token = localStorage.getItem('access_token') || '';
    const headers = { 'Authorization': `Bearer ${token}` };

    const fetchPrediction = async () => {
      setPredLoading(true);
      try {
        const resp = await fetch('/api/v1/operacional/kpi-trends/coverage-prediction', { headers });
        if (resp.ok) setCoveragePrediction(await resp.json());
      } catch {}
      setPredLoading(false);
    };

    const fetchPerformance = async () => {
      setPerfLoading(true);
      try {
        const resp = await fetch('/api/v1/operacional/kpi-trends/performance-scores', { headers });
        if (resp.ok) setPerformanceData(await resp.json());
      } catch {}
      setPerfLoading(false);
    };

    fetchPrediction();
    fetchPerformance();
  }, []);

  const periodLabels: Record<string, string> = { '7d': '7 dias', '30d': '30 dias', '90d': '90 dias' };

  // Score pode vir NULL do /performance-scores (colaborador sem turnos nos últimos 30d)
  // — exibir "—/sem dados", NUNCA 0. Decimais reais são preservados (ex.: 92.5).
  const formatScore = (score: number | null | undefined) => {
    if (score == null) return '—';
    return Number.isInteger(score) ? String(score) : score.toFixed(1);
  };

  const Skeleton = ({ className }: { className?: string }) => (
    <div className={`animate-pulse bg-muted rounded ${className ?? ''}`} />
  );

  return (
    <div className="space-y-6">
      {/* Header sticky */}
      <div className="sticky top-0 z-10 bg-background/95 backdrop-blur border-b pb-4 pt-2 -mx-6 px-6">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <Link href="/modulos/operacional">
              <Button variant="ghost" size="icon" className="h-8 w-8">
                <ArrowLeft className="h-4 w-4" />
              </Button>
            </Link>
            <div className="flex items-center gap-2">
              <div className="h-8 w-8 rounded-lg bg-[#1a47f5]/10 flex items-center justify-center">
                <TrendingUp className="h-4 w-4 text-[#1a47f5]" />
              </div>
              <div>
                <h1 className="font-display text-xl font-bold leading-none">KPI Tendências</h1>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Inteligência operacional — últimos {periodLabels[selectedPeriod]}
                </p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Period selector */}
            <div className="flex rounded-lg border overflow-hidden">
              {(['7d', '30d', '90d'] as const).map((p) => (
                <button
                  key={p}
                  onClick={() => setSelectedPeriod(p)}
                  className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                    selectedPeriod === p
                      ? 'bg-[#1a47f5] text-white'
                      : 'bg-background text-muted-foreground hover:bg-muted'
                  }`}
                >
                  {periodLabels[p]}
                </button>
              ))}
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetch()}
              disabled={isLoading}
              className="gap-2"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
              Atualizar
            </Button>
          </div>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {/* Cobertura */}
        <div className="rounded-xl border bg-card p-4 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Cobertura
            </span>
            <div className="h-7 w-7 rounded-lg bg-[#1a47f5]/10 flex items-center justify-center">
              <Shield className="h-3.5 w-3.5 text-[#1a47f5]" />
            </div>
          </div>
          {isLoading ? (
            <Skeleton className="h-8 w-20" />
          ) : (
            <div className="font-data text-2xl font-semibold tabular-nums">
              {summaryData.cobertura !== null ? `${summaryData.cobertura}%` : '—'}
            </div>
          )}
          <p className="text-xs text-muted-foreground">Postos cobertos</p>
        </div>

        {/* Colaboradores */}
        <div className="rounded-xl border bg-card p-4 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Colaboradores
            </span>
            <div className="h-7 w-7 rounded-lg bg-green-500/10 flex items-center justify-center">
              <Users className="h-3.5 w-3.5 text-green-600" />
            </div>
          </div>
          {isLoading ? (
            <Skeleton className="h-8 w-16" />
          ) : (
            <div className="font-data text-2xl font-semibold tabular-nums">
              {summaryData.colaboradores !== null ? summaryData.colaboradores : '—'}
            </div>
          )}
          <p className="text-xs text-muted-foreground">Ativos hoje</p>
        </div>

        {/* Escalas */}
        <div className="rounded-xl border bg-card p-4 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Escalas
            </span>
            <div className="h-7 w-7 rounded-lg bg-[#f97707]/10 flex items-center justify-center">
              <Calendar className="h-3.5 w-3.5 text-[#f97707]" />
            </div>
          </div>
          {isLoading ? (
            <Skeleton className="h-8 w-16" />
          ) : (
            <div className="font-data text-2xl font-semibold tabular-nums">
              {summaryData.escalas !== null ? summaryData.escalas : '—'}
            </div>
          )}
          <p className="text-xs text-muted-foreground">Vigentes</p>
        </div>

        {/* Ocorrências */}
        <div className="rounded-xl border bg-card p-4 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Ocorrências
            </span>
            <div className="h-7 w-7 rounded-lg bg-red-500/10 flex items-center justify-center">
              <AlertTriangle className="h-3.5 w-3.5 text-red-500" />
            </div>
          </div>
          {isLoading ? (
            <Skeleton className="h-8 w-16" />
          ) : (
            <div className="font-data text-2xl font-semibold tabular-nums">
              {summaryData.ocorrencias !== null ? summaryData.ocorrencias : '—'}
            </div>
          )}
          <p className="text-xs text-muted-foreground">Recentes</p>
        </div>
      </div>

      {/* Charts grid — row 1: Cobertura % + Ocorrências */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* AreaChart Cobertura */}
        <div className="rounded-xl border bg-card p-4">
          <div className="flex items-center gap-2 mb-4">
            <Activity className="h-4 w-4 text-[#1a47f5]" />
            <h2 className="text-sm font-semibold">Cobertura de Postos (%)</h2>
          </div>
          {isLoading ? (
            <Skeleton className="h-[250px] w-full" />
          ) : chartData.length === 0 ? (
            <div className="h-[250px] flex items-center justify-center text-muted-foreground text-sm">
              Sem dados disponíveis
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={250}>
              <AreaChart data={chartData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="coberturaGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#1a47f5" stopOpacity={0.2} />
                    <stop offset="95%" stopColor="#1a47f5" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                <XAxis dataKey="data" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
                <YAxis tick={{ fontSize: 10 }} domain={[0, 100]} unit="%" />
                <Tooltip
                  formatter={(value: any) => [`${value}%`, 'Cobertura']}
                  contentStyle={{ fontSize: 12 }}
                />
                <Area
                  type="monotone"
                  dataKey="cobertura"
                  stroke="#1a47f5"
                  strokeWidth={2}
                  fill="url(#coberturaGrad)"
                  fillOpacity={1}
                  connectNulls
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* BarChart Ocorrências */}
        <div className="rounded-xl border bg-card p-4">
          <div className="flex items-center gap-2 mb-4">
            <AlertTriangle className="h-4 w-4 text-red-500" />
            <h2 className="text-sm font-semibold">Ocorrências no Período</h2>
          </div>
          {isLoading ? (
            <Skeleton className="h-[250px] w-full" />
          ) : chartData.length === 0 ? (
            <div className="h-[250px] flex items-center justify-center text-muted-foreground text-sm">
              Sem dados disponíveis
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={chartData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                <XAxis dataKey="data" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip
                  formatter={(value: any) => [value, 'Ocorrências']}
                  contentStyle={{ fontSize: 12 }}
                />
                <Bar dataKey="ocorrencias" fill="#ef4444" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Charts grid — row 2: Colaboradores + Escalas */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* LineChart Colaboradores */}
        <div className="rounded-xl border bg-card p-4">
          <div className="flex items-center gap-2 mb-4">
            <Users className="h-4 w-4 text-green-600" />
            <h2 className="text-sm font-semibold">Colaboradores Ativos</h2>
          </div>
          {isLoading ? (
            <Skeleton className="h-[250px] w-full" />
          ) : chartData.length === 0 ? (
            <div className="h-[250px] flex items-center justify-center text-muted-foreground text-sm">
              Sem dados disponíveis
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={250}>
              <LineChart data={chartData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                <XAxis dataKey="data" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip
                  formatter={(value: any) => [value, 'Colaboradores']}
                  contentStyle={{ fontSize: 12 }}
                />
                <Line
                  type="monotone"
                  dataKey="colaboradores"
                  stroke="#22c55e"
                  strokeWidth={2}
                  dot={false}
                  connectNulls
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* BarChart Escalas */}
        <div className="rounded-xl border bg-card p-4">
          <div className="flex items-center gap-2 mb-4">
            <Calendar className="h-4 w-4 text-[#f97707]" />
            <h2 className="text-sm font-semibold">Escalas Vigentes</h2>
          </div>
          {isLoading ? (
            <Skeleton className="h-[250px] w-full" />
          ) : chartData.length === 0 ? (
            <div className="h-[250px] flex items-center justify-center text-muted-foreground text-sm">
              Sem dados disponíveis
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={chartData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                <XAxis dataKey="data" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip
                  formatter={(value: any) => [value, 'Escalas']}
                  contentStyle={{ fontSize: 12 }}
                />
                <Bar dataKey="escalas" fill="#f97707" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Widget Previsão de Faltas */}
      <div className="rounded-xl border bg-card p-5">
        <div className="flex items-center gap-2 mb-4">
          <div className="h-8 w-8 rounded-lg bg-[#1a47f5]/10 flex items-center justify-center">
            <Target className="h-4 w-4 text-[#1a47f5]" />
          </div>
          <div>
            <h2 className="text-sm font-semibold">Previsão de Faltas</h2>
            <p className="text-xs text-muted-foreground">Análise inteligente baseada em ocorrências</p>
          </div>
        </div>

        {isLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-6 w-32" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-3/4" />
          </div>
        ) : !absencePrediction ? (
          <div className="text-muted-foreground text-sm py-4 text-center">
            Dados insuficientes para previsão. Aguarde acúmulo de histórico.
          </div>
        ) : (
          <div className="space-y-4">
            {/* Risk badge + trend */}
            <div className="flex items-center gap-3 flex-wrap">
              <span
                className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wide ${
                  absencePrediction.riskLevel === 'alto'
                    ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                    : absencePrediction.riskLevel === 'moderado'
                    ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400'
                    : 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                }`}
              >
                {absencePrediction.riskLevel === 'alto' && (
                  <AlertTriangle className="h-3 w-3" />
                )}
                Risco {absencePrediction.riskLevel.charAt(0).toUpperCase() + absencePrediction.riskLevel.slice(1)}
              </span>

              <div className="flex items-center gap-1 text-sm text-muted-foreground">
                {absencePrediction.trend === 'alta' ? (
                  <TrendingUp className="h-4 w-4 text-red-500" />
                ) : absencePrediction.trend === 'baixa' ? (
                  <TrendingDown className="h-4 w-4 text-green-500" />
                ) : (
                  <Activity className="h-4 w-4 text-yellow-500" />
                )}
                <span>
                  Tendência {absencePrediction.trend} — média {absencePrediction.avg} / último valor: {absencePrediction.last}
                </span>
              </div>
            </div>

            {/* Recommendation */}
            <div className="rounded-lg bg-muted/50 border p-3">
              <p className="text-sm">{absencePrediction.recommendation}</p>
            </div>

            <p className="text-xs text-muted-foreground">
              Análise baseada nos últimos dados de ocorrências do período selecionado ({periodLabels[selectedPeriod]}).
            </p>
          </div>
        )}
      </div>

      {/* New widgets — 2-column grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

        {/* Coverage Prediction Widget */}
        <div className="bg-zinc-900 rounded-xl border border-zinc-800 p-6">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
              <Shield className="w-5 h-5 text-blue-400" />
            </div>
            <div>
              <h3 className="text-white font-semibold">Previsão de Cobertura — 48h</h3>
              <p className="text-xs text-zinc-500">Análise preditiva de riscos operacionais</p>
            </div>
            <div className="ml-auto">
              {coveragePrediction && (
                <span className={`px-3 py-1 rounded-full text-xs font-medium ${
                  coveragePrediction.nivel_risco === 'critico' ? 'bg-red-500/20 text-red-400' :
                  coveragePrediction.nivel_risco === 'alto' ? 'bg-orange-500/20 text-orange-400' :
                  coveragePrediction.nivel_risco === 'moderado' ? 'bg-yellow-500/20 text-yellow-400' :
                  'bg-green-500/20 text-green-400'
                }`}>
                  Risco {coveragePrediction.nivel_risco?.toUpperCase()}
                </span>
              )}
            </div>
          </div>

          {predLoading ? (
            <div className="flex items-center justify-center h-32">
              <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : coveragePrediction ? (
            <div className="space-y-6">
              {/* Risk score bar */}
              <div className="grid grid-cols-3 gap-4">
                <div className="bg-zinc-800 rounded-lg p-4 text-center">
                  <p className="font-data text-2xl font-semibold tabular-nums text-white">{coveragePrediction.cobertura_atual?.toFixed(1)}%</p>
                  <p className="text-xs text-zinc-500 mt-1">Cobertura atual</p>
                </div>
                <div className="bg-zinc-800 rounded-lg p-4 text-center">
                  {/* Postos ATIVOS — série kpi-trends (by_status.active); fallback: prediction (já filtra status='active') */}
                  <p className="font-data text-2xl font-semibold tabular-nums text-white">{summaryData.postos ?? coveragePrediction.total_postos}</p>
                  <p className="text-xs text-zinc-500 mt-1">Postos ativos</p>
                </div>
                <div className="bg-zinc-800 rounded-lg p-4 text-center">
                  <p className="font-data text-2xl font-semibold tabular-nums text-white">{coveragePrediction.total_colaboradores}</p>
                  <p className="text-xs text-zinc-500 mt-1">Colaboradores</p>
                </div>
              </div>

              {/* Risk factors */}
              {coveragePrediction.fatores_risco && Object.entries(coveragePrediction.fatores_risco).some(([, v]) => v) && (
                <div className="bg-yellow-500/5 border border-yellow-500/20 rounded-lg p-4">
                  <p className="text-xs font-medium text-yellow-400 mb-2">⚠ Fatores de Risco Identificados:</p>
                  <div className="flex flex-wrap gap-2">
                    {coveragePrediction.fatores_risco.segunda_feira && (
                      <span className="text-xs px-2 py-1 bg-yellow-500/10 text-yellow-400 rounded">Segunda-feira</span>
                    )}
                    {coveragePrediction.fatores_risco.sexta_feira && (
                      <span className="text-xs px-2 py-1 bg-yellow-500/10 text-yellow-400 rounded">Sexta-feira</span>
                    )}
                    {coveragePrediction.fatores_risco.ocorrencias_elevadas && (
                      <span className="text-xs px-2 py-1 bg-red-500/10 text-red-400 rounded">Ocorrências elevadas</span>
                    )}
                  </div>
                </div>
              )}

              {/* Hourly prediction mini-chart */}
              {coveragePrediction.previsao_horaria?.length > 0 && (
                <div>
                  <p className="text-xs text-zinc-500 mb-3">Previsão hora a hora</p>
                  <div className="flex items-end gap-1 h-16">
                    {coveragePrediction.previsao_horaria.slice(0, 8).map((p: any, i: number) => (
                      <div key={i} className="flex-1 flex flex-col items-center gap-1">
                        <div
                          className={`w-full rounded-t ${
                            p.risk_score >= 70 ? 'bg-red-500' :
                            p.risk_score >= 50 ? 'bg-orange-500' :
                            p.risk_score >= 30 ? 'bg-yellow-500' :
                            'bg-green-500'
                          }`}
                          style={{ height: `${Math.max(8, p.risk_score)}%` }}
                        />
                        <span className="text-[9px] text-zinc-600 truncate w-full text-center">{p.hora?.split(' ')[1]}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Recommendation */}
              <div className="bg-blue-500/5 border border-blue-500/20 rounded-lg p-4">
                <p className="text-xs text-zinc-400">
                  <span className="text-blue-400 font-medium">Análise IA: </span>
                  {coveragePrediction.recomendacao}
                </p>
              </div>
            </div>
          ) : (
            <p className="text-zinc-500 text-sm text-center py-8">Dados de previsão não disponíveis</p>
          )}
        </div>

        {/* Performance Score Widget */}
        <div className="bg-zinc-900 rounded-xl border border-zinc-800 p-6">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-10 h-10 rounded-lg bg-purple-500/10 flex items-center justify-center">
              <Users className="w-5 h-5 text-purple-400" />
            </div>
            <div>
              <h3 className="text-white font-semibold">Performance da Equipe</h3>
              <p className="text-xs text-zinc-500">Score de confiabilidade por colaborador</p>
            </div>
            {performanceData && (
              <div className="ml-auto text-right">
                <p className="text-lg font-bold text-white">{formatScore(performanceData.average_score)}</p>
                <p className="text-xs text-zinc-500">Média geral</p>
              </div>
            )}
          </div>

          {perfLoading ? (
            <div className="flex items-center justify-center h-32">
              <div className="w-6 h-6 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : performanceData ? (
            <div className="space-y-4">
              {/* Distribution pills */}
              {performanceData.distribution && (
                <div className="flex gap-2 flex-wrap mb-4">
                  <span className="text-xs px-3 py-1 bg-green-500/10 text-green-400 rounded-full">
                    Excelente: {performanceData.distribution.excelente}
                  </span>
                  <span className="text-xs px-3 py-1 bg-blue-500/10 text-blue-400 rounded-full">
                    Bom: {performanceData.distribution.bom}
                  </span>
                  <span className="text-xs px-3 py-1 bg-yellow-500/10 text-yellow-400 rounded-full">
                    Regular: {performanceData.distribution.regular}
                  </span>
                  <span className="text-xs px-3 py-1 bg-red-500/10 text-red-400 rounded-full">
                    Crítico: {performanceData.distribution.critico}
                  </span>
                </div>
              )}

              {/* Top performers list */}
              <div>
                <p className="text-xs text-zinc-500 mb-3 flex items-center gap-1">
                  <TrendingUp className="w-3 h-3 text-green-400" /> Top 5 Performers
                </p>
                <div className="space-y-2">
                  {(performanceData.top_performers || []).slice(0, 5).map((emp: any, i: number) => (
                    <div key={emp.id} className="flex items-center gap-3">
                      <span className="text-xs text-zinc-600 w-4">{i + 1}.</span>
                      <div className="flex-1">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-xs text-zinc-300">{emp.name?.split(' ').slice(0, 2).join(' ')}</span>
                          <span className={`text-xs font-semibold ${emp.score == null ? 'text-zinc-500' : 'text-white'}`}>
                            {emp.score == null ? 'sem dados' : formatScore(emp.score)}
                          </span>
                        </div>
                        <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${
                              emp.score == null ? 'bg-zinc-700' :
                              emp.score >= 85 ? 'bg-green-500' :
                              emp.score >= 70 ? 'bg-blue-500' :
                              emp.score >= 50 ? 'bg-yellow-500' :
                              'bg-red-500'
                            }`}
                            style={{ width: `${emp.score ?? 0}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Needs attention */}
              {performanceData.needs_attention?.length > 0 && (
                <div className="mt-4 pt-4 border-t border-zinc-800">
                  <p className="text-xs text-zinc-500 mb-3 flex items-center gap-1">
                    <AlertTriangle className="w-3 h-3 text-red-400" /> Precisam de Atenção
                  </p>
                  <div className="space-y-2">
                    {performanceData.needs_attention.slice(0, 3).map((emp: any) => (
                      <div key={emp.id} className="flex items-center justify-between bg-red-500/5 rounded px-3 py-2">
                        <span className="text-xs text-zinc-300">{emp.name?.split(' ').slice(0, 2).join(' ')}</span>
                        <span className={`text-xs font-bold ${emp.score == null ? 'text-zinc-500' : 'text-red-400'}`}>
                          {emp.score == null ? 'sem dados' : `${formatScore(emp.score)} pts`}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <p className="text-zinc-500 text-sm text-center py-8">Dados de performance não disponíveis</p>
          )}
        </div>

      </div>
    </div>
  );
}
