'use client';

/**
 * Página de Detalhes do Edital
 * Visualização completa com abas e histórico
 */

import {
  FileText,
  ArrowLeft,
  Edit2,
  FileCheck,
  Download,
  Calendar,
  DollarSign,
  MapPin,
  Building2,
  Clock,
  AlertCircle,
  ExternalLink,
  CheckCircle,
  FileDown,
  History,
} from 'lucide-react';
import { useState } from 'react';
import { useRouter, useParams } from 'next/navigation';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  useBuscarEdital,
  useMarcarParticipacao,
  useAlterarStatusEdital,
} from '@/hooks/bidding/useTenders';
import { TenderStatusBadge } from '@/components/licitacoes/TenderStatusBadge';
import { ModalityBadge } from '@/components/licitacoes/ModalityBadge';
import { TenderFormModal } from '@/components/licitacoes/TenderFormModal';

type Tab = 'geral' | 'documentos' | 'propostas' | 'historico';

const STATUS_OPTIONS = [
  { value: 'aberto', label: 'Aberto' },
  { value: 'em_andamento', label: 'Em Andamento' },
  { value: 'em_analise', label: 'Em Análise' },
  { value: 'participando', label: 'Participando' },
  { value: 'interesse', label: 'Interesse' },
  { value: 'homologado', label: 'Homologado' },
  { value: 'cancelado', label: 'Cancelado' },
  { value: 'deserto', label: 'Deserto' },
  { value: 'fracassado', label: 'Fracassado' },
  { value: 'arquivado', label: 'Arquivado' },
];

export default function TenderDetailPage() {
  const router = useRouter();
  const params = useParams();
  const tenderId = params?.id as string;

  const [activeTab, setActiveTab] = useState<Tab>('geral');
  const [showEditModal, setShowEditModal] = useState(false);

  const { data: tender, isLoading, refetch } = useBuscarEdital(tenderId);
  const marcarParticipacaoMutation = useMarcarParticipacao();
  const alterarStatusMutation = useAlterarStatusEdital();

  const formatCurrency = (value?: number) => {
    if (!value) return 'Não informado';
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL',
    }).format(value);
  };

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return 'Não informado';
    return new Date(dateStr).toLocaleDateString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    });
  };

  const formatDateTime = (dateStr?: string) => {
    if (!dateStr) return 'Não informado';
    return new Date(dateStr).toLocaleDateString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const handleMarcarParticipacao = async () => {
    if (!tender) return;
    await marcarParticipacaoMutation.mutateAsync({
      tender_id: tender.id,
      participando: true,
      interesse: true,
    });
    refetch();
  };

  const handleAlterarStatus = async (novoStatus: string) => {
    if (!tender) return;
    await alterarStatusMutation.mutateAsync({
      tender_id: tender.id,
      novo_status: novoStatus,
    });
    refetch();
  };

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))]">
        <div className="animate-pulse-slow text-[hsl(var(--primary))]">
          <FileText className="w-12 h-12" />
        </div>
      </div>
    );
  }

  if (!tender) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))]">
        <div className="text-center">
          <AlertCircle className="w-12 h-12 text-red-500 mx-auto mb-4" />
          <h2 className="text-xl font-semibold">Edital não encontrado</h2>
          <Button className="mt-4" onClick={() => router.back()}>
            Voltar
          </Button>
        </div>
      </div>
    );
  }

  const tenderData = tender as any;

  return (
    <div className="min-h-screen bg-grid">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-[hsl(var(--background))]/80 backdrop-blur-xl border-b border-[hsl(var(--border))]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-4">
              <Link href="/modulos/licitacoes/editais">
                <Button variant="ghost" size="sm">
                  <ArrowLeft className="w-4 h-4 mr-2" />
                  Editais
                </Button>
              </Link>
              <div className="flex items-center gap-2">
                <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
                  <FileText className="w-5 h-5 text-blue-500" />
                </div>
                <div>
                  <h1 className="text-lg font-semibold text-[hsl(var(--foreground))]">
                    {tenderData.number || tender.id.slice(0, 8)}
                  </h1>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">
                    {tenderData.entity || 'Órgão não informado'}
                  </p>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={handleMarcarParticipacao}
                disabled={marcarParticipacaoMutation.isPending}
              >
                <FileCheck className="w-4 h-4 mr-2" />
                Marcar Participação
              </Button>
              <Button variant="outline" size="sm" onClick={() => setShowEditModal(true)}>
                <Edit2 className="w-4 h-4 mr-2" />
                Editar
              </Button>
              {tenderData.link && (
                <a href={tenderData.link} target="_blank" rel="noopener noreferrer">
                  <Button variant="outline" size="sm">
                    <Download className="w-4 h-4 mr-2" />
                    Ver Edital
                  </Button>
                </a>
              )}
            </div>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Header card */}
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-6 mb-6">
          <div className="flex items-start justify-between mb-4">
            <div className="flex-1">
              <div className="flex items-center gap-3 mb-2">
                <TenderStatusBadge status={tender.status} />
                <ModalityBadge modality={tender.modality} />
                {tenderData.pncp_id && (
                  <Badge variant="outline" className="bg-green-500/10 text-green-600">
                    PNCP
                  </Badge>
                )}
              </div>
              <h2 className="text-xl font-semibold text-[hsl(var(--foreground))] mb-2">
                {tender.title}
              </h2>
              {tender.description && (
                <p className="text-sm text-[hsl(var(--muted-foreground))]">
                  {tender.description}
                </p>
              )}
            </div>
            <div className="text-right">
              <p className="text-sm text-[hsl(var(--muted-foreground))] mb-1">
                Valor Estimado
              </p>
              <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                {formatCurrency(tender.estimated_value)}
              </p>
            </div>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 pt-4 border-t border-[hsl(var(--border))]">
            <div className="flex items-center gap-2">
              <Calendar className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />
              <div>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Abertura</p>
                <p className="text-sm font-medium">{formatDate(tender.opening_date)}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <MapPin className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />
              <div>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Localização</p>
                <p className="text-sm font-medium">
                  {tenderData.uf || 'N/A'} - {tenderData.city || 'N/A'}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Building2 className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />
              <div>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Segmento</p>
                <p className="text-sm font-medium">{tenderData.segment || 'N/A'}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Clock className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />
              <div>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Cadastrado em</p>
                <p className="text-sm font-medium">{formatDate(tender.created_at)}</p>
              </div>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl overflow-hidden">
          <div className="border-b border-[hsl(var(--border))]">
            <div className="flex">
              <button
                onClick={() => setActiveTab('geral')}
                className={`px-6 py-3 text-sm font-medium transition-colors ${
                  activeTab === 'geral'
                    ? 'text-[hsl(var(--primary))] border-b-2 border-[hsl(var(--primary))]'
                    : 'text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))]'
                }`}
              >
                Informações Gerais
              </button>
              <button
                onClick={() => setActiveTab('documentos')}
                className={`px-6 py-3 text-sm font-medium transition-colors ${
                  activeTab === 'documentos'
                    ? 'text-[hsl(var(--primary))] border-b-2 border-[hsl(var(--primary))]'
                    : 'text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))]'
                }`}
              >
                Documentos Exigidos
              </button>
              <button
                onClick={() => setActiveTab('propostas')}
                className={`px-6 py-3 text-sm font-medium transition-colors ${
                  activeTab === 'propostas'
                    ? 'text-[hsl(var(--primary))] border-b-2 border-[hsl(var(--primary))]'
                    : 'text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))]'
                }`}
              >
                Propostas
              </button>
              <button
                onClick={() => setActiveTab('historico')}
                className={`px-6 py-3 text-sm font-medium transition-colors ${
                  activeTab === 'historico'
                    ? 'text-[hsl(var(--primary))] border-b-2 border-[hsl(var(--primary))]'
                    : 'text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))]'
                }`}
              >
                Histórico
              </button>
            </div>
          </div>

          <div className="p-6">
            {/* Tab: Informações Gerais */}
            {activeTab === 'geral' && (
              <div className="space-y-6">
                <div className="grid grid-cols-2 gap-6">
                  <div>
                    <h3 className="text-sm font-semibold text-[hsl(var(--foreground))] mb-3">
                      Dados do Edital
                    </h3>
                    <dl className="space-y-2">
                      <div>
                        <dt className="text-xs text-[hsl(var(--muted-foreground))]">
                          Número
                        </dt>
                        <dd className="text-sm font-medium">
                          {tenderData.number || 'N/A'}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-xs text-[hsl(var(--muted-foreground))]">
                          Órgão/Entidade
                        </dt>
                        <dd className="text-sm font-medium">
                          {tenderData.entity || 'N/A'}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-xs text-[hsl(var(--muted-foreground))]">
                          Modalidade
                        </dt>
                        <dd className="text-sm font-medium">
                          <ModalityBadge modality={tender.modality} />
                        </dd>
                      </div>
                      <div>
                        <dt className="text-xs text-[hsl(var(--muted-foreground))]">
                          Critério de Julgamento
                        </dt>
                        <dd className="text-sm font-medium">
                          {tenderData.judgment_criteria || 'N/A'}
                        </dd>
                      </div>
                    </dl>
                  </div>

                  <div>
                    <h3 className="text-sm font-semibold text-[hsl(var(--foreground))] mb-3">
                      Prazos
                    </h3>
                    <dl className="space-y-2">
                      <div>
                        <dt className="text-xs text-[hsl(var(--muted-foreground))]">
                          Data de Publicação
                        </dt>
                        <dd className="text-sm font-medium">
                          {formatDate(tenderData.publication_date)}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-xs text-[hsl(var(--muted-foreground))]">
                          Data de Abertura
                        </dt>
                        <dd className="text-sm font-medium">
                          {formatDateTime(tender.opening_date)}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-xs text-[hsl(var(--muted-foreground))]">
                          Prazo para Proposta
                        </dt>
                        <dd className="text-sm font-medium">
                          {formatDate(tenderData.deadline_date)}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-xs text-[hsl(var(--muted-foreground))]">
                          Data de Encerramento
                        </dt>
                        <dd className="text-sm font-medium">
                          {formatDateTime(tender.closing_date)}
                        </dd>
                      </div>
                    </dl>
                  </div>
                </div>

                {tenderData.observations && (
                  <div>
                    <h3 className="text-sm font-semibold text-[hsl(var(--foreground))] mb-2">
                      Observações
                    </h3>
                    <p className="text-sm text-[hsl(var(--muted-foreground))] bg-[hsl(var(--muted))] p-4 rounded-lg">
                      {tenderData.observations}
                    </p>
                  </div>
                )}

                <div>
                  <h3 className="text-sm font-semibold text-[hsl(var(--foreground))] mb-2">
                    Alterar Status
                  </h3>
                  <div className="flex flex-wrap gap-2">
                    {STATUS_OPTIONS.map((option) => (
                      <Button
                        key={option.value}
                        variant={tender.status === option.value ? 'primary' : 'outline'}
                        size="sm"
                        onClick={() => handleAlterarStatus(option.value)}
                        disabled={
                          alterarStatusMutation.isPending || tender.status === option.value
                        }
                      >
                        {option.label}
                      </Button>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* Tab: Documentos */}
            {activeTab === 'documentos' && (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-[hsl(var(--foreground))]">
                    Documentos Exigidos no Edital
                  </h3>
                  <span className="text-xs text-[hsl(var(--muted-foreground))]">
                    {tenderData.required_documents?.length || 0} documento(s)
                  </span>
                </div>
                {tenderData.required_documents && tenderData.required_documents.length > 0 ? (
                  <div className="space-y-2">
                    {tenderData.required_documents.map((doc: any, idx: number) => (
                      <div key={idx} className="flex items-center gap-3 p-3 bg-[hsl(var(--muted))] rounded-lg">
                        <FileDown className="w-4 h-4 text-[hsl(var(--muted-foreground))] flex-shrink-0" />
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium truncate">
                            {typeof doc === 'string' ? doc : doc.name || doc.titulo || 'Documento'}
                          </p>
                          {doc.tipo && <p className="text-xs text-[hsl(var(--muted-foreground))]">{doc.tipo}</p>}
                        </div>
                        {doc.obrigatorio !== false && (
                          <span className="text-xs bg-red-500/10 text-red-600 px-2 py-0.5 rounded">Obrigatório</span>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-8">
                    <FileDown className="w-10 h-10 text-[hsl(var(--muted-foreground))]/50 mx-auto mb-3" />
                    <p className="text-sm text-[hsl(var(--muted-foreground))]">
                      Nenhum documento cadastrado para este edital.
                    </p>
                    <p className="text-xs text-[hsl(var(--muted-foreground))] mt-1">
                      Use o botão Editar para adicionar documentos exigidos.
                    </p>
                  </div>
                )}
              </div>
            )}

            {/* Tab: Propostas */}
            {activeTab === 'propostas' && (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-[hsl(var(--foreground))]">
                    Propostas Vinculadas
                  </h3>
                  <Link href={`/modulos/licitacoes/propostas?tender_id=${tenderId}`}>
                    <Button variant="outline" size="sm">
                      <FileCheck className="w-4 h-4 mr-2" />
                      Nova Proposta
                    </Button>
                  </Link>
                </div>
                {tenderData.proposals && tenderData.proposals.length > 0 ? (
                  <div className="space-y-2">
                    {tenderData.proposals.map((prop: any) => (
                      <Link key={prop.id} href={`/modulos/licitacoes/propostas/${prop.id}`}>
                        <div className="flex items-center justify-between p-3 bg-[hsl(var(--muted))] rounded-lg hover:bg-[hsl(var(--muted))]/80 transition-colors cursor-pointer">
                          <div className="flex items-center gap-3">
                            <FileCheck className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />
                            <div>
                              <p className="text-sm font-medium">{prop.razao_social || prop.cnpj || 'Proposta'}</p>
                              <p className="text-xs text-[hsl(var(--muted-foreground))]">
                                {prop.numero_proposta || prop.id?.slice(0, 8)}
                              </p>
                            </div>
                          </div>
                          <div className="text-right">
                            <p className="text-sm font-semibold">
                              {prop.valor_global
                                ? new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(prop.valor_global)
                                : '-'}
                            </p>
                            <span className={`text-xs px-2 py-0.5 rounded ${
                              prop.status === 'enviada' ? 'bg-blue-500/10 text-blue-600' :
                              prop.status === 'vencedora' ? 'bg-green-500/10 text-green-600' :
                              'bg-gray-500/10 text-gray-600'
                            }`}>
                              {prop.status || 'rascunho'}
                            </span>
                          </div>
                        </div>
                      </Link>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-8">
                    <FileCheck className="w-10 h-10 text-[hsl(var(--muted-foreground))]/50 mx-auto mb-3" />
                    <p className="text-sm text-[hsl(var(--muted-foreground))]">
                      Nenhuma proposta vinculada a este edital.
                    </p>
                    <Link href={`/modulos/licitacoes/propostas?tender_id=${tenderId}`}>
                      <Button variant="outline" size="sm" className="mt-3">
                        Criar Proposta
                      </Button>
                    </Link>
                  </div>
                )}
              </div>
            )}

            {/* Tab: Histórico */}
            {activeTab === 'historico' && (
              <div className="space-y-4">
                <h3 className="text-sm font-semibold text-[hsl(var(--foreground))]">
                  Histórico de Alterações
                </h3>
                <div className="space-y-0">
                  <div className="relative pl-6 pb-6 border-l-2 border-[hsl(var(--border))]">
                    <div className="absolute left-[-5px] top-0 w-2 h-2 rounded-full bg-blue-500" />
                    <div>
                      <p className="text-sm font-medium">Edital Criado</p>
                      <p className="text-xs text-[hsl(var(--muted-foreground))]">
                        {formatDate(tender.created_at)} — Status: {tender.status}
                      </p>
                    </div>
                  </div>
                  {tender.updated_at && tender.updated_at !== tender.created_at && (
                    <div className="relative pl-6 pb-6 border-l-2 border-[hsl(var(--border))]">
                      <div className="absolute left-[-5px] top-0 w-2 h-2 rounded-full bg-green-500" />
                      <div>
                        <p className="text-sm font-medium">Última Atualização</p>
                        <p className="text-xs text-[hsl(var(--muted-foreground))]">
                          {formatDate(tender.updated_at)}
                        </p>
                      </div>
                    </div>
                  )}
                  {tenderData.opening_date && (
                    <div className="relative pl-6 pb-6 border-l-2 border-[hsl(var(--border))]">
                      <div className="absolute left-[-5px] top-0 w-2 h-2 rounded-full bg-orange-500" />
                      <div>
                        <p className="text-sm font-medium">Abertura Prevista</p>
                        <p className="text-xs text-[hsl(var(--muted-foreground))]">
                          {formatDateTime(tenderData.opening_date)}
                        </p>
                      </div>
                    </div>
                  )}
                  {tenderData.closing_date && (
                    <div className="relative pl-6 border-l-2 border-transparent">
                      <div className="absolute left-[-5px] top-0 w-2 h-2 rounded-full bg-red-500" />
                      <div>
                        <p className="text-sm font-medium">Encerramento</p>
                        <p className="text-xs text-[hsl(var(--muted-foreground))]">
                          {formatDateTime(tenderData.closing_date)}
                        </p>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </main>

      {/* Edit Modal */}
      <TenderFormModal
        isOpen={showEditModal}
        onClose={() => setShowEditModal(false)}
        onSuccess={refetch}
        editData={tender}
      />
    </div>
  );
}
