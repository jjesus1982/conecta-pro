'use client';

import { use, useEffect, useState } from 'react';
import { msgFromDetail } from '@/lib/string';

// Página PÚBLICA de assinatura (sem login). O cliente abre o link da proposta, confere e assina.
// Provedor interno: a assinatura é registrada pelo próprio sistema (proposal_signatures).

interface Item { name: string; description?: string; quantity: number; unit_price: number; total?: number; }
interface PublicProposal {
  id: string; number: string; title: string; client_name?: string;
  total: number; status: string; signature_status?: string; valid_until?: string;
  payment_terms?: string; notes?: string; items: Item[];
}

const brl = (v: number) =>
  (Number(v) || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });

export default function AssinarPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [data, setData] = useState<PublicProposal | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [name, setName] = useState('');
  const [cpf, setCpf] = useState('');
  const [agree, setAgree] = useState(false);
  const [signing, setSigning] = useState(false);
  const [done, setDone] = useState<{ hash: string } | null>(null);

  useEffect(() => {
    fetch(`/api/v1/crm/proposals/${id}/public`)
      .then(async (r) => {
        if (!r.ok) throw new Error('Proposta não encontrada ou indisponível.');
        return r.json();
      })
      .then((d) => setData(d))
      .catch((e) => setErr(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  const alreadySigned = data?.signature_status === 'signed' || data?.status === 'accepted';

  const handleSign = async () => {
    if (!name.trim()) return setErr('Informe seu nome completo.');
    if (!agree) return setErr('É preciso concordar com os termos para assinar.');
    setErr(''); setSigning(true);
    try {
      const r = await fetch(`/api/v1/crm/proposals/${id}/sign`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ signer_name: name.trim(), signer_cpf: cpf.trim() || null }),
      });
      const j = await r.json();
      if (!r.ok || !j.signed) throw new Error(msgFromDetail(j.detail) || 'Não foi possível registrar a assinatura.');
      setDone({ hash: j.hash });
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setSigning(false);
    }
  };

  if (loading)
    return <Shell><p className="text-slate-500">Carregando proposta…</p></Shell>;
  if (err && !data)
    return <Shell><p className="text-red-600">{err}</p></Shell>;
  if (!data) return null;

  return (
    <Shell>
      <div className="border-b border-slate-200 pb-4 mb-6">
        <div className="text-blue-800 font-bold text-lg">Conecta Mais — Segurança e Tecnologia</div>
        <div className="text-slate-500 text-sm">Proposta {data.number}</div>
      </div>

      <h1 className="text-xl font-semibold text-slate-800 mb-1">{data.title}</h1>
      {data.client_name && <p className="text-slate-600 mb-4">Para: <b>{data.client_name}</b></p>}

      <table className="w-full text-sm mb-4">
        <thead>
          <tr className="text-left text-slate-500 border-b">
            <th className="py-2">Item</th>
            <th className="py-2 text-right">Qtd</th>
            <th className="py-2 text-right">Valor</th>
            <th className="py-2 text-right">Total</th>
          </tr>
        </thead>
        <tbody>
          {(data.items || []).map((it, i) => (
            <tr key={i} className="border-b border-slate-100">
              <td className="py-2">
                <div className="font-medium text-slate-800">{it.name}</div>
                {it.description && <div className="text-xs text-slate-500">{it.description}</div>}
              </td>
              <td className="py-2 text-right">{it.quantity}</td>
              <td className="py-2 text-right">{brl(it.unit_price)}</td>
              <td className="py-2 text-right">{brl(it.total ?? it.quantity * it.unit_price)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="text-right text-lg font-bold text-slate-900 mb-4">
        Total: {brl(data.total)}
      </div>

      {data.payment_terms && (
        <p className="text-sm text-slate-600 mb-1"><b>Condições:</b> {data.payment_terms}</p>
      )}
      {data.notes && <p className="text-sm text-slate-600 mb-4 whitespace-pre-line">{data.notes}</p>}

      <div className="mt-6 border-t border-slate-200 pt-6">
        {done ? (
          <div className="bg-green-50 border border-green-200 rounded-lg p-5 text-center">
            <div className="text-green-700 font-semibold text-lg">✓ Proposta assinada com sucesso!</div>
            <p className="text-slate-600 text-sm mt-1">Obrigado. Nossa equipe dará sequência ao seu atendimento.</p>
            <p className="text-xs text-slate-400 mt-3 break-all">Código de validação: {done.hash}</p>
          </div>
        ) : alreadySigned ? (
          <div className="bg-slate-50 border border-slate-200 rounded-lg p-5 text-center text-slate-600">
            Esta proposta já foi assinada. Obrigado!
          </div>
        ) : (
          <>
            <h2 className="font-semibold text-slate-800 mb-3">Assinatura digital</h2>
            {err && <p className="text-red-600 text-sm mb-2">{err}</p>}
            <div className="grid gap-3">
              <input
                className="border border-slate-300 rounded-lg px-3 py-2 text-sm"
                placeholder="Seu nome completo *"
                value={name} onChange={(e) => setName(e.target.value)} />
              <input
                className="border border-slate-300 rounded-lg px-3 py-2 text-sm"
                placeholder="CPF (opcional)"
                value={cpf} onChange={(e) => setCpf(e.target.value)} />
              <label className="flex items-start gap-2 text-sm text-slate-600">
                <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} className="mt-1" />
                <span>Li e concordo com os termos desta proposta e autorizo seu aceite, com validade legal de assinatura eletrônica.</span>
              </label>
              <button
                onClick={handleSign} disabled={signing}
                className="bg-blue-800 hover:bg-blue-900 disabled:opacity-50 text-white font-semibold rounded-lg py-3 transition">
                {signing ? 'Registrando…' : 'Assinar e aceitar a proposta'}
              </button>
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
      <div className="max-w-2xl mx-auto bg-white rounded-xl shadow-sm border border-slate-200 p-6 md:p-8">
        {children}
      </div>
    </div>
  );
}
