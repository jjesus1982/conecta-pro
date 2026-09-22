'use client';

import { Component, createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useSearchParams } from 'next/navigation';
import dynamic from 'next/dynamic';
import { PanelLeftClose, PanelLeft, Menu, Search, Plus, LogOut, LayoutGrid } from 'lucide-react';
import RdBell from './RdBell';
import { MODULES } from './modules';

// Scanner de câmera (QR PIX + código de barras de boleto) — reusa o componente do clássico.
// client-only (usa a câmera); só carrega quando o usuário abre o scanner.
const ScannerPagamento = dynamic(() => import('@/components/financeiro/ScannerPagamento'), { ssr: false });
// Assinatura de medida disciplinar: reusa o modal JÁ PROVADO do clássico (pad de traço +
// geolocalização + recusa com 2 testemunhas/Art. 477). O backend exige signature_data em
// base64, que um form declarativo não produz — por isso o componente entra inteiro aqui.
const DisciplinarySignatureModal = dynamic(
  () => import('@/components/operacional/disciplinary-signature-modal').then((m) => m.DisciplinarySignatureModal),
  { ssr: false });
const RdChart = dynamic(() => import('./RdChart'), { ssr: false });
import { rdLogout } from './session';
import { DocButtons } from './DocButtons';
import { FotoBatida } from './FotoBatida';
import { abrirDoc, type DocRef } from '@/lib/docsource';
import { ExportMenu } from './ExportMenu';

// multiselect guarda a seleção como JSON no estado de texto do form; aqui volta a lista para o <select multiple>.
function lerLista(v: string | undefined): string[] {
  if (!v) return [];
  try { const a = JSON.parse(v); return Array.isArray(a) ? a.map(String) : []; } catch { return []; }
}
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

type MenuItem = { id: string; label: string; icon: string; grupo?: string };
function normMenu(menu: unknown[]): MenuItem[] {
  return (menu || []).map((it: unknown) => {
    if (Array.isArray(it)) return { id: it[0], label: it[1], icon: it[2] };
    const o = it as MenuItem;
    return { id: o.id, label: o.label, icon: o.icon, grupo: o.grupo };
  }).filter((m) => m.id);
}

/**
 * Agrupa o menu por assunto, preservando a ordem de chegada.
 *
 * Origem: 17/09/2026. O Jordan: «a side bar tá gigante, me perco diante de tanta coisa» e
 * «parece que tudo faz a mesma coisa». Medido: 289 itens, e o RH sozinho tinha 44 — dos quais
 * 18 eram «CCT — alguma coisa», incluindo três entradas diferentes só para feriados.
 *
 * Item SEM `grupo` continua solto exatamente como antes: a mudança é aditiva, nenhum módulo
 * que não declarar grupo muda de aparência.
 */
type Bloco = { grupo: string | null; itens: MenuItem[] };
function agrupar(itens: MenuItem[]): Bloco[] {
  const blocos: Bloco[] = [];
  for (const it of itens) {
    const g = it.grupo || null;
    const ultimo = blocos[blocos.length - 1];
    // Solto e solto se juntam; grupo só continua se for o MESMO grupo em sequência.
    if (ultimo && ultimo.grupo === g) ultimo.itens.push(it);
    else blocos.push({ grupo: g, itens: [it] });
  }
  return blocos;
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
// Termo do campo "Buscar…" do cabeçalho. Context (e não prop) porque a tabela pode estar
// aninhada dentro de uma tela-grupo (tabs) — passar prop exigiria fiar por toda a árvore.
const SearchCtx = createContext('');
// Recarrega os dados da tela após uma ação de escrita. O fetch vive no componente
// externo; sem isto a linha alterada só sai da tabela depois de F5 — foi a sensação
// de "travado" reportada (a acao gravava, mas a tela nao dava sinal).
const ReloadCtx = createContext<() => void>(() => {});

/** Mensagem de erro legível do backend. FastAPI 422 devolve `detail` como LISTA de
 *  objetos — jogar isso num template vira "[object Object]" (bug real em produção). */
function msgErro(d: any): string {
  const det = d?.detail;
  if (typeof det === 'string') return det;
  if (Array.isArray(det)) {
    const partes = det
      .map((e: any) => (typeof e === 'string' ? e : e?.msg))
      .filter(Boolean);
    if (partes.length) return partes.join(' · ');
  }
  if (typeof d?.message === 'string') return d.message;
  return '';
}

function TableScreen({ scr }: { scr: any }) {
  const q = useContext(SearchCtx).trim().toLowerCase();
  const recarregar = useContext(ReloadCtx);
  const allRows = scr.rows || [];
  // Seletor opcional por coluna (ex.: Competência na Folha): scr.filterCol = índice da coluna.
  // Dropdown filtra as linhas client-side; default = 1º valor (as linhas já vêm ordenadas desc).
  // Retrocompatível: telas sem filterCol não mudam.
  const filterCol: number | null = typeof scr.filterCol === 'number' ? scr.filterCol : null;
  // valor do seletor: `row.filtro` quando existe (coluna invisível), senão a célula filterCol.
  // Sem isto, filtrar por Competência exigia mostrá-la em toda linha — coluna com um único
  // valor, que só roubava largura de Colaborador e dos valores em R$.
  const valFiltro = (r: any) => (r?.filtro != null ? r.filtro : (filterCol != null ? r?.cells?.[filterCol]?.v : null));
  const temFiltro = filterCol != null || allRows.some((r: any) => r?.filtro != null);
  // filterVals sai de allRows (não do resultado da busca) p/ a lista de meses não encolher
  // enquanto se digita.
  const filterVals: string[] = temFiltro
    ? Array.from(new Set(allRows.map(valFiltro).filter((v: any) => v != null && v !== '')).values()).map(String)
    : [];
  const [sel, setSel] = useState<string>('');
  const active = temFiltro ? (sel || filterVals[0] || '') : '';

  // ── VÁRIOS filtros na mesma tela (14/09/2026) ────────────────────────────────────────
  // O seletor acima é UM só, e nasceu para a Competência da Folha. O Jordan pediu o filtro
  // por CONDOMÍNIO no ponto — e quem trabalha ponto precisa dos dois ao mesmo tempo
  // ("setembro, Ideal Flores"), como a Pyetra já fazia no Sólides.
  //
  // Contrato: scr.filtros = [{key, label, todos?}] e row.filtros = {key: valor}.
  // Cada um vira um dropdown; combinam com E. "Todos" (default) não filtra nada — ao
  // contrário do seletor antigo, que abre no 1º valor porque lá o padrão é a competência
  // mais recente. Telas sem `filtros` não mudam em nada.
  const filtrosDecl: Array<{ key: string; label?: string; todos?: string; padrao?: string }> =
    Array.isArray(scr.filtros) ? scr.filtros : [];
  const TODOS = '__todos__';
  // `padrao` existe para NÃO piorar telas que já abriam filtradas: o Ponto abria no mês
  // corrente (o seletor antigo escolhia o 1º valor). Sem isto, trocar para multi-filtro
  // faria a tela abrir com três competências misturadas — pior do que antes da mudança.
  const [selMulti, setSelMulti] = useState<Record<string, string>>(
    () => Object.fromEntries(filtrosDecl.filter((f) => f.padrao).map((f) => [f.key, f.padrao as string])),
  );
  const opcoesDe = (key: string): string[] =>
    Array.from(new Set<string>(allRows
      .map((r: any) => r?.filtros?.[key])
      .filter((v: any) => v != null && v !== '')
      .map((v: any) => String(v))))
      .sort((a: string, b: string) => a.localeCompare(b, 'pt-BR'));

  const byCol0 = (temFiltro && active)
    ? allRows.filter((r: any) => String(valFiltro(r)) === active)
    : allRows;
  const byCol = filtrosDecl.length
    ? byCol0.filter((r: any) => filtrosDecl.every((f) => {
        const escolhido = selMulti[f.key] ?? TODOS;
        return escolhido === TODOS || String(r?.filtros?.[f.key] ?? '') === escolhido;
      }))
    : byCol0;
  // Busca do cabeçalho: substring sobre o texto das células (ex.: favorecido no extrato).
  // q vazio = comportamento anterior, intacto.
  const rows = q
    ? byCol.filter((r: any) => (r.cells || []).some((c: any) => String(c?.v ?? '').toLowerCase().includes(q)))
    : byCol;
  // Documentos por-LINHA + Editar por-LINHA (edit={endpoint,method,fields}) → coluna de ações.
  // Retrocompatível: telas sem docs/edit não mudam.
  const hasRowDocs = allRows.some((r: any) => Array.isArray(r.docs) && r.docs.length > 0);
  const hasRowEdit = allRows.some((r: any) => r.edit && Array.isArray(r.edit.fields));
  const hasRowActions = allRows.some((r: any) => Array.isArray(r.actions) && r.actions.length);
  // row.sign = payload de medida disciplinar → abre o pad de assinatura do clássico.
  const hasRowSign = allRows.some((r: any) => r.sign && r.sign.id);
  const [signRow, setSignRow] = useState<any>(null);
  const [signerType, setSignerType] = useState<string>('employee');
  const hasActions = hasRowDocs || hasRowEdit || hasRowActions || hasRowSign;
  const grid = hasActions ? `${scr.grid} minmax(200px, auto)` : scr.grid;
  const cols = hasActions ? [...(scr.cols || []), hasRowDocs ? 'Documento' : 'Ações'] : (scr.cols || []);
  // `fieldsRef` aponta para `scr.campos[ref]`: o formulário vem UMA vez por tela em vez de
  // uma vez por linha. Sem isto, o DP mandava 2,6 MB só de `fields` repetidos — a mesma
  // lista de opções 2.000 vezes na mesma resposta (medido em 15/09/2026, quando o Jordan
  // disse que o sistema estava pesado). Bloco sem `fieldsRef` segue como sempre.
  const comCampos = (bloco: any, linha?: any) => {
    if (!bloco) return bloco;
    // `verDaLinha` = o detalhe É a própria linha. Antes o servidor mandava os valores
    // duplicados dentro do botão "Ver" — a linha inteira repetida dentro dela mesma, em
    // TODA tabela do sistema. O rótulo é o cabeçalho da coluna e o valor é a célula: os
    // dois já chegaram. Montar aqui não custa nada e economiza megabytes na resposta.
    if (bloco.verDaLinha && linha) {
      return {
        ...bloco,
        fields: (scr.cols || []).map((c: string, i: number) => {
          const cel = (linha.cells || [])[i];
          const v = cel && typeof cel === 'object' ? cel.v : cel;
          return { label: c, value: (v ?? '') === '' ? '—' : v };
        }),
      };
    }
    if (Array.isArray(bloco.fields)) return bloco;
    const ref = bloco.fieldsRef;
    const achado = ref && scr.campos ? scr.campos[ref] : null;
    return achado ? { ...bloco, fields: achado } : bloco;
  };

  const [editRow, setEditRow] = useState<any>(null);
  const [editVals, setEditVals] = useState<Record<string, any>>({});
  const [editMsg, setEditMsg] = useState<{ ok: boolean; text: string } | null>(null);
  // Gate de OTP no modal da LINHA. O FormScreen já tratava `otp_required`; o botão de
  // linha não — a resposta caía no caminho de sucesso, o modal fechava em 1,1s e o
  // campo do código nunca chegava a existir. O Jordan recebia o OTP no e-mail e não
  // tinha onde digitar. Mesmo contrato do form: { otp_required, ref } -> reenvia com
  // otp_code + _gate_ref.
  const [editOtp, setEditOtp] = useState<{ ref: string; code: string } | null>(null);
  const [editBusy, setEditBusy] = useState(false);
  return (
    <div className="rd-tbl-wrap">
      {temFiltro && filterVals.length > 0 && (
        <div style={{ marginBottom: 10, display: 'flex', alignItems: 'center', gap: 8 }}>
          <label style={{ fontSize: 12.5, color: 'var(--placeholder)', fontWeight: 600 }}>{scr.filterLabel || 'Filtrar'}:</label>
          <select value={active} onChange={(e) => setSel(e.target.value)}
            style={{ padding: '6px 12px', borderRadius: 8, fontSize: 13, border: '1px solid var(--border, #d8dee9)', background: 'var(--surface, #fff)', color: 'var(--ink, #16277D)', fontWeight: 600, cursor: 'pointer' }}>
            {filterVals.map((v: string, i: number) => <option key={i} value={v}>{v}</option>)}
          </select>
          {/* "folha(s)" estava chumbado: o filtro nasceu na tela de FOLHA e o texto foi junto
                  para toda tabela filtrável. Na de diaristas dizia "16 folha(s)" para 16 diárias.
                  `filterUnit` deixa a tela dizer o que ela conta; "linha(s)" é o padrão honesto. */}
              <span style={{ fontSize: 12, color: 'var(--placeholder)' }}>{rows.length} {scr.filterUnit || 'linha(s)'}</span>
        </div>
      )}
      {filtrosDecl.length > 0 && (
        <div style={{ marginBottom: 10, display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          {filtrosDecl.map((f) => {
            const ops = opcoesDe(f.key);
            if (!ops.length) return null;
            return (
              <span key={f.key} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <label style={{ fontSize: 12.5, color: 'var(--placeholder)', fontWeight: 600 }}>{f.label || f.key}:</label>
                <select value={selMulti[f.key] ?? TODOS}
                  onChange={(e) => setSelMulti((m) => ({ ...m, [f.key]: e.target.value }))}
                  style={{ padding: '6px 12px', borderRadius: 8, fontSize: 13, border: '1px solid var(--border, #d8dee9)', background: 'var(--surface, #fff)', color: 'var(--ink, #16277D)', fontWeight: 600, cursor: 'pointer' }}>
                  <option value={TODOS}>{f.todos || 'Todos'}</option>
                  {ops.map((v, i) => <option key={i} value={v}>{v}</option>)}
                </select>
              </span>
            );
          })}
          <span style={{ fontSize: 12, color: 'var(--placeholder)' }}>{rows.length} {scr.filterUnit || 'linha(s)'}</span>
          {Object.values(selMulti).some((v) => v && v !== TODOS) && (
            <button type="button" onClick={() => setSelMulti(
              Object.fromEntries(filtrosDecl.filter((f) => f.padrao).map((f) => [f.key, f.padrao as string])))}
              style={{ fontSize: 12, padding: '5px 10px', borderRadius: 8, border: '1px solid var(--border, #d8dee9)', background: 'transparent', color: 'var(--placeholder)', cursor: 'pointer' }}>
              Limpar filtros
            </button>
          )}
        </div>
      )}
      <div className="rd-tbl-scroll">
        {/* min-width cresce com o nº de colunas. Era 680px fixo, então a Folha (12 colunas)
            espremia tudo para caber e o ellipsis comia justamente o VALOR: "R$ 1.67…",
            "R$ 797,…". Numa tela de folha, número cortado é pior que rolagem lateral —
            ninguém confere salário por reticências. ~112px por coluna é o que faz
            "R$ 1.670,00" caber inteiro na fonte 13px. */}
        <div className="rd-tbl-inner" style={{ minWidth: `max(680px, ${cols.length * 152}px)` }}>
          <div className="rd-tbl-head" style={{ gridTemplateColumns: grid }}>
            {cols.map((c: string, i: number) => <span className="rd-tbl-th" key={i}>{c}</span>)}
          </div>
          {rows.map((row: any, i: number) => (
            <div className="rd-tbl-row" style={{ gridTemplateColumns: grid }} key={i}>
              {(row.cells || []).map((cell: any, j: number) => (
                <span className={`rd-tbl-cell${cell.al === 'r' ? ' al-r' : ''}`} key={j}>
                  {cell.isFoto
                    ? <FotoBatida url={cell.v} alt={cell.alt} />
                    : cell.isBadge
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
                  {row.edit && (Array.isArray(row.edit.fields) || row.edit.fieldsRef) && (
                    <button type="button" className={`rd-btn ${row.edit.btnStyle === 'primary' ? 'rd-btn-primary' : 'rd-btn-outline'}`} style={{ padding: '5px 10px', fontSize: 12 }}
                      onClick={() => { const b = comCampos(row.edit, row); setEditRow(b); const v: Record<string, any> = {}; (b.fields || []).forEach((f: any) => { v[f.key] = f.value ?? ''; }); setEditVals(v); setEditMsg(null); setEditOtp(null); }}>
                      {row.edit.btnLabel || 'Editar'}
                    </button>
                  )}
                  {Array.isArray(row.actions) && row.actions.map((a:any, k:number) => (
                    <button key={k} type="button" className={`rd-btn ${a.btnStyle==='primary'?'rd-btn-primary':'rd-btn-outline'}`} style={{ padding:'5px 10px', fontSize:12 }}
                      onClick={() => { const b = comCampos(a, row); setEditRow(b); const v:Record<string,any>={}; (b.fields||[]).forEach((f:any)=>{v[f.key]=f.value??'';}); setEditVals(v); setEditMsg(null); setEditOtp(null); }}>
                      {a.btnLabel || 'Ação'}
                    </button>
                  ))}
                  {row.sign && row.sign.id && (
                    <>
                      <button type="button" className="rd-btn rd-btn-primary" style={{ padding: '5px 10px', fontSize: 12 }}
                        onClick={() => { setSignerType('employee'); setSignRow(row.sign); }}>
                        Assinar (funcionário)
                      </button>
                      <button type="button" className="rd-btn rd-btn-outline" style={{ padding: '5px 10px', fontSize: 12 }}
                        onClick={() => { setSignerType('manager'); setSignRow(row.sign); }}>
                        Assinar (empresa)
                      </button>
                    </>
                  )}
                </span>
              )}
            </div>
          ))}
          {rows.length === 0 && (
            <div className="rd-tbl-row" style={{ gridTemplateColumns: '1fr' }}>
              <span className="rd-tbl-cell" style={{ color: 'var(--placeholder)', fontSize: 13, padding: '18px 4px' }}>
                Nenhum registro ainda — os dados aparecem aqui assim que houver lançamentos.
              </span>
            </div>
          )}
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
        <div onClick={() => { setEditRow(null); setEditOtp(null); }} style={{ position: 'fixed', inset: 0, background: 'rgba(15,27,58,.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: 16 }}>
          <div onClick={(e) => e.stopPropagation()} style={{ background: 'var(--surface, #fff)', borderRadius: 14, padding: 20, width: 'min(560px, 94vw)', maxHeight: '88vh', overflow: 'auto', boxShadow: '0 20px 60px rgba(0,0,0,.25)' }}>
            <div style={{ fontWeight: 700, fontSize: 15, color: 'var(--ink, #16277D)', marginBottom: 12 }}>{editRow.title || 'Editar'}</div>
            {editMsg && <div className={`rd-badge ${editMsg.ok ? 'rd-b-success' : 'rd-b-error'}`} style={{ height: 'auto', padding: '8px 12px', fontSize: 12.5, marginBottom: 10, display: 'block' }}>{editMsg.text}</div>}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              {(editRow.fields || []).map((f: any, i: number) => (
                <div key={i} style={{ gridColumn: f.span === 'span 2' ? '1 / -1' : 'auto', display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <label style={{ fontSize: 12, color: 'var(--placeholder)', fontWeight: 600 }}>{f.label}</label>
                  {editRow.readOnly
                    ? <div style={{ fontSize: 13.5, color: 'var(--ink, #16277D)', fontWeight: 600, padding: '4px 0', wordBreak: 'break-word' }}>
                        {(f.value ?? editVals[f.key]) || '—'}
                        {/* 09/09/2026: detalhe pode trazer documentos (f.docs) — "abrir a pasta" mostra o PDF de cada item antes de assinar */}
                        {Array.isArray(f.docs) && f.docs.length > 0 && <div style={{ marginTop: 4 }}><DocButtons docs={f.docs} compact /></div>}
                      </div>
                    : f.type === 'select'
                    ? <select className="rd-input" value={editVals[f.key] ?? ''} onChange={(e) => setEditVals((s) => ({ ...s, [f.key]: e.target.value }))}>
                        {(f.options || []).map((o: any, k: number) => <option key={k} value={o.value}>{o.label}</option>)}
                      </select>
                    : f.type === 'multiselect'
                    ? <select className="rd-input" multiple style={{ height: 120 }} value={lerLista(editVals[f.key])}
                        onChange={(e) => setEditVals((s) => ({ ...s, [f.key]: JSON.stringify(Array.from(e.target.selectedOptions).map((o) => o.value)) }))}>
                        {(f.options || []).map((o: any, k: number) => <option key={k} value={o.value}>{o.label}</option>)}
                      </select>
                    : f.type === 'textarea'
                      ? <textarea className="rd-input" style={{ height: 80, resize: 'vertical' }} value={editVals[f.key] ?? ''} onChange={(e) => setEditVals((s) => ({ ...s, [f.key]: e.target.value }))} />
                      : <input className="rd-input" type={f.type === 'date' ? 'date' : 'text'} value={editVals[f.key] ?? ''} onChange={(e) => setEditVals((s) => ({ ...s, [f.key]: e.target.value }))} />}
                </div>
              ))}
            </div>
            {editOtp && (
              <div style={{ marginTop: 14, paddingTop: 14, borderTop: '1px solid var(--border, #E2E8F0)', display: 'flex', flexDirection: 'column', gap: 6 }}>
                <label style={{ fontSize: 12, color: 'var(--placeholder)', fontWeight: 600 }}>Código OTP (6 dígitos)</label>
                <input className="rd-input" style={{ maxWidth: 200, letterSpacing: 2, fontWeight: 600 }} inputMode="numeric" autoFocus
                  placeholder="000000" value={editOtp.code}
                  onChange={(e) => setEditOtp({ ...editOtp, code: e.target.value.replace(/\D/g, '').slice(0, 6) })} />
                <span style={{ fontSize: 12, color: '#B45309' }}>
                  Saída de dinheiro — nada foi pago ainda. O código foi enviado ao e-mail do Jordan.
                </span>
              </div>
            )}
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 14 }}>
              {editRow.readOnly && <button type="button" className="rd-btn rd-btn-primary" onClick={() => { setEditRow(null); setEditOtp(null); }}>Fechar</button>}
              {!editRow.readOnly && <button type="button" className="rd-btn rd-btn-outline" onClick={() => { setEditRow(null); setEditOtp(null); }}>Cancelar</button>}
              {!editRow.readOnly && <button type="button" className="rd-btn rd-btn-primary" disabled={editBusy || !!(editOtp && editOtp.code.length !== 6)} onClick={async () => {
                setEditBusy(true); setEditMsg(null);
                try {
                  let tok: string | null = null; try { tok = localStorage.getItem('access_token'); } catch { /* */ }
                  const _otp = editOtp && editOtp.code ? { otp_code: editOtp.code, _gate_ref: editOtp.ref } : {};
                  const res = await fetch(editRow.endpoint, { method: editRow.method || 'PATCH', headers: { 'Content-Type': 'application/json', ...(tok ? { Authorization: `Bearer ${tok}` } : {}) }, body: JSON.stringify({ ...(editRow.fixed || {}), ...editVals, ..._otp }) });
                  const d = await res.json().catch(() => ({}));
                  if (!res.ok) throw new Error(msgErro(d) || 'Não foi possível salvar.');
                  // Gate de dinheiro: o backend NÃO pagou, só emitiu o código. Fechar aqui
                  // (o caminho de sucesso abaixo) era o bug — some a única tela onde o
                  // código pode ser digitado. Mantém o modal aberto e pede o OTP.
                  if (d && d.otp_required) {
                    setEditOtp({ ref: d.ref || '', code: '' });
                    setEditMsg({ ok: true, text: d.message || 'Confirme com o código OTP enviado ao e-mail do Jordan.' });
                    return;
                  }
                  setEditMsg({ ok: true, text: d.message || editRow.okMsg || 'Salvo.' });
                  // Mostra o OK por um instante, fecha o modal e recarrega os dados.
                  // Antes o modal ficava aberto e a tabela nao mudava: o usuario clicava
                  // de novo achando que nao tinha funcionado.
                  setTimeout(() => { setEditRow(null); setEditMsg(null); setEditOtp(null); recarregar(); }, 1100);
                } catch (e) { setEditMsg({ ok: false, text: e instanceof Error ? e.message : 'Erro.' }); }
                finally { setEditBusy(false); }
              }}>{editBusy ? 'Enviando…' : editOtp ? 'Confirmar com OTP' : (editRow.submitLabel || 'Salvar')}</button>}
            </div>
          </div>
        </div>
      )}
      {signRow && (
        <DisciplinarySignatureModal
          isOpen
          action={signRow as any}
          signerType={signerType as any}
          onClose={() => setSignRow(null)}
          onSuccess={() => { setSignRow(null); recarregar(); }}
        />
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
  const [resultado, setResultado] = useState<Record<string, unknown> | null>(null); // painel opt-in (scr.submit.showResult)
  const [otp, setOtp] = useState<{ ref: string; code: string } | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [attMsg, setAttMsg] = useState<string | null>(null);
  const [scanOpen, setScanOpen] = useState(false);
  const [colar, setColar] = useState(''); // campo "colar código" (PIX copia-e-cola / linha digitável)
  const set = (k: string, v: string) => setVals((s) => ({ ...s, [k]: v }));
  // QA E2E 08/09: campo com `value` no builder (mês/ano, competência, período) não entrava no estado → o input
  // abria vazio e o envio dava 422 / deixava {mes}/{ano} sem preencher. Semeia o estado com os valores padrão.
  useEffect(() => {
    const v: Record<string, string> = {};
    for (const f of (scr.fields || []) as any[]) { if (f && f.key && f.value != null && f.value !== '') v[f.key] = typeof f.value === 'string' ? f.value : JSON.stringify(f.value); }
    if (Object.keys(v).length) setVals((s) => ({ ...v, ...s }));
  }, [scr]);
  const recarregar = useContext(ReloadCtx); // re-busca os dados do módulo após um write (refresca selects de outros forms)
  const gated = !!(scr.submit && scr.submit.gated); // ação money/gov (visual de aviso)
  const [preBusy, setPreBusy] = useState(false);
  const [preMsg, setPreMsg] = useState<{ ok: boolean; text: string } | null>(null);

  /** Lê um documento anexado e PREENCHE o formulário. Nunca submete.
   *  Não sobrescreve o que já foi digitado: quem está na tela viu o documento e pode ter
   *  corrigido um campo que o OCR leu torto — a leitura da máquina não pode ganhar da pessoa. */
  async function prefillDoc(file: File | undefined, cfg: any) {
    if (!file || !cfg) return;
    setPreBusy(true); setPreMsg(null);
    try {
      let tok = ''; try { tok = localStorage.getItem('access_token') || ''; } catch { /* */ }
      const fd = new FormData();
      fd.append('arquivo', file);
      if (cfg.alvo) fd.append('alvo', cfg.alvo);
      const res = await fetch(cfg.endpoint, {
        method: 'POST',
        headers: { ...(tok ? { Authorization: `Bearer ${tok}` } : {}) },
        body: fd,
      });
      const r = await res.json().catch(() => ({}));
      if (!res.ok) { setPreMsg({ ok: false, text: msgErro(r) || 'Não consegui ler o documento.' }); return; }
      const campos = (r && r.campos) || {};
      const aplicados: string[] = [];
      setVals((s) => {
        const n = { ...s };
        for (const [k, v] of Object.entries(campos)) {
          if (v == null || v === '') continue;
          if (n[k]) continue;              // já digitado → a pessoa manda
          n[k] = String(v); aplicados.push(k);
        }
        return n;
      });
      const n = Object.keys(campos).length;
      setPreMsg({
        ok: n > 0,
        text: n > 0
          ? `${r.documento ? r.documento + ' — ' : ''}${n} campo(s) lido(s). Confira antes de salvar.`
          : (r.message || 'Nenhum campo legível neste arquivo. Preencha à mão.'),
      });
    } catch {
      setPreMsg({ ok: false, text: 'Falha ao enviar o documento.' });
    } finally { setPreBusy(false); }
  }

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

  // Campos `type: "json"` chegam como TEXTO do textarea e a rota espera lista/objeto.
  // Converte só esses; o que não for JSON válido segue como texto e o backend responde o
  // erro real — melhor que engolir e mandar coisa errada em silêncio.
  function corpoComJson(): Record<string, unknown> {
    const campos: any[] = scr.fields || [];
    const out: Record<string, unknown> = { ...vals };
    for (const f of campos) {
      if (f?.type !== 'json' && f?.type !== 'multiselect') continue;
      const bruto = (vals as Record<string, string>)[f.key];
      if (bruto == null || bruto === '') { delete out[f.key]; continue; }
      try { out[f.key] = JSON.parse(bruto); } catch { /* deixa o texto; o backend diz o que faltou */ }
    }
    return out;
  }

  async function fire(extra: Record<string, unknown>) {
    let tok: string | null = null;
    try { tok = localStorage.getItem('access_token'); } catch { /* */ }
    // Upload multipart (scr.submit.multipart): manda arquivo(s) + campos como FormData. Sem
    // Content-Type manual (o browser põe o boundary). scr.submit.fixed = campos constantes
    // (ex.: folder_id/category); titleFromFile = usa o nome do arquivo como title se faltar.
    // _url é montado ANTES do branch multipart porque as rotas de anexo (consultor
    // perguntar-arquivo, currículo, folha Alterdata) recebem o ARQUIVO no corpo e os demais
    // campos como QUERY — as duas coisas ao mesmo tempo.
    let _url = scr.submit.endpoint;
    // Parâmetro de PATH: endpoint com {chave} (ex.: /prontuario/{employee_id}) recebe o valor do campo
    // de mesma chave, que sai do corpo/query. Sem isso rota com id no caminho não tinha como virar form.
    const _noPath = new Set<string>();
    _url = _url.replace(/\{(\w+)\}/g, (m: string, k: string) => {
      const v = (vals as Record<string, string>)[k];
      if (v == null || v === '') return m;
      _noPath.add(k); return encodeURIComponent(v);
    });
    if (scr.submit.query) {
      const _qs = new URLSearchParams();
      for (const [k, v] of Object.entries({ ...vals, ...extra })) if (v != null && v !== '' && !_noPath.has(k)) _qs.append(k, String(v));
      const _s = _qs.toString();
      if (_s) _url += (_url.includes('?') ? '&' : '?') + _s;   // preserva query já fixa no endpoint
    }
    if (scr.submit.multipart) {
      const fd = new FormData();
      for (const [k, v] of Object.entries(scr.submit.fixed || {})) fd.append(k, String(v));
      // com query, os campos JÁ foram para a URL: repetir no FormData faria o backend ver o
      // mesmo campo duas vezes, por dois canais.
      if (!scr.submit.query) for (const [k, v] of Object.entries({ ...vals, ...extra })) { if (v != null && v !== '') fd.append(k, String(v)); }
      let firstName = '';
      for (const [k, f] of Object.entries(files)) { if (f) { fd.append(k, f); if (!firstName) firstName = f.name; } }
      if (scr.submit.titleFromFile && firstName && !fd.has('title')) fd.append('title', firstName);
      const resm = await fetch(_url, {
        method: scr.submit.method || 'POST',
        headers: { ...(tok ? { Authorization: `Bearer ${tok}` } : {}) },
        body: fd,
      });
      const dm = await resm.json().catch(() => ({}));
      return { res: resm, d: dm };
    }
    // JSON: o corpo continua indo mesmo com query — rota que declara só query o ignora, e
    // manter um caminho único de fetch evita duas manutenções.
    // GET/HEAD não podem ter corpo (fetch lança TypeError) — forms de CONSULTA usam method GET + query.
    const _semCorpo = ['GET', 'HEAD'].includes(String(scr.submit.method || 'POST').toUpperCase());
    const res = await fetch(_url, {
      method: scr.submit.method || 'POST',
      headers: { 'Content-Type': 'application/json', ...(tok ? { Authorization: `Bearer ${tok}` } : {}) },
      ...(_semCorpo ? {} : { body: JSON.stringify(Object.fromEntries(Object.entries({ ...corpoComJson(), ...extra }).filter(([k]) => !_noPath.has(k)))) }),
    });
    const d = await res.json().catch(() => ({}));
    return { res, d };
  }

  async function submit(withOtp = false) {
    setResultado(null);
    if (!scr.submit) return;
    setBusy(true); setMsg(null);
    try {
      const extra = withOtp && otp ? { otp_code: otp.code, _gate_ref: otp.ref } : {};
      const { res, d } = await fire(extra);
      if (d && d.otp_required) { // gate exige OTP humano → entra no modo OTP, mantém os campos
        setOtp({ ref: d.ref || '', code: '' }); setConfirming(false);
        // CONFERÊNCIA ANTES DE ASSINAR. Enquanto este painel não existia, a tela dizia
        // «49 diarista(s) · R$ 0,49» e já pedia o código: o OTP era digitado sem nunca ter
        // visto nome, chave e valor de quem recebe. Ver a lista em outra aba não serve —
        // outro filtro é outra seleção, e a que importa é a que está prestes a sair.
        // Não depende de showResult: em tela de dinheiro, conferir não é opt-in.
        if (typeof d === 'object') setResultado(d as Record<string, unknown>);
        setMsg({ ok: true, text: d.message || 'Confirme com o código OTP enviado ao e-mail do Jordan.' });
        return;
      }
      // msgErro() e não `d.detail`: o 422 do FastAPI vem como LISTA de objetos, e jogar
      // isso num template imprime "[object Object]". O helper já existia e era usado nos
      // outros dois pontos de submit — este, o do FORM, tinha ficado de fora. Apareceu ao
      // tornar `regime_empresa` obrigatório em 15/08/2026: o guard que impede o número
      // errado só ajuda se a tela disser POR QUE recusou.
      if (!res.ok) throw new Error(msgErro(d) || 'Não foi possível concluir.');
      // honesto: mostra a mensagem REAL do backend (não inventa sucesso)
      setMsg({ ok: d.ok !== false, text: d.message || scr.submit.okMsg || 'Concluído.' });
      // Gancho de RESULTADO (opt-in scr.submit.showResult): forms de CÁLCULO devolvem escalares
      // (ex.: valor_das, alíquota) que o gestor precisa VER. Sem a flag, nada muda nos outros forms.
      const _showRes = !!(scr.submit && (scr.submit as { showResult?: boolean }).showResult);
      if (_showRes && d && typeof d === 'object') setResultado(d as Record<string, unknown>);
      // Gancho de documento: ações que GERAM um doc (aviso de férias, recibos, exports) devolvem
      // d.doc {url, fmt} → abre direto (aditivo; formas sem d.doc não mudam).
      if (d && d.doc && d.doc.url) { try { await abrirDoc(d.doc as DocRef); } catch { /* abre manual depois */ } }
      setFiles({}); setOtp(null); setConfirming(false);
      if (!_showRes) setVals({}); // calculadora: mantém os inputs p/ recalcular; write: limpa
      // Fio solto: após um write bem-sucedido, re-busca os dados do módulo para que os selects
      // de OUTROS forms reflitam a mudança sem F5. Calculadora (showResult) NÃO recarrega — não
      // escreve nada e o reload apagaria o painel de resultado (armadilha do recarregar 1200ms).
      if (d.ok !== false && !_showRes) setTimeout(() => { try { recarregar(); } catch { /* noop */ } }, 1200);
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
      {resultado && (() => {
        // CONTAGEM x DINHEIRO. Não dá pra decidir pelo valor: 86 (notas) e 250000
        // (reais) são ambos inteiros — por isso quem decide é o NOME do campo.
        // Dinheiro sempre com 2 casas (R$250.000,00 ao lado de R$42.050,83);
        // contagem sem casas (86 documentos, não "86,00").
        const MOEDA = /valor|receita|saldo|liquido|líquido|bruto|economia|preco|preço|custo|salario|salário|das|irpj|csll|cofins|pis|cpp|iss|inss|fgts|multa|juros|desconto/i;
        const fmt = (v: unknown, k = '') => typeof v !== 'number' ? String(v)
          : (MOEDA.test(k) || !Number.isInteger(v))
            ? v.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
            : v.toLocaleString('pt-BR');
        const pretty = (k: string) => k.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
        const skip = new Set(['ok', 'message', 'doc', 'otp_required', 'ref', 'otp', 'erro', 'detail']);
        const rows: Array<{ label: string; value: string | null; sub?: string }> = [];
        for (const [k, v] of Object.entries(resultado)) {
          if (skip.has(k)) continue;
          // Lista de gente (ex.: `itens` do lote antes do OTP): uma linha por pessoa, com a
          // chave PIX embaixo do nome. Antes o painel descartava todo array em silêncio —
          // o dado chegava do backend e sumia na renderização.
          if (Array.isArray(v)) {
            if (!v.length) continue;
            rows.push({ label: `${pretty(k)} (${v.length})`, value: null });
            for (const el of v as unknown[]) {
              if (el && typeof el === 'object') {
                const o = el as Record<string, unknown>;
                const nome = String(o.nome ?? o.beneficiario ?? o.label ?? '—');
                const chave = o.chave ?? o.pix_key;
                const val = o.valor ?? o.value;
                rows.push({
                  label: nome,
                  sub: chave != null ? String(chave) : undefined,
                  value: typeof val === 'number' ? fmt(val, 'valor') : (val != null ? String(val) : ''),
                });
              } else { rows.push({ label: String(el), value: '' }); }
            }
            continue;
          }
          if (v && typeof v === 'object' && !Array.isArray(v)) {
            rows.push({ label: pretty(k), value: null });
            for (const [k2, v2] of Object.entries(v as Record<string, unknown>)) {
              if (v2 !== null && typeof v2 !== 'object') rows.push({ label: '· ' + pretty(k2), value: fmt(v2, k2) });
            }
          } else if (v !== null && !Array.isArray(v)) {
            rows.push({ label: pretty(k), value: fmt(v, k) });
          }
        }
        if (!rows.length) return null;
        return (
          <div style={{ background: 'var(--card, rgba(127,127,127,0.06))', border: '1px solid rgba(127,127,127,0.2)', borderRadius: 10, padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 3 }}>
            <div style={{ fontSize: 12, fontWeight: 700, opacity: 0.75, marginBottom: 4 }}>Resultado</div>
            {rows.map((r, i) => r.value === null ? (
              <div key={i} style={{ fontSize: 12, fontWeight: 700, opacity: 0.6, marginTop: 4 }}>{r.label}</div>
            ) : (
              <div key={i} style={{ display: 'flex', justifyContent: 'space-between', gap: 14, fontSize: 12.5, alignItems: 'baseline' }}>
                <span style={{ opacity: 0.7 }}>
                  {r.label}
                  {r.sub && <span style={{ opacity: 0.55, fontSize: 11.5, marginLeft: 6, fontVariantNumeric: 'tabular-nums' }}>{r.sub}</span>}
                </span>
                <span style={{ fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>{r.value}</span>
              </div>
            ))}
          </div>
        );
      })()}
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
      {/* Anexar documento e PREENCHER (scr.prefill). Diferente de scr.attach: aquele manda o
          arquivo junto no submit; este só LÊ e devolve campos, sem criar nada. O que voltar cai
          no formulário e a pessoa confere antes de salvar — por isso nunca submete sozinho. */}
      {scr.prefill && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <label className="rd-btn rd-btn-outline" style={{ cursor: preBusy ? 'wait' : 'pointer', opacity: preBusy ? 0.6 : 1, display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12.5, padding: '7px 12px' }}>
            📄 {preBusy ? 'Lendo o documento…' : (scr.prefill.label || 'Anexar documento e preencher')}
            <input type="file" accept={scr.prefill.accept || 'image/*,.pdf'} style={{ display: 'none' }}
              disabled={preBusy}
              onChange={(e) => { prefillDoc(e.target.files?.[0], scr.prefill); e.currentTarget.value = ''; }} />
          </label>
          {scr.prefill.hint && !preMsg && <span className="rd-scr-sub" style={{ margin: 0 }}>{scr.prefill.hint}</span>}
          {preMsg && (
            <span className={`rd-badge ${preMsg.ok ? 'rd-b-success' : 'rd-b-error'}`}
              style={{ height: 'auto', padding: '6px 10px', fontSize: 12 }}>{preMsg.text}</span>
          )}
        </div>
      )}
      {scr.originField && (
        <div className="rd-field" style={{ gridColumn: 'span 2' }}>
          <label className="rd-label" style={{ textTransform: 'none', letterSpacing: 0, fontSize: 11 }}>
            Conta de origem — de qual empresa o dinheiro sai
          </label>
          {/* ⚠️ SEM default 'inter'. Antes era `vals.origem || 'inter'`: a tela MOSTRAVA
              "Inter — Conecta Mais Eletrônica" selecionado enquanto o valor real seguia
              VAZIO. O operador lia Inter, não tocava no campo, e o pagamento saía da
              empresa errada — foi assim que duas ordens de VT da Patrimonial nasceram na
              Eletrônica em 14/08. De qual CNPJ o dinheiro sai é decisão, e decisão não
              tem padrão. */}
          <select className="rd-input" value={vals.origem || ''} onChange={(e) => set('origem', e.target.value)}>
            <option value="">— escolha a conta —</option>
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
            {f.type === 'geo' ? (
              /* GPS do celular: preenche lat/lng (latKey/lngKey) — check-in do gerente no posto (07/09/2026) */
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <button type="button" className="rd-btn rd-btn-outline" onClick={() => {
                  if (typeof navigator === 'undefined' || !navigator.geolocation) { set(f.key, 'sem GPS neste aparelho'); return; }
                  set(f.key, 'obtendo…');
                  navigator.geolocation.getCurrentPosition((pos) => {
                    const la = pos.coords.latitude.toFixed(6), lo = pos.coords.longitude.toFixed(6);
                    set(f.latKey || 'lat', la); set(f.lngKey || 'lng', lo);
                    set(f.key, `${la}, ${lo} (±${Math.round(pos.coords.accuracy)} m)`);
                  }, (err) => set(f.key, `sem GPS: ${err.message}`), { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 });
                }}>📍 Usar minha localização</button>
                <span style={{ fontSize: 12, color: 'var(--muted, #64748B)' }}>{vals[f.key] || 'ainda não capturada'}</span>
              </div>
            ) : f.type === 'file' ? (
              <input className="rd-input" type="file" accept={f.accept}
                onChange={(e) => setFiles((s) => ({ ...s, [f.key]: (e.target.files && e.target.files[0]) || null }))} />
            ) : f.type === 'select' ? (
              <select className="rd-input" value={vals[f.key] || ''} onChange={(e) => set(f.key, e.target.value)}>
                <option value="">{f.ph || 'Selecione…'}</option>
                {(f.options || []).map((o: any) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            ) : f.type === 'multiselect' ? (
              // Vários valores → guardados como JSON no estado (Record<string,string>) e viram lista em corpoComJson().
              <select className="rd-input" multiple style={{ height: Math.min(220, 28 * Math.max(4, (f.options || []).length)) }}
                value={lerLista(vals[f.key])}
                onChange={(e) => set(f.key, JSON.stringify(Array.from(e.target.selectedOptions).map((o) => o.value)))}>
                {(f.options || []).map((o: any) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            ) : (f.type === 'textarea' || f.type === 'json') ? (
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
function TabsScreen({ scr, tab, onTab, onNav }: { scr: any; tab: string; onTab: (id: string) => void; onNav?: (id: string) => void }) {
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
      {act ? <Screen scr={act.screen} onNav={onNav} /> : <EmptyReal />}
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
/** Um bloco que estoura não pode levar o módulo inteiro junto.
 *
 * Origem: 15/09/2026, vídeo `errodp.mp4`. O backend passou a emitir `fieldsRef`/`verDaLinha`
 * e o bundle que estava no ar não sabia ler nenhuma das duas. O throw subiu até o
 * `app/error.tsx` — boundary de ROTA — e apagou a página inteira: tela preta, «Algo deu
 * errado», e com ela o menu lateral. A Pyetra não tinha como nem trocar de tela; só restava
 * voltar para o início e tentar outro módulo, que quebrava igual.
 *
 * Aqui o erro para no conteúdo. O shell (menu, abas, busca, topo) continua de pé e ela navega
 * para outro lugar. O `key` do elemento reseta este estado quando a tela muda — sem isso a
 * tela quebrada gruda e a próxima nasce quebrada por herança.
 */
class TelaSegura extends Component<{ children: ReactNode }, { erro: Error | null }> {
  state: { erro: Error | null } = { erro: null };

  static getDerivedStateFromError(erro: Error) { return { erro }; }

  componentDidCatch(erro: Error) {
    // Vai para o console do navegador: é o que a varredura de telas lê para acusar a quebra.
    console.error('[redesign] a tela quebrou ao renderizar:', erro);
  }

  render() {
    if (!this.state.erro) return this.props.children;
    return (
      <div className="rd-card" style={{ padding: 24, marginTop: 16 }}>
        <div style={{ fontWeight: 600, marginBottom: 6 }}>Esta tela não abriu</div>
        <div style={{ color: 'var(--muted)', fontSize: 13, marginBottom: 14 }}>
          O resto do módulo continua funcionando — use o menu ao lado para seguir. Se repetir,
          avise com o nome da tela.
        </div>
        <button type="button" className="rd-btn" onClick={() => this.setState({ erro: null })}>
          Tentar de novo
        </button>
      </div>
    );
  }
}

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
  const [q, setQ] = useState(''); // termo do campo "Buscar…" (o input era decorativo: sem estado)
  // 'idle' sem token (exemplo direto) · 'loading' buscando · 'done' resolvido
  const [dataState, setDataState] = useState<'idle' | 'loading' | 'done'>('idle');
  // Bumpado por ReloadCtx após uma ação de escrita → refaz o fetch da tela.
  const [reloadKey, setReloadKey] = useState(0);
  //: grupo -> aberto. Ausente = decide pelo item ativo (ver `agrupar`).
  const [abertos, setAbertos] = useState<Record<string, boolean>>({});

  // `useSearchParams` e não `window.location.search`: o Ctrl+K navega para OUTRA ABA do MESMO
  // módulo, então só a query muda. Lendo o window direto e dependendo de [screens], o efeito
  // não rodava de novo — a URL virava `?t=kits-assinaturas-pendentes` e a tela ficava na Visão
  // geral. Medido no navegador em 17/09/2026; no terminal a navegação parecia perfeita.
  const sp = useSearchParams();

  useEffect(() => {
    try { if (localStorage.getItem('rd-sidebar-collapsed') === '1') setCollapsed(true); } catch { /* */ }
    const t = sp.get('t');
    // confia no ?t da URL (telas de ação/extraMenu chegam via patch, depois)
    if (t) setActive(t);
    const tb = sp.get('tab');
    if (tb) setActiveTab(tb); // aba do grupo (fundação tabs F0)
  }, [screens, sp]);

  // Dados reais da API (READ-ONLY). Sem token → mantém exemplos do pacote.
  // RETRY: logo após o login o token pode ainda não estar no localStorage quando este efeito
  // roda — a versão anterior desistia na hora e a tela ficava com o menu curto do pacote, SEM
  // as telas reais e sem os botões de documento, até um F5 manual. Falha de rede/401 idem.
  useEffect(() => {
    let cancel = false;
    let tentativa = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const carregar = () => {
      if (cancel) return;
      let tok: string | null = null;
      try { tok = localStorage.getItem('access_token'); } catch { /* */ }
      if (!tok) {
        if (tentativa++ < 5) { timer = setTimeout(carregar, 300 * tentativa); }
        else setDataState('idle');
        return;
      }
      setDataState('loading');
      fetch(`/api/v1/redesign/data/${slug}`, { headers: { Authorization: `Bearer ${tok}` } })
        .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
        .then((j) => { if (!cancel) { setPatches(j.screens || {}); setExtraMenu(j.extraMenu || []); setDataState('done'); } })
        .catch(() => {
          if (cancel) return;
          if (tentativa++ < 3) { timer = setTimeout(carregar, 600 * tentativa); }
          else setDataState('done');
        });
    };
    carregar();
    return () => { cancel = true; if (timer) clearTimeout(timer); };
  }, [slug, reloadKey]);

  // Módulo cujo menu vem TODO do backend (JSON do pacote com "menu": []) nasce SEM tela ativa:
  // o useState inicial lê menu[0] do pacote, que não existe, e `active` fica ''. Como
  // `isReal = !!patches[active]` não tem fallback (ao contrário de `scr`, logo abaixo), a tela
  // exibe "Aguardando dado" para sempre — mesmo com a API devolvendo linhas. Foi o que manteve
  // a Central de Aprovações vazia com 3 rascunhos no banco: a lista existia, ninguém a via.
  // Só entra quando `active` está vazio, então não atropela ?t= nem clique do usuário.
  useEffect(() => {
    if (active) return;
    const primeira = normMenu(extraMenu)[0]?.id;
    if (primeira) setActive(primeira);
  }, [extraMenu, active]);

  const toggle = () => setCollapsed((c) => { const n = !c; try { localStorage.setItem('rd-sidebar-collapsed', n ? '1' : '0'); } catch { /* */ } return n; });
  const go = (id: string, tabId?: string) => {
    setQ(''); // troca de tela zera a busca (senão a tela nova abre filtrada e parece vazia)
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
  // Quem está logado. Estava fixo em 'Jordan Jesus'/'JJ': a Pyetra logava e via o nome do
  // Jordan no rodapé da conta dela. /auth/me já devolve name+role — era só ligar.
  const [me, setMe] = useState<{ name: string; role: string } | null>(null);
  useEffect(() => {
    let vivo = true;
    let tok = ''; try { tok = localStorage.getItem('access_token') || ''; } catch { /* */ }
    if (!tok) return;
    fetch('/api/v1/auth/me', { headers: { Authorization: `Bearer ${tok}` } })
      .then((r) => (r.ok ? r.json() : null))
      .then((u) => { if (vivo && u?.name) setMe({ name: u.name, role: u.role || '' }); })
      .catch(() => { /* sem sessão legível: mostra o genérico, nunca o nome de outra pessoa */ });
    return () => { vivo = false; };
  }, []);
  const nomeUsuario = me?.name || 'Minha conta';
  const papelUsuario = me?.role || '';
  const initials = (me?.name || '')
    .split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]).join('').toUpperCase() || '—';

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
          {agrupar([...menu, ...normMenu(extraMenu)]).map((bloco, bi) => {
            const itemAtivoAqui = bloco.itens.some((m) => m.id === active);
            // O grupo do item aberto nasce expandido — a pessoa tem de VER onde está.
            const aberto = bloco.grupo === null || abertos[bloco.grupo] === true
              || (abertos[bloco.grupo] === undefined && itemAtivoAqui);
            return (
              <div key={bloco.grupo ?? `solto-${bi}`}>
                {bloco.grupo && (
                  <button
                    type="button"
                    className={`rd-nav-item rd-nav-grupo${itemAtivoAqui && !aberto ? ' active' : ''}`}
                    aria-expanded={aberto}
                    onClick={() => setAbertos((a) => ({ ...a, [bloco.grupo as string]: !aberto }))}
                    title={`${bloco.grupo} — ${bloco.itens.length} telas`}
                  >
                    <Ico d={bloco.itens[0]?.icon || 'M3 3v18h18'} size={17}
                         stroke={itemAtivoAqui ? '#fff' : '#9DB0D9'} />
                    <span style={{ flex: 1 }}>{bloco.grupo}</span>
                    {!collapsed && (
                      <span style={{ fontSize: 10, opacity: .55, marginLeft: 6 }}>
                        {bloco.itens.length} {aberto ? '▾' : '▸'}
                      </span>
                    )}
                  </button>
                )}
                {aberto && bloco.itens.map((m) => (
                  <button key={m.id} type="button" title={m.label}
                    className={`rd-nav-item${m.id === active ? ' active' : ''}`}
                    style={bloco.grupo ? { paddingLeft: collapsed ? undefined : 30 } : undefined}
                    onClick={() => go(m.id)}>
                    <Ico d={m.icon} size={17} stroke={m.id === active ? '#fff' : '#9DB0D9'} />
                    <span>{m.label}</span>
                  </button>
                ))}
              </div>
            );
          })}
        </nav>
        <div className="rd-side-foot">
          <div className="rd-avatar">{initials}</div>
          {!collapsed && (
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="n">{nomeUsuario}</div>
              <div className="r">{papelUsuario}</div>
            </div>
          )}
          {!collapsed && (
            <div style={{ display: 'flex', gap: 4 }}>
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
          {/* Filtra o conteúdo da tela ABERTA. Para trocar de TELA é o Ctrl+K. */}
          <div className="rd-search">
            <Search size={16} color="var(--placeholder)" />
            <input placeholder={scr?.searchHint || 'Buscar…'} value={q} onChange={(e) => setQ(e.target.value)} />
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
              ? (
                <ReloadCtx.Provider value={() => setReloadKey((k) => k + 1)}>
                  <SearchCtx.Provider value={q}>
                    <TelaSegura key={`${active}:${activeTab || ''}`}>
                      {scr?.type === 'tabs'
                        ? <TabsScreen scr={scr} tab={activeTab} onTab={(id) => go(active, id)} onNav={go} />
                        : <Screen scr={scr} onNav={go} />}
                    </TelaSegura>
                  </SearchCtx.Provider>
                </ReloadCtx.Provider>
              )
              : <EmptyReal />}
        </main>
      </div>
    </div>
  );
}
