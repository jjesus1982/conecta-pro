'use client';

/**
 * Dashboard de Licitações — Conecta PRO
 * Dados reais: 11 editais, 8 certidões, 5 propostas
 */

import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import Link from 'next/link';
import {
  FileText, Shield, AlertTriangle, Target, Award, DollarSign,
  TrendingUp, ChevronRight, RefreshCw, CheckCircle, XCircle,
  Clock, Building2, Bot, Search, Gavel,
} from 'lucide-react';
import { api } from '@/lib/api';

// ─── Types ───────────────────────────────────────────────────────────────────

interface BiddingStats {
  total_editais: number;
  participando: number;
  pipeline_valor: number;
  ganhas: number;
  perdidas: number;
  total_ganho: number;
  taxa_conversao: number;
  certidoes_validas: number;
  certidoes_total: number;
}

interface Tender {
  id: string;
  numero: string;
  orgao_nome: string;
  objeto_resumido: string;
  valor_estimado: number;
  status: string;
  participando: boolean;
  modalidade: string;
  data_abertura: string | null;
  data_encerramento_propostas: string | null;
  segmento: string;
  tags: any;
}

interface Certificate {
  id: string;
  tipo: string;
  nome: string;
  situacao: string;
  status: string;
  data_validade: string | null;
  dias_para_vencer: number;
}

interface Proposal {
  id: string;
  numero: string;
  valor_total: number;
  status: string;
  edital_numero: string;
  orgao_nome: string;
  objeto_resumido: string;
}

interface Alerta {
  tipo: string;
  nome: string;
  dias: number;
  severity: string;
  message: string;
}

interface DashboardData {
  stats: BiddingStats;
  tenders: Tender[];
  certificates: Certificate[];
  proposals: Proposal[];
  alertas: Alerta[];
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const fmt = (v: number) => v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });

const statusLabel: Record<string, { label: string; color: string }> = {
  draft: { label: 'Rascunho', color: 'bg-slate-500/10 text-slate-400 border-slate-500/30' },
  analyzing: { label: 'Em Análise', color: 'bg-blue-500/10 text-blue-500 border-blue-500/30' },
  decided_go: { label: 'Participar', color: 'bg-cyan-500/10 text-cyan-500 border-cyan-500/30' },
  proposal_ready: { label: 'Proposta Pronta', color: 'bg-amber-500/10 text-amber-500 border-amber-500/30' },
  in_dispute: { label: 'Em Disputa', color: 'bg-orange-500/10 text-orange-500 border-orange-500/30' },
  won: { label: 'GANHA', color: 'bg-emerald-500/10 text-emerald-500 border-emerald-500/30' },
  lost: { label: 'Perdida', color: 'bg-red-500/10 text-red-500 border-red-500/30' },
};

const certStatusIcon = (dias: number) => {
  if (dias <= 0) return <XCircle className="h-4 w-4 text-red-500" />;
  if (dias <= 15) return <AlertTriangle className="h-4 w-4 text-red-500" />;
  if (dias <= 30) return <Clock className="h-4 w-4 text-amber-500" />;
  return <CheckCircle className="h-4 w-4 text-emerald-500" />;
};

// ─── Funnel stages ───────────────────────────────────────────────────────────

const funnelStages = [
  { key: 'draft', label: 'Identificados', color: 'bg-slate-500' },
  { key: 'analyzing', label: 'Em Análise', color: 'bg-blue-500' },
  { key: 'decided_go', label: 'Decidido Ir', color: 'bg-cyan-500' },
  { key: 'proposal_ready', label: 'Proposta Pronta', color: 'bg-amber-500' },
  { key: 'in_dispute', label: 'Em Disputa', color: 'bg-orange-500' },
  { key: 'won', label: 'Ganhas', color: 'bg-emerald-500' },
  { key: 'lost', label: 'Perdidas', color: 'bg-red-500' },
];

// ─── Component ───────────────────────────────────────────────────────────────

export default function LicitacoesPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/api/v1/financial/bidding/dashboard');
      setData(res.data);
    } catch (err) {
      console.error('Erro ao carregar licitações:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  if (loading || !data) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <RefreshCw className="h-8 w-8 animate-spin text-blue-500" />
      </div>
    );
  }

  const { stats, tenders, certificates, proposals, alertas } = data;

  // Funnel counts
  const funnelCounts = funnelStages.map(s => ({
    ...s,
    count: tenders.filter(t => t.status === s.key).length,
    value: tenders.filter(t => t.status === s.key).reduce((sum, t) => sum + t.valor_estimado, 0),
  }));
  const maxFunnel = Math.max(...funnelCounts.map(f => f.count), 1);

  return (
    <div className="space-y-6 p-1">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold text-[hsl(var(--foreground))]">Licitações e Propostas</h1>
          <p className="text-sm text-[hsl(var(--muted-foreground))]">
            Pipeline: {fmt(stats.pipeline_valor)} — {stats.participando} editais ativos
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link href="/modulos/licitacoes/editais">
            <Button variant="outline" size="sm"><Search className="h-4 w-4 mr-1" />Buscar Editais</Button>
          </Link>
          <Link href="/modulos/licitacoes/ia">
            <Button variant="outline" size="sm"><Bot className="h-4 w-4 mr-1" />IA Hub</Button>
          </Link>
          <Button variant="outline" size="sm" onClick={loadData} disabled={loading}>
            <RefreshCw className={`h-4 w-4 mr-1 ${loading ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </div>

      {/* Alertas de Certidões */}
      {alertas.length > 0 && (
        <Card className="border-red-500/30 bg-red-500/5">
          <CardContent className="pt-4 pb-3">
            <div className="flex items-center gap-2 mb-3">
              <AlertTriangle className="h-4 w-4 text-red-500" />
              <span className="text-sm font-semibold text-red-500">Alertas de Habilitação</span>
            </div>
            <div className="space-y-2">
              {alertas.map((a, i) => (
                <div key={i} className="flex items-center gap-3 text-sm">
                  <Badge variant={a.severity === 'critical' ? 'destructive' : 'secondary'} className="text-[10px] w-[70px] justify-center">
                    {a.severity === 'critical' ? 'VENCIDA' : a.severity === 'high' ? 'URGENTE' : 'ATENÇÃO'}
                  </Badge>
                  <span className="text-[hsl(var(--foreground))]">{a.message}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        <Card className="border-l-4 border-l-blue-500">
          <CardContent className="pt-4 pb-3">
            <p className="text-xs text-[hsl(var(--muted-foreground))] uppercase">Pipeline</p>
            <p className="text-xl font-bold text-[hsl(var(--foreground))] mt-1">{fmt(stats.pipeline_valor)}</p>
            <p className="text-xs text-[hsl(var(--muted-foreground))]">{stats.participando} editais</p>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-emerald-500">
          <CardContent className="pt-4 pb-3">
            <p className="text-xs text-[hsl(var(--muted-foreground))] uppercase">Ganhas</p>
            <p className="text-xl font-bold text-emerald-500 mt-1">{stats.ganhas}</p>
            <p className="text-xs text-[hsl(var(--muted-foreground))]">{fmt(stats.total_ganho)}</p>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-amber-500">
          <CardContent className="pt-4 pb-3">
            <p className="text-xs text-[hsl(var(--muted-foreground))] uppercase">Taxa Conversão</p>
            <p className="text-xl font-bold text-amber-500 mt-1">{stats.taxa_conversao}%</p>
            <p className="text-xs text-[hsl(var(--muted-foreground))]">{stats.ganhas}W / {stats.perdidas}L</p>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-violet-500">
          <CardContent className="pt-4 pb-3">
            <p className="text-xs text-[hsl(var(--muted-foreground))] uppercase">Certidões</p>
            <p className="text-xl font-bold text-[hsl(var(--foreground))] mt-1">{stats.certidoes_validas}/{stats.certidoes_total}</p>
            <p className="text-xs text-[hsl(var(--muted-foreground))]">válidas</p>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-red-500">
          <CardContent className="pt-4 pb-3">
            <p className="text-xs text-[hsl(var(--muted-foreground))] uppercase">Alertas</p>
            <p className="text-xl font-bold text-red-500 mt-1">{alertas.length}</p>
            <p className="text-xs text-[hsl(var(--muted-foreground))]">certidões em risco</p>
          </CardContent>
        </Card>
      </div>

      {/* Funnel + Certidões */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Funnel */}
        <Card className="lg:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <Target className="h-4 w-4 text-blue-500" />
              Funil de Licitações
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {funnelCounts.map(stage => (
                <div key={stage.key} className="flex items-center gap-3">
                  <span className="text-xs text-[hsl(var(--muted-foreground))] w-[110px] text-right truncate">{stage.label}</span>
                  <div className="flex-1 h-7 bg-[hsl(var(--muted))] rounded-md overflow-hidden">
                    <div
                      className={`h-full ${stage.color} rounded-md flex items-center justify-between px-2 transition-all`}
                      style={{ width: `${Math.max((stage.count / maxFunnel) * 100, 8)}%` }}
                    >
                      <span className="text-xs font-bold text-white">{stage.count}</span>
                      {stage.value > 0 && (
                        <span className="text-[9px] text-white/80 hidden sm:inline">{fmt(stage.value)}</span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Checklist de Certidões */}
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base flex items-center gap-2">
                <Shield className="h-4 w-4 text-violet-500" />
                Certidões
              </CardTitle>
              <Link href="/modulos/licitacoes/certidoes">
                <Button variant="ghost" size="sm" className="text-xs h-7">Ver todas</Button>
              </Link>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {certificates.map(cert => (
                <div key={cert.id} className="flex items-center gap-2 p-2 rounded-lg border border-[hsl(var(--border))]">
                  {certStatusIcon(cert.dias_para_vencer)}
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium truncate">{cert.tipo}</p>
                    <p className="text-[10px] text-[hsl(var(--muted-foreground))] truncate">{cert.nome}</p>
                  </div>
                  <Badge
                    variant="outline"
                    className={`text-[9px] ${cert.dias_para_vencer <= 0 ? 'text-red-500 border-red-500/30' : cert.dias_para_vencer <= 15 ? 'text-red-500 border-red-500/30' : cert.dias_para_vencer <= 30 ? 'text-amber-500 border-amber-500/30' : 'text-emerald-500 border-emerald-500/30'}`}
                  >
                    {cert.dias_para_vencer <= 0 ? 'VENCIDA' : `${cert.dias_para_vencer}d`}
                  </Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Tabela de Editais */}
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base flex items-center gap-2">
              <Gavel className="h-4 w-4 text-blue-500" />
              Editais ({tenders.length})
            </CardTitle>
            <Link href="/modulos/licitacoes/editais">
              <Button variant="ghost" size="sm" className="text-xs h-7">Ver todos <ChevronRight className="h-3 w-3 ml-1" /></Button>
            </Link>
          </div>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[90px]">Número</TableHead>
                  <TableHead>Órgão</TableHead>
                  <TableHead>Objeto</TableHead>
                  <TableHead className="text-right w-[120px]">Valor Estimado</TableHead>
                  <TableHead className="w-[80px]">Modalidade</TableHead>
                  <TableHead className="w-[110px]">Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {tenders.map(t => {
                  const st = statusLabel[t.status] || { label: t.status, color: '' };
                  return (
                    <TableRow key={t.id}>
                      <TableCell className="font-mono text-xs">{t.numero}</TableCell>
                      <TableCell className="text-sm max-w-[200px] truncate" title={t.orgao_nome}>
                        {t.orgao_nome}
                      </TableCell>
                      <TableCell className="text-xs max-w-[250px] truncate" title={t.objeto_resumido || ''}>
                        {t.objeto_resumido || '—'}
                      </TableCell>
                      <TableCell className="text-right font-mono text-sm">{fmt(t.valor_estimado)}</TableCell>
                      <TableCell className="text-[10px] uppercase">{t.modalidade || '—'}</TableCell>
                      <TableCell>
                        <Badge variant="outline" className={`text-[10px] ${st.color}`}>
                          {st.label}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      {/* Propostas */}
      {proposals.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base flex items-center gap-2">
                <FileText className="h-4 w-4 text-amber-500" />
                Propostas ({proposals.length})
              </CardTitle>
              <Link href="/modulos/licitacoes/propostas">
                <Button variant="ghost" size="sm" className="text-xs h-7">Ver todas</Button>
              </Link>
            </div>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[110px]">Proposta</TableHead>
                    <TableHead className="w-[90px]">Edital</TableHead>
                    <TableHead>Órgão</TableHead>
                    <TableHead className="text-right w-[120px]">Valor</TableHead>
                    <TableHead className="w-[100px]">Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {proposals.map(p => {
                    const st = statusLabel[p.status] || { label: p.status, color: '' };
                    return (
                      <TableRow key={p.id}>
                        <TableCell className="font-mono text-xs">{p.numero}</TableCell>
                        <TableCell className="font-mono text-xs">{p.edital_numero}</TableCell>
                        <TableCell className="text-sm max-w-[200px] truncate">{p.orgao_nome}</TableCell>
                        <TableCell className="text-right font-mono text-sm">{fmt(p.valor_total)}</TableCell>
                        <TableCell>
                          <Badge variant="outline" className={`text-[10px] ${st.color}`}>
                            {st.label}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Integration Banner */}
      <Card className="border-[hsl(var(--primary))]/20 bg-gradient-to-r from-[hsl(var(--primary))]/5 to-transparent">
        <CardContent className="py-4">
          <div className="flex items-center gap-4">
            <div className="w-10 h-10 rounded-xl bg-[hsl(var(--primary))]/10 flex items-center justify-center flex-shrink-0">
              <TrendingUp className="w-5 h-5 text-[hsl(var(--primary))]" />
            </div>
            <div className="flex-1">
              <h3 className="font-semibold text-sm">Integração ERP Completa</h3>
              <p className="text-xs text-[hsl(var(--muted-foreground))]">
                Licitação → Contrato → Execução → Medição → Fatura → NF-e
              </p>
            </div>
            <div className="flex gap-2">
              {[
                { label: 'Editais', href: '/modulos/licitacoes/editais' },
                { label: 'Propostas', href: '/modulos/licitacoes/propostas' },
                { label: 'Certidões', href: '/modulos/licitacoes/certidoes' },
                { label: 'Contratos', href: '/modulos/licitacoes/contratos' },
              ].map(item => (
                <Link key={item.label} href={item.href}>
                  <Button variant="outline" size="sm" className="text-xs h-7">{item.label}</Button>
                </Link>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
