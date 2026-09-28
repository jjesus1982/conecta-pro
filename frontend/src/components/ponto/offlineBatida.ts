/**
 * A conversa da página com o service worker do ponto (frente 02, 13/09/2026).
 *
 * A regra que decide o desenho: quem sincroniza é a PÁGINA, não o service worker. Um SW não
 * enxerga o localStorage onde o token vive — a versão anterior do `sw-ponto.js` postava para
 * `/ponto/sync` sem cabeçalho de autorização, e esse destino grava a batida SEM reconferir o rosto
 * no servidor. Aqui a fila sobe por `/ponto/offline/sync`, com o token da pessoa, e o servidor
 * recompara o rosto antes de aceitar.
 *
 * 🔒 LGPD — o descriptor é dado biométrico. Ele vive no IndexedDB (nunca no localStorage, nunca em
 * claro numa chave que qualquer script lê), com VALIDADE vinda do servidor, e some quando vence,
 * quando o aparelho muda de dono e quando a batida é aceita.
 */

const SW_URL = '/sw-ponto.js';
const DEVICE_KEY = 'conecta_ponto_device_id';

export interface BatidaOfflineLocal {
  punch_id: string;
  employee_id: string;
  punch_type: string;
  /** hora do APARELHO, ISO local. É a hora do fato; o servidor mede a diferença e não corrige. */
  hora_aparelho: string;
  device_id: string;
  chave_idempotente: string;
  descriptor?: number[];
  foto_base64?: string;
  latitude?: number | null;
  longitude?: number | null;
  accuracy?: number | null;
  distancia_aparelho?: number | null;
  tentativas_offline?: { motivo: string; quando?: string; distancia?: number | null }[];
  synced?: boolean;
}

export interface ConfigOffline {
  limiar_distancia: number;
  validade_cache_horas: number;
  divergencia_relogio_max_seg: number;
  janela_idempotencia_min: number;
}

/** Identificador do APARELHO. Não é biometria e não identifica pessoa — só o celular. */
export function deviceId(): string {
  if (typeof window === 'undefined') return 'ssr';
  let id = '';
  try {
    id = localStorage.getItem(DEVICE_KEY) || '';
    if (!id) {
      id = `CEL-${crypto.randomUUID().slice(0, 12)}`;
      localStorage.setItem(DEVICE_KEY, id);
    }
  } catch {
    // navegador com storage bloqueado: um id por sessão ainda é melhor que nenhum
    id = `CEL-EFEMERO-${Math.random().toString(36).slice(2, 10)}`;
  }
  return id;
}

/** ISO local (sem sufixo Z): é a hora de parede do aparelho, que é como a coluna guarda. */
export function horaLocalISO(d: Date = new Date()): string {
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

/** (pessoa, MINUTO da hora do aparelho, aparelho) — a MESMA regra que o servidor aplica. */
export function chaveIdempotente(employeeId: string, horaISO: string, dev: string): string {
  return `${employeeId}:${horaISO.slice(0, 16)}:${dev}`;
}

export async function registrarSW(): Promise<ServiceWorkerRegistration | null> {
  if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return null;
  try {
    const reg = await navigator.serviceWorker.register(SW_URL, { scope: '/' });
    await navigator.serviceWorker.ready;
    return reg;
  } catch {
    return null;
  }
}

/** Pergunta ao SW e espera a resposta. Sem SW ativo, devolve null em vez de travar a tela. */
function perguntar<T>(type: string, data?: unknown, resposta?: string, timeoutMs = 4000): Promise<T | null> {
  if (typeof navigator === 'undefined' || !navigator.serviceWorker?.controller) return Promise.resolve(null);
  return new Promise((resolve) => {
    const canal = new MessageChannel();
    const timer = setTimeout(() => resolve(null), timeoutMs);
    canal.port1.onmessage = (e) => {
      if (resposta && e.data?.type !== resposta) return;
      clearTimeout(timer);
      resolve(e.data as T);
    };
    navigator.serviceWorker.controller!.postMessage({ type, data }, [canal.port2]);
  });
}

export async function salvarOffline(b: BatidaOfflineLocal): Promise<boolean> {
  const r = await perguntar<{ type: string }>('SAVE_PUNCH_OFFLINE', b, 'PUNCH_SAVED_OFFLINE');
  return Boolean(r);
}

export async function pendentes(): Promise<BatidaOfflineLocal[]> {
  const r = await perguntar<{ punches: BatidaOfflineLocal[] }>('GET_PENDING', undefined, 'PENDING');
  return r?.punches || [];
}

export async function marcarSincronizadas(ids: string[]): Promise<void> {
  if (ids.length) await perguntar('MARK_SYNCED', { punch_ids: ids }, 'MARKED_SYNCED');
}

export async function guardarDescriptor(employeeId: string, descriptor: number[], validadeHoras: number): Promise<void> {
  await perguntar('CACHE_DESCRIPTOR', { employee_id: employeeId, descriptor, validade_horas: validadeHoras }, 'DESCRIPTOR_CACHED');
}

export async function lerDescriptorCache(
  employeeId: string,
): Promise<number[] | null> {
  const r = await perguntar<{ data: { employee_id: string; descriptor: number[] } | null }>(
    'GET_DESCRIPTOR', undefined, 'DESCRIPTOR',
  );
  const reg = r?.data;
  if (!reg || !Array.isArray(reg.descriptor)) return null;
  // aparelho que trocou de dono não devolve o rosto do dono anterior
  if (reg.employee_id && employeeId && reg.employee_id !== employeeId) {
    await apagarBiometria();
    return null;
  }
  return reg.descriptor;
}

export async function apagarBiometria(): Promise<void> {
  await perguntar('WIPE_BIOMETRIA', undefined, 'BIOMETRIA_APAGADA');
}

/** É erro de REDE (vale guardar offline) ou o servidor respondendo (não vale)? */
export function ehFalhaDeRede(e: unknown): boolean {
  const err = e as { response?: { status?: number }; code?: string; message?: string };
  const st = err?.response?.status;
  // 🔴 28/09/2026 — 502 NÃO É RECUSA. Medido: das 13:00 às 13:02 o backend ficou fora e o nginx
  // devolveu 502 a 205 requisições, 72 delas batidas de ponto, de 4 pessoas — as mesmas quatro
  // que disseram "apertei e nada aconteceu" (Telma, Livia, Daniel, Edilene), no minuto de maior
  // movimento do dia, a volta do almoço.
  //
  // ⭐ Estes códigos vêm do NGINX, não do aplicativo: significam que a batida nunca foi vista.
  // A consequência é idêntica à de não haver sinal, então guardar no aparelho não contorna
  // recusa nenhuma — recusar é que apaga um fato que aconteceu de verdade.
  //
  // 504 fica FORA de propósito: ali o nginx desistiu de esperar e o aplicativo pode ter
  // gravado a batida. Guardar offline nesse caso duplicaria o ponto da pessoa.
  if (st === 502 || st === 503) return true;
  if (st) return false; // o aplicativo respondeu: 4xx e 5xx dele são decisão, não falta de sinal
  return true;
}
