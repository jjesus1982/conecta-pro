'use client';

import { useState, useEffect, useMemo } from 'react';
import {
  FileText, ArrowLeft, Inbox, Loader2, Plus, X, Save, Search,
  ChevronLeft, ChevronRight as ChevronRightIcon, Pencil, FileDown,
  Filter,
} from 'lucide-react';
import { toast } from 'sonner';
import { useRouter } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { PageHeader } from '@/components/ui/page-header';

const API_BASE = '/api/v1/people-management/hr';

function getAuthHeaders() {
  const token = typeof window !== 'undefined'
    ? (localStorage.getItem('access_token') || localStorage.getItem('token'))
    : null;
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

const contractTypeLabels: Record<string, string> = {
  clt_indeterminate: 'CLT Indeterminado',
  clt_determinate: 'CLT Determinado',
  temporary: 'Temporário',
  intermittent: 'Intermitente',
  apprentice: 'Aprendiz',
  intern: 'Estagiário',
};

const contractTypeOptions = [
  { value: 'clt_indeterminate', label: 'CLT - Prazo Indeterminado' },
  { value: 'clt_determinate', label: 'CLT - Prazo Determinado' },
  { value: 'temporary', label: 'Temporário' },
  { value: 'intermittent', label: 'Intermitente' },
  { value: 'apprentice', label: 'Aprendiz' },
  { value: 'intern', label: 'Estagiário' },
];

const statusConfig: Record<string, { label: string; className: string }> = {
  current: { label: 'Vigente', className: 'bg-green-500 text-white' },
  ended: { label: 'Encerrado', className: 'bg-gray-500 text-white' },
};

function deriveStatus(contract: any): string {
  if (contract.is_current) return 'current';
  return 'ended';
}

function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '-';
  const parts = String(dateStr).split('T')[0]?.split('-') ?? [];
  if (parts.length === 3) return `${parts[2]}/${parts[1]}/${parts[0]}`;
  return dateStr ?? '-';
}

function formatCurrency(value: number | null | undefined): string {
  if (value == null) return 'R$ 0,00';
  return `R$ ${Number(value).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`;
}

const PAGE_SIZE = 10;

const emptyFormData = {
  employee_id: '',
  type: 'clt_indeterminate',
  start_date: '',
  end_date: '',
  base_salary: '',
  weekly_hours: '44',
  work_schedule: '',
  job_title: '',
  department: '',
  cost_center: '',
  hazard_pay_percent: '',
  unhealthy_pay_percent: '',
  night_shift_percent: '',
  union_name: '',
  union_code: '',
  notes: '',
};

export default function ContratosPage() {
  const router = useRouter();

  // Data state
  const [contratos, setContratos] = useState<any[]>([]);
  const [employees, setEmployees] = useState<any[]>([]);
  // Assinatura universal: status geral por contrato (EMPLOYEE + COMPANY).
  const [sigStatus, setSigStatus] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);

  // Filter / search / sort / pagination
  const [filtroStatus, setFiltroStatus] = useState<string>('todos');
  const [searchTerm, setSearchTerm] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [sortField, setSortField] = useState<string>('start_date');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  // Create form
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState({ ...emptyFormData });
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});

  // Edit / detail
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editData, setEditData] = useState<Record<string, any>>({});
  const [editSaving, setEditSaving] = useState(false);

  // Detail panel
  const [detailContract, setDetailContract] = useState<any | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // Load contracts using the paginated list endpoint + employees for name lookup
  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const [contractsRes, empRes] = await Promise.all([
          fetch(`${API_BASE}/contracts?page=1&page_size=100`, { headers: getAuthHeaders() }),
          fetch(`${API_BASE}/employees?page_size=100`, { headers: getAuthHeaders() }),
        ]);

        if (contractsRes.ok) {
          const contractsData = await contractsRes.json();
          setContratos(contractsData.items || contractsData || []);
        } else {
          toast.error('Erro ao carregar contratos', { duration: 4000 });
          setContratos([]);
        }

        if (empRes.ok) {
          const empData = await empRes.json();
          setEmployees(empData.items || empData || []);
        }
      } catch {
        toast.error('Erro de conexão ao carregar dados', { duration: 4000 });
        setContratos([]);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [refreshKey]);

  // Employee name lookup map (colaboradores ativos)
  const employeeMap = useMemo(() => {
    const map: Record<string, string> = {};
    employees.forEach((emp: any) => {
      map[emp.id] = emp.nome || emp.name || 'N/A';
    });
    return map;
  }, [employees]);

  // Resolve nome do colaborador SEM cair no UUID cru.
  // Prioridade: employee_name do backend (JOIN autoritativo, sempre preenchido
  // quando o colaborador existe) → mapa de ativos → fallback honesto p/ removido.
  const resolveEmployeeName = (contract: any): string => {
    const backendName = contract?.employee_name;
    if (backendName && String(backendName).trim()) return String(backendName);
    const mapped = employeeMap[contract?.employee_id];
    if (mapped && mapped !== 'N/A') return mapped;
    const id = contract?.employee_id ? String(contract.employee_id) : '';
    return id ? `(colaborador removido) #${id.slice(0, 8)}` : '(colaborador removido)';
  };

  // Reset page when filter/search changes
  useEffect(() => { setCurrentPage(1); }, [filtroStatus, searchTerm]);

  // Filtered + searched + sorted
  const filteredData = useMemo(() => {
    let items = contratos;

    // Status filter
    if (filtroStatus === 'current') {
      items = items.filter(c => c.is_current === true);
    } else if (filtroStatus === 'ended') {
      items = items.filter(c => !c.is_current);
    } else if (contractTypeOptions.some(opt => opt.value === filtroStatus)) {
      // Filter by contract type
      items = items.filter(c => c.type === filtroStatus);
    }

    // Search
    if (searchTerm.trim()) {
      const term = searchTerm.toLowerCase();
      items = items.filter(c => {
        const empName = resolveEmployeeName(c).toLowerCase();
        const contractType = (contractTypeLabels[c.type] || c.type || '').toLowerCase();
        const jobTitle = (c.job_title || '').toLowerCase();
        const dept = (c.department || '').toLowerCase();
        return empName.includes(term) || contractType.includes(term) || jobTitle.includes(term) || dept.includes(term);
      });
    }

    // Sort
    if (sortField) {
      items = [...items].sort((a, b) => {
        let va: string, vb: string;
        if (sortField === 'employee_name') {
          va = resolveEmployeeName(a).toLowerCase();
          vb = resolveEmployeeName(b).toLowerCase();
        } else if (sortField === 'base_salary') {
          const na = Number(a.base_salary || 0);
          const nb = Number(b.base_salary || 0);
          return sortDir === 'asc' ? na - nb : nb - na;
        } else {
          va = String(a[sortField] || '').toLowerCase();
          vb = String(b[sortField] || '').toLowerCase();
        }
        return sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
      });
    }

    return items;
  }, [contratos, filtroStatus, searchTerm, sortField, sortDir, employeeMap]);

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

  // --- Create contract ---
  const handleCreate = async () => {
    const errors: Record<string, string> = {};
    if (!formData.employee_id) errors.employee_id = 'Selecione um colaborador';
    if (!formData.start_date) errors.start_date = 'Data de início é obrigatória';
    if (!formData.base_salary || Number(formData.base_salary) <= 0) errors.base_salary = 'Salário base é obrigatório';
    if (Object.keys(errors).length > 0) {
      setFormErrors(errors);
      toast.error('Corrija os campos destacados', { duration: 4000 });
      return;
    }

    setSaving(true);
    try {
      const payload: Record<string, any> = {
        employee_id: formData.employee_id,
        type: formData.type,
        start_date: formData.start_date,
        base_salary: parseFloat(formData.base_salary),
      };
      if (formData.end_date) payload.end_date = formData.end_date;
      if (formData.weekly_hours) payload.weekly_hours = parseFloat(formData.weekly_hours);
      if (formData.work_schedule) payload.work_schedule = formData.work_schedule;
      if (formData.job_title) payload.job_title = formData.job_title;
      if (formData.department) payload.department = formData.department;
      if (formData.cost_center) payload.cost_center = formData.cost_center;
      if (formData.hazard_pay_percent) payload.hazard_pay_percent = parseFloat(formData.hazard_pay_percent);
      if (formData.unhealthy_pay_percent) payload.unhealthy_pay_percent = parseFloat(formData.unhealthy_pay_percent);
      if (formData.night_shift_percent) payload.night_shift_percent = parseFloat(formData.night_shift_percent);
      if (formData.union_name) payload.union_name = formData.union_name;
      if (formData.union_code) payload.union_code = formData.union_code;
      if (formData.notes) payload.notes = formData.notes;

      const res = await fetch(`${API_BASE}/contracts`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        setShowForm(false);
        setFormData({ ...emptyFormData });
        setFormErrors({});
        setRefreshKey(k => k + 1);
        toast.success('Contrato criado com sucesso!', { duration: 4000 });
      } else {
        const err = await res.json().catch(() => null);
        toast.error(err?.detail || 'Erro ao criar contrato', { duration: 5000 });
      }
    } catch {
      toast.error('Erro de conexão', { duration: 5000 });
    } finally {
      setSaving(false);
    }
  };

  // --- Edit contract (inline) ---
  const startEdit = (contract: any) => {
    setEditingId(contract.id);
    setEditData({
      end_date: contract.end_date ? String(contract.end_date).split('T')[0] : '',
      base_salary: contract.base_salary || '',
      weekly_hours: contract.weekly_hours || '',
      job_title: contract.job_title || '',
      department: contract.department || '',
      notes: contract.notes || '',
      hazard_pay_percent: contract.hazard_pay_percent || '',
      unhealthy_pay_percent: contract.unhealthy_pay_percent || '',
      night_shift_percent: contract.night_shift_percent || '',
    });
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditData({});
  };

  const saveEdit = async () => {
    if (!editingId) return;
    setEditSaving(true);
    try {
      const payload: Record<string, any> = {};
      if (editData.end_date) payload.end_date = editData.end_date;
      if (editData.base_salary) payload.base_salary = parseFloat(editData.base_salary);
      if (editData.weekly_hours) payload.weekly_hours = parseFloat(editData.weekly_hours);
      if (editData.job_title !== undefined) payload.job_title = editData.job_title || null;
      if (editData.department !== undefined) payload.department = editData.department || null;
      if (editData.notes !== undefined) payload.notes = editData.notes || null;
      if (editData.hazard_pay_percent) payload.hazard_pay_percent = parseFloat(editData.hazard_pay_percent);
      if (editData.unhealthy_pay_percent) payload.unhealthy_pay_percent = parseFloat(editData.unhealthy_pay_percent);
      if (editData.night_shift_percent) payload.night_shift_percent = parseFloat(editData.night_shift_percent);

      const res = await fetch(`${API_BASE}/contracts/${editingId}`, {
        method: 'PATCH',
        headers: getAuthHeaders(),
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        setEditingId(null);
        setEditData({});
        setRefreshKey(k => k + 1);
        toast.success('Contrato atualizado com sucesso!', { duration: 4000 });
      } else {
        const err = await res.json().catch(() => null);
        toast.error(err?.detail || 'Erro ao atualizar contrato', { duration: 5000 });
      }
    } catch {
      toast.error('Erro de conexão', { duration: 5000 });
    } finally {
      setEditSaving(false);
    }
  };

  // --- Detail panel ---
  const openDetail = async (contractId: string) => {
    setDetailLoading(true);
    setDetailContract(null);
    try {
      const res = await fetch(`${API_BASE}/contracts/${contractId}`, { headers: getAuthHeaders() });
      if (res.ok) {
        const data = await res.json();
        setDetailContract(data);
      } else {
        toast.error('Erro ao carregar detalhes do contrato', { duration: 4000 });
      }
    } catch {
      toast.error('Erro de conexão', { duration: 4000 });
    } finally {
      setDetailLoading(false);
    }
  };

  // --- Gerar Contrato CLT HTML ---
  const handleGerarContratoHtml = async (employeeId: string) => {
    try {
      const res = await fetch(`${API_BASE}/contracts/employee/${employeeId}/gerar-contrato-html`, {
        method: 'GET',
        headers: getAuthHeaders(),
      });
      if (res.ok) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        const cd = res.headers.get('Content-Disposition') || '';
        const match = cd.match(/filename="([^"]+)"/);
        a.download = match?.[1] ?? `contrato_trabalho_${employeeId.slice(0, 8)}.html`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
        toast.success('Contrato CLT gerado e baixado!', { duration: 4000 });
      } else {
        const err = await res.json().catch(() => null);
        toast.error(err?.detail || 'Erro ao gerar contrato', { duration: 5000 });
      }
    } catch {
      toast.error('Erro de conexão', { duration: 5000 });
    }
  };

  // --- Download PDF do contrato ---
  const handleGenerateDocument = async (contractId: string) => {
    try {
      const res = await fetch(`${API_BASE}/contracts/${contractId}/pdf`, {
        method: 'GET',
        headers: getAuthHeaders(),
      });
      if (res.ok) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `contrato_${contractId.slice(0, 8)}.pdf`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
        toast.success('PDF gerado e baixado com sucesso!', { duration: 4000 });
        loadSigStatus(contractId);  // gerar o PDF cria a solicitação de assinatura
      } else {
        const err = await res.json().catch(() => null);
        toast.error(err?.detail || 'Erro ao gerar PDF', { duration: 5000 });
      }
    } catch {
      toast.error('Erro de conexão', { duration: 5000 });
    }
  };

  // Consulta o status de assinatura (motor universal) de um contrato de trabalho.
  const loadSigStatus = async (contractId: string) => {
    try {
      const res = await fetch(`/api/v1/signatures/document/contract/${contractId}`, { headers: getAuthHeaders() });
      if (res.ok) {
        const data = await res.json();
        setSigStatus((prev) => ({ ...prev, [contractId]: data?.status_geral || 'none' }));
      }
    } catch { /* silencioso */ }
  };

  const sigBadge = (contractId: string) => {
    const s = sigStatus[contractId];
    if (!s || s === 'none') return null;
    const cls: Record<string, string> = { pending: 'bg-yellow-100 text-yellow-800', partial: 'bg-blue-100 text-blue-800', completed: 'bg-green-100 text-green-800' };
    const label: Record<string, string> = { pending: 'Assinatura pendente', partial: 'Assinatura parcial', completed: 'Assinado' };
    return <Badge className={`ml-1 ${cls[s] || 'bg-gray-100 text-gray-800'}`}>{label[s] || s}</Badge>;
  };

  // Carrega o status de assinatura dos contratos visíveis (uma vez cada).
  useEffect(() => {
    paginatedData.forEach((c: any) => { if (c?.id && sigStatus[c.id] === undefined) loadSigStatus(c.id); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paginatedData]);

  return (
    <div className="space-y-6 pb-28">
      {/* Header */}
      <PageHeader
        icon={<FileText className="h-5 w-5" />}
        title="Contratos de Trabalho"
        subtitle="Gerencie contratos de trabalho dos colaboradores"
        actions={(
          <>
            <Button type="button" variant="ghost" size="sm" onClick={() => router.push('/modulos/dp')}>
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={() => setFiltroStatus('todos')}>
              <Filter className="h-4 w-4 mr-1" /> Todos
            </Button>
            <Button type="button" size="sm" onClick={() => setShowForm(true)}>
              <Plus className="h-4 w-4 mr-1" /> Novo Contrato
            </Button>
          </>
        )}
      />

      {/* Status filter badges */}
      <div className="flex gap-2 flex-wrap">
        {Object.entries(statusConfig).map(([key, val]) => (
          <Badge
            key={key}
            className={`cursor-pointer ${filtroStatus === key ? val.className : 'bg-muted text-muted-foreground'}`}
            onClick={() => setFiltroStatus(prev => prev === key ? 'todos' : key)}
          >
            {val.label}
          </Badge>
        ))}
        {contractTypeOptions.map(opt => (
          <Badge
            key={opt.value}
            className={`cursor-pointer ${filtroStatus === opt.value ? 'bg-blue-500 text-white' : 'bg-muted text-muted-foreground'}`}
            onClick={() => setFiltroStatus(prev => prev === opt.value ? 'todos' : opt.value)}
          >
            {opt.label}
          </Badge>
        ))}
      </div>

      {/* Detail panel */}
      {detailContract && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Detalhes do Contrato</CardTitle>
              <Button type="button" variant="ghost" size="sm" onClick={() => setDetailContract(null)}>
                <X className="h-4 w-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {detailLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
                <div><span className="font-medium text-muted-foreground">Colaborador:</span><br />{resolveEmployeeName(detailContract)}</div>
                <div><span className="font-medium text-muted-foreground">Tipo:</span><br />{contractTypeLabels[detailContract.type] || detailContract.type}</div>
                <div><span className="font-medium text-muted-foreground">Status:</span><br /><Badge className={statusConfig[deriveStatus(detailContract)]?.className || 'bg-gray-500 text-white'}>{statusConfig[deriveStatus(detailContract)]?.label || 'N/A'}</Badge></div>
                <div><span className="font-medium text-muted-foreground">Data Início:</span><br />{formatDate(detailContract.start_date)}</div>
                <div><span className="font-medium text-muted-foreground">Data Fim:</span><br />{detailContract.end_date ? formatDate(detailContract.end_date) : 'Indeterminado'}</div>
                <div><span className="font-medium text-muted-foreground">Salário Base:</span><br />{formatCurrency(detailContract.base_salary)}</div>
                <div><span className="font-medium text-muted-foreground">Carga Horária:</span><br />{detailContract.weekly_hours ? `${detailContract.weekly_hours}h/semana` : '-'}</div>
                <div><span className="font-medium text-muted-foreground">Jornada:</span><br />{detailContract.work_schedule || '-'}</div>
                <div><span className="font-medium text-muted-foreground">Cargo:</span><br />{detailContract.job_title || '-'}</div>
                <div><span className="font-medium text-muted-foreground">Departamento:</span><br />{detailContract.department || '-'}</div>
                <div><span className="font-medium text-muted-foreground">Centro de Custo:</span><br />{detailContract.cost_center || '-'}</div>
                <div><span className="font-medium text-muted-foreground">Periculosidade:</span><br />{detailContract.hazard_pay_percent ? `${detailContract.hazard_pay_percent}%` : '-'}</div>
                <div><span className="font-medium text-muted-foreground">Insalubridade:</span><br />{detailContract.unhealthy_pay_percent ? `${detailContract.unhealthy_pay_percent}%` : '-'}</div>
                <div><span className="font-medium text-muted-foreground">Adicional Noturno:</span><br />{detailContract.night_shift_percent ? `${detailContract.night_shift_percent}%` : '-'}</div>
                <div><span className="font-medium text-muted-foreground">Sindicato:</span><br />{detailContract.union_name || '-'}</div>
                {detailContract.notes && (
                  <div className="md:col-span-3"><span className="font-medium text-muted-foreground">Observações:</span><br />{detailContract.notes}</div>
                )}
              </div>
            )}
            <div className="flex gap-2 mt-4">
              <Button type="button" variant="outline" size="sm" onClick={() => { startEdit(detailContract); setDetailContract(null); }}>
                <Pencil className="h-4 w-4 mr-1" /> Editar
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={() => handleGenerateDocument(detailContract.id)}>
                <FileDown className="h-4 w-4 mr-1" /> Gerar Documento
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={() => handleGerarContratoHtml(detailContract.employee_id)}>
                <FileDown className="h-4 w-4 mr-1" /> Contrato CLT (HTML)
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Create form */}
      {showForm && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Novo Contrato</CardTitle>
              <Button type="button" variant="ghost" size="sm" onClick={() => { setShowForm(false); setFormErrors({}); }}>
                <X className="h-4 w-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              <div>
                <label className="text-sm font-medium mb-1 block">Colaborador *</label>
                <select value={formData.employee_id} onChange={e => { setFormData(p => ({ ...p, employee_id: e.target.value })); setFormErrors(p => ({ ...p, employee_id: '' })); }} className={`w-full px-3 py-2 border rounded-md text-sm ${formErrors.employee_id ? 'border-red-500' : ''}`}>
                  <option value="">Selecione um colaborador</option>
                  {employees.map((emp: any) => <option key={emp.id} value={emp.id}>{emp.nome || emp.name}</option>)}
                </select>
                {formErrors.employee_id && <p className="text-red-500 text-xs mt-1">{formErrors.employee_id}</p>}
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Tipo de Contrato *</label>
                <select value={formData.type} onChange={e => setFormData(p => ({ ...p, type: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm">
                  {contractTypeOptions.map(opt => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
                </select>
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Data Início *</label>
                <input type="date" value={formData.start_date} onChange={e => { setFormData(p => ({ ...p, start_date: e.target.value })); setFormErrors(p => ({ ...p, start_date: '' })); }} className={`w-full px-3 py-2 border rounded-md text-sm ${formErrors.start_date ? 'border-red-500' : ''}`} />
                {formErrors.start_date && <p className="text-red-500 text-xs mt-1">{formErrors.start_date}</p>}
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Data Fim</label>
                <input type="date" value={formData.end_date} onChange={e => setFormData(p => ({ ...p, end_date: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" />
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Salário Base (R$) *</label>
                <input type="number" step="0.01" min="0" value={formData.base_salary} onChange={e => { setFormData(p => ({ ...p, base_salary: e.target.value })); setFormErrors(p => ({ ...p, base_salary: '' })); }} className={`w-full px-3 py-2 border rounded-md text-sm ${formErrors.base_salary ? 'border-red-500' : ''}`} placeholder="0.00" />
                {formErrors.base_salary && <p className="text-red-500 text-xs mt-1">{formErrors.base_salary}</p>}
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Carga Horária (h/semana)</label>
                <input type="number" step="1" min="0" max="44" value={formData.weekly_hours} onChange={e => setFormData(p => ({ ...p, weekly_hours: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" placeholder="44" />
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Jornada de Trabalho</label>
                <input type="text" value={formData.work_schedule} onChange={e => setFormData(p => ({ ...p, work_schedule: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" placeholder="Ex: 12x36, 6x1" maxLength={30} />
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Cargo</label>
                <input type="text" value={formData.job_title} onChange={e => setFormData(p => ({ ...p, job_title: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" placeholder="Ex: Vigilante" />
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Departamento</label>
                <input type="text" value={formData.department} onChange={e => setFormData(p => ({ ...p, department: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" placeholder="Ex: Operações" />
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Centro de Custo</label>
                <input type="text" value={formData.cost_center} onChange={e => setFormData(p => ({ ...p, cost_center: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" placeholder="Ex: CC-001" />
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Periculosidade (%)</label>
                <input type="number" step="0.01" min="0" max="100" value={formData.hazard_pay_percent} onChange={e => setFormData(p => ({ ...p, hazard_pay_percent: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" placeholder="30" />
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Insalubridade (%)</label>
                <input type="number" step="0.01" min="0" max="100" value={formData.unhealthy_pay_percent} onChange={e => setFormData(p => ({ ...p, unhealthy_pay_percent: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" placeholder="20" />
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Adicional Noturno (%)</label>
                <input type="number" step="0.01" min="0" max="100" value={formData.night_shift_percent} onChange={e => setFormData(p => ({ ...p, night_shift_percent: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" placeholder="20" />
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Sindicato</label>
                <input type="text" value={formData.union_name} onChange={e => setFormData(p => ({ ...p, union_name: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" placeholder="Nome do sindicato" />
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Código Sindical</label>
                <input type="text" value={formData.union_code} onChange={e => setFormData(p => ({ ...p, union_code: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" placeholder="Código do sindicato" />
              </div>
              <div className="md:col-span-2 lg:col-span-3">
                <label className="text-sm font-medium mb-1 block">Observações</label>
                <textarea value={formData.notes} onChange={e => setFormData(p => ({ ...p, notes: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" rows={2} placeholder="Anotações sobre o contrato..." />
              </div>
            </div>
            <div className="flex gap-2 mt-4">
              <Button type="button" size="sm" disabled={saving} onClick={handleCreate}>
                {saving ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Save className="h-4 w-4 mr-1" />}
                {saving ? 'Salvando...' : 'Criar Contrato'}
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={() => { setShowForm(false); setFormErrors({}); }}>Cancelar</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Edit inline panel */}
      {editingId && (
        <Card className="border-blue-300">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-blue-700">Editar Contrato</CardTitle>
              <Button type="button" variant="ghost" size="sm" onClick={cancelEdit}>
                <X className="h-4 w-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              <div>
                <label className="text-sm font-medium mb-1 block">Data Fim</label>
                <input type="date" value={editData.end_date || ''} onChange={e => setEditData(p => ({ ...p, end_date: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" />
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Salário Base (R$)</label>
                <input type="number" step="0.01" min="0" value={editData.base_salary || ''} onChange={e => setEditData(p => ({ ...p, base_salary: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" />
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Carga Horária (h/semana)</label>
                <input type="number" step="1" min="0" max="44" value={editData.weekly_hours || ''} onChange={e => setEditData(p => ({ ...p, weekly_hours: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" />
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Cargo</label>
                <input type="text" value={editData.job_title || ''} onChange={e => setEditData(p => ({ ...p, job_title: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" />
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Departamento</label>
                <input type="text" value={editData.department || ''} onChange={e => setEditData(p => ({ ...p, department: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" />
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Periculosidade (%)</label>
                <input type="number" step="0.01" min="0" max="100" value={editData.hazard_pay_percent || ''} onChange={e => setEditData(p => ({ ...p, hazard_pay_percent: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" />
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Insalubridade (%)</label>
                <input type="number" step="0.01" min="0" max="100" value={editData.unhealthy_pay_percent || ''} onChange={e => setEditData(p => ({ ...p, unhealthy_pay_percent: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" />
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Adicional Noturno (%)</label>
                <input type="number" step="0.01" min="0" max="100" value={editData.night_shift_percent || ''} onChange={e => setEditData(p => ({ ...p, night_shift_percent: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" />
              </div>
              <div className="md:col-span-2 lg:col-span-3">
                <label className="text-sm font-medium mb-1 block">Observações</label>
                <textarea value={editData.notes || ''} onChange={e => setEditData(p => ({ ...p, notes: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" rows={2} />
              </div>
            </div>
            <div className="flex gap-2 mt-4">
              <Button type="button" size="sm" disabled={editSaving} onClick={saveEdit}>
                {editSaving ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Save className="h-4 w-4 mr-1" />}
                {editSaving ? 'Salvando...' : 'Salvar Alterações'}
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={cancelEdit}>Cancelar</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Contracts table */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Contratos ({filteredData.length})</CardTitle>
            <div className="relative w-72">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <input
                type="text"
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
                placeholder="Buscar por nome, tipo, cargo..."
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
              <p className="font-medium">Nenhum contrato encontrado</p>
              <p className="text-sm text-muted-foreground mt-1">
                {searchTerm || filtroStatus !== 'todos'
                  ? 'Tente outra busca ou remova os filtros.'
                  : 'Clique em "Novo Contrato" para cadastrar.'}
              </p>
            </div>
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="cursor-pointer select-none" onClick={() => handleSort('employee_name')}>Colaborador{sortIcon('employee_name')}</TableHead>
                    <TableHead className="cursor-pointer select-none" onClick={() => handleSort('type')}>Tipo{sortIcon('type')}</TableHead>
                    <TableHead className="cursor-pointer select-none" onClick={() => handleSort('start_date')}>Início{sortIcon('start_date')}</TableHead>
                    <TableHead>Fim</TableHead>
                    <TableHead className="cursor-pointer select-none" onClick={() => handleSort('base_salary')}>Salário Base{sortIcon('base_salary')}</TableHead>
                    <TableHead>Cargo</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Ações</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {paginatedData.map((item: any) => {
                    const status = deriveStatus(item);
                    const st = statusConfig[status] || { label: status, className: 'bg-gray-500 text-white' };
                    return (
                      <TableRow key={item.id}>
                        <TableCell className="font-medium">{resolveEmployeeName(item)}</TableCell>
                        <TableCell>{contractTypeLabels[item.type] || item.type}</TableCell>
                        <TableCell>{formatDate(item.start_date)}</TableCell>
                        <TableCell>{item.end_date ? formatDate(item.end_date) : 'Indeterminado'}</TableCell>
                        <TableCell>{formatCurrency(item.base_salary)}</TableCell>
                        <TableCell>{item.job_title || '-'}</TableCell>
                        <TableCell><Badge className={st.className}>{st.label}</Badge>{sigBadge(item.id)}</TableCell>
                        <TableCell>
                          <div className="flex gap-1">
                            <Button variant="outline" size="sm" onClick={() => openDetail(item.id)}>
                              Detalhes
                            </Button>
                            <Button variant="ghost" size="sm" onClick={() => startEdit(item)} title="Editar">
                              <Pencil className="h-4 w-4" />
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
    </div>
  );
}
