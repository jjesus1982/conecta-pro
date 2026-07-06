'use client';

import { useState, useEffect, useCallback } from 'react';
import { Heart, Loader2, Search, ChevronLeft, ChevronRight, AlertTriangle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { PageHeader } from '@/components/ui/page-header';
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
  'Em Andamento': 'bg-yellow-900/30 text-yellow-400',
  'Concluida': 'bg-green-900/30 text-green-400',
  'in_progress': 'bg-yellow-900/30 text-yellow-400',
  'completed': 'bg-green-900/30 text-green-400',
  'active': 'bg-yellow-900/30 text-yellow-400',
};

const scoreCor = (s: number) => {
  if (s >= 80) return 'text-green-400';
  if (s >= 60) return 'text-yellow-400';
  return 'text-red-400';
};

export default function ClimaPage() {
  const [pesquisas, setPesquisas] = useState<any[]>([]);
  const [dashboardData, setDashboardData] = useState<any>(null);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const pageSize = 10;

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const headers = getAuthHeaders();
      const [dashRes, surveysRes, alertsRes] = await Promise.all([
        fetch(`${API_BASE}/climate/dashboard`, { headers }).catch(() => null),
        fetch(`${API_BASE}/climate/surveys?page=${page}&page_size=${pageSize}`, { headers }).catch(() => null),
        fetch(`${API_BASE}/climate/alerts`, { headers }).catch(() => null),
      ]);

      if (dashRes?.ok) {
        const d = await dashRes.json();
        setDashboardData(d);
      }

      if (surveysRes?.ok) {
        const data = await surveysRes.json();
        setPesquisas(data.items || data || []);
      } else if (surveysRes) {
        toast.error('Erro ao carregar pesquisas de clima', { duration: 5000 });
      }

      if (alertsRes?.ok) {
        const data = await alertsRes.json();
        setAlerts(data.items || data || []);
      }
    } catch {
      toast.error('Erro de conexao ao carregar dados de clima', { duration: 5000 });
      setPesquisas([]);
    } finally { setLoading(false); }
  }, [page]);

  useEffect(() => { loadData(); }, [loadData]);

  const scoreGeral = dashboardData?.overall_score
    ?? (pesquisas.length > 0
      ? Math.round(pesquisas.reduce((a: number, p: any) => a + (p.score || p.overall_score || 0), 0) / pesquisas.length)
      : 0);

  const filtered = pesquisas.filter((p: any) => {
    if (!search) return true;
    const s = search.toLowerCase();
    return (p.name || p.nome || p.title || '').toLowerCase().includes(s) ||
           (p.period || p.periodo || '').toLowerCase().includes(s);
  });

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const paginatedData = filtered.slice((page - 1) * pageSize, page * pageSize);

  return (
    <div className="space-y-6 pb-28">
      <PageHeader
        icon={<Heart className="h-5 w-5" />}
        title="Clima Organizacional"
        subtitle="Pesquisas e indicadores de clima"
      />

      {loading ? (
        <div className="flex items-center justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>
      ) : (
        <>
          {alerts.length > 0 && (
            <Card className="border-yellow-800 bg-yellow-900/10">
              <CardContent className="pt-4">
                <div className="flex items-center gap-2 text-yellow-400 mb-2">
                  <AlertTriangle className="h-5 w-5" />
                  <span className="font-medium">{alerts.length} alerta(s) de clima</span>
                </div>
                <ul className="space-y-1 text-sm text-muted-foreground">
                  {alerts.slice(0, 5).map((a: any, i: number) => (
                    <li key={i}>{a.message || a.description || a.title || JSON.stringify(a)}</li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}

          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader><CardTitle className="text-sm font-medium">Score Geral</CardTitle></CardHeader>
              <CardContent>
                <div className="flex flex-col items-center">
                  <span className={`text-6xl font-bold ${scoreCor(scoreGeral)}`}>{scoreGeral}</span>
                  <span className="text-muted-foreground text-sm mt-1">de 100 pontos</span>
                  <div className="w-full mt-4 bg-gray-800 rounded-full h-3">
                    <div className={`h-3 rounded-full transition-all ${scoreGeral >= 80 ? 'bg-green-500' : scoreGeral >= 60 ? 'bg-yellow-500' : 'bg-red-500'}`} style={{ width: `${scoreGeral}%` }} />
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle className="text-sm font-medium">Resumo</CardTitle></CardHeader>
              <CardContent>
                <div className="space-y-2 text-sm text-muted-foreground">
                  <p>Total de pesquisas: <span className="font-bold text-foreground">{pesquisas.length}</span></p>
                  <p>Pesquisas ativas: <span className="font-bold text-foreground">{pesquisas.filter((p: any) => p.ativo === true || p.status === 'active' || p.status === 'in_progress').length}</span></p>
                  <p>Concluidas: <span className="font-bold text-foreground">{pesquisas.filter((p: any) => p.ativo === false || p.status === 'completed').length}</span></p>
                  {dashboardData?.participation_rate !== undefined && (
                    <p>Taxa de participacao: <span className="font-bold text-foreground">{dashboardData.participation_rate}%</span></p>
                  )}
                  <p>Alertas ativos: <span className="font-bold text-foreground">{alerts.length}</span></p>
                </div>
              </CardContent>
            </Card>
          </div>

          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <input
              type="text"
              placeholder="Buscar pesquisa por nome ou periodo..."
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
                      <th className="text-left p-4 text-muted-foreground font-medium">Pesquisa</th>
                      <th className="text-left p-4 text-muted-foreground font-medium">Periodo</th>
                      <th className="text-center p-4 text-muted-foreground font-medium">Respostas</th>
                      <th className="text-center p-4 text-muted-foreground font-medium">Score Medio</th>
                      <th className="text-center p-4 text-muted-foreground font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {paginatedData.length === 0 ? (
                      <tr><td colSpan={5} className="p-8 text-center text-muted-foreground">Nenhuma pesquisa de clima encontrada</td></tr>
                    ) : paginatedData.map((p: any, i: number) => {
                      const cor = statusCores[p.status] || 'bg-gray-800 text-gray-400';
                      const label = p.status === 'completed' ? 'Concluida' : p.status === 'in_progress' || p.status === 'active' ? 'Em Andamento' : p.status;
                      return (
                        <tr key={p.id || i} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                          <td className="p-4 font-medium">{p.name || p.nome || p.title}</td>
                          <td className="p-4 text-muted-foreground">{p.period || p.periodo || '-'}</td>
                          <td className="p-4 text-center">{p.responses || p.respostas || 0}/{p.total_employees || p.total || '-'}</td>
                          <td className="p-4 text-center"><span className={scoreCor(p.score || p.overall_score || 0)}>{p.score || p.overall_score || 0}</span></td>
                          <td className="p-4 text-center"><span className={`text-xs px-2 py-1 rounded ${cor}`}>{label}</span></td>
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
                <button
                  type="button"
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="p-2 rounded hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <span className="text-sm">Pagina {page} de {totalPages}</span>
                <button
                  type="button"
                  onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                  className="p-2 rounded hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed"
                >
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
