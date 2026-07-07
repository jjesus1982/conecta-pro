'use client';

import { ListTodo, Plus, Play, Pause, Pencil, Trash2, Zap, Loader2, ArrowLeft, CheckCircle, XCircle, Clock, Activity } from 'lucide-react';
import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogTrigger,
} from '@/components/ui/dialog';
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
import { useRouter } from 'next/navigation';
import {
  useTasks,
  useTaskStats,
  useCreateTask,
  useUpdateTask,
  useDeleteTask,
  useActivateTask,
  usePauseTask,
  useTriggerTask,
} from '@/hooks/scheduler';
import type { TaskCreate } from '@/types/generated/scheduler/models';

function TaskStatusBadge({ status }: { status: string }) {
  const config: Record<string, { className: string; label: string }> = {
    active: { className: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200', label: 'Ativo' },
    paused: { className: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200', label: 'Pausado' },
    disabled: { className: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200', label: 'Desativado' },
    draft: { className: 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200', label: 'Rascunho' },
    completed: { className: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200', label: 'Concluida' },
    failed: { className: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200', label: 'Falhou' },
    expired: { className: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200', label: 'Expirada' },
  };
  const c = config[status] || config.draft || { className: '', label: status };
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${c.className}`}>
      {c.label}
    </span>
  );
}

function TaskTypeBadge({ type }: { type: string }) {
  const config: Record<string, string> = {
    cron: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900 dark:text-indigo-200',
    interval: 'bg-cyan-100 text-cyan-800 dark:bg-cyan-900 dark:text-cyan-200',
    once: 'bg-pink-100 text-pink-800 dark:bg-pink-900 dark:text-pink-200',
    event: 'bg-violet-100 text-violet-800 dark:bg-violet-900 dark:text-violet-200',
    dependency: 'bg-teal-100 text-teal-800 dark:bg-teal-900 dark:text-teal-200',
    manual: 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200',
  };
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${config[type] || config.manual}`}>
      {type}
    </span>
  );
}

function formatDate(value: unknown): string {
  if (!value) return '-';
  try {
    return new Date(value as string).toLocaleDateString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return '-';
  }
}

function formatSchedule(task: any): string {
  if (task.cron_expression) return task.cron_expression;
  if (task.interval_seconds) {
    const secs = task.interval_seconds as number;
    if (secs >= 3600) return `${Math.floor(secs / 3600)}h`;
    if (secs >= 60) return `${Math.floor(secs / 60)}min`;
    return `${secs}s`;
  }
  return '-';
}

export default function TarefasPage() {
  const router = useRouter();

  // State
  const [createOpen, setCreateOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [editingTask, setEditingTask] = useState<any>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

  // Form state (create)
  const [formName, setFormName] = useState('');
  const [formHandler, setFormHandler] = useState('');
  const [formType, setFormType] = useState('cron');
  const [formCron, setFormCron] = useState('');
  const [formInterval, setFormInterval] = useState('');
  const [formTimeout, setFormTimeout] = useState('300');
  const [formMaxRetries, setFormMaxRetries] = useState('3');
  const [formPriority, setFormPriority] = useState('5');
  const [formDescription, setFormDescription] = useState('');

  // Edit form state
  const [editName, setEditName] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [editCron, setEditCron] = useState('');
  const [editInterval, setEditInterval] = useState('');
  const [editTimeout, setEditTimeout] = useState('');
  const [editMaxRetries, setEditMaxRetries] = useState('');

  // Hooks
  const { data: tasksData, isLoading: tasksLoading } = useTasks();
  const { data: taskStats, isLoading: statsLoading } = useTaskStats();

  const createTask = useCreateTask();
  const updateTask = useUpdateTask();
  const deleteTask = useDeleteTask();
  const activateTask = useActivateTask();
  const pauseTask = usePauseTask();
  const triggerTask = useTriggerTask();

  const tasks = tasksData?.items ?? [];

  // Stats derivadas
  const byStatus = (taskStats?.by_status ?? {}) as Record<string, number>;
  const activeTasks = byStatus['active'] ?? 0;
  const pausedTasks = byStatus['paused'] ?? 0;
  const failedTasks = byStatus['failed'] ?? 0;

  // Handlers
  function resetCreateForm() {
    setFormName('');
    setFormHandler('');
    setFormType('cron');
    setFormCron('');
    setFormInterval('');
    setFormTimeout('300');
    setFormMaxRetries('3');
    setFormPriority('5');
    setFormDescription('');
  }

  function handleCreate() {
    const payload: TaskCreate = {
      name: formName,
      handler: formHandler,
      task_type: formType as any,
      timeout_seconds: parseInt(formTimeout) || 300,
      max_retries: parseInt(formMaxRetries) || 3,
      priority: parseInt(formPriority) || 5,
    };
    if (formDescription) {
      payload.description = formDescription as any;
    }
    if (formType === 'cron' && formCron) {
      payload.cron_expression = formCron as any;
    }
    if (formType === 'interval' && formInterval) {
      payload.interval_seconds = parseInt(formInterval) as any;
    }

    createTask.mutate(payload, {
      onSuccess: () => {
        setCreateOpen(false);
        resetCreateForm();
      },
    });
  }

  function openEditDialog(task: any) {
    setEditingTask(task);
    setEditName(task.name || '');
    setEditDescription(task.description || '');
    setEditCron(task.cron_expression || '');
    setEditInterval(task.interval_seconds ? String(task.interval_seconds) : '');
    setEditTimeout(task.timeout_seconds ? String(task.timeout_seconds) : '');
    setEditMaxRetries(task.max_retries !== undefined ? String(task.max_retries) : '');
    setEditOpen(true);
  }

  function handleUpdate() {
    if (!editingTask) return;
    const updates: any = {};
    if (editName && editName !== editingTask.name) updates.name = editName;
    if (editDescription !== (editingTask.description || '')) updates.description = editDescription || null;
    if (editCron !== (editingTask.cron_expression || '')) updates.cron_expression = editCron || null;
    if (editInterval !== (editingTask.interval_seconds ? String(editingTask.interval_seconds) : '')) {
      updates.interval_seconds = editInterval ? parseInt(editInterval) : null;
    }
    if (editTimeout !== (editingTask.timeout_seconds ? String(editingTask.timeout_seconds) : '')) {
      updates.timeout_seconds = editTimeout ? parseInt(editTimeout) : null;
    }
    if (editMaxRetries !== (editingTask.max_retries !== undefined ? String(editingTask.max_retries) : '')) {
      updates.max_retries = editMaxRetries ? parseInt(editMaxRetries) : null;
    }

    updateTask.mutate(
      { taskId: editingTask.id, updates },
      {
        onSuccess: () => {
          setEditOpen(false);
          setEditingTask(null);
        },
      }
    );
  }

  function handleDelete(taskId: string) {
    deleteTask.mutate(
      { taskId },
      {
        onSuccess: () => setDeleteConfirmId(null),
      }
    );
  }

  function handleActivate(taskId: string) {
    activateTask.mutate(taskId);
  }

  function handlePause(taskId: string) {
    pauseTask.mutate(taskId);
  }

  function handleTrigger(taskId: string) {
    triggerTask.mutate({ taskId });
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
              <ListTodo className="h-6 w-6" />
              Tarefas Agendadas
            </h1>
          </div>
          <p className="text-muted-foreground ml-10">
            Gerenciamento completo de tarefas agendadas
          </p>
        </div>

        <Dialog open={createOpen} onOpenChange={setCreateOpen}>
          <DialogTrigger asChild>
            <Button onClick={() => { resetCreateForm(); setCreateOpen(true); }}>
              <Plus className="h-4 w-4 mr-2" />
              Nova Tarefa
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-[500px]">
            <DialogHeader>
              <DialogTitle>Criar Nova Tarefa</DialogTitle>
            </DialogHeader>
            <div className="grid gap-4 py-4">
              <div className="grid gap-2">
                <Label htmlFor="create-name">Nome *</Label>
                <Input
                  id="create-name"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder="Nome da tarefa"
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="create-handler">Handler *</Label>
                <Input
                  id="create-handler"
                  value={formHandler}
                  onChange={(e) => setFormHandler(e.target.value)}
                  placeholder="modulo.funcao_handler"
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="create-description">Descricao</Label>
                <Input
                  id="create-description"
                  value={formDescription}
                  onChange={(e) => setFormDescription(e.target.value)}
                  placeholder="Descricao da tarefa"
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="create-type">Tipo</Label>
                <Select value={formType} onValueChange={setFormType} aria-label="Form Type">
                  <SelectTrigger>
                    <SelectValue placeholder="Tipo da tarefa" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="cron">Cron</SelectItem>
                    <SelectItem value="interval">Intervalo</SelectItem>
                    <SelectItem value="once">Unica</SelectItem>
                    <SelectItem value="event">Evento</SelectItem>
                    <SelectItem value="manual">Manual</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {formType === 'cron' && (
                <div className="grid gap-2">
                  <Label htmlFor="create-cron">Expressao Cron</Label>
                  <Input
                    id="create-cron"
                    value={formCron}
                    onChange={(e) => setFormCron(e.target.value)}
                    placeholder="0 0 * * *"
                  />
                </div>
              )}
              {formType === 'interval' && (
                <div className="grid gap-2">
                  <Label htmlFor="create-interval">Intervalo (segundos)</Label>
                  <Input
                    id="create-interval"
                    type="number"
                    value={formInterval}
                    onChange={(e) => setFormInterval(e.target.value)}
                    placeholder="3600"
                  />
                </div>
              )}
              <div className="grid grid-cols-3 gap-4">
                <div className="grid gap-2">
                  <Label htmlFor="create-timeout">Timeout (s)</Label>
                  <Input
                    id="create-timeout"
                    type="number"
                    value={formTimeout}
                    onChange={(e) => setFormTimeout(e.target.value)}
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="create-retries">Max Retries</Label>
                  <Input
                    id="create-retries"
                    type="number"
                    value={formMaxRetries}
                    onChange={(e) => setFormMaxRetries(e.target.value)}
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="create-priority">Prioridade</Label>
                  <Input
                    id="create-priority"
                    type="number"
                    value={formPriority}
                    onChange={(e) => setFormPriority(e.target.value)}
                  />
                </div>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setCreateOpen(false)}>
                Cancelar
              </Button>
              <Button
                onClick={handleCreate}
                disabled={!formName || !formHandler || createTask.isPending}
              >
                {createTask.isPending && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
                Criar Tarefa
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {/* Stats Bar */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total</CardTitle>
            <ListTodo className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums">{taskStats?.total_tasks ?? 0}</div>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Ativas</CardTitle>
            <CheckCircle className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-green-600">{activeTasks}</div>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Pausadas</CardTitle>
            <Pause className="h-4 w-4 text-yellow-600" />
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-yellow-600">{pausedTasks}</div>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Com Falha</CardTitle>
            <XCircle className="h-4 w-4 text-red-600" />
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-red-600">{failedTasks}</div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Tasks Table */}
      <Card>
        <CardContent className="p-0">
          {tasksLoading ? (
            <div className="p-6 space-y-3">
              {[1, 2, 3, 4, 5].map((i) => (
                <div key={i} className="h-12 animate-pulse rounded bg-muted" />
              ))}
            </div>
          ) : tasks.length === 0 ? (
            <div className="p-12 text-center text-muted-foreground">
              Nenhum registro encontrado
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nome</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Cron/Intervalo</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Ultima Execucao</TableHead>
                  <TableHead>Proxima Execucao</TableHead>
                  <TableHead className="text-right">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {tasks.map((task) => (
                  <TableRow key={task.id}>
                    <TableCell>
                      <div>
                        <p className="font-medium text-sm">{task.name}</p>
                        {task.description && (
                          <p className="text-xs text-muted-foreground truncate max-w-[200px]">
                            {task.description as string}
                          </p>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      <TaskTypeBadge type={task.task_type} />
                    </TableCell>
                    <TableCell>
                      <code className="text-xs bg-muted px-1.5 py-0.5 rounded">
                        {formatSchedule(task)}
                      </code>
                    </TableCell>
                    <TableCell>
                      <TaskStatusBadge status={task.status} />
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {formatDate(task.last_run_at)}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {formatDate(task.next_run_at)}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => openEditDialog(task)}
                          title="Editar"
                        >
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                        {task.status === 'active' ? (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handlePause(task.id)}
                            disabled={pauseTask.isPending}
                            title="Pausar"
                          >
                            <Pause className="h-3.5 w-3.5 text-yellow-600" />
                          </Button>
                        ) : (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleActivate(task.id)}
                            disabled={activateTask.isPending}
                            title="Ativar"
                          >
                            <Play className="h-3.5 w-3.5 text-green-600" />
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleTrigger(task.id)}
                          disabled={triggerTask.isPending}
                          title="Disparar agora"
                        >
                          <Zap className="h-3.5 w-3.5 text-blue-600" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setDeleteConfirmId(task.id)}
                          title="Excluir"
                        >
                          <Trash2 className="h-3.5 w-3.5 text-red-600" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Edit Dialog */}
      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>Editar Tarefa</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="edit-name">Nome</Label>
              <Input
                id="edit-name"
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="edit-description">Descricao</Label>
              <Input
                id="edit-description"
                value={editDescription}
                onChange={(e) => setEditDescription(e.target.value)}
              />
            </div>
            {editingTask?.task_type === 'cron' && (
              <div className="grid gap-2">
                <Label htmlFor="edit-cron">Expressao Cron</Label>
                <Input
                  id="edit-cron"
                  value={editCron}
                  onChange={(e) => setEditCron(e.target.value)}
                  placeholder="0 0 * * *"
                />
              </div>
            )}
            {editingTask?.task_type === 'interval' && (
              <div className="grid gap-2">
                <Label htmlFor="edit-interval">Intervalo (segundos)</Label>
                <Input
                  id="edit-interval"
                  type="number"
                  value={editInterval}
                  onChange={(e) => setEditInterval(e.target.value)}
                />
              </div>
            )}
            <div className="grid grid-cols-2 gap-4">
              <div className="grid gap-2">
                <Label htmlFor="edit-timeout">Timeout (s)</Label>
                <Input
                  id="edit-timeout"
                  type="number"
                  value={editTimeout}
                  onChange={(e) => setEditTimeout(e.target.value)}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="edit-retries">Max Retries</Label>
                <Input
                  id="edit-retries"
                  type="number"
                  value={editMaxRetries}
                  onChange={(e) => setEditMaxRetries(e.target.value)}
                />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditOpen(false)}>
              Cancelar
            </Button>
            <Button
              onClick={handleUpdate}
              disabled={updateTask.isPending}
            >
              {updateTask.isPending && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
              Salvar Alteracoes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={!!deleteConfirmId} onOpenChange={(open) => !open && setDeleteConfirmId(null)}>
        <DialogContent className="sm:max-w-[400px]">
          <DialogHeader>
            <DialogTitle>Confirmar Exclusão</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Tem certeza que deseja excluir esta tarefa? Esta acao nao pode ser desfeita.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteConfirmId(null)}>
              Cancelar
            </Button>
            <Button
              variant="destructive"
              onClick={() => deleteConfirmId && handleDelete(deleteConfirmId)}
              disabled={deleteTask.isPending}
            >
              {deleteTask.isPending && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
              Excluir
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
