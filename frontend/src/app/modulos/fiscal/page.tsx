'use client';

import { Landmark, FileText, Users, Database, FileSpreadsheet, FileCode, Award, RefreshCw, ArrowRight, AlertCircle, Receipt } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { PageHeader } from '@/components/ui/page-header';
import { StatCard } from '@/components/ui/stat-card';
import { useObterDashboardMonitoramento, useHealthCheck } from '@/hooks/government';

export default function FiscalDashboardPage() {
  const router = useRouter();
  const {
    data: dashboardData,
    isLoading,
    isError,
    error,
    refetch,
  } = useObterDashboardMonitoramento();
  const { data: healthData } = useHealthCheck();

  // Cards com DADO REAL: o dashboard de monitoramento gov não traz nfse/certidões,
  // então os cards ficavam "0" divergindo dos 80 reais das outras telas.
  const [realStats, setRealStats] = useState<{ nfse?: number; certidoes?: number }>({});
  useEffect(() => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
    const H = { ...(token ? { Authorization: `Bearer ${token}` } : {}) };
    fetch('/api/v1/financial/fiscal/dashboard', { headers: H })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => d?.stats?.total_nfse_emitidas != null && setRealStats((p) => ({ ...p, nfse: d.stats.total_nfse_emitidas })))
      .catch(() => {});
    fetch('/api/v1/ged/certidoes', { headers: H })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        const total = Array.isArray(d?.certidoes) ? d.certidoes.length : (Array.isArray(d) ? d.length : null);
        if (total != null) setRealStats((p) => ({ ...p, certidoes: total }));
      })
      .catch(() => {});
  }, []);

  const dashboard = dashboardData as any;
  const nfseEmitidas = realStats.nfse ?? dashboard?.nfse_emitidas ?? dashboard?.nfse?.total ?? 0;
  const esocialPendente = dashboard?.esocial_pendente ?? dashboard?.esocial?.pendentes ?? 0;
  const certidoesCount = realStats.certidoes ?? dashboard?.certidoes ?? dashboard?.certificados?.total ?? 0;
  const syncStatus = healthData?.status ?? dashboard?.sync_status ?? 'offline';

  const syncOnline = syncStatus === 'ok' || syncStatus === 'healthy';
  const statsCards = [
    {
      title: 'NFS-e Emitidas',
      value: nfseEmitidas,
      icon: FileText,
      color: '#2563eb',
    },
    {
      title: 'eSocial Pendente',
      value: esocialPendente,
      icon: Users,
      color: '#ea580c',
    },
    {
      title: 'Certidoes',
      value: certidoesCount,
      icon: Award,
      color: '#16a34a',
    },
    {
      title: 'Status Sync',
      value: syncOnline ? 'Online' : 'Offline',
      icon: RefreshCw,
      color: syncOnline ? '#059669' : '#dc2626',
    },
  ];

  const navigationCards = [
    {
      title: 'e-CAC',
      description: 'Situação fiscal, débitos e parcelamentos na Receita (certificado A1)',
      icon: Landmark,
      href: '/modulos/fiscal/ecac',
      color: 'text-rose-600',
      bgColor: 'bg-rose-50',
    },
    {
      title: 'NF-e',
      description: 'Emissão e gestão de Notas Fiscais Eletrônicas (produtos)',
      icon: Receipt,
      href: '/modulos/financeiro/fiscal',
      color: 'text-emerald-600',
      bgColor: 'bg-emerald-50',
    },
    {
      title: 'NFS-e',
      description: 'Emissao e gestao de Notas Fiscais de Servico Eletronica',
      icon: FileText,
      href: '/modulos/fiscal/nfse',
      color: 'text-blue-600',
      bgColor: 'bg-blue-50',
    },
    {
      title: 'eSocial',
      description: 'Eventos trabalhistas e previdenciarios',
      icon: Users,
      href: '/modulos/fiscal/esocial',
      color: 'text-purple-600',
      bgColor: 'bg-purple-50',
    },
    {
      title: 'SPED',
      description: 'Sistema Publico de Escrituracao Digital',
      icon: Database,
      href: '/modulos/fiscal/sped',
      color: 'text-indigo-600',
      bgColor: 'bg-indigo-50',
    },
    {
      title: 'DCTFWeb',
      description: 'Declaracao de Debitos e Creditos Tributarios',
      icon: FileSpreadsheet,
      href: '/modulos/fiscal/dctfweb',
      color: 'text-teal-600',
      bgColor: 'bg-teal-50',
    },
    {
      title: 'EFD-Reinf',
      description: 'Escrituracao Fiscal Digital de Retencoes e Informações',
      icon: FileCode,
      href: '/modulos/fiscal/reinf',
      color: 'text-cyan-600',
      bgColor: 'bg-cyan-50',
    },
    {
      title: 'Certidoes',
      description: 'Gestao de certidoes e certificados digitais',
      icon: Award,
      href: '/modulos/fiscal/certidoes',
      color: 'text-amber-600',
      bgColor: 'bg-amber-50',
    },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <PageHeader
        eyebrow="FISCAL"
        title="Fiscal"
        subtitle="Gestão fiscal, tributária e obrigações acessórias"
        icon={<Landmark className="h-5 w-5" />}
        actions={
          <Button variant="outline" onClick={() => refetch()} disabled={isLoading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
            Atualizar
          </Button>
        }
      />

      {/* Error */}
      {isError && (
        <div className="flex items-center gap-3 p-4 rounded-lg bg-[hsl(var(--destructive))]/10 border border-[hsl(var(--destructive))]/30">
          <AlertCircle className="w-5 h-5 text-[hsl(var(--destructive))]" />
          <div>
            <p className="font-medium text-[hsl(var(--destructive))]">Erro ao carregar dashboard</p>
            <p className="text-sm text-[hsl(var(--muted-foreground))]">
              {(error as Error)?.message || 'Tente novamente em alguns instantes'}
            </p>
          </div>
          <Button variant="secondary" size="sm" onClick={() => refetch()} className="ml-auto">
            Tentar novamente
          </Button>
        </div>
      )}

      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {statsCards.map((card) => (
          <StatCard
            key={card.title}
            label={card.title}
            value={isLoading ? '...' : card.value}
            icon={<card.icon className="h-4 w-4" />}
            color={card.color}
          />
        ))}
      </div>

      {/* Navigation Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {navigationCards.map((card) => (
          <Card
            key={card.title}
            variant="interactive"
            className="cursor-pointer"
            onClick={() => router.push(card.href)}
          >
            <CardContent className="pt-6">
              <div className="flex items-start gap-4">
                <div className={`w-12 h-12 rounded-lg ${card.bgColor} flex items-center justify-center flex-shrink-0`}>
                  <card.icon className={`h-6 w-6 ${card.color}`} />
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="font-semibold text-[hsl(var(--foreground))]">{card.title}</h3>
                  <p className="text-sm text-[hsl(var(--muted-foreground))] mt-1">
                    {card.description}
                  </p>
                  <div className="flex items-center gap-1 mt-3 text-sm text-[hsl(var(--primary))]">
                    <span>Acessar</span>
                    <ArrowRight className="h-4 w-4" />
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
