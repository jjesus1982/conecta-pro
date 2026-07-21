'use client';

/**
 * Prestadores PJ — GERADOR de link de autocadastro (RH/DP).
 * O RH cria o prestador (nome + empresa + papel) → o sistema pré-semeia e devolve o link
 * individual `/autocadastro-pj?token=…` pronto pra mandar. Fim do pré-seed manual.
 */
import { useState, useEffect, useCallback } from 'react';
import { Loader2, Building2, Link2, Copy, Check, Plus, RefreshCw, UserPlus } from 'lucide-react';
import { toast } from 'sonner';

const API = '/api/v1/people-management/human-resources/prestadores-pj';

function getAuthHeaders(): Record<string, string> {
  let token: string | null = null;
  if (typeof window !== 'undefined') {
    try { token = localStorage.getItem('access_token') || localStorage.getItem('token'); } catch { token = null; }
  }
  return { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) };
}

interface Prestador {
  id: string; nome: string; papel: string | null; empresa: string | null;
  status: string; status_label: string; cnpj: string | null; token: string; link: string; criado_em: string | null;
}

function linkAbs(link: string) {
  return typeof window !== 'undefined' ? window.location.origin + link : link;
}

export default function PrestadoresPJPage() {
  const [lista, setLista] = useState<Prestador[]>([]);
  const [linksEmpresa, setLinksEmpresa] = useState<{ empresa: string; link: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [nome, setNome] = useState('');
  const [empresa, setEmpresa] = useState<'eletronica' | 'patrimonial'>('eletronica');
  const [papel, setPapel] = useState('');
  const [criando, setCriando] = useState(false);
  const [novoLink, setNovoLink] = useState<{ nome: string; empresa: string; link: string } | null>(null);
  const [copiado, setCopiado] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    setLoading(true);
    try {
      const [r, rl] = await Promise.all([
        fetch(API, { headers: getAuthHeaders() }),
        fetch(`${API}/links-empresa`, { headers: getAuthHeaders() }),
      ]);
      const d = await r.json();
      setLista(d.prestadores || []);
      const dl = await rl.json();
      setLinksEmpresa(dl.links || []);
    } catch { toast.error('Não foi possível carregar os prestadores.'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { carregar(); }, [carregar]);

  const copiar = (link: string, id: string) => {
    navigator.clipboard?.writeText(linkAbs(link));
    setCopiado(id); setTimeout(() => setCopiado(null), 2000);
    toast.success('Link copiado!');
  };

  const criar = async () => {
    if (!nome.trim()) { toast.error('Informe o nome do prestador.'); return; }
    setCriando(true); setNovoLink(null);
    try {
      const r = await fetch(API, { method: 'POST', headers: getAuthHeaders(), body: JSON.stringify({ nome: nome.trim(), empresa, papel: papel.trim() || null }) });
      if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || 'erro'); }
      const d = await r.json();
      setNovoLink({ nome: d.nome, empresa: d.empresa, link: d.link });
      setNome(''); setPapel('');
      carregar();
    } catch (e: unknown) { toast.error((e as Error).message || 'Não foi possível criar o prestador.'); }
    finally { setCriando(false); }
  };

  const regenerar = async (p: Prestador) => {
    try {
      const r = await fetch(`${API}/${p.id}/regenerar-link`, { method: 'POST', headers: getAuthHeaders() });
      if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || 'erro'); }
      toast.success('Novo link gerado (o antigo foi invalidado).');
      carregar();
    } catch (e: unknown) { toast.error((e as Error).message || 'Não foi possível regenerar.'); }
  };

  const empresaCor = (e: string | null) => /eletr/i.test(e || '') ? '#2563EB' : '#0E7C57';

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center gap-2 mb-1">
        <Link2 className="w-6 h-6 text-[#F97316]" />
        <h1 className="text-2xl font-bold text-slate-900">Prestadores PJ — gerador de link</h1>
      </div>
      <p className="text-[14px] text-slate-500 mb-6">
        Mande o <b>link da empresa certa</b> pro prestador — ele preenche tudo sozinho (nome, documento, PIX,
        selfie). A empresa vem do link (não da escolha dele). PJ = pago contra nota fiscal, nunca folha CLT.
      </p>

      {/* 2 LINKS FIXOS DE EMPRESA — "manda e esquece" */}
      <div className="rounded-2xl border-2 border-[#F97316]/30 bg-orange-50/40 p-5 mb-6">
        <div className="flex items-center gap-2 mb-3"><Link2 className="w-5 h-5 text-[#F97316]" />
          <h2 className="text-[15px] font-bold text-slate-800">Links de autocadastro (mande pro prestador)</h2></div>
        <div className="grid md:grid-cols-2 gap-3">
          {linksEmpresa.map((l) => (
            <div key={l.link} className="rounded-xl bg-white border border-slate-200 p-3.5">
              <p className="text-[13px] font-bold mb-1.5" style={{ color: /eletr/i.test(l.empresa) ? '#2563EB' : '#0E7C57' }}>
                <Building2 className="w-4 h-4 inline mr-1" />{l.empresa}</p>
              <div className="flex items-center gap-2">
                <code className="flex-1 text-[12px] text-slate-600 bg-slate-50 rounded-lg px-2.5 py-2 border border-slate-200 truncate">{linkAbs(l.link)}</code>
                <button onClick={() => copiar(l.link, 'emp-' + l.link)} className="rounded-lg bg-[#F97316] text-white text-[13px] font-semibold px-3 py-2 flex items-center gap-1 shrink-0">
                  {copiado === 'emp-' + l.link ? <><Check className="w-4 h-4" /> Copiado</> : <><Copy className="w-4 h-4" /> Copiar</>}</button>
              </div>
            </div>
          ))}
        </div>
        <p className="text-[12px] text-slate-400 mt-2">Esses 2 links são fixos e reutilizáveis — pode mandar pra quantos prestadores quiser.</p>
      </div>

      {/* Formulário (opcional: pré-cadastrar uma pessoa específica) */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 mb-6">
        <div className="flex items-center gap-2 mb-4"><UserPlus className="w-5 h-5 text-slate-400" />
          <h2 className="text-[15px] font-bold text-slate-700">Pré-cadastrar uma pessoa específica <span className="text-[12px] font-normal text-slate-400">(opcional)</span></h2></div>
        <div className="grid md:grid-cols-4 gap-3 items-end">
          <div className="md:col-span-2">
            <label className="text-[13px] text-slate-500">Nome completo</label>
            <input value={nome} onChange={(e) => setNome(e.target.value)} placeholder="Nome do prestador"
              className="w-full rounded-xl border-2 border-slate-200 px-3 py-2.5 text-[15px] outline-none focus:border-slate-400" />
          </div>
          <div>
            <label className="text-[13px] text-slate-500">Empresa</label>
            <select value={empresa} onChange={(e) => setEmpresa(e.target.value as 'eletronica' | 'patrimonial')}
              className="w-full rounded-xl border-2 border-slate-200 px-3 py-2.5 text-[15px] outline-none focus:border-slate-400 bg-white">
              <option value="eletronica">Conecta Mais Eletrônica</option>
              <option value="patrimonial">Conecta Mais Patrimonial</option>
            </select>
          </div>
          <div>
            <label className="text-[13px] text-slate-500">Papel (opcional)</label>
            <input value={papel} onChange={(e) => setPapel(e.target.value)} placeholder="dev / instalador…"
              className="w-full rounded-xl border-2 border-slate-200 px-3 py-2.5 text-[15px] outline-none focus:border-slate-400" />
          </div>
        </div>
        <button onClick={criar} disabled={criando}
          className="mt-4 rounded-xl bg-[#F97316] text-white text-[15px] font-bold px-5 py-2.5 flex items-center gap-2 disabled:opacity-50">
          {criando ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />} Gerar link
        </button>

        {novoLink && (
          <div className="mt-4 rounded-xl border-2 border-emerald-200 bg-emerald-50 p-4">
            <p className="text-[14px] font-semibold text-emerald-800 mb-1">✓ Link gerado para {novoLink.nome} · {novoLink.empresa}</p>
            <div className="flex items-center gap-2">
              <code className="flex-1 text-[13px] text-slate-700 bg-white rounded-lg px-3 py-2 border border-slate-200 truncate">{linkAbs(novoLink.link)}</code>
              <button onClick={() => copiar(novoLink.link, 'novo')} className="rounded-lg bg-emerald-600 text-white text-[14px] font-semibold px-3 py-2 flex items-center gap-1.5">
                {copiado === 'novo' ? <><Check className="w-4 h-4" /> Copiado</> : <><Copy className="w-4 h-4" /> Copiar</>}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Lista */}
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-[15px] font-bold text-slate-700">Prestadores ({lista.length})</h2>
        <button onClick={carregar} className="text-[13px] text-slate-500 flex items-center gap-1 hover:text-slate-700"><RefreshCw className="w-4 h-4" /> Atualizar</button>
      </div>
      {loading ? (
        <div className="py-10 text-center text-slate-400"><Loader2 className="w-7 h-7 animate-spin mx-auto" /></div>
      ) : lista.length === 0 ? (
        <p className="text-center text-slate-400 py-8">Nenhum prestador ainda. Crie o primeiro acima.</p>
      ) : (
        <div className="space-y-2">
          {lista.map((p) => (
            <div key={p.id} className="rounded-xl border border-slate-200 bg-white p-3.5 flex items-center gap-3 flex-wrap">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <p className="font-semibold text-slate-800">{p.nome}</p>
                  <span className="text-[11px] font-bold px-2 py-0.5 rounded-full text-white" style={{ background: empresaCor(p.empresa) }}>
                    <Building2 className="w-3 h-3 inline mr-0.5" />{p.empresa}</span>
                  {p.papel && <span className="text-[12px] text-slate-400">· {p.papel}</span>}
                </div>
                <p className="text-[12px] text-slate-400 mt-0.5">{p.cnpj ? `CNPJ: ${p.cnpj}` : 'sem CNPJ'}</p>
              </div>
              <span className="text-[12px] font-bold px-2.5 py-1 rounded-full"
                style={{ background: p.status === 'pj_ativo' ? '#E4F4EC' : '#FBEED9', color: p.status === 'pj_ativo' ? '#0E7C57' : '#B4690E' }}>
                {p.status_label}</span>
              {p.status !== 'pj_ativo' && (
                <div className="flex items-center gap-1.5">
                  <button onClick={() => copiar(p.link, p.id)} title="Copiar link"
                    className="rounded-lg border border-slate-200 text-slate-600 text-[13px] font-semibold px-3 py-1.5 flex items-center gap-1 hover:bg-slate-50">
                    {copiado === p.id ? <><Check className="w-4 h-4 text-emerald-600" /> Copiado</> : <><Copy className="w-4 h-4" /> Link</>}</button>
                  <button onClick={() => regenerar(p)} title="Gerar novo link (invalida o antigo)"
                    className="rounded-lg border border-slate-200 text-slate-400 p-1.5 hover:bg-slate-50"><RefreshCw className="w-4 h-4" /></button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
