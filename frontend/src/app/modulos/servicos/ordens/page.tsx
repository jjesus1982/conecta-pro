'use client';

import { ClipboardList, Search, RefreshCw, Plus, MoreHorizontal, AlertCircle, Eye, Edit, Play, CheckCircle, XCircle, Trash2 } from 'lucide-react';
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
import { toast } from 'sonner';
import { OrdemFormModal } from '@/components/servicos/ordem-form-modal';
import { OrdemDetailModal } from '@/components/servicos/ordem-detail-modal';

const prioridadeConfig: Record<string, { label: string; className: string }> = {
  baixa: { label: 'Baixa', className: 'bg-gray-100 text-gray-800' },
  media: { label: 'Media', className: 'bg-blue-100 text-blue-800' },
  alta: { label: 'Alta', className: 'bg-orange-100 text-orange-800' },
  urgente: { label: 'Urgente', className: 'bg-red-100 text-red-800' },
};

const statusConfig: Record<string, { label: string; className: string }> = {
  aberta: { label: 'Aberta', className: 'bg-blue-100 text-blue-800' },
  em_andamento: { label: 'Em Andamento', className: 'bg-yellow-100 text-yellow-800' },
  concluida: { label: 'Concluida', className: 'bg-green-100 text-green-800' },
  cancelada: { label: 'Cancelada', className: 'bg-red-100 text-red-800' },
};

function formatDate(dateStr: string): string {
  if (!dateStr) return '-';
  try {
    return new Date(dateStr).toLocaleDateString('pt-BR');
  } catch {
    return dateStr;
  }
}

export default function OrdensPage() {
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [prioridadeFilter, setPrioridadeFilter] = useState('all');
  const [ordens, setOrdens] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const [formOpen, setFormOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [editOrdem, setEditOrdem] = useState<any | null>(null);
  const [selectedOrdem, setSelectedOrdem] = useState<any | null>(null);

  // Confirm modal state
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmAction, setConfirmAction] = useState<{
    title: string;
    message: string;
    action: () => Promise<void>;
    variant: 'danger' | 'warning' | 'info';
  } | null>(null);

  // Filter ordens
  const filteredOrdens = ordens.filter((ordem) => {
    const matchSearch = !search ||
      ordem.titulo.toLowerCase().includes(search.toLowerCase()) ||
      ordem.cliente.toLowerCase().includes(search.toLowerCase());
    const matchStatus = statusFilter === 'all' || ordem.status === statusFilter;
    const matchPrioridade = prioridadeFilter === 'all' || ordem.prioridade === prioridadeFilter;
    return matchSearch && matchStatus && matchPrioridade;
  });

  const stats = {
    total: ordens.length,
    abertas: ordens.filter((o) => o.status === 'aberta').length,
    emAndamento: ordens.filter((o) => o.status === 'em_andamento').length,
    concluidas: ordens.filter((o) => o.status === 'concluida').length,
  };

  const openConfirm = (
    title: string,
    message: string,
    action: () => Promise<void>,
    variant: 'danger' | 'warning' | 'info' = 'warning'
  ) => {
    setConfirmAction({ title, message, action, variant });
    setConfirmOpen(true);
  };

  const handleCreate = async (data: any) => {
    const newOrdem = {
      ...data,
      id: crypto.randomUUID(),
      status: 'aberta',
      created_at: new Date().toISOString(),
    };
    setOrdens([newOrdem, ...ordens]);
    setFormOpen(false);
    toast.success('Ordem de servico criada com sucesso');
  };

  const handleUpdate = async (data: any) => {
    if (!editOrdem) return;
    setOrdens(ordens.map((o) => o.id === editOrdem.id ? { ...o, ...data, updated_at: new Date().toISOString() } : o));
    setFormOpen(false);
    setEditOrdem(null);
    toast.success('Ordem de servico atualizada com sucesso');
  };

  const handleChangeStatus = async (id: string, newStatus: string) => {
    setOrdens(ordens.map((o) => o.id === id ? { ...o, status: newStatus, updated_at: new Date().toISOString() } : o));
    const statusLabel = statusConfig[newStatus]?.label || newStatus;
    toast.success(`Status alterado para ${statusLabel}`);
  };

  const handleDelete = async (id: string) => {
    setOrdens(ordens.filter((o) => o.id !== id));
    toast.success('Ordem de servico removida');
  };

  const getStatusBadge = (status: string) => {
    const config = statusConfig[status] || { label: status, className: 'bg-gray-100 text-gray-800' };
    return <Badge className={config.className}>{config.label}</Badge>;
  };

  const getPrioridadeBadge = (prioridade: string) => {
    const config = prioridadeConfig[prioridade] || { label: prioridade, className: 'bg-gray-100 text-gray-800' };
    return <Badge className={config.className}>{config.label}</Badge>;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <ClipboardList className="h-6 w-6" />
            Ordens de Servico
          </h1>
          <p className="text-muted-foreground">Gestao de ordens de servico</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" disabled={isLoading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
            Atualizar
          </Button>
          <Button onClick={() => { setEditOrdem(null); setFormOpen(true); }}>
            <Plus className="h-4 w-4 mr-2" />
            Nova OS
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total</CardTitle>
            <ClipboardList className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums">{stats.total}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Abertas</CardTitle>
            <AlertCircle className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-blue-600">{stats.abertas}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Em Andamento</CardTitle>
            <Play className="h-4 w-4 text-yellow-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-yellow-600">{stats.emAndamento}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Concluidas</CardTitle>
            <CheckCircle className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-green-600">{stats.concluidas}</div>
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
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Buscar por titulo, cliente..."
                className="pl-10"
              />
            </div>
            <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v)}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos os status</SelectItem>
                <SelectItem value="aberta">Aberta</SelectItem>
                <SelectItem value="em_andamento">Em Andamento</SelectItem>
                <SelectItem value="concluida">Concluida</SelectItem>
                <SelectItem value="cancelada">Cancelada</SelectItem>
              </SelectContent>
            </Select>
            <Select value={prioridadeFilter} onValueChange={(v) => setPrioridadeFilter(v)}>
              <SelectTrigger className="w-[160px]">
                <SelectValue placeholder="Prioridade" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todas prioridades</SelectItem>
                <SelectItem value="baixa">Baixa</SelectItem>
                <SelectItem value="media">Media</SelectItem>
                <SelectItem value="alta">Alta</SelectItem>
                <SelectItem value="urgente">Urgente</SelectItem>
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
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
            </div>
          ) : filteredOrdens.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <ClipboardList className="h-16 w-16 mx-auto mb-4 opacity-50" />
              <h3 className="text-lg font-medium">Nenhuma ordem de servico encontrada</h3>
              <p className="mt-2">Tente ajustar os filtros ou crie uma nova ordem</p>
              <Button className="mt-4" onClick={() => { setEditOrdem(null); setFormOpen(true); }}>
                <Plus className="h-4 w-4 mr-2" />
                Nova OS
              </Button>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Titulo</TableHead>
                  <TableHead>Cliente</TableHead>
                  <TableHead>Prioridade</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Data</TableHead>
                  <TableHead className="w-[80px]">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredOrdens.map((ordem) => (
                  <TableRow key={ordem.id}>
                    <TableCell>
                      <div className="font-medium">{ordem.titulo}</div>
                    </TableCell>
                    <TableCell className="text-sm">{ordem.cliente || '-'}</TableCell>
                    <TableCell>{getPrioridadeBadge(ordem.prioridade)}</TableCell>
                    <TableCell>{getStatusBadge(ordem.status)}</TableCell>
                    <TableCell className="text-sm">{formatDate(ordem.data_prevista)}</TableCell>
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-8 w-8">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => { setSelectedOrdem(ordem); setDetailOpen(true); }}>
                            <Eye className="h-4 w-4 mr-2" />
                            Ver detalhes
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => { setEditOrdem(ordem); setFormOpen(true); }}>
                            <Edit className="h-4 w-4 mr-2" />
                            Editar
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          {ordem.status === 'aberta' && (
                            <DropdownMenuItem onClick={() =>
                              openConfirm(
                                'Iniciar OS',
                                `Deseja iniciar a OS "${ordem.titulo}"?`,
                                () => handleChangeStatus(ordem.id, 'em_andamento'),
                                'info'
                              )
                            }>
                              <Play className="h-4 w-4 mr-2" />
                              Iniciar
                            </DropdownMenuItem>
                          )}
                          {ordem.status === 'em_andamento' && (
                            <DropdownMenuItem onClick={() =>
                              openConfirm(
                                'Concluir OS',
                                `Deseja concluir a OS "${ordem.titulo}"?`,
                                () => handleChangeStatus(ordem.id, 'concluida'),
                                'info'
                              )
                            }>
                              <CheckCircle className="h-4 w-4 mr-2" />
                              Concluir
                            </DropdownMenuItem>
                          )}
                          {(ordem.status === 'aberta' || ordem.status === 'em_andamento') && (
                            <DropdownMenuItem onClick={() =>
                              openConfirm(
                                'Cancelar OS',
                                `Deseja cancelar a OS "${ordem.titulo}"?`,
                                () => handleChangeStatus(ordem.id, 'cancelada'),
                                'warning'
                              )
                            }>
                              <XCircle className="h-4 w-4 mr-2" />
                              Cancelar
                            </DropdownMenuItem>
                          )}
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            className="text-destructive"
                            onClick={() =>
                              openConfirm(
                                'Deletar OS',
                                `Deletar a OS "${ordem.titulo}" permanentemente?`,
                                () => handleDelete(ordem.id),
                                'danger'
                              )
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

      {/* Modals */}
      <OrdemFormModal
        isOpen={formOpen}
        onClose={() => { setFormOpen(false); setEditOrdem(null); }}
        ordem={editOrdem}
        onSubmit={editOrdem ? handleUpdate : handleCreate}
        isLoading={false}
      />

      <OrdemDetailModal
        isOpen={detailOpen}
        onClose={() => { setDetailOpen(false); setSelectedOrdem(null); }}
        ordem={selectedOrdem}
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
        />
      )}
    </div>
  );
}
