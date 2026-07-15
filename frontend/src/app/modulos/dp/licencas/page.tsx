'use client';

import { useState, useEffect, useMemo } from 'react';
import { msgFromDetail } from '@/lib/string';
import { CalendarDays, ArrowLeft, Inbox, Loader2, Plus, X, Save, Search, Filter, ChevronLeft, ChevronRight as ChevronRightIcon } from 'lucide-react';
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

// [Causa-raiz nº1] Vocabulário do BANCO (sst_afastamentos.status): ativo, em_andamento, encerrado.
// Os chips/filtros usam ESSAS chaves (o filtro é client-side: l.status === filtroStatus).
const statusConfig: Record<string, { label: string; className: string }> = {
  ativo: { label: 'Ativo', className: 'bg-blue-500 text-white' },
  em_andamento: { label: 'Em Andamento', className: 'bg-yellow-500 text-white' },
  encerrado: { label: 'Encerrado', className: 'bg-gray-500 text-white' },
  cancelado: { label: 'Cancelado', className: 'bg-red-400 text-white' },
};

// Normaliza status vindo do banco (case-insensitive + sinônimos EN↔PT legados) p/ o bucket de exibição.
const _leaveStatusSynonyms: Record<string, string> = {
  active: 'ativo', ativo: 'ativo', ativa: 'ativo',
  in_progress: 'em_andamento', em_andamento: 'em_andamento', ongoing: 'em_andamento',
  ended: 'encerrado', encerrado: 'encerrado', encerrada: 'encerrado', closed: 'encerrado',
  cancelled: 'cancelado', canceled: 'cancelado', cancelado: 'cancelado', cancelada: 'cancelado',
};
function normLeaveStatus(raw: string | null | undefined): string {
  const k = String(raw || '').trim().toLowerCase();
  return _leaveStatusSynonyms[k] || k || 'ativo';
}

const typeConfig: Record<string, string> = {
  medical_leave: 'Licença Médica',
  medica: 'Licença Médica',
  maternidade: 'Maternidade',
  maternity: 'Maternidade',
  paternidade: 'Paternidade',
  paternity: 'Paternidade',
  acidente: 'Acidente de Trabalho',
  work_accident: 'Acidente de Trabalho',
  obito: 'Nojo (Obito)',
  bereavement: 'Nojo (Obito)',
  casamento: 'Gala (Casamento)',
  marriage: 'Gala (Casamento)',
  jury_duty: 'Serviço do Júri',
  military: 'Serviço Militar',
  other: 'Outro',
};

const leaveTypeOptions = [
  { value: 'medica', label: 'Licença Médica' },
  { value: 'maternidade', label: 'Maternidade' },
  { value: 'paternidade', label: 'Paternidade' },
  { value: 'acidente', label: 'Acidente de Trabalho' },
  { value: 'obito', label: 'Nojo (Obito)' },
  { value: 'casamento', label: 'Gala (Casamento)' },
  { value: 'jury_duty', label: 'Serviço do Júri' },
  { value: 'military', label: 'Serviço Militar' },
  { value: 'other', label: 'Outro' },
];

const PAGE_SIZE = 15;

function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '-';
  const base = String(dateStr).split('T')[0] ?? dateStr;
  const parts = base.split('-');
  return parts.length === 3 ? `${parts[2]}/${parts[1]}/${parts[0]}` : '-';
}

export default function LicencasPage() {
  const router = useRouter();
  const [licencas, setLicencas] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [totalItems, setTotalItems] = useState(0);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [employees, setEmployees] = useState<any[]>([]);
  const [formData, setFormData] = useState({ employee_id: '', leave_type: 'medica', start_date: '', end_date: '', cid: '', notes: '' });
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});
  const [refreshKey, setRefreshKey] = useState(0);
  const [searchTerm, setSearchTerm] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [filtroStatus, setFiltroStatus] = useState<string>('todos');
  const [sortField, setSortField] = useState<string>('');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  // Load leaves from API
  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const res = await fetch(`${API_BASE}/leaves?page=${currentPage}&page_size=${PAGE_SIZE}`, { headers: getAuthHeaders() });
        if (res.ok) {
          const data = await res.json();
          setLicencas(data.items || []);
          setTotalItems(data.total || 0);
        } else {
          setLicencas([]);
          setTotalItems(0);
        }
      } catch {
        setLicencas([]);
        setTotalItems(0);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [currentPage, refreshKey]);

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
  useEffect(() => { setCurrentPage(1); }, [searchTerm, filtroStatus]);

  // Filtered + searched + sorted
  const filteredData = useMemo(() => {
    let items = [...licencas];
    if (filtroStatus !== 'todos') {
      items = items.filter(l => normLeaveStatus(l.status) === filtroStatus);
    }
    if (searchTerm.trim()) {
      const term = searchTerm.toLowerCase();
      items = items.filter(l =>
        (l.type || '').toLowerCase().includes(term) ||
        (l.employee_id || '').toLowerCase().includes(term) ||
        (l.id || '').toLowerCase().includes(term) ||
        (typeConfig[l.type] || '').toLowerCase().includes(term)
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
  }, [licencas, filtroStatus, searchTerm, sortField, sortDir]);

  const totalPages = Math.max(1, Math.ceil(totalItems / PAGE_SIZE));

  // Summary by status
  const statusSummary = useMemo(() => {
    return licencas.reduce((acc, l) => {
      const st = normLeaveStatus(l.status);
      acc[st] = (acc[st] || 0) + 1;
      return acc;
    }, {} as Record<string, number>);
  }, [licencas]);

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

  const handleCreate = async () => {
    const errors: Record<string, string> = {};
    if (!formData.employee_id) errors.employee_id = 'Colaborador é obrigatório';
    if (!formData.start_date) errors.start_date = 'Data inicio e obrigatoria';
    if (Object.keys(errors).length > 0) {
      setFormErrors(errors);
      toast.error('Corrija os campos destacados', { duration: 5000 });
      return;
    }
    setSaving(true);
    try {
      const payload = {
        employee_id: formData.employee_id,
        leave_type: formData.leave_type,
        start_date: formData.start_date,
        end_date: formData.end_date || null,
        cid: formData.cid || null,
        notes: formData.notes || null,
      };
      const res = await fetch(`${API_BASE}/leaves`, { method: 'POST', headers: getAuthHeaders(), body: JSON.stringify(payload) });
      if (res.ok) {
        setShowForm(false);
        setFormData({ employee_id: '', leave_type: 'medica', start_date: '', end_date: '', cid: '', notes: '' });
        setFormErrors({});
        setRefreshKey(k => k + 1);
        toast.success('Licença registrada com sucesso!', { duration: 4000 });
      } else {
        const err = await res.json().catch(() => null);
        toast.error(msgFromDetail(err?.detail) || 'Erro ao registrar licença', { duration: 5000 });
      }
    } catch { toast.error('Erro de conexão', { duration: 5000 }); } finally { setSaving(false); }
  };

  return (
    <div className="space-y-6 pb-28">
      <PageHeader
        icon={<CalendarDays className="h-5 w-5" />}
        title="Licenças e Afastamentos"
        subtitle="Controle de licenças e afastamentos"
        actions={(
          <>
            <Button type="button" variant="ghost" size="sm" onClick={() => router.push('/modulos/dp')}>
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={() => setFiltroStatus('todos')}>
              <Filter className="h-4 w-4 mr-1" /> Todos
            </Button>
            <Button type="button" size="sm" onClick={() => setShowForm(true)}>
              <Plus className="h-4 w-4 mr-1" /> Nova Licença
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
            onClick={() => setFiltroStatus(key)}
          >
            {val.label} {statusSummary[key] ? `(${statusSummary[key]})` : ''}
          </Badge>
        ))}
      </div>

      {showForm && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Nova Licença</CardTitle>
              <Button type="button" variant="ghost" size="sm" onClick={() => setShowForm(false)}><X className="h-4 w-4" /></Button>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="text-sm font-medium mb-1 block">Colaborador *</label>
                <select value={formData.employee_id} onChange={e => { setFormData(p => ({ ...p, employee_id: e.target.value })); setFormErrors(p => ({ ...p, employee_id: '' })); }} className={`w-full px-3 py-2 border rounded-md text-sm ${formErrors.employee_id ? 'border-red-500' : ''}`}>
                  <option value="">Selecione o colaborador</option>
                  {employees.map((emp: any) => (
                    <option key={emp.id} value={emp.id}>{emp.nome || emp.name}</option>
                  ))}
                </select>
                {formErrors.employee_id && <p className="text-red-500 text-xs mt-1">{formErrors.employee_id}</p>}
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Tipo de Licença</label>
                <select value={formData.leave_type} onChange={e => setFormData(p => ({ ...p, leave_type: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm">
                  {leaveTypeOptions.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
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
              {(formData.leave_type === 'medica' || formData.leave_type === 'medical_leave') && (
                <div>
                  <label className="text-sm font-medium mb-1 block">CID</label>
                  <input type="text" value={formData.cid} onChange={e => setFormData(p => ({ ...p, cid: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" placeholder="Ex: J11" />
                </div>
              )}
              <div className="md:col-span-2">
                <label className="text-sm font-medium mb-1 block">Observações</label>
                <textarea value={formData.notes} onChange={e => setFormData(p => ({ ...p, notes: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" rows={3} placeholder="Observações adicionais" />
              </div>
            </div>
            <div className="flex gap-2 mt-4">
              <Button type="button" size="sm" disabled={saving} onClick={handleCreate}>
                {saving ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Save className="h-4 w-4 mr-1" />}
                {saving ? 'Salvando...' : 'Registrar Licença'}
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={() => setShowForm(false)}>Cancelar</Button>
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Licenças Registradas</CardTitle>
            <div className="relative w-64">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <input
                type="text"
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
                placeholder="Buscar por tipo, ID..."
                className="w-full pl-9 pr-3 py-2 border rounded-md text-sm"
              />
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>
          ) : filteredData.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
              <Inbox className="h-12 w-12 mb-3" />
              <p className="font-medium">Nenhuma licença encontrada</p>
              <p className="text-sm text-muted-foreground mt-1">
                {searchTerm ? 'Tente outra busca.' : 'As licenças aparecerão aqui quando registradas.'}
              </p>
            </div>
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="cursor-pointer select-none" onClick={() => handleSort('employee_id')}>Colaborador{sortIcon('employee_id')}</TableHead>
                    <TableHead className="cursor-pointer select-none" onClick={() => handleSort('type')}>Tipo{sortIcon('type')}</TableHead>
                    <TableHead>Inicio</TableHead>
                    <TableHead>Fim</TableHead>
                    <TableHead className="cursor-pointer select-none" onClick={() => handleSort('status')}>Status{sortIcon('status')}</TableHead>
                    <TableHead>ID</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredData.map((item, i) => {
                    const normSt = normLeaveStatus(item.status);
                    const st = statusConfig[normSt] || { label: item.status || 'N/A', className: 'bg-gray-500 text-white' };
                    // Backend (sst_afastamentos) devolve data_inicio/data_fim_prevista; aceita start_date/end_date como fallback.
                    const inicio = item.data_inicio || item.start_date;
                    const fim = item.data_fim_prevista || item.end_date;
                    return (
                      <TableRow key={item.id || i}>
                        <TableCell className="font-medium text-xs">{item.employee_nome || (item.employee_id ? item.employee_id.slice(0, 8) + '...' : '-')}</TableCell>
                        <TableCell>{typeConfig[item.type] || item.type || '-'}</TableCell>
                        <TableCell>{formatDate(inicio)}</TableCell>
                        <TableCell>{formatDate(fim)}</TableCell>
                        <TableCell><Badge className={st.className}>{st.label}</Badge></TableCell>
                        <TableCell className="text-xs text-muted-foreground">{item.id ? item.id.slice(0, 8) + '...' : '-'}</TableCell>
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
    </div>
  );
}
