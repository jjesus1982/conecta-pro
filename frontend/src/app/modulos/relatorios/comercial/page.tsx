'use client';

import { TrendingUp, Users, Target, AlertTriangle, RefreshCw, Activity, Star, ArrowLeft, AlertCircle } from 'lucide-react';
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
import { useTopLeads, useChurnAnalytics } from '@/hooks/analytics';

export default function ComercialRelatorioPage() {
  const router = useRouter();
  const [periodo, setPeriodo] = useState('30dias');

  const {
    data: leadsData,
    isLoading: leadsLoading,
    error: leadsError,
    refetch: refetchLeads,
  } = useTopLeads();

  const {
    data: churnData,
    isLoading: churnLoading,
    error: churnError,
    refetch: refetchChurn,
  } = useChurnAnalytics();

  const isLoading = leadsLoading || churnLoading;
  const error = leadsError || churnError;

  const refetchAll = () => {
    refetchLeads();
    refetchChurn();
  };

  // Extract data with safe fallbacks
  const leads = (leadsData as any)?.leads || (leadsData as any)?.items || (Array.isArray(leadsData) ? leadsData : []);
  const churn = (churnData as any) || {};

  const totalLeads = Array.isArray(leads) ? leads.length : 0;

  const scoreMedio = Array.isArray(leads) && leads.length > 0
    ? leads.reduce((sum: number, lead: any) => sum + ((lead?.score || lead?.lead_score || 0)), 0) / leads.length
    : 0;

  const riscoChurn = (churn?.risco_medio || churn?.average_risk || churn?.churn_rate || 0);
  const conversao = (churn?.taxa_conversao || churn?.conversion_rate || 0);

  // Churn details
  const churnItems = (churn?.items || churn?.usuarios || churn?.users || churn?.segments || []);
  const churnSummary = (churn?.resumo || churn?.summary || {});

  const getQualityBadge = (quality: string) => {
    const normalized = (quality || '').toLowerCase();
    if (normalized === 'hot' || normalized === 'quente') {
      return <Badge className="bg-red-100 text-red-800 hover:bg-red-100">Quente</Badge>;
    }
    if (normalized === 'warm' || normalized === 'morno') {
      return <Badge className="bg-orange-100 text-orange-800 hover:bg-orange-100">Morno</Badge>;
    }
    if (normalized === 'cold' || normalized === 'frio') {
      return <Badge className="bg-blue-100 text-blue-800 hover:bg-blue-100">Frio</Badge>;
    }
    return <Badge className="bg-gray-100 text-gray-800 hover:bg-gray-100">{quality || 'N/A'}</Badge>;
  };

  const getRiskBadge = (risk: string | number) => {
    const normalized = typeof risk === 'string' ? risk.toLowerCase() : '';
    const numRisk = typeof risk === 'number' ? risk : parseFloat(String(risk));

    if (normalized === 'alto' || normalized === 'high' || (numRisk > 0.7)) {
      return <Badge className="bg-red-100 text-red-800 hover:bg-red-100">Alto</Badge>;
    }
    if (normalized === 'medio' || normalized === 'medium' || (numRisk > 0.4)) {
      return <Badge className="bg-yellow-100 text-yellow-800 hover:bg-yellow-100">Médio</Badge>;
    }
    if (normalized === 'baixo' || normalized === 'low' || numRisk >= 0) {
      return <Badge className="bg-green-100 text-green-800 hover:bg-green-100">Baixo</Badge>;
    }
    return <Badge className="bg-gray-100 text-gray-800 hover:bg-gray-100">{String(risk) || 'N/A'}</Badge>;
  };

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))]">
        <div className="flex flex-col items-center gap-3">
          <RefreshCw className="w-8 h-8 animate-spin text-[hsl(var(--primary))]" />
          <p className="text-sm text-[hsl(var(--muted-foreground))]">Carregando relatório comercial...</p>
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
                <div className="w-10 h-10 rounded-lg bg-amber-500/10 flex items-center justify-center">
                  <TrendingUp className="w-5 h-5 text-amber-500" />
                </div>
                <div>
                  <h1 className="text-lg font-semibold text-[hsl(var(--foreground))]">
                    Relatório Comercial
                  </h1>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">
                    Leads, scoring e análise de churn
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
              {(error as any)?.message || 'Erro ao carregar relatório comercial'}
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
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Top Leads</p>
                  <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))] mt-1">{totalLeads}</p>
                </div>
                <div className="w-10 h-10 rounded-lg bg-amber-500/10 flex items-center justify-center">
                  <Users className="w-5 h-5 text-amber-500" />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Score Médio</p>
                  <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))] mt-1">
                    {scoreMedio > 0
                      ? scoreMedio <= 1
                        ? `${(scoreMedio * 100).toFixed(0)}%`
                        : scoreMedio.toFixed(1)
                      : '--'}
                  </p>
                </div>
                <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
                  <Star className="w-5 h-5 text-blue-500" />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Risco Churn</p>
                  <p className="font-data text-2xl font-semibold tabular-nums text-red-500 mt-1">
                    {typeof riscoChurn === 'number' && riscoChurn > 0
                      ? `${(riscoChurn * (riscoChurn <= 1 ? 100 : 1)).toFixed(1)}%`
                      : '--'}
                  </p>
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
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Conversão</p>
                  <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))] mt-1">
                    {typeof conversao === 'number' && conversao > 0
                      ? `${(conversao * (conversao <= 1 ? 100 : 1)).toFixed(1)}%`
                      : '--'}
                  </p>
                </div>
                <div className="w-10 h-10 rounded-lg bg-emerald-500/10 flex items-center justify-center">
                  <Target className="w-5 h-5 text-emerald-500" />
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Top Leads */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Star className="w-5 h-5 text-amber-500" />
              <CardTitle>Top Leads</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            {Array.isArray(leads) && leads.length > 0 ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Nome</TableHead>
                    <TableHead>Empresa</TableHead>
                    <TableHead>Score</TableHead>
                    <TableHead>Qualidade</TableHead>
                    <TableHead>Origem</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {leads.map((lead: any, index: number) => {
                    const score = lead?.score || lead?.lead_score || 0;
                    const scoreDisplay = score <= 1 ? `${(score * 100).toFixed(0)}%` : score.toFixed(1);

                    return (
                      <TableRow key={lead?.id || lead?.user_id || index}>
                        <TableCell className="font-medium">
                          {lead?.nome || lead?.name || lead?.user_name || `Lead ${index + 1}`}
                        </TableCell>
                        <TableCell className="text-sm text-[hsl(var(--muted-foreground))]">
                          {lead?.empresa || lead?.company || lead?.organization || '--'}
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <div className="w-16 h-1.5 bg-[hsl(var(--muted))] rounded-full overflow-hidden">
                              <div
                                className="h-full bg-amber-500 rounded-full transition-all"
                                style={{ width: `${Math.min(score <= 1 ? score * 100 : score, 100)}%` }}
                              />
                            </div>
                            <span className="text-sm font-medium">{scoreDisplay}</span>
                          </div>
                        </TableCell>
                        <TableCell>
                          {getQualityBadge(lead?.qualidade || lead?.quality || lead?.lead_quality || '')}
                        </TableCell>
                        <TableCell className="text-sm text-[hsl(var(--muted-foreground))]">
                          {lead?.origem || lead?.source || lead?.channel || '--'}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            ) : (
              <div className="flex flex-col items-center justify-center py-8 text-[hsl(var(--muted-foreground))]">
                <Users className="w-10 h-10 mb-2 opacity-50" />
                <p className="text-sm">Nenhum lead encontrado</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Análise de Churn */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Activity className="w-5 h-5 text-red-500" />
              <CardTitle>Análise de Churn</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            {/* Summary */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
              <div className="p-3 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))]">
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Taxa de Churn</p>
                <p className="text-lg font-bold text-[hsl(var(--foreground))] mt-1">
                  {typeof riscoChurn === 'number' && riscoChurn > 0
                    ? `${(riscoChurn * (riscoChurn <= 1 ? 100 : 1)).toFixed(1)}%`
                    : '--'}
                </p>
              </div>
              <div className="p-3 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))]">
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Usuários em Risco</p>
                <p className="text-lg font-bold text-red-500 mt-1">
                  {churnSummary?.usuarios_risco || churnSummary?.at_risk_users || churn?.at_risk_count || 0}
                </p>
              </div>
              <div className="p-3 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))]">
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Retenção</p>
                <p className="text-lg font-bold text-emerald-500 mt-1">
                  {typeof (churnSummary?.retencao || churnSummary?.retention_rate || churn?.retention_rate) === 'number'
                    ? `${(((churnSummary?.retencao || churnSummary?.retention_rate || churn?.retention_rate) as number) * 100).toFixed(1)}%`
                    : '--'}
                </p>
              </div>
            </div>

            {/* Churn items table */}
            {Array.isArray(churnItems) && churnItems.length > 0 ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Nome/Segmento</TableHead>
                    <TableHead>Risco</TableHead>
                    <TableHead>Probabilidade</TableHead>
                    <TableHead>Último Acesso</TableHead>
                    <TableHead>Ação Recomendada</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {churnItems.map((item: any, index: number) => {
                    const prob = item?.probabilidade || item?.probability || item?.churn_probability || 0;

                    return (
                      <TableRow key={item?.id || item?.user_id || index}>
                        <TableCell className="font-medium">
                          {item?.nome || item?.name || item?.segment || item?.user_name || `Item ${index + 1}`}
                        </TableCell>
                        <TableCell>
                          {getRiskBadge(item?.risco || item?.risk_level || prob)}
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <div className="w-16 h-1.5 bg-[hsl(var(--muted))] rounded-full overflow-hidden">
                              <div
                                className="h-full bg-red-500 rounded-full transition-all"
                                style={{ width: `${Math.min(prob <= 1 ? prob * 100 : prob, 100)}%` }}
                              />
                            </div>
                            <span className="text-sm">
                              {prob <= 1 ? `${(prob * 100).toFixed(0)}%` : `${prob.toFixed(1)}%`}
                            </span>
                          </div>
                        </TableCell>
                        <TableCell className="text-sm text-[hsl(var(--muted-foreground))]">
                          {item?.ultimo_acesso || item?.last_active || item?.last_seen
                            ? new Date(item?.ultimo_acesso || item?.last_active || item?.last_seen).toLocaleDateString('pt-BR')
                            : '--'}
                        </TableCell>
                        <TableCell className="text-sm text-[hsl(var(--muted-foreground))] max-w-xs truncate">
                          {item?.acao || item?.recommended_action || item?.action || '--'}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            ) : (
              <div className="flex flex-col items-center justify-center py-8 text-[hsl(var(--muted-foreground))]">
                <Activity className="w-10 h-10 mb-2 opacity-50" />
                <p className="text-sm">Nenhum dado de churn disponível</p>
              </div>
            )}
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
