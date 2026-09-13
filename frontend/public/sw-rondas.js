/**
 * Service Worker da Ronda Mobile — frente 6 (12/09/2026).
 *
 * Só a CASCA: guarda a página, os chunks e os GETs da API que a ronda-mobile pediu com sinal
 * ("download dos locais para uso offline"), e devolve do cache quando a rede falha.
 * A FILA de checkpoints/fotos NÃO mora aqui — fica no IndexedDB da página
 * (src/features/rondas/filaOffline.ts), porque o envio precisa do token do localStorage.
 *
 * Escopo: /modulos/operacional/ronda-mobile (registrado pela própria página). Não toca
 * sw.js (push) nem sw-ponto.js.
 */

const CACHE = 'conecta-rondas-v1';

self.addEventListener('install', (event) => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((nomes) => Promise.all(nomes.filter((n) => n.startsWith('conecta-rondas-') && n !== CACHE).map((n) => caches.delete(n))))
      .then(() => self.clients.claim())
  );
});

// rede primeiro; se cair, o que foi visto por último. Só GET, só mesma origem.
self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  // fotos dos checkpoints são blobs autenticados e grandes: não cacheia
  if (url.pathname.includes('/fotos/')) return;

  event.respondWith(
    fetch(req)
      .then((resp) => {
        if (resp.ok) {
          const clone = resp.clone();
          caches.open(CACHE).then((c) => c.put(req, clone)).catch(() => undefined);
        }
        return resp;
      })
      .catch(() => caches.match(req).then((hit) => hit || new Response('Sem sinal e sem cópia local', { status: 503 })))
  );
});
