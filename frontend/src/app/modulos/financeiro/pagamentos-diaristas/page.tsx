'use client';

import { useState, useEffect } from 'react';
import { Users, Loader2, CalendarDays, Send, AlertTriangle, CheckCircle2, RefreshCw, UserPlus } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

const API = '/api/v1/financial/pagamentos-diaristas';

function authHeaders(json = true) {
  const t = typeof window !== 'undefined' ? (localStorage.getItem('access_token') || localStorage.getItem('token')) : null;
  return { ...(json ? { 'Content-Type': 'application/json' } : {}), ...(t ? { Authorization: `Bearer ${t}` } : {}) };
}
const brl = (v: any) => { const n = Number(v); return isNaN(n) ? '—' : n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }); };

export default function PagamentosDiaristasPage() {
  const hoje = new Date().toISOString().slice(0, 10);
  const [data, setData] = useState(hoje);
  const [lote, setLote] = useState<any[]>([]);
  const [totalPagar, setTotalPagar] = useState(0);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [preview, setPreview] = useState<any>(null);
  const [pagando, setPagando] = useState(false);
  const [resultado, setResultado] = useState<any>(null);
  const [sugestoes, setSugestoes] = useState<any[]>([]);
  const [showSug, setShowSug] = useState(false);

  const carregarLote = async (d = data) => {
    try {
      const r = await fetch(`${API}/lote?data=${d}`, { headers: authHeaders() }).then(x => x.json());
      setLote(r?.itens || []); setTotalPagar(r?.total_a_pagar || 0);
    } catch { /* */ }
  };
  const carregarSugestoes = async () => {
    try {
      const r = await fetch(`${API}/sugestoes-cadastro?dias=30`, { headers: authHeaders() }).then(x => x.json());
      setSugestoes((r?.sugestoes || []).filter((s: any) => !s.ja_cadastrado));
    } catch { /* */ }
  };
  useEffect(() => { carregarLote(); carregarSugestoes(); }, []);

  const programar = async () => {
    setBusy(true); setMsg(null); setResultado(null);
    try {
      const r = await fetch(`${API}/programar/${data}`, { method: 'POST', headers: authHeaders() }).then(x => x.json());
      if (r?.detail) { setMsg(r.detail); return; }
      setMsg(`Escala de ${r.escalados} diarista(s) → ${r.programados_novos} novo(s) programado(s)${r.sem_pix ? `, ${r.sem_pix} sem PIX` : ''}.`);
      carregarLote();
    } catch { setMsg('Falha ao programar.'); } finally { setBusy(false); }
  };

  const abrirPreview = async () => {
    setPagando(true); setResultado(null);
    try {
      const r = await fetch(`${API}/executar`, { method: 'POST', headers: authHeaders(), body: JSON.stringify({ data, confirmar: false }) }).then(x => x.json());
      setPreview(r);
    } catch { setMsg('Falha na prévia.'); } finally { setPagando(false); }
  };
  const confirmarPagamento = async () => {
    setPagando(true);
    try {
      const r = await fetch(`${API}/executar`, { method: 'POST', headers: authHeaders(), body: JSON.stringify({ data, confirmar: true }) }).then(x => x.json());
      setResultado(r); setPreview(null); carregarLote();
    } catch { setMsg('Falha ao pagar.'); } finally { setPagando(false); }
  };

  const [mBen, setMBen] = useState(''); const [mPix, setMPix] = useState(''); const [mQtd, setMQtd] = useState(1);
  const adicionarManual = async () => {
    if (!mBen.trim() || !mPix.trim()) { setMsg('Informe beneficiário e chave PIX.'); return; }
    setBusy(true);
    try {
      await fetch(`${API}/manual`, { method: 'POST', headers: authHeaders(), body: JSON.stringify({ data, beneficiario: mBen, pix_key: mPix, quantidade: mQtd, tipo: 'cobertura_clt' }) });
      setMBen(''); setMPix(''); setMQtd(1); carregarLote();
    } finally { setBusy(false); }
  };

  const badge = (s: string) => {
    const map: any = { a_revisar: 'bg-blue-100 text-blue-700', sem_pix: 'bg-red-100 text-red-700', pago: 'bg-green-100 text-green-700', cancelado: 'bg-gray-100 text-gray-500' };
    return <span className={`text-xs px-2 py-0.5 rounded ${map[s] || 'bg-gray-100'}`}>{s.replace('_', ' ')}</span>;
  };

  return (
    <div className="p-6 space-y-6 max-w-5xl">
      <div className="flex items-center gap-3">
        <Users className="h-7 w-7 text-emerald-700" />
        <div>
          <h1 className="font-display text-2xl font-semibold text-gray-900">Pagamentos de Diaristas (VT+VR)</h1>
          <p className="text-sm text-muted-foreground">A escala do Operacional vira lote a pagar aqui. Revise e pague em lote via PIX (Banco Inter). R$10 VT + R$22 VR = R$32/dia.</p>
        </div>
      </div>

      {/* Programar */}
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base flex items-center gap-2"><CalendarDays className="h-4 w-4 text-emerald-600" /> Programar do dia (a partir da escala)</CardTitle></CardHeader>
        <CardContent className="flex flex-wrap items-center gap-3">
          <input type="date" value={data} onChange={e => { setData(e.target.value); carregarLote(e.target.value); }} className="border rounded px-3 py-2 text-sm" />
          <Button onClick={programar} disabled={busy} className="bg-emerald-600 hover:bg-emerald-700 text-white">
            {busy ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <RefreshCw className="h-4 w-4 mr-1" />} Programar VT+VR da escala
          </Button>
          {msg && <span className="text-sm text-gray-600">{msg}</span>}
        </CardContent>
      </Card>

      {/* Adicionar manual (cobertura CLT ou líder com ajudantes) */}
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base flex items-center gap-2"><UserPlus className="h-4 w-4 text-emerald-600" /> Adicionar pagamento (cobertura CLT ou líder com ajudantes)</CardTitle></CardHeader>
        <CardContent className="flex flex-wrap items-end gap-2">
          <div><label className="text-xs text-muted-foreground">Beneficiário</label><input value={mBen} onChange={e => setMBen(e.target.value)} placeholder="Ex.: Francisco Edinei" className="block border rounded px-2 py-1.5 text-sm w-52" /></div>
          <div><label className="text-xs text-muted-foreground">Chave PIX</label><input value={mPix} onChange={e => setMPix(e.target.value)} placeholder="CPF / chave" className="block border rounded px-2 py-1.5 text-sm w-40" /></div>
          <div><label className="text-xs text-muted-foreground">Qtd pessoas</label><input type="number" min={1} value={mQtd} onChange={e => setMQtd(Math.max(1, Number(e.target.value)))} className="block border rounded px-2 py-1.5 text-sm w-20" /></div>
          <div className="text-sm text-gray-600 pb-1.5">= <b>{brl(32 * mQtd)}</b></div>
          <Button onClick={adicionarManual} disabled={busy} variant="outline">Adicionar ao lote</Button>
          <p className="w-full text-xs text-muted-foreground">Ex.: um líder que leva 2 ajudantes recebe o VT+VR dos dois num PIX só → quantidade 2 = R$64.</p>
        </CardContent>
      </Card>

      {/* Lote */}
      <Card>
        <CardHeader className="pb-2 flex-row items-center justify-between">
          <CardTitle className="text-base">Lote a pagar — {data}</CardTitle>
          <div className="text-sm">Total: <b>{brl(totalPagar)}</b> · {lote.filter(i => i.status === 'a_revisar').length} a revisar</div>
        </CardHeader>
        <CardContent>
          {lote.length === 0 ? <p className="text-sm text-gray-400">Nenhum pagamento programado para esta data. Use "Programar VT+VR da escala".</p> : (
            <div className="divide-y">
              {lote.map(i => (
                <div key={i.id} className="py-2 flex items-center justify-between gap-2 text-sm">
                  <div className="flex-1">
                    <span className="font-medium">{i.beneficiario}</span>
                    <span className="text-xs text-gray-400 ml-2">{i.pix_key ? `PIX: ${i.pix_key}` : 'sem chave PIX'}</span>
                    {i.tipo === 'cobertura_clt' && <Badge variant="outline" className="ml-2 text-xs">cobertura CLT</Badge>}
                  </div>
                  <span className="font-semibold">{brl(i.valor)}</span>
                  {badge(i.status)}
                </div>
              ))}
            </div>
          )}
          {lote.some(i => i.status === 'a_revisar') && (
            <div className="mt-4 flex items-center justify-end gap-2">
              <Button onClick={abrirPreview} disabled={pagando} className="bg-emerald-600 hover:bg-emerald-700 text-white">
                {pagando ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Send className="h-4 w-4 mr-1" />} Pagar em lote (PIX)
              </Button>
            </div>
          )}
          {resultado && (
            <div className="mt-3 rounded border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-800 flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4" /> {resultado.pagos} pago(s) — {brl(resultado.total_pago)}{resultado.falhas ? ` · ${resultado.falhas} falha(s)` : ''}.
            </div>
          )}
        </CardContent>
      </Card>

      {/* Sugestões de cadastro */}
      {sugestoes.length > 0 && (
        <Card className="border-amber-200">
          <CardHeader className="pb-2 flex-row items-center justify-between">
            <CardTitle className="text-base flex items-center gap-2"><UserPlus className="h-4 w-4 text-amber-600" /> Diaristas a cadastrar (do histórico de pagamentos)</CardTitle>
            <button onClick={() => setShowSug(s => !s)} className="text-xs text-amber-700">{showSug ? 'ocultar' : `ver ${sugestoes.length}`}</button>
          </CardHeader>
          {showSug && (
            <CardContent>
              <p className="text-xs text-muted-foreground mb-2">Pessoas que você já pagou R$32 (VT+VR) nos últimos 30 dias e ainda não estão cadastradas. Cadastre cada uma no Operacional com <b>CPF (obrigatório)</b> e chave PIX.</p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-1.5">
                {sugestoes.map((s, i) => (
                  <div key={i} className="flex items-center justify-between text-sm border rounded px-2 py-1">
                    <span>{s.nome}</span>
                    <Badge variant="outline" className="text-xs">{s.pagamentos_periodo}x pagos</Badge>
                  </div>
                ))}
              </div>
            </CardContent>
          )}
        </Card>
      )}

      {/* Modal de confirmação do pagamento */}
      {preview && (
        <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onClick={() => setPreview(null)}>
          <div className="bg-white rounded-lg shadow-xl max-w-md w-full p-5" onClick={e => e.stopPropagation()}>
            <div className="flex items-center gap-2 text-amber-700 font-semibold mb-2"><AlertTriangle className="h-5 w-5" /> Confirmar pagamento em lote</div>
            <p className="text-sm text-gray-700">Você vai enviar <b>{preview.itens} PIX</b> totalizando <b>{brl(preview.total)}</b> pela conta Inter. Esta ação é <b>irreversível</b>.</p>
            {!preview.dentro_do_limite && <p className="text-sm text-red-600 mt-1 flex items-center gap-1"><AlertTriangle className="w-3.5 h-3.5" /> Excede o limite de {brl(preview.limite)}/lote.</p>}
            <div className="mt-3 max-h-40 overflow-auto text-xs text-gray-600 border rounded p-2">
              {(preview.beneficiarios || []).map((b: any, i: number) => <div key={i} className="flex justify-between"><span>{b.nome}</span><span>{brl(b.valor)}</span></div>)}
            </div>
            <div className="mt-4 flex items-center justify-end gap-2">
              <Button variant="outline" onClick={() => setPreview(null)}>Cancelar</Button>
              <Button onClick={confirmarPagamento} disabled={pagando || !preview.dentro_do_limite || !preview.itens} className="bg-emerald-600 hover:bg-emerald-700 text-white">
                {pagando ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Send className="h-4 w-4 mr-1" />} Confirmar e pagar {brl(preview.total)}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
