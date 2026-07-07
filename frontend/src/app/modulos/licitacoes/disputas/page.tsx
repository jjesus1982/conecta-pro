'use client';

/**
 * Dashboard de Disputas - WARRIOR Agent
 * Robo de Lances para Pregoes Eletronicos
 * Conecta PRO - Modulo de Licitacoes
 */

import { useState, useMemo, useCallback } from 'react';
import {
  Swords,
  Target,
  TrendingDown,
  Trophy,
  Activity,
  Play,
  Pause,
  Send,
  Loader2,
  AlertCircle,
  Clock,
  Hash,
  DollarSign,
  BarChart3,
  ChevronLeft,
  RefreshCw,
  Zap,
  Users,
  ArrowDown,
  ArrowUp,
  Minus,
} from 'lucide-react';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useWarriorStatus } from '@/hooks/bidding/useAgents';
import { useDisputeWebSocket } from '@/hooks/useDisputeWebSocket';

// ===== TYPES =====

interface Lance {
  rodada: number;
  valor: number;
  posicao: number;
  status: 'aceito' | 'melhor' | 'superado' | 'recusado';
  timestamp: string;
}

interface Concorrente {
  nome: string;
  perfil: 'agressivo' | 'moderado' | 'conservador' | 'sniper';
  valor_final: number;
  desistiu: boolean;
}

interface DisputaAtiva {
  pregao: string;
  portal: string;
  orgao: string;
  objeto: string;
  status: 'em_disputa' | 'convocacao' | 'encerrada';
  posicao_atual: number;
  melhor_lance: number;
  meu_ultimo_lance: number;
  lances: Lance[];
  convocacoes: string[];
}

interface SimulacaoResultado {
  resultado: 'VENCEDOR' | 'SEGUNDO' | 'TERCEIRO' | 'ELIMINADO';
  valor_final: number;
  posicao: number;
  economia_percentual: number;
  lances: Array<{ rodada: number; nosso: number; melhor_concorrente: number }>;
  concorrentes: Concorrente[];
}

interface DisputaHistorico {
  id: string;
  pregao: string;
  portal: string;
  data: string;
  resultado: 'vencedor' | 'segundo' | 'terceiro' | 'eliminado' | 'desistiu';
  valor_final: number;
  economia_percentual: number;
}

// ===== MOCK DATA =====

const MOCK_DISPUTA_ATIVA: DisputaAtiva | null = null; // No active dispute by default

const MOCK_HISTORICO: DisputaHistorico[] = [
  {
    id: '1',
    pregao: 'PE 012/2026',
    portal: 'ComprasNet',
    data: '2026-03-10',
    resultado: 'vencedor',
    valor_final: 2340000,
    economia_percentual: 12.5,
  },
  {
    id: '2',
    pregao: 'PE 008/2026',
    portal: 'PNCP',
    data: '2026-03-05',
    resultado: 'segundo',
    valor_final: 1890000,
    economia_percentual: 8.2,
  },
  {
    id: '3',
    pregao: 'PE 003/2026',
    portal: 'ComprasNet',
    data: '2026-02-28',
    resultado: 'vencedor',
    valor_final: 3150000,
    economia_percentual: 15.1,
  },
  {
    id: '4',
    pregao: 'PE 045/2025',
    portal: 'Licitacoes-e',
    data: '2026-02-15',
    resultado: 'eliminado',
    valor_final: 0,
    economia_percentual: 0,
  },
  {
    id: '5',
    pregao: 'PE 041/2025',
    portal: 'ComprasNet',
    data: '2026-02-10',
    resultado: 'vencedor',
    valor_final: 1250000,
    economia_percentual: 10.8,
  },
  {
    id: '6',
    pregao: 'PE 039/2025',
    portal: 'PNCP',
    data: '2026-02-01',
    resultado: 'terceiro',
    valor_final: 980000,
    economia_percentual: 5.3,
  },
];

const MOCK_KPI = {
  disputas_ativas: 0,
  disputas_vencidas: 3,
  economia_media: 11.5,
  posicao_media: 1.8,
};

// ===== HELPERS =====

const formatCurrency = (value: number) => {
  if (!value) return 'R$ 0,00';
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
  }).format(value);
};

const formatDate = (dateStr: string) => {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleDateString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
};

const getResultadoBadge = (resultado: DisputaHistorico['resultado']) => {
  const map: Record<string, { label: string; className: string }> = {
    vencedor: { label: 'Vencedor', className: 'bg-green-500/10 text-green-700 border-green-500/20' },
    segundo: { label: '2o Lugar', className: 'bg-blue-500/10 text-blue-700 border-blue-500/20' },
    terceiro: { label: '3o Lugar', className: 'bg-yellow-500/10 text-yellow-700 border-yellow-500/20' },
    eliminado: { label: 'Eliminado', className: 'bg-red-500/10 text-red-700 border-red-500/20' },
    desistiu: { label: 'Desistiu', className: 'bg-gray-500/10 text-gray-500 border-gray-500/20' },
  };
  const cfg = map[resultado] || map.eliminado;
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${cfg?.className}`}>
      {cfg?.label}
    </span>
  );
};

const getSimResultadoBadge = (resultado: SimulacaoResultado['resultado']) => {
  const map: Record<string, { className: string }> = {
    VENCEDOR: { className: 'bg-green-500/10 text-green-700 border-green-500/20' },
    SEGUNDO: { className: 'bg-blue-500/10 text-blue-700 border-blue-500/20' },
    TERCEIRO: { className: 'bg-yellow-500/10 text-yellow-700 border-yellow-500/20' },
    ELIMINADO: { className: 'bg-red-500/10 text-red-700 border-red-500/20' },
  };
  const cfg = map[resultado] || map.ELIMINADO;
  return (
    <span className={`inline-flex items-center rounded-full border px-3 py-1 text-sm font-bold ${cfg?.className}`}>
      {resultado}
    </span>
  );
};

const getPortalBadge = (portal: string) => {
  const map: Record<string, string> = {
    PNCP: 'bg-blue-500/10 text-blue-700 border-blue-500/20',
    ComprasNet: 'bg-green-500/10 text-green-700 border-green-500/20',
    'Licitacoes-e': 'bg-orange-500/10 text-orange-700 border-orange-500/20',
  };
  const className = map[portal] || 'bg-gray-500/10 text-gray-700 border-gray-500/20';
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold ${className}`}>
      {portal}
    </span>
  );
};

const getLanceStatusIcon = (status: Lance['status']) => {
  switch (status) {
    case 'melhor':
      return <ArrowUp className="w-3 h-3 text-green-500" />;
    case 'superado':
      return <ArrowDown className="w-3 h-3 text-red-500" />;
    case 'aceito':
      return <Minus className="w-3 h-3 text-blue-500" />;
    case 'recusado':
      return <AlertCircle className="w-3 h-3 text-red-500" />;
    default:
      return null;
  }
};

// ===== COMPONENT =====

export default function DisputasDashboardPage() {
  const [activeTab, setActiveTab] = useState<'ativa' | 'simulacoes' | 'historico'>('ativa');

  // Warrior status from API
  const { data: warriorData, isLoading: warriorLoading } = useWarriorStatus(true);
  const warriorActive = warriorData?.status === 'operational' || warriorData?.status === 'active';

  // Active dispute state (mock)
  const [disputaAtiva] = useState<DisputaAtiva | null>(MOCK_DISPUTA_ATIVA);
  const [robotPaused, setRobotPaused] = useState(false);
  const [manualLanceValue, setManualLanceValue] = useState('');
  const [sendingLance, setSendingLance] = useState(false);

  // Simulation state
  const [simValorRef, setSimValorRef] = useState('2500000');
  const [simEstrategia, setSimEstrategia] = useState('moderado');
  const [simPisoMinimo, setSimPisoMinimo] = useState('2000000');
  const [simRodadas, setSimRodadas] = useState('10');
  const [simConcorrentes, setSimConcorrentes] = useState('3');
  const [simRunning, setSimRunning] = useState(false);
  const [simResult, setSimResult] = useState<SimulacaoResultado | null>(null);

  // WebSocket para tempo real
  const [wsLances, setWsLances] = useState<Array<{ item_id: string; valor: number; posicao: number }>>([]);
  const [wsConvocacao, setWsConvocacao] = useState<{ tipo: string; prazo_minutos: number; mensagem: string } | null>(null);
  const [showConvocacaoModal, setShowConvocacaoModal] = useState(false);

  const handleLanceEnviado = useCallback((data: any) => {
    setWsLances(prev => [...prev, data]);
  }, []);

  const handleLanceCoberto = useCallback((_data: any) => {
    // Could add toast notification here
  }, []);

  const handleConvocacao = useCallback((data: any) => {
    setWsConvocacao(data);
    setShowConvocacaoModal(true);
  }, []);

  const handleFimDisputa = useCallback((_data: any) => {
    // Refresh data when dispute ends
  }, []);

  const { isConnected } = useDisputeWebSocket({
    sessaoId: disputaAtiva?.pregao?.replace(/[^a-zA-Z0-9]/g, '_') || '',
    onLanceEnviado: handleLanceEnviado,
    onLanceCoberto: handleLanceCoberto,
    onConvocacao: handleConvocacao,
    onFimDisputa: handleFimDisputa,
  });

  // KPIs
  const kpi = MOCK_KPI;

  // Historico
  const historico = MOCK_HISTORICO;

  // Handlers
  const handleSendManualLance = async () => {
    if (!manualLanceValue.trim()) return;
    setSendingLance(true);
    // Simulated delay
    await new Promise((r) => setTimeout(r, 1500));
    setSendingLance(false);
    setManualLanceValue('');
  };

  const handleRunSimulation = async () => {
    setSimRunning(true);
    setSimResult(null);

    // Simulated computation
    await new Promise((r) => setTimeout(r, 2000));

    const valorRef = parseFloat(simValorRef) || 2500000;
    const piso = parseFloat(simPisoMinimo) || 2000000;
    const rodadas = parseInt(simRodadas) || 10;
    const numConc = parseInt(simConcorrentes) || 3;

    // Generate mock simulation
    const lances: SimulacaoResultado['lances'] = [];
    let nossoValor = valorRef;
    let melhorConc = valorRef * 0.98;
    const decremento = (valorRef - piso) / rodadas;

    for (let i = 1; i <= rodadas; i++) {
      nossoValor = Math.max(piso, nossoValor - decremento * (simEstrategia === 'agressivo' ? 1.3 : simEstrategia === 'sniper' ? 0.5 : simEstrategia === 'conservador' ? 0.7 : 1.0));
      melhorConc = Math.max(piso * 0.95, melhorConc - decremento * (0.8 + Math.random() * 0.4));
      lances.push({
        rodada: i,
        nosso: Math.round(nossoValor),
        melhor_concorrente: Math.round(melhorConc),
      });
    }

    const finalNosso = lances[lances.length - 1]!.nosso;
    const finalConc = lances[lances.length - 1]!.melhor_concorrente;
    const venceu = finalNosso <= finalConc;

    const concorrentes: Concorrente[] = Array.from({ length: numConc }, (_, i) => ({
      nome: `Empresa ${String.fromCharCode(65 + i)}`,
      perfil: (['agressivo', 'moderado', 'conservador', 'sniper'] as const)[i % 4]!,
      valor_final: Math.round(finalConc * (1 + i * 0.03)),
      desistiu: i >= numConc - 1 && Math.random() > 0.5,
    }));

    setSimResult({
      resultado: venceu ? 'VENCEDOR' : 'SEGUNDO',
      valor_final: finalNosso,
      posicao: venceu ? 1 : 2,
      economia_percentual: Math.round(((valorRef - finalNosso) / valorRef) * 100 * 10) / 10,
      lances,
      concorrentes,
    });

    setSimRunning(false);
  };

  // Max bar value for chart
  const maxBarValue = useMemo(() => {
    if (!simResult) return 1;
    let max = 0;
    for (const l of simResult.lances) {
      if (l.nosso > max) max = l.nosso;
      if (l.melhor_concorrente > max) max = l.melhor_concorrente;
    }
    return max || 1;
  }, [simResult]);

  const tabs = [
    { id: 'ativa' as const, label: 'Disputa Ativa', icon: Activity },
    { id: 'simulacoes' as const, label: 'Simulacoes', icon: Target },
    { id: 'historico' as const, label: 'Historico', icon: Clock },
  ];

  return (
    <div className="min-h-screen bg-grid">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-[hsl(var(--background))]/80 backdrop-blur-xl border-b border-[hsl(var(--border))]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-4">
              <Link href="/modulos/licitacoes">
                <Button variant="ghost" size="sm">
                  <ChevronLeft className="w-4 h-4 mr-2" />
                  Licitacoes
                </Button>
              </Link>
              <div className="flex items-center gap-2">
                <div className="w-10 h-10 rounded-lg bg-red-500/10 flex items-center justify-center">
                  <Swords className="w-5 h-5 text-red-500" />
                </div>
                <div>
                  <h1 className="text-lg font-semibold text-[hsl(var(--foreground))]">
                    Dashboard de Disputas
                  </h1>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">
                    Robo de Lances — WARRIOR Agent
                  </p>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Badge
                variant="outline"
                className={`text-xs px-3 py-1 ${
                  warriorLoading
                    ? 'border-gray-500/20 text-gray-500'
                    : warriorActive
                    ? 'border-green-500/20 text-green-600 bg-green-500/5'
                    : 'border-yellow-500/20 text-yellow-600 bg-yellow-500/5'
                }`}
              >
                {warriorLoading ? (
                  <Loader2 className="w-3 h-3 mr-1 animate-spin" />
                ) : (
                  <Zap className="w-3 h-3 mr-1" />
                )}
                {warriorLoading ? 'Carregando...' : warriorActive ? 'WARRIOR Ativo' : 'WARRIOR Idle'}
              </Badge>
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`} />
                <span className="text-xs text-[hsl(var(--muted-foreground))]">
                  {isConnected ? 'Tempo real' : 'Offline'}
                </span>
              </div>
              <Button
                variant="default"
                onClick={() => setActiveTab('simulacoes')}
              >
                <Play className="w-4 h-4 mr-2" />
                Nova Simulacao
              </Button>
            </div>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        {/* KPI Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                    Disputas Ativas
                  </p>
                  <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))] mt-1">
                    {kpi.disputas_ativas}
                  </p>
                </div>
                <div className="w-10 h-10 rounded-lg bg-red-500/10 flex items-center justify-center">
                  <Swords className="w-5 h-5 text-red-500" />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                    Disputas Vencidas
                  </p>
                  <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))] mt-1">
                    {kpi.disputas_vencidas}
                  </p>
                </div>
                <div className="w-10 h-10 rounded-lg bg-green-500/10 flex items-center justify-center">
                  <Trophy className="w-5 h-5 text-green-500" />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                    Economia Media
                  </p>
                  <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))] mt-1">
                    {kpi.economia_media}
                    <span className="text-sm font-normal text-[hsl(var(--muted-foreground))]">%</span>
                  </p>
                </div>
                <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
                  <TrendingDown className="w-5 h-5 text-blue-500" />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                    Posicao Media
                  </p>
                  <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))] mt-1">
                    {kpi.posicao_media}
                    <span className="text-sm font-normal text-[hsl(var(--muted-foreground))]">o</span>
                  </p>
                </div>
                <div className="w-10 h-10 rounded-lg bg-purple-500/10 flex items-center justify-center">
                  <Target className="w-5 h-5 text-purple-500" />
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Tabs */}
        <div className="border-b border-[hsl(var(--border))]">
          <div className="flex gap-1">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                    isActive
                      ? 'border-primary text-[hsl(var(--foreground))]'
                      : 'border-transparent text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))] hover:border-[hsl(var(--border))]'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  {tab.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* Tab Content: Disputa Ativa */}
        {activeTab === 'ativa' && (
          <div className="space-y-4">
            {!disputaAtiva ? (
              /* Empty state */
              <div className="text-center py-16 bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl">
                <Swords className="w-16 h-16 text-[hsl(var(--muted-foreground))]/40 mx-auto mb-4" />
                <h3 className="text-lg font-medium text-[hsl(var(--foreground))]">
                  Nenhuma disputa ativa
                </h3>
                <p className="text-[hsl(var(--muted-foreground))] mt-1 max-w-md mx-auto">
                  O WARRIOR esta monitorando os portais. Quando uma disputa iniciar, os dados aparecerao aqui em tempo real.
                </p>
                <Button
                  variant="outline"
                  className="mt-6"
                  onClick={() => setActiveTab('simulacoes')}
                >
                  <Target className="w-4 h-4 mr-2" />
                  Executar Simulacao
                </Button>
              </div>
            ) : (
              /* Active dispute view */
              <div className="space-y-4">
                {/* Dispute info card */}
                <Card className="border-red-500/20">
                  <CardHeader className="pb-3">
                    <div className="flex items-center justify-between">
                      <CardTitle className="flex items-center gap-2 text-base">
                        <Swords className="w-5 h-5 text-red-500" />
                        {disputaAtiva.pregao}
                      </CardTitle>
                      <Badge
                        variant="outline"
                        className={
                          disputaAtiva.status === 'em_disputa'
                            ? 'border-green-500/20 text-green-600 bg-green-500/5 animate-pulse'
                            : disputaAtiva.status === 'convocacao'
                            ? 'border-yellow-500/20 text-yellow-600 bg-yellow-500/5'
                            : 'border-gray-500/20 text-gray-500'
                        }
                      >
                        {disputaAtiva.status === 'em_disputa'
                          ? 'Em Disputa'
                          : disputaAtiva.status === 'convocacao'
                          ? 'Convocacao'
                          : 'Encerrada'}
                      </Badge>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
                      <div>
                        <p className="text-xs text-[hsl(var(--muted-foreground))]">Portal</p>
                        <div className="mt-1">{getPortalBadge(disputaAtiva.portal)}</div>
                      </div>
                      <div>
                        <p className="text-xs text-[hsl(var(--muted-foreground))]">Orgao</p>
                        <p className="text-sm font-medium text-[hsl(var(--foreground))] mt-1">{disputaAtiva.orgao}</p>
                      </div>
                      <div>
                        <p className="text-xs text-[hsl(var(--muted-foreground))]">Status</p>
                        <p className="text-sm font-medium text-[hsl(var(--foreground))] mt-1 capitalize">{disputaAtiva.status.replace('_', ' ')}</p>
                      </div>
                      <div>
                        <p className="text-xs text-[hsl(var(--muted-foreground))]">Posicao Atual</p>
                        <p className="text-xl font-bold text-[hsl(var(--foreground))] mt-1">{disputaAtiva.posicao_atual}o</p>
                      </div>
                      <div>
                        <p className="text-xs text-[hsl(var(--muted-foreground))]">Melhor Lance</p>
                        <p className="text-sm font-bold text-green-600 mt-1">{formatCurrency(disputaAtiva.melhor_lance)}</p>
                      </div>
                      <div>
                        <p className="text-xs text-[hsl(var(--muted-foreground))]">Meu Ultimo Lance</p>
                        <p className="text-sm font-bold text-blue-600 mt-1">{formatCurrency(disputaAtiva.meu_ultimo_lance)}</p>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                {/* Lance History Table */}
                <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl overflow-hidden">
                  <div className="px-4 py-3 border-b border-[hsl(var(--border))]">
                    <h3 className="text-sm font-semibold text-[hsl(var(--foreground))] flex items-center gap-2">
                      <BarChart3 className="w-4 h-4" />
                      Historico de Lances
                    </h3>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className="border-b border-[hsl(var(--border))] bg-[hsl(var(--muted))]">
                          <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">Rodada</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">Valor</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">Posicao</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">Status</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">Horario</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[hsl(var(--border))]">
                        {disputaAtiva.lances.map((lance, idx) => (
                          <tr key={idx} className="hover:bg-[hsl(var(--muted))]/50 transition-colors">
                            <td className="px-4 py-3 text-sm font-mono text-[hsl(var(--foreground))]">
                              <div className="flex items-center gap-2">
                                <Hash className="w-3 h-3 text-[hsl(var(--muted-foreground))]" />
                                {lance.rodada}
                              </div>
                            </td>
                            <td className="px-4 py-3 text-sm font-medium text-[hsl(var(--foreground))]">
                              {formatCurrency(lance.valor)}
                            </td>
                            <td className="px-4 py-3 text-sm text-[hsl(var(--foreground))]">{lance.posicao}o</td>
                            <td className="px-4 py-3">
                              <div className="flex items-center gap-1.5 text-xs font-semibold capitalize">
                                {getLanceStatusIcon(lance.status)}
                                {lance.status}
                              </div>
                            </td>
                            <td className="px-4 py-3 text-xs text-[hsl(var(--muted-foreground))]">{lance.timestamp}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Convocacoes */}
                {disputaAtiva.convocacoes.length > 0 && (
                  <div className="space-y-2">
                    {disputaAtiva.convocacoes.map((conv, idx) => (
                      <Card key={idx} className="border-yellow-500/20 bg-yellow-500/5">
                        <CardContent className="p-4 flex items-center gap-3">
                          <AlertCircle className="w-5 h-5 text-yellow-600 flex-shrink-0" />
                          <p className="text-sm text-[hsl(var(--foreground))]">{conv}</p>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                )}

                {/* Manual Override */}
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-sm flex items-center gap-2">
                      <Send className="w-4 h-4" />
                      Controle Manual
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="flex flex-col sm:flex-row items-start sm:items-end gap-3">
                      <div className="flex-1 w-full">
                        <label className="text-xs text-[hsl(var(--muted-foreground))] mb-1 block">
                          Valor do Lance Manual
                        </label>
                        <div className="relative">
                          <DollarSign className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[hsl(var(--muted-foreground))]" />
                          <input
                            type="number"
                            placeholder="0,00"
                            value={manualLanceValue}
                            onChange={(e) => setManualLanceValue(e.target.value)}
                            className="w-full h-9 rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--background))] pl-9 pr-3 text-sm text-[hsl(var(--foreground))]"
                          />
                        </div>
                      </div>
                      <Button
                        onClick={handleSendManualLance}
                        disabled={!manualLanceValue.trim() || sendingLance}
                      >
                        {sendingLance ? (
                          <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        ) : (
                          <Send className="w-4 h-4 mr-2" />
                        )}
                        Enviar Lance Manual
                      </Button>
                      <Button
                        variant={robotPaused ? 'default' : 'outline'}
                        onClick={() => setRobotPaused(!robotPaused)}
                        className={robotPaused ? 'bg-yellow-600 hover:bg-yellow-700' : ''}
                      >
                        {robotPaused ? (
                          <Play className="w-4 h-4 mr-2" />
                        ) : (
                          <Pause className="w-4 h-4 mr-2" />
                        )}
                        {robotPaused ? 'Retomar Robo' : 'Pausar Robo'}
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              </div>
            )}
          </div>
        )}

        {/* Tab Content: Simulacoes */}
        {activeTab === 'simulacoes' && (
          <div className="space-y-6">
            {/* Simulation Form */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <Target className="w-5 h-5 text-purple-500" />
                  Configurar Simulacao
                </CardTitle>
                <p className="text-sm text-[hsl(var(--muted-foreground))]">
                  Simule uma disputa de pregao eletronico com diferentes estrategias e parametros
                </p>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {/* Valor de referencia */}
                  <div>
                    <label className="text-sm font-medium text-[hsl(var(--foreground))] mb-1.5 block">
                      Valor de Referencia (R$)
                    </label>
                    <input
                      type="number"
                      value={simValorRef}
                      onChange={(e) => setSimValorRef(e.target.value)}
                      placeholder="2500000"
                      className="w-full h-9 rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--background))] px-3 text-sm text-[hsl(var(--foreground))]"
                    />
                  </div>

                  {/* Estrategia */}
                  <div>
                    <label className="text-sm font-medium text-[hsl(var(--foreground))] mb-1.5 block">
                      Estrategia
                    </label>
                    <select
                      value={simEstrategia}
                      onChange={(e) => setSimEstrategia(e.target.value)}
                      className="w-full h-9 rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--background))] px-3 text-sm text-[hsl(var(--foreground))]"
                    >
                      <option value="agressivo">Agressivo</option>
                      <option value="moderado">Moderado</option>
                      <option value="conservador">Conservador</option>
                      <option value="sniper">Sniper</option>
                    </select>
                  </div>

                  {/* Piso minimo */}
                  <div>
                    <label className="text-sm font-medium text-[hsl(var(--foreground))] mb-1.5 block">
                      Piso Minimo (R$)
                    </label>
                    <input
                      type="number"
                      value={simPisoMinimo}
                      onChange={(e) => setSimPisoMinimo(e.target.value)}
                      placeholder="2000000"
                      className="w-full h-9 rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--background))] px-3 text-sm text-[hsl(var(--foreground))]"
                    />
                  </div>

                  {/* Numero de rodadas */}
                  <div>
                    <label className="text-sm font-medium text-[hsl(var(--foreground))] mb-1.5 block">
                      Numero de Rodadas
                    </label>
                    <input
                      type="number"
                      value={simRodadas}
                      onChange={(e) => setSimRodadas(e.target.value)}
                      min={1}
                      max={50}
                      className="w-full h-9 rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--background))] px-3 text-sm text-[hsl(var(--foreground))]"
                    />
                  </div>

                  {/* Concorrentes */}
                  <div>
                    <label className="text-sm font-medium text-[hsl(var(--foreground))] mb-1.5 block">
                      Concorrentes
                    </label>
                    <input
                      type="number"
                      value={simConcorrentes}
                      onChange={(e) => setSimConcorrentes(e.target.value)}
                      min={1}
                      max={10}
                      className="w-full h-9 rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--background))] px-3 text-sm text-[hsl(var(--foreground))]"
                    />
                  </div>
                </div>

                <div className="flex justify-end pt-2">
                  <Button
                    onClick={handleRunSimulation}
                    disabled={simRunning}
                  >
                    {simRunning ? (
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    ) : (
                      <Play className="w-4 h-4 mr-2" />
                    )}
                    Executar Simulacao
                  </Button>
                </div>
              </CardContent>
            </Card>

            {/* Simulation Results */}
            {simResult && (
              <div className="space-y-4">
                {/* Result Summary */}
                <Card className="border-primary/20">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base flex items-center gap-2">
                      <Trophy className="w-5 h-5 text-primary" />
                      Resultado da Simulacao
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                      <div className="text-center p-3 bg-[hsl(var(--muted))] rounded-lg">
                        <p className="text-xs text-[hsl(var(--muted-foreground))] mb-1">Resultado</p>
                        {getSimResultadoBadge(simResult.resultado)}
                      </div>
                      <div className="text-center p-3 bg-[hsl(var(--muted))] rounded-lg">
                        <p className="text-xs text-[hsl(var(--muted-foreground))] mb-1">Valor Final</p>
                        <p className="text-lg font-bold text-[hsl(var(--foreground))]">
                          {formatCurrency(simResult.valor_final)}
                        </p>
                      </div>
                      <div className="text-center p-3 bg-[hsl(var(--muted))] rounded-lg">
                        <p className="text-xs text-[hsl(var(--muted-foreground))] mb-1">Posicao</p>
                        <p className="text-lg font-bold text-[hsl(var(--foreground))]">{simResult.posicao}o</p>
                      </div>
                      <div className="text-center p-3 bg-[hsl(var(--muted))] rounded-lg">
                        <p className="text-xs text-[hsl(var(--muted-foreground))] mb-1">Economia</p>
                        <p className="text-lg font-bold text-green-600">{simResult.economia_percentual}%</p>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                {/* Bar Chart */}
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-sm flex items-center gap-2">
                      <BarChart3 className="w-4 h-4" />
                      Lances por Rodada
                    </CardTitle>
                    <div className="flex items-center gap-4 mt-2">
                      <div className="flex items-center gap-1.5 text-xs text-[hsl(var(--muted-foreground))]">
                        <div className="w-3 h-3 rounded-sm bg-blue-500" />
                        Nosso Lance
                      </div>
                      <div className="flex items-center gap-1.5 text-xs text-[hsl(var(--muted-foreground))]">
                        <div className="w-3 h-3 rounded-sm bg-red-400" />
                        Melhor Concorrente
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      {simResult.lances.map((lance) => (
                        <div key={lance.rodada} className="flex items-center gap-3">
                          <span className="text-xs font-mono text-[hsl(var(--muted-foreground))] w-6 text-right">
                            R{lance.rodada}
                          </span>
                          <div className="flex-1 space-y-1">
                            <div className="flex items-center gap-2">
                              <div
                                className="h-4 rounded-sm bg-blue-500 transition-all"
                                style={{ width: `${(lance.nosso / maxBarValue) * 100}%` }}
                              />
                              <span className="text-xs text-[hsl(var(--muted-foreground))] whitespace-nowrap">
                                {formatCurrency(lance.nosso)}
                              </span>
                            </div>
                            <div className="flex items-center gap-2">
                              <div
                                className="h-4 rounded-sm bg-red-400 transition-all"
                                style={{ width: `${(lance.melhor_concorrente / maxBarValue) * 100}%` }}
                              />
                              <span className="text-xs text-[hsl(var(--muted-foreground))] whitespace-nowrap">
                                {formatCurrency(lance.melhor_concorrente)}
                              </span>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>

                {/* Concorrentes Table */}
                <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl overflow-hidden">
                  <div className="px-4 py-3 border-b border-[hsl(var(--border))]">
                    <h3 className="text-sm font-semibold text-[hsl(var(--foreground))] flex items-center gap-2">
                      <Users className="w-4 h-4" />
                      Concorrentes Simulados
                    </h3>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className="border-b border-[hsl(var(--border))] bg-[hsl(var(--muted))]">
                          <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">Nome</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">Perfil</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">Valor Final</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">Desistiu</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[hsl(var(--border))]">
                        {simResult.concorrentes.map((conc, idx) => (
                          <tr key={idx} className="hover:bg-[hsl(var(--muted))]/50 transition-colors">
                            <td className="px-4 py-3 text-sm font-medium text-[hsl(var(--foreground))]">{conc.nome}</td>
                            <td className="px-4 py-3">
                              <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold capitalize ${
                                conc.perfil === 'agressivo'
                                  ? 'bg-red-500/10 text-red-700 border-red-500/20'
                                  : conc.perfil === 'sniper'
                                  ? 'bg-purple-500/10 text-purple-700 border-purple-500/20'
                                  : conc.perfil === 'conservador'
                                  ? 'bg-blue-500/10 text-blue-700 border-blue-500/20'
                                  : 'bg-green-500/10 text-green-700 border-green-500/20'
                              }`}>
                                {conc.perfil}
                              </span>
                            </td>
                            <td className="px-4 py-3 text-sm text-[hsl(var(--foreground))]">{formatCurrency(conc.valor_final)}</td>
                            <td className="px-4 py-3 text-sm">
                              {conc.desistiu ? (
                                <span className="text-red-500 font-medium">Sim</span>
                              ) : (
                                <span className="text-green-500 font-medium">Nao</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Tab Content: Historico */}
        {activeTab === 'historico' && (
          <div className="space-y-4">
            <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl overflow-hidden">
              <div className="px-4 py-3 border-b border-[hsl(var(--border))] flex items-center justify-between">
                <h3 className="text-sm font-semibold text-[hsl(var(--foreground))] flex items-center gap-2">
                  <Clock className="w-4 h-4" />
                  Historico de Disputas
                </h3>
                <Button variant="ghost" size="sm">
                  <RefreshCw className="w-4 h-4 mr-1" />
                  Atualizar
                </Button>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-[hsl(var(--border))] bg-[hsl(var(--muted))]">
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">Pregao</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">Portal</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">Data</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">Resultado</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">Valor Final</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">Economia</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[hsl(var(--border))]">
                    {historico.map((item) => (
                      <tr key={item.id} className="hover:bg-[hsl(var(--muted))]/50 transition-colors">
                        <td className="px-4 py-3 text-sm font-medium text-[hsl(var(--foreground))]">
                          {item.pregao}
                        </td>
                        <td className="px-4 py-3">
                          {getPortalBadge(item.portal)}
                        </td>
                        <td className="px-4 py-3 text-sm text-[hsl(var(--foreground))]">
                          {formatDate(item.data)}
                        </td>
                        <td className="px-4 py-3">
                          {getResultadoBadge(item.resultado)}
                        </td>
                        <td className="px-4 py-3 text-sm font-medium text-[hsl(var(--foreground))]">
                          {item.valor_final > 0 ? formatCurrency(item.valor_final) : '-'}
                        </td>
                        <td className="px-4 py-3">
                          {item.economia_percentual > 0 ? (
                            <span className="text-sm font-semibold text-green-600">
                              {item.economia_percentual}%
                            </span>
                          ) : (
                            <span className="text-sm text-[hsl(var(--muted-foreground))]">-</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {historico.length === 0 && (
              <div className="text-center py-12 bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl">
                <Clock className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
                <h3 className="text-lg font-medium text-[hsl(var(--foreground))]">
                  Nenhuma disputa no historico
                </h3>
                <p className="text-[hsl(var(--muted-foreground))] mt-1">
                  As disputas concluidas aparecerao aqui automaticamente.
                </p>
              </div>
            )}
          </div>
        )}
      </main>

      {/* Convocação Modal (WebSocket) */}
      {showConvocacaoModal && wsConvocacao && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="bg-[hsl(var(--card))] border-2 border-red-500 rounded-xl p-6 max-w-md w-full mx-4 shadow-xl">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-full bg-red-500/10 flex items-center justify-center">
                <AlertCircle className="w-5 h-5 text-red-500" />
              </div>
              <div>
                <h3 className="text-lg font-bold text-red-600">CONVOCACAO</h3>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">
                  Prazo: {wsConvocacao.prazo_minutos} minutos
                </p>
              </div>
            </div>
            <p className="text-sm text-[hsl(var(--foreground))] mb-4">
              {wsConvocacao.mensagem}
            </p>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setShowConvocacaoModal(false)}>
                Fechar
              </Button>
              <Button variant="default" className="bg-red-600 hover:bg-red-700 text-white" onClick={() => setShowConvocacaoModal(false)}>
                Atender Convocacao
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
