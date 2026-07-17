'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { customInstance } from '@/lib/api-client';
import { FileCheck, Plus, Search, Filter, Loader2, X } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

interface Justificativa {
  id?: string | number;
  colaborador?: string;
  employee_name?: string;
  data?: string;
  date?: string;
  tipo?: string;
  type?: string;
  motivo?: string;
  reason?: string;
  status?: 'pendente' | 'aprovada' | 'rejeitada' | string;
  anexo?: boolean;
  has_attachment?: boolean;
}

interface Employee {
  id: string;
  nome?: string;
  name?: string;
}

interface JustificativaPayload {
  employee_id: string;
  justification_type: string;
  reason: string;
  category: string;
}

const statusConfig: Record<string, { label: string; classes: string }> = {
  pendente: { label: 'Pendente', classes: 'bg-amber-500/10 text-amber-500 border border-amber-500/30' },
  aprovada: { label: 'Aprovada', classes: 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/30' },
  rejeitada: { label: 'Rejeitada', classes: 'bg-red-500/10 text-red-500 border border-red-500/30' },
};

export default function JustificativasPage() {
  const queryClient = useQueryClient();
  const [filtro, setFiltro] = useState('todos');
  const [busca, setBusca] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({ employee_id: '', justification_type: 'atraso', reason: '', category: 'outro' });

  const { data: employees } = useQuery<Employee[]>({
    queryKey: ['ponto', 'employees-list'],
    queryFn: async () => {
      // page_size máx do endpoint é 100 (200 dava 422 e a tela ficava vazia)
      const res = await customInstance({ url: '/api/v1/people-management/hr/employees', params: { page_size: 100 } }) as unknown as { items?: Employee[] } | Employee[];
      return Array.isArray(res) ? res : res?.items ?? [];
    },
    staleTime: 60000,
  });

  const { data: rawData, isLoading, error } = useQuery<Justificativa[]>({
    queryKey: ['ponto', 'justificativas', 'pendentes'],
    queryFn: async () => {
      const res = await customInstance({ url: '/api/v1/people-management/ponto/justificativas/pendentes' }) as unknown;
      if (Array.isArray(res)) return res as Justificativa[];
      const obj = res as Record<string, unknown>;
      return (obj?.items ?? obj?.justificativas ?? []) as Justificativa[];
    },
    staleTime: 30000,
    retry: 2,
  });

  const justificativas: Justificativa[] = rawData ?? [];

  const createMutation = useMutation({
    mutationFn: (body: JustificativaPayload) => customInstance({
      url: '/api/v1/people-management/ponto/justificativa',
      method: 'POST',
      data: body,
    }),
    onSuccess: () => {
      setShowForm(false);
      setFormData({ employee_id: '', justification_type: 'atraso', reason: '', category: 'outro' });
      queryClient.invalidateQueries({ queryKey: ['ponto', 'justificativas'] });
    },
  });

  const filtered = justificativas.filter((j) => {
    const status = j.status || 'pendente';
    const nome = j.colaborador || j.employee_name || '';
    const matchFiltro = filtro === 'todos' || status === filtro;
    const matchBusca = !busca || nome.toLowerCase().includes(busca.toLowerCase());
    return matchFiltro && matchBusca;
  });

  function handleSubmitJustificativa(e: React.FormEvent) {
    e.preventDefault();
    if (!formData.employee_id || !formData.reason) return;
    createMutation.mutate({
      employee_id: formData.employee_id,
      justification_type: formData.justification_type,
      reason: formData.reason,
      category: formData.category,
    });
  }

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <FileCheck className="w-6 h-6 text-amber-500" />
          <h1 className="font-display text-2xl font-bold text-[hsl(var(--foreground))]">Justificativas</h1>
        </div>
        <button
          type="button"
          onClick={() => setShowForm(true)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
        >
          <Plus className="h-4 w-4" />
          Nova Justificativa
        </button>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 text-red-500 px-4 py-3 rounded-lg text-sm">
          Erro ao carregar justificativas: {(error as Error).message}
        </div>
      )}

      {createMutation.isSuccess && (
        <div className="bg-emerald-500/10 border border-emerald-500/30 text-emerald-500 px-4 py-3 rounded-lg text-sm">
          Justificativa criada com sucesso!
        </div>
      )}

      <div className="flex items-center gap-4">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[hsl(var(--muted-foreground))]" />
          <input
            type="text"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            placeholder="Buscar por colaborador..."
            className="w-full pl-10 pr-4 py-2 border border-[hsl(var(--border))] rounded-lg text-sm bg-[hsl(var(--card))] focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        </div>
        <div className="flex gap-2">
          {['todos', 'pendente', 'aprovada', 'rejeitada'].map((f) => (
            <button
              key={f}
              onClick={() => setFiltro(f)}
              className={`px-3 py-1.5 text-xs font-medium rounded-full transition-colors ${
                filtro === f
                  ? 'bg-blue-600 text-white'
                  : 'bg-[hsl(var(--secondary))] text-[hsl(var(--muted-foreground))] hover:bg-[hsl(var(--secondary))]/80'
              }`}
            >
              {f === 'todos' ? 'Todos' : statusConfig[f]?.label}
            </button>
          ))}
        </div>
      </div>

      <Card className="border border-[hsl(var(--border))]">
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[hsl(var(--border))] bg-[hsl(var(--secondary))]">
                    <th className="text-left py-3 px-4 font-medium text-[hsl(var(--muted-foreground))]">Colaborador</th>
                    <th className="text-left py-3 px-4 font-medium text-[hsl(var(--muted-foreground))]">Data</th>
                    <th className="text-left py-3 px-4 font-medium text-[hsl(var(--muted-foreground))]">Tipo</th>
                    <th className="text-left py-3 px-4 font-medium text-[hsl(var(--muted-foreground))]">Motivo</th>
                    <th className="text-left py-3 px-4 font-medium text-[hsl(var(--muted-foreground))]">Anexo</th>
                    <th className="text-left py-3 px-4 font-medium text-[hsl(var(--muted-foreground))]">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="py-8 text-center text-[hsl(var(--muted-foreground))]">
                        Nenhuma justificativa encontrada
                      </td>
                    </tr>
                  ) : (
                    filtered.map((j, idx) => {
                      const status = j.status || 'pendente';
                      const hasAttachment = j.anexo ?? j.has_attachment ?? false;
                      return (
                        <tr key={j.id ?? idx} className="border-b border-[hsl(var(--border))] hover:bg-[hsl(var(--secondary))] cursor-pointer">
                          <td className="py-3 px-4 font-medium text-[hsl(var(--foreground))]">{j.colaborador || j.employee_name || '--'}</td>
                          <td className="py-3 px-4 text-[hsl(var(--muted-foreground))]">{j.data || j.date || '--'}</td>
                          <td className="py-3 px-4">
                            <span className="inline-flex px-2 py-0.5 text-xs font-medium rounded bg-[hsl(var(--secondary))] text-[hsl(var(--foreground))]">
                              {j.tipo || j.type || '--'}
                            </span>
                          </td>
                          <td className="py-3 px-4 text-[hsl(var(--muted-foreground))] max-w-xs truncate">{j.motivo || j.reason || '--'}</td>
                          <td className="py-3 px-4">
                            {hasAttachment ? (
                              <span className="text-blue-500 text-xs font-medium">Sim</span>
                            ) : (
                              <span className="text-[hsl(var(--muted-foreground))] text-xs">Nao</span>
                            )}
                          </td>
                          <td className="py-3 px-4">
                            <span className={`inline-flex px-2 py-1 text-xs font-medium rounded-full ${statusConfig[status]?.classes ?? 'bg-[hsl(var(--secondary))] text-[hsl(var(--muted-foreground))]'}`}>
                              {statusConfig[status]?.label ?? status}
                            </span>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {showForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <Card className="w-full max-w-md border border-[hsl(var(--border))]">
            <CardContent className="p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-bold text-[hsl(var(--foreground))]">Nova Justificativa</h3>
                <button onClick={() => setShowForm(false)} className="p-1 hover:bg-[hsl(var(--secondary))] rounded">
                  <X className="h-5 w-5 text-[hsl(var(--muted-foreground))]" />
                </button>
              </div>
              {createMutation.isError && (
                <div className="bg-red-500/10 border border-red-500/30 text-red-500 px-3 py-2 rounded-lg text-sm mb-4">
                  {(createMutation.error as Error).message}
                </div>
              )}
              <form onSubmit={handleSubmitJustificativa} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-[hsl(var(--foreground))] mb-1">Colaborador</label>
                  <select
                    value={formData.employee_id}
                    onChange={(e) => setFormData({ ...formData, employee_id: e.target.value })}
                    className="w-full px-3 py-2 border border-[hsl(var(--border))] rounded-lg text-sm bg-[hsl(var(--card))] focus:outline-none focus:ring-2 focus:ring-blue-500"
                    required
                  >
                    <option value="">Selecione...</option>
                    {(employees ?? []).map((emp) => (
                      <option key={emp.id} value={emp.id}>{emp.nome || emp.name || emp.id}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-[hsl(var(--foreground))] mb-1">Tipo</label>
                  <select
                    value={formData.justification_type}
                    onChange={(e) => setFormData({ ...formData, justification_type: e.target.value })}
                    className="w-full px-3 py-2 border border-[hsl(var(--border))] rounded-lg text-sm bg-[hsl(var(--card))] focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="atraso">Atraso</option>
                    <option value="falta">Falta</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-[hsl(var(--foreground))] mb-1">Categoria</label>
                  <select
                    value={formData.category}
                    onChange={(e) => setFormData({ ...formData, category: e.target.value })}
                    className="w-full px-3 py-2 border border-[hsl(var(--border))] rounded-lg text-sm bg-[hsl(var(--card))] focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="transito">Trânsito</option>
                    <option value="saude">Saúde</option>
                    <option value="familiar">Familiar</option>
                    <option value="transporte_publico">Transporte Público</option>
                    <option value="acidente">Acidente</option>
                    <option value="outro">Outro</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-[hsl(var(--foreground))] mb-1">Motivo</label>
                  <textarea
                    value={formData.reason}
                    onChange={(e) => setFormData({ ...formData, reason: e.target.value })}
                    rows={3}
                    placeholder="Descreva o motivo (mínimo 5 caracteres)"
                    className="w-full px-3 py-2 border border-[hsl(var(--border))] rounded-lg text-sm bg-[hsl(var(--card))] focus:outline-none focus:ring-2 focus:ring-blue-500"
                    required
                  />
                </div>
                <div className="flex justify-end gap-3 pt-2">
                  <button
                    type="button"
                    onClick={() => setShowForm(false)}
                    disabled={createMutation.isPending}
                    className="px-4 py-2 bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-lg text-sm font-medium hover:bg-[hsl(var(--secondary))]"
                  >
                    Cancelar
                  </button>
                  <button
                    type="submit"
                    disabled={createMutation.isPending}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 flex items-center gap-2"
                  >
                    {createMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                    Salvar
                  </button>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
