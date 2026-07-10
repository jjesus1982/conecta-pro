'use client';

import { Users, Search, RefreshCw, AlertCircle, User, Mail, Building2, Briefcase, Phone, Calendar, Edit, Eye, MoreHorizontal, Zap, Plus } from 'lucide-react';
import { useState, useEffect, useMemo, useRef } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { PageHeader } from '@/components/ui/page-header';
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { ExportButton } from '@/components/ui/export-button';
import { useEmployees, useUpdateEmployee, useEmployeesFromSolides } from '@/hooks/operacional/useEmployees';
import { useCctCargos, cargoLabel } from '@/hooks/hr/useCctCargos';
import { customInstance } from '@/lib/api-client';

// Tipo normalizado para exibição
interface Employee {
  id: string;
  nome: string;
  email?: string | null;
  matricula?: string | null;
  status?: string | null;
  cargo?: string | null;
  cct_cargo_id?: string | null;
  departamento?: string | null;
  telefone?: string | null;
  data_admissao?: string | null;
  insalubridade_percentual?: number | null;
  periculosidade_percentual?: number | null;
  adicional_ronda_percentual?: number | null;
  fonte: 'local' | 'solides';
}

export default function ColaboradoresPage() {
  const router = useRouter();
  // Tela de gestão de pessoas: busca TODOS os status (ativos + afastados + inativos...)
  // via status='todos' — o default do backend segue 'ativo' p/ não quebrar dropdowns.
  const { data: localData, isLoading: localLoading, error: localError, refetch: refetchLocal } = useEmployees({ status: 'todos', page_size: 500 });
  const { data: solidesData, isLoading: solidesLoading, refetch: refetchSolides } = useEmployeesFromSolides(
    undefined,
    { query: { retry: 1 } }
  );

  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [saving, setSaving] = useState(false);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [selectedEmployee, setSelectedEmployee] = useState<Employee | null>(null);
  const [editForm, setEditForm] = useState({ nome: '', email: '', cargo: '', cct_cargo_id: '', departamento: '', telefone: '', status: '', insalubridade_percentual: '', periculosidade_percentual: '', adicional_ronda_percentual: '' });
  const [newDialogOpen, setNewDialogOpen] = useState(false);
  const [newForm, setNewForm] = useState({ nome: '', email: '', matricula: '', cargo: '', cct_cargo_id: '', departamento: '', telefone: '', insalubridade_percentual: '', periculosidade_percentual: '', adicional_ronda_percentual: '' });
  const { cargos: cctCargos, loading: cargosLoading } = useCctCargos();
  const [newSaving, setNewSaving] = useState(false);
  const [newError, setNewError] = useState<string | null>(null);
  const searchParams = useSearchParams();
  const didAutoOpen = useRef(false);

  const loading = localLoading || solidesLoading;

  // Montar mapa de dados do Sólides indexado por nome normalizado
  const solidesMap = useMemo(() => {
    const map = new Map<string, Record<string, string | null | undefined>>();
    const items = (solidesData as any)?.items ?? [];
    for (const s of items) {
      const key = (s.nome || s.name || '').toLowerCase().trim();
      if (key) map.set(key, s);
    }
    return map;
  }, [solidesData]);

  // Combinar dados locais enriquecidos com Sólides
  const employees: Employee[] = useMemo(() => {
    const localItems = (localData as any)?.items ?? [];
    return localItems.map((raw: any): Employee => {
      const nome = raw.nome || raw.full_name || raw.name || '';
      const solidesMatch = solidesMap.get(nome.toLowerCase().trim());
      return {
        id: raw.id,
        nome,
        email: raw.email,
        matricula: raw.matricula || raw.registration || solidesMatch?.matricula,
        status: raw.status || solidesMatch?.status,
        cargo: raw.cargo || solidesMatch?.cargo,
        cct_cargo_id: raw.cct_cargo_id ?? null,
        departamento: raw.departamento || solidesMatch?.departamento,
        telefone: raw.telefone || solidesMatch?.telefone,
        data_admissao: raw.data_admissao || solidesMatch?.data_admissao,
        insalubridade_percentual: raw.insalubridade_percentual ?? null,
        periculosidade_percentual: raw.periculosidade_percentual ?? null,
        adicional_ronda_percentual: raw.adicional_ronda_percentual ?? null,
        fonte: solidesMatch ? 'solides' : 'local',
      };
    });
  }, [localData, solidesMap]);

  const total = (localData as any)?.total ?? employees.length;
  const solidesTotal = (solidesData as any)?.total ?? 0;

  const { mutateAsync: updateEmployeeMutation } = useUpdateEmployee();

  const handleEdit = (employee: Employee) => {
    setSelectedEmployee(employee);
    setEditForm({
      nome: employee.nome || '',
      email: employee.email || '',
      cargo: employee.cargo || '',
      cct_cargo_id: employee.cct_cargo_id || '',
      departamento: employee.departamento || '',
      telefone: employee.telefone || '',
      status: employee.status || 'ativo',
      insalubridade_percentual: employee.insalubridade_percentual != null ? String(employee.insalubridade_percentual) : '',
      periculosidade_percentual: employee.periculosidade_percentual != null ? String(employee.periculosidade_percentual) : '',
      adicional_ronda_percentual: employee.adicional_ronda_percentual != null ? String(employee.adicional_ronda_percentual) : '',
    });
    setEditDialogOpen(true);
  };

  const handleSaveEdit = async () => {
    if (!selectedEmployee) return;
    setSaving(true);
    try {
      // Adicionais são float (0-40 / 0-30) — converter de string para número; '' vira null (limpa o campo)
      const { insalubridade_percentual, periculosidade_percentual, adicional_ronda_percentual, ...rest } = editForm;
      const payload: Record<string, unknown> = {
        ...rest,
        insalubridade_percentual: insalubridade_percentual === '' ? null : parseFloat(insalubridade_percentual),
        periculosidade_percentual: periculosidade_percentual === '' ? null : parseFloat(periculosidade_percentual),
        adicional_ronda_percentual: adicional_ronda_percentual === '' ? null : parseFloat(adicional_ronda_percentual),
      };
      await updateEmployeeMutation({ employeeId: selectedEmployee.id, data: payload });
      setEditDialogOpen(false);
      refetchLocal();
      refetchSolides();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Erro ao salvar alterações');
    } finally {
      setSaving(false);
    }
  };

  // Auto-open new dialog when ?novo=1 param is present (from CommandPalette)
  useEffect(() => {
    if (!didAutoOpen.current && searchParams?.get('novo') === '1') {
      didAutoOpen.current = true;
      setNewDialogOpen(true);
    }
  }, [searchParams]);

  const handleCreateEmployee = async () => {
    if (!newForm.nome.trim()) { setNewError('Nome é obrigatório'); return; }
    if (!newForm.email.trim()) { setNewError('E-mail é obrigatório'); return; }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(newForm.email)) { setNewError('E-mail inválido'); return; }
    if (!newForm.matricula.trim()) { setNewError('Matrícula é obrigatória'); return; }
    setNewSaving(true);
    setNewError(null);
    try {
      const { insalubridade_percentual, periculosidade_percentual, adicional_ronda_percentual, ...rest } = newForm;
      const payload: Record<string, unknown> = { ...rest, status: 'ativo' };
      if (insalubridade_percentual !== '') payload.insalubridade_percentual = parseFloat(insalubridade_percentual);
      if (periculosidade_percentual !== '') payload.periculosidade_percentual = parseFloat(periculosidade_percentual);
      if (adicional_ronda_percentual !== '') payload.adicional_ronda_percentual = parseFloat(adicional_ronda_percentual);
      await customInstance({ url: '/api/v1/operacional/employees/', method: 'POST', data: payload });
      setNewDialogOpen(false);
      setNewForm({ nome: '', email: '', matricula: '', cargo: '', cct_cargo_id: '', departamento: '', telefone: '', insalubridade_percentual: '', periculosidade_percentual: '', adicional_ronda_percentual: '' });
      refetchLocal();
    } catch (err: unknown) {
      setNewError(err instanceof Error ? err.message : 'Erro ao criar colaborador');
    } finally {
      setNewSaving(false);
    }
  };

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => {
    if (localError) setError(String(localError));
  }, [localError]);

  const filteredEmployees = employees.filter((emp) => {
    const matchSearch = !debouncedSearch || (
      emp.nome.toLowerCase().includes(debouncedSearch.toLowerCase()) ||
      (emp.email || '').toLowerCase().includes(debouncedSearch.toLowerCase()) ||
      (emp.matricula || '').toLowerCase().includes(debouncedSearch.toLowerCase()) ||
      (emp.cargo || '').toLowerCase().includes(debouncedSearch.toLowerCase()) ||
      (emp.departamento || '').toLowerCase().includes(debouncedSearch.toLowerCase())
    );
    const empStatus = (emp.status || '').toLowerCase();
    const matchStatus =
      statusFilter === 'all' ||
      empStatus === statusFilter ||
      // 'afastado' cobre também o status real do banco 'afastado_inss'
      (statusFilter === 'afastado' && empStatus.startsWith('afastado'));
    return matchSearch && matchStatus;
  });

  // Contadores derivados do campo STATUS real dos employees (ativo/afastado_inss/inativo/demitido)
  // — nunca da flag is_active (podre no banco).
  const activeCount = employees.filter((e) => (e.status || '').toLowerCase() === 'ativo').length;
  const afastadosCount = employees.filter((e) =>
    (e.status || '').toLowerCase().startsWith('afastado')
  ).length;

  const getStatusBadge = (status?: string | null) => {
    if (!status) return <Badge variant="outline">-</Badge>;
    const s = status.toLowerCase();
    if (s === 'ativo' || s === 'active') return <Badge className="bg-green-100 text-green-800">Ativo</Badge>;
    if (s === 'inativo' || s === 'inactive') return <Badge variant="secondary">Inativo</Badge>;
    if (s === 'afastado_inss') return <Badge className="bg-yellow-100 text-yellow-800">Afastado (INSS)</Badge>;
    if (s === 'afastado' || s === 'on_leave') return <Badge className="bg-yellow-100 text-yellow-800">Afastado</Badge>;
    if (s === 'demitido') return <Badge className="bg-red-100 text-red-800">Demitido</Badge>;
    if (s === 'ferias') return <Badge className="bg-blue-100 text-blue-800">Férias</Badge>;
    return <Badge variant="outline">{status}</Badge>;
  };

  const formatDate = (dateStr?: string | null) => {
    if (!dateStr) return '-';
    try { return new Date(dateStr).toLocaleDateString('pt-BR'); } catch { return dateStr; }
  };

  const exportData = filteredEmployees.map((emp) => ({
    'Matrícula': emp.matricula || '-',
    'Nome': emp.nome || '-',
    'Email': emp.email || '-',
    'Cargo': emp.cargo || '-',
    'Departamento': emp.departamento || '-',
    'Telefone': emp.telefone || '-',
    'Data Admissão': formatDate(emp.data_admissao),
    'Status': emp.status || '-',
  }));

  return (
    <div className="space-y-6">
      {/* Header */}
      <PageHeader
        eyebrow="OPERACIONAL"
        title="Colaboradores"
        subtitle={`${total} colaboradores • ${solidesTotal > 0 ? `${solidesTotal} no Sólides DP` : 'carregando Sólides...'}`}
        icon={<Users className="h-6 w-6" />}
        actions={
          <>
            <Badge variant="outline" className="text-xs gap-1">
              <Zap className="h-3 w-3 text-yellow-500" />
              Enriquecido com Sólides DP
            </Badge>
            <Button onClick={() => setNewDialogOpen(true)}>
              <Plus className="h-4 w-4 mr-2" />
              Novo Colaborador
            </Button>
            <ExportButton
              data={exportData}
              filename="colaboradores"
              pdfTitle="Relatório de Colaboradores"
              formats={['excel', 'pdf', 'csv']}
              size="sm"
              variant="outline"
              buttonText="Exportar"
            />
            <Button variant="outline" onClick={() => { refetchLocal(); refetchSolides(); }} disabled={loading}>
              <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
              Atualizar
            </Button>
          </>
        }
      />

      {/* Filtros */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-col md:flex-row gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Buscar por nome, email, matrícula, cargo..."
                className="pl-10"
              />
            </div>
            <Select value={statusFilter} onValueChange={setStatusFilter} aria-label="Status Filter">
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos os status</SelectItem>
                <SelectItem value="ativo">Ativos</SelectItem>
                <SelectItem value="inativo">Inativos</SelectItem>
                <SelectItem value="afastado">Afastados (INSS)</SelectItem>
                <SelectItem value="demitido">Demitidos</SelectItem>
                <SelectItem value="ferias">Férias</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-destructive" />
          <p className="text-sm text-destructive flex-1">{error}</p>
          <Button variant="outline" size="sm" onClick={() => { refetchLocal(); setError(null); }}>
            Tentar novamente
          </Button>
        </div>
      )}

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent><div className="font-data text-2xl font-semibold tabular-nums">{total}</div></CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Ativos</CardTitle>
            <User className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums">{activeCount}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Afastados</CardTitle>
            <User className="h-4 w-4 text-yellow-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums">{afastadosCount}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Exibindo</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent><div className="font-data text-2xl font-semibold tabular-nums">{filteredEmployees.length}</div></CardContent>
        </Card>
      </div>

      {/* Tabela */}
      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
            </div>
          ) : filteredEmployees.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <Users className="h-16 w-16 mx-auto mb-4 opacity-50" />
              <h3 className="text-lg font-medium">Nenhum colaborador encontrado</h3>
              <p className="mt-2">Tente ajustar os filtros de busca</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nome</TableHead>
                  <TableHead className="hidden lg:table-cell">Matrícula</TableHead>
                  <TableHead>Cargo</TableHead>
                  <TableHead className="hidden md:table-cell">Departamento</TableHead>
                  <TableHead className="hidden lg:table-cell">Admissão</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="w-[80px]">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredEmployees.map((employee) => (
                  <TableRow
                    key={employee.id}
                    className="cursor-pointer hover:bg-muted/50 transition-colors"
                    onClick={() => router.push(`/modulos/operacional/colaboradores/${employee.id}`)}
                  >
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <div className="h-8 w-8 rounded-full bg-muted flex items-center justify-center">
                          <User className="h-4 w-4 text-muted-foreground" />
                        </div>
                        <div>
                          <div className="font-medium">{employee.nome || '-'}</div>
                          {employee.email && (
                            <div className="text-xs text-muted-foreground flex items-center gap-1">
                              <Mail className="h-3 w-3" />
                              {employee.email}
                            </div>
                          )}
                        </div>
                      </div>
                    </TableCell>
                    <TableCell className="hidden lg:table-cell">
                      <code className="text-xs bg-muted px-1.5 py-0.5 rounded">
                        {employee.matricula || '-'}
                      </code>
                    </TableCell>
                    <TableCell>
                      {employee.cargo ? (
                        <div className="flex items-center gap-1 text-sm">
                          <Briefcase className="h-3 w-3 text-muted-foreground" />
                          {employee.cargo}
                        </div>
                      ) : '-'}
                    </TableCell>
                    <TableCell className="hidden md:table-cell">
                      {employee.departamento ? (
                        <div className="flex items-center gap-1 text-sm">
                          <Building2 className="h-3 w-3 text-muted-foreground" />
                          {employee.departamento}
                        </div>
                      ) : '-'}
                    </TableCell>
                    <TableCell className="hidden lg:table-cell">
                      {employee.data_admissao ? (
                        <div className="flex items-center gap-1 text-sm">
                          <Calendar className="h-3 w-3 text-muted-foreground" />
                          {formatDate(employee.data_admissao)}
                        </div>
                      ) : '-'}
                    </TableCell>
                    <TableCell>{getStatusBadge(employee.status)}</TableCell>
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8"
                          title="Ver Perfil"
                          onClick={(e) => {
                            e.stopPropagation();
                            router.push(`/modulos/operacional/colaboradores/${employee.id}`);
                          }}
                        >
                          <User className="h-4 w-4" />
                        </Button>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-8 w-8">
                              <MoreHorizontal className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem onClick={() => router.push(`/modulos/operacional/colaboradores/${employee.id}`)}>
                              <Eye className="h-4 w-4 mr-2" />
                              Ver Perfil
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={() => handleEdit(employee)}>
                              <Edit className="h-4 w-4 mr-2" />
                              Editar
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Modal de Edição */}
      <Dialog open={editDialogOpen} onOpenChange={setEditDialogOpen}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>Editar Colaborador</DialogTitle>
            <DialogDescription>{selectedEmployee?.nome}</DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="edit-nome">Nome Completo</Label>
              <Input id="edit-nome" value={editForm.nome}
                onChange={(e) => setEditForm({ ...editForm, nome: e.target.value })}
                placeholder="Nome do colaborador" />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="edit-email">E-mail</Label>
              <Input id="edit-email" type="email" value={editForm.email}
                onChange={(e) => setEditForm({ ...editForm, email: e.target.value })}
                placeholder="email@exemplo.com" />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="cargo">Cargo (CCT SINDECOMPRESTS)</Label>
              <select
                id="cargo"
                value={editForm.cct_cargo_id}
                disabled={cargosLoading}
                onChange={(e) => {
                  const id = e.target.value;
                  const cargo = cctCargos.find((c) => String(c.id) === id);
                  setEditForm({ ...editForm, cct_cargo_id: id, cargo: cargo ? cargoLabel(cargo) : '' });
                }}
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm"
              >
                <option value="">{cargosLoading ? 'Carregando cargos...' : (editForm.cargo || 'Selecione o cargo')}</option>
                {cctCargos.map((c) => (
                  <option key={String(c.id)} value={String(c.id)}>{cargoLabel(c)}</option>
                ))}
              </select>
              {(() => {
                const sel = cctCargos.find((c) => String(c.id) === editForm.cct_cargo_id);
                return sel?.piso_salarial != null ? (
                  <p className="text-xs text-muted-foreground">
                    Piso CCT: {sel.piso_salarial.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}
                  </p>
                ) : null;
              })()}
            </div>
            <div className="grid gap-2">
              <Label htmlFor="departamento">Departamento</Label>
              <Input id="departamento" value={editForm.departamento}
                onChange={(e) => setEditForm({ ...editForm, departamento: e.target.value })}
                placeholder="Ex: Operações, Segurança..." />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="telefone">Telefone</Label>
              <Input id="telefone" value={editForm.telefone}
                onChange={(e) => setEditForm({ ...editForm, telefone: e.target.value })}
                placeholder="(11) 99999-9999" />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="status">Status</Label>
              <Select value={editForm.status} onValueChange={(v) => setEditForm({ ...editForm, status: v })}>
                <SelectTrigger><SelectValue placeholder="Selecione o status" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="ativo">Ativo</SelectItem>
                  <SelectItem value="inativo">Inativo</SelectItem>
                  <SelectItem value="afastado">Afastado</SelectItem>
                  <SelectItem value="ferias">Férias</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label>Adicionais por Funcionário (%)</Label>
              <p className="text-xs text-muted-foreground -mt-1">
                Individuais — dependem do posto/atividade real (não do cargo). Deixe 0 quando não houver.
              </p>
              <div className="grid grid-cols-3 gap-3">
                <div className="grid gap-1">
                  <Label htmlFor="edit-insalubridade" className="text-xs font-normal">Insalubridade (%)</Label>
                  <Input id="edit-insalubridade" type="number" step="0.01" min="0" max="40"
                    value={editForm.insalubridade_percentual}
                    onChange={(e) => setEditForm({ ...editForm, insalubridade_percentual: e.target.value })}
                    placeholder="0" />
                </div>
                <div className="grid gap-1">
                  <Label htmlFor="edit-periculosidade" className="text-xs font-normal">Periculosidade (%)</Label>
                  <Input id="edit-periculosidade" type="number" step="0.01" min="0" max="30"
                    value={editForm.periculosidade_percentual}
                    onChange={(e) => setEditForm({ ...editForm, periculosidade_percentual: e.target.value })}
                    placeholder="0" />
                </div>
                <div className="grid gap-1">
                  <Label htmlFor="edit-ronda" className="text-xs font-normal">Ad. Ronda (%)</Label>
                  <Input id="edit-ronda" type="number" step="0.01" min="0" max="30"
                    value={editForm.adicional_ronda_percentual}
                    onChange={(e) => setEditForm({ ...editForm, adicional_ronda_percentual: e.target.value })}
                    placeholder="0" />
                </div>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditDialogOpen(false)}>Cancelar</Button>
            <Button onClick={handleSaveEdit} disabled={saving}>
              {saving ? 'Salvando...' : 'Salvar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Modal de Novo Colaborador */}
      <Dialog open={newDialogOpen} onOpenChange={setNewDialogOpen}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>Novo Colaborador</DialogTitle>
            <DialogDescription>Preencha os dados para cadastrar um novo colaborador.</DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="new-nome">Nome completo *</Label>
              <Input id="new-nome" value={newForm.nome}
                onChange={(e) => setNewForm({ ...newForm, nome: e.target.value })}
                placeholder="Nome do colaborador" />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="new-email">E-mail *</Label>
              <Input id="new-email" type="email" value={newForm.email}
                onChange={(e) => setNewForm({ ...newForm, email: e.target.value })}
                placeholder="email@exemplo.com" />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="grid gap-2">
                <Label htmlFor="new-matricula">Matrícula *</Label>
                <Input id="new-matricula" value={newForm.matricula}
                  onChange={(e) => setNewForm({ ...newForm, matricula: e.target.value })}
                  placeholder="Ex: 001234" />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="new-telefone">Telefone</Label>
                <Input id="new-telefone" value={newForm.telefone}
                  onChange={(e) => setNewForm({ ...newForm, telefone: e.target.value })}
                  placeholder="(11) 99999-9999" />
              </div>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="new-cargo">Cargo (CCT SINDECOMPRESTS)</Label>
              <select
                id="new-cargo"
                value={newForm.cct_cargo_id}
                disabled={cargosLoading}
                onChange={(e) => {
                  const id = e.target.value;
                  const cargo = cctCargos.find((c) => String(c.id) === id);
                  setNewForm({ ...newForm, cct_cargo_id: id, cargo: cargo ? cargoLabel(cargo) : '' });
                }}
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm"
              >
                <option value="">{cargosLoading ? 'Carregando cargos...' : 'Selecione o cargo'}</option>
                {cctCargos.map((c) => (
                  <option key={String(c.id)} value={String(c.id)}>{cargoLabel(c)}</option>
                ))}
              </select>
              {(() => {
                const sel = cctCargos.find((c) => String(c.id) === newForm.cct_cargo_id);
                return sel?.piso_salarial != null ? (
                  <p className="text-xs text-muted-foreground">
                    Piso CCT: {sel.piso_salarial.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}
                  </p>
                ) : null;
              })()}
            </div>
            <div className="grid gap-2">
              <Label htmlFor="new-departamento">Departamento</Label>
              <Input id="new-departamento" value={newForm.departamento}
                onChange={(e) => setNewForm({ ...newForm, departamento: e.target.value })}
                placeholder="Ex: Operações, Segurança..." />
            </div>
            <div className="grid gap-2">
              <Label>Adicionais por Funcionário (%)</Label>
              <p className="text-xs text-muted-foreground -mt-1">
                Individuais — dependem do posto/atividade real (não do cargo). Deixe 0 quando não houver.
              </p>
              <div className="grid grid-cols-3 gap-3">
                <div className="grid gap-1">
                  <Label htmlFor="new-insalubridade" className="text-xs font-normal">Insalubridade (%)</Label>
                  <Input id="new-insalubridade" type="number" step="0.01" min="0" max="40"
                    value={newForm.insalubridade_percentual}
                    onChange={(e) => setNewForm({ ...newForm, insalubridade_percentual: e.target.value })}
                    placeholder="0" />
                </div>
                <div className="grid gap-1">
                  <Label htmlFor="new-periculosidade" className="text-xs font-normal">Periculosidade (%)</Label>
                  <Input id="new-periculosidade" type="number" step="0.01" min="0" max="30"
                    value={newForm.periculosidade_percentual}
                    onChange={(e) => setNewForm({ ...newForm, periculosidade_percentual: e.target.value })}
                    placeholder="0" />
                </div>
                <div className="grid gap-1">
                  <Label htmlFor="new-ronda" className="text-xs font-normal">Ad. Ronda (%)</Label>
                  <Input id="new-ronda" type="number" step="0.01" min="0" max="30"
                    value={newForm.adicional_ronda_percentual}
                    onChange={(e) => setNewForm({ ...newForm, adicional_ronda_percentual: e.target.value })}
                    placeholder="0" />
                </div>
              </div>
            </div>
            {newError && (
              <div className="text-sm text-destructive flex items-center gap-2">
                <AlertCircle className="h-4 w-4" />
                {newError}
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setNewDialogOpen(false); setNewError(null); }}>Cancelar</Button>
            <Button onClick={handleCreateEmployee} disabled={newSaving}>
              {newSaving ? 'Salvando...' : 'Cadastrar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
