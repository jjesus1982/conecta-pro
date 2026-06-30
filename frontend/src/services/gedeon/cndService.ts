/**
 * GEDEON — Emissão de CND pela UI (robô real via ponte). Emitir / status / baixar PDF.
 */
import { api } from '@/lib/api';

export interface CndItem {
  document_type: string;
  name: string;
  orgao: string | null;
  emissao: string | null;
  validade: string | null;
  situacao: string | null;
  alerta: boolean;
  tem_pdf: boolean;
}

export interface PortalManual { nome: string; url: string; }

export interface CndStatus {
  emissao: { state: string; atual?: string; cnpj?: string; ts?: string };
  certidoes: CndItem[];
  manuais?: Record<string, PortalManual>;
}

export async function uploadCnd(documentType: string, file: File): Promise<{ ok: boolean; situacao: string; validade: string | null }> {
  const fd = new FormData();
  fd.append('document_type', documentType);
  fd.append('file', file);
  const { data } = await api.post('/api/v1/gedeon/cnd/upload', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}

export async function emitirCnd(portais?: string[]): Promise<{ status: string; portais: string[] }> {
  const { data } = await api.post('/api/v1/gedeon/cnd/emitir', { portais: portais || null });
  return data;
}

export async function statusCnd(): Promise<CndStatus> {
  const { data } = await api.get('/api/v1/gedeon/cnd/status');
  return data;
}

/** Baixa o PDF (com auth) e abre em nova aba. */
export async function abrirPdfCnd(documentType: string): Promise<void> {
  const resp = await api.get(`/api/v1/gedeon/cnd/pdf/${documentType}`, { responseType: 'blob' });
  const url = URL.createObjectURL(resp.data as Blob);
  window.open(url, '_blank');
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

export const PORTAL_LABEL: Record<string, string> = {
  sefaz_am: 'SEFAZ-AM (Estadual)',
  cndt: 'CNDT (Trabalhista)',
  prefeitura: 'Prefeitura de Manaus (Municipal)',
  federal: 'Receita Federal',
  caixa: 'FGTS / Caixa',
};

/** dias até a validade (negativo = vencida). */
export function diasParaVencer(validade: string | null): number | null {
  if (!validade) return null;
  const d = new Date(validade + 'T12:00:00');
  return Math.ceil((d.getTime() - Date.now()) / 86400000);
}
