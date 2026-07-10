'use client';

import {
  Brain, Activity, Shield, TrendingUp,
  CheckCircle, Users, MapPin, Clock, Target, Zap, RefreshCw,
  BarChart2, ArrowLeft, ChevronRight, Wifi, WifiOff, Bell,
} from 'lucide-react';
import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/hooks/useAuth';
import { useOperacionalWebSocket, type OperacionalEvent } from '@/hooks/operacional/useOperacionalWebSocket';
import api from '@/lib/api';

interface TopPerformer {
  employee_name: string;
  score: number;
  rank: number;
  highlights: string[];
  eligible_for_promotion: boolean;
}

// Chaves REAIS de GET /operacional/ai/command-center (provado por curl):
// overview.{agentes_ativos,agentes_presentes,agentes_ausentes,total_postos,cobertura_atual}
// coverage_prediction.{total_postos,postos_cobertos,cobertura_atual,nivel_risco}
// weekly_risk_map: ARRAY de {dia,nivel_risco,cobertura}
// agents_status: contagens {total,presentes,ausentes} — NÃO é mapa agente→status
interface CommandCenterData {
  overview?: {
    agentes_ativos?: number;
    agentes_presentes?: number;
    agentes_ausentes?: number;
    total_postos?: number;
    cobertura_atual?: number;
  } | null;
  coverage_prediction?: {
    total_postos?: number;
    postos_cobertos?: number;
    cobertura_atual?: number;
    nivel_risco?: string;
  } | null;
  weekly_risk_map?: Array<{
    dia?: string;
    nivel_risco?: string;
    cobertura?: number;
  }> | null;
  agents_status?: {
    total?: number;
    presentes?: number;
    ausentes?: number;
  } | null;
}

interface PerformanceData {
  team_average_score?: number;
  total_analyzed?: number;
  top_performers?: TopPerformer[];
  score_distribution?: Record<string, number>;
}

const RISK_COLORS: Record<string, string> = {
  baixo: 'text-green-400 bg-green-900/30',
  confiavel: 'text-green-400 bg-green-900/30',
  medio: 'text-yellow-400 bg-yellow-900/30',
  atencao: 'text-yellow-400 bg-yellow-900/30',
  alto: 'text-orange-400 bg-orange-900/30',
  alto_risco: 'text-orange-400 bg-orange-900/30',
  critico: 'text-red-400 bg-red-900/30',
};

const RISK_LABELS: Record<string, string> = {
  baixo: 'Baixo',
  confiavel: 'Confiável',
  medio: 'Médio',
  atencao: 'Atenção',
  alto: 'Alto Risco',
  alto_risco: 'Alto Risco',
  critico: 'Crítico',
};

const RISK_DOT: Record<string, string> = {
  baixo: 'bg-green-400',
  medio: 'bg-yellow-400',
  alto: 'bg-orange-400',
  critico: 'bg-red-400',
};

export default function AICommandCenterOperacionalPage() {
  const router = useRouter();
  const { isLoading: authLoading, isAuthenticated } = useAuth();
  const [commandData, setCommandData] = useState<CommandCenterData | null>(null);
  const [performanceData, setPerformanceData] = useState<PerformanceData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [authLoading, isAuthenticated, router]);

  const loadData = useCallback(async () => {
    try {
      setIsLoading(true);
      const [cmdRes, perfRes] = await Promise.allSettled([
        api.get('/api/v1/operacional/ai/command-center'),
        api.get('/api/v1/operacional/ai/performance-overview'),
      ]);

      if (cmdRes.status === 'fulfilled') {
        setCommandData((cmdRes.value as any).data);
      }
      if (perfRes.status === 'fulfilled') {
        setPerformanceData((perfRes.value as any).data);
      }
      setLastUpdated(new Date());
    } catch (err) {
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isAuthenticated) {
      loadData();
    }
  }, [isAuthenticated, loadData]);

  const overview = commandData?.overview;
  const coveragePrediction = commandData?.coverage_prediction;
  const weeklyRiskMap = Array.isArray(commandData?.weekly_risk_map)
    ? commandData!.weekly_risk_map!
    : [];
  // Cobertura real vem de overview.cobertura_atual (fallback coverage_prediction)
  const coverageScore = overview?.cobertura_atual ?? coveragePrediction?.cobertura_atual ?? 0;
  const teamScore = performanceData?.team_average_score;

  // WebSocket em tempo real
  const { isConnected: wsConnected, events: wsEvents, clearEvents } = useOperacionalWebSocket({
    room: 'operacional',
    autoConnect: true,
  });

  return (
    <div className="min-h-screen bg-[#0a0f1e] text-white">
      {/* Header */}
      <div className="bg-gradient-to-r from-[#111b57] to-[#1a47f5]/20 border-b border-white/10 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link href="/modulos/operacional">
              <Button variant="ghost" size="sm" className="text-white/70 hover:text-white">
                <ArrowLeft className="w-4 h-4 mr-2" />
                Operacional
              </Button>
            </Link>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-purple-500 to-blue-600 flex items-center justify-center">
                <Brain className="w-5 h-5 text-white" />
              </div>
              <div>
                <h1 className="font-display text-xl font-bold">AI Command Center</h1>
                <p className="text-sm text-white/60">Inteligência Operacional em Tempo Real</p>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {/* Indicador WebSocket */}
            <div className="flex items-center gap-1.5">
              {wsConnected ? (
                <>
                  <Wifi className="w-3.5 h-3.5 text-green-400" />
                  <span className="text-xs text-green-400">Tempo real</span>
                </>
              ) : (
                <>
                  <WifiOff className="w-3.5 h-3.5 text-white/30" />
                  <span className="text-xs text-white/30">Offline</span>
                </>
              )}
            </div>
            {lastUpdated && (
              <span className="text-xs text-white/40">
                Atualizado: {lastUpdated.toLocaleTimeString('pt-BR')}
              </span>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={loadData}
              disabled={isLoading}
              className="border-white/20 text-white/70 hover:text-white"
            >
              <RefreshCw className={`w-4 h-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
              Atualizar
            </Button>
          </div>
        </div>
      </div>

      <div className="p-6 space-y-6">
        {/* KPI Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-white/5 border border-white/10 rounded-xl p-4">
            <div className="flex items-center gap-2 mb-2">
              <MapPin className="w-4 h-4 text-cyan-400" />
              <span className="text-xs text-white/60">Postos</span>
            </div>
            <div className="font-data text-2xl font-semibold tabular-nums text-white">
              {isLoading ? '—' : overview?.total_postos ?? coveragePrediction?.total_postos ?? '—'}
            </div>
            <div className="text-xs text-green-400 mt-1">
              {coveragePrediction?.postos_cobertos != null
                ? `${coveragePrediction.postos_cobertos} cobertos`
                : 'Operacionais'}
            </div>
          </div>

          <div className="bg-white/5 border border-white/10 rounded-xl p-4">
            <div className="flex items-center gap-2 mb-2">
              <Shield className="w-4 h-4 text-blue-400" />
              <span className="text-xs text-white/60">Cobertura Atual</span>
            </div>
            <div className={`font-data text-2xl font-semibold tabular-nums ${coverageScore >= 90 ? 'text-green-400' : coverageScore >= 75 ? 'text-yellow-400' : 'text-red-400'}`}>
              {isLoading ? '—' : `${coverageScore}%`}
            </div>
            <div className="text-xs text-white/40 mt-1">
              {coveragePrediction?.nivel_risco
                ? `Risco ${RISK_LABELS[coveragePrediction.nivel_risco] ?? coveragePrediction.nivel_risco}`
                : 'Dos postos ativos'}
            </div>
          </div>

          <div className="bg-white/5 border border-white/10 rounded-xl p-4">
            <div className="flex items-center gap-2 mb-2">
              <Users className="w-4 h-4 text-orange-400" />
              <span className="text-xs text-white/60">Agentes Ativos</span>
            </div>
            <div className="font-data text-2xl font-semibold tabular-nums text-white">
              {isLoading ? '—' : overview?.agentes_ativos ?? '—'}
            </div>
            <div className="text-xs text-white/40 mt-1">
              {overview?.agentes_presentes != null
                ? `${overview.agentes_presentes} presentes · ${overview.agentes_ausentes ?? 0} ausentes`
                : 'Colaboradores em operação'}
            </div>
          </div>

          <div className="bg-white/5 border border-white/10 rounded-xl p-4">
            <div className="flex items-center gap-2 mb-2">
              <BarChart2 className="w-4 h-4 text-purple-400" />
              <span className="text-xs text-white/60">Score da Equipe</span>
            </div>
            <div className="font-data text-2xl font-semibold tabular-nums text-purple-400">
              {isLoading ? '—' : teamScore ?? '—'}
            </div>
            <div className="text-xs text-white/40 mt-1">
              {teamScore != null ? 'Performance média' : 'Sem dados no momento'}
            </div>
          </div>
        </div>

        {/* Main Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Previsão de Cobertura */}
          <div className="bg-white/5 border border-white/10 rounded-xl p-5">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <Target className="w-5 h-5 text-blue-400" />
                <h2 className="font-semibold">Previsão de Cobertura</h2>
              </div>
              <span className="text-xs text-white/40 bg-blue-900/30 px-2 py-1 rounded">
                Semana
              </span>
            </div>

            {isLoading ? (
              <div className="space-y-3">
                {[1, 2, 3].map(i => (
                  <div key={i} className="h-12 bg-white/5 rounded-lg animate-pulse" />
                ))}
              </div>
            ) : coveragePrediction ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between p-3 bg-white/5 rounded-lg">
                  <div>
                    <div className="text-sm font-medium">Postos cobertos</div>
                    <div className="text-xs text-white/50">Alocações vigentes nos postos ativos</div>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="text-right">
                      <div className="text-sm font-bold">
                        {coveragePrediction.postos_cobertos ?? '—'}/{coveragePrediction.total_postos ?? '—'}
                      </div>
                      <div className="text-xs text-white/40">
                        {coveragePrediction.cobertura_atual != null ? `${coveragePrediction.cobertura_atual}%` : 'cobertura'}
                      </div>
                    </div>
                    {coveragePrediction.nivel_risco && (
                      <span className={`text-xs px-2 py-1 rounded-full ${RISK_COLORS[coveragePrediction.nivel_risco] || 'text-gray-400 bg-gray-800'}`}>
                        {RISK_LABELS[coveragePrediction.nivel_risco] || coveragePrediction.nivel_risco}
                      </span>
                    )}
                  </div>
                </div>

                {/* Mapa de risco semanal (weekly_risk_map é ARRAY de dias) */}
                {weeklyRiskMap.length > 0 && (
                  <div className="grid grid-cols-7 gap-1.5">
                    {weeklyRiskMap.map((day, idx) => (
                      <div key={idx} className="flex flex-col items-center p-2 bg-white/5 rounded-lg text-center">
                        <span className="text-[10px] uppercase tracking-wider text-white/50">{day.dia ?? '—'}</span>
                        <span className={`my-1.5 w-2 h-2 rounded-full ${RISK_DOT[day.nivel_risco ?? ''] || 'bg-gray-500'}`} />
                        <span className="text-xs font-medium tabular-nums text-white/80">
                          {day.cobertura != null ? `${day.cobertura}%` : '—'}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div className="flex items-center justify-center h-32 text-white/40">
                <CheckCircle className="w-6 h-6 mr-2 text-green-400" />
                Sem dados de cobertura no momento
              </div>
            )}
          </div>

          {/* Top Performers */}
          <div className="bg-white/5 border border-white/10 rounded-xl p-5">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <TrendingUp className="w-5 h-5 text-green-400" />
                <h2 className="font-semibold">Top Performers</h2>
              </div>
              <span className="text-xs text-white/40 bg-green-900/30 px-2 py-1 rounded">
                Últimos 90 dias
              </span>
            </div>

            {isLoading ? (
              <div className="space-y-3">
                {[1, 2, 3].map(i => (
                  <div key={i} className="h-12 bg-white/5 rounded-lg animate-pulse" />
                ))}
              </div>
            ) : performanceData?.top_performers?.length ? (
              <div className="space-y-3">
                {performanceData.top_performers.map((performer) => (
                  <div key={performer.rank} className="flex items-center gap-3 p-3 bg-white/5 rounded-lg">
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold
                      ${performer.rank === 1 ? 'bg-yellow-500/20 text-yellow-400' :
                        performer.rank === 2 ? 'bg-gray-400/20 text-gray-300' :
                        performer.rank === 3 ? 'bg-orange-600/20 text-orange-400' :
                        'bg-white/10 text-white/60'}`}>
                      {performer.rank}
                    </div>
                    <div className="flex-1">
                      <div className="text-sm font-medium">{performer.employee_name}</div>
                      <div className="text-xs text-white/40">
                        {performer.highlights?.[0] || 'Excelente performance'}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-bold text-green-400">{performer.score}</div>
                      <div className="text-xs text-white/40">score</div>
                    </div>
                    {performer.eligible_for_promotion && (
                      <div className="text-xs bg-purple-900/40 text-purple-400 px-2 py-0.5 rounded">
                        Promoção
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex items-center justify-center h-32 text-white/40">
                <Users className="w-6 h-6 mr-2" />
                Nenhum dado disponível
              </div>
            )}

            {performanceData && (
              Object.keys(performanceData.score_distribution ?? {}).length > 0 ? (
                <div className="mt-4 grid grid-cols-5 gap-1">
                  {Object.entries(performanceData.score_distribution ?? {}).map(([key, val]) => (
                    <div key={key} className="text-center">
                      <div className={`text-lg font-bold ${
                        key === 'excelente' ? 'text-green-400' :
                        key === 'bom' ? 'text-blue-400' :
                        key === 'satisfatorio' ? 'text-yellow-400' :
                        key === 'atencao' ? 'text-orange-400' : 'text-red-400'
                      }`}>{val ?? 0}</div>
                      <div className="text-xs text-white/30 capitalize">{key.replace('_', ' ')}</div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="mt-4 text-xs text-white/40 text-center">
                  Distribuição de scores sem dados no momento
                </div>
              )
            )}
          </div>
        </div>

        {/* Agentes de IA */}
        <div className="bg-white/5 border border-white/10 rounded-xl p-5">
          <div className="flex items-center gap-2 mb-4">
            <Zap className="w-5 h-5 text-yellow-400" />
            <h2 className="font-semibold">Agentes de IA Ativos</h2>
          </div>
          {isLoading ? (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
              {[1, 2, 3, 4, 5, 6].map(i => (
                <div key={i} className="h-20 bg-white/5 rounded-lg animate-pulse" />
              ))}
            </div>
          ) : (
            // A API não expõe status por agente de IA (agents_status traz contagens
            // de COLABORADORES: total/presentes/ausentes) — seção honesta "sem dados"
            <div className="flex items-center justify-center h-20 text-white/40 text-sm">
              <Brain className="w-4 h-4 mr-2" />
              Telemetria por agente de IA indisponível no momento — aguardando dado
            </div>
          )}
        </div>

        {/* Presença da equipe (agents_status real: contagens) */}
        {commandData?.agents_status && commandData.agents_status.total != null && (
          <div className="bg-gradient-to-r from-purple-900/30 to-blue-900/30 border border-purple-500/20 rounded-xl p-5">
            <div className="flex items-center gap-2 mb-3">
              <Activity className="w-5 h-5 text-purple-400" />
              <h2 className="font-semibold">Presença da Equipe</h2>
            </div>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <div className="font-data text-xl font-semibold tabular-nums text-white">
                  {commandData.agents_status.total}
                </div>
                <div className="text-xs text-white/50">Agentes no efetivo</div>
              </div>
              <div>
                <div className="font-data text-xl font-semibold tabular-nums text-green-400">
                  {commandData.agents_status.presentes ?? 0}
                </div>
                <div className="text-xs text-white/50">Presentes agora</div>
              </div>
              <div>
                <div className="font-data text-xl font-semibold tabular-nums text-orange-400">
                  {commandData.agents_status.ausentes ?? 0}
                </div>
                <div className="text-xs text-white/50">Ausentes</div>
              </div>
            </div>
          </div>
        )}

        {/* Links rápidos */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { href: '/modulos/operacional/escalas', icon: Clock, label: 'Ver Escalas', color: 'blue' },
            { href: '/modulos/operacional/substituicoes', icon: RefreshCw, label: 'Substituições', color: 'green' },
            { href: '/modulos/operacional/colaboradores', icon: Users, label: 'Colaboradores', color: 'purple' },
            { href: '/modulos/operacional/kpi', icon: BarChart2, label: 'KPI & Métricas', color: 'orange' },
          ].map((link) => (
            <Link key={link.href} href={link.href}>
              <div className={`p-4 bg-white/5 border border-white/10 rounded-xl hover:bg-white/10 transition-all cursor-pointer flex items-center gap-3`}>
                <link.icon className={`w-5 h-5 text-${link.color}-400`} />
                <span className="text-sm font-medium">{link.label}</span>
                <ChevronRight className="w-4 h-4 text-white/30 ml-auto" />
              </div>
            </Link>
          ))}
        </div>

        {/* Notificações em Tempo Real (WebSocket) */}
        {wsEvents.length > 0 && (
          <div className="bg-white/5 border border-white/10 rounded-xl p-5">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Bell className="w-4 h-4 text-yellow-400" />
                <h2 className="font-semibold text-sm">Notificações em Tempo Real</h2>
                <span className="text-xs bg-yellow-500/20 text-yellow-400 px-2 py-0.5 rounded-full">
                  {wsEvents.length}
                </span>
              </div>
              <button
                onClick={clearEvents}
                className="text-xs text-white/40 hover:text-white/70 transition-colors"
              >
                Limpar
              </button>
            </div>
            <div className="space-y-2 max-h-40 overflow-y-auto">
              {wsEvents.slice(0, 10).map((ev: OperacionalEvent, idx: number) => (
                <div
                  key={idx}
                  className="flex items-start gap-2 text-xs p-2 bg-black/20 rounded-lg"
                >
                  <span className={`mt-0.5 w-2 h-2 rounded-full flex-shrink-0 ${
                    ev.type === 'coverage_alert' || ev.type === 'absence_alert'
                      ? 'bg-red-400'
                      : ev.type === 'anomaly_detected'
                      ? 'bg-orange-400'
                      : ev.type === 'shift_reminder'
                      ? 'bg-blue-400'
                      : 'bg-green-400'
                  }`} />
                  <div className="flex-1 min-w-0">
                    <span className="text-white/70 capitalize">
                      {(ev.type ?? 'evento').replace(/_/g, ' ')}
                    </span>
                    {ev.data?.message ? (
                      <span className="text-white/40 ml-1">— {String(ev.data.message)}</span>
                    ) : null}
                  </div>
                  <span className="text-white/20 flex-shrink-0">
                    {new Date(ev.timestamp).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
