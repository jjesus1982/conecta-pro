'use client';

import { LogIn, Monitor, Bell, RefreshCw, ArrowRight, Users, AlertTriangle, MapPin } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { PageHeader } from '@/components/ui/page-header';
import { StatCard } from '@/components/ui/stat-card';
;
import { useCampoDashboard, useMonitoringHealth } from '@/hooks/campo/useCampo';

/** Shape dos dados retornados pelo dashboard do campo */
interface CampoDashboardData {
  checkins_hoje?: number;
  checkins?: number;
  agentes_em_campo?: number;
  agentes?: number;
  ocorrencias?: number;
  alertas?: number;
  [key: string]: unknown;
}

/** Extensao do HealthStatus para campos opcionais de alerta */
interface HealthDataWithAlerts {
  status?: string;
  alertas?: number;
  [key: string]: unknown;
}

export default function CampoPage() {
  const router = useRouter();
  const {
    data: dashboardRaw,
    isLoading: dashLoading,
    isError: dashError,
    error: dashErrorObj,
    refetch: refetchDash,
  } = useCampoDashboard();
  // health tem refetchInterval e NÃO deve segurar a primeira renderização
  const { data: healthRaw } = useMonitoringHealth();
  const isLoading = dashLoading;

  // Cast para interfaces que refletem os dados reais do backend
  const dashboard = dashboardRaw as CampoDashboardData | undefined;
  const health = healthRaw as HealthDataWithAlerts | undefined;

  const stats = {
    checkinsHoje: dashboard?.checkins_hoje ?? dashboard?.checkins ?? 0,
    agentesEmCampo: dashboard?.agentes_em_campo ?? dashboard?.agentes ?? 0,
    ocorrencias: dashboard?.ocorrencias ?? 0,
    alertas: health?.alertas ?? dashboard?.alertas ?? 0,
  };

  const modules = [
    {
      title: 'Check-in / Check-out',
      description: 'Registros de entrada e saida dos colaboradores nos postos de trabalho.',
      icon: LogIn,
      href: '/modulos/campo/checkin',
      color: 'cyan',
    },
    {
      title: 'Monitoramento',
      description: 'Acompanhamento em tempo real dos agentes em campo e status do sistema.',
      icon: Monitor,
      href: '/modulos/campo/monitoramento',
      color: 'violet',
    },
    {
      title: 'Comunicados',
      description: 'Envio e gestao de comunicados para equipes em campo.',
      icon: Bell,
      href: '/modulos/campo/comunicados',
      color: 'amber',
    },
  ];

  if (isLoading && !dashError) {
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
          eyebrow="OPERACOES"
          title="Campo"
          subtitle="Gestao de operacoes em campo"
          icon={<MapPin className="w-5 h-5" />}
          actions={
            <Button variant="outline" size="sm" onClick={() => refetchDash()}>
              <RefreshCw className="w-4 h-4 mr-2" />
              Atualizar
            </Button>
          }
        />

        {/* Erro honesto ao carregar o dashboard (cards de navegação seguem funcionando) */}
        {dashError && (
          <div className="mb-6 flex items-center justify-between gap-3 rounded-xl border border-red-300 bg-red-500/10 px-4 py-3">
            <div className="flex items-center gap-2 text-sm text-red-700 dark:text-red-400">
              <AlertTriangle className="w-4 h-4 flex-shrink-0" />
              <span>
                Erro ao carregar os indicadores do campo:{' '}
                {(dashErrorObj as Error | undefined)?.message || 'falha de conexão com o servidor'}
              </span>
            </div>
            <Button variant="outline" size="sm" onClick={() => refetchDash()}>
              <RefreshCw className="w-4 h-4 mr-2" />
              Tentar novamente
            </Button>
          </div>
        )}

        {/* Stats Cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <StatCard
            icon={<LogIn className="w-4 h-4" />}
            color="#06b6d4"
            label="Check-ins Hoje"
            value={stats.checkinsHoje}
          />
          <StatCard
            icon={<Users className="w-4 h-4" />}
            color="#22c55e"
            label="Agentes em Campo"
            value={stats.agentesEmCampo}
          />
          <StatCard
            icon={<Monitor className="w-4 h-4" />}
            color="#8b5cf6"
            label="Ocorrencias"
            value={stats.ocorrencias}
          />
          <StatCard
            icon={<AlertTriangle className="w-4 h-4" />}
            color="#ef4444"
            label="Alertas"
            value={stats.alertas}
          />
        </div>

        {/* Module Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {modules.map((mod) => {
            const Icon = mod.icon;
            return (
              <Card
                key={mod.href}
                className="cursor-pointer hover:border-[hsl(var(--primary))]/50 transition-all duration-200 hover:shadow-lg"
                onClick={() => router.push(mod.href)}
              >
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <div className={`w-12 h-12 rounded-lg bg-${mod.color}-500/10 flex items-center justify-center`}>
                      <Icon className={`w-6 h-6 text-${mod.color}-500`} />
                    </div>
                    <ArrowRight className="w-5 h-5 text-[hsl(var(--muted-foreground))]" />
                  </div>
                  <CardTitle className="text-base mt-3">{mod.title}</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-[hsl(var(--muted-foreground))]">
                    {mod.description}
                  </p>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </main>
    </div>
  );
}
