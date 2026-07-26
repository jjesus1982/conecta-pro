'use client';

import { useEffect, useMemo, useState, type ReactNode } from 'react';
import dynamic from 'next/dynamic';
import { PanelLeftClose, PanelLeft, Menu, Search, Plus, LogOut, LayoutGrid } from 'lucide-react';
import RdBell from './RdBell';
import { MODULES } from './modules';

// Scanner de câmera (QR PIX + código de barras de boleto) — reusa o componente do clássico.
// client-only (usa a câmera); só carrega quando o usuário abre o scanner.
const ScannerPagamento = dynamic(() => import('@/components/financeiro/ScannerPagamento'), { ssr: false });
const RdChart = dynamic(() => import('./RdChart'), { ssr: false });
import { rdLogout } from './session';
import { DocButtons } from './DocButtons';
import { abrirDoc, type DocRef } from '@/lib/docsource';
import { ExportMenu } from './ExportMenu';
import ChatScreen from './ChatScreen';

// ── Ícone via path bruto do pacote (lucide, traço 2px) ───────────────────────
function Ico({ d, size = 17, stroke = 'currentColor' }: { d: string; size?: number; stroke?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={stroke}
      strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" style={{ flex: 'none' }}>
      <path d={d} />
    </svg>
  );
}

type MenuItem = { id: string; label: string; icon: string };
function normMenu(menu: unknown[]): MenuItem[] {
  return (menu || []).map((it: unknown) => {
    if (Array.isArray(it)) return { id: it[0], label: it[1], icon: it[2] };
    const o = it as { id: string; label: string; icon: string };
    return { id: o.id, label: o.label, icon: o.icon };
  }).filter((m) => m.id);
}

// ── Pílula de status ─────────────────────────────────────────────────────────
function Pill({ v, color, bg }: { v: ReactNode; color: string; bg: string }) {
  return <span className="rd-pill" style={{ color, background: bg }}>{v}</span>;
}

// ── Renderizadores de tela (1:1 com o template dc) ───────────────────────────
function DashScreen({ scr, onNav }: { scr: any; onNav?: (id: string) => void }) {
  return (
    <div className="rd-dash">
      <div className="rd-dash-kpis">
        {(scr.kpis || []).map((k: any, i: number) => {
          const clickable = !!(onNav && k.to);
          return (
            <div className="rd-kpi" key={i} onClick={clickable ? () => onNav!(k.to) : undefined}
              role={clickable ? 'button' : undefined} tabIndex={clickable ? 0 : undefined}
              title={clickable ? 'Ver detalhes' : undefined}
              style={clickable ? { cursor: 'pointer' } : undefined}>
              <div className="rd-kpi-ico"><Ico d={k.icon} size={20} stroke="var(--navy)" /></div>
              <div className="rd-kpi-v" style={{ color: k.color || 'var(--ink)' }}>{k.v}</div>
              <div className="rd-kpi-l">{k.l}{clickable ? ' ›' : ''}</div>
            </div>
          );
        })}
      </div>
      {Array.isArray(scr.charts) && scr.charts.length > 0 && (
        <div className="rd-panels" style={{ ['--pg' as any]: scr.chartGrid || '1fr 1fr', marginBottom: 14 }}>
          {scr.charts.map((c: any, i: number) => (
            <div className="rd-panel" key={`c${i}`}>
              <div className="rd-panel-h">{c.title}</div>
              <RdChart chart={c} />
            </div>
          ))}
        </div>
      )}
      <div className="rd-panels" style={{ ['--pg' as any]: scr.panelGrid || '1fr' }}>
        {(scr.panels || []).map((p: any, i: number) => (
          <div className="rd-panel" key={i}>
            <div className="rd-panel-h">{p.title}</div>
            {(p.rows || []).map((r: any, j: number) => (
              <div className="rd-panel-row" key={j}>
                <span className="l">{r.left}</span>
                {r.right != null && <Pill v={r.right} color={r.color || 'var(--ink-weak)'} bg={r.bg || 'var(--fill)'} />}
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

// TableScreen — tabela + (opcional) painéis de contexto abaixo (tela COMPOSTA, p/ fidelidade
// de telas do clássico que têm tabela + seções: ex. riscos trabalhista + tributário).
function TableScreen({ scr }: { scr: any }) {
  const allRows = scr.rows || [];
  // Seletor opcional por coluna (ex.: Competência na Folha): scr.filterCol = índice da coluna.
  // Dropdown filtra as linhas client-side; default = 1º valor (as linhas já vêm ordenadas desc).
  // Retrocompatível: telas sem filterCol não mudam.
  const filterCol: number | null = typeof scr.filterCol === 'number' ? scr.filterCol : null;
  const filterVals: string[] = filterCol != null
    ? Array.from(new Set(allRows.map((r: any) => r.cells?.[filterCol]?.v).filter((v: any) => v != null && v !== '')).values()).map(String)
    : [];
  const [sel, setSel] = useState<string>('');
  const active = filterCol != null ? (sel || filterVals[0] || '') : '';
  const rows = (filterCol != null && active)
    ? allRows.filter((r: any) => String(r.cells?.[filterCol]?.v) === active)
    : allRows;
  // Documentos por-LINHA + Editar por-LINHA (edit={endpoint,method,fields}) → coluna de ações.
  // Retrocompatível: telas sem docs/edit não mudam.
  const hasRowDocs = allRows.some((r: any) => Array.isArray(r.docs) && r.docs.length > 0);
  const hasRowEdit = allRows.some((r: any) => r.edit && Array.isArray(r.edit.fields));
  const hasRowActions = allRows.some((r: any) => Array.isArray(r.actions) && r.actions.length);
  const hasActions = hasRowDocs || hasRowEdit || hasRowActions;
  const grid = hasActions ? `${scr.grid} minmax(150px, auto)` : scr.grid;
  const cols = hasActions ? [...(scr.cols || []), hasRowDocs ? 'Documento' : 'Ações'] : (scr.cols || []);
  const [editRow, setEditRow] = useState<any>(null);
  const [editVals, setEditVals] = useState<Record<string, any>>({});
  const [editMsg, setEditMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [editBusy, setEditBusy] = useState(false);
  return (
    <div className="rd-tbl-wrap">
      {filterCol != null && filterVals.length > 0 && (
        <div style={{ marginBottom: 10, display: 'flex', alignItems: 'center', gap: 8 }}>
          <label style={{ fontSize: 12.5, color: 'var(--placeholder)', fontWeight: 600 }}>{scr.filterLabel || 'Filtrar'}:</label>
          <select value={active} onChange={(e) => setSel(e.target.value)}
            style={{ padding: '6px 12px', borderRadius: 8, fontSize: 13, border: '1px solid var(--border, #d8dee9)', background: 'var(--card, #fff)', color: 'var(--ink, #16277D)', fontWeight: 600, cursor: 'pointer' }}>
            {filterVals.map((v: string, i: number) => <option key={i} value={v}>{v}</option>)}
          </select>
          <span style={{ fontSize: 12, color: 'var(--placeholder)' }}>{rows.length} folha(s)</span>
        </div>
      )}
      <div className="rd-tbl-scroll">
        <div className="rd-tbl-inner">
          <div className="rd-tbl-head" style={{ gridTemplateColumns: grid }}>
            {cols.map((c: string, i: number) => <span className="rd-tbl-th" key={i}>{c}</span>)}
          </div>
          {rows.map((row: any, i: number) => (
            <div className="rd-tbl-row" style={{ gridTemplateColumns: grid }} key={i}>
              {(row.cells || []).map((cell: any, j: number) => (
                <span className="rd-tbl-cell" key={j}>
                  {cell.isBadge
                    ? <Pill v={cell.v} color={cell.color} bg={cell.bg} />
                    : <>
                        {cell.ini && <span className="rd-init">{cell.ini}</span>}
                        <span className="tx" style={{ fontWeight: cell.w || 500, color: cell.tc || '#334155' }}>{cell.v}</span>
                      </>}
                </span>
              ))}
              {hasActions && (
                <span className="rd-tbl-cell" style={{ justifyContent: 'flex-end', gap: 6 }}>
                  {Array.isArray(row.docs) && row.docs.length > 0 && <DocButtons docs={row.docs} compact />}
                  {row.edit && Array.isArray(row.edit.fields) && (
                    <button type="button" className={`rd-btn ${row.edit.btnStyle === 'primary' ? 'rd-btn-primary' : 'rd-btn-outline'}`} style={{ padding: '5px 10px', fontSize: 12 }}
                      onClick={() => { setEditRow(row.edit); const v: Record<string, any> = {}; row.edit.fields.forEach((f: any) => { v[f.key] = f.value ?? ''; }); setEditVals(v); setEditMsg(null); }}>
                      {row.edit.btnLabel || 'Editar'}
                    </button>
                  )}
                  {Array.isArray(row.actions) && row.actions.map((a:any, k:number) => (
                    <button key={k} type="button" className={`rd-btn ${a.btnStyle==='primary'?'rd-btn-primary':'rd-btn-outline'}`} style={{ padding:'5px 10px', fontSize:12 }}
                      onClick={() => { setEditRow(a); const v:Record<string,any>={}; (a.fields||[]).forEach((f:any)=>{v[f.key]=f.value??'';}); setEditVals(v); setEditMsg(null); }}>
                      {a.btnLabel || 'Ação'}
                    </button>
                  ))}
                </span>
              )}
            </div>
          ))}
        </div>
      </div>
      {Array.isArray(scr.panels) && scr.panels.length > 0 && (
        <div className="rd-panels" style={{ ['--pg' as any]: scr.panelGrid || '1fr 1fr', marginTop: 16 }}>
          {scr.panels.map((p: any, i: number) => (
            <div className="rd-panel" key={i}>
              <div className="rd-panel-h">{p.title}</div>
              {(p.rows || []).map((r: any, j: number) => (
                <div className="rd-panel-row" key={j}>
                  <span className="l">{r.left}</span>
                  {r.right != null && <Pill v={r.right} color={r.color || 'var(--ink-weak)'} bg={r.bg || 'var(--fill)'} />}
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
      {editRow && (
        <div onClick={() => setEditRow(null)} style={{ position: 'fixed', inset: 0, background: 'rgba(15,27,58,.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: 16 }}>
          <div onClick={(e) => e.stopPropagation()} style={{ background: 'var(--card, #fff)', borderRadius: 14, padding: 20, width: 'min(560px, 94vw)', maxHeight: '88vh', overflow: 'auto', boxShadow: '0 20px 60px rgba(0,0,0,.25)' }}>
            <div style={{ fontWeight: 700, fontSize: 15, color: 'var(--ink, #16277D)', marginBottom: 12 }}>{editRow.title || 'Editar'}</div>
            {editMsg && <div className={`rd-badge ${editMsg.ok ? 'rd-b-success' : 'rd-b-error'}`} style={{ height: 'auto', padding: '8px 12px', fontSize: 12.5, marginBottom: 10, display: 'block' }}>{editMsg.text}</div>}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              {editRow.fields.map((f: any, i: number) => (
                <div key={i} style={{ gridColumn: f.span === 'span 2' ? '1 / -1' : 'auto', display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <label style={{ fontSize: 12, color: 'var(--placeholder)', fontWeight: 600 }}>{f.label}</label>
                  {f.type === 'select'
                    ? <select className="rd-input" value={editVals[f.key] ?? ''} onChange={(e) => setEditVals((s) => ({ ...s, [f.key]: e.target.value }))}>
                        {(f.options || []).map((o: any, k: number) => <option key={k} value={o.value}>{o.label}</option>)}
                      </select>
                    : f.type === 'textarea'
                      ? <textarea className="rd-input" style={{ height: 80, resize: 'vertical' }} value={editVals[f.key] ?? ''} onChange={(e) => setEditVals((s) => ({ ...s, [f.key]: e.target.value }))} />
                      : <input className="rd-input" type={f.type === 'date' ? 'date' : 'text'} value={editVals[f.key] ?? ''} onChange={(e) => setEditVals((s) => ({ ...s, [f.key]: e.target.value }))} />}
                </div>
              ))}
            </div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 14 }}>
              <button type="button" className="rd-btn rd-btn-outline" onClick={() => setEditRow(null)}>Cancelar</button>
              <button type="button" className="rd-btn rd-btn-primary" disabled={editBusy} onClick={async () => {
                setEditBusy(true); setEditMsg(null);
                try {
                  let tok: string | null = null; try { tok = localStorage.getItem('access_token'); } catch { /* */ }
                  const res = await fetch(editRow.endpoint, { method: editRow.method || 'PATCH', headers: { 'Content-Type': 'application/json', ...(tok ? { Authorization: `Bearer ${tok}` } : {}) }, body: JSON.stringify({ ...(editRow.fixed || {}), ...editVals }) });
                  const d = await res.json().catch(() => ({}));
                  if (!res.ok) throw new Error(d.detail || 'Não foi possível salvar.');
                  setEditMsg({ ok: true, text: d.message || editRow.okMsg || 'Salvo. Recarregue a tela para ver a alteração.' });
                } catch (e) { setEditMsg({ ok: false, text: e instanceof Error ? e.message : 'Erro.' }); }
                finally { setEditBusy(false); }
              }}>{editBusy ? 'Enviando…' : (editRow.submitLabel || 'Salvar')}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function CardsScreen({ scr }: { scr: any }) {
  return (
    <div className="rd-cardgrid">
      {(scr.cards || []).map((cd: any, i: number) => (
        <div className="rd-dc-card" key={i}>
          <div className="rd-dc-card-h">
            <div style={{ minWidth: 0 }}>
              <div className="rd-dc-card-t">{cd.title}</div>
              {cd.sub && <div className="rd-dc-card-s">{cd.sub}</div>}
            </div>
            {cd.badge && <Pill v={cd.badge} color={cd.color || 'var(--ink-weak)'} bg={cd.bg || 'var(--fill)'} />}
          </div>
          {cd.hasStats && (
            <div className="rd-dc-stats">
              {(cd.stats || []).map((s: any, j: number) => (
                <div key={j}>
                  <div className="v" style={{ color: s.color || 'var(--ink)' }}>{s.v}</div>
                  <div className="l">{s.l}</div>
                </div>
              ))}
            </div>
          )}
          {cd.hasLines && (
            <div className="rd-dc-lines">
              {(cd.lines || []).map((ln: any, j: number) => (
                <div className="row" key={j}><span className="l">{ln.l}</span><span className="v">{ln.v}</span></div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function ListScreen({ scr }: { scr: any }) {
  return (
    <div className="rd-list-card">
      {(scr.items || []).map((it: any, i: number) => (
        <div className="rd-list-row" key={i}>
          {it.dot && <span className="dot" style={{ background: it.dot }} />}
          <div className="main">
            <div className="tt">{it.title}</div>
            {it.meta && <div className="mt">{it.meta}</div>}
          </div>
          {it.badge && <Pill v={it.badge} color={it.color || 'var(--ink-weak)'} bg={it.bg || 'var(--fill)'} />}
        </div>
      ))}
    </div>
  );
}

// FormScreen (Fase 2): data-driven + fluxo confirmar/OTP que casa com o redesign_write_gate.
// Backend responde { otp_required: true, ref, message } → a tela pede o código e reenvia com
// otp_code. scr.submit.confirm (string) força uma confirmação humana antes de disparar.
function FormScreen({ scr }: { scr: any }) {
  const [vals, setVals] = useState<Record<string, string>>({});
  const [files, setFiles] = useState<Record<string, File | null>>({});
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [otp, setOtp] = useState<{ ref: string; code: string } | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [attMsg, setAttMsg] = useState<string | null>(null);
  const [scanOpen, setScanOpen] = useState(false);
  const [colar, setColar] = useState(''); // campo "colar código" (PIX copia-e-cola / linha digitável)
  const set = (k: string, v: string) => setVals((s) => ({ ...s, [k]: v }));
  const gated = !!(scr.submit && scr.submit.gated); // ação money/gov (visual de aviso)

  // Preenche o form a partir da resposta de um endpoint de decode (fills = {campoForm: chaveResposta}).
  function aplicarFills(r: any, fills: Record<string, string>) {
    const upd: Record<string, string> = {};
    for (const [fk, rk] of Object.entries(fills || {})) {
      const v = (r as any)[rk];
      if (v != null && v !== '') upd[fk] = fk === 'valor' && !isNaN(Number(v)) ? Number(v).toFixed(2) : String(v);
    }
    setVals((s) => ({ ...s, ...upd }));
    return upd;
  }

  // Decodifica um código colado/escaneado (PIX copia-e-cola ou QR) via endpoint read-only (NÃO paga).
  async function decode(texto: string, cfg: any) {
    const t = (texto || '').trim();
    if (!t || !cfg) return;
    setAttMsg('Lendo o código…');
    try {
      let tok = ''; try { tok = localStorage.getItem('access_token') || ''; } catch { /* */ }
      const res = await fetch(cfg.endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(tok ? { Authorization: `Bearer ${tok}` } : {}) },
        body: JSON.stringify({ [cfg.field || 'brcode']: t }),
      });
      const r = await res.json().catch(() => ({}));
      const okFlag = cfg.okFlag || 'valido';
      if (!res.ok || (okFlag && !r[okFlag])) {
        setAttMsg(r?.motivo || (typeof r?.detail === 'string' ? r.detail : 'Código inválido ou não reconhecido.'));
        return;
      }
      const upd = aplicarFills(r, cfg.fills || {});
      // QR dinâmico: guarda o copia-e-cola bruto pra preservar o txid do PSP.
      if (r.dinamico && cfg.dynamicField) setVals((s) => ({ ...s, [cfg.dynamicField]: t }));
      const nome = r.nome || r.chave || upd.chave || '';
      setAttMsg(`Lido${nome ? `: ${nome}` : ''}${r.valor ? ` — R$ ${Number(r.valor).toFixed(2)}` : ''}. Confira antes de enviar.`);
    } catch { setAttMsg('Falha ao ler o código.'); }
  }

  // Câmera detectou algo: QR (ou texto tipo PIX) → decode; código de barras → preenche o campo do boleto.
  function onScan(texto: string, formato: 'qr' | 'barcode') {
    setScanOpen(false);
    const t = (texto || '').trim();
    const ehPix = formato === 'qr' || /br\.gov\.bcb\.pix/i.test(t) || t.toUpperCase().startsWith('000201');
    if (ehPix && scr.scan?.pix) { setColar(t); decode(t, scr.scan.pix); return; }
    if (scr.scan?.barcodeField) { set(scr.scan.barcodeField, t); setAttMsg('Código de barras lido do boleto. Confira antes de enviar.'); return; }
    if (scr.scan?.pix) { setColar(t); decode(t, scr.scan.pix); }
  }

  // Anexo que PREENCHE o form (scr.attach) — ex.: anexar o PDF do boleto e o backend extrai a
  // linha digitável/valor (endpoint read-only, NÃO paga). fills = {campoForm: chaveResposta}.
  async function anexar(file?: File) {
    if (!file || !scr.attach) return;
    setAttMsg('Lendo o arquivo…');
    try {
      let tok = ''; try { tok = localStorage.getItem('access_token') || ''; } catch { /* */ }
      const fd = new FormData(); fd.append(scr.attach.field || 'arquivo', file);
      const res = await fetch(scr.attach.endpoint, { method: 'POST', headers: tok ? { Authorization: `Bearer ${tok}` } : {}, body: fd });
      const r = await res.json().catch(() => ({}));
      const okFlag = scr.attach.okFlag;
      if (!res.ok || (okFlag && !r[okFlag])) {
        setAttMsg(r?.motivo || (typeof r?.detail === 'string' ? r.detail : 'Não consegui ler o arquivo.'));
        return;
      }
      const upd: Record<string, string> = {};
      for (const [fk, rk] of Object.entries(scr.attach.fills || {})) {
        const v = (r as any)[rk as string];
        if (v != null && v !== '') upd[fk] = fk === 'valor' && !isNaN(Number(v)) ? Number(v).toFixed(2) : String(v);
      }
      setVals((s) => ({ ...s, ...upd }));
      setAttMsg(`Dados carregados do arquivo${r.valor ? ` — R$ ${Number(r.valor).toFixed(2)}` : ''}. Confira antes de enviar.`);
    } catch { setAttMsg('Falha ao ler o arquivo.'); }
  }

  async function fire(extra: Record<string, unknown>) {
    let tok: string | null = null;
    try { tok = localStorage.getItem('access_token'); } catch { /* */ }
    // Upload multipart (scr.submit.multipart): manda arquivo(s) + campos como FormData. Sem
    // Content-Type manual (o browser põe o boundary). scr.submit.fixed = campos constantes
    // (ex.: folder_id/category); titleFromFile = usa o nome do arquivo como title se faltar.
    if (scr.submit.multipart) {
      const fd = new FormData();
      for (const [k, v] of Object.entries(scr.submit.fixed || {})) fd.append(k, String(v));
      for (const [k, v] of Object.entries({ ...vals, ...extra })) { if (v != null && v !== '') fd.append(k, String(v)); }
      let firstName = '';
      for (const [k, f] of Object.entries(files)) { if (f) { fd.append(k, f); if (!firstName) firstName = f.name; } }
      if (scr.submit.titleFromFile && firstName && !fd.has('title')) fd.append('title', firstName);
      const resm = await fetch(scr.submit.endpoint, {
        method: scr.submit.method || 'POST',
        headers: { ...(tok ? { Authorization: `Bearer ${tok}` } : {}) },
        body: fd,
      });
      const dm = await resm.json().catch(() => ({}));
      return { res: resm, d: dm };
    }
    const res = await fetch(scr.submit.endpoint, {
      method: scr.submit.method || 'POST',
      headers: { 'Content-Type': 'application/json', ...(tok ? { Authorization: `Bearer ${tok}` } : {}) },
      body: JSON.stringify({ ...vals, ...extra }),
    });
    const d = await res.json().catch(() => ({}));
    return { res, d };
  }

  async function submit(withOtp = false) {
    if (!scr.submit) return;
    setBusy(true); setMsg(null);
    try {
      const extra = withOtp && otp ? { otp_code: otp.code, _gate_ref: otp.ref } : {};
      const { res, d } = await fire(extra);
      if (d && d.otp_required) { // gate exige OTP humano → entra no modo OTP, mantém os campos
        setOtp({ ref: d.ref || '', code: '' }); setConfirming(false);
        setMsg({ ok: true, text: d.message || 'Confirme com o código OTP enviado ao e-mail do Jordan.' });
        return;
      }
      if (!res.ok) throw new Error(d.detail || 'Não foi possível concluir.');
      // honesto: mostra a mensagem REAL do backend (não inventa sucesso)
      setMsg({ ok: d.ok !== false, text: d.message || scr.submit.okMsg || 'Concluído.' });
      // Gancho de documento: ações que GERAM um doc (aviso de férias, recibos, exports) devolvem
      // d.doc {url, fmt} → abre direto (aditivo; formas sem d.doc não mudam).
      if (d && d.doc && d.doc.url) { try { await abrirDoc(d.doc as DocRef); } catch { /* abre manual depois */ } }
      setVals({}); setFiles({}); setOtp(null); setConfirming(false);
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : 'Erro.' });
    } finally { setBusy(false); }
  }

  function onPrimary() {
    if (scr.submit && scr.submit.confirm && !confirming) { setConfirming(true); return; }
    setConfirming(false); submit(false);
  }

  return (
    <div className="rd-form-card">
      {msg && (
        <div className={`rd-badge ${msg.ok ? 'rd-b-success' : 'rd-b-error'}`} style={{ height: 'auto', padding: '8px 12px', fontSize: 12.5, alignSelf: 'flex-start' }}>
          {msg.text}
        </div>
      )}
      {scr.attach && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <label className="rd-btn rd-btn-outline" style={{ cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12.5, padding: '7px 12px' }}>
            📎 {scr.attach.label || 'Anexar arquivo'}
            <input type="file" accept={scr.attach.accept || 'application/pdf'} style={{ display: 'none' }}
              onChange={(e) => { anexar(e.target.files?.[0]); e.currentTarget.value = ''; }} />
          </label>
          {attMsg && <span className="rd-scr-sub" style={{ margin: 0 }}>{attMsg}</span>}
        </div>
      )}
      {(scr.scan || scr.decode) && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          {scr.scan && (
            <button type="button" className="rd-btn rd-btn-outline" style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12.5, padding: '7px 12px' }}
              onClick={() => setScanOpen(true)}>
              📷 {scr.scan.label || 'Escanear (câmera)'}
            </button>
          )}
          {scr.decode && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, flex: '1 1 260px', minWidth: 220 }}>
              <input className="rd-input" style={{ flex: 1, fontSize: 12.5 }} placeholder={scr.decode.ph || 'Cole o PIX copia-e-cola / código'}
                value={colar} onChange={(e) => setColar(e.target.value)} />
              <button type="button" className="rd-btn rd-btn-outline" style={{ fontSize: 12.5, padding: '7px 12px', whiteSpace: 'nowrap' }}
                disabled={!colar.trim()} onClick={() => decode(colar, scr.decode)}>
                {scr.decode.cta || 'Ler'}
              </button>
            </div>
          )}
          {!scr.attach && attMsg && <span className="rd-scr-sub" style={{ margin: 0, flexBasis: '100%' }}>{attMsg}</span>}
        </div>
      )}
      {scanOpen && <ScannerPagamento onClose={() => setScanOpen(false)} onDetect={onScan} />}
      {scr.originField && (
        <div className="rd-field" style={{ gridColumn: 'span 2' }}>
          <label className="rd-label" style={{ textTransform: 'none', letterSpacing: 0, fontSize: 11 }}>
            Conta de origem — de qual empresa o dinheiro sai
          </label>
          <select className="rd-input" value={vals.origem || 'inter'} onChange={(e) => set('origem', e.target.value)}>
            <option value="inter">Inter — Conecta Mais Eletrônica (paga direto, sem app)</option>
            <option value="cora">Cora — Conecta Mais Patrimonial (aprovar no app Cora)</option>
          </select>
          {(vals.origem || 'inter') === 'cora' && (
            <span className="rd-scr-sub" style={{ margin: '4px 0 0', color: '#B45309' }}>
              Pela Cora, o valor sai da Patrimonial e você precisa APROVAR no app Cora para concluir (regra do banco).
            </span>
          )}
        </div>
      )}
      <div className="rd-form-grid">
        {(scr.fields || []).map((f: any, i: number) => (
          <div className="rd-field" key={i} style={{ gridColumn: f.span || 'span 1' }}>
            <label className="rd-label" style={{ textTransform: 'none', letterSpacing: 0, fontSize: 11 }}>{f.label}</label>
            {f.type === 'file' ? (
              <input className="rd-input" type="file" accept={f.accept}
                onChange={(e) => setFiles((s) => ({ ...s, [f.key]: (e.target.files && e.target.files[0]) || null }))} />
            ) : f.type === 'select' ? (
              <select className="rd-input" value={vals[f.key] || ''} onChange={(e) => set(f.key, e.target.value)}>
                <option value="">{f.ph || 'Selecione…'}</option>
                {(f.options || []).map((o: any) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            ) : f.type === 'textarea' ? (
              <textarea className="rd-input" style={{ height: 92, paddingTop: 10, resize: 'vertical' }}
                placeholder={f.ph} value={vals[f.key] || ''} onChange={(e) => set(f.key, e.target.value)} />
            ) : (
              <input className="rd-input" type={f.type === 'date' ? 'date' : 'text'} placeholder={f.ph}
                value={vals[f.key] || ''} onChange={(e) => set(f.key, e.target.value)} />
            )}
          </div>
        ))}
      </div>

      {confirming && !otp && (
        <div className="rd-scr-sub" style={{ color: '#B45309', fontWeight: 600 }}>
          {scr.submit.confirm} — confirme para prosseguir.
        </div>
      )}

      <div className="rd-form-actions">
        {otp ? (
          <>
            <input className="rd-input" style={{ maxWidth: 190 }} inputMode="numeric" placeholder="Código OTP (6 dígitos)"
              value={otp.code} onChange={(e) => setOtp({ ...otp, code: e.target.value })} />
            <button className="rd-btn rd-btn-primary" disabled={busy || !otp.code} onClick={() => submit(true)}>
              {busy ? 'Confirmando…' : 'Confirmar com OTP'}
            </button>
            <button className="rd-btn rd-btn-outline" onClick={() => { setOtp(null); setMsg(null); }}>Cancelar</button>
          </>
        ) : (
          <>
            <button className="rd-btn rd-btn-primary" disabled={busy || !scr.submit} onClick={onPrimary}>
              {busy ? 'Enviando…' : confirming ? 'Confirmar' : (scr.cta || 'Salvar')}
            </button>
            <button className="rd-btn rd-btn-outline" onClick={() => { setVals({}); setMsg(null); setConfirming(false); }}>
              {confirming ? 'Cancelar' : 'Limpar'}
            </button>
          </>
        )}
      </div>

      {otp && <div className="rd-scr-sub" style={{ marginTop: 4, color: '#B45309' }}>Ação sensível (dinheiro/gov) — precisa do código OTP enviado ao e-mail do Jordan para liberar. Nada é disparado sem ele.</div>}
      {gated && !otp && <div className="rd-scr-sub" style={{ marginTop: 4 }}>Ação protegida por OTP humano — ao enviar, um código vai ao e-mail do Jordan.</div>}
      {!scr.submit && <div className="rd-scr-sub" style={{ marginTop: 4 }}>Formulário de exemplo do pacote — escrita ainda não ligada nesta tela.</div>}
    </div>
  );
}

// Estado vazio honesto: tela sem dado REAL não mostra exemplo — fica vazia ("aguardando dado").
function EmptyReal() {
  return (
    <div className="rd-card rd-card-pad" style={{ textAlign: 'center', padding: '56px 24px', color: 'var(--ink-weak)' }}>
      <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--ink)', marginBottom: 6 }}>Aguardando dado</div>
      <div style={{ fontSize: 13, maxWidth: 420, margin: '0 auto', lineHeight: 1.5 }}>
        Esta tela ainda não tem dados reais no sistema. Ela será preenchida automaticamente assim que houver registros — não exibimos exemplos.
      </div>
    </div>
  );
}

// TabsScreen (F0) — grupo com abas; cada aba renderiza uma tela normal pelos renderers existentes.
function TabsScreen({ scr, tab, onTab }: { scr: any; tab: string; onTab: (id: string) => void }) {
  const tabs = Array.isArray(scr.tabs) ? scr.tabs : [];
  const act = tabs.find((x: any) => x.id === tab) || tabs[0];
  return (
    <div className="rd-tabs-wrap">
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 14 }}>
        {tabs.map((x: any) => (
          <button key={x.id} type="button" onClick={() => onTab(x.id)}
            className={`rd-btn ${act && act.id === x.id ? 'rd-btn-primary' : 'rd-btn-outline'}`}
            style={{ fontSize: 12.5, padding: '6px 12px' }}>
            {x.label}
          </button>
        ))}
      </div>
      {act ? <Screen scr={act.screen} /> : <EmptyReal />}
    </div>
  );
}

function Screen({ scr, onNav }: { scr: any; onNav?: (id: string) => void }) {
  if (!scr) return <div className="rd-card rd-card-pad" style={{ color: 'var(--ink-weak)' }}>Tela em preparação.</div>;
  switch (scr.type) {
    case 'dash': return <DashScreen scr={scr} onNav={onNav} />;
    case 'table': return <TableScreen scr={scr} />;
    case 'cards': return <CardsScreen scr={scr} />;
    case 'list': return <ListScreen scr={scr} />;
    case 'form': return <FormScreen key={scr.submit?.endpoint || scr.title} scr={scr} />;
    case 'chat': return <ChatScreen scr={scr} />;
    default: return <div className="rd-card rd-card-pad">Tipo não suportado: {scr.type}</div>;
  }
}

// ── ModuleView: shell do módulo + tela ativa ────────────────────────────────
export default function ModuleView({ slug }: { slug: string }) {
  const data = MODULES[slug];
  const menu = useMemo(() => normMenu(data?.menu || []), [data]);
  const screens = data?.screens || {};
  const mod = data?.mod || { name: slug, desc: '', icon: '' };

  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [active, setActive] = useState<string>(menu[0]?.id || '');
  const [activeTab, setActiveTab] = useState<string>('');
  const [patches, setPatches] = useState<Record<string, any>>({});
  const [extraMenu, setExtraMenu] = useState<any[]>([]);
  // 'idle' sem token (exemplo direto) · 'loading' buscando · 'done' resolvido
  const [dataState, setDataState] = useState<'idle' | 'loading' | 'done'>('idle');

  useEffect(() => {
    try { if (localStorage.getItem('rd-sidebar-collapsed') === '1') setCollapsed(true); } catch { /* */ }
    const sp = new URLSearchParams(window.location.search);
    const t = sp.get('t');
    // confia no ?t da URL (telas de ação/extraMenu chegam via patch, depois)
    if (t) setActive(t);
    const tb = sp.get('tab');
    if (tb) setActiveTab(tb); // aba do grupo (fundação tabs F0)
  }, [screens]);

  // Dados reais da API (READ-ONLY). Sem token → mantém exemplos do pacote.
  useEffect(() => {
    let cancel = false;
    let tok: string | null = null;
    try { tok = localStorage.getItem('access_token'); } catch { /* */ }
    if (!tok) { setDataState('idle'); return; }
    setDataState('loading');
    fetch(`/api/v1/redesign/data/${slug}`, { headers: { Authorization: `Bearer ${tok}` } })
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((j) => { if (!cancel) { setPatches(j.screens || {}); setExtraMenu(j.extraMenu || []); setDataState('done'); } })
      .catch(() => { if (!cancel) setDataState('done'); });
    return () => { cancel = true; };
  }, [slug]);

  const toggle = () => setCollapsed((c) => { const n = !c; try { localStorage.setItem('rd-sidebar-collapsed', n ? '1' : '0'); } catch { /* */ } return n; });
  const go = (id: string, tabId?: string) => {
    setActive(id); setActiveTab(tabId || ''); setMobileOpen(false);
    try {
      const u = new URL(window.location.href);
      u.searchParams.set('t', id);
      if (tabId) u.searchParams.set('tab', tabId); else u.searchParams.delete('tab');
      window.history.replaceState(null, '', u);
    } catch { /* */ }
  };

  const isReal = !!patches[active];
  const scr = patches[active] || screens[active] || screens[menu[0]?.id ?? ''];

  // Deep-link antigo (?t=<id-antigo>): tela virou stub redirect (F0) → resolve p/ grupo+aba.
  useEffect(() => {
    const s: any = patches[active];
    if (s && s.type === 'redirect' && s.groupRef) go(s.groupRef.t, s.groupRef.tab);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [patches, active]);

  // Tela EFETIVA (aba ativa quando o grupo é type=tabs) — header (sub/docs/export) segue a aba.
  const effScr = scr?.type === 'tabs'
    ? (((scr.tabs || []).find((x: any) => x.id === activeTab) || (scr.tabs || [])[0]) as any)?.screen
    : scr;
  const initials = 'JJ';

  if (!data) return <div className="rd-content"><div className="rd-card rd-card-pad">Módulo não encontrado: {slug}</div></div>;

  return (
    <div className="rd-shell">
      {mobileOpen && <div className="rd-scrim" onClick={() => setMobileOpen(false)} />}
      <aside className={`rd-sidebar${collapsed ? ' collapsed' : ''}${mobileOpen ? ' open' : ''}`}>
        <div className="rd-brand">
          <a href="/redesign" title="Início" aria-label="Voltar para a página inicial" className="rd-brand-home">
            <img src="/images/quadrante.png" alt="Início — Conecta PRO" className="rd-brand-logo" />
          </a>
          <div className="rd-brand-name"><span className="rd-brand-word">CONECTA</span><span className="rd-brand-badge">PRO</span></div>
        </div>
        <div className="rd-mod-ctx">
          <div className="ico">{mod.icon && <Ico d={mod.icon} size={16} stroke="#fff" />}</div>
          <div><div className="nm">{mod.name}</div><div className="ds">{mod.desc}</div></div>
        </div>
        <nav className="rd-nav">
          {[...menu, ...normMenu(extraMenu)].map((m) => (
            <button key={m.id} type="button" title={m.label}
              className={`rd-nav-item${m.id === active ? ' active' : ''}`} onClick={() => go(m.id)}>
              <Ico d={m.icon} size={17} stroke={m.id === active ? '#fff' : '#9DB0D9'} />
              <span>{m.label}</span>
            </button>
          ))}
        </nav>
        <div className="rd-side-foot">
          <div className="rd-avatar">{initials}</div>
          {!collapsed && (
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="n">Jordan Jesus</div>
              <div className="r">admin</div>
            </div>
          )}
          {!collapsed && (
            <div style={{ display: 'flex', gap: 4 }}>
              <a href="/modulos" title="Sistema clássico" className="rd-foot-ico"><LayoutGrid size={15} /></a>
              <button type="button" title="Sair" onClick={rdLogout} className="rd-foot-ico"><LogOut size={15} /></button>
            </div>
          )}
        </div>
      </aside>

      <div className="rd-main">
        <header className="rd-topbar">
          <button type="button" className="rd-icon-btn rd-collapse-btn" onClick={toggle} aria-label="Recolher menu"
            style={{ border: 'none', background: 'transparent' }}>
            {collapsed ? <PanelLeft size={18} /> : <PanelLeftClose size={18} />}
          </button>
          <button type="button" className="rd-icon-btn rd-menu-btn" onClick={() => setMobileOpen((o) => !o)} aria-label="Abrir menu"
            style={{ border: 'none', background: 'transparent' }}>
            <Menu size={20} />
          </button>
          <div className="rd-crumb">{mod.name} › <b>{scr?.title}</b></div>
          <span className={`rd-badge ${dataState === 'loading' ? 'rd-b-neutral' : isReal ? 'rd-b-success' : 'rd-b-neutral'}`} style={{ height: 20 }}>
            {dataState === 'loading' ? 'carregando…' : isReal ? 'dados reais' : 'aguardando dado'}
          </span>
          <div className="rd-search">
            <Search size={16} color="var(--placeholder)" />
            <input placeholder={scr?.searchHint || 'Buscar…'} />
          </div>
          <RdBell />
          {scr?.cta && isReal && (scr.type === 'form' || (scr.ctaTo && (patches[scr.ctaTo] || screens[scr.ctaTo]))) && (
            <button
              type="button"
              className="rd-btn rd-btn-primary"
              onClick={() => {
                if (scr.type === 'form') {
                  // Tela de formulário: o cta do topo rola/foca o form (não é mais gêmeo morto do submit).
                  const el = document.querySelector('.rd-content input, .rd-content textarea, .rd-content select') as HTMLElement | null;
                  if (el) { el.scrollIntoView({ behavior: 'smooth', block: 'center' }); el.focus(); }
                } else if (scr.ctaTo) {
                  // Tela com ação: navega para o formulário-alvo declarado pelo builder.
                  go(scr.ctaTo);
                }
              }}
            >
              <Plus size={16} /> {scr.cta}
            </button>
          )}
        </header>
        <main className="rd-content">
          <div>
            <div className="rd-scr-title">{scr?.title}</div>
            {(effScr?.sub || scr?.sub) && isReal && <div className="rd-scr-sub">{effScr?.sub || scr?.sub}</div>}
          </div>
          {isReal && (
            (Array.isArray(effScr?.docs) && effScr.docs.length > 0) ||
            (effScr?.type === 'table' && Array.isArray(effScr?.rows) && effScr.rows.length > 0 && !effScr?.noExport)
          ) && (
            <div style={{ marginTop: 12, marginBottom: 2, display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', justifyContent: 'space-between' }}>
              <div>{Array.isArray(effScr?.docs) && effScr.docs.length > 0 && <DocButtons docs={effScr.docs} />}</div>
              {effScr?.type === 'table' && Array.isArray(effScr?.rows) && effScr.rows.length > 0 && !effScr?.noExport && (
                <ExportMenu
                  cols={(effScr.cols || []).map((c: string) => String(c))}
                  rows={(effScr.rows || []).map((r: any) => (r.cells || []).map((c: any) => String(c?.v ?? '')))}
                  nome={effScr.title || scr?.title || 'lista'} titulo={effScr.title || scr?.title} />
              )}
            </div>
          )}
          {dataState === 'loading'
            ? <div className="rd-dash" aria-busy="true">
                <div className="rd-dash-kpis">
                  {[0, 1, 2, 3].map((i) => <div className="rd-skel" key={i} style={{ height: 92 }} />)}
                </div>
                <div className="rd-skel" style={{ height: 220 }} />
              </div>
            : (isReal || scr?.type === 'chat')
              ? (scr?.type === 'tabs'
                  ? <TabsScreen scr={scr} tab={activeTab} onTab={(id) => go(active, id)} />
                  : <Screen scr={scr} onNav={go} />)
              : <EmptyReal />}
        </main>
      </div>
    </div>
  );
}
