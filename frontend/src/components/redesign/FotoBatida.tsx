'use client';

import { useEffect, useState } from 'react';

/**
 * Miniatura da SELFIE de uma batida de ponto.
 *
 * Existe porque a foto é o que responde três perguntas que o DP faz todo dia e não tinha
 * como responder aqui: a pessoa está de farda? o agente de portaria está barbeado? é ela
 * mesma no posto? (pedido do Jordan, 14/09/2026 — é o que a Pyetra já via no Sólides).
 *
 * `<img src>` não serve: a rota exige token, e o navegador não manda o Authorization numa
 * tag de imagem. Então busca com o token e vira object-URL, o mesmo caminho dos documentos.
 * O object-URL é revogado no desmonte — sem isso, rolar uma tabela de 2.000 linhas vaza
 * memória até a aba travar.
 */
export function FotoBatida({ url, alt }: { url: string; alt?: string }) {
  const [src, setSrc] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [grande, setGrande] = useState(false);

  useEffect(() => {
    let vivo = true;
    let obj: string | null = null;
    (async () => {
      try {
        const tk = typeof window !== 'undefined' ? localStorage.getItem('access_token') || '' : '';
        const r = await fetch(url, { headers: { Authorization: `Bearer ${tk}` } });
        if (!r.ok) {
          // 404 com motivo é informação, não falha: batida antiga não tem foto guardada.
          const j = await r.json().catch(() => null);
          if (vivo) setErro(j?.detail ? String(j.detail).slice(0, 80) : 'sem foto');
          return;
        }
        const b = await r.blob();
        obj = URL.createObjectURL(b);
        if (vivo) setSrc(obj); else URL.revokeObjectURL(obj);
      } catch {
        if (vivo) setErro('falha ao carregar');
      }
    })();
    return () => { vivo = false; if (obj) URL.revokeObjectURL(obj); };
  }, [url]);

  if (erro) return <span style={{ fontSize: 11, color: 'var(--placeholder)' }} title={erro}>—</span>;
  if (!src) return <span style={{ fontSize: 11, color: 'var(--placeholder)' }}>…</span>;

  return (
    <>
      <img
        src={src}
        alt={alt || 'Selfie da batida'}
        onClick={() => setGrande(true)}
        style={{ width: 40, height: 40, objectFit: 'cover', borderRadius: 6, cursor: 'zoom-in', border: '1px solid var(--border, #d8dee9)' }}
      />
      {grande && (
        <div
          onClick={() => setGrande(false)}
          style={{ position: 'fixed', inset: 0, zIndex: 80, background: 'rgba(0,0,0,.72)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'zoom-out' }}
        >
          <figure style={{ margin: 0, textAlign: 'center' }}>
            <img src={src} alt={alt || 'Selfie da batida'} style={{ maxWidth: '86vw', maxHeight: '78vh', borderRadius: 10 }} />
            {alt && <figcaption style={{ color: '#fff', marginTop: 10, fontSize: 13 }}>{alt}</figcaption>}
          </figure>
        </div>
      )}
    </>
  );
}
