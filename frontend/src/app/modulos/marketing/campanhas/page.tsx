'use client';
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { customInstance } from '@/lib/api-client';
import { Plus, Megaphone, Users, TrendingUp } from 'lucide-react';
import { toast } from 'sonner';
import { PageHeader } from '@/components/ui/page-header';
import { StatCard } from '@/components/ui/stat-card';

export default function CampanhasPage() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: '', type: 'organic', budget: 0, description: '' });

  const { data, isLoading } = useQuery({
    queryKey: ['marketing-campaigns'],
    queryFn: () => customInstance({ url: '/api/v1/marketing/campaigns/', method: 'GET' }),
    staleTime: 30_000,
  });

  const createMutation = useMutation({
    mutationFn: (data: any) => customInstance({ url: '/api/v1/marketing/campaigns/', method: 'POST', data }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['marketing-campaigns'] }); toast.success('Campanha criada'); setShowForm(false); },
  });

  const activateMutation = useMutation({
    mutationFn: (id: string) => customInstance({ url: `/api/v1/marketing/campaigns/${id}`, method: 'PUT', data: { status: 'active' } }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['marketing-campaigns'] }); toast.success('Campanha ativada'); },
    onError: () => { toast.error('Erro ao ativar campanha'); },
  });

  const campaigns = (data as any)?.items || [];

  return (
    <div className="p-6 space-y-6">
      <PageHeader
        eyebrow="MARKETING"
        title="Campanhas de Marketing"
        subtitle="Gerencie campanhas de aquisição de clientes"
        icon={<Megaphone className="h-5 w-5" />}
        actions={
          <button onClick={() => setShowForm(!showForm)} className="flex items-center gap-2 bg-cyan-600 text-white px-4 py-2 rounded-lg hover:bg-cyan-700">
            <Plus className="h-4 w-4" /> Nova Campanha
          </button>
        }
      />

      {showForm && (
        <div className="bg-white border rounded-xl p-4 space-y-3">
          <input placeholder="Nome da campanha" value={form.name} onChange={e => setForm({...form, name: e.target.value})} className="w-full border rounded px-3 py-2" />
          <div className="flex gap-3">
            <select value={form.type} onChange={e => setForm({...form, type: e.target.value})} className="border rounded px-3 py-2">
              <option value="organic">Orgânico</option>
              <option value="meta_ads">Meta Ads</option>
              <option value="google_ads">Google Ads</option>
              <option value="whatsapp">WhatsApp</option>
              <option value="email">Email</option>
              <option value="indicacao">Indicação</option>
            </select>
            <input type="number" placeholder="Budget R$" value={form.budget} onChange={e => setForm({...form, budget: Number(e.target.value)})} className="border rounded px-3 py-2 w-40" />
          </div>
          <textarea placeholder="Descrição" value={form.description} onChange={e => setForm({...form, description: e.target.value})} className="w-full border rounded px-3 py-2 h-20" />
          <button onClick={() => createMutation.mutate(form)} disabled={!form.name} className="bg-cyan-600 text-white px-4 py-2 rounded-lg disabled:opacity-50">Criar Campanha</button>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <StatCard label="Campanhas" value={campaigns.length} icon={<Megaphone className="h-4 w-4" />} color="#0891b2" />
        <StatCard label="Total Leads" value={campaigns.reduce((s: number, c: any) => s + (c.total_leads || 0), 0)} icon={<Users className="h-4 w-4" />} color="#3b82f6" />
        <StatCard label="Convertidos" value={<span className="text-green-600">{campaigns.reduce((s: number, c: any) => s + (c.converted || 0), 0)}</span>} icon={<TrendingUp className="h-4 w-4" />} color="#16a34a" />
      </div>

      {isLoading ? <p className="text-gray-400">Carregando...</p> : campaigns.length === 0 ? (
        <div className="bg-white rounded-xl border p-8 text-center text-gray-400">Nenhuma campanha criada ainda. Clique em "Nova Campanha" para começar.</div>
      ) : (
        <div className="bg-white rounded-xl border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50"><tr><th className="text-left p-3">Campanha</th><th className="text-left p-3">Tipo</th><th className="text-right p-3">Budget</th><th className="text-right p-3">Leads</th><th className="text-right p-3">Conversao</th><th className="text-left p-3">Status</th><th className="text-left p-3">Ações</th></tr></thead>
            <tbody>
              {campaigns.map((c: any) => (
                <tr key={c.id} className="border-t hover:bg-gray-50">
                  <td className="p-3 font-medium">{c.name}</td>
                  <td className="p-3"><span className="bg-gray-100 px-2 py-0.5 rounded text-xs">{c.type}</span></td>
                  <td className="p-3 text-right">R$ {c.budget?.toLocaleString('pt-BR')}</td>
                  <td className="p-3 text-right">{c.total_leads}</td>
                  <td className="p-3 text-right font-medium text-green-600">{c.roi}%</td>
                  <td className="p-3"><span className={`px-2 py-0.5 rounded text-xs ${c.status === 'active' ? 'bg-green-100 text-green-700' : 'bg-gray-100'}`}>{c.status}</span></td>
                  <td className="p-3">
                    {c.status !== 'active' && (
                      <button
                        onClick={() => activateMutation.mutate(c.id)}
                        disabled={activateMutation.isPending}
                        className="text-xs bg-green-600 text-white px-3 py-1.5 rounded-lg hover:bg-green-700 disabled:opacity-50"
                      >
                        Ativar
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
