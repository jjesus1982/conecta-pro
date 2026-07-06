'use client';

import { useState, useEffect, useRef } from 'react';
import { Landmark, Bot, Send, Loader2, AlertTriangle, History, Paperclip, X, TrendingUp } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';

const API_BASE = '/api/v1/financial/cfo';

function getAuthHeaders(json = true) {
  const token = typeof window !== 'undefined' ? (localStorage.getItem('access_token') || localStorage.getItem('token')) : null;
  return { ...(json ? { 'Content-Type': 'application/json' } : {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) };
}

const AREAS = [
  { value: 'fluxo_caixa', label: 'Fluxo de Caixa' },
  { value: 'resultado', label: 'Resultado / Margem' },
  { value: 'tributos', label: 'Tributos & Encargos' },
  { value: 'estrategico', label: 'Estratégico' },
];

const brl = (v: any) => {
  const n = Number(v);
  return isNaN(n) ? '—' : n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
};

/** Render leve de Markdown (## títulos, **negrito**, listas, --- ). */
function Markdown({ text }: { text: string }) {
  const inline = (s: string, key: any) => {
    const parts = s.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean);
    return parts.map((p, i) =>
      p.startsWith('**') && p.endsWith('**') ? <strong key={i}>{p.slice(2, -2)}</strong>
      : p.startsWith('`') && p.endsWith('`') ? <code key={i} className="bg-gray-100 px-1 rounded text-[13px]">{p.slice(1, -1)}</code>
      : <span key={i}>{p}</span>
    );
  };
  const lines = (text || '').split('\n');
  const out: any[] = [];
  let list: any[] = [];
  const flush = () => { if (list.length) { out.push(<ul key={`u${out.length}`} className="list-disc ml-5 my-1 space-y-0.5">{list}</ul>); list = []; } };
  lines.forEach((raw, i) => {
    const l = raw.trimEnd();
    if (/^#{1,4}\s/.test(l)) { flush(); const t = l.replace(/^#{1,4}\s/, ''); out.push(<h3 key={i} className="font-semibold text-emerald-800 mt-3 mb-1">{inline(t, i)}</h3>); }
    else if (/^(\s*[-*•]\s+)/.test(l)) { list.push(<li key={i}>{inline(l.replace(/^\s*[-*•]\s+/, ''), i)}</li>); }
    else if (/^\s*\d+[.)]\s+/.test(l)) { list.push(<li key={i}>{inline(l.replace(/^\s*\d+[.)]\s+/, ''), i)}</li>); }
    else if (/^\s*---+\s*$/.test(l)) { flush(); out.push(<hr key={i} className="my-2 border-gray-200" />); }
    else if (l.trim() === '') { flush(); }
    else { flush(); out.push(<p key={i} className="my-1 leading-relaxed">{inline(l, i)}</p>); }
  });
  flush();
  return <div className="text-sm text-gray-800">{out}</div>;
}

export default function CfoPage() {
  const [area, setArea] = useState('fluxo_caixa');
  const [pergunta, setPergunta] = useState('');
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [resposta, setResposta] = useState<any>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [historico, setHistorico] = useState<any[]>([]);
  const [pano, setPano] = useState<any>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const carregarHistorico = async () => {
    try {
      const h = await fetch(`${API_BASE}/historico`, { headers: getAuthHeaders() })
        .then((r) => (r.ok ? r.json() : null)).catch(() => null);
      setHistorico((h?.consultas as any[]) || []);
    } catch { /* */ }
  };
  const carregarPanorama = async () => {
    try {
      const p = await fetch(`${API_BASE}/panorama`, { headers: getAuthHeaders() })
        .then((r) => (r.ok ? r.json() : null)).catch(() => null);
      setPano(p);
    } catch { /* */ }
  };
  const [prev, setPrev] = useState<any>(null);
  const carregarPrevisao = async () => {
    try {
      const p = await fetch(`${API_BASE}/previsao-custos`, { headers: getAuthHeaders() })
        .then((r) => (r.ok ? r.json() : null)).catch(() => null);
      setPrev(p);
    } catch { /* */ }
  };
  useEffect(() => { carregarHistorico(); carregarPanorama(); carregarPrevisao(); }, []);

  const [addCusto, setAddCusto] = useState(false);
  const [nc, setNc] = useState<any>({ categoria: 'fixo', descricao: '', valor: '', parcelas_total: '', parcelas_pagas: '' });
  const salvarCusto = async () => {
    if (!nc.descricao.trim() || !nc.valor) return;
    const body: any = { categoria: nc.categoria, descricao: nc.descricao, valor: Number(nc.valor) };
    if (nc.parcelas_total) { body.parcelas_total = Number(nc.parcelas_total); body.parcelas_pagas = Number(nc.parcelas_pagas || 0); }
    await fetch(`${API_BASE}/custos-recorrentes`, { method: 'POST', headers: getAuthHeaders(), body: JSON.stringify(body) });
    setNc({ categoria: 'fixo', descricao: '', valor: '', parcelas_total: '', parcelas_pagas: '' }); setAddCusto(false); carregarPrevisao();
  };
  const removerCusto = async (id: number) => { await fetch(`${API_BASE}/custos-recorrentes/${id}`, { method: 'DELETE', headers: getAuthHeaders() }); carregarPrevisao(); };

  const consultar = async () => {
    if ((!pergunta.trim() && !arquivo) || loading) return;
    setLoading(true); setErro(null); setResposta(null);
    try {
      let r: Response;
      if (arquivo) {
        const fd = new FormData();
        fd.append('arquivo', arquivo); fd.append('area', area); fd.append('pergunta', pergunta);
        r = await fetch(`${API_BASE}/perguntar-arquivo`, { method: 'POST', headers: getAuthHeaders(false), body: fd });
      } else {
        r = await fetch(`${API_BASE}/perguntar`, { method: 'POST', headers: getAuthHeaders(), body: JSON.stringify({ area, pergunta }) });
      }
      if (!r.ok) { const e = await r.json().catch(() => ({})); setErro(e?.detail || `O CFO não respondeu agora (HTTP ${r.status}).`); return; }
      const data = await r.json();
      if (data?.indisponivel) { setErro('CFO IA temporariamente indisponível — os números do painel continuam reais.'); if (data?.panorama) setPano(data.panorama); return; }
      setResposta(data);
      if (data?.panorama) setPano(data.panorama);
      carregarHistorico();
    } catch {
      setErro('Falha de comunicação com o CFO IA. Tente novamente.');
    } finally { setLoading(false); }
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); consultar(); }
  };

  const k = pano?.kpis || {};
  const kv = (code: string) => k?.[code]?.valor;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center gap-3">
        <Landmark className="h-7 w-7 text-emerald-700" />
        <div>
          <h1 className="font-display text-2xl font-semibold text-gray-900">CFO IA</h1>
          <p className="text-sm text-muted-foreground">Seu diretor financeiro de bolso — responde ancorado nos números reais do ERP. Anexe extratos/planilhas para análise. Apoio, não decisão contábil.</p>
        </div>
      </div>

      {/* Painel real (fotografia financeira agora) */}
      {pano && (
        <Card className="border-emerald-200">
          <CardHeader className="pb-2"><CardTitle className="flex items-center gap-2 text-base"><TrendingUp className="h-4 w-4 text-emerald-600" /> Situação financeira agora (dados reais)</CardTitle></CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
              <div>
                <div className="text-xs text-muted-foreground">Saldo em conta</div>
                <div className="font-semibold">{brl(pano.saldo_banco)}</div>
                {pano.saldo_fonte && <div className={`text-[10px] ${String(pano.saldo_fonte).includes('vivo') ? 'text-emerald-600' : 'text-amber-600'}`}>{String(pano.saldo_fonte).includes('vivo') ? '● ao vivo (Inter)' : '○ cadastro'}</div>}
              </div>
              <div><div className="text-xs text-muted-foreground">MRR</div><div className="font-semibold">{brl(kv('MRR') ?? pano.mrr_contratado)}</div></div>
              <div><div className="text-xs text-muted-foreground">Folha mensal</div><div className="font-semibold">{brl(kv('FOLHA') ?? pano.folha_mensal)}</div></div>
              <div><div className="text-xs text-muted-foreground">Margem</div><div className="font-semibold">{kv('MARGEM') != null ? `${Number(kv('MARGEM')).toFixed(1)}%` : '—'}</div></div>
              <div><div className="text-xs text-muted-foreground">Runway (saldo ÷ folha)</div><div className={`font-semibold ${pano.runway_meses != null && pano.runway_meses < 1 ? 'text-red-600' : ''}`}>{pano.runway_meses != null ? `${pano.runway_meses} meses` : '—'}</div></div>
              <div><div className="text-xs text-muted-foreground">A receber (pend.)</div><div className="font-semibold">{brl(pano.receber_pendente)}</div></div>
              <div><div className="text-xs text-muted-foreground">A pagar (pend.)</div><div className="font-semibold">{brl(pano.pagar_pendente)}</div></div>
              <div><div className="text-xs text-muted-foreground">Clientes · Contratos</div><div className="font-semibold">{kv('CLIENTES') != null ? Number(kv('CLIENTES')) : '?'} · {Number(pano.contratos || 0)}</div></div>
            </div>
            {pano.pendencias && (Number(pano.pendencias.pagar_vencido_valor) > 0 || Number(pano.pendencias.receber_vencido_valor) > 0) && (
              <div className="mt-3 pt-3 border-t flex flex-wrap gap-2 text-xs">
                <span className="font-medium text-gray-600">Ações pendentes:</span>
                {Number(pano.pendencias.pagar_vencido_valor) > 0 && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-red-50 border border-red-200 text-red-700 px-2 py-0.5">
                    <AlertTriangle className="h-3 w-3" /> A pagar vencido: {brl(pano.pendencias.pagar_vencido_valor)} ({Number(pano.pendencias.pagar_vencido_qtd)})
                  </span>
                )}
                {Number(pano.pendencias.receber_vencido_valor) > 0 && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 border border-amber-200 text-amber-700 px-2 py-0.5">
                    <TrendingUp className="h-3 w-3" /> A receber vencido: {brl(pano.pendencias.receber_vencido_valor)} ({Number(pano.pendencias.receber_vencido_qtd)})
                  </span>
                )}
                <span className="text-gray-400">— pergunte ao CFO "o que fazer?"</span>
              </div>
            )}
            {pano.cross_modulo && (
              <div className="mt-3 pt-3 border-t">
                <div className="text-xs font-medium text-gray-600 mb-1.5">Visão cross-módulo (o financeiro enxerga toda a empresa)</div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                  <div><div className="text-xs text-muted-foreground">Pipeline comercial</div><div className="font-semibold text-blue-700">{brl(pano.cross_modulo.pipeline_aberto)}</div><div className="text-[10px] text-gray-400">ponderado {brl(pano.cross_modulo.pipeline_ponderado)}</div></div>
                  <div><div className="text-xs text-muted-foreground">Reembolsos a pagar (DP)</div><div className="font-semibold">{brl(pano.cross_modulo.reembolsos_a_pagar)}</div><div className="text-[10px] text-gray-400">{Number(pano.cross_modulo.reembolsos_qtd || 0)} pedidos</div></div>
                  <div><div className="text-xs text-muted-foreground">Contingência (Jurídico)</div><div className={`font-semibold ${Number(pano.cross_modulo.processos_ativos) > 0 ? 'text-orange-600' : ''}`}>{Number(pano.cross_modulo.processos_ativos || 0)} processo(s)</div><div className="text-[10px] text-gray-400">passivo potencial</div></div>
                  <div><div className="text-xs text-muted-foreground">Pendências fiscais (DET)</div><div className={`font-semibold ${Number(pano.cross_modulo.det_pendencias) > 0 ? 'text-red-600' : ''}`}>{Number(pano.cross_modulo.det_pendencias || 0)}</div><div className="text-[10px] text-gray-400">FGTS/INSS a resolver</div></div>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Previsibilidade de custos mensais */}
      {prev && (
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-base flex items-center gap-2"><TrendingUp className="h-4 w-4 text-emerald-600" /> Previsão de custos mensais</CardTitle></CardHeader>
          <CardContent>
            <div className="divide-y text-sm">
              {(prev.itens || []).map((it: any, i: number) => (
                <div key={i} className="py-1.5 flex items-center justify-between gap-2">
                  <span className="flex-1">{it.categoria}</span>
                  <span className="text-[10px] text-gray-400 hidden md:inline">{it.fonte}</span>
                  <span className={`font-semibold w-28 text-right ${!it.valor ? 'text-gray-300' : ''}`}>{brl(it.valor)}</span>
                  {it.id ? <button onClick={() => removerCusto(it.id)} className="text-gray-300 hover:text-red-600"><X className="h-3.5 w-3.5" /></button> : <span className="w-3.5" />}
                </div>
              ))}
            </div>
            <div className="mt-2">
              {!addCusto ? (
                <button onClick={() => setAddCusto(true)} className="text-xs text-emerald-700 hover:underline">+ Registrar custo (parcelamento / acordo / fixo / tributo)</button>
              ) : (
                <div className="flex flex-wrap items-end gap-2 border rounded p-2 bg-gray-50">
                  <select value={nc.categoria} onChange={e => setNc({ ...nc, categoria: e.target.value })} className="border rounded px-2 py-1 text-xs">
                    <option value="fixo">Custo fixo</option><option value="parcelamento">Parcelamento</option>
                    <option value="acordo">Acordo</option><option value="tributo">Tributo</option><option value="fornecedor">Fornecedor</option>
                  </select>
                  <input value={nc.descricao} onChange={e => setNc({ ...nc, descricao: e.target.value })} placeholder="Descrição (ex.: Aluguel, DARF INSS)" className="border rounded px-2 py-1 text-xs w-48" />
                  <input value={nc.valor} onChange={e => setNc({ ...nc, valor: e.target.value })} type="number" placeholder="Valor/mês" className="border rounded px-2 py-1 text-xs w-24" />
                  {(nc.categoria === 'parcelamento' || nc.categoria === 'acordo') && <>
                    <input value={nc.parcelas_total} onChange={e => setNc({ ...nc, parcelas_total: e.target.value })} type="number" placeholder="parcelas" className="border rounded px-2 py-1 text-xs w-20" />
                    <input value={nc.parcelas_pagas} onChange={e => setNc({ ...nc, parcelas_pagas: e.target.value })} type="number" placeholder="pagas" className="border rounded px-2 py-1 text-xs w-16" />
                  </>}
                  <Button onClick={salvarCusto} className="bg-emerald-600 hover:bg-emerald-700 text-white h-7 text-xs">Salvar</Button>
                  <button onClick={() => setAddCusto(false)} className="text-xs text-gray-400">cancelar</button>
                </div>
              )}
            </div>
            <div className="mt-2 pt-2 border-t flex items-center justify-between text-sm">
              <span className="font-semibold">Custo mensal total previsto</span>
              <span className="font-bold text-lg">{brl(prev.total_custo_mensal)}</span>
            </div>
            <div className="mt-1 grid grid-cols-3 gap-2 text-xs text-center">
              <div><div className="text-muted-foreground">Receita (MRR)</div><div className="font-semibold">{brl(prev.receita_mensal)}</div></div>
              <div><div className="text-muted-foreground">Resultado estimado</div><div className={`font-semibold ${Number(prev.resultado_mensal_estimado) < 0 ? 'text-red-600' : 'text-emerald-700'}`}>{brl(prev.resultado_mensal_estimado)}</div></div>
              <div><div className="text-muted-foreground">Caixa cobre</div><div className="font-semibold">{prev.cobertura_caixa_meses != null ? `${prev.cobertura_caixa_meses} meses` : '—'}</div></div>
            </div>
            <p className="mt-2 text-[10px] text-muted-foreground">{prev.observacao}</p>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base"><Bot className="h-4 w-4 text-emerald-600" /> Pergunte ao CFO</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <label className="text-xs font-medium text-muted-foreground">Lente</label>
                <div className="flex flex-wrap gap-2 mt-1">
                  {AREAS.map((a) => (
                    <button key={a.value} onClick={() => setArea(a.value)}
                      className={`px-3 py-1.5 rounded-md text-sm border transition-colors ${area === a.value ? 'bg-emerald-600 text-white border-emerald-600' : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'}`}>
                      {a.label}
                    </button>
                  ))}
                </div>
              </div>
              <Textarea
                value={pergunta}
                onChange={(e) => setPergunta(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder={arquivo ? 'Pergunta sobre o documento (opcional) — Enter para enviar' : 'Ex.: "Meu caixa cobre a folha deste mês?" · "Qual cliente devo priorizar na cobrança?" (Enter envia)'}
                rows={4}
                disabled={loading}
              />
              {arquivo && (
                <div className="flex items-center gap-2 text-sm bg-emerald-50 border border-emerald-200 rounded px-3 py-1.5">
                  <Paperclip className="h-4 w-4 text-emerald-600" />
                  <span className="flex-1 truncate">{arquivo.name}</span>
                  <button onClick={() => setArquivo(null)} className="text-gray-400 hover:text-gray-700"><X className="h-4 w-4" /></button>
                </div>
              )}
              <div className="flex items-center justify-between gap-2">
                <label className="flex items-center gap-1.5 text-sm text-gray-600 border rounded px-3 py-2 cursor-pointer hover:bg-gray-50">
                  <Paperclip className="h-4 w-4" /> Anexar (PDF/planilha)
                  <input ref={fileRef} type="file" accept=".pdf,.docx,.txt,.csv,.xls,.xlsx" className="hidden"
                    onChange={(e) => setArquivo(e.target.files?.[0] || null)} />
                </label>
                <Button onClick={consultar} disabled={loading || (!pergunta.trim() && !arquivo)} className="bg-emerald-600 hover:bg-emerald-700 text-white">
                  {loading ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Analisando...</> : <><Send className="h-4 w-4 mr-2" /> Perguntar</>}
                </Button>
              </div>
              {loading && <p className="text-xs text-muted-foreground text-center">O CFO está analisando os números — pode levar de 10 a 30 segundos.</p>}
            </CardContent>
          </Card>

          {erro && (
            <Card className="border-red-300 bg-red-50">
              <CardContent className="py-4 text-sm text-red-700 flex items-center gap-2">
                <AlertTriangle className="h-4 w-4" /> {erro}
              </CardContent>
            </Card>
          )}

          {resposta && (
            <Card>
              <CardHeader className="pb-3"><CardTitle className="text-base">Análise do CFO</CardTitle></CardHeader>
              <CardContent className="space-y-4">
                {resposta.escalonar && (
                  <div className="flex items-start gap-2 rounded-md border border-orange-300 bg-orange-50 px-3 py-2 text-sm text-orange-800">
                    <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
                    <span>Decisão sensível — valide com a contabilidade (Domínio/TOTVS) antes de agir.</span>
                  </div>
                )}
                <Markdown text={resposta.resposta} />
                {resposta.disclaimer && <div className="border-t pt-3 text-xs text-muted-foreground italic">{resposta.disclaimer}</div>}
              </CardContent>
            </Card>
          )}
        </div>

        <div>
          <Card>
            <CardHeader className="pb-3"><CardTitle className="flex items-center gap-2 text-base"><History className="h-4 w-4 text-gray-500" /> Últimas análises</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              {historico.length === 0 ? (
                <p className="text-sm text-muted-foreground">Sem consultas registradas.</p>
              ) : (
                historico.map((h: any, i: number) => (
                  <div key={h.id ?? i} className="border rounded-md px-3 py-2 text-sm">
                    <div className="flex items-center justify-between gap-2 mb-1">
                      {h.area && <Badge variant="outline" className="text-xs">{AREAS.find(a => a.value === h.area)?.label || h.area}</Badge>}
                      {h.escalonar && <Badge className="bg-orange-500 text-white text-xs">atenção</Badge>}
                    </div>
                    <div className="text-gray-700 line-clamp-3">{h.pergunta || '—'}</div>
                    {h.created_at && <div className="text-xs text-muted-foreground mt-1">{new Date(h.created_at).toLocaleString('pt-BR')}</div>}
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
