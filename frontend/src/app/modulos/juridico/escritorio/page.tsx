'use client';

import { useState, useEffect } from 'react';
import { Scale, PiggyBank, Loader2, TrendingUp, Cpu, Building2, Plus, Info } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Button } from '@/components/ui/button';

const API_BASE = '/api/v1/juridico/escritorio';

function getAuthHeaders() {
  const token = typeof window !== 'undefined' ? (localStorage.getItem('access_token') || localStorage.getItem('token')) : null;
  return { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) };
}
const fmt = (v: number | null | undefined) => (v == null ? '—' : `R$ ${(v || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`);
const pct = (v: number | null | undefined) => (v == null ? '—' : `${(v || 0).toLocaleString('pt-BR', { maximumFractionDigits: 1 })}%`);

const AREAS = ['trabalhista', 'civel', 'tributaria'];

export default function EscritorioRoiPage() {
  const [roi, setRoi] = useState<any>(null);
  const [consultas, setConsultas] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  // form
  const [area, setArea] = useState('trabalhista');
  const [assunto, setAssunto] = useState('');
  const [resolvidoPor, setResolvidoPor] = useState('interno');
  const [custo, setCusto] = useState('');
  const [data, setData] = useState('');
  const [salvando, setSalvando] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  const carregar = async () => {
    setLoading(true);
    setErro(null);
    try {
      const [rRoi, rCons] = await Promise.all([
        fetch(`${API_BASE}/roi`, { headers: getAuthHeaders() }).then((r) => (r.ok ? r.json() : null)),
        fetch(`${API_BASE}/consultas`, { headers: getAuthHeaders() }).then((r) => (r.ok ? r.json() : null)),
      ]);
      if (!rRoi) throw new Error('roi');
      setRoi(rRoi);
      setConsultas((rCons?.consultas as any[]) || []);
    } catch (e: any) {
      setErro('Não foi possível carregar os dados de ROI do escritório.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    carregar();
  }, []);

  const registrar = async () => {
    if (assunto.trim().length < 1) {
      setFeedback('Informe o assunto da demanda.');
      return;
    }
    setSalvando(true);
    setFeedback(null);
    try {
      const body: any = { assunto, area, resolvido_por: resolvidoPor };
      if (custo.trim()) body.custo = Number(custo.replace(',', '.'));
      if (data) body.data = data;
      const r = await fetch(`${API_BASE}/consultas`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify(body),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d?.detail || `HTTP ${r.status}`);
      setFeedback('Demanda registrada.');
      setAssunto('');
      setCusto('');
      setData('');
      await carregar();
    } catch (e: any) {
      setFeedback(`Falha ao registrar demanda: ${e.message}`);
    } finally {
      setSalvando(false);
    }
  };

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="h-6 w-6 animate-spin" /></div>;
  if (erro || !roi) return <div className="p-6 text-sm text-red-600">{erro || 'Sem dados.'}</div>;

  const custoFixo = roi.custo_mensal_fixo || {};
  const serie: any[] = roi.serie_mensal || [];
  const maxSerie = Math.max(1, ...serie.map((s) => Math.max(s.interno || 0, s.escritorio || 0)));

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center gap-3">
        <Scale className="h-7 w-7 text-blue-700" />
        <div>
          <h1 className="font-display text-2xl font-bold text-[hsl(var(--foreground))]">Escritório & ROI</h1>
          <p className="text-sm text-muted-foreground">Internalizar demandas jurídicas via IA vs escritório externo pago.</p>
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <Building2 className="h-5 w-5 text-gray-600" />
            </div>
            <div className="font-data text-2xl font-semibold tabular-nums mt-2">{fmt(custoFixo.valor)}<span className="text-sm text-muted-foreground">/mês</span></div>
            <div className="text-xs text-muted-foreground">Custo fixo do escritório</div>
            {custoFixo.rotulo && (
              <div className="text-[10px] text-amber-600 mt-1 flex items-start gap-1"><Info className="h-3 w-3 mt-0.5 shrink-0" />{custoFixo.rotulo}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <TrendingUp className="h-5 w-5 text-blue-600" />
            <div className="font-data text-2xl font-semibold tabular-nums mt-2">{pct(roi.pct_internalizacao)}</div>
            <div className="text-xs text-muted-foreground">Internalização ({roi.resolvidas_interno}/{roi.total_demandas} demandas)</div>
          </CardContent>
        </Card>

        <Card className="border-green-300 bg-green-50">
          <CardContent className="pt-6">
            <PiggyBank className="h-5 w-5 text-green-600" />
            <div className="font-data text-2xl font-semibold tabular-nums mt-2 text-green-700">{fmt(roi.economia_estimada)}</div>
            <div className="text-xs text-muted-foreground">Economia estimada</div>
            {roi.economia_estimada_metodo && (
              <div className="text-[10px] text-green-700 mt-1">{roi.economia_estimada_metodo}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <Cpu className="h-5 w-5 text-purple-600" />
            <div className="font-data text-2xl font-semibold tabular-nums mt-2">{roi.consultas_ia_internas ?? 0}</div>
            <div className="text-xs text-muted-foreground">Consultas IA internas</div>
            {roi.consultas_ia_nota && <div className="text-[10px] text-muted-foreground mt-1">{roi.consultas_ia_nota}</div>}
          </CardContent>
        </Card>
      </div>

      {/* resumo demandas */}
      <div className="grid grid-cols-3 gap-4">
        <Card><CardContent className="pt-6"><div className="font-data text-2xl font-semibold tabular-nums">{roi.total_demandas ?? 0}</div><div className="text-xs text-muted-foreground">Total de demandas</div></CardContent></Card>
        <Card><CardContent className="pt-6"><div className="font-data text-2xl font-semibold tabular-nums text-blue-600">{roi.resolvidas_interno ?? 0}</div><div className="text-xs text-muted-foreground">Resolvidas internamente</div></CardContent></Card>
        <Card><CardContent className="pt-6"><div className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--muted-foreground))]">{roi.resolvidas_escritorio ?? 0}</div><div className="text-xs text-muted-foreground">Resolvidas pelo escritório {fmt(roi.custo_variavel_escritorio)}</div></CardContent></Card>
      </div>

      {/* Série mensal (mini gráfico de barras) */}
      <Card>
        <CardHeader><CardTitle className="text-base">Série mensal — interno vs escritório</CardTitle></CardHeader>
        <CardContent>
          <div className="flex items-center gap-4 text-xs mb-3">
            <span className="flex items-center gap-1"><span className="inline-block w-3 h-3 rounded-sm bg-blue-500" /> Interno</span>
            <span className="flex items-center gap-1"><span className="inline-block w-3 h-3 rounded-sm bg-gray-400" /> Escritório</span>
          </div>
          <div className="flex items-end gap-4 h-40 border-b">
            {serie.map((s) => (
              <div key={s.mes} className="flex-1 flex flex-col items-center gap-1 justify-end h-full">
                <div className="flex items-end gap-1 h-full w-full justify-center">
                  <div className="w-4 bg-blue-500 rounded-t" style={{ height: `${((s.interno || 0) / maxSerie) * 100}%` }} title={`Interno: ${s.interno}`} />
                  <div className="w-4 bg-gray-400 rounded-t" style={{ height: `${((s.escritorio || 0) / maxSerie) * 100}%` }} title={`Escritório: ${s.escritorio}`} />
                </div>
                <div className="text-[10px] text-muted-foreground">{s.mes?.slice(5)}</div>
              </div>
            ))}
          </div>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Mês</TableHead>
                <TableHead>Interno</TableHead>
                <TableHead>Escritório</TableHead>
                <TableHead>Custo escritório</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {serie.map((s) => (
                <TableRow key={s.mes}>
                  <TableCell>{s.mes}</TableCell>
                  <TableCell>{s.interno ?? 0}</TableCell>
                  <TableCell>{s.escritorio ?? 0}</TableCell>
                  <TableCell>{fmt(s.custo_escritorio)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Form registrar demanda */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2"><Plus className="h-4 w-4 text-blue-600" /> Registrar demanda</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <div>
              <label className="text-sm font-medium">Área</label>
              <select className="mt-1 w-full border rounded-md px-3 py-2 text-sm bg-white capitalize" value={area} onChange={(e) => setArea(e.target.value)}>
                {AREAS.map((a) => <option key={a} value={a}>{a}</option>)}
              </select>
            </div>
            <div>
              <label className="text-sm font-medium">Resolvido por</label>
              <select className="mt-1 w-full border rounded-md px-3 py-2 text-sm bg-white" value={resolvidoPor} onChange={(e) => setResolvidoPor(e.target.value)}>
                <option value="interno">Interno (IA)</option>
                <option value="escritorio">Escritório externo</option>
              </select>
            </div>
            <div>
              <label className="text-sm font-medium">Custo (R$)</label>
              <input type="number" min="0" step="0.01" className="mt-1 w-full border rounded-md px-3 py-2 text-sm" value={custo} onChange={(e) => setCusto(e.target.value)} placeholder="0,00" />
            </div>
            <div className="lg:col-span-2">
              <label className="text-sm font-medium">Assunto</label>
              <input className="mt-1 w-full border rounded-md px-3 py-2 text-sm" value={assunto} onChange={(e) => setAssunto(e.target.value)} placeholder="Ex.: Revisão de cláusula de reajuste" />
            </div>
            <div>
              <label className="text-sm font-medium">Data</label>
              <input type="date" className="mt-1 w-full border rounded-md px-3 py-2 text-sm" value={data} onChange={(e) => setData(e.target.value)} />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button onClick={registrar} disabled={salvando}>
              {salvando ? <><Loader2 className="h-4 w-4 mr-1 animate-spin" /> Salvando…</> : 'Registrar demanda'}
            </Button>
            {feedback && <span className="text-sm text-blue-800">{feedback}</span>}
          </div>
        </CardContent>
      </Card>

      {/* Lista consultas */}
      <Card>
        <CardHeader><CardTitle className="text-base">Demandas registradas ({consultas.length})</CardTitle></CardHeader>
        <CardContent>
          {consultas.length === 0 ? (
            <div className="text-sm text-muted-foreground py-8 text-center">Nenhuma demanda registrada ainda.</div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Assunto</TableHead>
                  <TableHead>Área</TableHead>
                  <TableHead>Resolvido por</TableHead>
                  <TableHead>Custo</TableHead>
                  <TableHead>Data</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {consultas.map((c) => (
                  <TableRow key={c.id}>
                    <TableCell className="font-medium">{c.assunto}</TableCell>
                    <TableCell className="capitalize">{c.area || '—'}</TableCell>
                    <TableCell>
                      {c.resolvido_por === 'interno'
                        ? <Badge className="bg-blue-500 text-white">interno (IA)</Badge>
                        : <Badge className="bg-gray-500 text-white">escritório</Badge>}
                    </TableCell>
                    <TableCell>{fmt(c.custo)}</TableCell>
                    <TableCell className="text-sm">{c.data || (c.created_at ? new Date(c.created_at).toLocaleDateString('pt-BR') : '—')}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Disclaimer */}
      {roi.disclaimer && (
        <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-800">
          <Info className="h-4 w-4 mt-0.5 shrink-0" />
          <span>{roi.disclaimer}</span>
        </div>
      )}
    </div>
  );
}
