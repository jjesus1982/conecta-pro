'use client';

/**
 * Candidatos do RH — HUB unificado (Funil candidato→colaborador + Recrutamento).
 *
 * Esteira do FUNIL: quem se autocadastrou pela vaga (employees.status='candidato'),
 * com dados/selfie/PIX prontos. O RH aprova/reprova; ao aprovar, a informação desce a
 * cadeia RH → DP → operacional → ponto → financeiro (propagação = Fase 4).
 * Link para o Recrutamento manual (ATS clássico) mantém as duas ferramentas juntas.
 */
import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import {
  Loader2, UserCheck, UserX, Briefcase, MapPin, CreditCard, Camera, ClipboardList,
  RefreshCw, ArrowUpRight, X, Building2, ArrowRight, ShieldCheck, Clock,
  FileText, Eye, Download,
} from 'lucide-react';
import { toast } from 'sonner';
import { abrirPdf } from '@/lib/pdf';

const API = '/api/v1/people-management/human-resources/candidatos';

function getAuthHeaders(): Record<string, string> {
  let token: string | null = null;
  if (typeof window !== 'undefined') {
    try { token = localStorage.getItem('access_token') || localStorage.getItem('token'); } catch { token = null; }
  }
  return { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) };
}

interface Candidato {
  id: string; protocolo: string; nome: string; cargo_pleiteado: string;
  status: string; status_label: string; email: string; telefone: string; cpf: string;
  cidade: string; uf: string; pix_key: string; pix_key_type: string;
  facial_cadastrada: boolean; dados_ok: number; dados_total: number; criado_em: string | null;
  score: number | null; nivel_score: string | null; recomendacao: string | null;
}
interface Fator { check: string; impacto: number; status: string; resumo: string }
interface DossieCheck { check_type: string; provider: string; status: string; resumo: string }

interface Posto {
  id: string; nome: string; code: string; shift_type: string;
  cliente: string; required: number; current: number; vagas: number;
}

const FILTROS = [
  { key: 'candidato', label: 'Em análise' },
  { key: 'em_admissao', label: 'Em admissão' },
  { key: 'aprovado', label: 'Aprovados' },
  { key: 'reprovado', label: 'Reprovados' },
];

export default function CandidatosRHPage() {
  const [filtro, setFiltro] = useState('candidato');
  const [lista, setLista] = useState<Candidato[]>([]);
  const [contadores, setContadores] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [agindo, setAgindo] = useState<string | null>(null);

  // ── Modal de aprovação (escolher posto) ──
  const [aprovarAlvo, setAprovarAlvo] = useState<Candidato | null>(null);
  const [postos, setPostos] = useState<Posto[]>([]);
  const [postoSel, setPostoSel] = useState('');
  const [turnoSel, setTurnoSel] = useState('diurno');
  const [paridadeSel, setParidadeSel] = useState('impares');
  const [carregandoPostos, setCarregandoPostos] = useState(false);

  // ── Modal de admissão (checklist com gates) ──
  interface ChkItem { item_key: string; label: string; categoria: string; obrigatorio_legal: boolean; gate_humano: boolean; status: string; observacao: string | null }
  interface ChkResumo { total: number; concluidos: number; pendentes: number; pode_iniciar: boolean; bloqueios_legais: string[] }
  const [admAlvo, setAdmAlvo] = useState<Candidato | null>(null);
  const [chkItens, setChkItens] = useState<ChkItem[]>([]);
  const [chkResumo, setChkResumo] = useState<ChkResumo | null>(null);
  const [chkLoading, setChkLoading] = useState(false);
  const [admDocs, setAdmDocs] = useState<{ id: string; tipo: string; nome: string; is_pdf: boolean }[]>([]);

  const abrirAdmissao = async (c: Candidato) => {
    setAdmAlvo(c); setChkItens([]); setChkResumo(null); setChkLoading(true); setAdmDocs([]);
    try {
      const r = await fetch(`${API}/${c.id}/admissao`, { headers: getAuthHeaders() });
      const d = await r.json();
      setChkItens(d.itens || []); setChkResumo(d.resumo || null);
      // certidões ficam PERMANENTES no dossiê — traz elas pro checklist de admissão também
      const rd = await fetch(`${API}/${c.id}/dossie`, { headers: getAuthHeaders() });
      const dd = await rd.json();
      setAdmDocs(dd.documentos || []);
    } catch { toast.error('Não foi possível carregar o checklist.'); }
    finally { setChkLoading(false); }
  };

  const marcarItem = async (item: ChkItem) => {
    const novo = item.status === 'ok' ? 'pendente' : 'ok';
    try {
      const r = await fetch(`${API}/${admAlvo!.id}/admissao/${item.item_key}`, {
        method: 'POST', headers: getAuthHeaders(), body: JSON.stringify({ status: novo }),
      });
      if (!r.ok) throw new Error();
      // recarrega
      const rr = await fetch(`${API}/${admAlvo!.id}/admissao`, { headers: getAuthHeaders() });
      const d = await rr.json();
      setChkItens(d.itens || []); setChkResumo(d.resumo || null);
    } catch { toast.error('Não foi possível atualizar o item.'); }
  };

  // ── Dossiê / score (Fase 6.2) ──
  const [verificandoId, setVerificandoId] = useState<string | null>(null);
  const [dossieAlvo, setDossieAlvo] = useState<Candidato | null>(null);
  const [dossie, setDossie] = useState<{ fatores?: Fator[]; checks?: DossieCheck[]; pendentes?: DossieCheck[];
    documentos?: { id: string; tipo: string; nome: string; is_pdf: boolean }[] } | null>(null);

  const verificarCandidato = async (c: Candidato) => {
    setVerificandoId(c.id);
    try {
      const r = await fetch(`${API}/${c.id}/verificar`, { method: 'POST', headers: getAuthHeaders() });
      if (!r.ok) throw new Error();
      const d = await r.json();
      toast.success(`Score ${d.score} — ${d.recomendacao} (${d.checks_reais}/${d.checks_total} verificações).`);
      carregar();
    } catch { toast.error('Não foi possível verificar o candidato.'); }
    finally { setVerificandoId(null); }
  };

  const abrirDossie = async (c: Candidato) => {
    setDossieAlvo(c); setDossie(null);
    try {
      const r = await fetch(`${API}/${c.id}/dossie`, { headers: getAuthHeaders() });
      const d = await r.json();
      setDossie({ checks: (d.checks || []).filter((x: DossieCheck) => x.status !== 'pendente'),
                  pendentes: (d.checks || []).filter((x: DossieCheck) => x.status === 'pendente'),
                  documentos: d.documentos || [] });
    } catch { toast.error('Não foi possível abrir o dossiê.'); }
  };

  const corNivel = (n: string | null) => n === 'baixo' ? '#059669' : n === 'medio' ? '#B4690E' : n === 'alto' ? '#C0392B' : '#94A3B8';

  const carregar = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API}?status_filtro=${filtro}`, { headers: getAuthHeaders() });
      if (!r.ok) throw new Error('falha');
      const d = await r.json();
      setLista(d.candidatos || []);
      setContadores(d.contadores || {});
    } catch {
      toast.error('Não foi possível carregar a esteira de candidatos.');
      setLista([]);
    } finally { setLoading(false); }
  }, [filtro]);

  useEffect(() => { carregar(); }, [carregar]);

  const reprovar = async (c: Candidato) => {
    if (!confirm(`Confirma reprovar a candidatura de ${c.nome} (${c.cargo_pleiteado})?`)) return;
    setAgindo(c.id);
    try {
      const r = await fetch(`${API}/${c.id}/decisao`, {
        method: 'POST', headers: getAuthHeaders(), body: JSON.stringify({ decisao: 'reprovado' }),
      });
      if (!r.ok) throw new Error('falha');
      toast.success('Candidato reprovado.');
      carregar();
    } catch {
      toast.error('Não foi possível reprovar o candidato.');
    } finally { setAgindo(null); }
  };

  const abrirAprovar = async (c: Candidato) => {
    setAprovarAlvo(c); setPostoSel(''); setTurnoSel('diurno'); setParidadeSel('impares');
    setCarregandoPostos(true);
    try {
      const r = await fetch(`${API}/postos`, { headers: getAuthHeaders() });
      const d = await r.json();
      setPostos(d.postos || []);
    } catch { setPostos([]); toast.error('Não foi possível carregar os postos.'); }
    finally { setCarregandoPostos(false); }
  };

  const ehPortaria = (aprovarAlvo?.cargo_pleiteado || '').toUpperCase().includes('PORTARIA');

  const confirmarAprovar = async () => {
    if (!aprovarAlvo || !postoSel) { toast.error('Escolha o posto.'); return; }
    setAgindo(aprovarAlvo.id);
    try {
      const body: Record<string, unknown> = { posto_id: postoSel };
      if (ehPortaria) { body.turno = turnoSel; body.paridade = paridadeSel; }
      const r = await fetch(`${API}/${aprovarAlvo.id}/aprovar`, {
        method: 'POST', headers: getAuthHeaders(), body: JSON.stringify(body),
      });
      if (!r.ok) throw new Error('falha');
      const d = await r.json();
      const p = d.propagacao || {};
      toast.success(
        `${d.nome} ativado! Matrícula ${p.dp?.matricula}, ${p.operacional?.posto} ` +
        `(${p.operacional?.turnos_gerados} turnos), contrato enviado para assinatura.`,
        { duration: 8000 },
      );
      setAprovarAlvo(null);
      carregar();
    } catch {
      toast.error('Não foi possível aprovar/ativar o candidato.');
    } finally { setAgindo(null); }
  };

  return (
    <div className="p-4 sm:p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-1 gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <ClipboardList className="w-7 h-7" style={{ color: '#F97316' }} />
          <h1 className="text-2xl font-extrabold" style={{ color: '#1E3A5F' }}>Candidatos</h1>
        </div>
        <div className="flex items-center gap-3">
          <Link href="/modulos/rh/recrutamento/candidatos" className="text-[14px] font-semibold text-slate-500 hover:text-slate-700 flex items-center gap-1">
            Recrutamento manual <ArrowUpRight className="w-4 h-4" />
          </Link>
          <button onClick={carregar} className="text-slate-500 hover:text-slate-700 flex items-center gap-1 text-sm">
            <RefreshCw className="w-4 h-4" /> Atualizar
          </button>
        </div>
      </div>
      <p className="text-[15px] text-slate-500 mb-5">
        Autocadastros da vaga (dados eSocial, selfie e PIX prontos). Ao <b className="text-slate-700">aprovar</b>, o
        candidato vira colaborador e a informação desce a cadeia <b className="text-slate-700">RH → DP → operacional → ponto → financeiro</b>.
      </p>

      <div className="flex gap-2 mb-5 flex-wrap">
        {FILTROS.map((f) => (
          <button
            key={f.key}
            onClick={() => setFiltro(f.key)}
            className={`px-4 py-2 rounded-xl text-[15px] font-semibold border-2 transition-colors ${
              filtro === f.key ? 'text-white border-transparent' : 'bg-white text-slate-600 border-slate-200'
            }`}
            style={filtro === f.key ? { background: '#2D5F8B' } : undefined}
          >
            {f.label}
            <span className={`ml-2 text-sm ${filtro === f.key ? 'text-white/80' : 'text-slate-400'}`}>
              {contadores[f.key] ?? 0}
            </span>
          </button>
        ))}
      </div>

      {loading ? (
        <div className="py-16 text-center text-slate-400"><Loader2 className="w-8 h-8 animate-spin mx-auto" /></div>
      ) : lista.length === 0 ? (
        <div className="py-16 text-center text-slate-400 text-[15px]">Nenhum candidato {FILTROS.find((f) => f.key === filtro)?.label.toLowerCase()}.</div>
      ) : (
        <div className="space-y-3">
          {lista.map((c) => (
            <div key={c.id} className="rounded-2xl bg-white border border-slate-200 p-4 sm:p-5">
              <div className="flex items-start justify-between gap-3 flex-wrap">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-lg font-bold text-slate-900">{c.nome}</span>
                    <span className="text-xs font-mono text-slate-400">{c.protocolo}</span>
                  </div>
                  <div className="mt-1.5 flex items-center gap-x-4 gap-y-1 flex-wrap text-[14px] text-slate-600">
                    <span className="flex items-center gap-1"><Briefcase className="w-4 h-4 text-slate-400" /> {c.cargo_pleiteado}</span>
                    <span className="flex items-center gap-1"><MapPin className="w-4 h-4 text-slate-400" /> {c.cidade || '—'}{c.uf ? `/${c.uf}` : ''}</span>
                    <span className="flex items-center gap-1"><CreditCard className="w-4 h-4 text-slate-400" /> {c.pix_key || '—'} <span className="text-slate-400">({c.pix_key_type || '?'})</span></span>
                  </div>
                  <div className="mt-2 flex items-center gap-2 flex-wrap">
                    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${c.dados_ok >= c.dados_total ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'}`}>
                      Dados {c.dados_ok}/{c.dados_total}
                    </span>
                    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full flex items-center gap-1 ${c.facial_cadastrada ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}>
                      <Camera className="w-3 h-3" /> {c.facial_cadastrada ? 'Selfie ✓' : 'Sem selfie'}
                    </span>
                    {c.score != null ? (
                      <button onClick={() => abrirDossie(c)}
                        className="text-xs font-bold px-2 py-0.5 rounded-full text-white flex items-center gap-1"
                        style={{ background: corNivel(c.nivel_score) }} title="Ver dossiê">
                        <ShieldCheck className="w-3 h-3" /> Score {c.score} · {c.recomendacao}
                      </button>
                    ) : (
                      <button onClick={() => verificarCandidato(c)} disabled={verificandoId === c.id}
                        className="text-xs font-semibold px-2 py-0.5 rounded-full border border-slate-300 text-slate-500 flex items-center gap-1 disabled:opacity-50">
                        {verificandoId === c.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <ShieldCheck className="w-3 h-3" />} Verificar
                      </button>
                    )}
                    <span className="text-xs text-slate-400">{c.email}</span>
                  </div>
                </div>

                {filtro === 'candidato' ? (
                  <div className="flex gap-2 shrink-0">
                    <button
                      onClick={() => reprovar(c)}
                      disabled={agindo === c.id}
                      className="px-4 py-2 rounded-xl border-2 border-red-200 text-red-600 font-semibold text-[15px] hover:bg-red-50 disabled:opacity-50 flex items-center gap-1"
                    >
                      <UserX className="w-4 h-4" /> Reprovar
                    </button>
                    <button
                      onClick={() => abrirAprovar(c)}
                      disabled={agindo === c.id}
                      className="px-4 py-2 rounded-xl text-white font-semibold text-[15px] disabled:opacity-50 flex items-center gap-1"
                      style={{ background: '#059669' }}
                    >
                      {agindo === c.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <UserCheck className="w-4 h-4" />} Aprovar
                    </button>
                  </div>
                ) : (
                  <div className="flex items-center gap-2 shrink-0">
                    <span className={`text-[15px] font-bold px-3 py-1 rounded-full ${c.status === 'aprovado' ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-600'}`}>
                      {c.status_label}
                    </span>
                    {(c.status === 'aprovado' || c.status === 'ativo') && (
                      <button onClick={() => abrirAdmissao(c)}
                        className="px-3 py-1.5 rounded-xl border-2 font-semibold text-[14px] flex items-center gap-1"
                        style={{ borderColor: '#2D5F8B', color: '#2D5F8B' }}>
                        <ClipboardList className="w-4 h-4" /> Admissão
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Modal de aprovação — RH escolhe o posto e a cascata dispara */}
      {aprovarAlvo && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setAprovarAlvo(null)}>
          <div className="w-full max-w-md rounded-2xl bg-white shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between p-5 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <UserCheck className="w-6 h-6" style={{ color: '#059669' }} />
                <h2 className="text-lg font-bold text-slate-900">Aprovar e alocar</h2>
              </div>
              <button onClick={() => setAprovarAlvo(null)} className="text-slate-400 hover:text-slate-600"><X className="w-5 h-5" /></button>
            </div>
            <div className="p-5">
              <p className="text-[15px] text-slate-600 mb-1">
                <b className="text-slate-900">{aprovarAlvo.nome}</b> — vaga de <b className="text-slate-900">{aprovarAlvo.cargo_pleiteado}</b>
              </p>
              <p className="text-[13px] text-slate-400 mb-4">
                Ao confirmar, o candidato vira colaborador ativo, é alocado no posto, recebe a escala, o login e o
                contrato para assinar. <b>RH → DP → operacional → ponto → financeiro.</b>
              </p>

              <label className="block text-[14px] font-semibold text-slate-700 mb-1.5">Posto de lotação</label>
              {carregandoPostos ? (
                <div className="py-3 text-slate-400 text-sm flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin" /> carregando postos…</div>
              ) : (
                <select value={postoSel} onChange={(e) => setPostoSel(e.target.value)}
                  className="w-full rounded-xl border-2 border-slate-200 bg-white px-3.5 py-3 text-[15px] text-slate-900 focus:border-[#059669] focus:outline-none">
                  <option value="">Selecione o posto…</option>
                  {postos.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.nome}{p.vagas > 0 ? ` — ${p.vagas} vaga(s)` : ''} ({p.cliente})
                    </option>
                  ))}
                </select>
              )}

              {ehPortaria && (
                <div className="mt-4 grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-[14px] font-semibold text-slate-700 mb-1.5">Turno (12x36)</label>
                    <select value={turnoSel} onChange={(e) => setTurnoSel(e.target.value)}
                      className="w-full rounded-xl border-2 border-slate-200 bg-white px-3 py-2.5 text-[15px] focus:border-[#059669] focus:outline-none">
                      <option value="diurno">Diurno (07–19)</option>
                      <option value="noturno">Noturno (19–07)</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-[14px] font-semibold text-slate-700 mb-1.5">Escala</label>
                    <select value={paridadeSel} onChange={(e) => setParidadeSel(e.target.value)}
                      className="w-full rounded-xl border-2 border-slate-200 bg-white px-3 py-2.5 text-[15px] focus:border-[#059669] focus:outline-none">
                      <option value="impares">Dias ímpares</option>
                      <option value="pares">Dias pares</option>
                    </select>
                  </div>
                </div>
              )}

              <button
                onClick={confirmarAprovar}
                disabled={!postoSel || agindo === aprovarAlvo.id}
                className="mt-6 w-full rounded-xl py-3.5 text-white font-bold text-[16px] disabled:opacity-50 flex items-center justify-center gap-2"
                style={{ background: '#059669' }}
              >
                {agindo === aprovarAlvo.id
                  ? <><Loader2 className="w-5 h-5 animate-spin" /> Ativando…</>
                  : <><Building2 className="w-5 h-5" /> Aprovar e ativar <ArrowRight className="w-4 h-4" /></>}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal de admissão — checklist com gates legais */}
      {admAlvo && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setAdmAlvo(null)}>
          <div className="w-full max-w-lg max-h-[88vh] overflow-y-auto rounded-2xl bg-white shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between p-5 border-b border-slate-100 sticky top-0 bg-white">
              <div className="flex items-center gap-2">
                <ClipboardList className="w-6 h-6" style={{ color: '#F97316' }} />
                <h2 className="text-lg font-bold text-slate-900">Admissão — {admAlvo.nome}</h2>
              </div>
              <button onClick={() => setAdmAlvo(null)} className="text-slate-400 hover:text-slate-600"><X className="w-5 h-5" /></button>
            </div>
            <div className="p-5">
              {chkResumo && (
                <div className="mb-4 rounded-xl p-3 flex items-center justify-between"
                  style={{ background: chkResumo.pode_iniciar ? '#E4F4EC' : '#FBE7E4' }}>
                  <span className="text-[15px] font-semibold" style={{ color: chkResumo.pode_iniciar ? '#0E7C57' : '#C0392B' }}>
                    {chkResumo.pode_iniciar ? '✓ Pode iniciar (sem bloqueio legal)' : '⚠ Não pode iniciar — falta item legal'}
                  </span>
                  <span className="text-[13px] font-mono text-slate-500">{chkResumo.concluidos}/{chkResumo.total}</span>
                </div>
              )}
              {chkLoading ? (
                <div className="py-10 text-center text-slate-400"><Loader2 className="w-7 h-7 animate-spin mx-auto" /></div>
              ) : (
                <div className="space-y-2">
                  {chkItens.map((it) => (
                    <div key={it.item_key} className="flex items-start gap-3 rounded-xl border border-slate-200 p-3">
                      <button onClick={() => marcarItem(it)}
                        className="mt-0.5 w-6 h-6 rounded-md border-2 flex items-center justify-center shrink-0"
                        style={{ borderColor: it.status === 'ok' ? '#059669' : '#CBD5E1', background: it.status === 'ok' ? '#059669' : 'white' }}>
                        {it.status === 'ok' && <UserCheck className="w-4 h-4 text-white" />}
                      </button>
                      <div className="min-w-0 flex-1">
                        <p className="text-[15px] font-medium text-slate-800 leading-snug">{it.label}</p>
                        <div className="mt-1 flex items-center gap-2 flex-wrap">
                          <span className="text-[11px] text-slate-400 font-mono">{it.categoria}</span>
                          {it.obrigatorio_legal && <span className="text-[11px] font-bold px-1.5 py-0.5 rounded" style={{ background: '#FBE7E4', color: '#C0392B' }}>exigido por lei</span>}
                          {it.gate_humano && <span className="text-[11px] font-bold px-1.5 py-0.5 rounded" style={{ background: '#FBEED9', color: '#B4690E' }}>🔒 confirmação humana</span>}
                        </div>
                        {it.observacao && <p className="mt-1 text-[12px] text-slate-400">{it.observacao}</p>}
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {admDocs.length > 0 && (
                <div className="mt-5">
                  <h3 className="text-[13px] font-bold uppercase tracking-wide text-slate-500 mb-2 flex items-center gap-1.5">
                    <FileText className="w-4 h-4 text-[#C0392B]" /> Certidões (permanentes no dossiê)
                  </h3>
                  <div className="space-y-2">
                    {admDocs.map((doc) => {
                      const rot: Record<string, string> = {
                        certidao_cndt: 'Certidão Negativa de Débitos Trabalhistas (TST)',
                        certidao_jf: 'Certidão da Justiça Federal',
                        certidao_antecedentes: 'Certidão de Antecedentes Criminais (PF)',
                        certidao_mandados: 'Certidão de Mandados de Prisão (BNMP/CNJ)',
                        certidao_improbidade: 'Certidão de Improbidade e Inelegibilidade (CNJ)',
                        certidao_trabalho_escravo: 'Certidão — Lista Suja do Trabalho Escravo',
                        certidao_ceis: 'Certidão de Inidôneos e Suspensos (CEIS)',
                        comprovante_receita: 'Comprovante — Situação Receita Federal',
                      };
                      const docUrl = `${API}/${admAlvo.id}/documento/${doc.id}`;
                      return (
                        <div key={doc.id} className="flex items-center gap-2 rounded-lg border border-slate-200 p-2.5">
                          <FileText className="w-4 h-4 shrink-0 text-[#C0392B]" />
                          <p className="text-[14px] font-medium text-slate-800 flex-1">{rot[doc.tipo] || doc.nome}</p>
                          <button onClick={() => abrirPdf(docUrl)} title="Visualizar"
                            className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500"><Eye className="w-4 h-4" /></button>
                          <button onClick={() => abrirPdf(docUrl, { download: true, nome: `${doc.tipo}.pdf` })} title="Baixar"
                            className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500"><Download className="w-4 h-4" /></button>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
              <p className="mt-4 text-[12px] text-slate-400 leading-snug">
                Itens 🔒 (ASO apto, eSocial S-2200) só são marcados aqui com confirmação humana — o sistema registra quem e quando.
                O S-2200 é transmissão real ao governo: prepare aqui, confirme a transmissão na Portte/eSocial.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Modal do dossiê / score */}
      {dossieAlvo && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setDossieAlvo(null)}>
          <div className="w-full max-w-lg max-h-[88vh] overflow-y-auto rounded-2xl bg-white shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between p-5 border-b border-slate-100 sticky top-0 bg-white">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-6 h-6" style={{ color: '#F97316' }} />
                <h2 className="text-lg font-bold text-slate-900">Dossiê — {dossieAlvo.nome}</h2>
              </div>
              <button onClick={() => setDossieAlvo(null)} className="text-slate-400 hover:text-slate-600"><X className="w-5 h-5" /></button>
            </div>
            <div className="p-5">
              <div className="mb-4 rounded-xl p-4 flex items-center justify-between" style={{ background: corNivel(dossieAlvo.nivel_score) + '18' }}>
                <div>
                  <p className="text-3xl font-extrabold" style={{ color: corNivel(dossieAlvo.nivel_score) }}>{dossieAlvo.score}</p>
                  <p className="text-[13px] font-semibold" style={{ color: corNivel(dossieAlvo.nivel_score) }}>
                    Risco {dossieAlvo.nivel_score} · recomendação: {dossieAlvo.recomendacao}
                  </p>
                </div>
                <button onClick={() => verificarCandidato(dossieAlvo)} className="text-[13px] text-slate-500 flex items-center gap-1 hover:text-slate-700">
                  <RefreshCw className="w-4 h-4" /> Reverificar
                </button>
              </div>
              {!dossie ? (
                <div className="py-8 text-center text-slate-400"><Loader2 className="w-6 h-6 animate-spin mx-auto" /></div>
              ) : (
                <>
                  <h3 className="text-[13px] font-bold uppercase tracking-wide text-slate-500 mb-2">Verificado</h3>
                  <div className="space-y-2 mb-4">
                    {(dossie.checks || []).map((c) => (
                      <div key={c.check_type} className="flex items-start gap-2 rounded-lg border border-slate-200 p-2.5">
                        {c.status === 'ok'
                          ? <UserCheck className="w-4 h-4 mt-0.5 shrink-0" style={{ color: '#059669' }} />
                          : <UserX className="w-4 h-4 mt-0.5 shrink-0" style={{ color: '#C0392B' }} />}
                        <div><p className="text-[14px] font-medium text-slate-800">{c.resumo}</p>
                          <p className="text-[11px] text-slate-400 font-mono">{c.provider}</p></div>
                      </div>
                    ))}
                  </div>
                  {(dossie.documentos || []).length > 0 && (
                    <>
                      <h3 className="text-[13px] font-bold uppercase tracking-wide text-slate-500 mb-2">Certidões &amp; documentos</h3>
                      <div className="space-y-2 mb-4">
                        {(dossie.documentos || []).map((doc) => {
                          const rot: Record<string, string> = {
                            certidao_cndt: 'Certidão Negativa de Débitos Trabalhistas (TST)',
                            certidao_jf: 'Certidão da Justiça Federal',
                            certidao_antecedentes: 'Certidão de Antecedentes Criminais (PF)',
                            certidao_mandados: 'Certidão de Mandados de Prisão (BNMP/CNJ)',
                            certidao_improbidade: 'Certidão de Improbidade e Inelegibilidade (CNJ)',
                            certidao_trabalho_escravo: 'Certidão — Lista Suja do Trabalho Escravo',
                            certidao_ceis: 'Certidão de Inidôneos e Suspensos (CEIS)',
                            comprovante_receita: 'Comprovante — Situação Receita Federal',
                          };
                          const docUrl = `${API}/${dossieAlvo.id}/documento/${doc.id}`;
                          return (
                            <div key={doc.id} className="flex items-center gap-2 rounded-lg border border-slate-200 p-2.5">
                              <FileText className="w-4 h-4 shrink-0 text-[#C0392B]" />
                              <p className="text-[14px] font-medium text-slate-800 flex-1">{rot[doc.tipo] || doc.nome}</p>
                              <button onClick={() => abrirPdf(docUrl)} title="Visualizar"
                                className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500"><Eye className="w-4 h-4" /></button>
                              <button onClick={() => abrirPdf(docUrl, { download: true, nome: `${doc.tipo}.pdf` })} title="Baixar"
                                className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500"><Download className="w-4 h-4" /></button>
                            </div>
                          );
                        })}
                      </div>
                    </>
                  )}
                  <h3 className="text-[13px] font-bold uppercase tracking-wide text-slate-500 mb-2">Aguardando integração</h3>
                  <div className="space-y-2">
                    {(dossie.pendentes || []).map((c) => (
                      <div key={c.check_type} className="flex items-start gap-2 rounded-lg border border-dashed border-slate-200 p-2.5 opacity-80">
                        <Clock className="w-4 h-4 mt-0.5 shrink-0 text-slate-400" />
                        <div><p className="text-[14px] text-slate-600">{c.resumo}</p>
                          <p className="text-[11px] text-slate-400 font-mono">{c.provider}</p></div>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
