'use client';

import { Users, UserPlus, Target, Building2, FileText, RefreshCw, ArrowRight, Phone, Mail, Calendar, MessageSquare, Clock } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { PageHeader } from '@/components/ui/page-header';
import { StatCard } from '@/components/ui/stat-card';
import { customInstance } from '@/lib/api-client';
import { useCRMDashboardKpis } from '@/hooks/crm';
import { formatCurrency } from '@/lib/utils';
import { TaxasWidget } from '@/components/crm/TaxasWidget';

export default function CRMDashboardPage() {
  const router = useRouter();
  const { data: kpis, isLoading, refetch } = useCRMDashboardKpis();
  const { data: activitiesData, isLoading: activitiesLoading } = useQuery<any[]>({
    queryKey: ['crm-activities-recent'],
    queryFn: () => customInstance<any[]>({ url: '/api/v1/crm/activities/recent', method: 'GET' }),
    staleTime: 30_000,
  });

  const kpiData = kpis as any;

  const activityTypeConfig: Record<string, { icon: typeof Phone; color: string; bg: string; label: string }> = {
    call: { icon: Phone, color: 'text-blue-600', bg: 'bg-blue-100', label: 'Ligacao' },
    email: { icon: Mail, color: 'text-purple-600', bg: 'bg-purple-100', label: 'Email' },
    meeting: { icon: Calendar, color: 'text-green-600', bg: 'bg-green-100', label: 'Reuniao' },
    note: { icon: MessageSquare, color: 'text-orange-600', bg: 'bg-orange-100', label: 'Nota' },
  };

  const getActivityConfig = (type: string) =>
    activityTypeConfig[type] || { icon: Clock, color: 'text-gray-600', bg: 'bg-gray-100', label: type || 'Atividade' };

  const formatRelativeTime = (dateStr: string) => {
    try {
      const date = new Date(dateStr);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffMin = Math.floor(diffMs / 60000);
      if (diffMin < 1) return 'agora';
      if (diffMin < 60) return `${diffMin}min atras`;
      const diffH = Math.floor(diffMin / 60);
      if (diffH < 24) return `${diffH}h atras`;
      const diffD = Math.floor(diffH / 24);
      return `${diffD}d atras`;
    } catch {
      return dateStr || '-';
    }
  };

  const cards = [
    {
      title: 'Leads',
      description: 'Gerenciar leads e captacao',
      icon: UserPlus,
      href: '/modulos/crm/leads',
      value: kpiData?.leads_total || 0,
      subtitle: `${kpiData?.leads_new_month || 0} novos este mes`,
      color: 'text-blue-600',
      bgColor: 'bg-blue-50',
    },
    {
      title: 'Oportunidades',
      description: 'Pipeline de vendas',
      icon: Target,
      href: '/modulos/crm/oportunidades',
      value: kpiData?.opportunities_total || 0,
      subtitle: kpiData?.pipeline_value ? formatCurrency(kpiData.pipeline_value) : 'Pipeline',
      color: 'text-purple-600',
      bgColor: 'bg-purple-50',
    },
    {
      title: 'Clientes',
      description: 'Base de clientes ativos',
      icon: Building2,
      href: '/modulos/crm/clientes',
      value: kpiData?.clientes_total ?? kpiData?.leads_qualified ?? 0,
      subtitle: `${kpiData?.condominios_total ?? 0} condomínios`,
      color: 'text-green-600',
      bgColor: 'bg-green-50',
    },
    {
      title: 'Propostas',
      description: 'Propostas comerciais',
      icon: FileText,
      href: '/modulos/crm/propostas',
      value: kpiData?.proposals_total || 0,
      subtitle: kpiData?.proposals_total_value ? formatCurrency(kpiData.proposals_total_value) : 'Valor total',
      color: 'text-orange-600',
      bgColor: 'bg-orange-50',
    },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <PageHeader
        eyebrow="COMERCIAL"
        title="CRM"
        subtitle="Gestao de relacionamento com clientes"
        icon={<Users className="w-5 h-5" />}
        actions={
          <Button variant="outline" onClick={() => refetch()} disabled={isLoading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
            Atualizar
          </Button>
        }
      />

      {/* KPI Summary */}
      {kpiData && (
        <div className="grid gap-4 md:grid-cols-3">
          <StatCard
            icon={<Target className="w-4 h-4" />}
            color="#16a34a"
            label="Win Rate"
            value={kpiData.opportunities_win_rate ? `${(kpiData.opportunities_win_rate * 100).toFixed(1)}%` : '0%'}
          />
          <StatCard
            icon={<Users className="w-4 h-4" />}
            label="Ticket Medio"
            value={formatCurrency(kpiData.avg_deal_size || 0)}
          />
          <StatCard
            icon={<Clock className="w-4 h-4" />}
            label="Ciclo Medio"
            value={`${kpiData.avg_sales_cycle_days || 0} dias`}
          />
        </div>
      )}

      {/* Taxas do dia */}
      <TaxasWidget />

      {/* Cards de navegacao */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {cards.map((card) => (
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
              <div className="font-data text-2xl font-semibold tabular-nums">{isLoading ? '...' : card.value}</div>
              <p className="text-xs text-muted-foreground mt-1">{card.subtitle}</p>
              <div className="flex items-center gap-1 mt-2 text-xs text-primary">
                <span>Acessar</span>
                <ArrowRight className="h-3 w-3" />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Contatos card */}
      <Card
        className="cursor-pointer hover:shadow-md transition-shadow"
        onClick={() => router.push('/modulos/crm/contatos')}
      >
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-lg bg-cyan-50 flex items-center justify-center">
                <Users className="h-5 w-5 text-cyan-600" />
              </div>
              <div>
                <h3 className="font-medium">Contatos</h3>
                <p className="text-sm text-muted-foreground">Gerenciar contatos vinculados a clientes</p>
              </div>
            </div>
            <ArrowRight className="h-5 w-5 text-muted-foreground" />
          </div>
        </CardContent>
      </Card>

      {/* Atividades Recentes */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <CardTitle className="text-lg font-semibold flex items-center gap-2">
            <Clock className="h-5 w-5" />
            Atividades Recentes
          </CardTitle>
          {activitiesData && (
            <Badge variant="secondary">{activitiesData.length} atividade{activitiesData.length !== 1 ? 's' : ''}</Badge>
          )}
        </CardHeader>
        <CardContent>
          {activitiesLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary" />
            </div>
          ) : !activitiesData || activitiesData.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <Clock className="h-12 w-12 mx-auto mb-3 opacity-40" />
              <p className="text-sm">Nenhuma atividade recente</p>
            </div>
          ) : (
            <div className="space-y-4">
              {(Array.isArray(activitiesData) ? activitiesData : []).slice(0, 10).map((activity: any, idx: number) => {
                const config = getActivityConfig(activity.type || activity.activity_type);
                const IconComp = config.icon;
                return (
                  <div key={activity.id || idx} className="flex items-start gap-3">
                    <div className={`h-8 w-8 rounded-full ${config.bg} flex items-center justify-center flex-shrink-0 mt-0.5`}>
                      <IconComp className={`h-4 w-4 ${config.color}`} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-sm truncate">
                          {activity.subject || activity.title || config.label}
                        </span>
                        <Badge variant="outline" className="text-xs flex-shrink-0">
                          {config.label}
                        </Badge>
                      </div>
                      <div className="flex items-center gap-2 mt-0.5">
                        {(activity.client_name || activity.lead_name) && (
                          <span className="text-xs text-muted-foreground truncate">
                            {activity.client_name || activity.lead_name}
                          </span>
                        )}
                        <span className="text-xs text-muted-foreground flex-shrink-0">
                          {formatRelativeTime(activity.created_at || activity.date)}
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
