'use client';

import { useState, useEffect, useMemo } from 'react';
import {
  UserMinus, ArrowLeft, Inbox, Loader2, Plus, X, Save, Search,
  ChevronLeft, ChevronRight as ChevronRightIcon, Eye, Calculator,
  CheckCircle2, AlertCircle, Clock, Ban, FileText, Calendar,
} from 'lucide-react';
import { toast } from 'sonner';
import { useRouter } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';

const API_BASE = '/api/v1/people-management/hr';

function getAuthHeaders() {
  const token = typeof window !== 'undefined' ? (localStorage.getItem('access_token') || localStorage.getItem('token')) : null;
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

// Backend status values from TerminationStatus enum
const statusConfig: Record<string, { label: string; className: string; icon: React.ReactNode }> = {
  initiated: { label: 'Iniciado', className: 'bg-blue-500 text-white', icon: <Clock className="h-3 w-3" /> },
  notice_period: { label: 'Aviso Prévio', className: 'bg-yellow-500 text-white', icon: <Calendar className="h-3 w-3" /> },
  calculating: { label: 'Calculando', className: 'bg-orange-500 text-white', icon: <Calculator className="h-3 w-3" /> },
  pending_payment: { label: 'Pgto Pendente', className: 'bg-purple-500 text-white', icon: <AlertCircle className="h-3 w-3" /> },
  completed: { label: 'Concluída', className: 'bg-green-500 text-white', icon: <CheckCircle2 className="h-3 w-3" /> },
  cancelled: { label: 'Cancelada', className: 'bg-red-500 text-white', icon: <Ban className="h-3 w-3" /> },
};

// Backend type values from TerminationType enum
const tipoConfig: Record<string, string> = {
  voluntary: 'Voluntária',
  involuntary: 'Involuntária',
  just_cause: 'Justa Causa',
  mutual_agreement: 'Acordo Mútuo',
  contract_end: 'Fim de Contrato',
  retirement: 'Aposentadoria',
};

const PAGE_SIZE = 10;

interface TerminationItem {
  id: string;
  employee_id: string;
  type: string;
  reason: string | null;
  notice_period_days: number | null;
  notice_start_date: string | null;
  last_working_day: string | null;
  status: string;
  severance_amount: number | null;
  vacation_balance_amount: number | null;
  thirteenth_salary_amount: number | null;
  fgts_amount: number | null;
  total_amount: number | null;
  exit_interview_done: boolean;
  exit_interview_notes: string | null;
  esocial_event_sent: boolean;
  documents_generated: Record<string, unknown> | null;
  created_by_id: string | null;
  created_at: string;
  updated_at: string;
  // Enriched on frontend
  _employee_name?: string;
}

interface EmployeeOption {
  id: string;
  nome: string;
  cpf?: string;
  cargo?: string;
}

interface CalculationResult {
  employee_id: string;
  employee_name: string;
  termination_type: string;
  last_working_day: string | null;
  months_worked: number;
  saldo_salario: number;
  aviso_previo_indenizado: number;
  ferias_vencidas: number;
  ferias_proporcionais: number;
  terco_constitucional: number;
  decimo_terceiro_proporcional: number;
  multa_fgts_40: number;
  total_proventos: number;
  total_descontos: number;
  total_liquido: number;
  inss?: number;
  irrf?: number;
}

export default function RescisaoPage() {
  const router = useRouter();

  // Data state
  const [rescisoes, setRescisoes] = useState<TerminationItem[]>([]);
  const [employees, setEmployees] = useState<EmployeeOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);

  // Filter/search/sort state
  const [filtroStatus, setFiltroStatus] = useState<string>('todos');
  const [searchTerm, setSearchTerm] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [sortField, setSortField] = useState<string>('');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  // Form state
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState({
    employee_id: '',
    type: 'voluntary',
    last_working_day: '',
    reason: '',
    notice_period_days: '',
    notes: '',
  });
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});

  // Detail view state
  const [selectedItem, setSelectedItem] = useState<TerminationItem | null>(null);
  const [showDetail, setShowDetail] = useState(false);

  // Calculation state
  const [calculating, setCalculating] = useState(false);
  const [calcResult, setCalcResult] = useState<CalculationResult | null>(null);

  // Completing state
  const [completing, setCompleting] = useState(false);

  // ---------- Data loading ----------
  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        // Load terminations
        const statusParam = filtroStatus !== 'todos' ? `&status=${filtroStatus}` : '';
        const res = await fetch(`${API_BASE}/terminations?page=1&page_size=100${statusParam}`, { headers: getAuthHeaders() });
        if (res.ok) {
          const data = await res.json();
          setRescisoes(data.items || []);
        } else {
          setRescisoes([]);
        }

        // Load employees for the form
        const empRes = await fetch(`${API_BASE}/employees?page_size=100`, { headers: getAuthHeaders() });
        if (empRes.ok) {
          const empData = await empRes.json();
          setEmployees(empData.items || []);
        }
      } catch {
        setRescisoes([]);
        toast.error('Erro ao carregar dados', { duration: 4000 });
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [filtroStatus, refreshKey]);

  // Reset page when filter/search changes
  useEffect(() => { setCurrentPage(1); }, [filtroStatus, searchTerm]);

  // ---------- Enriched data with employee names ----------
  const employeeMap = useMemo(() => {
    const map: Record<string, string> = {};
    for (const emp of employees) {
      map[emp.id] = emp.nome;
    }
    return map;
  }, [employees]);

  // ---------- Filtered + searched + sorted data ----------
  const filteredData = useMemo(() => {
    let items = rescisoes.map(r => ({
      ...r,
      _employee_name: employeeMap[r.employee_id] || 'Funcionário',
    }));

    if (searchTerm.trim()) {
      const term = searchTerm.toLowerCase();
      items = items.filter(r =>
        (r._employee_name || '').toLowerCase().includes(term) ||
        (r.reason || '').toLowerCase().includes(term) ||
        (tipoConfig[r.type] || '').toLowerCase().includes(term)
      );
    }

    if (sortField) {
      items = [...items].sort((a, b) => {
        const va = String((a as Record<string, unknown>)[sortField] || '').toLowerCase();
        const vb = String((b as Record<string, unknown>)[sortField] || '').toLowerCase();
        return sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
      });
    }

    return items;
  }, [rescisoes, searchTerm, sortField, sortDir, employeeMap]);

  const totalPages = Math.max(1, Math.ceil(filteredData.length / PAGE_SIZE));
  const paginatedData = filteredData.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  const handleSort = (field: string) => {
    if (sortField === field) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDir('asc');
    }
  };

  const sortIcon = (field: string) => {
    if (sortField !== field) return ' ↕';
    return sortDir === 'asc' ? ' ↑' : ' ↓';
  };

  // ---------- Format helpers ----------
  function formatDate(dateStr: string | null | undefined): string {
    if (!dateStr) return '-';
    const parts = String(dateStr).split('-');
    if (parts.length === 3) return `${parts[2]}/${parts[1]}/${parts[0]}`;
    return dateStr;
  }

  function formatCurrency(value: number | null | undefined): string {
    if (value == null) return 'R$ 0,00';
    return `R$ ${Number(value).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }

  // ---------- Handlers ----------
  const handleCreate = async () => {
    const errors: Record<string, string> = {};
    if (!formData.employee_id) errors.employee_id = 'Selecione um colaborador';
    if (!formData.last_working_day) errors.last_working_day = 'Data é obrigatória';
    if (Object.keys(errors).length > 0) {
      setFormErrors(errors);
      toast.error('Corrija os campos destacados', { duration: 4000 });
      return;
    }

    setSaving(true);
    try {
      const payload: Record<string, unknown> = {
        employee_id: formData.employee_id,
        type: formData.type,
        last_working_day: formData.last_working_day || undefined,
        reason: formData.reason || undefined,
        notes: formData.notes || undefined,
      };
      if (formData.notice_period_days) {
        payload.notice_period_days = parseInt(formData.notice_period_days, 10);
      }

      const res = await fetch(`${API_BASE}/terminations`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        setShowForm(false);
        resetForm();
        setRefreshKey(k => k + 1);
        toast.success('Processo de rescisão criado com sucesso!', { duration: 4000 });
      } else {
        const err = await res.json().catch(() => null);
        toast.error(err?.detail || 'Erro ao criar rescisão', { duration: 5000 });
      }
    } catch {
      toast.error('Erro de conexão com o servidor', { duration: 5000 });
    } finally {
      setSaving(false);
    }
  };

  const resetForm = () => {
    setFormData({ employee_id: '', type: 'voluntary', last_working_day: '', reason: '', notice_period_days: '', notes: '' });
    setFormErrors({});
  };

  const handleViewDetail = async (item: TerminationItem) => {
    try {
      const res = await fetch(`${API_BASE}/terminations/${item.id}`, { headers: getAuthHeaders() });
      if (res.ok) {
        const detail = await res.json();
        setSelectedItem({ ...detail, _employee_name: employeeMap[detail.employee_id] || 'Funcionário' });
      } else {
        setSelectedItem({ ...item, _employee_name: employeeMap[item.employee_id] || 'Funcionário' });
      }
    } catch {
      setSelectedItem({ ...item, _employee_name: employeeMap[item.employee_id] || 'Funcionário' });
    }
    setCalcResult(null);
    setShowDetail(true);
  };

  const handleCalculate = async (terminationId: string) => {
    setCalculating(true);
    setCalcResult(null);
    try {
      const res = await fetch(`${API_BASE}/terminations/${terminationId}/calculate`, {
        method: 'POST',
        headers: getAuthHeaders(),
      });
      if (res.ok) {
        const data = await res.json();
        setCalcResult(data);
        toast.success('Cálculo rescisório realizado!', { duration: 4000 });
      } else {
        const err = await res.json().catch(() => null);
        toast.error(err?.detail || 'Erro ao calcular verbas rescisórias', { duration: 5000 });
      }
    } catch {
      toast.error('Erro de conexão', { duration: 5000 });
    } finally {
      setCalculating(false);
    }
  };

  const handleComplete = async (terminationId: string) => {
    setCompleting(true);
    try {
      const res = await fetch(`${API_BASE}/terminations/${terminationId}/complete`, {
        method: 'POST',
        headers: getAuthHeaders(),
      });
      if (res.ok) {
        toast.success('Rescisão concluída com sucesso! Funcionário desligado.', { duration: 5000 });
        setShowDetail(false);
        setRefreshKey(k => k + 1);
      } else {
        const err = await res.json().catch(() => null);
        toast.error(err?.detail || 'Erro ao concluir rescisão', { duration: 5000 });
      }
    } catch {
      toast.error('Erro de conexão', { duration: 5000 });
    } finally {
      setCompleting(false);
    }
  };

  // ---------- Stats ----------
  const stats = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const r of rescisoes) {
      counts[r.status] = (counts[r.status] || 0) + 1;
    }
    return {
      total: rescisoes.length,
      initiated: counts['initiated'] || 0,
      notice_period: counts['notice_period'] || 0,
      calculating: counts['calculating'] || 0,
      pending_payment: counts['pending_payment'] || 0,
      completed: counts['completed'] || 0,
      cancelled: counts['cancelled'] || 0,
    };
  }, [rescisoes]);

  // ---------- Render ----------
  return (
    <div className="space-y-6 pb-28">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button type="button" variant="ghost" size="sm" onClick={() => router.push('/modulos/dp')}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <UserMinus className="h-6 w-6" />
              Processos de Rescisão
            </h1>
            <p className="text-muted-foreground">Gerencie desligamentos e rescisões de colaboradores</p>
          </div>
        </div>
        <Button type="button" size="sm" onClick={() => setShowForm(true)}>
          <Plus className="h-4 w-4 mr-1" /> Iniciar Rescisão
        </Button>
      </div>

      {/* Status Filter Badges */}
      <div className="flex gap-2 flex-wrap">
        <Badge
          className={`cursor-pointer ${filtroStatus === 'todos' ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'}`}
          onClick={() => setFiltroStatus('todos')}
        >
          Todos ({stats.total})
        </Badge>
        {Object.entries(statusConfig).map(([key, val]) => (
          <Badge
            key={key}
            className={`cursor-pointer flex items-center gap-1 ${filtroStatus === key ? val.className : 'bg-muted text-muted-foreground'}`}
            onClick={() => setFiltroStatus(key)}
          >
            {val.icon}
            {val.label} ({(stats as Record<string, number>)[key] || 0})
          </Badge>
        ))}
      </div>

      {/* Create Form */}
      {showForm && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <FileText className="h-5 w-5" />
                Nova Rescisão
              </CardTitle>
              <Button type="button" variant="ghost" size="sm" onClick={() => { setShowForm(false); resetForm(); }}>
                <X className="h-4 w-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="text-sm font-medium mb-1 block">Colaborador *</label>
                <select
                  value={formData.employee_id}
                  onChange={e => { setFormData(p => ({ ...p, employee_id: e.target.value })); setFormErrors(p => ({ ...p, employee_id: '' })); }}
                  className={`w-full px-3 py-2 border rounded-md text-sm ${formErrors.employee_id ? 'border-red-500' : ''}`}
                >
                  <option value="">Selecione um colaborador</option>
                  {employees.map((emp) => (
                    <option key={emp.id} value={emp.id}>
                      {emp.nome}{emp.cpf ? ` — ${emp.cpf}` : ''}{emp.cargo ? ` (${emp.cargo})` : ''}
                    </option>
                  ))}
                </select>
                {formErrors.employee_id && <p className="text-red-500 text-xs mt-1 flex items-center gap-1"><AlertCircle className="h-3 w-3" />{formErrors.employee_id}</p>}
              </div>

              <div>
                <label className="text-sm font-medium mb-1 block">Tipo de Rescisão *</label>
                <select
                  value={formData.type}
                  onChange={e => setFormData(p => ({ ...p, type: e.target.value }))}
                  className="w-full px-3 py-2 border rounded-md text-sm"
                >
                  {Object.entries(tipoConfig).map(([key, label]) => (
                    <option key={key} value={key}>{label}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-sm font-medium mb-1 block">Último Dia de Trabalho *</label>
                <input
                  type="date"
                  value={formData.last_working_day}
                  onChange={e => { setFormData(p => ({ ...p, last_working_day: e.target.value })); setFormErrors(p => ({ ...p, last_working_day: '' })); }}
                  className={`w-full px-3 py-2 border rounded-md text-sm ${formErrors.last_working_day ? 'border-red-500' : ''}`}
                />
                {formErrors.last_working_day && <p className="text-red-500 text-xs mt-1 flex items-center gap-1"><AlertCircle className="h-3 w-3" />{formErrors.last_working_day}</p>}
              </div>

              <div>
                <label className="text-sm font-medium mb-1 block">Dias de Aviso Prévio</label>
                <input
                  type="number"
                  min={0}
                  max={90}
                  value={formData.notice_period_days}
                  onChange={e => setFormData(p => ({ ...p, notice_period_days: e.target.value }))}
                  className="w-full px-3 py-2 border rounded-md text-sm"
                  placeholder="0 a 90 dias"
                />
              </div>

              <div className="md:col-span-2">
                <label className="text-sm font-medium mb-1 block">Motivo</label>
                <textarea
                  value={formData.reason}
                  onChange={e => setFormData(p => ({ ...p, reason: e.target.value }))}
                  className="w-full px-3 py-2 border rounded-md text-sm"
                  rows={2}
                  placeholder="Motivo da rescisão"
                />
              </div>

              <div className="md:col-span-2">
                <label className="text-sm font-medium mb-1 block">Observações</label>
                <textarea
                  value={formData.notes}
                  onChange={e => setFormData(p => ({ ...p, notes: e.target.value }))}
                  className="w-full px-3 py-2 border rounded-md text-sm"
                  rows={2}
                  placeholder="Observações internas"
                />
              </div>
            </div>

            <div className="flex gap-2 mt-4">
              <Button type="button" size="sm" disabled={saving} onClick={handleCreate}>
                {saving ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Save className="h-4 w-4 mr-1" />}
                {saving ? 'Salvando...' : 'Criar Rescisão'}
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={() => { setShowForm(false); resetForm(); }}>Cancelar</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Table */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Rescisões</CardTitle>
            <div className="relative w-64">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <input
                type="text"
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
                placeholder="Buscar por nome, motivo..."
                className="w-full pl-9 pr-3 py-2 border rounded-md text-sm"
              />
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex flex-col items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
              <p className="text-sm text-muted-foreground mt-2">Carregando rescisões...</p>
            </div>
          ) : filteredData.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
              <Inbox className="h-12 w-12 mb-3" />
              <p className="font-medium">Nenhum processo de rescisão encontrado</p>
              <p className="text-sm text-muted-foreground mt-1">
                {searchTerm
                  ? 'Tente outra busca.'
                  : filtroStatus !== 'todos'
                    ? 'Nenhuma rescisão com este status. Tente outro filtro.'
                    : 'Clique em "Iniciar Rescisão" para criar um processo.'}
              </p>
            </div>
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="cursor-pointer select-none" onClick={() => handleSort('_employee_name')}>Colaborador{sortIcon('_employee_name')}</TableHead>
                    <TableHead className="cursor-pointer select-none" onClick={() => handleSort('type')}>Tipo{sortIcon('type')}</TableHead>
                    <TableHead className="cursor-pointer select-none" onClick={() => handleSort('status')}>Status{sortIcon('status')}</TableHead>
                    <TableHead className="cursor-pointer select-none" onClick={() => handleSort('last_working_day')}>Último Dia{sortIcon('last_working_day')}</TableHead>
                    <TableHead>Valor Total</TableHead>
                    <TableHead>Ações</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {paginatedData.map((item) => {
                    const st = statusConfig[item.status] || { label: item.status, className: 'bg-gray-500 text-white', icon: null };
                    return (
                      <TableRow key={item.id}>
                        <TableCell className="font-medium">{item._employee_name || 'Funcionário'}</TableCell>
                        <TableCell>{tipoConfig[item.type] || item.type}</TableCell>
                        <TableCell>
                          <Badge className={`flex items-center gap-1 w-fit ${st.className}`}>
                            {st.icon}
                            {st.label}
                          </Badge>
                        </TableCell>
                        <TableCell>{formatDate(item.last_working_day)}</TableCell>
                        <TableCell>{formatCurrency(item.total_amount)}</TableCell>
                        <TableCell>
                          <Button variant="outline" size="sm" onClick={() => handleViewDetail(item)}>
                            <Eye className="h-4 w-4 mr-1" /> Detalhes
                          </Button>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>

              {/* Pagination */}
              <div className="flex items-center justify-between mt-4 text-sm">
                <span className="text-muted-foreground">
                  {filteredData.length} registro{filteredData.length !== 1 ? 's' : ''} — Página {currentPage} de {totalPages}
                </span>
                <div className="flex gap-1">
                  <Button variant="outline" size="sm" disabled={currentPage <= 1} onClick={() => setCurrentPage(p => p - 1)}>
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                  {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => {
                    const page = totalPages <= 5 ? i + 1 : Math.max(1, Math.min(currentPage - 2, totalPages - 4)) + i;
                    return (
                      <Button key={page} variant={currentPage === page ? 'default' : 'outline'} size="sm" onClick={() => setCurrentPage(page)}>
                        {page}
                      </Button>
                    );
                  })}
                  <Button variant="outline" size="sm" disabled={currentPage >= totalPages} onClick={() => setCurrentPage(p => p + 1)}>
                    <ChevronRightIcon className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {/* Detail Modal */}
      {showDetail && selectedItem && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={() => setShowDetail(false)}>
          <div className="bg-background rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-6 border-b">
              <h2 className="text-lg font-semibold flex items-center gap-2">
                <FileText className="h-5 w-5" />
                Detalhes da Rescisão
              </h2>
              <Button type="button" variant="ghost" size="sm" onClick={() => setShowDetail(false)}>
                <X className="h-4 w-4" />
              </Button>
            </div>

            <div className="p-6 space-y-6">
              {/* General Info */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-sm text-muted-foreground">Colaborador</p>
                  <p className="font-medium">{selectedItem._employee_name || 'Funcionário'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Status</p>
                  <Badge className={`flex items-center gap-1 w-fit mt-1 ${(statusConfig[selectedItem.status] || { className: 'bg-gray-500 text-white' }).className}`}>
                    {statusConfig[selectedItem.status]?.icon}
                    {statusConfig[selectedItem.status]?.label || selectedItem.status}
                  </Badge>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Tipo</p>
                  <p className="font-medium">{tipoConfig[selectedItem.type] || selectedItem.type}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Último Dia de Trabalho</p>
                  <p className="font-medium">{formatDate(selectedItem.last_working_day)}</p>
                </div>
                {selectedItem.notice_period_days != null && (
                  <div>
                    <p className="text-sm text-muted-foreground">Aviso Prévio</p>
                    <p className="font-medium">{selectedItem.notice_period_days} dias</p>
                  </div>
                )}
                {selectedItem.notice_start_date && (
                  <div>
                    <p className="text-sm text-muted-foreground">Início Aviso Prévio</p>
                    <p className="font-medium">{formatDate(selectedItem.notice_start_date)}</p>
                  </div>
                )}
                <div>
                  <p className="text-sm text-muted-foreground">Criado em</p>
                  <p className="font-medium">{selectedItem.created_at ? new Date(selectedItem.created_at).toLocaleString('pt-BR') : '-'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Atualizado em</p>
                  <p className="font-medium">{selectedItem.updated_at ? new Date(selectedItem.updated_at).toLocaleString('pt-BR') : '-'}</p>
                </div>
              </div>

              {/* Reason */}
              {selectedItem.reason && (
                <div>
                  <p className="text-sm text-muted-foreground mb-1">Motivo</p>
                  <p className="text-sm bg-muted p-3 rounded-md">{selectedItem.reason}</p>
                </div>
              )}

              {/* Financial Summary */}
              {(selectedItem.total_amount != null && selectedItem.total_amount > 0) && (
                <div>
                  <p className="text-sm font-medium mb-2">Verbas Rescisórias</p>
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    <div className="flex justify-between bg-muted/50 p-2 rounded">
                      <span>Indenização</span>
                      <span className="font-medium">{formatCurrency(selectedItem.severance_amount)}</span>
                    </div>
                    <div className="flex justify-between bg-muted/50 p-2 rounded">
                      <span>Férias</span>
                      <span className="font-medium">{formatCurrency(selectedItem.vacation_balance_amount)}</span>
                    </div>
                    <div className="flex justify-between bg-muted/50 p-2 rounded">
                      <span>13º Salário</span>
                      <span className="font-medium">{formatCurrency(selectedItem.thirteenth_salary_amount)}</span>
                    </div>
                    <div className="flex justify-between bg-muted/50 p-2 rounded">
                      <span>FGTS</span>
                      <span className="font-medium">{formatCurrency(selectedItem.fgts_amount)}</span>
                    </div>
                    <div className="col-span-2 flex justify-between bg-primary/10 p-2 rounded font-semibold">
                      <span>Total Líquido</span>
                      <span>{formatCurrency(selectedItem.total_amount)}</span>
                    </div>
                  </div>
                </div>
              )}

              {/* Calculation Result */}
              {calcResult && (
                <div>
                  <p className="text-sm font-medium mb-2">Cálculo Rescisório Detalhado</p>
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    <div className="flex justify-between bg-green-50 dark:bg-green-950/30 p-2 rounded">
                      <span>Saldo de Salário</span>
                      <span className="font-medium">{formatCurrency(calcResult.saldo_salario)}</span>
                    </div>
                    <div className="flex justify-between bg-green-50 dark:bg-green-950/30 p-2 rounded">
                      <span>Aviso Prévio Ind.</span>
                      <span className="font-medium">{formatCurrency(calcResult.aviso_previo_indenizado)}</span>
                    </div>
                    <div className="flex justify-between bg-green-50 dark:bg-green-950/30 p-2 rounded">
                      <span>Férias Vencidas</span>
                      <span className="font-medium">{formatCurrency(calcResult.ferias_vencidas)}</span>
                    </div>
                    <div className="flex justify-between bg-green-50 dark:bg-green-950/30 p-2 rounded">
                      <span>Férias Proporcionais</span>
                      <span className="font-medium">{formatCurrency(calcResult.ferias_proporcionais)}</span>
                    </div>
                    <div className="flex justify-between bg-green-50 dark:bg-green-950/30 p-2 rounded">
                      <span>1/3 Constitucional</span>
                      <span className="font-medium">{formatCurrency(calcResult.terco_constitucional)}</span>
                    </div>
                    <div className="flex justify-between bg-green-50 dark:bg-green-950/30 p-2 rounded">
                      <span>13º Proporcional</span>
                      <span className="font-medium">{formatCurrency(calcResult.decimo_terceiro_proporcional)}</span>
                    </div>
                    <div className="flex justify-between bg-green-50 dark:bg-green-950/30 p-2 rounded">
                      <span>Multa FGTS 40%</span>
                      <span className="font-medium">{formatCurrency(calcResult.multa_fgts_40)}</span>
                    </div>
                    <div className="flex justify-between bg-green-50 dark:bg-green-950/30 p-2 rounded">
                      <span>Meses Trabalhados</span>
                      <span className="font-medium">{calcResult.months_worked}</span>
                    </div>
                    <div className="col-span-2 border-t pt-2 mt-1 space-y-1">
                      <div className="flex justify-between">
                        <span>Total Proventos</span>
                        <span className="font-medium text-green-600">{formatCurrency(calcResult.total_proventos)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span>Total Descontos</span>
                        <span className="font-medium text-red-600">- {formatCurrency(calcResult.total_descontos)}</span>
                      </div>
                      <div className="flex justify-between font-semibold text-base pt-1 border-t">
                        <span>Total Líquido</span>
                        <span className="text-primary">{formatCurrency(calcResult.total_liquido)}</span>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Checklists */}
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div className="flex items-center gap-2">
                  {selectedItem.exit_interview_done
                    ? <CheckCircle2 className="h-4 w-4 text-green-500" />
                    : <AlertCircle className="h-4 w-4 text-muted-foreground" />
                  }
                  <span>Entrevista de Desligamento</span>
                </div>
                <div className="flex items-center gap-2">
                  {selectedItem.esocial_event_sent
                    ? <CheckCircle2 className="h-4 w-4 text-green-500" />
                    : <AlertCircle className="h-4 w-4 text-muted-foreground" />
                  }
                  <span>Evento eSocial Enviado</span>
                </div>
              </div>

              {/* Actions */}
              <div className="flex gap-2 pt-2 border-t">
                {selectedItem.status !== 'completed' && selectedItem.status !== 'cancelled' && (
                  <>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      disabled={calculating}
                      onClick={() => handleCalculate(selectedItem.id)}
                    >
                      {calculating
                        ? <Loader2 className="h-4 w-4 animate-spin mr-1" />
                        : <Calculator className="h-4 w-4 mr-1" />
                      }
                      {calculating ? 'Calculando...' : 'Calcular Verbas'}
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      disabled={completing}
                      onClick={() => handleComplete(selectedItem.id)}
                    >
                      {completing
                        ? <Loader2 className="h-4 w-4 animate-spin mr-1" />
                        : <CheckCircle2 className="h-4 w-4 mr-1" />
                      }
                      {completing ? 'Concluindo...' : 'Concluir Rescisão'}
                    </Button>
                  </>
                )}
                <Button type="button" variant="outline" size="sm" onClick={() => setShowDetail(false)}>
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
