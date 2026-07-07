'use client';

import { Heart, Stethoscope, HardHat, AlertTriangle, FileCheck, ShieldAlert, Package, ArrowRight, FileText, UserX, Pill, Shield } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useRouter } from 'next/navigation';
import { usePCMSOStatistics, useEPIStatistics, usePPRAStatistics } from '@/hooks/health-occupational';
import { useSSTDashboard } from '@/hooks/sst';

const subPages = [
  {
    title: 'Exames Medicos (PCMSO)',
    description: 'Gestao de exames ocupacionais, ASOs e agendamentos conforme NR-7',
    icon: Stethoscope,
    href: '/modulos/gestao-pessoas/saude-ocupacional/exames',
    color: 'text-blue-600',
    bg: 'bg-blue-50',
  },
  {
    title: 'EPIs (NR-6)',
    description: 'Controle de equipamentos de protecao individual, entregas e estoque',
    icon: HardHat,
    href: '/modulos/gestao-pessoas/saude-ocupacional/epi',
    color: 'text-purple-600',
    bg: 'bg-purple-50',
  },
  {
    title: 'Riscos Ocupacionais (PPRA/PGR)',
    description: 'Mapeamento de riscos, medidas de controle e analise por setor',
    icon: AlertTriangle,
    href: '/modulos/gestao-pessoas/saude-ocupacional/riscos',
    color: 'text-orange-600',
    bg: 'bg-orange-50',
  },
  {
    title: 'LTCAT (NR-15 / Lei 8.213)',
    description: 'Laudo Tecnico das Condicoes Ambientais do Trabalho - agentes de risco e aposentadoria especial',
    icon: FileText,
    href: '/modulos/gestao-pessoas/saude-ocupacional/ltcat',
    color: 'text-teal-600',
    bg: 'bg-teal-50',
  },
  {
    title: 'CAT - Acidente de Trabalho',
    description: 'Registro e acompanhamento de Comunicacoes de Acidente de Trabalho',
    icon: AlertTriangle,
    href: '/modulos/gestao-pessoas/saude-ocupacional/cat',
    color: 'text-red-600',
    bg: 'bg-red-50',
  },
  {
    title: 'Afastamentos',
    description: 'Controle de afastamentos de colaboradores',
    icon: UserX,
    href: '/modulos/gestao-pessoas/saude-ocupacional/afastamentos',
    color: 'text-yellow-600',
    bg: 'bg-yellow-50',
  },
  {
    title: 'Estabilidade Pos-Acidente',
    description: 'Controle de colaboradores em periodo de estabilidade provisoria (CCT Clausula 29a)',
    icon: Shield,
    href: '/modulos/gestao-pessoas/saude-ocupacional/estabilidade',
    color: 'text-indigo-600',
    bg: 'bg-indigo-50',
  },
  {
    title: 'Ajuda Medicamento',
    description: 'Benefício CCT Clausula 15a - Auxilio medicamento R$ 300/mes',
    icon: Pill,
    href: '/modulos/gestao-pessoas/saude-ocupacional/ajuda-medicamento',
    color: 'text-emerald-600',
    bg: 'bg-emerald-50',
  },
];

export default function SaudeOcupacionalPage() {
  const router = useRouter();
  const { data: pcmsoStats, isLoading: pcmsoLoading } = usePCMSOStatistics();
  const { data: epiStats, isLoading: epiLoading } = useEPIStatistics();
  const { data: ppraStats, isLoading: ppraLoading } = usePPRAStatistics();
  const { data: dashboard, isLoading: dashboardLoading } = useSSTDashboard();

  const statsLoading = pcmsoLoading || epiLoading || ppraLoading || dashboardLoading;

  return (
    <div className="space-y-6 pb-28">
      {/* Header */}
      <div>
        <h1 className="font-display text-2xl font-bold flex items-center gap-2">
          <Heart className="h-6 w-6" />
          Saude Ocupacional
        </h1>
        <p className="text-muted-foreground">
          Gestao integrada de saude e seguranca do trabalho - PCMSO, EPIs, PPRA/PGR, SST.
        </p>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Exames</CardTitle>
            <Stethoscope className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums">{(pcmsoStats as any)?.total_exames ?? 0}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">ASOs Vencendo</CardTitle>
            <FileCheck className="h-4 w-4 text-yellow-600" />
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-yellow-600">
                {(dashboard as any)?.asos_vencendo_30d ?? (pcmsoStats as any)?.asos_vencendo ?? 0}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Afastados Ativos</CardTitle>
            <UserX className="h-4 w-4 text-orange-600" />
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-orange-600">
                {(dashboard as any)?.afastados_ativos ?? 0}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Riscos Mapeados</CardTitle>
            <ShieldAlert className="h-4 w-4 text-red-600" />
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-red-600">
                {(ppraStats as any)?.total_riscos ?? 0}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Sub-page navigation cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {subPages.map((page) => (
          <Card
            key={page.href}
            className="cursor-pointer transition-all hover:shadow-md hover:border-primary/30"
            onClick={() => router.push(page.href)}
          >
            <CardContent className="flex items-center gap-4 p-6">
              <div className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-lg ${page.bg}`}>
                <page.icon className={`h-6 w-6 ${page.color}`} />
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="font-semibold">{page.title}</h3>
                <p className="text-sm text-muted-foreground">{page.description}</p>
              </div>
              <ArrowRight className="h-5 w-5 shrink-0 text-muted-foreground" />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
