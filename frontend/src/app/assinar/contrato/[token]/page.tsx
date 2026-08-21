'use client';

import { use, useEffect, useState } from 'react';
import { msgFromDetail } from '@/lib/string';

// Página PÚBLICA de assinatura de CONTRATO (sem login). O síndico/representante abre o link
// que recebeu, LÊ o instrumento inteiro e assina.
//
// Separada de /assinar/[id] (propostas) de propósito: aquela fala com
// /crm/proposals/{id}/public e tem outro objeto. Misturar as duas na mesma página só criaria
// um if gigante e risco de quebrar o fluxo de proposta, que já funciona.
//
// Motor: `modules/signatures` — /signatures/public/{token} (dados), .../documento (o PDF) e
// POST no mesmo caminho (assina). O token é a credencial; o PIN é o segundo fator.

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

export default function AssinarContratoPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);
  const [info, setInfo] = useState<Info | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [name, setName] = useState('');
  const [cpf, setCpf] = useState('');
  const [pin, setPin] = useState('');
  const [leu, setLeu] = useState(false);
  const [agree, setAgree] = useState(false);
  const [signing, setSigning] = useState(false);
  const [done, setDone] = useState<{ hash: string; quando: string } | null>(null);

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

  const handleSign = async () => {
    if (!name.trim()) return setErr('Informe seu nome completo.');
    if (info?.requires_pin && !pin.trim()) return setErr('Informe o código de verificação que você recebeu.');
    if (!leu) return setErr('Confirme que leu o contrato antes de assinar.');
    if (!agree) return setErr('É preciso concordar com os termos para assinar.');
    setErr('');
    setSigning(true);
    try {
      const r = await fetch(`/api/v1/signatures/public/${token}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          access_code: pin.trim() || null,
          signer_name: name.trim(),
          signer_document: cpf.trim() || null,
        }),
      });
      const j = await r.json();
      if (!r.ok) throw new Error(msgFromDetail(j.detail) || 'Não foi possível registrar a assinatura.');
      setDone({ hash: j.signature_hash, quando: j.signed_at });
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setSigning(false);
    }
  };

  if (loading) return <Shell><p className="text-slate-500">Carregando o contrato…</p></Shell>;
  if (err && !info) return <Shell><p className="text-red-600">{err}</p></Shell>;
  if (!info) return null;

  const indisponivel = info.is_expired || info.already_signed;

  return (
    <Shell>
      <div className="border-b border-slate-200 pb-4 mb-6">
        <div className="text-[#16277D] font-bold text-lg">Conecta Mais</div>
        <div className="text-slate-500 text-sm">Assinatura eletrônica de contrato</div>
      </div>

      <h1 className="text-xl font-semibold text-slate-800 mb-1">{info.title}</h1>
      {info.signer_name && (
        <p className="text-slate-600 mb-4">
          Signatário: <b>{info.signer_name}</b>
        </p>
      )}

      {/* o contrato inteiro, na própria página — ninguém deve assinar às cegas */}
      <div className="border border-slate-200 rounded-lg overflow-hidden mb-3">
        <object data={docUrl} type="application/pdf" className="w-full h-[70vh]">
          <div className="p-6 text-center text-sm text-slate-600">
            Seu navegador não exibe PDF aqui.
            <a href={docUrl} target="_blank" rel="noreferrer" className="text-[#16277D] font-semibold underline ml-1">
              Abrir o contrato
            </a>
          </div>
        </object>
      </div>
      <p className="text-right mb-6">
        <a href={docUrl} target="_blank" rel="noreferrer" className="text-sm text-[#16277D] underline">
          Abrir em nova aba / baixar
        </a>
      </p>

      <div className="border-t border-slate-200 pt-6">
        {done ? (
          <div className="bg-green-50 border border-green-200 rounded-lg p-5 text-center">
            <div className="text-green-700 font-semibold text-lg">✓ Contrato assinado</div>
            <p className="text-slate-600 text-sm mt-1">
              Obrigado. Uma via assinada fica registrada no sistema, com o manifesto de assinaturas ao final.
            </p>
            <p className="text-xs text-slate-400 mt-3 break-all">Código de verificação: {done.hash}</p>
          </div>
        ) : info.already_signed ? (
          <div className="bg-slate-50 border border-slate-200 rounded-lg p-5 text-center text-slate-600">
            Este contrato já foi assinado. Obrigado!
          </div>
        ) : info.is_expired ? (
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-5 text-center text-amber-800">
            Este link de assinatura expirou. Fale com a Conecta Mais para receber um novo.
          </div>
        ) : (
          <>
            <h2 className="font-semibold text-slate-800 mb-3">Assinar eletronicamente</h2>
            {err && <p className="text-red-600 text-sm mb-2">{err}</p>}
            <div className="grid gap-3">
              <input
                className="border border-slate-300 rounded-lg px-3 py-2 text-sm"
                placeholder="Nome completo *"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
              <input
                className="border border-slate-300 rounded-lg px-3 py-2 text-sm"
                placeholder="CPF"
                value={cpf}
                onChange={(e) => setCpf(e.target.value)}
              />
              {info.requires_pin && (
                <input
                  className="border border-slate-300 rounded-lg px-3 py-2 text-sm tracking-widest"
                  placeholder="Código de verificação (6 dígitos) *"
                  inputMode="numeric"
                  maxLength={6}
                  value={pin}
                  onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))}
                />
              )}
              <label className="flex items-start gap-2 text-sm text-slate-600">
                <input type="checkbox" checked={leu} onChange={(e) => setLeu(e.target.checked)} className="mt-1" />
                <span>Li o contrato acima, na íntegra.</span>
              </label>
              <label className="flex items-start gap-2 text-sm text-slate-600">
                <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} className="mt-1" />
                <span>
                  Concordo com todas as cláusulas e assino este instrumento por assinatura eletrônica, na forma do
                  art. 10, § 2º, da MP nº 2.200-2/2001.
                </span>
              </label>
              <button
                onClick={handleSign}
                disabled={signing || indisponivel}
                className="bg-[#16277D] hover:bg-[#101c5c] disabled:opacity-50 text-white font-semibold rounded-lg py-3 transition"
              >
                {signing ? 'Registrando…' : 'Assinar contrato'}
              </button>
              <p className="text-xs text-slate-400 text-center">
                Sua assinatura registra data, hora, IP e um código de verificação, que constam do manifesto ao final do
                contrato.
              </p>
            </div>
          </>
        )}
      </div>
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-slate-100 py-8 px-4">
      <div className="max-w-3xl mx-auto bg-white rounded-xl shadow-sm border border-slate-200 p-6 md:p-8">
        {children}
      </div>
    </div>
  );
}
