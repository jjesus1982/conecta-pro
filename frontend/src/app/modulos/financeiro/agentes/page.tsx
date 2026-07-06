'use client';

import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { api } from '@/lib/api';
import {
  ArrowLeft,
  Bot,
  Cpu,
  CheckCircle,
  AlertTriangle,
  XCircle,
  Activity,
  TrendingUp,
  TrendingDown,
  Shield,
  RefreshCw,
  Wrench,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { cn, formatCurrency } from '@/lib/utils';

// ─── Types ───────────────────────────────────────────────────────────────────

interface AgentInfo {
  name: string;
  schedule: string;
  skills: string[];
  skills_loaded: string[];
  skills_missing: string[];
}

interface AgentsStatus {
  total_agents: number;
  skills_available: number;
  skills_list: string[];
  gedeon_layer: string;
  timestamp: string;
  agents: AgentInfo[];
}

interface McpTool {
  name: string;
  description: string;
  inputSchema: { type: string; properties: Record<string, unknown>; required: string[] };
}

interface McpToolsResponse {
  tools: McpTool[];
  total: number;
}

interface FinancialDashboard {
  mrr: number;
  saldo: { atual: number; status: string };
  saude_financeira: { score: number; classificacao: string; alertas: string[] };
  mes_atual: { entradas: number; saidas: number };
  contas_receber: { total: number };
  contas_pagar: { total: number };
}

interface ComplianceData {
  total_debitos: number;
  justificados: number;
  pendentes_criticos: number;
  compliance_pct: number;
  sem_categoria: number;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function agentStatusColor(agent: AgentInfo): string {
  if (agent.skills_missing.length === 0) return 'border-green-200 bg-green-500/5';
  if (agent.skills_missing.length <= 1)  return 'border-yellow-200 bg-yellow-500/5';
  return 'border-orange-200 bg-orange-500/5';
}

function agentBadge(agent: AgentInfo) {
  if (agent.skills_missing.length === 0) {
    return (
      <span className="inline-flex items-center gap-1 text-xs bg-green-100 text-green-800 px-2 py-0.5 rounded-full">
        <CheckCircle className="h-3 w-3" />Ativo
      </span>
    );
  }
  if (agent.skills_missing.length <= 1) {
    return (
      <span className="inline-flex items-center gap-1 text-xs bg-yellow-100 text-yellow-800 px-2 py-0.5 rounded-full">
        <AlertTriangle className="h-3 w-3" />Parcial
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-xs bg-orange-100 text-orange-800 px-2 py-0.5 rounded-full">
      <XCircle className="h-3 w-3" />Sem skills
    </span>
  );
}

function agentIcon(name: string) {
  if (name.includes('Advisor'))   return <TrendingUp className="h-4 w-4 text-blue-600" />;
  if (name.includes('Cashflow'))  return <Activity className="h-4 w-4 text-emerald-600" />;
  if (name.includes('Risk'))      return <Shield className="h-4 w-4 text-red-600" />;
  if (name.includes('Collection'))return <TrendingDown className="h-4 w-4 text-orange-600" />;
  if (name.includes('Pricing'))   return <TrendingUp className="h-4 w-4 text-violet-600" />;
  if (name.includes('Tax'))       return <CheckCircle className="h-4 w-4 text-gray-600" />;
  if (name.includes('Billing'))   return <Activity className="h-4 w-4 text-indigo-600" />;
  if (name.includes('Costing'))   return <Cpu className="h-4 w-4 text-cyan-600" />;
  return <Bot className="h-4 w-4 text-gray-500" />;
}

// ─── Componente principal ─────────────────────────────────────────────────────

export default function AgentesPage() {
  const { data: status, isLoading: loadingAgents, refetch } = useQuery<AgentsStatus>({
    queryKey: ['agents-status'],
    queryFn: () => api.get<AgentsStatus>('/api/v1/financial/ai/agents/status').then((r) => r.data),
    staleTime: 5 * 60 * 1000,
    refetchInterval: 60 * 1000,
  });

  const { data: dashboard } = useQuery<FinancialDashboard>({
    queryKey: ['financial-dashboard'],
    queryFn: () => api.get<FinancialDashboard>('/api/v1/financial/dashboard').then((r) => r.data),
    staleTime: 5 * 60 * 1000,
  });

  const { data: mcp } = useQuery<McpToolsResponse>({
    queryKey: ['mcp-tools'],
    queryFn: () => api.get<McpToolsResponse>('/api/v1/mcp/financial/tools').then((r) => r.data),
    staleTime: 30 * 60 * 1000,
  });

  const { data: compliance } = useQuery<ComplianceData>({
    queryKey: ['lucro-real-compliance'],
    queryFn: () => api.get<ComplianceData>('/api/v1/justificativa/compliance').then((r) => r.data),
    staleTime: 5 * 60 * 1000,
  });

  const saude = dashboard?.saude_financeira;
  const saudeColor = !saude ? 'text-gray-600'
    : saude.score >= 70 ? 'text-green-600'
    : saude.score >= 40 ? 'text-yellow-600'
    : 'text-red-600';

  const agentesAtivos  = (status?.agents ?? []).filter((a) => a.skills_missing.length === 0).length;
  const agentesParcial = (status?.agents ?? []).filter((a) => a.skills_missing.length > 0 && a.skills_missing.length <= 1).length;
  const agentesSemSkill = (status?.agents ?? []).filter((a) => a.skills_missing.length > 1).length;

  return (
    <div className="min-h-screen bg-background animate-fade-in">
      {/* Header */}
      <div className="border-b bg-card">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-4 flex items-center gap-3">
          <Link href="/modulos/financeiro">
            <button className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors">
              <ArrowLeft className="h-4 w-4" />Voltar
            </button>
          </Link>
          <div className="h-5 w-px bg-border" />
          <div className="flex items-center gap-2">
            <div className="h-8 w-8 rounded-lg bg-violet-600 flex items-center justify-center">
              <Bot className="h-4 w-4 text-white" />
            </div>
            <div>
              <h1 className="text-base font-semibold leading-tight">GEDEON — Agentes Financeiros</h1>
              <p className="text-xs text-muted-foreground">
                {loadingAgents ? 'Carregando...' :
                  `${status?.total_agents ?? 0} agentes · ${status?.skills_available ?? 0} skills · ${status?.gedeon_layer ?? ''}`}
              </p>
            </div>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
            <span className="text-xs text-muted-foreground">
              {status?.timestamp ? new Date(status.timestamp).toLocaleTimeString('pt-BR') : '—'}
            </span>
            <button
              onClick={() => void refetch()}
              className="p-1.5 rounded-md hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
              title="Atualizar"
            >
              <RefreshCw className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6 space-y-6">

        {/* KPIs financeiros reais */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Card>
            <CardContent className="pt-4 pb-3">
              <p className="text-xs text-muted-foreground">MRR Bruto</p>
              <p className="text-lg font-bold text-emerald-600 mt-1">
                {formatCurrency(dashboard?.mrr ?? 0)}
              </p>
              <p className="text-xs text-muted-foreground mt-1">Abr/2026</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4 pb-3">
              <p className="text-xs text-muted-foreground">Saldo Inter</p>
              <p className={cn('text-lg font-bold mt-1',
                (dashboard?.saldo?.atual ?? 0) > 50000 ? 'text-emerald-600' : 'text-red-600')}>
                {formatCurrency(dashboard?.saldo?.atual ?? 0)}
              </p>
              <p className="text-xs text-muted-foreground mt-1 capitalize">
                {dashboard?.saldo?.status ?? '—'}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4 pb-3">
              <p className="text-xs text-muted-foreground">Score Saúde</p>
              <p className={cn('text-lg font-bold mt-1', saudeColor)}>
                {saude?.score ?? 0}<span className="text-sm font-normal">/100</span>
              </p>
              <p className="text-xs text-muted-foreground mt-1 capitalize">
                {saude?.classificacao ?? '—'} · {saude?.alertas?.length ?? 0} alertas
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4 pb-3">
              <p className="text-xs text-muted-foreground">Compliance LR</p>
              <p className="text-lg font-bold text-emerald-600 mt-1">
                {compliance?.compliance_pct?.toFixed(1) ?? '—'}%
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                {compliance?.justificados ?? 0}/{compliance?.total_debitos ?? 0} classif.
              </p>
            </CardContent>
          </Card>
        </div>

        {/* Status dos agentes — resumo */}
        <div className="grid grid-cols-3 gap-3">
          <Card className="border-green-200">
            <CardContent className="pt-4 pb-3 flex items-center gap-3">
              <div className="h-9 w-9 rounded-lg bg-green-100 flex items-center justify-center shrink-0">
                <CheckCircle className="h-5 w-5 text-green-600" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-green-600">{agentesAtivos}</p>
                <p className="text-xs text-muted-foreground">Ativos</p>
              </div>
            </CardContent>
          </Card>
          <Card className="border-yellow-200">
            <CardContent className="pt-4 pb-3 flex items-center gap-3">
              <div className="h-9 w-9 rounded-lg bg-yellow-100 flex items-center justify-center shrink-0">
                <AlertTriangle className="h-5 w-5 text-yellow-600" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-yellow-600">{agentesParcial}</p>
                <p className="text-xs text-muted-foreground">Parcial</p>
              </div>
            </CardContent>
          </Card>
          <Card className="border-orange-200">
            <CardContent className="pt-4 pb-3 flex items-center gap-3">
              <div className="h-9 w-9 rounded-lg bg-orange-100 flex items-center justify-center shrink-0">
                <XCircle className="h-5 w-5 text-orange-600" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-orange-600">{agentesSemSkill}</p>
                <p className="text-xs text-muted-foreground">Sem skills</p>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Grid de agentes */}
        <div>
          <h2 className="text-sm font-semibold text-foreground mb-3">
            Agentes GEDEON ({status?.total_agents ?? 0})
          </h2>
          {loadingAgents ? (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="h-28 rounded-xl bg-muted animate-pulse" />
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {(status?.agents ?? []).map((agent) => (
                <Card
                  key={agent.name}
                  className={cn('border', agentStatusColor(agent))}
                >
                  <CardContent className="pt-4 pb-3">
                    <div className="flex items-start justify-between mb-1.5">
                      <div className="flex items-center gap-1.5">
                        {agentIcon(agent.name)}
                        <p className="text-sm font-medium leading-tight">
                          {agent.name.replace('Agent', '')}
                        </p>
                      </div>
                      {agentBadge(agent)}
                    </div>
                    <p className="text-xs text-muted-foreground mb-2">{agent.schedule}</p>
                    <div className="flex flex-wrap gap-1">
                      {agent.skills_loaded.map((s) => (
                        <span key={s} className="text-xs bg-green-100 text-green-700 px-1.5 py-0.5 rounded">
                          {s.split('-').slice(0, 2).join('-')}
                        </span>
                      ))}
                      {agent.skills_missing.map((s) => (
                        <span key={s} className="text-xs bg-red-100 text-red-600 px-1.5 py-0.5 rounded">
                          <AlertTriangle className="w-3 h-3 inline" /> {s.split('-').slice(0, 2).join('-')}
                        </span>
                      ))}
                      {agent.skills.length === 0 && (
                        <span className="text-xs text-muted-foreground italic">sem skills configuradas</span>
                      )}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </div>

        {/* Skills disponíveis */}
        {(status?.skills_list ?? []).length > 0 && (
          <div>
            <h2 className="text-sm font-semibold text-foreground mb-3">
              Skills disponíveis ({status?.skills_available ?? 0})
            </h2>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
              {(status?.skills_list ?? []).map((skill) => (
                <div
                  key={skill}
                  className="text-xs p-2 bg-muted/40 border border-border rounded-lg text-foreground truncate"
                  title={skill}
                >
                  {skill}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* MCP Tools */}
        {mcp && (mcp.tools ?? []).length > 0 && (
          <div>
            <h2 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
              <Wrench className="h-4 w-4 text-violet-600" />
              MCP Server Financeiro ({mcp.total ?? mcp.tools.length} ferramentas)
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {mcp.tools.map((tool) => (
                <Card key={tool.name} className="border-violet-200/60">
                  <CardContent className="pt-3 pb-3">
                    <p className="text-sm font-mono font-medium text-violet-700">
                      {tool.name}
                    </p>
                    <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                      {tool.description}
                    </p>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        )}

        {/* Alertas da saúde financeira */}
        {(saude?.alertas ?? []).length > 0 && (
          <div>
            <h2 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-amber-500" />
              Alertas financeiros ({saude?.alertas?.length ?? 0})
            </h2>
            <div className="space-y-2">
              {(saude?.alertas ?? []).map((alerta, i) => (
                <div
                  key={i}
                  className="flex gap-2 p-3 rounded-lg border border-amber-200 bg-amber-500/5 text-sm"
                >
                  <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
                  <span className="text-amber-800">{alerta}</span>
                </div>
              ))}
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
