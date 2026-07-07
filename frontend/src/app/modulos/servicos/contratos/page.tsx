'use client';

import { FileSignature, Search, RefreshCw, Plus, MoreHorizontal, AlertCircle, Eye, Edit, Play, Pause, XCircle, Trash2, Send, DollarSign } from 'lucide-react';
import { useState } from 'react';
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
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { ConfirmModal } from '@/components/ui/modal';
;
import {
  useContracts,
  useCreateContract,
  useUpdateContract,
  useDeleteContract,
  useSubmitContract,
  useActivateContract,
  useSuspendContract,
  useTerminateContract,
} from '@/hooks/contracts';
import { ContratoFormModal } from '@/components/servicos/contrato-form-modal';
import { ContratoDetailModal } from '@/components/servicos/contrato-detail-modal';

const statusConfig: Record<string, { label: string; className: string }> = {
  draft: { label: 'Rascunho', className: 'bg-gray-100 text-gray-800' },
  submitted: { label: 'Submetido', className: 'bg-blue-100 text-blue-800' },
  active: { label: 'Ativo', className: 'bg-green-100 text-green-800' },
  suspended: { label: 'Suspenso', className: 'bg-yellow-100 text-yellow-800' },
  terminated: { label: 'Encerrado', className: 'bg-red-100 text-red-800' },
};

const tipoConfig: Record<string, string> = {
  servico_vigilancia: 'Vigilancia',
  servico_portaria: 'Portaria',
  servico_limpeza: 'Limpeza',
  misto: 'Misto',
};

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
  }).format(value);
}

function formatDate(dateStr: string): string {
  if (!dateStr) return '-';
  try {
    return new Date(dateStr).toLocaleDateString('pt-BR');
  } catch {
    return dateStr;
  }
}

export default function ContratosPage() {
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [contractTypeFilter, setContractTypeFilter] = useState('all');
  const [page, setPage] = useState(0);
  const pageSize = 20;

  const { data: contractsData, isLoading, error, refetch } = useContracts({
    page: page + 1,
    page_size: pageSize,
    search: search || undefined,
    status: statusFilter !== 'all' ? statusFilter : undefined,
    contract_type: contractTypeFilter !== 'all' ? contractTypeFilter : undefined,
  });

  const createMutation = useCreateContract();
  const updateMutation = useUpdateContract();
  const deleteMutation = useDeleteContract();
  const submitMutation = useSubmitContract();
  const activateMutation = useActivateContract();
  const suspendMutation = useSuspendContract();
  const terminateMutation = useTerminateContract();

  const [formOpen, setFormOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [editContrato, setEditContrato] = useState<any | null>(null);
  const [selectedContrato, setSelectedContrato] = useState<any | null>(null);

  // Confirm modal state
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmAction, setConfirmAction] = useState<{
    title: string;
    message: string;
    action: () => Promise<any>;
    variant: 'danger' | 'warning' | 'info';
  } | null>(null);

  const contracts = (contractsData as any)?.items || (Array.isArray(contractsData) ? contractsData : []);
  const total = (contractsData as any)?.total || contracts.length;

  const stats = {
    total,
    active: contracts.filter((c: any) => c.status === 'active').length,
    suspended: contracts.filter((c: any) => c.status === 'suspended').length,
    valorMensalTotal: contracts
      .filter((c: any) => c.status === 'active')
      .reduce((acc: number, c: any) => acc + (c.valor_mensal || c.monthly_value || 0), 0),
  };

  const openConfirm = (
    title: string,
    message: string,
    action: () => Promise<any>,
    variant: 'danger' | 'warning' | 'info' = 'warning'
  ) => {
    setConfirmAction({ title, message, action, variant });
    setConfirmOpen(true);
  };

  const handleCreate = async (data: any) => {
    await createMutation.mutateAsync(data);
    setFormOpen(false);
  };

  const handleUpdate = async (data: any) => {
    if (!editContrato) return;
    await updateMutation.mutateAsync({ contractId: editContrato.id, data });
    setFormOpen(false);
    setEditContrato(null);
  };

  const getStatusBadge = (status: string) => {
    const config = statusConfig[status] || { label: status, className: 'bg-gray-100 text-gray-800' };
    return <Badge className={config.className}>{config.label}</Badge>;
  };

  const getTipoBadge = (tipo: string) => {
    const label = tipoConfig[tipo] || tipo;
    return <Badge className="bg-indigo-100 text-indigo-800">{label}</Badge>;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <FileSignature className="h-6 w-6" />
            Contratos
          </h1>
          <p className="text-muted-foreground">Gestao de contratos de servico</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => refetch()} disabled={isLoading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
            Atualizar
          </Button>
          <Button onClick={() => { setEditContrato(null); setFormOpen(true); }}>
            <Plus className="h-4 w-4 mr-2" />
            Novo Contrato
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total</CardTitle>
            <FileSignature className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums">{stats.total}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Ativos</CardTitle>
            <Play className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-green-600">{stats.active}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Suspensos</CardTitle>
            <Pause className="h-4 w-4 text-yellow-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-yellow-600">{stats.suspended}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Valor Mensal Total</CardTitle>
            <DollarSign className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-blue-600">
              {formatCurrency(stats.valorMensalTotal)}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-col md:flex-row gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => { setSearch(e.target.value); setPage(0); }}
                placeholder="Buscar por numero, titulo, cliente..."
                className="pl-10"
              />
            </div>
            <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v); setPage(0); }}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos os status</SelectItem>
                <SelectItem value="draft">Rascunho</SelectItem>
                <SelectItem value="submitted">Submetido</SelectItem>
                <SelectItem value="active">Ativo</SelectItem>
                <SelectItem value="suspended">Suspenso</SelectItem>
                <SelectItem value="terminated">Encerrado</SelectItem>
              </SelectContent>
            </Select>
            <Select value={contractTypeFilter} onValueChange={(v) => { setContractTypeFilter(v); setPage(0); }}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Tipo" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos os tipos</SelectItem>
                <SelectItem value="servico_vigilancia">Vigilancia</SelectItem>
                <SelectItem value="servico_portaria">Portaria</SelectItem>
                <SelectItem value="servico_limpeza">Limpeza</SelectItem>
                <SelectItem value="misto">Misto</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Error */}
      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-destructive" />
          <p className="text-sm text-destructive flex-1">Erro ao carregar contratos</p>
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
          ) : contracts.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <FileSignature className="h-16 w-16 mx-auto mb-4 opacity-50" />
              <h3 className="text-lg font-medium">Nenhum contrato encontrado</h3>
              <p className="mt-2">Tente ajustar os filtros ou crie um novo contrato</p>
              <Button className="mt-4" onClick={() => { setEditContrato(null); setFormOpen(true); }}>
                <Plus className="h-4 w-4 mr-2" />
                Novo Contrato
              </Button>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Numero</TableHead>
                  <TableHead>Titulo</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Valor Mensal</TableHead>
                  <TableHead>Data Fim</TableHead>
                  <TableHead className="w-[80px]">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {contracts.map((contrato: any) => (
                  <TableRow key={contrato.id}>
                    <TableCell>
                      <span className="font-mono text-sm">{contrato.numero || '-'}</span>
                    </TableCell>
                    <TableCell>
                      <div className="font-medium">{contrato.titulo || contrato.title || '-'}</div>
                    </TableCell>
                    <TableCell>{getTipoBadge(contrato.contract_type)}</TableCell>
                    <TableCell>{getStatusBadge(contrato.status)}</TableCell>
                    <TableCell className="text-sm">
                      {formatCurrency(contrato.valor_mensal || contrato.monthly_value || 0)}
                    </TableCell>
                    <TableCell className="text-sm">
                      {formatDate(contrato.data_fim || contrato.end_date)}
                    </TableCell>
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-8 w-8">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => { setSelectedContrato(contrato); setDetailOpen(true); }}>
                            <Eye className="h-4 w-4 mr-2" />
                            Ver detalhes
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => { setEditContrato(contrato); setFormOpen(true); }}>
                            <Edit className="h-4 w-4 mr-2" />
                            Editar
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          {contrato.status === 'draft' && (
                            <DropdownMenuItem onClick={() =>
                              openConfirm(
                                'Submeter Contrato',
                                `Deseja submeter o contrato "${contrato.numero}"?`,
                                () => submitMutation.mutateAsync(contrato.id),
                                'info'
                              )
                            }>
                              <Send className="h-4 w-4 mr-2" />
                              Submeter
                            </DropdownMenuItem>
                          )}
                          {contrato.status === 'submitted' && (
                            <DropdownMenuItem onClick={() =>
                              openConfirm(
                                'Ativar Contrato',
                                `Deseja ativar o contrato "${contrato.numero}"?`,
                                () => activateMutation.mutateAsync(contrato.id),
                                'info'
                              )
                            }>
                              <Play className="h-4 w-4 mr-2" />
                              Ativar
                            </DropdownMenuItem>
                          )}
                          {contrato.status === 'active' && (
                            <DropdownMenuItem onClick={() =>
                              openConfirm(
                                'Suspender Contrato',
                                `Deseja suspender o contrato "${contrato.numero}"?`,
                                () => suspendMutation.mutateAsync({ contractId: contrato.id }),
                                'warning'
                              )
                            }>
                              <Pause className="h-4 w-4 mr-2" />
                              Suspender
                            </DropdownMenuItem>
                          )}
                          {(contrato.status === 'active' || contrato.status === 'suspended') && (
                            <DropdownMenuItem onClick={() =>
                              openConfirm(
                                'Encerrar Contrato',
                                `Deseja encerrar o contrato "${contrato.numero}"? Esta acao nao pode ser desfeita.`,
                                () => terminateMutation.mutateAsync({ contractId: contrato.id }),
                                'danger'
                              )
                            }>
                              <XCircle className="h-4 w-4 mr-2" />
                              Encerrar
                            </DropdownMenuItem>
                          )}
                          {contrato.status === 'draft' && (
                            <>
                              <DropdownMenuSeparator />
                              <DropdownMenuItem
                                className="text-destructive"
                                onClick={() =>
                                  openConfirm(
                                    'Deletar Contrato',
                                    `Deletar o contrato "${contrato.numero}" permanentemente?`,
                                    () => deleteMutation.mutateAsync(contrato.id),
                                    'danger'
                                  )
                                }
                              >
                                <Trash2 className="h-4 w-4 mr-2" />
                                Deletar
                              </DropdownMenuItem>
                            </>
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

      {/* Pagination */}
      {total > pageSize && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Mostrando {page * pageSize + 1}-{Math.min((page + 1) * pageSize, total)} de {total}
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage(Math.max(0, page - 1))}
              disabled={page === 0}
            >
              Anterior
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage(page + 1)}
              disabled={(page + 1) * pageSize >= total}
            >
              Proximo
            </Button>
          </div>
        </div>
      )}

      {/* Modals */}
      <ContratoFormModal
        isOpen={formOpen}
        onClose={() => { setFormOpen(false); setEditContrato(null); }}
        contrato={editContrato}
        onSubmit={editContrato ? handleUpdate : handleCreate}
        isLoading={createMutation.isPending || updateMutation.isPending}
      />

      <ContratoDetailModal
        isOpen={detailOpen}
        onClose={() => { setDetailOpen(false); setSelectedContrato(null); }}
        contrato={selectedContrato}
      />

      {confirmAction && (
        <ConfirmModal
          isOpen={confirmOpen}
          onClose={() => setConfirmOpen(false)}
          onConfirm={async () => {
            await confirmAction.action();
            setConfirmOpen(false);
          }}
          title={confirmAction.title}
          message={confirmAction.message}
          variant={confirmAction.variant}
          isLoading={
            submitMutation.isPending ||
            activateMutation.isPending ||
            suspendMutation.isPending ||
            terminateMutation.isPending ||
            deleteMutation.isPending
          }
        />
      )}
    </div>
  );
}
