'use client';

import { Shield, MapPin, Calendar, Users, Clock, ChevronRight, ArrowLeft, Search, Plus, AlertCircle, CheckCircle, CheckCircle2, XCircle, UserCheck, FileWarning, Navigation, TrendingUp, TrendingDown, Activity, FileText, CalendarCheck, AlertTriangle, Brain } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
;
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useAuth } from '@/hooks/useAuth';
import { usePostStats } from '@/hooks/usePosts';
import { useScaleStats } from '@/hooks/useScales';
import { useOccurrenceStats } from '@/hooks/useOccurrences';
import { useTodayShifts } from '@/hooks/useShifts';
import { useKPITrends } from '@/hooks/useKPITrends';
import { KPIWidget, KPIWidgetSkeleton } from '@/components/ui/kpi-widget';
import { OperacionalTourProvider } from '@/features/onboarding/components/OperacionalTourProvider';
import { TourTrigger } from '@/features/onboarding/components/TourTrigger';
import { PageHeader } from '@/components/ui/page-header';
import { StatCard } from '@/components/ui/stat-card';

// Sub-módulos do Operacional
const subModules = [
  {
    id: 'ai-command-center',
    title: 'AI Command Center',
    description: 'Centro de comando inteligente com 6 agentes de IA operacional',
    icon: Brain,
    href: '/modulos/operacional/ai-command-center',
    color: 'purple',
    stats: null,
  },
  {
    id: 'postos',
    title: 'Postos de Trabalho',
    description: 'Gerenciar postos, locais e requisitos de trabalho',
    icon: MapPin,
    href: '/modulos/operacional/postos',
    color: 'cyan',
    stats: { label: 'postos ativos', key: 'total' },
  },
  {
    id: 'colaboradores',
    title: 'Colaboradores',
    description: 'Gerenciar colaboradores e equipes operacionais',
    icon: UserCheck,
    href: '/modulos/operacional/colaboradores',
    color: 'purple',
    stats: null,
  },
  {
    id: 'escalas',
    title: 'Escalas',
    description: 'Criar e gerenciar escalas mensais de trabalho',
    icon: Calendar,
    href: '/modulos/operacional/escalas',
    color: 'blue',
    stats: { label: 'escalas', key: 'scales' },
  },
  {
    id: 'alocacoes',
    title: 'Alocações',
    description: 'Alocar funcionários nos postos de trabalho',
    icon: Users,
    href: '/modulos/operacional/alocacoes',
    color: 'green',
    stats: { label: 'alocados', key: 'total_allocated' },
  },
  {
    id: 'turnos',
    title: 'Turnos',
    description: 'Visualizar e gerenciar turnos diários',
    icon: Clock,
    href: '/modulos/operacional/turnos',
    color: 'orange',
    stats: { label: 'turnos hoje', key: 'shifts' },
  },
  {
    id: 'ocorrencias',
    title: 'Ocorrências',
    description: 'Registrar e acompanhar ocorrências operacionais',
    icon: FileWarning,
    href: '/modulos/operacional/ocorrencias',
    color: 'red',
    stats: null,
  },
  {
    id: 'rondas',
    title: 'Rondas',
    description: 'Gerenciar rondas e pontos de verificação',
    icon: Navigation,
    href: '/modulos/operacional/rondas',
    color: 'indigo',
    stats: null,
  },
  {
    id: 'diaristas',
    title: 'Diaristas',
    description: 'Gestão de diaristas com IA e avaliações',
    icon: Users,
    href: '/modulos/operacional/diaristas',
    color: 'cyan',
    stats: null,
  },
  {
    id: 'substituicoes',
    title: 'Substituições',
    description: 'Gerenciar substituições de funcionários',
    icon: UserCheck,
    href: '/modulos/operacional/substituicoes',
    color: 'orange',
    stats: null,
  },
  {
    id: 'banco-horas',
    title: 'Banco de Horas',
    description: 'Controle de horas extras e compensações',
    icon: Clock,
    href: '/modulos/operacional/banco-horas',
    color: 'purple',
    stats: null,
  },
];

export default function OperacionalPage() {
  const router = useRouter();
  const { user, isLoading: authLoading, isAuthenticated } = useAuth();
  const { stats, isLoading: statsLoading } = usePostStats();
  const { stats: scaleStats, isLoading: scaleStatsLoading } = useScaleStats();
  const { stats: occurrenceStats, isLoading: occurrenceStatsLoading } = useOccurrenceStats();
  const { shifts: todayShifts, isLoading: shiftsLoading } = useTodayShifts();
  const { data: trendsData, isLoading: trendsLoading } = useKPITrends({ period: '7d' });

  const moduleStats = {
    postos: stats?.total,
    escalas: scaleStats?.total,
    alocacoes: stats?.total_allocated,
    turnos: shiftsLoading ? null : todayShifts.length,
  } as const;

  // KPIs Estratégicos
  const coverageRate = stats?.total && stats.filled
    ? Math.round((stats.filled / stats.total) * 100)
    : 0;

  const monthlyHours = scaleStats?.total_hours || 0;

  // Delta REAL da cobertura no período (último − primeiro ponto da série de trends).
  // Sem série suficiente → sem tendência (nada de percentual inventado).
  const coverageSeries = trendsData?.cobertura_percentual;
  const coverageFirst = Array.isArray(coverageSeries) ? coverageSeries[0] : undefined;
  const coverageLast = Array.isArray(coverageSeries)
    ? coverageSeries[coverageSeries.length - 1]
    : undefined;
  const coverageChange =
    typeof coverageFirst === 'number' && typeof coverageLast === 'number' && coverageSeries!.length >= 2
      ? Math.round((coverageLast - coverageFirst) * 10) / 10
      : undefined;

  const pendingOccurrences = occurrenceStats?.pending_resolution || 0;

  const activeScales = scaleStats?.by_status?.in_progress || 0;

  const shiftsNeedingSubstitution = todayShifts.filter(
    (shift) => shift.needs_substitution
  ).length;

  // Redirecionar se não autenticado
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [authLoading, isAuthenticated, router]);

  if (authLoading || statsLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))]">
        <div className="animate-pulse-slow text-[hsl(var(--primary))]">
          <Shield className="w-12 h-12" />
        </div>
      </div>
    );
  }

  return (
    <OperacionalTourProvider userRole="USUARIO" autoStart={false} showNotification={false}>
    <div className="min-h-screen bg-grid">
      {/* Main content */}
      <main className="py-6">
        <PageHeader
          eyebrow="OPERACIONAL"
          title="Operacional"
          subtitle="Gestao de postos, escalas e alocacoes"
          icon={<Shield className="w-5 h-5" />}
          actions={
            <>
              <Link href="/dashboard">
                <Button variant="ghost" size="sm">
                  <ArrowLeft className="w-4 h-4 mr-2" />
                  Voltar
                </Button>
              </Link>
              <TourTrigger variant="menu-item" />
            </>
          }
        />
        {/* KPIs Estratégicos */}
        <div className="mb-8" data-tour="dashboard-kpis">
          <h2 className="text-lg font-semibold text-[hsl(var(--foreground))] mb-4">
            KPIs Estratégicos
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-5 gap-4">
            {/* Postos Ativos */}
            {statsLoading || trendsLoading ? (
              <KPIWidgetSkeleton />
            ) : (
              <KPIWidget
                title="Postos Ativos"
                value={stats?.total || 0}
                icon={MapPin}
                iconColor="text-cyan-500"
                iconBgColor="bg-cyan-500/10"
                onClick={() => router.push('/modulos/operacional/postos')}
                sparklineData={trendsData?.postos_ativos}
                sparklineColor="#06b6d4"
              />
            )}

            {/* Colaboradores Ativos */}
            {statsLoading || trendsLoading ? (
              <KPIWidgetSkeleton />
            ) : (
              <KPIWidget
                title="Colaboradores Ativos"
                value={stats?.total_allocated || 0}
                icon={UserCheck}
                iconColor="text-purple-500"
                iconBgColor="bg-purple-500/10"
                onClick={() => router.push('/modulos/operacional/colaboradores')}
                sparklineData={trendsData?.colaboradores_ativos}
                sparklineColor="#a855f7"
              />
            )}

            {/* Escalas em Andamento */}
            {scaleStatsLoading || trendsLoading ? (
              <KPIWidgetSkeleton />
            ) : (
              <KPIWidget
                title="Escalas em Andamento"
                value={activeScales}
                icon={CalendarCheck}
                iconColor="text-blue-500"
                iconBgColor="bg-blue-500/10"
                onClick={() => router.push('/modulos/operacional/escalas')}
                sparklineData={trendsData?.escalas_em_andamento}
                sparklineColor="#3b82f6"
              />
            )}

            {/* Ocorrências Pendentes */}
            {occurrenceStatsLoading || trendsLoading ? (
              <KPIWidgetSkeleton />
            ) : (
              <KPIWidget
                title="Ocorrências Pendentes"
                value={pendingOccurrences}
                icon={FileText}
                iconColor={
                  pendingOccurrences === 0
                    ? 'text-green-500'
                    : pendingOccurrences < 5
                    ? 'text-yellow-500'
                    : 'text-red-500'
                }
                iconBgColor={
                  pendingOccurrences === 0
                    ? 'bg-green-500/10'
                    : pendingOccurrences < 5
                    ? 'bg-yellow-500/10'
                    : 'bg-red-500/10'
                }
                onClick={() => router.push('/modulos/operacional/ocorrencias')}
                sparklineData={trendsData?.ocorrencias_mes}
                sparklineColor={
                  pendingOccurrences === 0
                    ? '#22c55e'
                    : pendingOccurrences < 5
                    ? '#eab308'
                    : '#ef4444'
                }
              />
            )}

            {/* Taxa de Cobertura */}
            {statsLoading || trendsLoading ? (
              <KPIWidgetSkeleton />
            ) : (
              <KPIWidget
                title="Cobertura de Postos"
                value={`${coverageRate}%`}
                change={coverageChange}
                changeType={
                  coverageChange === undefined || coverageChange === 0
                    ? 'neutral'
                    : coverageChange > 0
                    ? 'positive'
                    : 'negative'
                }
                icon={Activity}
                iconColor={
                  coverageRate >= 90
                    ? 'text-green-500'
                    : coverageRate >= 70
                    ? 'text-yellow-500'
                    : 'text-red-500'
                }
                iconBgColor={
                  coverageRate >= 90
                    ? 'bg-green-500/10'
                    : coverageRate >= 70
                    ? 'bg-yellow-500/10'
                    : 'bg-red-500/10'
                }
                onClick={() => router.push('/modulos/operacional/postos')}
                sparklineData={trendsData?.cobertura_percentual}
                sparklineColor={
                  coverageRate >= 90
                    ? '#22c55e'
                    : coverageRate >= 70
                    ? '#eab308'
                    : '#ef4444'
                }
              />
            )}
          </div>
        </div>

        {/* Stats Cards */}
        <div className="mb-8" data-tour="analytics-charts">
          <h2 className="text-lg font-semibold text-[hsl(var(--foreground))] mb-4">
            Visão Geral Rápida
          </h2>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard
              icon={<MapPin className="w-4 h-4" />}
              color="#06b6d4"
              label="Postos"
              value={stats?.total || 0}
              onClick={() => router.push('/modulos/operacional/postos')}
            />
            <StatCard
              icon={<CheckCircle className="w-4 h-4" />}
              color="#22c55e"
              label="Preenchidos"
              value={stats?.filled || 0}
              onClick={() => router.push('/modulos/operacional/postos')}
            />
            <StatCard
              icon={<AlertCircle className="w-4 h-4" />}
              color="#f97316"
              label="Com vagas"
              value={stats?.with_vacancy || 0}
              onClick={() => router.push('/modulos/operacional/postos')}
            />
            <StatCard
              icon={<Users className="w-4 h-4" />}
              color="#3b82f6"
              label="Alocados"
              value={stats?.total_allocated || 0}
              onClick={() => router.push('/modulos/operacional/alocacoes')}
            />
          </div>
        </div>

        {/* Sub-modules Grid */}
        <div className="mb-8" data-tour="team-panel" data-tour-operations="operations-panel">
          <h2 className="text-lg font-semibold text-[hsl(var(--foreground))] mb-4">
            Módulos Operacionais
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {subModules.map((module) => {
            const Icon = module.icon;
            const isDisabled = false;

            return (
              <Link
                key={module.id}
                href={isDisabled ? '#' : module.href}
                className={isDisabled ? 'cursor-not-allowed' : ''}
              >
                <div
                  className={`
                    group relative bg-[hsl(var(--card))] border border-[hsl(var(--border))]
                    rounded-xl p-6 transition-all duration-200
                    ${isDisabled ? 'opacity-60' : 'hover:border-[hsl(var(--primary))] hover:shadow-lg'}
                  `}
                >
                  <div className="flex items-start gap-4">
                    <div
                      className={`
                        w-12 h-12 rounded-xl flex items-center justify-center
                        ${module.color === 'cyan' ? 'bg-cyan-500/10' : ''}
                        ${module.color === 'blue' ? 'bg-blue-500/10' : ''}
                        ${module.color === 'green' ? 'bg-green-500/10' : ''}
                        ${module.color === 'orange' ? 'bg-orange-500/10' : ''}
                        ${module.color === 'purple' ? 'bg-purple-500/10' : ''}
                        ${module.color === 'red' ? 'bg-red-500/10' : ''}
                        ${module.color === 'indigo' ? 'bg-indigo-500/10' : ''}
                      `}
                    >
                      <Icon
                        className={`
                          w-6 h-6
                          ${module.color === 'cyan' ? 'text-cyan-500' : ''}
                          ${module.color === 'blue' ? 'text-blue-500' : ''}
                          ${module.color === 'green' ? 'text-green-500' : ''}
                          ${module.color === 'orange' ? 'text-orange-500' : ''}
                          ${module.color === 'purple' ? 'text-purple-500' : ''}
                          ${module.color === 'red' ? 'text-red-500' : ''}
                          ${module.color === 'indigo' ? 'text-indigo-500' : ''}
                        `}
                      />
                    </div>
                  <div className="flex-1">
                    <h3 className="text-lg font-semibold text-[hsl(var(--foreground))] mb-1">
                      {module.title}
                    </h3>
                    <p className="text-sm text-[hsl(var(--muted-foreground))]">
                      {module.description}
                    </p>
                    {module.stats && (
                      <p className="text-xs text-[hsl(var(--muted-foreground))] mt-3">
                        {module.stats.label}:{' '}
                        <span className="text-[hsl(var(--foreground))] font-semibold">
                          {moduleStats[module.id as keyof typeof moduleStats] ?? '...'}
                        </span>
                      </p>
                    )}
                  </div>
                    <ChevronRight
                      className={`
                        w-5 h-5 text-[hsl(var(--muted-foreground))]
                        transition-transform group-hover:translate-x-1
                        ${isDisabled ? 'hidden' : ''}
                      `}
                    />
                  </div>
                </div>
              </Link>
            );
          })}
          </div>
        </div>

        {/* Quick Stats by Type */}
        {stats && Object.keys(stats.by_type).length > 0 && (
          <div className="mt-8">
            <h2 className="text-lg font-semibold text-[hsl(var(--foreground))] mb-4">
              Postos por Tipo
            </h2>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
              {Object.entries(stats.by_type).map(([type, count]) => (
                <div
                  key={type}
                  className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-lg p-3 text-center"
                >
                  <p className="text-xl font-bold text-[hsl(var(--foreground))]">{count}</p>
                  <p className="text-xs text-[hsl(var(--muted-foreground))] capitalize">
                    {type.replace(/_/g, ' ')}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* AI Command Center Section */}
        <div className="bg-gradient-to-r from-blue-950/50 to-indigo-950/50 rounded-xl border border-blue-900/30 p-6 mt-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-8 h-8 rounded-lg bg-blue-500/20 flex items-center justify-center">
              <Brain className="w-4 h-4 text-blue-400" />
            </div>
            <h3 className="text-white font-semibold text-sm">Centro de Comando IA</h3>
            <span className="ml-auto text-xs text-blue-400/70">Centro de Inteligência</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-black/20 rounded-lg p-4">
              <p className="text-xs text-zinc-500 mb-1">Status Operacional</p>
              <p className="text-sm font-semibold text-green-400 flex items-center gap-1.5">
                {coverageRate >= 90 ? (
                  <><CheckCircle2 className="w-4 h-4" /> Operação Normal</>
                ) : coverageRate >= 70 ? (
                  <><AlertTriangle className="w-4 h-4" /> Atenção Necessária</>
                ) : (
                  <><XCircle className="w-4 h-4" /> Cobertura Crítica</>
                )}
              </p>
              <p className="text-xs text-zinc-600 mt-1">{coverageRate}% de cobertura</p>
            </div>
            <div className="bg-black/20 rounded-lg p-4">
              <p className="text-xs text-zinc-500 mb-1">Risco Próximas 24h</p>
              <p className={`text-sm font-semibold flex items-center gap-1.5 ${shiftsNeedingSubstitution > 2 ? 'text-red-400' : shiftsNeedingSubstitution > 0 ? 'text-yellow-400' : 'text-green-400'}`}>
                {shiftsNeedingSubstitution > 2 ? (
                  <><AlertTriangle className="w-4 h-4" /> Alto</>
                ) : shiftsNeedingSubstitution > 0 ? (
                  <><AlertTriangle className="w-4 h-4" /> Moderado</>
                ) : (
                  <><CheckCircle2 className="w-4 h-4" /> Baixo</>
                )}
              </p>
              <p className="text-xs text-zinc-600 mt-1">
                {shiftsNeedingSubstitution} {shiftsNeedingSubstitution === 1 ? 'turno em atenção' : 'turnos em atenção'}
              </p>
            </div>
            <div className="bg-black/20 rounded-lg p-4">
              <p className="text-xs text-zinc-500 mb-1">Ação Recomendada</p>
              <p className="text-sm font-semibold text-blue-400">
                {shiftsNeedingSubstitution > 0 ? 'Ver Substituições' : pendingOccurrences > 0 ? 'Resolver Ocorrências' : 'Tudo em Ordem'}
              </p>
              <p className="text-xs text-zinc-600 mt-1">
                {shiftsNeedingSubstitution > 0
                  ? `${shiftsNeedingSubstitution} solicitação${shiftsNeedingSubstitution > 1 ? 'ões' : ''} pendente${shiftsNeedingSubstitution > 1 ? 's' : ''}`
                  : pendingOccurrences > 0
                  ? `${pendingOccurrences} ocorrência${pendingOccurrences > 1 ? 's' : ''} aberta${pendingOccurrences > 1 ? 's' : ''}`
                  : 'Nenhuma ação urgente'}
              </p>
            </div>
          </div>
        </div>
      </main>
    </div>
    </OperacionalTourProvider>
  );
}
