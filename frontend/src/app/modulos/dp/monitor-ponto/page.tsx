'use client';

/**
 * Monitor do Ponto (ao vivo) — acompanhamento do rollout (RH/DP).
 * Adesão (ativação/rosto/contingência), batidas de hoje e feed em tempo real.
 * Auto-refresh a cada 20s. Tudo é fato no banco (nunca estimado).
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { Activity, Loader2, UserCheck, ScanFace, Clock, AlertTriangle, RefreshCw, Fingerprint, MessageCircleWarning } from 'lucide-react';

const API = '/api/v1/people-management/human-resources/ativacao-ponto/monitor';

function getAuthHeaders(): Record<string, string> {
  let token: string | null = null;
  if (typeof window !== 'undefined') {
    try { token = localStorage.getItem('access_token') || localStorage.getItem('token'); } catch { token = null; }
  }
  return { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) };
}

interface Monitor {
  ativacao: { total: number; com_rosto: number; primeiro_acesso: number; rosto_pendente: number; ativados_hoje: number; pendentes: number };
  batidas_hoje: { total: number; funcionarios: number; contingencia: number; pendente_validar: number; entradas: number; saidas: number };
  feed: { nome: string; punch_type: string; device_type: string; status: string; hora: string }[];
  atualizado_em: string;
}

function Card({ icon: Icon, label, value, sub, color }: { icon: React.ElementType; label: string; value: number | string; sub?: string; color: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4">
      <div className="flex items-center gap-2 mb-1">
        <Icon className="w-4 h-4" style={{ color }} />
        <span className="text-[12px] font-semibold uppercase tracking-wide text-slate-400">{label}</span>
      </div>
      <p className="text-3xl font-bold text-slate-900 tabular-nums">{value}</p>
      {sub && <p className="text-[12px] text-slate-400 mt-0.5">{sub}</p>}
    </div>
  );
}

export default function MonitorPontoPage() {
  const [d, setD] = useState<Monitor | null>(null);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState('');
  const [auto, setAuto] = useState(true);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const carregar = useCallback(async () => {
    try {
      const r = await fetch(API, { headers: getAuthHeaders() });
      if (!r.ok) throw new Error();
      setD(await r.json()); setErro('');
    } catch { setErro('Não foi possível carregar (precisa de acesso ao DP).'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    carregar();
    if (timer.current) clearInterval(timer.current);
    if (auto) timer.current = setInterval(carregar, 20000);
    return () => { if (timer.current) clearInterval(timer.current); };
  }, [carregar, auto]);

  const deviceBadge = (dev: string, status: string) => {
    if (status === 'pending_contingencia' || dev === 'contingencia') return { t: 'contingência', c: '#B4690E', bg: '#FBEED9' };
    if (dev === 'tangerino') return { t: 'tangerino', c: '#64748B', bg: '#F1F5F9' };
    return { t: 'facial', c: '#0E7C57', bg: '#E4F4EC' };
  };
  const tipoLabel = (t: string) => t?.replace('_', ' ') || t;

  const a = d?.ativacao; const b = d?.batidas_hoje;

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-1 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Activity className="w-6 h-6 text-[#F26522]" />
          <h1 className="text-2xl font-bold text-slate-900">Monitor do Ponto <span className="text-[13px] font-normal text-slate-400">(ao vivo)</span></h1>
        </div>
        <div className="flex items-center gap-3">
          {d && <span className="text-[12px] text-slate-400">atualizado às <b className="tabular-nums">{d.atualizado_em}</b></span>}
          <button onClick={() => setAuto((v) => !v)} className={`text-[12px] font-semibold px-2.5 py-1 rounded-full flex items-center gap-1 ${auto ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}>
            <span className={`w-2 h-2 rounded-full ${auto ? 'bg-emerald-500 animate-pulse' : 'bg-slate-400'}`} /> {auto ? 'ao vivo (20s)' : 'pausado'}
          </button>
          <button onClick={carregar} className="text-slate-400 hover:text-slate-700"><RefreshCw className="w-4 h-4" /></button>
        </div>
      </div>
      <p className="text-[13px] text-slate-500 mb-5">Adesão dos funcionários e batidas de hoje, em tempo real.</p>

      {erro && <div className="mb-4 rounded-xl bg-red-50 border border-red-200 text-red-700 text-[14px] px-4 py-3">{erro}</div>}
      {loading && !d ? (
        <div className="py-16 text-center text-slate-400"><Loader2 className="w-8 h-8 animate-spin mx-auto" /></div>
      ) : d && (
        <>
          <p className="text-[12px] font-semibold uppercase tracking-wider text-slate-400 mb-2">Adesão ao primeiro acesso</p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
            <Card icon={UserCheck} label="Ativados" value={`${a!.primeiro_acesso}/${a!.total}`} sub={`${a!.ativados_hoje} hoje`} color="#0E7C57" />
            <Card icon={ScanFace} label="Com rosto" value={a!.com_rosto} sub="reconhecimento pronto" color="#16277D" />
            <Card icon={MessageCircleWarning} label="Rosto pendente" value={a!.rosto_pendente} sub="contingência — DP cadastra" color="#B4690E" />
            <Card icon={Clock} label="Pendentes" value={a!.pendentes} sub="ainda não entraram" color="#94A3B8" />
          </div>

          <p className="text-[12px] font-semibold uppercase tracking-wider text-slate-400 mb-2">Batidas de hoje</p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
            <Card icon={Fingerprint} label="Batidas" value={b!.total} sub={`${b!.funcionarios} pessoas`} color="#F26522" />
            <Card icon={Clock} label="Entradas / Saídas" value={`${b!.entradas} / ${b!.saidas}`} color="#16277D" />
            <Card icon={MessageCircleWarning} label="Contingências" value={b!.contingencia} sub="sem rosto" color="#B4690E" />
            <Card icon={AlertTriangle} label="Validar (DP)" value={b!.pendente_validar} sub="contingência a aprovar" color={b!.pendente_validar > 0 ? '#DC2626' : '#94A3B8'} />
          </div>

          <p className="text-[12px] font-semibold uppercase tracking-wider text-slate-400 mb-2">Últimas atividades</p>
          <div className="rounded-2xl border border-slate-200 bg-white divide-y divide-slate-100">
            {d.feed.length === 0 ? (
              <p className="text-center text-slate-400 py-8 text-[14px]">Nenhuma batida hoje ainda.</p>
            ) : d.feed.map((f, i) => {
              const bd = deviceBadge(f.device_type, f.status);
              return (
                <div key={i} className="flex items-center gap-3 px-4 py-2.5">
                  <span className="text-[13px] font-mono text-slate-400 tabular-nums w-11">{f.hora}</span>
                  <span className="flex-1 min-w-0 text-[14px] text-slate-800 truncate">{f.nome}</span>
                  <span className="text-[12px] text-slate-500 capitalize">{tipoLabel(f.punch_type)}</span>
                  <span className="text-[11px] font-bold px-2 py-0.5 rounded-full" style={{ background: bd.bg, color: bd.c }}>{bd.t}</span>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
