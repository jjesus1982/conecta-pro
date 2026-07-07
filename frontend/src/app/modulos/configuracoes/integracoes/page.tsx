'use client';

import {
  Plug,
  RefreshCw,
  HardDrive,
  FileText,
  Mail,
  CheckCircle2,
  XCircle,
  Clock,
  AlertCircle,
  Loader2,
  Building2,
} from 'lucide-react';
import { useEffect, useState, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

interface IntegrationCard {
  id: string;
  name: string;
  description: string;
  icon: React.ElementType;
  iconColor: string;
  connected: boolean | null;
  lastSync: string | null;
  details?: string;
  balance?: string | null;
}

function getAuthHeaders() {
  const token =
    typeof window !== 'undefined'
      ? localStorage.getItem('access_token') || localStorage.getItem('token')
      : null;
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function fetchSolidesStatus(): Promise<{ connected: boolean; last_sync: string | null }> {
  const res = await fetch('/api/v1/integrations/solides/status', {
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error('solides');
  const data = await res.json();
  return {
    connected: data.connected ?? false,
    last_sync: data.last_full_sync_at || data.last_incremental_sync_at || null,
  };
}

async function fetchBankingStatus(): Promise<{
  connected: boolean;
  last_sync: string | null;
  details: string;
  balance: string | null;
}> {
  const [statusRes, balancesRes] = await Promise.all([
    fetch('/api/v1/integrations/banking/status', { headers: getAuthHeaders() }),
    fetch('/api/v1/integrations/banking/balances', { headers: getAuthHeaders() }),
  ]);

  const statusData = statusRes.ok ? await statusRes.json() : [];
  const balancesData = balancesRes.ok ? await balancesRes.json() : null;

  const inter = Array.isArray(statusData)
    ? statusData.find((b: { bank_code: string }) => b.bank_code === '077') || statusData[0]
    : null;

  let balance: string | null = null;
  if (balancesData?.balances) {
    const interBalance = balancesData.balances.find(
      (b: { bank_code: string }) => b.bank_code === '077'
    );
    if (interBalance?.balance != null) {
      balance = interBalance.balance.toLocaleString('pt-BR', {
        style: 'currency',
        currency: 'BRL',
      });
    }
  }

  return {
    connected: inter?.connected ?? false,
    last_sync: inter?.last_sync || null,
    details: inter ? `${inter.bank_name} — Cód. ${inter.bank_code}` : 'Banco Inter 077',
    balance,
  };
}

function formatDate(iso: string | null): string {
  if (!iso) return 'Nunca';
  const d = new Date(iso);
  return d.toLocaleString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function StatusBadge({ connected }: { connected: boolean | null }) {
  if (connected === null) {
    return (
      <Badge className="bg-gray-100 text-gray-600 flex items-center gap-1 w-fit">
        <Loader2 className="h-3 w-3 animate-spin" />
        Verificando
      </Badge>
    );
  }
  if (connected) {
    return (
      <Badge className="bg-green-100 text-green-700 flex items-center gap-1 w-fit">
        <CheckCircle2 className="h-3 w-3" />
        Conectado
      </Badge>
    );
  }
  return (
    <Badge className="bg-red-100 text-red-700 flex items-center gap-1 w-fit">
      <XCircle className="h-3 w-3" />
      Desconectado
    </Badge>
  );
}

export default function ConfiguracoesIntegracoesPage() {
  const [integrations, setIntegrations] = useState<IntegrationCard[]>([
    {
      id: 'banking',
      name: 'Banco Inter 077',
      description: 'Integração bancária — PIX, TED, boleto e extrato automático',
      icon: Building2,
      iconColor: 'text-orange-600 bg-orange-50',
      connected: null,
      lastSync: null,
      details: 'Banco Inter — Cód. 077',
      balance: null,
    },
    {
      id: 'solides',
      name: 'Sólides Tangerino',
      description: 'Sincronização de colaboradores, cargos e departamentos (RH)',
      icon: RefreshCw,
      iconColor: 'text-cyan-600 bg-cyan-50',
      connected: null,
      lastSync: null,
    },
    {
      id: 'gdrive',
      name: 'Google Drive OAuth2',
      description: 'Armazenamento e compartilhamento de documentos GED',
      icon: HardDrive,
      iconColor: 'text-blue-600 bg-blue-50',
      connected: false,
      lastSync: null,
    },
    {
      id: 'nfse',
      name: 'NFS-e Portal Nacional',
      description: 'Emissão de notas fiscais de serviço — ABRASF 2.04 / padrão nacional',
      icon: FileText,
      iconColor: 'text-purple-600 bg-purple-50',
      connected: true,
      lastSync: null,
      details: 'Prefeitura de Manaus — ISS 5%',
    },
    {
      id: 'smtp',
      name: 'SMTP Email',
      description: 'Envio de notificações, alertas e documentos por e-mail',
      icon: Mail,
      iconColor: 'text-green-600 bg-green-50',
      connected: false,
      lastSync: null,
    },
  ]);

  const [loadingLive, setLoadingLive] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadLiveStatus = useCallback(async () => {
    setLoadingLive(true);
    setError(null);
    try {
      const [solides, banking] = await Promise.all([
        fetchSolidesStatus().catch(() => null),
        fetchBankingStatus().catch(() => null),
      ]);

      setIntegrations((prev) =>
        prev.map((item) => {
          if (item.id === 'solides' && solides) {
            return {
              ...item,
              connected: solides.connected,
              lastSync: solides.last_sync,
            };
          }
          if (item.id === 'banking' && banking) {
            return {
              ...item,
              connected: banking.connected,
              lastSync: banking.last_sync,
              details: banking.details,
              balance: banking.balance,
            };
          }
          return item;
        })
      );
    } catch {
      setError('Erro ao carregar status de algumas integrações.');
    } finally {
      setLoadingLive(false);
    }
  }, []);

  useEffect(() => {
    loadLiveStatus();
  }, [loadLiveStatus]);

  const connectedCount = integrations.filter((i) => i.connected === true).length;
  const totalCount = integrations.length;

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
            Status e configuração das integrações externas do sistema
          </p>
        </div>
        <Button variant="outline" onClick={loadLiveStatus} disabled={loadingLive}>
          <RefreshCw className={`h-4 w-4 mr-2 ${loadingLive ? 'animate-spin' : ''}`} />
          Atualizar
        </Button>
      </div>

      {/* Error banner */}
      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-destructive flex-shrink-0" />
          <p className="text-sm text-destructive">{error}</p>
        </div>
      )}

      {/* Summary */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total de Integrações</CardTitle>
            <Plug className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums">{totalCount}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Conectadas</CardTitle>
            <CheckCircle2 className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-green-600">{connectedCount}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Desconectadas</CardTitle>
            <XCircle className="h-4 w-4 text-red-500" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-red-500">{totalCount - connectedCount}</div>
          </CardContent>
        </Card>
      </div>

      {/* Integration Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {integrations.map((integration) => {
          const Icon = integration.icon;
          return (
            <Card key={integration.id} className="hover:shadow-md transition-shadow">
              <CardContent className="pt-5">
                <div className="flex items-start gap-4">
                  <div className={`p-3 rounded-xl ${integration.iconColor} flex-shrink-0`}>
                    <Icon className="h-5 w-5" />
                  </div>
                  <div className="flex-1 min-w-0 space-y-2">
                    <div className="flex items-center justify-between gap-2 flex-wrap">
                      <h3 className="font-semibold text-sm">{integration.name}</h3>
                      <StatusBadge connected={integration.connected} />
                    </div>
                    <p className="text-xs text-muted-foreground">{integration.description}</p>
                    {integration.details && (
                      <p className="text-xs text-muted-foreground font-medium">
                        {integration.details}
                      </p>
                    )}
                    {integration.balance && (
                      <p className="text-sm font-semibold text-green-700">
                        Saldo: {integration.balance}
                      </p>
                    )}
                    <div className="flex items-center gap-1 text-xs text-muted-foreground">
                      <Clock className="h-3 w-3" />
                      <span>Última sync: {formatDate(integration.lastSync)}</span>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
