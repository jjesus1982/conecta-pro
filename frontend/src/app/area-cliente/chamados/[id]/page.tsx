'use client';

import React, { useEffect, useState, useCallback, FormEvent, useRef } from 'react';
import { msgFromDetail } from '@/lib/string';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import {
  ArrowLeft, Send, Loader2, XCircle, Paperclip, Download, AlertTriangle,
} from 'lucide-react';
import { toast } from 'sonner';

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || '') + '/api/v1/portal';

function getPortalHeaders() {
  const token = typeof window !== 'undefined' ? localStorage.getItem('portal_token') : null;
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

interface TicketMessage {
  id: string;
  ticket_id: string;
  sender_name: string;
  sender_type: string; // CLIENT or INTERNAL
  message: string;
  created_at: string;
  attachments?: { name: string; url: string }[] | null;
}

interface TicketDetail {
  id: string;
  subject: string;
  description: string;
  status: string;
  priority: string;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
  messages: TicketMessage[];
}

const statusLabels: Record<string, string> = {
  ABERTO: 'Aberto',
  EM_ANDAMENTO: 'Em Andamento',
  RESPONDIDO: 'Respondido',
  FECHADO: 'Fechado',
};

const statusColors: Record<string, string> = {
  ABERTO: 'bg-blue-100 text-blue-800',
  EM_ANDAMENTO: 'bg-yellow-100 text-yellow-800',
  RESPONDIDO: 'bg-green-100 text-green-800',
  FECHADO: 'bg-gray-100 text-gray-600',
};

const priorityLabels: Record<string, string> = {
  BAIXA: 'Baixa',
  NORMAL: 'Normal',
  ALTA: 'Alta',
  URGENTE: 'Urgente',
};

const priorityColors: Record<string, string> = {
  BAIXA: 'bg-gray-100 text-gray-600',
  NORMAL: 'bg-blue-100 text-blue-700',
  ALTA: 'bg-orange-100 text-orange-700',
  URGENTE: 'bg-red-100 text-red-700',
};

function formatDateTime(dateStr: string): string {
  if (!dateStr) return '';
  try {
    return new Date(dateStr).toLocaleDateString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return dateStr;
  }
}

export default function ChamadoDetailPage() {
  const params = useParams();
  const ticketId = params.id as string;
  const [ticket, setTicket] = useState<TicketDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [replyText, setReplyText] = useState('');
  const [sending, setSending] = useState(false);
  const [closing, setClosing] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const fetchTicket = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`${API_BASE}/tickets/${ticketId}`, {
        headers: getPortalHeaders(),
      });

      if (res.status === 401) {
        toast.error('Sessao expirada. Faca login novamente.', { duration: 5000 });
        return;
      }

      if (res.status === 404) {
        setError('Chamado nao encontrado.');
        return;
      }

      if (!res.ok) {
        setError('Erro ao carregar chamado.');
        return;
      }

      const data: TicketDetail = await res.json();
      setTicket(data);
    } catch {
      setError('Erro ao carregar chamado.');
      toast.error('Erro ao carregar chamado. Verifique sua conexao.', { duration: 5000 });
    } finally {
      setLoading(false);
    }
  }, [ticketId]);

  useEffect(() => {
    fetchTicket();
  }, [fetchTicket]);

  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [ticket?.messages]);

  async function handleSendMessage(e: FormEvent) {
    e.preventDefault();
    if (!replyText.trim()) return;
    setSending(true);
    try {
      const res = await fetch(`${API_BASE}/tickets/${ticketId}/messages`, {
        method: 'POST',
        headers: getPortalHeaders(),
        body: JSON.stringify({ message: replyText.trim() }),
      });
      if (res.ok) {
        const updatedTicket: TicketDetail = await res.json();
        setTicket(updatedTicket);
        setReplyText('');
        toast.success('Mensagem enviada com sucesso!', { duration: 4000 });
      } else {
        const data = await res.json().catch(() => null);
        toast.error(msgFromDetail(data?.detail) || 'Erro ao enviar mensagem.', { duration: 5000 });
      }
    } catch {
      toast.error('Erro ao enviar mensagem. Tente novamente.', { duration: 5000 });
    } finally {
      setSending(false);
    }
  }

  async function handleClose() {
    if (!confirm('Deseja fechar este chamado?')) return;
    setClosing(true);
    try {
      const res = await fetch(`${API_BASE}/tickets/${ticketId}/close`, {
        method: 'PATCH',
        headers: getPortalHeaders(),
      });
      if (res.ok) {
        const updatedTicket: TicketDetail = await res.json();
        setTicket(updatedTicket);
        toast.success('Chamado fechado com sucesso.', { duration: 4000 });
      } else {
        const data = await res.json().catch(() => null);
        toast.error(msgFromDetail(data?.detail) || 'Erro ao fechar chamado.', { duration: 5000 });
      }
    } catch {
      toast.error('Erro ao fechar chamado. Tente novamente.', { duration: 5000 });
    } finally {
      setClosing(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
      </div>
    );
  }

  if (error && !ticket) {
    return (
      <div className="text-center py-20">
        <AlertTriangle className="h-12 w-12 text-gray-300 mx-auto mb-4" />
        <p className="text-gray-500">{error}</p>
        <Link href="/area-cliente/chamados" className="text-indigo-600 hover:underline text-sm mt-2 inline-block">
          Voltar para Chamados
        </Link>
      </div>
    );
  }

  if (!ticket) {
    return (
      <div className="text-center py-20">
        <p className="text-gray-500">Chamado nao encontrado.</p>
        <Link href="/area-cliente/chamados" className="text-indigo-600 hover:underline text-sm mt-2 inline-block">
          Voltar para Chamados
        </Link>
      </div>
    );
  }

  const isClosed = ticket.status === 'FECHADO';
  const messages = ticket.messages || [];

  return (
    <div className="space-y-6 pb-28">
      {/* Back */}
      <Link
        href="/area-cliente/chamados"
        className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-indigo-600 transition-colors"
      >
        <ArrowLeft className="h-4 w-4" />
        Voltar para Chamados
      </Link>

      {/* Header */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-gray-900">{ticket.subject}</h1>
            <p className="text-xs text-gray-400 mt-1">
              Aberto em {formatDateTime(ticket.created_at)}
            </p>
            {ticket.description && (
              <p className="text-sm text-gray-600 mt-3">{ticket.description}</p>
            )}
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <span
              className={`text-xs font-medium px-2.5 py-1 rounded-full ${
                statusColors[ticket.status] || 'bg-gray-100 text-gray-600'
              }`}
            >
              {statusLabels[ticket.status] || ticket.status}
            </span>
            <span
              className={`text-xs font-medium px-2.5 py-1 rounded-full ${
                priorityColors[ticket.priority] || 'bg-gray-100 text-gray-600'
              }`}
            >
              {priorityLabels[ticket.priority] || ticket.priority}
            </span>
          </div>
        </div>
      </div>

      {/* Messages */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <h2 className="text-sm font-semibold text-gray-700 mb-4">
          Conversacao ({messages.length} {messages.length === 1 ? 'mensagem' : 'mensagens'})
        </h2>
        <div className="space-y-4 max-h-[500px] overflow-y-auto pr-2">
          {messages.length === 0 ? (
            <p className="text-center text-gray-400 text-sm py-8">Nenhuma mensagem ainda.</p>
          ) : (
            messages.map((msg) => {
              const isClient = msg.sender_type === 'CLIENT';
              return (
                <div
                  key={msg.id}
                  className={`flex ${isClient ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[75%] rounded-xl px-4 py-3 ${
                      isClient
                        ? 'bg-indigo-50 border border-indigo-100'
                        : 'bg-gray-50 border border-gray-100'
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs font-semibold text-gray-700">
                        {msg.sender_name}
                      </span>
                      <span className="text-xs text-gray-400">
                        {formatDateTime(msg.created_at)}
                      </span>
                    </div>
                    <p className="text-sm text-gray-700 whitespace-pre-wrap">{msg.message}</p>
                    {/* Attachments */}
                    {msg.attachments && msg.attachments.length > 0 && (
                      <div className="mt-2 space-y-1">
                        {msg.attachments.map((att, idx) => (
                          <a
                            key={idx}
                            href={att.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center gap-1.5 text-xs text-indigo-600 hover:text-indigo-800"
                          >
                            <Paperclip className="h-3 w-3" />
                            {att.name}
                            <Download className="h-3 w-3" />
                          </a>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              );
            })
          )}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Reply / Close */}
      {!isClosed ? (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <form onSubmit={handleSendMessage} className="space-y-4">
            <textarea
              value={replyText}
              onChange={(e) => setReplyText(e.target.value)}
              placeholder="Digite sua mensagem..."
              rows={4}
              className="w-full border border-gray-300 rounded-lg px-4 py-3 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none resize-none text-gray-900 placeholder-gray-400"
            />
            <div className="flex items-center justify-between">
              <button
                type="button"
                onClick={handleClose}
                disabled={closing}
                className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-red-600 transition-colors disabled:opacity-50"
              >
                {closing ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <XCircle className="h-4 w-4" />
                )}
                Fechar Chamado
              </button>
              <button
                type="submit"
                disabled={sending || !replyText.trim()}
                className="flex items-center gap-2 bg-indigo-600 text-white px-5 py-2.5 rounded-lg font-medium hover:bg-indigo-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {sending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
                Enviar
              </button>
            </div>
          </form>
        </div>
      ) : (
        <div className="bg-gray-50 rounded-xl border border-gray-200 p-6 text-center text-sm text-gray-500">
          Este chamado foi fechado{ticket.closed_at ? ` em ${formatDateTime(ticket.closed_at)}` : ''}. Para novas solicitacoes, abra um novo chamado.
        </div>
      )}
    </div>
  );
}
