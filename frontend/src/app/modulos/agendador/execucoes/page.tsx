'use client';

import { History, ArrowLeft, XCircle, Loader2, CheckCircle, Clock, AlertTriangle, Ban, SkipForward, RefreshCw, Timer } from 'lucide-react';
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
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
;
import { useRouter } from 'next/navigation';
import {
  useExecutions,
  useCancelExecution,
} from '@/hooks/scheduler';

function ExecutionStatusBadge({ status }: { status: string }) {
  const config: Record<string, { className: string; label: string; icon: React.ReactNode }> = {
    pending: {
      className: 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200',
      label: 'Pendente',
      icon: <Clock className="h-3 w-3 mr-1" />,
    },
    queued: {
      className: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
      label: 'Na Fila',
      icon: <Timer className="h-3 w-3 mr-1" />,
    },
    running: {
      className: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
      label: 'Executando',
      icon: <Loader2 className="h-3 w-3 mr-1 animate-spin" />,
    },
    success: {
      className: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
      label: 'Concluida',
      icon: <CheckCircle className="h-3 w-3 mr-1" />,
    },
    failed: {
      className: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
      label: 'Falhou',
      icon: <XCircle className="h-3 w-3 mr-1" />,
    },
    timeout: {
      className: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200',
      label: 'Timeout',
      icon: <AlertTriangle className="h-3 w-3 mr-1" />,
    },
    cancelled: {
      className: 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200',
      label: 'Cancelada',
      icon: <Ban className="h-3 w-3 mr-1" />,
    },
    skipped: {
      className: 'bg-gray-100 text-gray-600 dark:bg-gray-900 dark:text-gray-400',
      label: 'Ignorada',
      icon: <SkipForward className="h-3 w-3 mr-1" />,
    },
    retry: {
      className: 'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200',
      label: 'Tentando',
      icon: <RefreshCw className="h-3 w-3 mr-1" />,
    },
  };
  const c = config[status] || config.pending || { className: '', label: status, icon: null };
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${c.className}`}>
      {c.icon}
      {c.label}
    </span>
  );
}

function formatDateTime(value: unknown): string {
  if (!value) return '-';
  try {
    return new Date(value as string).toLocaleDateString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return '-';
  }
}

function formatDuration(seconds: unknown): string {
  if (seconds === null || seconds === undefined) return '-';
  const s = Number(seconds);
  if (isNaN(s)) return '-';
  if (s < 1) return `${Math.round(s * 1000)}ms`;
  if (s < 60) return `${s.toFixed(1)}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
}

function canCancel(status: string): boolean {
  return ['pending', 'queued', 'running'].includes(status);
}

export default function ExecucoesPage() {
  const router = useRouter();
  const [cancelDialogId, setCancelDialogId] = useState<string | null>(null);
  const [cancelReason, setCancelReason] = useState('');

  // Hooks
  const { data: executions, isLoading } = useExecutions();
  const cancelExecution = useCancelExecution();

  const executionsList = Array.isArray(executions) ? executions : [];

  // Stats derivadas
  const totalExecutions = executionsList.length;
  const runningCount = executionsList.filter((e) => e.status === 'running').length;
  const successCount = executionsList.filter((e) => e.status === 'success').length;
  const failedCount = executionsList.filter((e) => e.status === 'failed').length;

  function handleCancel() {
    if (!cancelDialogId) return;
    cancelExecution.mutate(
      { executionId: cancelDialogId, reason: cancelReason || undefined },
      {
        onSuccess: () => {
          setCancelDialogId(null);
          setCancelReason('');
        },
      }
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => router.push('/modulos/agendador')}
            >
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <h1 className="font-display text-2xl font-bold flex items-center gap-2">
              <History className="h-6 w-6" />
              Historico de Execucoes
            </h1>
          </div>
          <p className="text-muted-foreground ml-10">
            Acompanhamento de todas as execucoes de tarefas agendadas
          </p>
        </div>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total</CardTitle>
            <History className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums">{totalExecutions}</div>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Executando</CardTitle>
            <Loader2 className="h-4 w-4 text-blue-600 animate-spin" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-blue-600">{runningCount}</div>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Concluidas</CardTitle>
            <CheckCircle className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-green-600">{successCount}</div>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Falhas</CardTitle>
            <XCircle className="h-4 w-4 text-red-600" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-red-600">{failedCount}</div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Executions Table */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-6 space-y-3">
              {[1, 2, 3, 4, 5].map((i) => (
                <div key={i} className="h-12 animate-pulse rounded bg-muted" />
              ))}
            </div>
          ) : executionsList.length === 0 ? (
            <div className="p-12 text-center text-muted-foreground">
              Nenhum registro encontrado
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Tarefa</TableHead>
                  <TableHead>Inicio</TableHead>
                  <TableHead>Fim</TableHead>
                  <TableHead>Duracao</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Resultado</TableHead>
                  <TableHead className="text-right">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {executionsList.map((execution) => (
                  <TableRow key={execution.id}>
                    <TableCell>
                      <div>
                        <p className="text-sm font-medium truncate max-w-[180px]">
                          {execution.task_id}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          #{execution.execution_number} | Tentativa {execution.attempt_number}
                        </p>
                      </div>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {formatDateTime(execution.started_at)}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {formatDateTime(execution.completed_at)}
                    </TableCell>
                    <TableCell className="text-xs">
                      {formatDuration(execution.duration_seconds)}
                    </TableCell>
                    <TableCell>
                      <ExecutionStatusBadge status={execution.status} />
                    </TableCell>
                    <TableCell>
                      {execution.error_message ? (
                        <span className="text-xs text-red-600 truncate max-w-[200px] block" title={execution.error_message as string}>
                          {(execution.error_message as string).slice(0, 50)}
                          {(execution.error_message as string).length > 50 ? '...' : ''}
                        </span>
                      ) : execution.output_result ? (
                        <span className="text-xs text-muted-foreground truncate max-w-[200px] block">
                          OK
                        </span>
                      ) : execution.progress_message ? (
                        <div className="flex items-center gap-2">
                          <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden max-w-[100px]">
                            <div
                              className="h-full bg-blue-600 rounded-full transition-all"
                              style={{ width: `${execution.progress_percent ?? 0}%` }}
                            />
                          </div>
                          <span className="text-xs text-muted-foreground">
                            {execution.progress_percent ?? 0}%
                          </span>
                        </div>
                      ) : (
                        <span className="text-xs text-muted-foreground">-</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      {canCancel(execution.status) ? (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            setCancelDialogId(execution.id);
                            setCancelReason('');
                          }}
                          disabled={cancelExecution.isPending}
                          title="Cancelar execucao"
                        >
                          <Ban className="h-3.5 w-3.5 text-red-600" />
                        </Button>
                      ) : (
                        <span className="text-xs text-muted-foreground">-</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Cancel Confirmation Dialog */}
      <Dialog open={!!cancelDialogId} onOpenChange={(open) => !open && setCancelDialogId(null)}>
        <DialogContent className="sm:max-w-[400px]">
          <DialogHeader>
            <DialogTitle>Cancelar Execucao</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <p className="text-sm text-muted-foreground">
              Tem certeza que deseja cancelar esta execucao?
            </p>
            <div className="grid gap-2">
              <Label htmlFor="cancel-reason">Motivo (opcional)</Label>
              <Input
                id="cancel-reason"
                value={cancelReason}
                onChange={(e) => setCancelReason(e.target.value)}
                placeholder="Motivo do cancelamento"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCancelDialogId(null)}>
              Voltar
            </Button>
            <Button
              variant="destructive"
              onClick={handleCancel}
              disabled={cancelExecution.isPending}
            >
              {cancelExecution.isPending && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
              Cancelar Execucao
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
