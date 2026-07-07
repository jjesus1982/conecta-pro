'use client';

import React, { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import KitsDoCliente from '@/components/gdrive/KitsDoCliente';
import {
  FolderOpen, Loader2, FileText, AlertTriangle, CheckCircle2,
  Clock, Send, Eye, Download, Users, ChevronRight, FolderArchive,
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

interface PortalKit {
  id: string;
  reference_month: string;
  status: string;
  completion_percentage: number;
  total_documents: number;
  total_employees: number;
  google_drive_link: string | null;
}

interface PaginatedResponse {
  items: PortalKit[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

const statusLabels: Record<string, string> = {
  em_montagem: 'Em Montagem',
  completo: 'Completo',
  enviado: 'Enviado',
  conferido: 'Conferido',
  aprovado: 'Aprovado',
};

const statusColors: Record<string, string> = {
  em_montagem: 'bg-amber-500/10 text-amber-500 border-amber-500/30',
  completo: 'bg-blue-500/10 text-blue-500 border-blue-500/30',
  enviado: 'bg-emerald-500/10 text-emerald-500 border-emerald-500/30',
  conferido: 'bg-purple-500/10 text-purple-500 border-purple-500/30',
  aprovado: 'bg-emerald-500/10 text-emerald-500 border-emerald-500/30',
};

const cardBorderColors: Record<string, string> = {
  em_montagem: 'border-l-amber-500',
  completo: 'border-l-blue-500',
  enviado: 'border-l-emerald-500',
  conferido: 'border-l-purple-500',
  aprovado: 'border-l-emerald-500',
};

const statusFilterOptions = [
  { key: '', label: 'Todos' },
  { key: 'em_montagem', label: 'Em Montagem' },
  { key: 'completo', label: 'Completo' },
  { key: 'enviado', label: 'Enviado' },
  { key: 'conferido', label: 'Conferido' },
  { key: 'aprovado', label: 'Aprovado' },
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

export default function KitsPage() {
  const [kits, setKits] = useState<PortalKit[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [total, setTotal] = useState(0);
  const pageSize = 12;

  const fetchKits = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams();
      params.set('skip', String((currentPage - 1) * pageSize));
      params.set('limit', String(pageSize));
      if (statusFilter) params.set('status', statusFilter);

      const res = await fetch(`${API_BASE}/kits?${params.toString()}`, {
        headers: getPortalHeaders(),
      });

      if (res.status === 401) {
        toast.error('Sessao expirada. Faca login novamente.', { duration: 5000 });
        return;
      }

      if (!res.ok) {
        throw new Error('Erro ao carregar kits.');
      }

      const data: PaginatedResponse = await res.json();
      setKits(data.items || []);
      setTotal(data.total || 0);
      setTotalPages(data.pages || 0);
    } catch {
      setError('Erro ao carregar kits documentais.');
      toast.error('Erro ao carregar kits. Verifique sua conexao.', { duration: 5000 });
    } finally {
      setLoading(false);
    }
  }, [currentPage, statusFilter]);

  useEffect(() => {
    fetchKits();
  }, [fetchKits]);

  function handleFilterChange(newStatus: string) {
    setStatusFilter(newStatus);
    setCurrentPage(1);
  }

  return (
    <div className="space-y-6 pb-28">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold text-[hsl(var(--foreground))]">Meus Kits</h1>
          <p className="text-[hsl(var(--muted-foreground))] text-sm mt-1">
            Kits documentais organizados por mes de referencia.
            {total > 0 && <span className="ml-1 font-medium">({total} kits)</span>}
          </p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2">
        {statusFilterOptions.map((opt) => (
          <button
            key={opt.key}
            onClick={() => handleFilterChange(opt.key)}
            className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ${
              statusFilter === opt.key
                ? 'bg-indigo-600 text-white'
                : 'bg-[hsl(var(--secondary))] text-[hsl(var(--muted-foreground))] hover:bg-[hsl(var(--muted))]'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-center gap-3 p-4 bg-red-500/10 border border-red-500/30 rounded-xl text-sm text-red-500">
          <AlertTriangle className="h-5 w-5 flex-shrink-0" />
          <span>{error}</span>
          <button onClick={fetchKits} className="ml-auto text-red-500 hover:text-red-400 font-medium underline">
            Tentar novamente
          </button>
        </div>
      )}

      {/* Summary stats */}
      {!loading && kits.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[
            { label: 'Total', value: total, color: 'text-[hsl(var(--foreground))]', bg: 'bg-[hsl(var(--secondary))]', icon: FolderOpen },
            { label: 'Aprovados', value: kits.filter(k => k.status === 'aprovado').length, color: 'text-emerald-500', bg: 'bg-emerald-500/10', icon: CheckCircle2 },
            { label: 'Pendentes', value: kits.filter(k => ['enviado','conferido'].includes(k.status)).length, color: 'text-amber-500', bg: 'bg-amber-500/10', icon: Clock },
            { label: 'Em montagem', value: kits.filter(k => k.status === 'em_montagem').length, color: 'text-blue-500', bg: 'bg-blue-500/10', icon: Send },
          ].map(({ label, value, color, bg, icon: Icon }) => (
            <div key={label} className={`${bg} rounded-xl p-4 flex items-center gap-3`}>
              <Icon className={`h-5 w-5 ${color}`} />
              <div>
                <p className={`font-data text-xl font-semibold tabular-nums ${color}`}>{value}</p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">{label}</p>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Content */}
      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
        </div>
      ) : kits.length === 0 ? (
        <div className="bg-[hsl(var(--card))] rounded-xl shadow-sm border border-[hsl(var(--border))] p-12 text-center">
          <FolderOpen className="h-12 w-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
          <p className="text-[hsl(var(--muted-foreground))] font-medium">Nenhum kit encontrado.</p>
          <p className="text-[hsl(var(--muted-foreground))] text-sm mt-1">
            {statusFilter ? 'Tente selecionar outro filtro.' : 'Seus kits aparecerao aqui quando disponiveis.'}
          </p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {kits.map((kit) => {
              const pct = Number(kit.completion_percentage) || 0;
              const canApprove = ['enviado', 'conferido'].includes(kit.status);
              return (
              <Link
                key={kit.id}
                href={`/area-cliente/kits/${kit.id}`}
                className={`bg-[hsl(var(--card))] rounded-xl shadow-sm border border-[hsl(var(--border))] border-l-4 ${
                  cardBorderColors[kit.status] || 'border-l-[hsl(var(--border))]'
                } p-5 hover:shadow-md transition-all group relative`}
              >
                {canApprove && (
                  <span className="absolute top-3 right-3 flex h-2.5 w-2.5">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-amber-500"></span>
                  </span>
                )}
                <div className="flex items-start justify-between mb-3 pr-4">
                  <div>
                    <p className="text-base font-semibold text-[hsl(var(--foreground))] group-hover:text-indigo-500 transition-colors capitalize">
                      {formatMonth(kit.reference_month)}
                    </p>
                    <p className="text-xs text-[hsl(var(--muted-foreground))] mt-0.5">Mês de referência</p>
                  </div>
                  <span className={`text-xs font-medium px-2.5 py-1 rounded-full border ${statusColors[kit.status] || 'bg-[hsl(var(--secondary))] text-[hsl(var(--muted-foreground))] border-[hsl(var(--border))]'}`}>
                    {statusLabels[kit.status] || kit.status}
                  </span>
                </div>

                {/* Progress bar */}
                <div className="mb-4">
                  <div className="flex justify-between text-xs text-[hsl(var(--muted-foreground))] mb-1">
                    <span>Conclusão</span>
                    <span className="font-data font-semibold tabular-nums">{pct}%</span>
                  </div>
                  <div className="w-full bg-[hsl(var(--secondary))] rounded-full h-2">
                    <div
                      className={`h-2 rounded-full transition-all ${pct === 100 ? 'bg-emerald-500' : pct > 60 ? 'bg-indigo-500' : 'bg-amber-400'}`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>

                <div className="flex items-center justify-between text-xs text-[hsl(var(--muted-foreground))]">
                  <div className="flex items-center gap-3">
                    <span className="flex items-center gap-1">
                      <FileText className="h-3.5 w-3.5" />{kit.total_documents ?? 0} docs
                    </span>
                    <span className="flex items-center gap-1">
                      <Users className="h-3.5 w-3.5" />{kit.total_employees ?? 0} func.
                    </span>
                  </div>
                  <span className="flex items-center gap-1 text-indigo-500 font-medium group-hover:gap-1.5 transition-all">
                    {canApprove ? 'Aprovar' : 'Ver'} <ChevronRight className="h-3.5 w-3.5" />
                  </span>
                </div>
                {kit.google_drive_link && (
                  <a
                    href={kit.google_drive_link}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    className="mt-3 flex items-center justify-center gap-2
                               w-full bg-orange-500 hover:bg-orange-600
                               text-white text-xs font-medium
                               py-1.5 rounded-lg transition-colors"
                  >
                    <Download className="h-3.5 w-3.5" />
                    Acessar no Drive
                  </a>
                )}
              </Link>
            )})}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 mt-6">
              <button
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={currentPage <= 1}
                className="px-3 py-1.5 text-sm font-medium border border-[hsl(var(--border))] rounded-lg hover:bg-[hsl(var(--secondary))] disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Anterior
              </button>
              <span className="text-sm text-[hsl(var(--muted-foreground))]">
                Pagina {currentPage} de {totalPages}
              </span>
              <button
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage >= totalPages}
                className="px-3 py-1.5 text-sm font-medium border border-[hsl(var(--border))] rounded-lg hover:bg-[hsl(var(--secondary))] disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Proxima
              </button>
            </div>
          )}
        </>
      )}
      {/* Histórico de kits no Google Drive */}
      <div className="mt-8 border-t border-[hsl(var(--border))] pt-8">
        <h2 className="text-lg font-semibold text-[hsl(var(--foreground))] mb-4 flex items-center gap-2">
          <FolderArchive className="h-5 w-5" /> Histórico no Google Drive
        </h2>
        <KitsDoCliente clienteId="" />
      </div>
    </div>
  );
}
