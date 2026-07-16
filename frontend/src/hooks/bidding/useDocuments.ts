'use client';

/**
 * Hooks React Query - Documents (Documentos de Licitação)
 * Cobertura 100% dos 11 endpoints backend
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { msgFromDetail } from '@/lib/string';
import { toast } from 'sonner';
import documentsService, {
  type ListDocumentsParams,
} from '@/services/bidding/documents.service';
import type {
  CompanyDocumentCreate,
  CompanyDocumentUpdate,
} from '@/types/generated/bidding';

const QUERY_KEYS = {
  all: ['bidding', 'documents'] as const,
  lists: () => [...QUERY_KEYS.all, 'list'] as const,
  list: (params?: ListDocumentsParams) => [...QUERY_KEYS.lists(), params] as const,
  details: () => [...QUERY_KEYS.all, 'detail'] as const,
  detail: (id: string) => [...QUERY_KEYS.details(), id] as const,
  expiring: (params?: unknown) => [...QUERY_KEYS.all, 'expiring', params] as const,
  status: () => [...QUERY_KEYS.all, 'status'] as const,
  habilitacao: () => [...QUERY_KEYS.all, 'habilitacao'] as const,
  tipos: () => [...QUERY_KEYS.all, 'tipos'] as const,
  tipo: (tipo: string) => [...QUERY_KEYS.all, 'tipo', tipo] as const,
};

// GET /documents/
export function useListarDocumentos(params?: ListDocumentsParams) {
  return useQuery({
    queryKey: QUERY_KEYS.list(params),
    queryFn: () => documentsService.listarDocumentos(params),
    staleTime: 1000 * 60 * 5,
  });
}

// GET /documents/expiring
export function useListarDocumentosVencendo(params?: { dias?: number }) {
  return useQuery({
    queryKey: QUERY_KEYS.expiring(params),
    queryFn: () => documentsService.listarVencendo(params),
    staleTime: 1000 * 60 * 10,
  });
}

// GET /documents/status
export function useStatusGeralDocumentos() {
  return useQuery({
    queryKey: QUERY_KEYS.status(),
    queryFn: () => documentsService.getStatusGeral(),
    staleTime: 1000 * 60 * 10,
  });
}

// GET /documents/habilitacao
export function useVerificarHabilitacao() {
  return useQuery({
    queryKey: QUERY_KEYS.habilitacao(),
    queryFn: () => documentsService.verificarHabilitacao(),
    staleTime: 1000 * 60 * 10,
  });
}

// GET /documents/tipos
export function useListarTiposDocumento() {
  return useQuery({
    queryKey: QUERY_KEYS.tipos(),
    queryFn: () => documentsService.listarTipos(),
    staleTime: 1000 * 60 * 30,
  });
}

// GET /documents/tipo/{tipo}
export function useBuscarDocumentoPorTipo(tipo: string, enabled = true) {
  return useQuery({
    queryKey: QUERY_KEYS.tipo(tipo),
    queryFn: () => documentsService.buscarPorTipo(tipo),
    enabled: enabled && !!tipo,
    staleTime: 1000 * 60 * 5,
  });
}

// GET /documents/{id}
export function useBuscarDocumento(documentId: string, enabled = true) {
  return useQuery({
    queryKey: QUERY_KEYS.detail(documentId),
    queryFn: () => documentsService.buscarDocumentoPorId(documentId),
    enabled: enabled && !!documentId,
    staleTime: 1000 * 60 * 5,
  });
}

// POST /documents/
export function useCriarDocumento() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CompanyDocumentCreate) => documentsService.criarDocumento(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.lists() });
      toast.success('Documento criado com sucesso');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao criar documento');
    },
  });
}

// PUT /documents/{id}
export function useAtualizarDocumento() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: CompanyDocumentUpdate }) =>
      documentsService.atualizarDocumento(id, data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.lists() });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.detail(data.id) });
      toast.success('Documento atualizado com sucesso');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao atualizar documento');
    },
  });
}

// DELETE /documents/{id}
export function useRemoverDocumento() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (documentId: string) => documentsService.removerDocumento(documentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.lists() });
      toast.success('Documento removido com sucesso');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao remover documento');
    },
  });
}

// POST /documents/atualizar-status
export function useAtualizarStatusEmLote() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => documentsService.atualizarStatusEmLote(),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.lists() });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.status() });
      toast.success(`${data.total_atualizado} documentos atualizados`);
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao atualizar status');
    },
  });
}
