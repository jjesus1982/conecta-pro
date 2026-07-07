'use client';

import { Building2, Search, RefreshCw, Plus, MoreHorizontal, Users, AlertCircle, Eye, Edit, Play, Pause, XCircle, Zap, Trash2 } from 'lucide-react';
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
  useTenants,
  useCreateTenant,
  useUpdateTenant,
  useDeleteTenant,
  useActivateTenant,
  useSuspendTenant,
  useCancelTenant,
  useConvertTrialTenant,
  useUpdateTenantPlan,
  useUpdateTenantAddress,
  useEnableTenantFeature,
  useDisableTenantFeature,
} from '@/hooks/useConfig';
import { TenantFormModal } from '@/components/configuracoes/tenant-form-modal';
import { TenantDetailModal } from '@/components/configuracoes/tenant-detail-modal';
import type { TenantResponse } from '@/types/generated/config/conectaPROCONFIGModuleAPI.schemas';

export default function TenantsPage() {
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [planFilter, setPlanFilter] = useState('all');
  const [page, setPage] = useState(0);
  const pageSize = 20;

  const { data: tenantsData, isLoading, error, refetch } = useTenants({
    skip: page * pageSize,
    limit: pageSize,
    search: search || undefined,
    status: statusFilter !== 'all' ? statusFilter : undefined,
    plan: planFilter !== 'all' ? planFilter : undefined,
  });

  const createMutation = useCreateTenant();
  const updateMutation = useUpdateTenant();
  const deleteMutation = useDeleteTenant();
  const activateMutation = useActivateTenant();
  const suspendMutation = useSuspendTenant();
  const cancelMutation = useCancelTenant();
  const convertTrialMutation = useConvertTrialTenant();
  const updatePlanMutation = useUpdateTenantPlan();
  const updateAddressMutation = useUpdateTenantAddress();
  const enableFeatureMutation = useEnableTenantFeature();
  const disableFeatureMutation = useDisableTenantFeature();

  const [formOpen, setFormOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [editTenant, setEditTenant] = useState<TenantResponse | null>(null);
  const [selectedTenant, setSelectedTenant] = useState<TenantResponse | null>(null);

  // Confirm modal state
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmAction, setConfirmAction] = useState<{
    title: string;
    message: string;
    action: () => Promise<void>;
    variant: 'danger' | 'warning' | 'info';
  } | null>(null);

  const tenants = tenantsData?.items || [];
  const total = tenantsData?.total || 0;

  const stats = {
    total,
    active: tenants.filter((t) => t.status === 'active').length,
    trial: tenants.filter((t) => t.status === 'trial').length,
    suspended: tenants.filter((t) => t.status === 'suspended').length,
  };

  const openConfirm = (title: string, message: string, action: () => Promise<void>, variant: 'danger' | 'warning' | 'info' = 'warning') => {
    setConfirmAction({ title, message, action, variant });
    setConfirmOpen(true);
  };

  const handleCreate = async (data: any) => {
    await createMutation.mutateAsync(data);
    setFormOpen(false);
  };

  const handleUpdate = async (data: any) => {
    if (!editTenant) return;
    await updateMutation.mutateAsync({ id: editTenant.id, data });
    setFormOpen(false);
    setEditTenant(null);
  };

  const getStatusBadge = (status: string) => {
    const map: Record<string, string> = {
      active: 'bg-green-100 text-green-800',
      trial: 'bg-blue-100 text-blue-800',
      suspended: 'bg-yellow-100 text-yellow-800',
      canceled: 'bg-red-100 text-red-800',
      inactive: 'bg-gray-100 text-gray-800',
    };
    const labels: Record<string, string> = {
      active: 'Ativo',
      trial: 'Trial',
      suspended: 'Suspenso',
      canceled: 'Cancelado',
      inactive: 'Inativo',
    };
    return <Badge className={map[status] || ''}>{labels[status] || status}</Badge>;
  };

  const getPlanBadge = (plan: string) => {
    const map: Record<string, string> = {
      free: 'bg-gray-100 text-gray-800',
      starter: 'bg-blue-100 text-blue-800',
      pro: 'bg-purple-100 text-purple-800',
      enterprise: 'bg-amber-100 text-amber-800',
    };
    return (
      <Badge className={map[plan] || 'bg-gray-100 text-gray-800'}>
        {plan.charAt(0).toUpperCase() + plan.slice(1)}
      </Badge>
    );
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <Building2 className="h-6 w-6" />
            Tenants
          </h1>
          <p className="text-muted-foreground">Gestao de tenants, planos e status</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => refetch()} disabled={isLoading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
            Atualizar
          </Button>
          <Button onClick={() => { setEditTenant(null); setFormOpen(true); }}>
            <Plus className="h-4 w-4 mr-2" />
            Novo Tenant
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total</CardTitle>
            <Building2 className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums">{stats.total}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Ativos</CardTitle>
            <Users className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-green-600">{stats.active}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Trial</CardTitle>
            <Zap className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-blue-600">{stats.trial}</div>
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
                placeholder="Buscar por nome, email, CNPJ..."
                className="pl-10"
              />
            </div>
            <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v); setPage(0); }}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos os status</SelectItem>
                <SelectItem value="active">Ativo</SelectItem>
                <SelectItem value="trial">Trial</SelectItem>
                <SelectItem value="suspended">Suspenso</SelectItem>
                <SelectItem value="canceled">Cancelado</SelectItem>
                <SelectItem value="inactive">Inativo</SelectItem>
              </SelectContent>
            </Select>
            <Select value={planFilter} onValueChange={(v) => { setPlanFilter(v); setPage(0); }}>
              <SelectTrigger className="w-[160px]">
                <SelectValue placeholder="Plano" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos os planos</SelectItem>
                <SelectItem value="free">Free</SelectItem>
                <SelectItem value="starter">Starter</SelectItem>
                <SelectItem value="pro">Pro</SelectItem>
                <SelectItem value="enterprise">Enterprise</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Error */}
      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-destructive" />
          <p className="text-sm text-destructive flex-1">Erro ao carregar tenants</p>
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
          ) : tenants.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <Building2 className="h-16 w-16 mx-auto mb-4 opacity-50" />
              <h3 className="text-lg font-medium">Nenhum tenant encontrado</h3>
              <p className="mt-2">Tente ajustar os filtros ou crie um novo tenant</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nome</TableHead>
                  <TableHead>CNPJ</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead>Plano</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Usuarios</TableHead>
                  <TableHead className="w-[80px]">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {tenants.map((tenant) => (
                  <TableRow key={tenant.id}>
                    <TableCell>
                      <div>
                        <div className="font-medium">{tenant.nome}</div>
                        <div className="text-xs text-muted-foreground font-mono">{tenant.codigo}</div>
                      </div>
                    </TableCell>
                    <TableCell className="text-sm">{tenant.cnpj || '-'}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">{tenant.email}</TableCell>
                    <TableCell>{getPlanBadge(tenant.plan)}</TableCell>
                    <TableCell>{getStatusBadge(tenant.status)}</TableCell>
                    <TableCell className="text-sm">
                      {tenant.current_users ?? 0}/{tenant.max_users}
                    </TableCell>
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-8 w-8">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => { setSelectedTenant(tenant); setDetailOpen(true); }}>
                            <Eye className="h-4 w-4 mr-2" />
                            Ver detalhes
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => { setEditTenant(tenant); setFormOpen(true); }}>
                            <Edit className="h-4 w-4 mr-2" />
                            Editar
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          {tenant.status !== 'active' && (
                            <DropdownMenuItem onClick={() =>
                              openConfirm('Ativar Tenant', `Deseja ativar "${tenant.nome}"?`, () => activateMutation.mutateAsync(tenant.id).then(() => {}), 'info')
                            }>
                              <Play className="h-4 w-4 mr-2" />
                              Ativar
                            </DropdownMenuItem>
                          )}
                          {tenant.status === 'active' && (
                            <DropdownMenuItem onClick={() =>
                              openConfirm('Suspender Tenant', `Deseja suspender "${tenant.nome}"?`, () => suspendMutation.mutateAsync(tenant.id).then(() => {}), 'warning')
                            }>
                              <Pause className="h-4 w-4 mr-2" />
                              Suspender
                            </DropdownMenuItem>
                          )}
                          {tenant.status === 'trial' && (
                            <DropdownMenuItem onClick={() =>
                              openConfirm('Converter Trial', `Converter "${tenant.nome}" para plano pago?`, () => convertTrialMutation.mutateAsync(tenant.id).then(() => {}), 'info')
                            }>
                              <Zap className="h-4 w-4 mr-2" />
                              Converter Trial
                            </DropdownMenuItem>
                          )}
                          {tenant.status !== 'canceled' && (
                            <DropdownMenuItem onClick={() =>
                              openConfirm('Cancelar Tenant', `Deseja cancelar "${tenant.nome}"? Esta acao nao pode ser desfeita.`, () => cancelMutation.mutateAsync(tenant.id).then(() => {}), 'danger')
                            }>
                              <XCircle className="h-4 w-4 mr-2" />
                              Cancelar
                            </DropdownMenuItem>
                          )}
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            className="text-destructive"
                            onClick={() =>
                              openConfirm('Deletar Tenant', `Deletar "${tenant.nome}" permanentemente?`, () => deleteMutation.mutateAsync(tenant.id).then(() => {}), 'danger')
                            }
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
      <TenantFormModal
        isOpen={formOpen}
        onClose={() => { setFormOpen(false); setEditTenant(null); }}
        tenant={editTenant}
        onSubmit={editTenant ? handleUpdate : handleCreate}
        isLoading={createMutation.isPending || updateMutation.isPending}
      />

      <TenantDetailModal
        isOpen={detailOpen}
        onClose={() => { setDetailOpen(false); setSelectedTenant(null); }}
        tenant={selectedTenant}
        onUpdatePlan={async (plan) => {
          if (!selectedTenant) return;
          await updatePlanMutation.mutateAsync({ id: selectedTenant.id, plan });
        }}
        onUpdateAddress={async (address) => {
          if (!selectedTenant) return;
          await updateAddressMutation.mutateAsync({ id: selectedTenant.id, address });
        }}
        onEnableFeature={async (feature) => {
          if (!selectedTenant) return;
          await enableFeatureMutation.mutateAsync({ id: selectedTenant.id, feature });
        }}
        onDisableFeature={async (feature) => {
          if (!selectedTenant) return;
          await disableFeatureMutation.mutateAsync({ id: selectedTenant.id, feature });
        }}
        isLoading={updatePlanMutation.isPending || updateAddressMutation.isPending || enableFeatureMutation.isPending || disableFeatureMutation.isPending}
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
          isLoading={activateMutation.isPending || suspendMutation.isPending || cancelMutation.isPending || convertTrialMutation.isPending || deleteMutation.isPending}
        />
      )}
    </div>
  );
}
