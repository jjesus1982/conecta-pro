'use client';
// FloatingChat — assistente flutuante (FAB + painel) disponível em toda tela autenticada,
// tanto no /modulos quanto no /redesign. Estilo LITERAL próprio (marca Navy→Laranja, painel
// claro) porque os dois ambientes usam sistemas de token de cor diferentes e incompatíveis
// (/modulos = hsl(var(--card)) shadcn; /redesign = --surface/--ink/--orange). Cores literais
// = funciona igual nos dois, sem depender do tema do host.
// Chama POST /api/v1/consultores/chat/executar (gera-doc p/ todos os perfis) e baixa os PDFs
// que a resposta traz em d.documentos[]. Bearer do localStorage access_token (URL relativa).
import { useState, useRef, useEffect } from 'react';
import { MessageCircle, X, Send, Download, Loader2 } from 'lucide-react';

type Doc = { nome?: string; arquivo_base64?: string; resumo?: string };
type Msg = { role: 'user' | 'assistant'; text: string; docs?: Doc[]; aviso?: boolean };

const ENDPOINT = '/api/v1/consultores/chat/executar';
const SUGGESTIONS = ['Gera o DRE do mês', 'Meu holerite', 'Monta uma proposta'];
const NAVY = '#16277D';
const GRAD = 'linear-gradient(135deg, #16277D, #F26522)';

// base64 → download de PDF com o nome real. atob + loop p/ bytes (sem lib).
function downloadPdf(nome: string, b64: string) {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  const url = URL.createObjectURL(new Blob([bytes], { type: 'application/pdf' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = nome && nome.toLowerCase().endsWith('.pdf') ? nome : `${nome || 'documento'}.pdf`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

export default function FloatingChat() {
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { if (open) endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [msgs, busy, open]);

  async function send(pergunta: string) {
    const q = (pergunta || '').trim();
    if (!q || busy) return;
    setInput('');
    setMsgs((m) => [...m, { role: 'user', text: q }]);
    setBusy(true);
    let tok: string | null = null;
    try { tok = localStorage.getItem('access_token'); } catch { /* */ }
    try {
      const res = await fetch(ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(tok ? { Authorization: `Bearer ${tok}` } : {}) },
        body: JSON.stringify({ pergunta: q }),
      });
      const d = await res.json().catch(() => ({} as any));
      if (res.status === 401 || res.status === 403) {
        setMsgs((m) => [...m, { role: 'assistant', text: 'Sua sessão expirou. Faça login de novo para continuar.', aviso: true }]);
      } else if (!res.ok) {
        setMsgs((m) => [...m, { role: 'assistant', text: (d && d.detail) || `Não consegui responder agora (erro ${res.status}).`, aviso: true }]);
      } else {
        setMsgs((m) => [...m, {
          role: 'assistant',
          text: d.resposta || '(sem resposta)',
          docs: Array.isArray(d.documentos) ? d.documentos.filter((x: Doc) => x && x.arquivo_base64) : [],
        }]);
      }
    } catch {
      setMsgs((m) => [...m, { role: 'assistant', text: 'Falha de rede ao consultar. Tente de novo.', aviso: true }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {/* FAB — sempre visível/clicável, canto inferior-direito */}
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label={open ? 'Fechar assistente' : 'Abrir assistente'}
        className="fixed bottom-5 right-5 z-[9999] w-14 h-14 rounded-full flex items-center justify-center text-white shadow-xl transition-transform hover:scale-105 active:scale-95"
        style={{ background: GRAD, border: 'none' }}
      >
        {open ? <X className="w-6 h-6" /> : <MessageCircle className="w-6 h-6" />}
      </button>

      {/* Painel */}
      {open && (
        <div
          className="fixed bottom-24 right-5 z-[9999] w-[min(92vw,400px)] h-[min(72vh,620px)] flex flex-col rounded-2xl overflow-hidden"
          style={{ background: '#FFFFFF', border: '1px solid #E7ECF3', boxShadow: '0 12px 40px rgba(16,39,125,0.18)', color: '#1a2233' }}
          role="dialog"
          aria-label="Assistente Conecta"
        >
          {/* Header */}
          <div className="flex-shrink-0 flex items-center justify-between px-4 py-3" style={{ borderBottom: '1px solid #E7ECF3' }}>
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg flex items-center justify-center text-white" style={{ background: GRAD }}>
                <MessageCircle className="w-4 h-4" />
              </div>
              <span className="text-sm font-semibold" style={{ color: '#16233f' }}>Assistente Conecta</span>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="Fechar"
              className="w-8 h-8 flex items-center justify-center rounded-lg transition-colors hover:bg-[#F1F4FA]"
              style={{ color: '#6b7280', background: 'transparent', border: 'none' }}
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Mensagens */}
          <div className="flex-1 overflow-y-auto px-4 py-3 flex flex-col gap-3">
            {msgs.length === 0 && (
              <div className="m-auto text-center max-w-[300px]">
                <p className="text-sm mb-3" style={{ color: '#6b7280' }}>Como posso ajudar?</p>
                <div className="flex flex-wrap gap-2 justify-center">
                  {SUGGESTIONS.map((s, i) => (
                    <button
                      key={i}
                      type="button"
                      onClick={() => send(s)}
                      className="px-3 py-1.5 text-xs rounded-full transition-colors hover:bg-[#F1F4FA]"
                      style={{ border: '1px solid #E7ECF3', color: '#1a2233', background: '#fff' }}
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {msgs.map((m, i) => {
              const mine = m.role === 'user';
              return (
                <div key={i} className={mine ? 'self-end max-w-[85%]' : 'self-start max-w-[85%]'}>
                  <div
                    className="px-3.5 py-2.5 rounded-2xl text-[13px] leading-relaxed whitespace-pre-wrap"
                    style={
                      mine
                        ? { background: NAVY, color: '#fff', borderBottomRightRadius: 4 }
                        : m.aviso
                        ? { background: '#FEF3E7', color: '#8a4b0a', border: '1px solid #F7C99A', borderBottomLeftRadius: 4 }
                        : { background: '#F1F4FA', color: '#1a2233', border: '1px solid #E7ECF3', borderBottomLeftRadius: 4 }
                    }
                  >
                    {m.text}
                  </div>
                  {!mine && m.docs && m.docs.length > 0 && (
                    <div className="flex flex-col gap-1.5 mt-2">
                      {m.docs.map((doc, j) => (
                        <button
                          key={j}
                          type="button"
                          onClick={() => downloadPdf(doc.nome || 'documento.pdf', doc.arquivo_base64 || '')}
                          className="flex items-center gap-2 px-3 py-2 rounded-lg text-left transition-colors hover:bg-[#F1F4FA]"
                          style={{ border: '1px solid #E7ECF3', background: '#fff' }}
                          title={doc.resumo || doc.nome}
                        >
                          <Download className="w-4 h-4 flex-shrink-0" style={{ color: '#F26522' }} />
                          <span className="text-xs font-medium truncate" style={{ color: '#16233f' }}>{doc.nome || 'documento.pdf'}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
            {busy && (
              <div className="self-start flex items-center gap-2 text-xs" style={{ color: '#6b7280' }}>
                <Loader2 className="w-3.5 h-3.5 animate-spin" /> pensando…
              </div>
            )}
            <div ref={endRef} />
          </div>

          {/* Rodapé — textarea + enviar */}
          <form
            onSubmit={(e) => { e.preventDefault(); send(input); }}
            className="flex-shrink-0 flex items-end gap-2 p-3"
            style={{ borderTop: '1px solid #E7ECF3' }}
          >
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input); } }}
              placeholder="Pergunte ou peça um documento…"
              rows={1}
              disabled={busy}
              aria-label="Sua mensagem"
              className="flex-1 resize-none max-h-28 rounded-xl px-3 py-2 text-[13px] outline-none disabled:opacity-60"
              style={{ border: '1px solid #E7ECF3', background: '#F1F4FA', color: '#1a2233' }}
            />
            <button
              type="submit"
              disabled={busy || !input.trim()}
              aria-label="Enviar"
              className="w-9 h-9 flex-shrink-0 flex items-center justify-center rounded-xl text-white disabled:opacity-40 transition-opacity"
              style={{ background: NAVY, border: 'none' }}
            >
              <Send className="w-4 h-4" />
            </button>
          </form>
        </div>
      )}
    </>
  );
}
