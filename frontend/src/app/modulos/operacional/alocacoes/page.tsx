'use client';

import dynamic from 'next/dynamic';
import { Users, ArrowLeft, Filter, Eye, Calendar, ChevronLeft, ChevronRight, RefreshCw, AlertCircle, Ban, Plus, ArrowRightLeft } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { PageHeader } from '@/components/ui/page-header';
import { Input } from '@/components/ui/input';
import { Modal, ModalFooter } from '@/components/ui/modal';
import { useAuth } from '@/hooks/useAuth';
import { useAllocations, useTerminateAllocation, useCreateAllocation } from '@/hooks/operacional/useAllocations';
import { usePosts } from '@/hooks/operacional/usePosts';
import { useEmployees } from '@/hooks/operacional/useEmployees';
import { getErrorMessage } from '@/lib/api';
const AllocationDetailModal = dynamic(() => import('@/components/operacional/allocation-detail-modal').then(m => m.AllocationDetailModal), { ssr: false });
const AllocationFormModal = dynamic(() => import('@/components/operacional/allocation-form-modal').then(m => m.AllocationFormModal), { ssr: false });
import { ExportButton } from '@/components/ui/export-button';
import type { Allocation, AllocationFilter, AllocationStatus, AllocationTerminate, Employee, Post } from '@/types/operacional';
import { ALLOCATION_STATUS_LABELS } from '@/types/operacional';

export default function AlocacoesPage() {
  const router = useRouter();
  const { isLoading: authLoading, isAuthenticated } = useAuth();
  const {
    data: allocationsData,
    isLoading,
    error,
    refetch,
  } = useAllocations();
  const allocations = (allocationsData?.items ?? []) as Allocation[];
  const total = allocationsData?.total ?? allocations.length;
  const refresh = () => { refetch(); };
  const [page, setPage] = useState(1);
  const [pageSize] = useState(10);
  const totalPages = Math.ceil(total / pageSize);
  const [filters, setFilters] = useState<AllocationFilter>({});
  const { data: postsData } = usePosts();
  const posts = useMemo(() => (postsData?.items ?? []) as Post[], [postsData?.items]);
  const { data: employeesData } = useEmployees();
  const employees = useMemo(() => (employeesData?.items ?? []) as Employee[], [employeesData?.items]);
  const terminateAllocationMutation = useTerminateAllocation();
  const createAllocationMutation = useCreateAllocation();

  const [showFilters, setShowFilters] = useState(false);
  const [selectedAllocation, setSelectedAllocation] = useState<Allocation | null>(null);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [showFormModal, setShowFormModal] = useState(false);
  const [showTerminateModal, setShowTerminateModal] = useState(false);
  const [isTerminating, setIsTerminating] = useState(false);
  const [terminateError, setTerminateError] = useState<string | null>(null);
  const [terminateData, setTerminateData] = useState<AllocationTerminate>({
    end_date: '',
    termination_reason: '',
    notes: '',
  });

  // Estado para transferência de posto
  const [showTransferModal, setShowTransferModal] = useState(false);
  const [isTransferring, setIsTransferring] = useState(false);
  const [transferError, setTransferError] = useState<string | null>(null);
  const [transferData, setTransferData] = useState({
    new_post_id: '',
    transfer_date: '',
    notes: '',
  });

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [authLoading, isAuthenticated, router]);

  const postMap = useMemo(() => {
    return posts.reduce<Record<string, Post>>((acc, post) => {
      acc[post.id] = post;
      return acc;
    }, {});
  }, [posts]);

  const employeeMap = useMemo(() => {
    return employees.reduce<Record<string, Employee>>((acc, employee) => {
      acc[employee.id] = employee;
      return acc;
    }, {});
  }, [employees]);

  const getEmployeeLabel = (allocation: Allocation) => {
    // Usar dados denormalizados da API se disponíveis
    if (allocation.employee_name) {
      return allocation.employee_name;
    }
    // Fallback para lookup no map
    const employee = employeeMap[allocation.employee_id];
    return (
      employee?.full_name ||
      employee?.name ||
      employee?.email ||
      employee?.registration ||
      allocation.employee_id.substring(0, 8) + '...'
    );
  };

  const getPostLabel = (allocation: Allocation) => {
    // Usar dados denormalizados da API se disponíveis
    if (allocation.post_name) {
      return allocation.post_code
        ? `${allocation.post_name} (${allocation.post_code})`
        : allocation.post_name;
    }
    // Fallback para lookup no map
    const post = postMap[allocation.post_id];
    return post ? `${post.name} (${post.code})` : allocation.post_id.substring(0, 8) + '...';
  };

  // Helper para dropdown de funcionários (sem objeto Allocation)
  const getEmployeeName = (employee: Employee) => {
    return employee?.full_name || employee?.name || employee?.email || employee?.registration || employee.id.substring(0, 8) + '...';
  };

  const getStatusBadge = (status: AllocationStatus) => {
    const base = 'inline-flex items-center px-2 py-1 rounded-full text-xs font-medium';
    switch (status) {
      case 'active':
        return `${base} bg-green-500/10 text-green-500`;
      case 'pending':
        return `${base} bg-yellow-500/10 text-yellow-500`;
      case 'suspended':
        return `${base} bg-orange-500/10 text-orange-500`;
      case 'terminated':
        return `${base} bg-red-500/10 text-red-500`;
      default:
        return `${base} bg-gray-500/10 text-gray-500`;
    }
  };

  const openDetail = (allocation: Allocation) => {
    setSelectedAllocation(allocation);
    setShowDetailModal(true);
  };

  const openTerminate = (allocation: Allocation) => {
    setSelectedAllocation(allocation);
    setTerminateData({ end_date: '', termination_reason: '', notes: '' });
    setTerminateError(null);
    setShowTerminateModal(true);
  };

  const handleTerminate = async () => {
    if (!selectedAllocation) return;

    if (!terminateData.end_date || !terminateData.termination_reason) {
      setTerminateError('Informe data e motivo do encerramento.');
      return;
    }

    setIsTerminating(true);
    setTerminateError(null);

    try {
      await terminateAllocationMutation.mutateAsync({ allocationId: selectedAllocation.id, data: terminateData });
      setShowTerminateModal(false);
      setSelectedAllocation(null);
      refresh();
    } catch (err) {
      setTerminateError(getErrorMessage(err));
    } finally {
      setIsTerminating(false);
    }
  };

  const openTransfer = (allocation: Allocation) => {
    setSelectedAllocation(allocation);
    setTransferData({
      new_post_id: '',
      transfer_date: new Date().toISOString().split('T')[0] ?? '',
      notes: '',
    });
    setTransferError(null);
    setShowTransferModal(true);
  };

  const handleTransfer = async () => {
    if (!selectedAllocation) return;

    if (!transferData.new_post_id) {
      setTransferError('Selecione o novo posto de trabalho.');
      return;
    }

    if (!transferData.transfer_date) {
      setTransferError('Informe a data da transferência.');
      return;
    }

    if (transferData.new_post_id === selectedAllocation.post_id) {
      setTransferError('Selecione um posto diferente do atual.');
      return;
    }

    setIsTransferring(true);
    setTransferError(null);

    try {
      // 1. Encerra a alocação atual
      await terminateAllocationMutation.mutateAsync({
        allocationId: selectedAllocation.id,
        data: {
          end_date: transferData.transfer_date,
          termination_reason: 'Transferência de posto',
          notes: transferData.notes || `Transferido para outro posto em ${new Date(transferData.transfer_date).toLocaleDateString('pt-BR')}`,
        },
      });

      // 2. Cria nova alocação no novo posto
      await createAllocationMutation.mutateAsync({
        data: {
          employee_id: selectedAllocation.employee_id,
          post_id: transferData.new_post_id,
          start_date: transferData.transfer_date,
          is_primary: selectedAllocation.is_primary,
          is_temporary: selectedAllocation.is_temporary,
          role: selectedAllocation.role || undefined,
          notes: `Transferido do posto anterior em ${new Date(transferData.transfer_date).toLocaleDateString('pt-BR')}`,
        },
      });

      setShowTransferModal(false);
      setSelectedAllocation(null);
      refresh();
    } catch (err) {
      setTransferError(getErrorMessage(err));
    } finally {
      setIsTransferring(false);
    }
  };

  // Filtra postos disponíveis para transferência (exclui o posto atual)
  const availablePostsForTransfer = useMemo(() => {
    if (!selectedAllocation) return posts;
    return posts.filter((post) => post.id !== selectedAllocation.post_id);
  }, [posts, selectedAllocation]);

  // Detectar conflitos: colaboradores alocados múltiplas vezes no mesmo dia
  const conflicts = useMemo(() => {
    const items = (allocations as any[]) || [];
    const byEmployeeDate: Record<string, any[]> = {};
    items.forEach((alloc: any) => {
      const key = `${alloc.employee_id}_${alloc.date || alloc.start_date || ''}`;
      if (!byEmployeeDate[key]) byEmployeeDate[key] = [];
      byEmployeeDate[key].push(alloc);
    });
    return Object.entries(byEmployeeDate)
      .filter(([, allocs]) => allocs.length > 1)
      .map(([key, allocs]) => ({
        key,
        employeeName: allocs[0].employee_name || 'Colaborador',
        date: allocs[0].date || allocs[0].start_date || '',
        count: allocs.length,
        posts: allocs.map((a: any) => a.post_name || a.post_id || 'Posto').join(', '),
      }));
  }, [allocations]);

  // Preparar dados para exportação
  const exportData = allocations.map((alloc) => ({
    'Colaborador': alloc.employee_name || '-',
    'Posto': alloc.post_name || '-',
    'Status': ALLOCATION_STATUS_LABELS[alloc.status as AllocationStatus] || alloc.status,
    'Data Início': new Date(alloc.start_date).toLocaleDateString('pt-BR'),
    'Data Fim': alloc.end_date ? new Date(alloc.end_date).toLocaleDateString('pt-BR') : 'Indeterminado',
    'Criado em': new Date(alloc.created_at).toLocaleDateString('pt-BR'),
  }));

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))]">
        <div className="animate-pulse-slow text-[hsl(var(--primary))]">
          <Users className="w-12 h-12" />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-grid">
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <PageHeader
          eyebrow="OPERACIONAL"
          title="Alocacoes"
          subtitle={`${total} alocacoes encontradas`}
          icon={<Users className="w-5 h-5" />}
          actions={
            <>
              <Link href="/modulos/operacional">
                <Button variant="ghost" size="sm">
                  <ArrowLeft className="w-4 h-4 mr-2" />
                  Operacional
                </Button>
              </Link>
              <ExportButton
                data={exportData}
                filename="alocacoes"
                pdfTitle="Relatório de Alocações"
                formats={['excel', 'pdf', 'csv']}
                size="sm"
                variant="outline"
                buttonText="Exportar"
              />
              <Button variant="primary" size="sm" onClick={() => setShowFormModal(true)}>
                <Plus className="w-4 h-4 mr-2" />
                Nova Alocação
              </Button>
            </>
          }
        />

        <div className="flex flex-col sm:flex-row gap-4 mb-6">
          <Button
            variant="outline"
            onClick={() => setShowFilters(!showFilters)}
            className={showFilters ? 'border-[hsl(var(--primary))]' : ''}
          >
            <Filter className="w-4 h-4 mr-2" />
            Filtros
          </Button>
          <Button variant="outline" onClick={refresh} disabled={isLoading}>
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          </Button>
        </div>

        {showFilters && (
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4 mb-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-medium text-[hsl(var(--foreground))]">Filtros</h3>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setFilters({})}
              >
                Limpar filtros
              </Button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <div>
                <label className="text-sm text-[hsl(var(--muted-foreground))] mb-1 block">
                  Posto
                </label>
                <select
                  className="w-full px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-sm"
                  value={filters.post_id || ''}
                  onChange={(e) =>
                    setFilters({ ...filters, post_id: e.target.value || undefined })
                  }
                >
                  <option value="">Todos</option>
                  {posts.map((post) => (
                    <option key={post.id} value={post.id}>
                      {post.name} ({post.code})
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-sm text-[hsl(var(--muted-foreground))] mb-1 block">
                  Funcionario
                </label>
                <select
                  className="w-full px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-sm"
                  value={filters.employee_id || ''}
                  onChange={(e) =>
                    setFilters({ ...filters, employee_id: e.target.value || undefined })
                  }
                >
                  <option value="">Todos</option>
                  {employees.map((employee) => (
                    <option key={employee.id} value={employee.id}>
                      {getEmployeeName(employee)}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-sm text-[hsl(var(--muted-foreground))] mb-1 block">
                  Status
                </label>
                <select
                  className="w-full px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-sm"
                  value={filters.status || ''}
                  onChange={(e) =>
                    setFilters({
                      ...filters,
                      status: (e.target.value || undefined) as AllocationStatus | undefined,
                    })
                  }
                >
                  <option value="">Todos</option>
                  {Object.entries(ALLOCATION_STATUS_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-sm text-[hsl(var(--muted-foreground))] mb-1 block">
                  Vigentes
                </label>
                <div className="flex items-center gap-2 h-10">
                  <input
                    type="checkbox"
                    checked={filters.is_current === true}
                    onChange={(e) =>
                      setFilters({
                        ...filters,
                        is_current: e.target.checked ? true : undefined,
                      })
                    }
                    className="rounded border-[hsl(var(--border))]"
                  />
                  <span className="text-sm">Apenas vigentes</span>
                </div>
              </div>
              <div>
                <label className="text-sm text-[hsl(var(--muted-foreground))] mb-1 block">
                  Inicio de
                </label>
                <Input
                  type="date"
                  value={filters.start_date_from || ''}
                  onChange={(e) =>
                    setFilters({
                      ...filters,
                      start_date_from: e.target.value || undefined,
                    })
                  }
                />
              </div>
              <div>
                <label className="text-sm text-[hsl(var(--muted-foreground))] mb-1 block">
                  Inicio ate
                </label>
                <Input
                  type="date"
                  value={filters.start_date_to || ''}
                  onChange={(e) =>
                    setFilters({
                      ...filters,
                      start_date_to: e.target.value || undefined,
                    })
                  }
                />
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 mb-6 flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-red-500" />
            <p className="text-red-500">{error instanceof Error ? error.message : 'Erro ao carregar alocações'}</p>
            <Button variant="outline" size="sm" onClick={() => refresh()} className="ml-auto">
              Tentar novamente
            </Button>
          </div>
        )}

        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-pulse-slow text-[hsl(var(--primary))]">
              <Users className="w-8 h-8" />
            </div>
          </div>
        ) : allocations.length === 0 ? (
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-12 text-center">
            <Users className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
            <h3 className="text-lg font-medium text-[hsl(var(--foreground))] mb-2">
              Nenhuma alocacao encontrada
            </h3>
            <p className="text-sm text-[hsl(var(--muted-foreground))] mb-4">
              Crie uma nova alocacao para iniciar o vinculo
            </p>
            <Button onClick={() => setShowFormModal(true)}>
              <Plus className="w-4 h-4 mr-2" />
              Nova Alocação
            </Button>
          </div>
        ) : (
          <>
            {conflicts.length > 0 && (
              <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 mb-6">
                <div className="flex items-center gap-2 mb-3">
                  <AlertCircle className="w-5 h-5 text-red-500" />
                  <h3 className="font-semibold text-red-500">{conflicts.length} Conflito(s) de Alocação Detectado(s)</h3>
                </div>
                <div className="space-y-2">
                  {conflicts.map(c => (
                    <div key={c.key} className="bg-[hsl(var(--background))]/60 rounded-lg px-3 py-2 text-sm">
                      <span className="font-medium text-[hsl(var(--foreground))]">{c.employeeName}</span>
                      <span className="text-[hsl(var(--muted-foreground))]"> alocado {c.count}× em {c.date ? new Date(c.date).toLocaleDateString('pt-BR') : '—'}: </span>
                      <span className="text-red-500">{c.posts}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-[hsl(var(--muted))]">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wider">
                        Funcionario
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wider">
                        Posto
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wider">
                        Inicio
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wider">
                        Status
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wider">
                        Ações
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[hsl(var(--border))]">
                    {allocations.map((allocation) => (
                      <tr
                        key={allocation.id}
                        className="hover:bg-[hsl(var(--muted))]/50 transition-colors cursor-pointer"
                        onClick={() => openDetail(allocation)}
                      >
                        <td className="px-4 py-4">
                          <div className="flex items-center gap-3">
                            <div className="w-9 h-9 rounded-lg bg-green-500/10 flex items-center justify-center flex-shrink-0">
                              <Users className="w-4 h-4 text-green-500" />
                            </div>
                            <div>
                              <p className="font-medium text-[hsl(var(--foreground))]">
                                {getEmployeeLabel(allocation)}
                              </p>
                              {allocation.employee_matricula && (
                                <p className="text-xs text-[hsl(var(--muted-foreground))]">
                                  Mat: {allocation.employee_matricula}
                                </p>
                              )}
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-4">
                          <p className="text-sm text-[hsl(var(--foreground))]">
                            {getPostLabel(allocation)}
                          </p>
                        </td>
                        <td className="px-4 py-4">
                          <div className="flex items-center gap-2">
                            <Calendar className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />
                            <span className="text-sm text-[hsl(var(--foreground))]">
                              {new Date(allocation.start_date).toLocaleDateString('pt-BR')}
                            </span>
                          </div>
                        </td>
                        <td className="px-4 py-4">
                          <span className={getStatusBadge(allocation.status as AllocationStatus)}>
                            {ALLOCATION_STATUS_LABELS[allocation.status as AllocationStatus] || allocation.status}
                          </span>
                        </td>
                        <td
                          className="px-4 py-4 text-right"
                          onClick={(event) => event.stopPropagation()}
                        >
                          <div className="flex items-center justify-end gap-1">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => openDetail(allocation)}
                              title="Visualizar"
                            >
                              <Eye className="w-4 h-4" />
                            </Button>
                            {allocation.status === 'active' && (
                              <>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => openTransfer(allocation)}
                                  title="Transferir de Posto"
                                  className="text-blue-500 hover:text-blue-600 hover:bg-blue-500/10"
                                >
                                  <ArrowRightLeft className="w-4 h-4" />
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => openTerminate(allocation)}
                                  title="Encerrar"
                                  className="text-red-500 hover:text-red-600 hover:bg-red-500/10"
                                >
                                  <Ban className="w-4 h-4" />
                                </Button>
                              </>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-4">
                <p className="text-sm text-[hsl(var(--muted-foreground))]">
                  Mostrando {(page - 1) * pageSize + 1} a {Math.min(page * pageSize, total)} de {total}
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
          </>
        )}
      </main>

      <AllocationDetailModal
        allocation={selectedAllocation}
        isOpen={showDetailModal}
        onClose={() => {
          setShowDetailModal(false);
          setSelectedAllocation(null);
        }}
        employeeName={selectedAllocation ? getEmployeeLabel(selectedAllocation) : undefined}
        postName={selectedAllocation ? getPostLabel(selectedAllocation) : undefined}
        onTerminate={selectedAllocation?.status === 'active' ? () => openTerminate(selectedAllocation) : undefined}
      />

      <AllocationFormModal
        isOpen={showFormModal}
        onClose={() => setShowFormModal(false)}
        onSuccess={refresh}
        posts={posts}
        employees={employees}
      />

      <Modal
        isOpen={showTerminateModal}
        onClose={() => setShowTerminateModal(false)}
        title="Encerrar Alocação"
        description="Informe data e motivo do encerramento"
        size="sm"
      >
        <div className="space-y-4">
          {terminateError && (
            <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3 text-red-500 text-sm">
              {terminateError}
            </div>
          )}
          <div>
            <label className="block text-sm text-[hsl(var(--muted-foreground))] mb-1">
              Data de encerramento *
            </label>
            <Input
              type="date"
              value={terminateData.end_date}
              onChange={(e) => setTerminateData({ ...terminateData, end_date: e.target.value })}
            />
          </div>
          <div>
            <label className="block text-sm text-[hsl(var(--muted-foreground))] mb-1">
              Motivo *
            </label>
            <Input
              value={terminateData.termination_reason}
              onChange={(e) =>
                setTerminateData({ ...terminateData, termination_reason: e.target.value })
              }
              placeholder="Ex: Substituicao definitiva"
            />
          </div>
          <div>
            <label className="block text-sm text-[hsl(var(--muted-foreground))] mb-1">
              Observações
            </label>
            <textarea
              value={terminateData.notes || ''}
              onChange={(e) => setTerminateData({ ...terminateData, notes: e.target.value })}
              rows={3}
              className="w-full px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-sm resize-none"
            />
          </div>
        </div>
        <ModalFooter>
          <Button variant="outline" onClick={() => setShowTerminateModal(false)} disabled={isTerminating}>
            Cancelar
          </Button>
          <Button variant="primary" onClick={handleTerminate} disabled={isTerminating}>
            {isTerminating ? 'Encerrando...' : 'Encerrar'}
          </Button>
        </ModalFooter>
      </Modal>

      {/* Modal de Transferência de Posto */}
      <Modal
        isOpen={showTransferModal}
        onClose={() => setShowTransferModal(false)}
        title="Transferir Funcionário"
        description={selectedAllocation ? `Transferir ${selectedAllocation.employee_name || 'funcionário'} para outro posto de trabalho` : 'Selecione o novo posto'}
        size="md"
      >
        <div className="space-y-4">
          {transferError && (
            <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3 text-red-500 text-sm">
              {transferError}
            </div>
          )}

          {/* Informação do posto atual */}
          {selectedAllocation && (
            <div className="bg-[hsl(var(--muted))]/50 rounded-lg p-3">
              <p className="text-sm text-[hsl(var(--muted-foreground))]">Posto atual:</p>
              <p className="font-medium text-[hsl(var(--foreground))]">
                {selectedAllocation.post_name || getPostLabel(selectedAllocation)}
              </p>
            </div>
          )}

          <div>
            <label className="block text-sm text-[hsl(var(--muted-foreground))] mb-1">
              Novo Posto de Trabalho *
            </label>
            <select
              className="w-full px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-sm"
              value={transferData.new_post_id}
              onChange={(e) => setTransferData({ ...transferData, new_post_id: e.target.value })}
            >
              <option value="">Selecione o novo posto...</option>
              {availablePostsForTransfer.map((post) => (
                <option key={post.id} value={post.id}>
                  {post.name} ({post.code})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm text-[hsl(var(--muted-foreground))] mb-1">
              Data da Transferência *
            </label>
            <Input
              type="date"
              value={transferData.transfer_date}
              onChange={(e) => setTransferData({ ...transferData, transfer_date: e.target.value })}
            />
          </div>

          <div>
            <label className="block text-sm text-[hsl(var(--muted-foreground))] mb-1">
              Observações
            </label>
            <textarea
              value={transferData.notes}
              onChange={(e) => setTransferData({ ...transferData, notes: e.target.value })}
              rows={3}
              placeholder="Motivo da transferência ou observações adicionais..."
              className="w-full px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-sm resize-none"
            />
          </div>

          <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-lg p-3">
            <p className="text-sm text-yellow-600">
              <strong>Atenção:</strong> Esta ação irá encerrar a alocação atual e criar uma nova no posto selecionado.
            </p>
          </div>
        </div>
        <ModalFooter>
          <Button variant="outline" onClick={() => setShowTransferModal(false)} disabled={isTransferring}>
            Cancelar
          </Button>
          <Button variant="primary" onClick={handleTransfer} disabled={isTransferring}>
            {isTransferring ? 'Transferindo...' : 'Confirmar Transferência'}
          </Button>
        </ModalFooter>
      </Modal>
    </div>
  );
}
