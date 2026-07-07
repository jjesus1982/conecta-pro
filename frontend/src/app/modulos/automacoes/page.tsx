'use client';

import { Zap, GitBranch, History, ArrowRight, Loader2, PlayCircle, CheckCircle2, Activity } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
;
import { useRouter } from 'next/navigation';
import { useWorkflowList } from '@/hooks/workflows';
import type { WorkflowResponse } from '@/hooks/workflows';

const subPages = [
  {
    title: 'Workflows',
    description: 'Criar, editar e gerenciar workflows de automacao',
    href: '/modulos/automacoes/workflows',
    icon: GitBranch,
    color: 'text-blue-600 bg-blue-50 dark:text-blue-400 dark:bg-blue-950',
  },
  {
    title: 'Historico de Execucoes',
    description: 'Acompanhar execucoes, status e historico de workflows',
    href: '/modulos/automacoes/execucoes',
    icon: History,
    color: 'text-purple-600 bg-purple-50 dark:text-purple-400 dark:bg-purple-950',
  },
];

export default function AutomacoesPage() {
  const router = useRouter();

  const { data: workflowsData, isLoading } = useWorkflowList({ tenant_id: '' });

  const workflows: WorkflowResponse[] = workflowsData ?? [];

  const totalWorkflows = workflows.length;
  const activeWorkflows = workflows.filter(
    (w) => w.status === 'ACTIVE'
  ).length;
  const totalExecutions = workflows.reduce(
    (acc, w) => acc + (w.total_executions ?? 0),
    0
  );
  const runningEstimate = workflows.filter(
    (w) => w.status === 'ACTIVE' && w.total_executions > w.successful_executions + w.failed_executions
  ).length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <Zap className="h-6 w-6" />
            Automacoes e Workflows
          </h1>
          <p className="text-muted-foreground">
            Automacao de processos e fluxos de trabalho
          </p>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Workflows</CardTitle>
            <GitBranch className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-blue-600">
                {totalWorkflows}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Ativos</CardTitle>
            <CheckCircle2 className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-green-600">
                {activeWorkflows}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Execucoes Recentes</CardTitle>
            <Activity className="h-4 w-4 text-purple-600" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-purple-600">
                {totalExecutions}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Em Execucao</CardTitle>
            <PlayCircle className="h-4 w-4 text-amber-600" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-amber-600">
                {runningEstimate}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Sub-pages Grid */}
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
    </div>
  );
}
