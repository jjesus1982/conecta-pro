'use client';

import {
  FileText,
  Search,
  RefreshCw,
  Upload,
  MoreHorizontal,
  Trash2,
  AlertCircle,
  CheckCircle2,
  XCircle,
  Clock,
  Folder,
  Building2,
} from 'lucide-react';
import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ConfirmModal } from '@/components/ui/modal';
import { toast } from 'sonner';
import {
  useListarDocumentos,
  useCriarDocumento,
  useRemoverDocumento,
} from '@/hooks/bidding/useDocuments';
import { DocumentUploadModal } from '@/components/licitacoes/DocumentUploadModal';
import { DocumentStatusBadge } from '@/components/licitacoes/DocumentStatusBadge';
import { formatDate } from '@/lib/utils';

export default function DocumentosPage() {
  const [search, setSearch] = useState('');
  const [tipoFilter, setTipoFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [page, setPage] = useState(0);
  const pageSize = 20;

  const { data: documentosData, isLoading, error, refetch } = useListarDocumentos({
    tipo: tipoFilter !== 'all' ? tipoFilter : undefined,
    status: statusFilter !== 'all' ? statusFilter : undefined,
  });

  const uploadMutation = useCriarDocumento();
  const removerMutation = useRemoverDocumento();

  const [uploadOpen, setUploadOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmAction, setConfirmAction] = useState<{
    title: string;
    message: string;
    action: () => Promise<void>;
    variant: 'danger' | 'warning' | 'info';
  } | null>(null);

  const documentos = (documentosData as any)?.items || (Array.isArray(documentosData) ? documentosData : []);
  const total = (documentosData as any)?.total || documentos.length;

  // Stats
  const stats = {
    total: documentos.length,
    aprovados: documentos.filter((d: any) => d.status === 'aprovado').length,
    pendentes: documentos.filter((d: any) => d.status === 'pendente').length,
    rejeitados: documentos.filter((d: any) => d.status === 'rejeitado').length,
  };

  const openConfirm = (
    title: string,
    message: string,
    action: () => Promise<void>,
    variant: 'danger' | 'warning' | 'info' = 'warning'
  ) => {
    setConfirmAction({ title, message, action, variant });
    setConfirmOpen(true);
  };

  const handleUploadSubmit = async (data: any) => {
    try {
      await uploadMutation.mutateAsync(data);
      setUploadOpen(false);
    } catch (err) {
      // Error handled by mutation
    }
  };


  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <Folder className="h-6 w-6" />
            Documentos de Licitação
          </h1>
          <p className="text-muted-foreground">Gestão de documentos de editais e da empresa</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => refetch()} disabled={isLoading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
            Atualizar
          </Button>
          <Button onClick={() => setUploadOpen(true)}>
            <Upload className="h-4 w-4 mr-2" />
            Upload Documento
          </Button>
        </div>
      </div>

      <Tabs defaultValue="empresa" className="space-y-4">
        <TabsList>
          <TabsTrigger value="editais">Documentos de Editais</TabsTrigger>
          <TabsTrigger value="empresa">
            Documentos da Empresa
            {stats.total > 0 && (
              <Badge variant="secondary" className="ml-2">
                {stats.total}
              </Badge>
            )}
          </TabsTrigger>
        </TabsList>

        {/* Documentos de Editais */}
        <TabsContent value="editais" className="space-y-4">
          <Card>
            <CardContent className="py-12">
              <div className="text-center text-muted-foreground">
                <FileText className="h-16 w-16 mx-auto mb-4 opacity-50" />
                <h3 className="text-lg font-medium">Documentos de Editais</h3>
                <p className="mt-2">
                  Visualize e gerencie documentos exigidos em editais específicos
                </p>
                <p className="mt-2 text-sm">
                  Acesse a página de cada edital para ver os documentos exigidos
                </p>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Documentos da Empresa */}
        <TabsContent value="empresa" className="space-y-4">
          {/* Stats */}
          <div className="grid gap-4 md:grid-cols-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Total</CardTitle>
                <FileText className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="font-data text-2xl font-semibold tabular-nums">{stats.total}</div>
                <p className="text-xs text-muted-foreground">Documentos cadastrados</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Aprovados</CardTitle>
                <CheckCircle2 className="h-4 w-4 text-green-600" />
              </CardHeader>
              <CardContent>
                <div className="font-data text-2xl font-semibold tabular-nums text-green-600">{stats.aprovados}</div>
                <p className="text-xs text-muted-foreground">Validados</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Pendentes</CardTitle>
                <Clock className="h-4 w-4 text-yellow-600" />
              </CardHeader>
              <CardContent>
                <div className="font-data text-2xl font-semibold tabular-nums text-yellow-600">{stats.pendentes}</div>
                <p className="text-xs text-muted-foreground">Aguardando validação</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Rejeitados</CardTitle>
                <XCircle className="h-4 w-4 text-red-600" />
              </CardHeader>
              <CardContent>
                <div className="font-data text-2xl font-semibold tabular-nums text-red-600">{stats.rejeitados}</div>
                <p className="text-xs text-muted-foreground">Precisam correção</p>
              </CardContent>
            </Card>
          </div>

          {/* Filters */}
          <Card>
            <CardContent className="pt-6">
              <div className="flex flex-col md:flex-row gap-4">
                <div className="flex-1 relative">
                  <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    value={search}
                    onChange={(e) => {
                      setSearch(e.target.value);
                      setPage(0);
                    }}
                    placeholder="Buscar por nome, tipo..."
                    className="pl-10"
                  />
                </div>
                <Select
                  value={tipoFilter}
                  onValueChange={(v) => {
                    setTipoFilter(v);
                    setPage(0);
                  }}
                >
                  <SelectTrigger className="w-[200px]">
                    <SelectValue placeholder="Tipo" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos os tipos</SelectItem>
                    <SelectItem value="contrato_social">Contrato Social</SelectItem>
                    <SelectItem value="estatuto">Estatuto Social</SelectItem>
                    <SelectItem value="ata_eleicao">Ata de Eleição</SelectItem>
                    <SelectItem value="procuracao">Procuração</SelectItem>
                    <SelectItem value="balanco_patrimonial">Balanço Patrimonial</SelectItem>
                    <SelectItem value="alvara">Alvará</SelectItem>
                    <SelectItem value="outros">Outros</SelectItem>
                  </SelectContent>
                </Select>
                <Select
                  value={statusFilter}
                  onValueChange={(v) => {
                    setStatusFilter(v);
                    setPage(0);
                  }}
                >
                  <SelectTrigger className="w-[180px]">
                    <SelectValue placeholder="Status" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos os status</SelectItem>
                    <SelectItem value="pendente">Pendente</SelectItem>
                    <SelectItem value="aprovado">Aprovado</SelectItem>
                    <SelectItem value="rejeitado">Rejeitado</SelectItem>
                    <SelectItem value="vencido">Vencido</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>

          {/* Error */}
          {error && (
            <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
              <AlertCircle className="h-5 w-5 text-destructive" />
              <p className="text-sm text-destructive flex-1">Erro ao carregar documentos</p>
              <Button variant="outline" size="sm" onClick={() => refetch()}>
                Tentar novamente
              </Button>
            </div>
          )}

          {/* Table */}
          <Card>
            <CardContent className="p-0">
              {isLoading ? (
                <div className="flex items-center justify-center py-12">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
                </div>
              ) : documentos.length === 0 ? (
                <div className="text-center py-12 text-muted-foreground">
                  <Building2 className="h-16 w-16 mx-auto mb-4 opacity-50" />
                  <h3 className="text-lg font-medium">Nenhum documento encontrado</h3>
                  <p className="mt-2">Faça upload de documentos da empresa para começar</p>
                  <Button className="mt-4" onClick={() => setUploadOpen(true)}>
                    <Upload className="h-4 w-4 mr-2" />
                    Upload Documento
                  </Button>
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Tipo</TableHead>
                      <TableHead>Nome</TableHead>
                      <TableHead>Data Upload</TableHead>
                      <TableHead>Validade</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="w-[80px]">Ações</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {documentos.map((documento: any) => (
                      <TableRow key={documento.id}>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <FileText className="h-4 w-4 text-muted-foreground" />
                            <span className="text-sm">{documento.tipo_documento}</span>
                          </div>
                        </TableCell>
                        <TableCell>
                          <div className="font-medium">{documento.nome}</div>
                          {documento.observacoes && (
                            <p className="text-xs text-muted-foreground truncate max-w-xs">
                              {documento.observacoes}
                            </p>
                          )}
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {formatDate(documento.created_at || documento.data_upload)}
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {documento.data_validade ? formatDate(documento.data_validade) : 'Sem validade'}
                        </TableCell>
                        <TableCell>
                          <DocumentStatusBadge status={documento.status || 'pendente'} />
                        </TableCell>
                        <TableCell>
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button variant="ghost" size="icon" className="h-8 w-8">
                                <MoreHorizontal className="h-4 w-4" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              <DropdownMenuItem
                                className="text-destructive"
                                onClick={() =>
                                  openConfirm(
                                    'Deletar Documento',
                                    `Deletar "${documento.nome}" permanentemente?`,
                                    () => removerMutation.mutateAsync(documento.id),
                                    'danger'
                                  )
                                }
                              >
                                <Trash2 className="h-4 w-4 mr-2" />
                                Deletar
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>

          {/* Pagination */}
          {total > pageSize && (
            <div className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">
                Mostrando {page * pageSize + 1}-{Math.min((page + 1) * pageSize, total)} de {total}
              </p>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage(Math.max(0, page - 1))}
                  disabled={page === 0}
                >
                  Anterior
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage(page + 1)}
                  disabled={(page + 1) * pageSize >= total}
                >
                  Próximo
                </Button>
              </div>
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* Modals */}
      <DocumentUploadModal
        isOpen={uploadOpen}
        onClose={() => setUploadOpen(false)}
        onSubmit={handleUploadSubmit}
        isLoading={uploadMutation.isPending}
      />

      {confirmAction && (
        <ConfirmModal
          isOpen={confirmOpen}
          onClose={() => setConfirmOpen(false)}
          onConfirm={async () => {
            await confirmAction.action();
            setConfirmOpen(false);
          }}
          title={confirmAction.title}
          message={confirmAction.message}
          variant={confirmAction.variant}
          isLoading={removerMutation.isPending}
        />
      )}
    </div>
  );
}
