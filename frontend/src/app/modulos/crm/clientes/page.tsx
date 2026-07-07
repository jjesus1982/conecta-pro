'use client';

import { Building2, Search, RefreshCw, Plus, MoreHorizontal, Eye, Edit, Trash2, AlertCircle, Users, CheckCircle2, ExternalLink } from 'lucide-react';
import { useState } from 'react';
import Link from 'next/link';
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
import { ClienteFormModal } from '@/components/crm/cliente-form-modal';
import { ClienteDetailModal } from '@/components/crm/cliente-detail-modal';
import { useCRMClients } from '@/hooks/crm/useCRMClients';
import { useCreateClient, useUpdateClient, useDeleteClient } from '@/hooks/clients';
import { clientLabel } from '@/utils/crm/clientLabel';

export default function ClientesPage() {
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [page, setPage] = useState(0);
  const pageSize = 20;

  const { data: clientsData, isLoading, error, refetch } = useCRMClients();
  const createMutation = useCreateClient();
  const updateMutation = useUpdateClient();
  const deleteMutation = useDeleteClient();

  const [formOpen, setFormOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [editItem, setEditItem] = useState<any | null>(null);
  const [selectedItem, setSelectedItem] = useState<any | null>(null);

  // Confirm modal state
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmAction, setConfirmAction] = useState<{
    title: string;
    message: string;
    action: () => Promise<void>;
    variant: 'danger' | 'warning' | 'info';
  } | null>(null);

  // Handle both array and object responses from Orval hooks
  const allClients = Array.isArray(clientsData) ? clientsData : (clientsData as any)?.items || [];

  // Client-side filtering
  const filteredClients = allClients.filter((client: any) => {
    const nome = clientLabel(client).toLowerCase();
    const matchesSearch = !search ||
      nome.includes(search.toLowerCase()) ||
      (client.cnpj || '').includes(search) ||
      (client.email || '').toLowerCase().includes(search.toLowerCase());
    const matchesStatus = statusFilter === 'all' || client.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  const total = filteredClients.length;
  const clients = filteredClients.slice(page * pageSize, (page + 1) * pageSize);

  const stats = {
    total: allClients.length,
    ativos: allClients.filter((c: any) => ['active', 'ativo'].includes(c.status)).length,
    condominios: allClients.filter((c: any) => {
      const name = (c.name || c.nome || '').toLowerCase();
      return c.client_type === 'condominium' || c.client_type === 'condominio' ||
        name.includes('condominio') || name.includes('condomínio') ||
        (name.includes('residencial') && c.crm_origin !== 'direto');
    }).length,
    bloqueados: allClients.filter((c: any) => ['blocked', 'bloqueado'].includes(c.status)).length,
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
    if (!editItem) return;
    await updateMutation.mutateAsync({ clientId: editItem.id, data });
    setFormOpen(false);
    setEditItem(null);
  };

  const getStatusBadge = (status: string) => {
    const map: Record<string, string> = {
      active: 'bg-green-100 text-green-800', ativo: 'bg-green-100 text-green-800',
      suspended: 'bg-yellow-100 text-yellow-800', suspenso: 'bg-yellow-100 text-yellow-800',
      blocked: 'bg-red-100 text-red-800', bloqueado: 'bg-red-100 text-red-800',
      inactive: 'bg-gray-100 text-gray-800', inativo: 'bg-gray-100 text-gray-800',
      inadimplente: 'bg-orange-100 text-orange-800',
      prospect: 'bg-cyan-100 text-cyan-800',
    };
    const labels: Record<string, string> = {
      active: 'Ativo', ativo: 'Ativo',
      suspended: 'Suspenso', suspenso: 'Suspenso',
      blocked: 'Bloqueado', bloqueado: 'Bloqueado',
      inactive: 'Inativo', inativo: 'Inativo',
      inadimplente: 'Inadimplente',
      prospect: 'Prospecto',
    };
    return <Badge className={map[status] || 'bg-gray-100 text-gray-800'}>{labels[status] || status || '-'}</Badge>;
  };

  const getSegmentoBadge = (segment: string) => {
    const map: Record<string, string> = {
      residencial: 'bg-teal-100 text-teal-800',
      comercial: 'bg-amber-100 text-amber-800',
      industrial: 'bg-blue-100 text-blue-800',
      publico: 'bg-purple-100 text-purple-800',
      misto: 'bg-indigo-100 text-indigo-800',
      small: 'bg-sky-100 text-sky-800',
      medium: 'bg-cyan-100 text-cyan-800',
      large: 'bg-blue-100 text-blue-800',
      enterprise: 'bg-indigo-100 text-indigo-800',
    };
    const labels: Record<string, string> = {
      residencial: 'Residencial',
      comercial: 'Comercial',
      industrial: 'Industrial',
      publico: 'Público',
      misto: 'Misto',
      small: 'Pequeno Porte',
      medium: 'Médio Porte',
      large: 'Grande Porte',
      enterprise: 'Enterprise',
    };
    return <Badge className={map[segment] || 'bg-gray-100 text-gray-800'}>{labels[segment] || segment || '-'}</Badge>;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <Building2 className="h-6 w-6" />
            Clientes
          </h1>
          <p className="text-muted-foreground">Gestao de clientes e condominios</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => refetch()} disabled={isLoading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
            Atualizar
          </Button>
          <Button onClick={() => { setEditItem(null); setFormOpen(true); }}>
            <Plus className="h-4 w-4 mr-2" />
            Novo Cliente
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Clientes</CardTitle>
            <Building2 className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums">{stats.total}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Ativos</CardTitle>
            <CheckCircle2 className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-green-600">{stats.ativos}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Condominios</CardTitle>
            <Users className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-blue-600">{stats.condominios}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Bloqueados</CardTitle>
            <AlertCircle className="h-4 w-4 text-red-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-red-600">{stats.bloqueados}</div>
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
                placeholder="Buscar por nome, CNPJ, email..."
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
                <SelectItem value="suspended">Suspenso</SelectItem>
                <SelectItem value="blocked">Bloqueado</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Error */}
      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-destructive" />
          <p className="text-sm text-destructive flex-1">Erro ao carregar clientes</p>
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
          ) : clients.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <Building2 className="h-16 w-16 mx-auto mb-4 opacity-50" />
              <h3 className="text-lg font-medium">Nenhum cliente encontrado</h3>
              <p className="mt-2">Tente ajustar os filtros ou cadastre um novo cliente</p>
              <Button className="mt-4" onClick={() => { setEditItem(null); setFormOpen(true); }}>
                <Plus className="h-4 w-4 mr-2" />
                Novo Cliente
              </Button>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nome</TableHead>
                  <TableHead>CNPJ</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead>Segmento</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="w-[80px]">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {clients.map((client: any) => (
                  <TableRow key={client.id}>
                    <TableCell>
                      <Link
                        href={`/modulos/crm/clientes/${client.id}`}
                        className="font-medium text-primary hover:underline"
                      >
                        {clientLabel(client)}
                      </Link>
                    </TableCell>
                    <TableCell className="text-sm">{client.cnpj || '-'}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">{client.email || '-'}</TableCell>
                    <TableCell>{getSegmentoBadge(client.segment)}</TableCell>
                    <TableCell>{getStatusBadge(client.status)}</TableCell>
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-8 w-8">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => { setSelectedItem(client); setDetailOpen(true); }}>
                            <Eye className="h-4 w-4 mr-2" />
                            Ver detalhes
                          </DropdownMenuItem>
                          <DropdownMenuItem asChild>
                            <Link href={`/modulos/crm/clientes/${client.id}`}>
                              <ExternalLink className="h-4 w-4 mr-2" />
                              Ver 360°
                            </Link>
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => { setEditItem(client); setFormOpen(true); }}>
                            <Edit className="h-4 w-4 mr-2" />
                            Editar
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            className="text-destructive"
                            onClick={() =>
                              openConfirm(
                                'Deletar Cliente',
                                `Deletar "${client.nome}" permanentemente?`,
                                () => deleteMutation.mutateAsync({ clientId: client.id }),
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
      <ClienteFormModal
        isOpen={formOpen}
        onClose={() => { setFormOpen(false); setEditItem(null); }}
        cliente={editItem}
        onSubmit={editItem ? handleUpdate : handleCreate}
        isLoading={createMutation.isPending || updateMutation.isPending}
      />

      <ClienteDetailModal
        isOpen={detailOpen}
        onClose={() => { setDetailOpen(false); setSelectedItem(null); }}
        cliente={selectedItem}
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
