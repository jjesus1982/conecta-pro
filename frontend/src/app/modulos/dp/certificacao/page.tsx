'use client';

import { useState, useEffect, useCallback } from 'react';
import { ShieldCheck, ArrowLeft, Inbox, Loader2, Check, X, AlertTriangle, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { useRouter } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';

const API_BASE = '/api/v1/people-management';

function getAuthHeaders() {
  const token = typeof window !== 'undefined' ? (localStorage.getItem('access_token') || localStorage.getItem('token')) : null;
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

const fmt = (v: number | null) => (v == null ? '—' : `R$ ${(v || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`);

const statusBadge: Record<string, { label: string; className: string }> = {
  pendente: { label: 'Pendente', className: 'bg-yellow-500 text-white' },
  certificado: { label: 'Certificado', className: 'bg-green-600 text-white' },
  rejeitado: { label: 'Rejeitado', className: 'bg-red-500 text-white' },
};

interface Cert {
  id: string;
  tipo_calculo: string;
  referencia_id: string | null;
  competencia: string | null;
  calculado_valor: number | null;
  esperado_valor: number | null;
  divergencia: boolean;
  divergencia_desc: string | null;
  status: string;
  certificado_por: string | null;
  certificado_em: string | null;
  observacao: string | null;
  valida: boolean | null;
}

export default function CertificacaoPage() {
  const router = useRouter();
  const [certs, setCerts] = useState<Cert[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>('pendente');
  const [acting, setActing] = useState<string | null>(null);

  const fetchCerts = useCallback(async () => {
    setLoading(true);
    try {
      const q = filter ? `?status=${filter}` : '';
      const res = await fetch(`${API_BASE}/certifications${q}`, { headers: getAuthHeaders() });
      const data = res.ok ? await res.json() : [];
      setCerts(Array.isArray(data) ? data : []);
    } catch {
      setCerts([]);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { fetchCerts(); }, [fetchCerts]);

  const certificar = async (id: string) => {
    setActing(id);
    try {
      const res = await fetch(`${API_BASE}/certifications/${id}/certify`, {
        method: 'PATCH', headers: getAuthHeaders(), body: JSON.stringify({ observacao: 'Conferido e certificado' }),
      });
      if (!res.ok) throw new Error();
      toast.success('Cálculo certificado — assinatura registrada');
      fetchCerts();
    } catch { toast.error('Falha ao certificar'); } finally { setActing(null); }
  };

  const rejeitar = async (id: string) => {
    const motivo = window.prompt('Motivo da rejeição (obrigatório):');
    if (!motivo) return;
    setActing(id);
    try {
      const res = await fetch(`${API_BASE}/certifications/${id}/reject`, {
        method: 'PATCH', headers: getAuthHeaders(), body: JSON.stringify({ observacao: motivo }),
      });
      if (!res.ok) throw new Error();
      toast.success('Cálculo rejeitado');
      fetchCerts();
    } catch { toast.error('Falha ao rejeitar'); } finally { setActing(null); }
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={() => router.back()}><ArrowLeft className="h-4 w-4" /></Button>
        <ShieldCheck className="h-6 w-6 text-green-600" />
        <div>
          <h1 className="text-2xl font-bold">Certificação Humana</h1>
          <p className="text-sm text-muted-foreground">O trabalho humano de conferir e certificar — nada de risco jurídico vai a produção sem sua assinatura.</p>
        </div>
        <Button variant="outline" size="sm" className="ml-auto" onClick={fetchCerts}><RefreshCw className="h-4 w-4 mr-1" />Atualizar</Button>
      </div>

      <div className="flex gap-2">
        {['pendente', 'certificado', 'rejeitado', ''].map((s) => (
          <Button key={s || 'todos'} size="sm" variant={filter === s ? 'default' : 'outline'} onClick={() => setFilter(s)}>
            {s ? statusBadge[s]?.label : 'Todos'}
          </Button>
        ))}
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">Fila de conferência</CardTitle></CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex justify-center py-10"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
          ) : certs.length === 0 ? (
            <div className="flex flex-col items-center py-10 text-muted-foreground"><Inbox className="h-8 w-8 mb-2" />Nada nesta fila</div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Tipo</TableHead><TableHead>Competência</TableHead>
                  <TableHead>Calculado</TableHead><TableHead>Esperado (Domínio)</TableHead>
                  <TableHead>Status</TableHead><TableHead>Válida</TableHead><TableHead className="text-right">Ação</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {certs.map((c) => (
                  <TableRow key={c.id}>
                    <TableCell className="font-medium">{c.tipo_calculo}{c.divergencia && <AlertTriangle className="inline h-4 w-4 text-amber-500 ml-1" />}</TableCell>
                    <TableCell>{c.competencia || '—'}</TableCell>
                    <TableCell>{fmt(c.calculado_valor)}</TableCell>
                    <TableCell className={c.divergencia ? 'text-amber-600 font-semibold' : ''}>{fmt(c.esperado_valor)}</TableCell>
                    <TableCell><Badge className={statusBadge[c.status]?.className}>{statusBadge[c.status]?.label || c.status}</Badge></TableCell>
                    <TableCell>
                      {c.status === 'certificado' && (c.valida
                        ? <Badge className="bg-green-600 text-white">Válida</Badge>
                        : <Badge className="bg-red-500 text-white" title="O cálculo mudou após a assinatura — expirou">Expirada</Badge>)}
                    </TableCell>
                    <TableCell className="text-right">
                      {c.status === 'pendente' && (
                        <div className="flex gap-2 justify-end">
                          <Button size="sm" className="bg-green-600 hover:bg-green-700" disabled={acting === c.id} onClick={() => certificar(c.id)}>
                            {acting === c.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <><Check className="h-4 w-4 mr-1" />Certificar</>}
                          </Button>
                          <Button size="sm" variant="destructive" disabled={acting === c.id} onClick={() => rejeitar(c.id)}><X className="h-4 w-4 mr-1" />Rejeitar</Button>
                        </div>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
