'use client';

import { useState, useEffect, useRef } from 'react';
import { msgFromDetail } from '@/lib/string';
import {
  TrendingUp, Bot, Send, Loader2, AlertTriangle, History, Paperclip, X,
  Users, Target, FileCheck, Landmark,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { PageHeader } from '@/components/ui/page-header';
import { StatCard } from '@/components/ui/stat-card';

const API_BASE = '/api/v1/comercial/consultor';

function getAuthHeaders(json = true) {
  const token = typeof window !== 'undefined' ? (localStorage.getItem('access_token') || localStorage.getItem('token')) : null;
  return { ...(json ? { 'Content-Type': 'application/json' } : {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) };
}

const AREAS = [
  { value: 'pipeline', label: 'Pipeline / Funil' },
  { value: 'propostas', label: 'Propostas' },
  { value: 'clientes', label: 'Clientes / Cross-sell' },
  { value: 'estrategia', label: 'Estratégia' },
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
      : p.startsWith('`') && p.endsWith('`') ? <code key={i} className="bg-[hsl(var(--muted))] px-1 rounded text-[13px]">{p.slice(1, -1)}</code>
      : <span key={i}>{p}</span>
    );
  };
  const lines = (text || '').split('\n');
  const out: any[] = [];
  let list: any[] = [];
  const flush = () => { if (list.length) { out.push(<ul key={`u${out.length}`} className="list-disc ml-5 my-1 space-y-0.5">{list}</ul>); list = []; } };
  lines.forEach((raw, i) => {
    const l = raw.trimEnd();
    if (/^#{1,4}\s/.test(l)) { flush(); const t = l.replace(/^#{1,4}\s/, ''); out.push(<h3 key={i} className="font-display font-semibold text-brand-500 mt-3 mb-1">{inline(t, i)}</h3>); }
    else if (/^(\s*[-*•]\s+)/.test(l)) { list.push(<li key={i}>{inline(l.replace(/^\s*[-*•]\s+/, ''), i)}</li>); }
    else if (/^\s*\d+[.)]\s+/.test(l)) { list.push(<li key={i}>{inline(l.replace(/^\s*\d+[.)]\s+/, ''), i)}</li>); }
    else if (/^\s*---+\s*$/.test(l)) { flush(); out.push(<hr key={i} className="my-2 border-[hsl(var(--border))]" />); }
    else if (l.trim() === '') { flush(); }
    else { flush(); out.push(<p key={i} className="my-1 leading-relaxed">{inline(l, i)}</p>); }
  });
  flush();
  return <div className="text-sm text-[hsl(var(--foreground))]">{out}</div>;
}

export default function ConsultorComercialPage() {
  const [area, setArea] = useState('pipeline');
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
      if (!r.ok) { const e = await r.json().catch(() => ({})); setErro(msgFromDetail(e?.detail) || `O consultor não respondeu agora (HTTP ${r.status}).`); return; }
      const data = await r.json();
      if (data?.indisponivel) { setErro('Consultor Comercial IA temporariamente indisponível — os números do painel continuam reais.'); if (data?.panorama) setPano(data.panorama); return; }
      setResposta(data);
      if (data?.panorama) setPano(data.panorama);
      carregarHistorico();
    } catch {
      setErro('Falha de comunicação com o Consultor Comercial IA. Tente novamente.');
    } finally { setLoading(false); }
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); consultar(); }
  };

  const estagios = (pano?.pipeline?.por_estagio as any[]) || [];

  return (
    <div className="p-6 space-y-6">
      <PageHeader
        eyebrow="COMERCIAL · CONSULTOR IA"
        title="Consultor Comercial IA"
        subtitle="Seu CMO de bolso — funil, conversão, MRR e cross-sell ancorados nos dados reais do CRM. Apoio, não decisão comercial."
        icon={<TrendingUp className="w-5 h-5" />}
      />

      {/* Painel real (fotografia comercial agora) */}
      {pano && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <Target className="h-4 w-4 text-brand-500" /> Situação comercial agora (dados reais)
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 grid-cols-2 lg:grid-cols-4">
              <StatCard
                icon={<Landmark className="w-4 h-4" />}
                color="#16a34a"
                label="MRR contratado"
                value={brl(pano.contratos?.mrr)}
                sub={`${Number(pano.contratos?.ativos || 0)} contratos ativos`}
              />
              <StatCard
                icon={<Target className="w-4 h-4" />}
                color="#2563eb"
                label="Pipeline aberto"
                value={brl(pano.pipeline?.aberto_valor)}
                sub={`${Number(pano.pipeline?.aberto_qtd || 0)} oportunidades`}
              />
              <StatCard
                icon={<Users className="w-4 h-4" />}
                color="#f97707"
                label="Leads novos (30d)"
                value={Number(pano.leads?.novos_30d || 0)}
                sub={`${Number(pano.leads?.total || 0)} leads na base`}
              />
              <StatCard
                icon={<FileCheck className="w-4 h-4" />}
                color="#9333ea"
                label="Propostas aceitas (90d)"
                value={Number(pano.propostas?.aceitas_90d || 0)}
                sub={`${Number(pano.propostas?.enviadas_90d || 0)} enviadas em 90d`}
              />
            </div>

            {estagios.length > 0 && (
              <div className="pt-3 border-t border-[hsl(var(--border))]">
                <div className="font-data text-[10px] uppercase tracking-[0.18em] text-[hsl(var(--muted-foreground))]/70 mb-2">
                  Funil aberto por estágio
                </div>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-[hsl(var(--muted-foreground))]">
                      <th className="py-1 font-medium">Estágio</th>
                      <th className="py-1 font-medium text-right">Oportunidades</th>
                      <th className="py-1 font-medium text-right">Valor</th>
                    </tr>
                  </thead>
                  <tbody>
                    {estagios.map((e: any) => (
                      <tr key={e.estagio} className="border-t border-[hsl(var(--border))]">
                        <td className="py-1.5">{e.rotulo || e.estagio}</td>
                        <td className="py-1.5 text-right font-data tabular-nums">{Number(e.qtd || 0)}</td>
                        <td className="py-1.5 text-right font-data tabular-nums">{brl(e.valor)}</td>
                      </tr>
                    ))}
                    <tr className="border-t border-[hsl(var(--border))] font-semibold">
                      <td className="py-1.5">Total aberto</td>
                      <td className="py-1.5 text-right font-data tabular-nums">{Number(pano.pipeline?.aberto_qtd || 0)}</td>
                      <td className="py-1.5 text-right font-data tabular-nums">{brl(pano.pipeline?.aberto_valor)}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            )}

            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-[hsl(var(--muted-foreground))]">
              <span>Clientes ativos: <span className="font-data">{Number(pano.clientes_ativos || 0)}</span></span>
              {pano.ticket_medio_mrr != null && <span>Ticket médio (MRR/contrato): <span className="font-data">{brl(pano.ticket_medio_mrr)}</span></span>}
              {pano.pipeline?.ganhas_90d && <span>Ganhas 90d: <span className="font-data">{Number(pano.pipeline.ganhas_90d.qtd || 0)} · {brl(pano.pipeline.ganhas_90d.valor)}</span></span>}
              {pano.nps && !pano.nps.disponivel && <span className="opacity-70">NPS: aguardando dado ({pano.nps.fonte})</span>}
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base"><Bot className="h-4 w-4 text-brand-500" /> Pergunte ao CMO</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <label className="font-data text-[10px] uppercase tracking-[0.18em] text-[hsl(var(--muted-foreground))]/70">Lente</label>
                <div className="flex flex-wrap gap-2 mt-1">
                  {AREAS.map((a) => (
                    <button key={a.value} onClick={() => setArea(a.value)}
                      className={`px-3 py-1.5 rounded-md text-sm border transition-colors ${area === a.value
                        ? 'bg-brand-500 text-white border-brand-500'
                        : 'bg-[hsl(var(--card))] text-[hsl(var(--foreground))] border-[hsl(var(--border))] hover:bg-[hsl(var(--muted))]'}`}>
                      {a.label}
                    </button>
                  ))}
                </div>
              </div>
              <Textarea
                value={pergunta}
                onChange={(e) => setPergunta(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder={arquivo ? 'Pergunta sobre o documento (opcional) — Enter para enviar' : 'Ex.: "Onde está o gargalo do funil?" · "Qual cliente tem espaço para cross-sell?" (Enter envia)'}
                rows={4}
                disabled={loading}
              />
              {arquivo && (
                <div className="flex items-center gap-2 text-sm bg-brand-500/10 border border-brand-500/30 rounded px-3 py-1.5">
                  <Paperclip className="h-4 w-4 text-brand-500" />
                  <span className="flex-1 truncate">{arquivo.name}</span>
                  <button onClick={() => setArquivo(null)} className="text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))]"><X className="h-4 w-4" /></button>
                </div>
              )}
              <div className="flex items-center justify-between gap-2">
                <label className="flex items-center gap-1.5 text-sm text-[hsl(var(--muted-foreground))] border border-[hsl(var(--border))] rounded px-3 py-2 cursor-pointer hover:bg-[hsl(var(--muted))]">
                  <Paperclip className="h-4 w-4" /> Anexar (PDF/planilha)
                  <input ref={fileRef} type="file" accept=".pdf,.docx,.txt,.csv,.xls,.xlsx" className="hidden"
                    onChange={(e) => setArquivo(e.target.files?.[0] || null)} />
                </label>
                <Button onClick={consultar} disabled={loading || (!pergunta.trim() && !arquivo)}>
                  {loading ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Analisando...</> : <><Send className="h-4 w-4 mr-2" /> Perguntar</>}
                </Button>
              </div>
              {loading && <p className="text-xs text-[hsl(var(--muted-foreground))] text-center">O CMO está analisando o funil — pode levar de 10 a 30 segundos.</p>}
            </CardContent>
          </Card>

          {erro && (
            <Card className="border-red-500/40 bg-red-500/5">
              <CardContent className="py-4 text-sm text-red-500 flex items-center gap-2">
                <AlertTriangle className="h-4 w-4" /> {erro}
              </CardContent>
            </Card>
          )}

          {resposta && (
            <Card>
              <CardHeader className="pb-3"><CardTitle className="font-display text-base">Análise do CMO</CardTitle></CardHeader>
              <CardContent className="space-y-4">
                {resposta.escalonar && (
                  <div className="flex items-start gap-2 rounded-md border border-orange-500/40 bg-orange-500/10 px-3 py-2 text-sm text-orange-500">
                    <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
                    <span>Decisão comercial sensível — valide com o gestor antes de agir (desconto, cancelamento, reajuste, cláusula).</span>
                  </div>
                )}
                <Markdown text={resposta.resposta} />
                {resposta.disclaimer && <div className="border-t border-[hsl(var(--border))] pt-3 text-xs text-[hsl(var(--muted-foreground))] italic">{resposta.disclaimer}</div>}
              </CardContent>
            </Card>
          )}
        </div>

        <div>
          <Card>
            <CardHeader className="pb-3"><CardTitle className="flex items-center gap-2 text-base"><History className="h-4 w-4 text-[hsl(var(--muted-foreground))]" /> Últimas análises</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              {historico.length === 0 ? (
                <p className="text-sm text-[hsl(var(--muted-foreground))]">Sem consultas registradas.</p>
              ) : (
                historico.map((h: any, i: number) => (
                  <div key={h.id ?? i} className="border border-[hsl(var(--border))] rounded-md px-3 py-2 text-sm">
                    <div className="flex items-center justify-between gap-2 mb-1">
                      {h.area && <Badge variant="outline" className="text-xs">{AREAS.find(a => a.value === h.area)?.label || h.area}</Badge>}
                      {h.escalonar && <Badge className="bg-orange-500 text-white text-xs">atenção</Badge>}
                    </div>
                    <div className="text-[hsl(var(--foreground))] line-clamp-3">{h.pergunta || '—'}</div>
                    {h.created_at && <div className="text-xs text-[hsl(var(--muted-foreground))] mt-1">{new Date(h.created_at).toLocaleString('pt-BR')}</div>}
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
