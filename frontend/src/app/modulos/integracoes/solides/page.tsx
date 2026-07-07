'use client';

import { Zap, RefreshCw, Settings, Users, AlertTriangle, CheckCircle2, XCircle, Search, Play, Eye, AlertCircle, Clock, ArrowRight, Loader2, Calendar } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
;
import {
  useSolidesStatus,
  useSolidesConfig,
  useSolidesEmployees,
  useSolidesSyncLogs,
  useSolidesConflicts,
  useConfigureSolides,
  useTriggerSolidesSync,
  useResolveSolidesConflict,
  useDisableSolides,
} from '@/hooks/integrations';

export default function SolidesPage() {
  const [activeTab, setActiveTab] = useState<'status' | 'employees' | 'logs' | 'conflicts'>('status');
  const [search, setSearch] = useState('');

  const { data: statusData, isLoading: statusLoading, refetch: refetchStatus } = useSolidesStatus();
  const { data: configData } = useSolidesConfig();
  const { data: employeesData, isLoading: employeesLoading } = useSolidesEmployees();
  const { data: logsData, isLoading: logsLoading } = useSolidesSyncLogs();
  const { data: conflictsData, isLoading: conflictsLoading } = useSolidesConflicts();

  const triggerSyncMutation = useTriggerSolidesSync();
  const disableMutation = useDisableSolides();

  const [syncingFerias, setSyncingFerias] = useState(false);
  const [syncingEscalas, setSyncingEscalas] = useState(false);

  function getAuthHeaders() {
    const token = typeof window !== 'undefined' ? (localStorage.getItem('access_token') || localStorage.getItem('token')) : null;
    return { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) };
  }

  const handleSyncFerias = async () => {
    setSyncingFerias(true);
    try {
      const res = await fetch('/api/v1/people-management/hr/vacations/sync-solides', { method: 'POST', headers: getAuthHeaders() });
      const data = await res.json().catch(() => null);
      if (res.ok && data?.success) toast.success(`Férias Sólides: ${data.total_importadas ?? 0} importadas`, { duration: 5000 });
      else toast.error(data?.detail || 'Erro ao sincronizar férias', { duration: 5000 });
    } catch { toast.error('Erro de conexão', { duration: 5000 }); }
    finally { setSyncingFerias(false); }
  };

  const handleSyncEscalas = async () => {
    setSyncingEscalas(true);
    try {
      const res = await fetch('/api/v1/people-management/ponto/sync-escalas', { method: 'POST', headers: getAuthHeaders() });
      const data = await res.json().catch(() => null);
      if (res.ok) toast.success(`Escalas Sólides: ${data?.total_atualizados ?? data?.updated ?? 0} atualizados`, { duration: 5000 });
      else toast.error(data?.detail || 'Erro ao sincronizar escalas', { duration: 5000 });
    } catch { toast.error('Erro de conexão', { duration: 5000 }); }
    finally { setSyncingEscalas(false); }
  };

  const status = statusData as any;
  const config = configData as any;
  const employees = Array.isArray(employeesData) ? employeesData : (employeesData as any)?.items || [];
  const logs = Array.isArray(logsData) ? logsData : (logsData as any)?.items || [];
  const conflicts = Array.isArray(conflictsData) ? conflictsData : (conflictsData as any)?.items || [];

  const isConnected = status?.connected || status?.is_active || false;
  const lastSync = status?.last_sync || status?.last_sync_at || null;
  const syncStatus = status?.sync_status || 'desconhecido';

  const filteredEmployees = employees.filter((e: any) =>
    !search || (e.nome || e.name || '').toLowerCase().includes(search.toLowerCase())
  );

  const getStatusBadge = (s: string) => {
    const map: Record<string, string> = {
      success: 'bg-green-100 text-green-800',
      completed: 'bg-green-100 text-green-800',
      running: 'bg-blue-100 text-blue-800',
      pending: 'bg-yellow-100 text-yellow-800',
      error: 'bg-red-100 text-red-800',
      failed: 'bg-red-100 text-red-800',
    };
    return <Badge className={map[s] || 'bg-gray-100 text-gray-800'}>{s}</Badge>;
  };

  const tabs = [
    { key: 'status' as const, label: 'Status', icon: Settings },
    { key: 'employees' as const, label: 'Colaboradores', icon: Users },
    { key: 'logs' as const, label: 'Logs', icon: Clock },
    { key: 'conflicts' as const, label: 'Conflitos', icon: AlertTriangle },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <Zap className="h-6 w-6" />
            Solides DP
          </h1>
          <p className="text-muted-foreground">Integracao com Solides Departamento Pessoal</p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            onClick={() => refetchStatus()}
            disabled={statusLoading}
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${statusLoading ? 'animate-spin' : ''}`} />
            Atualizar
          </Button>
          <Button variant="outline" onClick={handleSyncFerias} disabled={syncingFerias || !isConnected}>
            {syncingFerias ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Calendar className="h-4 w-4 mr-2" />}
            Sync Férias
          </Button>
          <Button variant="outline" onClick={handleSyncEscalas} disabled={syncingEscalas || !isConnected}>
            {syncingEscalas ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Users className="h-4 w-4 mr-2" />}
            Sync Escalas
          </Button>
          <Button
            onClick={() => triggerSyncMutation.mutate({ sync_type: 'full' } as any)}
            disabled={triggerSyncMutation.isPending || !isConnected}
          >
            <Play className="h-4 w-4 mr-2" />
            Sincronizar Tudo
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Status</CardTitle>
            {isConnected ? (
              <CheckCircle2 className="h-4 w-4 text-green-600" />
            ) : (
              <XCircle className="h-4 w-4 text-red-600" />
            )}
          </CardHeader>
          <CardContent>
            <div className={`font-data text-2xl font-semibold tabular-nums ${isConnected ? 'text-green-600' : 'text-red-600'}`}>
              {isConnected ? 'Conectado' : 'Desconectado'}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Colaboradores</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums">{employees.length}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Ultima Sync</CardTitle>
            <Clock className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-sm font-medium">
              {lastSync ? new Date(lastSync).toLocaleString('pt-BR') : 'Nunca'}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Conflitos</CardTitle>
            <AlertTriangle className="h-4 w-4 text-yellow-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-yellow-600">{conflicts.length}</div>
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab.key
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <tab.icon className="h-4 w-4" />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === 'status' && (
        <Card>
          <CardHeader>
            <CardTitle>Configuração da Integração</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label className="text-muted-foreground text-xs">Status da Conexao</Label>
                <div className="mt-1">
                  <Badge className={isConnected ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}>
                    {isConnected ? 'Conectado' : 'Desconectado'}
                  </Badge>
                </div>
              </div>
              <div>
                <Label className="text-muted-foreground text-xs">Status da Sync</Label>
                <div className="mt-1">{getStatusBadge(syncStatus)}</div>
              </div>
              <div>
                <Label className="text-muted-foreground text-xs">Ultima Sincronizacao</Label>
                <p className="text-sm">{lastSync ? new Date(lastSync).toLocaleString('pt-BR') : 'Nunca sincronizado'}</p>
              </div>
              <div>
                <Label className="text-muted-foreground text-xs">Colaboradores Sincronizados</Label>
                <p className="text-sm">{employees.length}</p>
              </div>
            </div>
            {config && (
              <div className="border-t pt-4 mt-4">
                <h4 className="font-medium mb-3">Dados da Configuração</h4>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label className="text-muted-foreground text-xs">API URL</Label>
                    <p className="text-sm font-mono">{(config as any)?.api_url || '-'}</p>
                  </div>
                  <div>
                    <Label className="text-muted-foreground text-xs">Empresa ID</Label>
                    <p className="text-sm font-mono">{(config as any)?.company_id || '-'}</p>
                  </div>
                </div>
              </div>
            )}
            <div className="flex gap-2 mt-4">
              <Button
                variant="destructive"
                size="sm"
                onClick={() => disableMutation.mutate()}
                disabled={disableMutation.isPending || !isConnected}
              >
                Desabilitar Integracao
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {activeTab === 'employees' && (
        <div className="space-y-4">
          <Card>
            <CardContent className="pt-6">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Buscar colaborador..."
                  className="pl-10"
                />
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-0">
              {employeesLoading ? (
                <div className="flex items-center justify-center py-12">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
                </div>
              ) : filteredEmployees.length === 0 ? (
                <div className="text-center py-12 text-muted-foreground">
                  <Users className="h-16 w-16 mx-auto mb-4 opacity-50" />
                  <h3 className="text-lg font-medium">Nenhum colaborador encontrado</h3>
                  <p className="mt-2">Sincronize para importar colaboradores do Solides</p>
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Nome</TableHead>
                      <TableHead>CPF</TableHead>
                      <TableHead>Cargo</TableHead>
                      <TableHead>Departamento</TableHead>
                      <TableHead>Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredEmployees.map((emp: any, i: number) => (
                      <TableRow key={emp.id || i}>
                        <TableCell className="font-medium">{emp.nome || emp.name || '-'}</TableCell>
                        <TableCell className="text-sm font-mono">{emp.cpf || '-'}</TableCell>
                        <TableCell className="text-sm">{emp.cargo || emp.position || '-'}</TableCell>
                        <TableCell className="text-sm">{emp.departamento || emp.department || '-'}</TableCell>
                        <TableCell>
                          <Badge className={emp.ativo || emp.active ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'}>
                            {emp.ativo || emp.active ? 'Ativo' : 'Inativo'}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {activeTab === 'logs' && (
        <Card>
          <CardContent className="p-0">
            {logsLoading ? (
              <div className="flex items-center justify-center py-12">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
              </div>
            ) : logs.length === 0 ? (
              <div className="text-center py-12 text-muted-foreground">
                <Clock className="h-16 w-16 mx-auto mb-4 opacity-50" />
                <h3 className="text-lg font-medium">Nenhum log encontrado</h3>
                <p className="mt-2">Os logs de sincronizacao aparecerao aqui</p>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Data</TableHead>
                    <TableHead>Tipo</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Registros</TableHead>
                    <TableHead>Duracao</TableHead>
                    <TableHead>Mensagem</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {logs.map((log: any, i: number) => (
                    <TableRow key={log.id || i}>
                      <TableCell className="text-sm">
                        {log.created_at || log.started_at
                          ? new Date(log.created_at || log.started_at).toLocaleString('pt-BR')
                          : '-'}
                      </TableCell>
                      <TableCell className="text-sm">{log.sync_type || log.tipo || '-'}</TableCell>
                      <TableCell>{getStatusBadge(log.status || 'desconhecido')}</TableCell>
                      <TableCell className="text-sm">{log.records_processed || log.registros || 0}</TableCell>
                      <TableCell className="text-sm">{log.duration || log.duracao || '-'}</TableCell>
                      <TableCell className="text-sm text-muted-foreground max-w-[200px] truncate">
                        {log.message || log.mensagem || '-'}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      )}

      {activeTab === 'conflicts' && (
        <Card>
          <CardContent className="p-0">
            {conflictsLoading ? (
              <div className="flex items-center justify-center py-12">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
              </div>
            ) : conflicts.length === 0 ? (
              <div className="text-center py-12 text-muted-foreground">
                <CheckCircle2 className="h-16 w-16 mx-auto mb-4 opacity-50" />
                <h3 className="text-lg font-medium">Nenhum conflito</h3>
                <p className="mt-2">Todos os dados estão sincronizados corretamente</p>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Colaborador</TableHead>
                    <TableHead>Campo</TableHead>
                    <TableHead>Valor Solides</TableHead>
                    <TableHead>Valor Local</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Data</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {conflicts.map((conflict: any, i: number) => (
                    <TableRow key={conflict.id || i}>
                      <TableCell className="font-medium">{conflict.employee_name || conflict.colaborador || '-'}</TableCell>
                      <TableCell className="text-sm">{conflict.field || conflict.campo || '-'}</TableCell>
                      <TableCell className="text-sm font-mono">{conflict.solides_value || conflict.valor_solides || '-'}</TableCell>
                      <TableCell className="text-sm font-mono">{conflict.local_value || conflict.valor_local || '-'}</TableCell>
                      <TableCell>
                        <Badge className={
                          conflict.status === 'resolved' ? 'bg-green-100 text-green-800' :
                          conflict.status === 'ignored' ? 'bg-gray-100 text-gray-800' :
                          'bg-yellow-100 text-yellow-800'
                        }>
                          {conflict.status === 'resolved' ? 'Resolvido' :
                           conflict.status === 'ignored' ? 'Ignorado' : 'Pendente'}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-sm">
                        {conflict.created_at
                          ? new Date(conflict.created_at).toLocaleDateString('pt-BR')
                          : '-'}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
