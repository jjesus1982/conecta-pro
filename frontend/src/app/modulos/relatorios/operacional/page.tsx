'use client';

import { ClipboardCheck, Shield, AlertTriangle, CheckCircle2, RefreshCw, Activity, Users, MapPin, ArrowLeft, AlertCircle } from 'lucide-react';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
;
import { useExecutiveSummary, useMonitoringDashboard } from '@/hooks/analytics';
import { formatDate } from '@/lib/utils';

export default function OperacionalRelatorioPage() {
  const router = useRouter();
  const [periodo, setPeriodo] = useState('30dias');

  const {
    data: summaryData,
    isLoading: summaryLoading,
    error: summaryError,
    refetch: refetchSummary,
  } = useExecutiveSummary();

  const {
    data: monitoringData,
    isLoading: monitoringLoading,
    error: monitoringError,
    refetch: refetchMonitoring,
  } = useMonitoringDashboard();

  const isLoading = summaryLoading || monitoringLoading;
  const error = summaryError || monitoringError;

  const refetchAll = () => {
    refetchSummary();
    refetchMonitoring();
  };

  // Extract data with safe fallbacks
  const summary = (summaryData as any) || {};
  const monitoring = (monitoringData as any) || {};

  const escalasAtivas = (summary?.escalas_ativas || summary?.active_scales || monitoring?.active_scales || 0);
  const ocorrencias = (summary?.ocorrencias || summary?.incidents || monitoring?.incidents || 0);
  const slaCumprido = (summary?.sla_cumprido || summary?.sla_compliance || monitoring?.sla_compliance || 0);
  const postosAtivos = (summary?.postos_ativos || summary?.active_posts || monitoring?.active_posts || 0);

  // Monitoring items
  const monitoringItems = (monitoring?.models || monitoring?.items || monitoring?.modelos || []);
  const summaryItems = (summary?.items || summary?.resumo || []);

  const getStatusBadge = (status: string) => {
    const normalized = (status || '').toLowerCase();
    if (normalized === 'ativo' || normalized === 'active' || normalized === 'healthy') {
      return <Badge className="bg-green-100 text-green-800 hover:bg-green-100">Ativo</Badge>;
    }
    if (normalized === 'alerta' || normalized === 'warning' || normalized === 'degraded') {
      return <Badge className="bg-yellow-100 text-yellow-800 hover:bg-yellow-100">Alerta</Badge>;
    }
    if (normalized === 'critico' || normalized === 'critical' || normalized === 'unhealthy') {
      return <Badge className="bg-red-100 text-red-800 hover:bg-red-100">Crítico</Badge>;
    }
    return <Badge className="bg-gray-100 text-gray-800 hover:bg-gray-100">{status || 'N/A'}</Badge>;
  };

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))]">
        <div className="flex flex-col items-center gap-3">
          <RefreshCw className="w-8 h-8 animate-spin text-[hsl(var(--primary))]" />
          <p className="text-sm text-[hsl(var(--muted-foreground))]">Carregando relatório operacional...</p>
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
                <div className="w-10 h-10 rounded-lg bg-emerald-500/10 flex items-center justify-center">
                  <ClipboardCheck className="w-5 h-5 text-emerald-500" />
                </div>
                <div>
                  <h1 className="text-lg font-semibold text-[hsl(var(--foreground))]">
                    Relatório Operacional
                  </h1>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">
                    Escalas, ocorrências e monitoramento
                  </p>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Select value={periodo} onValueChange={setPeriodo} aria-label="Periodo">
                <SelectTrigger className="w-[140px]">
                  <SelectValue placeholder="Período" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="hoje">Hoje</SelectItem>
                  <SelectItem value="7dias">7 dias</SelectItem>
                  <SelectItem value="30dias">30 dias</SelectItem>
                  <SelectItem value="90dias">90 dias</SelectItem>
                </SelectContent>
              </Select>
              <Button variant="outline" size="sm" onClick={refetchAll} disabled={isLoading}>
                <RefreshCw className={`w-4 h-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
                Atualizar
              </Button>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        {/* Error */}
        {error && (
          <div className="bg-destructive/10 border border-destructive/20 rounded-xl p-4 flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-destructive" />
            <p className="text-sm text-destructive">
              {(error as any)?.message || 'Erro ao carregar relatório operacional'}
            </p>
            <Button variant="outline" size="sm" onClick={refetchAll} className="ml-auto">
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
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Escalas Ativas</p>
                  <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))] mt-1">{escalasAtivas}</p>
                </div>
                <div className="w-10 h-10 rounded-lg bg-emerald-500/10 flex items-center justify-center">
                  <Users className="w-5 h-5 text-emerald-500" />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Ocorrências</p>
                  <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))] mt-1">{ocorrencias}</p>
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
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">SLA Cumprido</p>
                  <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))] mt-1">
                    {typeof slaCumprido === 'number'
                      ? `${(slaCumprido * (slaCumprido <= 1 ? 100 : 1)).toFixed(1)}%`
                      : slaCumprido || '0%'}
                  </p>
                </div>
                <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
                  <CheckCircle2 className="w-5 h-5 text-blue-500" />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Postos Ativos</p>
                  <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))] mt-1">{postosAtivos}</p>
                </div>
                <div className="w-10 h-10 rounded-lg bg-violet-500/10 flex items-center justify-center">
                  <MapPin className="w-5 h-5 text-violet-500" />
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Resumo Executivo */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Shield className="w-5 h-5 text-emerald-500" />
              <CardTitle>Resumo Executivo</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            {Array.isArray(summaryItems) && summaryItems.length > 0 ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {summaryItems.map((item: any, index: number) => (
                  <div
                    key={index}
                    className="p-3 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))]"
                  >
                    <p className="text-xs text-[hsl(var(--muted-foreground))]">
                      {item?.titulo || item?.title || item?.label || item?.name || `Item ${index + 1}`}
                    </p>
                    <p className="text-lg font-bold text-[hsl(var(--foreground))] mt-1">
                      {item?.valor || item?.value || '--'}
                    </p>
                    {(item?.descricao || item?.description) && (
                      <p className="text-xs text-[hsl(var(--muted-foreground))] mt-1">
                        {item?.descricao || item?.description}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                <div className="p-3 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))]">
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Escalas Ativas</p>
                  <p className="text-lg font-bold text-[hsl(var(--foreground))] mt-1">{escalasAtivas}</p>
                </div>
                <div className="p-3 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))]">
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Ocorrências</p>
                  <p className="text-lg font-bold text-[hsl(var(--foreground))] mt-1">{ocorrencias}</p>
                </div>
                <div className="p-3 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))]">
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">SLA</p>
                  <p className="text-lg font-bold text-[hsl(var(--foreground))] mt-1">
                    {typeof slaCumprido === 'number'
                      ? `${(slaCumprido * (slaCumprido <= 1 ? 100 : 1)).toFixed(1)}%`
                      : slaCumprido || '0%'}
                  </p>
                </div>
                <div className="p-3 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))]">
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Postos</p>
                  <p className="text-lg font-bold text-[hsl(var(--foreground))] mt-1">{postosAtivos}</p>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Monitoramento */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Activity className="w-5 h-5 text-blue-500" />
              <CardTitle>Monitoramento</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            {Array.isArray(monitoringItems) && monitoringItems.length > 0 ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Nome</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Métricas</TableHead>
                    <TableHead>Última Atualização</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {monitoringItems.map((item: any, index: number) => (
                    <TableRow key={item?.id || item?.name || index}>
                      <TableCell className="font-medium">
                        {item?.nome || item?.name || item?.model_name || `Monitor ${index + 1}`}
                      </TableCell>
                      <TableCell>
                        {getStatusBadge(item?.status || item?.health_status || 'N/A')}
                      </TableCell>
                      <TableCell className="text-sm text-[hsl(var(--muted-foreground))]">
                        {item?.metricas || item?.metrics
                          ? typeof (item?.metricas || item?.metrics) === 'object'
                            ? JSON.stringify(item?.metricas || item?.metrics).slice(0, 50)
                            : String(item?.metricas || item?.metrics)
                          : '--'}
                      </TableCell>
                      <TableCell className="text-sm text-[hsl(var(--muted-foreground))]">
                        {item?.ultima_atualizacao || item?.last_updated || item?.updated_at
                          ? formatDate(item?.ultima_atualizacao || item?.last_updated || item?.updated_at)
                          : '--'}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <div className="flex flex-col items-center justify-center py-8 text-[hsl(var(--muted-foreground))]">
                <Activity className="w-10 h-10 mb-2 opacity-50" />
                <p className="text-sm">Nenhum dado de monitoramento disponível</p>
              </div>
            )}
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
