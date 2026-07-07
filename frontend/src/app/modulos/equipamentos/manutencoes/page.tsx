'use client';

import { Settings, Search, RefreshCw, Plus, MoreHorizontal, Eye, Edit, Play, CheckCircle, XCircle, Trash2, AlertCircle, Clock, AlertTriangle, Wrench } from 'lucide-react';
import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { ConfirmModal } from '@/components/ui/modal';
;
import { useMaintenanceList, useMaintenanceStats, useCreateMaintenance, useUpdateMaintenance, useDeleteMaintenance, useStartMaintenance, useCompleteMaintenance, useCancelMaintenance } from '@/hooks/equipment';
import { MaintenanceFormModal } from '@/components/equipamentos/maintenance-form-modal';
import { MaintenanceDetailModal } from '@/components/equipamentos/maintenance-detail-modal';

// Status badges
const STATUS_CONFIG: Record<string, { className: string; label: string }> = {
  scheduled: { className: 'bg-blue-100 text-blue-800', label: 'Agendada' },
  in_progress: { className: 'bg-yellow-100 text-yellow-800', label: 'Em Andamento' },
  completed: { className: 'bg-green-100 text-green-800', label: 'Concluída' },
  cancelled: { className: 'bg-gray-100 text-gray-800', label: 'Cancelada' },
  waiting_parts: { className: 'bg-orange-100 text-orange-800', label: 'Aguard. Peças' },
};

// Type badges
const TYPE_CONFIG: Record<string, { className: string; label: string }> = {
  preventiva: { className: 'bg-blue-100 text-blue-800', label: 'Preventiva' },
  corretiva: { className: 'bg-orange-100 text-orange-800', label: 'Corretiva' },
  emergencial: { className: 'bg-red-100 text-red-800', label: 'Emergencial' },
};

// Priority badges
const PRIORITY_CONFIG: Record<string, { className: string; label: string }> = {
  low: { className: 'bg-gray-100 text-gray-800', label: 'Baixa' },
  medium: { className: 'bg-blue-100 text-blue-800', label: 'Média' },
  high: { className: 'bg-orange-100 text-orange-800', label: 'Alta' },
  critical: { className: 'bg-red-100 text-red-800', label: 'Crítica' },
};

export default function ManutencoesPage() {
  // Filters
  const [search, setSearch] = useState('');
  const [filterType, setFilterType] = useState<string>('all');
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [filterPriority, setFilterPriority] = useState<string>('all');
  const [skip, setSkip] = useState(0);
  const limit = 20;

  // Modal states
  const [showFormModal, setShowFormModal] = useState(false);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [showCancelModal, setShowCancelModal] = useState(false);
  const [selectedMaintenance, setSelectedMaintenance] = useState<any>(null);
  const [editMaintenance, setEditMaintenance] = useState<any>(null);

  // Queries
  const { data: listData, isLoading, refetch } = useMaintenanceList({
    page: Math.floor(skip / limit) + 1,
    page_size: limit,
    search: search || undefined,
    maintenance_type: filterType !== 'all' ? filterType : undefined,
    status: filterStatus !== 'all' ? filterStatus : undefined,
    priority: filterPriority !== 'all' ? filterPriority : undefined,
  });
  const { data: stats, isLoading: statsLoading } = useMaintenanceStats();

  // Mutations
  const createMutation = useCreateMaintenance();
  const updateMutation = useUpdateMaintenance();
  const deleteMutation = useDeleteMaintenance();
  const startMutation = useStartMaintenance();
  const completeMutation = useCompleteMaintenance();
  const cancelMutation = useCancelMaintenance();

  const items = listData?.items ?? [];
  const total = listData?.total ?? 0;

  // Handlers
  const handleRefresh = () => {
    refetch();
  };

  const handleNew = () => {
    setEditMaintenance(null);
    setShowFormModal(true);
  };

  const handleView = (maintenance: any) => {
    setSelectedMaintenance(maintenance);
    setShowDetailModal(true);
  };

  const handleEdit = (maintenance: any) => {
    setEditMaintenance(maintenance);
    setShowFormModal(true);
  };

  const handleFormSubmit = async (data: any) => {
    if (editMaintenance) {
      await updateMutation.mutateAsync({ maintenanceId: editMaintenance.id, data });
    } else {
      await createMutation.mutateAsync(data);
    }
    setShowFormModal(false);
    setEditMaintenance(null);
    handleRefresh();
  };

  const handleStart = async (maintenance: any) => {
    await startMutation.mutateAsync(maintenance.id);
    handleRefresh();
  };

  const handleComplete = async (maintenance: any) => {
    await completeMutation.mutateAsync({ maintenanceId: maintenance.id });
    handleRefresh();
  };

  const handleCancelConfirm = async () => {
    if (!selectedMaintenance) return;
    await cancelMutation.mutateAsync(selectedMaintenance.id);
    setShowCancelModal(false);
    setSelectedMaintenance(null);
    handleRefresh();
  };

  const handleDeleteConfirm = async () => {
    if (!selectedMaintenance) return;
    await deleteMutation.mutateAsync(selectedMaintenance.id);
    setShowDeleteModal(false);
    setSelectedMaintenance(null);
    handleRefresh();
  };

  const confirmCancel = (maintenance: any) => {
    setSelectedMaintenance(maintenance);
    setShowCancelModal(true);
  };

  const confirmDelete = (maintenance: any) => {
    setSelectedMaintenance(maintenance);
    setShowDeleteModal(true);
  };

  const formatDate = (dateStr: string | null | undefined) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString('pt-BR');
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <Settings className="h-6 w-6" />
            Manutenções
          </h1>
          <p className="text-muted-foreground">
            Gestão de manutenções preventivas e corretivas
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={handleRefresh} disabled={isLoading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
            Atualizar
          </Button>
          <Button onClick={handleNew}>
            <Plus className="h-4 w-4 mr-2" />
            Nova Manutenção
          </Button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total</CardTitle>
            <Wrench className="h-4 w-4 text-muted-foreground" />
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
            <CardTitle className="text-sm font-medium">Em Andamento</CardTitle>
            <Clock className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-blue-600">{stats?.in_progress ?? 0}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Atrasadas</CardTitle>
            <AlertTriangle className="h-4 w-4 text-red-600" />
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-red-600">{stats?.overdue ?? 0}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Concluídas</CardTitle>
            <CheckCircle className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-green-600">{stats?.completed ?? 0}</div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-col lg:flex-row gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Buscar por equipamento, técnico, código..."
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setSkip(0);
                }}
                className="pl-10"
              />
            </div>

            <Select value={filterType} onValueChange={(value) => { setFilterType(value); setSkip(0); }}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Tipo" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos os Tipos</SelectItem>
                <SelectItem value="preventiva">Preventiva</SelectItem>
                <SelectItem value="corretiva">Corretiva</SelectItem>
                <SelectItem value="emergencial">Emergencial</SelectItem>
              </SelectContent>
            </Select>

            <Select value={filterStatus} onValueChange={(value) => { setFilterStatus(value); setSkip(0); }}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos os Status</SelectItem>
                <SelectItem value="scheduled">Agendada</SelectItem>
                <SelectItem value="in_progress">Em Andamento</SelectItem>
                <SelectItem value="completed">Concluída</SelectItem>
                <SelectItem value="cancelled">Cancelada</SelectItem>
              </SelectContent>
            </Select>

            <Select value={filterPriority} onValueChange={(value) => { setFilterPriority(value); setSkip(0); }}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Prioridade" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todas Prioridades</SelectItem>
                <SelectItem value="low">Baixa</SelectItem>
                <SelectItem value="medium">Média</SelectItem>
                <SelectItem value="high">Alta</SelectItem>
                <SelectItem value="critical">Crítica</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : items.length === 0 ? (
            <div className="text-center py-12">
              <Wrench className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
              <h3 className="text-lg font-medium">Nenhuma manutenção encontrada</h3>
              <p className="text-muted-foreground mt-1">
                Ajuste os filtros ou registre uma nova manutenção
              </p>
              <Button className="mt-4" onClick={handleNew}>
                <Plus className="h-4 w-4 mr-2" />
                Nova Manutenção
              </Button>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Equipamento</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Prioridade</TableHead>
                  <TableHead>Técnico</TableHead>
                  <TableHead>Previsão</TableHead>
                  <TableHead className="text-right">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item: any) => {
                  const statusCfg = STATUS_CONFIG[item.status] ?? { className: 'bg-gray-100 text-gray-800', label: item.status };
                  const typeCfg = TYPE_CONFIG[item.maintenance_type] ?? { className: 'bg-gray-100 text-gray-800', label: item.maintenance_type };
                  const priorityCfg = PRIORITY_CONFIG[item.priority] ?? { className: 'bg-gray-100 text-gray-800', label: item.priority };

                  return (
                    <TableRow key={item.id} className="cursor-pointer hover:bg-muted/50" onClick={() => handleView(item)}>
                      <TableCell>
                        <div>
                          <p className="font-medium">{item.equipment_name}</p>
                          {item.codigo && (
                            <p className="text-xs text-muted-foreground font-mono">{item.codigo}</p>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge className={typeCfg.className}>{typeCfg.label}</Badge>
                      </TableCell>
                      <TableCell>
                        <Badge className={statusCfg.className}>{statusCfg.label}</Badge>
                      </TableCell>
                      <TableCell>
                        <Badge className={priorityCfg.className}>{priorityCfg.label}</Badge>
                      </TableCell>
                      <TableCell>{item.technician_name || '-'}</TableCell>
                      <TableCell>{formatDate(item.scheduled_date)}</TableCell>
                      <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="sm">
                              <MoreHorizontal className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem onClick={() => handleView(item)}>
                              <Eye className="h-4 w-4 mr-2" />
                              Ver detalhes
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={() => handleEdit(item)}>
                              <Edit className="h-4 w-4 mr-2" />
                              Editar
                            </DropdownMenuItem>

                            {item.status === 'scheduled' && (
                              <DropdownMenuItem onClick={() => handleStart(item)}>
                                <Play className="h-4 w-4 mr-2" />
                                Iniciar
                              </DropdownMenuItem>
                            )}

                            {item.status === 'in_progress' && (
                              <DropdownMenuItem onClick={() => handleComplete(item)}>
                                <CheckCircle className="h-4 w-4 mr-2" />
                                Completar
                              </DropdownMenuItem>
                            )}

                            {item.status !== 'completed' && item.status !== 'cancelled' && (
                              <>
                                <DropdownMenuSeparator />
                                <DropdownMenuItem
                                  onClick={() => confirmCancel(item)}
                                  className="text-orange-600"
                                >
                                  <XCircle className="h-4 w-4 mr-2" />
                                  Cancelar
                                </DropdownMenuItem>
                              </>
                            )}

                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              onClick={() => confirmDelete(item)}
                              className="text-red-600"
                            >
                              <Trash2 className="h-4 w-4 mr-2" />
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

        {/* Pagination */}
        {total > limit && (
          <div className="flex items-center justify-between px-6 py-4 border-t">
            <p className="text-sm text-muted-foreground">
              Mostrando {skip + 1} a {Math.min(skip + limit, total)} de {total} registros
            </p>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setSkip(Math.max(0, skip - limit))}
                disabled={skip === 0}
              >
                Anterior
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setSkip(skip + limit)}
                disabled={skip + limit >= total}
              >
                Próximo
              </Button>
            </div>
          </div>
        )}
      </Card>

      {/* Form Modal */}
      <MaintenanceFormModal
        isOpen={showFormModal}
        onClose={() => {
          setShowFormModal(false);
          setEditMaintenance(null);
        }}
        maintenance={editMaintenance}
        onSubmit={handleFormSubmit}
        isLoading={createMutation.isPending || updateMutation.isPending}
      />

      {/* Detail Modal */}
      <MaintenanceDetailModal
        isOpen={showDetailModal}
        onClose={() => {
          setShowDetailModal(false);
          setSelectedMaintenance(null);
        }}
        maintenance={selectedMaintenance}
      />

      {/* Cancel Confirm Modal */}
      <ConfirmModal
        isOpen={showCancelModal}
        onClose={() => {
          setShowCancelModal(false);
          setSelectedMaintenance(null);
        }}
        onConfirm={handleCancelConfirm}
        title="Cancelar Manutenção"
        message={`Tem certeza que deseja cancelar a manutenção ${selectedMaintenance?.codigo ?? selectedMaintenance?.equipment_name ?? ''}? Esta ação não pode ser desfeita.`}
        confirmText="Cancelar Manutenção"
        variant="warning"
        isLoading={cancelMutation.isPending}
      />

      {/* Delete Confirm Modal */}
      <ConfirmModal
        isOpen={showDeleteModal}
        onClose={() => {
          setShowDeleteModal(false);
          setSelectedMaintenance(null);
        }}
        onConfirm={handleDeleteConfirm}
        title="Excluir Manutenção"
        message={`Tem certeza que deseja excluir a manutenção ${selectedMaintenance?.codigo ?? selectedMaintenance?.equipment_name ?? ''}? Esta ação não pode ser desfeita.`}
        confirmText="Excluir"
        variant="danger"
        isLoading={deleteMutation.isPending}
      />
    </div>
  );
}
