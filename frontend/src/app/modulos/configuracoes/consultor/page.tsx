'use client';

import { useState, useEffect, useRef } from 'react';
import { msgFromDetail } from '@/lib/string';
import {
  Crown, Bot, Send, Loader2, AlertTriangle, History, Paperclip, X,
  TrendingUp, TrendingDown, Minus, Users, Wallet, Briefcase, BarChart3, Scale, FolderOpen,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';

const API_BASE = '/api/v1/gestao/consultor';

function getAuthHeaders(json = true) {
  const token = typeof window !== 'undefined' ? (localStorage.getItem('access_token') || localStorage.getItem('token')) : null;
  return { ...(json ? { 'Content-Type': 'application/json' } : {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) };
}

const AREAS = [
  { value: 'visao_geral', label: 'Visão Geral' },
  { value: 'riscos', label: 'Riscos' },
  { value: 'crescimento', label: 'Crescimento' },
  { value: 'prioridades', label: 'Prioridades' },
];

const brl = (v: any) => {
  const n = Number(v);
  return isNaN(n) ? '—' : n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
};

const fmtKpi = (k: any) => {
  if (k?.valor == null) return '—';
  const n = Number(k.valor);
  if (k.unidade === 'BRL') return brl(n);
  if (k.unidade === '%') return `${n.toLocaleString('pt-BR', { maximumFractionDigits: 1 })}%`;
  return `${n.toLocaleString('pt-BR', { maximumFractionDigits: 1 })}${k.unidade ? ` ${k.unidade}` : ''}`;
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
    if (/^#{1,4}\s/.test(l)) { flush(); const t = l.replace(/^#{1,4}\s/, ''); out.push(<h3 key={i} className="font-semibold text-indigo-900 mt-3 mb-1">{inline(t, i)}</h3>); }
    else if (/^(\s*[-*•]\s+)/.test(l)) { list.push(<li key={i}>{inline(l.replace(/^\s*[-*•]\s+/, ''), i)}</li>); }
    else if (/^\s*\d+[.)]\s+/.test(l)) { list.push(<li key={i}>{inline(l.replace(/^\s*\d+[.)]\s+/, ''), i)}</li>); }
    else if (/^\s*---+\s*$/.test(l)) { flush(); out.push(<hr key={i} className="my-2 border-gray-200" />); }
    else if (l.trim() === '') { flush(); }
    else { flush(); out.push(<p key={i} className="my-1 leading-relaxed">{inline(l, i)}</p>); }
  });
  flush();
  return <div className="text-sm text-gray-800">{out}</div>;
}

function Trend({ t }: { t: string | null | undefined }) {
  const v = String(t || '').toLowerCase();
  if (v.includes('up') || v.includes('alta') || v.includes('cresc')) return <TrendingUp className="h-3.5 w-3.5 text-emerald-600" />;
  if (v.includes('down') || v.includes('baixa') || v.includes('qued')) return <TrendingDown className="h-3.5 w-3.5 text-red-600" />;
  return <Minus className="h-3.5 w-3.5 text-gray-300" />;
}

function StatCard({ icon: Icon, label, value, sub, tone }: { icon: any; label: string; value: string; sub?: string; tone?: string }) {
  return (
    <Card className="border-gray-200">
      <CardContent className="pt-4 pb-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="text-xs text-muted-foreground">{label}</div>
            <div className={`text-lg font-semibold truncate ${tone || 'text-gray-900'}`}>{value}</div>
            {sub && <div className="text-[11px] text-gray-400 mt-0.5">{sub}</div>}
          </div>
          <div className="rounded-md bg-indigo-50 p-2 shrink-0"><Icon className="h-4 w-4 text-indigo-700" /></div>
        </div>
      </CardContent>
    </Card>
  );
}

export default function ConsultorExecutivoPage() {
  const [area, setArea] = useState('visao_geral');
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
  useEffect(() => { carregarHistorico(); carregarPanorama(); }, []);

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
      if (!r.ok) { const e = await r.json().catch(() => ({})); setErro(msgFromDetail(e?.detail) || `O Consultor Executivo não respondeu agora (HTTP ${r.status}).`); return; }
      const data = await r.json();
      if (data?.indisponivel) { setErro('Consultor Executivo temporariamente indisponível — os números do painel continuam reais.'); if (data?.panorama) setPano(data.panorama); return; }
      setResposta(data);
      if (data?.panorama) setPano(data.panorama);
      carregarHistorico();
    } catch {
      setErro('Falha de comunicação com o Consultor Executivo. Tente novamente.');
    } finally { setLoading(false); }
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); consultar(); }
  };

  const kpis: any[] = Array.isArray(pano?.kpis) ? pano.kpis : [];
  const contratos = typeof pano?.contratos === 'object' ? pano.contratos : null;
  const folha = typeof pano?.folha_ultima === 'object' && pano?.folha_ultima ? pano.folha_ultima : null;
  const comercial = typeof pano?.comercial === 'object' ? pano.comercial : null;
  const vencidos = typeof pano?.vencidos === 'object' ? pano.vencidos : null;
  const juridico = typeof pano?.juridico === 'object' ? pano.juridico : null;
  const ged = typeof pano?.ged_intercorrencias === 'object' ? pano.ged_intercorrencias : null;
  const nfse = typeof pano?.nfse_mes_corrente === 'object' ? pano.nfse_mes_corrente : null;

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="rounded-lg bg-indigo-900 p-2.5"><Crown className="h-6 w-6 text-amber-400" /></div>
        <div>
          <h1 className="font-display text-2xl font-semibold text-gray-900">Consultor Executivo IA</h1>
          <p className="text-sm text-muted-foreground">
            Conselheiro do CEO — visão cross-módulo ancorada nos dados reais do ERP (comercial, pessoas, financeiro, fiscal, jurídico e GED). Apoio à decisão, não decisão.
          </p>
        </div>
      </div>

      {/* StatCards executivos */}
      {pano && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatCard icon={Wallet} label="MRR contratado" value={contratos ? brl(contratos.mrr) : 'indisponível'} sub={contratos ? `${contratos.ativos} contratos ativos` : undefined} />
          <StatCard icon={Briefcase} label={`Folha líquida${folha ? ` (${folha.competencia})` : ''}`} value={folha ? brl(folha.liquido) : 'sem competência'} sub={folha ? `${folha.holerites} holerites` : undefined} />
          <StatCard icon={Users} label="Funcionários ativos" value={typeof pano.funcionarios_ativos === 'number' ? String(pano.funcionarios_ativos) : 'indisponível'} sub={nfse ? `NFS-e ${nfse.competencia}: ${nfse.qtd} (${brl(nfse.valor_servicos)})` : undefined} />
          <StatCard icon={BarChart3} label="Pipeline comercial" value={comercial ? brl(comercial.pipeline_valor) : 'indisponível'} sub={comercial ? `${comercial.oportunidades_abertas} oportunidades · ${comercial.leads_abertos} leads abertos` : undefined} />
        </div>
      )}

      {/* Alertas transversais (vencidos, jurídico, GED) */}
      {pano && (vencidos || juridico || ged) && (
        <div className="flex flex-wrap gap-2 text-xs">
          {vencidos && Number(vencidos.receber?.valor) > 0 && (
            <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 border border-amber-200 text-amber-800 px-2.5 py-1">
              <AlertTriangle className="h-3 w-3" /> A receber vencido: {brl(vencidos.receber.valor)} ({vencidos.receber.qtd} títulos)
            </span>
          )}
          {vencidos && Number(vencidos.pagar?.valor) > 0 && (
            <span className="inline-flex items-center gap-1 rounded-full bg-red-50 border border-red-200 text-red-700 px-2.5 py-1">
              <AlertTriangle className="h-3 w-3" /> A pagar vencido: {brl(vencidos.pagar.valor)} ({vencidos.pagar.qtd} títulos)
            </span>
          )}
          {juridico && Number(juridico.processos_abertos) > 0 && (
            <span className="inline-flex items-center gap-1 rounded-full bg-orange-50 border border-orange-200 text-orange-800 px-2.5 py-1">
              <Scale className="h-3 w-3" /> Jurídico: {juridico.processos_abertos} processo(s) em aberto
            </span>
          )}
          {ged && Number(ged.abertas) > 0 && (
            <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 border border-blue-200 text-blue-800 px-2.5 py-1">
              <FolderOpen className="h-3 w-3" /> GED: {ged.abertas} intercorrência(s) aberta(s)
            </span>
          )}
        </div>
      )}

      {/* Tabela dos KPIs executivos */}
      {kpis.length > 0 && (
        <Card className="border-indigo-100">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <BarChart3 className="h-4 w-4 text-indigo-700" /> KPIs executivos (dados reais)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-muted-foreground border-b">
                    <th className="py-1.5 pr-3 font-medium">Indicador</th>
                    <th className="py-1.5 pr-3 font-medium text-right">Valor</th>
                    <th className="py-1.5 pr-3 font-medium text-right hidden md:table-cell">Anterior</th>
                    <th className="py-1.5 font-medium text-center w-16">Tendência</th>
                  </tr>
                </thead>
                <tbody>
                  {kpis.map((k: any) => (
                    <tr key={k.code} className="border-b last:border-0">
                      <td className="py-1.5 pr-3">
                        <span className="font-medium text-gray-800">{k.nome}</span>
                        <span className="ml-1.5 text-[10px] text-gray-400">{k.code}</span>
                      </td>
                      <td className="py-1.5 pr-3 text-right font-semibold">{fmtKpi(k)}</td>
                      <td className="py-1.5 pr-3 text-right text-gray-500 hidden md:table-cell">{k.anterior != null ? fmtKpi({ ...k, valor: k.anterior }) : '—'}</td>
                      <td className="py-1.5 text-center"><span className="inline-flex justify-center"><Trend t={k.tendencia} /></span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {pano?.fonte && <p className="mt-2 text-[10px] text-muted-foreground">{pano.fonte}</p>}
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base"><Bot className="h-4 w-4 text-indigo-700" /> Pergunte ao Consultor Executivo</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <label className="text-xs font-medium text-muted-foreground">Lente</label>
                <div className="flex flex-wrap gap-2 mt-1">
                  {AREAS.map((a) => (
                    <button key={a.value} onClick={() => setArea(a.value)}
                      className={`px-3 py-1.5 rounded-md text-sm border transition-colors ${area === a.value ? 'bg-indigo-800 text-white border-indigo-800' : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'}`}>
                      {a.label}
                    </button>
                  ))}
                </div>
              </div>
              <Textarea
                value={pergunta}
                onChange={(e) => setPergunta(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder={arquivo ? 'Pergunta sobre o documento (opcional) — Enter para enviar' : 'Ex.: "Qual o estado da empresa hoje?" · "Quais os 3 maiores riscos agora?" · "O que priorizo esta semana?" (Enter envia)'}
                rows={4}
                disabled={loading}
              />
              {arquivo && (
                <div className="flex items-center gap-2 text-sm bg-indigo-50 border border-indigo-200 rounded px-3 py-1.5">
                  <Paperclip className="h-4 w-4 text-indigo-700" />
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
                <Button onClick={consultar} disabled={loading || (!pergunta.trim() && !arquivo)} className="bg-indigo-800 hover:bg-indigo-900 text-white">
                  {loading ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Analisando...</> : <><Send className="h-4 w-4 mr-2" /> Perguntar</>}
                </Button>
              </div>
              {loading && <p className="text-xs text-muted-foreground text-center">O Consultor Executivo está cruzando os módulos — pode levar de 10 a 30 segundos.</p>}
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
              <CardHeader className="pb-3"><CardTitle className="text-base">Leitura executiva</CardTitle></CardHeader>
              <CardContent className="space-y-4">
                {resposta.escalonar && (
                  <div className="flex items-start gap-2 rounded-md border border-orange-300 bg-orange-50 px-3 py-2 text-sm text-orange-800">
                    <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
                    <span>Decisão sensível — valide com contabilidade e jurídico antes de agir.</span>
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
