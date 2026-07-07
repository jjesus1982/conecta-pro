'use client';

import { History, RefreshCw, AlertCircle, CheckCircle2, XCircle, PlayCircle, Loader2, Ban, Activity, BarChart3 } from 'lucide-react';
import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
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
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
;
import {
  useWorkflowList,
  useExecutionList,
  useCancelExecution,
} from '@/hooks/workflows';
import type {
  WorkflowResponse,
  ExecutionResponse,
  ExecutionStatus,
} from '@/hooks/workflows';

const executionStatusConfig: Record<
  string,
  { label: string; className: string; icon: React.ElementType }
> = {
  PENDING: {
    label: 'Pendente',
    className: 'bg-slate-100 text-slate-800',
    icon: Loader2,
  },
  QUEUED: {
    label: 'Na Fila',
    className: 'bg-slate-100 text-slate-800',
    icon: Loader2,
  },
  RUNNING: {
    label: 'Executando',
    className: 'bg-blue-100 text-blue-800',
    icon: PlayCircle,
  },
  PAUSED: {
    label: 'Pausado',
    className: 'bg-orange-100 text-orange-800',
    icon: Ban,
  },
  WAITING: {
    label: 'Aguardando',
    className: 'bg-amber-100 text-amber-800',
    icon: Loader2,
  },
  RETRYING: {
    label: 'Tentando Novamente',
    className: 'bg-amber-100 text-amber-800',
    icon: RefreshCw,
  },
  COMPLETED: {
    label: 'Concluido',
    className: 'bg-green-100 text-green-800',
    icon: CheckCircle2,
  },
  FAILED: {
    label: 'Falhou',
    className: 'bg-red-100 text-red-800',
    icon: XCircle,
  },
  CANCELLED: {
    label: 'Cancelado',
    className: 'bg-gray-100 text-gray-800',
    icon: Ban,
  },
  TIMEOUT: {
    label: 'Timeout',
    className: 'bg-red-100 text-red-800',
    icon: AlertCircle,
  },
};

function formatDuration(ms: number | null | undefined): string {
  if (!ms) return '-';
  if (ms < 1000) return `${ms}ms`;
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${minutes}m ${remainingSeconds}s`;
}

function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleDateString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export default function ExecucoesPage() {
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string>('');
  const [cancelOpen, setCancelOpen] = useState(false);
  const [selectedExecution, setSelectedExecution] = useState<ExecutionResponse | null>(null);

  const { data: workflowsData, isLoading: workflowsLoading } = useWorkflowList({
    tenant_id: '',
  });

  const {
    data: executionsData,
    isLoading: executionsLoading,
    error,
    refetch,
  } = useExecutionList(selectedWorkflowId, {}, { enabled: !!selectedWorkflowId });

  const cancelMutation = useCancelExecution();

  const workflows: WorkflowResponse[] = workflowsData ?? [];
  const executions: ExecutionResponse[] = executionsData ?? [];

  // Derive stats from executions
  const stats = {
    total: executions.length,
    completed: executions.filter((e) => e.status === 'COMPLETED').length,
    failed: executions.filter((e) => e.status === 'FAILED').length,
    running: executions.filter(
      (e) => e.status === 'RUNNING' || e.status === 'PENDING' || e.status === 'QUEUED'
    ).length,
  };

  const isLoading = workflowsLoading || executionsLoading;

  const handleCancelOpen = (execution: ExecutionResponse) => {
    setSelectedExecution(execution);
    setCancelOpen(true);
  };

  const handleCancel = async () => {
    if (!selectedExecution) return;
    await cancelMutation.mutateAsync(selectedExecution.id);
    setCancelOpen(false);
    setSelectedExecution(null);
  };

  const getStatusBadge = (status: string) => {
    const config = executionStatusConfig[status] ?? {
      label: status,
      className: 'bg-gray-100 text-gray-800',
      icon: AlertCircle,
    };
    return <Badge className={config.className}>{config.label}</Badge>;
  };

  const isRunning = (status: string) =>
    status === 'RUNNING' || status === 'PENDING' || status === 'QUEUED';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <History className="h-6 w-6" />
            Historico de Execucoes
          </h1>
          <p className="text-muted-foreground">
            Acompanhe as execucoes dos workflows
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            onClick={() => refetch()}
            disabled={isLoading || !selectedWorkflowId}
          >
            <RefreshCw
              className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`}
            />
            Atualizar
          </Button>
        </div>
      </div>

      {/* Workflow Selector */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-col md:flex-row gap-4 items-end">
            <div className="flex-1 space-y-2">
              <label className="text-sm font-medium">Selecione o Workflow</label>
              <Select
                value={selectedWorkflowId}
                onValueChange={setSelectedWorkflowId}
               aria-label="Selected Workflow Id">
                <SelectTrigger>
                  <SelectValue placeholder="Selecione um workflow para ver as execucoes" />
                </SelectTrigger>
                <SelectContent>
                  {workflows.map((w) => (
                    <SelectItem key={w.id} value={w.id}>
                      {w.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Stats Cards */}
      {selectedWorkflowId && (
        <div className="grid gap-4 md:grid-cols-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Total</CardTitle>
              <BarChart3 className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              {executionsLoading ? (
                <div className="h-8 w-16 animate-pulse rounded bg-muted" />
              ) : (
                <div className="font-data text-2xl font-semibold tabular-nums">{stats.total}</div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Concluidos</CardTitle>
              <CheckCircle2 className="h-4 w-4 text-green-600" />
            </CardHeader>
            <CardContent>
              {executionsLoading ? (
                <div className="h-8 w-16 animate-pulse rounded bg-muted" />
              ) : (
                <div className="font-data text-2xl font-semibold tabular-nums text-green-600">
                  {stats.completed}
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Falhas</CardTitle>
              <XCircle className="h-4 w-4 text-red-600" />
            </CardHeader>
            <CardContent>
              {executionsLoading ? (
                <div className="h-8 w-16 animate-pulse rounded bg-muted" />
              ) : (
                <div className="font-data text-2xl font-semibold tabular-nums text-red-600">
                  {stats.failed}
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Em Execucao</CardTitle>
              <Activity className="h-4 w-4 text-blue-600" />
            </CardHeader>
            <CardContent>
              {executionsLoading ? (
                <div className="h-8 w-16 animate-pulse rounded bg-muted" />
              ) : (
                <div className="font-data text-2xl font-semibold tabular-nums text-blue-600">
                  {stats.running}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-destructive" />
          <p className="text-sm text-destructive flex-1">
            Erro ao carregar execucoes
          </p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Tentar novamente
          </Button>
        </div>
      )}

      {/* Table */}
      {!selectedWorkflowId ? (
        <Card>
          <CardContent className="py-12">
            <div className="text-center text-muted-foreground">
              <History className="h-16 w-16 mx-auto mb-4 opacity-50" />
              <h3 className="text-lg font-medium">
                Selecione um workflow
              </h3>
              <p className="mt-2">
                Escolha um workflow acima para visualizar o historico de execucoes
              </p>
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="p-0">
            {executionsLoading ? (
              <div className="flex items-center justify-center py-12">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
              </div>
            ) : executions.length === 0 ? (
              <div className="text-center py-12 text-muted-foreground">
                <History className="h-16 w-16 mx-auto mb-4 opacity-50" />
                <h3 className="text-lg font-medium">
                  Nenhum registro encontrado
                </h3>
                <p className="mt-2">
                  Nenhuma execucao encontrada para este workflow
                </p>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Workflow</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Passos</TableHead>
                    <TableHead>Duracao</TableHead>
                    <TableHead>Erro</TableHead>
                    <TableHead className="w-[100px]">Ações</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {executions.map((execution) => (
                    <TableRow
                      key={execution.id}
                      className={
                        isRunning(execution.status)
                          ? 'bg-blue-50/50 dark:bg-blue-950/20'
                          : ''
                      }
                    >
                      <TableCell>
                        <div className="font-medium">
                          {execution.workflow_name ?? 'Workflow'}
                        </div>
                        <div className="text-xs text-muted-foreground font-mono">
                          {execution.id.substring(0, 8)}...
                        </div>
                      </TableCell>
                      <TableCell>
                        {getStatusBadge(execution.status)}
                      </TableCell>
                      <TableCell>
                        <span className="text-green-600">
                          {execution.steps_completed}
                        </span>
                        {' / '}
                        <span>{execution.steps_total}</span>
                        {execution.steps_failed > 0 && (
                          <>
                            {' '}
                            <span className="text-red-600">
                              ({execution.steps_failed} falha
                              {execution.steps_failed > 1 ? 's' : ''})
                            </span>
                          </>
                        )}
                      </TableCell>
                      <TableCell>
                        {formatDuration(execution.execution_time_ms)}
                      </TableCell>
                      <TableCell>
                        {execution.error_message ? (
                          <span
                            className="text-xs text-red-600 truncate block max-w-[200px]"
                            title={execution.error_message}
                          >
                            {execution.error_message}
                          </span>
                        ) : (
                          <span className="text-muted-foreground">-</span>
                        )}
                      </TableCell>
                      <TableCell>
                        {isRunning(execution.status) ? (
                          <Button
                            variant="outline"
                            size="sm"
                            className="text-red-600 hover:text-red-700"
                            onClick={() => handleCancelOpen(execution)}
                          >
                            <Ban className="h-3 w-3 mr-1" />
                            Cancelar
                          </Button>
                        ) : (
                          <span className="text-muted-foreground text-sm">-</span>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      )}

      {/* Cancel Confirmation Dialog */}
      <Dialog
        open={cancelOpen}
        onOpenChange={(open) => {
          setCancelOpen(open);
          if (!open) setSelectedExecution(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Cancelar Execucao</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Tem certeza que deseja cancelar esta execucao? A execucao sera
            interrompida imediatamente.
          </p>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setCancelOpen(false);
                setSelectedExecution(null);
              }}
            >
              Voltar
            </Button>
            <Button
              variant="destructive"
              onClick={handleCancel}
              disabled={cancelMutation.isPending}
            >
              {cancelMutation.isPending ? 'Cancelando...' : 'Confirmar Cancelamento'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
