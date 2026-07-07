'use client';

import { GitBranch, Plus, RefreshCw, MoreHorizontal, Edit, Trash2, PlayCircle, PauseCircle, AlertCircle } from 'lucide-react';
import { useState } from 'react';
import { Card, CardContent } from '@/components/ui/card';
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
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
;
import {
  useWorkflowList,
  useCreateWorkflow,
  useUpdateWorkflow,
  useDeleteWorkflow,
  useActivateWorkflow,
  useDeactivateWorkflow,
} from '@/hooks/workflows';
import type {
  WorkflowResponse,
  WorkflowCreate,
  WorkflowCategory,
  WorkflowStatus,
} from '@/hooks/workflows';

const statusConfig: Record<string, { label: string; className: string }> = {
  ACTIVE: { label: 'Ativo', className: 'bg-green-100 text-green-800' },
  INACTIVE: { label: 'Inativo', className: 'bg-gray-100 text-gray-800' },
  DRAFT: { label: 'Rascunho', className: 'bg-yellow-100 text-yellow-800' },
  PAUSED: { label: 'Pausado', className: 'bg-orange-100 text-orange-800' },
  ARCHIVED: { label: 'Arquivado', className: 'bg-slate-100 text-slate-800' },
  ERROR: { label: 'Erro', className: 'bg-red-100 text-red-800' },
};

const categoryLabels: Record<string, string> = {
  CRM: 'CRM',
  HR: 'RH',
  FINANCE: 'Financeiro',
  OPERATIONS: 'Operacoes',
  ONBOARDING: 'Onboarding',
  MARKETING: 'Marketing',
  SUPPORT: 'Suporte',
  COMMUNICATION: 'Comunicacao',
  DOCUMENT: 'Documentos',
  INTEGRATION: 'Integracoes',
  MAINTENANCE: 'Manutencao',
  SECURITY: 'Seguranca',
  ANALYTICS: 'Analytics',
  CUSTOM: 'Personalizado',
};

const categoryOptions: { value: string; label: string }[] = Object.entries(
  categoryLabels
).map(([value, label]) => ({ value, label }));

export default function WorkflowsPage() {
  const { data: workflowsData, isLoading, error, refetch } = useWorkflowList({
    tenant_id: '',
  });

  const createMutation = useCreateWorkflow();
  const updateMutation = useUpdateWorkflow();
  const deleteMutation = useDeleteWorkflow();
  const activateMutation = useActivateWorkflow();
  const deactivateMutation = useDeactivateWorkflow();

  const [createOpen, setCreateOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [selectedWorkflow, setSelectedWorkflow] = useState<WorkflowResponse | null>(null);

  // Form state
  const [formName, setFormName] = useState('');
  const [formDescription, setFormDescription] = useState('');
  const [formCategory, setFormCategory] = useState<string>('CUSTOM');

  const workflows: WorkflowResponse[] = workflowsData ?? [];

  const resetForm = () => {
    setFormName('');
    setFormDescription('');
    setFormCategory('CUSTOM');
  };

  const handleCreate = async () => {
    const payload: WorkflowCreate = {
      name: formName,
      description: formDescription || undefined,
      category: formCategory as WorkflowCategory,
      tenant_id: '',
    };
    await createMutation.mutateAsync(payload);
    setCreateOpen(false);
    resetForm();
  };

  const handleEditOpen = (workflow: WorkflowResponse) => {
    setSelectedWorkflow(workflow);
    setFormName(workflow.name);
    setFormDescription(workflow.description ?? '');
    setFormCategory(workflow.category ?? 'CUSTOM');
    setEditOpen(true);
  };

  const handleUpdate = async () => {
    if (!selectedWorkflow) return;
    await updateMutation.mutateAsync({
      workflowId: selectedWorkflow.id,
      data: {
        name: formName,
        description: formDescription || undefined,
        category: formCategory as WorkflowCategory,
      },
    });
    setEditOpen(false);
    setSelectedWorkflow(null);
    resetForm();
  };

  const handleDeleteOpen = (workflow: WorkflowResponse) => {
    setSelectedWorkflow(workflow);
    setDeleteOpen(true);
  };

  const handleDelete = async () => {
    if (!selectedWorkflow) return;
    await deleteMutation.mutateAsync(selectedWorkflow.id);
    setDeleteOpen(false);
    setSelectedWorkflow(null);
  };

  const handleActivate = async (workflowId: string) => {
    await activateMutation.mutateAsync(workflowId);
  };

  const handleDeactivate = async (workflowId: string) => {
    await deactivateMutation.mutateAsync(workflowId);
  };

  const getStatusBadge = (status: string) => {
    const config = statusConfig[status] ?? {
      label: status,
      className: 'bg-gray-100 text-gray-800',
    };
    return <Badge className={config.className}>{config.label}</Badge>;
  };

  const getCategoryBadge = (category?: string) => {
    if (!category) return <span className="text-muted-foreground">-</span>;
    const label = categoryLabels[category] ?? category;
    return <Badge variant="outline">{label}</Badge>;
  };

  const renderForm = () => (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="workflow-name">Nome</Label>
        <Input
          id="workflow-name"
          value={formName}
          onChange={(e) => setFormName(e.target.value)}
          placeholder="Nome do workflow"
          maxLength={200}
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="workflow-description">Descricao</Label>
        <Input
          id="workflow-description"
          value={formDescription}
          onChange={(e) => setFormDescription(e.target.value)}
          placeholder="Descricao do workflow (opcional)"
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="workflow-category">Categoria</Label>
        <Select value={formCategory} onValueChange={setFormCategory} aria-label="Form Category">
          <SelectTrigger>
            <SelectValue placeholder="Selecione a categoria" />
          </SelectTrigger>
          <SelectContent>
            {categoryOptions.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <GitBranch className="h-6 w-6" />
            Workflows
          </h1>
          <p className="text-muted-foreground">
            Gerencie workflows de automacao
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => refetch()} disabled={isLoading}>
            <RefreshCw
              className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`}
            />
            Atualizar
          </Button>
          <Dialog
            open={createOpen}
            onOpenChange={(open) => {
              setCreateOpen(open);
              if (!open) resetForm();
            }}
          >
            <DialogTrigger asChild>
              <Button>
                <Plus className="h-4 w-4 mr-2" />
                Novo Workflow
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Criar Workflow</DialogTitle>
              </DialogHeader>
              {renderForm()}
              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={() => {
                    setCreateOpen(false);
                    resetForm();
                  }}
                >
                  Cancelar
                </Button>
                <Button
                  onClick={handleCreate}
                  disabled={!formName.trim() || createMutation.isPending}
                >
                  {createMutation.isPending ? 'Criando...' : 'Criar'}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-destructive" />
          <p className="text-sm text-destructive flex-1">
            Erro ao carregar workflows
          </p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Tentar novamente
          </Button>
        </div>
      )}

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
            </div>
          ) : workflows.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <GitBranch className="h-16 w-16 mx-auto mb-4 opacity-50" />
              <h3 className="text-lg font-medium">Nenhum registro encontrado</h3>
              <p className="mt-2">Crie um novo workflow para comecar</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nome</TableHead>
                  <TableHead>Categoria</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Execucoes</TableHead>
                  <TableHead>Sucesso / Falha</TableHead>
                  <TableHead className="w-[80px]">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {workflows.map((workflow) => (
                  <TableRow key={workflow.id}>
                    <TableCell>
                      <div className="font-medium">{workflow.name}</div>
                      {workflow.description && (
                        <div className="text-xs text-muted-foreground mt-0.5">
                          {workflow.description}
                        </div>
                      )}
                    </TableCell>
                    <TableCell>{getCategoryBadge(workflow.category)}</TableCell>
                    <TableCell>{getStatusBadge(workflow.status)}</TableCell>
                    <TableCell>
                      <span className="font-medium">
                        {workflow.total_executions ?? 0}
                      </span>
                    </TableCell>
                    <TableCell>
                      <span className="text-green-600">
                        {workflow.successful_executions ?? 0}
                      </span>
                      {' / '}
                      <span className="text-red-600">
                        {workflow.failed_executions ?? 0}
                      </span>
                    </TableCell>
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                          >
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem
                            onClick={() => handleEditOpen(workflow)}
                          >
                            <Edit className="h-4 w-4 mr-2" />
                            Editar
                          </DropdownMenuItem>
                          {workflow.status === 'ACTIVE' ? (
                            <DropdownMenuItem
                              onClick={() => handleDeactivate(workflow.id)}
                            >
                              <PauseCircle className="h-4 w-4 mr-2" />
                              Desativar
                            </DropdownMenuItem>
                          ) : (
                            <DropdownMenuItem
                              onClick={() => handleActivate(workflow.id)}
                            >
                              <PlayCircle className="h-4 w-4 mr-2" />
                              Ativar
                            </DropdownMenuItem>
                          )}
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            className="text-destructive"
                            onClick={() => handleDeleteOpen(workflow)}
                          >
                            <Trash2 className="h-4 w-4 mr-2" />
                            Deletar
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

      {/* Edit Dialog */}
      <Dialog
        open={editOpen}
        onOpenChange={(open) => {
          setEditOpen(open);
          if (!open) {
            setSelectedWorkflow(null);
            resetForm();
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Editar Workflow</DialogTitle>
          </DialogHeader>
          {renderForm()}
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setEditOpen(false);
                setSelectedWorkflow(null);
                resetForm();
              }}
            >
              Cancelar
            </Button>
            <Button
              onClick={handleUpdate}
              disabled={!formName.trim() || updateMutation.isPending}
            >
              {updateMutation.isPending ? 'Salvando...' : 'Salvar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog
        open={deleteOpen}
        onOpenChange={(open) => {
          setDeleteOpen(open);
          if (!open) setSelectedWorkflow(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Confirmar Exclusão</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Tem certeza que deseja deletar o workflow{' '}
            <strong>{selectedWorkflow?.name}</strong>? Esta acao nao pode ser
            desfeita.
          </p>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setDeleteOpen(false);
                setSelectedWorkflow(null);
              }}
            >
              Cancelar
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? 'Deletando...' : 'Deletar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
