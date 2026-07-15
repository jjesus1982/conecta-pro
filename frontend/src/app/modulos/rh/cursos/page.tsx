'use client';

import { useState, useEffect, useCallback } from 'react';
import { msgFromDetail } from '@/lib/string';
import { BookOpen, Plus, Clock, Users, CheckCircle, XCircle, Loader2, X, Search, ChevronLeft, ChevronRight } from 'lucide-react';
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

const categoriaCores: Record<string, string> = {
  mandatory_security: 'bg-red-900/30 text-red-400',
  mandatory_safety: 'bg-orange-900/30 text-orange-400',
  technical: 'bg-blue-900/30 text-blue-400',
  behavioral: 'bg-green-900/30 text-green-400',
  leadership: 'bg-purple-900/30 text-purple-400',
  compliance: 'bg-yellow-900/30 text-yellow-400',
  onboarding: 'bg-cyan-900/30 text-cyan-400',
  other: 'bg-gray-800 text-gray-400',
};

const categoriaLabels: Record<string, string> = {
  mandatory_security: 'Obrigatorio Seguranca',
  mandatory_safety: 'Obrigatorio SST',
  technical: 'Tecnico',
  behavioral: 'Comportamental',
  leadership: 'Lideranca',
  compliance: 'Compliance',
  onboarding: 'Integracao',
  other: 'Outros',
};

export default function CursosPage() {
  const [cursos, setCursos] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const pageSize = 9;
  const [form, setForm] = useState({
    name: '', category: 'technical', duration_hours: 8,
    is_mandatory: false, description: '', validity_months: '' as string,
  });

  const loadCursos = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/training/courses?limit=100`, { headers: getAuthHeaders() });
      if (res.ok) {
        const data = await res.json();
        setCursos(data.items || data || []);
      } else {
        toast.error('Erro ao carregar cursos', { duration: 5000 });
      }
    } catch {
      toast.error('Erro de conexao ao carregar cursos', { duration: 5000 });
      setCursos([]);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { loadCursos(); }, [loadCursos]);

  async function handleSave() {
    if (!form.name.trim()) return;
    setSaving(true);
    try {
      const body: Record<string, unknown> = {
        name: form.name,
        category: form.category,
        duration_hours: form.duration_hours,
        is_mandatory: form.is_mandatory,
      };
      if (form.description) body.description = form.description;
      if (form.validity_months) body.validity_months = Number(form.validity_months);
      const res = await fetch(`${API_BASE}/training/courses`, {
        method: 'POST', headers: getAuthHeaders(), body: JSON.stringify(body),
      });
      if (res.ok) {
        toast.success('Curso criado com sucesso', { duration: 4000 });
        setShowModal(false);
        setForm({ name: '', category: 'technical', duration_hours: 8, is_mandatory: false, description: '', validity_months: '' });
        await loadCursos();
      } else {
        const err = await res.json().catch(() => null);
        toast.error(msgFromDetail(err?.detail) || 'Erro ao criar curso', { duration: 5000 });
      }
    } catch {
      toast.error('Erro de conexao ao salvar curso', { duration: 5000 });
    } finally { setSaving(false); }
  }

  const filtered = cursos.filter((c: any) => {
    if (!search) return true;
    const s = search.toLowerCase();
    return (c.name || c.nome || '').toLowerCase().includes(s) ||
           (categoriaLabels[c.category] || c.category || '').toLowerCase().includes(s) ||
           (c.description || '').toLowerCase().includes(s);
  });

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const paginatedData = filtered.slice((page - 1) * pageSize, page * pageSize);

  return (
    <div className="space-y-6 pb-28">
      <PageHeader
        icon={<BookOpen className="h-5 w-5" />}
        title="Catalogo de Cursos"
        subtitle="Cursos disponiveis para treinamento"
        actions={<Button onClick={() => setShowModal(true)}><Plus className="h-4 w-4 mr-2" />Novo Curso</Button>}
      />

      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <input
          type="text"
          placeholder="Buscar por nome, categoria ou descricao..."
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          className="w-full pl-10 pr-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm"
        />
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>
      ) : paginatedData.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">Nenhum curso encontrado</div>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {paginatedData.map((curso: any, i: number) => {
              const cat = curso.category || 'other';
              return (
                <Card key={curso.id || i} className="hover:shadow-md transition-shadow">
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-sm font-medium">{curso.name || curso.nome}</CardTitle>
                      {curso.is_mandatory && (
                        <span className="text-xs bg-red-900/30 text-red-400 px-2 py-0.5 rounded">Obrigatorio</span>
                      )}
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <span className={`text-xs px-2 py-0.5 rounded ${categoriaCores[cat] || 'bg-gray-800 text-gray-400'}`}>
                      {categoriaLabels[cat] || cat}
                    </span>
                    <div className="flex items-center gap-4 text-sm text-muted-foreground">
                      <span className="flex items-center gap-1"><Clock className="h-3 w-3" />{curso.duration_hours || '-'}h</span>
                      <span className="flex items-center gap-1"><Users className="h-3 w-3" />{curso.participants_count || 0}</span>
                    </div>
                    <div className="flex items-center gap-1 text-sm">
                      {curso.is_active !== false ? (
                        <><CheckCircle className="h-4 w-4 text-green-500" /><span className="text-green-500">Ativo</span></>
                      ) : (
                        <><XCircle className="h-4 w-4 text-gray-500" /><span className="text-gray-500">Inativo</span></>
                      )}
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>

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
              <h2 className="text-lg font-bold">Novo Curso</h2>
              <button onClick={() => setShowModal(false)} type="button"><X className="h-5 w-5 text-gray-400 hover:text-white" /></button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="text-sm text-muted-foreground">Titulo *</label>
                <input className="w-full mt-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm"
                  value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="Ex: Tecnicas de Portaria" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-sm text-muted-foreground">Categoria</label>
                  <select className="w-full mt-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm"
                    value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
                    {Object.entries(categoriaLabels).map(([k, v]) => (
                      <option key={k} value={k}>{v}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-sm text-muted-foreground">Carga Horaria (h)</label>
                  <input type="number" min={1} className="w-full mt-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm"
                    value={form.duration_hours} onChange={(e) => setForm({ ...form, duration_hours: Number(e.target.value) })} />
                </div>
              </div>
              <div>
                <label className="text-sm text-muted-foreground">Descricao</label>
                <textarea className="w-full mt-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm"
                  rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
              </div>
              <div className="flex items-center gap-4">
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={form.is_mandatory} onChange={(e) => setForm({ ...form, is_mandatory: e.target.checked })} />
                  Obrigatorio
                </label>
                {form.is_mandatory && (
                  <div className="flex items-center gap-2">
                    <label className="text-sm text-muted-foreground">Validade (meses):</label>
                    <input type="number" min={1} className="w-20 px-2 py-1 bg-gray-800 border border-gray-700 rounded text-sm"
                      value={form.validity_months} onChange={(e) => setForm({ ...form, validity_months: e.target.value })} />
                  </div>
                )}
              </div>
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <Button variant="outline" onClick={() => setShowModal(false)}>Cancelar</Button>
              <Button onClick={handleSave} disabled={saving || !form.name.trim()}>
                {saving ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Plus className="h-4 w-4 mr-2" />}
                Salvar
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
