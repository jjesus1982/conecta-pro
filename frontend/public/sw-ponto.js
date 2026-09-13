/**
 * Service Worker do Ponto — Conecta PRO
 *
 * O que ele faz:
 * - guarda a página da batida e os MODELOS do reconhecimento facial no cache, para a câmera
 *   funcionar sem sinal (sem os modelos, offline a tela abre e nunca reconhece);
 * - guarda a batida feita offline no IndexedDB, com o rosto capturado, a hora do APARELHO, o
 *   identificador do aparelho e a chave idempotente;
 * - guarda o descriptor de referência com VALIDADE, e o apaga no logout (LGPD: é dado biométrico);
 * - avisa a página quando o sinal volta. Ele NÃO sincroniza sozinho — ver abaixo.
 *
 * 🔴 POR QUE O SW NÃO SINCRONIZA MAIS SOZINHO (frente 02, 13/09/2026)
 * A versão anterior fazia `fetch('/api/v1/people-management/ponto/sync')` SEM cabeçalho de
 * autorização — um service worker não enxerga o localStorage onde o token vive. Duas consequências:
 * a chamada nunca passava do 401, e o destino era a rota antiga, que grava a batida SEM reconferir
 * o rosto no servidor. Ou seja: se um dia ela passasse, seria exatamente a porta de fraude que
 * esta frente existe para fechar.
 * Agora quem sincroniza é a PÁGINA, que tem o token e chama `/ponto/offline/sync` (a rota que
 * reconfere). O preço é que a fila só sobe quando o app é aberto de novo — aceito de propósito:
 * guardar o token do porteiro no IndexedDB, num celular compartilhado de guarita, é pior.
 */

const CACHE_NAME = 'conecta-ponto-v2';

/** Sem estes arquivos a câmera abre offline e não reconhece ninguém. */
const CACHE_ASSETS = [
  '/modulos/meu-espaco',
  '/modulos/gestao-pessoas/ponto',
  '/modulos/gestao-pessoas/ponto/batida',
  '/models/tiny_face_detector_model-weights_manifest.json',
  '/models/tiny_face_detector_model-shard1',
  '/models/face_landmark_68_model-weights_manifest.json',
  '/models/face_landmark_68_model-shard1',
  '/models/face_recognition_model-weights_manifest.json',
  '/models/face_recognition_model-shard1',
  '/models/face_recognition_model-shard2',
];

// IndexedDB
const DB_NAME = 'conecta_ponto_offline';
const DB_VERSION = 1;
const STORE_PUNCHES = 'pending_punches';
const STORE_EMPLOYEE = 'cached_employee';
const STORE_SCHEDULE = 'cached_schedule';
const STORE_SYNC = 'sync_metadata';

// ==========================================
// INSTALL / ACTIVATE
// ==========================================
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) =>
      // um asset que falta não pode impedir os outros de entrar no cache: `addAll` é tudo-ou-nada
      Promise.all(CACHE_ASSETS.map((u) => cache.add(u).catch(() => null)))
    )
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(names.filter((n) => n !== CACHE_NAME).map((n) => caches.delete(n)))
    )
  );
  self.clients.claim();
});

// ==========================================
// FETCH — rede primeiro, cache quando não há rede
// ==========================================
self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return response;
      })
      .catch(() =>
        caches.match(event.request).then((cached) => cached || new Response('Offline', { status: 503 }))
      )
  );
});

// ==========================================
// MENSAGENS DA PÁGINA
// ==========================================
self.addEventListener('message', (event) => {
  const { type, data } = event.data || {};
  // a página pergunta por MessageChannel (event.ports[0]) e espera a resposta naquela porta;
  // sem porta, cai no broadcast para o cliente que perguntou
  const responder = (msg) => {
    if (event.ports && event.ports[0]) event.ports[0].postMessage(msg);
    else if (event.source) event.source.postMessage(msg);
  };

  switch (type) {
    case 'SAVE_PUNCH_OFFLINE':
      savePunchOffline(data).then((punch) => responder({ type: 'PUNCH_SAVED_OFFLINE', data: punch }));
      break;

    case 'GET_PENDING':
      getPendingPunches().then((punches) => responder({ type: 'PENDING', punches }));
      break;

    case 'GET_PENDING_COUNT':
      getPendingPunches().then((p) => responder({ type: 'PENDING_COUNT', count: p.length }));
      break;

    case 'MARK_SYNCED':
      // a página já subiu a fila por /ponto/offline/sync e diz o que foi aceito
      markAsSynced(data?.punch_ids || []).then(() => responder({ type: 'MARKED_SYNCED' }));
      break;

    case 'CACHE_DESCRIPTOR':
      // 🔒 descriptor é dado biométrico: entra com validade e nunca vai para o localStorage
      cacheDescriptor(data).then(() => responder({ type: 'DESCRIPTOR_CACHED' }));
      break;

    case 'GET_DESCRIPTOR':
      getDescriptor().then((d) => responder({ type: 'DESCRIPTOR', data: d }));
      break;

    case 'WIPE_BIOMETRIA':
      // logout: apaga o rosto de referência e o rosto guardado nas batidas ainda não enviadas
      wipeBiometria().then(() => responder({ type: 'BIOMETRIA_APAGADA' }));
      break;
  }
});

// ==========================================
// INDEXEDDB
// ==========================================
function openDB() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = (event) => {
      const db = event.target.result;
      if (!db.objectStoreNames.contains(STORE_PUNCHES)) {
        const store = db.createObjectStore(STORE_PUNCHES, { keyPath: 'punch_id' });
        store.createIndex('employee_id', 'employee_id');
        store.createIndex('timestamp', 'timestamp');
        store.createIndex('synced', 'synced');
      }
      if (!db.objectStoreNames.contains(STORE_EMPLOYEE)) db.createObjectStore(STORE_EMPLOYEE, { keyPath: 'id' });
      if (!db.objectStoreNames.contains(STORE_SCHEDULE)) db.createObjectStore(STORE_SCHEDULE, { keyPath: 'id' });
      if (!db.objectStoreNames.contains(STORE_SYNC)) db.createObjectStore(STORE_SYNC, { keyPath: 'key' });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

/**
 * Guarda a batida offline. `chave_idempotente` é (pessoa, MINUTO da hora do aparelho, aparelho) —
 * a MESMA regra do servidor. Reenviar a fila inteira é seguro: o servidor devolve "duplicada" em
 * vez de criar uma segunda batida.
 */
async function savePunchOffline(punchData) {
  const db = await openDB();
  const tx = db.transaction(STORE_PUNCHES, 'readwrite');
  const punch = {
    ...punchData,
    punch_id: punchData.punch_id || crypto.randomUUID(),
    synced: false,
    saved_at: new Date().toISOString(),
  };
  tx.objectStore(STORE_PUNCHES).put(punch);
  return new Promise((resolve) => {
    tx.oncomplete = () => resolve(punch);
  });
}

async function getPendingPunches() {
  const db = await openDB();
  const store = db.transaction(STORE_PUNCHES, 'readonly').objectStore(STORE_PUNCHES);
  return new Promise((resolve) => {
    // IDBKeyRange.only(false) porque booleano não é chave válida em alguns navegadores
    const request = store.getAll();
    request.onsuccess = () => resolve((request.result || []).filter((p) => !p.synced));
    request.onerror = () => resolve([]);
  });
}

async function markAsSynced(punchIds) {
  if (!punchIds.length) return true;
  const db = await openDB();
  const tx = db.transaction(STORE_PUNCHES, 'readwrite');
  const store = tx.objectStore(STORE_PUNCHES);
  for (const id of punchIds) {
    const request = store.get(id);
    request.onsuccess = () => {
      const punch = request.result;
      if (punch) {
        punch.synced = true;
        punch.synced_at = new Date().toISOString();
        // 🔒 o rosto já cumpriu a função: foi ao servidor e foi reconferido. Não fica no aparelho.
        delete punch.descriptor;
        delete punch.foto_base64;
        store.put(punch);
      }
    };
  }
  return new Promise((resolve) => {
    tx.oncomplete = () => resolve(true);
  });
}

// ==========================================
// DESCRIPTOR DE REFERÊNCIA — biometria com prazo
// ==========================================

/** `{ employee_id, descriptor, validade_horas }` → guardado com o instante de expiração. */
async function cacheDescriptor(data) {
  if (!data || !Array.isArray(data.descriptor)) return false;
  const horas = Number(data.validade_horas) > 0 ? Number(data.validade_horas) : 24;
  const db = await openDB();
  const tx = db.transaction(STORE_EMPLOYEE, 'readwrite');
  tx.objectStore(STORE_EMPLOYEE).put({
    id: 'face_ref',
    employee_id: data.employee_id || null,
    descriptor: data.descriptor,
    expira_em: Date.now() + horas * 3600 * 1000,
  });
  return new Promise((resolve) => {
    tx.oncomplete = () => resolve(true);
  });
}

/** Devolve o descriptor só dentro da validade — vencido é apagado na hora, não devolvido. */
async function getDescriptor() {
  const db = await openDB();
  const store = db.transaction(STORE_EMPLOYEE, 'readonly').objectStore(STORE_EMPLOYEE);
  const reg = await new Promise((resolve) => {
    const r = store.get('face_ref');
    r.onsuccess = () => resolve(r.result || null);
    r.onerror = () => resolve(null);
  });
  if (!reg) return null;
  if (!reg.expira_em || reg.expira_em < Date.now()) {
    await wipeBiometria();
    return null;
  }
  return reg;
}

/** Logout, troca de pessoa no aparelho, ou validade vencida. */
async function wipeBiometria() {
  const db = await openDB();
  const tx = db.transaction([STORE_EMPLOYEE, STORE_PUNCHES], 'readwrite');
  tx.objectStore(STORE_EMPLOYEE).delete('face_ref');
  // batidas ainda não enviadas PERMANECEM (a pessoa trabalhou e o registro é dela), mas sem o
  // rosto: o servidor vai tratá-las como "não deu para comparar" e mandar para o DP conferir.
  const req = tx.objectStore(STORE_PUNCHES).getAll();
  req.onsuccess = () => {
    for (const p of req.result || []) {
      if (p.synced) continue;
      delete p.descriptor;
      delete p.foto_base64;
      tx.objectStore(STORE_PUNCHES).put(p);
    }
  };
  return new Promise((resolve) => {
    tx.oncomplete = () => resolve(true);
  });
}

// ==========================================
// VOLTA DO SINAL — avisa a página, que é quem tem o token
// ==========================================
async function avisarClientes(tipo) {
  const clients = await self.clients.matchAll({ includeUncontrolled: true });
  const pendentes = await getPendingPunches();
  clients.forEach((c) => c.postMessage({ type: tipo, pendentes: pendentes.length }));
}

self.addEventListener('online', () => {
  avisarClientes('SYNC_NECESSARIO');
});

self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-punches') event.waitUntil(avisarClientes('SYNC_NECESSARIO'));
});
