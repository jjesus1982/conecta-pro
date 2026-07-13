'use client';

import { useState, useEffect } from 'react';
import { Users, Loader2, CalendarDays, Send, AlertTriangle, CheckCircle2, UserPlus, ClipboardList } from 'lucide-react';
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
  // OTP do lote (dinheiro que sai)
  const [otpLote, setOtpLote] = useState<string | null>(null);
  const [otpCode, setOtpCode] = useState('');
  const [otpMsg, setOtpMsg] = useState<string | null>(null);
  const [otpBusy, setOtpBusy] = useState(false);
  const [sugestoes, setSugestoes] = useState<any[]>([]);
  const [showSug, setShowSug] = useState(false);

  // FLUXO 2a — diaristas lançados no dia (fonte: lançamento de diárias do Gonzaga)
  const [dataLanc, setDataLanc] = useState(hoje);
  const [lancados, setLancados] = useState<any>(null);
  const [busyLanc, setBusyLanc] = useState(false);
  const [msgLanc, setMsgLanc] = useState<string | null>(null);

  // FLUXO 2b — lote mensal de diárias (dia 15)
  const agora = new Date();
  const [mesLote, setMesLote] = useState(agora.getMonth() + 1);
  const [anoLote, setAnoLote] = useState(agora.getFullYear());
  const [busyMes, setBusyMes] = useState(false);
  const [msgMes, setMsgMes] = useState<string | null>(null);

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
  const carregarLancados = async (d = dataLanc) => {
    setMsgLanc(null);
    try {
      const r = await fetch(`${API}/lancados-dia/${d}`, { headers: authHeaders() }).then(x => x.json());
      if (r?.detail) { setLancados(null); setMsgLanc(typeof r.detail === 'string' ? r.detail : 'Falha ao carregar lançados do dia.'); return; }
      setLancados(r);
    } catch { setLancados(null); setMsgLanc('Falha ao carregar lançados do dia.'); }
  };
  useEffect(() => { carregarLote(); carregarSugestoes(); carregarLancados(); }, []);

  const programarLancados = async () => {
    setBusyLanc(true); setMsgLanc(null);
    try {
      const r = await fetch(`${API}/programar-lancados-dia/${dataLanc}`, { method: 'POST', headers: authHeaders() }).then(x => x.json());
      if (r?.detail) { setMsgLanc(typeof r.detail === 'string' ? r.detail : 'Falha ao programar.'); return; }
      setMsgLanc(`${r.programados_novos ?? 0} novo(s) programado(s), ${r.ja_programados ?? 0} já programado(s)${r.sem_pix ? `, ${r.sem_pix} sem PIX` : ''} — total do dia ${brl(r.total_a_pagar_do_dia)}.`);
      carregarLancados(dataLanc);
      if (dataLanc !== data) { setData(dataLanc); }
      carregarLote(dataLanc);
    } catch { setMsgLanc('Falha ao programar os lançados do dia.'); } finally { setBusyLanc(false); }
  };

  const programarMensais = async () => {
    setBusyMes(true); setMsgMes(null);
    try {
      const r = await fetch(`${API}/programar-diarias-mensais/${anoLote}/${mesLote}`, { method: 'POST', headers: authHeaders() }).then(x => x.json());
      if (r?.detail) { setMsgMes(typeof r.detail === 'string' ? r.detail : 'Falha ao programar o lote mensal.'); return; }
      setMsgMes(`${r.diaristas ?? 0} diarista(s), ${r.programados_novos ?? 0} novo(s) programado(s)${r.sem_pix ? `, ${r.sem_pix} sem PIX` : ''} — total ${brl(r.total_a_pagar)}, pagamento em ${r.data_pagamento || '—'}.`);
      if (r.data_pagamento) { setData(r.data_pagamento); carregarLote(r.data_pagamento); }
    } catch { setMsgMes('Falha ao programar o lote mensal.'); } finally { setBusyMes(false); }
  };

  const abrirPreview = async () => {
    setPagando(true); setResultado(null);
    setOtpLote(null); setOtpCode(''); setOtpMsg(null);  // recomeça o gate OTP a cada prévia
    try {
      const r = await fetch(`${API}/executar`, { method: 'POST', headers: authHeaders(), body: JSON.stringify({ data, confirmar: false }) }).then(x => x.json());
      setPreview(r);
    } catch { setMsg('Falha na prévia.'); } finally { setPagando(false); }
  };
  const solicitarOtp = async () => {
    setOtpBusy(true); setOtpMsg(null);
    try {
      const r = await fetch(`${API}/solicitar-otp`, { method: 'POST', headers: authHeaders(), body: JSON.stringify({ data }) }).then(x => x.json());
      if (r?.ok && r?.lote_id) {
        setOtpLote(r.lote_id);
        setOtpMsg(`Código enviado por e-mail (válido ${Math.round((r.expires_in_seconds ?? 600) / 60)} min). Digite abaixo para confirmar.`);
      } else {
        setOtpMsg(r?.mensagem || r?.detail || 'Falha ao gerar o código.');
      }
    } catch { setOtpMsg('Falha ao solicitar o código.'); } finally { setOtpBusy(false); }
  };
  const confirmarPagamento = async () => {
    if (!otpLote || otpCode.trim().length < 6) { setOtpMsg('Informe o código de 6 dígitos do e-mail.'); return; }
    setPagando(true);
    try {
      const r = await fetch(`${API}/executar`, { method: 'POST', headers: authHeaders(), body: JSON.stringify({ data, confirmar: true, otp_code: otpCode.trim(), lote_id: otpLote }) }).then(x => x.json());
      if (r?.otp_invalido || r?.otp_requerido) { setOtpMsg(r?.mensagem || 'Código inválido. Gere um novo.'); return; }
      setResultado(r); setPreview(null); setOtpLote(null); setOtpCode(''); setOtpMsg(null); carregarLote();
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
          <p className="text-sm text-muted-foreground">A relação de diaristas do dia (lançada pelo Gonzaga no Operacional) vira lote a pagar aqui. Revise e pague em lote via PIX (Banco Inter). R$10 VT + R$22 VR = R$32/dia.</p>
        </div>
      </div>

      {/* Diaristas lançados no dia (fonte: relação de diárias do Gonzaga) — caminho principal do VT+VR diário */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2"><ClipboardList className="h-4 w-4 text-emerald-600" /> 1. Diaristas lançados no dia (relação do Gonzaga)</CardTitle>
          <p className="text-xs text-muted-foreground">Escolha o dia, confira quem o Gonzaga lançou e programe o VT+VR (R$32) de cada um. Quem estiver "sem PIX" precisa ser completado no cadastro do Operacional.</p>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <input type="date" value={dataLanc} onChange={e => { setDataLanc(e.target.value); carregarLancados(e.target.value); }} className="border rounded px-3 py-2 text-sm" />
            <Button onClick={programarLancados} disabled={busyLanc || !lancados?.itens?.length} className="bg-emerald-600 hover:bg-emerald-700 text-white">
              {busyLanc ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Send className="h-4 w-4 mr-1" />} Programar VT+VR dos lançados
            </Button>
            {lancados && <span className="text-xs text-muted-foreground">{lancados.total_diaristas ?? 0} diarista(s) · {lancados.total_lancamentos ?? 0} lançamento(s)</span>}
          </div>
          {msgLanc && <div className="text-sm text-gray-600">{msgLanc}</div>}
          {!lancados?.itens?.length ? (
            !msgLanc && <p className="text-sm text-gray-400">Nenhuma diária lançada pelo Operacional nesta data.</p>
          ) : (
            <div className="divide-y">
              {lancados.itens.map((i: any) => (
                <div key={i.lancamento_id} className="py-2 flex flex-wrap items-center justify-between gap-2 text-sm">
                  <div className="flex-1 min-w-0">
                    <span className="font-medium">{i.nome}</span>
                    <span className="text-xs text-gray-500 ml-2">{i.funcao}{i.posto ? ` · ${i.posto}` : ''}{i.turno && i.turno !== 'ÚNICO' ? ` · ${i.turno}` : ''}</span>
                  </div>
                  <span className="font-semibold">{brl(i.valor_diaria)}</span>
                  <div className="flex items-center gap-1">
                    {!i.tem_pix && <Badge className="bg-red-100 text-red-700 text-xs">sem PIX</Badge>}
                    {!i.tem_cpf && <Badge className="bg-red-100 text-red-700 text-xs">sem CPF</Badge>}
                    {i.ja_programado_vt_vr && <Badge className="bg-green-100 text-green-700 text-xs">já programado</Badge>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Lote mensal das diárias (dia 15) */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2"><CalendarDays className="h-4 w-4 text-emerald-600" /> Programar diárias do mês (lote dia 15)</CardTitle>
          <p className="text-xs text-muted-foreground">soma os dias trabalhados × valor da diária de cada diarista no mês e programa o lote para o dia 15</p>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-3">
          <select value={mesLote} onChange={e => setMesLote(Number(e.target.value))} className="border rounded px-3 py-2 text-sm bg-white">
            {Array.from({ length: 12 }, (_, i) => i + 1).map(m => <option key={m} value={m}>{String(m).padStart(2, '0')}</option>)}
          </select>
          <select value={anoLote} onChange={e => setAnoLote(Number(e.target.value))} className="border rounded px-3 py-2 text-sm bg-white">
            {[agora.getFullYear() - 1, agora.getFullYear(), agora.getFullYear() + 1].map(a => <option key={a} value={a}>{a}</option>)}
          </select>
          <Button onClick={programarMensais} disabled={busyMes} className="bg-emerald-600 hover:bg-emerald-700 text-white">
            {busyMes ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Send className="h-4 w-4 mr-1" />} {busyMes ? 'Programando…' : 'Programar lote do mês'}
          </Button>
          {msgMes && <span className="text-sm text-gray-600">{msgMes}</span>}
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
          {msg && <span className="text-sm text-red-600">{msg}</span>}
          <p className="w-full text-xs text-muted-foreground">Ex.: um líder que leva 2 ajudantes recebe o VT+VR dos dois num PIX só → quantidade 2 = R$64.</p>
        </CardContent>
      </Card>

      {/* Lote */}
      <Card>
        <CardHeader className="pb-2 flex-row items-center justify-between">
          <CardTitle className="text-base flex items-center gap-2">
            2. Lote a pagar —
            <input type="date" value={data} onChange={e => { setData(e.target.value); carregarLote(e.target.value); }} className="border rounded px-2 py-1 text-sm font-normal" />
          </CardTitle>
          <div className="text-sm">Total: <b>{brl(totalPagar)}</b> · {lote.filter(i => i.status === 'a_revisar').length} a revisar</div>
        </CardHeader>
        <CardContent>
          {lote.length === 0 ? <p className="text-sm text-gray-400">Nenhum pagamento programado para esta data. Programe pelo passo 1 (relação do Gonzaga) ou adicione manualmente abaixo.</p> : (
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

            {/* Gate OTP — dinheiro que sai exige o código do e-mail */}
            {preview.dentro_do_limite && preview.itens > 0 && (
              <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3">
                {!otpLote ? (
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm text-amber-800">Para pagar, gere o código de autorização (enviado ao seu e-mail).</span>
                    <Button onClick={solicitarOtp} disabled={otpBusy} variant="outline" className="whitespace-nowrap">
                      {otpBusy ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : null} Solicitar código
                    </Button>
                  </div>
                ) : (
                  <div className="flex items-center gap-2">
                    <label className="text-sm text-amber-800 whitespace-nowrap">Código do e-mail:</label>
                    <input value={otpCode} onChange={e => setOtpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                      inputMode="numeric" maxLength={6} placeholder="000000"
                      className="border rounded px-3 py-1.5 text-lg tracking-widest font-mono w-32 text-center" />
                    <button onClick={solicitarOtp} disabled={otpBusy} className="text-xs text-amber-700 underline">reenviar</button>
                  </div>
                )}
                {otpMsg && <p className="mt-2 text-xs text-amber-800">{otpMsg}</p>}
              </div>
            )}

            <div className="mt-4 flex items-center justify-end gap-2">
              <Button variant="outline" onClick={() => setPreview(null)}>Cancelar</Button>
              <Button onClick={confirmarPagamento} disabled={pagando || !preview.dentro_do_limite || !preview.itens || !otpLote || otpCode.length < 6} className="bg-emerald-600 hover:bg-emerald-700 text-white">
                {pagando ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Send className="h-4 w-4 mr-1" />} Confirmar e pagar {brl(preview.total)}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
