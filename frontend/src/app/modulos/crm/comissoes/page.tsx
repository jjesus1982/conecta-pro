'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { customInstance } from '@/lib/api-client';
import {
  Coins,
  Search,
  RefreshCw,
  Plus,
  MoreHorizontal,
  Eye,
  Edit,
  Trash2,
  AlertCircle,
  DollarSign,
  TrendingUp,
  Users,
} from 'lucide-react';
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
import { formatCurrency } from '@/lib/utils';
import { toast } from 'sonner';

const COMMISSION_STATUS_BADGE: Record<string, string> = {
  pending: 'bg-yellow-100 text-yellow-800',
  approved: 'bg-blue-100 text-blue-800',
  paid: 'bg-green-100 text-green-800',
  cancelled: 'bg-red-100 text-red-800',
};

const COMMISSION_STATUS_LABEL: Record<string, string> = {
  pending: 'Pendente',
  approved: 'Aprovada',
  paid: 'Paga',
  cancelled: 'Cancelada',
};

const RULE_STATUS_BADGE: Record<string, string> = {
  active: 'bg-green-100 text-green-800',
  inactive: 'bg-gray-100 text-gray-800',
  draft: 'bg-yellow-100 text-yellow-800',
};

const RULE_STATUS_LABEL: Record<string, string> = {
  active: 'Ativa',
  inactive: 'Inativa',
  draft: 'Rascunho',
};

export default function ComissoesPage() {
  const [activeTab, setActiveTab] = useState<'comissoes' | 'regras'>('comissoes');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(0);
  const pageSize = 20;

  const {
    data: commissionsData,
    isLoading: loadingCommissions,
    error: errorCommissions,
    refetch: refetchCommissions,
  } = useQuery({
    queryKey: ['crm-commissions', search, page],
    queryFn: async () => {
      const params: Record<string, any> = {
        skip: page * pageSize,
        limit: pageSize,
      };
      if (search) params.search = search;
      const res = await customInstance({
        url: '/api/v1/crm/commissions',
        method: 'GET',
        params,
      });
      return res;
    },
  });

  const {
    data: rulesData,
    isLoading: loadingRules,
    error: errorRules,
    refetch: refetchRules,
  } = useQuery({
    queryKey: ['crm-commission-rules'],
    queryFn: async () => {
      const res = await customInstance({
        url: '/api/v1/crm/commissions/rules',
        method: 'GET',
      });
      return res;
    },
  });

  const { data: statsData } = useQuery({
    queryKey: ['crm-commissions-stats'],
    queryFn: async () => {
      const res = await customInstance({
        url: '/api/v1/crm/commissions/stats',
        method: 'GET',
      });
      return res;
    },
  });

  const commissions = (commissionsData as any)?.items || (Array.isArray(commissionsData) ? commissionsData : []);
  const totalCommissions = (commissionsData as any)?.total || commissions.length;

  const rules = (rulesData as any)?.items || (Array.isArray(rulesData) ? rulesData : []);

  const st = statsData as any;
  const stats = {
    totalComissoes: st?.total || st?.total_commissions || totalCommissions,
    valorTotal: st?.total_value || st?.valor_total || 0,
    pendentes: st?.pending || st?.pendentes || 0,
  };

  const isLoading = activeTab === 'comissoes' ? loadingCommissions : loadingRules;
  const error = activeTab === 'comissoes' ? errorCommissions : errorRules;
  const refetch = activeTab === 'comissoes' ? refetchCommissions : refetchRules;

  const getCommissionStatusBadge = (status: string) => (
    <Badge className={COMMISSION_STATUS_BADGE[status] || 'bg-gray-100 text-gray-800'}>
      {COMMISSION_STATUS_LABEL[status] || status}
    </Badge>
  );

  const getRuleStatusBadge = (status: string) => (
    <Badge className={RULE_STATUS_BADGE[status] || 'bg-gray-100 text-gray-800'}>
      {RULE_STATUS_LABEL[status] || status}
    </Badge>
  );

  const formatDate = (date: string | null | undefined) => {
    if (!date) return '-';
    try {
      return new Date(date).toLocaleDateString('pt-BR');
    } catch {
      return date;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <Coins className="h-6 w-6" />
            Comissoes
          </h1>
          <p className="text-muted-foreground">Gestao de comissoes e regras de comissionamento</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => refetch()} disabled={isLoading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
            Atualizar
          </Button>
          <Button
            onClick={() =>
              toast.info(
                activeTab === 'comissoes'
                  ? 'Formulario de nova comissao em desenvolvimento'
                  : 'Formulario de nova regra em desenvolvimento'
              )
            }
          >
            <Plus className="h-4 w-4 mr-2" />
            {activeTab === 'comissoes' ? 'Nova Comissao' : 'Nova Regra'}
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Comissoes</CardTitle>
            <Coins className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums">{stats.totalComissoes}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Valor Total</CardTitle>
            <DollarSign className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-green-600">{formatCurrency(stats.valorTotal)}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Pendentes</CardTitle>
            <TrendingUp className="h-4 w-4 text-yellow-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-yellow-600">{stats.pendentes}</div>
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <div className="flex border-b">
        <button
          onClick={() => { setActiveTab('comissoes'); setPage(0); setSearch(''); }}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'comissoes'
              ? 'border-cyan-600 text-cyan-600'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          Comissoes
        </button>
        <button
          onClick={() => { setActiveTab('regras'); setPage(0); setSearch(''); }}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'regras'
              ? 'border-cyan-600 text-cyan-600'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          Regras
        </button>
      </div>

      {/* Search */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(0); }}
              placeholder={activeTab === 'comissoes' ? 'Buscar por vendedor, referencia...' : 'Buscar por nome da regra...'}
              className="pl-10"
            />
          </div>
        </CardContent>
      </Card>

      {/* Error */}
      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-destructive" />
          <p className="text-sm text-destructive flex-1">
            Erro ao carregar {activeTab === 'comissoes' ? 'comissoes' : 'regras'}
          </p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Tentar novamente
          </Button>
        </div>
      )}

      {/* Table - Comissoes */}
      {activeTab === 'comissoes' && (
        <Card>
          <CardContent className="p-0">
            {loadingCommissions ? (
              <div className="flex items-center justify-center py-12">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
              </div>
            ) : commissions.length === 0 ? (
              <div className="text-center py-12 text-muted-foreground">
                <Coins className="h-16 w-16 mx-auto mb-4 opacity-50" />
                <h3 className="text-lg font-medium">Nenhuma comissao encontrada</h3>
                <p className="mt-2">Tente ajustar os filtros ou registre uma nova comissao</p>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Referencia</TableHead>
                    <TableHead>Vendedor</TableHead>
                    <TableHead>Valor Venda</TableHead>
                    <TableHead>Comissao</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="w-[80px]">Ações</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {commissions.map((item: any) => (
                    <TableRow key={item.id}>
                      <TableCell>
                        <div className="font-medium">
                          {item.reference || item.referencia || item.ref || '-'}
                        </div>
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {item.salesperson_name || item.vendedor || item.seller_name || '-'}
                      </TableCell>
                      <TableCell className="text-sm font-medium">
                        {formatCurrency(item.sale_value || item.valor_venda || 0)}
                      </TableCell>
                      <TableCell className="text-sm font-medium text-green-600">
                        {formatCurrency(item.final_commission || item.commission_value || item.valor_comissao || item.value || 0)}
                      </TableCell>
                      <TableCell>{getCommissionStatusBadge(item.status || 'pending')}</TableCell>
                      <TableCell>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-8 w-8">
                              <MoreHorizontal className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem
                              onClick={() => toast.info('Detalhes da comissao em desenvolvimento')}
                            >
                              <Eye className="h-4 w-4 mr-2" />
                              Ver detalhes
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              onClick={() => toast.info('Edição de comissao em desenvolvimento')}
                            >
                              <Edit className="h-4 w-4 mr-2" />
                              Editar
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              className="text-destructive"
                              onClick={() => toast.info('Exclusão de comissao em desenvolvimento')}
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
      )}

      {/* Table - Regras */}
      {activeTab === 'regras' && (
        <Card>
          <CardContent className="p-0">
            {loadingRules ? (
              <div className="flex items-center justify-center py-12">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
              </div>
            ) : rules.length === 0 ? (
              <div className="text-center py-12 text-muted-foreground">
                <Users className="h-16 w-16 mx-auto mb-4 opacity-50" />
                <h3 className="text-lg font-medium">Nenhuma regra encontrada</h3>
                <p className="mt-2">Crie uma regra de comissionamento para comecar</p>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Nome</TableHead>
                    <TableHead>Tipo</TableHead>
                    <TableHead>Valor Base</TableHead>
                    <TableHead>Trigger</TableHead>
                    <TableHead>Vigencia</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="w-[80px]">Ações</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rules.map((item: any) => (
                    <TableRow key={item.id}>
                      <TableCell>
                        <div className="font-medium">{item.name || item.nome || '-'}</div>
                      </TableCell>
                      <TableCell className="text-sm">
                        {item.type || item.tipo || item.commission_type || '-'}
                      </TableCell>
                      <TableCell className="text-sm font-medium">
                        {item.base_value != null
                          ? item.is_percentage || item.tipo === 'percentual'
                            ? `${item.base_value}%`
                            : formatCurrency(item.base_value || item.valor_base || 0)
                          : formatCurrency(item.valor_base || 0)}
                      </TableCell>
                      <TableCell className="text-sm">
                        {item.trigger || item.gatilho || item.trigger_event || '-'}
                      </TableCell>
                      <TableCell className="text-sm">
                        {item.start_date || item.vigencia_inicio
                          ? `${formatDate(item.start_date || item.vigencia_inicio)} - ${formatDate(item.end_date || item.vigencia_fim)}`
                          : '-'}
                      </TableCell>
                      <TableCell>{getRuleStatusBadge(item.status || 'active')}</TableCell>
                      <TableCell>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-8 w-8">
                              <MoreHorizontal className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem
                              onClick={() => toast.info('Detalhes da regra em desenvolvimento')}
                            >
                              <Eye className="h-4 w-4 mr-2" />
                              Ver detalhes
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              onClick={() => toast.info('Edição de regra em desenvolvimento')}
                            >
                              <Edit className="h-4 w-4 mr-2" />
                              Editar
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              className="text-destructive"
                              onClick={() => toast.info('Exclusão de regra em desenvolvimento')}
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
      )}

      {/* Pagination (comissoes tab only) */}
      {activeTab === 'comissoes' && totalCommissions > pageSize && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Mostrando {page * pageSize + 1}-{Math.min((page + 1) * pageSize, totalCommissions)} de{' '}
            {totalCommissions}
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
              disabled={(page + 1) * pageSize >= totalCommissions}
            >
              Proximo
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
