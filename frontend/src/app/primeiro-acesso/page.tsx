'use client';

/**
 * PRIMEIRO ACESSO DO FUNCIONÁRIO (link público) — fluxo do Jordan (2026-07-21).
 * Tela 1: CPF (obrigatório, âncora de identidade — CPF de fora = barrado).
 * Tela 2: dados já preenchidos + completa o que falta (100% p/ avançar).
 * Tela 3: cadastra o rosto → senha vira o CPF → cai no Portal do Funcionário.
 * Re-login depois: e-mail + CPF, ou pelo rosto (tela de login).
 */
import { useState, useCallback } from 'react';
import { Loader2, ShieldCheck, IdCard, ArrowRight, ScanFace, Search } from 'lucide-react';
import { FacialCapture, type FacialCaptureResult } from '@/components/ponto/FacialCapture';
import { useAuth } from '@/hooks/useAuth';

const BASE = '/api/v1/people-management/portal/primeiro-acesso';

// Campos do cadastro (rótulo + agrupamento). Obrigatório = vier em `faltantes`.
const CAMPOS: { key: string; label: string; grupo: 'contato' | 'endereco' | 'doc'; tipo?: string }[] = [
  { key: 'telefone', label: 'Telefone / celular', grupo: 'contato' },
  { key: 'cep', label: 'CEP', grupo: 'endereco' },
  { key: 'logradouro', label: 'Endereço (rua/avenida)', grupo: 'endereco' },
  { key: 'numero', label: 'Número', grupo: 'endereco' },
  { key: 'bairro', label: 'Bairro', grupo: 'endereco' },
  { key: 'cidade', label: 'Cidade', grupo: 'endereco' },
  { key: 'uf', label: 'UF', grupo: 'endereco' },
  { key: 'nome_mae', label: 'Nome da mãe', grupo: 'doc' },
  { key: 'nome_pai', label: 'Nome do pai', grupo: 'doc' },
  { key: 'naturalidade', label: 'Naturalidade (cidade de nascimento)', grupo: 'doc' },
  { key: 'nacionalidade', label: 'Nacionalidade', grupo: 'doc' },
  { key: 'rg', label: 'RG', grupo: 'doc' },
  { key: 'estado_civil', label: 'Estado civil', grupo: 'doc' },
  { key: 'pis', label: 'PIS/PASEP', grupo: 'doc' },
];

export default function PrimeiroAcessoPage() {
  const { login } = useAuth();
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [cpf, setCpf] = useState('');
  const [token, setToken] = useState('');
  const [nome, setNome] = useState('');
  const [email, setEmail] = useState('');
  const [cargo, setCargo] = useState('');
  const [form, setForm] = useState<Record<string, string>>({});
  const [faltantes, setFaltantes] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [buscandoPis, setBuscandoPis] = useState(false);
  const [erro, setErro] = useState('');

  const soDigitos = (v: string) => v.replace(/\D/g, '');
  const cpfMask = (v: string) => {
    const d = soDigitos(v).slice(0, 11);
    return d.replace(/(\d{3})(\d)/, '$1.$2').replace(/(\d{3})(\d)/, '$1.$2').replace(/(\d{3})(\d{1,2})$/, '$1-$2');
  };
  const set = (k: string, v: string) => setForm((p) => ({ ...p, [k]: v }));

  // ── Tela 1: CPF → identifica ──────────────────────────────────────────────
  const identificar = useCallback(async () => {
    setErro('');
    if (soDigitos(cpf).length !== 11) { setErro('Informe os 11 dígitos do CPF.'); return; }
    setLoading(true);
    try {
      const r = await fetch(`${BASE}/identificar`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cpf: soDigitos(cpf) }),
      });
      const d = await r.json();
      if (!r.ok) { setErro(d.detail || 'CPF não encontrado.'); return; }
      setToken(d.token); setNome(d.nome); setEmail(d.email); setCargo(d.cargo || '');
      setForm({ ...(d.dados || {}) });
      setFaltantes(new Set((d.faltantes || []).map((f: { campo: string }) => f.campo)));
      setStep(2);
    } catch { setErro('Falha de conexão. Tente de novo.'); }
    finally { setLoading(false); }
  }, [cpf]);

  const buscarPis = async () => {
    setBuscandoPis(true); setErro('');
    try {
      const r = await fetch(`${BASE}/buscar-pis`, { method: 'POST', headers: { Authorization: `Bearer ${token}` } });
      const d = await r.json();
      if (d.encontrado && d.pis) { set('pis', d.pis); }
      else { setErro(d.mensagem || 'PIS não encontrado — preencha manualmente ou deixe em branco.'); }
    } catch { setErro('Não foi possível buscar o PIS agora.'); }
    finally { setBuscandoPis(false); }
  };

  // ── Tela 2: completa o cadastro ───────────────────────────────────────────
  const completar = useCallback(async () => {
    setErro('');
    const faltaAgora = [...faltantes].filter((k) => k !== 'pis' && !String(form[k] || '').trim());
    if (faltaAgora.length) {
      setErro('Preencha todos os campos obrigatórios destacados.');
      return;
    }
    setLoading(true);
    try {
      const campos: Record<string, string> = {};
      for (const c of CAMPOS) if (String(form[c.key] || '').trim()) campos[c.key] = String(form[c.key]).trim();
      const r = await fetch(`${BASE}/completar`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ campos }),
      });
      const d = await r.json();
      if (!r.ok) { setErro(d.detail || 'Não foi possível salvar.'); return; }
      setFaltantes(new Set((d.faltantes || []).map((f: { campo: string }) => f.campo)));
      if (d.cadastro_completo) setStep(3);
      else setErro('Ainda faltam campos obrigatórios.');
    } catch { setErro('Falha ao salvar. Tente de novo.'); }
    finally { setLoading(false); }
  }, [faltantes, form, token]);

  // ── Tela 3: rosto → conclui → loga → portal ───────────────────────────────
  const aoCapturarRosto = useCallback(async (res: FacialCaptureResult) => {
    if (!res?.descriptor?.length) { setErro('Não deu pra ler o rosto. Tente de novo.'); return; }
    setLoading(true); setErro('');
    try {
      const r = await fetch(`${BASE}/concluir`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ descriptor: res.descriptor }),
      });
      const d = await r.json();
      if (!r.ok) { setErro(d.detail || 'Não foi possível concluir.'); setLoading(false); return; }
      // senha = CPF → loga no fluxo normal e entra no portal
      const ok = await login({ email: d.email, password: soDigitos(cpf) });
      if (ok.success) window.location.href = d.portal_url || '/modulos/meu-espaco';
      else { setErro('Cadastro concluído, mas o login falhou. Vá em Entrar e use e-mail + CPF.'); setLoading(false); }
    } catch { setErro('Falha ao concluir. Tente de novo.'); setLoading(false); }
  }, [token, cpf, login]);

  const grupo = (g: 'contato' | 'endereco' | 'doc') => CAMPOS.filter((c) => c.grupo === g);
  const inputCls = (k: string) =>
    `w-full rounded-xl border-2 px-3 py-2.5 text-[15px] outline-none focus:border-[#16277D] ${
      faltantes.has(k) && !String(form[k] || '').trim() ? 'border-orange-300 bg-orange-50/40' : 'border-slate-200'
    }`;

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col items-center px-4 py-8">
      <div className="w-full max-w-lg">
        <div className="flex items-center gap-2 mb-6 justify-center">
          <ShieldCheck className="w-6 h-6 text-[#F26522]" />
          <h1 className="text-xl font-bold text-[#16277D]">Primeiro acesso — Portal do Funcionário</h1>
        </div>

        {/* passos */}
        <div className="flex items-center justify-center gap-2 mb-6">
          {[1, 2, 3].map((n) => (
            <div key={n} className={`h-2 rounded-full transition-all ${step >= n ? 'w-8 bg-[#F26522]' : 'w-2 bg-slate-300'}`} />
          ))}
        </div>

        {erro && <div className="mb-4 rounded-xl bg-red-50 border border-red-200 text-red-700 text-[14px] px-4 py-3">{erro}</div>}

        {/* ── TELA 1 ── */}
        {step === 1 && (
          <div className="rounded-2xl bg-white border border-slate-200 p-6 shadow-sm">
            <div className="flex items-center gap-2 mb-2"><IdCard className="w-5 h-5 text-[#16277D]" />
              <h2 className="text-[16px] font-bold text-slate-800">Informe seu CPF</h2></div>
            <p className="text-[13px] text-slate-500 mb-4">Use o CPF cadastrado na empresa. É por ele que a gente confirma que é você.</p>
            <input inputMode="numeric" value={cpfMask(cpf)} onChange={(e) => setCpf(e.target.value)}
              placeholder="000.000.000-00" className="w-full rounded-xl border-2 border-slate-200 px-3 py-3 text-[18px] tracking-wide outline-none focus:border-[#16277D] text-center"
              onKeyDown={(e) => e.key === 'Enter' && identificar()} />
            <button onClick={identificar} disabled={loading}
              className="mt-4 w-full rounded-xl bg-[#F26522] text-white text-[16px] font-bold py-3 flex items-center justify-center gap-2 disabled:opacity-50">
              {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <>Continuar <ArrowRight className="w-5 h-5" /></>}
            </button>
          </div>
        )}

        {/* ── TELA 2 ── */}
        {step === 2 && (
          <div className="rounded-2xl bg-white border border-slate-200 p-6 shadow-sm">
            <p className="text-[15px] text-slate-800 mb-1">Olá, <b>{nome}</b> 👋</p>
            <p className="text-[13px] text-slate-500 mb-5">{cargo && `${cargo} · `}Confira seus dados e <b>complete o que falta</b> (campos em laranja). Só avança com tudo preenchido.</p>

            {(['contato', 'endereco', 'doc'] as const).map((g) => (
              <div key={g} className="mb-4">
                <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-2">
                  {g === 'contato' ? 'Contato' : g === 'endereco' ? 'Endereço' : 'Documentos e filiação'}
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {grupo(g).map((c) => (
                    <div key={c.key} className={c.key === 'nome_mae' || c.key === 'nome_pai' || c.key === 'logradouro' ? 'sm:col-span-2' : ''}>
                      <label className="text-[12px] text-slate-500">
                        {c.label}{faltantes.has(c.key) && c.key !== 'pis' && <span className="text-[#F26522]"> *</span>}
                      </label>
                      {c.key === 'pis' ? (
                        <div className="flex gap-2">
                          <input value={form.pis || ''} onChange={(e) => set('pis', e.target.value)} className={inputCls('pis')} inputMode="numeric" />
                          {faltantes.has('pis') && (
                            <button onClick={buscarPis} disabled={buscandoPis} title="Buscar meu PIS"
                              className="shrink-0 rounded-xl border-2 border-[#16277D] text-[#16277D] px-3 flex items-center gap-1 text-[13px] font-semibold disabled:opacity-50">
                              {buscandoPis ? <Loader2 className="w-4 h-4 animate-spin" /> : <><Search className="w-4 h-4" /> Buscar</>}
                            </button>
                          )}
                        </div>
                      ) : (
                        <input value={form[c.key] || ''} onChange={(e) => set(c.key, e.target.value)} className={inputCls(c.key)} />
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}
            <p className="text-[12px] text-slate-400 mb-3">PIS é opcional — se não souber, toque em Buscar ou deixe em branco.</p>
            <button onClick={completar} disabled={loading}
              className="w-full rounded-xl bg-[#F26522] text-white text-[16px] font-bold py-3 flex items-center justify-center gap-2 disabled:opacity-50">
              {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <>Salvar e continuar <ArrowRight className="w-5 h-5" /></>}
            </button>
          </div>
        )}

        {/* ── TELA 3 ── */}
        {step === 3 && (
          <div className="rounded-2xl bg-white border border-slate-200 p-6 shadow-sm">
            <div className="flex items-center gap-2 mb-2"><ScanFace className="w-5 h-5 text-[#16277D]" />
              <h2 className="text-[16px] font-bold text-slate-800">Cadastre seu rosto</h2></div>
            <p className="text-[13px] text-slate-500 mb-4">É como você vai bater o ponto e entrar no portal. Olhe pra câmera num lugar iluminado.</p>
            {loading ? (
              <div className="py-12 text-center text-slate-500"><Loader2 className="w-8 h-8 animate-spin mx-auto mb-2" />Concluindo…</div>
            ) : (
              <FacialCapture onCapture={aoCapturarRosto} onError={(e) => setErro(e)} />
            )}
          </div>
        )}

        <p className="text-center text-[12px] text-slate-400 mt-6">Conecta PRO · Portal do Funcionário</p>
      </div>
    </div>
  );
}
