'use client';

import { useState } from 'react';
import { useRouter, useParams } from 'next/navigation';
import {
  ArrowLeft,
  FileText,
  Edit,
  Send,
  Download,
  RefreshCw,
  Calendar,
  DollarSign,
  Clock,
  Building,
  FileCheck,
  Loader2,
  AlertCircle,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { Alert } from '@/components/ui/alert';
import { ProposalStatusBadge } from '@/components/licitacoes/ProposalStatusBadge';
import { ProposalFormModal } from '@/components/licitacoes/ProposalFormModal';
import { SubmitProposalDialog } from '@/components/licitacoes/SubmitProposalDialog';
import {
  useBuscarProposta,
  useAtualizarProposta,
  useEnviarProposta,
} from '@/hooks/bidding/useProposals';
import type { ProposalFormData } from '@/components/licitacoes/ProposalFormModal';

export default function PropostaDetalhePage() {
  const router = useRouter();
  const params = useParams();
  const proposalId = params.id as string;

  // Estados
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [isSubmitDialogOpen, setIsSubmitDialogOpen] = useState(false);
  const [activeTab, setActiveTab] = useState('dados-gerais');

  // Hooks
  const {
    data: proposal,
    isLoading,
    error,
    refetch,
  } = useBuscarProposta(proposalId);
  const atualizarProposta = useAtualizarProposta();
  const submeterProposta = useEnviarProposta();

  // Handlers
  const handleSubmitForm = async (data: ProposalFormData) => {
    await atualizarProposta.mutateAsync({
      id: proposalId,
      data: data as unknown as import('@/services/bidding/proposals.service').BiddingProposalUpdate,
    });
    setIsFormOpen(false);
  };

  const handleConfirmSubmit = async (observacoes?: string) => {
    await submeterProposta.mutateAsync({
      proposalId,
      observacoes,
    });
    setIsSubmitDialogOpen(false);
  };


  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL',
    }).format(value);
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('pt-BR');
  };

  const canSubmit = proposal?.status === 'rascunho' || proposal?.status === 'em_analise';
  const canEdit = proposal?.status === 'rascunho' ||
                  proposal?.status === 'em_analise' ||
                  proposal?.status === 'rejeitada';

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !proposal) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" onClick={() => router.back()}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Voltar
        </Button>
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <p>Erro ao carregar proposta. Tente novamente.</p>
        </Alert>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="space-y-1">
          <Button variant="ghost" onClick={() => router.back()} className="mb-2">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Voltar
          </Button>
          <div className="flex items-center gap-3">
            <FileText className="h-8 w-8 text-muted-foreground" />
            <div>
              <h1 className="font-display text-3xl font-bold tracking-tight">
                Proposta {(proposal as any).numero_proposta || proposal.id.substring(0, 8)}
              </h1>
              <p className="text-muted-foreground">
                {String(proposal.razao_social || '')}
              </p>
            </div>
          </div>
        </div>
        <div className="flex gap-2">
          {canSubmit && (
            <Button
              onClick={() => setIsSubmitDialogOpen(true)}
              disabled={submeterProposta.isPending}
            >
              <Send className="mr-2 h-4 w-4" />
              Submeter
            </Button>
          )}
          {canEdit && (
            <Button
              variant="outline"
              onClick={() => setIsFormOpen(true)}
              disabled={atualizarProposta.isPending}
            >
              <Edit className="mr-2 h-4 w-4" />
              Editar
            </Button>
          )}
          <Button variant="outline" onClick={() => refetch()}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Atualizar
          </Button>
        </div>
      </div>

      {/* Cards de Resumo */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-green-100 rounded-lg">
              <DollarSign className="h-5 w-5 text-green-600" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Valor Global</p>
              <p className="text-xl font-bold">
                {formatCurrency(Number(proposal.valor_global) || 0)}
              </p>
            </div>
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-100 rounded-lg">
              <Clock className="h-5 w-5 text-blue-600" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Prazo Entrega</p>
              <p className="text-xl font-bold">
                {(proposal as any).prazo_entrega || 0} dias
              </p>
            </div>
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-orange-100 rounded-lg">
              <Calendar className="h-5 w-5 text-orange-600" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Validade</p>
              <p className="text-xl font-bold">
                {(proposal as any).validade_proposta || 0} dias
              </p>
            </div>
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-purple-100 rounded-lg">
              <FileCheck className="h-5 w-5 text-purple-600" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Status</p>
              <ProposalStatusBadge status={proposal.status as any} />
            </div>
          </div>
        </Card>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="dados-gerais">Dados Gerais</TabsTrigger>
          <TabsTrigger value="itens">
            Itens da Proposta
          </TabsTrigger>
          <TabsTrigger value="documentos">Documentos</TabsTrigger>
          <TabsTrigger value="historico">Histórico</TabsTrigger>
        </TabsList>

        {/* Tab: Dados Gerais */}
        <TabsContent value="dados-gerais" className="space-y-4">
          <Card className="p-6">
            <h3 className="font-semibold text-lg mb-4">Informações do Edital</h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-muted-foreground">ID do Edital</p>
                <p className="font-medium">{proposal.tender_id}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Data de Criação</p>
                <p className="font-medium">
                  {proposal.created_at ? formatDate(proposal.created_at) : '-'}
                </p>
              </div>
            </div>
          </Card>

          <Card className="p-6">
            <h3 className="font-semibold text-lg mb-4">Dados da Empresa</h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-muted-foreground">CNPJ</p>
                <p className="font-medium">{String(proposal.cnpj || '')}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Razão Social</p>
                <p className="font-medium">{String(proposal.razao_social || '')}</p>
              </div>
            </div>
          </Card>

          <Card className="p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-lg">Status da Proposta</h3>
              <ProposalStatusBadge status={proposal.status as any} />
            </div>
          </Card>

          {(proposal as any).observacoes_tecnicas && (
            <Card className="p-6">
              <h3 className="font-semibold text-lg mb-4">
                Observações Técnicas
              </h3>
              <p className="text-muted-foreground whitespace-pre-wrap">
                {(proposal as any).observacoes_tecnicas}
              </p>
            </Card>
          )}

          {(proposal as any).observacoes_comerciais && (
            <Card className="p-6">
              <h3 className="font-semibold text-lg mb-4">
                Observações Comerciais
              </h3>
              <p className="text-muted-foreground whitespace-pre-wrap">
                {(proposal as any).observacoes_comerciais}
              </p>
            </Card>
          )}
        </TabsContent>

        {/* Tab: Itens da Proposta */}
        <TabsContent value="itens">
          <Card className="p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold">Itens da Proposta</h3>
            </div>
            {(proposal as any).itens && (proposal as any).itens.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b">
                      <th className="text-left py-2 px-3 font-medium text-muted-foreground">#</th>
                      <th className="text-left py-2 px-3 font-medium text-muted-foreground">Descricao</th>
                      <th className="text-right py-2 px-3 font-medium text-muted-foreground">Qtd</th>
                      <th className="text-right py-2 px-3 font-medium text-muted-foreground">Valor Unit.</th>
                      <th className="text-right py-2 px-3 font-medium text-muted-foreground">Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(proposal as any).itens.map((item: any, idx: number) => (
                      <tr key={idx} className="border-b last:border-0">
                        <td className="py-2 px-3">{item.numero || idx + 1}</td>
                        <td className="py-2 px-3">{item.descricao}</td>
                        <td className="py-2 px-3 text-right">{item.quantidade} {item.unidade || ''}</td>
                        <td className="py-2 px-3 text-right">{formatCurrency(item.valor_unitario || 0)}</td>
                        <td className="py-2 px-3 text-right font-medium">
                          {formatCurrency((item.quantidade || 1) * (item.valor_unitario || 0))}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr className="border-t-2">
                      <td colSpan={4} className="py-2 px-3 text-right font-semibold">Total:</td>
                      <td className="py-2 px-3 text-right font-bold text-lg">
                        {formatCurrency(
                          (proposal as any).itens.reduce((sum: number, item: any) =>
                            sum + ((item.quantidade || 1) * (item.valor_unitario || 0)), 0
                          )
                        )}
                      </td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            ) : (
              <div className="text-center py-12">
                <FileText className="h-12 w-12 mx-auto mb-4 text-muted-foreground opacity-30" />
                <h3 className="text-lg font-semibold mb-2">Nenhum item cadastrado</h3>
                <p className="text-muted-foreground text-sm">
                  Adicione itens para detalhar a proposta.
                </p>
              </div>
            )}
          </Card>
        </TabsContent>

        {/* Tab: Documentos */}
        <TabsContent value="documentos">
          <Card className="p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold">Documentos da Proposta</h3>
              <Button variant="outline" size="sm">
                <Download className="h-4 w-4 mr-2" />
                Gerar PDF
              </Button>
            </div>
            <div className="space-y-3">
              <div className="flex items-center justify-between p-3 bg-muted rounded-lg">
                <div className="flex items-center gap-3">
                  <FileText className="h-5 w-5 text-blue-500" />
                  <div>
                    <p className="text-sm font-medium">Carta Proposta</p>
                    <p className="text-xs text-muted-foreground">Documento principal da proposta</p>
                  </div>
                </div>
                <Badge variant={proposal.status !== 'rascunho' ? 'default' : 'secondary'}>
                  {proposal.status !== 'rascunho' ? 'Gerado' : 'Pendente'}
                </Badge>
              </div>
              <div className="flex items-center justify-between p-3 bg-muted rounded-lg">
                <div className="flex items-center gap-3">
                  <FileText className="h-5 w-5 text-green-500" />
                  <div>
                    <p className="text-sm font-medium">Planilha de Custos</p>
                    <p className="text-xs text-muted-foreground">Detalhamento de custos e BDI</p>
                  </div>
                </div>
                <Badge variant="secondary">Pendente</Badge>
              </div>
              <div className="flex items-center justify-between p-3 bg-muted rounded-lg">
                <div className="flex items-center gap-3">
                  <FileText className="h-5 w-5 text-orange-500" />
                  <div>
                    <p className="text-sm font-medium">Declaracoes</p>
                    <p className="text-xs text-muted-foreground">ME/EPP, Nao emprega menor, etc.</p>
                  </div>
                </div>
                <Badge variant="secondary">Pendente</Badge>
              </div>
            </div>
          </Card>
        </TabsContent>

        {/* Tab: Histórico */}
        <TabsContent value="historico">
          <Card className="p-6">
            <h3 className="font-semibold text-lg mb-4">Histórico de Status</h3>
            <div className="space-y-4">
              <div className="flex items-start gap-4 pb-4 border-b">
                <div className="p-2 bg-blue-100 rounded-full">
                  <FileCheck className="h-4 w-4 text-blue-600" />
                </div>
                <div className="flex-1">
                  <div className="flex items-center justify-between">
                    <p className="font-medium">Proposta Criada</p>
                    <p className="text-sm text-muted-foreground">
                      {proposal.created_at ? formatDate(proposal.created_at) : '-'}
                    </p>
                  </div>
                  <p className="text-sm text-muted-foreground">
                    Status inicial: Rascunho
                  </p>
                </div>
              </div>

              {proposal.updated_at && proposal.updated_at !== proposal.created_at && (
                <div className="flex items-start gap-4">
                  <div className="p-2 bg-green-100 rounded-full">
                    <RefreshCw className="h-4 w-4 text-green-600" />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center justify-between">
                      <p className="font-medium">Última Atualização</p>
                      <p className="text-sm text-muted-foreground">
                        {formatDate(proposal.updated_at)}
                      </p>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      Status atual: {proposal.status}
                    </p>
                  </div>
                </div>
              )}
            </div>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Modals */}
      <ProposalFormModal
        isOpen={isFormOpen}
        onClose={() => setIsFormOpen(false)}
        proposal={proposal}
        onSubmit={handleSubmitForm}
        isLoading={atualizarProposta.isPending}
      />

      <SubmitProposalDialog
        isOpen={isSubmitDialogOpen}
        onClose={() => setIsSubmitDialogOpen(false)}
        onConfirm={handleConfirmSubmit}
        proposalNumber={(proposal as any).numero_proposta}
        isSubmitting={submeterProposta.isPending}
      />
    </div>
  );
}
