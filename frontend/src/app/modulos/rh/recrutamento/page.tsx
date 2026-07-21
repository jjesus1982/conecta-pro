'use client';

import { useState, useEffect, useCallback } from 'react';
import { Users, Briefcase, UserPlus, FileText, Calendar, RefreshCw, ArrowRight } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

const API_BASE = '/api/v1/recruitment';

function getAuthHeaders() {
  const token = typeof window !== 'undefined' ? (localStorage.getItem('access_token') || localStorage.getItem('token')) : null;
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export default function RecrutamentoDashboardPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [posStats, setPosStats] = useState<any>(null);
  const [candStats, setCandStats] = useState<any>(null);
  const [appStats, setAppStats] = useState<any>(null);
  const [intStats, setIntStats] = useState<any>(null);
  const [hasError, setHasError] = useState(false);

  const fetchStats = useCallback(async () => {
    setLoading(true);
    setHasError(false);
    try {
      const headers = getAuthHeaders();
      const [posRes, candRes, appRes, intRes] = await Promise.allSettled([
        fetch(`${API_BASE}/job-positions/stats`, { headers }),
        fetch(`${API_BASE}/candidates/stats`, { headers }),
        fetch(`${API_BASE}/applications/stats`, { headers }),
        fetch(`${API_BASE}/interviews/stats`, { headers }),
      ]);

      if (posRes.status === 'fulfilled' && posRes.value.ok) {
        setPosStats(await posRes.value.json());
      }
      if (candRes.status === 'fulfilled' && candRes.value.ok) {
        setCandStats(await candRes.value.json());
      }
      if (appRes.status === 'fulfilled' && appRes.value.ok) {
        setAppStats(await appRes.value.json());
      }
      if (intRes.status === 'fulfilled' && intRes.value.ok) {
        setIntStats(await intRes.value.json());
      }

      const allFailed = [posRes, candRes, appRes, intRes].every(
        r => r.status === 'rejected' || (r.status === 'fulfilled' && !r.value.ok)
      );
      if (allFailed) {
        setHasError(true);
      }
    } catch {
      setHasError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchStats(); }, [fetchStats]);

  const statCards = [
    {
      title: 'Vagas Abertas',
      value: posStats?.open_positions ?? 0,
      subtitle: `${posStats?.total_positions ?? 0} vagas no total`,
      icon: Briefcase,
      color: 'text-blue-600',
      bgColor: 'bg-blue-50',
    },
    {
      title: 'Candidatos Ativos',
      value: candStats?.active_candidates ?? 0,
      subtitle: `${candStats?.total_candidates ?? 0} candidatos cadastrados`,
      icon: UserPlus,
      color: 'text-green-600',
      bgColor: 'bg-green-50',
    },
    {
      title: 'Candidaturas Ativas',
      value: appStats?.active_applications ?? appStats?.in_process ?? 0,
      subtitle: `${appStats?.total_applications ?? 0} candidaturas no total`,
      icon: FileText,
      color: 'text-purple-600',
      bgColor: 'bg-purple-50',
    },
    {
      title: 'Entrevistas Agendadas',
      value: intStats?.scheduled ?? 0,
      subtitle: `${intStats?.total_interviews ?? 0} entrevistas no total`,
      icon: Calendar,
      color: 'text-orange-600',
      bgColor: 'bg-orange-50',
    },
  ];

  const navCards = [
    {
      title: 'Vagas',
      description: 'Gerenciar vagas e posicoes abertas',
      icon: Briefcase,
      href: '/modulos/rh/recrutamento/vagas',
      color: 'text-blue-600',
      bgColor: 'bg-blue-50',
    },
    {
      title: 'Candidatos',
      description: 'Base de candidatos cadastrados',
      icon: UserPlus,
      href: '/modulos/rh/recrutamento/candidatos',
      color: 'text-green-600',
      bgColor: 'bg-green-50',
    },
    {
      title: 'Candidaturas',
      description: 'Acompanhar candidaturas e etapas',
      icon: FileText,
      href: '/modulos/rh/recrutamento/candidaturas',
      color: 'text-purple-600',
      bgColor: 'bg-purple-50',
    },
    {
      title: 'Entrevistas',
      description: 'Agenda de entrevistas e avaliacoes',
      icon: Calendar,
      href: '/modulos/rh/recrutamento/entrevistas',
      color: 'text-orange-600',
      bgColor: 'bg-orange-50',
    },
  ];

  return (
    <div className="space-y-6 pb-28">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <Users className="h-6 w-6" />
            Recrutamento e Selecao
          </h1>
          <p className="text-muted-foreground">
            Gerencie vagas, candidatos, candidaturas e entrevistas
          </p>
        </div>
        <Button variant="outline" onClick={fetchStats} disabled={loading}>
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          Atualizar
        </Button>
      </div>

      {/* Error Banner */}
      {hasError && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-800/30 dark:bg-red-900/20 dark:text-red-400">
          <p className="font-medium">Erro ao carregar dados do recrutamento</p>
          <p className="mt-1 text-red-600 dark:text-red-500">
            Alguns servicos estao temporariamente indisponiveis. Tente novamente.
          </p>
          <Button variant="outline" size="sm" className="mt-2" onClick={fetchStats}>
            <RefreshCw className="h-3 w-3 mr-1" /> Tentar novamente
          </Button>
        </div>
      )}

      {/* Stat Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {statCards.map((card) => (
          <Card key={card.title}>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">{card.title}</p>
                  <p className="font-data text-2xl font-semibold tabular-nums">
                    {loading ? '...' : card.value}
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">{card.subtitle}</p>
                </div>
                <div className={`h-10 w-10 rounded-lg ${card.bgColor} flex items-center justify-center`}>
                  <card.icon className={`h-5 w-5 ${card.color}`} />
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Navigation Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {navCards.map((card) => (
          <Card
            key={card.title}
            className="cursor-pointer hover:shadow-md transition-shadow"
            onClick={() => router.push(card.href)}
          >
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">{card.title}</CardTitle>
              <card.icon className={`h-5 w-5 ${card.color}`} />
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">{card.description}</p>
              <div className="flex items-center gap-1 mt-3 text-xs text-primary">
                <span>Acessar</span>
                <ArrowRight className="h-3 w-3" />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
