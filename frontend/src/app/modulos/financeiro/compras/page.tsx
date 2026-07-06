'use client';

import { ShoppingCart, Search, RefreshCw, Plus, MoreHorizontal, Eye, Edit, AlertCircle, ArrowLeft, FileText, ClipboardList } from 'lucide-react';
import { useState } from 'react';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import {
  usePurchaseRequisitions,
  usePurchaseOrders,
  usePurchaseDashboard,
  useCreatePurchaseRequisition,
  useCreatePurchaseOrder,
} from '@/hooks/financial/useFinancial';
import { PurchaseFormModal } from '@/components/financeiro/purchase-form-modal';
import { PurchaseDetailModal } from '@/components/financeiro/purchase-detail-modal';
import { useCondominio } from '@/contexts/CondominioContext';

type TabType = 'requisitions' | 'orders';

const formatCurrency = (value: number | undefined | null) => {
  if (value == null) return 'R$ 0,00';
  return value.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
};

const formatDate = (date: string | undefined | null) => {
  if (!date) return '-';
  return new Date(date).toLocaleDateString('pt-BR');
};

const getRequisitionStatusColor = (status: string) => {
  switch (status) {
    case 'pending':
      return 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20';
    case 'approved':
      return 'bg-green-500/10 text-green-500 border-green-500/20';
    case 'rejected':
      return 'bg-red-500/10 text-red-500 border-red-500/20';
    case 'in_progress':
      return 'bg-blue-500/10 text-blue-500 border-blue-500/20';
    case 'completed':
      return 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20';
    default:
      return 'bg-gray-500/10 text-gray-500 border-gray-500/20';
  }
};

const getOrderStatusColor = (status: string) => {
  switch (status) {
    case 'draft':
      return 'bg-gray-500/10 text-gray-500 border-gray-500/20';
    case 'sent':
      return 'bg-blue-500/10 text-blue-500 border-blue-500/20';
    case 'confirmed':
      return 'bg-green-500/10 text-green-500 border-green-500/20';
    case 'delivered':
      return 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20';
    case 'cancelled':
      return 'bg-red-500/10 text-red-500 border-red-500/20';
    default:
      return 'bg-gray-500/10 text-gray-500 border-gray-500/20';
  }
};

const STATUS_LABELS: Record<string, string> = {
  pending: 'Pendente',
  approved: 'Aprovada',
  rejected: 'Rejeitada',
  in_progress: 'Em Andamento',
  completed: 'Concluida',
  draft: 'Rascunho',
  sent: 'Enviada',
  confirmed: 'Confirmada',
  delivered: 'Entregue',
  cancelled: 'Cancelada',
};

export default function ComprasPage() {
  const { condominioId } = useCondominio();
  const [activeTab, setActiveTab] = useState<TabType>('requisitions');
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [showFormModal, setShowFormModal] = useState(false);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [selectedItem, setSelectedItem] = useState<any>(null);
  const [formType, setFormType] = useState<'requisition' | 'order'>('requisition');

  const { data: requisitionsRaw, isLoading: loadingRequisitions, refetch: refetchRequisitions } = usePurchaseRequisitions({ condominio_id: condominioId });
  const { data: ordersRaw, isLoading: loadingOrders, refetch: refetchOrders } = usePurchaseOrders({ condominio_id: condominioId });
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const requisitions: any[] = (requisitionsRaw as any)?.items ?? [];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const orders: any[] = (ordersRaw as any)?.items ?? [];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { data: dashboardRaw, isLoading: loadingDashboard } = usePurchaseDashboard({ condominio_id: condominioId });
  const dashboard = dashboardRaw as any;
  const createRequisition = useCreatePurchaseRequisition();
  const createOrder = useCreatePurchaseOrder();

  const isLoading = activeTab === 'requisitions' ? loadingRequisitions : loadingOrders;

  const handleRefresh = () => {
    if (activeTab === 'requisitions') {
      refetchRequisitions();
    } else {
      refetchOrders();
    }
  };

  const handleCreate = () => {
    setFormType(activeTab === 'requisitions' ? 'requisition' : 'order');
    setShowFormModal(true);
  };

  const handleView = (item: unknown) => {
    setSelectedItem(item);
    setShowDetailModal(true);
  };

  const handleFormSubmit = async (data: Record<string, unknown>) => {
    try {
      if (formType === 'requisition') {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        await createRequisition.mutateAsync({ data: data as any });
      } else {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        await createOrder.mutateAsync({ data: data as any });
      }
      setShowFormModal(false);
      // refetch() removido - mutation já invalida queries automaticamente
    } catch (error) {
      void error;
    }
  };

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const filteredRequisitions = requisitions.filter((item: any) => {
    const matchesSearch =
      !searchTerm ||
      item.number?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      item.title?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      item.description?.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesStatus = statusFilter === 'all' || item.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const filteredOrders = orders.filter((item: any) => {
    const matchesSearch =
      !searchTerm ||
      item.number?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      item.supplier_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      item.description?.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesStatus = statusFilter === 'all' || item.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  return (
    <div className="min-h-screen bg-grid">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-[hsl(var(--background))]/80 backdrop-blur-xl border-b border-[hsl(var(--border))]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-4">
              <Link href="/modulos/financeiro">
                <Button variant="ghost" size="sm">
                  <ArrowLeft className="w-4 h-4 mr-2" />
                  Financeiro
                </Button>
              </Link>
              <div className="flex items-center gap-2">
                <div className="w-10 h-10 rounded-lg bg-orange-500/10 flex items-center justify-center">
                  <ShoppingCart className="w-5 h-5 text-orange-500" />
                </div>
                <div>
                  <h1 className="text-lg font-semibold text-[hsl(var(--foreground))]">
                    Compras
                  </h1>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">
                    Requisicoes e ordens de compra
                  </p>
                </div>
              </div>
            </div>
            <Button variant="primary" size="sm" onClick={handleCreate}>
              <Plus className="w-4 h-4 mr-2" />
              {activeTab === 'requisitions' ? 'Nova Requisicao' : 'Nova Ordem'}
            </Button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Stats Cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-orange-500/10 flex items-center justify-center">
                <ClipboardList className="w-5 h-5 text-orange-500" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                  {dashboard?.total ?? 0}
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Total Requisicoes</p>
              </div>
            </div>
          </div>

          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
                <FileText className="w-5 h-5 text-blue-500" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                  {dashboard?.total_orders ?? 0}
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Total Ordens</p>
              </div>
            </div>
          </div>

          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-green-500/10 flex items-center justify-center">
                <ShoppingCart className="w-5 h-5 text-green-500" />
              </div>
              <div>
                <p className="font-data text-xl font-semibold tabular-nums text-green-500 truncate">
                  {formatCurrency(dashboard?.total_estimated ? parseFloat(dashboard.total_estimated) : undefined)}
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Valor Total</p>
              </div>
            </div>
          </div>

          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-yellow-500/10 flex items-center justify-center">
                <AlertCircle className="w-5 h-5 text-yellow-500" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-yellow-500">
                  {dashboard?.pending_approval ?? 0}
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Pendentes</p>
              </div>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex items-center gap-1 mb-6 bg-[hsl(var(--muted))] rounded-lg p-1 w-fit">
          <button
            onClick={() => { setActiveTab('requisitions'); setStatusFilter('all'); }}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              activeTab === 'requisitions'
                ? 'bg-[hsl(var(--card))] text-[hsl(var(--foreground))] shadow-sm'
                : 'text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))]'
            }`}
          >
            Requisicoes
          </button>
          <button
            onClick={() => { setActiveTab('orders'); setStatusFilter('all'); }}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              activeTab === 'orders'
                ? 'bg-[hsl(var(--card))] text-[hsl(var(--foreground))] shadow-sm'
                : 'text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))]'
            }`}
          >
            Ordens de Compra
          </button>
        </div>

        {/* Search and Filters */}
        <div className="flex flex-col sm:flex-row gap-4 mb-6">
          <div className="flex-1">
            <Input
              type="search"
              placeholder="Buscar por codigo, descricao ou fornecedor..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              icon={<Search className="w-4 h-4" />}
            />
          </div>
          <Select value={statusFilter} onValueChange={setStatusFilter} aria-label="Status Filter">
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos</SelectItem>
              {activeTab === 'requisitions' ? (
                <>
                  <SelectItem value="pending">Pendente</SelectItem>
                  <SelectItem value="approved">Aprovada</SelectItem>
                  <SelectItem value="rejected">Rejeitada</SelectItem>
                  <SelectItem value="in_progress">Em Andamento</SelectItem>
                  <SelectItem value="completed">Concluida</SelectItem>
                </>
              ) : (
                <>
                  <SelectItem value="draft">Rascunho</SelectItem>
                  <SelectItem value="sent">Enviada</SelectItem>
                  <SelectItem value="confirmed">Confirmada</SelectItem>
                  <SelectItem value="delivered">Entregue</SelectItem>
                  <SelectItem value="cancelled">Cancelada</SelectItem>
                </>
              )}
            </SelectContent>
          </Select>
          <Button variant="outline" onClick={handleRefresh} disabled={isLoading}>
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          </Button>
        </div>

        {/* Loading state */}
        {isLoading && (
          <div className="flex items-center justify-center py-12">
            <div className="animate-pulse-slow text-[hsl(var(--primary))]">
              <ShoppingCart className="w-8 h-8" />
            </div>
          </div>
        )}

        {/* Requisitions Table */}
        {!isLoading && activeTab === 'requisitions' && (
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Codigo</TableHead>
                  <TableHead>Solicitante</TableHead>
                  <TableHead>Descricao</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Data</TableHead>
                  <TableHead className="text-right">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                {filteredRequisitions.map((item: any) => (
                  <TableRow
                    key={item.id}
                    className="cursor-pointer"
                    onClick={() => handleView(item)}
                  >
                    <TableCell className="font-medium">{item.number || item.id?.slice(0, 8)}</TableCell>
                    <TableCell>{item.requester_id?.slice(0, 8) || '-'}</TableCell>
                    <TableCell className="max-w-[200px] truncate">{item.description || '-'}</TableCell>
                    <TableCell>
                      <Badge className={getRequisitionStatusColor(item.status)}>
                        {STATUS_LABELS[item.status] || item.status}
                      </Badge>
                    </TableCell>
                    <TableCell>{formatDate(item.created_at)}</TableCell>
                    <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="sm">
                            <MoreHorizontal className="w-4 h-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => handleView(item)}>
                            <Eye className="w-4 h-4 mr-2" />
                            Visualizar
                          </DropdownMenuItem>
                          <DropdownMenuItem>
                            <Edit className="w-4 h-4 mr-2" />
                            Editar
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>

            {filteredRequisitions.length === 0 && (
              <div className="text-center py-12">
                <ClipboardList className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
                <h3 className="text-lg font-medium text-[hsl(var(--foreground))]">
                  Nenhuma requisicao encontrada
                </h3>
                <p className="text-[hsl(var(--muted-foreground))] mt-1 mb-4">
                  {searchTerm ? 'Tente ajustar os filtros de busca' : 'Crie a primeira requisicao de compra'}
                </p>
                {!searchTerm && (
                  <Button variant="primary" onClick={handleCreate}>
                    <Plus className="w-4 h-4 mr-2" />
                    Nova Requisicao
                  </Button>
                )}
              </div>
            )}
          </div>
        )}

        {/* Orders Table */}
        {!isLoading && activeTab === 'orders' && (
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Codigo</TableHead>
                  <TableHead>Fornecedor</TableHead>
                  <TableHead>Valor Total</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Data</TableHead>
                  <TableHead className="text-right">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                {filteredOrders.map((item: any) => (
                  <TableRow
                    key={item.id}
                    className="cursor-pointer"
                    onClick={() => handleView(item)}
                  >
                    <TableCell className="font-medium">{item.number || item.id?.slice(0, 8)}</TableCell>
                    <TableCell>{item.supplier_id?.slice(0, 8) || '-'}</TableCell>
                    <TableCell className="font-medium text-green-500">
                      {item.total ? formatCurrency(parseFloat(item.total)) : formatCurrency(undefined)}
                    </TableCell>
                    <TableCell>
                      <Badge className={getOrderStatusColor(item.status)}>
                        {STATUS_LABELS[item.status] || item.status}
                      </Badge>
                    </TableCell>
                    <TableCell>{formatDate(item.created_at)}</TableCell>
                    <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="sm">
                            <MoreHorizontal className="w-4 h-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => handleView(item)}>
                            <Eye className="w-4 h-4 mr-2" />
                            Visualizar
                          </DropdownMenuItem>
                          <DropdownMenuItem>
                            <Edit className="w-4 h-4 mr-2" />
                            Editar
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>

            {filteredOrders.length === 0 && (
              <div className="text-center py-12">
                <FileText className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
                <h3 className="text-lg font-medium text-[hsl(var(--foreground))]">
                  Nenhuma ordem de compra encontrada
                </h3>
                <p className="text-[hsl(var(--muted-foreground))] mt-1 mb-4">
                  {searchTerm ? 'Tente ajustar os filtros de busca' : 'Crie a primeira ordem de compra'}
                </p>
                {!searchTerm && (
                  <Button variant="primary" onClick={handleCreate}>
                    <Plus className="w-4 h-4 mr-2" />
                    Nova Ordem
                  </Button>
                )}
              </div>
            )}
          </div>
        )}
      </main>

      {/* Modals */}
      <PurchaseFormModal
        isOpen={showFormModal}
        onClose={() => setShowFormModal(false)}
        onSubmit={handleFormSubmit}
        isLoading={createRequisition.isPending || createOrder.isPending}
        type={formType}
      />

      <PurchaseDetailModal
        isOpen={showDetailModal}
        onClose={() => { setShowDetailModal(false); setSelectedItem(null); }}
        item={selectedItem}
        type={activeTab === 'requisitions' ? 'requisition' : 'order'}
      />
    </div>
  );
}
