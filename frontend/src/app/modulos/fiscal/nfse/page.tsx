'use client';

import { Search, Plus, RefreshCw, AlertCircle, FileText, Eye, XCircle, Filter, DollarSign, Ban } from 'lucide-react';
import { useState } from 'react';
;
import { Button } from '@/components/ui/button';
import { abrirPdf } from '@/lib/pdf';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { PageHeader } from '@/components/ui/page-header';
import { StatCard } from '@/components/ui/stat-card';
import { ConfirmModal } from '@/components/ui/modal';
import { NfseFormModal } from '@/components/fiscal/nfse-form-modal';
import { NfseDetailModal } from '@/components/fiscal/nfse-detail-modal';
import { useListarNFSe, useEmitirNFSeNacional, useCancelarNFSeNacional } from '@/hooks/government';
import { cn } from '@/lib/utils';

const statusConfig: Record<string, { label: string; color: string }> = {
  emitida: { label: 'Emitida', color: 'bg-green-100 text-green-800' },
  cancelada: { label: 'Cancelada', color: 'bg-red-100 text-red-800' },
  pendente: { label: 'Pendente', color: 'bg-yellow-100 text-yellow-800' },
  processando: { label: 'Processando', color: 'bg-blue-100 text-blue-800' },
};

export default function NfsePage() {
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [page, setPage] = useState(1);
  const [showFormModal, setShowFormModal] = useState(false);
  const [selectedNfse, setSelectedNfse] = useState<any | null>(null);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [showCancelModal, setShowCancelModal] = useState(false);
  const [cancelTarget, setCancelTarget] = useState<any | null>(null);

  const {
    data: nfseData,
    isLoading,
    isError,
    error,
    refetch,
  } = useListarNFSe({
    data_emissao_inicial: undefined,
  } as any);

  const emitirMutation = useEmitirNFSeNacional();
  const cancelarMutation = useCancelarNFSeNacional();

  const nfseList = Array.isArray(nfseData)
    ? nfseData
    : (nfseData as any)?.items || [];

  const filteredList = search
    ? nfseList.filter((item: any) =>
        (item.tomador_nome || '').toLowerCase().includes(search.toLowerCase()) ||
        (item.numero || '').toLowerCase().includes(search.toLowerCase())
      )
    : nfseList;

  const totalEmitidas = nfseList.filter((n: any) => n.status === 'emitida').length;
  const totalCanceladas = nfseList.filter((n: any) => n.status === 'cancelada').length;
  const valorTotal = nfseList.reduce(
    (acc: number, n: any) => acc + (n.valor_servico || 0),
    0
  );

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

  const handleEmitir = (data: any) => {
    // Mapeia o form (campos planos) para a estrutura do endpoint NFS-e Nacional
    const payload: any = {
      tomador: {
        cpf_cnpj: (data.tomador_cnpj || '').replace(/\D/g, ''),
        razao_social: data.tomador_nome,
        logradouro: data.tomador_logradouro || 'NAO INFORMADO',
        numero: data.tomador_numero || 'S/N',
        bairro: data.tomador_bairro || 'CENTRO',
        codigo_municipio: '1302603',
        uf: 'AM',
        cep: (data.tomador_cep || '69000000').replace(/\D/g, ''),
      },
      servico: {
        codigo_tributacao_nacional: data.codigo_servico || '110201',
        descricao: data.descricao_servico,
        valor_servico: String(data.valor_servico),
        aliquota_iss: String(data.aliquota_iss || 0.05),
      },
      prestador: {
        cnpj: '35710481000103',
        inscricao_municipal: '45177801',
        codigo_municipio: '1302603',
        razao_social: 'JORDAN SANTOS DE JESUS LTDA',
        optante_simples: false,
      },
      numero: data.numero_rps || undefined,
    };
    emitirMutation.mutate(payload, {
      onSuccess: () => {
        setShowFormModal(false);
        refetch();
      },
    });
  };

  const handleCancelar = () => {
    if (!cancelTarget) return;
    cancelarMutation.mutate(
      {
        numero_nota: cancelTarget.numero,
        codigo_cancelamento: 'CANCEL',
        motivo: 'Cancelamento solicitado pelo usuario',
      },
      {
        onSuccess: () => {
          setShowCancelModal(false);
          setCancelTarget(null);
          refetch();
        },
      }
    );
  };

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <PageHeader
        eyebrow="FISCAL"
        title="NFS-e"
        subtitle="Notas Fiscais de Servico Eletronica"
        icon={<FileText className="h-5 w-5" />}
        actions={
          <>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => refetch()}
              disabled={isLoading}
            >
              <RefreshCw className={cn('w-4 h-4', isLoading && 'animate-spin')} />
            </Button>
            <Button onClick={() => setShowFormModal(true)}>
              <Plus className="w-4 h-4 mr-2" />
              Emitir NFS-e
            </Button>
          </>
        }
      />

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard
          label="Total Emitidas"
          value={isLoading ? '...' : totalEmitidas}
          icon={<FileText className="w-5 h-5" />}
          color="#22c55e"
        />
        <StatCard
          label="Canceladas"
          value={isLoading ? '...' : totalCanceladas}
          icon={<Ban className="w-5 h-5" />}
          color="#ef4444"
        />
        <StatCard
          label="Valor Total"
          value={isLoading ? '...' : formatCurrency(valorTotal)}
          icon={<DollarSign className="w-5 h-5" />}
          color="#3b82f6"
        />
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4">
        <div className="flex-1">
          <Input
            type="search"
            placeholder="Buscar por numero ou tomador..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            icon={<Search className="w-4 h-4" />}
          />
        </div>
        <div className="flex gap-2 flex-wrap">
          <Button
            variant={statusFilter === undefined ? 'primary' : 'secondary'}
            size="sm"
            onClick={() => setStatusFilter(undefined)}
          >
            Todos
          </Button>
          <Button
            variant={statusFilter === 'emitida' ? 'primary' : 'secondary'}
            size="sm"
            onClick={() => setStatusFilter('emitida')}
          >
            Emitida
          </Button>
          <Button
            variant={statusFilter === 'cancelada' ? 'primary' : 'secondary'}
            size="sm"
            onClick={() => setStatusFilter('cancelada')}
          >
            Cancelada
          </Button>
          <Button
            variant={statusFilter === 'pendente' ? 'primary' : 'secondary'}
            size="sm"
            onClick={() => setStatusFilter('pendente')}
          >
            Pendente
          </Button>
        </div>
      </div>

      {/* Error */}
      {isError && (
        <div className="flex items-center gap-3 p-4 rounded-lg bg-[hsl(var(--destructive))]/10 border border-[hsl(var(--destructive))]/30">
          <AlertCircle className="w-5 h-5 text-[hsl(var(--destructive))]" />
          <div>
            <p className="font-medium text-[hsl(var(--destructive))]">Erro ao carregar NFS-e</p>
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
                      Numero
                    </th>
                    <th className="text-left p-4 text-sm font-medium text-[hsl(var(--muted-foreground))] hidden md:table-cell">
                      Tomador
                    </th>
                    <th className="text-right p-4 text-sm font-medium text-[hsl(var(--muted-foreground))]">
                      Valor
                    </th>
                    <th className="text-left p-4 text-sm font-medium text-[hsl(var(--muted-foreground))]">
                      Status
                    </th>
                    <th className="text-left p-4 text-sm font-medium text-[hsl(var(--muted-foreground))] hidden lg:table-cell">
                      Data
                    </th>
                    <th className="w-24 p-4 text-sm font-medium text-[hsl(var(--muted-foreground))]">
                      Ações
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[hsl(var(--border))]">
                  {filteredList.map((nfse: any) => {
                    const st = statusConfig[nfse.status] || statusConfig.pendente || { label: 'Pendente', color: 'bg-yellow-100 text-yellow-800' };
                    return (
                      <tr
                        key={nfse.id || nfse.numero}
                        className="hover:bg-[hsl(var(--secondary))]/50 transition-colors"
                      >
                        <td className="p-4">
                          <p className="font-medium text-[hsl(var(--foreground))]">
                            {nfse.numero || '-'}
                          </p>
                        </td>
                        <td className="p-4 hidden md:table-cell">
                          <p className="text-sm text-[hsl(var(--foreground))]">
                            {nfse.tomador_nome || '-'}
                          </p>
                          <p className="text-xs text-[hsl(var(--muted-foreground))]">
                            {nfse.tomador_cnpj || ''}
                          </p>
                        </td>
                        <td className="p-4 text-right">
                          <span className="font-mono text-sm text-[hsl(var(--foreground))]">
                            {formatCurrency(nfse.valor_servico || 0)}
                          </span>
                        </td>
                        <td className="p-4">
                          <span className={cn('inline-flex px-2 py-1 text-xs font-medium rounded-full', st.color)}>
                            {st.label}
                          </span>
                        </td>
                        <td className="p-4 hidden lg:table-cell">
                          <span className="text-sm text-[hsl(var(--muted-foreground))]">
                            {formatDate(nfse.data_emissao)}
                          </span>
                        </td>
                        <td className="p-4">
                          <div className="flex items-center gap-1">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => {
                                setSelectedNfse(nfse);
                                setShowDetailModal(true);
                              }}
                              title="Ver detalhes"
                            >
                              <Eye className="w-4 h-4" />
                            </Button>
                            {nfse.id && (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => abrirPdf(`/api/v1/financial/fiscal/nfse/${nfse.id}/danfse`, { download: true, nome: `danfse_${nfse.numero || nfse.id}.pdf` })}
                                title="Baixar DANFSe (PDF)"
                              >
                                <FileText className="w-4 h-4" />
                              </Button>
                            )}
                            {nfse.status === 'emitida' && (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => {
                                  setCancelTarget(nfse);
                                  setShowCancelModal(true);
                                }}
                                title="Cancelar"
                              >
                                <XCircle className="w-4 h-4 text-red-500" />
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
              <FileText className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
              <h3 className="text-lg font-medium text-[hsl(var(--foreground))]">
                Nenhuma NFS-e encontrada
              </h3>
              <p className="text-[hsl(var(--muted-foreground))] mt-1">
                {search || statusFilter
                  ? 'Tente ajustar os filtros'
                  : 'Comece emitindo sua primeira NFS-e'}
              </p>
              {!search && !statusFilter && (
                <Button className="mt-4" onClick={() => setShowFormModal(true)}>
                  <Plus className="w-4 h-4 mr-2" />
                  Emitir NFS-e
                </Button>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Pagination info */}
      {!isLoading && filteredList.length > 0 && (
        <div className="text-sm text-[hsl(var(--muted-foreground))] text-center">
          Mostrando {filteredList.length} NFS-e
        </div>
      )}

      {/* Modals */}
      <NfseFormModal
        isOpen={showFormModal}
        onClose={() => setShowFormModal(false)}
        onSubmit={handleEmitir}
        isLoading={emitirMutation.isPending}
      />

      <NfseDetailModal
        isOpen={showDetailModal}
        onClose={() => {
          setShowDetailModal(false);
          setSelectedNfse(null);
        }}
        nfse={selectedNfse}
      />

      <ConfirmModal
        isOpen={showCancelModal}
        onClose={() => {
          setShowCancelModal(false);
          setCancelTarget(null);
        }}
        onConfirm={handleCancelar}
        title="Cancelar NFS-e"
        message={`Deseja realmente cancelar a NFS-e ${cancelTarget?.numero || ''}? Esta acao nao pode ser desfeita.`}
        confirmText="Cancelar NFS-e"
        variant="danger"
        isLoading={cancelarMutation.isPending}
      />
    </div>
  );
}
