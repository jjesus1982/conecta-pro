'use client';

import { Calendar, Search, RefreshCw, Plus, MoreHorizontal, AlertCircle, Eye, Edit, CheckCircle, XCircle, Trash2, Clock } from 'lucide-react';
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
import { AgendamentoFormModal } from '@/components/servicos/agendamento-form-modal';
import { AgendamentoDetailModal } from '@/components/servicos/agendamento-detail-modal';

const tipoConfig: Record<string, { label: string; className: string }> = {
  visita: { label: 'Visita', className: 'bg-blue-100 text-blue-800' },
  manutencao: { label: 'Manutencao', className: 'bg-orange-100 text-orange-800' },
  instalacao: { label: 'Instalacao', className: 'bg-purple-100 text-purple-800' },
  auditoria: { label: 'Auditoria', className: 'bg-cyan-100 text-cyan-800' },
};

const statusConfig: Record<string, { label: string; className: string }> = {
  agendado: { label: 'Agendado', className: 'bg-blue-100 text-blue-800' },
  confirmado: { label: 'Confirmado', className: 'bg-green-100 text-green-800' },
  em_andamento: { label: 'Em Andamento', className: 'bg-yellow-100 text-yellow-800' },
  concluido: { label: 'Concluido', className: 'bg-green-100 text-green-800' },
  cancelado: { label: 'Cancelado', className: 'bg-red-100 text-red-800' },
};

function formatDate(dateStr: string): string {
  if (!dateStr) return '-';
  try {
    return new Date(dateStr).toLocaleDateString('pt-BR');
  } catch {
    return dateStr;
  }
}

function isToday(dateStr: string): boolean {
  if (!dateStr) return false;
  try {
    const date = new Date(dateStr);
    const today = new Date();
    return (
      date.getFullYear() === today.getFullYear() &&
      date.getMonth() === today.getMonth() &&
      date.getDate() === today.getDate()
    );
  } catch {
    return false;
  }
}

function isNextWeek(dateStr: string): boolean {
  if (!dateStr) return false;
  try {
    const date = new Date(dateStr);
    const today = new Date();
    const nextWeek = new Date();
    nextWeek.setDate(today.getDate() + 7);
    return date >= today && date <= nextWeek;
  } catch {
    return false;
  }
}

export default function AgendamentosPage() {
  const [search, setSearch] = useState('');
  const [tipoFilter, setTipoFilter] = useState('all');
  const [agendamentos, setAgendamentos] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const [formOpen, setFormOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [editAgendamento, setEditAgendamento] = useState<any | null>(null);
  const [selectedAgendamento, setSelectedAgendamento] = useState<any | null>(null);

  // Confirm modal state
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmAction, setConfirmAction] = useState<{
    title: string;
    message: string;
    action: () => Promise<void>;
    variant: 'danger' | 'warning' | 'info';
  } | null>(null);

  // Filter agendamentos
  const filteredAgendamentos = agendamentos.filter((ag) => {
    const matchSearch = !search ||
      ag.titulo.toLowerCase().includes(search.toLowerCase()) ||
      (ag.responsavel && ag.responsavel.toLowerCase().includes(search.toLowerCase()));
    const matchTipo = tipoFilter === 'all' || ag.tipo === tipoFilter;
    return matchSearch && matchTipo;
  });

  const stats = {
    total: agendamentos.length,
    hoje: agendamentos.filter((ag) => isToday(ag.data)).length,
    proximaSemana: agendamentos.filter((ag) => isNextWeek(ag.data)).length,
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
    const newAgendamento = {
      ...data,
      id: crypto.randomUUID(),
      status: 'agendado',
      created_at: new Date().toISOString(),
    };
    setAgendamentos([newAgendamento, ...agendamentos]);
    setFormOpen(false);
    toast.success('Agendamento criado com sucesso');
  };

  const handleUpdate = async (data: any) => {
    if (!editAgendamento) return;
    setAgendamentos(agendamentos.map((ag) =>
      ag.id === editAgendamento.id ? { ...ag, ...data, updated_at: new Date().toISOString() } : ag
    ));
    setFormOpen(false);
    setEditAgendamento(null);
    toast.success('Agendamento atualizado com sucesso');
  };

  const handleChangeStatus = async (id: string, newStatus: string) => {
    setAgendamentos(agendamentos.map((ag) =>
      ag.id === id ? { ...ag, status: newStatus, updated_at: new Date().toISOString() } : ag
    ));
    const statusLabel = statusConfig[newStatus]?.label || newStatus;
    toast.success(`Status alterado para ${statusLabel}`);
  };

  const handleDelete = async (id: string) => {
    setAgendamentos(agendamentos.filter((ag) => ag.id !== id));
    toast.success('Agendamento removido');
  };

  const getStatusBadge = (status: string) => {
    const config = statusConfig[status] || { label: status, className: 'bg-gray-100 text-gray-800' };
    return <Badge className={config.className}>{config.label}</Badge>;
  };

  const getTipoBadge = (tipo: string) => {
    const config = tipoConfig[tipo] || { label: tipo, className: 'bg-gray-100 text-gray-800' };
    return <Badge className={config.className}>{config.label}</Badge>;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <Calendar className="h-6 w-6" />
            Agendamentos
          </h1>
          <p className="text-muted-foreground">Gestao de agendamentos de visitas e servicos</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" disabled={isLoading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
            Atualizar
          </Button>
          <Button onClick={() => { setEditAgendamento(null); setFormOpen(true); }}>
            <Plus className="h-4 w-4 mr-2" />
            Novo Agendamento
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total</CardTitle>
            <Calendar className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums">{stats.total}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Hoje</CardTitle>
            <Clock className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-blue-600">{stats.hoje}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Proxima Semana</CardTitle>
            <Calendar className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-green-600">{stats.proximaSemana}</div>
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
                placeholder="Buscar por titulo, responsavel..."
                className="pl-10"
              />
            </div>
            <Select value={tipoFilter} onValueChange={(v) => setTipoFilter(v)}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Tipo" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos os tipos</SelectItem>
                <SelectItem value="visita">Visita</SelectItem>
                <SelectItem value="manutencao">Manutencao</SelectItem>
                <SelectItem value="instalacao">Instalacao</SelectItem>
                <SelectItem value="auditoria">Auditoria</SelectItem>
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
          ) : filteredAgendamentos.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <Calendar className="h-16 w-16 mx-auto mb-4 opacity-50" />
              <h3 className="text-lg font-medium">Nenhum agendamento encontrado</h3>
              <p className="mt-2">Tente ajustar os filtros ou crie um novo agendamento</p>
              <Button className="mt-4" onClick={() => { setEditAgendamento(null); setFormOpen(true); }}>
                <Plus className="h-4 w-4 mr-2" />
                Novo Agendamento
              </Button>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Titulo</TableHead>
                  <TableHead>Data/Hora</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Responsavel</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="w-[80px]">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredAgendamentos.map((agendamento) => (
                  <TableRow key={agendamento.id}>
                    <TableCell>
                      <div className="font-medium">{agendamento.titulo}</div>
                    </TableCell>
                    <TableCell className="text-sm">
                      <div>{formatDate(agendamento.data)}</div>
                      <div className="text-xs text-muted-foreground">
                        {agendamento.hora_inicio || '--:--'} - {agendamento.hora_fim || '--:--'}
                      </div>
                    </TableCell>
                    <TableCell>{getTipoBadge(agendamento.tipo)}</TableCell>
                    <TableCell className="text-sm">{agendamento.responsavel || '-'}</TableCell>
                    <TableCell>{getStatusBadge(agendamento.status)}</TableCell>
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-8 w-8">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => { setSelectedAgendamento(agendamento); setDetailOpen(true); }}>
                            <Eye className="h-4 w-4 mr-2" />
                            Ver detalhes
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => { setEditAgendamento(agendamento); setFormOpen(true); }}>
                            <Edit className="h-4 w-4 mr-2" />
                            Editar
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          {agendamento.status === 'agendado' && (
                            <DropdownMenuItem onClick={() =>
                              openConfirm(
                                'Confirmar Agendamento',
                                `Deseja confirmar o agendamento "${agendamento.titulo}"?`,
                                () => handleChangeStatus(agendamento.id, 'confirmado'),
                                'info'
                              )
                            }>
                              <CheckCircle className="h-4 w-4 mr-2" />
                              Confirmar
                            </DropdownMenuItem>
                          )}
                          {agendamento.status === 'confirmado' && (
                            <DropdownMenuItem onClick={() =>
                              openConfirm(
                                'Concluir Agendamento',
                                `Deseja concluir o agendamento "${agendamento.titulo}"?`,
                                () => handleChangeStatus(agendamento.id, 'concluido'),
                                'info'
                              )
                            }>
                              <CheckCircle className="h-4 w-4 mr-2" />
                              Concluir
                            </DropdownMenuItem>
                          )}
                          {(agendamento.status === 'agendado' || agendamento.status === 'confirmado') && (
                            <DropdownMenuItem onClick={() =>
                              openConfirm(
                                'Cancelar Agendamento',
                                `Deseja cancelar o agendamento "${agendamento.titulo}"?`,
                                () => handleChangeStatus(agendamento.id, 'cancelado'),
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
                                'Deletar Agendamento',
                                `Deletar o agendamento "${agendamento.titulo}" permanentemente?`,
                                () => handleDelete(agendamento.id),
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
      <AgendamentoFormModal
        isOpen={formOpen}
        onClose={() => { setFormOpen(false); setEditAgendamento(null); }}
        agendamento={editAgendamento}
        onSubmit={editAgendamento ? handleUpdate : handleCreate}
        isLoading={false}
      />

      <AgendamentoDetailModal
        isOpen={detailOpen}
        onClose={() => { setDetailOpen(false); setSelectedAgendamento(null); }}
        agendamento={selectedAgendamento}
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
