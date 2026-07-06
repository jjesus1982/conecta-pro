'use client';

import { useState, useEffect, useCallback } from 'react';
import { TrendingUp, ArrowRight, Loader2, Search, ChevronLeft, ChevronRight } from 'lucide-react';
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

const statusCores: Record<string, string> = {
  'Iniciado': 'bg-blue-900/30 text-blue-400',
  'Em Andamento': 'bg-yellow-900/30 text-yellow-400',
  'Concluido': 'bg-green-900/30 text-green-400',
  'in_progress': 'bg-yellow-900/30 text-yellow-400',
  'started': 'bg-blue-900/30 text-blue-400',
  'completed': 'bg-green-900/30 text-green-400',
};

const statusLabels: Record<string, string> = {
  in_progress: 'Em Andamento',
  started: 'Iniciado',
  completed: 'Concluido',
};

const progressoCor = (p: number) => {
  if (p >= 80) return 'bg-green-500';
  if (p >= 50) return 'bg-yellow-500';
  return 'bg-blue-500';
};

export default function CarreiraPage() {
  const [planos, setPlanos] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const pageSize = 10;

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/career/plans?limit=100`, { headers: getAuthHeaders() });
      if (res.ok) {
        const data = await res.json();
        setPlanos(data.items || data || []);
      } else {
        toast.error('Erro ao carregar planos de carreira', { duration: 5000 });
      }
    } catch {
      toast.error('Erro de conexao ao carregar planos de carreira', { duration: 5000 });
      setPlanos([]);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const filtered = planos.filter((p: any) => {
    if (!search) return true;
    const s = search.toLowerCase();
    return (p.employee_name || p.colaborador || '').toLowerCase().includes(s) ||
           (p.current_position || p.cargoAtual || '').toLowerCase().includes(s) ||
           (p.target_position || p.cargoAlvo || '').toLowerCase().includes(s) ||
           (p.mentor_name || p.mentor || '').toLowerCase().includes(s);
  });

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const paginatedData = filtered.slice((page - 1) * pageSize, page * pageSize);

  return (
    <div className="space-y-6 pb-28">
      <PageHeader
        icon={<TrendingUp className="h-5 w-5" />}
        title="Planos de Carreira"
        subtitle="Desenvolvimento e progressao dos colaboradores"
      />

      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <input
          type="text"
          placeholder="Buscar por colaborador, cargo ou mentor..."
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          className="w-full pl-10 pr-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm"
        />
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>
      ) : (
        <>
          <Card>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-800">
                      <th className="text-left p-4 text-muted-foreground font-medium">Colaborador</th>
                      <th className="text-left p-4 text-muted-foreground font-medium">Cargo Atual</th>
                      <th className="text-left p-4 text-muted-foreground font-medium">Cargo Alvo</th>
                      <th className="text-center p-4 text-muted-foreground font-medium">Nivel</th>
                      <th className="text-center p-4 text-muted-foreground font-medium">Progresso</th>
                      <th className="text-center p-4 text-muted-foreground font-medium">Status</th>
                      <th className="text-left p-4 text-muted-foreground font-medium">Mentor</th>
                    </tr>
                  </thead>
                  <tbody>
                    {paginatedData.length === 0 ? (
                      <tr><td colSpan={7} className="p-8 text-center text-muted-foreground">Nenhum plano de carreira encontrado</td></tr>
                    ) : paginatedData.map((p: any, i: number) => {
                      const status = statusLabels[p.status] || p.status;
                      const cor = statusCores[p.status] || statusCores[status] || 'bg-gray-800 text-gray-400';
                      const prog = p.progress || p.progresso || 0;
                      return (
                        <tr key={p.id || i} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                          <td className="p-4 font-medium">{p.employee_name || p.colaborador}</td>
                          <td className="p-4 text-muted-foreground">{p.current_position || p.cargoAtual}</td>
                          <td className="p-4 text-muted-foreground">{p.target_position || p.cargoAlvo}</td>
                          <td className="p-4 text-center">
                            <span className="flex items-center justify-center gap-1 text-xs text-muted-foreground">
                              {p.current_level || p.nivelAtual || '-'} <ArrowRight className="h-3 w-3" /> {p.target_level || p.nivelAlvo || '-'}
                            </span>
                          </td>
                          <td className="p-4">
                            <div className="flex items-center gap-2">
                              <div className="flex-1 bg-gray-800 rounded-full h-2">
                                <div className={`${progressoCor(prog)} h-2 rounded-full transition-all`} style={{ width: `${prog}%` }} />
                              </div>
                              <span className="text-xs font-medium w-8 text-right">{prog}%</span>
                            </div>
                          </td>
                          <td className="p-4 text-center">
                            <span className={`text-xs px-2 py-1 rounded ${cor}`}>{status}</span>
                          </td>
                          <td className="p-4 text-muted-foreground">{p.mentor_name || p.mentor || '-'}</td>
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
