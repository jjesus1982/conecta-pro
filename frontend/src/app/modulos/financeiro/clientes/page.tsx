'use client';

import { Users, Search, RefreshCw, Plus, MoreHorizontal, Eye, Edit, Trash2, AlertCircle, ArrowLeft, UserCheck, DollarSign, ChevronLeft, ChevronRight } from 'lucide-react';
import { useState } from 'react';
import Link from 'next/link';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  useCustomers,
  useCreateCustomer,
  useCustomerStats,
} from '@/hooks/financial/useFinancial';
import { CustomerFormModal } from '@/components/financeiro/customer-form-modal';
import { cn, formatCurrency } from '@/lib/utils';
import { useCondominio } from '@/contexts/CondominioContext';
import type { CustomerResponse } from '@/types/generated/financial/models/customerResponse';

export default function ClientesPage() {
  const { condominioId } = useCondominio();
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [showFormModal, setShowFormModal] = useState(false);
  const [selectedCustomer, setSelectedCustomer] = useState<CustomerResponse | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);

  // Hooks de dados
  const {
    data: customersData,
    isLoading,
    isError,
    error,
    refetch,
  } = useCustomers({
    condominio_id: condominioId,
    skip: (page - 1) * pageSize,
    limit: pageSize,
    ...(search && { search }),
    ...(statusFilter && { status: statusFilter }),
  });

  const createCustomer = useCreateCustomer();

  const customers: CustomerResponse[] = Array.isArray(customersData) ? (customersData as CustomerResponse[]) : [];
  const total = customers.length;
  const totalPages = Math.ceil(total / pageSize);

  const totalCustomers = total;
  const activeCustomers = customers.filter((c) => c.status === 'ativo').length;

  const handleView = (customer: CustomerResponse) => {
    setSelectedCustomer(customer);
  };

  const handleEdit = (customer: CustomerResponse) => {
    setSelectedCustomer(customer);
    setShowFormModal(true);
  };

  const handleCreate = () => {
    setSelectedCustomer(null);
    setShowFormModal(true);
  };

  const handleFormSubmit = async (data: any) => {
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      await createCustomer.mutateAsync({ data: data as any });
      setShowFormModal(false);
      setSelectedCustomer(null);
      refetch();
    } catch (err) {
      throw err;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active':
        return 'bg-green-500/10 text-green-500 border-green-500/30';
      case 'inactive':
        return 'bg-gray-500/10 text-gray-500 border-gray-500/30';
      case 'defaulter':
        return 'bg-red-500/10 text-red-500 border-red-500/30';
      default:
        return 'bg-gray-500/10 text-gray-500 border-gray-500/30';
    }
  };

  const getStatusLabel = (status: string) => {
    switch (status) {
      case 'active':
        return 'Ativo';
      case 'inactive':
        return 'Inativo';
      case 'defaulter':
        return 'Inadimplente';
      default:
        return status;
    }
  };

  // Filter localmente por search
  const filteredCustomers: CustomerResponse[] = search
    ? customers.filter((c) =>
        c.name?.toLowerCase().includes(search.toLowerCase()) ||
        c.email?.toLowerCase().includes(search.toLowerCase()) ||
        c.cpf_cnpj?.toLowerCase().includes(search.toLowerCase())
      )
    : customers;

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <Link href="/modulos/financeiro">
            <Button variant="ghost" size="sm">
              <ArrowLeft className="w-4 h-4 mr-2" />
              Financeiro
            </Button>
          </Link>
          <div className="flex items-center gap-2">
            <div className="w-10 h-10 rounded-lg bg-cyan-500/10 flex items-center justify-center">
              <Users className="w-5 h-5 text-cyan-500" />
            </div>
            <div>
              <h1 className="text-lg font-semibold text-[hsl(var(--foreground))]">
                Clientes
              </h1>
              <p className="text-xs text-[hsl(var(--muted-foreground))]">
                {total} clientes cadastrados
              </p>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => refetch()}
            disabled={isLoading}
          >
            <RefreshCw className={cn('w-4 h-4', isLoading && 'animate-spin')} />
          </Button>
          <Button variant="primary" size="sm" onClick={handleCreate}>
            <Plus className="w-4 h-4 mr-2" />
            Novo Cliente
          </Button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-cyan-500/10 flex items-center justify-center">
              <Users className="w-5 h-5 text-cyan-500" />
            </div>
            <div>
              <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                {isLoading ? '...' : totalCustomers}
              </p>
              <p className="text-xs text-[hsl(var(--muted-foreground))]">Total de Clientes</p>
            </div>
          </div>
        </div>

        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-green-500/10 flex items-center justify-center">
              <UserCheck className="w-5 h-5 text-green-500" />
            </div>
            <div>
              <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                {isLoading ? '...' : activeCustomers}
              </p>
              <p className="text-xs text-[hsl(var(--muted-foreground))]">Ativos</p>
            </div>
          </div>
        </div>

        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-red-500/10 flex items-center justify-center">
              <DollarSign className="w-5 h-5 text-red-500" />
            </div>
            <div>
              <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                {isLoading
                  ? '...'
                  : customers.filter((c) => String(c.status) === 'defaulter').length}
              </p>
              <p className="text-xs text-[hsl(var(--muted-foreground))]">Inadimplentes</p>
            </div>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4">
        <div className="flex-1">
          <Input
            type="search"
            placeholder="Buscar por nome, email ou documento..."
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            icon={<Search className="w-4 h-4" />}
          />
        </div>
        <div className="flex gap-2 flex-wrap">
          <Button
            variant={statusFilter === undefined ? 'primary' : 'secondary'}
            size="sm"
            onClick={() => { setStatusFilter(undefined); setPage(1); }}
          >
            Todos
          </Button>
          <Button
            variant={statusFilter === ('active' as string) ? 'primary' : 'secondary'}
            size="sm"
            onClick={() => { setStatusFilter('active'); setPage(1); }}
          >
            Ativos
          </Button>
          <Button
            variant={statusFilter === ('defaulter' as string) ? 'primary' : 'secondary'}
            size="sm"
            onClick={() => { setStatusFilter('defaulter'); setPage(1); }}
          >
            Inadimplentes
          </Button>
        </div>
      </div>

      {/* Error */}
      {isError && (
        <div className="flex items-center gap-3 p-4 rounded-lg bg-[hsl(var(--destructive))]/10 border border-[hsl(var(--destructive))]/30">
          <AlertCircle className="w-5 h-5 text-[hsl(var(--destructive))]" />
          <div>
            <p className="font-medium text-[hsl(var(--destructive))]">Erro ao carregar clientes</p>
            <p className="text-sm text-[hsl(var(--muted-foreground))]">
              {(error as Error)?.message || 'Tente novamente em alguns instantes'}
            </p>
          </div>
          <Button variant="secondary" size="sm" onClick={() => refetch()} className="ml-auto">
            Tentar novamente
          </Button>
        </div>
      )}

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="divide-y divide-[hsl(var(--border))]">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="p-4 flex items-center gap-4">
                  <div className="flex-1 space-y-2">
                    <div className="h-4 w-48 bg-[hsl(var(--secondary))] rounded animate-shimmer" />
                    <div className="h-3 w-32 bg-[hsl(var(--secondary))] rounded animate-shimmer" />
                  </div>
                  <div className="h-6 w-20 bg-[hsl(var(--secondary))] rounded animate-shimmer" />
                </div>
              ))}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-[hsl(var(--border))]">
                    <th className="text-left p-4 text-sm font-medium text-[hsl(var(--muted-foreground))]">
                      Nome
                    </th>
                    <th className="text-left p-4 text-sm font-medium text-[hsl(var(--muted-foreground))] hidden md:table-cell">
                      Email
                    </th>
                    <th className="text-right p-4 text-sm font-medium text-[hsl(var(--muted-foreground))] hidden lg:table-cell">
                      Debito Total
                    </th>
                    <th className="text-left p-4 text-sm font-medium text-[hsl(var(--muted-foreground))]">
                      Status
                    </th>
                    <th className="w-12 p-4"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[hsl(var(--border))]">
                  {filteredCustomers.map((customer: CustomerResponse) => (
                    <tr
                      key={customer.id}
                      className="hover:bg-[hsl(var(--secondary))]/50 transition-colors cursor-pointer"
                      onClick={() => handleView(customer)}
                    >
                      <td className="p-4">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-lg bg-cyan-500/10 flex items-center justify-center flex-shrink-0">
                            <Users className="w-5 h-5 text-cyan-500" />
                          </div>
                          <div>
                            <p className="font-medium text-[hsl(var(--foreground))]">
                              {customer.name}
                            </p>
                            <p className="text-xs text-[hsl(var(--muted-foreground))]">
                              {customer.cpf_cnpj || '-'}
                            </p>
                          </div>
                        </div>
                      </td>
                      <td className="p-4 hidden md:table-cell">
                        <span className="text-sm text-[hsl(var(--muted-foreground))]">
                          {customer.email || '-'}
                        </span>
                      </td>
                      <td className="p-4 text-right hidden lg:table-cell">
                        <span
                          className={cn(
                            'font-mono text-sm font-medium',
                            (Number(customer.total_debt) || 0) > 0 ? 'text-red-500' : 'text-[hsl(var(--foreground))]'
                          )}
                        >
                          {formatCurrency(Number(customer.total_debt) || 0)}
                        </span>
                      </td>
                      <td className="p-4">
                        <span
                          className={cn(
                            'inline-flex px-2 py-1 text-xs font-medium rounded-full border',
                            getStatusColor(customer.status || 'active')
                          )}
                        >
                          {getStatusLabel(customer.status || 'active')}
                        </span>
                      </td>
                      <td className="p-4" onClick={(e) => e.stopPropagation()}>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="sm">
                              <MoreHorizontal className="w-4 h-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem onClick={() => handleView(customer)}>
                              <Eye className="w-4 h-4 mr-2" />
                              Visualizar
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={() => handleEdit(customer)}>
                              <Edit className="w-4 h-4 mr-2" />
                              Editar
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Empty state */}
          {!isLoading && !isError && filteredCustomers.length === 0 && (
            <div className="text-center py-12">
              <Users className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
              <h3 className="text-lg font-medium text-[hsl(var(--foreground))]">
                Nenhum cliente encontrado
              </h3>
              <p className="text-[hsl(var(--muted-foreground))] mt-1">
                {search || statusFilter
                  ? 'Tente ajustar os filtros de busca'
                  : 'Cadastre seu primeiro cliente'}
              </p>
              {!search && !statusFilter && (
                <Button className="mt-4" onClick={handleCreate}>
                  <Plus className="w-4 h-4 mr-2" />
                  Novo Cliente
                </Button>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-[hsl(var(--muted-foreground))]">
            Mostrando {(page - 1) * pageSize + 1} a{' '}
            {Math.min(page * pageSize, total)} de {total} clientes
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage(page - 1)}
              disabled={page <= 1}
            >
              <ChevronLeft className="w-4 h-4" />
            </Button>
            <span className="text-sm text-[hsl(var(--foreground))]">
              Pagina {page} de {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage(page + 1)}
              disabled={page >= totalPages}
            >
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
        </div>
      )}

      {/* Modal */}
      <CustomerFormModal
        isOpen={showFormModal}
        onClose={() => {
          setShowFormModal(false);
          setSelectedCustomer(null);
        }}
        customer={selectedCustomer}
        onSubmit={handleFormSubmit}
        isLoading={createCustomer.isPending}
      />
    </div>
  );
}
