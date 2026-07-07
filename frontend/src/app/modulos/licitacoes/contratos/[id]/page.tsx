'use client';

import { useParams, useRouter } from 'next/navigation';
import { useState } from 'react';
import {
  FileSignature,
  ArrowLeft,
  Edit,
  Plus,
  RefreshCw,
  FileText,
  Calendar,
  DollarSign,
  Building2,
  AlertCircle,
  CheckCircle2,
  ExternalLink,
  Upload,
  BarChart3,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  useBuscarContrato,
  useAditivar,
  useListarMedicoes,
  useCriarMedicao,
  useAprovarMedicao,
} from '@/hooks/bidding/useContracts';
import { useListarDocumentos } from '@/hooks/bidding/useDocuments';
import { ContractStatusBadge } from '@/components/licitacoes/ContractStatusBadge';
import { ContractAddendumModal } from '@/components/licitacoes/ContractAddendumModal';
import { formatCurrency, formatDate } from '@/lib/utils';

export default function ContratoDetalhePage() {
  const params = useParams();
  const router = useRouter();
  const contractId = params.id as string;

  const { data: contrato, isLoading, error, refetch } = useBuscarContrato(contractId);
  const aditivarMutation = useAditivar();

  const [addendumOpen, setAddendumOpen] = useState(false);
  const [novaMedicaoOpen, setNovaMedicaoOpen] = useState(false);
  const [aprovarMedicaoOpen, setAprovarMedicaoOpen] = useState(false);
  const [medicaoSelecionada, setMedicaoSelecionada] = useState<any>(null);

  // Medições hooks
  const { data: medicoes, isLoading: medicoesLoading } = useListarMedicoes(contractId);
  const criarMedicaoMutation = useCriarMedicao();
  const aprovarMedicaoMutation = useAprovarMedicao();

  // Documentos hooks
  const { data: documentos, isLoading: documentosLoading } = useListarDocumentos();

  // Nova Medição form state
  const [medicaoForm, setMedicaoForm] = useState({
    competencia: '',
    periodo_inicio: '',
    periodo_fim: '',
    valor_bruto: '',
  });

  // Aprovar Medição form state
  const [aprovarForm, setAprovarForm] = useState({
    observacoes: '',
  });

  const medicoesList: any[] = Array.isArray(medicoes) ? medicoes : [];
  const documentosList: any[] = Array.isArray(documentos) ? documentos : [];

  const getMedicaoStatusBadge = (status: string) => {
    const variants: Record<string, { label: string; className: string }> = {
      rascunho: { label: 'Rascunho', className: 'bg-gray-100 text-gray-700 border-gray-200' },
      enviada: { label: 'Enviada', className: 'bg-blue-100 text-blue-700 border-blue-200' },
      em_analise: { label: 'Em Análise', className: 'bg-yellow-100 text-yellow-700 border-yellow-200' },
      aprovada: { label: 'Aprovada', className: 'bg-green-100 text-green-700 border-green-200' },
      paga: { label: 'Paga', className: 'bg-purple-100 text-purple-700 border-purple-200' },
    };
    const v = variants[status] || { label: status, className: 'bg-gray-100 text-gray-700 border-gray-200' };
    return (
      <Badge variant="outline" className={v.className}>
        {v.label}
      </Badge>
    );
  };

  const handleCriarMedicao = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await criarMedicaoMutation.mutateAsync({
        contract_id: contractId,
        numero_medicao: medicoesList.length + 1,
        competencia: medicaoForm.competencia,
        periodo_inicio: medicaoForm.periodo_inicio || undefined,
        periodo_fim: medicaoForm.periodo_fim || undefined,
        valor_bruto: parseFloat(medicaoForm.valor_bruto),
      });
      setNovaMedicaoOpen(false);
      setMedicaoForm({ competencia: '', periodo_inicio: '', periodo_fim: '', valor_bruto: '' });
      refetch();
    } catch (err) {
      // Error handled by mutation
    }
  };

  const handleAprovarMedicao = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!medicaoSelecionada) return;
    try {
      await aprovarMedicaoMutation.mutateAsync({
        measurementId: medicaoSelecionada.id,
        contractId: contractId,
        observacoes: aprovarForm.observacoes || undefined,
      });
      setAprovarMedicaoOpen(false);
      setMedicaoSelecionada(null);
      setAprovarForm({ observacoes: '' });
      refetch();
    } catch (err) {
      // Error handled by mutation
    }
  };

  const openAprovarDialog = (medicao: any) => {
    setMedicaoSelecionada(medicao);
    setAprovarForm({ observacoes: '' });
    setAprovarMedicaoOpen(true);
  };

  const handleAddendumSubmit = async (data: any) => {
    try {
      await aditivarMutation.mutateAsync(data);
      setAddendumOpen(false);
      refetch();
    } catch (err) {
      // Error handled by mutation
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    );
  }

  if (error || !contrato) {
    return (
      <div className="space-y-6">
        <Button variant="ghost" onClick={() => router.back()}>
          <ArrowLeft className="h-4 w-4 mr-2" />
          Voltar
        </Button>
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-destructive" />
          <p className="text-sm text-destructive flex-1">Erro ao carregar contrato</p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Tentar novamente
          </Button>
        </div>
      </div>
    );
  }

  const c = contrato as any;
  const aditivos = c.aditivos || [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <Button variant="ghost" onClick={() => router.back()} className="mb-2">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Voltar
          </Button>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <FileSignature className="h-6 w-6" />
            Contrato {c.numero_contrato}
          </h1>
          <p className="text-muted-foreground">{c.orgao_contratante}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => refetch()} disabled={isLoading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
            Atualizar
          </Button>
          <Button variant="outline" onClick={() => router.push(`/modulos/licitacoes/contratos/${contractId}/editar`)}>
            <Edit className="h-4 w-4 mr-2" />
            Editar
          </Button>
        </div>
      </div>

      <Tabs defaultValue="dados" className="space-y-4">
        <TabsList>
          <TabsTrigger value="dados">Dados Gerais</TabsTrigger>
          <TabsTrigger value="aditivos">
            Aditivos
            {aditivos.length > 0 && (
              <Badge variant="secondary" className="ml-2">
                {aditivos.length}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="medicoes">
            Medições
            {medicoesList.length > 0 && (
              <Badge variant="secondary" className="ml-2">
                {medicoesList.length}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="documentos">Documentos</TabsTrigger>
        </TabsList>

        {/* Dados Gerais */}
        <TabsContent value="dados" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Informações do Contrato</CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-muted-foreground">Número do Contrato</p>
                <p className="font-medium">{c.numero_contrato}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Status</p>
                <div className="mt-1">
                  <ContractStatusBadge status={c.status || 'vigente'} />
                </div>
              </div>
              <div className="col-span-2">
                <p className="text-sm text-muted-foreground">Órgão Contratante</p>
                <p className="font-medium flex items-center gap-2">
                  <Building2 className="h-4 w-4" />
                  {c.orgao_contratante}
                </p>
              </div>
              <div className="col-span-2">
                <p className="text-sm text-muted-foreground">Objeto</p>
                <p className="font-medium">{c.objeto}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Valor Total</p>
                <p className="font-medium text-lg flex items-center gap-2">
                  <DollarSign className="h-5 w-5 text-green-600" />
                  {formatCurrency(c.valor_total || 0)}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">ID da Proposta</p>
                <p className="font-medium text-xs">{c.proposta_id || 'N/A'}</p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Datas e Vigência</CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <p className="text-sm text-muted-foreground">Data de Assinatura</p>
                <p className="font-medium flex items-center gap-2">
                  <Calendar className="h-4 w-4" />
                  {formatDate(c.data_assinatura)}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Data de Início</p>
                <p className="font-medium flex items-center gap-2">
                  <Calendar className="h-4 w-4 text-green-600" />
                  {formatDate(c.data_inicio)}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Data de Término</p>
                <p className="font-medium flex items-center gap-2">
                  <Calendar className="h-4 w-4 text-red-600" />
                  {formatDate(c.data_fim)}
                </p>
              </div>
            </CardContent>
          </Card>

          {c.observacoes && (
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Observações</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm">{c.observacoes}</p>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Aditivos */}
        <TabsContent value="aditivos" className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">
              {aditivos.length} aditivo(s) cadastrado(s)
            </p>
            <Button onClick={() => setAddendumOpen(true)}>
              <Plus className="h-4 w-4 mr-2" />
              Novo Aditivo
            </Button>
          </div>

          <Card>
            <CardContent className="p-0">
              {aditivos.length === 0 ? (
                <div className="text-center py-12 text-muted-foreground">
                  <FileText className="h-16 w-16 mx-auto mb-4 opacity-50" />
                  <h3 className="text-lg font-medium">Nenhum aditivo cadastrado</h3>
                  <p className="mt-2">Crie um aditivo para registrar alterações no contrato</p>
                  <Button className="mt-4" onClick={() => setAddendumOpen(true)}>
                    <Plus className="h-4 w-4 mr-2" />
                    Novo Aditivo
                  </Button>
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Tipo</TableHead>
                      <TableHead>Data</TableHead>
                      <TableHead>Valor/Prazo</TableHead>
                      <TableHead>Justificativa</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {aditivos.map((aditivo: any, index: number) => (
                      <TableRow key={index}>
                        <TableCell>
                          <Badge variant="outline">
                            {aditivo.tipo_aditivo === 'prazo' && 'Prazo'}
                            {aditivo.tipo_aditivo === 'valor' && 'Valor'}
                            {aditivo.tipo_aditivo === 'escopo' && 'Escopo'}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-sm">
                          {formatDate(aditivo.data_aditivo)}
                        </TableCell>
                        <TableCell className="text-sm font-medium">
                          {aditivo.tipo_aditivo === 'valor' && formatCurrency(aditivo.novo_valor || 0)}
                          {aditivo.tipo_aditivo === 'prazo' && formatDate(aditivo.nova_data_fim)}
                          {aditivo.tipo_aditivo === 'escopo' && '-'}
                        </TableCell>
                        <TableCell className="text-sm max-w-md truncate">
                          {aditivo.justificativa}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Medições */}
        <TabsContent value="medicoes" className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-semibold">Medições</h2>
              {medicoesList.length > 0 && (
                <Badge variant="secondary">{medicoesList.length}</Badge>
              )}
            </div>
            <Button onClick={() => setNovaMedicaoOpen(true)}>
              <Plus className="h-4 w-4 mr-2" />
              Nova Medição
            </Button>
          </div>

          <Card>
            <CardContent className="p-0">
              {medicoesLoading ? (
                <div className="flex items-center justify-center py-12">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
                </div>
              ) : medicoesList.length === 0 ? (
                <div className="text-center py-12 text-muted-foreground">
                  <BarChart3 className="h-16 w-16 mx-auto mb-4 opacity-50" />
                  <h3 className="text-lg font-medium">Nenhuma medição cadastrada</h3>
                  <p className="mt-2">Crie uma medição para registrar o andamento do contrato</p>
                  <Button className="mt-4" onClick={() => setNovaMedicaoOpen(true)}>
                    <Plus className="h-4 w-4 mr-2" />
                    Nova Medição
                  </Button>
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Número</TableHead>
                      <TableHead>Competência</TableHead>
                      <TableHead>Período</TableHead>
                      <TableHead className="text-right">Valor Bruto</TableHead>
                      <TableHead className="text-right">Valor Líquido</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right">Ações</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {medicoesList.map((medicao: any) => (
                      <TableRow key={medicao.id}>
                        <TableCell className="font-medium">
                          #{medicao.numero_medicao}
                        </TableCell>
                        <TableCell className="text-sm">
                          {medicao.competencia}
                        </TableCell>
                        <TableCell className="text-sm">
                          {medicao.periodo_inicio && medicao.periodo_fim
                            ? `${formatDate(medicao.periodo_inicio)} - ${formatDate(medicao.periodo_fim)}`
                            : medicao.periodo_inicio
                            ? formatDate(medicao.periodo_inicio)
                            : '-'}
                        </TableCell>
                        <TableCell className="text-sm text-right font-medium">
                          {formatCurrency(medicao.valor_bruto || 0)}
                        </TableCell>
                        <TableCell className="text-sm text-right font-medium">
                          {formatCurrency(medicao.valor_liquido || 0)}
                        </TableCell>
                        <TableCell>
                          {getMedicaoStatusBadge(medicao.status)}
                        </TableCell>
                        <TableCell className="text-right">
                          {(medicao.status === 'enviada' || medicao.status === 'em_analise') && (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => openAprovarDialog(medicao)}
                            >
                              <CheckCircle2 className="h-4 w-4 mr-1" />
                              Aprovar
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Documentos */}
        <TabsContent value="documentos" className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-semibold">Documentos</h2>
              {documentosList.length > 0 && (
                <Badge variant="secondary">{documentosList.length}</Badge>
              )}
            </div>
            <Button
              variant="outline"
              onClick={() => router.push('/modulos/licitacoes/documentos')}
            >
              <Upload className="h-4 w-4 mr-2" />
              Gerenciar Documentos
            </Button>
          </div>

          {documentosLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
            </div>
          ) : documentosList.length > 0 ? (
            <Card>
              <CardContent className="p-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Tipo</TableHead>
                      <TableHead>Nome</TableHead>
                      <TableHead>Validade</TableHead>
                      <TableHead>Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {documentosList.map((doc: any) => (
                      <TableRow key={doc.id}>
                        <TableCell>
                          <Badge variant="outline">
                            {(doc.tipo_documento || '').replace(/_/g, ' ')}
                          </Badge>
                        </TableCell>
                        <TableCell className="font-medium text-sm">
                          {doc.nome || doc.tipo_documento || '-'}
                        </TableCell>
                        <TableCell className="text-sm">
                          {doc.data_validade ? formatDate(doc.data_validade) : 'Sem validade'}
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant="outline"
                            className={
                              doc.status === 'vigente'
                                ? 'bg-green-100 text-green-700 border-green-200'
                                : doc.status === 'vencido'
                                ? 'bg-red-100 text-red-700 border-red-200'
                                : doc.status === 'a_vencer'
                                ? 'bg-yellow-100 text-yellow-700 border-yellow-200'
                                : 'bg-gray-100 text-gray-700 border-gray-200'
                            }
                          >
                            {doc.status || 'N/A'}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardContent className="py-12">
                <div className="text-center text-muted-foreground">
                  <FileText className="h-16 w-16 mx-auto mb-4 opacity-50" />
                  <h3 className="text-lg font-medium">Documentos da Empresa</h3>
                  <p className="mt-2 max-w-md mx-auto">
                    Gerencie os documentos de habilitação da empresa na página de Documentos.
                    Documentos vigentes são compartilhados entre todos os contratos.
                  </p>
                  <Button
                    className="mt-4"
                    variant="outline"
                    onClick={() => router.push('/modulos/licitacoes/documentos')}
                  >
                    <ExternalLink className="h-4 w-4 mr-2" />
                    Ir para Documentos
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>

      {/* Modal de Aditivo */}
      <ContractAddendumModal
        isOpen={addendumOpen}
        onClose={() => setAddendumOpen(false)}
        onSubmit={handleAddendumSubmit}
        contractId={contractId}
        isLoading={aditivarMutation.isPending}
      />

      {/* Modal Nova Medição */}
      <Dialog open={novaMedicaoOpen} onOpenChange={setNovaMedicaoOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Nova Medição</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleCriarMedicao} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="competencia">Competência *</Label>
              <Input
                id="competencia"
                type="month"
                value={medicaoForm.competencia}
                onChange={(e) =>
                  setMedicaoForm({ ...medicaoForm, competencia: e.target.value })
                }
                required
              />
              <p className="text-xs text-muted-foreground">
                Mês/ano de referência da medição
              </p>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="periodo_inicio">Período Início</Label>
                <Input
                  id="periodo_inicio"
                  type="date"
                  value={medicaoForm.periodo_inicio}
                  onChange={(e) =>
                    setMedicaoForm({ ...medicaoForm, periodo_inicio: e.target.value })
                  }
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="periodo_fim">Período Fim</Label>
                <Input
                  id="periodo_fim"
                  type="date"
                  value={medicaoForm.periodo_fim}
                  onChange={(e) =>
                    setMedicaoForm({ ...medicaoForm, periodo_fim: e.target.value })
                  }
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="valor_bruto">Valor Bruto (R$) *</Label>
              <Input
                id="valor_bruto"
                type="number"
                step="0.01"
                min="0"
                value={medicaoForm.valor_bruto}
                onChange={(e) =>
                  setMedicaoForm({ ...medicaoForm, valor_bruto: e.target.value })
                }
                required
                placeholder="0,00"
              />
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setNovaMedicaoOpen(false)}
                disabled={criarMedicaoMutation.isPending}
              >
                Cancelar
              </Button>
              <Button type="submit" disabled={criarMedicaoMutation.isPending}>
                <Plus className="h-4 w-4 mr-2" />
                {criarMedicaoMutation.isPending ? 'Criando...' : 'Criar Medição'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Modal Aprovar Medição */}
      <Dialog open={aprovarMedicaoOpen} onOpenChange={setAprovarMedicaoOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Aprovar Medição</DialogTitle>
          </DialogHeader>
          {medicaoSelecionada && (
            <form onSubmit={handleAprovarMedicao} className="space-y-4">
              <div className="bg-muted/50 rounded-lg p-4 space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Medição</span>
                  <span className="font-medium">#{medicaoSelecionada.numero_medicao}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Competência</span>
                  <span className="font-medium">{medicaoSelecionada.competencia}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Valor Bruto</span>
                  <span className="font-medium">{formatCurrency(medicaoSelecionada.valor_bruto || 0)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Valor Líquido</span>
                  <span className="font-medium">{formatCurrency(medicaoSelecionada.valor_liquido || 0)}</span>
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="aprovar_observacoes">Observações</Label>
                <Textarea
                  id="aprovar_observacoes"
                  value={aprovarForm.observacoes}
                  onChange={(e) =>
                    setAprovarForm({ ...aprovarForm, observacoes: e.target.value })
                  }
                  placeholder="Observações sobre a aprovação (opcional)"
                  rows={3}
                />
              </div>
              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setAprovarMedicaoOpen(false);
                    setMedicaoSelecionada(null);
                  }}
                  disabled={aprovarMedicaoMutation.isPending}
                >
                  Cancelar
                </Button>
                <Button type="submit" disabled={aprovarMedicaoMutation.isPending}>
                  <CheckCircle2 className="h-4 w-4 mr-2" />
                  {aprovarMedicaoMutation.isPending ? 'Aprovando...' : 'Confirmar Aprovação'}
                </Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
