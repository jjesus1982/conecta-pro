'use client';

import { Clock, ListTodo, History, ArrowRight, AlertTriangle, Activity, Server, Layers, RefreshCw, Loader2, Play } from 'lucide-react';
import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
;
import { useRouter } from 'next/navigation';
import {
  useTaskStats,
  useDueTasks,
} from '@/hooks/scheduler';
import { useQueueStats } from '@/hooks/scheduler';
import { useWorkerStats } from '@/hooks/scheduler';
import { useRunSchedulerCycle } from '@/hooks/scheduler';

const subPages = [
  {
    title: 'Tarefas Agendadas',
    description: 'Criar, editar e gerenciar tarefas agendadas com cron, intervalo ou execucao unica',
    href: '/modulos/agendador/tarefas',
    icon: ListTodo,
    color: 'text-blue-600 bg-blue-50 dark:text-blue-400 dark:bg-blue-950',
  },
  {
    title: 'Historico de Execucoes',
    description: 'Visualizar historico completo de execucoes, status, duracao e resultados',
    href: '/modulos/agendador/execucoes',
    icon: History,
    color: 'text-purple-600 bg-purple-50 dark:text-purple-400 dark:bg-purple-950',
  },
];

function StatusBadge({ status }: { status: string }) {
  const variants: Record<string, string> = {
    active: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
    paused: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
    disabled: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
    draft: 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200',
    completed: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
    failed: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
    expired: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200',
  };
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${variants[status] || variants.draft}`}>
      {status}
    </span>
  );
}

export default function AgendadorPage() {
  const router = useRouter();

  // Stats
  const { data: taskStats, isLoading: statsLoading } = useTaskStats();
  const { data: queueStats, isLoading: queueLoading } = useQueueStats();
  const { data: workerStats, isLoading: workerLoading } = useWorkerStats();

  // Tarefas pendentes
  const { data: dueTasks, isLoading: dueLoading } = useDueTasks(10);

  // Ciclo manual
  const runCycle = useRunSchedulerCycle();

  const isLoading = statsLoading || queueLoading || workerLoading;

  // Derivar contagem de itens na fila a partir de by_status
  const queueItemsTotal = (() => {
    if (!queueStats?.by_status) return 0;
    const byStatus = queueStats.by_status as Record<string, number>;
    return Object.values(byStatus).reduce((acc, val) => acc + (typeof val === 'number' ? val : 0), 0);
  })();

  // Derivar contagem de execucoes recentes
  const recentExecutions = (() => {
    if (!taskStats?.executions) return 0;
    const execs = taskStats.executions as Record<string, number>;
    return Object.values(execs).reduce((acc, val) => acc + (typeof val === 'number' ? val : 0), 0);
  })();

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <Clock className="h-6 w-6" />
            Agendador de Tarefas
          </h1>
          <p className="text-muted-foreground">
            Gerenciamento de tarefas agendadas, execucoes e filas de processamento
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => runCycle.mutate()}
          disabled={runCycle.isPending}
        >
          {runCycle.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin mr-2" />
          ) : (
            <Play className="h-4 w-4 mr-2" />
          )}
          Executar Ciclo
        </Button>
      </div>

      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Tarefas</CardTitle>
            <ListTodo className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-blue-600">
                {taskStats?.total_tasks ?? 0}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Execucoes Recentes</CardTitle>
            <Activity className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-green-600">
                {recentExecutions}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Itens na Fila</CardTitle>
            <Layers className="h-4 w-4 text-amber-600" />
          </CardHeader>
          <CardContent>
            {queueLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-amber-600">
                {queueItemsTotal}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Workers Ativos</CardTitle>
            <Server className="h-4 w-4 text-purple-600" />
          </CardHeader>
          <CardContent>
            {workerLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-purple-600">
                {workerStats?.active_workers ?? 0}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Navigation Cards */}
      <div className="grid gap-4 md:grid-cols-2">
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

      {/* Due Tasks Alert */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-amber-600" />
            Tarefas Pendentes de Execucao
          </CardTitle>
        </CardHeader>
        <CardContent>
          {dueLoading ? (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-10 animate-pulse rounded bg-muted" />
              ))}
            </div>
          ) : !dueTasks || dueTasks.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Nenhuma tarefa pendente de execucao no momento.
            </p>
          ) : (
            <div className="space-y-2">
              {dueTasks.map((task) => (
                <div
                  key={task.id}
                  className="flex items-center justify-between p-3 rounded-lg border bg-amber-50/50 dark:bg-amber-950/20"
                >
                  <div className="flex items-center gap-3">
                    <Clock className="h-4 w-4 text-amber-600" />
                    <div>
                      <p className="text-sm font-medium">{task.name}</p>
                      <p className="text-xs text-muted-foreground">
                        {task.task_type} | Prioridade: {task.priority}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <StatusBadge status={task.status} />
                    {task.next_run_at && (
                      <span className="text-xs text-muted-foreground">
                        {new Date(task.next_run_at as string).toLocaleDateString('pt-BR', {
                          day: '2-digit',
                          month: '2-digit',
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </span>
                    )}
                  </div>
                </div>
              ))}
              {dueTasks.length > 0 && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="w-full mt-2"
                  onClick={() => router.push('/modulos/agendador/tarefas')}
                >
                  Ver todas as tarefas
                  <ArrowRight className="h-4 w-4 ml-2" />
                </Button>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
