// Fundação de documentos do REDESIGN — abrir (HTML/nova aba) e baixar (PDF/formato nativo)
// QUALQUER documento gerado/puxado/inserido, com o Bearer do localStorage (o <a href> cru
// não carrega o token). Cobre os 3 MODOS de fonte que o backend do Conecta PRO usa:
//   • 'blob' (default) — endpoint devolve o arquivo direto (FileResponse/StreamingResponse).
//   • 'json' — endpoint devolve { content, filename, mime? } (ex.: conciliação bancária).
//   • Content-Disposition — o nome do arquivo vem no header (honrado no download).
// Reusa abrirPdf (que já surfaça a mensagem de erro REAL do servidor).
import { abrirPdf } from './pdf';

export type DocFmt = 'pdf' | 'html' | 'xml' | 'txt' | 'xlsx' | 'csv' | 'zip' | 'json';

export interface DocRef {
  label: string;          // texto do botão/chip
  url?: string;           // rota (mesma origem, normalmente /api/v1/...). Copiar EXATA do backend.
  mode?: 'blob' | 'json'; // 'blob' = arquivo direto (default); 'json' = { content, filename }
  fmt?: DocFmt;           // decide ícone e se há "Abrir" (só pdf/html/xml/txt/json abrem inline)
  filename?: string;      // nome sugerido no download (senão usa Content-Disposition/servidor)
  disabled?: boolean;     // documento indisponível (stub/placeholder/sem transmissão) → botão off
  motivo?: string;        // tooltip quando disabled ("aguardando emissão real")
  gate?: string;          // informativo (o gate REAL é no backend; isto é só UX)
}

function token(): string {
  try {
    return (typeof window !== 'undefined'
      ? localStorage.getItem('access_token') || localStorage.getItem('token') || '' : '');
  } catch { return ''; }
}

async function alertErro(res: Response, verbo: string) {
  let msg = `Não foi possível ${verbo} o documento (HTTP ${res.status}).`;
  try {
    const j = await res.json();
    if (j?.detail) msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail);
  } catch { /* corpo não-JSON — mantém padrão */ }
  alert(msg);
}

// modo 'json': backend devolve { content, filename, mime? } → decodifica para Blob.
async function fetchJsonDoc(url: string, verbo: string): Promise<{ blob: Blob; filename: string } | null> {
  let res: Response;
  try {
    res = await fetch(url, { headers: { Authorization: `Bearer ${token()}` } });
  } catch { alert(`Falha de rede ao ${verbo} o documento.`); return null; }
  if (!res.ok) { await alertErro(res, verbo); return null; }
  const j = await res.json().catch(() => null);
  if (!j || j.content == null) { alert('Resposta inesperada do servidor (sem conteúdo).'); return null; }
  const mime = j.mime || (String(j.filename || '').endsWith('.csv') ? 'text/csv;charset=utf-8' : 'application/octet-stream');
  return { blob: new Blob([j.content], { type: mime }), filename: j.filename || 'documento' };
}

function dispararDownload(blob: Blob, filename: string) {
  const objUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = objUrl; a.download = filename || '';
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(objUrl), 60000);
}

// Abrível inline = dá para VER no navegador. Binários (xlsx/csv/zip) só baixam.
export function isAbrivel(fmt?: DocFmt): boolean {
  return !fmt || ['pdf', 'html', 'xml', 'txt', 'json'].includes(fmt);
}

export async function abrirDoc(doc: DocRef): Promise<void> {
  if (doc.disabled || !doc.url) return;
  if (doc.mode === 'json') {
    const r = await fetchJsonDoc(doc.url, 'abrir');
    if (!r) return;
    const objUrl = URL.createObjectURL(r.blob);
    window.open(objUrl, '_blank', 'noopener');
    setTimeout(() => URL.revokeObjectURL(objUrl), 60000);
    return;
  }
  await abrirPdf(doc.url); // 'blob': abre em nova aba via object URL
}

export async function baixarDoc(doc: DocRef): Promise<void> {
  if (doc.disabled || !doc.url) return;
  if (doc.mode === 'json') {
    const r = await fetchJsonDoc(doc.url, 'baixar');
    if (!r) return;
    dispararDownload(r.blob, doc.filename || r.filename);
    return;
  }
  await abrirPdf(doc.url, { download: true, nome: doc.filename }); // 'blob': baixa o arquivo
}
