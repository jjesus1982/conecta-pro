'use client';

import React, { useEffect, useState, FormEvent } from 'react';
import { msgFromDetail } from '@/lib/string';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { ArrowLeft, Send, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || '') + '/api/v1/portal';

function getPortalHeaders() {
  const token = typeof window !== 'undefined' ? localStorage.getItem('portal_token') : null;
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

interface KitOption {
  id: string;
  reference_month: string;
}

const priorityOptions = [
  { value: 'BAIXA', label: 'Baixa' },
  { value: 'NORMAL', label: 'Normal' },
  { value: 'ALTA', label: 'Alta' },
  { value: 'URGENTE', label: 'Urgente' },
];

function formatMonth(dateStr: string): string {
  if (!dateStr) return '-';
  try {
    const d = new Date(dateStr + (dateStr.length <= 10 ? 'T00:00:00' : ''));
    return d.toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' });
  } catch {
    return dateStr;
  }
}

export default function NovoChamadoPage() {
  const router = useRouter();
  const [subject, setSubject] = useState('');
  const [kitId, setKitId] = useState('');
  const [priority, setPriority] = useState('NORMAL');
  const [description, setDescription] = useState('');
  const [kits, setKits] = useState<KitOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    async function fetchKits() {
      try {
        const res = await fetch(`${API_BASE}/kits?limit=100`, { headers: getPortalHeaders() });
        if (res.ok) {
          const data = await res.json();
          const items: KitOption[] = Array.isArray(data) ? data : data.items || [];
          setKits(items);
        }
      } catch {
        // Kit list is optional, silently handle
      }
    }
    fetchKits();
  }, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError('');

    if (!subject.trim()) {
      setError('Informe o assunto do chamado.');
      toast.error('Informe o assunto do chamado.', { duration: 5000 });
      return;
    }
    if (subject.trim().length < 3) {
      setError('O assunto deve ter pelo menos 3 caracteres.');
      toast.error('O assunto deve ter pelo menos 3 caracteres.', { duration: 5000 });
      return;
    }
    if (!description.trim()) {
      setError('Descreva o motivo do chamado.');
      toast.error('Descreva o motivo do chamado.', { duration: 5000 });
      return;
    }
    if (description.trim().length < 10) {
      setError('A descricao deve ter pelo menos 10 caracteres.');
      toast.error('A descricao deve ter pelo menos 10 caracteres.', { duration: 5000 });
      return;
    }

    setLoading(true);
    try {
      const body: Record<string, unknown> = {
        subject: subject.trim(),
        priority,
        description: description.trim(),
      };
      if (kitId) body.kit_id = kitId;

      const res = await fetch(`${API_BASE}/tickets`, {
        method: 'POST',
        headers: getPortalHeaders(),
        body: JSON.stringify(body),
      });

      if (res.status === 401) {
        toast.error('Sessao expirada. Faca login novamente.', { duration: 5000 });
        return;
      }

      if (!res.ok) {
        const data = await res.json().catch(() => null);
        throw new Error(msgFromDetail(data?.detail) || 'Erro ao criar chamado.');
      }

      toast.success('Chamado criado com sucesso! Nossa equipe respondera em breve.', { duration: 4000 });
      router.push('/area-cliente/chamados');
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Erro ao enviar chamado. Tente novamente.';
      setError(message);
      toast.error(message, { duration: 5000 });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6 max-w-2xl pb-28">
      {/* Back */}
      <Link
        href="/area-cliente/chamados"
        className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-indigo-600 transition-colors"
      >
        <ArrowLeft className="h-4 w-4" />
        Voltar para Chamados
      </Link>

      <div>
        <h1 className="font-display text-2xl font-bold text-[hsl(var(--foreground))]">Novo Chamado</h1>
        <p className="text-gray-500 text-sm mt-1">
          Preencha os dados abaixo para abrir uma solicitacao.
        </p>
      </div>

      {/* Error */}
      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Form */}
      <form onSubmit={handleSubmit} className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 space-y-5">
        {/* Subject */}
        <div>
          <label htmlFor="subject" className="block text-sm font-medium text-gray-700 mb-1">
            Assunto *
          </label>
          <input
            id="subject"
            type="text"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            placeholder="Resumo da sua solicitacao"
            required
            minLength={3}
            maxLength={200}
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none text-gray-900 placeholder-gray-400"
          />
        </div>

        {/* Kit selector */}
        <div>
          <label htmlFor="kit" className="block text-sm font-medium text-gray-700 mb-1">
            Kit Relacionado <span className="text-gray-400">(opcional)</span>
          </label>
          <select
            id="kit"
            value={kitId}
            onChange={(e) => setKitId(e.target.value)}
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none text-gray-900 bg-white"
          >
            <option value="">Nenhum kit selecionado</option>
            {kits.map((kit) => (
              <option key={kit.id} value={kit.id}>
                Kit {formatMonth(kit.reference_month)}
              </option>
            ))}
          </select>
        </div>

        {/* Priority */}
        <div>
          <label htmlFor="priority" className="block text-sm font-medium text-gray-700 mb-1">
            Prioridade
          </label>
          <select
            id="priority"
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none text-gray-900 bg-white"
          >
            {priorityOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        {/* Description */}
        <div>
          <label htmlFor="description" className="block text-sm font-medium text-gray-700 mb-1">
            Descricao *
          </label>
          <textarea
            id="description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Descreva com detalhes o motivo do seu chamado..."
            rows={5}
            required
            minLength={10}
            maxLength={5000}
            className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none resize-none text-gray-900 placeholder-gray-400"
          />
          <p className="text-xs text-gray-400 mt-1">{description.length}/5000 caracteres</p>
        </div>

        {/* Submit */}
        <div className="pt-2">
          <button
            type="submit"
            disabled={loading}
            className="flex items-center gap-2 bg-indigo-600 text-white px-6 py-2.5 rounded-lg font-medium hover:bg-indigo-700 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Enviando...
              </>
            ) : (
              <>
                <Send className="h-4 w-4" />
                Enviar Chamado
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
}
