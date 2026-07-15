'use client';

import { useState, useEffect, useRef } from 'react';
import { msgFromDetail } from '@/lib/string';
import {
  Users, Bot, Send, Loader2, AlertTriangle, History, Paperclip, X,
  Wallet, Fingerprint, HeartPulse, Palmtree, UserMinus, ShieldCheck,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';

const API_BASE = '/api/v1/rh/consultor';

function getAuthHeaders(json = true) {
  const token = typeof window !== 'undefined' ? (localStorage.getItem('access_token') || localStorage.getItem('token')) : null;
  return { ...(json ? { 'Content-Type': 'application/json' } : {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) };
}

const AREAS = [
  { value: 'folha', label: 'Folha de Pagamento' },
  { value: 'ponto', label: 'Ponto Eletrônico' },
  { value: 'beneficios_sst', label: 'Benefícios & SST' },
  { value: 'movimentacao', label: 'Movimentação' },
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

function StatCard({ icon: Icon, label, value, sub, tone = 'default' }: {
  icon: any; label: string; value: string; sub?: string; tone?: 'default' | 'alert' | 'ok';
}) {
  const toneCls = tone === 'alert' ? 'text-red-600' : tone === 'ok' ? 'text-indigo-700' : 'text-gray-900';
  return (
    <div className="rounded-lg border bg-white px-4 py-3 flex items-start gap-3">
      <div className="rounded-md bg-indigo-50 p-2 mt-0.5">
        <Icon className="h-4 w-4 text-indigo-600" />
      </div>
      <div className="min-w-0">
        <div className="text-xs text-muted-foreground truncate">{label}</div>
        <div className={`font-semibold text-lg leading-tight ${toneCls}`}>{value}</div>
        {sub && <div className="text-[11px] text-muted-foreground mt-0.5">{sub}</div>}
      </div>
    </div>
  );
}

export default function ConsultorPessoasPage() {
  const [area, setArea] = useState('folha');
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
      if (!r.ok) { const e = await r.json().catch(() => ({})); setErro(msgFromDetail(e?.detail) || `O Consultor de Pessoas não respondeu agora (HTTP ${r.status}).`); return; }
      const data = await r.json();
      if (data?.indisponivel) { setErro('Consultor de Pessoas IA temporariamente indisponível — os números do painel continuam reais.'); if (data?.panorama) setPano(data.panorama); return; }
      setResposta(data);
      if (data?.panorama) setPano(data.panorama);
      carregarHistorico();
    } catch {
      setErro('Falha de comunicação com o Consultor de Pessoas IA. Tente novamente.');
    } finally { setLoading(false); }
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); consultar(); }
  };

  const folha = pano?.folha || {};
  const asos = pano?.asos || {};
  const ponto = pano?.ponto || {};
  const ferias = pano?.ferias || {};
  const resc = pano?.rescisoes || {};

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center gap-3">
        <div className="rounded-lg bg-indigo-600 p-2.5">
          <Users className="h-6 w-6 text-white" />
        </div>
        <div>
          <h1 className="font-display text-2xl font-semibold text-gray-900">Consultor de Pessoas IA</h1>
          <p className="text-sm text-muted-foreground">
            Seu CHRO/DP de bolso — CLT + CCT SINDECOMPRESTS (agentes de portaria), ancorado nos dados reais do ERP.
            Dado trabalhista nunca se inventa. Apoio, não decisão jurídica.
          </p>
        </div>
      </div>

      {/* Painel real (fotografia de pessoas agora) */}
      {pano && (
        <Card className="border-indigo-200">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <ShieldCheck className="h-4 w-4 text-indigo-600" /> Situação de pessoas agora (dados reais)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <StatCard
                icon={Users}
                label="Funcionários ativos"
                value={String(pano.headcount?.ativos ?? '—')}
                sub={pano.cargos_top5?.[0] ? `${pano.cargos_top5[0].cargo}: ${pano.cargos_top5[0].quantidade}` : undefined}
                tone="ok"
              />
              <StatCard
                icon={Wallet}
                label={`Folha líquida ${folha.competencia ? `(${folha.competencia})` : ''}`}
                value={folha.competencia ? brl(folha.liquido_total) : 'sem folha registrada'}
                sub={folha.competencia ? `${folha.holerites} holerites · FGTS ${brl(folha.fgts_total)} · INSS ${brl(folha.inss_total)}` : undefined}
              />
              <StatCard
                icon={HeartPulse}
                label="ASOs vencendo (60d)"
                value={String(asos.vencendo_60d ?? '—')}
                sub={Number(asos.vencidas) > 0 ? `${asos.vencidas} já vencidas — regularizar` : `${asos.total ?? 0} ASOs no total`}
                tone={Number(asos.vencidas) > 0 ? 'alert' : 'default'}
              />
              <StatCard
                icon={Fingerprint}
                label="Batidas de ponto (7d)"
                value={String(ponto.batidas_7d ?? '—')}
                sub={`${ponto.funcionarios_batendo_7d ?? 0} funcionários · ${ponto.batidas_pendentes_revisao ?? 0} pendentes de revisão`}
              />
            </div>

            <div className="mt-3 pt-3 border-t flex flex-wrap gap-2 text-xs">
              <span className="font-medium text-gray-600">Movimentação:</span>
              <span className="inline-flex items-center gap-1 rounded-full bg-indigo-50 border border-indigo-200 text-indigo-700 px-2 py-0.5">
                <Palmtree className="h-3 w-3" /> Férias aguardando aprovação: {Number(ferias.aguardando_aprovacao ?? 0)}
              </span>
              <span className="inline-flex items-center gap-1 rounded-full bg-gray-50 border border-gray-200 text-gray-700 px-2 py-0.5">
                <UserMinus className="h-3 w-3" /> Rescisões (180d): {Number(resc.ultimos_180d ?? 0)}
              </span>
              {Number(ponto.justificativas_pendentes) > 0 && (
                <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 border border-amber-200 text-amber-700 px-2 py-0.5">
                  <AlertTriangle className="h-3 w-3" /> Justificativas de ponto pendentes: {Number(ponto.justificativas_pendentes)}
                </span>
              )}
              <span className="text-gray-400">— pergunte ao consultor &quot;o que priorizar?&quot;</span>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base">
                <Bot className="h-4 w-4 text-indigo-600" /> Pergunte ao Consultor de Pessoas
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <label className="text-xs font-medium text-muted-foreground">Lente</label>
                <div className="flex flex-wrap gap-2 mt-1">
                  {AREAS.map((a) => (
                    <button key={a.value} onClick={() => setArea(a.value)}
                      className={`px-3 py-1.5 rounded-md text-sm border transition-colors ${area === a.value ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'}`}>
                      {a.label}
                    </button>
                  ))}
                </div>
              </div>
              <Textarea
                value={pergunta}
                onChange={(e) => setPergunta(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder={arquivo ? 'Pergunta sobre o documento (opcional) — Enter para enviar' : 'Ex.: "Quais ASOs preciso regularizar primeiro?" · "A folha de junho fecha com o headcount ativo?" (Enter envia)'}
                rows={4}
                disabled={loading}
              />
              {arquivo && (
                <div className="flex items-center gap-2 text-sm bg-indigo-50 border border-indigo-200 rounded px-3 py-1.5">
                  <Paperclip className="h-4 w-4 text-indigo-600" />
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
                <Button onClick={consultar} disabled={loading || (!pergunta.trim() && !arquivo)} className="bg-indigo-600 hover:bg-indigo-700 text-white">
                  {loading ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Analisando...</> : <><Send className="h-4 w-4 mr-2" /> Perguntar</>}
                </Button>
              </div>
              {loading && <p className="text-xs text-muted-foreground text-center">O consultor está analisando os dados de pessoas — pode levar de 10 a 30 segundos.</p>}
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
              <CardHeader className="pb-3"><CardTitle className="text-base">Análise do Consultor de Pessoas</CardTitle></CardHeader>
              <CardContent className="space-y-4">
                {resposta.escalonar && (
                  <div className="flex items-start gap-2 rounded-md border border-orange-300 bg-orange-50 px-3 py-2 text-sm text-orange-800">
                    <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
                    <span>Tema trabalhista sensível — valide com o jurídico/contabilidade antes de qualquer ato formal.</span>
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
