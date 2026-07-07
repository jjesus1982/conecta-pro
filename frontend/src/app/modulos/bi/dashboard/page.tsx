'use client';

import { useState, useRef, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  LineChart, Line, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import {
  DollarSign, Users, Building2, Percent, Receipt, FileText, Target,
  AlertTriangle, CheckCircle2, Clock, ChevronUp, ChevronDown, Minus,
  BarChart3, RefreshCw, Download, FileSpreadsheet, Calendar, TrendingUp,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

const API = process.env.NEXT_PUBLIC_API_URL || '';
const MESES = ['', 'Janeiro', 'Fevereiro', 'Marco', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];
const MESES_SHORT = ['', 'Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];

function headers(): Record<string, string> {
  const t = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  return { 'Content-Type': 'application/json', ...(t ? { Authorization: `Bearer ${t}` } : {}) };
}

async function fetchJSON<T>(url: string): Promise<T> {
  const r = await fetch(`${API}${url}`, { headers: headers() });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

// ── Types ──────────────────────────────────────────────────────────────────

interface KPI {
  codigo: string; nome: string; categoria: string; unidade: string;
  valor_atual: number; valor_anterior: number; meta: number;
  variacao_pct: number; tendencia: string;
  historico: Array<{ period: string; value: number }>;
}
interface FiscalItem { tipo: string; nome: string; competencia: string; vencimento: string; valor: number }
interface BiDashboard { kpis: KPI[]; fiscal: { obrigacoes_cumpridas: number; obrigacoes_pendentes: number; proximas: FiscalItem[] } }
interface NfseDashboard {
  totais: { nfse_emitidas: number; clientes_ativos: number; faturamento_bruto: number; iss_total: number; ticket_medio: number };
  por_mes: Array<{ competencia: string; nfse_emitidas: number; faturamento_bruto: number; iss_total: number; faturamento_liquido: number }>;
  por_cliente: Array<{ cliente: string; cnpj: string; nfse_emitidas: number; total_bruto: number; total_iss: number }>;
  por_servico: Array<{ servico: string; quantidade: number; total: number }>;
}
interface HeadcountData {
  total_headcount: number; total_folha_bruta: number;
  por_cliente: Array<{ client_id: string; cliente: string; cnpj: string; headcount: number; folha_bruta: number; contrato_mensal: number }>;
}

// ── Formatters ─────────────────────────────────────────────────────────────

const BRL = (v: number) => v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
const PCT = (v: number) => `${v.toFixed(1)}%`;
const NUM = (v: number) => v.toLocaleString('pt-BR');

const BLUE = '#0A2540';
const BLUE2 = '#1E3A5F';
const ORANGE = '#FF6B35';
const GREEN = '#22C55E';
const RED = '#EF4444';
const YELLOW = '#F59E0B';
const PURPLE = '#8B5CF6';
const CYAN = '#06B6D4';
const PINK = '#EC4899';
const PIE_COLORS = [BLUE, ORANGE, BLUE2, GREEN, PURPLE, CYAN, PINK];

// ── KPI Card ───────────────────────────────────────────────────────────────

function KPICard({ kpi }: { kpi: KPI }) {
  const isUp = kpi.variacao_pct > 0;
  const isDown = kpi.variacao_pct < 0;
  const fmt = (v: number) => kpi.unidade === 'BRL' ? BRL(v) : kpi.unidade === '%' ? PCT(v) : NUM(v);
  const icons: Record<string, React.ReactNode> = {
    MRR: <DollarSign className="h-4 w-4" />, FOLHA: <DollarSign className="h-4 w-4" />,
    MARGEM: <Percent className="h-4 w-4" />, HEADCOUNT: <Users className="h-4 w-4" />,
    CLIENTES: <Building2 className="h-4 w-4" />, TICKET: <Target className="h-4 w-4" />,
    RPF: <TrendingUp className="h-4 w-4" />, CUSTO_FOLHA: <AlertTriangle className="h-4 w-4" />,
    NFSE_COUNT: <FileText className="h-4 w-4" />, ISS_TOTAL: <Receipt className="h-4 w-4" />,
  };
  const inv = kpi.codigo === 'CUSTO_FOLHA' || kpi.codigo === 'FOLHA' || kpi.codigo === 'ISS_TOTAL';
  const tc = inv ? (isUp ? 'text-red-500' : isDown ? 'text-green-500' : 'text-gray-400') : (isUp ? 'text-green-500' : isDown ? 'text-red-500' : 'text-gray-400');

  return (
    <Card className="hover:shadow-md transition-shadow">
      <CardContent className="pt-4 pb-3 px-4">
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide truncate">{kpi.nome}</span>
          <span className="text-muted-foreground">{icons[kpi.codigo] || <BarChart3 className="h-4 w-4" />}</span>
        </div>
        <div className="text-xl font-bold text-gray-900 dark:text-white">{fmt(kpi.valor_atual)}</div>
        <div className="flex items-center gap-1.5 mt-1">
          <span className={`flex items-center text-xs font-medium ${tc}`}>
            {isUp ? <ChevronUp className="h-3 w-3" /> : isDown ? <ChevronDown className="h-3 w-3" /> : <Minus className="h-3 w-3" />}
            {Math.abs(kpi.variacao_pct).toFixed(1)}%
          </span>
          <span className="text-xs text-muted-foreground">vs ant.</span>
        </div>
        {kpi.meta > 0 && (
          <div className="mt-2">
            <div className="flex justify-between text-xs text-muted-foreground mb-0.5">
              <span>Meta: {fmt(kpi.meta)}</span>
              <span>{Math.min(Math.round((kpi.valor_atual / kpi.meta) * 100), 999)}%</span>
            </div>
            <div className="w-full bg-gray-100 dark:bg-gray-800 rounded-full h-1.5">
              <div className="h-1.5 rounded-full transition-all" style={{
                width: `${Math.min((kpi.valor_atual / kpi.meta) * 100, 100)}%`,
                backgroundColor: (kpi.valor_atual / kpi.meta) >= 0.9 ? GREEN : (kpi.valor_atual / kpi.meta) >= 0.7 ? YELLOW : RED,
              }} />
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ── Efficiency Card ────────────────────────────────────────────────────────

function EffCard({ label, value, meta, fmt, inv }: { label: string; value: number; meta: number; fmt: (v: number) => string; inv?: boolean }) {
  const ok = inv ? value / meta <= 1 : value / meta >= 1;
  return (
    <div className={`border rounded-lg p-3 ${ok ? 'border-green-200 bg-green-50 dark:bg-green-950/20' : 'border-yellow-200 bg-yellow-50 dark:bg-yellow-950/20'}`}>
      <div className="text-xs text-muted-foreground mb-0.5">{label}</div>
      <div className="text-lg font-bold">{fmt(value)}</div>
      <div className="flex items-center justify-between mt-1">
        <span className="text-xs text-muted-foreground">Meta: {fmt(meta)}</span>
        {ok
          ? <span className="text-xs font-medium text-green-700 dark:text-green-400 flex items-center gap-0.5"><CheckCircle2 className="h-3 w-3" /> OK</span>
          : <span className="text-xs font-medium text-yellow-700 dark:text-yellow-400 flex items-center gap-0.5"><AlertTriangle className="h-3 w-3" /> Atencao</span>}
      </div>
    </div>
  );
}

// ── Main Page ──────────────────────────────────────────────────────────────

export default function BiDashboardPage() {
  const now = new Date();
  const [tab, setTab] = useState<'overview' | 'fiscal'>('overview');
  const [selMonth, setSelMonth] = useState(now.getMonth() + 1);
  const [selYear, setSelYear] = useState(now.getFullYear());
  const [exporting, setExporting] = useState<'pdf' | 'xlsx' | null>(null);
  const dashRef = useRef<HTMLDivElement>(null);

  const { data: bi, isLoading: biL, refetch } = useQuery<BiDashboard>({
    queryKey: ['bi-dashboard'], queryFn: () => fetchJSON('/api/v1/financial/bi/dashboard'), staleTime: 60_000,
  });
  const { data: nfse, isLoading: nfseL } = useQuery<NfseDashboard>({
    queryKey: ['nfse-dashboard'], queryFn: () => fetchJSON('/api/v1/financial/nfse/dashboard'), staleTime: 60_000,
  });
  const { data: hc } = useQuery<HeadcountData>({
    queryKey: ['headcount'], queryFn: () => fetchJSON('/api/v1/financial/headcount'), staleTime: 60_000,
  });

  const isLoading = biL || nfseL;
  const kpis = bi?.kpis || [];

  // ── Computed data ──────────────────────────────────────────────────────

  const evolucaoData = (() => {
    const mrr = kpis.find(k => k.codigo === 'MRR');
    const fol = kpis.find(k => k.codigo === 'FOLHA');
    if (!mrr) return [];
    const mh = mrr.historico || [];
    const fh = fol?.historico || [];
    const r = mh.map((m, i) => {
      const p = m.period.split('-');
      return {
        label: MESES_SHORT[parseInt(p[1] || '0')] || m.period,
        faturamento: m.value, folha: fh[i]?.value || 0,
        margem: m.value > 0 ? Math.round(((m.value - (fh[i]?.value || 0)) / m.value) * 100) : 0,
      };
    });
    const lastM = mh[mh.length - 1]?.value || 0;
    const lastF = fh[fh.length - 1]?.value || 0;
    r.push({ label: 'Mar*', faturamento: Math.round(lastM * 1.005), folha: lastF, margem: Math.round(((lastM * 1.005 - lastF) / (lastM * 1.005)) * 100) });
    r.push({ label: 'Abr*', faturamento: Math.round(lastM * 1.01), folha: lastF, margem: Math.round(((lastM * 1.01 - lastF) / (lastM * 1.01)) * 100) });
    return r;
  })();

  const servicoData = (nfse?.por_servico || []).map(s => ({
    name: s.servico.replace('Servicos de ', '').replace('Manutencao de ', 'Manut. ')
      .replace('sistema ', '').replace('portaria e servicos gerais', 'Port.+Serv.Gerais')
      .replace('portaria e limpeza', 'Port.+Limpeza').replace('limpeza e jardinagem', 'Limpeza/Jard.')
      .replace('seguranca eletronica', 'Seg.Eletron.').replace('piscina', 'Piscina')
      .replace(/^./, c => c.toUpperCase()),
    value: s.total, qty: s.quantidade,
  }));

  const clienteData = (nfse?.por_cliente || []).map(c => ({
    name: c.cliente.replace('CONDOMINIO ', '').replace('RESIDENCIAL ', '').replace('DO EDIFICIO ', ''),
    value: c.total_bruto, nfse: c.nfse_emitidas,
  }));

  const projecaoAnual = (kpis.find(k => k.codigo === 'MRR')?.valor_atual || 0) * 12;
  const custoFolha = kpis.find(k => k.codigo === 'CUSTO_FOLHA');
  const margem = kpis.find(k => k.codigo === 'MARGEM');
  const ticket = kpis.find(k => k.codigo === 'TICKET');
  const rpf = kpis.find(k => k.codigo === 'RPF');

  // ── Export PDF ─────────────────────────────────────────────────────────

  const exportPDF = useCallback(async () => {
    setExporting('pdf');
    try {
      const { default: jsPDF } = await import('jspdf');
      await import('jspdf-autotable');
      const doc = new jsPDF('landscape', 'mm', 'a4');

      // Header
      doc.setFillColor(10, 37, 64);
      doc.rect(0, 0, 297, 18, 'F');
      doc.setTextColor(255, 255, 255);
      doc.setFontSize(13);
      doc.text('CONECTA PRO — Dashboard Business Intelligence', 10, 12);
      doc.setFontSize(10);
      doc.text(`Periodo: ${MESES[selMonth]}/${selYear}  |  Gerado: ${new Date().toLocaleDateString('pt-BR')}`, 200, 12);

      // KPIs
      let y = 24;
      doc.setTextColor(10, 37, 64);
      doc.setFontSize(11);
      doc.text('Indicadores Executivos', 10, y);
      y += 4;

      const kpiRows = kpis.map(k => {
        const fmt = k.unidade === 'BRL' ? BRL(k.valor_atual) : k.unidade === '%' ? PCT(k.valor_atual) : NUM(k.valor_atual);
        const fmtMeta = k.unidade === 'BRL' ? BRL(k.meta) : k.unidade === '%' ? PCT(k.meta) : NUM(k.meta);
        const delta = `${k.variacao_pct >= 0 ? '+' : ''}${k.variacao_pct.toFixed(1)}%`;
        return [k.nome, fmt, fmtMeta, delta, k.tendencia];
      });

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (doc as any).autoTable({
        startY: y, head: [['KPI', 'Valor Atual', 'Meta', 'Var.%', 'Tendencia']],
        body: kpiRows, theme: 'striped', headStyles: { fillColor: [10, 37, 64] },
        styles: { fontSize: 8 }, margin: { left: 10, right: 10 },
      });

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      y = ((doc as any).lastAutoTable?.finalY || y + 40) + 8;

      // Clientes
      doc.setFontSize(11);
      doc.text('Faturamento por Cliente', 10, y);
      y += 4;

      const cliRows = (nfse?.por_cliente || []).map(c => [
        c.cliente, c.cnpj, String(c.nfse_emitidas), BRL(c.total_bruto), BRL(c.total_iss),
      ]);

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (doc as any).autoTable({
        startY: y, head: [['Cliente', 'CNPJ', 'NFS-e', 'Faturamento', 'ISS']],
        body: cliRows, theme: 'striped', headStyles: { fillColor: [10, 37, 64] },
        styles: { fontSize: 7 }, margin: { left: 10, right: 10 },
      });

      // Fiscal (page 2)
      if (bi?.fiscal.proximas && bi.fiscal.proximas.length > 0) {
        doc.addPage();
        doc.setFillColor(10, 37, 64);
        doc.rect(0, 0, 297, 18, 'F');
        doc.setTextColor(255, 255, 255);
        doc.setFontSize(13);
        doc.text('CONECTA PRO — Obrigacoes Fiscais', 10, 12);

        doc.setTextColor(10, 37, 64);
        doc.setFontSize(11);
        doc.text(`Cumpridas: ${bi.fiscal.obrigacoes_cumpridas}  |  Pendentes: ${bi.fiscal.obrigacoes_pendentes}`, 10, 26);

        const fiscRows = bi.fiscal.proximas.map(o => [
          o.tipo, o.nome, o.competencia,
          new Date(o.vencimento).toLocaleDateString('pt-BR'),
          o.valor > 0 ? BRL(o.valor) : '—',
        ]);

        // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (doc as any).autoTable({
          startY: 32, head: [['Tipo', 'Obrigacao', 'Comp.', 'Vencimento', 'Valor']],
          body: fiscRows, theme: 'striped', headStyles: { fillColor: [10, 37, 64] },
          styles: { fontSize: 8 }, margin: { left: 10, right: 10 },
        });
      }

      doc.save(`BI_Dashboard_${selYear}_${String(selMonth).padStart(2, '0')}.pdf`);
    } catch (e) {
      console.error('Export PDF error:', e);
    } finally {
      setExporting(null);
    }
  }, [kpis, nfse, bi, selMonth, selYear]);

  // ── Export Excel ───────────────────────────────────────────────────────

  const exportExcel = useCallback(async () => {
    setExporting('xlsx');
    try {
      const XLSX = await import('xlsx');
      const wb = XLSX.utils.book_new();

      // KPIs sheet
      const kpiData = [['KPI', 'Categoria', 'Valor Atual', 'Valor Anterior', 'Meta', 'Variacao %', 'Tendencia']];
      kpis.forEach(k => kpiData.push([k.nome, k.categoria, String(k.valor_atual), String(k.valor_anterior), String(k.meta), String(k.variacao_pct), k.tendencia]));
      XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(kpiData), 'KPIs');

      // Clientes sheet
      const cliData = [['Cliente', 'CNPJ', 'NFS-e', 'Faturamento Bruto', 'ISS']];
      (nfse?.por_cliente || []).forEach(c => cliData.push([c.cliente, c.cnpj, String(c.nfse_emitidas), String(c.total_bruto), String(c.total_iss)]));
      XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(cliData), 'Por Cliente');

      // Servicos sheet
      const svcData = [['Servico', 'Quantidade', 'Total']];
      (nfse?.por_servico || []).forEach(s => svcData.push([s.servico, String(s.quantidade), String(s.total)]));
      XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(svcData), 'Por Servico');

      // Headcount sheet
      if (hc) {
        const hcData = [['Cliente', 'Headcount', 'Folha Bruta', 'Contrato Mensal']];
        hc.por_cliente.forEach(c => hcData.push([c.cliente, String(c.headcount), String(c.folha_bruta), String(c.contrato_mensal)]));
        hcData.push(['TOTAL', String(hc.total_headcount), String(hc.total_folha_bruta), '']);
        XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(hcData), 'Headcount');
      }

      // Fiscal sheet
      if (bi?.fiscal.proximas) {
        const fData = [['Tipo', 'Obrigacao', 'Competência', 'Vencimento', 'Valor']];
        bi.fiscal.proximas.forEach(o => fData.push([o.tipo, o.nome, o.competencia, o.vencimento, String(o.valor)]));
        XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(fData), 'Fiscal');
      }

      XLSX.writeFile(wb, `BI_Conecta_${selYear}_${String(selMonth).padStart(2, '0')}.xlsx`);
    } catch (e) {
      console.error('Export Excel error:', e);
    } finally {
      setExporting(null);
    }
  }, [kpis, nfse, hc, bi, selMonth, selYear]);

  // ── Render ─────────────────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-8 bg-gray-200 dark:bg-gray-800 rounded w-64" />
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          {Array.from({ length: 10 }).map((_, i) => <div key={i} className="h-28 bg-gray-200 dark:bg-gray-800 rounded-lg" />)}
        </div>
        <div className="h-80 bg-gray-200 dark:bg-gray-800 rounded-lg" />
      </div>
    );
  }

  return (
    <div className="space-y-6" ref={dashRef}>
      {/* Header + Filters + Export */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <BarChart3 className="h-6 w-6" style={{ color: BLUE }} />
            Business Intelligence
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">Conecta Mais — Indicadores Executivos</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {/* Period filter */}
          <div className="flex items-center gap-1 bg-gray-100 dark:bg-gray-800 rounded-lg px-2 py-1">
            <Calendar className="h-4 w-4 text-muted-foreground" />
            <select value={selMonth} onChange={e => setSelMonth(Number(e.target.value))}
              className="bg-transparent text-sm font-medium outline-none cursor-pointer pr-1">
              {MESES.map((m, i) => i > 0 && <option key={i} value={i}>{m}</option>)}
            </select>
            <select value={selYear} onChange={e => setSelYear(Number(e.target.value))}
              className="bg-transparent text-sm font-medium outline-none cursor-pointer">
              <option value={2025}>2025</option>
              <option value={2026}>2026</option>
              <option value={2027}>2027</option>
            </select>
          </div>

          {/* Tabs */}
          <div className="flex bg-gray-100 dark:bg-gray-800 rounded-lg p-0.5">
            <button onClick={() => setTab('overview')} className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${tab === 'overview' ? 'bg-white dark:bg-gray-700 shadow-sm' : 'text-muted-foreground'}`}>Geral</button>
            <button onClick={() => setTab('fiscal')} className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${tab === 'fiscal' ? 'bg-white dark:bg-gray-700 shadow-sm' : 'text-muted-foreground'}`}>Fiscal</button>
          </div>

          {/* Actions */}
          <Button variant="outline" size="sm" onClick={exportPDF} disabled={exporting === 'pdf'}>
            <Download className="h-4 w-4 mr-1" /> {exporting === 'pdf' ? 'Gerando...' : 'PDF'}
          </Button>
          <Button variant="outline" size="sm" onClick={exportExcel} disabled={exporting === 'xlsx'} className="text-green-700 border-green-300 hover:bg-green-50">
            <FileSpreadsheet className="h-4 w-4 mr-1" /> {exporting === 'xlsx' ? 'Gerando...' : 'Excel'}
          </Button>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Period indicator */}
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Calendar className="h-4 w-4" />
        <span>Exibindo dados de <strong className="text-foreground">{MESES[selMonth]} {selYear}</strong></span>
        {selMonth <= 2 && selYear === 2026 && <span className="px-2 py-0.5 rounded-full bg-green-100 text-green-700 text-xs font-medium">Dados reais</span>}
        {(selMonth > 2 || selYear !== 2026) && <span className="px-2 py-0.5 rounded-full bg-gray-100 text-gray-500 text-xs font-medium">Sem dados NFS-e</span>}
      </div>

      {tab === 'overview' ? (
        <>
          {/* KPI Cards */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            {kpis.map(k => <KPICard key={k.codigo} kpi={k} />)}
          </div>

          {/* Charts row */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <Card className="lg:col-span-2">
              <CardHeader className="pb-2"><CardTitle className="text-base">Evolucao Mensal (* = projecao)</CardTitle></CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart data={evolucaoData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                    <XAxis dataKey="label" tick={{ fontSize: 12 }} />
                    <YAxis tick={{ fontSize: 11 }} tickFormatter={(v: number) => `${(v / 1000).toFixed(0)}k`} />
                    <Tooltip formatter={(value) => BRL(Number(value))} />
                    <Legend />
                    <Line type="monotone" dataKey="faturamento" name="Faturamento" stroke={BLUE} strokeWidth={2.5} dot={{ r: 4 }} />
                    <Line type="monotone" dataKey="folha" name="Folha" stroke={ORANGE} strokeWidth={2} dot={{ r: 3 }} strokeDasharray="5 5" />
                  </LineChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-base">Receita por Servico</CardTitle></CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={300}>
                  <PieChart>
                    <Pie data={servicoData} cx="50%" cy="50%" innerRadius={50} outerRadius={90} paddingAngle={2} dataKey="value" label={false}>
                      {servicoData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                    </Pie>
                    <Tooltip formatter={(value) => BRL(Number(value))} />
                    <Legend formatter={(value: string) => <span className="text-xs">{value}</span>} />
                  </PieChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </div>

          {/* Bar chart */}
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-base">Faturamento por Cliente (acumulado)</CardTitle></CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={Math.max(300, clienteData.length * 36)}>
                <BarChart data={clienteData} layout="vertical" margin={{ left: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis type="number" tick={{ fontSize: 11 }} tickFormatter={(v: number) => `${(v / 1000).toFixed(0)}k`} />
                  <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={180} />
                  <Tooltip formatter={(value) => BRL(Number(value))} />
                  <Bar dataKey="value" name="Faturamento" fill={BLUE} radius={[0, 4, 4, 0]} barSize={20} />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Efficiency */}
          <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
            <EffCard label="Margem Bruta" value={margem?.valor_atual || 0} meta={60} fmt={PCT} />
            <EffCard label="Custo Folha / Fat." value={custoFolha?.valor_atual || 0} meta={40} fmt={PCT} inv />
            <EffCard label="Ticket Medio" value={ticket?.valor_atual || 0} meta={20000} fmt={BRL} />
            <EffCard label="Receita / Func." value={rpf?.valor_atual || 0} meta={4000} fmt={BRL} />
            <div className="border border-blue-200 bg-blue-50 dark:bg-blue-950/20 rounded-lg p-3">
              <div className="text-xs text-muted-foreground mb-0.5">Projecao Anual</div>
              <div className="text-lg font-bold text-blue-700 dark:text-blue-400">{BRL(projecaoAnual)}</div>
              <div className="text-xs text-muted-foreground mt-1">MRR x 12</div>
            </div>
          </div>

          {/* Headcount table */}
          {hc && hc.por_cliente.length > 0 && (
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-base">Headcount por Cliente</CardTitle></CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead><tr className="border-b bg-muted/50">
                      <th className="text-left p-2 font-medium">Cliente</th>
                      <th className="text-right p-2 font-medium">HC</th>
                      <th className="text-right p-2 font-medium">Folha</th>
                      <th className="text-right p-2 font-medium">Contrato</th>
                      <th className="text-right p-2 font-medium">%F/C</th>
                    </tr></thead>
                    <tbody>
                      {hc.por_cliente.map((c, i) => {
                        const p = c.contrato_mensal > 0 ? c.folha_bruta / c.contrato_mensal * 100 : 0;
                        return (<tr key={i} className="border-b hover:bg-muted/30">
                          <td className="p-2 font-medium">{c.cliente}</td>
                          <td className="p-2 text-right">{c.headcount}</td>
                          <td className="p-2 text-right">{BRL(c.folha_bruta)}</td>
                          <td className="p-2 text-right">{c.contrato_mensal > 0 ? BRL(c.contrato_mensal) : '—'}</td>
                          <td className="p-2 text-right">{p > 0 ? <span className={p > 50 ? 'text-yellow-600' : 'text-green-600'}>{p.toFixed(1)}%</span> : '—'}</td>
                        </tr>);
                      })}
                    </tbody>
                    <tfoot><tr className="border-t-2 font-bold">
                      <td className="p-2">Total</td>
                      <td className="p-2 text-right">{hc.total_headcount}</td>
                      <td className="p-2 text-right">{BRL(hc.total_folha_bruta)}</td>
                      <td className="p-2 text-right" colSpan={2} />
                    </tr></tfoot>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}
        </>
      ) : (
        /* Fiscal tab */
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Card className="border-green-200 bg-green-50/50 dark:bg-green-950/10">
              <CardContent className="pt-4">
                <div className="flex items-center gap-2 mb-1"><CheckCircle2 className="h-5 w-5 text-green-600" /><span className="text-sm font-medium">Cumpridas</span></div>
                <div className="font-data text-3xl font-semibold tabular-nums text-green-700">{bi?.fiscal.obrigacoes_cumpridas || 0}</div>
              </CardContent>
            </Card>
            <Card className="border-yellow-200 bg-yellow-50/50 dark:bg-yellow-950/10">
              <CardContent className="pt-4">
                <div className="flex items-center gap-2 mb-1"><Clock className="h-5 w-5 text-yellow-600" /><span className="text-sm font-medium">Pendentes</span></div>
                <div className="font-data text-3xl font-semibold tabular-nums text-yellow-700">{bi?.fiscal.obrigacoes_pendentes || 0}</div>
              </CardContent>
            </Card>
            <Card className="border-blue-200 bg-blue-50/50 dark:bg-blue-950/10">
              <CardContent className="pt-4">
                <div className="flex items-center gap-2 mb-1"><Receipt className="h-5 w-5 text-blue-600" /><span className="text-sm font-medium">Total a Recolher</span></div>
                <div className="font-data text-3xl font-semibold tabular-nums text-blue-700">{BRL((bi?.fiscal.proximas || []).reduce((a, o) => a + o.valor, 0))}</div>
              </CardContent>
            </Card>
          </div>
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-base">Obrigacoes Fiscais Pendentes</CardTitle></CardHeader>
            <CardContent>
              <table className="w-full text-sm">
                <thead><tr className="border-b bg-muted/50">
                  <th className="text-left p-2 font-medium">Tipo</th>
                  <th className="text-left p-2 font-medium">Obrigacao</th>
                  <th className="text-left p-2 font-medium">Comp.</th>
                  <th className="text-left p-2 font-medium">Vencimento</th>
                  <th className="text-right p-2 font-medium">Valor</th>
                  <th className="text-center p-2 font-medium">Prazo</th>
                </tr></thead>
                <tbody>
                  {(bi?.fiscal.proximas || []).map((o, i) => {
                    const d = Math.ceil((new Date(o.vencimento).getTime() - Date.now()) / 86400000);
                    const sc = d < 0 ? 'bg-red-100 text-red-700' : d <= 7 ? 'bg-yellow-100 text-yellow-700' : 'bg-green-100 text-green-700';
                    return (<tr key={i} className="border-b hover:bg-muted/30">
                      <td className="p-2"><span className="px-2 py-0.5 rounded text-xs font-medium bg-gray-100 dark:bg-gray-800">{o.tipo}</span></td>
                      <td className="p-2 font-medium">{o.nome}</td>
                      <td className="p-2">{o.competencia}</td>
                      <td className="p-2">{new Date(o.vencimento).toLocaleDateString('pt-BR')}</td>
                      <td className="p-2 text-right font-mono">{o.valor > 0 ? BRL(o.valor) : '—'}</td>
                      <td className="p-2 text-center"><span className={`px-2 py-0.5 rounded-full text-xs font-medium ${sc}`}>{d < 0 ? 'Vencida' : `${d}d`}</span></td>
                    </tr>);
                  })}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
