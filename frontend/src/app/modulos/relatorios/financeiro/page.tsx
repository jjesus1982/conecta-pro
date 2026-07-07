'use client';

import { PieChart, DollarSign, TrendingUp, AlertTriangle, RefreshCw, Activity, ShieldAlert, ArrowLeft, AlertCircle } from 'lucide-react';
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
import { useForecastAccuracy, useFraudAnalytics } from '@/hooks/analytics';
import { formatCurrency, formatDate } from '@/lib/utils';

export default function FinanceiroRelatorioPage() {
  const router = useRouter();
  const [periodo, setPeriodo] = useState('mensal');

  const lookbackDays = periodo === 'mensal' ? 30 : periodo === 'trimestral' ? 90 : 365;

  const {
    data: accuracyData,
    isLoading: accuracyLoading,
    error: accuracyError,
    refetch: refetchAccuracy,
  } = useForecastAccuracy(lookbackDays);

  const {
    data: fraudData,
    isLoading: fraudLoading,
    error: fraudError,
    refetch: refetchFraud,
  } = useFraudAnalytics();

  const isLoading = accuracyLoading || fraudLoading;
  const error = accuracyError || fraudError;

  const refetchAll = () => {
    refetchAccuracy();
    refetchFraud();
  };

  // Extract data with safe fallbacks
  const accuracy = (accuracyData as any) || {};
  const fraud = (fraudData as any) || {};

  const receitaPrevista = (accuracy?.receita_prevista || accuracy?.predicted_revenue || accuracy?.forecast_value || 0);
  const precisaoForecast = (accuracy?.precisao || accuracy?.accuracy || accuracy?.mape || 0);
  const alertasFraude = (fraud?.total_alertas || fraud?.total_alerts || fraud?.alert_count || 0);
  const inadimplencia = (fraud?.inadimplencia || fraud?.default_rate || accuracy?.default_rate || 0);

  // Forecast scenarios/details
  const forecastItems = (accuracy?.scenarios || accuracy?.predictions || accuracy?.items || []);
  // Fraud alerts details
  const fraudAlerts = (fraud?.alertas || fraud?.alerts || fraud?.recent_alerts || []);
  const fraudSummary = (fraud?.resumo || fraud?.summary || {});

  const getRiskBadge = (risk: string) => {
    const normalized = (risk || '').toLowerCase();
    if (normalized === 'alto' || normalized === 'high' || normalized === 'critical') {
      return <Badge className="bg-red-100 text-red-800 hover:bg-red-100">Alto</Badge>;
    }
    if (normalized === 'medio' || normalized === 'medium') {
      return <Badge className="bg-yellow-100 text-yellow-800 hover:bg-yellow-100">Médio</Badge>;
    }
    if (normalized === 'baixo' || normalized === 'low') {
      return <Badge className="bg-green-100 text-green-800 hover:bg-green-100">Baixo</Badge>;
    }
    return <Badge className="bg-gray-100 text-gray-800 hover:bg-gray-100">{risk || 'N/A'}</Badge>;
  };

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))]">
        <div className="flex flex-col items-center gap-3">
          <RefreshCw className="w-8 h-8 animate-spin text-[hsl(var(--primary))]" />
          <p className="text-sm text-[hsl(var(--muted-foreground))]">Carregando relatório financeiro...</p>
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
                <div className="w-10 h-10 rounded-lg bg-violet-500/10 flex items-center justify-center">
                  <PieChart className="w-5 h-5 text-violet-500" />
                </div>
                <div>
                  <h1 className="text-lg font-semibold text-[hsl(var(--foreground))]">
                    Relatório Financeiro
                  </h1>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">
                    Previsões, fraudes e indicadores financeiros
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
                  <SelectItem value="mensal">Mensal</SelectItem>
                  <SelectItem value="trimestral">Trimestral</SelectItem>
                  <SelectItem value="anual">Anual</SelectItem>
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
              {(error as any)?.message || 'Erro ao carregar relatório financeiro'}
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
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Receita Prevista</p>
                  <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))] mt-1">
                    {typeof receitaPrevista === 'number' && receitaPrevista > 0
                      ? formatCurrency(receitaPrevista)
                      : '--'}
                  </p>
                </div>
                <div className="w-10 h-10 rounded-lg bg-emerald-500/10 flex items-center justify-center">
                  <DollarSign className="w-5 h-5 text-emerald-500" />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Precisão Forecast</p>
                  <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))] mt-1">
                    {typeof precisaoForecast === 'number'
                      ? `${(precisaoForecast * (precisaoForecast <= 1 ? 100 : 1)).toFixed(1)}%`
                      : '--'}
                  </p>
                </div>
                <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
                  <TrendingUp className="w-5 h-5 text-blue-500" />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Alertas Fraude</p>
                  <p className="font-data text-2xl font-semibold tabular-nums text-red-500 mt-1">{alertasFraude}</p>
                </div>
                <div className="w-10 h-10 rounded-lg bg-red-500/10 flex items-center justify-center">
                  <ShieldAlert className="w-5 h-5 text-red-500" />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Índice Inadimplência</p>
                  <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))] mt-1">
                    {typeof inadimplencia === 'number'
                      ? `${(inadimplencia * (inadimplencia <= 1 ? 100 : 1)).toFixed(1)}%`
                      : '--'}
                  </p>
                </div>
                <div className="w-10 h-10 rounded-lg bg-orange-500/10 flex items-center justify-center">
                  <AlertTriangle className="w-5 h-5 text-orange-500" />
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Previsão de Vendas */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <TrendingUp className="w-5 h-5 text-blue-500" />
              <CardTitle>Previsão de Vendas</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            {Array.isArray(forecastItems) && forecastItems.length > 0 ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Período</TableHead>
                    <TableHead>Valor Previsto</TableHead>
                    <TableHead>Valor Real</TableHead>
                    <TableHead>Variação</TableHead>
                    <TableHead>Precisão</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {forecastItems.map((item: any, index: number) => {
                    const predicted = item?.valor_previsto || item?.predicted_value || item?.forecast || 0;
                    const actual = item?.valor_real || item?.actual_value || item?.actual || 0;
                    const variation = actual && predicted ? ((actual - predicted) / predicted) * 100 : 0;
                    const itemAccuracy = item?.precisao || item?.accuracy || 0;

                    return (
                      <TableRow key={item?.id || index}>
                        <TableCell className="font-medium">
                          {item?.periodo || item?.period || item?.date
                            ? formatDate(item?.periodo || item?.period || item?.date)
                            : `Período ${index + 1}`}
                        </TableCell>
                        <TableCell>
                          {typeof predicted === 'number' ? formatCurrency(predicted) : '--'}
                        </TableCell>
                        <TableCell>
                          {typeof actual === 'number' && actual > 0 ? formatCurrency(actual) : '--'}
                        </TableCell>
                        <TableCell>
                          <span className={variation >= 0 ? 'text-green-600' : 'text-red-600'}>
                            {variation !== 0 ? `${variation > 0 ? '+' : ''}${variation.toFixed(1)}%` : '--'}
                          </span>
                        </TableCell>
                        <TableCell>
                          {typeof itemAccuracy === 'number'
                            ? `${(itemAccuracy * (itemAccuracy <= 1 ? 100 : 1)).toFixed(1)}%`
                            : '--'}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="p-3 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))]">
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Receita Prevista</p>
                  <p className="text-lg font-bold text-[hsl(var(--foreground))] mt-1">
                    {typeof receitaPrevista === 'number' && receitaPrevista > 0
                      ? formatCurrency(receitaPrevista)
                      : '--'}
                  </p>
                </div>
                <div className="p-3 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))]">
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Precisão</p>
                  <p className="text-lg font-bold text-[hsl(var(--foreground))] mt-1">
                    {typeof precisaoForecast === 'number'
                      ? `${(precisaoForecast * (precisaoForecast <= 1 ? 100 : 1)).toFixed(1)}%`
                      : '--'}
                  </p>
                </div>
                <div className="p-3 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))]">
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Período</p>
                  <p className="text-lg font-bold text-[hsl(var(--foreground))] mt-1">
                    {periodo === 'mensal' ? '30 dias' : periodo === 'trimestral' ? '90 dias' : '365 dias'}
                  </p>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Análise de Fraude */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <ShieldAlert className="w-5 h-5 text-red-500" />
              <CardTitle>Análise de Fraude</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            {/* Summary cards */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
              <div className="p-3 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))]">
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Total de Alertas</p>
                <p className="text-lg font-bold text-[hsl(var(--foreground))] mt-1">{alertasFraude}</p>
              </div>
              <div className="p-3 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))]">
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Valor em Risco</p>
                <p className="text-lg font-bold text-red-500 mt-1">
                  {typeof (fraudSummary?.valor_risco || fraudSummary?.risk_value) === 'number'
                    ? formatCurrency(fraudSummary?.valor_risco || fraudSummary?.risk_value)
                    : '--'}
                </p>
              </div>
              <div className="p-3 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))]">
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Taxa de Detecção</p>
                <p className="text-lg font-bold text-[hsl(var(--foreground))] mt-1">
                  {typeof (fraudSummary?.taxa_deteccao || fraudSummary?.detection_rate) === 'number'
                    ? `${((fraudSummary?.taxa_deteccao || fraudSummary?.detection_rate) * 100).toFixed(1)}%`
                    : '--'}
                </p>
              </div>
            </div>

            {/* Fraud alerts table */}
            {Array.isArray(fraudAlerts) && fraudAlerts.length > 0 ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Tipo</TableHead>
                    <TableHead>Descrição</TableHead>
                    <TableHead>Risco</TableHead>
                    <TableHead>Valor</TableHead>
                    <TableHead>Data</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {fraudAlerts.map((alert: any, index: number) => (
                    <TableRow key={alert?.id || index}>
                      <TableCell className="font-medium">
                        {alert?.tipo || alert?.type || 'Transação'}
                      </TableCell>
                      <TableCell className="max-w-xs truncate text-sm text-[hsl(var(--muted-foreground))]">
                        {alert?.descricao || alert?.description || alert?.message || '--'}
                      </TableCell>
                      <TableCell>
                        {getRiskBadge(alert?.risco || alert?.risk_level || alert?.severity || '')}
                      </TableCell>
                      <TableCell>
                        {typeof (alert?.valor || alert?.amount) === 'number'
                          ? formatCurrency(alert?.valor || alert?.amount)
                          : '--'}
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
                <ShieldAlert className="w-10 h-10 mb-2 opacity-50" />
                <p className="text-sm">Nenhum alerta de fraude registrado</p>
              </div>
            )}
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
