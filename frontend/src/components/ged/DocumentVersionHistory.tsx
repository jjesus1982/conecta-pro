'use client';

import { Clock, Download, Archive, CheckCircle2, XCircle, FileText, User, Calendar, ArrowUpDown, Eye } from 'lucide-react';
import { msgFromDetail } from '@/lib/string';
import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { toast } from 'sonner';
import { documentVersionService } from '@/services/ged/documentVersionService';
import { formatFileSize } from '@/utils/file-helpers';
import type { DocumentVersionResponse } from '@/types/generated/ged/schemas/documentVersionResponse';

interface DocumentVersionHistoryProps {
  documentId: string;
  open: boolean;
  onClose: () => void;
}

export function DocumentVersionHistory({
  documentId,
  open,
  onClose,
}: DocumentVersionHistoryProps) {
  const [versions, setVersions] = useState<DocumentVersionResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [comparing, setComparing] = useState<{ versionA: number; versionB: number } | null>(null);
  const [compareResult, setCompareResult] = useState<any>(null);

  useEffect(() => {
    if (open && documentId) {
      loadVersions();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- Intentional deps
  }, [open, documentId]);

  const loadVersions = async () => {
    setLoading(true);
    try {
      const data = await documentVersionService.listByDocument(documentId);
      setVersions(data);
    } catch (error: any) {
      toast.error('Erro ao carregar versões', {
        description: error.response?.msgFromDetail(data?.detail) || 'Erro desconhecido',
      });
    } finally {
      setLoading(false);
    }
  };

  const handleSetCurrent = async (versionId: string) => {
    try {
      await documentVersionService.setCurrent(versionId);
      toast.success('Versão definida como atual');
      loadVersions();
    } catch (error: any) {
      toast.error('Erro ao definir versão atual', {
        description: error.response?.msgFromDetail(data?.detail) || 'Erro desconhecido',
      });
    }
  };

  const handleArchive = async (versionId: string) => {
    try {
      await documentVersionService.archive(versionId);
      toast.success('Versão arquivada');
      loadVersions();
    } catch (error: any) {
      toast.error('Erro ao arquivar versão', {
        description: error.response?.msgFromDetail(data?.detail) || 'Erro desconhecido',
      });
    }
  };

  const handleDelete = async (versionId: string) => {
    if (!confirm('Tem certeza que deseja excluir esta versão? Esta ação não pode ser desfeita.')) {
      return;
    }

    try {
      await documentVersionService.delete(versionId);
      toast.success('Versão excluída');
      loadVersions();
    } catch (error: any) {
      toast.error('Erro ao excluir versão', {
        description: error.response?.msgFromDetail(data?.detail) || 'Erro desconhecido',
      });
    }
  };

  const handleCompare = async (versionA: number, versionB: number) => {
    setComparing({ versionA, versionB });
    try {
      const result = await documentVersionService.compare(documentId, versionA, versionB);
      setCompareResult(result);
    } catch (error: any) {
      toast.error('Erro ao comparar versões', {
        description: error.response?.msgFromDetail(data?.detail) || 'Erro desconhecido',
      });
      setComparing(null);
    }
  };

  const formatDate = (date: string) => {
    return new Date(date).toLocaleString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const getVersionBadgeColor = (version: DocumentVersionResponse) => {
    if (version.is_current) return 'bg-green-500';
    if (version.status === 'arquivada') return 'bg-gray-400';
    if (version.status === 'obsoleta') return 'bg-yellow-500';
    return 'bg-blue-500';
  };

  return (
    <>
    {loading && open && (
      <div aria-hidden="true" style={{ position: 'absolute', width: 0, height: 0, overflow: 'hidden' }}>
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900" />
      </div>
    )}
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-4xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Histórico de Versões</DialogTitle>
          <DialogDescription>
            Visualize e gerencie todas as versões deste documento
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900" />
          </div>
        ) : (
          <div className="space-y-4">
            {/* Resumo */}
            <div className="grid grid-cols-3 gap-4 p-4 bg-gray-50 rounded-lg">
              <div>
                <p className="text-sm text-gray-500">Total de Versões</p>
                <p className="font-data text-2xl font-semibold tabular-nums">{versions.length}</p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Versão Atual</p>
                <p className="font-data text-2xl font-semibold tabular-nums">
                  {versions.find((v) => v.is_current) != null
                    ? `v${versions.find((v) => v.is_current)!.version_number}`
                    : '-'}
                </p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Última Atualização</p>
                <p className="text-sm font-medium">
                  {versions[0] ? formatDate(versions[0].created_at) : '-'}
                </p>
              </div>
            </div>

            {/* Timeline de versões */}
            <div className="space-y-4">
              {versions.map((version, index) => (
                <div
                  key={version.id}
                  className={`p-4 border rounded-lg ${
                    version.is_current ? 'border-green-500 bg-green-50' : 'border-gray-200'
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      {/* Header */}
                      <div className="flex items-center gap-2 mb-2">
                        <FileText className="h-5 w-5 text-gray-400" />
                        <span className="font-semibold">
                          Versão {version.version_number}
                          {version.version_label && ` - ${version.version_label}`}
                        </span>
                        <Badge className={getVersionBadgeColor(version)}>
                          {version.is_current ? 'Atual' : version.status}
                        </Badge>
                        <Badge variant="outline">{version.version_type}</Badge>
                      </div>

                      {/* Informações */}
                      <div className="grid grid-cols-2 gap-2 text-sm text-gray-600 mb-2">
                        <div className="flex items-center gap-1">
                          <User className="h-4 w-4" />
                          <span>Por: {version.created_by}</span>
                        </div>
                        <div className="flex items-center gap-1">
                          <Calendar className="h-4 w-4" />
                          <span>{formatDate(version.created_at)}</span>
                        </div>
                        <div className="flex items-center gap-1">
                          <FileText className="h-4 w-4" />
                          <span>{version.file_name}</span>
                        </div>
                        <div className="flex items-center gap-1">
                          <Archive className="h-4 w-4" />
                          <span>{formatFileSize(version.file_size_bytes)}</span>
                        </div>
                      </div>

                      {/* Resumo de mudanças */}
                      {version.change_summary && (
                        <div className="mt-2 p-2 bg-white rounded border border-gray-200">
                          <p className="text-sm font-medium mb-1">Alterações:</p>
                          <p className="text-sm text-gray-600">{version.change_summary}</p>
                        </div>
                      )}

                      {/* Estatísticas */}
                      <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
                        <span className="flex items-center gap-1">
                          <Eye className="h-3 w-3" />
                          {version.view_count} visualizações
                        </span>
                        <span className="flex items-center gap-1">
                          <Download className="h-3 w-3" />
                          {version.download_count} downloads
                        </span>
                      </div>
                    </div>

                    {/* Ações */}
                    <div className="flex flex-col gap-2 ml-4">
                      {!version.is_current && version.status === 'ativa' && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleSetCurrent(version.id)}
                        >
                          <CheckCircle2 className="h-4 w-4 mr-1" />
                          Definir como Atual
                        </Button>
                      )}

                      {index < versions.length - 1 && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() =>
                            handleCompare(version.version_number, versions[index + 1]!.version_number)
                          }
                        >
                          <ArrowUpDown className="h-4 w-4 mr-1" />
                          Comparar
                        </Button>
                      )}

                      {version.status === 'ativa' && !version.is_current && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleArchive(version.id)}
                        >
                          <Archive className="h-4 w-4 mr-1" />
                          Arquivar
                        </Button>
                      )}

                      {!version.is_current && (
                        <Button
                          variant="destructive"
                          size="sm"
                          onClick={() => handleDelete(version.id)}
                        >
                          <XCircle className="h-4 w-4 mr-1" />
                          Excluir
                        </Button>
                      )}
                    </div>
                  </div>

                  {/* Linha do tempo */}
                  {index < versions.length - 1 && (
                    <div className="flex items-center justify-center my-2">
                      <div className="h-8 w-px bg-gray-300" />
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* Dialog de comparação */}
            {compareResult && comparing && (
              <div className="mt-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
                <h4 className="font-semibold mb-2">
                  Comparação: Versão {comparing.versionA} vs Versão {comparing.versionB}
                </h4>
                <div className="space-y-2 text-sm">
                  <p>
                    <strong>Diferença de tamanho:</strong>{' '}
                    {formatFileSize(Math.abs(compareResult.size_diff))}
                    {compareResult.size_diff > 0 ? ' maior' : ' menor'}
                  </p>
                  <p>
                    <strong>Conteúdo:</strong>{' '}
                    {compareResult.same_content ? (
                      <span className="text-green-600">Idêntico</span>
                    ) : (
                      <span className="text-orange-600">Diferente</span>
                    )}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setComparing(null);
                    setCompareResult(null);
                  }}
                  className="mt-2"
                >
                  Fechar Comparação
                </Button>
              </div>
            )}
          </div>
        )}

        <div className="flex justify-end gap-2 mt-4">
          <Button variant="outline" onClick={onClose}>
            Fechar
          </Button>
        </div>
      </DialogContent>
    </Dialog>
    </>
  );
}
