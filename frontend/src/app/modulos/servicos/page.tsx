'use client';

import { FileSignature, ClipboardList, Calendar, RefreshCw, ArrowRight, AlertCircle } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
;
import { useContractStats, useContractAlerts } from '@/hooks/contracts';

export default function ServicosPage() {
  const router = useRouter();
  const { data: stats, isLoading: statsLoading, error: statsError, refetch: refetchStats } = useContractStats();
  const { data: alerts, isLoading: alertsLoading, refetch: refetchAlerts } = useContractAlerts();

  const isLoading = statsLoading || alertsLoading;

  const contratosAtivos = (stats as any)?.active_count || 0;
  const totalAlertas = Array.isArray(alerts) ? alerts.length : (alerts as any)?.total || 0;

  const handleRefresh = () => {
    refetchStats();
    refetchAlerts();
  };

  const cards = [
    {
      title: 'Contratos',
      description: 'Gestao de contratos de servico',
      icon: FileSignature,
      href: '/modulos/servicos/contratos',
      value: contratosAtivos,
      valueLabel: 'Ativos',
      color: 'text-blue-600',
      bgColor: 'bg-blue-50',
    },
    {
      title: 'Ordens de Servico',
      description: 'Gestao de ordens de servico',
      icon: ClipboardList,
      href: '/modulos/servicos/ordens',
      value: 0,
      valueLabel: 'Abertas',
      color: 'text-purple-600',
      bgColor: 'bg-purple-50',
    },
    {
      title: 'Agendamentos',
      description: 'Agendamentos de visitas e servicos',
      icon: Calendar,
      href: '/modulos/servicos/agendamentos',
      value: 0,
      valueLabel: 'Hoje',
      color: 'text-green-600',
      bgColor: 'bg-green-50',
    },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <FileSignature className="h-6 w-6" />
            Servicos
          </h1>
          <p className="text-muted-foreground">Gestao de contratos, ordens de servico e agendamentos</p>
        </div>
        <Button variant="outline" onClick={handleRefresh} disabled={isLoading}>
          <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
          Atualizar
        </Button>
      </div>

      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Contratos Ativos</CardTitle>
            <FileSignature className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-blue-600">
              {isLoading ? '...' : contratosAtivos}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">OS Abertas</CardTitle>
            <ClipboardList className="h-4 w-4 text-purple-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-purple-600">0</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Agendamentos Hoje</CardTitle>
            <Calendar className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-green-600">0</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Alertas</CardTitle>
            <AlertCircle className="h-4 w-4 text-orange-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-orange-600">
              {isLoading ? '...' : totalAlertas}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Error */}
      {statsError && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-destructive" />
          <p className="text-sm text-destructive flex-1">Erro ao carregar estatisticas</p>
          <Button variant="outline" size="sm" onClick={handleRefresh}>
            Tentar novamente
          </Button>
        </div>
      )}

      {/* Navigation Cards */}
      <div className="grid gap-4 md:grid-cols-3">
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
              <p className="text-xs text-muted-foreground mt-1">{card.description}</p>
              <div className="flex items-center gap-1 mt-2 text-xs text-primary">
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
