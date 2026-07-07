'use client';

import { ShieldCheck, Eye, CheckCircle2, FileText, Trash2, Lock, ArrowRight, Shield, AlertTriangle, Loader2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
;
import { useRouter } from 'next/navigation';
import { useLGPDStatus, useHealthCheck } from '@/hooks/security-lgpd';

const subPages = [
  {
    title: 'Auditoria',
    description: 'Logs de auditoria LGPD',
    href: '/modulos/seguranca/auditoria',
    icon: Eye,
    color: 'text-purple-600 bg-purple-50 dark:text-purple-400 dark:bg-purple-950',
  },
  {
    title: 'Consentimento',
    description: 'Gestao de consentimentos',
    href: '/modulos/seguranca/consentimento',
    icon: CheckCircle2,
    color: 'text-green-600 bg-green-50 dark:text-green-400 dark:bg-green-950',
  },
  {
    title: 'PIA/DPIA',
    description: 'Avaliacao de impacto',
    href: '/modulos/seguranca/pia-dpia',
    icon: FileText,
    color: 'text-blue-600 bg-blue-50 dark:text-blue-400 dark:bg-blue-950',
  },
  {
    title: 'Esquecimento',
    description: 'Direito ao esquecimento',
    href: '/modulos/seguranca/esquecimento',
    icon: Trash2,
    color: 'text-red-600 bg-red-50 dark:text-red-400 dark:bg-red-950',
  },
  {
    title: 'Mascaramento',
    description: 'Mascaramento de dados',
    href: '/modulos/seguranca/mascaramento',
    icon: Eye,
    color: 'text-amber-600 bg-amber-50 dark:text-amber-400 dark:bg-amber-950',
  },
  {
    title: 'Criptografia',
    description: 'Criptografia de dados',
    href: '/modulos/seguranca/criptografia',
    icon: Lock,
    color: 'text-cyan-600 bg-cyan-50 dark:text-cyan-400 dark:bg-cyan-950',
  },
];

export default function SegurancaPage() {
  const router = useRouter();
  const { data: lgpdData, isLoading: lgpdLoading } = useLGPDStatus();
  const { data: healthData, isLoading: healthLoading } = useHealthCheck();

  const isLoading = lgpdLoading || healthLoading;

  // Cast data para acessar propriedades dinamicas do backend
  const lgpdStatus = lgpdData?.data as Record<string, unknown> | undefined;
  const activeConsents = (lgpdStatus?.active_consents ?? lgpdStatus?.consentimentos_ativos ?? 0) as number;
  const piasCompleted = (lgpdStatus?.pias_completed ?? lgpdStatus?.pias_realizadas ?? 0) as number;
  const erasureRequests = (lgpdStatus?.erasure_requests ?? lgpdStatus?.solicitacoes_esquecimento ?? 0) as number;

  const isHealthy = healthData?.status === 'healthy' || (healthData as Record<string, unknown> | undefined)?.healthy === true;
  const healthLabel = isHealthy ? 'Saudavel' : 'Degradado';
  const healthVariant = isHealthy ? 'default' : 'destructive';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <ShieldCheck className="h-6 w-6" />
            Seguranca & LGPD
          </h1>
          <p className="text-muted-foreground">
            Compliance LGPD, auditoria e protecao de dados
          </p>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Consentimentos Ativos</CardTitle>
            <CheckCircle2 className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-green-600">
                {activeConsents}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">PIAs Realizadas</CardTitle>
            <FileText className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-blue-600">
                {piasCompleted}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Solicitações de Esquecimento</CardTitle>
            <Trash2 className="h-4 w-4 text-red-600" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-red-600">
                {erasureRequests}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Status dos Servicos</CardTitle>
            {isHealthy ? (
              <Shield className="h-4 w-4 text-green-600" />
            ) : (
              <AlertTriangle className="h-4 w-4 text-amber-600" />
            )}
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            ) : (
              <Badge variant={healthVariant}>
                {healthLabel}
              </Badge>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Sub-pages Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {subPages.map((page) => (
          <Card
            key={page.href}
            className="hover:shadow-md transition-shadow cursor-pointer h-full"
            onClick={() => router.push(page.href)}
          >
            <CardContent className="pt-6">
              <div className="flex items-start gap-3">
                <div className={`p-2 rounded-lg ${page.color}`}>
                  <page.icon className="h-5 w-5" />
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="font-semibold text-sm">{page.title}</h3>
                  <p className="text-xs text-muted-foreground mt-1">
                    {page.description}
                  </p>
                </div>
                <ArrowRight className="h-4 w-4 text-muted-foreground flex-shrink-0 mt-1" />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
