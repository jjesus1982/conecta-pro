'use client';

import { useState, useEffect, useMemo } from 'react';
import { Sun, ArrowLeft, Inbox, Loader2, Plus, X, Save, Search, ChevronLeft, ChevronRight as ChevronRightIcon, Eye, CheckCircle, XCircle, Calendar, Clock, AlertTriangle, UserCheck } from 'lucide-react';
import { toast } from 'sonner';
import { useRouter } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { PageHeader } from '@/components/ui/page-header';

const API_BASE = '/api/v1/people-management/hr';

function getAuthHeaders() {
  const token = typeof window !== 'undefined' ? (localStorage.getItem('access_token') || localStorage.getItem('token')) : null;
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

const statusConfig: Record<string, { label: string; className: string; icon: React.ReactNode }> = {
  pendente: { label: 'Pendente', className: 'bg-yellow-500 text-white', icon: <Clock className="h-3 w-3" /> },
  aprovado: { label: 'Aprovado', className: 'bg-green-500 text-white', icon: <CheckCircle className="h-3 w-3" /> },
  rejeitado: { label: 'Rejeitado', className: 'bg-red-500 text-white', icon: <XCircle className="h-3 w-3" /> },
  cancelado: { label: 'Cancelado', className: 'bg-gray-500 text-white', icon: <X className="h-3 w-3" /> },
};

const typeConfig: Record<string, { label: string; className: string }> = {
  ferias: { label: 'Férias', className: 'bg-blue-100 text-blue-800' },
  afastamento: { label: 'Afastamento', className: 'bg-orange-100 text-orange-800' },
  licenca: { label: 'Licença', className: 'bg-purple-100 text-purple-800' },
  folga: { label: 'Folga', className: 'bg-cyan-100 text-cyan-800' },
};

const PAGE_SIZE = 10;

function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '-';
  const parts = String(dateStr).split('-');
  if (parts.length === 3) return `${parts[2]}/${parts[1]}/${parts[0]}`;
  return String(dateStr);
}

function formatDateTime(dateStr: string | null | undefined): string {
  if (!dateStr) return '-';
  try {
    const d = new Date(dateStr);
    return d.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch {
    return String(dateStr);
  }
}

interface VacationItem {
  id: string;
  employee_id: string;
  employee_name?: string;
  type: string;
  status: string;
  start_date: string;
  end_date: string;
  days?: string;
  reason?: string;
  notes?: string;
  approved_by?: string;
  approved_at?: string;
  rejected_reason?: string;
  created_at: string;
  updated_at: string;
}

export default function FeriasPage() {
  const router = useRouter();
  const [ferias, setFerias] = useState<VacationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [employees, setEmployees] = useState<any[]>([]);
  const [formData, setFormData] = useState({
    employee_id: '',
    type: 'ferias',
    start_date: '',
    end_date: '',
    reason: '',
    notes: '',
  });
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});
  const [refreshKey, setRefreshKey] = useState(0);
  const [searchTerm, setSearchTerm] = useState('');
  const [filtroStatus, setFiltroStatus] = useState<string>('todos');
  const [currentPage, setCurrentPage] = useState(1);
  const [sortField, setSortField] = useState<string>('');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  // Detail / approve / reject modal
  const [selectedVacation, setSelectedVacation] = useState<VacationItem | null>(null);
  const [showDetail, setShowDetail] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [vacationBalance, setVacationBalance] = useState<Record<string, any> | null>(null);
  const [balanceLoading, setBalanceLoading] = useState(false);
  const [showRejectInput, setShowRejectInput] = useState(false);
  const [syncingSolides, setSyncingSolides] = useState(false);

  // Status counts from API
  const [statusCounts, setStatusCounts] = useState({ pendente: 0, aprovado: 0, rejeitado: 0, cancelado: 0, total: 0 });

  // Fetch vacation list
  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const params = new URLSearchParams();
        if (filtroStatus !== 'todos') params.set('status', filtroStatus);

        const url = `${API_BASE}/vacations${params.toString() ? '?' + params.toString() : ''}`;
        const res = await fetch(url, { headers: getAuthHeaders() });
        if (res.ok) {
          const data = await res.json();
          const items: VacationItem[] = data.items || data || [];
          setFerias(items);
          setStatusCounts({
            pendente: data.pendente ?? 0,
            aprovado: data.aprovado ?? 0,
            rejeitado: data.rejeitado ?? 0,
            cancelado: items.filter((i: VacationItem) => i.status === 'cancelado').length,
            total: data.total ?? items.length,
          });
        } else {
          setFerias([]);
        }
      } catch {
        setFerias([]);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [filtroStatus, refreshKey]);

  // Fetch employees for form
  useEffect(() => {
    if (!showForm) return;
    async function loadEmployees() {
      try {
        const res = await fetch(`${API_BASE}/employees?page_size=100`, { headers: getAuthHeaders() });
        if (res.ok) {
          const data = await res.json();
          setEmployees(data.items || data || []);
        }
      } catch { /* ignore */ }
    }
    loadEmployees();
  }, [showForm]);

  // Reset page on filter/search change
  useEffect(() => { setCurrentPage(1); }, [filtroStatus, searchTerm]);

  // Filtered + searched + sorted data
  const filteredData = useMemo(() => {
    let items = ferias;
    if (searchTerm.trim()) {
      const term = searchTerm.toLowerCase();
      items = items.filter(a =>
        (a.employee_name || '').toLowerCase().includes(term) ||
        (a.type || '').toLowerCase().includes(term) ||
        (a.days || '').toLowerCase().includes(term)
      );
    }
    if (sortField) {
      items = [...items].sort((a, b) => {
        const va = String((a as any)[sortField] || '').toLowerCase();
        const vb = String((b as any)[sortField] || '').toLowerCase();
        return sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
      });
    }
    return items;
  }, [ferias, searchTerm, sortField, sortDir]);

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

  // Create vacation request
  const handleCreate = async () => {
    const errors: Record<string, string> = {};
    if (!formData.employee_id) errors.employee_id = 'Selecione um colaborador';
    if (!formData.start_date) errors.start_date = 'Data de início é obrigatória';
    if (!formData.end_date) errors.end_date = 'Data de fim é obrigatória';
    if (formData.start_date && formData.end_date && formData.start_date > formData.end_date) {
      errors.end_date = 'Data de fim deve ser após a data de início';
    }
    if (Object.keys(errors).length > 0) {
      setFormErrors(errors);
      toast.error('Corrija os campos destacados', { duration: 4000 });
      return;
    }
    setSaving(true);
    try {
      const selectedEmployee = employees.find(e => e.id === formData.employee_id);
      const payload = {
        employee_id: formData.employee_id,
        employee_name: selectedEmployee?.nome || selectedEmployee?.name || null,
        type: formData.type,
        start_date: formData.start_date,
        end_date: formData.end_date,
        reason: formData.reason || null,
        notes: formData.notes || null,
      };
      const res = await fetch(`${API_BASE}/vacations`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        setShowForm(false);
        setFormData({ employee_id: '', type: 'ferias', start_date: '', end_date: '', reason: '', notes: '' });
        setFormErrors({});
        setRefreshKey(k => k + 1);
        toast.success('Solicitação de férias criada com sucesso!', { duration: 4000 });
      } else {
        const err = await res.json().catch(() => null);
        toast.error(err?.detail || 'Erro ao criar solicitação de férias', { duration: 5000 });
      }
    } catch {
      toast.error('Erro de conexão com o servidor', { duration: 5000 });
    } finally {
      setSaving(false);
    }
  };

  // Open detail view
  const handleViewDetail = async (item: VacationItem) => {
    setSelectedVacation(item);
    setShowDetail(true);
    setShowRejectInput(false);
    setRejectReason('');
    setVacationBalance(null);
    // Fetch fresh detail
    try {
      const res = await fetch(`${API_BASE}/vacations/${item.id}`, { headers: getAuthHeaders() });
      if (res.ok) {
        const detail = await res.json();
        setSelectedVacation(detail);
      }
    } catch { /* use cached */ }
    // Fetch vacation balance for this employee
    if (item.employee_id) {
      setBalanceLoading(true);
      try {
        const balRes = await fetch(`${API_BASE}/vacations/employee/${item.employee_id}/balance`, { headers: getAuthHeaders() });
        if (balRes.ok) {
          const balData = await balRes.json();
          setVacationBalance(balData);
        }
      } catch { /* ignore */ }
      finally { setBalanceLoading(false); }
    }
  };

  // Approve
  const handleApprove = async () => {
    if (!selectedVacation) return;
    setActionLoading(true);
    try {
      const res = await fetch(`${API_BASE}/vacations/${selectedVacation.id}/approve`, {
        method: 'POST',
        headers: getAuthHeaders(),
      });
      if (res.ok) {
        toast.success('Férias aprovadas com sucesso!', { duration: 4000 });
        setShowDetail(false);
        setSelectedVacation(null);
        setRefreshKey(k => k + 1);
      } else {
        const err = await res.json().catch(() => null);
        toast.error(err?.detail || 'Erro ao aprovar férias', { duration: 5000 });
      }
    } catch {
      toast.error('Erro de conexão', { duration: 5000 });
    } finally {
      setActionLoading(false);
    }
  };

  // Reject
  const handleReject = async () => {
    if (!selectedVacation) return;
    setActionLoading(true);
    try {
      const params = rejectReason ? `?reason=${encodeURIComponent(rejectReason)}` : '';
      const res = await fetch(`${API_BASE}/vacations/${selectedVacation.id}/reject${params}`, {
        method: 'POST',
        headers: getAuthHeaders(),
      });
      if (res.ok) {
        toast.success('Férias rejeitadas', { duration: 4000 });
        setShowDetail(false);
        setSelectedVacation(null);
        setShowRejectInput(false);
        setRejectReason('');
        setRefreshKey(k => k + 1);
      } else {
        const err = await res.json().catch(() => null);
        toast.error(err?.detail || 'Erro ao rejeitar férias', { duration: 5000 });
      }
    } catch {
      toast.error('Erro de conexão', { duration: 5000 });
    } finally {
      setActionLoading(false);
    }
  };

  // Cancel (delete)
  const handleCancel = async () => {
    if (!selectedVacation) return;
    setActionLoading(true);
    try {
      const res = await fetch(`${API_BASE}/vacations/${selectedVacation.id}`, {
        method: 'DELETE',
        headers: getAuthHeaders(),
      });
      if (res.ok || res.status === 204) {
        toast.success('Solicitação cancelada', { duration: 4000 });
        setShowDetail(false);
        setSelectedVacation(null);
        setRefreshKey(k => k + 1);
      } else {
        const err = await res.json().catch(() => null);
        toast.error(err?.detail || 'Erro ao cancelar solicitação', { duration: 5000 });
      }
    } catch {
      toast.error('Erro de conexão', { duration: 5000 });
    } finally {
      setActionLoading(false);
    }
  };

  const handleSyncSolides = async () => {
    setSyncingSolides(true);
    try {
      const res = await fetch(`${API_BASE}/vacations/sync-solides`, {
        method: 'POST',
        headers: getAuthHeaders(),
      });
      const data = await res.json().catch(() => null);
      if (res.ok && data?.success) {
        toast.success(`Sync Sólides: ${data.total_importadas ?? 0} importadas, ${data.total_atualizadas ?? 0} atualizadas`, { duration: 5000 });
        setRefreshKey(k => k + 1);
      } else {
        toast.error(data?.reason || data?.detail || 'Erro ao sincronizar com Sólides', { duration: 5000 });
      }
    } catch {
      toast.error('Erro de conexão ao sincronizar Sólides', { duration: 5000 });
    } finally {
      setSyncingSolides(false);
    }
  };

  return (
    <div className="space-y-6 pb-28">
      {/* Header */}
      <PageHeader
        icon={<Sun className="h-5 w-5" />}
        title="Gestão de Férias"
        subtitle="Programação e controle de férias dos colaboradores"
        actions={(
          <>
            <Button type="button" variant="ghost" size="sm" onClick={() => router.push('/modulos/dp')}>
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <Button type="button" size="sm" variant="outline" onClick={handleSyncSolides} disabled={syncingSolides}>
              {syncingSolides ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Calendar className="h-4 w-4 mr-1" />}
              Sync Sólides
            </Button>
            <Button type="button" size="sm" onClick={() => setShowForm(true)}>
              <Plus className="h-4 w-4 mr-1" /> Solicitar Férias
            </Button>
          </>
        )}
      />

      {/* Status Summary Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card className={`cursor-pointer transition-colors ${filtroStatus === 'todos' ? 'ring-2 ring-primary' : ''}`} onClick={() => setFiltroStatus('todos')}>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Total</p>
                <p className="font-data text-2xl font-semibold tabular-nums">{statusCounts.total}</p>
              </div>
              <Calendar className="h-8 w-8 text-muted-foreground" />
            </div>
          </CardContent>
        </Card>
        <Card className={`cursor-pointer transition-colors ${filtroStatus === 'pendente' ? 'ring-2 ring-yellow-500' : ''}`} onClick={() => setFiltroStatus('pendente')}>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Pendentes</p>
                <p className="font-data text-2xl font-semibold tabular-nums text-yellow-600">{statusCounts.pendente}</p>
              </div>
              <Clock className="h-8 w-8 text-yellow-500" />
            </div>
          </CardContent>
        </Card>
        <Card className={`cursor-pointer transition-colors ${filtroStatus === 'aprovado' ? 'ring-2 ring-green-500' : ''}`} onClick={() => setFiltroStatus('aprovado')}>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Aprovadas</p>
                <p className="font-data text-2xl font-semibold tabular-nums text-green-600">{statusCounts.aprovado}</p>
              </div>
              <CheckCircle className="h-8 w-8 text-green-500" />
            </div>
          </CardContent>
        </Card>
        <Card className={`cursor-pointer transition-colors ${filtroStatus === 'rejeitado' ? 'ring-2 ring-red-500' : ''}`} onClick={() => setFiltroStatus('rejeitado')}>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Rejeitadas</p>
                <p className="font-data text-2xl font-semibold tabular-nums text-red-600">{statusCounts.rejeitado}</p>
              </div>
              <XCircle className="h-8 w-8 text-red-500" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Status Filter Badges */}
      <div className="flex gap-2 flex-wrap">
        <Badge
          className={`cursor-pointer ${filtroStatus === 'todos' ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'}`}
          onClick={() => setFiltroStatus('todos')}
        >
          Todos
        </Badge>
        {Object.entries(statusConfig).map(([key, val]) => (
          <Badge
            key={key}
            className={`cursor-pointer ${filtroStatus === key ? val.className : 'bg-muted text-muted-foreground'}`}
            onClick={() => setFiltroStatus(key)}
          >
            {val.label}
          </Badge>
        ))}
      </div>

      {/* Create Form */}
      {showForm && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Solicitar Férias / Afastamento</CardTitle>
              <Button type="button" variant="ghost" size="sm" onClick={() => { setShowForm(false); setFormErrors({}); }}>
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
                  {employees.map((emp: any) => (
                    <option key={emp.id} value={emp.id}>{emp.nome || emp.name}</option>
                  ))}
                </select>
                {formErrors.employee_id && <p className="text-red-500 text-xs mt-1">{formErrors.employee_id}</p>}
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Tipo</label>
                <select
                  value={formData.type}
                  onChange={e => setFormData(p => ({ ...p, type: e.target.value }))}
                  className="w-full px-3 py-2 border rounded-md text-sm"
                >
                  <option value="ferias">Férias</option>
                  <option value="afastamento">Afastamento</option>
                  <option value="licenca">Licença</option>
                  <option value="folga">Folga</option>
                </select>
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Data Início *</label>
                <input
                  type="date"
                  value={formData.start_date}
                  onChange={e => { setFormData(p => ({ ...p, start_date: e.target.value })); setFormErrors(p => ({ ...p, start_date: '' })); }}
                  className={`w-full px-3 py-2 border rounded-md text-sm ${formErrors.start_date ? 'border-red-500' : ''}`}
                />
                {formErrors.start_date && <p className="text-red-500 text-xs mt-1">{formErrors.start_date}</p>}
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Data Fim *</label>
                <input
                  type="date"
                  value={formData.end_date}
                  onChange={e => { setFormData(p => ({ ...p, end_date: e.target.value })); setFormErrors(p => ({ ...p, end_date: '' })); }}
                  className={`w-full px-3 py-2 border rounded-md text-sm ${formErrors.end_date ? 'border-red-500' : ''}`}
                />
                {formErrors.end_date && <p className="text-red-500 text-xs mt-1">{formErrors.end_date}</p>}
              </div>
              {formData.start_date && formData.end_date && formData.start_date <= formData.end_date && (
                <div className="md:col-span-2">
                  <p className="text-sm text-muted-foreground">
                    Periodo: {formatDate(formData.start_date)} a {formatDate(formData.end_date)} ({Math.ceil((new Date(formData.end_date).getTime() - new Date(formData.start_date).getTime()) / (1000 * 60 * 60 * 24)) + 1} dias)
                  </p>
                </div>
              )}
              <div>
                <label className="text-sm font-medium mb-1 block">Motivo</label>
                <input
                  type="text"
                  value={formData.reason}
                  onChange={e => setFormData(p => ({ ...p, reason: e.target.value }))}
                  className="w-full px-3 py-2 border rounded-md text-sm"
                  placeholder="Motivo da solicitação"
                />
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Observações</label>
                <input
                  type="text"
                  value={formData.notes}
                  onChange={e => setFormData(p => ({ ...p, notes: e.target.value }))}
                  className="w-full px-3 py-2 border rounded-md text-sm"
                  placeholder="Observações adicionais"
                />
              </div>
            </div>
            <div className="flex gap-2 mt-4">
              <Button type="button" size="sm" disabled={saving} onClick={handleCreate}>
                {saving ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Save className="h-4 w-4 mr-1" />}
                {saving ? 'Salvando...' : 'Criar Solicitação'}
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={() => { setShowForm(false); setFormErrors({}); }}>Cancelar</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Main Table */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Solicitações de Férias</CardTitle>
            <div className="relative w-64">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <input
                type="text"
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
                placeholder="Buscar por nome ou tipo..."
                className="w-full pl-9 pr-3 py-2 border rounded-md text-sm"
              />
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : filteredData.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
              <Inbox className="h-12 w-12 mb-3" />
              <p className="font-medium">Nenhuma solicitacao de ferias encontrada</p>
              <p className="text-sm text-muted-foreground mt-1">
                {searchTerm ? 'Tente outra busca.' : filtroStatus !== 'todos' ? 'Nenhum registro com esse status.' : 'Clique em "Solicitar Férias" para criar uma solicitacao.'}
              </p>
            </div>
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="cursor-pointer select-none" onClick={() => handleSort('employee_name')}>Colaborador{sortIcon('employee_name')}</TableHead>
                    <TableHead className="cursor-pointer select-none" onClick={() => handleSort('type')}>Tipo{sortIcon('type')}</TableHead>
                    <TableHead className="cursor-pointer select-none" onClick={() => handleSort('start_date')}>Periodo{sortIcon('start_date')}</TableHead>
                    <TableHead>Dias</TableHead>
                    <TableHead className="cursor-pointer select-none" onClick={() => handleSort('status')}>Status{sortIcon('status')}</TableHead>
                    <TableHead className="cursor-pointer select-none" onClick={() => handleSort('created_at')}>Criado em{sortIcon('created_at')}</TableHead>
                    <TableHead>Ações</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {paginatedData.map((item) => {
                    const st = statusConfig[item.status] || { label: item.status, className: 'bg-gray-500 text-white', icon: null };
                    const tp = typeConfig[item.type] || { label: item.type, className: 'bg-gray-100 text-gray-800' };
                    return (
                      <TableRow key={item.id}>
                        <TableCell className="font-medium">{item.employee_name || '-'}</TableCell>
                        <TableCell><Badge className={tp.className}>{tp.label}</Badge></TableCell>
                        <TableCell>{formatDate(item.start_date)} - {formatDate(item.end_date)}</TableCell>
                        <TableCell>{item.days || '-'}</TableCell>
                        <TableCell>
                          <Badge className={st.className}>
                            <span className="flex items-center gap-1">{st.icon} {st.label}</span>
                          </Badge>
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">{formatDateTime(item.created_at)}</TableCell>
                        <TableCell>
                          <div className="flex gap-1">
                            <Button variant="outline" size="sm" onClick={() => handleViewDetail(item)}>
                              <Eye className="h-3.5 w-3.5 mr-1" /> Detalhes
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>

              {/* Pagination */}
              <div className="flex items-center justify-between mt-4 text-sm">
                <span className="text-muted-foreground">
                  {filteredData.length} registro{filteredData.length !== 1 ? 's' : ''} — Pagina {currentPage} de {totalPages}
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
      {showDetail && selectedVacation && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <Card className="w-full max-w-2xl max-h-[90vh] overflow-y-auto">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="flex items-center gap-2">
                  <Sun className="h-5 w-5" />
                  Detalhes da Solicitação
                </CardTitle>
                <Button type="button" variant="ghost" size="sm" onClick={() => { setShowDetail(false); setSelectedVacation(null); setShowRejectInput(false); }}>
                  <X className="h-4 w-4" />
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Status Badge */}
              <div className="flex items-center gap-3">
                {(() => {
                  const st = statusConfig[selectedVacation.status] || { label: selectedVacation.status, className: 'bg-gray-500 text-white', icon: null };
                  return <Badge className={`text-sm px-3 py-1 ${st.className}`}><span className="flex items-center gap-1">{st.icon} {st.label}</span></Badge>;
                })()}
                {(() => {
                  const tp = typeConfig[selectedVacation.type] || { label: selectedVacation.type, className: 'bg-gray-100 text-gray-800' };
                  return <Badge className={tp.className}>{tp.label}</Badge>;
                })()}
              </div>

              {/* Info Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <p className="text-sm text-muted-foreground">Colaborador</p>
                  <p className="font-medium">{selectedVacation.employee_name || '-'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Dias</p>
                  <p className="font-medium">{selectedVacation.days || '-'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Data Início</p>
                  <p className="font-medium">{formatDate(selectedVacation.start_date)}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Data Fim</p>
                  <p className="font-medium">{formatDate(selectedVacation.end_date)}</p>
                </div>
                {selectedVacation.reason && (
                  <div className="md:col-span-2">
                    <p className="text-sm text-muted-foreground">Motivo</p>
                    <p className="font-medium">{selectedVacation.reason}</p>
                  </div>
                )}
                {selectedVacation.notes && (
                  <div className="md:col-span-2">
                    <p className="text-sm text-muted-foreground">Observações</p>
                    <p className="font-medium">{selectedVacation.notes}</p>
                  </div>
                )}
                {selectedVacation.rejected_reason && (
                  <div className="md:col-span-2">
                    <p className="text-sm text-muted-foreground text-red-600">Motivo da Rejeicao</p>
                    <p className="font-medium text-red-600">{selectedVacation.rejected_reason}</p>
                  </div>
                )}
                {selectedVacation.approved_at && (
                  <div>
                    <p className="text-sm text-muted-foreground">Aprovado em</p>
                    <p className="font-medium">{formatDateTime(selectedVacation.approved_at)}</p>
                  </div>
                )}
                <div>
                  <p className="text-sm text-muted-foreground">Criado em</p>
                  <p className="font-medium">{formatDateTime(selectedVacation.created_at)}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Atualizado em</p>
                  <p className="font-medium">{formatDateTime(selectedVacation.updated_at)}</p>
                </div>
              </div>

              {/* Vacation Balance */}
              <div className="border rounded-md p-3 bg-muted/30">
                <p className="text-sm font-medium mb-2 flex items-center gap-1"><UserCheck className="h-4 w-4" /> Saldo de Férias</p>
                {balanceLoading ? (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Carregando saldo...</div>
                ) : vacationBalance ? (
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                    <div><span className="text-muted-foreground">Dias disponiveis:</span><br /><span className="font-bold text-green-600">{vacationBalance.days_available ?? vacationBalance.saldo_dias ?? '-'}</span></div>
                    <div><span className="text-muted-foreground">Dias usados:</span><br /><span className="font-bold">{vacationBalance.days_used ?? vacationBalance.dias_usados ?? '-'}</span></div>
                    <div><span className="text-muted-foreground">Dias totais:</span><br /><span className="font-bold">{vacationBalance.days_total ?? vacationBalance.dias_direito ?? '-'}</span></div>
                    <div><span className="text-muted-foreground">Periodo aquisitivo:</span><br /><span className="font-bold">{vacationBalance.acquisition_period ?? vacationBalance.periodo_aquisitivo ?? '-'}</span></div>
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">Saldo nao disponivel</p>
                )}
              </div>

              {/* Reject reason input */}
              {showRejectInput && (
                <div>
                  <label className="text-sm font-medium mb-1 block">Motivo da rejeicao (opcional)</label>
                  <textarea
                    value={rejectReason}
                    onChange={e => setRejectReason(e.target.value)}
                    className="w-full px-3 py-2 border rounded-md text-sm"
                    rows={3}
                    placeholder="Informe o motivo da rejeicao..."
                  />
                </div>
              )}

              {/* Actions */}
              <div className="flex gap-2 pt-4 border-t">
                {selectedVacation.status === 'pendente' && (
                  <>
                    <Button
                      type="button"
                      size="sm"
                      disabled={actionLoading}
                      onClick={handleApprove}
                      className="bg-green-600 hover:bg-green-700 text-white"
                    >
                      {actionLoading ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <CheckCircle className="h-4 w-4 mr-1" />}
                      Aprovar
                    </Button>
                    {!showRejectInput ? (
                      <Button
                        type="button"
                        variant="destructive"
                        size="sm"
                        disabled={actionLoading}
                        onClick={() => setShowRejectInput(true)}
                      >
                        <XCircle className="h-4 w-4 mr-1" /> Rejeitar
                      </Button>
                    ) : (
                      <Button
                        type="button"
                        variant="destructive"
                        size="sm"
                        disabled={actionLoading}
                        onClick={handleReject}
                      >
                        {actionLoading ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <XCircle className="h-4 w-4 mr-1" />}
                        Confirmar Rejeicao
                      </Button>
                    )}
                  </>
                )}
                {(selectedVacation.status === 'pendente' || selectedVacation.status === 'aprovado') && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={actionLoading}
                    onClick={handleCancel}
                  >
                    <AlertTriangle className="h-4 w-4 mr-1" /> Cancelar Solicitação
                  </Button>
                )}
                <Button type="button" variant="ghost" size="sm" onClick={() => { setShowDetail(false); setSelectedVacation(null); setShowRejectInput(false); }}>
                  Fechar
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
