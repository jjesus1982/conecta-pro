'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { msgFromDetail } from '@/lib/string';
import { Bot, Send, ThumbsDown, ThumbsUp, X } from 'lucide-react';
import { toast } from 'sonner';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  feedbackGiven?: 'positive' | 'negative';
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
}

function generateSessionId(): string {
  return `portal-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

async function portalFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('portal_token');
  const res = await fetch(`${API_BASE}/api/v1/portal${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers ?? {}),
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(msgFromDetail(err.detail) || 'Erro na requisição');
  }
  return res.json() as Promise<T>;
}

export default function PortalAssistantWidget() {
  const [isOpen, setIsOpen] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [sessionId] = useState<string>(() => generateSessionId());
  const [greetingLoaded, setGreetingLoaded] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Verifica autenticacao no lado do cliente
  useEffect(() => {
    const token = localStorage.getItem('portal_token');
    setIsAuthenticated(!!token);
  }, []);

  // Carrega saudação ao abrir o widget pela primeira vez
  const loadGreeting = useCallback(async () => {
    if (greetingLoaded) return;
    setGreetingLoaded(true);

    try {
      const data = await portalFetch<{ greeting: string; suggestions: string[] }>(
        '/assistente/greeting'
      );
      setSuggestions(data.suggestions ?? []);
      setMessages([
        {
          id: 'greeting',
          role: 'assistant',
          content: data.greeting,
          timestamp: new Date(),
        },
      ]);
    } catch {
      setSuggestions([
        'Status dos meus kits',
        'Como baixar meus documentos?',
        'Abrir um chamado',
      ]);
      setMessages([
        {
          id: 'greeting',
          role: 'assistant',
          content:
            'Olá! Sou o assistente do portal da Conecta PRO. Como posso ajudá-lo?',
          timestamp: new Date(),
        },
      ]);
    }
  }, [greetingLoaded]);

  const handleOpen = useCallback(() => {
    setIsOpen(true);
    loadGreeting();
    setTimeout(() => inputRef.current?.focus(), 100);
  }, [loadGreeting]);

  // Scroll automático
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isLoading]);

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isLoading) return;

      const userMsg: Message = {
        id: `u-${Date.now()}`,
        role: 'user',
        content: trimmed,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, userMsg]);
      setInput('');
      setIsLoading(true);

      try {
        const data = await portalFetch<{
          response: string;
          suggestions: string[];
          session_id: string;
          message_id: string;
        }>('/assistente/send', {
          method: 'POST',
          body: JSON.stringify({ message: trimmed, session_id: sessionId }),
        });

        const assistantMsg: Message = {
          id: data.message_id,
          role: 'assistant',
          content: data.response,
          timestamp: new Date(),
        };

        setMessages((prev) => [...prev, assistantMsg]);

        if (data.suggestions?.length) {
          setSuggestions(data.suggestions);
        }
      } catch (err) {
        const errMsg = err instanceof Error ? err.message : 'Erro inesperado';
        toast.error(`Erro ao enviar mensagem: ${errMsg}`);
        setMessages((prev) => [
          ...prev,
          {
            id: `err-${Date.now()}`,
            role: 'assistant',
            content:
              'Desculpe, ocorreu um erro ao processar sua mensagem. Tente novamente em instantes.',
            timestamp: new Date(),
          },
        ]);
      } finally {
        setIsLoading(false);
        setTimeout(() => inputRef.current?.focus(), 50);
      }
    },
    [isLoading, sessionId]
  );

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      sendMessage(input);
    },
    [input, sendMessage]
  );

  const handleSuggestion = useCallback(
    (suggestion: string) => {
      sendMessage(suggestion);
    },
    [sendMessage]
  );

  const handleFeedback = useCallback(
    async (messageId: string, rating: 'positive' | 'negative') => {
      setMessages((prev) =>
        prev.map((m) => (m.id === messageId ? { ...m, feedbackGiven: rating } : m))
      );
      try {
        await portalFetch('/assistente/feedback', {
          method: 'POST',
          body: JSON.stringify({ message_id: messageId, rating }),
        });
      } catch {
        // Falha silenciosa no feedback
      }
    },
    []
  );

  // Nao renderiza se nao autenticado
  if (!isAuthenticated) return null;

  return (
    <>
      {/* Botao flutuante */}
      {!isOpen && (
        <button
          onClick={handleOpen}
          className="fixed bottom-6 right-6 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-indigo-600 text-white shadow-lg hover:bg-indigo-700 transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
          aria-label="Abrir assistente virtual"
        >
          <Bot className="h-7 w-7" />
        </button>
      )}

      {/* Painel do chat */}
      {isOpen && (
        <div className="fixed bottom-6 right-6 z-50 flex flex-col w-96 h-[520px] rounded-2xl shadow-2xl border border-gray-200 bg-white overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between bg-indigo-600 px-4 py-3">
            <div className="flex items-center gap-2">
              <Bot className="h-5 w-5 text-indigo-200" />
              <div>
                <p className="text-sm font-semibold text-white">Assistente Conecta PRO</p>
                <p className="text-xs text-indigo-200">Portal do Cliente</p>
              </div>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              className="text-indigo-200 hover:text-white transition-colors"
              aria-label="Fechar assistente"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Mensagens */}
          <div
            ref={scrollRef}
            className="flex-1 overflow-y-auto p-4 space-y-4 bg-gray-50"
          >
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div className="max-w-[80%]">
                  <div
                    className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                      msg.role === 'user'
                        ? 'bg-indigo-600 text-white rounded-br-sm'
                        : 'bg-white text-gray-800 border border-gray-200 rounded-bl-sm shadow-sm'
                    }`}
                  >
                    {msg.content}
                  </div>
                  <div
                    className={`mt-1 flex items-center gap-2 ${
                      msg.role === 'user' ? 'justify-end' : 'justify-start'
                    }`}
                  >
                    <span className="text-xs text-gray-400">{formatTime(msg.timestamp)}</span>
                    {msg.role === 'assistant' && msg.id !== 'greeting' && (
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => handleFeedback(msg.id, 'positive')}
                          disabled={!!msg.feedbackGiven}
                          className={`rounded p-0.5 transition-colors ${
                            msg.feedbackGiven === 'positive'
                              ? 'text-green-500'
                              : 'text-gray-300 hover:text-green-500'
                          }`}
                          aria-label="Resposta útil"
                        >
                          <ThumbsUp className="h-3 w-3" />
                        </button>
                        <button
                          onClick={() => handleFeedback(msg.id, 'negative')}
                          disabled={!!msg.feedbackGiven}
                          className={`rounded p-0.5 transition-colors ${
                            msg.feedbackGiven === 'negative'
                              ? 'text-red-400'
                              : 'text-gray-300 hover:text-red-400'
                          }`}
                          aria-label="Resposta não útil"
                        >
                          <ThumbsDown className="h-3 w-3" />
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}

            {/* Indicador de carregamento */}
            {isLoading && (
              <div className="flex justify-start">
                <div className="bg-white border border-gray-200 rounded-2xl rounded-bl-sm px-4 py-3 shadow-sm">
                  <div className="flex items-center gap-1.5">
                    <div className="h-2 w-2 rounded-full bg-indigo-400 animate-bounce [animation-delay:-0.3s]" />
                    <div className="h-2 w-2 rounded-full bg-indigo-400 animate-bounce [animation-delay:-0.15s]" />
                    <div className="h-2 w-2 rounded-full bg-indigo-400 animate-bounce" />
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Sugestoes */}
          {suggestions.length > 0 && !isLoading && (
            <div className="px-3 py-2 border-t border-gray-100 bg-white flex gap-1.5 overflow-x-auto scrollbar-hide">
              {suggestions.slice(0, 4).map((s) => (
                <button
                  key={s}
                  onClick={() => handleSuggestion(s)}
                  className="flex-shrink-0 rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-xs text-indigo-700 hover:bg-indigo-100 transition-colors whitespace-nowrap"
                >
                  {s}
                </button>
              ))}
            </div>
          )}

          {/* Input */}
          <form
            onSubmit={handleSubmit}
            className="flex items-center gap-2 border-t border-gray-200 bg-white px-3 py-3"
          >
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Digite sua pergunta..."
              disabled={isLoading}
              className="flex-1 rounded-full border border-gray-300 bg-gray-50 px-4 py-2 text-sm text-gray-800 placeholder-gray-400 focus:border-indigo-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-200 disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={!input.trim() || isLoading}
              className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-indigo-600 text-white transition-colors hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-1"
              aria-label="Enviar mensagem"
            >
              <Send className="h-4 w-4" />
            </button>
          </form>
        </div>
      )}
    </>
  );
}
