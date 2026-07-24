'use client';

import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { PanelLeftClose, PanelLeft, Menu, Search, Bell, Plus, LogOut, LayoutGrid } from 'lucide-react';
import { MODULES } from './modules';
import { rdLogout } from './session';
import { DocButtons } from './DocButtons';
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
function DashScreen({ scr }: { scr: any }) {
  return (
    <div className="rd-dash">
      <div className="rd-dash-kpis">
        {(scr.kpis || []).map((k: any, i: number) => (
          <div className="rd-kpi" key={i}>
            <div className="rd-kpi-ico"><Ico d={k.icon} size={20} stroke="var(--navy)" /></div>
            <div className="rd-kpi-v" style={{ color: k.color || 'var(--ink)' }}>{k.v}</div>
            <div className="rd-kpi-l">{k.l}</div>
          </div>
        ))}
      </div>
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
  const rows = scr.rows || [];
  // Documentos por-LINHA (holerite por colaborador, DANFSe por nota…): se alguma linha declara
  // docs, anexa uma coluna "Documento" ao grid — retrocompatível (telas sem row.docs não mudam).
  const hasRowDocs = rows.some((r: any) => Array.isArray(r.docs) && r.docs.length > 0);
  const grid = hasRowDocs ? `${scr.grid} minmax(150px, auto)` : scr.grid;
  const cols = hasRowDocs ? [...(scr.cols || []), 'Documento'] : (scr.cols || []);
  return (
    <div className="rd-tbl-wrap">
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
              {hasRowDocs && (
                <span className="rd-tbl-cell" style={{ justifyContent: 'flex-end' }}>
                  {Array.isArray(row.docs) && row.docs.length > 0 && <DocButtons docs={row.docs} compact />}
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
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [otp, setOtp] = useState<{ ref: string; code: string } | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [attMsg, setAttMsg] = useState<string | null>(null);
  const set = (k: string, v: string) => setVals((s) => ({ ...s, [k]: v }));
  const gated = !!(scr.submit && scr.submit.gated); // ação money/gov (visual de aviso)

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
      setVals({}); setOtp(null); setConfirming(false);
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
      <div className="rd-form-grid">
        {(scr.fields || []).map((f: any, i: number) => (
          <div className="rd-field" key={i} style={{ gridColumn: f.span || 'span 1' }}>
            <label className="rd-label" style={{ textTransform: 'none', letterSpacing: 0, fontSize: 11 }}>{f.label}</label>
            {f.type === 'select' ? (
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

function Screen({ scr }: { scr: any }) {
  if (!scr) return <div className="rd-card rd-card-pad" style={{ color: 'var(--ink-weak)' }}>Tela em preparação.</div>;
  switch (scr.type) {
    case 'dash': return <DashScreen scr={scr} />;
    case 'table': return <TableScreen scr={scr} />;
    case 'cards': return <CardsScreen scr={scr} />;
    case 'list': return <ListScreen scr={scr} />;
    case 'form': return <FormScreen scr={scr} />;
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
          <button type="button" className="rd-icon-btn" aria-label="Notificações"><Bell size={18} /><span className="rd-dot-badge">3</span></button>
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
                  : <Screen scr={scr} />)
              : <EmptyReal />}
        </main>
      </div>
    </div>
  );
}
