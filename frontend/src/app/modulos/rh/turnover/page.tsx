'use client';

import { useState, useEffect, useCallback } from 'react';
import { Users, AlertTriangle, AlertCircle, CheckCircle, XOctagon, Loader2, Search, ChevronLeft, ChevronRight } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
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

const nivelCores: Record<string, string> = {
  'Baixo': 'bg-green-900/30 text-green-400', 'low': 'bg-green-900/30 text-green-400',
  'Medio': 'bg-yellow-900/30 text-yellow-400', 'medium': 'bg-yellow-900/30 text-yellow-400',
  'Alto': 'bg-orange-900/30 text-orange-400', 'high': 'bg-orange-900/30 text-orange-400',
  'Critico': 'bg-red-900/30 text-red-400', 'critical': 'bg-red-900/30 text-red-400',
};

const nivelLabels: Record<string, string> = { low: 'Baixo', medium: 'Medio', high: 'Alto', critical: 'Critico' };

const scoreCor = (s: number) => {
  if (s >= 0.8) return 'text-red-400';
  if (s >= 0.6) return 'text-orange-400';
  if (s >= 0.4) return 'text-yellow-400';
  return 'text-green-400';
};

export default function TurnoverPage() {
  const [dashboardData, setDashboardData] = useState<any>(null);
  const [motivos, setMotivos] = useState<any[]>([]);
  const [colaboradores, setColaboradores] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const pageSize = 10;

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const headers = getAuthHeaders();
      const [dashRes, motivosRes] = await Promise.all([
        fetch(`${API_BASE}/turnover/dashboard`, { headers }),
        fetch(`${API_BASE}/turnover/motivos`, { headers }).catch(() => null),
      ]);

      if (dashRes.ok) {
        const d = await dashRes.json();
        setDashboardData(d);
        // Extract predictions/employees from dashboard data
        const items = d.predictions || d.employees || d.risk_employees || d.items || [];
        setColaboradores(Array.isArray(items) ? items : []);
      } else {
        toast.error('Erro ao carregar dados de turnover', { duration: 5000 });
      }

      if (motivosRes?.ok) {
        const data = await motivosRes.json();
        setMotivos(data.items || data || []);
      }
    } catch {
      toast.error('Erro de conexao ao carregar turnover', { duration: 5000 });
      setColaboradores([]);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const distribuicao = [
    { nivel: 'Baixo', key: ['Baixo', 'low'], cor: 'text-green-400', bgCor: 'bg-green-900/30', icon: CheckCircle },
    { nivel: 'Medio', key: ['Medio', 'medium'], cor: 'text-yellow-400', bgCor: 'bg-yellow-900/30', icon: AlertCircle },
    { nivel: 'Alto', key: ['Alto', 'high'], cor: 'text-orange-400', bgCor: 'bg-orange-900/30', icon: AlertTriangle },
    { nivel: 'Critico', key: ['Critico', 'critical'], cor: 'text-red-400', bgCor: 'bg-red-900/30', icon: XOctagon },
  ].map(d => ({ ...d, count: colaboradores.filter((c: any) => d.key.includes(c.nivel || c.risk_level)).length }));

  const filtered = colaboradores.filter((c: any) => {
    if (!search) return true;
    const s = search.toLowerCase();
    return (c.employee_name || c.colaborador || '').toLowerCase().includes(s) ||
           (c.factors || c.fatores || '').toLowerCase().includes(s);
  });

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const paginatedData = filtered.slice((page - 1) * pageSize, page * pageSize);

  return (
    <div className="space-y-6 pb-28">
      <PageHeader
        icon={<Users className="h-5 w-5" />}
        title="Previsao de Turnover"
        subtitle="Analise preditiva de risco de desligamento"
      />

      {loading ? (
        <div className="flex items-center justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>
      ) : (
        <>
          {dashboardData && (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
              {dashboardData.turnover_rate !== undefined && (
                <Card>
                  <CardContent className="pt-6">
                    <p className="text-sm text-muted-foreground">Taxa de Turnover</p>
                    <p className="font-data text-2xl font-semibold tabular-nums text-blue-400">{dashboardData.turnover_rate}%</p>
                    <p className="text-xs text-muted-foreground mt-1">Meta: {'<'} 5%</p>
                  </CardContent>
                </Card>
              )}
              {distribuicao.map((d) => (
                <Card key={d.nivel}>
                  <CardContent className="pt-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm text-muted-foreground">{d.nivel}</p>
                        <p className={`font-data text-2xl font-semibold tabular-nums ${d.cor}`}>{d.count}</p>
                        <p className="text-xs text-muted-foreground mt-1">colaboradores</p>
                      </div>
                      <div className={`h-10 w-10 rounded-lg ${d.bgCor} flex items-center justify-center`}>
                        <d.icon className={`h-5 w-5 ${d.cor}`} />
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}

          {!dashboardData && (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
              {distribuicao.map((d) => (
                <Card key={d.nivel}>
                  <CardContent className="pt-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm text-muted-foreground">{d.nivel}</p>
                        <p className={`font-data text-2xl font-semibold tabular-nums ${d.cor}`}>{d.count}</p>
                        <p className="text-xs text-muted-foreground mt-1">colaboradores</p>
                      </div>
                      <div className={`h-10 w-10 rounded-lg ${d.bgCor} flex items-center justify-center`}>
                        <d.icon className={`h-5 w-5 ${d.cor}`} />
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}

          {motivos.length > 0 && (
            <Card>
              <CardContent className="pt-6">
                <h3 className="text-sm font-medium mb-3">Principais Motivos de Desligamento</h3>
                <div className="space-y-2">
                  {motivos.slice(0, 5).map((m: any, i: number) => (
                    <div key={i} className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">{m.motivo || m.reason || m.name}</span>
                      <span className="font-medium">{m.total || m.count || 0}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <input
              type="text"
              placeholder="Buscar colaborador ou fator de risco..."
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
                      <th className="text-center p-4 text-muted-foreground font-medium">Score de Risco</th>
                      <th className="text-center p-4 text-muted-foreground font-medium">Nivel</th>
                      <th className="text-left p-4 text-muted-foreground font-medium">Fatores Principais</th>
                      <th className="text-left p-4 text-muted-foreground font-medium">Ações Sugeridas</th>
                    </tr>
                  </thead>
                  <tbody>
                    {paginatedData.length === 0 ? (
                      <tr><td colSpan={5} className="p-8 text-center text-muted-foreground">Nenhuma previsao de turnover disponivel</td></tr>
                    ) : paginatedData.map((c: any, i: number) => {
                      const nivel = nivelLabels[c.risk_level] || c.nivel || c.risk_level;
                      const cor = nivelCores[c.risk_level || c.nivel] || 'bg-gray-800 text-gray-400';
                      const score = c.score || c.risk_score || 0;
                      return (
                        <tr key={c.id || i} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                          <td className="p-4 font-medium">{c.employee_name || c.colaborador}</td>
                          <td className="p-4 text-center"><span className={`font-mono font-bold ${scoreCor(score)}`}>{(score * 100).toFixed(0)}%</span></td>
                          <td className="p-4 text-center"><span className={`text-xs px-2 py-1 rounded ${cor}`}>{nivel}</span></td>
                          <td className="p-4 text-muted-foreground text-xs">{c.factors || c.fatores || '-'}</td>
                          <td className="p-4 text-muted-foreground text-xs">{c.suggested_actions || c.acoes || '-'}</td>
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
