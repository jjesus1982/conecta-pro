'use client';

import React, { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import {
  FolderOpen, Clock, MessageSquare, ArrowRight, Loader2, RefreshCw,
  AlertTriangle, CheckCircle2, Users, TrendingUp, Shield, Bell,
  FileText, ChevronRight, Activity, CalendarDays, AlertCircle,
  HelpCircle, Star, Zap,
} from 'lucide-react';
import { toast } from 'sonner';
import { usePortalAuth } from './hooks/usePortalAuth';

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
}

interface PortalTicket {
  id: string;
  subject: string;
  status: string;
  priority: string;
  created_at: string;
  updated_at: string;
}

interface AnalyticsOverview {
  health_score: number;
  kits_total: number;
  kits_approved: number;
  kits_pending: number;
  tickets_open: number;
  tickets_total: number;
  documents_total: number;
  documents_signed: number;
  last_kit_date: string | null;
}

const statusLabels: Record<string, string> = {
  em_montagem: 'Em Montagem',
  completo: 'Completo',
  enviado: 'Enviado',
  conferido: 'Conferido',
  aprovado: 'Aprovado',
};

const statusColors: Record<string, string> = {
  em_montagem: 'bg-yellow-100 text-yellow-800 border-yellow-200',
  completo: 'bg-blue-100 text-blue-800 border-blue-200',
  enviado: 'bg-indigo-100 text-indigo-800 border-indigo-200',
  conferido: 'bg-purple-100 text-purple-800 border-purple-200',
  aprovado: 'bg-emerald-100 text-emerald-800 border-emerald-200',
};

const ticketStatusColors: Record<string, string> = {
  ABERTO: 'bg-blue-100 text-blue-700',
  EM_ANDAMENTO: 'bg-yellow-100 text-yellow-700',
  RESPONDIDO: 'bg-green-100 text-green-700',
  FECHADO: 'bg-gray-100 text-gray-500',
};

const ticketPriorityColors: Record<string, string> = {
  BAIXA: 'text-gray-400',
  NORMAL: 'text-blue-500',
  ALTA: 'text-orange-500',
  URGENTE: 'text-red-500',
};

function formatMonth(dateStr: string): string {
  if (!dateStr) return '-';
  try {
    const d = new Date(dateStr + (dateStr.length <= 10 ? 'T00:00:00' : ''));
    return d.toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' });
  } catch {
    return dateStr;
  }
}

function formatDate(dateStr: string): string {
  if (!dateStr) return '-';
  try {
    return new Date(dateStr).toLocaleDateString('pt-BR', {
      day: '2-digit', month: '2-digit', year: 'numeric',
    });
  } catch { return dateStr; }
}

function timeAgo(dateStr: string): string {
  try {
    const diff = Date.now() - new Date(dateStr).getTime();
    const d = Math.floor(diff / 86400000);
    const h = Math.floor(diff / 3600000);
    const m = Math.floor(diff / 60000);
    if (d > 0) return `há ${d} dia${d > 1 ? 's' : ''}`;
    if (h > 0) return `há ${h}h`;
    return `há ${m}min`;
  } catch { return ''; }
}

function HealthGauge({ score }: { score: number }) {
  const color = score >= 80 ? '#10b981' : score >= 60 ? '#f59e0b' : '#ef4444';
  const label = score >= 80 ? 'Excelente' : score >= 60 ? 'Bom' : 'Atenção';
  return (
    <div className="flex flex-col items-center">
      <div className="relative w-24 h-24">
        <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
          <circle cx="50" cy="50" r="38" fill="none" stroke="#e5e7eb" strokeWidth="10" strokeDasharray="120 239" strokeDashoffset="0" />
          <circle cx="50" cy="50" r="38" fill="none" stroke={color} strokeWidth="10"
            strokeDasharray={`${(score / 100) * 120} 239`} strokeLinecap="round" />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">{score}</span>
        </div>
      </div>
      <span className="text-xs font-medium mt-1" style={{ color }}>{label}</span>
    </div>
  );
}

export default function DashboardPage() {
  const { clientName } = usePortalAuth();
  const [kits, setKits] = useState<PortalKit[]>([]);
  const [tickets, setTickets] = useState<PortalTicket[]>([]);
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
  const [opResumo, setOpResumo] = useState<{ equipe_total: number; assiduidade_local_pct: number; condominio: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [kitsRes, ticketsRes, overviewRes, opRes] = await Promise.all([
        fetch(`${API_BASE}/kits?limit=6`, { headers: getPortalHeaders() }),
        fetch(`${API_BASE}/tickets?limit=5`, { headers: getPortalHeaders() }),
        fetch(`${API_BASE}/analytics/overview`, { headers: getPortalHeaders() }),
        fetch(`${API_BASE}/operacao/resumo`, { headers: getPortalHeaders() }),
      ]);
      if (opRes.ok) setOpResumo(await opRes.json());

      if (kitsRes.status === 401) {
        toast.error('Sessão expirada. Faça login novamente.', { duration: 5000 });
        return;
      }

      if (kitsRes.ok) {
        const kData = await kitsRes.json();
        setKits(Array.isArray(kData) ? kData : kData.items || []);
      }
      if (ticketsRes.ok) {
        const tData = await ticketsRes.json();
        setTickets(Array.isArray(tData) ? tData : tData.items || []);
      }
      if (overviewRes.ok) {
        setOverview(await overviewRes.json());
      }
    } catch {
      setError('Erro ao carregar dados do painel.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const openTickets = tickets.filter((t) => t.status !== 'FECHADO');
  const urgentTickets = tickets.filter((t) => t.priority === 'URGENTE' && t.status !== 'FECHADO');
  const pendingKits = kits.filter((k) => ['enviado', 'conferido'].includes(k.status));
  const latestKit = kits[0];

  if (loading) {
    return (
      <div className="flex items-center justify-center py-32">
        <div className="text-center space-y-3">
          <Loader2 className="h-10 w-10 animate-spin text-indigo-600 mx-auto" />
          <p className="text-sm text-gray-500">Carregando seu painel...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 pb-28">

      {/* ── Header ─────────────────────────────────── */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold text-[hsl(var(--foreground))]">
            Olá, {clientName?.split(' ')[0] || 'Bem-vindo'}! 👋
          </h1>
          <p className="text-gray-500 mt-0.5 text-sm">
            {new Date().toLocaleDateString('pt-BR', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
          </p>
        </div>
        <button
          onClick={fetchData}
          className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-indigo-600 transition-colors mt-1"
        >
          <RefreshCw className="h-3.5 w-3.5" /> Atualizar
        </button>
      </div>

      {/* ── Alertas urgentes ───────────────────────── */}
      {urgentTickets.length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-red-500 flex-shrink-0" />
          <div className="flex-1">
            <p className="text-sm font-semibold text-red-800">
              {urgentTickets.length} chamado{urgentTickets.length > 1 ? 's' : ''} urgente{urgentTickets.length > 1 ? 's' : ''} em aberto
            </p>
            <p className="text-xs text-red-600">{urgentTickets[0]?.subject}</p>
          </div>
          <Link href="/area-cliente/chamados" className="text-xs font-medium text-red-700 underline">
            Ver
          </Link>
        </div>
      )}

      {error && (
        <div className="flex items-center gap-3 p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700">
          <AlertTriangle className="h-5 w-5 flex-shrink-0" />
          <span>{error}</span>
          <button onClick={fetchData} className="ml-auto text-red-600 hover:text-red-800 font-medium underline">
            Tentar novamente
          </button>
        </div>
      )}

      {/* ── Cards de métricas ──────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Health Score */}
        <div className="col-span-2 sm:col-span-1 bg-white rounded-xl border border-gray-200 shadow-sm p-5 flex items-center gap-4">
          <HealthGauge score={overview?.health_score ?? 0} />
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wide font-medium">Saúde Documental</p>
            <p className="text-xs text-gray-400 mt-1">
              {overview?.documents_signed ?? 0}/{overview?.documents_total ?? 0} docs assinados
            </p>
          </div>
        </div>

        {/* Kits */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
          <div className="flex items-center justify-between mb-3">
            <div className="p-2 bg-indigo-50 rounded-lg">
              <FolderOpen className="h-5 w-5 text-indigo-600" />
            </div>
            <span className="text-xs text-gray-400">total</span>
          </div>
          <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">{overview?.kits_total ?? kits.length}</p>
          <p className="text-xs text-gray-500 mt-0.5">Kits documentais</p>
          <p className="text-xs text-emerald-600 font-medium mt-1">
            {overview?.kits_approved ?? 0} aprovados
          </p>
        </div>

        {/* Chamados */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
          <div className="flex items-center justify-between mb-3">
            <div className="p-2 bg-blue-50 rounded-lg">
              <MessageSquare className="h-5 w-5 text-blue-600" />
            </div>
            <span className="text-xs text-gray-400">abertos</span>
          </div>
          <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">{openTickets.length}</p>
          <p className="text-xs text-gray-500 mt-0.5">Chamados ativos</p>
          <p className="text-xs text-gray-400 font-medium mt-1">
            {overview?.tickets_total ?? tickets.length} no total
          </p>
        </div>

        {/* Pendente aprovação */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
          <div className="flex items-center justify-between mb-3">
            <div className={`p-2 rounded-lg ${pendingKits.length > 0 ? 'bg-amber-50' : 'bg-gray-50'}`}>
              <Clock className={`h-5 w-5 ${pendingKits.length > 0 ? 'text-amber-600' : 'text-gray-400'}`} />
            </div>
            <span className="text-xs text-gray-400">pendente</span>
          </div>
          <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">{pendingKits.length}</p>
          <p className="text-xs text-gray-500 mt-0.5">Aguardando sua aprovação</p>
          {pendingKits.length > 0 && (
            <Link href="/area-cliente/kits" className="text-xs text-amber-600 font-medium mt-1 block hover:underline">
              Aprovar agora →
            </Link>
          )}
        </div>
      </div>

      {/* ── Linha 2: Kits + Kit ativo ─────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

        {/* Lista de kits recentes */}
        <div className="lg:col-span-2 bg-white rounded-xl border border-gray-200 shadow-sm">
          <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <FolderOpen className="h-4 w-4 text-indigo-600" />
              <h2 className="font-semibold text-gray-900">Kits Documentais</h2>
            </div>
            <Link href="/area-cliente/kits" className="text-xs text-indigo-600 hover:text-indigo-800 font-medium flex items-center gap-1">
              Ver todos <ChevronRight className="h-3 w-3" />
            </Link>
          </div>
          <div className="divide-y divide-gray-50">
            {kits.length === 0 ? (
              <div className="px-6 py-10 text-center text-gray-400 text-sm">
                Nenhum kit disponível no momento.
              </div>
            ) : (
              kits.slice(0, 5).map((kit) => {
                const pct = Number(kit.completion_percentage) || 0;
                return (
                  <Link
                    key={kit.id}
                    href={`/area-cliente/kits/${kit.id}`}
                    className="px-6 py-3.5 flex items-center gap-4 hover:bg-gray-50 transition-colors group"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-sm font-medium text-gray-900 capitalize">
                          {formatMonth(kit.reference_month)}
                        </span>
                        <span className={`text-xs font-medium px-2 py-0.5 rounded-full border ${statusColors[kit.status] || 'bg-gray-100 text-gray-600 border-gray-200'}`}>
                          {statusLabels[kit.status] || kit.status}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="flex-1 bg-gray-100 rounded-full h-1.5">
                          <div
                            className={`h-1.5 rounded-full transition-all ${pct === 100 ? 'bg-emerald-500' : pct > 50 ? 'bg-indigo-500' : 'bg-amber-400'}`}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                        <span className="text-xs text-gray-400 w-8 text-right">{pct}%</span>
                      </div>
                    </div>
                    <div className="text-right text-xs text-gray-400 hidden sm:block">
                      <div>{kit.total_documents} docs</div>
                      <div>{kit.total_employees} func.</div>
                    </div>
                    <ChevronRight className="h-4 w-4 text-gray-300 group-hover:text-indigo-500 transition-colors flex-shrink-0" />
                  </Link>
                );
              })
            )}
          </div>
        </div>

        {/* Status do kit mais recente */}
        <div className="flex flex-col gap-4">
          {/* Kit atual */}
          {latestKit && (
            <div className="bg-gradient-to-br from-indigo-600 to-blue-700 rounded-xl p-5 text-white">
              <div className="flex items-center gap-2 mb-4">
                <CalendarDays className="h-4 w-4 opacity-80" />
                <span className="text-xs opacity-80 font-medium uppercase tracking-wide">Kit Atual</span>
              </div>
              <p className="font-bold text-lg capitalize mb-1">{formatMonth(latestKit.reference_month)}</p>
              <span className="inline-block text-xs font-semibold bg-white/20 px-2 py-0.5 rounded-full mb-4">
                {statusLabels[latestKit.status] || latestKit.status}
              </span>
              <div className="mb-2">
                <div className="flex justify-between text-xs opacity-80 mb-1">
                  <span>Conclusão</span>
                  <span>{Number(latestKit.completion_percentage) || 0}%</span>
                </div>
                <div className="w-full bg-white/20 rounded-full h-2">
                  <div
                    className="bg-white h-2 rounded-full transition-all"
                    style={{ width: `${Number(latestKit.completion_percentage) || 0}%` }}
                  />
                </div>
              </div>
              <div className="flex justify-between text-xs opacity-70 mt-3">
                <span>{latestKit.total_documents} documentos</span>
                <span>{latestKit.total_employees} funcionários</span>
              </div>
              <Link
                href={`/area-cliente/kits/${latestKit.id}`}
                className="mt-4 block w-full text-center bg-white/20 hover:bg-white/30 transition-colors rounded-lg py-2 text-sm font-medium"
              >
                Ver detalhes
              </Link>
            </div>
          )}

          {/* Ações rápidas */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Ações rápidas</p>
            <div className="space-y-2">
              <Link
                href="/area-cliente/chamados/novo"
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-indigo-50 transition-colors group"
              >
                <div className="p-1.5 bg-indigo-100 rounded-lg group-hover:bg-indigo-200 transition-colors">
                  <MessageSquare className="h-3.5 w-3.5 text-indigo-600" />
                </div>
                <span className="text-sm text-gray-700 group-hover:text-indigo-700">Abrir Chamado</span>
                <ChevronRight className="h-4 w-4 text-gray-300 ml-auto group-hover:text-indigo-500" />
              </Link>
              <Link
                href="/area-cliente/kits"
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-indigo-50 transition-colors group"
              >
                <div className="p-1.5 bg-blue-100 rounded-lg group-hover:bg-blue-200 transition-colors">
                  <FolderOpen className="h-3.5 w-3.5 text-blue-600" />
                </div>
                <span className="text-sm text-gray-700 group-hover:text-indigo-700">Meus Kits</span>
                <ChevronRight className="h-4 w-4 text-gray-300 ml-auto group-hover:text-indigo-500" />
              </Link>
              <Link
                href="/area-cliente/analytics"
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-indigo-50 transition-colors group"
              >
                <div className="p-1.5 bg-emerald-100 rounded-lg group-hover:bg-emerald-200 transition-colors">
                  <TrendingUp className="h-3.5 w-3.5 text-emerald-600" />
                </div>
                <span className="text-sm text-gray-700 group-hover:text-indigo-700">Relatórios</span>
                <ChevronRight className="h-4 w-4 text-gray-300 ml-auto group-hover:text-indigo-500" />
              </Link>
            </div>
          </div>
        </div>
      </div>

      {/* ── Chamados recentes ─────────────────────── */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
        <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <MessageSquare className="h-4 w-4 text-blue-600" />
            <h2 className="font-semibold text-gray-900">Chamados Recentes</h2>
            {openTickets.length > 0 && (
              <span className="bg-blue-100 text-blue-700 text-xs font-semibold px-2 py-0.5 rounded-full">
                {openTickets.length} abertos
              </span>
            )}
          </div>
          <Link href="/area-cliente/chamados" className="text-xs text-indigo-600 hover:text-indigo-800 font-medium flex items-center gap-1">
            Ver todos <ChevronRight className="h-3 w-3" />
          </Link>
        </div>
        {tickets.length === 0 ? (
          <div className="px-6 py-8 text-center">
            <MessageSquare className="h-8 w-8 text-gray-200 mx-auto mb-2" />
            <p className="text-sm text-gray-400">Nenhum chamado ainda.</p>
            <Link href="/area-cliente/chamados/novo" className="text-xs text-indigo-600 hover:underline mt-1 inline-block">
              Abrir primeiro chamado →
            </Link>
          </div>
        ) : (
          <div className="divide-y divide-gray-50">
            {tickets.map((ticket) => (
              <Link
                key={ticket.id}
                href={`/area-cliente/chamados/${ticket.id}`}
                className="px-6 py-3.5 flex items-center gap-3 hover:bg-gray-50 transition-colors group"
              >
                <div className={`w-2 h-2 rounded-full flex-shrink-0 ${
                  ticket.priority === 'URGENTE' ? 'bg-red-500' :
                  ticket.priority === 'ALTA' ? 'bg-orange-400' : 'bg-gray-300'
                }`} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900 truncate">{ticket.subject}</p>
                  <p className="text-xs text-gray-400">{timeAgo(ticket.updated_at)}</p>
                </div>
                <span className={`text-xs font-medium px-2.5 py-0.5 rounded-full flex-shrink-0 ${ticketStatusColors[ticket.status] || 'bg-gray-100 text-gray-600'}`}>
                  {ticket.status === 'ABERTO' ? 'Aberto' : ticket.status === 'EM_ANDAMENTO' ? 'Em andamento' : ticket.status === 'RESPONDIDO' ? 'Respondido' : 'Fechado'}
                </span>
                <ChevronRight className="h-4 w-4 text-gray-300 group-hover:text-indigo-500 transition-colors" />
              </Link>
            ))}
          </div>
        )}
      </div>

      {/* ── Linha 3: Status do serviço ─────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
          <div className="flex items-center gap-3 mb-3">
            <div className="p-2 bg-emerald-50 rounded-lg">
              <Shield className="h-4 w-4 text-emerald-600" />
            </div>
            <span className="text-sm font-semibold text-gray-700">Status do Serviço</span>
          </div>
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${(opResumo?.equipe_total ?? 0) > 0 ? 'bg-emerald-500 animate-pulse' : 'bg-gray-300'}`} />
            <span className="text-xs text-gray-600 font-medium">{(opResumo?.equipe_total ?? 0) > 0 ? 'Operacional' : 'Sem equipe alocada'}</span>
          </div>
          <p className="text-xs text-gray-400 mt-1">{opResumo?.condominio ? `Equipe ativa no ${opResumo.condominio}` : 'Equipe da Conecta Mais'}</p>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
          <div className="flex items-center gap-3 mb-3">
            <div className="p-2 bg-blue-50 rounded-lg">
              <Users className="h-4 w-4 text-blue-600" />
            </div>
            <span className="text-sm font-semibold text-gray-700">Equipe Alocada</span>
          </div>
          <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">{opResumo?.equipe_total ?? '—'}</p>
          <p className="text-xs text-gray-400 mt-0.5">funcionários em serviço</p>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
          <div className="flex items-center gap-3 mb-3">
            <div className="p-2 bg-emerald-50 rounded-lg">
              <Activity className="h-4 w-4 text-emerald-600" />
            </div>
            <span className="text-sm font-semibold text-gray-700">Presença no local</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex-1 bg-gray-100 rounded-full h-2">
              <div className="bg-emerald-500 h-2 rounded-full" style={{ width: `${opResumo?.assiduidade_local_pct ?? 0}%` }} />
            </div>
            <span className="text-xs font-semibold text-emerald-600">{opResumo?.assiduidade_local_pct ?? 0}%</span>
          </div>
          <p className="text-xs text-gray-400 mt-1">Ponto batido dentro do condomínio</p>
        </div>
      </div>

      {/* ── Precisa de ajuda? ─────────────────────── */}
      <div className="bg-gradient-to-r from-indigo-600 via-indigo-700 to-blue-700 rounded-xl p-6 text-white">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="bg-white/20 p-3 rounded-xl">
              <HelpCircle className="h-6 w-6" />
            </div>
            <div>
              <h3 className="font-bold text-lg">Precisa de suporte?</h3>
              <p className="text-indigo-100 text-sm">
                Nossa equipe responde em até 2 horas em dias úteis.
              </p>
            </div>
          </div>
          <div className="flex gap-3">
            <Link
              href="/area-cliente/chamados/novo"
              className="bg-white text-indigo-700 px-5 py-2.5 rounded-lg font-semibold hover:bg-indigo-50 transition-colors text-sm whitespace-nowrap"
            >
              Abrir Chamado
            </Link>
            <Link
              href="/area-cliente/analytics"
              className="bg-white/20 hover:bg-white/30 text-white px-5 py-2.5 rounded-lg font-medium transition-colors text-sm whitespace-nowrap"
            >
              Ver Relatórios
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
