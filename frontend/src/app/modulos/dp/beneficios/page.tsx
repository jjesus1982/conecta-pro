'use client';

import { useState, useEffect, useMemo } from 'react';
import { msgFromDetail } from '@/lib/string';
import { Gift, ArrowLeft, Inbox, Loader2, Plus, X, Save, Search, Filter, Edit, Trash2, ChevronLeft, ChevronRight as ChevronRightIcon, DollarSign } from 'lucide-react';
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

// Mapa de exibição alinhado ao vocabulário REAL gravado no banco (employee_benefits.status):
// active / inactive / cancelled (inglês minúsculo). Chips enviam/comparam esses valores.
const statusConfig: Record<string, { label: string; className: string }> = {
  active: { label: 'Ativo', className: 'bg-green-500 text-white' },
  inactive: { label: 'Inativo', className: 'bg-yellow-500 text-white' },
  cancelled: { label: 'Cancelado', className: 'bg-red-500 text-white' },
};

const typeLabels: Record<string, string> = {
  vale_transporte: 'Vale Transporte',
  vale_refeicao: 'Vale Refeição',
  vale_alimentacao: 'Vale Alimentação',
  plano_saude: 'Plano de Saúde',
  plano_odontologico: 'Plano Odontológico',
  seguro_vida: 'Seguro de Vida',
  auxilio_creche: 'Auxilio Creche',
  gym_pass: 'Gym Pass',
  other: 'Outro',
};

const typeOptions = [
  { value: 'vale_transporte', label: 'Vale Transporte' },
  { value: 'vale_refeicao', label: 'Vale Refeição' },
  { value: 'vale_alimentacao', label: 'Vale Alimentação' },
  { value: 'plano_saude', label: 'Plano de Saúde' },
  { value: 'plano_odontologico', label: 'Plano Odontológico' },
  { value: 'seguro_vida', label: 'Seguro de Vida' },
  { value: 'auxilio_creche', label: 'Auxilio Creche' },
  { value: 'gym_pass', label: 'Gym Pass' },
  { value: 'other', label: 'Outro' },
];

const fmt = (v: number | null | undefined) => `R$ ${(v || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`;

const PAGE_SIZE = 15;

export default function BeneficiosPage() {
  const router = useRouter();
  const [beneficios, setBeneficios] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [employees, setEmployees] = useState<any[]>([]);
  const [formData, setFormData] = useState({
    employee_id: '',
    type: 'vale_transporte',
    provider: '',
    plan_name: '',
    employee_contribution: '',
    company_contribution: '',
    start_date: '',
    end_date: '',
    card_number: '',
    notes: '',
  });
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});
  const [refreshKey, setRefreshKey] = useState(0);
  const [searchTerm, setSearchTerm] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [filtroStatus, setFiltroStatus] = useState<string>('todos');
  const [filtroType, setFiltroType] = useState<string>('todos');
  const [sortField, setSortField] = useState<string>('');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [selectedEmployeeTotal, setSelectedEmployeeTotal] = useState<string | null>(null);
  const [employeeTotal, setEmployeeTotal] = useState<Record<string, any> | null>(null);
  const [totalLoading, setTotalLoading] = useState(false);

  // Carrega o dataset COMPLETO para que cards, filtro por tipo e busca enxerguem TODOS os
  // registros — não apenas a página atual. O backend limita page_size<=100, então paginamos
  // no servidor (loop) e acumulamos tudo; a paginação exibida é client-side.
  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const SERVER_PAGE = 100;
        const all: any[] = [];
        let page = 1;
        // Primeira página traz o total; seguimos até cobri-lo (guarda de segurança em 50 páginas).
        for (let guard = 0; guard < 50; guard++) {
          const res = await fetch(`${API_BASE}/benefits?page=${page}&page_size=${SERVER_PAGE}`, { headers: getAuthHeaders() });
          if (!res.ok) break;
          const data = await res.json();
          const items = data.items || [];
          all.push(...items);
          const total = data.total ?? all.length;
          if (all.length >= total || items.length === 0) break;
          page += 1;
        }
        setBeneficios(all);
      } catch {
        setBeneficios([]);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [refreshKey]);

  // Load employees for the form
  useEffect(() => {
    async function loadEmployees() {
      try {
        const res = await fetch(`${API_BASE}/employees?page_size=100`, { headers: getAuthHeaders() });
        if (res.ok) {
          const data = await res.json();
          setEmployees(data.items || data || []);
        }
      } catch { /* skip */ }
    }
    loadEmployees();
  }, []);

  // Reset page on filter/search change
  useEffect(() => { setCurrentPage(1); }, [searchTerm, filtroStatus, filtroType]);

  // Filtro + busca + ordenação sobre o dataset COMPLETO (client-side).
  // Status comparado case-insensitive contra o valor real do banco.
  const filteredData = useMemo(() => {
    let items = [...beneficios];
    if (filtroStatus !== 'todos') {
      items = items.filter(b => String(b.status || '').toLowerCase() === filtroStatus.toLowerCase());
    }
    if (filtroType !== 'todos') {
      items = items.filter(b => b.type === filtroType);
    }
    if (searchTerm.trim()) {
      const term = searchTerm.toLowerCase();
      items = items.filter(b =>
        (b.employee_name || '').toLowerCase().includes(term) ||
        (b.type || '').toLowerCase().includes(term) ||
        (b.provider || '').toLowerCase().includes(term) ||
        (b.plan_name || '').toLowerCase().includes(term) ||
        (b.employee_id || '').toLowerCase().includes(term) ||
        (b.card_number || '').toLowerCase().includes(term)
      );
    }
    if (sortField) {
      items = [...items].sort((a, b) => {
        const va = String(a[sortField] || '').toLowerCase();
        const vb = String(b[sortField] || '').toLowerCase();
        return sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
      });
    }
    return items;
  }, [beneficios, filtroStatus, filtroType, searchTerm, sortField, sortDir]);

  // Paginação client-side sobre a lista já filtrada.
  const totalItems = filteredData.length;
  const totalPages = Math.max(1, Math.ceil(totalItems / PAGE_SIZE));
  const pagedData = useMemo(
    () => filteredData.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE),
    [filteredData, currentPage],
  );

  // Summary by type
  const tipoSummary = useMemo(() => {
    return beneficios.reduce((acc, b) => {
      const tipo = b.type || 'other';
      if (!acc[tipo]) acc[tipo] = { count: 0, total: 0 };
      acc[tipo].count++;
      acc[tipo].total += (b.company_contribution || 0);
      return acc;
    }, {} as Record<string, { count: number; total: number }>);
  }, [beneficios]);

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

  const resetForm = () => {
    setFormData({ employee_id: '', type: 'vale_transporte', provider: '', plan_name: '', employee_contribution: '', company_contribution: '', start_date: '', end_date: '', card_number: '', notes: '' });
    setFormErrors({});
    setEditingId(null);
  };

  const fetchEmployeeTotal = async (employeeId: string) => {
    setSelectedEmployeeTotal(employeeId);
    setTotalLoading(true);
    try {
      const res = await fetch(`${API_BASE}/benefits/employee/${employeeId}/total`, { headers: getAuthHeaders() });
      if (res.ok) {
        const data = await res.json();
        setEmployeeTotal(data);
      } else {
        setEmployeeTotal(null);
      }
    } catch { setEmployeeTotal(null); }
    finally { setTotalLoading(false); }
  };

  const openEditForm = (item: any) => {
    setEditingId(item.id);
    if (item.employee_id) fetchEmployeeTotal(item.employee_id);
    setFormData({
      employee_id: item.employee_id || '',
      type: item.type || 'vale_transporte',
      provider: item.provider || '',
      plan_name: item.plan_name || '',
      employee_contribution: item.employee_contribution != null ? String(item.employee_contribution) : '',
      company_contribution: item.company_contribution != null ? String(item.company_contribution) : '',
      start_date: item.start_date || '',
      end_date: item.end_date || '',
      card_number: item.card_number || '',
      notes: item.notes || '',
    });
    setShowForm(true);
  };

  const handleSave = async () => {
    const errors: Record<string, string> = {};
    if (!editingId && !formData.employee_id) errors.employee_id = 'Selecione um colaborador';
    if (!formData.type) errors.type = 'Selecione o tipo de beneficio';
    if (Object.keys(errors).length > 0) {
      setFormErrors(errors);
      toast.error('Corrija os campos destacados', { duration: 5000 });
      return;
    }
    setSaving(true);
    try {
      const payload: any = {
        type: formData.type,
        provider: formData.provider || null,
        plan_name: formData.plan_name || null,
        employee_contribution: formData.employee_contribution ? parseFloat(formData.employee_contribution) : null,
        company_contribution: formData.company_contribution ? parseFloat(formData.company_contribution) : null,
        start_date: formData.start_date || null,
        end_date: formData.end_date || null,
        card_number: formData.card_number || null,
        notes: formData.notes || null,
      };
      if (!editingId) {
        payload.employee_id = formData.employee_id;
      }

      const url = editingId ? `${API_BASE}/benefits/${editingId}` : `${API_BASE}/benefits`;
      const method = editingId ? 'PATCH' : 'POST';
      const res = await fetch(url, { method, headers: getAuthHeaders(), body: JSON.stringify(payload) });

      if (res.ok) {
        setShowForm(false);
        resetForm();
        setRefreshKey(k => k + 1);
        toast.success(editingId ? 'Benefício atualizado com sucesso!' : 'Benefício criado com sucesso!', { duration: 4000 });
      } else {
        const err = await res.json().catch(() => null);
        toast.error(msgFromDetail(err?.detail) || 'Erro ao salvar beneficio', { duration: 5000 });
      }
    } catch { toast.error('Erro de conexão', { duration: 5000 }); } finally { setSaving(false); }
  };

  const handleCancel = async (id: string) => {
    if (!confirm('Cancelar este beneficio?')) return;
    try {
      const res = await fetch(`${API_BASE}/benefits/${id}`, { method: 'DELETE', headers: getAuthHeaders() });
      if (res.ok) {
        setRefreshKey(k => k + 1);
        toast.success('Benefício cancelado', { duration: 4000 });
      } else {
        const err = await res.json().catch(() => null);
        toast.error(msgFromDetail(err?.detail) || 'Erro ao cancelar beneficio', { duration: 5000 });
      }
    } catch { toast.error('Erro de conexão', { duration: 5000 }); }
  };

  return (
    <div className="space-y-6 pb-28">
      <PageHeader
        icon={<Gift className="h-5 w-5" />}
        title="Gestão de Benefícios"
        subtitle="Benefícios oferecidos aos colaboradores"
        actions={(
          <>
            <Button type="button" variant="ghost" size="sm" onClick={() => router.push('/modulos/dp')}>
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={() => { setFiltroStatus('todos'); setFiltroType('todos'); }}>
              <Filter className="h-4 w-4 mr-1" /> Todos
            </Button>
            <Button type="button" size="sm" className="whitespace-nowrap" onClick={() => { resetForm(); setShowForm(true); }}>
              <Plus className="h-4 w-4 mr-1" /> Novo Benefício
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
            onClick={() => setFiltroStatus(filtroStatus === key ? 'todos' : key)}
          >
            {val.label}
          </Badge>
        ))}
        <span className="border-l mx-2" />
        {typeOptions.slice(0, 5).map(opt => (
          <Badge
            key={opt.value}
            className={`cursor-pointer ${filtroType === opt.value ? 'bg-blue-500 text-white' : 'bg-muted text-muted-foreground'}`}
            onClick={() => setFiltroType(filtroType === opt.value ? 'todos' : opt.value)}
          >
            {opt.label}
          </Badge>
        ))}
      </div>

      {showForm && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>{editingId ? 'Editar Benefício' : 'Novo Benefício'}</CardTitle>
              <Button type="button" variant="ghost" size="sm" onClick={() => { setShowForm(false); resetForm(); }}><X className="h-4 w-4" /></Button>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {!editingId && (
                <div>
                  <label className="text-sm font-medium mb-1 block">Colaborador *</label>
                  <select value={formData.employee_id} onChange={e => { setFormData(p => ({ ...p, employee_id: e.target.value })); setFormErrors(p => ({ ...p, employee_id: '' })); }} className={`w-full px-3 py-2 border rounded-md text-sm ${formErrors.employee_id ? 'border-red-500' : ''}`}>
                    <option value="">Selecione um colaborador</option>
                    {employees.map((emp: any) => <option key={emp.id} value={emp.id}>{emp.nome || emp.name}</option>)}
                  </select>
                  {formErrors.employee_id && <p className="text-red-500 text-xs mt-1">{formErrors.employee_id}</p>}
                </div>
              )}
              <div>
                <label className="text-sm font-medium mb-1 block">Tipo *</label>
                <select value={formData.type} onChange={e => { setFormData(p => ({ ...p, type: e.target.value })); setFormErrors(p => ({ ...p, type: '' })); }} className={`w-full px-3 py-2 border rounded-md text-sm ${formErrors.type ? 'border-red-500' : ''}`}>
                  {typeOptions.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
                {formErrors.type && <p className="text-red-500 text-xs mt-1">{formErrors.type}</p>}
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Operadora/Fornecedor</label>
                <input type="text" value={formData.provider} onChange={e => setFormData(p => ({ ...p, provider: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" placeholder="Ex: Unimed, Sodexo..." />
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Nome do Plano</label>
                <input type="text" value={formData.plan_name} onChange={e => setFormData(p => ({ ...p, plan_name: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" placeholder="Ex: Enfermaria, Premium..." />
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Contrib. Empresa (R$)</label>
                <input type="number" step="0.01" value={formData.company_contribution} onChange={e => setFormData(p => ({ ...p, company_contribution: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" placeholder="0.00" />
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Desc. Funcionario (R$)</label>
                <input type="number" step="0.01" value={formData.employee_contribution} onChange={e => setFormData(p => ({ ...p, employee_contribution: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" placeholder="0.00" />
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Data Início</label>
                <input type="date" value={formData.start_date} onChange={e => setFormData(p => ({ ...p, start_date: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" />
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Data Fim</label>
                <input type="date" value={formData.end_date} onChange={e => setFormData(p => ({ ...p, end_date: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" />
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Numero do Cartao</label>
                <input type="text" value={formData.card_number} onChange={e => setFormData(p => ({ ...p, card_number: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" placeholder="Numero do cartao beneficio" />
              </div>
              <div className="md:col-span-2">
                <label className="text-sm font-medium mb-1 block">Observações</label>
                <textarea value={formData.notes} onChange={e => setFormData(p => ({ ...p, notes: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" rows={2} placeholder="Observações adicionais" />
              </div>
            </div>
            <div className="flex gap-2 mt-4">
              <Button type="button" size="sm" disabled={saving} onClick={handleSave}>
                {saving ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Save className="h-4 w-4 mr-1" />}
                {saving ? 'Salvando...' : editingId ? 'Atualizar Benefício' : 'Criar Benefício'}
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={() => { setShowForm(false); resetForm(); }}>Cancelar</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>
      ) : (
        <>
          {/* Summary cards */}
          {Object.keys(tipoSummary).length > 0 && (
            <div className="grid gap-4 md:grid-cols-3 lg:grid-cols-5">
              {(Object.entries(tipoSummary) as [string, { count: number; total: number }][]).map(([tipo, data]) => (
                <Card key={tipo} className={`cursor-pointer transition-colors ${filtroType === tipo ? 'ring-2 ring-primary' : ''}`} onClick={() => setFiltroType(filtroType === tipo ? 'todos' : tipo)}>
                  <CardContent className="pt-4 pb-4">
                    <span className="text-sm font-medium">{typeLabels[tipo] || tipo}</span>
                    <p className="text-lg font-bold">{data.count} colab.</p>
                    <p className="text-xs text-muted-foreground">{fmt(data.total)}/mes</p>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}

          {/* Employee total cost card */}
          {selectedEmployeeTotal && (
            <Card className="border-blue-200 bg-blue-50/30">
              <CardContent className="pt-4 pb-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <DollarSign className="h-5 w-5 text-blue-600" />
                    <span className="text-sm font-medium">Custo Total de Benefícios do Colaborador</span>
                  </div>
                  <Button variant="ghost" size="sm" onClick={() => { setSelectedEmployeeTotal(null); setEmployeeTotal(null); }}>
                    <X className="h-4 w-4" />
                  </Button>
                </div>
                {totalLoading ? (
                  <div className="flex items-center gap-2 mt-2"><Loader2 className="h-4 w-4 animate-spin" /> <span className="text-sm text-muted-foreground">Calculando...</span></div>
                ) : employeeTotal ? (
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-2 text-sm">
                    <div><span className="text-muted-foreground">Custo empresa:</span><br /><span className="font-bold text-blue-700">{fmt(employeeTotal.total_company ?? employeeTotal.company_total ?? employeeTotal.total_empresa)}</span></div>
                    <div><span className="text-muted-foreground">Desc. funcionario:</span><br /><span className="font-bold">{fmt(employeeTotal.total_employee ?? employeeTotal.employee_total ?? employeeTotal.total_funcionario)}</span></div>
                    <div><span className="text-muted-foreground">Benefícios ativos:</span><br /><span className="font-bold">{employeeTotal.active_count ?? employeeTotal.total_benefits ?? employeeTotal.total_ativos ?? '-'}</span></div>
                    <div><span className="text-muted-foreground">Custo total:</span><br /><span className="font-bold text-green-700">{fmt(employeeTotal.grand_total ?? employeeTotal.total ?? ((employeeTotal.total_company || 0) + (employeeTotal.total_employee || 0)))}</span></div>
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground mt-2">Não foi possível calcular o total</p>
                )}
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Benefícios por Colaborador</CardTitle>
                <div className="relative w-64">
                  <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                  <input
                    type="text"
                    value={searchTerm}
                    onChange={e => setSearchTerm(e.target.value)}
                    placeholder="Buscar por tipo, operadora..."
                    className="w-full pl-9 pr-3 py-2 border rounded-md text-sm"
                  />
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {filteredData.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                  <Inbox className="h-12 w-12 mb-3" />
                  <p className="font-medium">Nenhum beneficio encontrado</p>
                  <p className="text-sm text-muted-foreground mt-1">
                    {searchTerm ? 'Tente outra busca.' : 'Clique em "Novo Benefício" para adicionar.'}
                  </p>
                </div>
              ) : (
                <>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="cursor-pointer select-none" onClick={() => handleSort('employee_name')}>Colaborador{sortIcon('employee_name')}</TableHead>
                        <TableHead className="cursor-pointer select-none" onClick={() => handleSort('type')}>Tipo{sortIcon('type')}</TableHead>
                        <TableHead className="cursor-pointer select-none" onClick={() => handleSort('provider')}>Operadora{sortIcon('provider')}</TableHead>
                        <TableHead>Plano</TableHead>
                        <TableHead>Contrib. Empresa</TableHead>
                        <TableHead>Desc. Funcionario</TableHead>
                        <TableHead className="cursor-pointer select-none" onClick={() => handleSort('start_date')}>Vigencia{sortIcon('start_date')}</TableHead>
                        <TableHead className="cursor-pointer select-none" onClick={() => handleSort('status')}>Status{sortIcon('status')}</TableHead>
                        <TableHead>Ações</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {pagedData.map((item, i) => {
                        const st = statusConfig[String(item.status || '').toLowerCase()] || { label: item.status || 'N/A', className: 'bg-gray-500 text-white' };
                        const startStr = item.start_date ? (() => { const p = String(item.start_date).split('-'); return p.length === 3 ? `${p[2]}/${p[1]}/${p[0]}` : '-'; })() : '-';
                        const endStr = item.end_date ? (() => { const p = String(item.end_date).split('-'); return p.length === 3 ? `${p[2]}/${p[1]}/${p[0]}` : '-'; })() : 'Indeterminado';
                        return (
                          <TableRow key={item.id || i}>
                            <TableCell className="font-medium">{item.employee_name || '-'}</TableCell>
                            <TableCell>{typeLabels[item.type] || item.type || '-'}</TableCell>
                            <TableCell>{item.provider || '-'}</TableCell>
                            <TableCell>{item.plan_name || '-'}</TableCell>
                            <TableCell>{fmt(item.company_contribution)}</TableCell>
                            <TableCell>{fmt(item.employee_contribution)}</TableCell>
                            <TableCell className="text-xs">{startStr} - {endStr}</TableCell>
                            <TableCell><Badge className={st.className}>{st.label}</Badge></TableCell>
                            <TableCell>
                              <div className="flex gap-1">
                                <Button type="button" variant="outline" size="sm" onClick={() => openEditForm(item)}><Edit className="h-3 w-3" /></Button>
                                <Button type="button" variant="ghost" size="sm" onClick={() => item.employee_id && fetchEmployeeTotal(item.employee_id)} title="Ver custo total do colaborador"><DollarSign className="h-3 w-3" /></Button>
                                {item.status === 'active' && (
                                  <Button type="button" variant="outline" size="sm" onClick={() => handleCancel(item.id)}><Trash2 className="h-3 w-3" /></Button>
                                )}
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
                      {totalItems} registro{totalItems !== 1 ? 's' : ''} — Pagina {currentPage} de {totalPages}
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
        </>
      )}
    </div>
  );
}
