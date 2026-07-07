'use client';

import { useState, useEffect, useRef } from 'react';
import {
  Landmark, FileText, Bot, Send, Loader2, AlertTriangle, History,
  Paperclip, X, ShieldCheck, Receipt, ArrowDownLeft, Package,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';

const API_BASE = '/api/v1/fiscal/consultor';

function getAuthHeaders(json = true) {
  const token = typeof window !== 'undefined' ? (localStorage.getItem('access_token') || localStorage.getItem('token')) : null;
  return { ...(json ? { 'Content-Type': 'application/json' } : {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) };
}

const AREAS = [
  { value: 'notas', label: 'Notas Fiscais' },
  { value: 'apuracao', label: 'Apuração & Tributos' },
  { value: 'certidoes', label: 'Certidões' },
  { value: 'obrigacoes', label: 'Obrigações & Prazos' },
];

const brl = (v: any) => {
  const n = Number(v);
  return isNaN(n) ? '—' : n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
};
const mesLabel = (m: string) => {
  const [y, mm] = String(m || '').split('-');
  const nomes = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];
  const i = Number(mm) - 1;
  return i >= 0 && i < 12 ? `${nomes[i]}/${y}` : m;
};

/** Render leve de Markdown (## títulos, **negrito**, listas, ---). */
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

function StatCard({ icon: Icon, titulo, valor, sub, tone }: { icon: any; titulo: string; valor: string; sub?: string; tone?: 'ok' | 'warn' | 'bad' }) {
  const cor = tone === 'bad' ? 'text-red-600' : tone === 'warn' ? 'text-amber-600' : 'text-gray-900';
  return (
    <Card>
      <CardContent className="pt-4 pb-3">
        <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
          <Icon className="h-3.5 w-3.5 text-indigo-600" /> {titulo}
        </div>
        <div className={`font-semibold text-lg tabular-nums ${cor}`}>{valor}</div>
        {sub && <div className="text-[11px] text-muted-foreground mt-0.5">{sub}</div>}
      </CardContent>
    </Card>
  );
}

export default function ConsultorFiscalPage() {
  const [area, setArea] = useState('notas');
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
      if (!r.ok) { const e = await r.json().catch(() => ({})); setErro(e?.detail || `O Consultor Fiscal não respondeu agora (HTTP ${r.status}).`); return; }
      const data = await r.json();
      if (data?.indisponivel) { setErro('Consultor Fiscal IA temporariamente indisponível — os números do painel continuam reais.'); if (data?.panorama) setPano(data.panorama); return; }
      setResposta(data);
      if (data?.panorama) setPano(data.panorama);
      carregarHistorico();
    } catch {
      setErro('Falha de comunicação com o Consultor Fiscal IA. Tente novamente.');
    } finally { setLoading(false); }
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); consultar(); }
  };

  const rm = pano?.resumo_mes_atual || {};
  const cert = pano?.certidoes || {};
  const obr = pano?.obrigacoes || {};

  // Tabela mensal: junta emitidas + tomadas + NF-e de entrada por mês
  const meses: string[] = Array.from(new Set([
    ...((pano?.emitidas_por_mes as any[]) || []).map((x: any) => x.mes),
    ...((pano?.tomadas_por_mes as any[]) || []).map((x: any) => x.mes),
    ...((pano?.nfe_entradas_por_mes as any[]) || []).map((x: any) => x.mes),
  ])).sort();
  const porMes = (lista: any[], m: string) => (lista || []).find((x: any) => x.mes === m) || {};

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center gap-3">
        <div className="h-11 w-11 rounded-lg bg-indigo-900 flex items-center justify-center">
          <Landmark className="h-6 w-6 text-white" />
        </div>
        <div>
          <h1 className="font-display text-2xl font-semibold text-gray-900">Consultor Fiscal IA</h1>
          <p className="text-sm text-muted-foreground">
            Notas, tributos, certidões e prazos — ancorado nos dados fiscais reais do ERP (Lucro Real desde 01/2026, ISS Manaus 5%). Apoio, não parecer contábil.
          </p>
        </div>
      </div>

      {/* Painel real (fotografia fiscal agora) */}
      {pano && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatCard
              icon={Receipt}
              titulo={`Receita NFS-e (${mesLabel(rm.mes || pano.mes_atual)})`}
              valor={brl(rm.nfse_emitidas_receita)}
              sub={Number(rm.nfse_emitidas_qtd) > 0 ? `${rm.nfse_emitidas_qtd} notas · ISS ${brl(rm.nfse_emitidas_iss)}` : 'aguardando emissão no mês'}
              tone={Number(rm.nfse_emitidas_qtd) === 0 ? 'warn' : undefined}
            />
            <StatCard
              icon={ArrowDownLeft}
              titulo="Serviços tomados (mês)"
              valor={brl(rm.tomadas_valor)}
              sub={`${Number(rm.tomadas_qtd || 0)} notas contra o CNPJ`}
            />
            <StatCard
              icon={Package}
              titulo="NF-e de entrada (mês)"
              valor={brl(rm.nfe_entrada_valor)}
              sub={`${Number(rm.nfe_entrada_qtd || 0)} notas (SEFAZ DFe)`}
            />
            <StatCard
              icon={ShieldCheck}
              titulo="Certidões (CNDs)"
              valor={`${Number(cert.validas || 0)} OK · ${Number(cert.vencendo_30d || 0)} vencendo`}
              sub={Number(cert.vencidas) > 0 ? `${cert.vencidas} vencida(s) — regularizar` : 'nenhuma vencida'}
              tone={Number(cert.vencidas) > 0 ? 'bad' : Number(cert.vencendo_30d) > 0 ? 'warn' : 'ok'}
            />
          </div>

          <Card className="border-indigo-200">
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-base">
                <FileText className="h-4 w-4 text-indigo-600" /> Movimento fiscal {pano.ano} (dados reais — Portal Nacional / SEFAZ)
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-xs text-muted-foreground border-b">
                      <th className="text-left py-1.5 pr-2 font-medium">Mês</th>
                      <th className="text-right py-1.5 px-2 font-medium">NFS-e emitidas</th>
                      <th className="text-right py-1.5 px-2 font-medium">Receita</th>
                      <th className="text-right py-1.5 px-2 font-medium">ISS</th>
                      <th className="text-right py-1.5 px-2 font-medium">Tomadas</th>
                      <th className="text-right py-1.5 pl-2 font-medium">NF-e entrada</th>
                    </tr>
                  </thead>
                  <tbody>
                    {meses.map((m) => {
                      const e = porMes(pano.emitidas_por_mes, m);
                      const t = porMes(pano.tomadas_por_mes, m);
                      const n = porMes(pano.nfe_entradas_por_mes, m);
                      return (
                        <tr key={m} className="border-b last:border-0">
                          <td className="py-1.5 pr-2 font-medium">{mesLabel(m)}</td>
                          <td className="py-1.5 px-2 text-right tabular-nums">{Number(e.qtd || 0)}</td>
                          <td className="py-1.5 px-2 text-right tabular-nums font-semibold">{e.receita != null ? brl(e.receita) : '—'}</td>
                          <td className="py-1.5 px-2 text-right tabular-nums text-gray-500">{e.iss != null ? brl(e.iss) : '—'}</td>
                          <td className="py-1.5 px-2 text-right tabular-nums">{t.valor != null ? brl(t.valor) : '—'}</td>
                          <td className="py-1.5 pl-2 text-right tabular-nums">{n.valor != null ? brl(n.valor) : '—'}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                  <tfoot>
                    <tr className="border-t-2">
                      <td className="py-1.5 pr-2 font-semibold">Total {pano.ano}</td>
                      <td className="py-1.5 px-2 text-right tabular-nums font-semibold">
                        {((pano.emitidas_por_mes as any[]) || []).reduce((s: number, x: any) => s + Number(x.qtd || 0), 0)}
                      </td>
                      <td className="py-1.5 px-2 text-right tabular-nums font-bold">{brl(pano.receita_ano)}</td>
                      <td className="py-1.5 px-2 text-right tabular-nums text-gray-600">{brl(pano.iss_ano)}</td>
                      <td className="py-1.5 px-2 text-right tabular-nums">
                        {brl(((pano.tomadas_por_mes as any[]) || []).reduce((s: number, x: any) => s + Number(x.valor || 0), 0))}
                      </td>
                      <td className="py-1.5 pl-2 text-right tabular-nums">
                        {brl(((pano.nfe_entradas_por_mes as any[]) || []).reduce((s: number, x: any) => s + Number(x.valor || 0), 0))}
                      </td>
                    </tr>
                  </tfoot>
                </table>
              </div>

              {(Number(obr.vencidas) > 0 || Number(cert.vencidas) > 0) && (
                <div className="mt-3 pt-3 border-t flex flex-wrap gap-2 text-xs">
                  <span className="font-medium text-gray-600">Pendências fiscais:</span>
                  {Number(obr.vencidas) > 0 && (
                    <span className="inline-flex items-center gap-1 rounded-full bg-red-50 border border-red-200 text-red-700 px-2 py-0.5">
                      <AlertTriangle className="h-3 w-3" /> {obr.vencidas} obrigação(ões) vencida(s) de {obr.pendentes} pendentes
                    </span>
                  )}
                  {Number(cert.vencidas) > 0 && (
                    <span className="inline-flex items-center gap-1 rounded-full bg-red-50 border border-red-200 text-red-700 px-2 py-0.5">
                      <ShieldCheck className="h-3 w-3" /> {cert.vencidas} certidão(ões) vencida(s)
                    </span>
                  )}
                  <span className="text-gray-400">— pergunte ao consultor "por onde começo a regularizar?"</span>
                </div>
              )}

              {(pano.historico_manaus as any[])?.length > 0 && (
                <div className="mt-3 pt-3 border-t">
                  <div className="text-xs font-medium text-gray-600 mb-1.5">Histórico municipal Manaus (2019-2025 — antes do Portal Nacional)</div>
                  <div className="flex flex-wrap gap-2">
                    {(pano.historico_manaus as any[]).map((h: any) => (
                      <div key={h.ano} className="rounded border px-2 py-1 text-xs bg-gray-50">
                        <span className="font-semibold">{h.ano}</span>
                        <span className="text-gray-500"> · {h.qtd} notas · </span>
                        <span className="tabular-nums">{brl(h.receita)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base"><Bot className="h-4 w-4 text-indigo-600" /> Pergunte ao Consultor Fiscal</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <label className="text-xs font-medium text-muted-foreground">Lente</label>
                <div className="flex flex-wrap gap-2 mt-1">
                  {AREAS.map((a) => (
                    <button key={a.value} onClick={() => setArea(a.value)}
                      className={`px-3 py-1.5 rounded-md text-sm border transition-colors ${area === a.value ? 'bg-indigo-700 text-white border-indigo-700' : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'}`}>
                      {a.label}
                    </button>
                  ))}
                </div>
              </div>
              <Textarea
                value={pergunta}
                onChange={(e) => setPergunta(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder={arquivo ? 'Pergunta sobre o documento (opcional) — Enter para enviar' : 'Ex.: "Quanto de ISS recolho sobre junho?" · "Quais certidões preciso renovar antes da próxima licitação?" (Enter envia)'}
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
                  <Paperclip className="h-4 w-4" /> Anexar (guia/nota/planilha)
                  <input ref={fileRef} type="file" accept=".pdf,.docx,.txt,.csv,.xls,.xlsx" className="hidden"
                    onChange={(e) => setArquivo(e.target.files?.[0] || null)} />
                </label>
                <Button onClick={consultar} disabled={loading || (!pergunta.trim() && !arquivo)} className="bg-indigo-700 hover:bg-indigo-800 text-white">
                  {loading ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Analisando...</> : <><Send className="h-4 w-4 mr-2" /> Perguntar</>}
                </Button>
              </div>
              {loading && <p className="text-xs text-muted-foreground text-center">O consultor está cruzando notas, certidões e prazos — pode levar de 10 a 30 segundos.</p>}
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
              <CardHeader className="pb-3"><CardTitle className="text-base">Análise do Consultor Fiscal</CardTitle></CardHeader>
              <CardContent className="space-y-4">
                {resposta.escalonar && (
                  <div className="flex items-start gap-2 rounded-md border border-orange-300 bg-orange-50 px-3 py-2 text-sm text-orange-800">
                    <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
                    <span>Tema sensível — valide com a contabilidade (Portte) antes de recolher ou transmitir.</span>
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
