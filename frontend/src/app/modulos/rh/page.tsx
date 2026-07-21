'use client';

import { useState, useEffect } from 'react';
import { Users, Briefcase, GraduationCap, ClipboardCheck, Smile, UserPlus, TrendingUp, Heart, BarChart3, Brain, ArrowRight } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { PageHeader } from '@/components/ui/page-header';
import { StatCard } from '@/components/ui/stat-card';

const API_BASE = '/api/v1/people-management/human-resources';

function getAuthHeaders() {
  let token: string | null = null;
  if (typeof window !== 'undefined') {
    try {
      token = localStorage.getItem('access_token') || localStorage.getItem('token');
    } catch {
      token = null;
    }
  }
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export default function RHDashboardPage() {
  const router = useRouter();
  const [stats, setStats] = useState({ courses: 0, reviews: 0, trainings: 0, plans: 0 });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [coursesRes, reviewsRes, trainingsRes, plansRes] = await Promise.all([
          fetch(`${API_BASE}/training/courses?limit=1`, { headers: getAuthHeaders() }).catch(() => null),
          fetch(`${API_BASE}/performance/reviews?limit=1`, { headers: getAuthHeaders() }).catch(() => null),
          fetch(`${API_BASE}/training/?limit=1`, { headers: getAuthHeaders() }).catch(() => null),
          fetch(`${API_BASE}/career/plans?limit=1`, { headers: getAuthHeaders() }).catch(() => null),
        ]);
        const getTotal = async (res: Response | null) => {
          if (res?.ok) { const d = await res.json(); return d.total || (d.items || d || []).length; }
          return 0;
        };
        setStats({
          courses: await getTotal(coursesRes),
          reviews: await getTotal(reviewsRes),
          trainings: await getTotal(trainingsRes),
          plans: await getTotal(plansRes),
        });
      } catch { /* fallback */ } finally { setLoading(false); }
    }
    load();
  }, []);

  const statCards = [
    { title: 'Cursos Ativos', value: loading ? '...' : stats.courses, subtitle: 'Catalogo de cursos', icon: GraduationCap, color: '#16a34a' },
    { title: 'Avaliacoes', value: loading ? '...' : stats.reviews, subtitle: 'Total de avaliacoes', icon: ClipboardCheck, color: '#9333ea' },
    { title: 'Treinamentos', value: loading ? '...' : stats.trainings, subtitle: 'Turmas agendadas', icon: Briefcase, color: '#2563eb' },
    { title: 'Planos de Carreira', value: loading ? '...' : stats.plans, subtitle: 'Em andamento', icon: TrendingUp, color: '#ea580c' },
  ];

  const navCards = [
    { title: 'Recrutamento', description: 'Vagas, candidatos e selecao', icon: UserPlus, href: '/modulos/rh/recrutamento', color: 'text-blue-600' },
    { title: 'Treinamentos', description: 'Agenda e gestao de treinamentos', icon: GraduationCap, href: '/modulos/rh/treinamentos', color: 'text-green-600' },
    { title: 'Avaliacoes', description: 'Avaliacoes de desempenho', icon: ClipboardCheck, href: '/modulos/rh/avaliacoes', color: 'text-purple-600' },
    { title: 'Plano de Carreira', description: 'Desenvolvimento e progressao', icon: TrendingUp, href: '/modulos/rh/carreira', color: 'text-cyan-600' },
    { title: 'Clima', description: 'Pesquisas de clima organizacional', icon: Heart, href: '/modulos/rh/clima', color: 'text-red-600' },
    { title: 'Turnover', description: 'Previsao e analise de turnover', icon: Users, href: '/modulos/rh/turnover', color: 'text-amber-600' },
    { title: 'Onboarding', description: 'Integracao de novos colaboradores', icon: Smile, href: '/modulos/rh/onboarding', color: 'text-teal-600' },
    { title: 'Dashboard', description: 'KPIs e indicadores de RH', icon: BarChart3, href: '/modulos/rh/dashboard', color: 'text-indigo-600' },
    { title: 'IA', description: 'Inteligencia artificial de pessoas', icon: Brain, href: '/modulos/rh/ia', color: 'text-pink-600' },
  ];

  return (
    <div className="space-y-6 pb-28">
      <PageHeader
        icon={<Users className="h-5 w-5" />}
        title="Recursos Humanos"
        subtitle="Recrutamento, treinamento, avaliacao e desenvolvimento"
      />

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {statCards.map((card) => (
          <StatCard
            key={card.title}
            icon={<card.icon className="h-4 w-4" />}
            label={card.title}
            value={card.value}
            sub={card.subtitle}
            color={card.color}
          />
        ))}
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {navCards.map((card) => (
          <Card key={card.title} className="cursor-pointer hover:shadow-md transition-shadow" onClick={() => router.push(card.href)}>
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
