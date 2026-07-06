'use client';

import { useState, useEffect, useCallback } from 'react';
import { FileText, Receipt, Building2, AlertTriangle, RefreshCw } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { api } from '@/lib/api';

const fmt = (v: number) => v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
const MESES = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];

interface NfseEntrada {
  id: string;
  prestador_nome: string;
  prestador_cnpj: string;
  descricao_servico: string;
  data_emissao: string;
  valor_servico: number;
  valor_liquido: number;
  categoria: string;
  status: string;
}

interface Resumo {
  total_despesas_documentadas: number;
  fornecedores: number;
  detalhes: Array<{ prestador_nome: string; total_bruto: number; qtd: number; categoria: string }>;
  aviso: string;
}

export default function NfseEntradaPage() {
  const [ano, setAno] = useState('2026');
  const [mes, setMes] = useState('all');
  const [notas, setNotas] = useState<NfseEntrada[]>([]);
  const [resumo, setResumo] = useState<Resumo | null>(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const compParam = mes !== 'all' ? `&competencia=${ano}-${mes.padStart(2, '0')}` : '';
      const mesParam = mes !== 'all' ? `&mes=${mes}` : '';
      const [notasRes, resumoRes] = await Promise.all([
        api.get(`/api/v1/financial/nfse-entrada?ano=${ano}${compParam}`),
        api.get(`/api/v1/financial/nfse-entrada/resumo-fiscal?ano=${ano}${mesParam}`),
      ]);
      setNotas(notasRes.data?.nfse_entrada ?? []);
      setTotal(notasRes.data?.total ?? 0);
      setResumo(resumoRes.data);
    } catch { /* silent */ }
    finally { setLoading(false); }
  }, [ano, mes]);

  useEffect(() => { loadData(); }, [loadData]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-semibold flex items-center gap-2">
            <Receipt className="h-6 w-6" />
            NFS-e de Entrada — Compras com Nota
          </h1>
          <p className="text-muted-foreground text-sm">
            Notas fiscais de fornecedores — obrigatorio para Lucro Real
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={ano} onValueChange={setAno} aria-label="Ano">
            <SelectTrigger className="w-[90px]"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="2025">2025</SelectItem>
              <SelectItem value="2026">2026</SelectItem>
            </SelectContent>
          </Select>
          <Select value={mes} onValueChange={setMes} aria-label="Mes">
            <SelectTrigger className="w-[120px]"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos</SelectItem>
              {MESES.map((m, i) => <SelectItem key={i} value={String(i + 1)}>{m}</SelectItem>)}
            </SelectContent>
          </Select>
          <Button variant="outline" size="sm" onClick={loadData} disabled={loading}>
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card><CardContent className="pt-4">
          <p className="text-xs text-muted-foreground">Despesas Documentadas</p>
          <p className="font-data text-2xl font-semibold tabular-nums">{fmt(resumo?.total_despesas_documentadas ?? 0)}</p>
        </CardContent></Card>
        <Card><CardContent className="pt-4">
          <p className="text-xs text-muted-foreground">Notas Recebidas</p>
          <p className="font-data text-2xl font-semibold tabular-nums">{total}</p>
        </CardContent></Card>
        <Card><CardContent className="pt-4">
          <p className="text-xs text-muted-foreground">Fornecedores</p>
          <p className="font-data text-2xl font-semibold tabular-nums">{resumo?.fornecedores ?? 0}</p>
        </CardContent></Card>
      </div>

      {/* Aviso fiscal */}
      <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 flex items-center gap-2">
        <AlertTriangle className="h-4 w-4 text-amber-600 flex-shrink-0" />
        <p className="text-sm text-amber-800">{resumo?.aviso ?? 'Lucro Real: toda despesa deve ter NFS-e vinculada'}</p>
      </div>

      {/* Fornecedores resumo */}
      {resumo?.detalhes && resumo.detalhes.length > 0 && (
        <div className="grid gap-3 md:grid-cols-3">
          {resumo.detalhes.map((f) => (
            <Card key={f.prestador_nome}>
              <CardContent className="pt-4">
                <div className="flex items-center gap-2 mb-1">
                  <Building2 className="h-4 w-4 text-muted-foreground" />
                  <span className="font-medium text-sm truncate">{f.prestador_nome}</span>
                </div>
                <p className="text-lg font-bold">{fmt(Number(f.total_bruto))}</p>
                <p className="text-xs text-muted-foreground">{f.qtd} notas — {f.categoria}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Tabela */}
      <Card>
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="text-left p-3 font-medium">Fornecedor</th>
                <th className="text-left p-3 font-medium">Descricao</th>
                <th className="text-left p-3 font-medium">Data</th>
                <th className="text-right p-3 font-medium">Valor</th>
                <th className="text-left p-3 font-medium">Categoria</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={5} className="p-8 text-center text-muted-foreground">Carregando...</td></tr>
              ) : notas.length === 0 ? (
                <tr><td colSpan={5} className="p-8 text-center text-muted-foreground">Nenhuma NFS-e de entrada</td></tr>
              ) : notas.map((nf) => (
                <tr key={nf.id} className="border-b hover:bg-muted/30">
                  <td className="p-3 font-medium">{nf.prestador_nome}</td>
                  <td className="p-3 text-muted-foreground truncate max-w-[200px]">{nf.descricao_servico}</td>
                  <td className="p-3">{new Date(nf.data_emissao).toLocaleDateString('pt-BR')}</td>
                  <td className="p-3 text-right font-medium">{fmt(Number(nf.valor_servico))}</td>
                  <td className="p-3"><Badge variant="secondary" className="text-xs">{nf.categoria}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}
