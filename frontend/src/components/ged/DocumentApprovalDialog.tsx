'use client';

import { CheckCircle, XCircle, AlertCircle } from 'lucide-react';
import { msgFromDetail } from '@/lib/string';
import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import { type DocumentResponse, formatFileSize } from '@/types/generated/ged/conectaPROMóduloGED.schemas';
import {
  approveDocumentApiV1GedDocumentsDocumentIdApprovePost,
  rejectDocumentApiV1GedDocumentsDocumentIdRejectPost,
} from '@/types/generated/ged/ged-documentos/ged-documentos';

interface DocumentApprovalDialogProps {
  document: DocumentResponse | null;
  open: boolean;
  onClose: () => void;
  onApproved?: () => void;
}

export function DocumentApprovalDialog({
  document,
  open,
  onClose,
  onApproved,
}: DocumentApprovalDialogProps) {
  const [rejectionReason, setRejectionReason] = useState('');
  const [loading, setLoading] = useState(false);

  const handleApprove = async () => {
    if (!document) return;

    setLoading(true);
    try {
      await approveDocumentApiV1GedDocumentsDocumentIdApprovePost(document.id);
      toast.success('Documento aprovado');
      onApproved?.();
      onClose();
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      toast.error('Erro ao aprovar documento', {
        description: msgFromDetail(err.response?.data?.detail) || 'Erro desconhecido',
      });
    } finally {
      setLoading(false);
    }
  };

  const handleReject = async () => {
    if (!document) return;

    if (!rejectionReason.trim()) {
      toast.error('Motivo da rejeição é obrigatório');
      return;
    }

    setLoading(true);
    try {
      await rejectDocumentApiV1GedDocumentsDocumentIdRejectPost(document.id, { reason: rejectionReason });
      toast.success('Documento rejeitado');
      onApproved?.();
      onClose();
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      toast.error('Erro ao rejeitar documento', {
        description: msgFromDetail(err.response?.data?.detail) || 'Erro desconhecido',
      });
    } finally {
      setLoading(false);
    }
  };

  if (!document) return null;

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Aprovação de Documento</DialogTitle>
          <DialogDescription>
            Revise o documento e decida se aprova ou rejeita
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Informações do documento */}
          <div className="p-4 bg-gray-50 border rounded-lg space-y-2">
            <div>
              <Label className="text-sm text-gray-600">Título</Label>
              <p className="font-medium">{document.title}</p>
            </div>

            {document.description && (
              <div>
                <Label className="text-sm text-gray-600">Descrição</Label>
                <p className="text-sm">{document.description}</p>
              </div>
            )}

            <div className="grid grid-cols-3 gap-4 text-sm">
              <div>
                <Label className="text-xs text-gray-600">Tipo</Label>
                <p>{document.document_type}</p>
              </div>
              <div>
                <Label className="text-xs text-gray-600">Categoria</Label>
                <p>{document.category}</p>
              </div>
              <div>
                <Label className="text-xs text-gray-600">Tamanho</Label>
                <p>{formatFileSize(document.file_size_bytes)}</p>
              </div>
            </div>

            <div>
              <Label className="text-sm text-gray-600">Criado por</Label>
              <p className="text-sm">{document.created_by}</p>
              <p className="text-xs text-gray-500">
                {new Date(document.created_at).toLocaleString('pt-BR')}
              </p>
            </div>
          </div>

          {/* Aviso */}
          <div className="flex items-start gap-2 p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
            <AlertCircle className="h-5 w-5 text-yellow-600 mt-0.5" />
            <div className="text-sm text-yellow-900">
              <p className="font-medium mb-1">Atenção</p>
              <p>
                Ao aprovar, o documento será marcado como aprovado e poderá ser publicado. Ao
                rejeitar, o documento voltará para revisão.
              </p>
            </div>
          </div>

          {/* Motivo de rejeição */}
          <div>
            <Label>Motivo da Rejeição (se aplicável)</Label>
            <Textarea
              placeholder="Descreva o motivo caso vá rejeitar o documento"
              value={rejectionReason}
              onChange={(e) => setRejectionReason(e.target.value)}
              rows={4}
            />
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-4">
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button
            variant="destructive"
            onClick={handleReject}
            disabled={loading}
          >
            <XCircle className="h-4 w-4 mr-2" />
            Rejeitar
          </Button>
          <Button
            onClick={handleApprove}
            disabled={loading}
            className="bg-green-600 hover:bg-green-700"
          >
            <CheckCircle className="h-4 w-4 mr-2" />
            Aprovar
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
