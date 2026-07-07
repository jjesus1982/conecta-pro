'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  ShieldCheck, ShieldAlert, Loader2, CheckCircle2, AlertTriangle, XCircle, Send,
  FileSignature, Receipt, UserSearch, RefreshCw, ExternalLink, Truck, PenLine,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  conferirKit, type AtlasResult,
  pendenciasAssinatura, type AssinaturasResult,
  faturarKit, type FaturarPreview,
  statusEntrega, prepararEntrega, marcarEntregue, type EntregaStatus,
  listarFuncionarios, visaoFuncionario, type VisaoFuncionario,
  alinhamentoDp, type DpAlinhamento,
} from '@/services/gedeon/kitGestaoService';

const sevIcon = (s: string) =>
  s === 'ok' ? <CheckCircle2 className="w-4 h-4 text-emerald-500" />
  : s === 'alerta' ? <AlertTriangle className="w-4 h-4 text-amber-500" />
  : <XCircle className="w-4 h-4 text-red-500" />;

export default function KitGestaoSecoes({ cond, comp, onChange }: { cond: string; comp: string; onChange?: () => void }) {
  // ── ATLAS ──
  const [atlas, setAtlas] = useState<AtlasResult | null>(null);
  const [atlasLoad, setAtlasLoad] = useState(false);
  const rodarAtlas = useCallback(async (refresh = false) => {
    setAtlasLoad(true);
    try { setAtlas(await conferirKit(cond, comp || undefined, refresh)); } catch { setAtlas(null); }
    finally { setAtlasLoad(false); }
  }, [cond, comp]);
  useEffect(() => { rodarAtlas(false); }, [rodarAtlas]);

  // ── Entrega ──
  const [entrega, setEntrega] = useState<EntregaStatus | null>(null);
  const [entregaLoad, setEntregaLoad] = useState(false);
  const carregarEntrega = useCallback(async () => {
    try { setEntrega(await statusEntrega(cond, comp || undefined)); } catch { /* ignore */ }
  }, [cond, comp]);
  useEffect(() => { carregarEntrega(); }, [carregarEntrega]);
  const onPreparar = async () => {
    setEntregaLoad(true);
    try { setEntrega(await prepararEntrega(cond, comp || undefined)); onChange?.(); }
    finally { setEntregaLoad(false); }
  };
  const onMarcarEntregue = async () => {
    const canal = prompt('Canal de entrega (whatsapp / email / impresso / manual):', 'whatsapp') || 'manual';
    setEntregaLoad(true);
    try { setEntrega(await marcarEntregue(cond, { competencia: comp || undefined, canal })); }
    finally { setEntregaLoad(false); }
  };

  // ── Faturamento ──
  const [fatLoad, setFatLoad] = useState(false);
  const [preview, setPreview] = useState<FaturarPreview | null>(null);
  const onPreview = async (tipo: 'nfse' | 'boleto' | 'ambos') => {
    setFatLoad(true);
    try { setPreview(await faturarKit(cond, { competencia: comp || undefined, tipo, confirmar: false })); }
    catch (e) { alert('Não foi possível montar o preview: ' + msg(e)); }
    finally { setFatLoad(false); }
  };
  const onConfirmarFaturar = async () => {
    if (!preview) return;
    if (!confirm(`ATENÇÃO: isso vai EMITIR nota/cobrança REAL no valor de R$ ${preview.valor?.toLocaleString('pt-BR')}.\nConfirma?`)) return;
    setFatLoad(true);
    try { const r = await faturarKit(cond, { competencia: comp || undefined, tipo: 'ambos', confirmar: true }); setPreview(r); alert('Emitido. Confira no Faturamento/Fiscal.'); onChange?.(); }
    catch (e) { alert('Falha ao emitir: ' + msg(e)); }
    finally { setFatLoad(false); }
  };

  // ── Pendências de assinatura ──
  const [assin, setAssin] = useState<AssinaturasResult | null>(null);
  useEffect(() => { pendenciasAssinatura(cond, comp || undefined).then(setAssin).catch(() => setAssin(null)); }, [cond, comp]);
  const pendCond = assin?.condominios?.[0];

  // ── DP ──
  const [dp, setDp] = useState<DpAlinhamento | null>(null);
  useEffect(() => { alinhamentoDp(cond, comp || undefined).then(setDp).catch(() => setDp(null)); }, [cond, comp]);

  // ── Visão por funcionário ──
  const [funcs, setFuncs] = useState<string[]>([]);
  const [funcSel, setFuncSel] = useState('');
  const [visao, setVisao] = useState<VisaoFuncionario | null>(null);
  const [visaoLoad, setVisaoLoad] = useState(false);
  useEffect(() => { listarFuncionarios(cond, comp || undefined).then((r) => setFuncs(r.funcionarios || [])).catch(() => setFuncs([])); }, [cond, comp]);
  const verFunc = async (nome: string) => {
    setFuncSel(nome); if (!nome) { setVisao(null); return; }
    setVisaoLoad(true);
    try { setVisao(await visaoFuncionario(nome, cond, comp || undefined)); } catch { setVisao(null); }
    finally { setVisaoLoad(false); }
  };

  return (
    <div className="space-y-5">
      {/* ATLAS + Entrega lado a lado */}
      <div className="grid md:grid-cols-2 gap-5">
        {/* ATLAS */}
        <Card className="border border-[hsl(var(--border))]">
          <CardHeader className="pb-2 flex flex-row items-center justify-between">
            <CardTitle className="text-base flex items-center gap-2">
              {atlas?.selo === 'conferido' ? <ShieldCheck className="w-4 h-4 text-emerald-500" /> : <ShieldAlert className="w-4 h-4 text-amber-500" />}
              ATLAS — Conferência
            </CardTitle>
            <button onClick={() => rodarAtlas(true)} className="p-1.5 rounded-lg border border-[hsl(var(--border))] hover:bg-[hsl(var(--secondary))]" title="Reconferir">
              {atlasLoad ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            </button>
          </CardHeader>
          <CardContent>
            {!atlas ? <p className="text-sm text-[hsl(var(--muted-foreground))]">{atlasLoad ? 'Conferindo…' : 'Sem conferência.'}</p> : (
              <>
                <div className="flex items-center gap-2 mb-3">
                  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold ${atlas.selo === 'conferido' ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/30' : 'bg-red-500/10 text-red-500 border border-red-500/30'}`}>
                    {atlas.selo === 'conferido' ? <><CheckCircle2 className="w-3 h-3" /> CONFERIDO</> : <><AlertTriangle className="w-3 h-3" /> REVISAR</>}
                  </span>
                  <span className="text-xs text-[hsl(var(--muted-foreground))]">{atlas.resumo.ok} ok · {atlas.resumo.alertas} alertas · {atlas.resumo.erros} erros</span>
                  <span className="text-xs text-[hsl(var(--muted-foreground))] ml-auto">{atlas.funcionarios_folha} na folha · {atlas.funcionarios_ativos} ativos</span>
                </div>
                <ul className="space-y-1 max-h-60 overflow-y-auto">
                  {atlas.checks.map((c, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm">
                      {sevIcon(c.severidade)}
                      <div className="min-w-0"><span className="font-medium">{c.check}:</span> <span className="text-[hsl(var(--muted-foreground))]">{c.mensagem}</span></div>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </CardContent>
        </Card>

        {/* Entrega */}
        <Card className="border border-[hsl(var(--border))]">
          <CardHeader className="pb-2"><CardTitle className="text-base flex items-center gap-2"><Truck className="w-4 h-4 text-blue-500" /> Entrega ao cliente</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center gap-2">
              <span className={`px-2 py-0.5 rounded-full text-xs font-semibold border ${
                entrega?.estado === 'entregue' ? 'bg-emerald-500/10 text-emerald-500 border-emerald-500/30'
                : entrega?.estado === 'preparado' ? 'bg-blue-500/10 text-blue-500 border-blue-500/30' : 'bg-gray-500/10 text-[hsl(var(--muted-foreground))] border-gray-500/30'}`}>
                {entrega?.estado === 'entregue' ? 'Entregue' : entrega?.estado === 'preparado' ? 'Preparado' : 'Não preparado'}
              </span>
              {entrega?.indice_link && <a href={entrega.indice_link} target="_blank" rel="noreferrer" className="text-xs text-blue-400 hover:underline flex items-center gap-1">Índice/capa <ExternalLink className="w-3 h-3" /></a>}
            </div>
            <p className="text-xs text-[hsl(var(--muted-foreground))]">Gera a capa/índice do kit (com selo ATLAS) no Drive. O <strong>envio ao cliente é manual</strong> — depois marque como entregue.</p>
            <div className="flex flex-wrap gap-2">
              <button onClick={onPreparar} disabled={entregaLoad} className="px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs flex items-center gap-1.5 disabled:opacity-50">
                {entregaLoad ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FileSignature className="w-3.5 h-3.5" />} Preparar entrega
              </button>
              <button onClick={onMarcarEntregue} disabled={entregaLoad || entrega?.estado === 'nao_preparado'} className="px-3 py-1.5 rounded-lg border border-emerald-300 text-emerald-700 hover:bg-emerald-50 text-xs flex items-center gap-1.5 disabled:opacity-40">
                <Send className="w-3.5 h-3.5" /> Marcar como entregue
              </button>
            </div>
            {entrega?.entregue_em && <p className="text-xs text-[hsl(var(--muted-foreground))]">Entregue em {new Date(entrega.entregue_em).toLocaleString('pt-BR')} via {entrega.canal}.</p>}
          </CardContent>
        </Card>
      </div>

      {/* Faturamento + Assinaturas */}
      <div className="grid md:grid-cols-2 gap-5">
        {/* Faturamento */}
        <Card className="border border-[hsl(var(--border))]">
          <CardHeader className="pb-2"><CardTitle className="text-base flex items-center gap-2"><Receipt className="w-4 h-4 text-violet-500" /> Faturamento — NFS-e + Boleto</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <p className="text-xs text-[hsl(var(--muted-foreground))]">Emite a NFS-e e o boleto do condomínio. <strong>Sempre veja o preview antes</strong> — emitir cria nota/cobrança REAL.</p>
            <div className="flex flex-wrap gap-2">
              <button onClick={() => onPreview('ambos')} disabled={fatLoad} className="px-3 py-1.5 rounded-lg border border-violet-300 text-violet-700 hover:bg-violet-50 text-xs flex items-center gap-1.5 disabled:opacity-50">
                {fatLoad ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Receipt className="w-3.5 h-3.5" />} Preview NFS-e + boleto
              </button>
              <button onClick={() => onPreview('nfse')} disabled={fatLoad} className="px-2.5 py-1.5 rounded-lg border border-[hsl(var(--border))] text-[hsl(var(--muted-foreground))] hover:bg-[hsl(var(--secondary))] text-xs disabled:opacity-50">só NFS-e</button>
              <button onClick={() => onPreview('boleto')} disabled={fatLoad} className="px-2.5 py-1.5 rounded-lg border border-[hsl(var(--border))] text-[hsl(var(--muted-foreground))] hover:bg-[hsl(var(--secondary))] text-xs disabled:opacity-50">só boleto</button>
            </div>
            {preview && (
              <div className="text-xs bg-[hsl(var(--secondary))] rounded-lg p-3 space-y-1 border border-[hsl(var(--border))]">
                <div><strong>Valor:</strong> R$ {preview.valor?.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}</div>
                <div><strong>Mês emissão:</strong> {preview.mes_emissao}</div>
                {!preview.emitido && <div className="text-amber-500">{preview.aviso}</div>}
                {preview.emitido && <div className="text-emerald-500 flex items-center gap-1"><CheckCircle2 className="w-3 h-3" /> Emitido.</div>}
                {!preview.emitido && (
                  <button onClick={onConfirmarFaturar} disabled={fatLoad} className="mt-2 px-3 py-1.5 rounded-lg bg-violet-600 hover:bg-violet-700 text-white text-xs flex items-center gap-1.5 disabled:opacity-50">
                    <PenLine className="w-3.5 h-3.5" /> Confirmar e EMITIR (real)
                  </button>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Pendências de assinatura */}
        <Card className="border border-[hsl(var(--border))]">
          <CardHeader className="pb-2"><CardTitle className="text-base flex items-center gap-2"><FileSignature className="w-4 h-4 text-amber-500" /> Pendências de assinatura</CardTitle></CardHeader>
          <CardContent>
            {!assin ? <p className="text-sm text-[hsl(var(--muted-foreground))]">Carregando…</p> : !pendCond ? <p className="text-sm text-[hsl(var(--muted-foreground))]">Sem dados.</p> : (
              <>
                <p className="text-sm mb-2">
                  <span className="font-semibold">{pendCond.assinados}</span> assinaram ·{' '}
                  <span className={`font-semibold ${pendCond.total_pendentes ? 'text-amber-500' : 'text-emerald-500'}`}>{pendCond.total_pendentes}</span> pendentes
                  <span className="text-xs text-[hsl(var(--muted-foreground))]"> (de {pendCond.funcionarios_folha} na folha)</span>
                </p>
                {pendCond.pendentes.length === 0 ? <p className="text-xs text-emerald-500 flex items-center gap-1">Todos assinaram o VT/VR <CheckCircle2 className="w-3 h-3" /></p> : (
                  <ul className="space-y-1 max-h-48 overflow-y-auto">
                    {pendCond.pendentes.map((p, i) => (
                      <li key={i} className="text-sm flex items-center gap-2">
                        <AlertTriangle className="w-3.5 h-3.5 text-amber-500" /> {p.funcionario}
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-[hsl(var(--secondary))] text-[hsl(var(--muted-foreground))] ml-auto">{p.estado === 'aguardando' ? 'aguardando' : 'sem recibo'}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Visão por funcionário + DP */}
      <div className="grid md:grid-cols-2 gap-5">
        {/* Visão por funcionário */}
        <Card className="border border-[hsl(var(--border))]">
          <CardHeader className="pb-2"><CardTitle className="text-base flex items-center gap-2"><UserSearch className="w-4 h-4 text-blue-500" /> Visão por funcionário</CardTitle></CardHeader>
          <CardContent>
            <select value={funcSel} onChange={(e) => verFunc(e.target.value)} className="text-sm bg-[hsl(var(--card))] text-[hsl(var(--foreground))] border border-[hsl(var(--border))] rounded-lg px-3 py-2 w-full mb-3">
              <option value="">Selecione um funcionário…</option>
              {funcs.map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
            {visaoLoad && <p className="text-sm text-[hsl(var(--muted-foreground))] flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin" /> Buscando docs…</p>}
            {visao && (
              <div className="text-sm space-y-2">
                <p className="text-[hsl(var(--muted-foreground))]">{visao.total_docs} documento(s) — {visao.condominio || cond}</p>
                {visao.kit.length > 0 && <div><p className="text-xs font-semibold text-[hsl(var(--foreground))]">No kit ({visao.kit.length})</p>
                  <ul className="ml-3">{visao.kit.map((d, i) => <li key={i} className="text-xs text-[hsl(var(--muted-foreground))] truncate">• {d.link ? <a href={d.link} target="_blank" rel="noreferrer" className="hover:underline">{d.nome}</a> : d.nome} <span className="text-[hsl(var(--muted-foreground))]">({d.subpasta})</span></li>)}</ul></div>}
                {visao.solides_assinados.length > 0 && <div><p className="text-xs font-semibold text-[hsl(var(--foreground))]">Assinados Sólides ({visao.solides_assinados.length})</p>
                  <ul className="ml-3">{visao.solides_assinados.map((d, i) => <li key={i} className="text-xs text-[hsl(var(--muted-foreground))]">• {d.label}</li>)}</ul></div>}
                {visao.onvio.length > 0 && <div><p className="text-xs font-semibold text-[hsl(var(--foreground))]">Onvio ({visao.onvio.length})</p>
                  <ul className="ml-3">{visao.onvio.slice(0, 8).map((d, i) => <li key={i} className="text-xs text-[hsl(var(--muted-foreground))] truncate">• {d.nome_arquivo}</li>)}</ul></div>}
                {visao.total_docs === 0 && <p className="text-xs text-[hsl(var(--muted-foreground))]">Nenhum documento encontrado para esta pessoa.</p>}
              </div>
            )}
          </CardContent>
        </Card>

        {/* DP */}
        <Card className="border border-[hsl(var(--border))]">
          <CardHeader className="pb-2"><CardTitle className="text-base flex items-center gap-2"><RefreshCw className="w-4 h-4 text-emerald-500" /> Alinhamento DP (Sólides)</CardTitle></CardHeader>
          <CardContent>
            {!dp ? <p className="text-sm text-[hsl(var(--muted-foreground))]">Carregando…</p> : (
              <div className="text-sm space-y-2">
                <p><span className="font-semibold">{dp.com_espelho_dp}</span>/{dp.funcionarios_folha} funcionários da folha com espelho no DP</p>
                {dp.sem_espelho_dp.length > 0 && (
                  <div><p className="text-xs font-semibold text-amber-500">Sem espelho no DP ({dp.sem_espelho_dp.length}):</p>
                    <ul className="ml-3">{dp.sem_espelho_dp.slice(0, 8).map((x, i) => <li key={i} className="text-xs text-[hsl(var(--muted-foreground))]">• {x.folha}</li>)}</ul></div>
                )}
                {dp.afastamentos_mes.length > 0 ? (
                  <div><p className="text-xs font-semibold text-purple-500">Afastamentos no mês ({dp.afastamentos_mes.length}):</p>
                    <ul className="ml-3">{dp.afastamentos_mes.map((a, i) => <li key={i} className="text-xs text-[hsl(var(--muted-foreground))]">• {a.funcionario} — {a.tipo} ({a.inicio})</li>)}</ul></div>
                ) : <p className="text-xs text-[hsl(var(--muted-foreground))]">Sem afastamentos registrados no DP para o mês.</p>}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function msg(e: unknown): string {
  if (e && typeof e === 'object' && 'response' in e) {
    const r = (e as { response?: { data?: { detail?: string } } }).response;
    if (r?.data?.detail) return r.data.detail;
  }
  return e instanceof Error ? e.message : String(e);
}
