'use client';

import { FolderOpen, FileText, Upload, HardDrive, FolderPlus, ChevronRight, Clock, AlertTriangle, CheckCircle, XCircle, FileSignature, TrendingUp, Users, Share2, Tag, Archive, Calendar } from 'lucide-react';
import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import Link from 'next/link';
import {
  formatFileSize,
  type Folder,
  type Document,
  type GEDStats,
  DOCUMENT_TYPES,
  DOCUMENT_CATEGORIES,
} from '@/types/generated/ged/conectaPROMóduloGED.schemas';

// Stats estendido - o backend retorna mais campos que o GEDStats base
interface PageGEDStats extends GEDStats {
  active_folders?: number;
  active_documents?: number;
  total_storage_bytes?: number;
  total_versions?: number;
  expired_documents?: number;
  total_signatures?: number;
  total_shares?: number;
  active_shares?: number;
  total_tags?: number;
}

import {
  DocumentApprovalDialog,
  DocumentSignatureDialog,
  EditDocumentDialog,
} from '@/components/ged';

// MIGRAÇÃO PARA HOOKS GERADOS - Imports dos hooks React Query do Orval
import { useGetGedStatsApiV1GedStatsGet } from '@/types/generated/ged/ged-estatísticas/ged-estatísticas';
import { useListFoldersApiV1GedFoldersGet } from '@/types/generated/ged/ged-pastas/ged-pastas';
import {
  useGetPendingApprovalApiV1GedDocumentsPendingApprovalGet,
  useGetPendingSignatureApiV1GedDocumentsPendingSignatureGet,
  useGetExpiringSoonApiV1GedDocumentsExpiringSoonGet,
} from '@/types/generated/ged/ged-documentos/ged-documentos';

export default function DocumentosPage() {
  // MIGRAÇÃO PARA HOOKS GERADOS - Substituir useState + useEffect + Promise.all por React Query hooks
  const { data: statsData, isLoading: loadingStats } = useGetGedStatsApiV1GedStatsGet();
  const { data: foldersData, isLoading: loadingFolders } = useListFoldersApiV1GedFoldersGet({
    page: 1,
    page_size: 100
  });
  const { data: pendingApprovals = [], isLoading: loadingApprovals } = useGetPendingApprovalApiV1GedDocumentsPendingApprovalGet();
  const { data: pendingSignatures = [], isLoading: loadingSignatures } = useGetPendingSignatureApiV1GedDocumentsPendingSignatureGet();
  const { data: expiringDocs = [], isLoading: loadingExpiring } = useGetExpiringSoonApiV1GedDocumentsExpiringSoonGet({
    days: 30
  });

  // Computed values
  const loading = loadingStats || loadingFolders || loadingApprovals || loadingSignatures || loadingExpiring;
  const stats = (statsData as PageGEDStats | undefined) ?? null;
  const rootFolders = foldersData?.items?.filter((f: Folder) => f.is_root) || [];

  // Dialogs
  const [approvalDialog, setApprovalDialog] = useState<{ open: boolean; document: Document | null }>({
    open: false,
    document: null,
  });
  const [signatureDialog, setSignatureDialog] = useState<{ open: boolean; document: Document | null }>({
    open: false,
    document: null,
  });
  const [editDialog, setEditDialog] = useState<{ open: boolean; document: Document | null }>({
    open: false,
    document: null,
  });

  const handleApprove = (doc: Document) => {
    setApprovalDialog({ open: true, document: doc });
  };

  const handleSign = (doc: Document) => {
    setSignatureDialog({ open: true, document: doc });
  };

  const handleEdit = (doc: Document) => {
    setEditDialog({ open: true, document: doc });
  };

  // MIGRAÇÃO PARA HOOKS GERADOS - Removido loadData(), os dados são carregados automaticamente pelos hooks React Query
  // React Query faz refetch automático, cache e invalidação de queries

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
      </div>
    );
  }

  // eslint-disable-next-line react-hooks/purity -- Date.now() needed for expiry calculation
  const now = Date.now();

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold">Gestão Eletrônica de Documentos</h1>
          <p className="text-muted-foreground">
            Sistema completo de gestão, versionamento e controle de documentos
          </p>
        </div>
        <div className="flex gap-2">
          <Link href="/modulos/documentos/arquivos">
            <Button variant="outline">
              <Upload className="h-4 w-4 mr-2" />
              Upload
            </Button>
          </Link>
          <Link href="/modulos/documentos/pastas">
            <Button>
              <FolderPlus className="h-4 w-4 mr-2" />
              Nova Pasta
            </Button>
          </Link>
        </div>
      </div>

      {/* Stats Cards - Linha 1 */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardContent className="flex items-center gap-4 pt-6">
            <div className="p-3 rounded-lg bg-blue-100 dark:bg-blue-900">
              <FolderOpen className="h-6 w-6 text-blue-600 dark:text-blue-300" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Pastas</p>
              <p className="font-data text-2xl font-semibold tabular-nums">{stats?.total_folders || 0}</p>
              <p className="text-xs text-muted-foreground">
                {stats?.active_folders || 0} ativas
              </p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="flex items-center gap-4 pt-6">
            <div className="p-3 rounded-lg bg-green-100 dark:bg-green-900">
              <FileText className="h-6 w-6 text-green-600 dark:text-green-300" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Documentos</p>
              <p className="font-data text-2xl font-semibold tabular-nums">{stats?.total_documents || 0}</p>
              <p className="text-xs text-muted-foreground">
                {stats?.active_documents || 0} ativos
              </p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="flex items-center gap-4 pt-6">
            <div className="p-3 rounded-lg bg-purple-100 dark:bg-purple-900">
              <HardDrive className="h-6 w-6 text-purple-600 dark:text-purple-300" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Armazenamento</p>
              <p className="font-data text-2xl font-semibold tabular-nums">{formatFileSize(stats?.total_storage_bytes || 0)}</p>
              <p className="text-xs text-muted-foreground">
                {stats?.total_versions || 0} versões
              </p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="flex items-center gap-4 pt-6">
            <div className="p-3 rounded-lg bg-orange-100 dark:bg-orange-900">
              <AlertTriangle className="h-6 w-6 text-orange-600 dark:text-orange-300" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">A vencer</p>
              <p className="font-data text-2xl font-semibold tabular-nums">{expiringDocs.length}</p>
              <p className="text-xs text-muted-foreground">
                {stats?.expired_documents || 0} expirados
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Stats Cards - Linha 2 */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardContent className="flex items-center gap-4 pt-6">
            <div className="p-3 rounded-lg bg-yellow-100 dark:bg-yellow-900">
              <CheckCircle className="h-6 w-6 text-yellow-600 dark:text-yellow-300" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Aprovações</p>
              <p className="font-data text-2xl font-semibold tabular-nums">{pendingApprovals.length}</p>
              <p className="text-xs text-muted-foreground">pendentes</p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="flex items-center gap-4 pt-6">
            <div className="p-3 rounded-lg bg-indigo-100 dark:bg-indigo-900">
              <FileSignature className="h-6 w-6 text-indigo-600 dark:text-indigo-300" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Assinaturas</p>
              <p className="font-data text-2xl font-semibold tabular-nums">{pendingSignatures.length}</p>
              <p className="text-xs text-muted-foreground">
                {stats?.total_signatures || 0} total
              </p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="flex items-center gap-4 pt-6">
            <div className="p-3 rounded-lg bg-pink-100 dark:bg-pink-900">
              <Share2 className="h-6 w-6 text-pink-600 dark:text-pink-300" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Compartilhamentos</p>
              <p className="font-data text-2xl font-semibold tabular-nums">{stats?.total_shares || 0}</p>
              <p className="text-xs text-muted-foreground">
                {stats?.active_shares || 0} ativos
              </p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="flex items-center gap-4 pt-6">
            <div className="p-3 rounded-lg bg-teal-100 dark:bg-teal-900">
              <Tag className="h-6 w-6 text-teal-600 dark:text-teal-300" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Tags</p>
              <p className="font-data text-2xl font-semibold tabular-nums">{stats?.total_tags || 0}</p>
              <p className="text-xs text-muted-foreground">organizacionais</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Tabs com conteúdo detalhado */}
      <Tabs defaultValue="overview" className="w-full">
        <TabsList className="grid w-full grid-cols-5">
          <TabsTrigger value="overview">Visão Geral</TabsTrigger>
          <TabsTrigger value="approvals">
            Aprovações
            {pendingApprovals.length > 0 && (
              <Badge variant="destructive" className="ml-2">
                {pendingApprovals.length}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="signatures">
            Assinaturas
            {pendingSignatures.length > 0 && (
              <Badge variant="destructive" className="ml-2">
                {pendingSignatures.length}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="expiring">
            A Vencer
            {expiringDocs.length > 0 && (
              <Badge variant="secondary" className="ml-2">
                {expiringDocs.length}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="folders">Pastas</TabsTrigger>
        </TabsList>

        {/* Visão Geral */}
        <TabsContent value="overview" className="space-y-4">
          {/* Quick Access */}
          <div className="grid gap-4 md:grid-cols-3">
            <Link href="/modulos/documentos/arquivos">
              <Card className="hover:bg-accent/50 transition-colors cursor-pointer">
                <CardContent className="flex items-center gap-4 pt-6">
                  <FileText className="h-10 w-10 text-blue-500" />
                  <div className="flex-1">
                    <h3 className="font-semibold">Arquivos</h3>
                    <p className="text-sm text-muted-foreground">Gerenciar documentos</p>
                  </div>
                  <ChevronRight className="h-5 w-5 text-muted-foreground" />
                </CardContent>
              </Card>
            </Link>

            <Link href="/modulos/documentos/pastas">
              <Card className="hover:bg-accent/50 transition-colors cursor-pointer">
                <CardContent className="flex items-center gap-4 pt-6">
                  <FolderOpen className="h-10 w-10 text-yellow-500" />
                  <div className="flex-1">
                    <h3 className="font-semibold">Pastas</h3>
                    <p className="text-sm text-muted-foreground">Organizar estrutura</p>
                  </div>
                  <ChevronRight className="h-5 w-5 text-muted-foreground" />
                </CardContent>
              </Card>
            </Link>

            <Link href="/modulos/documentos/kits">
              <Card className="hover:bg-accent/50 transition-colors cursor-pointer">
                <CardContent className="flex items-center gap-4 pt-6">
                  <FolderPlus className="h-10 w-10 text-green-500" />
                  <div className="flex-1">
                    <h3 className="font-semibold">Kits de Documentos</h3>
                    <p className="text-sm text-muted-foreground">Templates e kits</p>
                  </div>
                  <ChevronRight className="h-5 w-5 text-muted-foreground" />
                </CardContent>
              </Card>
            </Link>
          </div>

          {/* Distribuição por Tipo */}
          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Documentos por Tipo</CardTitle>
                <CardDescription>Distribuição dos documentos</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {stats?.documents_by_type && Object.entries(stats.documents_by_type).slice(0, 5).map(([type, count]) => {
                    const typeLabel = DOCUMENT_TYPES[type as keyof typeof DOCUMENT_TYPES] || type;
                    const percentage = stats.total_documents > 0 ? (count / stats.total_documents) * 100 : 0;

                    return (
                      <div key={type} className="space-y-1">
                        <div className="flex items-center justify-between text-sm">
                          <span>{typeLabel}</span>
                          <span className="font-medium">{count}</span>
                        </div>
                        <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-blue-500"
                            style={{ width: `${percentage}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Documentos por Status</CardTitle>
                <CardDescription>Estado atual dos documentos</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {stats?.documents_by_status && Object.entries(stats.documents_by_status).map(([status, count]) => {
                    const percentage = stats.total_documents > 0 ? (count / stats.total_documents) * 100 : 0;
                    const colors: Record<string, string> = {
                      rascunho: 'bg-gray-500',
                      pendente_aprovacao: 'bg-yellow-500',
                      aprovado: 'bg-green-500',
                      rejeitado: 'bg-red-500',
                      publicado: 'bg-blue-500',
                      arquivado: 'bg-purple-500',
                      expirado: 'bg-orange-500',
                    };

                    return (
                      <div key={status} className="space-y-1">
                        <div className="flex items-center justify-between text-sm">
                          <span className="capitalize">{status.replace('_', ' ')}</span>
                          <span className="font-medium">{count}</span>
                        </div>
                        <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                          <div
                            className={`h-full ${colors[status] || 'bg-gray-500'}`}
                            style={{ width: `${percentage}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Aprovações Pendentes */}
        <TabsContent value="approvals" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <CheckCircle className="h-5 w-5" />
                Documentos Pendentes de Aprovação
              </CardTitle>
              <CardDescription>
                {pendingApprovals.length} documento(s) aguardando sua aprovação
              </CardDescription>
            </CardHeader>
            <CardContent>
              {pendingApprovals.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  <CheckCircle className="h-12 w-12 mx-auto mb-2 opacity-50" />
                  <p>Nenhum documento pendente de aprovação</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {pendingApprovals.map((doc) => (
                    <div
                      key={doc.id}
                      className="flex items-center justify-between p-4 border rounded-lg hover:bg-accent/50 transition-colors"
                    >
                      <div className="flex-1">
                        <h4 className="font-medium">{doc.title}</h4>
                        <p className="text-sm text-muted-foreground">{doc.description}</p>
                        <div className="flex items-center gap-2 mt-2">
                          <Badge variant="outline">{doc.document_type}</Badge>
                          <Badge variant="outline">{doc.category}</Badge>
                          <span className="text-xs text-muted-foreground">
                            Criado em {new Date(doc.created_at).toLocaleDateString('pt-BR')}
                          </span>
                        </div>
                      </div>
                      <Button onClick={() => handleApprove(doc)}>
                        Revisar
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Assinaturas Pendentes */}
        <TabsContent value="signatures" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FileSignature className="h-5 w-5" />
                Documentos Pendentes de Assinatura
              </CardTitle>
              <CardDescription>
                {pendingSignatures.length} documento(s) aguardando sua assinatura
              </CardDescription>
            </CardHeader>
            <CardContent>
              {pendingSignatures.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  <FileSignature className="h-12 w-12 mx-auto mb-2 opacity-50" />
                  <p>Nenhum documento pendente de assinatura</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {pendingSignatures.map((doc) => (
                    <div
                      key={doc.id}
                      className="flex items-center justify-between p-4 border rounded-lg hover:bg-accent/50 transition-colors"
                    >
                      <div className="flex-1">
                        <h4 className="font-medium">{doc.title}</h4>
                        <p className="text-sm text-muted-foreground">{doc.description}</p>
                        <div className="flex items-center gap-2 mt-2">
                          <Badge variant="outline">{doc.document_type}</Badge>
                          {doc.signature_deadline && (
                            <Badge variant="destructive">
                              <Clock className="h-3 w-3 mr-1" />
                              Prazo: {new Date(doc.signature_deadline).toLocaleDateString('pt-BR')}
                            </Badge>
                          )}
                        </div>
                      </div>
                      <Button onClick={() => handleSign(doc)}>
                        Assinar
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Documentos a Vencer */}
        <TabsContent value="expiring" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Calendar className="h-5 w-5" />
                Documentos Expirando em 30 Dias
              </CardTitle>
              <CardDescription>
                {expiringDocs.length} documento(s) próximo(s) do vencimento
              </CardDescription>
            </CardHeader>
            <CardContent>
              {expiringDocs.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  <Calendar className="h-12 w-12 mx-auto mb-2 opacity-50" />
                  <p>Nenhum documento expirando próximo</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {expiringDocs.map((doc) => {
                    const daysUntilExpiry = doc.valid_until
                      ? Math.ceil((new Date(doc.valid_until).getTime() - now) / (1000 * 60 * 60 * 24))
                      : null;

                    return (
                      <div
                        key={doc.id}
                        className="flex items-center justify-between p-4 border rounded-lg hover:bg-accent/50 transition-colors"
                      >
                        <div className="flex-1">
                          <h4 className="font-medium">{doc.title}</h4>
                          <p className="text-sm text-muted-foreground">{doc.description}</p>
                          <div className="flex items-center gap-2 mt-2">
                            <Badge variant="outline">{doc.document_type}</Badge>
                            {daysUntilExpiry !== null && (
                              <Badge variant={daysUntilExpiry <= 7 ? 'destructive' : 'secondary'}>
                                <AlertTriangle className="h-3 w-3 mr-1" />
                                {daysUntilExpiry} dia(s) restante(s)
                              </Badge>
                            )}
                          </div>
                        </div>
                        <Button variant="outline" onClick={() => handleEdit(doc)}>
                          Editar
                        </Button>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Pastas Principais */}
        <TabsContent value="folders" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FolderOpen className="h-5 w-5" />
                Pastas Principais
              </CardTitle>
            </CardHeader>
            <CardContent>
              {rootFolders.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  <FolderOpen className="h-12 w-12 mx-auto mb-2 opacity-50" />
                  <p>Nenhuma pasta encontrada</p>
                  <Link href="/modulos/documentos/pastas">
                    <Button variant="outline" className="mt-4">
                      <FolderPlus className="h-4 w-4 mr-2" />
                      Criar Pasta
                    </Button>
                  </Link>
                </div>
              ) : (
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                  {rootFolders.map((folder) => (
                    <Link
                      key={folder.id}
                      href={`/modulos/documentos/pastas?id=${folder.id}`}
                    >
                      <Card className="hover:bg-accent/50 transition-colors cursor-pointer">
                        <CardContent className="pt-4">
                          <div className="flex items-start gap-3">
                            <div className="p-2 rounded-lg bg-yellow-100 dark:bg-yellow-900">
                              <FolderOpen className="h-6 w-6 text-yellow-600 dark:text-yellow-300" />
                            </div>
                            <div className="flex-1 min-w-0">
                              <h4 className="font-medium truncate">{folder.name}</h4>
                              <p className="text-xs text-muted-foreground truncate">
                                {folder.description || 'Sem descrição'}
                              </p>
                              <div className="flex items-center gap-2 mt-2">
                                <Badge variant="outline" className="text-xs">
                                  {folder.document_count} docs
                                </Badge>
                                <Badge variant="outline" className="text-xs">
                                  {formatFileSize(folder.total_size_bytes)}
                                </Badge>
                              </div>
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    </Link>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Dialogs */}
      {/* MIGRAÇÃO PARA HOOKS GERADOS - React Query faz invalidação automática, não precisa de callback loadData */}
      <DocumentApprovalDialog
        document={approvalDialog.document}
        open={approvalDialog.open}
        onClose={() => setApprovalDialog({ open: false, document: null })}
        onApproved={() => setApprovalDialog({ open: false, document: null })}
      />

      {signatureDialog.document && (
        <DocumentSignatureDialog
          documentId={signatureDialog.document.id}
          open={signatureDialog.open}
          onClose={() => {
            setSignatureDialog({ open: false, document: null });
          }}
          mode="sign"
        />
      )}

      <EditDocumentDialog
        document={editDialog.document}
        open={editDialog.open}
        onClose={() => setEditDialog({ open: false, document: null })}
        onUpdated={() => setEditDialog({ open: false, document: null })}
      />
    </div>
  );
}
