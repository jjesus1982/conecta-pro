'use client';

import React, { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import {
  ArrowLeft, Download, FileText, User, Building2, Loader2, ShieldCheck, PenLine, AlertTriangle,
} from 'lucide-react';
import { toast } from 'sonner';
import KitApprovalSection from '../components/KitApprovalSection';

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || '') + '/api/v1/portal';

function getPortalHeaders() {
  const token = typeof window !== 'undefined' ? localStorage.getItem('portal_token') : null;
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

interface KitDetail {
  id: string;
  reference_month: string;
  status: string;
  completion_percentage: number;
  total_documents: number;
  total_employees: number;
  documents_signed: number;
  notes: string | null;
  sent_at: string | null;
  zip_file_path: string | null;
  google_drive_link: string | null;
  documents: KitDocument[];
}

interface KitDocument {
  id: string;
  document_name: string;
  document_type: string;
  file_size_bytes: number | null;
  mime_type: string | null;
  is_signed: boolean;
  created_at: string;
}

const statusLabels: Record<string, string> = {
  em_montagem: 'Em Montagem',
  completo: 'Completo',
  enviado: 'Enviado',
  conferido: 'Conferido',
  aprovado: 'Aprovado',
};

const statusColors: Record<string, string> = {
  em_montagem: 'bg-amber-500/10 text-amber-500',
  completo: 'bg-blue-500/10 text-blue-500',
  enviado: 'bg-emerald-500/10 text-emerald-500',
  conferido: 'bg-purple-500/10 text-purple-500',
  aprovado: 'bg-emerald-500/10 text-emerald-500',
};

function formatMonth(dateStr: string): string {
  if (!dateStr) return '-';
  try {
    const d = new Date(dateStr + (dateStr.length <= 10 ? 'T00:00:00' : ''));
    return d.toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' });
  } catch {
    return dateStr;
  }
}

function formatFileSize(bytes: number | null): string {
  if (!bytes) return '-';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function KitDetailPage() {
  const params = useParams();
  const kitId = params.id as string;
  const [kit, setKit] = useState<KitDetail | null>(null);
  const [documents, setDocuments] = useState<KitDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [downloadingDoc, setDownloadingDoc] = useState<string | null>(null);

  const fetchKit = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [kitRes, docsRes] = await Promise.all([
        fetch(`${API_BASE}/kits/${kitId}`, { headers: getPortalHeaders() }),
        fetch(`${API_BASE}/kits/${kitId}/documents`, { headers: getPortalHeaders() }),
      ]);

      if (kitRes.status === 401) {
        toast.error('Sessao expirada. Faca login novamente.', { duration: 5000 });
        return;
      }

      if (kitRes.ok) {
        const kitData = await kitRes.json();
        setKit(kitData);
      } else if (kitRes.status === 404) {
        setError('Kit nao encontrado.');
      } else {
        setError('Erro ao carregar dados do kit.');
      }

      if (docsRes.ok) {
        const d = await docsRes.json();
        setDocuments(Array.isArray(d) ? d : d.items || []);
      }
    } catch {
      setError('Erro ao carregar dados do kit.');
      toast.error('Erro ao carregar kit. Verifique sua conexao.', { duration: 5000 });
    } finally {
      setLoading(false);
    }
  }, [kitId]);

  useEffect(() => {
    fetchKit();
  }, [fetchKit]);


  async function handleDownloadDoc(doc: KitDocument) {
    setDownloadingDoc(doc.id);
    try {
      const token = localStorage.getItem('portal_token');
      const res = await fetch(`${API_BASE}/kits/${kitId}/documents/${doc.id}/download`, {
        headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      });
      if (res.ok) {
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = doc.document_name || `documento-${doc.id}`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
        toast.success(`Documento "${doc.document_name}" baixado.`, { duration: 4000 });
      } else if (res.status === 404) {
        toast.error('Arquivo nao encontrado no servidor.', { duration: 5000 });
      } else {
        toast.error('Erro ao baixar documento.', { duration: 5000 });
      }
    } catch {
      toast.error('Erro ao baixar documento. Tente novamente.', { duration: 5000 });
    } finally {
      setDownloadingDoc(null);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
      </div>
    );
  }

  if (error && !kit) {
    return (
      <div className="text-center py-20">
        <AlertTriangle className="h-12 w-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
        <p className="text-[hsl(var(--muted-foreground))]">{error}</p>
        <Link href="/area-cliente/kits" className="text-indigo-500 hover:underline text-sm mt-2 inline-block">
          Voltar para Meus Kits
        </Link>
      </div>
    );
  }

  if (!kit) {
    return (
      <div className="text-center py-20">
        <p className="text-[hsl(var(--muted-foreground))]">Kit nao encontrado.</p>
        <Link href="/area-cliente/kits" className="text-indigo-500 hover:underline text-sm mt-2 inline-block">
          Voltar para Meus Kits
        </Link>
      </div>
    );
  }

  const completionPct = Number(kit.completion_percentage) || 0;

  return (
    <div className="space-y-6 pb-28">
      {/* Back link */}
      <Link
        href="/area-cliente/kits"
        className="inline-flex items-center gap-1.5 text-sm text-[hsl(var(--muted-foreground))] hover:text-indigo-500 transition-colors"
      >
        <ArrowLeft className="h-4 w-4" />
        Voltar para Meus Kits
      </Link>

      {/* Kit Header */}
      <div className="bg-[hsl(var(--card))] rounded-xl shadow-sm border border-[hsl(var(--border))] p-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="font-display text-2xl font-bold text-[hsl(var(--foreground))]">Kit {formatMonth(kit.reference_month)}</h1>
            <div className="flex items-center gap-3 mt-2">
              <span
                className={`inline-block text-xs font-medium px-3 py-1 rounded-full ${
                  statusColors[kit.status] || 'bg-[hsl(var(--secondary))] text-[hsl(var(--muted-foreground))]'
                }`}
              >
                {statusLabels[kit.status] || kit.status}
              </span>
              <span className="text-xs text-[hsl(var(--muted-foreground))]">{kit.total_documents} documentos</span>
              {kit.documents_signed > 0 && (
                <span className="text-xs text-emerald-500">{kit.documents_signed} assinados</span>
              )}
            </div>
          </div>
          <div className="w-48">
            <div className="flex justify-between text-xs text-[hsl(var(--muted-foreground))] mb-1">
              <span>Conclusao</span>
              <span className="font-data font-semibold tabular-nums">{completionPct}%</span>
            </div>
            <div className="w-full bg-[hsl(var(--secondary))] rounded-full h-2.5">
              <div
                className="bg-indigo-600 h-2.5 rounded-full transition-all"
                style={{ width: `${completionPct}%` }}
              />
            </div>
          </div>
        </div>
        {kit.notes && (
          <div className="mt-4 pt-4 border-t border-[hsl(var(--border))]">
            <p className="text-sm text-[hsl(var(--muted-foreground))]">{kit.notes}</p>
          </div>
        )}
      </div>

      {/* Documents List */}
      {documents.length > 0 ? (
        <div className="bg-[hsl(var(--card))] rounded-xl shadow-sm border border-[hsl(var(--border))]">
          <div className="px-6 py-4 border-b border-[hsl(var(--border))] flex items-center gap-2">
            <FileText className="h-5 w-5 text-indigo-500" />
            <h2 className="text-lg font-semibold text-[hsl(var(--foreground))]">Documentos ({documents.length})</h2>
          </div>
          <div className="divide-y divide-[hsl(var(--border))]">
            {documents.map((doc) => (
              <div key={doc.id} className="px-6 py-3.5 flex items-center justify-between">
                <div className="flex items-center gap-3 min-w-0">
                  <FileText className="h-4 w-4 text-[hsl(var(--muted-foreground))] flex-shrink-0" />
                  <div className="min-w-0">
                    <span className="text-sm text-[hsl(var(--foreground))] truncate block">{doc.document_name}</span>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-xs bg-[hsl(var(--secondary))] text-[hsl(var(--muted-foreground))] px-2 py-0.5 rounded">
                        {doc.document_type}
                      </span>
                      {doc.file_size_bytes && (
                        <span className="text-xs text-[hsl(var(--muted-foreground))]">
                          {formatFileSize(doc.file_size_bytes)}
                        </span>
                      )}
                      {doc.is_signed && (
                        <span title="Assinado" className="flex items-center gap-0.5 text-xs text-emerald-500">
                          <PenLine className="h-3.5 w-3.5" />
                          Assinado
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                <button
                  onClick={() => handleDownloadDoc(doc)}
                  disabled={downloadingDoc === doc.id}
                  className="text-indigo-500 hover:text-indigo-400 p-2 rounded-lg hover:bg-indigo-500/10 transition-colors disabled:opacity-50 flex-shrink-0"
                  title="Baixar documento"
                >
                  {downloadingDoc === doc.id ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Download className="h-4 w-4" />
                  )}
                </button>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="bg-[hsl(var(--card))] rounded-xl shadow-sm border border-[hsl(var(--border))] p-12 text-center">
          <FileText className="h-12 w-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
          <p className="text-[hsl(var(--muted-foreground))]">Nenhum documento disponivel neste kit.</p>
        </div>
      )}

      {/* Actions */}
      <div className="flex flex-wrap gap-3">
        {kit.google_drive_link && (
          <a
            href={kit.google_drive_link}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 bg-indigo-600 text-white px-5 py-2.5 rounded-lg font-medium hover:bg-indigo-700 transition-colors"
          >
            <Download className="h-4 w-4" />
            Abrir no Google Drive
          </a>
        )}
      </div>

      {/* Aprovação digital com assinatura (substitui o confirm simples) */}
      <div className="mt-6">
        <KitApprovalSection kitId={kitId} kitStatus={kit.status} onApproved={fetchKit} />
      </div>
    </div>
  );
}
