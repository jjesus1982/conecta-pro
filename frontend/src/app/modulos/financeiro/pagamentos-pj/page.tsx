'use client';

import { useState, useEffect, useCallback } from 'react';
import { Briefcase, Loader2, Send, AlertTriangle, CheckCircle2, Building2, Landmark, Clock } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

const API = '/api/v1/financial/pagamentos-pj';

function authHeaders(json = true) {
  const t = typeof window !== 'undefined' ? (localStorage.getItem('access_token') || localStorage.getItem('token')) : null;
  return { ...(json ? { 'Content-Type': 'application/json' } : {}), ...(t ? { Authorization: `Bearer ${t}` } : {}) };
}
const brl = (v: any) => { const n = Number(v); return isNaN(n) ? '—' : n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }); };
const MESES = ['', 'Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];

export default function PagamentosPJPage() {
  const agora = new Date();
  const [mes, setMes] = useState(agora.getMonth() + 1);
  const [ano, setAno] = useState(agora.getFullYear());
  const [lote, setLote] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  // fluxo OTP (Inter)
  const [otpLote, setOtpLote] = useState<string | null>(null);
  const [otpCode, setOtpCode] = useState('');
  const [otpMsg, setOtpMsg] = useState<string | null>(null);
  const [otpBusy, setOtpBusy] = useState(false);
  const [pagando, setPagando] = useState(false);
  const [resultado, setResultado] = useState<any>(null);

  const carregarLote = useCallback(async () => {
    setBusy(true); setMsg(null);
    try {
      const r = await fetch(`${API}/lote/${ano}/${mes}`, { headers: authHeaders(false) }).then(x => x.json());
      setLote(r);
    } catch { setMsg('Falha ao carregar o lote.'); }
    finally { setBusy(false); }
  }, [ano, mes]);

  useEffect(() => { carregarLote(); }, [carregarLote]);

  const programar = async () => {
    setBusy(true); setMsg(null); setOtpLote(null); setResultado(null);
    try {
      const r = await fetch(`${API}/programar/${ano}/${mes}`, { method: 'POST', headers: authHeaders() }).then(x => x.json());
      setMsg(r?.ok ? `Folha programada: ${r.programados} novos, ${r.atualizados} atualizados — total ${brl(r.total)}` : (r?.detail || 'Falha ao programar.'));
      await carregarLote();
    } catch { setMsg('Falha ao programar a folha.'); }
    finally { setBusy(false); }
  };

  const solicitarOtp = async () => {
    setOtpBusy(true); setOtpMsg(null);
    try {
      const r = await fetch(`${API}/solicitar-otp/${ano}/${mes}`, { method: 'POST', headers: authHeaders() }).then(x => x.json());
      if (r?.ok && r?.lote_id) { setOtpLote(r.lote_id); setOtpMsg(`Código enviado ao seu e-mail (${r.quantidade} pagamento(s), ${brl(r.total)}). Válido por ${Math.round((r.expires_in_seconds || 600) / 60)} min.`); }
      else setOtpMsg(r?.mensagem || 'Não foi possível gerar o código.');
    } catch { setOtpMsg('Falha ao gerar o código.'); }
    finally { setOtpBusy(false); }
  };

  const pagarInter = async () => {
    if (!otpLote || otpCode.trim().length < 6) { setOtpMsg('Informe o código de 6 dígitos do e-mail.'); return; }
    setPagando(true); setOtpMsg(null);
    try {
      const r = await fetch(`${API}/executar/${ano}/${mes}`, { method: 'POST', headers: authHeaders(), body: JSON.stringify({ confirmar: true, otp_code: otpCode.trim(), lote_id: otpLote }) }).then(x => x.json());
      if (r?.otp_invalido || r?.otp_requerido) { setOtpMsg(r?.mensagem || 'Código inválido. Gere um novo.'); return; }
      setResultado(r); setOtpLote(null); setOtpCode('');
      await carregarLote();
    } catch { setOtpMsg('Falha ao executar o pagamento.'); }
    finally { setPagando(false); }
  };

  const inter = (lote?.inter_pagaveis || []) as any[];
  const cora = (lote?.cora_lista_app || []) as any[];
  const pend = (lote?.pendencias || []) as any[];
  const totalInter = inter.reduce((s, i) => s + Number(i.valor || 0), 0);
  const totalCora = cora.reduce((s, i) => s + Number(i.valor || 0), 0);

  return (
    <div className="max-w-5xl mx-auto p-4 space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h1 className="text-xl font-bold flex items-center gap-2"><Briefcase className="h-5 w-5" /> Folha de Pagamento PJ</h1>
        <div className="flex items-center gap-2">
          <select value={mes} onChange={e => setMes(Number(e.target.value))} className="border rounded px-2 py-1 text-sm">
            {MESES.slice(1).map((m, i) => <option key={i + 1} value={i + 1}>{m}</option>)}
          </select>
          <input type="number" value={ano} onChange={e => setAno(Number(e.target.value))} className="border rounded px-2 py-1 text-sm w-20" />
          <Button onClick={programar} disabled={busy} variant="outline">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Programar folha'}</Button>
        </div>
      </div>

      {msg && <div className="text-sm bg-blue-50 border border-blue-200 text-blue-800 rounded p-2">{msg}</div>}

      {/* Resumo */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <Card><CardContent className="p-3"><div className="text-xs text-gray-500">Total da folha</div><div className="text-lg font-bold">{brl(lote?.total)}</div></CardContent></Card>
        <Card><CardContent className="p-3"><div className="text-xs text-gray-500 flex items-center gap-1"><Landmark className="h-3 w-3" /> Inter (Eletrônica)</div><div className="text-lg font-bold text-emerald-700">{brl(totalInter)}</div></CardContent></Card>
        <Card><CardContent className="p-3"><div className="text-xs text-gray-500 flex items-center gap-1"><Building2 className="h-3 w-3" /> Cora (Patrimonial)</div><div className="text-lg font-bold text-indigo-700">{brl(totalCora)}</div></CardContent></Card>
      </div>

      {/* INTER — automático com OTP */}
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base flex items-center gap-2"><Landmark className="h-4 w-4 text-emerald-700" /> Inter — Conecta Mais Eletrônica <Badge variant="outline">automático</Badge></CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {inter.length === 0 ? <p className="text-sm text-gray-500">Nenhum pagamento Inter pronto (precisa de PIX e, de agosto em diante, nota fiscal).</p> : (
            <table className="w-full text-sm">
              <thead><tr className="text-left text-gray-500 border-b"><th className="py-1">Prestador</th><th>PIX</th><th className="text-right">Salário</th><th className="text-right">VA/VT</th><th className="text-right">Total</th></tr></thead>
              <tbody>
                {inter.map((i: any) => (
                  <tr key={i.id} className="border-b last:border-0">
                    <td className="py-1">{i.beneficiario}</td>
                    <td className="text-gray-500 text-xs">{i.pix_key}</td>
                    <td className="text-right">{brl(i.salario)}</td>
                    <td className="text-right text-gray-500">{brl(i.va_vt)}</td>
                    <td className="text-right font-semibold">{brl(i.valor)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {inter.length > 0 && (
            <div className="bg-amber-50 border border-amber-200 rounded p-3 space-y-2">
              <div className="flex items-center gap-2 text-sm text-amber-900"><AlertTriangle className="h-4 w-4" /> Pagamento via PIX (Inter) — <b>{brl(totalInter)}</b>. Confirme com o código enviado ao seu e-mail.</div>
              {!otpLote ? (
                <Button onClick={solicitarOtp} disabled={otpBusy} variant="outline" size="sm">{otpBusy ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : null} Solicitar código (OTP)</Button>
              ) : (
                <div className="flex items-center gap-2 flex-wrap">
                  <input value={otpCode} onChange={e => setOtpCode(e.target.value.replace(/\D/g, '').slice(0, 6))} placeholder="000000" inputMode="numeric" className="border rounded px-3 py-1 w-28 tracking-widest text-center" />
                  <Button onClick={pagarInter} disabled={pagando || otpCode.length < 6} className="bg-emerald-600 hover:bg-emerald-700 text-white" size="sm">{pagando ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Send className="h-4 w-4 mr-1" />} Pagar {brl(totalInter)}</Button>
                  <button onClick={solicitarOtp} disabled={otpBusy} className="text-xs text-amber-700 underline">reenviar código</button>
                </div>
              )}
              {otpMsg && <p className="text-xs text-amber-800">{otpMsg}</p>}
            </div>
          )}
          {resultado?.ok && (
            <div className="bg-emerald-50 border border-emerald-200 rounded p-3 text-sm text-emerald-900">
              <div className="flex items-center gap-2 font-semibold"><CheckCircle2 className="h-4 w-4" /> Pago via Inter: {brl(resultado.total_pago)} ({resultado.pagos?.length || 0} pagamento(s))</div>
              {resultado.falhas?.length > 0 && <div className="text-red-700 mt-1">Falhas: {resultado.falhas.map((f: any) => f.nome).join(', ')}</div>}
            </div>
          )}
        </CardContent>
      </Card>

      {/* CORA — lista para pagar no app */}
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base flex items-center gap-2"><Building2 className="h-4 w-4 text-indigo-700" /> Cora — Conecta Mais Patrimonial <Badge variant="outline">pagar no app</Badge></CardTitle></CardHeader>
        <CardContent>
          <p className="text-xs text-gray-500 mb-2">O Cora não paga por chave PIX via API — pague estes no <b>app do Cora</b>. A conciliação entra automática pelo extrato.</p>
          {cora.length === 0 ? <p className="text-sm text-gray-500">Nenhum pagamento Cora pronto.</p> : (
            <table className="w-full text-sm">
              <thead><tr className="text-left text-gray-500 border-b"><th className="py-1">Prestador</th><th>Chave PIX</th><th className="text-right">Total</th></tr></thead>
              <tbody>
                {cora.map((i: any) => (
                  <tr key={i.id} className="border-b last:border-0">
                    <td className="py-1">{i.beneficiario}</td>
                    <td><span className="font-mono text-xs bg-gray-100 px-1.5 py-0.5 rounded select-all">{i.pix_key}</span></td>
                    <td className="text-right font-semibold">{brl(i.valor)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      {/* Pendências */}
      {pend.length > 0 && (
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-base flex items-center gap-2"><Clock className="h-4 w-4 text-gray-500" /> Pendências ({pend.length})</CardTitle></CardHeader>
          <CardContent>
            <table className="w-full text-sm">
              <tbody>
                {pend.map((i: any) => (
                  <tr key={i.id} className="border-b last:border-0">
                    <td className="py-1">{i.beneficiario}</td>
                    <td><Badge variant="outline" className="text-xs">{i.status === 'sem_pix' ? 'aguardando autocadastro (PIX)' : 'aguardando nota fiscal'}</Badge></td>
                    <td className="text-right text-gray-500">{brl(i.valor)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
