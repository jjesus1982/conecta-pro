'use client';

// Formulário PÚBLICO de captura de lead (sem login). Embedável via link /form/<slug>.
import { use, useEffect, useState } from 'react';

export default function PublicFormPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  const [form, setForm] = useState<any>(null);
  const [err, setErr] = useState('');
  const [values, setValues] = useState<Record<string, string>>({});
  const [done, setDone] = useState(false);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    fetch(`/api/v1/crm/public/forms/${slug}`)
      .then((r) => { if (!r.ok) throw new Error('Formulário não encontrado.'); return r.json(); })
      .then(setForm).catch((e) => setErr(e.message));
  }, [slug]);

  const fields = form?.fields?.length ? form.fields : [{ key: 'name', label: 'Nome' }, { key: 'email', label: 'E-mail' }, { key: 'phone', label: 'Telefone' }];

  const submit = async () => {
    if (!values.name && !values.nome) return setErr('Informe seu nome.');
    setErr(''); setSending(true);
    try {
      const r = await fetch(`/api/v1/crm/public/forms/${slug}/submit`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(values),
      });
      if (!r.ok) throw new Error('Não foi possível enviar.');
      if (form?.redirect_url) { window.location.href = form.redirect_url; return; }
      setDone(true);
    } catch (e: any) { setErr(e.message); } finally { setSending(false); }
  };

  return (
    <div className="min-h-screen bg-slate-100 flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-white rounded-xl shadow-sm border border-slate-200 p-6">
        <div className="text-blue-800 font-bold text-lg mb-1">Conecta Mais — Segurança e Tecnologia</div>
        {err && !form ? <p className="text-red-600">{err}</p> : !form ? <p className="text-slate-400">Carregando…</p> : done ? (
          <div className="text-center py-6">
            <div className="text-green-700 font-semibold text-lg">✓ Recebemos seu contato!</div>
            <p className="text-slate-600 text-sm mt-1">Nossa equipe vai falar com você em breve.</p>
          </div>
        ) : (
          <>
            <h1 className="text-xl font-semibold text-slate-800 mb-4">{form.name}</h1>
            {err && <p className="text-red-600 text-sm mb-2">{err}</p>}
            <div className="grid gap-3">
              {fields.map((f: any) => (
                <div key={f.key}>
                  <label className="text-sm text-slate-600">{f.label}</label>
                  <input className="border border-slate-300 rounded-lg px-3 py-2 text-sm w-full mt-1"
                    type={f.key === 'email' ? 'email' : 'text'}
                    value={values[f.key] || ''} onChange={(e) => setValues({ ...values, [f.key]: e.target.value })} />
                </div>
              ))}
              <button onClick={submit} disabled={sending} className="bg-blue-800 hover:bg-blue-900 disabled:opacity-50 text-white font-semibold rounded-lg py-3 transition">
                {sending ? 'Enviando…' : 'Enviar'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
