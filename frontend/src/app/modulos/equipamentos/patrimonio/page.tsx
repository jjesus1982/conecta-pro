'use client';

import { Package, Search, RefreshCw, Plus, MoreHorizontal, AlertCircle, Eye, Edit, Trash2, Box, MapPin, Wrench } from 'lucide-react';
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
  useEquipmentList,
  useEquipmentStats,
  useCreateEquipment,
  useUpdateEquipment,
  useDeleteEquipment,
} from '@/hooks/equipment';
import { EquipmentFormModal } from '@/components/equipamentos/equipment-form-modal';
import { EquipmentDetailModal } from '@/components/equipamentos/equipment-detail-modal';

export default function PatrimonioPage() {
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [typeFilter, setTypeFilter] = useState('all');
  const [page, setPage] = useState(0);
  const pageSize = 20;

  const { data: equipmentData, isLoading, error, refetch } = useEquipmentList({
    page: page + 1,
    page_size: pageSize,
    search: search || undefined,
    status: statusFilter !== 'all' ? statusFilter : undefined,
    equipment_type: typeFilter !== 'all' ? typeFilter : undefined,
  });

  const { data: statsData } = useEquipmentStats();

  const createMutation = useCreateEquipment();
  const updateMutation = useUpdateEquipment();
  const deleteMutation = useDeleteEquipment();

  const [formOpen, setFormOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [editEquipment, setEditEquipment] = useState<any | null>(null);
  const [selectedEquipment, setSelectedEquipment] = useState<any | null>(null);

  // Confirm modal state
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmAction, setConfirmAction] = useState<{
    title: string;
    message: string;
    action: () => Promise<void>;
    variant: 'danger' | 'warning' | 'info';
  } | null>(null);

  const equipments = equipmentData?.items || [];
  const total = equipmentData?.total || 0;

  const stats = {
    total: statsData?.total ?? total,
    em_estoque: statsData?.in_stock ?? 0,
    em_campo: statsData?.installed ?? 0,
    em_manutencao: statsData?.in_maintenance ?? 0,
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
    if (!editEquipment) return;
    await updateMutation.mutateAsync({ equipmentId: editEquipment.id, data });
    setFormOpen(false);
    setEditEquipment(null);
  };

  const getStatusBadge = (status: string) => {
    const map: Record<string, string> = {
      em_estoque: 'bg-blue-100 text-blue-800',
      em_campo: 'bg-green-100 text-green-800',
      em_manutencao: 'bg-yellow-100 text-yellow-800',
      inativo: 'bg-gray-100 text-gray-800',
    };
    const labels: Record<string, string> = {
      em_estoque: 'Em Estoque',
      em_campo: 'Em Campo',
      em_manutencao: 'Em Manutenção',
      inativo: 'Inativo',
    };
    return <Badge className={map[status] || ''}>{labels[status] || status}</Badge>;
  };

  const getTypeLabel = (type: string) => {
    const labels: Record<string, string> = {
      camera: 'Câmera',
      controle_acesso: 'Controle de Acesso',
      alarme: 'Alarme',
      radio: 'Rádio',
      sensor: 'Sensor',
      outro: 'Outro',
    };
    return labels[type] || type;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <Package className="h-6 w-6" />
            Patrimônio
          </h1>
          <p className="text-muted-foreground">Gestão de equipamentos e ativos</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => refetch()} disabled={isLoading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
            Atualizar
          </Button>
          <Button onClick={() => { setEditEquipment(null); setFormOpen(true); }}>
            <Plus className="h-4 w-4 mr-2" />
            Novo Equipamento
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total</CardTitle>
            <Package className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums">{stats.total}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Em Estoque</CardTitle>
            <Box className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-blue-600">{stats.em_estoque}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Em Campo</CardTitle>
            <MapPin className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-green-600">{stats.em_campo}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Em Manutenção</CardTitle>
            <Wrench className="h-4 w-4 text-yellow-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-yellow-600">{stats.em_manutencao}</div>
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
                placeholder="Buscar por nome, número de série, código..."
                className="pl-10"
              />
            </div>
            <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v); setPage(0); }}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos os status</SelectItem>
                <SelectItem value="em_estoque">Em Estoque</SelectItem>
                <SelectItem value="em_campo">Em Campo</SelectItem>
                <SelectItem value="em_manutencao">Em Manutenção</SelectItem>
                <SelectItem value="inativo">Inativo</SelectItem>
              </SelectContent>
            </Select>
            <Select value={typeFilter} onValueChange={(v) => { setTypeFilter(v); setPage(0); }}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Tipo" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos os tipos</SelectItem>
                <SelectItem value="camera">Câmera</SelectItem>
                <SelectItem value="controle_acesso">Controle de Acesso</SelectItem>
                <SelectItem value="alarme">Alarme</SelectItem>
                <SelectItem value="radio">Rádio</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Error */}
      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-destructive" />
          <p className="text-sm text-destructive flex-1">Erro ao carregar equipamentos</p>
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
          ) : equipments.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <Package className="h-16 w-16 mx-auto mb-4 opacity-50" />
              <h3 className="text-lg font-medium">Nenhum equipamento encontrado</h3>
              <p className="mt-2">Tente ajustar os filtros ou cadastre um novo equipamento</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nome</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead>N.Série</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Localização</TableHead>
                  <TableHead className="w-[80px]">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {equipments.map((equipment: any) => (
                  <TableRow key={equipment.id}>
                    <TableCell>
                      <div>
                        <div className="font-medium">{equipment.nome}</div>
                        <div className="text-xs text-muted-foreground font-mono">{equipment.codigo}</div>
                      </div>
                    </TableCell>
                    <TableCell className="text-sm">{getTypeLabel(equipment.equipment_type)}</TableCell>
                    <TableCell className="text-sm font-mono">{equipment.serial_number || '-'}</TableCell>
                    <TableCell>{getStatusBadge(equipment.status)}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">{equipment.location || '-'}</TableCell>
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-8 w-8">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => { setSelectedEquipment(equipment); setDetailOpen(true); }}>
                            <Eye className="h-4 w-4 mr-2" />
                            Ver detalhes
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => { setEditEquipment(equipment); setFormOpen(true); }}>
                            <Edit className="h-4 w-4 mr-2" />
                            Editar
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            className="text-destructive"
                            onClick={() =>
                              openConfirm('Deletar Equipamento', `Deletar "${equipment.nome}" permanentemente?`, () => deleteMutation.mutateAsync(equipment.id), 'danger')
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
              Próximo
            </Button>
          </div>
        </div>
      )}

      {/* Modals */}
      <EquipmentFormModal
        isOpen={formOpen}
        onClose={() => { setFormOpen(false); setEditEquipment(null); }}
        equipment={editEquipment}
        onSubmit={editEquipment ? handleUpdate : handleCreate}
        isLoading={createMutation.isPending || updateMutation.isPending}
      />

      <EquipmentDetailModal
        isOpen={detailOpen}
        onClose={() => { setDetailOpen(false); setSelectedEquipment(null); }}
        equipment={selectedEquipment}
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
          isLoading={deleteMutation.isPending}
        />
      )}
    </div>
  );
}
