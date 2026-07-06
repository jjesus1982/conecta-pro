'use client';

import { UserCheck, Search, Filter, Eye, ArrowLeft, AlertCircle, RefreshCw, Mail, Phone, BadgeCheck, Building } from 'lucide-react';
import { useEffect, useState, useRef } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { PageHeader } from '@/components/ui/page-header';
import { useAuth } from '@/hooks/useAuth';
import { useEmployees } from '@/hooks/operacional/useEmployees';
import { getErrorMessage } from '@/lib/api';
import type { Employee } from '@/types/operacional';

// Tipo estendido com campos do Solides
type SolidesEmployeeExtended = Employee & {
  cargo?: string;
  departamento?: string;
  telefone?: string;
  data_admissao?: string;
};

export default function AgentesPage() {
  const router = useRouter();
  const { isLoading: authLoading, isAuthenticated } = useAuth();

  const { data: employeesData, isLoading, error: queryError, refetch } = useEmployees();
  const employeesRaw = employeesData?.items ?? [];
  const employees = employeesRaw as unknown as SolidesEmployeeExtended[];
  const total = employeesData?.total ?? employees.length;
  const [error, setError] = useState<string | null>(null);
  const [dataSource, setDataSource] = useState<string>('local');

  const [searchTerm, setSearchTerm] = useState('');
  const [debouncedSearchTerm, setDebouncedSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [showFilters, setShowFilters] = useState(false);

  // Modal state
  const [selectedEmployee, setSelectedEmployee] = useState<SolidesEmployeeExtended | null>(null);
  const [showDetailModal, setShowDetailModal] = useState(false);

  // Debounce search

  useEffect(() => {
    const timer = setTimeout(() => {

      setDebouncedSearchTerm(searchTerm);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchTerm]);


  // Redirecionar se nao autenticado
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [authLoading, isAuthenticated, router]);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [authLoading, isAuthenticated, router]);

  useEffect(() => {
    if (queryError) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- Form sync
      setError(String(queryError));
    }
  }, [queryError]);

  // Handlers
  const handleView = (employee: SolidesEmployeeExtended) => {
    setSelectedEmployee(employee);
    setShowDetailModal(true);
  };

  const handleRefresh = () => {
    refetch();
  };

  const clearFilters = () => {
    setSearchTerm('');
    setStatusFilter('');
  };

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))]">
        <div className="animate-pulse-slow text-[hsl(var(--primary))]">
          <UserCheck className="w-12 h-12" />
        </div>
      </div>
    );
  }

  // Filtrar agentes localmente
  const filteredEmployees = employees.filter((emp) => {
    // Filtro de busca
    if (debouncedSearchTerm) {
      const searchLower = debouncedSearchTerm.toLowerCase();
      const matchesSearch =
        emp.full_name?.toLowerCase().includes(searchLower) ||
        emp.name?.toLowerCase().includes(searchLower) ||
        emp.email?.toLowerCase().includes(searchLower) ||
        emp.registration?.toLowerCase().includes(searchLower) ||
        emp.cargo?.toLowerCase().includes(searchLower);
      if (!matchesSearch) return false;
    }
    // Filtro de status
    if (statusFilter && emp.status?.toLowerCase() !== statusFilter.toLowerCase()) {
      return false;
    }
    return true;
  });

  const getStatusColor = (status?: string | null) => {
    switch (status?.toLowerCase()) {
      case 'ativo':
        return 'bg-green-500/10 text-green-500';
      case 'inativo':
        return 'bg-gray-500/10 text-gray-500';
      case 'ferias':
        return 'bg-blue-500/10 text-blue-500';
      case 'afastado':
        return 'bg-yellow-500/10 text-yellow-500';
      case 'desligado':
        return 'bg-red-500/10 text-red-500';
      default:
        return 'bg-gray-500/10 text-gray-500';
    }
  };

  const activeCount = employees.filter(e => e.status?.toLowerCase() === 'ativo').length;

  return (
    <div className="min-h-screen bg-grid">
      {/* Main content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <PageHeader
          eyebrow="OPERACIONAL"
          title="Colaboradores"
          subtitle={`${total} colaboradores ${dataSource ? `(${dataSource})` : ''}`}
          icon={<UserCheck className="w-5 h-5" />}
          actions={
            <Link href="/modulos/operacional">
              <Button variant="ghost" size="sm">
                <ArrowLeft className="w-4 h-4 mr-2" />
                Operacional
              </Button>
            </Link>
          }
        />

        {/* Stats Cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-emerald-500/10 flex items-center justify-center">
                <UserCheck className="w-5 h-5 text-emerald-500" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                  {total}
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Total</p>
              </div>
            </div>
          </div>

          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-green-500/10 flex items-center justify-center">
                <BadgeCheck className="w-5 h-5 text-green-500" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                  {activeCount}
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Ativos</p>
              </div>
            </div>
          </div>

          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
                <Building className="w-5 h-5 text-blue-500" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                  -
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Alocados</p>
              </div>
            </div>
          </div>

          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-orange-500/10 flex items-center justify-center">
                <AlertCircle className="w-5 h-5 text-orange-500" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                  -
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Disponiveis</p>
              </div>
            </div>
          </div>
        </div>

        {/* Search and Filters */}
        <div className="flex flex-col sm:flex-row gap-4 mb-6">
          <div className="flex-1">
            <Input
              type="search"
              placeholder="Buscar por nome, email ou matricula..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              icon={<Search className="w-4 h-4" />}
            />
          </div>
          <Button
            variant="outline"
            onClick={() => setShowFilters(!showFilters)}
            className={showFilters ? 'border-[hsl(var(--primary))]' : ''}
          >
            <Filter className="w-4 h-4 mr-2" />
            Filtros
            {statusFilter && (
              <span className="ml-2 w-5 h-5 rounded-full bg-[hsl(var(--primary))] text-white text-xs flex items-center justify-center">
                1
              </span>
            )}
          </Button>
          <Button variant="outline" onClick={handleRefresh} disabled={isLoading}>
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          </Button>
        </div>

        {/* Filters Panel */}
        {showFilters && (
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4 mb-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-medium text-[hsl(var(--foreground))]">Filtros</h3>
              <Button variant="ghost" size="sm" onClick={clearFilters}>
                Limpar filtros
              </Button>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div>
                <label className="text-sm text-[hsl(var(--muted-foreground))] mb-1 block">
                  Status
                </label>
                <select
                  className="w-full px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))]"
                  value={statusFilter}
                  onChange={(e) => {
                    setStatusFilter(e.target.value);
                  }}
                >
                  <option value="">Todos</option>
                  <option value="ativo">Ativo</option>
                  <option value="inativo">Inativo</option>
                  <option value="ferias">Férias</option>
                  <option value="afastado">Afastado</option>
                  <option value="desligado">Desligado</option>
                </select>
              </div>
            </div>
          </div>
        )}

        {/* Error state */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 mb-6 flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-red-500" />
            <p className="text-red-500">{error}</p>
            <Button variant="outline" size="sm" onClick={handleRefresh} className="ml-auto">
              Tentar novamente
            </Button>
          </div>
        )}

        {/* Loading state */}
        {isLoading && (
          <div className="flex items-center justify-center py-12">
            <div className="animate-pulse-slow text-[hsl(var(--primary))]">
              <UserCheck className="w-8 h-8" />
            </div>
          </div>
        )}

        {/* Employees Table */}
        {!isLoading && !error && (
          <>
            <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-[hsl(var(--muted))]">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wider">
                        Colaborador
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wider">
                        Cargo
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wider">
                        Contato
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
                    {filteredEmployees.map((employee) => (
                      <tr
                        key={employee.id}
                        className="hover:bg-[hsl(var(--muted))]/50 transition-colors cursor-pointer"
                        onClick={() => handleView(employee)}
                      >
                        <td className="px-4 py-4">
                          <div className="flex items-center gap-3">
                            <div className="w-10 h-10 rounded-full bg-emerald-500/10 flex items-center justify-center flex-shrink-0">
                              <span className="text-emerald-500 font-semibold text-sm">
                                {(employee.full_name || employee.name || '?').charAt(0).toUpperCase()}
                              </span>
                            </div>
                            <div>
                              <p className="font-medium text-[hsl(var(--foreground))]">
                                {employee.full_name || employee.name || '-'}
                              </p>
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-4">
                          <span className="text-sm text-[hsl(var(--foreground))]">
                            {employee.cargo || '-'}
                          </span>
                        </td>
                        <td className="px-4 py-4">
                          <div className="flex flex-col gap-1">
                            {employee.email && (
                              <div className="flex items-center gap-1 text-sm text-[hsl(var(--muted-foreground))]">
                                <Mail className="w-3 h-3" />
                                <span className="truncate max-w-[200px]">{employee.email}</span>
                              </div>
                            )}
                            {employee.telefone && (
                              <div className="flex items-center gap-1 text-sm text-[hsl(var(--muted-foreground))]">
                                <Phone className="w-3 h-3" />
                                <span>{employee.telefone}</span>
                              </div>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-4">
                          <span
                            className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium capitalize ${getStatusColor(
                              employee.status
                            )}`}
                          >
                            {employee.status || 'N/A'}
                          </span>
                        </td>
                        <td className="px-4 py-4 text-right" onClick={(e) => e.stopPropagation()}>
                          <div className="flex items-center justify-end gap-1">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleView(employee)}
                              title="Visualizar"
                            >
                              <Eye className="w-4 h-4" />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Empty state */}
              {employees.length === 0 && !isLoading && (
                <div className="text-center py-12">
                  <UserCheck className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
                  <h3 className="text-lg font-medium text-[hsl(var(--foreground))]">
                    Nenhum colaborador encontrado
                  </h3>
                  <p className="text-[hsl(var(--muted-foreground))] mt-1 mb-4">
                    {searchTerm || statusFilter
                      ? 'Tente ajustar os filtros de busca'
                      : 'Os colaboradores sao sincronizados automaticamente do Solides'}
                  </p>
                </div>
              )}
            </div>

            {/* Info */}
            {employees.length > 0 && (
              <div className="flex items-center justify-between mt-4">
                <p className="text-sm text-[hsl(var(--muted-foreground))]">
                  Mostrando {employees.length} colaboradores
                </p>
              </div>
            )}
          </>
        )}
      </main>

      {/* Detail Modal */}
      {showDetailModal && selectedEmployee && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50">
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl w-full max-w-md shadow-xl">
            <div className="p-6">
              <div className="flex items-center gap-4 mb-6">
                <div className="w-16 h-16 rounded-full bg-emerald-500/10 flex items-center justify-center">
                  <span className="text-emerald-500 font-bold text-2xl">
                    {(selectedEmployee.full_name || selectedEmployee.name || '?').charAt(0).toUpperCase()}
                  </span>
                </div>
                <div>
                  <h2 className="text-xl font-semibold text-[hsl(var(--foreground))]">
                    {selectedEmployee.full_name || selectedEmployee.name || '-'}
                  </h2>
                  <span
                    className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium capitalize ${getStatusColor(
                      selectedEmployee.status
                    )}`}
                  >
                    {selectedEmployee.status || 'N/A'}
                  </span>
                </div>
              </div>

              <div className="space-y-4">
                {selectedEmployee.cargo && (
                  <div className="flex items-center gap-3">
                    <BadgeCheck className="w-5 h-5 text-[hsl(var(--muted-foreground))]" />
                    <div>
                      <p className="text-xs text-[hsl(var(--muted-foreground))]">Cargo</p>
                      <p className="text-[hsl(var(--foreground))]">{selectedEmployee.cargo}</p>
                    </div>
                  </div>
                )}

                {selectedEmployee.departamento && (
                  <div className="flex items-center gap-3">
                    <Building className="w-5 h-5 text-[hsl(var(--muted-foreground))]" />
                    <div>
                      <p className="text-xs text-[hsl(var(--muted-foreground))]">Departamento</p>
                      <p className="text-[hsl(var(--foreground))]">{selectedEmployee.departamento}</p>
                    </div>
                  </div>
                )}

                {selectedEmployee.email && (
                  <div className="flex items-center gap-3">
                    <Mail className="w-5 h-5 text-[hsl(var(--muted-foreground))]" />
                    <div>
                      <p className="text-xs text-[hsl(var(--muted-foreground))]">Email</p>
                      <p className="text-[hsl(var(--foreground))]">{selectedEmployee.email}</p>
                    </div>
                  </div>
                )}

                {selectedEmployee.telefone && (
                  <div className="flex items-center gap-3">
                    <Phone className="w-5 h-5 text-[hsl(var(--muted-foreground))]" />
                    <div>
                      <p className="text-xs text-[hsl(var(--muted-foreground))]">Telefone</p>
                      <p className="text-[hsl(var(--foreground))]">{selectedEmployee.telefone}</p>
                    </div>
                  </div>
                )}

                {selectedEmployee.registration && (
                  <div className="flex items-center gap-3">
                    <BadgeCheck className="w-5 h-5 text-[hsl(var(--muted-foreground))]" />
                    <div>
                      <p className="text-xs text-[hsl(var(--muted-foreground))]">Matricula</p>
                      <p className="text-[hsl(var(--foreground))]">{selectedEmployee.registration}</p>
                    </div>
                  </div>
                )}
              </div>

              <div className="mt-6 flex justify-end">
                <Button
                  variant="outline"
                  onClick={() => {
                    setShowDetailModal(false);
                    setSelectedEmployee(null);
                  }}
                >
                  Fechar
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
