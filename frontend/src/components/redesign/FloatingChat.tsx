'use client';
// FloatingChat — assistente flutuante (FAB + painel) disponível em toda tela autenticada,
// tanto no /modulos quanto no /redesign. Estilo LITERAL próprio (marca Navy→Laranja, painel
// claro) porque os dois ambientes usam sistemas de token de cor diferentes e incompatíveis
// (/modulos = hsl(var(--card)) shadcn; /redesign = --surface/--ink/--orange). Cores literais
// = funciona igual nos dois, sem depender do tema do host.
// Chama POST /api/v1/consultores/chat/executar (gera-doc p/ todos os perfis) e baixa os PDFs
// que a resposta traz em d.documentos[]. Bearer do localStorage access_token (URL relativa).
import { useState, useRef, useEffect } from 'react';
import { MessageCircle, X, Send, Download, Loader2, Paperclip, Mic, Volume2, VolumeX } from 'lucide-react';

type Doc = { nome?: string; arquivo_base64?: string; resumo?: string };
type Msg = { role: 'user' | 'assistant'; text: string; docs?: Doc[]; aviso?: boolean };

const ENDPOINT = '/api/v1/consultores/chat/executar';
const ENDPOINT_ARQUIVO = '/api/v1/consultores/chat/executar-arquivo';
const ACCEPT = '.pdf,.docx,.txt,.png,.jpg,.jpeg,.webp';
const SUGGESTIONS = ['Gera o DRE do mês', 'Meu holerite', 'Monta uma proposta'];
const NAVY = '#16277D';
const GRAD = 'linear-gradient(135deg, #16277D, #F26522)';
// Rota → lente ativa (rótulo p/ o usuário ver que o chat assumiu a persona do módulo).
const PERSONA_LABEL: Record<string, string> = {
  financeiro: 'CFO', crm: 'Comercial', juridico: 'Jurídico', fiscal: 'Fiscal',
  operacional: 'Operacional', 'departamento-pessoal': 'DP/RH', 'gestao-de-pessoas': 'DP/RH',
  rh: 'DP/RH', ged: 'GED', documentos: 'GED', aprovacoes: 'Executivo',
};

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
  const [file, setFile] = useState<File | null>(null);
  const [persona, setPersona] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);
  const endRef = useRef<HTMLDivElement>(null);

  // ── Voz (Web Speech API) — POC: ditar e ouvir ───────────────────────────────
  // Roda 100% no navegador: o áudio NÃO sai daqui e não há custo por uso. Por isso
  // não usamos Gemini Live/Whisper nesta prova — se a interação por voz provar valor,
  // aí sim vale STT/TTS próprio (faster-whisper + Kokoro) para ter voz melhor.
  const [ouvindo, setOuvindo] = useState(false);
  const [falarRespostas, setFalarRespostas] = useState(false);
  const [temVoz, setTemVoz] = useState(false);
  const recRef = useRef<any>(null);
  const ultimaFaladaRef = useRef<string>('');

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    setTemVoz(!!SR && 'speechSynthesis' in window);
  }, []);

  // Lê a última resposta do assistente quando o alto-falante está ligado.
  useEffect(() => {
    if (!falarRespostas || typeof window === 'undefined' || !('speechSynthesis' in window)) return;
    const ultima = [...msgs].reverse().find((m) => m.role === 'assistant');
    if (!ultima || !ultima.text || ultima.text === ultimaFaladaRef.current) return;
    ultimaFaladaRef.current = ultima.text;
    try {
      window.speechSynthesis.cancel();
      // Markdown e URL não se leem bem em voz alta; limpa antes de falar.
      const limpo = ultima.text.replace(/[*_`#>|]/g, '').replace(/https?:\/\/\S+/g, 'link').slice(0, 700);
      const u = new SpeechSynthesisUtterance(limpo);
      u.lang = 'pt-BR';
      u.rate = 1.05;
      const vozPt = window.speechSynthesis.getVoices().find((v) => v.lang?.toLowerCase().startsWith('pt'));
      if (vozPt) u.voice = vozPt;
      window.speechSynthesis.speak(u);
    } catch { /* voz é opcional: falhar aqui nunca quebra o chat */ }
  }, [msgs, falarRespostas]);

  // Erro de voz PRECISA aparecer: a 1ª versão engolia a falha e o botão parecia morto.
  function avisoVoz(texto: string) {
    setMsgs((m) => [...m, { role: 'assistant', text: texto, aviso: true }]);
  }

  async function alternarMicrofone() {
    if (typeof window === 'undefined') return;
    if (ouvindo) { try { recRef.current?.stop(); } catch { /* */ } return; }
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) { avisoVoz('Este navegador não reconhece voz. Use o Chrome ou o Edge.'); return; }

    // Pede o microfone ANTES: é o que faz o navegador mostrar o pedido de permissão.
    // Sem isto o SpeechRecognition podia falhar calado quando a permissão não existia.
    try {
      const st = await navigator.mediaDevices.getUserMedia({ audio: true });
      st.getTracks().forEach((t) => t.stop());   // só queríamos a permissão
    } catch {
      avisoVoz('Preciso do microfone para ouvir. Clique no cadeado 🔒 ao lado do endereço, '
             + 'libere o Microfone e tente de novo.');
      return;
    }

    const rec = new SR();
    rec.lang = 'pt-BR';
    rec.interimResults = true;   // mostra o texto enquanto fala
    rec.continuous = false;      // encerra sozinho no silêncio
    let ditado = '';
    rec.onresult = (e: any) => {
      let parcial = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) ditado += t; else parcial += t;
      }
      setInput((ditado + parcial).trim());
    };
    let erro = '';
    rec.onerror = (e: any) => {
      erro = e?.error || 'desconhecido';
      setOuvindo(false);
      // 'no-speech' e 'aborted' são normais (silêncio / usuário parou): não viram aviso.
      if (erro === 'no-speech' || erro === 'aborted') return;
      const recado: Record<string, string> = {
        'not-allowed': 'O microfone está bloqueado para este site. Clique no cadeado 🔒 ao lado do endereço, libere o Microfone e recarregue.',
        'service-not-allowed': 'O navegador bloqueou o serviço de voz. Verifique as permissões do site.',
        'audio-capture': 'Não encontrei nenhum microfone conectado.',
        network: 'O reconhecimento de voz do Chrome precisa de internet e não conseguiu conectar.',
      };
      avisoVoz(recado[erro] || `Não consegui usar o microfone (${erro}).`);
    };
    rec.onend = () => {
      setOuvindo(false);
      // Envia sozinho ao terminar de falar — é o que dá sensação de conversa.
      // Seguro porque o chat CRIA RASCUNHO: nada é executado sem aprovação humana.
      const texto = ditado.trim();
      if (texto) send(texto);
      else if (!erro) avisoVoz('Não captei nenhuma fala. Tente falar mais perto do microfone.');
    };
    try {
      rec.start();
      recRef.current = rec;
      setOuvindo(true);
    } catch (e: any) {
      setOuvindo(false);
      avisoVoz(`Não consegui iniciar o microfone: ${e?.message || e}`);
    }
  }

  useEffect(() => { if (open) endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [msgs, busy, open]);
  // Ao fechar o painel: para de ouvir e de falar (nada continua rodando escondido).
  useEffect(() => {
    if (open) return;
    try { recRef.current?.stop(); } catch { /* */ }
    try { window.speechSynthesis?.cancel(); } catch { /* */ }
  }, [open]);
  useEffect(() => {
    if (!open) return;
    try { setPersona(window.location.pathname.match(/\/redesign\/([a-z-]+)/)?.[1] || ''); } catch { /* */ }
  }, [open]);

  async function send(pergunta: string) {
    const q = (pergunta || '').trim();
    const anexo = file;
    if ((!q && !anexo) || busy) return;
    setInput('');
    setFile(null);
    if (fileRef.current) fileRef.current.value = '';
    setMsgs((m) => [...m, { role: 'user', text: anexo ? `📎 ${anexo.name}${q ? `\n${q}` : ''}` : q }]);
    setBusy(true);
    let tok: string | null = null;
    try { tok = localStorage.getItem('access_token'); } catch { /* */ }
    // Persona por CONTEXTO: a rota atual vira a lente (ex.: /redesign/financeiro → CFO).
    let persona = '';
    try { persona = (window.location.pathname.match(/\/redesign\/([a-z-]+)/)?.[1]) || ''; } catch { /* */ }
    try {
      const auth = tok ? { Authorization: `Bearer ${tok}` } : {};
      const res = anexo
        ? await (() => {
            const fd = new FormData();
            fd.append('arquivo', anexo);
            fd.append('pergunta', q);
            if (persona) fd.append('persona', persona);
            return fetch(ENDPOINT_ARQUIVO, { method: 'POST', headers: auth, body: fd });
          })()
        : await fetch(ENDPOINT, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...auth },
            body: JSON.stringify({ pergunta: q, persona }),
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
              {PERSONA_LABEL[persona] && (
                <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full" style={{ background: 'rgba(242,101,34,0.14)', color: '#C2410C' }}>
                  {PERSONA_LABEL[persona]}
                </span>
              )}
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

          {/* Rodapé — anexo + textarea + enviar */}
          <form
            onSubmit={(e) => { e.preventDefault(); send(input); }}
            className="flex-shrink-0 flex flex-col gap-2 p-3"
            style={{ borderTop: '1px solid #E7ECF3' }}
          >
            {file && (
              <div
                className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-xs"
                style={{ background: '#F1F4FA', border: '1px solid #E7ECF3', color: '#16233f' }}
              >
                <Paperclip className="w-3.5 h-3.5 flex-shrink-0" style={{ color: '#F26522' }} />
                <span className="flex-1 truncate">{file.name}</span>
                <button
                  type="button"
                  onClick={() => { setFile(null); if (fileRef.current) fileRef.current.value = ''; }}
                  aria-label="Remover anexo"
                  className="flex-shrink-0"
                  style={{ color: '#6b7280', background: 'transparent', border: 'none' }}
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            )}
          <div className="flex items-end gap-2">
            <input
              ref={fileRef}
              type="file"
              accept={ACCEPT}
              className="hidden"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
            />
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              disabled={busy}
              aria-label="Anexar arquivo (PDF, foto, documento)"
              title="Anexar PDF, foto ou documento"
              className="w-9 h-9 flex-shrink-0 flex items-center justify-center rounded-xl disabled:opacity-40 transition-colors hover:bg-[#F1F4FA]"
              style={{ border: '1px solid #E7ECF3', background: '#fff', color: '#16277D' }}
            >
              <Paperclip className="w-4 h-4" />
            </button>
            {temVoz && (
              <>
                <button
                  type="button"
                  onClick={alternarMicrofone}
                  disabled={busy}
                  aria-label={ouvindo ? 'Parar de ouvir' : 'Falar em vez de digitar'}
                  title={ouvindo ? 'Ouvindo… fale e pare para enviar' : 'Falar em vez de digitar'}
                  className="relative w-9 h-9 flex-shrink-0 flex items-center justify-center rounded-xl disabled:opacity-40 transition-colors hover:bg-[#F1F4FA]"
                  style={ouvindo
                    ? { border: '1px solid #F26522', background: '#F26522', color: '#fff' }
                    : { border: '1px solid #E7ECF3', background: '#fff', color: '#16277D' }}
                >
                  <Mic className="w-4 h-4" />
                  {ouvindo && (
                    <span
                      aria-hidden
                      className="absolute w-9 h-9 rounded-xl"
                      style={{ border: '2px solid #F26522', animation: 'ping 1.4s cubic-bezier(0,0,.2,1) infinite' }}
                    />
                  )}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setFalarRespostas((v) => {
                      if (v) { try { window.speechSynthesis?.cancel(); } catch { /* */ } }
                      return !v;
                    });
                  }}
                  aria-label={falarRespostas ? 'Desligar leitura em voz alta' : 'Ler respostas em voz alta'}
                  title={falarRespostas ? 'Leitura em voz alta ligada' : 'Ler respostas em voz alta'}
                  className="w-9 h-9 flex-shrink-0 flex items-center justify-center rounded-xl transition-colors hover:bg-[#F1F4FA]"
                  style={falarRespostas
                    ? { border: '1px solid #16277D', background: '#16277D', color: '#fff' }
                    : { border: '1px solid #E7ECF3', background: '#fff', color: '#6b7280' }}
                >
                  {falarRespostas ? <Volume2 className="w-4 h-4" /> : <VolumeX className="w-4 h-4" />}
                </button>
              </>
            )}
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input); } }}
              placeholder={ouvindo ? 'Ouvindo… pode falar' : (file ? 'Pergunte sobre o anexo (opcional)…' : 'Pergunte, fale pelo microfone ou anexe um PDF/foto…')}
              rows={1}
              disabled={busy}
              aria-label="Sua mensagem"
              className="flex-1 resize-none max-h-28 rounded-xl px-3 py-2 text-[13px] outline-none disabled:opacity-60"
              style={{ border: '1px solid #E7ECF3', background: '#F1F4FA', color: '#1a2233' }}
            />
            <button
              type="submit"
              disabled={busy || (!input.trim() && !file)}
              aria-label="Enviar"
              className="w-9 h-9 flex-shrink-0 flex items-center justify-center rounded-xl text-white disabled:opacity-40 transition-opacity"
              style={{ background: NAVY, border: 'none' }}
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
          </form>
        </div>
      )}
    </>
  );
}
