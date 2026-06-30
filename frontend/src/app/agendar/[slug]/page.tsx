'use client';

// Agendamento PÚBLICO de reunião/vistoria (sem login). Link /agendar/<slug>.
import { use, useEffect, useState } from 'react';

export default function PublicBookingPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  const [link, setLink] = useState<any>(null);
  const [err, setErr] = useState('');
  const [f, setF] = useState({ name: '', email: '', phone: '', date: '', time: '', notes: '' });
  const [done, setDone] = useState(false);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    fetch(`/api/v1/crm/public/booking/${slug}`)
      .then((r) => { if (!r.ok) throw new Error('Link de agendamento não encontrado.'); return r.json(); })
      .then(setLink).catch((e) => setErr(e.message));
  }, [slug]);

  const slots: string[] = (() => {
    if (!f.date || !link?.weekly_availability) return [];
    const dow = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'][new Date(f.date + 'T12:00:00').getDay()];
    return link.weekly_availability[dow] || [];
  })();

  const submit = async () => {
    if (!f.name || !f.date || !f.time) return setErr('Preencha nome, data e horário.');
    setErr(''); setSending(true);
    try {
      const r = await fetch(`/api/v1/crm/public/booking/${slug}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: f.name, email: f.email || null, phone: f.phone || null, scheduled_at: `${f.date}T${f.time}:00`, notes: f.notes || null }),
      });
      if (!r.ok) throw new Error('Não foi possível agendar.');
      setDone(true);
    } catch (e: any) { setErr(e.message); } finally { setSending(false); }
  };

  return (
    <div className="min-h-screen bg-slate-100 flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-white rounded-xl shadow-sm border border-slate-200 p-6">
        <div className="text-blue-800 font-bold text-lg mb-1">Conecta Mais — Segurança e Tecnologia</div>
        {err && !link ? <p className="text-red-600">{err}</p> : !link ? <p className="text-slate-400">Carregando…</p> : done ? (
          <div className="text-center py-6">
            <div className="text-green-700 font-semibold text-lg">✓ Agendamento confirmado!</div>
            <p className="text-slate-600 text-sm mt-1">{f.date} às {f.time}. Nossa equipe entrará em contato para confirmar.</p>
          </div>
        ) : (
          <>
            <h1 className="text-xl font-semibold text-slate-800">{link.name}</h1>
            <p className="text-slate-500 text-sm mb-4">Duração: {link.duration_min} min</p>
            {err && <p className="text-red-600 text-sm mb-2">{err}</p>}
            <div className="grid gap-3">
              <input className="border border-slate-300 rounded-lg px-3 py-2 text-sm" placeholder="Seu nome *" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
              <input className="border border-slate-300 rounded-lg px-3 py-2 text-sm" placeholder="E-mail" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
              <input className="border border-slate-300 rounded-lg px-3 py-2 text-sm" placeholder="Telefone" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} />
              <input className="border border-slate-300 rounded-lg px-3 py-2 text-sm" type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value, time: '' })} />
              {f.date && (
                slots.length ? (
                  <div className="flex flex-wrap gap-2">
                    {slots.map((s) => (
                      <button key={s} onClick={() => setF({ ...f, time: s })} className={`px-3 py-1.5 rounded-lg text-sm border ${f.time === s ? 'bg-blue-800 text-white border-blue-800' : 'border-slate-300'}`}>{s}</button>
                    ))}
                  </div>
                ) : <p className="text-sm text-slate-500">Sem horários nesse dia. Escolha outra data.</p>
              )}
              <textarea className="border border-slate-300 rounded-lg px-3 py-2 text-sm" placeholder="Observações (opcional)" value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} />
              <button onClick={submit} disabled={sending} className="bg-blue-800 hover:bg-blue-900 disabled:opacity-50 text-white font-semibold rounded-lg py-3 transition">
                {sending ? 'Agendando…' : 'Confirmar agendamento'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
