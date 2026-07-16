'use client';

/**
 * Fechamento de Ponto (DP) — painel mensal de espelhos de ponto.
 *
 * Lê o que o MOTOR calculou em time_sheets (GET /people-management/hr/ponto/espelho/painel/{mes}/{ano}):
 * status por funcionário (calculado / anomalias / fechado / homologado), botões
 * Calcular mês / Fechar mês (motor) e Enviar p/ homologação, download do espelho PDF
 * por funcionário e o placar de homologação (quantos já assinaram).
 *
 * Gate: module:dp (aplicado no backend pelo people_management + no menu).
 */

import { useState, useEffect, useCallback } from 'react';
import { msgFromDetail } from '@/lib/string';
import { useRouter } from 'next/navigation';
import {
  Clock, ArrowLeft, Loader2, AlertTriangle, CheckCircle2, Calculator,
  Lock, FileSignature, Download, ShieldCheck, Inbox, RefreshCw, ChevronRight,
} from 'lucide-react';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { StatCard } from '@/components/ui/stat-card';

const API_BASE = '/api/v1/people-management';
const HR_PONTO = `${API_BASE}/hr/ponto`;

function authHeaders(): Record<string, string> {
  const token = typeof window !== 'undefined'
    ? (localStorage.getItem('access_token') || localStorage.getItem('token')) : null;
  return { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) };
}

interface Funcionario {
  time_sheet_id: string;
  employee_id: string;
  employee_name: string;
  position_name: string | null;
  condominium_name: string | null;
  status: string | null;
  fechado: boolean;
  horas_trabalhadas: string;
  extras: string;
  adicional_noturno: string;
  faltas_dias: number;
  anomalias_abertas: number;
  homologacao_solicitada: boolean;
  homologado: boolean;
  employee_approved_at: string | null;
}
interface Painel {
  mes: number;
  ano: number;
  resumo: { total: number; calculados: number; com_anomalia: number; fechados: number; homologados: number };
  pode_fechar: boolean;
  funcionarios: Funcionario[];
}

const MESES = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];

function statusBadge(f: Funcionario) {
  if (f.homologado) return <Badge className="bg-emerald-500/10 text-emerald-500 border border-emerald-500/30">Homologado</Badge>;
  if (f.fechado && f.homologacao_solicitada) return <Badge className="bg-cyan-500/10 text-cyan-500 border border-cyan-500/30">Aguardando assinatura</Badge>;
  if (f.fechado) return <Badge className="bg-blue-500/10 text-blue-500 border border-blue-500/30">Fechado</Badge>;
  if (f.anomalias_abertas > 0) return <Badge className="bg-amber-500/10 text-amber-500 border border-amber-500/30">{f.anomalias_abertas} anomalia(s)</Badge>;
  return <Badge className="bg-slate-500/10 text-slate-400 border border-slate-500/30">Calculado</Badge>;
}

export default function FechamentoPontoPage() {
  const router = useRouter();
  const now = new Date();
  const [mes, setMes] = useState(now.getMonth() + 1);
  const [ano, setAno] = useState(now.getFullYear());
  const [painel, setPainel] = useState<Painel | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string>('');

  const carregar = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${HR_PONTO}/espelho/painel/${mes}/${ano}`, { headers: authHeaders() });
      if (!res.ok) throw new Error(String(res.status));
      setPainel(await res.json());
    } catch (err) {
      console.error('painel:', err);
      toast.error('Não foi possível carregar o painel de fechamento.');
      setPainel(null);
    } finally {
      setLoading(false);
    }
  }, [mes, ano]);

  useEffect(() => { carregar(); }, [carregar]);

  // Calcular mês (motor): /fechar-mes com fechar:false = calcula TODOS sem fechar.
  // Tolerante se o motor ainda não estiver disponível.
  const calcularMes = async () => {
    setBusy('calcular');
    try {
      const res = await fetch(`${HR_PONTO}/fechar-mes`, {
        method: 'POST', headers: authHeaders(), body: JSON.stringify({ mes, ano, fechar: false }),
      });
      if (res.status === 404) { toast.warning('Motor de cálculo do ponto ainda não disponível.'); return; }
      if (!res.ok) throw new Error(String(res.status));
      toast.success('Cálculo do mês concluído.');
      await carregar();
    } catch (err) {
      console.error('calcular:', err);
      toast.error('Falha ao calcular o mês.');
    } finally { setBusy(''); }
  };

  // Fechar mês (motor). Só habilita sem anomalia aberta.
  const fecharMes = async () => {
    if (!painel?.pode_fechar) { toast.warning('Resolva as anomalias abertas antes de fechar o mês.'); return; }
    if (!window.confirm(`Fechar o ponto de ${MESES[mes - 1]}/${ano}? Os espelhos ficarão disponíveis para homologação dos funcionários.`)) return;
    setBusy('fechar');
    try {
      const res = await fetch(`${HR_PONTO}/fechar-mes`, {
        method: 'POST', headers: authHeaders(), body: JSON.stringify({ mes, ano }),
      });
      if (res.status === 404) { toast.warning('Motor de fechamento ainda não disponível.'); return; }
      if (!res.ok) throw new Error(String(res.status));
      toast.success('Mês fechado. Envie os espelhos para homologação.');
      await carregar();
    } catch (err) {
      console.error('fechar:', err);
      toast.error('Falha ao fechar o mês.');
    } finally { setBusy(''); }
  };

  // Enviar espelhos fechados para homologação (assinatura do funcionário).
  const enviarHomologacao = async () => {
    setBusy('homologar');
    try {
      const res = await fetch(`${HR_PONTO}/espelho/solicitar-homologacao/${mes}/${ano}`, {
        method: 'POST', headers: authHeaders(),
      });
      if (!res.ok) throw new Error(String(res.status));
      const data = await res.json();
      toast.success(`${data.espelhos_enviados ?? 0} espelho(s) enviados para homologação.`);
      await carregar();
    } catch (err) {
      console.error('homologar:', err);
      toast.error('Falha ao enviar espelhos para homologação.');
    } finally { setBusy(''); }
  };

  const baixarEspelho = async (f: Funcionario) => {
    try {
      const res = await fetch(`${HR_PONTO}/espelho/${f.employee_id}/${mes}/${ano}/pdf`, { headers: authHeaders() });
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        toast.error(msgFromDetail(err?.detail) || 'Espelho ainda não disponível.');
        return;
      }
      const blob = await res.blob();
      window.open(URL.createObjectURL(blob), '_blank');
    } catch (err) {
      console.error('pdf:', err);
      toast.error('Não foi possível abrir o espelho.');
    }
  };

  const r = painel?.resumo;
  const pct = r && r.fechados > 0 ? Math.round((r.homologados / r.fechados) * 100) : 0;

  return (
    <div className="min-h-screen bg-[hsl(var(--background))]">
      <div className="max-w-7xl mx-auto p-4 lg:p-6 space-y-5">
        {/* Header */}
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={() => router.push('/modulos/dp')}>
              <ArrowLeft className="w-4 h-4 mr-1.5" /> DP
            </Button>
            <div className="flex items-center gap-2">
              <Clock className="w-5 h-5 text-[#f97707]" />
              <h1 className="font-display text-lg font-bold">Fechamento de Ponto</h1>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <select value={mes} onChange={(e) => setMes(Number(e.target.value))}
              className="text-sm rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-2 py-1.5">
              {MESES.map((m, i) => <option key={i} value={i + 1}>{m}</option>)}
            </select>
            <select value={ano} onChange={(e) => setAno(Number(e.target.value))}
              className="text-sm rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-2 py-1.5">
              {[now.getFullYear(), now.getFullYear() - 1].map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
            <Button variant="outline" size="sm" onClick={carregar} disabled={loading}>
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </Button>
          </div>
        </div>

        {/* Ações */}
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={calcularMes} disabled={busy !== ''}>
            {busy === 'calcular' ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> : <Calculator className="w-4 h-4 mr-1.5" />}
            Calcular mês
          </Button>
          <Button size="sm" onClick={fecharMes} disabled={busy !== '' || !painel?.pode_fechar}>
            {busy === 'fechar' ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> : <Lock className="w-4 h-4 mr-1.5" />}
            Fechar mês
          </Button>
          <Button size="sm" variant="outline" onClick={enviarHomologacao} disabled={busy !== '' || !r?.fechados}>
            {busy === 'homologar' ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> : <FileSignature className="w-4 h-4 mr-1.5" />}
            Enviar p/ homologação
          </Button>
        </div>

        {/* Placar */}
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
          <StatCard icon={<Clock className="w-4 h-4" />} label="Calculados" value={r?.calculados ?? 0} color="#64748b" />
          <StatCard icon={<AlertTriangle className="w-4 h-4" />} label="Com anomalia" value={r?.com_anomalia ?? 0} color="#f59e0b" />
          <StatCard icon={<Lock className="w-4 h-4" />} label="Fechados" value={r?.fechados ?? 0} color="#3b82f6" />
          <StatCard icon={<ShieldCheck className="w-4 h-4" />} label="Homologados" value={r?.homologados ?? 0} color="#10b981" />
          <StatCard icon={<CheckCircle2 className="w-4 h-4" />} label="Homologação" value={`${pct}%`} color="#f97707" />
        </div>

        {/* Barra de homologação */}
        {r && r.fechados > 0 && (
          <div>
            <div className="flex justify-between text-xs text-[hsl(var(--muted-foreground))] mb-1">
              <span>Espelhos homologados</span>
              <span>{r.homologados}/{r.fechados}</span>
            </div>
            <div className="h-2 w-full rounded-full bg-[hsl(var(--muted))]/40">
              <div className="h-2 rounded-full bg-[#10b981] transition-all" style={{ width: `${pct}%` }} />
            </div>
          </div>
        )}

        {/* Tabela */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <Clock className="w-4 h-4 text-[#f97707]" /> Espelhos de {MESES[mes - 1]}/{ano}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="flex justify-center py-12"><Loader2 className="w-7 h-7 animate-spin text-[#f97707]" /></div>
            ) : !painel || painel.funcionarios.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-14 text-center">
                <Inbox className="w-10 h-10 text-[hsl(var(--muted-foreground))]/40 mb-3" />
                <p className="text-sm font-medium">Nenhum espelho calculado para {MESES[mes - 1]}/{ano}</p>
                <p className="text-xs text-[hsl(var(--muted-foreground))] mt-1 max-w-md">
                  Rode o cálculo do mês no motor de ponto. Assim que os espelhos forem gerados em
                  time_sheets, o status de cada funcionário aparece aqui.
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Funcionário</TableHead>
                      <TableHead>Posto</TableHead>
                      <TableHead className="text-center">Horas</TableHead>
                      <TableHead className="text-center">Extras</TableHead>
                      <TableHead className="text-center">Faltas</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right">Espelho</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {painel.funcionarios.map((f) => (
                      <TableRow key={f.time_sheet_id}>
                        <TableCell>
                          <div className="font-medium text-sm">{f.employee_name}</div>
                          <div className="text-xs text-[hsl(var(--muted-foreground))]">{f.position_name || '—'}</div>
                        </TableCell>
                        <TableCell className="text-xs text-[hsl(var(--muted-foreground))]">{f.condominium_name || '—'}</TableCell>
                        <TableCell className="text-center font-mono text-sm">{f.horas_trabalhadas}</TableCell>
                        <TableCell className="text-center font-mono text-sm">{f.extras}</TableCell>
                        <TableCell className="text-center text-sm">{f.faltas_dias}</TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            {statusBadge(f)}
                            {f.anomalias_abertas > 0 && (
                              <button
                                onClick={() => router.push(`/modulos/dp/ponto?employee=${f.employee_id}&nome=${encodeURIComponent(f.employee_name || '')}&mes=${mes}&ano=${ano}`)}
                                className="text-xs text-amber-500 hover:underline inline-flex items-center gap-0.5"
                              >
                                corrigir <ChevronRight className="w-3 h-3" />
                              </button>
                            )}
                          </div>
                        </TableCell>
                        <TableCell className="text-right">
                          <Button variant="outline" size="sm" onClick={() => baixarEspelho(f)}>
                            <Download className="w-4 h-4 mr-1.5" /> PDF
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>

        <p className="text-[11px] text-[hsl(var(--muted-foreground))]/70">
          Os cálculos vêm do motor de ponto (time_sheets) — este painel não recalcula horas. O botão
          &quot;Fechar mês&quot; só habilita quando não há anomalias abertas. Espelhos fechados vão para a
          aba &quot;Documentos a assinar&quot; do funcionário (Meu Espaço); ao assinar, o espelho é homologado.
        </p>
      </div>
    </div>
  );
}
