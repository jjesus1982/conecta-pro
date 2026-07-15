'use client';

import { useState, useEffect, useCallback } from 'react';
import { msgFromDetail } from '@/lib/string';
import { ClipboardCheck, Plus, Star, Loader2, X, Save, Search, ChevronLeft, ChevronRight } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
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
  'draft': 'bg-gray-800 text-gray-400',
  'Rascunho': 'bg-gray-800 text-gray-400',
  'self_assessment': 'bg-blue-900/30 text-blue-400',
  'Auto-Avaliacao': 'bg-blue-900/30 text-blue-400',
  'manager_review': 'bg-yellow-900/30 text-yellow-400',
  'Revisao Gestor': 'bg-yellow-900/30 text-yellow-400',
  'completed': 'bg-green-900/30 text-green-400',
  'Concluida': 'bg-green-900/30 text-green-400',
};

const statusLabels: Record<string, string> = {
  draft: 'Rascunho',
  self_assessment: 'Auto-Avaliacao',
  manager_review: 'Revisao Gestor',
  completed: 'Concluida',
};

export default function AvaliacoesPage() {
  const [avaliacoes, setAvaliacoes] = useState<any[]>([]);
  const [ciclos, setCiclos] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const pageSize = 10;
  const [employees, setEmployees] = useState<any[]>([]);
  const [formData, setFormData] = useState({ employee_id: '', reviewer_id: '', type: 'quarterly', review_period_start: '', review_period_end: '' });

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const headers = getAuthHeaders();
      const [reviewsRes, ciclosRes, empRes] = await Promise.all([
        fetch(`${API_BASE}/performance/reviews?limit=100`, { headers }),
        fetch(`${API_BASE}/evaluation-360/ciclos`, { headers }).catch(() => null),
        fetch(`/api/v1/people-management/hr/employees?page=1&page_size=200`, { headers }).catch(() => null),
      ]);
      if (empRes?.ok) {
        const data = await empRes.json();
        setEmployees(data.items || data || []);
      }
      if (reviewsRes.ok) {
        const data = await reviewsRes.json();
        setAvaliacoes(data.items || data || []);
      } else {
        toast.error('Erro ao carregar avaliacoes', { duration: 5000 });
      }
      if (ciclosRes?.ok) {
        const data = await ciclosRes.json();
        setCiclos(data.items || data || []);
      }
    } catch {
      toast.error('Erro de conexao ao carregar avaliacoes', { duration: 5000 });
      setAvaliacoes([]);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const concluidas = avaliacoes.filter((a: any) => a.status === 'completed' || a.status === 'Concluida').length;
  const total = avaliacoes.length;
  const pct = total > 0 ? Math.round((concluidas / total) * 100) : 0;

  const filtered = avaliacoes.filter((a: any) => {
    if (!search) return true;
    const s = search.toLowerCase();
    return (a.employee_name || a.colaborador || '').toLowerCase().includes(s) ||
           (a.reviewer_name || a.avaliador || '').toLowerCase().includes(s);
  });

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const paginatedData = filtered.slice((page - 1) * pageSize, page * pageSize);

  return (
    <div className="space-y-6 pb-28">
      <PageHeader
        icon={<ClipboardCheck className="h-5 w-5" />}
        title="Avaliacoes de Desempenho"
        subtitle="Ciclos de avaliacao e acompanhamento"
        actions={<Button onClick={() => setShowForm(true)}><Plus className="h-4 w-4 mr-2" />Iniciar Ciclo de Avaliacao</Button>}
      />

      {showForm && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Nova Avaliacao de Desempenho</CardTitle>
              <Button variant="ghost" size="sm" onClick={() => setShowForm(false)}><X className="h-4 w-4" /></Button>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="text-sm font-medium mb-1 block">Colaborador *</label>
                <select value={formData.employee_id} onChange={e => setFormData(p => ({ ...p, employee_id: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm bg-background">
                  <option value="">Selecione o colaborador...</option>
                  {employees.map((emp: any) => <option key={emp.id} value={emp.id}>{emp.nome || emp.name || emp.full_name || emp.id}</option>)}
                </select>
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Avaliador *</label>
                <select value={formData.reviewer_id} onChange={e => setFormData(p => ({ ...p, reviewer_id: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm bg-background">
                  <option value="">Selecione o avaliador...</option>
                  {employees.map((emp: any) => <option key={emp.id} value={emp.id}>{emp.nome || emp.name || emp.full_name || emp.id}</option>)}
                </select>
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Tipo</label>
                <select value={formData.type} onChange={e => setFormData(p => ({ ...p, type: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm bg-background">
                  <option value="quarterly">Trimestral</option>
                  <option value="semi_annual">Semestral</option>
                  <option value="annual">Anual</option>
                  <option value="probation">Experiencia</option>
                </select>
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Periodo Inicio</label>
                <input type="date" value={formData.review_period_start} onChange={e => setFormData(p => ({ ...p, review_period_start: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm bg-background" />
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Periodo Fim</label>
                <input type="date" value={formData.review_period_end} onChange={e => setFormData(p => ({ ...p, review_period_end: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm bg-background" />
              </div>
            </div>
            <div className="flex gap-2 mt-4">
              <Button size="sm" disabled={saving || !formData.employee_id || !formData.reviewer_id || !formData.review_period_start || !formData.review_period_end} onClick={async () => {
                setSaving(true);
                try {
                  const res = await fetch(`${API_BASE}/performance/reviews`, { method: 'POST', headers: getAuthHeaders(), body: JSON.stringify(formData) });
                  if (res.ok) {
                    const newReview = await res.json();
                    setAvaliacoes(prev => [newReview, ...prev]);
                    setShowForm(false);
                    setFormData({ employee_id: '', reviewer_id: '', type: 'quarterly', review_period_start: '', review_period_end: '' });
                    toast.success('Avaliacao criada com sucesso', { duration: 4000 });
                  } else {
                    const err = await res.json().catch(() => null);
                    toast.error(msgFromDetail(err?.detail) || 'Erro ao criar avaliacao', { duration: 5000 });
                  }
                } catch {
                  toast.error('Erro de conexao ao criar avaliacao', { duration: 5000 });
                } finally { setSaving(false); }
              }}>
                {saving ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Save className="h-4 w-4 mr-1" />}
                {saving ? 'Salvando...' : 'Criar Avaliacao'}
              </Button>
              <Button variant="outline" size="sm" onClick={() => setShowForm(false)}>Cancelar</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-2">
            <Card className="border-primary/30 bg-primary/5">
              <CardContent className="pt-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-medium">Ciclo de Avaliacoes</p>
                    <p className="text-sm text-muted-foreground">{total} avaliacoes registradas</p>
                  </div>
                  <div className="text-right">
                    <p className="font-data text-2xl font-semibold tabular-nums">{pct}%</p>
                    <p className="text-xs text-muted-foreground">{concluidas}/{total} concluidas</p>
                  </div>
                </div>
                <div className="mt-3 w-full bg-gray-800 rounded-full h-2">
                  <div className="bg-primary h-2 rounded-full transition-all" style={{ width: `${pct}%` }} />
                </div>
              </CardContent>
            </Card>

            {ciclos.length > 0 && (
              <Card>
                <CardContent className="pt-4">
                  <p className="font-medium mb-2">Ciclos 360</p>
                  <div className="space-y-1 text-sm text-muted-foreground">
                    {ciclos.slice(0, 3).map((c: any, i: number) => (
                      <div key={i} className="flex items-center justify-between">
                        <span>{c.name || c.nome || `Ciclo ${i + 1}`}</span>
                        <span className={`text-xs px-2 py-0.5 rounded ${statusCores[c.status] || 'bg-gray-800 text-gray-400'}`}>
                          {statusLabels[c.status] || c.status}
                        </span>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}
          </div>

          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <input
              type="text"
              placeholder="Buscar por colaborador ou avaliador..."
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
                      <th className="text-left p-4 text-muted-foreground font-medium">Avaliador</th>
                      <th className="text-center p-4 text-muted-foreground font-medium">Tipo</th>
                      <th className="text-center p-4 text-muted-foreground font-medium">Score</th>
                      <th className="text-center p-4 text-muted-foreground font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {paginatedData.length === 0 ? (
                      <tr><td colSpan={5} className="p-8 text-center text-muted-foreground">Nenhuma avaliacao encontrada</td></tr>
                    ) : paginatedData.map((a: any, i: number) => {
                      const label = statusLabels[a.status] || a.status;
                      const cor = statusCores[a.status] || statusCores[label] || 'bg-gray-800 text-gray-400';
                      return (
                        <tr key={a.id || i} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                          <td className="p-4 font-medium">{a.employee_name || a.colaborador}</td>
                          <td className="p-4 text-muted-foreground">{a.reviewer_name || a.avaliador}</td>
                          <td className="p-4 text-center text-muted-foreground">{a.review_type || a.tipo || 'Trimestral'}</td>
                          <td className="p-4 text-center">
                            {a.overall_score || a.score ? (
                              <span className="flex items-center justify-center gap-1"><Star className="h-3 w-3 text-yellow-400" />{(a.overall_score || a.score).toFixed?.(1) || a.overall_score || a.score}</span>
                            ) : <span className="text-muted-foreground">-</span>}
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
