'use client';

/**
 * Painel do Ponto — LINK PÚBLICO (token) pro Jordan acompanhar o rollout no celular.
 * `/painel-ponto?token=…` — sem login. Ao vivo: quem cadastrou, quem bateu, quem falta.
 */
import { useState, useEffect, useCallback, useRef, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';

const BASE = '/api/v1/people-management/portal/painel-ponto';

interface Func {
  nome: string; posto: string | null; ativado: boolean; ativado_em: string | null;
  com_rosto: boolean; bateu_hoje: boolean; num_batidas: number; ultima_batida: string | null;
}
interface Painel {
  resumo: { ativos: number; total: number; ativados: number; com_rosto: number; pendentes: number; bateram_hoje: number; batidas_hoje: number; contingencias_validar: number; atrasados: number; de_folga: number; sem_horario_parametrizado: number; ainda_no_solides: number };
  funcionarios: Func[];
  atrasados: { nome: string; posto: string | null; entrada_prevista: string | null; atraso_min: number }[];
  de_folga: string[];
  ainda_no_solides: { nome: string; posto: string | null }[];
  fora_da_cobranca: { nome: string; motivo: string }[];
  feed: { nome: string; punch_type: string; device_type: string; status: string; hora: string }[];
  atualizado_em: string;
}

function Stat({ n, label, color }: { n: number | string; label: string; color: string }) {
  return (
    <div className="rounded-2xl bg-white border border-slate-200 p-3 text-center">
      <p className="text-2xl font-bold tabular-nums" style={{ color }}>{n}</p>
      <p className="text-[11px] text-slate-500 leading-tight mt-0.5">{label}</p>
    </div>
  );
}

function PainelInner() {
  const sp = useSearchParams();
  const token = sp.get('token') || '';
  const [d, setD] = useState<Painel | null>(null);
  const [erro, setErro] = useState('');
  const [loading, setLoading] = useState(true);
  const [filtro, setFiltro] = useState<'todos' | 'bateram' | 'atrasados' | 'folga'>('todos');
  const [busca, setBusca] = useState('');
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const carregar = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}?token=${encodeURIComponent(token)}`);
      if (r.status === 403) { setErro('Link inválido.'); setLoading(false); return; }
      if (!r.ok) throw new Error();
      setD(await r.json()); setErro('');
    } catch { setErro('Não foi possível carregar. Tentando de novo…'); }
    finally { setLoading(false); }
  }, [token]);

  useEffect(() => {
    carregar();
    if (timer.current) clearInterval(timer.current);
    timer.current = setInterval(carregar, 20000);
    return () => { if (timer.current) clearInterval(timer.current); };
  }, [carregar]);

  const r = d?.resumo;
  const lista = (d?.funcionarios || [])
    .filter((f) => filtro === 'todos'
      || (filtro === 'bateram' && f.bateu_hoje)
      || (filtro === 'atrasados' && (d?.atrasados || []).some((a) => a.nome === f.nome))
      || (filtro === 'folga' && (d?.de_folga || []).includes(f.nome)))
    .filter((f) => !busca || f.nome.toLowerCase().includes(busca.toLowerCase()) || (f.posto || '').toLowerCase().includes(busca.toLowerCase()));

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="max-w-xl mx-auto px-4 py-5">
        <div className="flex items-center justify-between mb-1">
          <h1 className="text-xl font-bold text-[#16277D]">Painel do Ponto</h1>
          {d && <span className="text-[11px] text-slate-400 flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" /> {d.atualizado_em}</span>}
        </div>
        <p className="text-[12px] text-slate-500 mb-4">Quem bateu, quem está de folga e quem ainda não apareceu — ao vivo.</p>

        {erro && <div className="rounded-xl bg-red-50 border border-red-200 text-red-700 text-[14px] px-4 py-3 mb-3">{erro}</div>}
        {loading && !d ? (
          <p className="text-center text-slate-400 py-16">Carregando…</p>
        ) : r && (
          <>
            <div className="rounded-2xl bg-white border border-slate-200 px-4 py-3 mb-2">
              <p className="text-[13px] text-slate-600 leading-snug">
                <b className="text-slate-900 text-[15px] tabular-nums">{r.ativos}</b> funcionários ·{' '}
                <b className="text-slate-900 text-[15px] tabular-nums">{r.total}</b> devem ponto hoje
                {d.fora_da_cobranca.length > 0 && (
                  <> · <b className="text-slate-900 text-[15px] tabular-nums">{d.fora_da_cobranca.length}</b> fora</>
                )}
              </p>
              {d.fora_da_cobranca.length > 0 && (
                <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">
                  {d.fora_da_cobranca.map((f) => `${f.nome.split(' ')[0]} (${f.motivo})`).join(' · ')}
                </p>
              )}
            </div>

            <div className="grid grid-cols-4 gap-2 mb-3">
              <Stat n={r.bateram_hoje} label="bateram hoje" color="#16277D" />
              <Stat n={r.atrasados} label="atrasados" color={r.atrasados > 0 ? '#B4231E' : '#0E7C57'} />
              <Stat n={r.de_folga} label="de folga" color="#5B6474" />
              <Stat n={r.batidas_hoje} label="batidas hoje" color="#F26522" />
            </div>

            {d.atrasados.length > 0 && (
              <div className="rounded-xl bg-red-50 border border-red-200 px-3 py-2.5 mb-3">
                <p className="text-[11px] font-bold uppercase tracking-wider text-red-700 mb-1.5">
                  Ainda não bateram
                </p>
                <div className="space-y-1">
                  {d.atrasados.map((a, i) => (
                    <div key={i} className="flex items-baseline gap-2 text-[13px]">
                      <span className="flex-1 min-w-0 truncate text-red-900">{a.nome}</span>
                      <span className="text-[11px] text-red-500 shrink-0 tabular-nums">
                        previsto {a.entrada_prevista} · {Math.floor(a.atraso_min / 60)}h{String(a.atraso_min % 60).padStart(2, '0')}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Nao e cobranca: e a fila da virada. A importacao do Solides chega 14-21h
                depois, entao sobre estes o painel nao tem o que afirmar hoje. */}
            {(d.ainda_no_solides || []).length > 0 && (
              <div className="rounded-xl bg-slate-50 border border-slate-200 px-3 py-2.5 mb-3">
                <p className="text-[11px] font-bold uppercase tracking-wider text-slate-600 mb-1.5">
                  Ainda batem pelo Sólides
                </p>
                <div className="space-y-1">
                  {d.ainda_no_solides.map((a, i) => (
                    <div key={i} className="flex items-baseline gap-2 text-[13px]">
                      <span className="flex-1 min-w-0 truncate text-slate-700">{a.nome}</span>
                      <span className="text-[11px] text-slate-400 shrink-0 truncate">{a.posto}</span>
                    </div>
                  ))}
                </div>
                <p className="text-[11px] text-slate-500 mt-1.5 leading-snug">
                  A batida deles chega de madrugada, no arquivo do Sólides — por isso não
                  entram como atraso.
                </p>
              </div>
            )}

            {r.sem_horario_parametrizado > 0 && (
              <div className="rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-[13px] px-3 py-2 mb-3">
                ⚠️ {r.sem_horario_parametrizado} pessoa(s) sem horário parametrizado — o painel não sabe cobrar atraso delas.
              </div>
            )}
            {r.contingencias_validar > 0 && (
              <div className="rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-[13px] px-3 py-2 mb-3">
                ⚠️ {r.contingencias_validar} batida(s) por contingência aguardando o DP validar.
              </div>
            )}

            <input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar por nome ou posto…"
              className="w-full rounded-xl border-2 border-slate-200 px-3 py-2.5 text-[15px] outline-none focus:border-[#16277D] mb-2" />
            <div className="flex gap-1.5 mb-3 text-[12px] font-semibold">
              {(['todos', 'bateram', 'atrasados', 'folga'] as const).map((f) => (
                <button key={f} onClick={() => setFiltro(f)}
                  className={`px-3 py-1.5 rounded-full capitalize ${filtro === f ? 'bg-[#16277D] text-white' : 'bg-white border border-slate-200 text-slate-500'}`}>
                  {f === 'bateram' ? 'bateram' : f}
                </button>
              ))}
            </div>

            <div className="space-y-1.5">
              {lista.map((f, i) => (
                <div key={i} className="rounded-xl bg-white border border-slate-200 p-3 flex items-center gap-2">
                  <div className="flex-1 min-w-0">
                    <p className="font-semibold text-slate-800 text-[14px] truncate">{f.nome}</p>
                    <p className="text-[11px] text-slate-400 truncate">{f.posto || 'sem posto'}{f.ativado_em && ` · cadastrou ${f.ativado_em}`}</p>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    {f.bateu_hoje
                      ? <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-[#16277D]/10 text-[#16277D]">{f.num_batidas}× · {f.ultima_batida}</span>
                      : d.de_folga.includes(f.nome)
                        ? <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-400">folga</span>
                        : null}
                    {f.ativado
                      ? <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-emerald-100 text-emerald-700">{f.com_rosto ? 'ativo' : 'sem rosto'}</span>
                      : <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-500">pendente</span>}
                  </div>
                </div>
              ))}
              {lista.length === 0 && <p className="text-center text-slate-400 py-8 text-[14px]">Ninguém aqui ainda.</p>}
            </div>

            {d.feed.length > 0 && (
              <>
                <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 mt-5 mb-2">Últimas batidas</p>
                <div className="rounded-2xl bg-white border border-slate-200 divide-y divide-slate-100">
                  {d.feed.map((e, i) => (
                    <div key={i} className="flex items-center gap-2 px-3 py-2 text-[13px]">
                      <span className="font-mono text-slate-400 tabular-nums w-10">{e.hora}</span>
                      <span className="flex-1 min-w-0 truncate text-slate-700">{e.nome}</span>
                      <span className="text-[11px] text-slate-400 capitalize">{e.punch_type?.replace('_', ' ')}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
            <p className="text-center text-[11px] text-slate-300 mt-6">Conecta PRO · atualiza sozinho a cada 20s</p>
          </>
        )}
      </div>
    </div>
  );
}

export default function PainelPontoPage() {
  return <Suspense><PainelInner /></Suspense>;
}
