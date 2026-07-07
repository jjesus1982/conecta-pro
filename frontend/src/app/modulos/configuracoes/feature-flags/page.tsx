'use client';

import { ToggleRight, Search, RefreshCw, Plus, MoreHorizontal, AlertCircle, Eye, Edit, Power, PowerOff, Trash2, Zap, Ban } from 'lucide-react';
import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';
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
  useFeatureFlags,
  useCreateFeatureFlag,
  useUpdateFeatureFlag,
  useDeleteFeatureFlag,
  useEnableFeatureFlag,
  useDisableFeatureFlag,
  useSetFeatureFlagPercentage,
  useSetGradualRollout,
  useToggleFeatureFlagForTenant,
} from '@/hooks/useConfig';
import { getCategoryLabel, getStatusLabel, getStatusColor } from '@/services/config/feature-flags';
import { FeatureFlagFormModal } from '@/components/configuracoes/feature-flag-form-modal';
import { FeatureFlagDetailModal } from '@/components/configuracoes/feature-flag-detail-modal';
import type { FeatureFlagResponse } from '@/types/generated/config/conectaPROCONFIGModuleAPI.schemas';

export default function FeatureFlagsPage() {
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [page, setPage] = useState(0);
  const pageSize = 20;

  const { data: flagsData, isLoading, error, refetch } = useFeatureFlags({
    skip: page * pageSize,
    limit: pageSize,
    search: search || undefined,
    status: statusFilter !== 'all' ? statusFilter : undefined,
    category: categoryFilter !== 'all' ? categoryFilter : undefined,
  });

  const createMutation = useCreateFeatureFlag();
  const updateMutation = useUpdateFeatureFlag();
  const deleteMutation = useDeleteFeatureFlag();
  const enableMutation = useEnableFeatureFlag();
  const disableMutation = useDisableFeatureFlag();
  const setPercentageMutation = useSetFeatureFlagPercentage();
  const setGradualMutation = useSetGradualRollout();
  const toggleTenantMutation = useToggleFeatureFlagForTenant();

  const [formOpen, setFormOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [editFlag, setEditFlag] = useState<FeatureFlagResponse | null>(null);
  const [selectedFlag, setSelectedFlag] = useState<FeatureFlagResponse | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmAction, setConfirmAction] = useState<{
    title: string;
    message: string;
    action: () => Promise<void>;
    variant: 'danger' | 'warning' | 'info';
  } | null>(null);

  const flags = flagsData?.items || [];
  const total = flagsData?.total || 0;

  const stats = {
    total,
    active: flags.filter((f) => f.ativo).length,
    rollout: flags.filter((f) => f.rollout_percentage && f.rollout_percentage > 0 && f.rollout_percentage < 100).length,
    disabled: flags.filter((f) => !f.ativo).length,
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
    if (!editFlag) return;
    await updateMutation.mutateAsync({ id: editFlag.id, data });
    setFormOpen(false);
    setEditFlag(null);
  };

  const getStatusBadgeColor = (flag: FeatureFlagResponse) => {
    const color = getStatusColor(flag);
    const map: Record<string, string> = {
      green: 'bg-green-100 text-green-800',
      blue: 'bg-blue-100 text-blue-800',
      yellow: 'bg-yellow-100 text-yellow-800',
      gray: 'bg-gray-100 text-gray-800',
    };
    return map[color] || 'bg-gray-100 text-gray-800';
  };

  const getTypeBadge = (type: string) => {
    const map: Record<string, string> = {
      boolean: 'bg-blue-100 text-blue-800',
      percentage: 'bg-purple-100 text-purple-800',
      gradual: 'bg-orange-100 text-orange-800',
      whitelist: 'bg-cyan-100 text-cyan-800',
    };
    return <Badge className={map[type] || 'bg-gray-100 text-gray-800'}>{type}</Badge>;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <ToggleRight className="h-6 w-6" />
            Feature Flags
          </h1>
          <p className="text-muted-foreground">Controle de features e rollout gradual</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => refetch()} disabled={isLoading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
            Atualizar
          </Button>
          <Button onClick={() => { setEditFlag(null); setFormOpen(true); }}>
            <Plus className="h-4 w-4 mr-2" />
            Nova Flag
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total</CardTitle>
            <ToggleRight className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums">{stats.total}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Ativas</CardTitle>
            <Power className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-green-600">{stats.active}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Em Rollout</CardTitle>
            <Zap className="h-4 w-4 text-orange-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-orange-600">{stats.rollout}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Desabilitadas</CardTitle>
            <Ban className="h-4 w-4 text-gray-500" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-gray-500">{stats.disabled}</div>
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
                placeholder="Buscar por nome ou codigo..."
                className="pl-10"
              />
            </div>
            <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v); setPage(0); }}>
              <SelectTrigger className="w-[160px]">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos</SelectItem>
                <SelectItem value="active">Ativas</SelectItem>
                <SelectItem value="inactive">Inativas</SelectItem>
              </SelectContent>
            </Select>
            <Select value={categoryFilter} onValueChange={(v) => { setCategoryFilter(v); setPage(0); }}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Categoria" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todas categorias</SelectItem>
                <SelectItem value="features">Funcionalidades</SelectItem>
                <SelectItem value="experimental">Experimental</SelectItem>
                <SelectItem value="maintenance">Manutencao</SelectItem>
                <SelectItem value="performance">Performance</SelectItem>
                <SelectItem value="ui">Interface</SelectItem>
                <SelectItem value="integrations">Integracoes</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Error */}
      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-destructive" />
          <p className="text-sm text-destructive flex-1">Erro ao carregar feature flags</p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>Tentar novamente</Button>
        </div>
      )}

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
            </div>
          ) : flags.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <ToggleRight className="h-16 w-16 mx-auto mb-4 opacity-50" />
              <h3 className="text-lg font-medium">Nenhuma feature flag encontrada</h3>
              <p className="mt-2">Crie uma nova feature flag para comecar</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nome / Codigo</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Rollout</TableHead>
                  <TableHead>Categoria</TableHead>
                  <TableHead className="w-[80px]">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {flags.map((flag) => (
                  <TableRow key={flag.id}>
                    <TableCell>
                      <div>
                        <div className="font-medium">{flag.nome}</div>
                        <div className="text-xs text-muted-foreground font-mono">{flag.codigo}</div>
                      </div>
                    </TableCell>
                    <TableCell>{getTypeBadge(flag.flag_type)}</TableCell>
                    <TableCell>
                      <Badge className={getStatusBadgeColor(flag)}>
                        {getStatusLabel(flag)}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2 min-w-[120px]">
                        <Progress value={flag.rollout_percentage ?? 0} className="flex-1 h-2" />
                        <span className="text-xs text-muted-foreground w-10 text-right">
                          {flag.rollout_percentage ?? 0}%
                        </span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <span className="text-sm">{getCategoryLabel(flag.category || 'features')}</span>
                    </TableCell>
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-8 w-8">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => { setSelectedFlag(flag); setDetailOpen(true); }}>
                            <Eye className="h-4 w-4 mr-2" />
                            Detalhes
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => { setEditFlag(flag); setFormOpen(true); }}>
                            <Edit className="h-4 w-4 mr-2" />
                            Editar
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          {flag.ativo ? (
                            <DropdownMenuItem onClick={() =>
                              openConfirm('Desabilitar Flag', `Desabilitar "${flag.nome}"?`, () => disableMutation.mutateAsync(flag.id).then(() => {}), 'warning')
                            }>
                              <PowerOff className="h-4 w-4 mr-2" />
                              Desabilitar
                            </DropdownMenuItem>
                          ) : (
                            <DropdownMenuItem onClick={() =>
                              openConfirm('Habilitar Flag', `Habilitar "${flag.nome}"?`, () => enableMutation.mutateAsync(flag.id).then(() => {}), 'info')
                            }>
                              <Power className="h-4 w-4 mr-2" />
                              Habilitar
                            </DropdownMenuItem>
                          )}
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            className="text-destructive"
                            onClick={() =>
                              openConfirm('Deletar Flag', `Deletar "${flag.nome}" permanentemente?`, () => deleteMutation.mutateAsync(flag.id).then(() => {}), 'danger')
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
            <Button variant="outline" size="sm" onClick={() => setPage(Math.max(0, page - 1))} disabled={page === 0}>
              Anterior
            </Button>
            <Button variant="outline" size="sm" onClick={() => setPage(page + 1)} disabled={(page + 1) * pageSize >= total}>
              Proximo
            </Button>
          </div>
        </div>
      )}

      {/* Modals */}
      <FeatureFlagFormModal
        isOpen={formOpen}
        onClose={() => { setFormOpen(false); setEditFlag(null); }}
        flag={editFlag}
        onSubmit={editFlag ? handleUpdate : handleCreate}
        isLoading={createMutation.isPending || updateMutation.isPending}
      />

      <FeatureFlagDetailModal
        isOpen={detailOpen}
        onClose={() => { setDetailOpen(false); setSelectedFlag(null); }}
        flag={selectedFlag}
        onSetPercentage={async (pct) => {
          if (!selectedFlag) return;
          await setPercentageMutation.mutateAsync({ id: selectedFlag.id, percentage: pct });
        }}
        onSetGradualRollout={async (rollout) => {
          if (!selectedFlag) return;
          await setGradualMutation.mutateAsync({ id: selectedFlag.id, rollout });
        }}
        onToggleTenant={async (tenantId, enabled) => {
          if (!selectedFlag) return;
          await toggleTenantMutation.mutateAsync({ id: selectedFlag.id, toggle: { tenant_id: tenantId, enabled } });
        }}
        isLoading={setPercentageMutation.isPending || setGradualMutation.isPending || toggleTenantMutation.isPending}
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
          isLoading={enableMutation.isPending || disableMutation.isPending || deleteMutation.isPending}
        />
      )}
    </div>
  );
}
