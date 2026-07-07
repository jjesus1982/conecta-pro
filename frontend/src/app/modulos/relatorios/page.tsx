'use client';

import { LayoutDashboard, ClipboardCheck, PieChart, TrendingUp, RefreshCw, ArrowRight, BarChart3, AlertCircle, FileText } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
;
import { useDashboardHealth } from '@/hooks/analytics';

const reportModules = [
  {
    title: 'Central de Relatorios PDF',
    description: 'Gere relatorios em PDF com dados reais: certidoes, headcount, GED, financeiro.',
    icon: FileText,
    href: '/modulos/relatorios/central',
    color: 'text-red-500',
    bg: 'bg-red-500/10',
  },
  {
    title: 'Dashboards Executivos',
    description: 'KPIs estratégicos, alertas ativos e insights preditivos para tomada de decisão.',
    icon: LayoutDashboard,
    href: '/modulos/relatorios/dashboards',
    color: 'text-blue-500',
    bg: 'bg-blue-500/10',
  },
  {
    title: 'Operacional',
    description: 'Escalas, ocorrências, SLA e monitoramento de postos em tempo real.',
    icon: ClipboardCheck,
    href: '/modulos/relatorios/operacional',
    color: 'text-emerald-500',
    bg: 'bg-emerald-500/10',
  },
  {
    title: 'Financeiro',
    description: 'Previsão de receita, análise de fraude e indicadores de inadimplência.',
    icon: PieChart,
    href: '/modulos/relatorios/financeiro',
    color: 'text-violet-500',
    bg: 'bg-violet-500/10',
  },
  {
    title: 'Comercial',
    description: 'Scoring de leads, análise de churn e métricas de conversão.',
    icon: TrendingUp,
    href: '/modulos/relatorios/comercial',
    color: 'text-amber-500',
    bg: 'bg-amber-500/10',
  },
];

export default function RelatoriosPage() {
  const router = useRouter();
  const { data: healthData, isLoading: healthLoading, refetch: refetchHealth } = useDashboardHealth();

  const healthStatus = (healthData as any)?.status || 'unknown';
  const isHealthy = healthStatus === 'healthy' || healthStatus === 'ok';

  return (
    <div className="min-h-screen bg-grid">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-[hsl(var(--background))]/80 backdrop-blur-xl border-b border-[hsl(var(--border))]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-indigo-500/10 flex items-center justify-center">
                <BarChart3 className="w-5 h-5 text-indigo-500" />
              </div>
              <div>
                <h1 className="text-lg font-semibold text-[hsl(var(--foreground))]">
                  Relatórios
                </h1>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">
                  Dashboards gerenciais e relatórios analíticos
                </p>
              </div>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetchHealth()}
              disabled={healthLoading}
            >
              <RefreshCw className={`w-4 h-4 mr-2 ${healthLoading ? 'animate-spin' : ''}`} />
              Atualizar
            </Button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Card>
            <CardContent className="pt-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">
                    Relatórios Disponíveis
                  </p>
                  <p className="font-data text-3xl font-semibold tabular-nums text-[hsl(var(--foreground))] mt-1">4</p>
                  <p className="text-xs text-[hsl(var(--muted-foreground))] mt-1">
                    Módulos de análise
                  </p>
                </div>
                <div className="w-12 h-12 rounded-lg bg-indigo-500/10 flex items-center justify-center">
                  <BarChart3 className="w-6 h-6 text-indigo-500" />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">
                    Status do Sistema
                  </p>
                  <div className="flex items-center gap-2 mt-1">
                    {healthLoading ? (
                      <RefreshCw className="w-5 h-5 animate-spin text-[hsl(var(--muted-foreground))]" />
                    ) : (
                      <>
                        <div
                          className={`w-3 h-3 rounded-full ${
                            isHealthy ? 'bg-green-500' : 'bg-red-500'
                          }`}
                        />
                        <p className="text-xl font-bold text-[hsl(var(--foreground))]">
                          {isHealthy ? 'Operacional' : 'Indisponível'}
                        </p>
                      </>
                    )}
                  </div>
                  <p className="text-xs text-[hsl(var(--muted-foreground))] mt-1">
                    Analytics Engine
                  </p>
                </div>
                <div
                  className={`w-12 h-12 rounded-lg flex items-center justify-center ${
                    isHealthy ? 'bg-green-500/10' : 'bg-red-500/10'
                  }`}
                >
                  {isHealthy ? (
                    <BarChart3 className="w-6 h-6 text-green-500" />
                  ) : (
                    <AlertCircle className="w-6 h-6 text-red-500" />
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Module Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {reportModules.map((module) => (
            <Card
              key={module.href}
              variant="interactive"
              onClick={() => router.push(module.href)}
              className="group"
            >
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className={`w-10 h-10 rounded-lg ${module.bg} flex items-center justify-center`}>
                      <module.icon className={`w-5 h-5 ${module.color}`} />
                    </div>
                    <CardTitle className="text-base">{module.title}</CardTitle>
                  </div>
                  <ArrowRight className="w-4 h-4 text-[hsl(var(--muted-foreground))] group-hover:text-[hsl(var(--primary))] transition-colors" />
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-[hsl(var(--muted-foreground))]">
                  {module.description}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      </main>
    </div>
  );
}
