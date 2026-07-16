'use client';

import { RefreshCw, AlertCircle, FileSpreadsheet, Eye, DollarSign, Clock, Send, Loader2, FileText } from 'lucide-react';
import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { PageHeader } from '@/components/ui/page-header';
import { StatCard } from '@/components/ui/stat-card';
import { DctfwebDetailModal } from '@/components/fiscal/dctfweb-detail-modal';
import {
  useEmitirDPS,
  useGerarGuiaMensal,
} from '@/hooks/government';
import { cn } from '@/lib/utils';

interface Declaracao {
  id: string;
  competencia: string;
  tipo: string;
  valor: number;
  status: string;
  data_envio?: string;
}

const statusConfig: Record<string, { label: string; color: string }> = {
  pendente: { label: 'Pendente', color: 'bg-yellow-100 text-yellow-800' },
  enviada: { label: 'Enviada', color: 'bg-green-100 text-green-800' },
  retificada: { label: 'Retificada', color: 'bg-blue-100 text-blue-800' },
  erro: { label: 'Erro', color: 'bg-red-100 text-red-800' },
};

const meses = [
  { value: '01', label: 'Janeiro' },
  { value: '02', label: 'Fevereiro' },
  { value: '03', label: 'Marco' },
  { value: '04', label: 'Abril' },
  { value: '05', label: 'Maio' },
  { value: '06', label: 'Junho' },
  { value: '07', label: 'Julho' },
  { value: '08', label: 'Agosto' },
  { value: '09', label: 'Setembro' },
  { value: '10', label: 'Outubro' },
  { value: '11', label: 'Novembro' },
  { value: '12', label: 'Dezembro' },
];

const currentYear = new Date().getFullYear();
const anos = Array.from({ length: 5 }, (_, i) => currentYear - i);

export default function DctfwebPage() {
  // init ESTÁVEL (igual no SSR e na hidratação — evita React #418); sincroniza no mount
  const [mesSelecionado, setMesSelecionado] = useState('01');
  const [anoSelecionado, setAnoSelecionado] = useState(currentYear);
  useEffect(() => {
    setMesSelecionado(String(new Date().getMonth() + 1).padStart(2, '0'));
    setAnoSelecionado(new Date().getFullYear());
  }, []);
  const [page, setPage] = useState(1);
  const [selectedDeclaracao, setSelectedDeclaracao] = useState<any | null>(null);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [declaracoes, setDeclaracoes] = useState<Declaracao[]>([]);

  const emitirDPSMutation = useEmitirDPS();
  const gerarGuiaMutation = useGerarGuiaMensal();

  const competenciaAtual = `${mesSelecionado}/${anoSelecionado}`;
  const filteredDeclaracoes = declaracoes.filter(
    (d) => d.competencia === competenciaAtual
  );

  const totalDeclaracoes = filteredDeclaracoes.length;
  const pendentes = filteredDeclaracoes.filter((d) => d.status === 'pendente').length;
  const enviadas = filteredDeclaracoes.filter((d) => d.status === 'enviada').length;

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL',
    }).format(value);
  };

  const formatDate = (dateStr: string | null | undefined) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    });
  };

  // Busca a guia REAL da competência (fiscal_obligations via /financial/relatorios/guias-do-mes).
  // O endpoint /government/fgts/calcular é uma calculadora UNITÁRIA (exige salario_base
  // individual) — usá-lo aqui dava 422 sempre e nunca traria o valor real da folha.
  const [buscandoGuia, setBuscandoGuia] = useState<string | null>(null);
  const buscarGuiaReal = async (orgao: 'FGTS' | 'INSS') => {
    setBuscandoGuia(orgao);
    try {
      const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
      const res = await fetch(
        `/api/v1/financial/relatorios/guias-do-mes?competencia=${encodeURIComponent(competenciaAtual)}`,
        { headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) } }
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const guia = (data?.guias || []).find((g: any) => (g.orgao || '').toUpperCase() === orgao);
      if (!guia) {
        const { toast } = await import('sonner');
        toast.info(`${orgao} da competência ${competenciaAtual} ainda sem valor apurado no sistema.`, { duration: 5000 });
        return;
      }
      const newDecl: Declaracao = {
        id: `${orgao.toLowerCase()}-${Date.now()}`,
        competencia: competenciaAtual,
        tipo: orgao,
        valor: Number(guia.valor) || 0,
        status: guia.status === 'pago' ? 'enviada' : 'pendente',
      };
      setDeclaracoes((prev) => [newDecl, ...prev.filter((d) => !(d.tipo === orgao && d.competencia === competenciaAtual))]);
    } catch {
      const { toast } = await import('sonner');
      toast.error(`Erro ao buscar guia ${orgao} da competência.`, { duration: 5000 });
    } finally {
      setBuscandoGuia(null);
    }
  };

  const handleCalcularFGTS = () => buscarGuiaReal('FGTS');

  const handleCalcularINSS = () => buscarGuiaReal('INSS');

  const handleGerarGuia = (declaracao: Declaracao) => {
    gerarGuiaMutation.mutate(
      {
        mes_referencia: mesSelecionado,
        ano_referencia: anoSelecionado,
      },
      {
        onSuccess: () => {
          setDeclaracoes((prev) =>
            prev.map((d) =>
              d.id === declaracao.id
                ? { ...d, status: 'enviada', data_envio: new Date().toISOString() }
                : d
            )
          );
        },
      }
    );
  };

  const isAnyLoading =
    buscandoGuia !== null ||
    emitirDPSMutation.isPending ||
    gerarGuiaMutation.isPending;

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <PageHeader
        eyebrow="FISCAL"
        title="DCTFWeb"
        subtitle="Declaracao de Debitos e Creditos Tributarios Federais"
        icon={<FileSpreadsheet className="h-5 w-5" />}
      />

      {/* Period Selector */}
      <div className="flex items-center gap-4 p-4 bg-[hsl(var(--muted))] rounded-lg">
        <div>
          <label className="block text-xs text-[hsl(var(--muted-foreground))] mb-1">Competência</label>
          <div className="flex gap-2">
            <select
              value={mesSelecionado}
              onChange={(e) => setMesSelecionado(e.target.value)}
              className="px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))] text-sm"
            >
              {meses.map((m) => (
                <option key={m.value} value={m.value}>{m.label}</option>
              ))}
            </select>
            <select
              value={anoSelecionado}
              onChange={(e) => setAnoSelecionado(Number(e.target.value))}
              className="px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))] text-sm"
            >
              {anos.map((a) => (
                <option key={a} value={a}>{a}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="flex gap-2 ml-auto">
          <Button
            variant="secondary"
            size="sm"
            onClick={handleCalcularFGTS}
            disabled={buscandoGuia === 'FGTS'}
          >
            {buscandoGuia === 'FGTS' ? (
              <Loader2 className="w-4 h-4 mr-1 animate-spin" />
            ) : (
              <DollarSign className="w-4 h-4 mr-1" />
            )}
            Calcular FGTS
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleCalcularINSS}
            disabled={buscandoGuia === 'INSS'}
          >
            {buscandoGuia === 'INSS' ? (
              <Loader2 className="w-4 h-4 mr-1 animate-spin" />
            ) : (
              <DollarSign className="w-4 h-4 mr-1" />
            )}
            Calcular INSS
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard
          label="Declaracoes"
          value={totalDeclaracoes}
          icon={<FileSpreadsheet className="w-5 h-5" />}
          color="#3b82f6"
        />
        <StatCard
          label="Pendentes"
          value={pendentes}
          icon={<Clock className="w-5 h-5" />}
          color="#eab308"
        />
        <StatCard
          label="Enviadas"
          value={enviadas}
          icon={<Send className="w-5 h-5" />}
          color="#22c55e"
        />
      </div>

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          {filteredDeclaracoes.length === 0 ? (
            <div className="text-center py-12">
              <FileSpreadsheet className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
              <h3 className="text-lg font-medium text-[hsl(var(--foreground))]">
                Nenhuma declaracao encontrada
              </h3>
              <p className="text-[hsl(var(--muted-foreground))] mt-1">
                Use os botoes acima para calcular FGTS ou INSS
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-[hsl(var(--border))]">
                    <th className="text-left p-4 text-sm font-medium text-[hsl(var(--muted-foreground))]">
                      Competência
                    </th>
                    <th className="text-left p-4 text-sm font-medium text-[hsl(var(--muted-foreground))]">
                      Tipo
                    </th>
                    <th className="text-right p-4 text-sm font-medium text-[hsl(var(--muted-foreground))]">
                      Valor
                    </th>
                    <th className="text-left p-4 text-sm font-medium text-[hsl(var(--muted-foreground))]">
                      Status
                    </th>
                    <th className="text-left p-4 text-sm font-medium text-[hsl(var(--muted-foreground))] hidden md:table-cell">
                      Data
                    </th>
                    <th className="w-24 p-4 text-sm font-medium text-[hsl(var(--muted-foreground))]">
                      Ações
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[hsl(var(--border))]">
                  {filteredDeclaracoes.map((declaracao) => {
                    const st = statusConfig[declaracao.status] || statusConfig.pendente || { label: 'Pendente', color: 'bg-yellow-100 text-yellow-800' };
                    return (
                      <tr
                        key={declaracao.id}
                        className="hover:bg-[hsl(var(--secondary))]/50 transition-colors"
                      >
                        <td className="p-4">
                          <span className="text-sm text-[hsl(var(--foreground))]">
                            {declaracao.competencia}
                          </span>
                        </td>
                        <td className="p-4">
                          <span className="font-medium text-[hsl(var(--foreground))]">
                            {declaracao.tipo}
                          </span>
                        </td>
                        <td className="p-4 text-right">
                          <span className="font-mono text-sm text-[hsl(var(--foreground))]">
                            {formatCurrency(declaracao.valor)}
                          </span>
                        </td>
                        <td className="p-4">
                          <span className={cn('inline-flex px-2 py-1 text-xs font-medium rounded-full', st.color)}>
                            {st.label}
                          </span>
                        </td>
                        <td className="p-4 hidden md:table-cell">
                          <span className="text-sm text-[hsl(var(--muted-foreground))]">
                            {formatDate(declaracao.data_envio)}
                          </span>
                        </td>
                        <td className="p-4">
                          <div className="flex items-center gap-1">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => {
                                setSelectedDeclaracao(declaracao);
                                setShowDetailModal(true);
                              }}
                              title="Ver detalhes"
                            >
                              <Eye className="w-4 h-4" />
                            </Button>
                            {declaracao.status === 'pendente' && (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleGerarGuia(declaracao)}
                                disabled={gerarGuiaMutation.isPending}
                                title="Gerar Guia"
                              >
                                <FileText className="w-4 h-4 text-green-500" />
                              </Button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Detail Modal */}
      <DctfwebDetailModal
        isOpen={showDetailModal}
        onClose={() => {
          setShowDetailModal(false);
          setSelectedDeclaracao(null);
        }}
        declaracao={selectedDeclaracao}
      />
    </div>
  );
}
