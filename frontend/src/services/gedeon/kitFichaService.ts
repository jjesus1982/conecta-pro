/**
 * GEDEON — Ficha individualizada do kit por condomínio (montagem ponto-a-ponto):
 * completude + checklist de eventos (auto + manual) + upload de anexos.
 */
import { api } from '@/lib/api';

export interface ChecklistDoc {
  key: string; label: string; presente: boolean; encontrados: number; esperado: number;
}
export interface ArquivoKit { id?: string; name: string; link: string | null }
export interface SubpastaKit { nome: string; docs: number; arquivos: ArquivoKit[] }
export interface EventoKit {
  id?: string; tipo: string; auto: boolean;
  funcionario?: string | null; data?: string | null; descricao: string; autor?: string | null;
}
export interface FichaKit {
  competencia: string; condominio: string;
  completude: number; status: string; total_docs: number; drive_link: string | null;
  checklist: ChecklistDoc[]; subpastas: SubpastaKit[];
  eventos: { auto: EventoKit[]; manuais: EventoKit[] };
  tipos_evento: string[];
}

export async function getFicha(condominio: string, competencia?: string, refresh = false): Promise<FichaKit> {
  const { data } = await api.get('/api/v1/gedeon/kits/ficha', {
    params: { condominio, ...(competencia ? { competencia } : {}), ...(refresh ? { refresh: true } : {}) },
  });
  return data;
}

export async function addEvento(e: {
  condominio: string; competencia?: string; tipo: string; descricao: string;
  funcionario?: string; data?: string;
}): Promise<EventoKit> {
  const { data } = await api.post('/api/v1/gedeon/kits/checklist', e);
  return data;
}

export async function delEvento(condominio: string, competencia: string, eventoId: string): Promise<void> {
  await api.delete('/api/v1/gedeon/kits/checklist', {
    params: { condominio, competencia, evento_id: eventoId },
  });
}

export async function uploadKit(
  condominio: string, competencia: string, file: File, subpasta?: string,
): Promise<{ ok: boolean; arquivo: string }> {
  const fd = new FormData();
  fd.append('condominio', condominio);
  fd.append('competencia', competencia);
  fd.append('file', file);
  if (subpasta) fd.append('subpasta', subpasta);
  const { data } = await api.post('/api/v1/gedeon/kits/upload', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}

export async function delArquivo(
  condominio: string, competencia: string, fileId: string, nome?: string,
): Promise<{ ok: boolean; arquivo: string }> {
  const { data } = await api.delete('/api/v1/gedeon/kits/arquivo', {
    params: { condominio, competencia, file_id: fileId, ...(nome ? { nome } : {}) },
  });
  return data;
}

export const TIPO_LABEL: Record<string, string> = {
  contratacao: 'Contratação',
  demissao: 'Demissão',
  ferias: 'Férias',
  migracao_posto: 'Migração de posto',
  entrada_outro_posto: 'Entrada de outro posto',
  atestado: 'Atestado médico',
  afastamento: 'Afastamento',
  observacao: 'Observação',
};

export const SUBPASTAS = [
  '1. Folha e Pessoal',
  '2. Vale Transporte e Alimentação',
  '3. Impostos e Certidões',
  '4. Faturamento',
];
