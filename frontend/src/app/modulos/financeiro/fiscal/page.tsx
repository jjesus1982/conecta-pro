'use client';

import { Landmark, Search, RefreshCw, Plus, MoreHorizontal, Eye, Edit, CheckCircle, AlertCircle, Send, ArrowLeft, FileText, XCircle } from 'lucide-react';
import { useState } from 'react';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { useCondominio } from '@/contexts/CondominioContext';
import {
  useNFes,
  useNFSes,
  useFiscalDashboard,
  useCreateNFe,
  useAuthorizeNFe,
} from '@/hooks/financial/useFinancial';
import { NFeFormModal } from '@/components/financeiro/nfe-form-modal';
import { NFeDetailModal } from '@/components/financeiro/nfe-detail-modal';
import type { NFeListResponse } from '@/types/generated/financial/models/nFeListResponse';
import type { NFeCreate } from '@/types/generated/financial/models/nFeCreate';

type TabType = 'nfe' | 'nfse';

const formatCurrency = (value: number | undefined | null) => {
  if (value == null) return 'R$ 0,00';
  return value.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
};

const formatDate = (date: string | undefined | null) => {
  if (!date) return '-';
  return new Date(date).toLocaleDateString('pt-BR');
};

const getStatusColor = (status: string) => {
  switch (status) {
    case 'draft':
      return 'bg-gray-500/10 text-gray-500 border-gray-500/20';
    case 'authorized':
      return 'bg-green-500/10 text-green-500 border-green-500/20';
    case 'cancelled':
      return 'bg-red-500/10 text-red-500 border-red-500/20';
    case 'rejected':
      return 'bg-orange-500/10 text-orange-500 border-orange-500/20';
    case 'pending':
      return 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20';
    default:
      return 'bg-gray-500/10 text-gray-500 border-gray-500/20';
  }
};

const STATUS_LABELS: Record<string, string> = {
  draft: 'Rascunho',
  authorized: 'Autorizada',
  cancelled: 'Cancelada',
  rejected: 'Rejeitada',
  pending: 'Pendente',
};

export default function FiscalPage() {
  const { condominioId } = useCondominio();
  const [activeTab, setActiveTab] = useState<TabType>('nfe');
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [showFormModal, setShowFormModal] = useState(false);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [selectedNFe, setSelectedNFe] = useState<NFeListResponse | null>(null);

  const { data: nfes = [], isLoading: loadingNFes, refetch: refetchNFes } = useNFes({ condominio_id: condominioId });
  const { data: nfses = [], isLoading: loadingNFSes, refetch: refetchNFSes } = useNFSes({ condominio_id: condominioId });
  const { data: dashboardRaw, isLoading: loadingDashboard } = useFiscalDashboard({ condominio_id: condominioId });
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const dashboard = dashboardRaw as any;
  const createNFe = useCreateNFe();
  const authorizeNFe = useAuthorizeNFe();

  const isLoading = activeTab === 'nfe' ? loadingNFes : loadingNFSes;

  const handleRefresh = () => {
    if (activeTab === 'nfe') refetchNFes();
    else refetchNFSes();
  };

  const handleView = (nfe: any) => {
    setSelectedNFe(nfe);
    setShowDetailModal(true);
  };

  const handleAuthorize = async (nfe: any) => {
    try {
      await authorizeNFe.mutateAsync({ data: { nfe_id: nfe.id } });
    } catch (error) {
    }
  };

  const handleFormSubmit = async (data: NFeCreate) => {
    try {
      await createNFe.mutateAsync({ data });
      setShowFormModal(false);
    } catch (error) {
    }
  };

  const currentData: NFeListResponse[] = activeTab === 'nfe'
    ? (Array.isArray(nfes) ? (nfes as NFeListResponse[]) : [])
    : (Array.isArray(nfses) ? (nfses as NFeListResponse[]) : []);

  const filteredData = currentData.filter((item: any) => {
    const matchesSearch =
      !searchTerm ||
      item.number?.toString().includes(searchTerm) ||
      item.recipient_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      item.access_key?.includes(searchTerm);
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
                <div className="w-10 h-10 rounded-lg bg-indigo-500/10 flex items-center justify-center">
                  <Landmark className="w-5 h-5 text-indigo-500" />
                </div>
                <div>
                  <h1 className="text-lg font-semibold text-[hsl(var(--foreground))]">
                    Fiscal
                  </h1>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">
                    Notas fiscais e obrigações
                  </p>
                </div>
              </div>
            </div>
            <Button variant="primary" size="sm" onClick={() => setShowFormModal(true)}>
              <Plus className="w-4 h-4 mr-2" />
              Nova Nota Fiscal
            </Button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Stats Cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-indigo-500/10 flex items-center justify-center">
                <FileText className="w-5 h-5 text-indigo-500" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                  {dashboard?.stats?.total_nfe_emitidas ?? 0}
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Total NF-e</p>
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
                  {dashboard?.stats?.total_nfse_emitidas ?? 0}
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Total NFS-e</p>
              </div>
            </div>
          </div>

          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-green-500/10 flex items-center justify-center">
                <CheckCircle className="w-5 h-5 text-green-500" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-green-500">
                  {dashboard?.stats?.total_nfe_mes ?? 0}
                </p>
                {/* rótulo honesto: o dado é NF-e de ENTRADA no mês, não "notas autorizadas" */}
                <p className="text-xs text-[hsl(var(--muted-foreground))]">NF-e entrada no mês</p>
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
                  {dashboard?.stats?.obrigacoes_pendentes ?? 0}
                </p>
                {/* rótulo honesto: são OBRIGAÇÕES fiscais em aberto, não notas pendentes */}
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Obrigações em aberto</p>
              </div>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex items-center gap-1 mb-6 bg-[hsl(var(--muted))] rounded-lg p-1 w-fit">
          <button
            onClick={() => { setActiveTab('nfe'); setStatusFilter('all'); }}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              activeTab === 'nfe'
                ? 'bg-[hsl(var(--card))] text-[hsl(var(--foreground))] shadow-sm'
                : 'text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))]'
            }`}
          >
            NF-e
          </button>
          <button
            onClick={() => { setActiveTab('nfse'); setStatusFilter('all'); }}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              activeTab === 'nfse'
                ? 'bg-[hsl(var(--card))] text-[hsl(var(--foreground))] shadow-sm'
                : 'text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))]'
            }`}
          >
            NFS-e
          </button>
        </div>

        {/* Search and Filters */}
        <div className="flex flex-col sm:flex-row gap-4 mb-6">
          <div className="flex-1">
            <Input
              type="search"
              placeholder="Buscar por numero, destinatario ou chave de acesso..."
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
              <SelectItem value="draft">Rascunho</SelectItem>
              <SelectItem value="authorized">Autorizada</SelectItem>
              <SelectItem value="cancelled">Cancelada</SelectItem>
              <SelectItem value="rejected">Rejeitada</SelectItem>
              <SelectItem value="pending">Pendente</SelectItem>
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
              <Landmark className="w-8 h-8" />
            </div>
          </div>
        )}

        {/* Table */}
        {!isLoading && (
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Numero</TableHead>
                  <TableHead>Serie</TableHead>
                  <TableHead>Destinatario</TableHead>
                  <TableHead>Valor</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Data</TableHead>
                  <TableHead className="text-right">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredData.map((nfe: any) => (
                  <TableRow
                    key={nfe.id}
                    className="cursor-pointer"
                    onClick={() => handleView(nfe)}
                  >
                    <TableCell className="font-medium">{nfe.number || '-'}</TableCell>
                    <TableCell>{nfe.series || '-'}</TableCell>
                    <TableCell>{nfe.recipient_name || '-'}</TableCell>
                    <TableCell className="font-medium">
                      {formatCurrency(nfe.amount || nfe.total_amount)}
                    </TableCell>
                    <TableCell>
                      <Badge className={getStatusColor(nfe.status)}>
                        {STATUS_LABELS[nfe.status] || nfe.status}
                      </Badge>
                    </TableCell>
                    <TableCell>{formatDate(nfe.issue_date || nfe.created_at)}</TableCell>
                    <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="sm">
                            <MoreHorizontal className="w-4 h-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => handleView(nfe)}>
                            <Eye className="w-4 h-4 mr-2" />
                            Visualizar
                          </DropdownMenuItem>
                          {nfe.status === 'draft' && (
                            <DropdownMenuItem onClick={() => handleAuthorize(nfe)}>
                              <Send className="w-4 h-4 mr-2" />
                              Autorizar
                            </DropdownMenuItem>
                          )}
                          {nfe.status === 'draft' && (
                            <DropdownMenuItem>
                              <Edit className="w-4 h-4 mr-2" />
                              Editar
                            </DropdownMenuItem>
                          )}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>

            {filteredData.length === 0 && (
              <div className="text-center py-12">
                <Landmark className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
                <h3 className="text-lg font-medium text-[hsl(var(--foreground))]">
                  Nenhuma {activeTab === 'nfe' ? 'NF-e' : 'NFS-e'} encontrada
                </h3>
                <p className="text-[hsl(var(--muted-foreground))] mt-1 mb-4">
                  {searchTerm ? 'Tente ajustar os filtros de busca' : 'Emita a primeira nota fiscal'}
                </p>
                {!searchTerm && (
                  <Button variant="primary" onClick={() => setShowFormModal(true)}>
                    <Plus className="w-4 h-4 mr-2" />
                    Nova Nota Fiscal
                  </Button>
                )}
              </div>
            )}
          </div>
        )}
      </main>

      {/* Modals */}
      <NFeFormModal
        isOpen={showFormModal}
        onClose={() => setShowFormModal(false)}
        onSubmit={handleFormSubmit}
        isLoading={createNFe.isPending}
      />

      <NFeDetailModal
        isOpen={showDetailModal}
        onClose={() => { setShowDetailModal(false); setSelectedNFe(null); }}
        nfe={selectedNFe}
      />
    </div>
  );
}
