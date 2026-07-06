'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  FileText, DollarSign, Users, Shield, AlertTriangle, RefreshCw,
  Calendar, Building2, CheckCircle, Clock, ArrowUpRight, RotateCcw,
  ChevronDown, ChevronUp, Receipt,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { api } from '@/lib/api';

// ─── Types ───────────────────────────────────────────────────────────────────

interface ContractClient {
  id: string;
  name: string;
  cnpj: string;
  email: string;
  city: string;
  state: string;
}

interface SlaConfig {
  retencao_issqn?: boolean;
  retencao_inss?: boolean;
  retencao_inss_aliquota?: number;
  retencao_pis_cofins_csll?: boolean;
}

interface Contract {
  id: string;
  contract_number: string;
  servico: string;
  description: string;
  monthly_value: number;
  total_value: number;
  start_date: string;
  end_date: string;
  status: string;
  contract_type: string;
  auto_renewal: boolean;
  renewal_period_months: number;
  adjustment_enabled: boolean;
  adjustment_index: string | null;
  sla_config: SlaConfig;
  client: ContractClient;
}

interface ContractsResponse {
  total: number;
  mrr_total: number;
  items: Contract[];
}

interface ContractsSummary {
  total_ativos: number;
  mrr_total: number;
  mrr_anual: number;
  retencoes: { com_inss: number; com_issqn: number; com_pis_cofins: number };
  vencimentos: { em_30_dias: number; em_60_dias: number; em_90_dias: number };
  alertas: Array<{
    contract_number: string;
    client: string;
    end_date: string;
    dias: number;
    severity: string;
    message: string;
  }>;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const fmt = (v: number) => v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });

const fmtCnpj = (cnpj: string) => {
  const c = cnpj.replace(/\D/g, '').padStart(14, '0');
  return `${c.slice(0,2)}.${c.slice(2,5)}.${c.slice(5,8)}/${c.slice(8,12)}-${c.slice(12)}`;
};

const shortName = (name: string) =>
  name.replace(/^CONDOMINIO\s+(RESIDENCIAL\s+)?/i, '')
      .replace(/^RESIDENCIAL\s+/i, '')
      .replace(/^DO\s+EDIFICIO\s+/i, 'Ed. ');

const daysUntil = (dateStr: string) => {
  const d = new Date(dateStr);
  const now = new Date();
  return Math.ceil((d.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
};

// ─── Component ───────────────────────────────────────────────────────────────

export default function ContratosPage() {
  const [contracts, setContracts] = useState<ContractsResponse | null>(null);
  const [summary, setSummary] = useState<ContractsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [renewDialogOpen, setRenewDialogOpen] = useState(false);
  const [renewTarget, setRenewTarget] = useState<Contract | null>(null);
  const [reajuste, setReajuste] = useState('0');
  const [renewLoading, setRenewLoading] = useState(false);
  const [sortField, setSortField] = useState<'value' | 'name' | 'end'>('value');
  const [sortAsc, setSortAsc] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [cRes, sRes] = await Promise.all([
        api.get('/api/v1/financial/contracts'),
        api.get('/api/v1/financial/contracts/summary'),
      ]);
      setContracts(cRes.data);
      setSummary(sRes.data);
    } catch (err) {
      console.error('Erro ao carregar contratos:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleRenew = async () => {
    if (!renewTarget) return;
    setRenewLoading(true);
    try {
      await api.post(`/api/v1/financial/contracts/${renewTarget.id}/renew`, null, {
        params: { reajuste_percent: parseFloat(reajuste) || 0, meses: 12 },
      });
      setRenewDialogOpen(false);
      setRenewTarget(null);
      setReajuste('0');
      await loadData();
    } catch (err) {
      console.error('Erro ao renovar:', err);
    } finally {
      setRenewLoading(false);
    }
  };

  if (loading || !contracts || !summary) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <RefreshCw className="h-8 w-8 animate-spin text-blue-500" />
      </div>
    );
  }

  // Sorting
  const sorted = [...contracts.items].sort((a, b) => {
    const dir = sortAsc ? 1 : -1;
    if (sortField === 'value') return (a.monthly_value - b.monthly_value) * dir;
    if (sortField === 'name') return a.client.name.localeCompare(b.client.name) * dir;
    return (new Date(a.end_date).getTime() - new Date(b.end_date).getTime()) * dir;
  });

  // Fiscal totals
  const issRetidoMensal = contracts.items
    .filter(c => c.sla_config.retencao_issqn)
    .reduce((s, c) => s + c.monthly_value * 0.05, 0);

  const inssRetidoMensal = contracts.items
    .filter(c => c.sla_config.retencao_inss)
    .reduce((s, c) => s + c.monthly_value * (c.sla_config.retencao_inss_aliquota || 0.11), 0);

  const pisCofinsMensal = contracts.items
    .filter(c => c.sla_config.retencao_pis_cofins_csll)
    .reduce((s, c) => s + c.monthly_value * 0.0465, 0);

  const totalRetencoes = issRetidoMensal + inssRetidoMensal + pisCofinsMensal;

  const toggleSort = (field: typeof sortField) => {
    if (sortField === field) setSortAsc(!sortAsc);
    else { setSortField(field); setSortAsc(false); }
  };

  const SortIcon = ({ field }: { field: typeof sortField }) => {
    if (sortField !== field) return null;
    return sortAsc ? <ChevronUp className="h-3 w-3 inline ml-0.5" /> : <ChevronDown className="h-3 w-3 inline ml-0.5" />;
  };

  return (
    <div className="space-y-6 p-1">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-semibold text-[hsl(var(--foreground))]">Gestão de Contratos</h1>
          <p className="text-sm text-[hsl(var(--muted-foreground))]">
            {summary.total_ativos} contratos ativos — CONECTAMAIS ELETRONICA LTDA
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Badge variant="outline" className="text-emerald-500 border-emerald-500/30">
            {summary.total_ativos} Ativos
          </Badge>
          {summary.vencimentos.em_30_dias > 0 && (
            <Badge variant="destructive">{summary.vencimentos.em_30_dias} Vencendo</Badge>
          )}
          <Button variant="outline" size="sm" onClick={loadData} disabled={loading}>
            <RefreshCw className={`h-4 w-4 mr-1 ${loading ? 'animate-spin' : ''}`} />
            Atualizar
          </Button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="border-l-4 border-l-emerald-500">
          <CardContent className="pt-4 pb-3">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wide">MRR Total</p>
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))] mt-1">{fmt(summary.mrr_total)}</p>
                <p className="text-xs text-[hsl(var(--muted-foreground))] mt-0.5">Anual: {fmt(summary.mrr_anual)}</p>
              </div>
              <div className="rounded-full bg-emerald-500/10 p-3">
                <DollarSign className="h-6 w-6 text-emerald-500" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-l-4 border-l-blue-500">
          <CardContent className="pt-4 pb-3">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wide">Contratos Ativos</p>
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))] mt-1">{summary.total_ativos}</p>
                <p className="text-xs text-[hsl(var(--muted-foreground))] mt-0.5">Todos condomínios</p>
              </div>
              <div className="rounded-full bg-blue-500/10 p-3">
                <FileText className="h-6 w-6 text-blue-500" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-l-4 border-l-amber-500">
          <CardContent className="pt-4 pb-3">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wide">Com Retenção INSS</p>
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))] mt-1">{summary.retencoes.com_inss}</p>
                <p className="text-xs text-amber-500 mt-0.5">INSS 11%: {fmt(inssRetidoMensal)}/mês</p>
              </div>
              <div className="rounded-full bg-amber-500/10 p-3">
                <Shield className="h-6 w-6 text-amber-500" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-l-4 border-l-violet-500">
          <CardContent className="pt-4 pb-3">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wide">Vencendo em 90d</p>
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))] mt-1">
                  {summary.vencimentos.em_30_dias + summary.vencimentos.em_60_dias + summary.vencimentos.em_90_dias}
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))] mt-0.5">Renovações previstas</p>
              </div>
              <div className="rounded-full bg-violet-500/10 p-3">
                <Calendar className="h-6 w-6 text-violet-500" />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Alertas de Vencimento */}
      {summary.alertas.length > 0 && (
        <Card className="border-amber-500/30 bg-amber-500/5">
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2 text-amber-500">
              <AlertTriangle className="h-4 w-4" />
              Alertas de Vencimento
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {summary.alertas.map(a => (
                <div key={a.contract_number} className="flex items-center justify-between rounded-lg border border-[hsl(var(--border))] p-3">
                  <div className="flex items-center gap-3">
                    <Badge variant={a.severity === 'critical' ? 'destructive' : a.severity === 'high' ? 'destructive' : 'secondary'} className="text-[10px]">
                      {a.severity === 'critical' ? 'VENCIDO' : a.severity === 'high' ? 'URGENTE' : 'ATENÇÃO'}
                    </Badge>
                    <span className="text-sm font-medium">{a.client}</span>
                    <span className="text-xs text-[hsl(var(--muted-foreground))]">{a.contract_number}</span>
                  </div>
                  <span className="text-xs text-[hsl(var(--muted-foreground))]">{a.message}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Tabela de Contratos */}
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base flex items-center gap-2">
              <Building2 className="h-4 w-4 text-blue-500" />
              Contratos Ativos
            </CardTitle>
            <Badge variant="outline" className="text-xs">{contracts.total} contratos</Badge>
          </div>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[80px]">Contrato</TableHead>
                  <TableHead className="cursor-pointer select-none" onClick={() => toggleSort('name')}>
                    Cliente <SortIcon field="name" />
                  </TableHead>
                  <TableHead className="w-[130px]">CNPJ</TableHead>
                  <TableHead>Serviço</TableHead>
                  <TableHead className="text-right cursor-pointer select-none w-[120px]" onClick={() => toggleSort('value')}>
                    Valor Mensal <SortIcon field="value" />
                  </TableHead>
                  <TableHead className="w-[110px]">Retenções</TableHead>
                  <TableHead className="cursor-pointer select-none w-[100px]" onClick={() => toggleSort('end')}>
                    Vigência <SortIcon field="end" />
                  </TableHead>
                  <TableHead className="w-[70px]">Status</TableHead>
                  <TableHead className="w-[100px]">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sorted.map(ct => {
                  const days = ct.end_date ? daysUntil(ct.end_date) : 999;
                  const isExpanded = expandedId === ct.id;
                  return (
                    <>
                      <TableRow key={ct.id} className="cursor-pointer hover:bg-[hsl(var(--muted))]/50" onClick={() => setExpandedId(isExpanded ? null : ct.id)}>
                        <TableCell className="font-mono text-xs">{ct.contract_number}</TableCell>
                        <TableCell className="text-sm font-medium max-w-[180px] truncate" title={ct.client.name}>
                          {shortName(ct.client.name)}
                        </TableCell>
                        <TableCell className="font-mono text-xs">{fmtCnpj(ct.client.cnpj)}</TableCell>
                        <TableCell className="text-xs max-w-[200px] truncate" title={ct.servico}>
                          {ct.servico}
                        </TableCell>
                        <TableCell className="text-right font-mono text-sm font-semibold">{fmt(ct.monthly_value)}</TableCell>
                        <TableCell>
                          <div className="flex gap-1 flex-wrap">
                            {ct.sla_config.retencao_issqn && (
                              <Badge variant="outline" className="text-[9px] px-1 py-0 text-amber-500 border-amber-500/30">ISS</Badge>
                            )}
                            {ct.sla_config.retencao_inss && (
                              <Badge variant="outline" className="text-[9px] px-1 py-0 text-red-500 border-red-500/30">INSS</Badge>
                            )}
                            {ct.sla_config.retencao_pis_cofins_csll && (
                              <Badge variant="outline" className="text-[9px] px-1 py-0 text-violet-500 border-violet-500/30">PIS/COF</Badge>
                            )}
                            {!ct.sla_config.retencao_issqn && !ct.sla_config.retencao_inss && !ct.sla_config.retencao_pis_cofins_csll && (
                              <span className="text-[9px] text-[hsl(var(--muted-foreground))]">Nenhuma</span>
                            )}
                          </div>
                        </TableCell>
                        <TableCell className="text-xs">
                          <div className="flex items-center gap-1">
                            {days <= 30 ? (
                              <Clock className="h-3 w-3 text-red-500" />
                            ) : days <= 90 ? (
                              <Clock className="h-3 w-3 text-amber-500" />
                            ) : (
                              <CheckCircle className="h-3 w-3 text-emerald-500" />
                            )}
                            <span>{ct.end_date ? new Date(ct.end_date).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: '2-digit' }) : '—'}</span>
                          </div>
                          <span className="text-[10px] text-[hsl(var(--muted-foreground))]">{days > 0 ? `${days}d` : 'Vencido'}</span>
                        </TableCell>
                        <TableCell>
                          <Badge
                            className={`text-[10px] ${ct.status === 'ativo' ? 'bg-emerald-500/10 text-emerald-500 border-emerald-500/30' : 'bg-red-500/10 text-red-500 border-red-500/30'}`}
                            variant="outline"
                          >
                            {ct.status}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 text-xs"
                            onClick={(e) => {
                              e.stopPropagation();
                              setRenewTarget(ct);
                              setRenewDialogOpen(true);
                            }}
                          >
                            <RotateCcw className="h-3 w-3 mr-1" />
                            Renovar
                          </Button>
                        </TableCell>
                      </TableRow>

                      {/* Expanded Row */}
                      {isExpanded && (
                        <TableRow key={`${ct.id}-expanded`}>
                          <TableCell colSpan={9} className="bg-[hsl(var(--muted))]/30 p-4">
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                              <div>
                                <p className="text-[10px] uppercase text-[hsl(var(--muted-foreground))] font-medium">Valor Anual</p>
                                <p className="font-semibold">{fmt(ct.total_value)}</p>
                              </div>
                              <div>
                                <p className="text-[10px] uppercase text-[hsl(var(--muted-foreground))] font-medium">Início</p>
                                <p>{ct.start_date ? new Date(ct.start_date).toLocaleDateString('pt-BR') : '—'}</p>
                              </div>
                              <div>
                                <p className="text-[10px] uppercase text-[hsl(var(--muted-foreground))] font-medium">Renovação Auto</p>
                                <p>{ct.auto_renewal ? `Sim (${ct.renewal_period_months}m)` : 'Não'}</p>
                              </div>
                              <div>
                                <p className="text-[10px] uppercase text-[hsl(var(--muted-foreground))] font-medium">Email</p>
                                <p className="truncate text-xs">{ct.client.email || '—'}</p>
                              </div>
                              <div>
                                <p className="text-[10px] uppercase text-[hsl(var(--muted-foreground))] font-medium">Descrição</p>
                                <p className="text-xs">{ct.description || '—'}</p>
                              </div>
                              <div>
                                <p className="text-[10px] uppercase text-[hsl(var(--muted-foreground))] font-medium">Reajuste</p>
                                <p>{ct.adjustment_enabled ? (ct.adjustment_index || 'IPCA') : 'Desabilitado'}</p>
                              </div>
                              <div>
                                <p className="text-[10px] uppercase text-[hsl(var(--muted-foreground))] font-medium">Cidade/UF</p>
                                <p>{ct.client.city}/{ct.client.state}</p>
                              </div>
                              <div>
                                <p className="text-[10px] uppercase text-[hsl(var(--muted-foreground))] font-medium">Tipo</p>
                                <p>{ct.contract_type}</p>
                              </div>
                            </div>
                          </TableCell>
                        </TableRow>
                      )}
                    </>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      {/* Totalizador Fiscal */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <Receipt className="h-4 w-4 text-amber-500" />
            Impacto Fiscal Mensal
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-4">
            <div className="rounded-lg border border-[hsl(var(--border))] p-4 text-center">
              <p className="text-xs text-[hsl(var(--muted-foreground))] uppercase">ISS Retido (5%)</p>
              <p className="font-data text-xl font-semibold tabular-nums text-amber-500 mt-1">{fmt(issRetidoMensal)}</p>
              <p className="text-[10px] text-[hsl(var(--muted-foreground))]">{summary.retencoes.com_issqn} contratos</p>
            </div>
            <div className="rounded-lg border border-[hsl(var(--border))] p-4 text-center">
              <p className="text-xs text-[hsl(var(--muted-foreground))] uppercase">INSS Retido (11%)</p>
              <p className="font-data text-xl font-semibold tabular-nums text-red-500 mt-1">{fmt(inssRetidoMensal)}</p>
              <p className="text-[10px] text-[hsl(var(--muted-foreground))]">{summary.retencoes.com_inss} contratos</p>
            </div>
            <div className="rounded-lg border border-[hsl(var(--border))] p-4 text-center">
              <p className="text-xs text-[hsl(var(--muted-foreground))] uppercase">PIS/COFINS/CSLL</p>
              <p className="font-data text-xl font-semibold tabular-nums text-violet-500 mt-1">{fmt(pisCofinsMensal)}</p>
              <p className="text-[10px] text-[hsl(var(--muted-foreground))]">{summary.retencoes.com_pis_cofins} contratos</p>
            </div>
            <div className="rounded-lg border border-[hsl(var(--border))] p-4 text-center">
              <p className="text-xs text-[hsl(var(--muted-foreground))] uppercase">Total Retenções</p>
              <p className="font-data text-xl font-semibold tabular-nums text-red-400 mt-1">{fmt(totalRetencoes)}</p>
              <p className="text-[10px] text-[hsl(var(--muted-foreground))]">/mês</p>
            </div>
            <div className="rounded-lg border border-emerald-500/30 p-4 text-center bg-emerald-500/5">
              <p className="text-xs text-[hsl(var(--muted-foreground))] uppercase">Receita Líquida</p>
              <p className="font-data text-xl font-semibold tabular-nums text-emerald-500 mt-1">{fmt(summary.mrr_total - totalRetencoes)}</p>
              <p className="text-[10px] text-[hsl(var(--muted-foreground))]">/mês após retenções</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Renewal Dialog */}
      <Dialog open={renewDialogOpen} onOpenChange={setRenewDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Renovar Contrato</DialogTitle>
            <DialogDescription>
              {renewTarget && (
                <span>
                  {renewTarget.contract_number} — {shortName(renewTarget.client.name)}
                  <br />
                  Valor atual: {fmt(renewTarget.monthly_value)}/mês
                </span>
              )}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div>
              <label className="text-sm font-medium">Reajuste (%)</label>
              <Input
                type="number"
                step="0.1"
                value={reajuste}
                onChange={e => setReajuste(e.target.value)}
                placeholder="Ex: 4.5 para IPCA"
                className="mt-1"
              />
              {renewTarget && parseFloat(reajuste) > 0 && (
                <p className="text-xs text-emerald-500 mt-1">
                  Novo valor: {fmt(renewTarget.monthly_value * (1 + parseFloat(reajuste) / 100))}/mês
                </p>
              )}
            </div>
            <div className="text-xs text-[hsl(var(--muted-foreground))]">
              <p>O contrato atual será encerrado e um novo será criado com:</p>
              <ul className="list-disc ml-4 mt-1">
                <li>Início: {renewTarget?.end_date ? new Date(new Date(renewTarget.end_date).getTime() + 86400000).toLocaleDateString('pt-BR') : '—'}</li>
                <li>Vigência: 12 meses</li>
                <li>Mesmas retenções fiscais</li>
              </ul>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRenewDialogOpen(false)}>Cancelar</Button>
            <Button onClick={handleRenew} disabled={renewLoading}>
              {renewLoading ? <RefreshCw className="h-4 w-4 animate-spin mr-1" /> : <ArrowUpRight className="h-4 w-4 mr-1" />}
              Renovar Contrato
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
