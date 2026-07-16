/**
 * Custom Hooks - Documents Upload
 * Hooks React Query para upload de documentos
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { msgFromDetail } from '@/lib/string';
import { toast } from 'sonner';
import * as uploadService from '@/services/documents/upload';

// ==================== Query Keys ====================

export const uploadKeys = {
  all: ['documents', 'upload'] as const,
  uploads: () => [...uploadKeys.all, 'list'] as const,
};

// ==================== Mutations ====================

/**
 * Hook para upload de documento único
 */
export const useUploadDocument = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: uploadService.UploadDocumentParams) =>
      uploadService.uploadDocument(params),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['documents'] });

      if (data.success) {
        toast.success(data.message || 'Documento enviado com sucesso!');
      } else {
        toast.warning(data.message || 'Upload concluído com avisos');
      }

      // Mostrar warnings se houver
      if (data.warnings && data.warnings.length > 0) {
        data.warnings.forEach((warning) => {
          toast.warning(warning);
        });
      }
    },
    onError: (error: any) => {
      const message =
        error?.response?.data?.detail?.[0]?.msg ||
        msgFromDetail(error?.response?.data?.detail) ||
        'Erro ao enviar documento';
      toast.error(message);
    },
  });
};

/**
 * Hook para upload de múltiplos documentos
 */
export const useUploadBatch = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: uploadService.UploadBatchParams) =>
      uploadService.uploadBatch(params),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['documents'] });

      const successful = data.filter((d) => d.success).length;
      const failed = data.filter((d) => !d.success).length;

      if (failed === 0) {
        toast.success(`${successful} documento(s) enviado(s) com sucesso!`);
      } else {
        toast.warning(
          `${successful} sucesso, ${failed} falha(s). Verifique os detalhes.`
        );
      }

      // Mostrar warnings de cada documento
      data.forEach((result, index) => {
        if (result.warnings && result.warnings.length > 0) {
          result.warnings.forEach((warning) => {
            toast.warning(`Documento ${index + 1}: ${warning}`);
          });
        }
      });
    },
    onError: (error: any) => {
      const message =
        error?.response?.data?.detail?.[0]?.msg ||
        msgFromDetail(error?.response?.data?.detail) ||
        'Erro ao enviar documentos';
      toast.error(message);
    },
  });
};
