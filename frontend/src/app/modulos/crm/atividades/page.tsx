'use client';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { customInstance } from '@/lib/api-client';
import { ListChecks, Clock, Plus, Check, Trash2, CalendarClock, Loader2, Activity } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';

const TIPO_LABEL: Record<string, string> = {
  lead_created: 'Lead criado', lead_status: 'Status do lead', proposal_created: 'Proposta criada',
  proposal_accepted: 'Proposta aceita', deal_stage: 'Deal movido', contract_created: 'Contrato gerado', note: 'Nota',
};
const PRIO_COR: Record<string, string> = { high: 'bg-red-100 text-red-700', medium: 'bg-amber-100 text-amber-700', low: 'bg-gray-100 text-gray-600' };

export default function AtividadesPage() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<'tarefas' | 'timeline'>('tarefas');
  const [statusFiltro, setStatusFiltro] = useState('pending');
  const [novaTarefa, setNovaTarefa] = useState({ title: '', due_date: '', priority: 'medium' });

  const { data: tarefasData, isLoading: loadingTar } = useQuery({
    queryKey: ['crm-tasks', statusFiltro],
    queryFn: () => customInstance({ url: `/api/v1/crm/tasks/?status=${statusFiltro}`, method: 'GET' }),
    staleTime: 15_000,
  });
  const tarefas = (tarefasData as any)?.items || [];

  const { data: timelineData } = useQuery({
    queryKey: ['crm-timeline'],
    queryFn: () => customInstance({ url: '/api/v1/crm/activities/timeline?limit=100', method: 'GET' }),
    enabled: tab === 'timeline',
    staleTime: 15_000,
  });
  const atividades = (timelineData as any)?.items || [];

  const criar = useMutation({
    mutationFn: () => customInstance({ url: '/api/v1/crm/tasks/', method: 'POST', data: { ...novaTarefa, due_date: novaTarefa.due_date || null } }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['crm-tasks'] }); setNovaTarefa({ title: '', due_date: '', priority: 'medium' }); toast.success('Tarefa criada'); },
    onError: () => toast.error('Erro ao criar tarefa'),
  });
  const concluir = useMutation({
    mutationFn: (id: string) => customInstance({ url: `/api/v1/crm/tasks/${id}`, method: 'PATCH', data: { status: 'done' } }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['crm-tasks'] }); toast.success('Concluída'); },
  });
  const excluir = useMutation({
    mutationFn: (id: string) => customInstance({ url: `/api/v1/crm/tasks/${id}`, method: 'DELETE' }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['crm-tasks'] }); toast.success('Excluída'); },
  });

  const hoje = new Date().toISOString().slice(0, 10);
  const fmtData = (d?: string) => d ? new Date(d + 'T00:00:00').toLocaleDateString('pt-BR') : '—';
  const fmtDataHora = (d?: string) => d ? new Date(d).toLocaleString('pt-BR') : '—';

  return (
    <div className="p-6 space-y-6 max-w-4xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2"><Activity className="h-6 w-6" />Atividades & Tarefas</h1>
        <p className="text-gray-500">Lembretes de follow-up e a linha do tempo do CRM</p>
      </div>

      <div className="flex gap-2 border-b">
        <button onClick={() => setTab('tarefas')} className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px flex items-center gap-1.5 ${tab === 'tarefas' ? 'border-cyan-600 text-cyan-700' : 'border-transparent text-gray-500'}`}><ListChecks className="h-4 w-4" />Tarefas</button>
        <button onClick={() => setTab('timeline')} className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px flex items-center gap-1.5 ${tab === 'timeline' ? 'border-cyan-600 text-cyan-700' : 'border-transparent text-gray-500'}`}><Clock className="h-4 w-4" />Timeline</button>
      </div>

      {tab === 'tarefas' && (
        <div className="space-y-4">
          {/* Nova tarefa */}
          <div className="bg-white rounded-xl border p-4 flex flex-col md:flex-row gap-2 items-stretch md:items-end">
            <div className="flex-1"><label className="text-xs text-gray-500">Tarefa</label>
              <input className="w-full border rounded-lg p-2 text-sm" placeholder="Ex: Ligar para o síndico do Laranjeiras" value={novaTarefa.title} onChange={e => setNovaTarefa({ ...novaTarefa, title: e.target.value })} /></div>
            <div><label className="text-xs text-gray-500">Vencimento</label>
              <input type="date" className="w-full border rounded-lg p-2 text-sm" value={novaTarefa.due_date} onChange={e => setNovaTarefa({ ...novaTarefa, due_date: e.target.value })} /></div>
            <div><label className="text-xs text-gray-500">Prioridade</label>
              <select className="w-full border rounded-lg p-2 text-sm" value={novaTarefa.priority} onChange={e => setNovaTarefa({ ...novaTarefa, priority: e.target.value })}>
                <option value="high">Alta</option><option value="medium">Média</option><option value="low">Baixa</option></select></div>
            <button disabled={!novaTarefa.title.trim() || criar.isPending} onClick={() => criar.mutate()} className="bg-cyan-600 hover:bg-cyan-700 disabled:opacity-50 text-white rounded-lg px-4 py-2 text-sm font-medium flex items-center gap-1 justify-center">
              {criar.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}Adicionar</button>
          </div>

          {/* Filtro */}
          <div className="flex gap-2 text-sm">
            {([['pending', 'Pendentes'], ['done', 'Concluídas']] as [string, string][]).map(([v, l]) => (
              <button key={v} onClick={() => setStatusFiltro(v)} className={`px-3 py-1 rounded-full ${statusFiltro === v ? 'bg-cyan-100 text-cyan-700' : 'bg-gray-100 text-gray-600'}`}>{l}</button>
            ))}
          </div>

          {loadingTar ? <p className="text-sm text-gray-400">Carregando...</p> : tarefas.length === 0 ? (
            <div className="bg-gray-50 rounded-xl border border-dashed p-10 text-center text-gray-400 text-sm">Nenhuma tarefa {statusFiltro === 'pending' ? 'pendente' : 'concluída'}.</div>
          ) : (
            <div className="space-y-2">
              {tarefas.map((t: any) => {
                const atrasada = statusFiltro === 'pending' && t.due_date && t.due_date < hoje;
                return (
                  <div key={t.id} className={`bg-white rounded-xl border p-3 flex items-center gap-3 ${atrasada ? 'border-red-300' : ''}`}>
                    {statusFiltro === 'pending' && <button onClick={() => concluir.mutate(t.id)} title="Concluir" className="h-6 w-6 rounded-full border-2 border-cyan-500 hover:bg-cyan-500 hover:text-white flex items-center justify-center text-cyan-500"><Check className="h-3.5 w-3.5" /></button>}
                    <div className="flex-1">
                      <p className={`text-sm font-medium ${t.status === 'done' ? 'line-through text-gray-400' : ''}`}>{t.title}</p>
                      <div className="flex items-center gap-2 text-xs text-gray-500 mt-0.5">
                        <span className={`px-1.5 rounded ${PRIO_COR[t.priority] || ''}`}>{t.priority === 'high' ? 'Alta' : t.priority === 'low' ? 'Baixa' : 'Média'}</span>
                        {t.due_date && <span className={`flex items-center gap-1 ${atrasada ? 'text-red-600 font-medium' : ''}`}><CalendarClock className="h-3 w-3" />{fmtData(t.due_date)}{atrasada ? ' (atrasada)' : ''}</span>}
                      </div>
                    </div>
                    <button onClick={() => { if (confirm('Excluir tarefa?')) excluir.mutate(t.id); }} className="text-gray-400 hover:text-red-600"><Trash2 className="h-4 w-4" /></button>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {tab === 'timeline' && (
        <div className="space-y-1">
          {atividades.length === 0 ? (
            <div className="bg-gray-50 rounded-xl border border-dashed p-10 text-center text-gray-400 text-sm">Sem atividades ainda. Conforme o CRM roda (leads, propostas, deals), a timeline preenche sozinha.</div>
          ) : (
            <div className="relative border-l-2 border-gray-200 ml-3 space-y-4 py-2">
              {atividades.map((a: any) => (
                <div key={a.id} className="relative pl-6">
                  <span className="absolute -left-[7px] top-1.5 h-3 w-3 rounded-full bg-cyan-500 border-2 border-white" />
                  <p className="text-sm font-medium">{a.subject}</p>
                  <p className="text-xs text-gray-500">{TIPO_LABEL[a.type] || a.type} · {fmtDataHora(a.created_at)}{a.client_name ? ` · ${a.client_name}` : ''}</p>
                  {a.description && <p className="text-xs text-gray-600 mt-0.5">{a.description}</p>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
