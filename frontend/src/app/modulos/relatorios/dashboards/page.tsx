'use client';

import { LayoutDashboard, TrendingUp, AlertTriangle, Lightbulb, RefreshCw, Activity, ArrowLeft, AlertCircle, TrendingDown } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
;
import {
  useExecutiveDashboard,
  useActiveAlerts,
  usePredictiveInsights,
} from '@/hooks/analytics';
import { formatDate } from '@/lib/utils';

export default function DashboardsExecutivosPage() {
  const router = useRouter();

  const {
    data: dashboardData,
    isLoading: dashboardLoading,
    error: dashboardError,
    refetch: refetchDashboard,
  } = useExecutiveDashboard();

  const {
    data: alertsData,
    isLoading: alertsLoading,
  } = useActiveAlerts();

  const {
    data: insightsData,
    isLoading: insightsLoading,
  } = usePredictiveInsights();

  const isLoading = dashboardLoading || alertsLoading || insightsLoading;
  const error = dashboardError;

  // Extract KPIs from dashboard data
  const kpis = (dashboardData as any)?.kpis || [];
  const alerts = (alertsData as any)?.alerts || (alertsData as any) || [];
  const insights = (insightsData as any)?.insights || (insightsData as any) || [];

  // Summary stats
  const totalKpis = Array.isArray(kpis) ? kpis.length : 0;
  const totalAlerts = Array.isArray(alerts) ? alerts.length : 0;
  const totalInsights = Array.isArray(insights) ? insights.length : 0;
  const criticalAlerts = Array.isArray(alerts)
    ? alerts.filter((a: any) => a?.prioridade === 'critica' || a?.priority === 'critical').length
    : 0;

  const getPriorityBadge = (priority: string) => {
    const normalized = (priority || '').toLowerCase();
    if (normalized === 'critica' || normalized === 'critical') {
      return <Badge className="bg-red-100 text-red-800 hover:bg-red-100">Crítica</Badge>;
    }
    if (normalized === 'alta' || normalized === 'high') {
      return <Badge className="bg-orange-100 text-orange-800 hover:bg-orange-100">Alta</Badge>;
    }
    if (normalized === 'media' || normalized === 'medium') {
      return <Badge className="bg-yellow-100 text-yellow-800 hover:bg-yellow-100">Média</Badge>;
    }
    return <Badge className="bg-blue-100 text-blue-800 hover:bg-blue-100">Baixa</Badge>;
  };

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))]">
        <div className="flex flex-col items-center gap-3">
          <RefreshCw className="w-8 h-8 animate-spin text-[hsl(var(--primary))]" />
          <p className="text-sm text-[hsl(var(--muted-foreground))]">Carregando dashboards...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-grid">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-[hsl(var(--background))]/80 backdrop-blur-xl border-b border-[hsl(var(--border))]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-4">
              <Button variant="ghost" size="sm" onClick={() => router.push('/modulos/relatorios')}>
                <ArrowLeft className="w-4 h-4 mr-2" />
                Relatórios
              </Button>
              <div className="flex items-center gap-2">
                <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
                  <LayoutDashboard className="w-5 h-5 text-blue-500" />
                </div>
                <div>
                  <h1 className="text-lg font-semibold text-[hsl(var(--foreground))]">
                    Dashboards Executivos
                  </h1>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">
                    KPIs, alertas e insights preditivos
                  </p>
                </div>
              </div>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetchDashboard()}
              disabled={isLoading}
            >
              <RefreshCw className={`w-4 h-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
              Atualizar
            </Button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        {/* Error */}
        {error && (
          <div className="bg-destructive/10 border border-destructive/20 rounded-xl p-4 flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-destructive" />
            <p className="text-sm text-destructive">
              {(error as any)?.message || 'Erro ao carregar dashboard executivo'}
            </p>
            <Button variant="outline" size="sm" onClick={() => refetchDashboard()} className="ml-auto">
              Tentar novamente
            </Button>
          </div>
        )}

        {/* Stats Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <Card>
            <CardContent className="pt-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Total KPIs</p>
                  <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))] mt-1">{totalKpis}</p>
                </div>
                <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
                  <Activity className="w-5 h-5 text-blue-500" />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Alertas Ativos</p>
                  <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))] mt-1">{totalAlerts}</p>
                </div>
                <div className="w-10 h-10 rounded-lg bg-orange-500/10 flex items-center justify-center">
                  <AlertTriangle className="w-5 h-5 text-orange-500" />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Alertas Críticos</p>
                  <p className="font-data text-2xl font-semibold tabular-nums text-red-500 mt-1">{criticalAlerts}</p>
                </div>
                <div className="w-10 h-10 rounded-lg bg-red-500/10 flex items-center justify-center">
                  <AlertTriangle className="w-5 h-5 text-red-500" />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Insights</p>
                  <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))] mt-1">{totalInsights}</p>
                </div>
                <div className="w-10 h-10 rounded-lg bg-violet-500/10 flex items-center justify-center">
                  <Lightbulb className="w-5 h-5 text-violet-500" />
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* KPIs por Categoria */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Activity className="w-5 h-5 text-blue-500" />
              <CardTitle>KPIs por Categoria</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            {Array.isArray(kpis) && kpis.length > 0 ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                {kpis.map((kpi: any, index: number) => (
                  <div
                    key={index}
                    className="p-3 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))]"
                  >
                    <p className="text-xs text-[hsl(var(--muted-foreground))] truncate">
                      {kpi?.nome || kpi?.name || kpi?.label || `KPI ${index + 1}`}
                    </p>
                    <p className="text-xl font-bold text-[hsl(var(--foreground))] mt-1">
                      {kpi?.valor || kpi?.value || '--'}
                    </p>
                    <div className="flex items-center gap-1 mt-1">
                      {(kpi?.trend === 'up' || kpi?.tendencia === 'alta') ? (
                        <TrendingUp className="w-3 h-3 text-green-500" />
                      ) : (kpi?.trend === 'down' || kpi?.tendencia === 'baixa') ? (
                        <TrendingDown className="w-3 h-3 text-red-500" />
                      ) : (
                        <Activity className="w-3 h-3 text-[hsl(var(--muted-foreground))]" />
                      )}
                      <span className="text-xs text-[hsl(var(--muted-foreground))]">
                        {kpi?.variacao || kpi?.change || kpi?.trend_value || 'estável'}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-8 text-[hsl(var(--muted-foreground))]">
                <Activity className="w-10 h-10 mb-2 opacity-50" />
                <p className="text-sm">Nenhum KPI disponível</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Alertas Ativos */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-orange-500" />
              <CardTitle>Alertas Ativos</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            {Array.isArray(alerts) && alerts.length > 0 ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Tipo</TableHead>
                    <TableHead>Mensagem</TableHead>
                    <TableHead>Prioridade</TableHead>
                    <TableHead>Data</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {alerts.map((alert: any, index: number) => (
                    <TableRow key={alert?.id || index}>
                      <TableCell className="font-medium">
                        {alert?.tipo || alert?.type || 'Sistema'}
                      </TableCell>
                      <TableCell className="max-w-xs truncate">
                        {alert?.mensagem || alert?.message || '--'}
                      </TableCell>
                      <TableCell>
                        {getPriorityBadge(alert?.prioridade || alert?.priority || 'baixa')}
                      </TableCell>
                      <TableCell className="text-sm text-[hsl(var(--muted-foreground))]">
                        {alert?.data || alert?.created_at
                          ? formatDate(alert?.data || alert?.created_at)
                          : '--'}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <div className="flex flex-col items-center justify-center py-8 text-[hsl(var(--muted-foreground))]">
                <AlertTriangle className="w-10 h-10 mb-2 opacity-50" />
                <p className="text-sm">Nenhum alerta ativo</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Insights Preditivos */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Lightbulb className="w-5 h-5 text-violet-500" />
              <CardTitle>Insights Preditivos</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            {Array.isArray(insights) && insights.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {insights.map((insight: any, index: number) => (
                  <div
                    key={insight?.id || index}
                    className="p-4 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))]"
                  >
                    <div className="flex items-start gap-2">
                      <Lightbulb className="w-4 h-4 text-violet-500 mt-0.5 shrink-0" />
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-[hsl(var(--foreground))]">
                          {insight?.titulo || insight?.title || `Insight ${index + 1}`}
                        </p>
                        <p className="text-xs text-[hsl(var(--muted-foreground))] mt-1 line-clamp-3">
                          {insight?.descricao || insight?.description || 'Sem descrição disponível'}
                        </p>
                        <div className="flex items-center gap-2 mt-2">
                          <div className="flex-1 h-1.5 bg-[hsl(var(--muted))] rounded-full overflow-hidden">
                            <div
                              className="h-full bg-violet-500 rounded-full transition-all"
                              style={{
                                width: `${Math.min(
                                  ((insight?.confianca || insight?.confidence || 0) * 100),
                                  100
                                )}%`,
                              }}
                            />
                          </div>
                          <span className="text-xs text-[hsl(var(--muted-foreground))] shrink-0">
                            {((insight?.confianca || insight?.confidence || 0) * 100).toFixed(0)}%
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-8 text-[hsl(var(--muted-foreground))]">
                <Lightbulb className="w-10 h-10 mb-2 opacity-50" />
                <p className="text-sm">Nenhum insight preditivo disponível</p>
              </div>
            )}
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
