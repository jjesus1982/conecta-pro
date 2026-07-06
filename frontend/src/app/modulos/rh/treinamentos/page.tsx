'use client';

import { useState, useEffect, useCallback } from 'react';
import { GraduationCap, Plus, MapPin, Loader2, X, Search, ChevronLeft, ChevronRight } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
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
  scheduled: 'bg-blue-900/30 text-blue-400',
  in_progress: 'bg-yellow-900/30 text-yellow-400',
  completed: 'bg-green-900/30 text-green-400',
  cancelled: 'bg-red-900/30 text-red-400',
};

const statusLabels: Record<string, string> = {
  scheduled: 'Agendado', in_progress: 'Em Andamento', completed: 'Concluido', cancelled: 'Cancelado',
};

export default function TreinamentosPage() {
  const [treinamentos, setTreinamentos] = useState<any[]>([]);
  const [cursos, setCursos] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const pageSize = 10;
  const [form, setForm] = useState({
    course_id: '', title: '', start_date: '', end_date: '',
    instructor_name: '', location: '', max_participants: 20,
  });

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [tRes, cRes] = await Promise.all([
        fetch(`${API_BASE}/training/?limit=100`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/training/courses?limit=100`, { headers: getAuthHeaders() }),
      ]);
      if (tRes.ok) {
        const data = await tRes.json();
        setTreinamentos(data.items || data || []);
      } else {
        toast.error('Erro ao carregar treinamentos', { duration: 5000 });
      }
      if (cRes.ok) {
        const data = await cRes.json();
        setCursos(data.items || data || []);
      }
    } catch {
      toast.error('Erro de conexao ao carregar treinamentos', { duration: 5000 });
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  async function handleSave() {
    if (!form.course_id || !form.title || !form.start_date) return;
    setSaving(true);
    try {
      const body: Record<string, unknown> = {
        course_id: form.course_id,
        title: form.title,
        start_date: form.start_date + 'T08:00:00Z',
        max_participants: form.max_participants,
      };
      if (form.end_date) body.end_date = form.end_date + 'T17:00:00Z';
      if (form.instructor_name) body.instructor_name = form.instructor_name;
      if (form.location) body.location = form.location;
      const res = await fetch(`${API_BASE}/training/`, {
        method: 'POST', headers: getAuthHeaders(), body: JSON.stringify(body),
      });
      if (res.ok) {
        toast.success('Treinamento agendado com sucesso', { duration: 4000 });
        setShowModal(false);
        setForm({ course_id: '', title: '', start_date: '', end_date: '', instructor_name: '', location: '', max_participants: 20 });
        await loadData();
      } else {
        const err = await res.json().catch(() => null);
        toast.error(err?.detail || 'Erro ao agendar treinamento', { duration: 5000 });
      }
    } catch {
      toast.error('Erro de conexao ao salvar treinamento', { duration: 5000 });
    } finally { setSaving(false); }
  }

  function formatDate(d: string | null) {
    if (!d) return '-';
    try { return new Date(d).toLocaleDateString('pt-BR'); } catch { return d; }
  }

  const filtered = treinamentos.filter((t: any) => {
    if (!search) return true;
    const s = search.toLowerCase();
    return (t.title || t.course_name || '').toLowerCase().includes(s) ||
           (t.instructor_name || '').toLowerCase().includes(s) ||
           (t.location || '').toLowerCase().includes(s);
  });

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const paginatedData = filtered.slice((page - 1) * pageSize, page * pageSize);

  return (
    <div className="space-y-6 pb-28">
      <PageHeader
        icon={<GraduationCap className="h-5 w-5" />}
        title="Treinamentos"
        subtitle="Agenda e gestao de treinamentos"
        actions={<Button onClick={() => setShowModal(true)}><Plus className="h-4 w-4 mr-2" />Agendar Treinamento</Button>}
      />

      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <input
          type="text"
          placeholder="Buscar por titulo, instrutor ou local..."
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
                      <th className="text-left p-4 text-muted-foreground font-medium">Curso</th>
                      <th className="text-left p-4 text-muted-foreground font-medium">Data Início</th>
                      <th className="text-left p-4 text-muted-foreground font-medium">Data Fim</th>
                      <th className="text-left p-4 text-muted-foreground font-medium">Local</th>
                      <th className="text-left p-4 text-muted-foreground font-medium">Instrutor</th>
                      <th className="text-center p-4 text-muted-foreground font-medium">Participantes</th>
                      <th className="text-center p-4 text-muted-foreground font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {paginatedData.length === 0 ? (
                      <tr><td colSpan={7} className="p-8 text-center text-muted-foreground">Nenhum treinamento encontrado</td></tr>
                    ) : paginatedData.map((t: any, i: number) => {
                      const label = statusLabels[t.status] || t.status;
                      const cor = statusCores[t.status] || 'bg-gray-800 text-gray-400';
                      return (
                        <tr key={t.id || i} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                          <td className="p-4 font-medium">{t.title || t.course_name}</td>
                          <td className="p-4 text-muted-foreground">{formatDate(t.start_date)}</td>
                          <td className="p-4 text-muted-foreground">{formatDate(t.end_date)}</td>
                          <td className="p-4 text-muted-foreground"><span className="flex items-center gap-1"><MapPin className="h-3 w-3" />{t.location || '-'}</span></td>
                          <td className="p-4 text-muted-foreground">{t.instructor_name || '-'}</td>
                          <td className="p-4 text-center">{t.current_participants || 0}/{t.max_participants || '-'}</td>
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

      {showModal && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
          <div className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-lg p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold">Agendar Treinamento</h2>
              <button onClick={() => setShowModal(false)} type="button"><X className="h-5 w-5 text-gray-400 hover:text-white" /></button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="text-sm text-muted-foreground">Curso *</label>
                <select className="w-full mt-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm"
                  value={form.course_id} onChange={(e) => {
                    const c = cursos.find((c: any) => c.id === e.target.value);
                    setForm({
                      ...form,
                      course_id: e.target.value,
                      title: c ? `${c.name} - Turma ${new Date().toLocaleDateString('pt-BR', { month: 'short', year: 'numeric' })}` : form.title,
                    });
                  }}>
                  <option value="">Selecione um curso</option>
                  {cursos.map((c: any) => (
                    <option key={c.id} value={c.id}>{c.name} ({c.duration_hours}h)</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-sm text-muted-foreground">Titulo da Turma *</label>
                <input className="w-full mt-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm"
                  value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })}
                  placeholder="Ex: NR-1 - Turma Abril/2026" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-sm text-muted-foreground">Data Início *</label>
                  <input type="date" className="w-full mt-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm"
                    value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} />
                </div>
                <div>
                  <label className="text-sm text-muted-foreground">Data Fim</label>
                  <input type="date" className="w-full mt-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm"
                    value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-sm text-muted-foreground">Instrutor</label>
                  <input className="w-full mt-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm"
                    value={form.instructor_name} onChange={(e) => setForm({ ...form, instructor_name: e.target.value })}
                    placeholder="Nome do instrutor" />
                </div>
                <div>
                  <label className="text-sm text-muted-foreground">Vagas</label>
                  <input type="number" min={1} className="w-full mt-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm"
                    value={form.max_participants} onChange={(e) => setForm({ ...form, max_participants: Number(e.target.value) })} />
                </div>
              </div>
              <div>
                <label className="text-sm text-muted-foreground">Local</label>
                <input className="w-full mt-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm"
                  value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })}
                  placeholder="Ex: Sala de treinamento Conecta Mais" />
              </div>
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <Button variant="outline" onClick={() => setShowModal(false)}>Cancelar</Button>
              <Button onClick={handleSave} disabled={saving || !form.course_id || !form.title || !form.start_date}>
                {saving ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Plus className="h-4 w-4 mr-2" />}
                Agendar
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
