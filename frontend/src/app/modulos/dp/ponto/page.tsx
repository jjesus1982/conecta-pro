'use client';

import { useState, useEffect, useMemo } from 'react';
import { Clock, ArrowLeft, Inbox, Loader2, AlertTriangle, Search, ChevronLeft, ChevronRight as ChevronRightIcon, Plus, X, Save, LogIn, LogOut } from 'lucide-react';
import { toast } from 'sonner';
import { useRouter } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { StatCard } from '@/components/ui/stat-card';

const API_BASE = '/api/v1/people-management';

function getAuthHeaders() {
  const token = typeof window !== 'undefined' ? (localStorage.getItem('access_token') || localStorage.getItem('token')) : null;
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

const statusConfig: Record<string, { label: string; className: string }> = {
  normal: { label: 'Normal', className: 'bg-green-500 text-white' },
  atraso: { label: 'Atraso', className: 'bg-yellow-500 text-white' },
  falta: { label: 'Falta', className: 'bg-red-500 text-white' },
  hora_extra: { label: 'Hora Extra', className: 'bg-blue-500 text-white' },
  late: { label: 'Atraso', className: 'bg-yellow-500 text-white' },
  absent: { label: 'Falta', className: 'bg-red-500 text-white' },
  overtime: { label: 'Hora Extra', className: 'bg-blue-500 text-white' },
  incomplete: { label: 'Incompleto', className: 'bg-orange-500 text-white' },
  justified: { label: 'Justificado', className: 'bg-cyan-500 text-white' },
  completed: { label: 'Completo', className: 'bg-green-500 text-white' },
};

const PAGE_SIZE = 15;

function formatTime(val: string | null | undefined): string {
  if (!val) return '--:--';
  if (val.includes('T')) {
    const d = new Date(val);
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  }
  return val;
}

function formatDate(val: string | null | undefined): string {
  if (!val) return '-';
  try {
    const parts = val.split('T')[0]?.split('-');
    if (parts && parts.length === 3) return `${parts[2]}/${parts[1]}/${parts[0]}`;
  } catch (err) { console.error('formatDate:', err); }
  return val;
}

export default function PontoPage() {
  const router = useRouter();
  // Data LOCAL (não toISOString, que converte p/ UTC e à noite "vira o dia" antes de Manaus → tela vazia)
  const _now = new Date();
  const today = `${_now.getFullYear()}-${String(_now.getMonth() + 1).padStart(2, '0')}-${String(_now.getDate()).padStart(2, '0')}`;
  const [viewMode, setViewMode] = useState<'daily' | 'monthly'>('daily');
  const [selectedDate, setSelectedDate] = useState(today);
  const [periodo, setPeriodo] = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  });
  const [registros, setRegistros] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [sortField, setSortField] = useState<string>('');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [filtroStatus, setFiltroStatus] = useState<string>('todos');
  const [refreshKey, setRefreshKey] = useState(0);

  // Manual entry form
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [manualEntry, setManualEntry] = useState({ employee_id: '', employee_name: '', date: today, clock_in: '', clock_out: '', observation: '' });

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        let allRecords: any[] = [];

        if (viewMode === 'daily') {
          // Try daily endpoint first
          const dailyRes = await fetch(`${API_BASE}/hr/time-records/daily/${selectedDate}`, { headers: getAuthHeaders() }).catch(() => null);
          if (dailyRes?.ok) {
            const data = await dailyRes.json();
            allRecords = Array.isArray(data) ? data : data.items || data.records || data.registros || [];
          } else {
            // Fallback: fetch all time-records with date filter
            const allRes = await fetch(`${API_BASE}/hr/time-records?date=${selectedDate}&page_size=100`, { headers: getAuthHeaders() }).catch(() => null);
            if (allRes?.ok) {
              const data = await allRes.json();
              allRecords = Array.isArray(data) ? data : data.items || data.records || [];
            }
          }
        } else {
          // Monthly view - fetch all records for the month
          const [year, month] = periodo.split('-');
          const startDate = `${year}-${month}-01`;
          const lastDay = new Date(parseInt(year || '2026'), parseInt(month || '1'), 0).getDate();
          const endDate = `${year}-${month}-${String(lastDay).padStart(2, '0')}`;

          const res = await fetch(`${API_BASE}/hr/time-records?start_date=${startDate}&end_date=${endDate}&page_size=1000`, { headers: getAuthHeaders() }).catch(() => null);
          if (res?.ok) {
            const data = await res.json();
            allRecords = Array.isArray(data) ? data : data.items || data.records || [];
          }
        }

        // Normalize records
        const normalized = allRecords.map((r: any) => ({
          id: r.id,
          employee_id: r.employee_id || r.funcionario_id,
          colaborador: r.employee_name || r.nome || r.colaborador || r.funcionario || 'N/A',
          data: r.date || r.data || r.record_date,
          entrada: r.clock_in || r.entrada || r.check_in || r.time_in,
          saida: r.clock_out || r.saida || r.check_out || r.time_out,
          total: r.total_hours || r.total || r.hours_worked || r.horas_trabalhadas,
          status: r.status || 'normal',
          observation: r.observation || r.observacao || r.notes || '',
        }));

        setRegistros(normalized);
        toast.info(`${normalized.length} registro${normalized.length !== 1 ? 's' : ''} carregado${normalized.length !== 1 ? 's' : ''}`, { duration: 3000 });
      } catch (err) {
        console.error('loadTimeRecords:', err);
        toast.error('Erro ao carregar registros de ponto', { duration: 5000 });
        setRegistros([]);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [viewMode, selectedDate, periodo, refreshKey]);

  useEffect(() => { setCurrentPage(1); }, [searchTerm, filtroStatus]);

  const handleClockIn = async () => {
    try {
      const res = await fetch(`${API_BASE}/hr/time-records/clock-in`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ date: selectedDate }),
      });
      if (res.ok) {
        toast.success('Entrada registrada com sucesso!', { duration: 4000 });
        setRefreshKey(k => k + 1);
      } else {
        const err = await res.json().catch(() => null);
        toast.error(err?.detail || 'Erro ao registrar entrada', { duration: 5000 });
      }
    } catch (err) {
      console.error('handleClockIn:', err);
      toast.error('Erro de conexão', { duration: 5000 });
    }
  };

  const handleClockOut = async (recordId: string) => {
    try {
      const res = await fetch(`${API_BASE}/hr/time-records/clock-out/${recordId}`, {
        method: 'POST',
        headers: getAuthHeaders(),
      });
      if (res.ok) {
        toast.success('Saida registrada com sucesso!', { duration: 4000 });
        setRefreshKey(k => k + 1);
      } else {
        const err = await res.json().catch(() => null);
        toast.error(err?.detail || 'Erro ao registrar saida', { duration: 5000 });
      }
    } catch (err) {
      console.error('handleClockOut:', err);
      toast.error('Erro de conexão', { duration: 5000 });
    }
  };

  const handleManualEntry = async () => {
    if (!manualEntry.employee_id && !manualEntry.employee_name) {
      toast.error('Informe o colaborador', { duration: 5000 });
      return;
    }
    if (!manualEntry.clock_in) {
      toast.error('Informe o horario de entrada', { duration: 5000 });
      return;
    }
    setSaving(true);
    try {
      const res = await fetch(`${API_BASE}/hr/time-records/clock-in`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          employee_id: manualEntry.employee_id || undefined,
          employee_name: manualEntry.employee_name || undefined,
          date: manualEntry.date,
          clock_in: manualEntry.clock_in,
          clock_out: manualEntry.clock_out || undefined,
          observation: manualEntry.observation || undefined,
        }),
      });
      if (res.ok) {
        toast.success('Registro manual criado com sucesso!', { duration: 4000 });
        setShowForm(false);
        setManualEntry({ employee_id: '', employee_name: '', date: today, clock_in: '', clock_out: '', observation: '' });
        setRefreshKey(k => k + 1);
      } else {
        const err = await res.json().catch(() => null);
        toast.error(err?.detail || 'Erro ao criar registro manual', { duration: 5000 });
      }
    } catch (err) {
      console.error('handleManualEntry:', err);
      toast.error('Erro de conexão', { duration: 5000 });
    } finally {
      setSaving(false);
    }
  };

  // Filtered + searched + sorted
  const filteredData = useMemo(() => {
    let items = [...registros];
    if (filtroStatus !== 'todos') {
      items = items.filter(r => r.status === filtroStatus);
    }
    if (searchTerm.trim()) {
      const term = searchTerm.toLowerCase();
      items = items.filter(r =>
        (r.colaborador || '').toLowerCase().includes(term) ||
        (r.observation || '').toLowerCase().includes(term)
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
  }, [registros, filtroStatus, searchTerm, sortField, sortDir]);

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

  // Summary stats
  const totalRegistros = registros.length;
  const horasExtras = registros.filter(r => r.status === 'hora_extra' || r.status === 'overtime').length;
  const faltas = registros.filter(r => r.status === 'falta' || r.status === 'absent').length;
  const atrasos = registros.filter(r => r.status === 'atraso' || r.status === 'late').length;

  const summaryCards = [
    { title: 'Total Registros', value: `${totalRegistros}`, icon: Clock, color: '#2563eb' },
    { title: 'Horas Extras', value: `${horasExtras}`, icon: Clock, color: '#16a34a' },
    { title: 'Faltas', value: `${faltas}`, icon: AlertTriangle, color: '#dc2626' },
    { title: 'Atrasos', value: `${atrasos}`, icon: AlertTriangle, color: '#ca8a04' },
  ];

  return (
    <div className="space-y-6 pb-28">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button type="button" variant="ghost" size="sm" onClick={() => router.push('/modulos/dp')}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <h1 className="font-display text-2xl font-semibold flex items-center gap-2">
              <Clock className="h-6 w-6" />
              Ponto Eletrônico
            </h1>
            <p className="text-muted-foreground">Registro e controle de ponto dos colaboradores</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex rounded-md border">
            <Button
              type="button"
              variant={viewMode === 'daily' ? 'default' : 'ghost'}
              size="sm"
              className="rounded-r-none"
              onClick={() => setViewMode('daily')}
            >
              Diário
            </Button>
            <Button
              type="button"
              variant={viewMode === 'monthly' ? 'default' : 'ghost'}
              size="sm"
              className="rounded-l-none"
              onClick={() => setViewMode('monthly')}
            >
              Mensal
            </Button>
          </div>
          {viewMode === 'daily' ? (
            <input
              type="date"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              className="rounded-md border px-3 py-2 text-sm bg-background"
            />
          ) : (
            <input
              type="month"
              value={periodo}
              onChange={(e) => setPeriodo(e.target.value)}
              className="rounded-md border px-3 py-2 text-sm bg-background"
            />
          )}
          <Button type="button" size="sm" onClick={() => setShowForm(true)}>
            <Plus className="h-4 w-4 mr-1" /> Registro Manual
          </Button>
        </div>
      </div>

      {/* Status filter badges */}
      <div className="flex gap-2 flex-wrap">
        <Badge
          className={`cursor-pointer ${filtroStatus === 'todos' ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'}`}
          onClick={() => setFiltroStatus('todos')}
        >
          Todos
        </Badge>
        {Object.entries(statusConfig).filter(([k]) => ['normal', 'atraso', 'falta', 'hora_extra', 'incomplete'].includes(k)).map(([key, val]) => (
          <Badge
            key={key}
            className={`cursor-pointer ${filtroStatus === key ? val.className : 'bg-muted text-muted-foreground'}`}
            onClick={() => setFiltroStatus(key)}
          >
            {val.label}
          </Badge>
        ))}
      </div>

      {/* Manual Entry Form */}
      {showForm && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Registro Manual de Ponto</CardTitle>
              <Button type="button" variant="ghost" size="sm" onClick={() => setShowForm(false)}><X className="h-4 w-4" /></Button>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="text-sm font-medium mb-1 block">Colaborador *</label>
                <input
                  type="text"
                  value={manualEntry.employee_name}
                  onChange={e => setManualEntry(p => ({ ...p, employee_name: e.target.value }))}
                  className="w-full px-3 py-2 border rounded-md text-sm"
                  placeholder="Nome do colaborador"
                />
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Data *</label>
                <input
                  type="date"
                  value={manualEntry.date}
                  onChange={e => setManualEntry(p => ({ ...p, date: e.target.value }))}
                  className="w-full px-3 py-2 border rounded-md text-sm"
                />
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Entrada *</label>
                <input
                  type="time"
                  value={manualEntry.clock_in}
                  onChange={e => setManualEntry(p => ({ ...p, clock_in: e.target.value }))}
                  className="w-full px-3 py-2 border rounded-md text-sm"
                />
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Saida</label>
                <input
                  type="time"
                  value={manualEntry.clock_out}
                  onChange={e => setManualEntry(p => ({ ...p, clock_out: e.target.value }))}
                  className="w-full px-3 py-2 border rounded-md text-sm"
                />
              </div>
              <div className="md:col-span-2">
                <label className="text-sm font-medium mb-1 block">Observacao</label>
                <input
                  type="text"
                  value={manualEntry.observation}
                  onChange={e => setManualEntry(p => ({ ...p, observation: e.target.value }))}
                  className="w-full px-3 py-2 border rounded-md text-sm"
                  placeholder="Justificativa ou observacao"
                />
              </div>
            </div>
            <div className="flex gap-2 mt-4">
              <Button type="button" size="sm" disabled={saving} onClick={handleManualEntry}>
                {saving ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Save className="h-4 w-4 mr-1" />}
                {saving ? 'Salvando...' : 'Salvar Registro'}
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={() => setShowForm(false)}>Cancelar</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>
      ) : (
        <>
          {/* Summary Cards */}
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            {summaryCards.map((card) => (
              <StatCard
                key={card.title}
                icon={<card.icon className="h-4 w-4" />}
                label={card.title}
                value={card.value}
                color={card.color}
              />
            ))}
          </div>

          {/* Records Table */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Registros de Ponto {viewMode === 'daily' ? `- ${formatDate(selectedDate)}` : ''}</CardTitle>
                <div className="flex items-center gap-2">
                  <div className="relative w-64">
                    <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                    <input
                      type="text"
                      value={searchTerm}
                      onChange={e => setSearchTerm(e.target.value)}
                      placeholder="Buscar por colaborador..."
                      className="w-full pl-9 pr-3 py-2 border rounded-md text-sm"
                    />
                  </div>
                  {viewMode === 'daily' && (
                    <Button type="button" size="sm" variant="outline" onClick={handleClockIn}>
                      <LogIn className="h-4 w-4 mr-1" /> Registrar Entrada
                    </Button>
                  )}
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {filteredData.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                  <Inbox className="h-12 w-12 mb-3" />
                  <p className="font-medium">Nenhum registro de ponto encontrado</p>
                  <p className="text-sm text-muted-foreground mt-1">
                    {searchTerm ? 'Tente outra busca.' : 'Os registros aparecerão conforme os colaboradores registram ponto.'}
                  </p>
                </div>
              ) : (
                <>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="cursor-pointer select-none" onClick={() => handleSort('colaborador')}>Colaborador{sortIcon('colaborador')}</TableHead>
                        <TableHead className="cursor-pointer select-none" onClick={() => handleSort('data')}>Data{sortIcon('data')}</TableHead>
                        <TableHead>Entrada</TableHead>
                        <TableHead>Saida</TableHead>
                        <TableHead>Total Horas</TableHead>
                        <TableHead className="cursor-pointer select-none" onClick={() => handleSort('status')}>Status{sortIcon('status')}</TableHead>
                        <TableHead>Ações</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {paginatedData.map((item, i) => {
                        const st = statusConfig[item.status] || { label: item.status || 'N/A', className: 'bg-gray-500 text-white' };
                        const hasNoClockOut = !item.saida;
                        return (
                          <TableRow key={item.id || i}>
                            <TableCell className="font-medium">{item.colaborador}</TableCell>
                            <TableCell>{formatDate(item.data)}</TableCell>
                            <TableCell>{formatTime(item.entrada)}</TableCell>
                            <TableCell>{formatTime(item.saida)}</TableCell>
                            <TableCell>{item.total || '--:--'}</TableCell>
                            <TableCell><Badge className={st.className}>{st.label}</Badge></TableCell>
                            <TableCell>
                              {hasNoClockOut && item.id ? (
                                <Button type="button" variant="outline" size="sm" onClick={() => handleClockOut(item.id)}>
                                  <LogOut className="h-3 w-3 mr-1" /> Saida
                                </Button>
                              ) : (
                                <span className="text-xs text-muted-foreground">-</span>
                              )}
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
        </>
      )}
    </div>
  );
}
