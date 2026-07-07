'use client';

import {
  FileText,
  Search,
  RefreshCw,
  Plus,
  MoreHorizontal,
  Eye,
  Edit,
  Trash2,
  AlertCircle,
  DollarSign,
  Clock,
  FileSignature,
  TrendingUp,
} from 'lucide-react';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
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
  useListarContratos,
  useListarContratosVigentes,
  useListarContratosVencendo,
  useCriarContrato,
  useAtualizarContrato,
  useRemoverContrato,
  useAditivar,
} from '@/hooks/bidding/useContracts';
import { ContractFormModal } from '@/components/licitacoes/ContractFormModal';
import { ContractAddendumModal } from '@/components/licitacoes/ContractAddendumModal';
import { ContractStatusBadge } from '@/components/licitacoes/ContractStatusBadge';
import { formatCurrency, formatDate } from '@/lib/utils';

export default function ContratosPage() {
  const router = useRouter();
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [page, setPage] = useState(0);
  const pageSize = 20;

  const { data: contratosData, isLoading, error, refetch } = useListarContratos({
    status: statusFilter !== 'all' ? statusFilter : undefined,
    page,
    size: pageSize,
  });

  const { data: vigentesData } = useListarContratosVigentes();
  const { data: vencendoData } = useListarContratosVencendo({ dias: 60 });

  const criarMutation = useCriarContrato();
  const atualizarMutation = useAtualizarContrato();
  const removerMutation = useRemoverContrato();
  const aditivarMutation = useAditivar();

  const [formOpen, setFormOpen] = useState(false);
  const [editItem, setEditItem] = useState<any | null>(null);
  const [addendumOpen, setAddendumOpen] = useState(false);
  const [selectedContractId, setSelectedContractId] = useState<string>('');

  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmAction, setConfirmAction] = useState<{
    title: string;
    message: string;
    action: () => Promise<void>;
    variant: 'danger' | 'warning' | 'info';
  } | null>(null);

  const contratos = (contratosData as any)?.items || (Array.isArray(contratosData) ? contratosData : []);
  const total = (contratosData as any)?.total || contratos.length;

  const vigentesCount = (vigentesData as any)?.total || (Array.isArray(vigentesData) ? vigentesData.length : 0);
  const vencendoCount = (vencendoData as any)?.total || (Array.isArray(vencendoData) ? vencendoData.length : 0);
  const valorTotal = contratos.reduce((sum: number, c: any) => sum + (c.valor_total || 0), 0);

  const openConfirm = (
    title: string,
    message: string,
    action: () => Promise<void>,
    variant: 'danger' | 'warning' | 'info' = 'warning'
  ) => {
    setConfirmAction({ title, message, action, variant });
    setConfirmOpen(true);
  };

  const openEdit = (contrato: any) => {
    setEditItem(contrato);
    setFormOpen(true);
  };

  const openCreate = () => {
    setEditItem(null);
    setFormOpen(true);
  };

  const openAddendum = (contractId: string) => {
    setSelectedContractId(contractId);
    setAddendumOpen(true);
  };

  const handleFormSubmit = async (data: any) => {
    try {
      if (editItem) {
        await atualizarMutation.mutateAsync({ id: editItem.id, data });
      } else {
        await criarMutation.mutateAsync(data);
      }
      setFormOpen(false);
      setEditItem(null);
    } catch (err) {
      // Error handled by mutation
    }
  };

  const handleAddendumSubmit = async (data: any) => {
    try {
      await aditivarMutation.mutateAsync(data);
      setAddendumOpen(false);
      setSelectedContractId('');
    } catch (err) {
      // Error handled by mutation
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <FileSignature className="h-6 w-6" />
            Contratos Públicos
          </h1>
          <p className="text-muted-foreground">Gestão de contratos e aditivos</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => refetch()} disabled={isLoading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
            Atualizar
          </Button>
          <Button onClick={openCreate}>
            <Plus className="h-4 w-4 mr-2" />
            Novo Contrato
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
            <div className="font-data text-2xl font-semibold tabular-nums">{total}</div>
            <p className="text-xs text-muted-foreground">Contratos cadastrados</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Vigentes</CardTitle>
            <TrendingUp className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-green-600">{vigentesCount}</div>
            <p className="text-xs text-muted-foreground">Em execução</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Vencendo</CardTitle>
            <Clock className="h-4 w-4 text-yellow-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-yellow-600">{vencendoCount}</div>
            <p className="text-xs text-muted-foreground">Próximos 60 dias</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Valor Total</CardTitle>
            <DollarSign className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-blue-600">{formatCurrency(valorTotal)}</div>
            <p className="text-xs text-muted-foreground">Soma dos contratos</p>
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
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(0);
                }}
                placeholder="Buscar por número, órgão, objeto..."
                className="pl-10"
              />
            </div>
            <Select
              value={statusFilter}
              onValueChange={(v) => {
                setStatusFilter(v);
                setPage(0);
              }}
            >
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos os status</SelectItem>
                <SelectItem value="vigente">Vigente</SelectItem>
                <SelectItem value="vencendo">Vencendo</SelectItem>
                <SelectItem value="vencido">Vencido</SelectItem>
                <SelectItem value="suspenso">Suspenso</SelectItem>
                <SelectItem value="rescindido">Rescindido</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Error */}
      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-destructive" />
          <p className="text-sm text-destructive flex-1">Erro ao carregar contratos</p>
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
          ) : contratos.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <FileSignature className="h-16 w-16 mx-auto mb-4 opacity-50" />
              <h3 className="text-lg font-medium">Nenhum contrato encontrado</h3>
              <p className="mt-2">Crie um novo contrato para começar</p>
              <Button className="mt-4" onClick={openCreate}>
                <Plus className="h-4 w-4 mr-2" />
                Novo Contrato
              </Button>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Número</TableHead>
                  <TableHead>Órgão</TableHead>
                  <TableHead>Objeto</TableHead>
                  <TableHead>Valor</TableHead>
                  <TableHead>Vigência</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="w-[80px]">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {contratos.map((contrato: any) => (
                  <TableRow key={contrato.id}>
                    <TableCell>
                      <div className="font-medium">{contrato.numero_contrato}</div>
                    </TableCell>
                    <TableCell className="text-sm">
                      {contrato.orgao_contratante}
                    </TableCell>
                    <TableCell className="max-w-xs truncate text-sm">
                      {contrato.objeto}
                    </TableCell>
                    <TableCell className="text-sm font-medium">
                      {formatCurrency(contrato.valor_total || 0)}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {formatDate(contrato.data_inicio)} - {formatDate(contrato.data_fim)}
                    </TableCell>
                    <TableCell>
                      <ContractStatusBadge status={contrato.status || 'vigente'} />
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
                            onClick={() => router.push(`/modulos/licitacoes/contratos/${contrato.id}`)}
                          >
                            <Eye className="h-4 w-4 mr-2" />
                            Ver detalhes
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => openAddendum(contrato.id)}>
                            <FileSignature className="h-4 w-4 mr-2" />
                            Criar Aditivo
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => openEdit(contrato)}>
                            <Edit className="h-4 w-4 mr-2" />
                            Editar
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            className="text-destructive"
                            onClick={() =>
                              openConfirm(
                                'Deletar Contrato',
                                `Deletar "${contrato.numero_contrato}" permanentemente?`,
                                () => removerMutation.mutateAsync(contrato.id),
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
              Próximo
            </Button>
          </div>
        </div>
      )}

      {/* Modals */}
      <ContractFormModal
        isOpen={formOpen}
        onClose={() => {
          setFormOpen(false);
          setEditItem(null);
        }}
        onSubmit={handleFormSubmit}
        editData={editItem}
        isLoading={criarMutation.isPending || atualizarMutation.isPending}
      />

      <ContractAddendumModal
        isOpen={addendumOpen}
        onClose={() => {
          setAddendumOpen(false);
          setSelectedContractId('');
        }}
        onSubmit={handleAddendumSubmit}
        contractId={selectedContractId}
        isLoading={aditivarMutation.isPending}
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
          isLoading={removerMutation.isPending}
        />
      )}
    </div>
  );
}
