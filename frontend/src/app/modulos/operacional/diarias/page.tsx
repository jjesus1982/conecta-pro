'use client';

import { useState, useEffect, useMemo } from 'react';
import { ClipboardList, Loader2, Plus, Trash2, CalendarDays, Users, BarChart3 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

const API = '/api/v1/operacional/diarias';
function authHeaders(json = true) {
  const t = typeof window !== 'undefined' ? (localStorage.getItem('access_token') || localStorage.getItem('token')) : null;
  return { ...(json ? { 'Content-Type': 'application/json' } : {}), ...(t ? { Authorization: `Bearer ${t}` } : {}) };
}
const brl = (v: any) => { const n = Number(v); return isNaN(n) ? '—' : n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }); };

export default function DiariasPage() {
  const hoje = new Date().toISOString().slice(0, 10);
  const [cad, setCad] = useState<any>(null);
  const [data, setData] = useState(hoje);
  const [diarista, setDiarista] = useState('');
  const [funcao, setFuncao] = useState('');
  const [posto, setPosto] = useState('');
  const [turno, setTurno] = useState('DIURNO');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [aba, setAba] = useState<'lancamentos' | 'resumo'>('lancamentos');
  const [lancs, setLancs] = useState<any>(null);
  const [resumo, setResumo] = useState<any>(null);

  const mes = Number(data.slice(5, 7)); const ano = Number(data.slice(0, 4));
  const ehAgente = funcao === 'AGENTE DE PORTARIA';

  const carregar = async () => {
    const c = await fetch(`${API}/cadastros`, { headers: authHeaders() }).then(r => r.json()).catch(() => null);
    setCad(c);
    if (c?.funcoes?.length && !funcao) setFuncao(c.funcoes[0]);
  };
  const carregarMes = async () => {
    const l = await fetch(`${API}/lancamentos?mes=${mes}&ano=${ano}`, { headers: authHeaders() }).then(r => r.json()).catch(() => null);
    setLancs(l);
    const r = await fetch(`${API}/resumo-diarista?mes=${mes}&ano=${ano}`, { headers: authHeaders() }).then(x => x.json()).catch(() => null);
    setResumo(r);
  };
  useEffect(() => { carregar(); }, []);
  useEffect(() => { carregarMes(); }, [mes, ano]);

  // valor automático (client-side, da tabela de preços)
  const valorAuto = useMemo(() => {
    if (!cad?.precos || !funcao) return null;
    const t = ehAgente ? turno : 'ÚNICO';
    const p = cad.precos.find((x: any) => x.funcao === funcao && x.turno === t);
    return p ? p.valor : null;
  }, [cad, funcao, turno, ehAgente]);

  const lancar = async () => {
    if (!diarista || !funcao || !posto) { setMsg('Selecione diarista, função e posto.'); return; }
    setBusy(true); setMsg(null);
    try {
      const r = await fetch(`${API}/lancar`, { method: 'POST', headers: authHeaders(), body: JSON.stringify({ data, diarista_id: Number(diarista), funcao, posto, turno: ehAgente ? turno : null }) }).then(x => x.json());
      if (r?.detail) { setMsg(r.detail); return; }
      setMsg(`Diária lançada: ${brl(r.valor)}.`); carregarMes();
    } finally { setBusy(false); }
  };
  const excluir = async (id: number) => { await fetch(`${API}/lancamentos/${id}`, { method: 'DELETE', headers: authHeaders() }); carregarMes(); };

  const sel = 'border rounded px-2 py-1.5 text-sm bg-white';
  return (
    <div className="p-6 space-y-6 max-w-5xl">
      <div className="flex items-center gap-3">
        <ClipboardList className="h-7 w-7 text-blue-700" />
        <div>
          <h1 className="font-display text-2xl font-bold text-gray-900">Lançamento de Diárias</h1>
          <p className="text-sm text-muted-foreground">Selecione nas listas — o valor sai automático da tabela de preços. O resumo por diarista é o que o Financeiro paga no dia 15.</p>
        </div>
      </div>

      {/* Lançar */}
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base flex items-center gap-2"><Plus className="h-4 w-4 text-blue-600" /> Lançar diária</CardTitle></CardHeader>
        <CardContent>
          {!cad ? <Loader2 className="h-5 w-5 animate-spin" /> : (
            <div className="flex flex-wrap items-end gap-3">
              <div><label className="text-xs text-muted-foreground block">Data</label><input type="date" value={data} onChange={e => setData(e.target.value)} className={sel} /></div>
              <div><label className="text-xs text-muted-foreground block">Diarista</label>
                <select value={diarista} onChange={e => setDiarista(e.target.value)} className={`${sel} w-48`}>
                  <option value="">Selecione…</option>
                  {cad.diaristas.map((d: any) => <option key={d.id} value={d.id}>{d.nome}{d.tem_pix ? '' : ' (sem PIX)'}</option>)}
                </select>
              </div>
              <div><label className="text-xs text-muted-foreground block">Função</label>
                <select value={funcao} onChange={e => setFuncao(e.target.value)} className={`${sel} w-44`}>
                  {cad.funcoes.map((f: string) => <option key={f} value={f}>{f}</option>)}
                </select>
              </div>
              <div><label className="text-xs text-muted-foreground block">Posto</label>
                <select value={posto} onChange={e => setPosto(e.target.value)} className={`${sel} w-44`}>
                  <option value="">Selecione…</option>
                  {cad.postos.map((p: string) => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>
              <div><label className="text-xs text-muted-foreground block">Turno</label>
                <select value={turno} disabled={!ehAgente} onChange={e => setTurno(e.target.value)} className={`${sel} w-36 ${!ehAgente ? 'bg-gray-100 text-gray-400' : ''}`}>
                  {ehAgente ? ['DIURNO', 'NOTURNO', 'MEIO PERÍODO'].map(t => <option key={t} value={t}>{t}</option>) : <option>—</option>}
                </select>
              </div>
              <div className="pb-1"><div className="text-xs text-muted-foreground">Valor</div><div className="text-lg font-bold text-blue-700">{valorAuto != null ? brl(valorAuto) : '—'}</div></div>
              <Button onClick={lancar} disabled={busy} className="bg-blue-600 hover:bg-blue-700 text-white">
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4 mr-1" />} Lançar
              </Button>
            </div>
          )}
          {msg && <div className="text-sm text-gray-600 mt-2">{msg}</div>}
        </CardContent>
      </Card>

      {/* Abas */}
      <div className="flex gap-2">
        <button onClick={() => setAba('lancamentos')} className={`px-3 py-1.5 rounded text-sm ${aba === 'lancamentos' ? 'bg-blue-600 text-white' : 'bg-gray-100'}`}><CalendarDays className="h-4 w-4 inline mr-1" />Lançamentos do mês</button>
        <button onClick={() => setAba('resumo')} className={`px-3 py-1.5 rounded text-sm ${aba === 'resumo' ? 'bg-blue-600 text-white' : 'bg-gray-100'}`}><Users className="h-4 w-4 inline mr-1" />Resumo p/ pagamento (dia 15)</button>
      </div>

      {aba === 'lancamentos' && (
        <Card>
          <CardHeader className="pb-2 flex-row items-center justify-between">
            <CardTitle className="text-base">Lançamentos — {String(mes).padStart(2, '0')}/{ano}</CardTitle>
            <div className="text-sm">{lancs?.total_lancamentos || 0} diárias · <b>{brl(lancs?.total_valor)}</b></div>
          </CardHeader>
          <CardContent>
            {!lancs?.itens?.length ? <p className="text-sm text-gray-400">Nenhuma diária lançada neste mês.</p> : (
              <div className="divide-y text-sm">
                {lancs.itens.map((i: any) => (
                  <div key={i.id} className="py-1.5 flex items-center justify-between gap-2">
                    <div className="flex-1"><span className="text-gray-400">{i.data.slice(8)}/{i.data.slice(5, 7)}</span> <b className="ml-1">{i.diarista}</b> <span className="text-gray-500">· {i.funcao} · {i.posto}{i.turno !== 'ÚNICO' ? ` · ${i.turno}` : ''}</span></div>
                    <span className="font-semibold">{brl(i.valor)}</span>
                    <button onClick={() => excluir(i.id)} className="text-gray-300 hover:text-red-600"><Trash2 className="h-4 w-4" /></button>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {aba === 'resumo' && (
        <Card>
          <CardHeader className="pb-2 flex-row items-center justify-between">
            <CardTitle className="text-base flex items-center gap-2"><Users className="h-4 w-4" /> Resumo por diarista — {String(mes).padStart(2, '0')}/{ano}</CardTitle>
            <div className="text-sm">{resumo?.total_diarias || 0} diárias · <b>{brl(resumo?.total)}</b></div>
          </CardHeader>
          <CardContent>
            {!resumo?.por_pessoa?.length ? <p className="text-sm text-gray-400">Sem diárias no mês.</p> : (
              <>
                <div className="divide-y text-sm">
                  {resumo.por_pessoa.map((p: any, idx: number) => (
                    <div key={idx} className="py-1.5 flex items-center justify-between gap-2">
                      <span className="flex-1 font-medium">{p.diarista}</span>
                      <span className="text-gray-500 text-xs">{p.qtd} diárias</span>
                      {!p.tem_cpf && <Badge className="bg-red-100 text-red-700 text-xs">sem CPF</Badge>}
                      {!p.tem_pix && <Badge className="bg-amber-100 text-amber-700 text-xs">sem PIX</Badge>}
                      <span className="font-semibold w-24 text-right">{brl(p.valor)}</span>
                    </div>
                  ))}
                </div>
                <div className="mt-3 text-xs text-muted-foreground flex items-center gap-1"><BarChart3 className="h-3.5 w-3.5" /> Este resumo é enviado ao Financeiro para pagamento em lote no dia 15. Complete CPF e PIX dos diaristas marcados.</div>
              </>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
