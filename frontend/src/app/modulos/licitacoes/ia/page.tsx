'use client';

/**
 * IA Hub - Central de Inteligência Artificial para Licitações
 * Conecta PRO - 7 Agentes IA especializados
 */

import { useState } from 'react';
import {
  Bot,
  Search,
  FileText,
  CheckCircle,
  Calculator,
  FileOutput,
  Swords,
  Shield,
  Play,
  Loader2,
  ChevronRight,
  Zap,
  AlertCircle,
  TrendingUp,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';

const API_URL = process.env.NEXT_PUBLIC_API_URL || (
  typeof window !== 'undefined' && window.location.hostname === 'localhost'
    ? 'http://localhost:8080'
    : 'https://erp.conectamais.pro'
);

interface AgentInfo {
  id: string;
  name: string;
  title: string;
  description: string;
  icon: React.ElementType;
  color: string;
  bgColor: string;
  status: 'operational' | 'development' | 'planned';
  capabilities: string[];
}

const AGENTS: AgentInfo[] = [
  {
    id: 'scout',
    name: 'SCOUT',
    title: 'Cacador de Editais',
    description: 'Busca automatica em multiplos portais de licitacao, filtragem por CNAE e ranqueamento por relevancia.',
    icon: Search,
    color: 'text-blue-600',
    bgColor: 'bg-blue-500/10',
    status: 'operational',
    capabilities: [
      'Busca no PNCP (API oficial)',
      'Filtragem por UF, modalidade, segmento',
      'Ranqueamento por relevancia',
      'Monitoramento de 15+ portais (em expansao)',
    ],
  },
  {
    id: 'analyst',
    name: 'ANALYST',
    title: 'Analisador de Editais',
    description: 'Leitura automatica de editais com IA, extracao de requisitos, identificacao de riscos e red flags.',
    icon: FileText,
    color: 'text-purple-600',
    bgColor: 'bg-purple-500/10',
    status: 'operational',
    capabilities: [
      'Analise de texto via Claude API',
      'Extracao de requisitos de habilitacao',
      'Identificacao de red flags',
      'Extracao de prazos e documentos',
    ],
  },
  {
    id: 'assessor',
    name: 'ASSESSOR',
    title: 'Avaliador de Viabilidade',
    description: 'Analise automatica GO/NO-GO baseada na capacidade da empresa vs requisitos do edital.',
    icon: CheckCircle,
    color: 'text-green-600',
    bgColor: 'bg-green-500/10',
    status: 'operational',
    capabilities: [
      'Score de viabilidade 0-100',
      'Recomendacao GO / NO-GO / CONDICIONAL',
      'Verificacao de certidoes',
      'Analise de capacidade tecnica e financeira',
    ],
  },
  {
    id: 'pricer',
    name: 'PRICER',
    title: 'Precificador Inteligente',
    description: 'Cálculo automatico de preco competitivo com BDI, encargos e 3 cenarios de margem.',
    icon: Calculator,
    color: 'text-orange-600',
    bgColor: 'bg-orange-500/10',
    status: 'operational',
    capabilities: [
      '3 cenarios: agressivo, equilibrado, conservador',
      'Cálculo de encargos sociais',
      'BDI por regime tributario',
      'Comparativo com precos historicos PNCP',
    ],
  },
  {
    id: 'compiler',
    name: 'COMPILER',
    title: 'Montador de Propostas',
    description: 'Geracao automatica de proposta comercial, planilha de custos, declaracoes e checklist.',
    icon: FileOutput,
    color: 'text-cyan-600',
    bgColor: 'bg-cyan-500/10',
    status: 'operational',
    capabilities: [
      'Carta proposta automatica',
      'Planilha de custos detalhada',
      'Declaracoes padrao (ME/EPP, menor, etc)',
      'Checklist de documentos',
    ],
  },
  {
    id: 'warrior',
    name: 'WARRIOR',
    title: 'Robo de Lances',
    description: 'Disputa automatica em pregoes eletronicos com estrategia configuravel.',
    icon: Swords,
    color: 'text-red-600',
    bgColor: 'bg-red-500/10',
    status: 'development',
    capabilities: [
      'Disputa em ComprasNet (em dev)',
      'Estrategia agressiva/equilibrada/conservadora',
      'Monitoramento em tempo real',
      'Resposta a convocacoes',
    ],
  },
  {
    id: 'sentinel',
    name: 'SENTINEL',
    title: 'Monitor de Certidoes',
    description: 'Monitoramento 24/7 de certidoes com alertas de vencimento e renovacao automatica.',
    icon: Shield,
    color: 'text-amber-600',
    bgColor: 'bg-amber-500/10',
    status: 'operational',
    capabilities: [
      'Monitoramento de 6 tipos de certidao',
      'Alertas 30/15/7/3/1 dias antes',
      'Renovacao automatica (CNDT, CRF)',
      'Dashboard de compliance',
    ],
  },
];

export default function IAHubPage() {
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [pipelineRunning, setPipelineRunning] = useState(false);
  const [pipelineResult, setPipelineResult] = useState<any>(null);
  const [editalText, setEditalText] = useState('');
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisResult, setAnalysisResult] = useState<any>(null);

  const handleRunPipeline = async () => {
    if (!editalText.trim()) return;
    setPipelineRunning(true);
    setPipelineResult(null);

    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_URL}/api/v1/bidding/agents/pipeline`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          texto_edital: editalText,
          regime_tributario: 'lucro_real',
          salario_base_vigilante: 1800.0,
          empresa: {
            razao_social: 'CONECTAMAIS ELETRONICA LTDA',
            cnpj: '35.710.481/0001-03',
            cidade: 'Manaus',
            representante: 'Jordan Santos de Jesus',
            cargo: 'Socio-Administrador',
          },
        }),
      });
      const data = await response.json();
      setPipelineResult(data);
    } catch (error) {
      setPipelineResult({ error: 'Erro ao executar pipeline' });
    } finally {
      setPipelineRunning(false);
    }
  };

  const handleAnalyze = async () => {
    if (!editalText.trim()) return;
    setAnalysisLoading(true);
    setAnalysisResult(null);

    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_URL}/api/v1/bidding/agents/analyst/analisar`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ texto_edital: editalText }),
      });
      const data = await response.json();
      setAnalysisResult(data);
    } catch (error) {
      setAnalysisResult({ error: 'Erro ao analisar' });
    } finally {
      setAnalysisLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-3xl font-bold flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-purple-500 to-blue-600 flex items-center justify-center">
              <Bot className="w-5 h-5 text-white" />
            </div>
            IA Hub - Licitacoes
          </h1>
          <p className="text-muted-foreground mt-1">
            7 agentes inteligentes trabalhando para voce vencer licitacoes
          </p>
        </div>
        <Badge variant="outline" className="text-sm px-3 py-1">
          <Zap className="w-3 h-3 mr-1" />
          Powered by Claude
        </Badge>
      </div>

      {/* Agent Cards Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {AGENTS.map((agent) => {
          const Icon = agent.icon;
          const isSelected = selectedAgent === agent.id;

          return (
            <Card
              key={agent.id}
              className={`cursor-pointer transition-all hover:shadow-lg ${
                isSelected ? 'ring-2 ring-primary shadow-lg' : ''
              }`}
              onClick={() => setSelectedAgent(isSelected ? null : agent.id)}
            >
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <div className={`w-10 h-10 rounded-xl ${agent.bgColor} flex items-center justify-center`}>
                    <Icon className={`w-5 h-5 ${agent.color}`} />
                  </div>
                  <Badge
                    variant={
                      agent.status === 'operational'
                        ? 'default'
                        : agent.status === 'development'
                        ? 'secondary'
                        : 'outline'
                    }
                    className="text-xs"
                  >
                    {agent.status === 'operational'
                      ? 'Ativo'
                      : agent.status === 'development'
                      ? 'Em Dev'
                      : 'Planejado'}
                  </Badge>
                </div>
                <CardTitle className="text-base mt-2">
                  <span className="font-mono text-xs text-muted-foreground">{agent.name}</span>
                  <br />
                  {agent.title}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground mb-3">{agent.description}</p>
                {isSelected && (
                  <div className="space-y-1 pt-2 border-t">
                    {agent.capabilities.map((cap, idx) => (
                      <div key={idx} className="flex items-center gap-2 text-xs">
                        <ChevronRight className="w-3 h-3 text-primary flex-shrink-0" />
                        <span>{cap}</span>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Pipeline Section */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-primary" />
            Pipeline Inteligente
          </CardTitle>
          <p className="text-sm text-muted-foreground">
            Cole o texto do edital e execute o pipeline completo: ANALYST → ASSESSOR → PRICER → COMPILER
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          <Textarea
            placeholder="Cole aqui o texto do edital para analise automatica..."
            className="min-h-[150px] font-mono text-sm"
            value={editalText}
            onChange={(e) => setEditalText(e.target.value)}
          />
          <div className="flex gap-2">
            <Button
              onClick={handleAnalyze}
              variant="outline"
              disabled={!editalText.trim() || analysisLoading}
            >
              {analysisLoading ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <FileText className="w-4 h-4 mr-2" />
              )}
              Apenas Analisar
            </Button>
            <Button
              onClick={handleRunPipeline}
              disabled={!editalText.trim() || pipelineRunning}
            >
              {pipelineRunning ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Play className="w-4 h-4 mr-2" />
              )}
              Executar Pipeline Completo
            </Button>
          </div>

          {/* Analysis Result */}
          {analysisResult && (
            <Card className="border-purple-500/20 bg-purple-500/5">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <FileText className="w-4 h-4 text-purple-600" />
                  Resultado da Analise
                </CardTitle>
              </CardHeader>
              <CardContent>
                {analysisResult.error ? (
                  <p className="text-sm text-red-600">{analysisResult.error}</p>
                ) : (
                  <div className="space-y-3">
                    {analysisResult.analise?.objeto_resumido && (
                      <div>
                        <p className="text-xs font-semibold text-muted-foreground">Objeto</p>
                        <p className="text-sm">{analysisResult.analise.objeto_resumido}</p>
                      </div>
                    )}
                    {analysisResult.analise?.modalidade_identificada && (
                      <div>
                        <p className="text-xs font-semibold text-muted-foreground">Modalidade</p>
                        <Badge variant="outline">{analysisResult.analise.modalidade_identificada}</Badge>
                      </div>
                    )}
                    {analysisResult.analise?.red_flags?.length > 0 && (
                      <div>
                        <p className="text-xs font-semibold text-muted-foreground mb-1">Red Flags</p>
                        {analysisResult.analise.red_flags.map((rf: any, idx: number) => (
                          <div key={idx} className="flex items-center gap-2 text-sm">
                            <AlertCircle className={`w-3 h-3 ${
                              rf.severidade === 'alta' ? 'text-red-500' : 'text-yellow-500'
                            }`} />
                            <span>{rf.descricao}</span>
                          </div>
                        ))}
                      </div>
                    )}
                    {analysisResult.analise?.recomendacao_participacao && (
                      <div>
                        <p className="text-xs font-semibold text-muted-foreground">Recomendacao</p>
                        <Badge variant={
                          analysisResult.analise.recomendacao_participacao === 'alta' ? 'default' :
                          analysisResult.analise.recomendacao_participacao === 'baixa' ? 'destructive' : 'secondary'
                        }>
                          {analysisResult.analise.recomendacao_participacao}
                        </Badge>
                      </div>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* Pipeline Result */}
          {pipelineResult && (
            <Card className="border-primary/20 bg-primary/5">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <TrendingUp className="w-4 h-4 text-primary" />
                  Resultado do Pipeline
                </CardTitle>
              </CardHeader>
              <CardContent>
                {pipelineResult.error ? (
                  <p className="text-sm text-red-600">{pipelineResult.error}</p>
                ) : (
                  <div className="space-y-4">
                    <div className="flex items-center gap-4">
                      <Badge variant={
                        pipelineResult.recomendacao === 'GO' ? 'default' :
                        pipelineResult.recomendacao === 'NO_GO' ? 'destructive' : 'secondary'
                      } className="text-sm px-3 py-1">
                        {pipelineResult.recomendacao || pipelineResult.status}
                      </Badge>
                      {pipelineResult.score && (
                        <span className="text-sm font-semibold">
                          Score: {pipelineResult.score}/100
                        </span>
                      )}
                    </div>

                    {pipelineResult.cenarios && (
                      <div className="grid grid-cols-3 gap-3">
                        {Object.entries(pipelineResult.cenarios).map(([key, cenario]: [string, any]) => (
                          <div key={key} className="p-3 bg-background rounded-lg border">
                            <p className="text-xs font-semibold text-muted-foreground capitalize">{key}</p>
                            <p className="text-lg font-bold">
                              {new Intl.NumberFormat('pt-BR', {
                                style: 'currency',
                                currency: 'BRL',
                              }).format(cenario.total || 0)}
                            </p>
                            <p className="text-xs text-muted-foreground">{cenario.descricao}</p>
                          </div>
                        ))}
                      </div>
                    )}

                    {pipelineResult.documentos_gerados > 0 && (
                      <p className="text-sm text-muted-foreground">
                        {pipelineResult.documentos_gerados} documento(s) gerado(s) pelo COMPILER
                      </p>
                    )}

                    {pipelineResult.justificativa && (
                      <p className="text-sm text-muted-foreground italic">
                        {pipelineResult.justificativa}
                      </p>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </CardContent>
      </Card>

      {/* Architecture Diagram */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Arquitetura do Pipeline</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center gap-2 flex-wrap py-4">
            {['SCOUT', 'ANALYST', 'ASSESSOR', 'PRICER', 'COMPILER', 'WARRIOR'].map((agent, idx) => (
              <div key={agent} className="flex items-center gap-2">
                <div className="px-3 py-1.5 rounded-lg bg-primary/10 text-primary text-xs font-mono font-semibold">
                  {agent}
                </div>
                {idx < 5 && <ChevronRight className="w-4 h-4 text-muted-foreground" />}
              </div>
            ))}
          </div>
          <div className="flex justify-center mt-2">
            <div className="px-3 py-1.5 rounded-lg bg-amber-500/10 text-amber-600 text-xs font-mono font-semibold">
              SENTINEL (24/7)
            </div>
          </div>
          <p className="text-center text-xs text-muted-foreground mt-4">
            Diferencial unico: Licitacao → Contrato → Execucao → Medicao → Fatura → NF-e (integracao ERP completa)
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
