'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  FileText,
  Plus,
  Eye,
  Edit,
  Trash2,
  Send,
  Loader2,
  AlertCircle,
  RefreshCw,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Card } from '@/components/ui/card';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Alert } from '@/components/ui/alert';
import { ProposalStatusBadge } from '@/components/licitacoes/ProposalStatusBadge';
import {
  ProposalFilters,
  type ProposalFiltersState,
} from '@/components/licitacoes/ProposalFilters';
import { ProposalFormModal } from '@/components/licitacoes/ProposalFormModal';
import { SubmitProposalDialog } from '@/components/licitacoes/SubmitProposalDialog';
import {
  useListarPropostas,
  useCriarProposta,
  useAtualizarProposta,
  useRemoverProposta,
  useEnviarProposta,
} from '@/hooks/bidding/useProposals';
import type {
  BiddingProposalResponse,
  ListProposalsParams,
} from '@/services/bidding/proposals.service';
import type { ProposalFormData } from '@/components/licitacoes/ProposalFormModal';

export default function PropostasPage() {
  const router = useRouter();

  // Estados
  const [filters, setFilters] = useState<ProposalFiltersState>({});
  const [page, setPage] = useState(1);
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [isSubmitDialogOpen, setIsSubmitDialogOpen] = useState(false);
  const [editingProposal, setEditingProposal] =
    useState<BiddingProposalResponse | null>(null);
  const [proposalToDelete, setProposalToDelete] =
    useState<BiddingProposalResponse | null>(null);
  const [proposalToSubmit, setProposalToSubmit] =
    useState<BiddingProposalResponse | null>(null);

  // Query params
  const queryParams: ListProposalsParams = {
    ...filters,
    page,
    size: 20,
  };

  // Hooks
  const {
    data: proposalsData,
    isLoading,
    error,
    refetch,
  } = useListarPropostas(queryParams);
  const criarProposta = useCriarProposta();
  const atualizarProposta = useAtualizarProposta();
  const removerProposta = useRemoverProposta();
  const submeterProposta = useEnviarProposta();

  const proposals = proposalsData?.items || [];
  const totalPages = proposalsData?.pages || 1;

  // Handlers
  const handleOpenForm = (proposal?: BiddingProposalResponse) => {
    setEditingProposal(proposal || null);
    setIsFormOpen(true);
  };

  const handleCloseForm = () => {
    setIsFormOpen(false);
    setEditingProposal(null);
  };

  const handleSubmitForm = async (data: ProposalFormData) => {
    if (editingProposal) {
      await atualizarProposta.mutateAsync({
        id: editingProposal.id,
        data: data as unknown as import('@/services/bidding/proposals.service').BiddingProposalUpdate,
      });
    } else {
      await criarProposta.mutateAsync(data as unknown as import('@/services/bidding/proposals.service').BiddingProposalCreate);
    }
    handleCloseForm();
  };

  const handleOpenDeleteDialog = (proposal: BiddingProposalResponse) => {
    setProposalToDelete(proposal);
    setIsDeleteDialogOpen(true);
  };

  const handleConfirmDelete = async () => {
    if (!proposalToDelete) return;
    await removerProposta.mutateAsync(proposalToDelete.id);
    setIsDeleteDialogOpen(false);
    setProposalToDelete(null);
  };

  const handleOpenSubmitDialog = (proposal: BiddingProposalResponse) => {
    setProposalToSubmit(proposal);
    setIsSubmitDialogOpen(true);
  };

  const handleConfirmSubmit = async (observacoes?: string) => {
    if (!proposalToSubmit) return;
    await submeterProposta.mutateAsync({
      proposalId: proposalToSubmit.id,
      observacoes,
    });
    setIsSubmitDialogOpen(false);
    setProposalToSubmit(null);
  };

  const handleViewDetails = (proposalId: string) => {
    router.push(`/modulos/licitacoes/propostas/${proposalId}`);
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

  const canSubmit = (proposal: BiddingProposalResponse) => {
    return proposal.status === 'rascunho' || proposal.status === 'em_analise';
  };

  const canEdit = (proposal: BiddingProposalResponse) => {
    return (
      proposal.status === 'rascunho' ||
      proposal.status === 'em_analise' ||
      proposal.status === 'rejeitada'
    );
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-3xl font-bold tracking-tight">
            Propostas de Licitação
          </h1>
          <p className="text-muted-foreground">
            Gerencie propostas comerciais para editais
          </p>
        </div>
        <Button onClick={() => handleOpenForm()}>
          <Plus className="mr-2 h-4 w-4" />
          Nova Proposta
        </Button>
      </div>

      {/* Filtros */}
      <ProposalFilters
        filters={filters}
        onFiltersChange={setFilters}
        onClearFilters={() => setFilters({})}
      />

      {/* Tabela */}
      <Card className="p-6">
        {error && (
          <Alert variant="destructive" className="mb-4">
            <AlertCircle className="h-4 w-4" />
            <p>Erro ao carregar propostas. Tente novamente.</p>
          </Alert>
        )}

        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : proposals.length === 0 ? (
          <div className="text-center py-12">
            <FileText className="h-16 w-16 mx-auto mb-4 text-muted-foreground opacity-30" />
            <h3 className="text-lg font-semibold mb-2">
              Nenhuma proposta encontrada
            </h3>
            <p className="text-muted-foreground mb-4">
              Comece criando uma nova proposta
            </p>
            <Button onClick={() => handleOpenForm()}>
              <Plus className="mr-2 h-4 w-4" />
              Nova Proposta
            </Button>
          </div>
        ) : (
          <>
            <div className="border rounded-lg overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Número</TableHead>
                    <TableHead>Edital</TableHead>
                    <TableHead>Razão Social</TableHead>
                    <TableHead className="text-right">Valor Proposto</TableHead>
                    <TableHead>Data Submissão</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-center w-[180px]">
                      Ações
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {proposals.map((proposal) => (
                    <TableRow key={proposal.id}>
                      <TableCell className="font-medium">
                        {(proposal as any).numero_proposta || 'N/A'}
                      </TableCell>
                      <TableCell>
                        {proposal.tender_id?.substring(0, 8)}...
                      </TableCell>
                      <TableCell>{String(proposal.razao_social || '')}</TableCell>
                      <TableCell className="text-right font-semibold">
                        {formatCurrency(Number(proposal.valor_global) || 0)}
                      </TableCell>
                      <TableCell>
                        {proposal.created_at
                          ? formatDate(proposal.created_at)
                          : '-'}
                      </TableCell>
                      <TableCell>
                        <ProposalStatusBadge status={proposal.status as any} />
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center justify-center gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleViewDetails(proposal.id)}
                            title="Ver detalhes"
                          >
                            <Eye className="h-4 w-4" />
                          </Button>

                          {canSubmit(proposal) && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleOpenSubmitDialog(proposal)}
                              title="Submeter proposta"
                            >
                              <Send className="h-4 w-4" />
                            </Button>
                          )}

                          {canEdit(proposal) && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleOpenForm(proposal)}
                              title="Editar"
                            >
                              <Edit className="h-4 w-4" />
                            </Button>
                          )}

                          {proposal.status === 'rascunho' && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleOpenDeleteDialog(proposal)}
                              className="text-destructive hover:text-destructive"
                              title="Remover"
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>

            {/* Paginação */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-4">
                <p className="text-sm text-muted-foreground">
                  Página {page} de {totalPages}
                </p>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page === 1}
                  >
                    Anterior
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    disabled={page === totalPages}
                  >
                    Próxima
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </Card>

      {/* Modals */}
      <ProposalFormModal
        isOpen={isFormOpen}
        onClose={handleCloseForm}
        proposal={editingProposal}
        onSubmit={handleSubmitForm}
        isLoading={criarProposta.isPending || atualizarProposta.isPending}
      />

      <SubmitProposalDialog
        isOpen={isSubmitDialogOpen}
        onClose={() => setIsSubmitDialogOpen(false)}
        onConfirm={handleConfirmSubmit}
        proposalNumber={(proposalToSubmit as any)?.numero_proposta}
        isSubmitting={submeterProposta.isPending}
      />

      <AlertDialog
        open={isDeleteDialogOpen}
        onOpenChange={setIsDeleteDialogOpen}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Confirmar Exclusão</AlertDialogTitle>
            <AlertDialogDescription>
              Tem certeza que deseja remover a proposta{' '}
              <strong>{(proposalToDelete as any)?.numero_proposta}</strong>?
              <br />
              Esta ação não pode ser desfeita.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={removerProposta.isPending}>
              Cancelar
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={handleConfirmDelete}
              disabled={removerProposta.isPending}
              className="bg-destructive hover:bg-destructive/90"
            >
              {removerProposta.isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Removendo...
                </>
              ) : (
                'Remover Proposta'
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
