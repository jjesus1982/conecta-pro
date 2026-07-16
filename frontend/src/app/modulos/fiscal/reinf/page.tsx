'use client';

import { RefreshCw, AlertCircle, FileCode, Eye, Plus, Send, Clock, Loader2, Filter } from 'lucide-react';
import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { PageHeader } from '@/components/ui/page-header';
import { StatCard } from '@/components/ui/stat-card';
import { ReinfDetailModal } from '@/components/fiscal/reinf-detail-modal';
import {
  useGerarR1000,
  useGerarR2010,
  useGerarR2099,
  useGerarR4010,
  useGerarR4020,
  useImportarReinf,
} from '@/hooks/government';
import { cn } from '@/lib/utils';

interface ReinfEvento {
  id: string;
  tipo_evento: string;
  competencia: string;
  status: string;
  data_envio?: string;
  protocolo?: string;
}

const statusConfig: Record<string, { label: string; color: string }> = {
  pendente: { label: 'Pendente', color: 'bg-yellow-100 text-yellow-800' },
  enviado: { label: 'Enviado', color: 'bg-blue-100 text-blue-800' },
  aceito: { label: 'Aceito', color: 'bg-green-100 text-green-800' },
  rejeitado: { label: 'Rejeitado', color: 'bg-red-100 text-red-800' },
  erro: { label: 'Erro', color: 'bg-red-100 text-red-800' },
};

const tipoEventos = [
  { value: '', label: 'Todos' },
  { value: 'R-1000', label: 'R-1000' },
  { value: 'R-2010', label: 'R-2010' },
  { value: 'R-2099', label: 'R-2099' },
  { value: 'R-4010', label: 'R-4010' },
  { value: 'R-4020', label: 'R-4020' },
];

const tipoEventoLabels: Record<string, string> = {
  'R-1000': 'Informações do Contribuinte',
  'R-2010': 'Retencao Contribuicao Previdenciaria',
  'R-2099': 'Fechamento dos Eventos Periodicos',
  'R-4010': 'Pagamentos/Creditos a PF',
  'R-4020': 'Pagamentos/Creditos a PJ',
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

export default function ReinfPage() {
  const [tipoFilter, setTipoFilter] = useState('');
  // init ESTÁVEL (igual no SSR e na hidratação — evita React #418); sincroniza no mount
  const [mesSelecionado, setMesSelecionado] = useState('01');
  const [anoSelecionado, setAnoSelecionado] = useState(currentYear);
  useEffect(() => {
    setMesSelecionado(String(new Date().getMonth() + 1).padStart(2, '0'));
    setAnoSelecionado(new Date().getFullYear());
  }, []);
  const [page, setPage] = useState(1);
  const [selectedEvento, setSelectedEvento] = useState<any | null>(null);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [eventos, setEventos] = useState<ReinfEvento[]>([]);

  const gerarR1000Mutation = useGerarR1000();
  const gerarR2010Mutation = useGerarR2010();
  const gerarR2099Mutation = useGerarR2099();
  const gerarR4010Mutation = useGerarR4010();
  const gerarR4020Mutation = useGerarR4020();
  const importarMutation = useImportarReinf();

  const competenciaAtual = `${mesSelecionado}/${anoSelecionado}`;

  const filteredEventos = eventos.filter((e) => {
    const matchTipo = tipoFilter ? e.tipo_evento === tipoFilter : true;
    const matchCompetencia = e.competencia === competenciaAtual;
    return matchTipo && matchCompetencia;
  });

  const totalEventos = filteredEventos.length;
  const pendentes = filteredEventos.filter((e) => e.status === 'pendente').length;
  const enviados = filteredEventos.filter((e) => e.status === 'enviado' || e.status === 'aceito').length;

  const formatDate = (dateStr: string | null | undefined) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const addEvento = (tipo: string) => {
    const newEvento: ReinfEvento = {
      id: `${tipo}-${Date.now()}`,
      tipo_evento: tipo,
      competencia: competenciaAtual,
      status: 'pendente',
    };
    setEventos((prev) => [newEvento, ...prev]);
  };

  const handleGerarR1000 = () => {
    gerarR1000Mutation.mutate({} as any, {
      onSuccess: () => addEvento('R-1000'),
    });
  };

  const handleGerarR2010 = () => {
    gerarR2010Mutation.mutate({} as any, {
      onSuccess: () => addEvento('R-2010'),
    });
  };

  const handleGerarR2099 = () => {
    gerarR2099Mutation.mutate({} as any, {
      onSuccess: () => addEvento('R-2099'),
    });
  };

  const handleGerarR4010 = () => {
    gerarR4010Mutation.mutate({} as any, {
      onSuccess: () => addEvento('R-4010'),
    });
  };

  const handleGerarR4020 = () => {
    gerarR4020Mutation.mutate({} as any, {
      onSuccess: () => addEvento('R-4020'),
    });
  };

  const isAnyLoading =
    gerarR1000Mutation.isPending ||
    gerarR2010Mutation.isPending ||
    gerarR2099Mutation.isPending ||
    gerarR4010Mutation.isPending ||
    gerarR4020Mutation.isPending;

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <PageHeader
        eyebrow="FISCAL"
        title="EFD-Reinf"
        subtitle="Escrituracao Fiscal Digital de Retencoes e Informações"
        icon={<FileCode className="h-5 w-5" />}
      />

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard
          label="Total Eventos"
          value={totalEventos}
          icon={<FileCode className="w-5 h-5" />}
          color="#06b6d4"
        />
        <StatCard
          label="Pendentes"
          value={pendentes}
          icon={<Clock className="w-5 h-5" />}
          color="#eab308"
        />
        <StatCard
          label="Enviados"
          value={enviados}
          icon={<Send className="w-5 h-5" />}
          color="#22c55e"
        />
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center">
        <div className="flex gap-2">
          <div>
            <label className="block text-xs text-[hsl(var(--muted-foreground))] mb-1">Tipo</label>
            <select
              value={tipoFilter}
              onChange={(e) => setTipoFilter(e.target.value)}
              className="px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))] text-sm"
            >
              {tipoEventos.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-[hsl(var(--muted-foreground))] mb-1">Mes</label>
            <select
              value={mesSelecionado}
              onChange={(e) => setMesSelecionado(e.target.value)}
              className="px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))] text-sm"
            >
              {meses.map((m) => (
                <option key={m.value} value={m.value}>{m.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-[hsl(var(--muted-foreground))] mb-1">Ano</label>
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

        <div className="flex gap-2 flex-wrap sm:ml-auto">
          <Button
            variant="secondary"
            size="sm"
            onClick={handleGerarR1000}
            disabled={gerarR1000Mutation.isPending}
          >
            {gerarR1000Mutation.isPending ? (
              <Loader2 className="w-3 h-3 mr-1 animate-spin" />
            ) : (
              <Plus className="w-3 h-3 mr-1" />
            )}
            R-1000
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleGerarR2010}
            disabled={gerarR2010Mutation.isPending}
          >
            {gerarR2010Mutation.isPending ? (
              <Loader2 className="w-3 h-3 mr-1 animate-spin" />
            ) : (
              <Plus className="w-3 h-3 mr-1" />
            )}
            R-2010
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleGerarR2099}
            disabled={gerarR2099Mutation.isPending}
          >
            {gerarR2099Mutation.isPending ? (
              <Loader2 className="w-3 h-3 mr-1 animate-spin" />
            ) : (
              <Plus className="w-3 h-3 mr-1" />
            )}
            R-2099
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleGerarR4010}
            disabled={gerarR4010Mutation.isPending}
          >
            {gerarR4010Mutation.isPending ? (
              <Loader2 className="w-3 h-3 mr-1 animate-spin" />
            ) : (
              <Plus className="w-3 h-3 mr-1" />
            )}
            R-4010
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleGerarR4020}
            disabled={gerarR4020Mutation.isPending}
          >
            {gerarR4020Mutation.isPending ? (
              <Loader2 className="w-3 h-3 mr-1 animate-spin" />
            ) : (
              <Plus className="w-3 h-3 mr-1" />
            )}
            R-4020
          </Button>
        </div>
      </div>

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          {filteredEventos.length === 0 ? (
            <div className="text-center py-12">
              <FileCode className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
              <h3 className="text-lg font-medium text-[hsl(var(--foreground))]">
                Nenhum evento encontrado
              </h3>
              <p className="text-[hsl(var(--muted-foreground))] mt-1">
                Use os botoes acima para gerar eventos EFD-Reinf
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-[hsl(var(--border))]">
                    <th className="text-left p-4 text-sm font-medium text-[hsl(var(--muted-foreground))]">
                      Tipo Evento
                    </th>
                    <th className="text-left p-4 text-sm font-medium text-[hsl(var(--muted-foreground))]">
                      Competência
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
                  {filteredEventos.map((evento) => {
                    const st = statusConfig[evento.status] || statusConfig.pendente || { label: 'Pendente', color: 'bg-yellow-100 text-yellow-800' };
                    return (
                      <tr
                        key={evento.id}
                        className="hover:bg-[hsl(var(--secondary))]/50 transition-colors"
                      >
                        <td className="p-4">
                          <div>
                            <p className="font-medium text-[hsl(var(--foreground))]">
                              {evento.tipo_evento}
                            </p>
                            <p className="text-xs text-[hsl(var(--muted-foreground))]">
                              {tipoEventoLabels[evento.tipo_evento] || ''}
                            </p>
                          </div>
                        </td>
                        <td className="p-4">
                          <span className="text-sm text-[hsl(var(--foreground))]">
                            {evento.competencia}
                          </span>
                        </td>
                        <td className="p-4">
                          <span className={cn('inline-flex px-2 py-1 text-xs font-medium rounded-full', st.color)}>
                            {st.label}
                          </span>
                        </td>
                        <td className="p-4 hidden md:table-cell">
                          <span className="text-sm text-[hsl(var(--muted-foreground))]">
                            {formatDate(evento.data_envio)}
                          </span>
                        </td>
                        <td className="p-4">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => {
                              setSelectedEvento(evento);
                              setShowDetailModal(true);
                            }}
                            title="Ver detalhes"
                          >
                            <Eye className="w-4 h-4" />
                          </Button>
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

      {/* Pagination info */}
      {filteredEventos.length > 0 && (
        <div className="text-sm text-[hsl(var(--muted-foreground))] text-center">
          Mostrando {filteredEventos.length} eventos
        </div>
      )}

      {/* Detail Modal */}
      <ReinfDetailModal
        isOpen={showDetailModal}
        onClose={() => {
          setShowDetailModal(false);
          setSelectedEvento(null);
        }}
        evento={selectedEvento}
      />
    </div>
  );
}
