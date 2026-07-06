'use client';

import { useState, useMemo, useEffect } from 'react';
import { Receipt, ArrowLeft, Inbox, Plus, X, Save, Search, Filter, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { useRouter } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { PageHeader } from '@/components/ui/page-header';

const API_HR = '/api/v1/people-management/hr';
const API_REIMB = '/api/v1/reimbursements/';

function getAuthHeaders() {
  const token = typeof window !== 'undefined' ? (localStorage.getItem('access_token') || localStorage.getItem('token')) : null;
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

const statusConfig: Record<string, { label: string; className: string }> = {
  rascunho:  { label: 'Rascunho',  className: 'bg-gray-500 text-white' },
  submetido: { label: 'Submetido', className: 'bg-yellow-500 text-white' },
  aprovado:  { label: 'Aprovado',  className: 'bg-green-500 text-white' },
  rejeitado: { label: 'Rejeitado', className: 'bg-red-500 text-white' },
  pago:      { label: 'Pago',      className: 'bg-blue-500 text-white' },
  cancelado: { label: 'Cancelado', className: 'bg-red-400 text-white' },
  pending:   { label: 'Pendente',  className: 'bg-yellow-500 text-white' },
  approved:  { label: 'Aprovado',  className: 'bg-green-500 text-white' },
  rejected:  { label: 'Rejeitado', className: 'bg-red-500 text-white' },
};

const categoryOptions = [
  { value: 'transporte',    label: 'Transporte' },
  { value: 'alimentacao',   label: 'Alimentação' },
  { value: 'hospedagem',    label: 'Hospedagem' },
  { value: 'material',      label: 'Material de Trabalho' },
  { value: 'comunicacao',   label: 'Comunicação' },
  { value: 'estacionamento',label: 'Estacionamento' },
  { value: 'pedagio',       label: 'Pedágio' },
  { value: 'saude',         label: 'Saúde' },
  { value: 'cursos',        label: 'Cursos/Treinamentos' },
  { value: 'outros',        label: 'Outros' },
];

const fmt = (v: number | string | null | undefined) =>
  `R$ ${(Number(v) || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`;

function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '-';
  const base = String(dateStr).split('T')[0] ?? dateStr;
  const parts = base.split('-');
  return parts.length === 3 ? `${parts[2]}/${parts[1]}/${parts[0]}` : '-';
}

export default function ReembolsosPage() {
  const router = useRouter();
  const [reembolsos, setReembolsos] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [employees, setEmployees] = useState<any[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [filtroStatus, setFiltroStatus] = useState('todos');
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [formData, setFormData] = useState({
    employee_id: '',
    category: 'transporte',
    description: '',
    amount: '',
    date: new Date().toISOString().split('T')[0] ?? '',
  });
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});

  // Carregar reembolsos
  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const res = await fetch(`${API_REIMB}?page_size=100`, { headers: getAuthHeaders() });
        if (res.ok) {
          const data = await res.json();
          setReembolsos(data.items || []);
        } else {
          setReembolsos([]);
        }
      } catch { setReembolsos([]); } finally { setLoading(false); }
    }
    load();
  }, [refreshKey]);

  // Carregar funcionários
  useEffect(() => {
    async function loadEmployees() {
      try {
        const res = await fetch(`${API_HR}/employees?page_size=100`, { headers: getAuthHeaders() });
        if (res.ok) {
          const data = await res.json();
          setEmployees(data.items || data || []);
        }
      } catch { /* skip */ }
    }
    loadEmployees();
  }, []);

  const filteredData = useMemo(() => {
    let items = [...reembolsos];
    if (filtroStatus !== 'todos') items = items.filter(r => r.status === filtroStatus);
    if (searchTerm.trim()) {
      const term = searchTerm.toLowerCase();
      items = items.filter(r =>
        (r.title || '').toLowerCase().includes(term) ||
        (r.code || '').toLowerCase().includes(term) ||
        (r.status || '').toLowerCase().includes(term)
      );
    }
    return items;
  }, [reembolsos, filtroStatus, searchTerm]);

  const handleCreate = async () => {
    const errors: Record<string, string> = {};
    if (!formData.employee_id) errors.employee_id = 'Colaborador é obrigatório';
    if (!formData.description.trim()) errors.description = 'Descrição é obrigatória';
    if (!formData.amount || Number(formData.amount) <= 0) errors.amount = 'Valor deve ser maior que zero';
    if (!formData.date) errors.date = 'Data é obrigatória';
    if (Object.keys(errors).length > 0) {
      setFormErrors(errors);
      toast.error('Corrija os campos destacados', { duration: 4000 });
      return;
    }

    const employee = employees.find(e => e.id === formData.employee_id);
    const employeeName = employee ? (employee.nome || employee.name || 'Colaborador') : 'Colaborador';
    const categoryLabel = categoryOptions.find(c => c.value === formData.category)?.label || formData.category;

    setSaving(true);
    try {
      const payload = {
        title: `Reembolso ${categoryLabel} — ${employeeName}`,
        description: formData.description,
        expense_date_start: formData.date,
        expense_date_end: formData.date,
        notes: `Solicitado para colaborador: ${employeeName} (ID: ${formData.employee_id})`,
        items: [{
          category_type: formData.category,
          description: formData.description,
          expense_date: formData.date,
          amount: Number(formData.amount),
        }],
      };

      const res = await fetch(API_REIMB, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        const created = await res.json();
        setShowForm(false);
        setFormData({ employee_id: '', category: 'transporte', description: '', amount: '', date: new Date().toISOString().split('T')[0] ?? '' });
        setFormErrors({});
        setRefreshKey(k => k + 1);
        toast.success(`Reembolso ${created.code} criado com sucesso!`, { duration: 4000 });
      } else {
        const err = await res.json().catch(() => null);
        toast.error(err?.detail || 'Erro ao criar reembolso', { duration: 5000 });
      }
    } catch { toast.error('Erro de conexão', { duration: 5000 }); } finally { setSaving(false); }
  };

  return (
    <div className="space-y-6 pb-28">
      <PageHeader
        icon={<Receipt className="h-5 w-5" />}
        title="Reembolsos"
        subtitle="Gerencie solicitações de reembolso dos colaboradores"
        actions={(
          <>
            <Button type="button" variant="ghost" size="sm" onClick={() => router.push('/modulos/dp')}>
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={() => setFiltroStatus('todos')}>
              <Filter className="h-4 w-4 mr-1" /> Todos
            </Button>
            <Button type="button" size="sm" onClick={() => setShowForm(true)}>
              <Plus className="h-4 w-4 mr-1" /> Novo Reembolso
            </Button>
          </>
        )}
      />

      <div className="flex gap-2 flex-wrap">
        {Object.entries(statusConfig).filter(([k]) => !['pending','approved','rejected'].includes(k)).map(([key, val]) => (
          <Badge
            key={key}
            className={`cursor-pointer ${filtroStatus === key ? val.className : 'bg-muted text-muted-foreground'}`}
            onClick={() => setFiltroStatus(filtroStatus === key ? 'todos' : key)}
          >
            {val.label}
          </Badge>
        ))}
      </div>

      {showForm && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Novo Reembolso</CardTitle>
              <Button type="button" variant="ghost" size="sm" onClick={() => setShowForm(false)}>
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
                  <option value="">Selecione o colaborador</option>
                  {employees.map((emp: any) => (
                    <option key={emp.id} value={emp.id}>{emp.nome || emp.name}</option>
                  ))}
                </select>
                {formErrors.employee_id && <p className="text-red-500 text-xs mt-1">{formErrors.employee_id}</p>}
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Categoria</label>
                <select
                  value={formData.category}
                  onChange={e => setFormData(p => ({ ...p, category: e.target.value }))}
                  className="w-full px-3 py-2 border rounded-md text-sm"
                >
                  {categoryOptions.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Valor (R$) *</label>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={formData.amount}
                  onChange={e => { setFormData(p => ({ ...p, amount: e.target.value })); setFormErrors(p => ({ ...p, amount: '' })); }}
                  className={`w-full px-3 py-2 border rounded-md text-sm ${formErrors.amount ? 'border-red-500' : ''}`}
                  placeholder="0,00"
                />
                {formErrors.amount && <p className="text-red-500 text-xs mt-1">{formErrors.amount}</p>}
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Data *</label>
                <input
                  type="date"
                  value={formData.date}
                  onChange={e => { setFormData(p => ({ ...p, date: e.target.value })); setFormErrors(p => ({ ...p, date: '' })); }}
                  className={`w-full px-3 py-2 border rounded-md text-sm ${formErrors.date ? 'border-red-500' : ''}`}
                />
                {formErrors.date && <p className="text-red-500 text-xs mt-1">{formErrors.date}</p>}
              </div>
              <div className="md:col-span-2">
                <label className="text-sm font-medium mb-1 block">Descrição *</label>
                <textarea
                  value={formData.description}
                  onChange={e => { setFormData(p => ({ ...p, description: e.target.value })); setFormErrors(p => ({ ...p, description: '' })); }}
                  className={`w-full px-3 py-2 border rounded-md text-sm ${formErrors.description ? 'border-red-500' : ''}`}
                  rows={2}
                  placeholder="Descreva a despesa (mínimo 3 caracteres)..."
                />
                {formErrors.description && <p className="text-red-500 text-xs mt-1">{formErrors.description}</p>}
              </div>
            </div>
            <div className="flex gap-2 mt-4">
              <Button type="button" size="sm" disabled={saving} onClick={handleCreate}>
                {saving ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Save className="h-4 w-4 mr-1" />}
                {saving ? 'Enviando...' : 'Solicitar Reembolso'}
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={() => setShowForm(false)}>Cancelar</Button>
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Solicitações de Reembolso</CardTitle>
            <div className="relative w-64">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <input
                type="text"
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
                placeholder="Buscar por título, código..."
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
              <p className="font-medium">Nenhum reembolso encontrado</p>
              <p className="text-sm mt-1">
                {searchTerm ? 'Tente outra busca.' : 'As solicitações aparecerão aqui quando registradas.'}
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Código</TableHead>
                  <TableHead>Título</TableHead>
                  <TableHead>Valor</TableHead>
                  <TableHead>Data</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredData.map((r: any) => {
                  const st = statusConfig[r.status] || { label: r.status || '-', className: 'bg-gray-500 text-white' };
                  return (
                    <TableRow key={r.id}>
                      <TableCell className="font-mono text-xs">{r.code || '-'}</TableCell>
                      <TableCell className="max-w-xs truncate">{r.title || '-'}</TableCell>
                      <TableCell>{fmt(r.total_amount)}</TableCell>
                      <TableCell>{formatDate(r.expense_date_start)}</TableCell>
                      <TableCell><Badge className={st.className}>{st.label}</Badge></TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
