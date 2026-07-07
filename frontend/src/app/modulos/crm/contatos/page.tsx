'use client';

import { Contact, Search, Plus, MoreHorizontal, Eye, Edit, Phone, Mail, AlertCircle, RefreshCw, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { toast } from 'sonner';
import { customInstance } from '@/lib/api-client';

interface ContatoAPI {
  id: string;
  nome: string;
  name?: string;
  email: string;
  telefone?: string;
  phone?: string;
  cargo?: string;
  role?: string;
  cliente?: string;
  client_name?: string;
  client_id?: string;
  ativo?: boolean;
  is_active?: boolean;
  created_at?: string;
}

export default function ContatosPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [selectedItem, setSelectedItem] = useState<ContatoAPI | null>(null);
  const [editItem, setEditItem] = useState<ContatoAPI | null>(null);

  // Form state
  const [formData, setFormData] = useState({
    nome: '',
    email: '',
    telefone: '',
    cargo: '',
    cliente: '',
  });

  // Fetch contacts from API
  const { data: contactsRaw, isLoading, error, refetch } = useQuery<any>({
    queryKey: ['crm-contacts'],
    queryFn: () => customInstance<any>({ url: '/api/v1/crm/contacts/', method: 'GET' }),
    staleTime: 30_000,
  });

  // Normalize response: handle array or {items: []} or {data: []}
  const contacts: ContatoAPI[] = Array.isArray(contactsRaw)
    ? contactsRaw
    : (contactsRaw as any)?.items || (contactsRaw as any)?.data || [];

  // Create contact mutation
  const createMutation = useMutation({
    mutationFn: (data: any) =>
      customInstance({ url: '/api/v1/crm/contacts/', method: 'POST', data }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['crm-contacts'] });
      toast.success('Contato criado com sucesso');
    },
    onError: () => {
      toast.error('Erro ao criar contato');
    },
  });

  // Update contact mutation
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: any }) =>
      customInstance({ url: `/api/v1/crm/contacts/${id}`, method: 'PUT', data }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['crm-contacts'] });
      toast.success('Contato atualizado com sucesso');
    },
    onError: () => {
      toast.error('Erro ao atualizar contato');
    },
  });

  // Delete contact mutation
  const deleteMutation = useMutation({
    mutationFn: (id: string) =>
      customInstance({ url: `/api/v1/crm/contacts/${id}`, method: 'DELETE' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['crm-contacts'] });
      toast.success('Contato removido com sucesso');
    },
    onError: () => {
      toast.error('Erro ao remover contato');
    },
  });

  // Normalize field access
  const getName = (c: ContatoAPI) => c.nome || c.name || '';
  const getPhone = (c: ContatoAPI) => c.telefone || c.phone || '';
  const getCargo = (c: ContatoAPI) => c.cargo || c.role || '';
  const getCliente = (c: ContatoAPI) => c.cliente || c.client_name || '';
  const isActive = (c: ContatoAPI) => c.ativo ?? c.is_active ?? true;

  const filteredContacts = contacts.filter((c) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      getName(c).toLowerCase().includes(q) ||
      (c.email || '').toLowerCase().includes(q) ||
      getPhone(c).includes(q) ||
      getCargo(c).toLowerCase().includes(q) ||
      getCliente(c).toLowerCase().includes(q)
    );
  });

  const stats = {
    total: contacts.length,
    ativos: contacts.filter((c) => isActive(c)).length,
  };

  const resetForm = () => {
    setFormData({ nome: '', email: '', telefone: '', cargo: '', cliente: '' });
  };

  const handleCreate = async () => {
    if (!formData.nome.trim()) {
      toast.error('Nome e obrigatorio');
      return;
    }
    await createMutation.mutateAsync(formData);
    resetForm();
    setFormOpen(false);
  };

  const handleUpdate = async () => {
    if (!editItem) return;
    await updateMutation.mutateAsync({ id: editItem.id, data: formData });
    resetForm();
    setEditItem(null);
    setFormOpen(false);
  };

  const handleDelete = async (id: string) => {
    await deleteMutation.mutateAsync(id);
  };

  const openEdit = (contact: ContatoAPI) => {
    setEditItem(contact);
    setFormData({
      nome: getName(contact),
      email: contact.email || '',
      telefone: getPhone(contact),
      cargo: getCargo(contact),
      cliente: getCliente(contact),
    });
    setFormOpen(true);
  };

  const openCreate = () => {
    setEditItem(null);
    resetForm();
    setFormOpen(true);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <Contact className="h-6 w-6" />
            Contatos
          </h1>
          <p className="text-muted-foreground">Gestao de contatos de clientes</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => refetch()} disabled={isLoading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
            Atualizar
          </Button>
          <Button onClick={openCreate}>
            <Plus className="h-4 w-4 mr-2" />
            Novo Contato
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Contatos</CardTitle>
            <Contact className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums">{stats.total}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Ativos</CardTitle>
            <Phone className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-green-600">{stats.ativos}</div>
          </CardContent>
        </Card>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-destructive" />
          <p className="text-sm text-destructive flex-1">Erro ao carregar contatos</p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Tentar novamente
          </Button>
        </div>
      )}

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-col md:flex-row gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Buscar por nome, email, telefone..."
                className="pl-10"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Inline Form */}
      {formOpen && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">{editItem ? 'Editar Contato' : 'Novo Contato'}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="grid gap-2">
                  <label className="text-sm font-medium">Nome</label>
                  <Input
                    value={formData.nome}
                    onChange={(e) => setFormData({ ...formData, nome: e.target.value })}
                    placeholder="Nome do contato"
                  />
                </div>
                <div className="grid gap-2">
                  <label className="text-sm font-medium">Email</label>
                  <Input
                    type="email"
                    value={formData.email}
                    onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                    placeholder="email@exemplo.com"
                  />
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="grid gap-2">
                  <label className="text-sm font-medium">Telefone</label>
                  <Input
                    value={formData.telefone}
                    onChange={(e) => setFormData({ ...formData, telefone: e.target.value })}
                    placeholder="(00) 00000-0000"
                  />
                </div>
                <div className="grid gap-2">
                  <label className="text-sm font-medium">Cargo</label>
                  <Input
                    value={formData.cargo}
                    onChange={(e) => setFormData({ ...formData, cargo: e.target.value })}
                    placeholder="Cargo do contato"
                  />
                </div>
                <div className="grid gap-2">
                  <label className="text-sm font-medium">Cliente</label>
                  <Input
                    value={formData.cliente}
                    onChange={(e) => setFormData({ ...formData, cliente: e.target.value })}
                    placeholder="Nome do cliente"
                  />
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
                  {editItem ? 'Salvar' : 'Criar Contato'}
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
          ) : filteredContacts.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <Contact className="h-16 w-16 mx-auto mb-4 opacity-50" />
              <h3 className="text-lg font-medium">Nenhum contato encontrado</h3>
              <p className="mt-2">Adicione um novo contato para comecar</p>
              <Button className="mt-4" onClick={openCreate}>
                <Plus className="h-4 w-4 mr-2" />
                Novo Contato
              </Button>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nome</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead>Telefone</TableHead>
                  <TableHead>Cargo</TableHead>
                  <TableHead>Cliente</TableHead>
                  <TableHead className="w-[80px]">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredContacts.map((contact) => (
                  <TableRow key={contact.id}>
                    <TableCell>
                      <div className="font-medium">{getName(contact)}</div>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1 text-sm text-muted-foreground">
                        <Mail className="h-3 w-3" />
                        {contact.email || '-'}
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1 text-sm text-muted-foreground">
                        <Phone className="h-3 w-3" />
                        {getPhone(contact) || '-'}
                      </div>
                    </TableCell>
                    <TableCell className="text-sm">{getCargo(contact) || '-'}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">{getCliente(contact) || '-'}</TableCell>
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-8 w-8">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => { setSelectedItem(contact); setDetailOpen(true); }}>
                            <Eye className="h-4 w-4 mr-2" />
                            Ver detalhes
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => openEdit(contact)}>
                            <Edit className="h-4 w-4 mr-2" />
                            Editar
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            className="text-destructive"
                            onClick={() => handleDelete(contact.id)}
                          >
                            <Trash2 className="h-4 w-4 mr-2" />
                            Remover
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

      {/* Detail View */}
      {detailOpen && selectedItem && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-lg">Detalhes do Contato</CardTitle>
            <Button variant="outline" size="sm" onClick={() => { setDetailOpen(false); setSelectedItem(null); }}>
              Fechar
            </Button>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-muted-foreground">Nome</p>
                <p className="font-medium">{getName(selectedItem)}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Email</p>
                <p className="font-medium">{selectedItem.email || '-'}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Telefone</p>
                <p className="font-medium">{getPhone(selectedItem) || '-'}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Cargo</p>
                <p className="font-medium">{getCargo(selectedItem) || '-'}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Cliente</p>
                <p className="font-medium">{getCliente(selectedItem) || '-'}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Status</p>
                <Badge className={isActive(selectedItem) ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'}>
                  {isActive(selectedItem) ? 'Ativo' : 'Inativo'}
                </Badge>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
