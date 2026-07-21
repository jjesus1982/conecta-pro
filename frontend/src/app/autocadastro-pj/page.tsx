'use client';

/**
 * Autocadastro de PRESTADOR PJ — 3º trilho (separado de CANDIDATO/ATS e de CLT).
 * Link tokenizado INDIVIDUAL: o token identifica o registro pré-semeado (empresa de destino
 * já definida — a pessoa NÃO escolhe a empresa). Coleta dados PJ (documento flexível CNPJ ou
 * CPF+pendente, dados bancários/PIX, papel, uploads) + selfie. Ao concluir → 'pj_ativo'.
 * SEM funil de candidato, SEM admissão CLT, SEM eSocial/CTPS/holerite.
 */
import React, { Suspense, useState, useEffect } from 'react';
import { useSearchParams } from 'next/navigation';
import { api } from '@/lib/api';
import { FacialCapture, type FacialCaptureResult } from '@/components/ponto/FacialCapture';
import { Loader2, CheckCircle2, Building2, Camera, AlertTriangle, Upload, FileText } from 'lucide-react';

const MARCA = { azul: '#1E3A5F', azulMedio: '#2D5F8B', laranja: '#F97316', fundo: '#F1F5F9' };
const BASE = '/api/v1/people-management/portal/autocadastro-pj';

interface Dados { modo: string; nome: string | null; papel: string | null; empresa: string | null; ja_concluido: boolean }

function AvisoNavegadorInApp() {
  const [inApp, setInApp] = useState(false);
  const [copiado, setCopiado] = useState(false);
  useEffect(() => {
    const ua = navigator.userAgent || '';
    setInApp(/WhatsApp|Instagram|FBAN|FBAV|FB_IAB|Messenger|Line\/|Snapchat|Twitter|MicroMessenger/i.test(ua));
  }, []);
  if (!inApp) return null;
  const link = typeof window !== 'undefined' ? window.location.href : '';
  return (
    <div className="max-w-md mx-auto px-4 mb-3">
      <div className="rounded-2xl border-2 border-amber-400 bg-amber-50 p-4">
        <p className="text-base font-bold text-amber-900 flex items-center gap-2">
          <AlertTriangle className="w-6 h-6 shrink-0" /> Abra no navegador do celular
        </p>
        <p className="mt-2 text-[15px] leading-relaxed text-amber-900">
          Você abriu pelo navegador do app (WhatsApp/Instagram) — aqui a <b>câmera não funciona</b>.
          Toque nos <b>⋯</b> e escolha <b>“Abrir no Safari/Chrome”</b>, ou copie o link:
        </p>
        <button onClick={() => { navigator.clipboard?.writeText(link); setCopiado(true); }}
          className="mt-3 w-full rounded-xl bg-amber-600 text-white text-base font-bold py-3 active:scale-[0.99]">
          {copiado ? 'Link copiado! Cole no navegador' : 'Copiar o link'}
        </button>
      </div>
    </div>
  );
}

function Moldura({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen py-6 px-4" style={{ background: MARCA.fundo }}>
      <AvisoNavegadorInApp />
      <div className="max-w-md mx-auto rounded-3xl bg-white shadow-lg overflow-hidden">
        <div className="px-6 py-5 text-white" style={{ background: `linear-gradient(135deg, ${MARCA.azul}, ${MARCA.azulMedio})` }}>
          <div className="flex items-center gap-2">
            <Building2 className="w-6 h-6" />
            <span className="text-lg font-extrabold">Cadastro de Prestador (PJ)</span>
          </div>
          <p className="text-[13px] opacity-80 mt-0.5">Grupo Conecta Mais · prestação de serviços</p>
        </div>
        <div className="p-6">{children}</div>
      </div>
    </div>
  );
}

type Campo = { key: string; label: string; type?: string; placeholder?: string; obrig?: boolean; full?: boolean };

function Fluxo() {
  const params = useSearchParams();
  const token = params.get('token') || '';
  const [step, setStep] = useState<'carregando' | 'termo' | 'form' | 'facial' | 'done'>('carregando');
  const [dados, setDados] = useState<Dados | null>(null);
  const [termoTexto, setTermoTexto] = useState('');
  const [aceite, setAceite] = useState(false);
  const [temCnpj, setTemCnpj] = useState<boolean | null>(null);
  const [form, setForm] = useState<Record<string, string>>({});
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState('');
  const [empresaFinal, setEmpresaFinal] = useState('');
  const [sessao] = useState(() => 'pj-' + Math.random().toString(36).slice(2) + Date.now().toString(36));
  const [docStatus, setDocStatus] = useState<Record<string, string>>({});

  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    if (!token) { setErro('Link inválido (sem token). Peça o link do seu cadastro.'); setStep('termo'); return; }
    (async () => {
      try {
        const d = await api.get(`${BASE}/dados`, { params: { token } });
        const dd = d.data as Dados;
        setDados(dd);
        if (dd.papel) set('papel_pj', dd.papel);
        if (dd.ja_concluido) { setEmpresaFinal(dd.empresa || ''); setStep('done'); return; }
        const t = await api.get(`${BASE}/termo`, { params: { token } });
        setTermoTexto((t.data?.texto as string) || '');
        setStep('termo');
      } catch (e: unknown) {
        const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
        setErro(typeof msg === 'string' ? msg : 'Link inválido ou expirado. Peça o link do seu cadastro.');
        setStep('termo');
      }
    })();
  }, [token]);

  const enviarDocumento = async (tipo: string, file: File) => {
    setDocStatus((s) => ({ ...s, [tipo]: 'enviando' }));
    try {
      const fd = new FormData();
      fd.append('token', token); fd.append('sessao', sessao); fd.append('tipo', tipo); fd.append('arquivo', file);
      const r = await api.post(`${BASE}/documento`, fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      const campos = (r.data?.campos || {}) as Record<string, string>;
      setForm((f) => {
        const novo = { ...f };
        for (const [k, v] of Object.entries(campos)) if (['cnpj', 'razao_social'].includes(k) && v && !((novo[k] || '').trim())) novo[k] = String(v);
        return novo;
      });
      setDocStatus((s) => ({ ...s, [tipo]: 'ok' }));
    } catch { setDocStatus((s) => ({ ...s, [tipo]: 'erro' })); }
  };

  const CAMPOS_CONTATO: Campo[] = [
    { key: 'telefone', label: 'Telefone/WhatsApp', obrig: true, full: true },
    { key: 'email', label: 'E-mail', type: 'email', obrig: true, full: true },
  ];
  const CAMPOS_PAGAMENTO: Campo[] = [
    { key: 'pix_key', label: 'Chave PIX (para receber)', obrig: true, full: true },
    { key: 'banco', label: 'Banco' },
    { key: 'agencia', label: 'Agência' },
    { key: 'conta', label: 'Conta' },
  ];

  const irParaFacial = () => {
    setErro('');
    if (dados?.modo === 'livre' && !(form.nome || '').trim()) { setErro('Informe seu nome completo.'); return; }
    if (temCnpj === null) { setErro('Informe se você já tem CNPJ.'); return; }
    const cnpjDig = (form.cnpj || '').replace(/\D/g, '');
    if (temCnpj && cnpjDig.length !== 14) { setErro('Informe um CNPJ válido (14 dígitos) ou marque "ainda não tenho CNPJ".'); return; }
    if (temCnpj && !(form.razao_social || '').trim()) { setErro('Informe a razão social da sua empresa.'); return; }
    const falta = CAMPOS_CONTATO.concat(CAMPOS_PAGAMENTO).filter((c) => c.obrig && !(form[c.key] || '').trim());
    if (falta.length) { setErro(`Preencha: ${falta.map((c) => c.label).join(', ')}`); return; }
    setStep('facial');
  };

  const concluir = async (r: FacialCaptureResult) => {
    if (!r.descriptor?.length) { setErro('Não consegui ler seu rosto. Tente em local iluminado.'); return; }
    setEnviando(true); setErro('');
    try {
      const resp = await api.post(`${BASE}/concluir`, {
        token,
        nome: dados?.modo === 'livre' ? (form.nome || null) : null,
        cnpj: temCnpj ? form.cnpj : null,
        cnpj_pendente: !temCnpj,
        razao_social: form.razao_social || null,
        regime_tributario: form.regime_tributario || null,
        inscricao_municipal: form.inscricao_municipal || null,
        telefone: form.telefone, email: form.email,
        pix_key: form.pix_key, banco: form.banco || null, agencia: form.agencia || null, conta: form.conta || null,
        papel_pj: form.papel_pj || null,
        face_descriptor: r.descriptor, sessao,
      });
      setEmpresaFinal((resp.data?.empresa as string) || dados?.empresa || '');
      setStep('done');
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setErro(typeof msg === 'string' ? msg : 'Não foi possível concluir. Verifique os dados.');
      setStep('form');
    } finally { setEnviando(false); }
  };

  const alerta = erro ? <div className="mb-4 rounded-xl bg-red-50 border-2 border-red-200 text-red-700 text-[15px] font-medium p-3.5">{erro}</div> : null;
  const inputCls = 'w-full rounded-xl border-2 border-slate-200 px-3.5 py-3 text-[16px] focus:border-slate-400 outline-none';

  if (step === 'carregando') {
    return <Moldura><div className="py-12 text-center text-slate-400"><Loader2 className="w-8 h-8 animate-spin mx-auto" /></div></Moldura>;
  }

  if (step === 'done') {
    return (
      <Moldura>
        <div className="text-center">
          <CheckCircle2 className="w-20 h-20 text-emerald-500 mx-auto mb-4" />
          <h1 className="text-2xl font-extrabold mb-1" style={{ color: MARCA.azul }}>Cadastro concluído!</h1>
          <p className="text-[15px] leading-relaxed text-slate-500 mb-2">
            Você está registrado como <b className="text-slate-700">prestador PJ</b>
            {empresaFinal ? <> da <b className="text-slate-700">{empresaFinal}</b></> : null}.
          </p>
          <p className="text-[14px] text-slate-400">Os pagamentos serão feitos por PIX, contra nota fiscal de serviço.</p>
        </div>
      </Moldura>
    );
  }

  if (step === 'facial') {
    return (
      <Moldura>
        <div className="text-center">
          <div className="flex items-center justify-center gap-2 mb-1">
            <Camera className="w-7 h-7" style={{ color: MARCA.laranja }} />
            <h1 className="text-2xl font-extrabold" style={{ color: MARCA.azul }}>Tire sua selfie</h1>
          </div>
          <p className="text-[15px] leading-relaxed text-slate-500 mb-5">Centralize o rosto no círculo — a captura é automática. Ela conclui seu cadastro.</p>
          {alerta}
          <FacialCapture onCapture={concluir} onError={(m) => setErro(m)} />
          {enviando && <p className="mt-3 text-[15px] text-slate-500 flex items-center justify-center gap-2"><Loader2 className="w-5 h-5 animate-spin" /> Enviando cadastro…</p>}
          <button onClick={() => setStep('form')} className="mt-4 text-[14px] text-slate-400 underline">Voltar aos dados</button>
        </div>
      </Moldura>
    );
  }

  if (step === 'termo') {
    return (
      <Moldura>
        {dados && (
          <div className="mb-4 rounded-xl p-3.5" style={{ background: '#EAF1F8' }}>
            <p className="text-[13px] font-bold uppercase tracking-wide" style={{ color: MARCA.azulMedio }}>Empresa contratante</p>
            <p className="text-[17px] font-extrabold" style={{ color: MARCA.azul }}>{dados.empresa || '—'}</p>
            <p className="text-[14px] text-slate-500">{dados.nome ? `${dados.nome}${dados.papel ? ` · ${dados.papel}` : ''}` : 'Cadastro de prestador de serviços'}</p>
          </div>
        )}
        <h1 className="text-xl font-extrabold mb-2" style={{ color: MARCA.azul }}>Termo de prestação de serviços</h1>
        {alerta}
        <div className="rounded-xl border-2 border-slate-200 p-4 text-[14px] leading-relaxed text-slate-600 whitespace-pre-line max-h-60 overflow-y-auto mb-3">
          {termoTexto || 'Carregando termo…'}
        </div>
        <label className="flex items-start gap-2.5 mb-4 cursor-pointer">
          <input type="checkbox" checked={aceite} onChange={(e) => setAceite(e.target.checked)} className="mt-1 w-5 h-5" />
          <span className="text-[15px] text-slate-700">Li e concordo com o termo acima.</span>
        </label>
        <button onClick={() => { if (!aceite) { setErro('Você precisa aceitar o termo.'); return; } setErro(''); setStep('form'); }}
          disabled={!token || !dados}
          className="w-full rounded-xl text-white text-[17px] font-bold py-3.5 active:scale-[0.99] disabled:opacity-50"
          style={{ background: MARCA.laranja }}>Continuar</button>
      </Moldura>
    );
  }

  // step === 'form'
  return (
    <Moldura>
      {dados && (
        <div className="mb-4 rounded-xl p-3 flex items-center gap-2" style={{ background: '#EAF1F8' }}>
          <Building2 className="w-5 h-5" style={{ color: MARCA.azulMedio }} />
          <div><p className="text-[13px] font-bold" style={{ color: MARCA.azul }}>{dados.empresa}</p>
            <p className="text-[12px] text-slate-500">{dados.nome ? `${dados.nome}${dados.papel ? ` · ${dados.papel}` : ''}` : 'Prestador de serviços'}</p></div>
        </div>
      )}
      {alerta}

      {/* Modo LIVRE (link de empresa): a pessoa preenche o próprio nome */}
      {dados?.modo === 'livre' && (
        <div className="mb-4">
          <h2 className="text-[14px] font-bold uppercase tracking-wide text-slate-500 mb-2">Seus dados</h2>
          <label className="text-[13px] text-slate-500">Nome completo *</label>
          <input value={form.nome || ''} onChange={(e) => set('nome', e.target.value)} className={inputCls} placeholder="Seu nome completo" />
        </div>
      )}

      {/* Documento flexível: tem CNPJ ou não */}
      <h2 className="text-[14px] font-bold uppercase tracking-wide text-slate-500 mb-2">Documento da empresa</h2>
      <div className="flex gap-2 mb-3">
        <button onClick={() => setTemCnpj(true)} className="flex-1 rounded-xl border-2 py-2.5 text-[15px] font-semibold"
          style={{ borderColor: temCnpj === true ? MARCA.laranja : '#E2E8F0', color: temCnpj === true ? MARCA.laranja : '#64748B' }}>Já tenho CNPJ</button>
        <button onClick={() => setTemCnpj(false)} className="flex-1 rounded-xl border-2 py-2.5 text-[15px] font-semibold"
          style={{ borderColor: temCnpj === false ? MARCA.laranja : '#E2E8F0', color: temCnpj === false ? MARCA.laranja : '#64748B' }}>Ainda não tenho</button>
      </div>
      {temCnpj === true && (
        <div className="grid grid-cols-2 gap-3 mb-4">
          <div className="col-span-2"><label className="text-[13px] text-slate-500">CNPJ *</label>
            <input value={form.cnpj || ''} onChange={(e) => set('cnpj', e.target.value)} className={inputCls} placeholder="00.000.000/0000-00" /></div>
          <div className="col-span-2"><label className="text-[13px] text-slate-500">Razão social *</label>
            <input value={form.razao_social || ''} onChange={(e) => set('razao_social', e.target.value)} className={inputCls} /></div>
          <div><label className="text-[13px] text-slate-500">Regime</label>
            <input value={form.regime_tributario || ''} onChange={(e) => set('regime_tributario', e.target.value)} className={inputCls} placeholder="MEI / Simples…" /></div>
          <div><label className="text-[13px] text-slate-500">Inscr. municipal</label>
            <input value={form.inscricao_municipal || ''} onChange={(e) => set('inscricao_municipal', e.target.value)} className={inputCls} /></div>
        </div>
      )}
      {temCnpj === false && (
        <p className="mb-4 text-[13px] text-slate-500 bg-amber-50 border border-amber-200 rounded-xl p-3">
          Sem problema — você se cadastra agora com CPF e recebe no PIX do CPF. Quando abrir o CNPJ, a gente atualiza.
        </p>
      )}

      <h2 className="text-[14px] font-bold uppercase tracking-wide text-slate-500 mb-2">Contato</h2>
      <div className="grid grid-cols-2 gap-3 mb-4">
        {CAMPOS_CONTATO.map((c) => (
          <div key={c.key} className={c.full ? 'col-span-2' : ''}>
            <label className="text-[13px] text-slate-500">{c.label}{c.obrig ? ' *' : ''}</label>
            <input type={c.type || 'text'} value={form[c.key] || ''} onChange={(e) => set(c.key, e.target.value)} className={inputCls} /></div>
        ))}
      </div>

      <h2 className="text-[14px] font-bold uppercase tracking-wide text-slate-500 mb-2">Recebimento</h2>
      <div className="grid grid-cols-2 gap-3 mb-4">
        {CAMPOS_PAGAMENTO.map((c) => (
          <div key={c.key} className={c.full ? 'col-span-2' : ''}>
            <label className="text-[13px] text-slate-500">{c.label}{c.obrig ? ' *' : ''}</label>
            <input value={form[c.key] || ''} onChange={(e) => set(c.key, e.target.value)} className={inputCls} /></div>
        ))}
      </div>

      <h2 className="text-[14px] font-bold uppercase tracking-wide text-slate-500 mb-2">Documentos (opcional)</h2>
      <div className="space-y-2 mb-5">
        {[['cartao_cnpj', 'Cartão CNPJ'], ['contrato_social', 'Contrato social'], ['rg', 'RG / CPF']].map(([tipo, lbl]) => (
          <label key={tipo} className="flex items-center gap-2 rounded-xl border-2 border-dashed border-slate-200 p-3 cursor-pointer">
            {docStatus[tipo] === 'enviando' ? <Loader2 className="w-5 h-5 animate-spin text-slate-400" /> :
              docStatus[tipo] === 'ok' ? <CheckCircle2 className="w-5 h-5 text-emerald-500" /> :
              docStatus[tipo] === 'erro' ? <FileText className="w-5 h-5 text-red-400" /> : <Upload className="w-5 h-5 text-slate-400" />}
            <span className="text-[15px] text-slate-600 flex-1">{lbl}</span>
            <input type="file" accept="image/*,application/pdf" className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) enviarDocumento(tipo, f); }} />
          </label>
        ))}
      </div>

      <button onClick={irParaFacial} disabled={enviando}
        className="w-full rounded-xl text-white text-[17px] font-bold py-3.5 active:scale-[0.99] disabled:opacity-50"
        style={{ background: MARCA.laranja }}>Continuar para a selfie</button>
    </Moldura>
  );
}

export default function AutocadastroPJPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center" style={{ background: MARCA.fundo }}><Loader2 className="w-8 h-8 animate-spin text-slate-400" /></div>}>
      <Fluxo />
    </Suspense>
  );
}
