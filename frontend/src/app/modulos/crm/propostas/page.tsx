'use client';

import { FileText, Search, RefreshCw, Plus, MoreHorizontal, Eye, Edit, Trash2, AlertCircle, DollarSign, Clock, CheckCircle, XCircle, Send, ThumbsUp } from 'lucide-react';
import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { customInstance } from '@/lib/api-client';
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
import { toast } from 'sonner';
import {
  useProposals,
  useProposalStats,
  useCreateProposal,
  useUpdateProposal,
  useDeleteProposal,
} from '@/hooks/crm';
import { formatCurrency, formatDate } from '@/lib/utils';

export default function PropostasPage() {
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [page, setPage] = useState(0);
  const pageSize = 20;

  const { data: proposalsData, isLoading, error, refetch } = useProposals({
    status: statusFilter !== 'all' ? statusFilter : undefined,
    search: search || undefined,
    skip: page * pageSize,
    limit: pageSize,
  } as any);

  const { data: statsData } = useProposalStats();

  const queryClient = useQueryClient();
  const createMutation = useCreateProposal();
  const updateMutation = useUpdateProposal();
  const deleteMutation = useDeleteProposal();

  const approveMutation = useMutation({
    mutationFn: (id: string) => customInstance({ url: `/api/v1/crm/proposals/${id}/approve`, method: 'POST', data: { action: 'approve' } }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['proposals'] }); toast.success('Proposta aprovada'); },
    onError: () => { toast.error('Erro ao aprovar proposta'); },
  });

  const rejectMutation = useMutation({
    mutationFn: ({ id, comments }: { id: string; comments?: string }) => customInstance({ url: `/api/v1/crm/proposals/${id}/approve`, method: 'POST', data: { action: 'reject', comments: comments || '' } }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['proposals'] }); toast.success('Proposta rejeitada'); },
    onError: () => { toast.error('Erro ao rejeitar proposta'); },
  });

  const sendMutation = useMutation({
    mutationFn: (id: string) => customInstance({ url: `/api/v1/crm/proposals/${id}/send`, method: 'POST' }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['proposals'] }); toast.success('Proposta enviada ao cliente'); },
    onError: () => { toast.error('Erro ao enviar proposta'); },
  });

  const acceptMutation = useMutation({
    mutationFn: (id: string) => customInstance({ url: `/api/v1/crm/proposals/${id}/approve`, method: 'POST', data: { action: 'approve' } }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['proposals'] }); toast.success('Proposta aceita pelo cliente'); },
    onError: () => { toast.error('Erro ao aceitar proposta'); },
  });

  const [formOpen, setFormOpen] = useState(false);
  const [editItem, setEditItem] = useState<any | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [selectedItem, setSelectedItem] = useState<any | null>(null);

  // Confirm modal
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmAction, setConfirmAction] = useState<{
    title: string;
    message: string;
    action: () => Promise<void>;
    variant: 'danger' | 'warning' | 'info';
  } | null>(null);

  // Form state
  const [formData, setFormData] = useState({
    title: '',
    client_name: '',
    client_email: '',
    total_value: 0,
    status: 'draft',
  });

  const propostas = (proposalsData as any)?.items || (Array.isArray(proposalsData) ? proposalsData : []);
  const total = (proposalsData as any)?.total || propostas.length;

  const pStats = statsData as any;
  const stats = {
    total: pStats?.proposals_total || total,
    rascunho: pStats?.proposals_pending || propostas.filter((p: any) => (p.status === 'draft' || p.status === 'rascunho')).length,
    enviadas: pStats?.proposals_sent || propostas.filter((p: any) => (p.status === 'sent' || p.status === 'enviada')).length,
    aprovadas: pStats?.proposals_accepted || propostas.filter((p: any) => (p.status === 'accepted' || p.status === 'aprovada')).length,
  };

  const resetForm = () => {
    setFormData({ title: '', client_name: '', client_email: '', total_value: 0, status: 'draft' });
  };

  const handleCreate = async () => {
    if (!formData.title.trim()) {
      toast.error('Titulo e obrigatorio');
      return;
    }
    try {
      await createMutation.mutateAsync({ data: { ...formData, client_email: formData.client_email.trim() || null } as any });
      resetForm();
      setFormOpen(false);
      toast.success('Proposta criada com sucesso');
    } catch {
      toast.error('Erro ao criar proposta');
    }
  };

  const handleUpdate = async () => {
    if (!editItem) return;
    try {
      await updateMutation.mutateAsync({ proposalId: editItem.id, data: { ...formData, client_email: formData.client_email.trim() || null } as any });
      resetForm();
      setEditItem(null);
      setFormOpen(false);
      toast.success('Proposta atualizada com sucesso');
    } catch {
      toast.error('Erro ao atualizar proposta');
    }
  };

  const openConfirm = (title: string, message: string, action: () => Promise<void>, variant: 'danger' | 'warning' | 'info' = 'warning') => {
    setConfirmAction({ title, message, action, variant });
    setConfirmOpen(true);
  };

  const openEdit = (proposta: any) => {
    setEditItem(proposta);
    setFormData({
      title: proposta.title || proposta.titulo || '',
      client_name: proposta.client_name || proposta.cliente || '',
      client_email: proposta.client_email || '',
      total_value: proposta.total_value || proposta.valor || 0,
      status: proposta.status || 'draft',
    });
    setFormOpen(true);
  };

  const openCreate = () => {
    setEditItem(null);
    resetForm();
    setFormOpen(true);
  };

  const getStatusBadge = (status: string) => {
    const map: Record<string, string> = {
      draft: 'bg-gray-100 text-gray-800',
      rascunho: 'bg-gray-100 text-gray-800',
      pending_approval: 'bg-yellow-100 text-yellow-800',
      approved: 'bg-emerald-100 text-emerald-800',
      sent: 'bg-blue-100 text-blue-800',
      enviada: 'bg-blue-100 text-blue-800',
      accepted: 'bg-green-100 text-green-800',
      aprovada: 'bg-green-100 text-green-800',
      rejected: 'bg-red-100 text-red-800',
      rejeitada: 'bg-red-100 text-red-800',
    };
    const labels: Record<string, string> = {
      draft: 'Rascunho',
      rascunho: 'Rascunho',
      pending_approval: 'Aguardando Aprovacao',
      approved: 'Aprovada',
      sent: 'Enviada',
      enviada: 'Enviada',
      accepted: 'Aprovada',
      aprovada: 'Aprovada',
      rejected: 'Rejeitada',
      rejeitada: 'Rejeitada',
    };
    return <Badge className={map[status] || 'bg-gray-100 text-gray-800'}>{labels[status] || status}</Badge>;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <FileText className="h-6 w-6" />
            Propostas
          </h1>
          <p className="text-muted-foreground">Gestao de propostas comerciais</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => refetch()} disabled={isLoading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
            Atualizar
          </Button>
          <Button onClick={openCreate}>
            <Plus className="h-4 w-4 mr-2" />
            Nova Proposta
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total</CardTitle>
            <FileText className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.total}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Rascunho</CardTitle>
            <Clock className="h-4 w-4 text-gray-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-gray-600">{stats.rascunho}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Enviadas</CardTitle>
            <FileText className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-blue-600">{stats.enviadas}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Aprovadas</CardTitle>
            <DollarSign className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-600">{stats.aprovadas}</div>
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
                placeholder="Buscar por titulo, cliente..."
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
                <SelectItem value="pending_approval">Aguardando Aprovacao</SelectItem>
                <SelectItem value="approved">Aprovada Internamente</SelectItem>
                <SelectItem value="sent">Enviada</SelectItem>
                <SelectItem value="accepted">Aceita</SelectItem>
                <SelectItem value="rejected">Rejeitada</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Error */}
      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-destructive" />
          <p className="text-sm text-destructive flex-1">Erro ao carregar propostas</p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Tentar novamente
          </Button>
        </div>
      )}

      {/* Inline Form */}
      {formOpen && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">{editItem ? 'Editar Proposta' : 'Nova Proposta'}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="grid gap-2">
                  <label className="text-sm font-medium">Titulo</label>
                  <Input
                    value={formData.title}
                    onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                    placeholder="Titulo da proposta"
                  />
                </div>
                <div className="grid gap-2">
                  <label className="text-sm font-medium">Cliente</label>
                  <Input
                    value={formData.client_name}
                    onChange={(e) => setFormData({ ...formData, client_name: e.target.value })}
                    placeholder="Nome do cliente"
                  />
                </div>
              </div>
              <div className="grid gap-2">
                <label className="text-sm font-medium">E-mail do cliente (opcional)</label>
                <Input
                  type="email"
                  value={formData.client_email}
                  onChange={(e) => setFormData({ ...formData, client_email: e.target.value })}
                  placeholder="email@cliente.com (opcional)"
                />
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="grid gap-2">
                  <label className="text-sm font-medium">Valor (R$)</label>
                  <Input
                    type="number"
                    value={formData.total_value}
                    onChange={(e) => setFormData({ ...formData, total_value: Number(e.target.value) })}
                    placeholder="0,00"
                  />
                </div>
                <div className="grid gap-2">
                  <label className="text-sm font-medium">Status</label>
                  <Select value={formData.status} onValueChange={(v) => setFormData({ ...formData, status: v })}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="draft">Rascunho</SelectItem>
                      <SelectItem value="sent">Enviada</SelectItem>
                      <SelectItem value="accepted">Aprovada</SelectItem>
                      <SelectItem value="rejected">Rejeitada</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={() => { setFormOpen(false); setEditItem(null); resetForm(); }}>
                  Cancelar
                </Button>
                <Button
                  onClick={editItem ? handleUpdate : handleCreate}
                  disabled={createMutation.isPending || updateMutation.isPending}
                >
                  {(createMutation.isPending || updateMutation.isPending) && (
                    <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                  )}
                  {editItem ? 'Salvar' : 'Criar Proposta'}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
            </div>
          ) : propostas.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <FileText className="h-16 w-16 mx-auto mb-4 opacity-50" />
              <h3 className="text-lg font-medium">Nenhuma proposta encontrada</h3>
              <p className="mt-2">Crie uma nova proposta para comecar</p>
              <Button className="mt-4" onClick={openCreate}>
                <Plus className="h-4 w-4 mr-2" />
                Nova Proposta
              </Button>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Titulo</TableHead>
                  <TableHead>Cliente</TableHead>
                  <TableHead>Valor</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Data</TableHead>
                  <TableHead className="w-[80px]">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {propostas.map((proposta: any) => (
                  <TableRow key={proposta.id}>
                    <TableCell>
                      <div className="font-medium">{proposta.title || proposta.titulo || '-'}</div>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {proposta.client_name || proposta.cliente || '-'}
                    </TableCell>
                    <TableCell className="text-sm font-medium">
                      {formatCurrency(proposta.total_value || proposta.valor || 0)}
                    </TableCell>
                    <TableCell>{getStatusBadge(proposta.status)}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {formatDate(proposta.created_at || proposta.data)}
                    </TableCell>
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-8 w-8">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => { setSelectedItem(proposta); setDetailOpen(true); }}>
                            <Eye className="h-4 w-4 mr-2" />
                            Ver detalhes
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => openEdit(proposta)}>
                            <Edit className="h-4 w-4 mr-2" />
                            Editar
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          {proposta.status === 'pending_approval' && (
                            <>
                              <DropdownMenuItem
                                className="text-green-600"
                                onClick={() => approveMutation.mutate(proposta.id)}
                                disabled={approveMutation.isPending}
                              >
                                <CheckCircle className="h-4 w-4 mr-2" />
                                Aprovar
                              </DropdownMenuItem>
                              <DropdownMenuItem
                                className="text-red-600"
                                onClick={() =>
                                  openConfirm(
                                    'Rejeitar Proposta',
                                    `Rejeitar "${proposta.title || proposta.titulo}"?`,
                                    async () => { await rejectMutation.mutateAsync({ id: proposta.id }); },
                                    'warning'
                                  )
                                }
                              >
                                <XCircle className="h-4 w-4 mr-2" />
                                Rejeitar
                              </DropdownMenuItem>
                              <DropdownMenuSeparator />
                            </>
                          )}
                          {proposta.status === 'approved' && (
                            <>
                              <DropdownMenuItem
                                className="text-blue-600"
                                onClick={() => sendMutation.mutate(proposta.id)}
                                disabled={sendMutation.isPending}
                              >
                                <Send className="h-4 w-4 mr-2" />
                                Enviar ao Cliente
                              </DropdownMenuItem>
                              <DropdownMenuSeparator />
                            </>
                          )}
                          {proposta.status === 'sent' && (
                            <>
                              <DropdownMenuItem
                                className="text-green-600"
                                onClick={() => acceptMutation.mutate(proposta.id)}
                                disabled={acceptMutation.isPending}
                              >
                                <ThumbsUp className="h-4 w-4 mr-2" />
                                Aceitar
                              </DropdownMenuItem>
                              <DropdownMenuSeparator />
                            </>
                          )}
                          <DropdownMenuItem
                            className="text-destructive"
                            onClick={() =>
                              openConfirm(
                                'Deletar Proposta',
                                `Deletar "${proposta.title || proposta.titulo}" permanentemente?`,
                                () => deleteMutation.mutateAsync({ proposalId: proposta.id }),
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

      {/* Detail View */}
      {detailOpen && selectedItem && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-lg">Detalhes da Proposta</CardTitle>
            <Button variant="outline" size="sm" onClick={() => { setDetailOpen(false); setSelectedItem(null); }}>
              Fechar
            </Button>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-muted-foreground">Titulo</p>
                <p className="font-medium">{selectedItem.title || selectedItem.titulo || '-'}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Cliente</p>
                <p className="font-medium">{selectedItem.client_name || selectedItem.cliente || '-'}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Valor</p>
                <p className="font-medium">{formatCurrency(selectedItem.total_value || selectedItem.valor || 0)}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Status</p>
                {getStatusBadge(selectedItem.status)}
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Data</p>
                <p className="font-medium">{formatDate(selectedItem.created_at || selectedItem.data)}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Confirm Modal */}
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
