'use client';

import { useState, useEffect, useCallback } from 'react';
import { UserPlus, CheckCircle, Loader2, Search, ChevronLeft, ChevronRight, AlertTriangle } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { PageHeader } from '@/components/ui/page-header';
import { StatCard } from '@/components/ui/stat-card';
import { toast } from 'sonner';

const API_BASE = '/api/v1/people-management/human-resources';

function getAuthHeaders() {
  let token: string | null = null;
  if (typeof window !== 'undefined') {
    try {
      token = localStorage.getItem('access_token') || localStorage.getItem('token');
    } catch {
      token = null;
    }
  }
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

const statusCores: Record<string, string> = {
  'Iniciado': 'bg-blue-900/30 text-blue-400', 'started': 'bg-blue-900/30 text-blue-400',
  'Em Andamento': 'bg-yellow-900/30 text-yellow-400', 'in_progress': 'bg-yellow-900/30 text-yellow-400',
  'Concluido': 'bg-green-900/30 text-green-400', 'completed': 'bg-green-900/30 text-green-400',
  'pending': 'bg-orange-900/30 text-orange-400',
};

const statusLabels: Record<string, string> = { started: 'Iniciado', in_progress: 'Em Andamento', completed: 'Concluido', pending: 'Pendente' };

const progressoCor = (p: number) => {
  if (p >= 80) return 'bg-green-500';
  if (p >= 50) return 'bg-yellow-500';
  return 'bg-blue-500';
};

export default function OnboardingPage() {
  const [dashboardData, setDashboardData] = useState<any>(null);
  const [pendencias, setPendencias] = useState<any[]>([]);
  const [colaboradores, setColaboradores] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const pageSize = 10;

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const headers = getAuthHeaders();
      const [dashRes, pendRes] = await Promise.all([
        fetch(`${API_BASE}/onboarding/dashboard`, { headers }),
        fetch(`${API_BASE}/onboarding/pendencias`, { headers }).catch(() => null),
      ]);

      if (dashRes.ok) {
        const d = await dashRes.json();
        setDashboardData(d);
        // Extract onboarding items from dashboard data
        const items = d.onboardings || d.employees || d.items || [];
        setColaboradores(Array.isArray(items) ? items : []);
      } else {
        toast.error('Erro ao carregar dados de onboarding', { duration: 5000 });
      }

      if (pendRes?.ok) {
        const data = await pendRes.json();
        setPendencias(data.vencidos || data.items || []);
      }
    } catch {
      toast.error('Erro de conexao ao carregar onboarding', { duration: 5000 });
      setColaboradores([]);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const inProgress = dashboardData?.in_progress ?? colaboradores.filter((c: any) => c.status !== 'completed' && c.status !== 'Concluido').length;
  const completed = dashboardData?.completed ?? colaboradores.filter((c: any) => c.status === 'completed' || c.status === 'Concluido').length;
  const avgProgress = dashboardData?.avg_progress ?? (colaboradores.length > 0
    ? Math.round(colaboradores.reduce((a: number, c: any) => a + (c.progress || c.progresso || 0), 0) / colaboradores.length)
    : 0);

  const filtered = colaboradores.filter((c: any) => {
    if (!search) return true;
    const s = search.toLowerCase();
    return (c.employee_name || c.colaborador || '').toLowerCase().includes(s);
  });

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const paginatedData = filtered.slice((page - 1) * pageSize, page * pageSize);

  return (
    <div className="space-y-6 pb-28">
      <PageHeader
        icon={<UserPlus className="h-5 w-5" />}
        title="Onboarding de Novos Colaboradores"
        subtitle="Acompanhamento da integracao de novos colaboradores"
      />

      {loading ? (
        <div className="flex items-center justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-3">
            <StatCard label="Em Onboarding" value={inProgress} />
            <StatCard label="Concluidos" value={completed} />
            <StatCard label="Progresso Medio" value={`${avgProgress}%`} />
          </div>

          {pendencias.length > 0 && (
            <Card className="border-orange-800 bg-orange-900/10">
              <CardContent className="pt-4">
                <div className="flex items-center gap-2 text-orange-400 mb-2">
                  <AlertTriangle className="h-5 w-5" />
                  <span className="font-medium">{pendencias.length} pendencia(s) de onboarding</span>
                </div>
                <ul className="space-y-1 text-sm text-muted-foreground">
                  {pendencias.slice(0, 5).map((p: any, i: number) => (
                    <li key={i}>{p.employee_name || p.colaborador || p.nome} - {p.task || p.pendencia || p.description || p.titulo}</li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}

          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <input
              type="text"
              placeholder="Buscar colaborador..."
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(1); }}
              className="w-full pl-10 pr-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm"
            />
          </div>

          <Card>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-800">
                      <th className="text-left p-4 text-muted-foreground font-medium">Colaborador</th>
                      <th className="text-left p-4 text-muted-foreground font-medium">Data Admissão</th>
                      <th className="text-center p-4 text-muted-foreground font-medium">Progresso</th>
                      <th className="text-center p-4 text-muted-foreground font-medium">Etapas</th>
                      <th className="text-center p-4 text-muted-foreground font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {paginatedData.length === 0 ? (
                      <tr><td colSpan={5} className="p-8 text-center text-muted-foreground">Nenhum onboarding em andamento</td></tr>
                    ) : paginatedData.map((c: any, i: number) => {
                      const prog = c.progress || c.progresso || 0;
                      const label = statusLabels[c.status] || c.status;
                      const cor = statusCores[c.status] || statusCores[label] || 'bg-gray-800 text-gray-400';
                      const steps = c.completed_steps || c.etapasCompletas || 0;
                      const total = c.total_steps || c.etapasTotal || 8;
                      return (
                        <tr key={c.id || i} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                          <td className="p-4 font-medium">{c.employee_name || c.colaborador}</td>
                          <td className="p-4 text-muted-foreground">{c.admission_date || c.dataAdmissao || '-'}</td>
                          <td className="p-4">
                            <div className="flex items-center gap-2">
                              <div className="flex-1 bg-gray-800 rounded-full h-2">
                                <div className={`${progressoCor(prog)} h-2 rounded-full transition-all`} style={{ width: `${prog}%` }} />
                              </div>
                              <span className="text-xs font-medium w-8 text-right">{prog}%</span>
                            </div>
                          </td>
                          <td className="p-4 text-center">
                            <span className="flex items-center justify-center gap-1">
                              <CheckCircle className={`h-3 w-3 ${steps === total ? 'text-green-400' : 'text-muted-foreground'}`} />
                              {steps}/{total}
                            </span>
                          </td>
                          <td className="p-4 text-center">
                            <span className={`text-xs px-2 py-1 rounded ${cor}`}>{label}</span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

          {totalPages > 1 && (
            <div className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">
                Mostrando {((page - 1) * pageSize) + 1}-{Math.min(page * pageSize, filtered.length)} de {filtered.length}
              </p>
              <div className="flex items-center gap-2">
                <button type="button" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1} className="p-2 rounded hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed">
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <span className="text-sm">Pagina {page} de {totalPages}</span>
                <button type="button" onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages} className="p-2 rounded hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed">
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
