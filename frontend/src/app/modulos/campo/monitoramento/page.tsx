'use client';

import { Monitor, Activity, Wifi, WifiOff, AlertTriangle, RefreshCw, CheckCircle2, Eye, ArrowLeft, AlertCircle, Clock } from 'lucide-react';
import { useState } from 'react';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { PageHeader } from '@/components/ui/page-header';
import { StatCard } from '@/components/ui/stat-card';
;
import { MonitoramentoDetailModal } from '@/components/campo/monitoramento-detail-modal';
import { useMonitoringHealth, useMonitoringMetrics, useMonitoringStatus } from '@/hooks/campo/useCampo';

export default function MonitoramentoPage() {
  const { data: healthRaw, isLoading: healthLoading, isError: healthError, refetch: refetchHealth } = useMonitoringHealth();
  const { data: metricsRaw, isLoading: metricsLoading, isError: metricsError } = useMonitoringMetrics();
  const { data: statusRaw, isLoading: statusLoading, isError: statusError, refetch: refetchStatus } = useMonitoringStatus();

  // Cast to any to access dynamic fields not in generated types
  const health = healthRaw as any;
  const metrics = metricsRaw as any;
  const status = statusRaw as any;

  const [selectedEvento, setSelectedEvento] = useState<any>(null);
  const [detailOpen, setDetailOpen] = useState(false);

  const isLoading = healthLoading && metricsLoading && statusLoading;
  const hasError = healthError && metricsError && statusError;

  // Stats derivados dos hooks
  const agentesOnline = status?.agentes_online ?? metrics?.agentes_online ?? health?.agents_online ?? 0;
  const statusSistema = health?.status ?? status?.status ?? 'unknown';
  const alertasAtivos = health?.alertas ?? metrics?.alertas_ativos ?? status?.alertas ?? 0;
  const ultimoSync = health?.last_check ?? metrics?.ultimo_sync ?? status?.ultimo_sync ?? null;

  // Lista de agentes/servicos do status
  const agentes: any[] = status?.agentes ?? status?.services ?? health?.services ?? [];

  const formatDateTime = (date: string | null | undefined) => {
    if (!date) return '-';
    return new Date(date).toLocaleString('pt-BR');
  };

  const getSystemStatusColor = (s: string) => {
    const map: Record<string, string> = {
      healthy: 'text-green-500',
      ok: 'text-green-500',
      online: 'text-green-500',
      degraded: 'text-yellow-500',
      warning: 'text-yellow-500',
      unhealthy: 'text-red-500',
      offline: 'text-red-500',
      critical: 'text-red-500',
    };
    return map[s] || 'text-gray-500';
  };

  const getSystemStatusLabel = (s: string) => {
    const map: Record<string, string> = {
      healthy: 'Saudavel',
      ok: 'Operacional',
      online: 'Online',
      degraded: 'Degradado',
      warning: 'Atencao',
      unhealthy: 'Indisponivel',
      offline: 'Offline',
      critical: 'Critico',
    };
    return map[s] || s || 'Desconhecido';
  };

  const getStatusBadge = (s: string) => {
    const statusMap: Record<string, { label: string; className: string }> = {
      online: { label: 'Online', className: 'bg-green-100 text-green-800' },
      healthy: { label: 'Saudavel', className: 'bg-green-100 text-green-800' },
      ok: { label: 'OK', className: 'bg-green-100 text-green-800' },
      offline: { label: 'Offline', className: 'bg-red-100 text-red-800' },
      unhealthy: { label: 'Indisponivel', className: 'bg-red-100 text-red-800' },
      degraded: { label: 'Degradado', className: 'bg-yellow-100 text-yellow-800' },
      warning: { label: 'Atencao', className: 'bg-yellow-100 text-yellow-800' },
    };
    const config = statusMap[s] || { label: s || '-', className: 'bg-gray-100 text-gray-800' };
    return <Badge className={config.className}>{config.label}</Badge>;
  };

  const handleRefreshAll = () => {
    refetchHealth();
    refetchStatus();
  };

  const handleViewDetail = (agente: any) => {
    setSelectedEvento(agente);
    setDetailOpen(true);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-grid">
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <PageHeader
          eyebrow="CAMPO"
          title="Monitoramento"
          subtitle="Acompanhamento em tempo real"
          icon={<Monitor className="w-5 h-5" />}
          actions={
            <>
              <Link href="/modulos/campo">
                <Button variant="ghost" size="sm">
                  <ArrowLeft className="w-4 h-4 mr-2" />
                  Campo
                </Button>
              </Link>
              <div className="flex items-center gap-1 text-xs text-[hsl(var(--muted-foreground))]">
                <Activity className="w-3 h-3" />
                Auto-refresh: 30s
              </div>
              <Button variant="outline" size="sm" onClick={handleRefreshAll}>
                <RefreshCw className="w-4 h-4 mr-2" />
                Atualizar
              </Button>
            </>
          }
        />

        {/* Error State */}
        {hasError && (
          <div className="bg-destructive/10 border border-destructive/20 rounded-xl p-4 mb-6 flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-destructive flex-shrink-0" />
            <p className="text-destructive text-sm">
              Erro ao carregar dados de monitoramento. O sistema tentara novamente automaticamente.
            </p>
          </div>
        )}

        {/* Stats Cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <StatCard
            icon={<Wifi className="w-4 h-4" />}
            color="#22c55e"
            label="Agentes Online"
            value={agentesOnline}
          />

          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                  statusSistema === 'healthy' || statusSistema === 'ok'
                    ? 'bg-green-500/10'
                    : statusSistema === 'degraded' || statusSistema === 'warning'
                    ? 'bg-yellow-500/10'
                    : 'bg-red-500/10'
                }`}>
                  <CheckCircle2 className={`w-5 h-5 ${getSystemStatusColor(statusSistema)}`} />
                </div>
                <div>
                  <p className={`text-lg font-bold ${getSystemStatusColor(statusSistema)}`}>
                    {getSystemStatusLabel(statusSistema)}
                  </p>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Status Sistema</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <StatCard
            icon={<AlertTriangle className="w-4 h-4" />}
            color="#eab308"
            label="Alertas Ativos"
            value={alertasAtivos}
          />

          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
                  <Clock className="w-5 h-5 text-blue-500" />
                </div>
                <div>
                  <p className="text-sm font-bold text-[hsl(var(--foreground))]">
                    {formatDateTime(ultimoSync)}
                  </p>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Ultimo Sync</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Health Check Results */}
        {health && (
          <Card className="mb-6">
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Activity className="w-4 h-4" />
                Health Check
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {health.services && typeof health.services === 'object' && !Array.isArray(health.services) ? (
                  Object.entries(health.services).map(([key, value]: [string, any]) => (
                    <div
                      key={key}
                      className="p-3 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--muted))]/20"
                    >
                      <div className="flex items-center justify-between mb-1">
                        <p className="text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">{key}</p>
                        {typeof value === 'string' ? (
                          getStatusBadge(value)
                        ) : value?.status ? (
                          getStatusBadge(value.status)
                        ) : (
                          <Badge className="bg-gray-100 text-gray-800">-</Badge>
                        )}
                      </div>
                      {typeof value === 'object' && value?.latency && (
                        <p className="text-xs text-[hsl(var(--muted-foreground))]">
                          Latencia: {value.latency}ms
                        </p>
                      )}
                    </div>
                  ))
                ) : Array.isArray(health.services) ? (
                  health.services.map((svc: any, idx: number) => (
                    <div
                      key={svc.name || idx}
                      className="p-3 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--muted))]/20"
                    >
                      <div className="flex items-center justify-between mb-1">
                        <p className="text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                          {svc.name || svc.service || `Servico ${idx + 1}`}
                        </p>
                        {getStatusBadge(svc.status)}
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="col-span-full text-center py-4">
                    <p className="text-sm text-[hsl(var(--muted-foreground))]">
                      Dados de health check indisponiveis
                    </p>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Agents Status Grid */}
        {agentes.length > 0 ? (
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Monitor className="w-4 h-4" />
                Status dos Agentes
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-[hsl(var(--border))] bg-[hsl(var(--muted))]/30">
                      <th className="text-left px-4 py-3 text-xs font-semibold text-[hsl(var(--muted-foreground))] uppercase">Agente / Servico</th>
                      <th className="text-center px-4 py-3 text-xs font-semibold text-[hsl(var(--muted-foreground))] uppercase">Status</th>
                      <th className="text-left px-4 py-3 text-xs font-semibold text-[hsl(var(--muted-foreground))] uppercase">Localizacao</th>
                      <th className="text-left px-4 py-3 text-xs font-semibold text-[hsl(var(--muted-foreground))] uppercase">Ultima Atividade</th>
                      <th className="text-center px-4 py-3 text-xs font-semibold text-[hsl(var(--muted-foreground))] uppercase">Ações</th>
                    </tr>
                  </thead>
                  <tbody>
                    {agentes.map((agente, index) => (
                      <tr
                        key={agente.id || agente.name || index}
                        className={`border-b border-[hsl(var(--border))]/50 hover:bg-[hsl(var(--muted))]/20 transition-colors ${
                          index % 2 === 0 ? '' : 'bg-[hsl(var(--muted))]/10'
                        }`}
                      >
                        <td className="px-4 py-3 text-sm font-medium text-[hsl(var(--foreground))]">
                          <div className="flex items-center gap-2">
                            {agente.status === 'online' || agente.status === 'healthy' ? (
                              <Wifi className="w-4 h-4 text-green-500" />
                            ) : (
                              <WifiOff className="w-4 h-4 text-red-500" />
                            )}
                            {agente.agente || agente.nome || agente.name || '-'}
                          </div>
                        </td>
                        <td className="px-4 py-3 text-center">
                          {getStatusBadge(agente.status)}
                        </td>
                        <td className="px-4 py-3 text-sm text-[hsl(var(--muted-foreground))]">
                          {agente.localizacao || agente.local || '-'}
                        </td>
                        <td className="px-4 py-3 text-sm text-[hsl(var(--muted-foreground))]">
                          {formatDateTime(agente.ultima_atividade || agente.last_activity || agente.updated_at)}
                        </td>
                        <td className="px-4 py-3 text-center">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleViewDetail(agente)}
                          >
                            <Eye className="w-4 h-4" />
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        ) : !hasError ? (
          /* Empty State */
          <Card>
            <CardContent className="py-12">
              <div className="text-center">
                <Monitor className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
                <h3 className="text-lg font-medium text-[hsl(var(--foreground))]">
                  Nenhum agente em monitoramento
                </h3>
                <p className="text-[hsl(var(--muted-foreground))] mt-1">
                  Os dados de monitoramento serão exibidos quando houver agentes ativos.
                </p>
                <Button variant="outline" size="sm" className="mt-4" onClick={handleRefreshAll}>
                  <RefreshCw className="w-4 h-4 mr-2" />
                  Atualizar Agora
                </Button>
              </div>
            </CardContent>
          </Card>
        ) : null}
      </main>

      {/* Detail Modal */}
      <MonitoramentoDetailModal
        isOpen={detailOpen}
        onClose={() => { setDetailOpen(false); setSelectedEvento(null); }}
        evento={selectedEvento}
      />
    </div>
  );
}
