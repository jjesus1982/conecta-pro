'use client';

import { RefreshCw, Search, Play, XCircle, Clock, CheckCircle, AlertCircle, MoreHorizontal, Loader2, ChevronLeft, ChevronRight, ListOrdered, History } from 'lucide-react';
import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  useSyncQueue,
  useSyncQueueStats,
  useSyncRuns,
  useStartSync,
  useCancelSyncItem,
} from '@/hooks/integrations';

type ActiveTab = 'queue' | 'history';

const QUEUE_STATUS_BADGES: Record<string, string> = {
  pending: 'bg-gray-500/10 text-gray-500 border-gray-500/20',
  processing: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
  completed: 'bg-green-500/10 text-green-500 border-green-500/20',
  failed: 'bg-red-500/10 text-red-500 border-red-500/20',
  cancelled: 'bg-gray-500/10 text-gray-400 border-gray-400/20',
};

const QUEUE_STATUS_LABELS: Record<string, string> = {
  pending: 'Pendente',
  processing: 'Processando',
  completed: 'Concluído',
  failed: 'Falhou',
  cancelled: 'Cancelado',
};

const RUN_STATUS_BADGES: Record<string, string> = {
  running: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
  completed: 'bg-green-500/10 text-green-500 border-green-500/20',
  failed: 'bg-red-500/10 text-red-500 border-red-500/20',
};

const RUN_STATUS_LABELS: Record<string, string> = {
  running: 'Executando',
  completed: 'Concluído',
  failed: 'Falhou',
};

const QUEUE_STATUS_ICONS: Record<string, React.ReactNode> = {
  pending: <Clock className="w-3 h-3" />,
  processing: <RefreshCw className="w-3 h-3 animate-spin" />,
  completed: <CheckCircle className="w-3 h-3" />,
  failed: <AlertCircle className="w-3 h-3" />,
  cancelled: <XCircle className="w-3 h-3" />,
};

const PAGE_SIZE = 20;

export default function SyncPage() {
  const [activeTab, setActiveTab] = useState<ActiveTab>('queue');
  const [queuePage, setQueuePage] = useState(1);
  const [historyPage, setHistoryPage] = useState(1);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');

  // Debounce search
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search);
      setQueuePage(1);
      setHistoryPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);

  // Stats
  const { data: stats, isLoading: statsLoading, refetch: refetchStats } = useSyncQueueStats();

  // Queue data
  const queueParams: any = {
    skip: (queuePage - 1) * PAGE_SIZE,
    limit: PAGE_SIZE,
  };
  if (debouncedSearch) queueParams.search = debouncedSearch;
  const { data: queueData, isLoading: queueLoading, refetch: refetchQueue } = useSyncQueue(queueParams);

  // Runs data
  const runsParams: any = {
    skip: (historyPage - 1) * PAGE_SIZE,
    limit: PAGE_SIZE,
  };
  if (debouncedSearch) runsParams.search = debouncedSearch;
  const { data: runsData, isLoading: runsLoading, refetch: refetchRuns } = useSyncRuns(runsParams);

  // Mutations
  const startSync = useStartSync();
  const cancelSyncItem = useCancelSyncItem();

  const queueItems = Array.isArray(queueData) ? queueData : queueData?.items ?? [];
  const queueTotal = Array.isArray(queueData) ? queueData.length : queueData?.total ?? 0;
  const queueTotalPages = Math.max(1, Math.ceil(queueTotal / PAGE_SIZE));

  const runItems = Array.isArray(runsData) ? runsData : runsData?.items ?? [];
  const runsTotal = Array.isArray(runsData) ? runsData.length : runsData?.total ?? 0;
  const runsTotalPages = Math.max(1, Math.ceil(runsTotal / PAGE_SIZE));

  const formatDate = (dateStr: string | null | undefined) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const handleCancelItem = async (itemId: string) => {
    try {
      await cancelSyncItem.mutateAsync({ itemId, params: {} as any });
      refetchQueue();
      refetchStats();
    } catch (error) {
    }
  };

  const handleRefresh = () => {
    refetchStats();
    refetchQueue();
    refetchRuns();
  };

  const isLoading = activeTab === 'queue' ? queueLoading : runsLoading;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <RefreshCw className="h-6 w-6" />
            Sincronização
          </h1>
          <p className="text-muted-foreground">
            Acompanhe e gerencie filas de sincronização de dados
          </p>
        </div>
        <Button variant="outline" onClick={handleRefresh} disabled={isLoading}>
          <RefreshCw className={`w-4 h-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
          Atualizar
        </Button>
      </div>

      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Na Fila</CardTitle>
            <Clock className="h-4 w-4 text-gray-500" />
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--muted-foreground))]">
                {stats?.pending ?? 0}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Em Execução</CardTitle>
            <RefreshCw className="h-4 w-4 text-blue-500" />
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-blue-600">
                {stats?.processing ?? 0}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Concluídos</CardTitle>
            <CheckCircle className="h-4 w-4 text-green-500" />
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-green-600">
                {stats?.completed ?? 0}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Falhados</CardTitle>
            <AlertCircle className="h-4 w-4 text-red-500" />
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-red-600">
                {stats?.failed ?? 0}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-2 border-b border-[hsl(var(--border))] pb-0">
        <button
          onClick={() => setActiveTab('queue')}
          className={`flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'queue'
              ? 'border-[hsl(var(--primary))] text-[hsl(var(--primary))]'
              : 'border-transparent text-muted-foreground hover:text-[hsl(var(--foreground))]'
          }`}
        >
          <ListOrdered className="w-4 h-4" />
          Fila
        </button>
        <button
          onClick={() => setActiveTab('history')}
          className={`flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'history'
              ? 'border-[hsl(var(--primary))] text-[hsl(var(--primary))]'
              : 'border-transparent text-muted-foreground hover:text-[hsl(var(--foreground))]'
          }`}
        >
          <History className="w-4 h-4" />
          Histórico
        </button>
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <Input
          placeholder={activeTab === 'queue' ? 'Buscar na fila...' : 'Buscar no histórico...'}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="pl-10"
        />
      </div>

      {/* Queue Tab */}
      {activeTab === 'queue' && (
        <>
          <Card>
            <CardContent className="p-0">
              {queueLoading ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
                </div>
              ) : queueItems.length === 0 ? (
                <div className="text-center py-12">
                  <ListOrdered className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
                  <h3 className="text-lg font-medium">Fila vazia</h3>
                  <p className="text-muted-foreground mt-1">
                    Nenhum item na fila de sincronização
                  </p>
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Item</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Prioridade</TableHead>
                      <TableHead>Criado em</TableHead>
                      <TableHead className="text-right">Ações</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {queueItems.map((item: any) => (
                      <TableRow key={item.id}>
                        <TableCell className="font-medium text-sm">
                          {item.entity_type || item.type || '-'}
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant="outline"
                            className={`inline-flex items-center gap-1 ${QUEUE_STATUS_BADGES[item.status] || QUEUE_STATUS_BADGES.pending}`}
                          >
                            {QUEUE_STATUS_ICONS[item.status]}
                            {QUEUE_STATUS_LABELS[item.status] || item.status}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-sm">
                          {item.priority ?? '-'}
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {formatDate(item.created_at)}
                        </TableCell>
                        <TableCell className="text-right">
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button variant="ghost" size="sm">
                                <MoreHorizontal className="w-4 h-4" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              {(item.status === 'pending' || item.status === 'processing') && (
                                <DropdownMenuItem
                                  onClick={() => handleCancelItem(item.id)}
                                  className="text-red-500"
                                >
                                  <XCircle className="w-4 h-4 mr-2" />
                                  Cancelar
                                </DropdownMenuItem>
                              )}
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>

          {/* Queue Pagination */}
          {queueTotalPages > 1 && (
            <div className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">
                Mostrando {(queuePage - 1) * PAGE_SIZE + 1} a{' '}
                {Math.min(queuePage * PAGE_SIZE, queueTotal)} de {queueTotal} itens
              </p>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setQueuePage(queuePage - 1)}
                  disabled={queuePage <= 1}
                >
                  <ChevronLeft className="w-4 h-4" />
                </Button>
                <span className="text-sm">
                  Página {queuePage} de {queueTotalPages}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setQueuePage(queuePage + 1)}
                  disabled={queuePage >= queueTotalPages}
                >
                  <ChevronRight className="w-4 h-4" />
                </Button>
              </div>
            </div>
          )}
        </>
      )}

      {/* History Tab */}
      {activeTab === 'history' && (
        <>
          <Card>
            <CardContent className="p-0">
              {runsLoading ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
                </div>
              ) : runItems.length === 0 ? (
                <div className="text-center py-12">
                  <History className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
                  <h3 className="text-lg font-medium">Nenhuma execução encontrada</h3>
                  <p className="text-muted-foreground mt-1">
                    O histórico de sincronizações aparecerá aqui
                  </p>
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>ID</TableHead>
                      <TableHead>Conector</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Início</TableHead>
                      <TableHead>Fim</TableHead>
                      <TableHead>Registros</TableHead>
                      <TableHead className="text-right">Ações</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {runItems.map((run: any) => (
                      <TableRow key={run.id}>
                        <TableCell className="text-sm font-mono">
                          {run.id?.substring(0, 8) || '-'}...
                        </TableCell>
                        <TableCell className="text-sm font-medium">
                          {run.connector_name || '-'}
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant="outline"
                            className={RUN_STATUS_BADGES[run.status] || 'bg-gray-500/10 text-gray-500'}
                          >
                            {RUN_STATUS_LABELS[run.status] || run.status}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {formatDate(run.started_at)}
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {formatDate(run.finished_at)}
                        </TableCell>
                        <TableCell className="text-sm">
                          {run.records_processed ?? '-'}
                        </TableCell>
                        <TableCell className="text-right">
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button variant="ghost" size="sm">
                                <MoreHorizontal className="w-4 h-4" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              <DropdownMenuItem disabled>
                                <AlertCircle className="w-4 h-4 mr-2" />
                                Ver detalhes
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>

          {/* History Pagination */}
          {runsTotalPages > 1 && (
            <div className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">
                Mostrando {(historyPage - 1) * PAGE_SIZE + 1} a{' '}
                {Math.min(historyPage * PAGE_SIZE, runsTotal)} de {runsTotal} registros
              </p>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setHistoryPage(historyPage - 1)}
                  disabled={historyPage <= 1}
                >
                  <ChevronLeft className="w-4 h-4" />
                </Button>
                <span className="text-sm">
                  Página {historyPage} de {runsTotalPages}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setHistoryPage(historyPage + 1)}
                  disabled={historyPage >= runsTotalPages}
                >
                  <ChevronRight className="w-4 h-4" />
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
