'use client';

import { Trash2, Search, RefreshCw, Plus, MoreHorizontal, Eye, AlertCircle, Loader2, ChevronDown } from 'lucide-react';
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
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { ConfirmModal } from '@/components/ui/modal';
;
import {
  useErasureStatus,
  useRequestFullErasure,
  useRequestPersonalDataErasure,
  useRequestTransactionalErasure,
} from '@/hooks/security-lgpd';
import { ErasureRequestModal } from '@/components/seguranca/erasure-request-modal';

interface ErasureItem {
  id: string;
  holder_name: string;
  erasure_type: 'full' | 'personal' | 'transactional';
  status: 'pending' | 'processing' | 'completed' | 'failed';
  requested_at: string;
  completed_at?: string;
}

const typeLabels: Record<string, string> = {
  full: 'Completo',
  personal: 'Dados Pessoais',
  transactional: 'Transacional',
};

const typeVariants: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  full: 'destructive',
  personal: 'default',
  transactional: 'secondary',
};

const statusLabels: Record<string, string> = {
  pending: 'Pendente',
  processing: 'Processando',
  completed: 'Concluida',
  failed: 'Falhou',
};

const statusVariants: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  pending: 'secondary',
  processing: 'default',
  completed: 'outline',
  failed: 'destructive',
};

export default function EsquecimentoPage() {
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [formModalOpen, setFormModalOpen] = useState(false);
  const [erasureType, setErasureType] = useState<'full' | 'personal' | 'transactional'>('full');
  const [selectedItem, setSelectedItem] = useState<ErasureItem | null>(null);
  const [confirmModalOpen, setConfirmModalOpen] = useState(false);

  // Buscar lista de solicitações (usa ID vazio com enabled=false para lista)
  const { data: erasureData, isLoading, refetch } = useErasureStatus('', false);
  const requestFull = useRequestFullErasure();
  const requestPersonal = useRequestPersonalDataErasure();
  const requestTransactional = useRequestTransactionalErasure();

  const items: ErasureItem[] =
    (erasureData as any)?.data?.items || (erasureData as any)?.items || [];

  const filteredItems = items.filter((item) => {
    const matchesSearch =
      !search ||
      item.holder_name.toLowerCase().includes(search.toLowerCase());
    const matchesStatus = statusFilter === 'all' || item.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  const total = items.length;
  const pending = items.filter((i) => i.status === 'pending' || i.status === 'processing').length;
  const completed = items.filter((i) => i.status === 'completed').length;

  const handleOpenForm = (type: 'full' | 'personal' | 'transactional') => {
    setErasureType(type);
    setFormModalOpen(true);
  };

  const handleSubmitErasure = async (formData: {
    holder_name: string;
    holder_email: string;
    reason: string;
  }) => {
    const params = {
      titularId: formData.holder_name,
      titularEmail: formData.holder_email,
      reason: formData.reason,
    };

    if (erasureType === 'full') {
      await requestFull.mutateAsync(params);
    } else if (erasureType === 'personal') {
      await requestPersonal.mutateAsync(params);
    } else {
      await requestTransactional.mutateAsync(params);
    }

    setFormModalOpen(false);
    refetch();
  };

  const isMutating =
    requestFull.isPending ||
    requestPersonal.isPending ||
    requestTransactional.isPending;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <Trash2 className="h-6 w-6" />
            Direito ao Esquecimento
          </h1>
          <p className="text-muted-foreground">
            Gestão de solicitações de exclusão de dados (Art. 18 LGPD)
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Atualizar
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button>
                <Plus className="h-4 w-4 mr-2" />
                Nova Solicitação
                <ChevronDown className="h-4 w-4 ml-2" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => handleOpenForm('full')}>
                <Trash2 className="h-4 w-4 mr-2" />
                Exclusão Completa
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => handleOpenForm('personal')}>
                <AlertCircle className="h-4 w-4 mr-2" />
                Dados Pessoais
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => handleOpenForm('transactional')}>
                <Eye className="h-4 w-4 mr-2" />
                Transacional
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total</CardTitle>
            <Trash2 className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-blue-600">{total}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Pendentes</CardTitle>
            <AlertCircle className="h-4 w-4 text-amber-600" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-amber-600">{pending}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Concluidas</CardTitle>
            <Trash2 className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-green-600">{completed}</div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar por nome do titular..."
            className="pl-10"
          />
        </div>
        <Select value={statusFilter} onValueChange={setStatusFilter} aria-label="Status Filter">
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todos os Status</SelectItem>
            <SelectItem value="pending">Pendente</SelectItem>
            <SelectItem value="processing">Processando</SelectItem>
            <SelectItem value="completed">Concluida</SelectItem>
            <SelectItem value="failed">Falhou</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : filteredItems.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <Trash2 className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p className="font-medium">Nenhuma solicitação encontrada</p>
              <p className="text-sm mt-1">Crie uma nova solicitação de exclusão</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Titular</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Solicitado em</TableHead>
                  <TableHead>Concluido em</TableHead>
                  <TableHead className="w-[60px]">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredItems.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell className="font-medium">{item.holder_name}</TableCell>
                    <TableCell>
                      <Badge variant={typeVariants[item.erasure_type] || 'secondary'}>
                        {typeLabels[item.erasure_type] || item.erasure_type}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={statusVariants[item.status] || 'secondary'}>
                        {statusLabels[item.status] || item.status}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {item.requested_at
                        ? new Date(item.requested_at).toLocaleDateString('pt-BR')
                        : '-'}
                    </TableCell>
                    <TableCell>
                      {item.completed_at
                        ? new Date(item.completed_at).toLocaleDateString('pt-BR')
                        : '-'}
                    </TableCell>
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-8 w-8">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem
                            onClick={() => {
                              setSelectedItem(item);
                              setConfirmModalOpen(true);
                            }}
                          >
                            <Eye className="h-4 w-4 mr-2" />
                            Detalhes
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
      <ErasureRequestModal
        isOpen={formModalOpen}
        onClose={() => setFormModalOpen(false)}
        onSubmit={handleSubmitErasure}
        isLoading={isMutating}
        erasureType={erasureType}
      />

      {selectedItem && (
        <ConfirmModal
          isOpen={confirmModalOpen}
          onClose={() => {
            setConfirmModalOpen(false);
            setSelectedItem(null);
          }}
          onConfirm={() => {
            setConfirmModalOpen(false);
            setSelectedItem(null);
          }}
          title={`Solicitação: ${selectedItem.holder_name}`}
          message={`Tipo: ${typeLabels[selectedItem.erasure_type] || selectedItem.erasure_type}\nStatus: ${statusLabels[selectedItem.status] || selectedItem.status}\nSolicitado em: ${selectedItem.requested_at ? new Date(selectedItem.requested_at).toLocaleDateString('pt-BR') : '-'}\nConcluido em: ${selectedItem.completed_at ? new Date(selectedItem.completed_at).toLocaleDateString('pt-BR') : '-'}`}
          confirmText="Fechar"
          variant="info"
        />
      )}
    </div>
  );
}
