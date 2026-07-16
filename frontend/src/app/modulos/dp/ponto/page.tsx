'use client';

import { useState, useEffect, useMemo, Suspense } from 'react';
import { msgFromDetail } from '@/lib/string';
import { Clock, ArrowLeft, Inbox, Loader2, AlertTriangle, Search, ChevronLeft, ChevronRight as ChevronRightIcon, Plus, X, Save, LogIn, LogOut } from 'lucide-react';
import { toast } from 'sonner';
import { useRouter, useSearchParams } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { StatCard } from '@/components/ui/stat-card';
import { EmployeeSelect } from '@/components/sst/EmployeeSelect';

const API_BASE = '/api/v1/people-management';

function getAuthHeaders() {
  const token = typeof window !== 'undefined' ? (localStorage.getItem('access_token') || localStorage.getItem('token')) : null;
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

const statusConfig: Record<string, { label: string; className: string }> = {
  normal: { label: 'Normal', className: 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/30' },
  atraso: { label: 'Atraso', className: 'bg-amber-500/10 text-amber-500 border border-amber-500/30' },
  falta: { label: 'Falta', className: 'bg-red-500/10 text-red-500 border border-red-500/30' },
  hora_extra: { label: 'Hora Extra', className: 'bg-blue-500/10 text-blue-500 border border-blue-500/30' },
  late: { label: 'Atraso', className: 'bg-amber-500/10 text-amber-500 border border-amber-500/30' },
  absent: { label: 'Falta', className: 'bg-red-500/10 text-red-500 border border-red-500/30' },
  overtime: { label: 'Hora Extra', className: 'bg-blue-500/10 text-blue-500 border border-blue-500/30' },
  incomplete: { label: 'Incompleto', className: 'bg-orange-500/10 text-orange-500 border border-orange-500/30' },
  justified: { label: 'Justificado', className: 'bg-cyan-500/10 text-cyan-500 border border-cyan-500/30' },
  completed: { label: 'Completo', className: 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/30' },
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

function PontoPageInner() {
  const router = useRouter();
  // Deep-link do Fechamento de Ponto ("corrigir" numa anomalia): abre já no MÊS certo,
  // em visão MENSAL e filtrado no funcionário. useSearchParams (NÃO window.location.search):
  // no client-side router.push a URL só é commitada depois do render, então window.location
  // ainda mostrava a rota antiga e a tela caía em hoje/diário.
  const searchParams = useSearchParams();
  // Data LOCAL (não toISOString, que converte p/ UTC e à noite "vira o dia" antes de Manaus → tela vazia)
  const _now = new Date();
  const today = `${_now.getFullYear()}-${String(_now.getMonth() + 1).padStart(2, '0')}-${String(_now.getDate()).padStart(2, '0')}`;
  const _qpMes = searchParams.get('mes');
  const _qpAno = searchParams.get('ano');
  const _qpNome = searchParams.get('nome') || '';
  const _temPeriodoURL = Boolean(_qpMes && _qpAno);
  const _periodoURL = _temPeriodoURL
    ? `${_qpAno}-${String(Number(_qpMes)).padStart(2, '0')}`
    : `${_now.getFullYear()}-${String(_now.getMonth() + 1).padStart(2, '0')}`;
  const [viewMode, setViewMode] = useState<'daily' | 'monthly'>(_temPeriodoURL ? 'monthly' : 'daily');
  const [selectedDate, setSelectedDate] = useState(today);
  const [periodo, setPeriodo] = useState(_periodoURL);
  // Reage se os params mudarem depois do mount (nav de "corrigir" repetida na mesma página)
  useEffect(() => {
    if (_temPeriodoURL) {
      setViewMode('monthly');
      setPeriodo(_periodoURL);
      if (_qpNome) setSearchTerm(_qpNome);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [_periodoURL, _qpNome, _temPeriodoURL]);
  const [registros, setRegistros] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState(_qpNome);
  const [currentPage, setCurrentPage] = useState(1);
  const [sortField, setSortField] = useState<string>('');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [filtroStatus, setFiltroStatus] = useState<string>('todos');
  const [refreshKey, setRefreshKey] = useState(0);
  // Resumo mensal REAL (agregado do espelho/time_sheets), não a contagem por status das
  // linhas cruas — que ficava zerada porque time-records não carrega status 'falta'/'extra'.
  const [monthlyResumo, setMonthlyResumo] = useState<{ extras_min: number; faltas: number; atrasos_min: number } | null>(null);

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
            // Fallback: fetch all time-records with date filter (param correto: date_from/date_to)
            const allRes = await fetch(`${API_BASE}/hr/time-records?date_from=${selectedDate}&date_to=${selectedDate}&page_size=100`, { headers: getAuthHeaders() }).catch(() => null);
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

          // [Causa-raiz nº1] o endpoint usa date_from/date_to (não start_date/end_date) e limita
          // page_size a 100 (page_size>100 → 422). Paginamos até 100/página para a visão mensal.
          let pg = 1;
          const MAX_PAGES = 30; // teto de segurança (30*100 = 3000 registros/mês)
          while (pg <= MAX_PAGES) {
            const res = await fetch(`${API_BASE}/hr/time-records?date_from=${startDate}&date_to=${endDate}&page=${pg}&page_size=100`, { headers: getAuthHeaders() }).catch(() => null);
            if (!res?.ok) break;
            const data = await res.json();
            const batch = Array.isArray(data) ? data : data.items || data.records || [];
            allRecords = allRecords.concat(batch);
            const totalPages = (!Array.isArray(data) && data.total_pages) ? data.total_pages : (batch.length < 100 ? pg : pg + 1);
            if (batch.length < 100 || pg >= totalPages) break;
            pg += 1;
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
          // origem da linha: 'tangerino' (agregado Solides), 'manual' ou 'portal' (batida nativa).
          // O clock-out so opera sobre batida nativa; linha Solides tem id sintetico.
          source: r.source || r.registered_by || null,
        }));

        setRegistros(normalized);
        toast.info(`${normalized.length} registro${normalized.length !== 1 ? 's' : ''} carregado${normalized.length !== 1 ? 's' : ''}`, { duration: 3000 });

        // Cards do mês: agregado REAL do espelho (extras/faltas/atrasos), não a contagem
        // por status das linhas (que ficava zerada). Best-effort — falha não quebra a lista.
        if (viewMode === 'monthly') {
          try {
            const [y, m] = periodo.split('-');
            const pr = await fetch(`${API_BASE}/hr/ponto/espelho/painel/${Number(m)}/${y}`, { headers: getAuthHeaders() }).catch(() => null);
            if (pr?.ok) {
              const pd = await pr.json();
              const funcs: any[] = pd.funcionarios || pd.itens || [];
              setMonthlyResumo({
                extras_min: funcs.reduce((s, f) => s + (Number(f.extras_minutos) || 0), 0),
                faltas: funcs.reduce((s, f) => s + (Number(f.faltas_dias) || 0), 0),
                atrasos_min: funcs.reduce((s, f) => s + (Number(f.atrasos_minutos) || 0), 0),
              });
            } else {
              setMonthlyResumo(null);
            }
          } catch { setMonthlyResumo(null); }
        } else {
          setMonthlyResumo(null);
        }
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

  // "Registrar Entrada" nao pode disparar clock-in sem funcionario (ClockInRequest exige
  // employee_id + coords -> 422 garantido). Abre o formulario manual ja com a data selecionada,
  // onde o operador escolhe o colaborador. Sem botao que so da 422.
  const handleOpenClockIn = () => {
    setManualEntry(p => ({ ...p, date: selectedDate }));
    setShowForm(true);
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
        toast.error(msgFromDetail(err?.detail) || 'Erro ao registrar saida', { duration: 5000 });
      }
    } catch (err) {
      console.error('handleClockOut:', err);
      toast.error('Erro de conexão', { duration: 5000 });
    }
  };

  const handleManualEntry = async () => {
    // O registro manual EXIGE o UUID do funcionario — o backend grava por employee_id,
    // nao por nome. Sem o UUID nao ha como lancar a batida no funcionario correto.
    if (!manualEntry.employee_id) {
      toast.error('Selecione o colaborador (UUID) — o nome sozinho nao identifica o funcionario', { duration: 6000 });
      return;
    }
    if (!manualEntry.date) {
      toast.error('Informe a data', { duration: 5000 });
      return;
    }
    if (!manualEntry.clock_in) {
      toast.error('Informe o horario de entrada', { duration: 5000 });
      return;
    }
    setSaving(true);
    try {
      // CORRECAO CRITICA: usar o endpoint de LANCAMENTO MANUAL (POST "") que grava a
      // data/hora INFORMADA pelo operador e marca a batida como device_type='manual'.
      // Antes chamava /clock-in, que IGNORA a data/hora e carimba NOW() (adulteracao de jornada).
      // Enviamos record_date + clock_in/clock_out como datetime NAIVE em horario LOCAL
      // (America/Manaus) — o banco guarda wall-clock local, sem conversao UTC.
      const toLocalDateTime = (dateStr: string, timeStr: string): string => {
        // timeStr = "HH:MM" -> "YYYY-MM-DDTHH:MM:00" (sem timezone, hora local exata digitada)
        const hhmm = timeStr.length === 5 ? `${timeStr}:00` : timeStr;
        return `${dateStr}T${hhmm}`;
      };
      const payload: Record<string, unknown> = {
        employee_id: manualEntry.employee_id,
        record_date: manualEntry.date,
        clock_in: toLocalDateTime(manualEntry.date, manualEntry.clock_in),
        registered_by: 'manual',
        status: 'regular',
      };
      if (manualEntry.clock_out) {
        payload.clock_out = toLocalDateTime(manualEntry.date, manualEntry.clock_out);
      }
      if (manualEntry.observation) {
        payload.justification = manualEntry.observation;
      }
      const res = await fetch(`${API_BASE}/hr/time-records`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        toast.success('Registro manual criado com a data/hora informada!', { duration: 4000 });
        setShowForm(false);
        setManualEntry({ employee_id: '', employee_name: '', date: today, clock_in: '', clock_out: '', observation: '' });
        setRefreshKey(k => k + 1);
      } else {
        const err = await res.json().catch(() => null);
        toast.error(msgFromDetail(err?.detail) || 'Erro ao criar registro manual', { duration: 5000 });
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

  const _hm = (min: number) => `${Math.floor(min / 60)}h${String(min % 60).padStart(2, '0')}`;
  // No mês, os cards refletem o agregado REAL do espelho; no dia, a contagem por status.
  const summaryCards = viewMode === 'monthly' && monthlyResumo
    ? [
        { title: 'Total Registros', value: `${totalRegistros}`, icon: Clock, color: '#2563eb' },
        { title: 'Horas Extras', value: _hm(monthlyResumo.extras_min), icon: Clock, color: '#16a34a' },
        { title: 'Faltas', value: `${monthlyResumo.faltas}`, icon: AlertTriangle, color: '#dc2626' },
        { title: 'Atrasos', value: _hm(monthlyResumo.atrasos_min), icon: AlertTriangle, color: '#ca8a04' },
      ]
    : [
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
                <EmployeeSelect
                  value={manualEntry.employee_id}
                  onChange={(id, emp) => setManualEntry(p => ({ ...p, employee_id: id, employee_name: emp?.nome || '' }))}
                  placeholder="Selecione o colaborador..."
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
                    <Button type="button" size="sm" variant="outline" onClick={handleOpenClockIn}>
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
                        const st = statusConfig[item.status] || { label: item.status || 'N/A', className: 'bg-[hsl(var(--secondary))] text-[hsl(var(--muted-foreground))]' };
                        // Linha agregada do Solides (tangerino) tem id sintetico (tang-...-saida) que
                        // NAO referencia batida nativa: clock-out nela criaria uma saida duplicada/orfa.
                        // So oferecemos "Saida" em batida NATIVA (portal/manual) sem saida registrada.
                        const isAggregate = item.source === 'tangerino';
                        const hasNoClockOut = !item.saida && !isAggregate;
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
                              ) : isAggregate && !item.saida ? (
                                <span className="text-xs text-muted-foreground" title="Batida importada do Sólides — ajuste pela origem">Sólides</span>
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

// useSearchParams exige Suspense boundary no App Router (senão o build falha em página estática)
export default function PontoPage() {
  return (
    <Suspense fallback={null}>
      <PontoPageInner />
    </Suspense>
  );
}
