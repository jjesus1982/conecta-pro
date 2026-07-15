/**
 * Custom Hooks - Documents Processing
 * Hooks React Query para processamento de documentos
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { msgFromDetail } from '@/lib/string';
import { toast } from 'sonner';
import * as processingService from '@/services/documents/processing';

// ==================== Query Keys ====================

export const processingKeys = {
  all: ['documents', 'processing'] as const,
  ocr: (documentId: string) => [...processingKeys.all, 'ocr', documentId] as const,
  classification: (documentId: string) =>
    [...processingKeys.all, 'classification', documentId] as const,
  extraction: (documentId: string) =>
    [...processingKeys.all, 'extraction', documentId] as const,
  validation: (documentId: string) =>
    [...processingKeys.all, 'validation', documentId] as const,
  full: (documentId: string) =>
    [...processingKeys.all, 'full', documentId] as const,
};

// ==================== Mutations ====================

/**
 * Hook para executar OCR em documento
 */
export const useRunOCR = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: processingService.RunOCRParams) =>
      processingService.runOCR(params),
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({
        queryKey: processingKeys.ocr(variables.document_id),
      });
      queryClient.invalidateQueries({ queryKey: ['documents'] });

      toast.success(
        `OCR concluído: ${data.words} palavras em ${data.pages} página(s)`
      );
    },
    onError: (error: any) => {
      const message =
        error?.response?.data?.detail?.[0]?.msg ||
        error?.response?.msgFromDetail(data?.detail) ||
        'Erro ao executar OCR';
      toast.error(message);
    },
  });
};

/**
 * Hook para classificar documento
 */
export const useClassifyDocument = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (document_id: string) =>
      processingService.classifyDocument(document_id),
    onSuccess: (data, document_id) => {
      queryClient.invalidateQueries({
        queryKey: processingKeys.classification(document_id),
      });
      queryClient.invalidateQueries({ queryKey: ['documents'] });

      toast.success(
        `Documento classificado: ${data.document_type} (${Math.round(data.confidence * 100)}% confiança)`
      );
    },
    onError: (error: any) => {
      const message =
        error?.response?.data?.detail?.[0]?.msg ||
        error?.response?.msgFromDetail(data?.detail) ||
        'Erro ao classificar documento';
      toast.error(message);
    },
  });
};

/**
 * Hook para extrair dados de documento
 */
export const useExtractData = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: processingService.ExtractDataParams) =>
      processingService.extractData(params),
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({
        queryKey: processingKeys.extraction(variables.document_id),
      });
      queryClient.invalidateQueries({ queryKey: ['documents'] });

      toast.success(
        `Extração concluída: ${data.fields_extracted} campo(s) extraído(s)`
      );
    },
    onError: (error: any) => {
      const message =
        error?.response?.data?.detail?.[0]?.msg ||
        error?.response?.msgFromDetail(data?.detail) ||
        'Erro ao extrair dados';
      toast.error(message);
    },
  });
};

/**
 * Hook para validar dados extraídos
 */
export const useValidateData = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (document_id: string) =>
      processingService.validateData(document_id),
    onSuccess: (data, document_id) => {
      queryClient.invalidateQueries({
        queryKey: processingKeys.validation(document_id),
      });
      queryClient.invalidateQueries({ queryKey: ['documents'] });

      if (data.is_valid) {
        toast.success(
          `Validação concluída: ${data.fields_passed}/${data.total_fields} campo(s) válido(s)`
        );
      } else {
        toast.warning(
          `Validação com problemas: ${data.fields_failed} campo(s) inválido(s)`
        );
      }

      // Mostrar erros se houver
      if (data.errors && data.errors.length > 0) {
        data.errors.forEach((error) => {
          toast.error(error);
        });
      }
    },
    onError: (error: any) => {
      const message =
        error?.response?.data?.detail?.[0]?.msg ||
        error?.response?.msgFromDetail(data?.detail) ||
        'Erro ao validar dados';
      toast.error(message);
    },
  });
};

/**
 * Hook para processamento completo de documento
 */
export const useProcessDocument = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: processingService.ProcessDocumentParams) =>
      processingService.processDocument(params),
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({
        queryKey: processingKeys.full(variables.document_id),
      });
      queryClient.invalidateQueries({ queryKey: ['documents'] });

      const needsReview = data.needs_review ? ' (requer revisão)' : '';
      toast.success(
        `Processamento concluído: ${data.document_type}${needsReview}`
      );
    },
    onError: (error: any) => {
      const message =
        error?.response?.data?.detail?.[0]?.msg ||
        error?.response?.msgFromDetail(data?.detail) ||
        'Erro ao processar documento';
      toast.error(message);
    },
  });
};
