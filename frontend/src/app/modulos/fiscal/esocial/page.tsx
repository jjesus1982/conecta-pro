'use client';

import { Search, RefreshCw, AlertCircle, Users, Eye, Send, CheckSquare, Filter, Clock, XCircle } from 'lucide-react';
import { useState } from 'react';
;
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { PageHeader } from '@/components/ui/page-header';
import { StatCard } from '@/components/ui/stat-card';
import { EsocialDetailModal } from '@/components/fiscal/esocial-detail-modal';
import { useListarEventos, useEnviarEvento, useValidarEvento } from '@/hooks/government';
import { cn } from '@/lib/utils';

const statusConfig: Record<string, { label: string; color: string }> = {
  pendente: { label: 'Pendente', color: 'bg-yellow-100 text-yellow-800' },
  enviado: { label: 'Enviado', color: 'bg-blue-100 text-blue-800' },
  aceito: { label: 'Aceito', color: 'bg-green-100 text-green-800' },
  rejeitado: { label: 'Rejeitado', color: 'bg-red-100 text-red-800' },
  erro: { label: 'Erro', color: 'bg-red-100 text-red-800' },
};

const tipoEventos = [
  { value: '', label: 'Todos os Tipos' },
  { value: 'S-1000', label: 'S-1000 - Empregador' },
  { value: 'S-1010', label: 'S-1010 - Rubricas' },
  { value: 'S-1200', label: 'S-1200 - Remuneracao' },
  { value: 'S-1210', label: 'S-1210 - Pagamentos' },
  { value: 'S-2200', label: 'S-2200 - Admissão' },
  { value: 'S-2206', label: 'S-2206 - Alt. Contratual' },
  { value: 'S-2299', label: 'S-2299 - Desligamento' },
  { value: 'S-2300', label: 'S-2300 - TSV Inicio' },
  { value: 'S-2399', label: 'S-2399 - TSV Termino' },
];

export default function EsocialPage() {
  const [search, setSearch] = useState('');
  const [tipoFilter, setTipoFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [page, setPage] = useState(1);
  const [selectedEvento, setSelectedEvento] = useState<any | null>(null);
  const [showDetailModal, setShowDetailModal] = useState(false);

  const {
    data: eventosData,
    isLoading,
    isError,
    error,
    refetch,
  } = useListarEventos({
    tipo_evento: tipoFilter || undefined,
    status: statusFilter,
  });

  const enviarMutation = useEnviarEvento();
  const validarMutation = useValidarEvento();

  const eventosList = Array.isArray(eventosData)
    ? eventosData
    : (eventosData as any)?.items || [];

  const filteredList = search
    ? eventosList.filter((item: any) =>
        (item.tipo_evento || '').toLowerCase().includes(search.toLowerCase()) ||
        (item.protocolo || '').toLowerCase().includes(search.toLowerCase())
      )
    : eventosList;

  const totalEventos = eventosList.length;
  const pendentes = eventosList.filter((e: any) => e.status === 'pendente').length;
  const enviados = eventosList.filter((e: any) => e.status === 'enviado' || e.status === 'aceito').length;
  const comErro = eventosList.filter((e: any) => e.status === 'rejeitado' || e.status === 'erro').length;

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

  const handleReenviar = (evento: any) => {
    enviarMutation.mutate(
      {
        tipo_evento: evento.tipo_evento,
        dados_evento: evento.dados || {},
      },
      {
        onSuccess: () => refetch(),
      }
    );
  };

  const handleValidar = (evento: any) => {
    validarMutation.mutate({
      tipo_evento: evento.tipo_evento,
      dados_evento: evento.dados || {},
    });
  };

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <PageHeader
        eyebrow="FISCAL"
        title="eSocial"
        subtitle="Eventos trabalhistas e previdenciarios"
        icon={<Users className="h-5 w-5" />}
        actions={
          <Button
            variant="secondary"
            size="sm"
            onClick={() => refetch()}
            disabled={isLoading}
          >
            <RefreshCw className={cn('w-4 h-4', isLoading && 'animate-spin')} />
          </Button>
        }
      />

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Total Eventos"
          value={isLoading ? '...' : totalEventos}
          icon={<Users className="w-5 h-5" />}
          color="#3b82f6"
        />
        <StatCard
          label="Pendentes"
          value={isLoading ? '...' : pendentes}
          icon={<Clock className="w-5 h-5" />}
          color="#eab308"
        />
        <StatCard
          label="Enviados"
          value={isLoading ? '...' : enviados}
          icon={<Send className="w-5 h-5" />}
          color="#22c55e"
        />
        <StatCard
          label="Com Erro"
          value={isLoading ? '...' : comErro}
          icon={<XCircle className="w-5 h-5" />}
          color="#ef4444"
        />
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4">
        <div className="flex-1">
          <Input
            type="search"
            placeholder="Buscar por tipo ou protocolo..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            icon={<Search className="w-4 h-4" />}
          />
        </div>
        <select
          value={tipoFilter}
          onChange={(e) => setTipoFilter(e.target.value)}
          className="px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))] text-sm"
        >
          {tipoEventos.map((tipo) => (
            <option key={tipo.value} value={tipo.value}>{tipo.label}</option>
          ))}
        </select>
        <div className="flex gap-2 flex-wrap">
          <Button
            variant={statusFilter === undefined ? 'primary' : 'secondary'}
            size="sm"
            onClick={() => setStatusFilter(undefined)}
          >
            Todos
          </Button>
          <Button
            variant={statusFilter === 'pendente' ? 'primary' : 'secondary'}
            size="sm"
            onClick={() => setStatusFilter('pendente')}
          >
            Pendente
          </Button>
          <Button
            variant={statusFilter === 'enviado' ? 'primary' : 'secondary'}
            size="sm"
            onClick={() => setStatusFilter('enviado')}
          >
            Enviado
          </Button>
          <Button
            variant={statusFilter === 'aceito' ? 'primary' : 'secondary'}
            size="sm"
            onClick={() => setStatusFilter('aceito')}
          >
            Aceito
          </Button>
          <Button
            variant={statusFilter === 'rejeitado' ? 'primary' : 'secondary'}
            size="sm"
            onClick={() => setStatusFilter('rejeitado')}
          >
            Rejeitado
          </Button>
        </div>
      </div>

      {/* Error */}
      {isError && (
        <div className="flex items-center gap-3 p-4 rounded-lg bg-[hsl(var(--destructive))]/10 border border-[hsl(var(--destructive))]/30">
          <AlertCircle className="w-5 h-5 text-[hsl(var(--destructive))]" />
          <div>
            <p className="font-medium text-[hsl(var(--destructive))]">Erro ao carregar eventos</p>
            <p className="text-sm text-[hsl(var(--muted-foreground))]">
              {(error as Error)?.message || 'Tente novamente em alguns instantes'}
            </p>
          </div>
          <Button variant="secondary" size="sm" onClick={() => refetch()} className="ml-auto">
            Tentar novamente
          </Button>
        </div>
      )}

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="divide-y divide-[hsl(var(--border))]">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="p-4 flex items-center gap-4">
                  <div className="flex-1 space-y-2">
                    <div className="h-4 w-48 bg-[hsl(var(--secondary))] rounded animate-shimmer" />
                    <div className="h-3 w-32 bg-[hsl(var(--secondary))] rounded animate-shimmer" />
                  </div>
                  <div className="h-6 w-20 bg-[hsl(var(--secondary))] rounded animate-shimmer" />
                </div>
              ))}
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
                      Status
                    </th>
                    <th className="text-left p-4 text-sm font-medium text-[hsl(var(--muted-foreground))] hidden md:table-cell">
                      Data Envio
                    </th>
                    <th className="text-left p-4 text-sm font-medium text-[hsl(var(--muted-foreground))] hidden lg:table-cell">
                      Protocolo
                    </th>
                    <th className="w-32 p-4 text-sm font-medium text-[hsl(var(--muted-foreground))]">
                      Ações
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[hsl(var(--border))]">
                  {filteredList.map((evento: any) => {
                    const st = statusConfig[evento.status] || statusConfig.pendente || { label: 'Pendente', color: 'bg-yellow-100 text-yellow-800' };
                    return (
                      <tr
                        key={evento.id || evento.protocolo}
                        className="hover:bg-[hsl(var(--secondary))]/50 transition-colors"
                      >
                        <td className="p-4">
                          <p className="font-medium text-[hsl(var(--foreground))]">
                            {evento.tipo_evento || '-'}
                          </p>
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
                        <td className="p-4 hidden lg:table-cell">
                          <span className="text-sm font-mono text-[hsl(var(--muted-foreground))]">
                            {evento.protocolo || '-'}
                          </span>
                        </td>
                        <td className="p-4">
                          <div className="flex items-center gap-1">
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
                            {(evento.status === 'rejeitado' || evento.status === 'erro') && (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleReenviar(evento)}
                                disabled={enviarMutation.isPending}
                                title="Reenviar"
                              >
                                <Send className="w-4 h-4 text-blue-500" />
                              </Button>
                            )}
                            {evento.status === 'pendente' && (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleValidar(evento)}
                                disabled={validarMutation.isPending}
                                title="Validar"
                              >
                                <CheckSquare className="w-4 h-4 text-green-500" />
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

          {/* Empty state */}
          {!isLoading && !isError && filteredList.length === 0 && (
            <div className="text-center py-12">
              <Users className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
              <h3 className="text-lg font-medium text-[hsl(var(--foreground))]">
                Nenhum evento encontrado
              </h3>
              <p className="text-[hsl(var(--muted-foreground))] mt-1">
                {search || tipoFilter || statusFilter
                  ? 'Tente ajustar os filtros'
                  : 'Nenhum evento eSocial registrado'}
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Pagination info */}
      {!isLoading && filteredList.length > 0 && (
        <div className="text-sm text-[hsl(var(--muted-foreground))] text-center">
          Mostrando {filteredList.length} eventos
        </div>
      )}

      {/* Detail Modal */}
      <EsocialDetailModal
        isOpen={showDetailModal}
        onClose={() => {
          setShowDetailModal(false);
          setSelectedEvento(null);
        }}
        evento={selectedEvento}
        onReenviar={handleReenviar}
      />
    </div>
  );
}
