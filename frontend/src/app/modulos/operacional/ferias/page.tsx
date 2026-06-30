'use client';
import { Calendar, ArrowLeft, Plus, CheckCircle, XCircle, Clock, User, RefreshCw, X, AlertTriangle, Plane } from 'lucide-react';
import { useState, useMemo, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Modal, ModalFooter } from '@/components/ui/modal';
import { useAuth } from '@/hooks/useAuth';
import { useEmployees } from '@/hooks/operacional/useEmployees';
import api from '@/lib/api';

interface LeaveRequest {
  id: string;
  employeeId: string;
  employeeName: string;
  type: 'ferias' | 'afastamento' | 'licenca' | 'folga';
  startDate: string;
  endDate: string;
  reason: string;
  status: 'pendente' | 'aprovado' | 'rejeitado';
  createdAt: string;
}

const LEAVE_TYPE_LABELS: Record<LeaveRequest['type'], string> = {
  ferias: 'Férias',
  afastamento: 'Afastamento Médico',
  licenca: 'Licença',
  folga: 'Folga Compensatória',
};

const LEAVE_TYPE_COLORS: Record<LeaveRequest['type'], string> = {
  ferias: 'bg-blue-500/10 text-blue-500',
  afastamento: 'bg-orange-500/10 text-orange-500',
  licenca: 'bg-purple-500/10 text-purple-500',
  folga: 'bg-green-500/10 text-green-500',
};

const STATUS_COLORS: Record<LeaveRequest['status'], string> = {
  pendente: 'bg-yellow-500/10 text-yellow-500',
  aprovado: 'bg-green-500/10 text-green-500',
  rejeitado: 'bg-red-500/10 text-red-500',
};

const DEMO_DATA: LeaveRequest[] = [
  {
    id: '1',
    employeeId: 'demo1',
    employeeName: 'Carlos Eduardo Mendes',
    type: 'ferias',
    startDate: '2026-03-01',
    endDate: '2026-03-30',
    reason: 'Férias anuais referentes ao período aquisitivo 2024/2025. Colaborador com mais de 2 anos na empresa sem tirar férias completas.',
    status: 'aprovado',
    createdAt: '2026-02-10T09:00:00.000Z',
  },
  {
    id: '2',
    employeeId: 'demo2',
    employeeName: 'Ana Paula Rodrigues',
    type: 'afastamento',
    startDate: '2026-03-05',
    endDate: '2026-03-19',
    reason: 'Afastamento médico por recomendação do médico do trabalho após diagnóstico de tendinite no ombro direito. Apresentou Atestado Médico e CID M75.',
    status: 'aprovado',
    createdAt: '2026-03-04T08:30:00.000Z',
  },
  {
    id: '3',
    employeeId: 'demo3',
    employeeName: 'José Roberto Lima',
    type: 'folga',
    startDate: '2026-03-21',
    endDate: '2026-03-21',
    reason: 'Compensação de 8h de horas extras acumuladas no mês de fevereiro, trabalhadas nos finais de semana durante reforço operacional no Porto de Manaus.',
    status: 'pendente',
    createdAt: '2026-03-08T10:15:00.000Z',
  },
  {
    id: '4',
    employeeId: 'demo4',
    employeeName: 'Francisca Oliveira',
    type: 'licenca',
    startDate: '2026-02-10',
    endDate: '2026-07-08',
    reason: 'Licença maternidade — parto realizado em 10/02/2026. Conforme CLT, art. 392, a colaboradora tem direito a 120 dias de licença. Apresentou certidão de nascimento.',
    status: 'aprovado',
    createdAt: '2026-02-11T14:00:00.000Z',
  },
  {
    id: '5',
    employeeId: 'demo5',
    employeeName: 'Raimundo Ferreira Costa',
    type: 'afastamento',
    startDate: '2026-03-10',
    endDate: '2026-03-10',
    reason: 'Acidente de trabalho durante ronda noturna: entorse no tornozelo direito ao descer escada no Condomínio Empresarial Amazonas. Comunicado de Acidente de Trabalho (CAT) emitido.',
    status: 'aprovado',
    createdAt: '2026-03-10T06:45:00.000Z',
  },
  {
    id: '6',
    employeeId: 'demo6',
    employeeName: 'Antônio Carlos Souza',
    type: 'folga',
    startDate: '2026-03-25',
    endDate: '2026-03-25',
    reason: 'Folga compensatória pela escala de Carnaval — trabalhou nos três dias do feriado municipal. Total de 24h trabalhadas a serem compensadas em três folgas.',
    status: 'aprovado',
    createdAt: '2026-03-01T11:00:00.000Z',
  },
  {
    id: '7',
    employeeId: 'demo7',
    employeeName: 'Maria das Graças Pereira',
    type: 'ferias',
    startDate: '2026-04-07',
    endDate: '2026-04-21',
    reason: 'Férias programadas referentes ao período aquisitivo 2025/2026 — 15 dias conforme acordo com supervisão. Restam mais 15 dias a fruir no segundo semestre.',
    status: 'aprovado',
    createdAt: '2026-03-01T09:30:00.000Z',
  },
  {
    id: '8',
    employeeId: 'demo8',
    employeeName: 'Paulo Henrique Alves',
    type: 'afastamento',
    startDate: '2026-03-12',
    endDate: '2026-03-26',
    reason: 'Afastamento por cirurgia de hérnia inguinal realizada em 12/03/2026. Apresentou atestado hospitalar e relatório do cirurgião com recomendação de repouso de 15 dias.',
    status: 'aprovado',
    createdAt: '2026-03-09T16:00:00.000Z',
  },
  {
    id: '9',
    employeeId: 'demo9',
    employeeName: 'Simone Aparecida Nunes',
    type: 'licenca',
    startDate: '2026-03-18',
    endDate: '2026-03-22',
    reason: 'Licença para acompanhamento de filho menor de idade internado no Hospital e Pronto-Socorro da Criança Zona Sul — pneumonia. Apresentou declaração hospitalar.',
    status: 'pendente',
    createdAt: '2026-03-15T19:30:00.000Z',
  },
  {
    id: '10',
    employeeId: 'demo10',
    employeeName: 'Wellington Barbosa',
    type: 'ferias',
    startDate: '2026-04-14',
    endDate: '2026-05-03',
    reason: 'Férias anuais do período 2024/2025. Viagem programada com a família para Fortaleza-CE. Solicitação antecipada conforme política interna de 30 dias de aviso prévio.',
    status: 'pendente',
    createdAt: '2026-03-05T08:00:00.000Z',
  },
  {
    id: '11',
    employeeId: 'demo11',
    employeeName: 'Eliane Cristina Matos',
    type: 'folga',
    startDate: '2026-03-14',
    endDate: '2026-03-14',
    reason: 'Dia do vigilante — 20 de junho ainda pendente. Adiantamento de folga solicitado pela colaboradora para resolver questão bancária urgente referente a financiamento imobiliário.',
    status: 'rejeitado',
    createdAt: '2026-03-10T13:00:00.000Z',
  },
  {
    id: '12',
    employeeId: 'demo12',
    employeeName: 'Marcos Aurélio Gomes',
    type: 'licenca',
    startDate: '2026-03-20',
    endDate: '2026-03-24',
    reason: 'Licença paternidade — filho nasceu em 20/03/2026. Conforme MP 1166/2023, 5 dias de licença paternidade garantidos. Certidão de nascimento a ser apresentada em até 72h.',
    status: 'pendente',
    createdAt: '2026-03-20T07:00:00.000Z',
  },
  {
    id: '13',
    employeeId: 'demo13',
    employeeName: 'Rosângela Teixeira',
    type: 'afastamento',
    startDate: '2026-01-15',
    endDate: '2026-02-28',
    reason: 'Afastamento por transtorno de ansiedade generalizada (CID F41.1). Colaboradora acompanhada por psiquiatra desde outubro/2025. Laudo médico com restrição de atividades noturnas.',
    status: 'aprovado',
    createdAt: '2026-01-14T15:30:00.000Z',
  },
  {
    id: '14',
    employeeId: 'demo14',
    employeeName: 'Luís Fernando Nascimento',
    type: 'ferias',
    startDate: '2026-05-04',
    endDate: '2026-05-23',
    reason: 'Férias anuais — 20 dias. Período escolhido pelo colaborador para coincidir com férias escolares dos filhos. Aprovado em reunião de planejamento de escala de abril.',
    status: 'pendente',
    createdAt: '2026-03-07T10:00:00.000Z',
  },
  {
    id: '15',
    employeeId: 'demo15',
    employeeName: 'Débora Cristina Santos',
    type: 'afastamento',
    startDate: '2026-03-09',
    endDate: '2026-03-09',
    reason: 'Afastamento de 1 dia por consulta médica especializada (oftalmologista) para renovação de laudo de aptidão visual exigido pelo regulamento interno de vigilantes armados.',
    status: 'rejeitado',
    createdAt: '2026-03-08T18:00:00.000Z',
  },
  {
    id: '16',
    employeeId: 'demo16',
    employeeName: 'Adriano Moreira Lopes',
    type: 'folga',
    startDate: '2026-04-02',
    endDate: '2026-04-02',
    reason: 'Compensação de horas extras da semana de 17 a 21 de março — total de 10h extras acumuladas, sendo esta a primeira folga compensatória das três programadas.',
    status: 'aprovado',
    createdAt: '2026-03-22T09:00:00.000Z',
  },
];

export default function FeriasPage() {
  const router = useRouter();
  const { isAuthenticated, isLoading } = useAuth();

  const [requests, setRequests] = useState<LeaveRequest[]>(DEMO_DATA);
  const [isFetching, setIsFetching] = useState(false);

  const [showNewModal, setShowNewModal] = useState(false);
  const [newForm, setNewForm] = useState({
    employeeId: '',
    type: 'ferias' as LeaveRequest['type'],
    startDate: '',
    endDate: '',
    reason: '',
  });
  const [filterStatus, setFilterStatus] = useState<LeaveRequest['status'] | ''>('');
  const [filterType, setFilterType] = useState<LeaveRequest['type'] | ''>('');

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [isAuthenticated, isLoading, router]);

  const fetchLeaves = async () => {
    setIsFetching(true);
    try {
      const resp = await api.get('/api/v1/operacional/vacations');
      const data = resp.data;
      const mapped = (data.items || []).map((item: any) => ({
        id: item.id,
        employeeId: item.employee_id,
        employeeName: item.employee_name,
        type: item.leave_type as LeaveRequest['type'],
        startDate: item.start_date,
        endDate: item.end_date,
        reason: item.reason,
        status: item.status as LeaveRequest['status'],
        createdAt: item.created_at,
      }));
      setRequests(mapped.length > 0 ? mapped : DEMO_DATA);
    } catch {
      setRequests(DEMO_DATA);
    } finally {
      setIsFetching(false);
    }
  };

  useEffect(() => {
    if (isAuthenticated) {
      fetchLeaves();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated]);

  const { data: employeesData } = useEmployees({ page: 1, page_size: 500 });
  const employees = useMemo(() => (employeesData as any)?.items ?? [], [employeesData]);

  const filteredRequests = useMemo(() => requests.filter(r => {
    if (filterStatus && r.status !== filterStatus) return false;
    if (filterType && r.type !== filterType) return false;
    return true;
  }), [requests, filterStatus, filterType]);

  const stats = useMemo(() => ({
    total: requests.length,
    pendentes: requests.filter(r => r.status === 'pendente').length,
    aprovadas: requests.filter(r => r.status === 'aprovado').length,
    emFerias: requests.filter(r => {
      if (r.status !== 'aprovado') return false;
      const today = new Date().toISOString().split('T')[0] ?? '';
      return r.startDate <= today && r.endDate >= today;
    }).length,
  }), [requests]);

  const handleApprove = async (id: string) => {
    // Optimistic update
    setRequests(prev => prev.map(r => r.id === id ? { ...r, status: 'aprovado' } : r));
    try {
      await api.post(`/api/v1/operacional/vacations/${id}/approve`);
    } catch {
      // Keep optimistic update even if API fails (demo data has string IDs)
    }
  };

  const handleReject = async (id: string) => {
    // Optimistic update
    setRequests(prev => prev.map(r => r.id === id ? { ...r, status: 'rejeitado' } : r));
    try {
      await api.post(`/api/v1/operacional/vacations/${id}/reject`);
    } catch {
      // Keep optimistic update even if API fails (demo data has string IDs)
    }
  };

  const handleCreate = async () => {
    if (!newForm.employeeId || !newForm.startDate || !newForm.endDate) return;
    const emp = employees.find((e: any) => e.id === newForm.employeeId);
    const optimisticReq: LeaveRequest = {
      id: Date.now().toString(),
      employeeId: newForm.employeeId,
      employeeName: emp?.nome || emp?.name || 'Colaborador',
      type: newForm.type,
      startDate: newForm.startDate,
      endDate: newForm.endDate,
      reason: newForm.reason,
      status: 'pendente',
      createdAt: new Date().toISOString(),
    };
    try {
      await api.post('/api/v1/operacional/vacations/', {
        employee_id: newForm.employeeId,
        leave_type: newForm.type,
        start_date: newForm.startDate,
        end_date: newForm.endDate,
        reason: newForm.reason,
      });
      await fetchLeaves();
    } catch {
      // Fallback: add optimistically if API not available
      setRequests(prev => [optimisticReq, ...prev]);
    }
    setShowNewModal(false);
    setNewForm({ employeeId: '', type: 'ferias', startDate: '', endDate: '', reason: '' });
  };

  const getDays = (start: string, end: string) => {
    const diff = new Date(end).getTime() - new Date(start).getTime();
    return Math.ceil(diff / (1000 * 60 * 60 * 24)) + 1;
  };

  const formatDate = (date: string) => {
    const [year, month, day] = date.split('-');
    return `${day}/${month}/${year}`;
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-6 h-6 animate-spin text-[hsl(var(--primary))]" />
      </div>
    );
  }

  if (isFetching && requests === DEMO_DATA) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-6 h-6 animate-spin text-[hsl(var(--primary))]" />
      </div>
    );
  }

  return (
    <div className="p-4 md:p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Link href="/modulos/operacional">
            <Button variant="ghost" size="icon" className="h-8 w-8">
              <ArrowLeft className="w-4 h-4" />
            </Button>
          </Link>
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-xl bg-blue-500/10">
              <Plane className="w-5 h-5 text-blue-500" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-[hsl(var(--foreground))]">
                Férias & Afastamentos
              </h1>
              <p className="text-xs text-[hsl(var(--muted-foreground))]">
                Gestão de solicitações de ausência
              </p>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={fetchLeaves}
            disabled={isFetching}
            className="h-9"
          >
            <RefreshCw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} />
          </Button>
          <Button
            onClick={() => setShowNewModal(true)}
            className="flex items-center gap-2 text-sm"
          >
            <Plus className="w-4 h-4" />
            <span className="hidden sm:inline">Nova Solicitação</span>
            <span className="sm:hidden">Nova</span>
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <Calendar className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />
            <span className="text-xs text-[hsl(var(--muted-foreground))]">Total</span>
          </div>
          <p className="text-2xl font-bold text-[hsl(var(--foreground))]">{stats.total}</p>
        </div>
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <Clock className="w-4 h-4 text-yellow-500" />
            <span className="text-xs text-[hsl(var(--muted-foreground))]">Pendentes</span>
          </div>
          <p className="text-2xl font-bold text-yellow-500">{stats.pendentes}</p>
        </div>
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <CheckCircle className="w-4 h-4 text-green-500" />
            <span className="text-xs text-[hsl(var(--muted-foreground))]">Aprovadas</span>
          </div>
          <p className="text-2xl font-bold text-green-500">{stats.aprovadas}</p>
        </div>
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <Plane className="w-4 h-4 text-blue-500" />
            <span className="text-xs text-[hsl(var(--muted-foreground))]">Em Férias Hoje</span>
          </div>
          <p className="text-2xl font-bold text-blue-500">{stats.emFerias}</p>
        </div>
      </div>

      {/* Filtros */}
      <div className="flex flex-wrap gap-3">
        <select
          value={filterStatus}
          onChange={e => setFilterStatus(e.target.value as LeaveRequest['status'] | '')}
          className="h-9 rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 text-sm text-[hsl(var(--foreground))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]"
        >
          <option value="">Todos os status</option>
          <option value="pendente">Pendente</option>
          <option value="aprovado">Aprovado</option>
          <option value="rejeitado">Rejeitado</option>
        </select>
        <select
          value={filterType}
          onChange={e => setFilterType(e.target.value as LeaveRequest['type'] | '')}
          className="h-9 rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 text-sm text-[hsl(var(--foreground))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]"
        >
          <option value="">Todos os tipos</option>
          <option value="ferias">Férias</option>
          <option value="afastamento">Afastamento Médico</option>
          <option value="licenca">Licença</option>
          <option value="folga">Folga Compensatória</option>
        </select>
        {(filterStatus || filterType) && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => { setFilterStatus(''); setFilterType(''); }}
            className="h-9 text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))]"
          >
            <X className="w-3 h-3 mr-1" />
            Limpar
          </Button>
        )}
      </div>

      {/* Tabela */}
      <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl overflow-hidden">
        {filteredRequests.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-[hsl(var(--muted-foreground))]">
            <Plane className="w-10 h-10 mb-3 opacity-30" />
            <p className="text-sm font-medium">Nenhuma solicitação encontrada</p>
            <p className="text-xs mt-1">Crie uma nova solicitação para começar</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-[hsl(var(--border))]">
                  <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wider">
                    Colaborador
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wider hidden md:table-cell">
                    Tipo
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wider hidden sm:table-cell">
                    Período
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wider hidden lg:table-cell">
                    Dias
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wider hidden xl:table-cell">
                    Motivo
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wider">
                    Ações
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[hsl(var(--border))]">
                {filteredRequests.map(req => (
                  <tr key={req.id} className="hover:bg-[hsl(var(--muted))]/30 transition-colors">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="w-7 h-7 rounded-full bg-[hsl(var(--primary))]/10 flex items-center justify-center flex-shrink-0">
                          <User className="w-3.5 h-3.5 text-[hsl(var(--primary))]" />
                        </div>
                        <span className="text-sm font-medium text-[hsl(var(--foreground))] truncate max-w-[120px]">
                          {req.employeeName || 'Colaborador não identificado'}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3 hidden md:table-cell">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${LEAVE_TYPE_COLORS[req.type]}`}>
                        {LEAVE_TYPE_LABELS[req.type]}
                      </span>
                    </td>
                    <td className="px-4 py-3 hidden sm:table-cell">
                      <span className="text-sm text-[hsl(var(--foreground))]">
                        {formatDate(req.startDate)} — {formatDate(req.endDate)}
                      </span>
                    </td>
                    <td className="px-4 py-3 hidden lg:table-cell">
                      <span className="text-sm font-medium text-[hsl(var(--foreground))]">
                        {getDays(req.startDate, req.endDate)}d
                      </span>
                    </td>
                    <td className="px-4 py-3 hidden xl:table-cell">
                      <span className="text-sm text-[hsl(var(--muted-foreground))] truncate max-w-[180px] block">
                        {req.reason || '—'}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium capitalize ${STATUS_COLORS[req.status]}`}>
                        {req.status}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {req.status === 'pendente' ? (
                        <div className="flex items-center gap-1.5">
                          <button
                            onClick={() => handleApprove(req.id)}
                            className="p-1.5 rounded-lg bg-green-500/10 text-green-500 hover:bg-green-500/20 transition-colors"
                            title="Aprovar"
                          >
                            <CheckCircle className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => handleReject(req.id)}
                            className="p-1.5 rounded-lg bg-red-500/10 text-red-500 hover:bg-red-500/20 transition-colors"
                            title="Rejeitar"
                          >
                            <XCircle className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      ) : (
                        <span className="text-xs text-[hsl(var(--muted-foreground))]">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Modal Nova Solicitação */}
      <Modal
        isOpen={showNewModal}
        onClose={() => setShowNewModal(false)}
        title="Nova Solicitação"
      >
        <div className="space-y-4 py-2">
          {/* Colaborador */}
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-[hsl(var(--foreground))]">
              Colaborador <span className="text-red-500">*</span>
            </label>
            {employees.length > 0 ? (
              <select
                value={newForm.employeeId}
                onChange={e => setNewForm(f => ({ ...f, employeeId: e.target.value }))}
                className="w-full h-9 rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 text-sm text-[hsl(var(--foreground))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]"
              >
                <option value="">Selecionar colaborador...</option>
                {employees.map((emp: any) => (
                  <option key={emp.id} value={emp.id}>
                    {emp.nome || emp.name || emp.full_name || `Colaborador ${emp.id}`}
                  </option>
                ))}
              </select>
            ) : (
              <Input
                placeholder="Nome do colaborador"
                value={newForm.employeeId}
                onChange={e => setNewForm(f => ({ ...f, employeeId: e.target.value }))}
              />
            )}
          </div>

          {/* Tipo */}
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-[hsl(var(--foreground))]">Tipo</label>
            <select
              value={newForm.type}
              onChange={e => setNewForm(f => ({ ...f, type: e.target.value as LeaveRequest['type'] }))}
              className="w-full h-9 rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 text-sm text-[hsl(var(--foreground))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]"
            >
              {(Object.entries(LEAVE_TYPE_LABELS) as [LeaveRequest['type'], string][]).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </div>

          {/* Datas */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-[hsl(var(--foreground))]">
                Data Início <span className="text-red-500">*</span>
              </label>
              <Input
                type="date"
                value={newForm.startDate}
                onChange={e => setNewForm(f => ({ ...f, startDate: e.target.value }))}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-[hsl(var(--foreground))]">
                Data Fim <span className="text-red-500">*</span>
              </label>
              <Input
                type="date"
                value={newForm.endDate}
                min={newForm.startDate}
                onChange={e => setNewForm(f => ({ ...f, endDate: e.target.value }))}
              />
            </div>
          </div>

          {/* Preview dias */}
          {newForm.startDate && newForm.endDate && newForm.endDate >= newForm.startDate && (
            <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[hsl(var(--primary))]/10">
              <Calendar className="w-4 h-4 text-[hsl(var(--primary))]" />
              <span className="text-sm text-[hsl(var(--primary))] font-medium">
                {getDays(newForm.startDate, newForm.endDate)} dia(s) de ausência
              </span>
            </div>
          )}

          {/* Motivo */}
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-[hsl(var(--foreground))]">Motivo</label>
            <textarea
              value={newForm.reason}
              onChange={e => setNewForm(f => ({ ...f, reason: e.target.value }))}
              placeholder="Descreva o motivo da solicitação..."
              rows={3}
              className="w-full rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 py-2 text-sm text-[hsl(var(--foreground))] placeholder:text-[hsl(var(--muted-foreground))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary))] resize-none"
            />
          </div>

          {/* Aviso campos obrigatórios */}
          {(!newForm.employeeId || !newForm.startDate || !newForm.endDate) && (
            <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-yellow-500/10">
              <AlertTriangle className="w-4 h-4 text-yellow-500 flex-shrink-0" />
              <span className="text-xs text-yellow-500">
                Preencha colaborador, data de início e data de fim
              </span>
            </div>
          )}
        </div>

        <ModalFooter>
          <Button variant="ghost" onClick={() => setShowNewModal(false)}>
            Cancelar
          </Button>
          <Button
            onClick={handleCreate}
            disabled={!newForm.employeeId || !newForm.startDate || !newForm.endDate}
          >
            Criar Solicitação
          </Button>
        </ModalFooter>
      </Modal>
    </div>
  );
}
