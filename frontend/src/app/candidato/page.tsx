'use client';

/**
 * Autocadastro de CANDIDATO (Funil de candidato — Fase 1). Uma jornada:
 *   1) dados (rigor eSocial) + cargo pleiteado + chave PIX
 *   2) selfie (facial) na mesma tela
 *   3) candidatura recebida → acompanhar status (o candidato NÃO acessa o portal
 *      antes de ser aprovado pelo RH).
 * O registro fica isolado da produção (status='candidato'). Identidade Conecta Mais.
 */
import React, { Suspense, useState, useEffect, useRef } from 'react';
import { useSearchParams } from 'next/navigation';
import { api } from '@/lib/api';
import { FacialCapture, type FacialCaptureResult } from '@/components/ponto/FacialCapture';
import { Loader2, CheckCircle2, Briefcase, Camera, AlertTriangle, ShieldCheck } from 'lucide-react';

const MARCA = {
  azul: '#1E3A5F',
  azulMedio: '#2D5F8B',
  laranja: '#F97316',
  fundo: '#F1F5F9',
};

const BASE = '/api/v1/people-management/portal/candidato';

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
          Você abriu pelo navegador do app (WhatsApp/Instagram) — aqui a <b>câmera não funciona</b> e
          você não conseguirá tirar a selfie. Toque nos <b>⋯</b> e escolha <b>“Abrir no Safari”</b> (iPhone)
          ou <b>“Abrir no Chrome”</b> (Android). Ou copie o link:
        </p>
        <button
          onClick={() => { navigator.clipboard?.writeText(link); setCopiado(true); }}
          className="mt-3 w-full rounded-xl bg-amber-600 text-white text-base font-bold py-3 active:scale-[0.99]"
        >
          {copiado ? 'Link copiado! Cole no navegador' : 'Copiar o link'}
        </button>
      </div>
    </div>
  );
}

type Campo = { key: string; label: string; type?: string; placeholder?: string; obrig?: boolean; full?: boolean };
type Secao = { titulo: string; campos: Campo[] };

const SECOES: Secao[] = [
  {
    titulo: 'Identificação',
    campos: [
      { key: 'nome', label: 'Nome completo', obrig: true, full: true },
      { key: 'email', label: 'E-mail', type: 'email', obrig: true, full: true },
      { key: 'cpf', label: 'CPF', obrig: true },
      { key: 'data_nascimento', label: 'Nascimento', type: 'date', obrig: true },
      { key: 'telefone', label: 'Telefone/WhatsApp', obrig: true, full: true },
    ],
  },
  {
    titulo: 'Documentos e dados pessoais',
    campos: [
      { key: 'rg', label: 'RG', obrig: true },
      { key: 'pis', label: 'PIS/PASEP (opcional)', obrig: false },
      { key: 'estado_civil', label: 'Estado civil', obrig: true, placeholder: 'solteiro / casado…' },
      { key: 'nacionalidade', label: 'Nacionalidade', obrig: true, placeholder: 'Brasileira' },
      { key: 'naturalidade', label: 'Naturalidade (cidade natal)', obrig: true },
      { key: 'uf_nascimento', label: 'UF de nascimento', obrig: true, placeholder: 'AM' },
      { key: 'nome_mae', label: 'Nome da mãe', obrig: true, full: true },
      { key: 'nome_pai', label: 'Nome do pai', obrig: true, full: true },
    ],
  },
  {
    titulo: 'Endereço',
    campos: [
      { key: 'cep', label: 'CEP', obrig: true },
      { key: 'numero', label: 'Número' },
      { key: 'logradouro', label: 'Rua / Avenida', obrig: true, full: true },
      { key: 'bairro', label: 'Bairro', obrig: true },
      { key: 'cidade', label: 'Cidade', obrig: true },
      { key: 'uf', label: 'UF', placeholder: 'AM' },
    ],
  },
  {
    titulo: 'Recebimento (sua chave PIX)',
    campos: [
      { key: 'pix_key', label: 'Chave PIX (para receber salário)', obrig: true, full: true },
    ],
  },
];

const CAMPOS: Campo[] = SECOES.flatMap((s) => s.campos);

interface Cargo { nome: string }
interface Resultado {
  protocolo: string; nome: string; cargo_pleiteado: string; status_label: string; facial_ok: boolean;
}

function inputCls() {
  return 'w-full rounded-xl border-2 border-slate-200 bg-white px-3.5 py-3 text-base text-slate-900 placeholder:text-slate-400 focus:border-[#F97316] focus:outline-none';
}

function Moldura({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen w-full" style={{ background: MARCA.fundo }}>
      <div className="max-w-md mx-auto px-4 pb-10">
        <header className="pt-7 pb-5 flex flex-col items-center">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/images/logo-marca-v2.png" alt="Conecta Mais" className="h-14 w-auto" />
          <div className="mt-4 h-1.5 w-24 rounded-full" style={{ background: MARCA.laranja }} />
        </header>
        <div className="rounded-3xl bg-white shadow-sm border border-slate-200 p-5 sm:p-6">{children}</div>
      </div>
    </div>
  );
}

/** Assinatura em canvas (rubrica), touch e mouse. Exporta PNG base64 no onChange. */
function SignaturePad({ onChange }: { onChange: (png: string) => void }): React.JSX.Element {
  const ref = React.useRef<HTMLCanvasElement>(null);
  const desenhando = React.useRef(false);
  const pos = (e: React.PointerEvent) => {
    const c = ref.current!; const r = c.getBoundingClientRect();
    return { x: (e.clientX - r.left) * (c.width / r.width), y: (e.clientY - r.top) * (c.height / r.height) };
  };
  const start = (e: React.PointerEvent) => {
    desenhando.current = true; const ctx = ref.current!.getContext('2d')!;
    const p = pos(e); ctx.beginPath(); ctx.moveTo(p.x, p.y);
  };
  const move = (e: React.PointerEvent) => {
    if (!desenhando.current) return; e.preventDefault();
    const ctx = ref.current!.getContext('2d')!; ctx.lineWidth = 2.5; ctx.lineCap = 'round'; ctx.strokeStyle = '#1E3A5F';
    const p = pos(e); ctx.lineTo(p.x, p.y); ctx.stroke();
  };
  const end = () => { if (desenhando.current) { desenhando.current = false; onChange(ref.current!.toDataURL('image/png')); } };
  const limpar = () => { const c = ref.current!; c.getContext('2d')!.clearRect(0, 0, c.width, c.height); onChange(''); };
  return (
    <div>
      <canvas ref={ref} width={520} height={160}
        className="w-full rounded-xl border-2 border-slate-200 bg-white touch-none"
        style={{ height: 130 }}
        onPointerDown={start} onPointerMove={move} onPointerUp={end} onPointerLeave={end} />
      <button type="button" onClick={limpar} className="mt-1.5 text-[13px] text-slate-400 underline">Limpar assinatura</button>
    </div>
  );
}

function Fluxo() {
  const params = useSearchParams();
  const token = params.get('token') || '';
  const [step, setStep] = useState<'termo' | 'form' | 'facial' | 'done'>('termo');
  const [form, setForm] = useState<Record<string, string>>({});
  const [cargo, setCargo] = useState('');
  const [cargos, setCargos] = useState<Cargo[]>([]);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState('');
  const [res, setRes] = useState<Resultado | null>(null);
  const [cepLoading, setCepLoading] = useState(false);
  // Fase 6.1 — consentimento (termo assinado antes do cadastro)
  const [termoTexto, setTermoTexto] = useState('');
  const [aceite, setAceite] = useState(false);
  const [rubrica, setRubrica] = useState('');
  // Fase 6.1 — anexar documentos que se preenchem sozinhos
  const [sessao] = useState(() => 'cand-' + Math.random().toString(36).slice(2) + Date.now().toString(36));
  const [docStatus, setDocStatus] = useState<Record<string, string>>({});
  const [dependentes, setDependentes] = useState<{ nome: string; nascimento: string }[]>([]);

  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));

  const CAMPO_KEYS = new Set(CAMPOS.map((c) => c.key));

  const enviarDocumento = async (tipo: string, file: File) => {
    setDocStatus((s) => ({ ...s, [tipo]: 'enviando' }));
    setErro('');
    try {
      const fd = new FormData();
      fd.append('token', token); fd.append('sessao', sessao); fd.append('tipo', tipo); fd.append('arquivo', file);
      const r = await api.post(`${BASE}/documento`, fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      const campos = (r.data?.campos || {}) as Record<string, string>;
      // certidão de nascimento → vira dependente (salário-família)
      if (tipo === 'certidao_nascimento' && (campos.dependente_nome || campos.dependente_nascimento)) {
        setDependentes((d) => [...d, { nome: campos.dependente_nome || '', nascimento: campos.dependente_nascimento || '' }]);
      }
      // demais campos → mesclam no formulário (só os que existem no form e ainda vazios)
      setForm((f) => {
        const novo = { ...f };
        for (const [k, v] of Object.entries(campos)) {
          if (CAMPO_KEYS.has(k) && v && !((novo[k] || '').trim())) novo[k] = String(v);
        }
        return novo;
      });
      const n = Object.keys(campos).filter((k) => CAMPO_KEYS.has(k)).length;
      setDocStatus((s) => ({ ...s, [tipo]: n > 0 || tipo === 'certidao_nascimento' ? 'ok' : 'vazio' }));
    } catch {
      setDocStatus((s) => ({ ...s, [tipo]: 'erro' }));
    }
  };

  // carrega os cargos da CCT p/ o dropdown
  useEffect(() => {
    if (!token) return;
    (async () => {
      try {
        const r = await api.get(`${BASE}/cargos`, { params: { token } });
        setCargos((r.data?.cargos as Cargo[]) || []);
      } catch { /* silencioso — mostra erro só no submit */ }
      try {
        const t = await api.get(`${BASE}/termo`, { params: { token } });
        setTermoTexto((t.data?.texto as string) || '');
      } catch { /* silencioso */ }
    })();
  }, [token]);

  const aceitarTermo = async () => {
    setErro('');
    if (!aceite) { setErro('Você precisa ler e aceitar o termo para continuar.'); return; }
    setEnviando(true);
    try {
      await api.post(`${BASE}/termo-aceite`, { token, sessao, aceite: true, rubrica: rubrica || null });
      setStep('form');
    } catch {
      setErro('Não foi possível registrar o aceite. Tente de novo.');
    } finally { setEnviando(false); }
  };

  const buscarCep = async (cepRaw?: string) => {
    const cep = (cepRaw || '').replace(/\D/g, '');
    if (cep.length !== 8) return;
    setCepLoading(true);
    try {
      let d: { logradouro?: string; bairro?: string; cidade?: string; uf?: string } | null = null;
      try {
        const r = await fetch(`https://brasilapi.com.br/api/cep/v1/${cep}`);
        if (r.ok) { const j = await r.json(); d = { logradouro: j.street, bairro: j.neighborhood, cidade: j.city, uf: j.state }; }
      } catch { /* viacep */ }
      if (!d?.cidade) {
        try {
          const r2 = await fetch(`https://viacep.com.br/ws/${cep}/json/`);
          if (r2.ok) { const j = await r2.json(); if (!j.erro) d = { logradouro: j.logradouro, bairro: j.bairro, cidade: j.localidade, uf: j.uf }; }
        } catch { /* silencioso */ }
      }
      if (d) setForm((f) => ({ ...f, logradouro: d!.logradouro || f.logradouro, bairro: d!.bairro || f.bairro, cidade: d!.cidade || f.cidade, uf: d!.uf || f.uf }));
    } finally { setCepLoading(false); }
  };

  // valida o form e avança pro facial (a criação acontece após a selfie)
  const irParaFacial = () => {
    setErro('');
    if (!token) { setErro('Link inválido (sem token). Peça o link da vaga.'); return; }
    if (!cargo.trim()) { setErro('Escolha o cargo que você está concorrendo.'); return; }
    const faltando = CAMPOS.filter((c) => c.obrig && !(form[c.key] || '').trim());
    if (faltando.length) { setErro(`Preencha: ${faltando.map((c) => c.label).join(', ')}`); return; }
    setStep('facial');
  };

  // cria o candidato JÁ com a selfie (descriptor no corpo) — sem login, sem acesso ao portal
  const finalizar = async (r: FacialCaptureResult) => {
    if (!r.descriptor?.length) { setErro('Não consegui ler seu rosto. Tente em local iluminado.'); return; }
    setEnviando(true); setErro('');
    try {
      const resp = await api.post(`${BASE}/autocadastro`, {
        token, ...form, cargo_pleiteado: cargo, face_descriptor: r.descriptor,
        sessao, dependentes,
      });
      setRes(resp.data as Resultado);
      setStep('done');
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setErro(typeof msg === 'string' ? msg : 'Não foi possível enviar a candidatura. Verifique os dados.');
      setStep('form');
    } finally { setEnviando(false); }
  };

  const alerta = erro
    ? <div className="mb-4 rounded-xl bg-red-50 border-2 border-red-200 text-red-700 text-[15px] font-medium p-3.5">{erro}</div>
    : null;

  // ---- Passo 3: candidatura recebida ----
  if (step === 'done' && res) {
    return (
      <Moldura>
        <div className="text-center">
          <CheckCircle2 className="w-20 h-20 text-emerald-500 mx-auto mb-4" />
          <h1 className="text-2xl font-extrabold mb-1" style={{ color: MARCA.azul }}>Candidatura recebida!</h1>
          <p className="text-[15px] leading-relaxed text-slate-500 mb-5">
            Obrigado, {res.nome.split(' ')[0]}. Sua candidatura foi registrada e está <b className="text-slate-700">em análise</b> pelo RH.
          </p>
          <div className="rounded-2xl border-2 border-slate-100 bg-slate-50 p-5 text-left text-[15px] leading-relaxed space-y-1.5 mb-5">
            <p><b style={{ color: MARCA.azul }}>Protocolo:</b> {res.protocolo}</p>
            <p><b style={{ color: MARCA.azul }}>Vaga:</b> {res.cargo_pleiteado}</p>
            <p><b style={{ color: MARCA.azul }}>Status:</b> {res.status_label}</p>
            <p><b style={{ color: MARCA.azul }}>Selfie:</b> {res.facial_ok ? 'registrada ✓' : 'pendente'}</p>
          </div>
          <p className="text-[14px] text-slate-500 mb-5">
            Você será avisado se for aprovado. O acesso ao sistema é liberado só após a aprovação.
          </p>
          <a
            href={`/candidato/status?token=${encodeURIComponent(token)}`}
            className="block w-full rounded-2xl py-4 text-lg font-bold text-white active:scale-[0.99]"
            style={{ background: MARCA.laranja }}
          >
            Acompanhar minha candidatura
          </a>
        </div>
      </Moldura>
    );
  }

  // ---- Passo 2: selfie ----
  if (step === 'facial') {
    return (
      <Moldura>
        <div className="text-center">
          <div className="flex items-center justify-center gap-2 mb-1">
            <Camera className="w-7 h-7" style={{ color: MARCA.laranja }} />
            <h1 className="text-2xl font-extrabold" style={{ color: MARCA.azul }}>Tire sua selfie</h1>
          </div>
          <p className="text-[15px] leading-relaxed text-slate-500 mb-5">
            Centralize o rosto no círculo — a captura é automática. Ela conclui sua candidatura.
          </p>
          {alerta}
          <FacialCapture onCapture={finalizar} onError={(m) => setErro(m)} />
          {enviando && (
            <p className="mt-3 text-[15px] text-slate-500 flex items-center justify-center gap-2">
              <Loader2 className="w-5 h-5 animate-spin" /> Enviando candidatura…
            </p>
          )}
        </div>
      </Moldura>
    );
  }

  // ---- Passo 0: termo de consentimento (antes de tudo) ----
  if (step === 'termo') {
    return (
      <Moldura>
        <div className="flex items-center gap-2 mb-1">
          <ShieldCheck className="w-7 h-7" style={{ color: MARCA.laranja }} />
          <h1 className="text-2xl font-extrabold" style={{ color: MARCA.azul }}>Autorização</h1>
        </div>
        <p className="text-[15px] leading-relaxed text-slate-500 mb-4">
          Antes de começar, leia e assine a autorização abaixo.
        </p>
        {alerta}
        <div className="rounded-xl border-2 border-slate-200 bg-slate-50 p-4 max-h-64 overflow-y-auto text-[13.5px] leading-relaxed text-slate-700 whitespace-pre-wrap">
          {termoTexto || 'Carregando termo…'}
        </div>

        <label className="mt-4 flex items-start gap-2.5 cursor-pointer">
          <input type="checkbox" checked={aceite} onChange={(e) => setAceite(e.target.checked)}
            className="mt-1 w-5 h-5 accent-[#F97316]" />
          <span className="text-[15px] font-medium text-slate-700">Li e concordo com a autorização acima.</span>
        </label>

        <div className="mt-4">
          <p className="text-[14px] font-semibold text-slate-700 mb-1.5">Assine no quadro (opcional):</p>
          <SignaturePad onChange={setRubrica} />
        </div>

        <button onClick={aceitarTermo} disabled={enviando || !aceite}
          className="mt-6 w-full rounded-2xl py-4 text-lg font-bold text-white disabled:opacity-50 flex items-center justify-center gap-2 active:scale-[0.99]"
          style={{ background: MARCA.laranja }}>
          {enviando ? <><Loader2 className="w-6 h-6 animate-spin" /> Registrando…</> : 'Aceitar e começar'}
        </button>
      </Moldura>
    );
  }

  // ---- Passo 1: dados + cargo pleiteado + PIX ----
  return (
    <Moldura>
      <div className="flex items-center gap-2 mb-1">
        <Briefcase className="w-7 h-7" style={{ color: MARCA.laranja }} />
        <h1 className="text-2xl font-extrabold" style={{ color: MARCA.azul }}>Candidatura</h1>
      </div>
      <p className="text-[15px] leading-relaxed text-slate-500 mb-5">
        Preencha seus dados com o <b className="text-slate-700">mesmo rigor que o eSocial exige</b>, escolha a
        vaga e tire uma selfie. Simples e rápido.
      </p>

      {alerta}

      {/* Vaga (cargo pleiteado) — destaque */}
      <section className="mb-6">
        <h2 className="text-[13px] font-bold uppercase tracking-wider mb-3 pb-1.5 border-b-2" style={{ color: MARCA.azulMedio, borderColor: '#E2E8F0' }}>
          Vaga que você está concorrendo
        </h2>
        <label className="block text-[15px] font-semibold text-slate-700 mb-1.5">Cargo pleiteado <span className="text-red-500">*</span></label>
        <select value={cargo} onChange={(e) => setCargo(e.target.value)} className={inputCls()}>
          <option value="">Selecione o cargo…</option>
          {cargos.map((c) => (
            <option key={c.nome} value={c.nome}>{c.nome}</option>
          ))}
        </select>
      </section>

      {/* Fase 6.1 — anexar documentos: a IA extrai e preenche os campos sozinha */}
      <section className="mb-6 rounded-2xl border-2 border-dashed p-4" style={{ borderColor: '#CBD8E6', background: '#F6F9FC' }}>
        <h2 className="text-[14px] font-extrabold mb-1 flex items-center gap-2" style={{ color: MARCA.azul }}>
          <Camera className="w-5 h-5" style={{ color: MARCA.laranja }} /> Anexe seus documentos — preenche sozinho
        </h2>
        <p className="text-[13px] leading-snug text-slate-500 mb-3">
          Fotografe ou anexe (RG, CPF, comprovante, currículo…). Os campos abaixo se preenchem automaticamente — você só confere.
        </p>
        <div className="grid grid-cols-2 gap-2.5">
          {[
            { tipo: 'rg', label: 'RG' },
            { tipo: 'cpf', label: 'CPF' },
            { tipo: 'comprovante_endereco', label: 'Comprovante de endereço' },
            { tipo: 'ctps', label: 'Carteira de trabalho' },
            { tipo: 'curriculo', label: 'Currículo' },
            { tipo: 'certidao_nascimento', label: 'Certidão dos filhos' },
          ].map((d) => {
            const st = docStatus[d.tipo];
            const cor = st === 'ok' ? '#059669' : st === 'erro' ? '#DC2626' : st === 'vazio' ? '#B4690E' : '#CBD8E6';
            return (
              <label key={d.tipo}
                className="flex items-center gap-2 rounded-xl border-2 bg-white px-3 py-2.5 text-[14px] font-semibold text-slate-700 cursor-pointer active:scale-[0.99]"
                style={{ borderColor: cor }}>
                <input type="file" accept="image/*,application/pdf" capture="environment" className="hidden"
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) enviarDocumento(d.tipo, f); e.currentTarget.value = ''; }} />
                {st === 'enviando'
                  ? <Loader2 className="w-4 h-4 animate-spin shrink-0" style={{ color: MARCA.laranja }} />
                  : st === 'ok'
                    ? <CheckCircle2 className="w-4 h-4 shrink-0" style={{ color: '#059669' }} />
                    : <Camera className="w-4 h-4 shrink-0 text-slate-400" />}
                <span className="truncate">{d.label}</span>
              </label>
            );
          })}
        </div>
        {dependentes.length > 0 && (
          <p className="mt-3 text-[13px] font-medium" style={{ color: '#059669' }}>
            ✓ {dependentes.length} filho(s) registrado(s) para salário-família.
          </p>
        )}
      </section>

      <div className="space-y-6">
        {SECOES.map((secao) => (
          <section key={secao.titulo}>
            <h2 className="text-[13px] font-bold uppercase tracking-wider mb-3 pb-1.5 border-b-2" style={{ color: MARCA.azulMedio, borderColor: '#E2E8F0' }}>
              {secao.titulo}
            </h2>
            <div className="grid grid-cols-2 gap-3.5">
              {secao.campos.map((c) => (
                <div key={c.key} className={c.full ? 'col-span-2' : 'col-span-1'}>
                  <label className="block text-[15px] font-semibold text-slate-700 mb-1.5">
                    {c.label}
                    {c.obrig && <span className="text-red-500"> *</span>}
                    {c.key === 'cep' && cepLoading && <span className="ml-1 font-medium" style={{ color: MARCA.laranja }}>buscando…</span>}
                  </label>
                  <input
                    type={c.type || 'text'}
                    value={form[c.key] || ''}
                    placeholder={c.placeholder}
                    inputMode={c.key === 'cpf' || c.key === 'telefone' || c.key === 'cep' || c.key === 'pis' ? 'numeric' : undefined}
                    onChange={(e) => {
                      set(c.key, e.target.value);
                      if (c.key === 'cep' && e.target.value.replace(/\D/g, '').length === 8) buscarCep(e.target.value);
                    }}
                    onBlur={c.key === 'cep' ? () => buscarCep(form.cep) : undefined}
                    className={inputCls()}
                  />
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>

      <button
        onClick={irParaFacial}
        disabled={enviando}
        className="mt-7 w-full rounded-2xl py-4 text-lg font-bold text-white disabled:opacity-60 flex items-center justify-center gap-2 active:scale-[0.99]"
        style={{ background: MARCA.laranja }}
      >
        Continuar para a selfie
      </button>
    </Moldura>
  );
}

export default function CandidatoPage() {
  return (
    <main className="min-h-screen" style={{ background: MARCA.fundo }}>
      <div className="pt-4"><AvisoNavegadorInApp /></div>
      <Suspense fallback={<div className="p-10 text-center text-slate-400 text-base">Carregando…</div>}>
        <Fluxo />
      </Suspense>
    </main>
  );
}
