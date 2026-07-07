'use client';

import { Repeat, Search, RefreshCw, Plus, MoreHorizontal, Eye, Edit, FileSignature, Truck, XCircle, Trash2, AlertCircle } from 'lucide-react';
import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { ConfirmModal } from '@/components/ui/modal';
import {
  useComodatoList,
  useComodatoStats,
  useCreateComodato,
  useUpdateComodato,
  useDeleteComodato,
  useSignComodato,
  useDeliverComodato,
  useTerminateComodato,
} from '@/hooks/equipment';
import { ComodatoFormModal } from '@/components/equipamentos/comodato-form-modal';
import { ComodatoDetailModal } from '@/components/equipamentos/comodato-detail-modal';
import { cn } from '@/lib/utils';

const statusConfig: Record<string, { label: string; className: string }> = {
  draft: { label: 'Rascunho', className: 'bg-gray-100 text-gray-800' },
  pending_signature: { label: 'Aguard. Assinatura', className: 'bg-yellow-100 text-yellow-800' },
  active: { label: 'Ativo', className: 'bg-green-100 text-green-800' },
  pending_return: { label: 'Aguard. Devolucao', className: 'bg-orange-100 text-orange-800' },
  terminated: { label: 'Encerrado', className: 'bg-red-100 text-red-800' },
  expired: { label: 'Expirado', className: 'bg-gray-100 text-gray-800' },
};

const STATUS_OPTIONS = [
  { value: 'all', label: 'Todos os Status' },
  { value: 'draft', label: 'Rascunho' },
  { value: 'pending_signature', label: 'Aguard. Assinatura' },
  { value: 'active', label: 'Ativo' },
  { value: 'pending_return', label: 'Aguard. Devolucao' },
  { value: 'terminated', label: 'Encerrado' },
  { value: 'expired', label: 'Expirado' },
];

export default function ComodatosPage() {
  // Pagination & Filters
  const [page, setPage] = useState(0);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const limit = 20;

  // Modals
  const [formOpen, setFormOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [signOpen, setSignOpen] = useState(false);
  const [deliverOpen, setDeliverOpen] = useState(false);
  const [terminateOpen, setTerminateOpen] = useState(false);
  const [selectedComodato, setSelectedComodato] = useState<any>(null);

  // Queries
  const {
    data: listData,
    isLoading,
    isError,
    error,
    refetch,
  } = useComodatoList({
    search: search || undefined,
    status: statusFilter !== 'all' ? statusFilter : undefined,
  });

  const { data: statsRaw, isLoading: statsLoading } = useComodatoStats();
  const stats = statsRaw as { total?: number; active?: number; pending_signature?: number; expiring?: number } | undefined;

  // Mutations
  const createMutation = useCreateComodato();
  const updateMutation = useUpdateComodato();
  const deleteMutation = useDeleteComodato();
  const signMutation = useSignComodato();
  const deliverMutation = useDeliverComodato();
  const terminateMutation = useTerminateComodato();

  const items = listData?.items ?? [];
  const total = listData?.total ?? 0;
  const totalPages = Math.ceil(total / limit);

  // Handlers
  const handleCreate = () => {
    setSelectedComodato(null);
    setFormOpen(true);
  };

  const handleEdit = (comodato: any) => {
    setSelectedComodato(comodato);
    setFormOpen(true);
  };

  const handleViewDetail = (comodato: any) => {
    setSelectedComodato(comodato);
    setDetailOpen(true);
  };

  const handleFormSubmit = async (data: any) => {
    if (selectedComodato) {
      await updateMutation.mutateAsync({ comodatoId: selectedComodato.id, data });
    } else {
      await createMutation.mutateAsync(data);
    }
    setFormOpen(false);
    setSelectedComodato(null);
  };

  const handleDelete = (comodato: any) => {
    setSelectedComodato(comodato);
    setDeleteOpen(true);
  };

  const confirmDelete = async () => {
    if (!selectedComodato) return;
    await deleteMutation.mutateAsync(selectedComodato.id);
    setDeleteOpen(false);
    setSelectedComodato(null);
  };

  const handleSign = (comodato: any) => {
    setSelectedComodato(comodato);
    setSignOpen(true);
  };

  const confirmSign = async () => {
    if (!selectedComodato) return;
    await signMutation.mutateAsync({
      comodatoId: selectedComodato.id,
      params: { signed_by_client: 'TODO', signed_by_company: 'TODO' },
    });
    setSignOpen(false);
    setSelectedComodato(null);
  };

  const handleDeliver = (comodato: any) => {
    setSelectedComodato(comodato);
    setDeliverOpen(true);
  };

  const confirmDeliver = async () => {
    if (!selectedComodato) return;
    await deliverMutation.mutateAsync({
      comodatoId: selectedComodato.id,
      params: { delivered_by: 'TODO', received_by: 'TODO' },
    });
    setDeliverOpen(false);
    setSelectedComodato(null);
  };

  const handleTerminate = (comodato: any) => {
    setSelectedComodato(comodato);
    setTerminateOpen(true);
  };

  const confirmTerminate = async () => {
    if (!selectedComodato) return;
    await terminateMutation.mutateAsync({
      comodatoId: selectedComodato.id,
      params: { reason: 'Encerramento solicitado' },
    });
    setTerminateOpen(false);
    setSelectedComodato(null);
  };

  const formatDate = (dateStr: string | null | undefined) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString('pt-BR');
  };

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <Repeat className="h-6 w-6" />
            Comodatos
          </h1>
          <p className="text-muted-foreground">
            Gestao de contratos de comodato
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => refetch()}
            disabled={isLoading}
          >
            <RefreshCw className={cn('w-4 h-4', isLoading && 'animate-spin')} />
          </Button>
          <Button onClick={handleCreate}>
            <Plus className="w-4 h-4 mr-2" />
            Novo Comodato
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total</CardTitle>
            <Repeat className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums">{stats?.total ?? 0}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Ativos</CardTitle>
            <Repeat className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-green-600">{stats?.active ?? 0}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Aguardando Assinatura</CardTitle>
            <FileSignature className="h-4 w-4 text-yellow-600" />
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-yellow-600">{stats?.pending_signature ?? 0}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Expirando</CardTitle>
            <AlertCircle className="h-4 w-4 text-orange-600" />
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-orange-600">{stats?.expiring ?? 0}</div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            type="search"
            placeholder="Buscar por codigo, cliente ou equipamento..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(0);
            }}
            className="pl-10"
          />
        </div>
        <Select
          value={statusFilter}
          onValueChange={(value) => {
            setStatusFilter(value);
            setPage(0);
          }}
        >
          <SelectTrigger className="w-full sm:w-[220px]">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            {STATUS_OPTIONS.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Error */}
      {isError && (
        <div className="flex items-center gap-3 p-4 rounded-lg bg-[hsl(var(--destructive))]/10 border border-[hsl(var(--destructive))]/30">
          <AlertCircle className="w-5 h-5 text-[hsl(var(--destructive))]" />
          <div>
            <p className="font-medium text-[hsl(var(--destructive))]">Erro ao carregar comodatos</p>
            <p className="text-sm text-[hsl(var(--muted-foreground))]">
              {(error as Error)?.message || 'Tente novamente em alguns instantes'}
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={() => refetch()} className="ml-auto">
            Tentar novamente
          </Button>
        </div>
      )}

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="divide-y divide-[hsl(var(--border))]">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="p-4 flex items-center gap-4">
                  <div className="flex-1 space-y-2">
                    <div className="h-4 w-48 bg-muted rounded animate-pulse" />
                    <div className="h-3 w-32 bg-muted rounded animate-pulse" />
                  </div>
                  <div className="h-6 w-20 bg-muted rounded animate-pulse" />
                  <div className="h-4 w-24 bg-muted rounded animate-pulse" />
                </div>
              ))}
            </div>
          ) : items.length === 0 ? (
            <div className="text-center py-12">
              <Repeat className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
              <h3 className="text-lg font-medium">Nenhum comodato encontrado</h3>
              <p className="text-muted-foreground mt-1">
                {search || statusFilter !== 'all'
                  ? 'Tente ajustar os filtros ou crie um novo comodato'
                  : 'Comece criando seu primeiro contrato de comodato'}
              </p>
              {!search && statusFilter === 'all' && (
                <Button className="mt-4" onClick={handleCreate}>
                  <Plus className="w-4 h-4 mr-2" />
                  Novo Comodato
                </Button>
              )}
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Contrato</TableHead>
                  <TableHead>Cliente</TableHead>
                  <TableHead>Equipamento</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Vigencia</TableHead>
                  <TableHead className="w-12"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item: any) => {
                  const status = statusConfig[item.status] ?? { label: String(item.status), className: 'bg-gray-100 text-gray-800' };
                  return (
                    <TableRow key={item.id}>
                      <TableCell className="font-medium">{item.codigo}</TableCell>
                      <TableCell>{item.client_name}</TableCell>
                      <TableCell>{item.equipment_name}</TableCell>
                      <TableCell>
                        <Badge className={cn('border-0', status.className)}>
                          {status.label}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {formatDate(item.start_date)} - {formatDate(item.end_date)}
                      </TableCell>
                      <TableCell>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="sm">
                              <MoreHorizontal className="w-4 h-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem onClick={() => handleViewDetail(item)}>
                              <Eye className="w-4 h-4 mr-2" />
                              Ver detalhes
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={() => handleEdit(item)}>
                              <Edit className="w-4 h-4 mr-2" />
                              Editar
                            </DropdownMenuItem>
                            {item.status === 'pending_signature' && (
                              <DropdownMenuItem onClick={() => handleSign(item)}>
                                <FileSignature className="w-4 h-4 mr-2" />
                                Assinar
                              </DropdownMenuItem>
                            )}
                            {(item.status === 'pending_signature' || item.status === 'draft') && (
                              <DropdownMenuItem onClick={() => handleDeliver(item)}>
                                <Truck className="w-4 h-4 mr-2" />
                                Entregar
                              </DropdownMenuItem>
                            )}
                            {item.status === 'active' && (
                              <DropdownMenuItem onClick={() => handleTerminate(item)}>
                                <XCircle className="w-4 h-4 mr-2" />
                                Encerrar
                              </DropdownMenuItem>
                            )}
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              onClick={() => handleDelete(item)}
                              className="text-red-600 focus:text-red-600"
                            >
                              <Trash2 className="w-4 h-4 mr-2" />
                              Deletar
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Pagination */}
      {!isLoading && totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Mostrando {page * limit + 1}-{Math.min((page + 1) * limit, total)} de {total} comodatos
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page === 0}
              onClick={() => setPage((p) => Math.max(0, p - 1))}
            >
              Anterior
            </Button>
            <span className="text-sm text-muted-foreground">
              {page + 1} / {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages - 1}
              onClick={() => setPage((p) => p + 1)}
            >
              Proximo
            </Button>
          </div>
        </div>
      )}

      {/* Form Modal (Create / Edit) */}
      <ComodatoFormModal
        isOpen={formOpen}
        onClose={() => {
          setFormOpen(false);
          setSelectedComodato(null);
        }}
        comodato={selectedComodato}
        onSubmit={handleFormSubmit}
        isLoading={createMutation.isPending || updateMutation.isPending}
      />

      {/* Detail Modal */}
      <ComodatoDetailModal
        isOpen={detailOpen}
        onClose={() => {
          setDetailOpen(false);
          setSelectedComodato(null);
        }}
        comodato={selectedComodato}
      />

      {/* Confirm Delete */}
      <ConfirmModal
        isOpen={deleteOpen}
        onClose={() => {
          setDeleteOpen(false);
          setSelectedComodato(null);
        }}
        onConfirm={confirmDelete}
        title="Excluir Comodato"
        message={`Tem certeza que deseja excluir o comodato ${selectedComodato?.codigo ?? ''}? Esta acao nao pode ser desfeita.`}
        confirmText="Excluir"
        variant="danger"
        isLoading={deleteMutation.isPending}
      />

      {/* Confirm Sign */}
      <ConfirmModal
        isOpen={signOpen}
        onClose={() => {
          setSignOpen(false);
          setSelectedComodato(null);
        }}
        onConfirm={confirmSign}
        title="Assinar Comodato"
        message={`Confirma a assinatura do comodato ${selectedComodato?.codigo ?? ''}?`}
        confirmText="Assinar"
        variant="info"
        isLoading={signMutation.isPending}
      />

      {/* Confirm Deliver */}
      <ConfirmModal
        isOpen={deliverOpen}
        onClose={() => {
          setDeliverOpen(false);
          setSelectedComodato(null);
        }}
        onConfirm={confirmDeliver}
        title="Entregar Equipamento"
        message={`Confirma a entrega do equipamento do comodato ${selectedComodato?.codigo ?? ''}?`}
        confirmText="Confirmar Entrega"
        variant="info"
        isLoading={deliverMutation.isPending}
      />

      {/* Confirm Terminate */}
      <ConfirmModal
        isOpen={terminateOpen}
        onClose={() => {
          setTerminateOpen(false);
          setSelectedComodato(null);
        }}
        onConfirm={confirmTerminate}
        title="Encerrar Comodato"
        message={`Tem certeza que deseja encerrar o comodato ${selectedComodato?.codigo ?? ''}? O contrato sera finalizado.`}
        confirmText="Encerrar"
        variant="warning"
        isLoading={terminateMutation.isPending}
      />
    </div>
  );
}
