'use client';

import { Plug, Key, Webhook, FileText, RefreshCw, ArrowRight, AlertCircle, Loader2, Wifi, WifiOff, Clock, CheckCircle2, XCircle, AlertTriangle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useRouter } from 'next/navigation';
import { useEffect, useState, useCallback } from 'react';
import { fetchIntegrationStatus, type IntegrationStatusItem, type IntegrationStatusResponse } from '@/services/integrations/integrationStatusService';

const subPages = [
  {
    title: 'Conectores',
    description: 'Gerenciar conectores externos e integrações com sistemas terceiros',
    href: '/modulos/integracoes/conectores',
    icon: Plug,
    color: 'text-blue-600 bg-blue-50 dark:text-blue-400 dark:bg-blue-950',
  },
  {
    title: 'Sólides (RH)',
    description: 'Sincronização de colaboradores, cargos e departamentos',
    href: '/modulos/integracoes/solides',
    icon: RefreshCw,
    color: 'text-cyan-600 bg-cyan-50 dark:text-cyan-400 dark:bg-cyan-950',
  },
  {
    title: 'API Keys',
    description: 'Criar e gerenciar chaves de acesso para APIs externas',
    href: '/modulos/integracoes/api-keys',
    icon: Key,
    color: 'text-amber-600 bg-amber-50 dark:text-amber-400 dark:bg-amber-950',
  },
  {
    title: 'Webhooks',
    description: 'Configurar webhooks para automações e notificações em tempo real',
    href: '/modulos/integracoes/webhooks',
    icon: Webhook,
    color: 'text-green-600 bg-green-50 dark:text-green-400 dark:bg-green-950',
  },
  {
    title: 'Logs',
    description: 'Visualizar logs de requisições, erros e eventos de integração',
    href: '/modulos/integracoes/logs',
    icon: FileText,
    color: 'text-purple-600 bg-purple-50 dark:text-purple-400 dark:bg-purple-950',
  },
  {
    title: 'Sincronização',
    description: 'Acompanhar e gerenciar filas de sincronização de dados',
    href: '/modulos/integracoes/sync',
    icon: RefreshCw,
    color: 'text-cyan-600 bg-cyan-50 dark:text-cyan-400 dark:bg-cyan-950',
  },
];

const categoryLabels: Record<string, string> = {
  banking: 'Bancário',
  government: 'Governamental',
  hr: 'RH / Departamento Pessoal',
};

const statusConfig: Record<string, { icon: typeof CheckCircle2; color: string; label: string }> = {
  online: { icon: CheckCircle2, color: 'text-emerald-500', label: 'Online' },
  offline: { icon: XCircle, color: 'text-red-500', label: 'Offline' },
  degraded: { icon: AlertTriangle, color: 'text-amber-500', label: 'Instavel' },
  homologacao: { icon: Clock, color: 'text-blue-400', label: 'Homologacao' },
};

function StatusBadge({ status }: { status: string }) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const config = (statusConfig[status] || statusConfig['offline']) as any;
  const Icon = config.icon as typeof CheckCircle2;
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-medium ${config.color}`}>
      <Icon className="w-3.5 h-3.5" />
      {config.label}
    </span>
  );
}

function IntegrationCard({ item }: { item: IntegrationStatusItem }) {
  return (
    <div className="card-shine bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4 transition-all hover:shadow-sm">
      <div className="flex items-start justify-between mb-2">
        <h4 className="text-sm font-semibold text-[hsl(var(--foreground))]">{item.name}</h4>
        <StatusBadge status={item.status} />
      </div>
      <p className="text-xs text-[hsl(var(--muted-foreground))] mb-3">{item.description}</p>
      <div className="flex items-center gap-3 text-xs text-[hsl(var(--muted-foreground))]">
        {item.last_check && (
          <span className="flex items-center gap-1">
            <Clock className="w-3 h-3" />
            {new Date(item.last_check).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}
          </span>
        )}
        {item.response_time_ms && (
          <span>{Math.round(item.response_time_ms)}ms</span>
        )}
      </div>
      {item.error_message && (
        <p className="mt-2 text-xs text-red-400 truncate" title={item.error_message}>
          {item.error_message}
        </p>
      )}
    </div>
  );
}

export default function IntegracoesPage() {
  const router = useRouter();
  const [data, setData] = useState<IntegrationStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      setError(null);
      const result = await fetchIntegrationStatus();
      setData(result);
    } catch (err) {
      setError('Erro ao carregar status das integrações');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    // Auto-refresh a cada 60 segundos
    const interval = setInterval(loadData, 60000);
    return () => clearInterval(interval);
  }, [loadData]);

  // Agrupar por categoria
  const grouped = data?.integrations.reduce((acc, item) => {
    if (!acc[item.category]) acc[item.category] = [];
    acc[item.category]!.push(item);
    return acc;
  }, {} as Record<string, IntegrationStatusItem[]>) ?? {};

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <Plug className="h-6 w-6" />
            Integrações
          </h1>
          <p className="text-muted-foreground">
            Status em tempo real de todas as integrações externas
          </p>
        </div>
        <button
          onClick={loadData}
          className="flex items-center gap-2 text-sm px-3 py-2 rounded-lg border border-[hsl(var(--border))] hover:bg-[hsl(var(--secondary))] transition-colors"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Atualizar
        </button>
      </div>

      {/* Stats */}
      <div className="grid gap-4 grid-cols-2 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total</CardTitle>
            <Plug className="h-4 w-4 text-navy-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums">{loading ? '—' : data?.total ?? 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Online</CardTitle>
            <Wifi className="h-4 w-4 text-emerald-500" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-emerald-500">{loading ? '—' : data?.online ?? 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Offline</CardTitle>
            <WifiOff className="h-4 w-4 text-red-500" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-red-500">{loading ? '—' : data?.offline ?? 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Homologacao</CardTitle>
            <Clock className="h-4 w-4 text-blue-400" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-blue-400">{loading ? '—' : data?.homologacao ?? 0}</div>
            <p className="text-xs text-muted-foreground mt-1">tpAmb=2 (teste)</p>
          </CardContent>
        </Card>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {error}
        </div>
      )}

      {/* Integration Status by Category */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-[hsl(var(--muted-foreground))]" />
        </div>
      ) : (
        <div className="space-y-6">
          {Object.entries(grouped).map(([category, items]) => (
            <div key={category}>
              <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
                <div className="w-[3px] h-5 rounded-full gradient-brand" />
                {categoryLabels[category] || category}
                <span className="text-xs font-normal text-[hsl(var(--muted-foreground))]">
                  ({items.length})
                </span>
              </h2>
              <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                {items.map((item) => (
                  <IntegrationCard key={item.id} item={item} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Sub-pages Grid */}
      <div>
        <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
          <div className="w-[3px] h-5 rounded-full gradient-brand" />
          Gerenciamento
        </h2>
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
    </div>
  );
}
