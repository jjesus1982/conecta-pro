/**
 * Fila offline da ronda (frente 6, 12/09/2026).
 *
 * O checkpoint e as fotos ficam no IndexedDB do aparelho quando não há sinal e sobem
 * automaticamente na MESMA requisição (`POST /rondas/{id}/checkpoints/completo`) quando o
 * sinal volta. Teto declarado (TETO_ITENS / TETO_BYTES), compressão ANTES de enfileirar e
 * chave idempotente por (ronda, posto, tipo, hora do aparelho, device) — a retentativa não
 * duplica no servidor.
 *
 * Sem service worker para a fila, de propósito: o token vive no localStorage da página e o
 * envio precisa dele. O SW (`/sw-rondas.js`) só guarda a casca da página e os GETs.
 */

import axios from 'axios';
import { api } from '@/lib/api';

export const TETO_ITENS = 50;
export const TETO_BYTES = 100 * 1024 * 1024; // 100 MB
export const FOTO_MAX_LADO = 1280;
export const FOTO_QUALIDADE = 0.7;

const DB_NOME = 'conecta_rondas_offline';
const DB_VERSAO = 1;
const STORE = 'fila';
const RONDAS_URL = '/api/v1/operacional/rondas';

export interface FotoLocal {
  blob: Blob;
  /** true = veio da câmera do app (prova); false = galeria (não vale como prova). */
  capturada_na_hora: boolean;
  /** ISO — hora do aparelho no clique. */
  hora_aparelho: string;
}

export interface ItemFila {
  chave: string;
  round_id: string;
  dados: Record<string, unknown>;
  fotos: Blob[];
  anexos: Blob[];
  bytes: number;
  criado_em: string;
  tentativas: number;
  erro?: string;
}

// ── device id ────────────────────────────────────────────────────────────────
export function deviceId(): string {
  try {
    let id = localStorage.getItem('conecta_device_id');
    if (!id) {
      id = crypto.randomUUID();
      localStorage.setItem('conecta_device_id', id);
    }
    return id;
  } catch {
    return 'sem-storage';
  }
}

/** ≤ 120 chars (varchar(120) no banco). */
export function chaveIdempotente(
  roundId: string,
  postId: string | null | undefined,
  tipo: string,
  horaAparelho: string
): string {
  return `${roundId.slice(0, 8)}:${(postId ?? '-').slice(0, 8)}:${tipo.slice(0, 24)}:${horaAparelho}:${deviceId().slice(0, 8)}`;
}

// ── compressão ───────────────────────────────────────────────────────────────
export async function comprimirImagem(origem: Blob | ImageBitmap): Promise<Blob> {
  const bmp = origem instanceof Blob ? await createImageBitmap(origem) : origem;
  const escala = Math.min(1, FOTO_MAX_LADO / Math.max(bmp.width, bmp.height));
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(bmp.width * escala);
  canvas.height = Math.round(bmp.height * escala);
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('canvas indisponível');
  ctx.drawImage(bmp, 0, 0, canvas.width, canvas.height);
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (b) => (b ? resolve(b) : reject(new Error('falha ao comprimir a imagem'))),
      'image/jpeg',
      FOTO_QUALIDADE
    );
  });
}

// ── IndexedDB ────────────────────────────────────────────────────────────────
function abrirDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NOME, DB_VERSAO);
    req.onupgradeneeded = () => {
      if (!req.result.objectStoreNames.contains(STORE)) {
        req.result.createObjectStore(STORE, { keyPath: 'chave' });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function pedir<T>(req: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function listarFila(): Promise<ItemFila[]> {
  const db = await abrirDB();
  const itens = await pedir(db.transaction(STORE, 'readonly').objectStore(STORE).getAll());
  db.close();
  return (itens as ItemFila[]).sort((a, b) => a.criado_em.localeCompare(b.criado_em));
}

export async function resumoFila(): Promise<{ itens: number; bytes: number }> {
  const fila = await listarFila();
  return { itens: fila.length, bytes: fila.reduce((s, i) => s + i.bytes, 0) };
}

export async function enfileirar(
  item: Omit<ItemFila, 'bytes' | 'criado_em' | 'tentativas'>
): Promise<{ ok: true; itens: number } | { ok: false; motivo: string }> {
  const bytes = [...item.fotos, ...item.anexos].reduce((s, b) => s + b.size, 0);
  const atual = await resumoFila();
  if (atual.itens >= TETO_ITENS) {
    return { ok: false, motivo: `Fila cheia (${TETO_ITENS} itens). Procure sinal e envie os pendentes.` };
  }
  if (atual.bytes + bytes > TETO_BYTES) {
    return { ok: false, motivo: `Fila cheia (${Math.round(TETO_BYTES / 1e6)} MB). Procure sinal e envie os pendentes.` };
  }
  const db = await abrirDB();
  await pedir(
    db.transaction(STORE, 'readwrite').objectStore(STORE).put({
      ...item,
      bytes,
      criado_em: new Date().toISOString(),
      tentativas: 0,
    } satisfies ItemFila)
  );
  db.close();
  return { ok: true, itens: atual.itens + 1 };
}

async function gravar(item: ItemFila): Promise<void> {
  const db = await abrirDB();
  await pedir(db.transaction(STORE, 'readwrite').objectStore(STORE).put(item));
  db.close();
}

export async function removerDaFila(chave: string): Promise<void> {
  const db = await abrirDB();
  await pedir(db.transaction(STORE, 'readwrite').objectStore(STORE).delete(chave));
  db.close();
}

// ── envio ────────────────────────────────────────────────────────────────────
export function montarFormData(
  dados: Record<string, unknown>,
  fotos: Blob[],
  anexos: Blob[]
): FormData {
  const fd = new FormData();
  fd.append('dados', JSON.stringify(dados));
  fotos.forEach((b, i) => fd.append('fotos', b, `camera_${i + 1}.jpg`));
  anexos.forEach((b, i) => fd.append('anexos', b, `galeria_${i + 1}.jpg`));
  return fd;
}

export async function postarCompleto(roundId: string, fd: FormData): Promise<unknown> {
  const res = await api.post(`${RONDAS_URL}/${roundId}/checkpoints/completo`, fd, {
    // o axios global força application/json — sem o override o multipart sai sem boundary
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  });
  return res.data;
}

/** Erro que não adianta repetir (o servidor RECUSOU): 4xx menos 401/408/429. */
export function recusaDefinitiva(error: unknown): string | null {
  if (!axios.isAxiosError(error) || !error.response) return null;
  const s = error.response.status;
  if (s === 401 || s === 408 || s === 429 || s >= 500) return null;
  const d = error.response.data as { detail?: unknown } | undefined;
  return typeof d?.detail === 'string' ? d.detail : `HTTP ${s}`;
}

export interface ResultadoEnvio {
  enviados: number;
  ficaram: number;
  recusados: { chave: string; titulo: string; motivo: string }[];
}

/** Sobe a fila em ordem. Para no primeiro erro de rede (o sinal foi embora de novo). */
export async function enviarFila(): Promise<ResultadoEnvio> {
  const fila = await listarFila();
  const r: ResultadoEnvio = { enviados: 0, ficaram: 0, recusados: [] };
  for (const item of fila) {
    try {
      await postarCompleto(item.round_id, montarFormData(item.dados, item.fotos, item.anexos));
      await removerDaFila(item.chave);
      r.enviados++;
    } catch (error) {
      const motivo = recusaDefinitiva(error);
      if (motivo) {
        // o servidor disse não (ronda fechada, foto faltando…): guardar não resolve — tira da fila e avisa
        await removerDaFila(item.chave);
        r.recusados.push({ chave: item.chave, titulo: String(item.dados.title ?? item.dados.checkpoint_type ?? ''), motivo });
        continue;
      }
      item.tentativas++;
      item.erro = axios.isAxiosError(error) ? error.message : String(error);
      await gravar(item);
      r.ficaram = fila.length - r.enviados - r.recusados.length;
      break; // sem rede: os demais esperam
    }
  }
  return r;
}

// ── cache de leitura (postos / ronda ativa) para abrir sem sinal ─────────────
const CACHE_PREFIXO = 'conecta_rondas_cache:';
export function cacheSalvar(chave: string, valor: unknown): void {
  try {
    localStorage.setItem(CACHE_PREFIXO + chave, JSON.stringify({ em: new Date().toISOString(), valor }));
  } catch {
    /* storage cheio ou bloqueado: segue sem cache */
  }
}
export function cacheLer<T>(chave: string): { em: string; valor: T } | null {
  try {
    const raw = localStorage.getItem(CACHE_PREFIXO + chave);
    return raw ? (JSON.parse(raw) as { em: string; valor: T }) : null;
  } catch {
    return null;
  }
}
