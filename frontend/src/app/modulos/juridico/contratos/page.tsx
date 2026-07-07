'use client';

import { useState, useEffect } from 'react';
import { Scale, FileText, AlertTriangle, RefreshCw, TrendingUp, PenLine, Clock, Loader2 } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';

const API_BASE = '/api/v1/juridico/contratos';

function getAuthHeaders() {
  const token = typeof window !== 'undefined' ? (localStorage.getItem('access_token') || localStorage.getItem('token')) : null;
  return { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) };
}
const fmt = (v: number | null) => (v == null ? '—' : `R$ ${(v || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`);

export default function CentralContratosPage() {
  const router = useRouter();
  const [dash, setDash] = useState<any>(null);
  const [contratos, setContratos] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const [d, l] = await Promise.all([
          fetch(`${API_BASE}/dashboard`, { headers: getAuthHeaders() }).then((r) => r.json()).catch(() => null),
          fetch(`${API_BASE}`, { headers: getAuthHeaders() }).then((r) => r.json()).catch(() => null),
        ]);
        setDash(d);
        setContratos((l?.contratos as any[]) || []);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const kpis = dash
    ? [
        { label: 'Contratos ativos', value: dash.contratos_ativos, icon: FileText, color: 'text-blue-600' },
        { label: 'Valor mensal', value: fmt(dash.valor_mensal_ativo), icon: TrendingUp, color: 'text-green-600' },
        { label: 'Vencendo em 90d', value: dash.vencendo_90d, icon: Clock, color: 'text-yellow-600' },
        { label: 'Renovações pendentes', value: dash.renovacoes_pendentes, icon: RefreshCw, color: 'text-orange-600' },
        { label: 'Reajustes próximos', value: dash.reajustes_proximos, icon: TrendingUp, color: 'text-purple-600' },
        { label: 'Assinaturas pendentes', value: dash.assinaturas_pendentes, icon: PenLine, color: 'text-red-600' },
      ]
    : [];

  const badgeVenc = (c: any) => {
    if (c.vencido) return <Badge className="bg-red-600 text-white">Vencido</Badge>;
    if (c.vencimento_nivel === 'critico') return <Badge className="bg-red-500 text-white">{c.dias_para_vencer}d</Badge>;
    if (c.vencimento_nivel === 'atencao') return <Badge className="bg-yellow-500 text-white">{c.dias_para_vencer}d</Badge>;
    if (c.vencimento_nivel === 'proximo') return <Badge className="bg-blue-400 text-white">{c.dias_para_vencer}d</Badge>;
    return <span className="text-muted-foreground text-sm">{c.dias_para_vencer != null ? `${c.dias_para_vencer}d` : '—'}</span>;
  };

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="h-6 w-6 animate-spin" /></div>;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center gap-3">
        <Scale className="h-7 w-7 text-blue-700" />
        <div>
          <h1 className="font-display text-2xl font-bold text-[hsl(var(--foreground))]">Central de Contratos</h1>
          <p className="text-sm text-muted-foreground">Jurídico — visão consolidada e alertas (referência: {dash?.referencia})</p>
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        {kpis.map((k) => (
          <Card key={k.label}>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <k.icon className={`h-5 w-5 ${k.color}`} />
              </div>
              <div className="font-data text-2xl font-semibold tabular-nums mt-2">{k.value ?? 0}</div>
              <div className="text-xs text-muted-foreground">{k.label}</div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Alertas */}
      {dash?.alertas?.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <AlertTriangle className="h-4 w-4 text-orange-500" /> Alertas ({dash.alertas.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {dash.alertas.map((a: any) => (
              <div key={a.id} className="flex items-center justify-between border rounded-md px-3 py-2 text-sm">
                <div>
                  <span className="font-medium">{a.numero}</span> · {a.cliente}
                </div>
                <div className="flex items-center gap-2">
                  {a.motivos.map((m: string, i: number) => (
                    <Badge key={i} variant="outline" className={a.prioridade === 'critica' ? 'border-red-400 text-red-600' : ''}>{m}</Badge>
                  ))}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Tabela */}
      <Card>
        <CardHeader><CardTitle className="text-base">Contratos ({contratos.length})</CardTitle></CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Nº</TableHead>
                <TableHead>Cliente</TableHead>
                <TableHead>Serviço</TableHead>
                <TableHead>Valor/mês</TableHead>
                <TableHead>Vigência</TableHead>
                <TableHead>Vence em</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Alertas</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {contratos.map((c) => (
                <TableRow key={c.id} className="cursor-pointer" onClick={() => router.push(`/modulos/crm/contratos`)}>
                  <TableCell className="font-medium">{c.numero}</TableCell>
                  <TableCell>{c.cliente}</TableCell>
                  <TableCell className="text-sm">{c.tipo_servico || c.tipo || '—'}</TableCell>
                  <TableCell>{fmt(c.valor_mensal)}</TableCell>
                  <TableCell className="text-sm">{c.inicio} → {c.fim}</TableCell>
                  <TableCell>{badgeVenc(c)}</TableCell>
                  <TableCell><Badge className={c.status === 'active' ? 'bg-green-500 text-white' : 'bg-gray-400 text-white'}>{c.status}</Badge></TableCell>
                  <TableCell>
                    <div className="flex gap-1 flex-wrap">
                      {c.renovacao_pendente && <Badge variant="outline" className="text-orange-600">renov.</Badge>}
                      {c.reajuste_pendente && <Badge variant="outline" className="text-purple-600">reajuste</Badge>}
                      {c.assinatura_pendente && <Badge variant="outline" className="text-red-600">assinar</Badge>}
                      {!c.tem_alerta && <span className="text-muted-foreground text-xs">ok</span>}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
