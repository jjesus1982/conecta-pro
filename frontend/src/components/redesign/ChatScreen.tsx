'use client';
// ChatScreen — tela conversacional do redesign (peça 2 da camada cognitiva).
// Genérica: parametrizada por scr.chat = { endpoint, field, placeholder, suggestions, disclaimer }.
// Reaproveita o molde de fetch autenticado do FormScreen (localStorage access_token → Bearer,
// URL relativa /api/v1/...). Serve o Orquestrador Executivo agora e os 8 consultores depois (peça 3).
import { useState, useRef, useEffect } from 'react';

type Msg = { role: 'user' | 'assistant'; text: string; meta?: any };

export default function ChatScreen({ scr }: { scr: any }) {
  const cfg = scr?.chat || {};
  const endpoint: string = cfg.endpoint || '';
  const field: string = cfg.field || 'pergunta';
  const suggestions: string[] = cfg.suggestions || [];

  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [msgs, busy]);

  async function send(pergunta: string) {
    const q = (pergunta || '').trim();
    if (!q || busy || !endpoint) return;
    setInput('');
    setMsgs((m) => [...m, { role: 'user', text: q }]);
    setBusy(true);
    let tok: string | null = null;
    try { tok = localStorage.getItem('access_token'); } catch { /* */ }
    try {
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(tok ? { Authorization: `Bearer ${tok}` } : {}) },
        body: JSON.stringify({ [field]: q }),
      });
      const d = await res.json().catch(() => ({} as any));
      if (res.status === 401 || res.status === 403) {
        setMsgs((m) => [...m, { role: 'assistant', text: 'Este orquestrador é restrito à diretoria. Entre com um usuário autorizado (Jordan ou Pyetra).', meta: { aviso: true } }]);
      } else if (!res.ok) {
        setMsgs((m) => [...m, { role: 'assistant', text: (d && d.detail) || `Não consegui responder agora (erro ${res.status}).`, meta: { aviso: true } }]);
      } else {
        setMsgs((m) => [...m, { role: 'assistant', text: d.resposta || '(sem resposta)', meta: d }]);
      }
    } catch {
      setMsgs((m) => [...m, { role: 'assistant', text: 'Falha de rede ao consultar. Tente de novo.', meta: { aviso: true } }]);
    } finally {
      setBusy(false);
    }
  }

  function provLabel(meta: any): string | null {
    const p = String((meta && (meta.provider || meta.modelo)) || '').toLowerCase();
    if (p.includes('hermes')) return '🧠 Hermes';
    if (p) return 'IA direta';
    return null;
  }

  return (
    <div className="rd-card rd-card-pad" style={{ display: 'flex', flexDirection: 'column', height: 'clamp(440px, 68vh, 760px)' }}>
      <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 12, paddingRight: 4 }}>
        {msgs.length === 0 && (
          <div style={{ margin: 'auto', textAlign: 'center', maxWidth: 520 }}>
            <div className="rd-label" style={{ marginBottom: 12 }}>Comece por uma pergunta</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, justifyContent: 'center' }}>
              {suggestions.map((s: string, i: number) => (
                <button key={i} type="button" className="rd-btn rd-btn-outline" style={{ fontSize: 12 }} onClick={() => send(s)}>{s}</button>
              ))}
            </div>
          </div>
        )}
        {msgs.map((m, i) => {
          const aviso = !!(m.meta && m.meta.aviso);
          const mine = m.role === 'user';
          return (
            <div key={i} style={{ alignSelf: mine ? 'flex-end' : 'flex-start', maxWidth: '84%' }}>
              <div style={{
                padding: '10px 14px', borderRadius: 14, fontSize: 13, lineHeight: 1.55, whiteSpace: 'pre-wrap',
                background: mine ? 'var(--navy)' : (aviso ? 'var(--orange-bg)' : 'var(--fill)'),
                color: mine ? '#fff' : 'var(--ink)',
                border: mine ? 'none' : '1px solid var(--border)',
              }}>{m.text}</div>
              {!mine && m.meta && !aviso && (
                <div style={{ display: 'flex', gap: 6, marginTop: 5, flexWrap: 'wrap' }}>
                  {provLabel(m.meta) && <span className="rd-badge rd-b-neutral" style={{ fontSize: 10 }}>{provLabel(m.meta)}</span>}
                  {m.meta.grounded === false && <span className="rd-badge rd-b-orange" style={{ fontSize: 10 }}>confira os números</span>}
                </div>
              )}
            </div>
          );
        })}
        {busy && <div style={{ alignSelf: 'flex-start', color: 'var(--ink-weak)', fontSize: 12 }}>Consultando os números reais…</div>}
        <div ref={endRef} />
      </div>

      {cfg.disclaimer && <div style={{ fontSize: 11, color: 'var(--ink-weak)', margin: '10px 0 8px' }}>{cfg.disclaimer}</div>}

      <form onSubmit={(e) => { e.preventDefault(); send(input); }} style={{ display: 'flex', gap: 8 }}>
        <input
          className="rd-input"
          style={{ flex: 1 }}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={cfg.placeholder || 'Pergunte…'}
          disabled={busy}
          aria-label="Sua pergunta"
        />
        <button type="submit" className="rd-btn rd-btn-primary" disabled={busy || !input.trim()}>Enviar</button>
      </form>
    </div>
  );
}
