'use client';

/**
 * Ativação do Ponto (RH/DP) — painel de adesão + DISPARO do link de primeiro acesso.
 * Mostra os 50 CLT com status (ativou o rosto? pendente?) e dispara o link por
 * e-mail (todos) + WhatsApp (quem tem telefone). Prévia (dry-run) antes de enviar.
 */
import { useState, useEffect, useCallback } from 'react';
import { Loader2, Fingerprint, Copy, Check, RefreshCw, Send, Mail, MessageCircle, X, CheckCircle2, Clock } from 'lucide-react';
import { toast } from 'sonner';

const API = '/api/v1/people-management/human-resources/ativacao-ponto';

function getAuthHeaders(): Record<string, string> {
  let token: string | null = null;
  if (typeof window !== 'undefined') {
    try { token = localStorage.getItem('access_token') || localStorage.getItem('token'); } catch { token = null; }
  }
  return { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) };
}

interface Func {
  id: string; nome: string; posto: string | null; email: string | null;
  tem_email: boolean; tem_whatsapp: boolean; ativado: boolean; status: string; convite_enviado_em: string | null;
}
interface Lista { link: string; total: number; ativados: number; pendentes: number; funcionarios: Func[]; }

export default function AtivacaoPontoPage() {
  const [d, setD] = useState<Lista | null>(null);
  const [loading, setLoading] = useState(true);
  const [copiado, setCopiado] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [previa, setPrevia] = useState<{ total: number; com_email: number; com_whatsapp: number } | null>(null);
  const [enviando, setEnviando] = useState(false);

  const carregar = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(API, { headers: getAuthHeaders() });
      if (!r.ok) throw new Error();
      setD(await r.json());
    } catch { toast.error('Não foi possível carregar (precisa de acesso ao DP).'); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { carregar(); }, [carregar]);

  const copiar = () => {
    if (!d) return;
    navigator.clipboard?.writeText(d.link);
    setCopiado(true); setTimeout(() => setCopiado(false), 2000);
    toast.success('Link copiado!');
  };

  // abre o modal já com a prévia (dry-run)
  const abrirConfirm = async () => {
    setConfirmOpen(true); setPrevia(null);
    try {
      const r = await fetch(`${API}/disparar`, { method: 'POST', headers: getAuthHeaders(), body: JSON.stringify({ dry_run: true }) });
      const p = await r.json();
      setPrevia({ total: p.total, com_email: p.com_email, com_whatsapp: p.com_whatsapp });
    } catch { toast.error('Falha ao gerar a prévia.'); }
  };

  const disparar = async () => {
    setEnviando(true);
    try {
      const r = await fetch(`${API}/disparar`, { method: 'POST', headers: getAuthHeaders(), body: JSON.stringify({ dry_run: false }) });
      const res = await r.json();
      if (!r.ok) throw new Error(res.detail || 'erro');
      toast.success(`Enviado! ${res.com_email} por e-mail e ${res.com_whatsapp} por WhatsApp.`);
      setConfirmOpen(false); carregar();
    } catch (e: unknown) { toast.error((e as Error).message || 'Falha ao disparar.'); }
    finally { setEnviando(false); }
  };

  const reenviar = async (f: Func) => {
    try {
      const r = await fetch(`${API}/${f.id}/reenviar`, { method: 'POST', headers: getAuthHeaders() });
      if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || 'erro'); }
      toast.success(`Reenviado para ${f.nome.split(' ')[0]}.`); carregar();
    } catch (e: unknown) { toast.error((e as Error).message || 'Falha ao reenviar.'); }
  };

  const fmtData = (s: string | null) => s ? new Date(s).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : null;

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center gap-2 mb-1">
        <Fingerprint className="w-6 h-6 text-[#F26522]" />
        <h1 className="text-2xl font-bold text-slate-900">Ativação do Ponto</h1>
      </div>
      <p className="text-[14px] text-slate-500 mb-6">
        Dispare o link de <b>primeiro acesso</b> pros funcionários (e-mail + WhatsApp) e acompanhe quem já ativou.
        Cada um entra com o CPF, completa o cadastro e cadastra o rosto.
      </p>

      {/* Link + disparo */}
      <div className="rounded-2xl border-2 border-[#F26522]/30 bg-orange-50/40 p-5 mb-6">
        <div className="flex items-center gap-2 mb-3"><Send className="w-5 h-5 text-[#F26522]" />
          <h2 className="text-[15px] font-bold text-slate-800">Link de primeiro acesso</h2></div>
        <div className="flex items-center gap-2 mb-3">
          <code className="flex-1 text-[13px] text-slate-600 bg-white rounded-lg px-3 py-2.5 border border-slate-200 truncate">{d?.link || '—'}</code>
          <button onClick={copiar} className="rounded-lg border-2 border-slate-200 text-slate-600 text-[13px] font-semibold px-3 py-2 flex items-center gap-1 shrink-0 hover:bg-slate-50">
            {copiado ? <><Check className="w-4 h-4 text-emerald-600" /> Copiado</> : <><Copy className="w-4 h-4" /> Copiar</>}</button>
        </div>
        <button onClick={abrirConfirm} disabled={!d || d.pendentes === 0}
          className="rounded-xl bg-[#F26522] text-white text-[15px] font-bold px-5 py-2.5 flex items-center gap-2 disabled:opacity-50">
          <Send className="w-4 h-4" /> Disparar pra todos os pendentes {d ? `(${d.pendentes})` : ''}
        </button>
      </div>

      {/* Stats */}
      {d && (
        <div className="grid grid-cols-3 gap-3 mb-6">
          <div className="rounded-xl border border-slate-200 bg-white p-4 text-center">
            <p className="text-2xl font-bold text-slate-800">{d.total}</p><p className="text-[12px] text-slate-500">Funcionários</p></div>
          <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-center">
            <p className="text-2xl font-bold text-emerald-700">{d.ativados}</p><p className="text-[12px] text-emerald-600">Já ativaram</p></div>
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-center">
            <p className="text-2xl font-bold text-amber-700">{d.pendentes}</p><p className="text-[12px] text-amber-600">Pendentes</p></div>
        </div>
      )}

      {/* Lista */}
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-[15px] font-bold text-slate-700">Funcionários</h2>
        <button onClick={carregar} className="text-[13px] text-slate-500 flex items-center gap-1 hover:text-slate-700"><RefreshCw className="w-4 h-4" /> Atualizar</button>
      </div>
      {loading ? (
        <div className="py-10 text-center text-slate-400"><Loader2 className="w-7 h-7 animate-spin mx-auto" /></div>
      ) : (
        <div className="space-y-2">
          {d?.funcionarios.map((f) => (
            <div key={f.id} className="rounded-xl border border-slate-200 bg-white p-3.5 flex items-center gap-3 flex-wrap">
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-slate-800 truncate">{f.nome}</p>
                <p className="text-[12px] text-slate-400">{f.posto || 'sem posto'}{f.convite_enviado_em && ` · enviado ${fmtData(f.convite_enviado_em)}`}</p>
              </div>
              <div className="flex items-center gap-1.5 text-slate-400">
                <Mail className={`w-4 h-4 ${f.tem_email ? 'text-slate-600' : 'text-slate-300'}`} />
                <MessageCircle className={`w-4 h-4 ${f.tem_whatsapp ? 'text-emerald-600' : 'text-slate-300'}`} />
              </div>
              <span className="text-[12px] font-bold px-2.5 py-1 rounded-full flex items-center gap-1"
                style={{ background: f.ativado ? '#E4F4EC' : '#FBEED9', color: f.ativado ? '#0E7C57' : '#B4690E' }}>
                {f.ativado ? <><CheckCircle2 className="w-3.5 h-3.5" /> Ativado</> : <><Clock className="w-3.5 h-3.5" /> Pendente</>}</span>
              {!f.ativado && (
                <button onClick={() => reenviar(f)} className="rounded-lg border border-slate-200 text-slate-600 text-[13px] font-semibold px-3 py-1.5 flex items-center gap-1 hover:bg-slate-50">
                  <Send className="w-3.5 h-3.5" /> Reenviar</button>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Modal de confirmação */}
      {confirmOpen && (
        <div className="fixed inset-0 bg-slate-900/60 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl p-6 w-full max-w-md">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-[16px] font-bold text-slate-800 flex items-center gap-2"><Send className="w-5 h-5 text-[#F26522]" /> Confirmar disparo</h3>
              <button onClick={() => setConfirmOpen(false)} className="text-slate-400 hover:text-slate-600"><X className="w-5 h-5" /></button>
            </div>
            {!previa ? (
              <div className="py-8 text-center text-slate-400"><Loader2 className="w-6 h-6 animate-spin mx-auto" /></div>
            ) : (
              <>
                <p className="text-[14px] text-slate-600 mb-4">Vou enviar o link de primeiro acesso para os funcionários pendentes:</p>
                <div className="grid grid-cols-3 gap-2 mb-5 text-center">
                  <div className="rounded-lg bg-slate-50 p-3"><p className="text-xl font-bold text-slate-800">{previa.total}</p><p className="text-[11px] text-slate-500">pessoas</p></div>
                  <div className="rounded-lg bg-slate-50 p-3"><p className="text-xl font-bold text-slate-800">{previa.com_email}</p><p className="text-[11px] text-slate-500">por e-mail</p></div>
                  <div className="rounded-lg bg-slate-50 p-3"><p className="text-xl font-bold text-emerald-700">{previa.com_whatsapp}</p><p className="text-[11px] text-slate-500">por WhatsApp</p></div>
                </div>
                <div className="flex gap-2">
                  <button onClick={() => setConfirmOpen(false)} className="flex-1 rounded-xl border-2 border-slate-200 text-slate-600 font-semibold py-2.5">Cancelar</button>
                  <button onClick={disparar} disabled={enviando} className="flex-1 rounded-xl bg-[#F26522] text-white font-bold py-2.5 flex items-center justify-center gap-2 disabled:opacity-50">
                    {enviando ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />} Enviar agora</button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
