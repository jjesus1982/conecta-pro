'use client';

import { useState, useEffect, useCallback } from 'react';
import { Receipt, Building2, RefreshCw, FileText, Download, Landmark } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { api } from '@/lib/api';
import { abrirPdf } from '@/lib/pdf';

const fmt = (v: number) => (Number(v) || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
const MESES = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];

const CAT_LABEL: Record<string, string> = {
  contabilidade: 'Contabilidade', advocacia: 'Advocacia', seg_trabalho: 'Seg. Trabalho',
  tecnologia: 'Tecnologia', beneficios: 'Benefícios', seg_eletronica: 'Seg. Eletrônica',
  manutencao: 'Manutenção', material: 'Material', pj: 'Prestador PJ', outros: 'Outros',
};
const EMP_LABEL: Record<string, string> = {
  conecta_eletronica: 'Eletrônica', conecta_patrimonial: 'Patrimonial',
};

interface Nota {
  chave_acesso: string; numero: string; competencia: string; data_emissao: string;
  prestador_nome: string; prestador_cnpj: string; valor_servicos: number; iss_valor: number;
  descricao: string; empresa: string; categoria: string; tem_xml: boolean;
}

export default function NotasRecebidasPage() {
  const [ano, setAno] = useState('2026');
  const [mes, setMes] = useState('all');
  const [empresa, setEmpresa] = useState('all');
  const [categoria, setCategoria] = useState('all');
  const [notas, setNotas] = useState<Nota[]>([]);
  const [porCat, setPorCat] = useState<Record<string, { qtd: number; total: number }>>({});
  const [total, setTotal] = useState(0);
  const [totalValor, setTotalValor] = useState(0);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const p = new URLSearchParams({ ano });
      if (mes !== 'all') p.set('competencia', `${ano}-${mes.padStart(2, '0')}`);
      if (empresa !== 'all') p.set('empresa', empresa);
      if (categoria !== 'all') p.set('categoria', categoria);
      const res = await api.get(`/api/v1/financial/nfse-entrada?${p.toString()}`);
      setNotas(res.data?.nfse_entrada ?? []);
      setTotal(res.data?.total ?? 0);
      setTotalValor(res.data?.total_valor_bruto ?? 0);
      setPorCat(res.data?.por_categoria ?? {});
    } catch { /* silent */ }
    finally { setLoading(false); }
  }, [ano, mes, empresa, categoria]);

  useEffect(() => { loadData(); }, [loadData]);

  const cats = Object.entries(porCat).sort((a, b) => b[1].total - a[1].total);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="font-display text-2xl font-semibold flex items-center gap-2">
            <Receipt className="h-6 w-6" /> Notas Recebidas
          </h1>
          <p className="text-muted-foreground text-sm">Notas fiscais emitidas contra os 2 CNPJs do Grupo — serviços e materiais</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <Select value={empresa} onValueChange={setEmpresa}>
            <SelectTrigger className="w-[130px]"><SelectValue placeholder="Empresa" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Ambos CNPJs</SelectItem>
              <SelectItem value="conecta_eletronica">Eletrônica</SelectItem>
              <SelectItem value="conecta_patrimonial">Patrimonial</SelectItem>
            </SelectContent>
          </Select>
          <Select value={categoria} onValueChange={setCategoria}>
            <SelectTrigger className="w-[150px]"><SelectValue placeholder="Categoria" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todas categorias</SelectItem>
              {Object.entries(CAT_LABEL).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={ano} onValueChange={setAno}><SelectTrigger className="w-[88px]"><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="2025">2025</SelectItem><SelectItem value="2026">2026</SelectItem></SelectContent>
          </Select>
          <Select value={mes} onValueChange={setMes}><SelectTrigger className="w-[110px]"><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="all">Todos</SelectItem>{MESES.map((m, i) => <SelectItem key={i} value={String(i + 1)}>{m}</SelectItem>)}</SelectContent>
          </Select>
          <Button variant="outline" size="sm" onClick={loadData} disabled={loading}><RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} /></Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid gap-4 sm:grid-cols-3">
        <Card><CardContent className="pt-4"><p className="text-xs text-muted-foreground">Total recebido</p><p className="font-data text-2xl font-semibold tabular-nums">{fmt(totalValor)}</p></CardContent></Card>
        <Card><CardContent className="pt-4"><p className="text-xs text-muted-foreground">Notas</p><p className="font-data text-2xl font-semibold tabular-nums">{total}</p></CardContent></Card>
        <Card><CardContent className="pt-4"><p className="text-xs text-muted-foreground">Categorias</p><p className="font-data text-2xl font-semibold tabular-nums">{cats.length}</p></CardContent></Card>
      </div>

      {/* Resumo por categoria (clicável = filtra) */}
      {cats.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {cats.map(([c, v]) => (
            <button key={c} onClick={() => setCategoria(categoria === c ? 'all' : c)}
              className={`rounded-lg border px-3 py-1.5 text-left text-xs ${categoria === c ? 'border-primary bg-primary/5' : 'hover:bg-muted/40'}`}>
              <span className="font-medium">{CAT_LABEL[c] ?? c}</span> · {v.qtd} · <span className="tabular-nums">{fmt(v.total)}</span>
            </button>
          ))}
        </div>
      )}

      {/* Tabela */}
      <Card><CardContent className="p-0 overflow-x-auto">
        <table className="w-full text-sm">
          <thead><tr className="border-b bg-muted/50">
            <th className="text-left p-3 font-medium">Fornecedor</th>
            <th className="text-left p-3 font-medium">CNPJ</th>
            <th className="text-left p-3 font-medium">Data</th>
            <th className="text-left p-3 font-medium">Empresa</th>
            <th className="text-left p-3 font-medium">Categoria</th>
            <th className="text-right p-3 font-medium">Valor</th>
            <th className="text-right p-3 font-medium">Nota</th>
          </tr></thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} className="p-8 text-center text-muted-foreground">Carregando...</td></tr>
            ) : notas.length === 0 ? (
              <tr><td colSpan={7} className="p-8 text-center text-muted-foreground">Nenhuma nota recebida no filtro.</td></tr>
            ) : notas.map((nf) => (
              <tr key={nf.chave_acesso} className="border-b hover:bg-muted/30">
                <td className="p-3 font-medium max-w-[240px] truncate" title={nf.prestador_nome}>{nf.prestador_nome}</td>
                <td className="p-3 text-muted-foreground text-xs">{nf.prestador_cnpj}</td>
                <td className="p-3 whitespace-nowrap">{nf.data_emissao ? new Date(nf.data_emissao).toLocaleDateString('pt-BR') : nf.competencia}</td>
                <td className="p-3"><span className="inline-flex items-center gap-1 text-xs"><Landmark className="h-3 w-3 text-muted-foreground" />{EMP_LABEL[nf.empresa] ?? nf.empresa}</span></td>
                <td className="p-3"><Badge variant="secondary" className="text-xs">{CAT_LABEL[nf.categoria] ?? nf.categoria}</Badge></td>
                <td className="p-3 text-right font-medium tabular-nums">{fmt(nf.valor_servicos)}</td>
                <td className="p-3 text-right whitespace-nowrap">
                  <Button variant="ghost" size="sm" title="Ver PDF" onClick={() => abrirPdf(`/api/v1/financial/nfse-entrada/${nf.chave_acesso}/pdf`)}><FileText className="h-4 w-4" /></Button>
                  <Button variant="ghost" size="sm" title="Baixar PDF" onClick={() => abrirPdf(`/api/v1/financial/nfse-entrada/${nf.chave_acesso}/pdf`, { download: true, nome: `nfse-${nf.prestador_nome?.split(' ')[0]}-${nf.numero}.pdf` })}><Download className="h-4 w-4" /></Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent></Card>
    </div>
  );
}
