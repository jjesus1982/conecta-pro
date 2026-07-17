'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { customInstance } from '@/lib/api-client';
import {
  Clock,
  AlertTriangle,
  Timer,
  RefreshCw,
  ChevronRight,
  Fingerprint,
  FileText,
  CalendarX,
  Hourglass,
  Lock,
  Loader2,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { PageHeader } from '@/components/ui/page-header';

interface PontoDashboardData {
  total_colaboradores: number;
  presentes_hoje: number;
  ausentes_hoje: number;
  afastados: number;
  inconsistencias_periodo: number;
  sem_escala: number;
  pontos_em_aberto: number;
  banco_horas: {
    total_credito: number;
    total_debito: number;
    saldo_medio: number;
  };
  por_escala: Record<string, number>;
  ultima_sync_solides: string | null;
}

const quickLinks = [
  { label: 'Bater Ponto', href: '/modulos/gestao-pessoas/ponto/batida', icon: Fingerprint, color: 'text-blue-500', bg: 'bg-blue-500/10' },
  { label: 'Espelho de Ponto', href: '/modulos/gestao-pessoas/ponto/espelho', icon: FileText, color: 'text-indigo-500', bg: 'bg-indigo-500/10' },
  { label: 'Justificativas', href: '/modulos/gestao-pessoas/ponto/justificativas', icon: FileText, color: 'text-amber-500', bg: 'bg-amber-500/10' },
  { label: 'Atrasos e Faltas', href: '/modulos/gestao-pessoas/ponto/atrasos', icon: CalendarX, color: 'text-red-500', bg: 'bg-red-500/10' },
  { label: 'Banco de Horas', href: '/modulos/gestao-pessoas/ponto/banco-horas', icon: Hourglass, color: 'text-emerald-500', bg: 'bg-emerald-500/10' },
  { label: 'Fechamento Mensal', href: '/modulos/gestao-pessoas/ponto/fechamento', icon: Lock, color: 'text-[hsl(var(--muted-foreground))]', bg: 'bg-[hsl(var(--secondary))]' },
];

function formatSaldoMedio(horas: number | undefined): string {
  // o backend manda HORAS (float, ex.: -40.9) — exibe como ±HHhMM
  if (horas === undefined || horas === null || isNaN(horas)) return '--';
  const sign = horas >= 0 ? '+' : '-';
  const abs = Math.abs(horas);
  const h = Math.floor(abs);
  const m = Math.round((abs - h) * 60);
  return `${sign}${h}h${String(m).padStart(2, '0')}`;
}

export default function PontoDashboardPage() {
  const router = useRouter();
  const [currentTime, setCurrentTime] = useState(new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }));

  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentTime(new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }));
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  const { data, isLoading, error } = useQuery<PontoDashboardData>({
    queryKey: ['ponto', 'dashboard'],
    queryFn: () => customInstance({ url: '/api/v1/people-management/ponto/dashboard' }) as Promise<PontoDashboardData>,
    staleTime: 30000,
    retry: 2,
  });

  const summaryCards = [
    {
      label: 'Presentes Hoje',
      value: data ? `${data.presentes_hoje} / ${data.total_colaboradores}` : '--',
      icon: Fingerprint,
      color: 'text-blue-500',
      bg: 'bg-blue-500/10',
      detail: data ? `Ausentes: ${data.ausentes_hoje} | Afastados: ${data.afastados}` : 'Carregando...',
    },
    {
      label: 'Inconsistencias',
      value: data ? String(data.inconsistencias_periodo) : '--',
      icon: AlertTriangle,
      color: 'text-amber-500',
      bg: 'bg-amber-500/10',
      detail: data ? `Sem escala: ${data.sem_escala} | Em aberto: ${data.pontos_em_aberto}` : 'Carregando...',
    },
    {
      label: 'Banco de Horas',
      value: data ? formatSaldoMedio(data.banco_horas.saldo_medio) : '--',
      icon: Timer,
      color: data && data.banco_horas.saldo_medio >= 0 ? 'text-emerald-500' : 'text-red-500',
      bg: data && data.banco_horas.saldo_medio >= 0 ? 'bg-emerald-500/10' : 'bg-red-500/10',
      detail: data ? `Credito: ${data.banco_horas.total_credito}h | Debito: ${data.banco_horas.total_debito}h` : 'Carregando...',
    },
    {
      label: 'Sync Solides',
      value: data?.ultima_sync_solides ? 'OK' : 'Pendente',
      icon: RefreshCw,
      color: data?.ultima_sync_solides ? 'text-purple-500' : 'text-[hsl(var(--muted-foreground))]',
      bg: 'bg-purple-500/10',
      detail: data?.ultima_sync_solides ? `Ultimo: ${data.ultima_sync_solides}` : 'Nenhuma sync registrada',
    },
  ];

  return (
    <div className="p-6 space-y-6">
      <PageHeader
        eyebrow="PONTO"
        title="Controle de Ponto"
        subtitle="Gestao de jornada, batidas e banco de horas"
        icon={<Clock className="w-5 h-5" />}
        actions={
          <div className="text-right">
            <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">{currentTime}</p>
            <p className="text-sm text-[hsl(var(--muted-foreground))]">{new Date().toLocaleDateString('pt-BR', { weekday: 'long', day: '2-digit', month: 'long', year: 'numeric' })}</p>
          </div>
        }
      />

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 text-red-500 px-4 py-3 rounded-lg text-sm">
          Erro ao carregar dashboard: {(error as Error).message}
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {summaryCards.map((stat) => {
          const Icon = stat.icon;
          return (
            <Card key={stat.label} className="border border-[hsl(var(--border))]">
              <CardContent className="p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-[hsl(var(--muted-foreground))]">{stat.label}</p>
                    {isLoading ? (
                      <Loader2 className="h-6 w-6 animate-spin text-[hsl(var(--muted-foreground))] mt-2" />
                    ) : (
                      <>
                        <p className="font-data text-2xl font-semibold tabular-nums mt-1">{stat.value}</p>
                        <p className="text-xs text-[hsl(var(--muted-foreground))] mt-1">{stat.detail}</p>
                      </>
                    )}
                  </div>
                  <div className={`p-3 rounded-lg ${stat.bg}`}>
                    <Icon className={`h-5 w-5 ${stat.color}`} />
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {quickLinks.map((link) => {
          const Icon = link.icon;
          return (
            <Card
              key={link.href}
              className="cursor-pointer hover:shadow-lg transition-all duration-200 border border-[hsl(var(--border))] hover:border-[hsl(var(--primary))]/40"
              onClick={() => router.push(link.href)}
            >
              <CardContent className="p-5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className={`p-2 rounded-lg ${link.bg}`}>
                      <Icon className={`h-5 w-5 ${link.color}`} />
                    </div>
                    <span className="font-medium text-[hsl(var(--foreground))]">{link.label}</span>
                  </div>
                  <ChevronRight className="h-5 w-5 text-[hsl(var(--muted-foreground))]" />
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
