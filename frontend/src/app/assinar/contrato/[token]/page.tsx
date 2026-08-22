'use client';

import { use, useEffect, useState } from 'react';
import { msgFromDetail } from '@/lib/string';

// Portal PÚBLICO de assinatura de CONTRATO (sem login).
//
// Fluxo em dois passos (decisão do Jordan, 22/08): a pessoa lê o contrato, informa nome,
// CPF e e-mail, RECEBE o código de validação NO PRÓPRIO E-MAIL e só então assina. O código
// nunca viaja junto com o link — se fossem no mesmo lugar, os dois fatores viram um.
//
// Separada de /assinar/[id] (propostas) de propósito: aquela fala com
// /crm/proposals/{id}/public e tem outro objeto.
//
// Motor: `modules/signatures` — GET /signatures/public/{token} (dados), .../documento (PDF),
// POST .../codigo (manda o código) e POST no caminho base (assina).

interface Info {
  request_id: string;
  title: string;
  document_name?: string;
  signer_name?: string;
  requires_pin: boolean;
  status: string;
  already_signed: boolean;
  expires_at?: string;
  is_expired: boolean;
}

const NAVY = '#16277D';
const LARANJA = '#F26522';

export default function AssinarContratoPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);
  const [info, setInfo] = useState<Info | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');

  const [name, setName] = useState('');
  const [cpf, setCpf] = useState('');
  const [email, setEmail] = useState('');
  const [pin, setPin] = useState('');
  const [leu, setLeu] = useState(false);
  const [agree, setAgree] = useState(false);

  const [etapa, setEtapa] = useState<'dados' | 'codigo'>('dados');
  const [enviandoCodigo, setEnviandoCodigo] = useState(false);
  const [destino, setDestino] = useState('');
  const [signing, setSigning] = useState(false);
  const [done, setDone] = useState<{ hash: string } | null>(null);

  const docUrl = `/api/v1/signatures/public/${token}/documento`;

  useEffect(() => {
    fetch(`/api/v1/signatures/public/${token}`)
      .then(async (r) => {
        if (!r.ok) throw new Error('Link de assinatura inválido, expirado ou já utilizado.');
        return r.json();
      })
      .then((d: Info) => {
        setInfo(d);
        if (d.signer_name) setName(d.signer_name);
      })
      .catch((e) => setErr(e.message))
      .finally(() => setLoading(false));
  }, [token]);

  const cpfOk = cpf.replace(/\D/g, '').length === 11;
  const emailOk = /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim());

  const pedirCodigo = async () => {
    if (!name.trim()) return setErr('Informe seu nome completo.');
    if (!cpfOk) return setErr('Informe um CPF válido (11 dígitos).');
    if (!emailOk) return setErr('Informe um e-mail válido — é para lá que vai o código.');
    if (!leu) return setErr('Confirme que leu o contrato antes de prosseguir.');
    if (!agree) return setErr('É preciso concordar com os termos para assinar.');
    setErr('');
    setEnviandoCodigo(true);
    try {
      const r = await fetch(`/api/v1/signatures/public/${token}/codigo`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          signer_name: name.trim(),
          signer_document: cpf.trim(),
          signer_email: email.trim(),
        }),
      });
      const j = await r.json();
      if (!r.ok) throw new Error(msgFromDetail(j.detail) || 'Não foi possível enviar o código.');
      setDestino(j.para || email.trim());
      setEtapa('codigo');
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setEnviandoCodigo(false);
    }
  };

  const assinar = async () => {
    if (pin.trim().length !== 6) return setErr('Digite os 6 dígitos do código que enviamos.');
    setErr('');
    setSigning(true);
    try {
      const r = await fetch(`/api/v1/signatures/public/${token}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          access_code: pin.trim(),
          signer_name: name.trim(),
          signer_document: cpf.trim(),
          signer_email: email.trim(),
        }),
      });
      const j = await r.json();
      if (!r.ok) throw new Error(msgFromDetail(j.detail) || 'Não foi possível registrar a assinatura.');
      setDone({ hash: j.signature_hash });
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setSigning(false);
    }
  };

  if (loading)
    return (
      <Shell>
        <div className="py-24 text-center text-slate-400 text-sm">Carregando o contrato…</div>
      </Shell>
    );
  if (err && !info)
    return (
      <Shell>
        <Aviso tom="erro" titulo="Não foi possível abrir">{err}</Aviso>
      </Shell>
    );
  if (!info) return null;

  return (
    <Shell titulo={info.title} signatario={info.signer_name}>
      {/* o contrato inteiro, na própria página — ninguém deve assinar às cegas */}
      <section className="mb-8">
        <Rotulo>O contrato</Rotulo>
        {/* iframe, NÃO object: o CSP de produção traz `object-src 'none'`, então o PDF
            embutido em <object> não renderiza — o signatário via um quadro vazio e
            assinaria às cegas. Sem `frame-src` declarado, o iframe cai em
            `default-src 'self'`, e este PDF é da mesma origem. Só o navegador pegou isso;
            o HTML servido parecia correto. */}
        <div className="rounded-xl overflow-hidden border border-slate-200 shadow-sm bg-slate-50">
          <iframe src={docUrl} title="Contrato para leitura" className="w-full h-[72vh] block border-0" />
        </div>
        <noscript>
          <a href={docUrl}>Abrir o contrato</a>
        </noscript>
        <div className="flex justify-end mt-2">
          <a href={docUrl} target="_blank" rel="noreferrer" className="text-sm underline" style={{ color: NAVY }}>
            Abrir em nova aba / baixar
          </a>
        </div>
      </section>

      {done ? (
        <Aviso tom="ok" titulo="Contrato assinado">
          <p className="text-slate-600 text-sm">
            Enviamos a via assinada para <b>{email}</b>. Quando todas as partes assinarem, você recebe
            o aviso e a via final no mesmo endereço.
          </p>
          <p className="text-[11px] text-slate-400 mt-4 break-all font-[family-name:var(--font-data)]">
            Código de verificação: {done.hash}
          </p>
        </Aviso>
      ) : info.already_signed ? (
        <Aviso tom="neutro" titulo="Já assinado">
          Este documento já foi assinado por você. Obrigado!
        </Aviso>
      ) : info.is_expired ? (
        <Aviso tom="alerta" titulo="Link expirado">
          Fale com a Conecta Mais para receber um novo link de assinatura.
        </Aviso>
      ) : (
        <section>
          <Rotulo>Assinatura eletrônica</Rotulo>
          <Passos etapa={etapa} />

          <div className="rounded-xl border border-slate-200 bg-white p-6 md:p-7 shadow-sm">
            {err && (
              <p className="mb-4 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                {err}
              </p>
            )}

            {etapa === 'dados' ? (
              <div className="grid gap-4">
                <Campo rotulo="Nome completo" obrigatorio>
                  <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} />
                </Campo>
                <div className="grid md:grid-cols-2 gap-4">
                  <Campo rotulo="CPF" obrigatorio>
                    <input
                      className={inputCls}
                      inputMode="numeric"
                      placeholder="000.000.000-00"
                      value={cpf}
                      onChange={(e) => setCpf(e.target.value)}
                    />
                  </Campo>
                  <Campo rotulo="E-mail" obrigatorio dica="O código de validação vai para cá.">
                    <input
                      className={inputCls}
                      type="email"
                      autoComplete="email"
                      placeholder="voce@empresa.com.br"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                    />
                  </Campo>
                </div>

                <label className="flex items-start gap-3 text-sm text-slate-600 mt-1">
                  <input type="checkbox" checked={leu} onChange={(e) => setLeu(e.target.checked)} className="mt-1 accent-[#16277D]" />
                  <span>Li o contrato acima, na íntegra.</span>
                </label>
                <label className="flex items-start gap-3 text-sm text-slate-600">
                  <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} className="mt-1 accent-[#16277D]" />
                  <span>
                    Concordo com todas as cláusulas e assino este instrumento por assinatura eletrônica,
                    na forma do art. 10, § 2º, da MP nº 2.200-2/2001.
                  </span>
                </label>

                <button onClick={pedirCodigo} disabled={enviandoCodigo} className={botaoCls}>
                  {enviandoCodigo ? 'Enviando o código…' : 'Receber código por e-mail'}
                </button>
              </div>
            ) : (
              <div className="grid gap-4">
                <div className="text-sm text-slate-600">
                  Enviamos um código de 6 dígitos para <b>{destino}</b>. Digite-o abaixo para concluir
                  a assinatura.
                </div>
                <input
                  className="border border-slate-300 rounded-lg px-4 py-4 text-center text-3xl tracking-[0.5em] font-[family-name:var(--font-data)] focus:outline-none focus:ring-2 focus:ring-[#16277D]/30 focus:border-[#16277D]"
                  inputMode="numeric"
                  maxLength={6}
                  placeholder="······"
                  value={pin}
                  onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))}
                />
                <button onClick={assinar} disabled={signing} className={botaoCls}>
                  {signing ? 'Registrando…' : 'Assinar contrato'}
                </button>
                <button
                  onClick={() => {
                    setEtapa('dados');
                    setPin('');
                    setErr('');
                  }}
                  className="text-sm text-slate-500 underline"
                >
                  Corrigir meus dados ou reenviar o código
                </button>
              </div>
            )}

            <p className="text-xs text-slate-400 mt-5 leading-relaxed">
              Sua assinatura registra nome, CPF, e-mail, data, hora e endereço IP, com um código de
              verificação único — tudo consta do manifesto ao final do contrato.
            </p>
          </div>
        </section>
      )}
    </Shell>
  );
}

const inputCls =
  'w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#16277D]/30 focus:border-[#16277D]';

const botaoCls =
  'w-full text-white font-semibold rounded-lg py-3.5 transition disabled:opacity-50 bg-[#F26522] hover:bg-[#d9541a] shadow-sm';

function Campo({
  rotulo,
  obrigatorio,
  dica,
  children,
}: {
  rotulo: string;
  obrigatorio?: boolean;
  dica?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1.5">
        {rotulo} {obrigatorio && <span style={{ color: LARANJA }}>*</span>}
      </span>
      {children}
      {dica && <span className="block text-xs text-slate-400 mt-1">{dica}</span>}
    </label>
  );
}

function Rotulo({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3 mb-3">
      <span className="h-4 w-1 rounded-full" style={{ background: LARANJA }} />
      <h2 className="text-xs font-bold uppercase tracking-[0.18em]" style={{ color: NAVY }}>
        {children}
      </h2>
    </div>
  );
}

function Passos({ etapa }: { etapa: 'dados' | 'codigo' }) {
  const itens = [
    { n: 1, t: 'Seus dados' },
    { n: 2, t: 'Código por e-mail' },
  ];
  return (
    <ol className="flex items-center gap-3 mb-4">
      {itens.map((i, idx) => {
        const ativo = (etapa === 'dados' && i.n === 1) || (etapa === 'codigo' && i.n === 2);
        const feito = etapa === 'codigo' && i.n === 1;
        return (
          <li key={i.n} className="flex items-center gap-3">
            <span
              className="h-7 w-7 rounded-full grid place-items-center text-xs font-bold text-white"
              style={{ background: feito ? '#16A34A' : ativo ? NAVY : '#CBD5E1' }}
            >
              {feito ? '✓' : i.n}
            </span>
            <span className={`text-sm ${ativo ? 'font-semibold text-slate-800' : 'text-slate-400'}`}>{i.t}</span>
            {idx === 0 && <span className="w-8 h-px bg-slate-200" />}
          </li>
        );
      })}
    </ol>
  );
}

function Aviso({
  tom,
  titulo,
  children,
}: {
  tom: 'ok' | 'erro' | 'alerta' | 'neutro';
  titulo: string;
  children: React.ReactNode;
}) {
  const cores = {
    ok: { bg: '#F0FDF4', br: '#BBF7D0', tx: '#15803D' },
    erro: { bg: '#FEF2F2', br: '#FECACA', tx: '#B91C1C' },
    alerta: { bg: '#FFFBEB', br: '#FDE68A', tx: '#B45309' },
    neutro: { bg: '#F8FAFC', br: '#E2E8F0', tx: '#475569' },
  }[tom];
  return (
    <div className="rounded-xl border p-6 text-center" style={{ background: cores.bg, borderColor: cores.br }}>
      <div className="font-semibold text-base mb-1" style={{ color: cores.tx }}>
        {titulo}
      </div>
      <div className="text-sm text-slate-600">{children}</div>
    </div>
  );
}

function Shell({
  children,
  titulo,
  signatario,
}: {
  children: React.ReactNode;
  titulo?: string;
  signatario?: string;
}) {
  return (
    <div className="min-h-screen bg-slate-100">
      {/* faixa da marca — laranja sobre navy, o mesmo par do timbrado do contrato */}
      <div className="h-1.5" style={{ background: LARANJA }} />
      <header style={{ background: NAVY }}>
        <div className="max-w-4xl mx-auto px-5 py-6 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            {/* chip branco: a logo é azul sobre transparente e sumia no fundo navy */}
            <span className="bg-white rounded-lg px-2.5 py-1.5 grid place-items-center shrink-0">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src="/images/logo-transparent.png" alt="Conecta Mais" className="h-8 w-auto" />
            </span>
            <div className="leading-tight">
              <div className="text-white font-bold text-lg font-[family-name:var(--font-display)]">Conecta Mais</div>
              <div className="text-[11px] uppercase tracking-[0.2em] text-white/60">Segurança e Tecnologia</div>
            </div>
          </div>
          <div className="hidden sm:block text-right">
            <div className="text-[11px] uppercase tracking-[0.18em] text-white/50">Assinatura eletrônica</div>
            <div className="text-xs text-white/80">MP nº 2.200-2/2001</div>
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-5 py-8">
        {titulo && (
          <div className="mb-7">
            <h1 className="text-2xl font-bold text-slate-900 font-[family-name:var(--font-display)] leading-snug">
              {titulo}
            </h1>
            {signatario && (
              <p className="text-slate-500 text-sm mt-1">
                Signatário: <b className="text-slate-700">{signatario}</b>
              </p>
            )}
          </div>
        )}
        {children}
      </main>

      <footer className="max-w-4xl mx-auto px-5 pb-10 pt-2">
        <div className="border-t border-slate-200 pt-4 text-[11px] text-slate-400 flex flex-wrap gap-x-4 gap-y-1">
          <span>CONECTA MAIS PATRIMONIAL · CNPJ 66.014.833/0001-10</span>
          <span>0800 880 4414</span>
          <span>www.conectamais.pro</span>
        </div>
      </footer>
    </div>
  );
}
