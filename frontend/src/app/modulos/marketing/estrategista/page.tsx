'use client';
import { useMutation } from '@tanstack/react-query';
import { customInstance } from '@/lib/api-client';
import { Target, Sparkles, Loader2, Calendar, Megaphone, TrendingUp, ListChecks } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';

export default function EstrategistaPage() {
  const [objetivo, setObjetivo] = useState('');
  const [periodo, setPeriodo] = useState(30);
  const [orcamento, setOrcamento] = useState('');
  const [canais, setCanais] = useState('');
  const [plano, setPlano] = useState<any>(null);
  const [meta, setMeta] = useState<{ modelo?: string; fallback?: boolean }>({});

  const gerar = useMutation({
    mutationFn: () => customInstance({
      url: '/api/v1/marketing/estrategista/plan',
      method: 'POST',
      data: { objetivo, periodo_dias: periodo, orcamento: orcamento || null, canais_preferidos: canais || null },
    }),
    onSuccess: (data: any) => { setPlano(data.plano); setMeta({ modelo: data.modelo, fallback: data.fallback }); toast.success('Plano gerado — revise e ajuste'); },
    onError: () => toast.error('Erro ao gerar o plano. Tente novamente.'),
  });

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2"><Target className="h-6 w-6" />Estrategista IA</h1>
        <p className="text-gray-500">Descreva o objetivo e a IA monta o plano de campanha + calendário editorial na voz da marca. Você revisa e ajusta.</p>
      </div>

      <div className="bg-white rounded-xl border p-5 space-y-4">
        <div>
          <label className="text-sm font-medium block mb-1">Objetivo <span className="text-red-500">*</span></label>
          <textarea className="w-full border rounded-lg p-2 text-sm h-20" placeholder="Ex: Captar 15 novos condomínios para portaria remota em Manaus"
            value={objetivo} onChange={e => setObjetivo(e.target.value)} />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="text-sm font-medium block mb-1">Período: {periodo} dias</label>
            <input type="range" min={7} max={90} step={7} value={periodo} onChange={e => setPeriodo(Number(e.target.value))} className="w-full" />
          </div>
          <div>
            <label className="text-sm font-medium block mb-1">Orçamento (opcional)</label>
            <input className="w-full border rounded-lg p-2 text-sm" placeholder="Ex: R$ 3.000 em tráfego" value={orcamento} onChange={e => setOrcamento(e.target.value)} />
          </div>
          <div>
            <label className="text-sm font-medium block mb-1">Canais preferidos (opcional)</label>
            <input className="w-full border rounded-lg p-2 text-sm" placeholder="Ex: Instagram e Meta Ads" value={canais} onChange={e => setCanais(e.target.value)} />
          </div>
        </div>
        <button disabled={!objetivo.trim() || gerar.isPending} onClick={() => gerar.mutate()}
          className="bg-cyan-600 hover:bg-cyan-700 disabled:opacity-50 text-white rounded-lg px-4 py-2.5 text-sm font-medium flex items-center gap-2">
          {gerar.isPending ? <><Loader2 className="h-4 w-4 animate-spin" />Montando plano...</> : <><Sparkles className="h-4 w-4" />Gerar plano</>}
        </button>
      </div>

      {plano && (
        <div className="space-y-4">
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <span className="bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full font-medium">RASCUNHO — revise e ajuste</span>
            {meta.modelo && <span>· {meta.fallback ? 'fallback local' : meta.modelo}</span>}
          </div>

          {plano.resumo && (
            <div className="bg-white rounded-xl border p-4">
              <h2 className="font-semibold mb-1">Resumo da estratégia</h2>
              <p className="text-sm text-gray-700">{plano.resumo}</p>
              {plano.proposta_valor && <p className="text-sm text-cyan-700 mt-2 font-medium">{plano.proposta_valor}</p>}
            </div>
          )}

          {Array.isArray(plano.publico_alvo) && plano.publico_alvo.length > 0 && (
            <div className="bg-white rounded-xl border p-4">
              <h2 className="font-semibold mb-2">Público-alvo</h2>
              <ul className="list-disc pl-5 text-sm text-gray-700 space-y-1">
                {plano.publico_alvo.map((p: string, i: number) => <li key={i}>{p}</li>)}
              </ul>
            </div>
          )}

          {Array.isArray(plano.canais) && plano.canais.length > 0 && (
            <div className="bg-white rounded-xl border p-4">
              <h2 className="font-semibold mb-2 flex items-center gap-2"><Megaphone className="h-4 w-4" />Canais e alocação</h2>
              <div className="space-y-2">
                {plano.canais.map((c: any, i: number) => (
                  <div key={i} className="flex items-center gap-3 text-sm">
                    <span className="font-medium w-40 shrink-0">{c.canal}</span>
                    <div className="flex-1 bg-gray-100 rounded-full h-2.5"><div className="bg-cyan-500 h-2.5 rounded-full" style={{ width: `${c.alocacao_pct || 0}%` }} /></div>
                    <span className="w-12 text-right text-gray-600">{c.alocacao_pct || 0}%</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {Array.isArray(plano.calendario) && plano.calendario.length > 0 && (
            <div className="bg-white rounded-xl border p-4">
              <h2 className="font-semibold mb-2 flex items-center gap-2"><Calendar className="h-4 w-4" />Calendário editorial</h2>
              <table className="w-full text-sm">
                <thead className="bg-gray-50"><tr><th className="text-left p-2">Dia</th><th className="text-left p-2">Canal</th><th className="text-left p-2">Formato</th><th className="text-left p-2">Tema</th><th className="text-left p-2">CTA</th></tr></thead>
                <tbody>
                  {plano.calendario.map((it: any, i: number) => (
                    <tr key={i} className="border-t">
                      <td className="p-2 font-medium">{it.dia}</td>
                      <td className="p-2">{it.canal}</td>
                      <td className="p-2">{it.formato}</td>
                      <td className="p-2">{it.tema}</td>
                      <td className="p-2 text-gray-500">{it.cta}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {Array.isArray(plano.kpis) && plano.kpis.length > 0 && (
              <div className="bg-white rounded-xl border p-4">
                <h2 className="font-semibold mb-2 flex items-center gap-2"><TrendingUp className="h-4 w-4" />KPIs</h2>
                <ul className="list-disc pl-5 text-sm text-gray-700 space-y-1">{plano.kpis.map((k: string, i: number) => <li key={i}>{k}</li>)}</ul>
              </div>
            )}
            {Array.isArray(plano.proximos_passos) && plano.proximos_passos.length > 0 && (
              <div className="bg-white rounded-xl border p-4">
                <h2 className="font-semibold mb-2 flex items-center gap-2"><ListChecks className="h-4 w-4" />Próximos passos</h2>
                <ul className="list-disc pl-5 text-sm text-gray-700 space-y-1">{plano.proximos_passos.map((s: string, i: number) => <li key={i}>{s}</li>)}</ul>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
