'use client';

import { useState, useEffect } from 'react';
import { Brain, UserCheck, Users, Heart, CalendarClock, CheckCircle, Clock, AlertCircle, Loader2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { PageHeader } from '@/components/ui/page-header';

const API_HR = '/api/v1/people-management/hr';
const API_RH = '/api/v1/people-management/human-resources';

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

const StatusBadge = ({ status }: { status: string }) => {
  if (status === 'active' || status === 'Ativo') return (
    <span className="flex items-center gap-1 text-xs text-green-400">
      <CheckCircle className="h-3 w-3" />Ativo
    </span>
  );
  if (status === 'running') return (
    <span className="flex items-center gap-1 text-xs text-blue-400">
      <Loader2 className="h-3 w-3 animate-spin" />Executando
    </span>
  );
  return (
    <span className="flex items-center gap-1 text-xs text-yellow-400">
      <AlertCircle className="h-3 w-3" />Em Desenvolvimento
    </span>
  );
};

export default function IAPage() {
  const [featureStatus, setFeatureStatus] = useState<Record<string, string>>({});

  const features = [
    {
      title: 'Scoring de Candidatos',
      description: 'Analise automatica de curriculos e ranking de candidatos com base em competencias.',
      icon: UserCheck,
      color: 'text-blue-400',
      bgColor: 'bg-blue-900/30',
      skill: 'smart_recruiter',
      endpoint: `${API_RH}/recruitment`,
    },
    {
      title: 'Previsao de Turnover',
      description: 'Modelo preditivo que identifica colaboradores com risco de desligamento.',
      icon: Users,
      color: 'text-red-400',
      bgColor: 'bg-red-900/30',
      skill: 'hr_predictor',
      endpoint: `${API_RH}/turnover/dashboard`,
    },
    {
      title: 'Analise de Clima',
      description: 'Processamento de respostas abertas de pesquisas de clima organizacional.',
      icon: Heart,
      color: 'text-green-400',
      bgColor: 'bg-green-900/30',
      skill: 'performance_evaluator',
      endpoint: `${API_RH}/climate/dashboard`,
    },
    {
      title: 'Otimizacao de Escalas',
      description: 'Alocação otimizada de colaboradores em postos considerando competencias e custos.',
      icon: CalendarClock,
      color: 'text-purple-400',
      bgColor: 'bg-purple-900/30',
      skill: 'workforce_planner',
      endpoint: `${API_HR}/employees`,
    },
  ];

  useEffect(() => {
    async function checkStatus() {
      const statuses: Record<string, string> = {};
      for (const f of features) {
        try {
          const res = await fetch(`${f.endpoint}?limit=1`, { headers: getAuthHeaders() });
          statuses[f.skill] = res.ok ? 'active' : 'inactive';
        } catch {
          statuses[f.skill] = 'inactive';
        }
      }
      setFeatureStatus(statuses);
    }
    checkStatus();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="space-y-6 pb-28">
      <PageHeader
        icon={<Brain className="h-5 w-5" />}
        title="Inteligencia Artificial de Pessoas"
        subtitle="12 AI Skills integradas a gestao de pessoas"
      />

      <div className="grid gap-4 md:grid-cols-2">
        {features.map((f) => (
          <Card key={f.title} className="hover:shadow-md transition-shadow">
            <CardHeader className="flex flex-row items-start gap-4 space-y-0">
              <div className={`h-12 w-12 rounded-lg ${f.bgColor} flex items-center justify-center shrink-0`}>
                <f.icon className={`h-6 w-6 ${f.color}`} />
              </div>
              <div className="flex-1">
                <CardTitle className="text-sm font-medium">{f.title}</CardTitle>
                <p className="text-sm text-muted-foreground mt-1">{f.description}</p>
              </div>
            </CardHeader>
            <CardContent>
              <div className="flex items-center justify-between text-xs text-muted-foreground border-t border-gray-800 pt-3">
                <span className="flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  Skill: {f.skill}
                </span>
                <StatusBadge status={featureStatus[f.skill] || 'checking'} />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader><CardTitle className="text-sm">Skills Disponiveis (12 agentes)</CardTitle></CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
            {[
              'payroll_master', 'compliance_guardian', 'smart_documenter', 'benefits_optimizer',
              'smart_recruiter', 'training_advisor', 'performance_evaluator', 'hr_predictor',
              'smart_onboarder', 'workforce_planner', 'smart_notifier', 'people_orchestrator',
            ].map(skill => (
              <div key={skill} className="px-3 py-2 bg-gray-800/50 rounded text-xs text-muted-foreground flex items-center gap-2">
                <CheckCircle className="h-3 w-3 text-green-500" />
                {skill}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
