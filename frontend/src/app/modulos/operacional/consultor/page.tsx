'use client';

import { useState, useEffect, useRef } from 'react';
import { msgFromDetail } from '@/lib/string';
import { Shield, Bot, Send, Loader2, AlertTriangle, History, Paperclip, X, MapPin, Users } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';

const API_BASE = '/api/v1/operacional/consultor';

function getAuthHeaders(json = true) {
  const token = typeof window !== 'undefined' ? (localStorage.getItem('access_token') || localStorage.getItem('token')) : null;
  return { ...(json ? { 'Content-Type': 'application/json' } : {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) };
}

const AREAS = [
  { value: 'postos', label: 'Postos & Cobertura' },
  { value: 'alocacoes', label: 'Alocações & Escalas' },
  { value: 'diaristas', label: 'Diaristas' },
  { value: 'ocorrencias', label: 'Ocorrências' },
];

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
    if (/^#{1,4}\s/.test(l)) { flush(); const t = l.replace(/^#{1,4}\s/, ''); out.push(<h3 key={i} className="font-semibold text-sky-800 mt-3 mb-1">{inline(t, i)}</h3>); }
    else if (/^(\s*[-*•]\s+)/.test(l)) { list.push(<li key={i}>{inline(l.replace(/^\s*[-*•]\s+/, ''), i)}</li>); }
    else if (/^\s*\d+[.)]\s+/.test(l)) { list.push(<li key={i}>{inline(l.replace(/^\s*\d+[.)]\s+/, ''), i)}</li>); }
    else if (/^\s*---+\s*$/.test(l)) { flush(); out.push(<hr key={i} className="my-2 border-gray-200" />); }
    else if (l.trim() === '') { flush(); }
    else { flush(); out.push(<p key={i} className="my-1 leading-relaxed">{inline(l, i)}</p>); }
  });
  flush();
  return <div className="text-sm text-gray-800">{out}</div>;
}

export default function ConsultorOperacionalPage() {
  const [area, setArea] = useState('postos');
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
      if (!r.ok) { const e = await r.json().catch(() => ({})); setErro(msgFromDetail(e?.detail) || `O Consultor Operacional não respondeu agora (HTTP ${r.status}).`); return; }
      const data = await r.json();
      if (data?.indisponivel) { setErro('Consultor Operacional IA temporariamente indisponível — os números do painel continuam reais.'); if (data?.panorama) setPano(data.panorama); return; }
      setResposta(data);
      if (data?.panorama) setPano(data.panorama);
      carregarHistorico();
    } catch {
      setErro('Falha de comunicação com o Consultor Operacional IA. Tente novamente.');
    } finally { setLoading(false); }
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); consultar(); }
  };

  const cob = pano?.cobertura || {};

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center gap-3">
        <Shield className="h-7 w-7 text-sky-700" />
        <div>
          <h1 className="font-display text-2xl font-semibold text-gray-900">Consultor Operacional IA</h1>
          <p className="text-sm text-muted-foreground">Seu COO de bolso — cobertura de postos, escalas 12x36, diaristas e ocorrências, ancorado nos dados reais do ERP. Apoio, não decisão de campo.</p>
        </div>
      </div>

      {/* Painel real (fotografia operacional agora) */}
      {pano && (
        <Card className="border-sky-200">
          <CardHeader className="pb-2"><CardTitle className="flex items-center gap-2 text-base"><MapPin className="h-4 w-4 text-sky-600" /> Situação operacional agora (dados reais)</CardTitle></CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
              <div>
                <div className="text-xs text-muted-foreground">Postos ativos</div>
                <div className="font-semibold">{Number(pano.postos?.ativos ?? 0)} <span className="text-xs text-gray-400 font-normal">de {Number(pano.postos?.total ?? 0)}</span></div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Alocações ativas</div>
                <div className="font-semibold">{Number(pano.alocacoes_ativas ?? 0)}</div>
                <div className="text-[10px] text-gray-400">{Number(pano.funcionarios?.ativos ?? 0)} funcionários ativos</div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Diaristas ativos</div>
                <div className="font-semibold">{Number(pano.diaristas?.ativos ?? 0)} <span className="text-xs text-gray-400 font-normal">de {Number(pano.diaristas?.total ?? 0)}</span></div>
                <div className="text-[10px] text-gray-400">{Number(pano.vinculos_diaristas_ativos ?? 0)} vínculos ativos</div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Cobertura de postos</div>
                <div className={`font-semibold ${cob.percentual != null && cob.percentual < 100 ? 'text-amber-600' : 'text-sky-700'}`}>
                  {cob.percentual != null ? `${cob.percentual}%` : '—'}
                </div>
                <div className="text-[10px] text-gray-400">{Number(cob.postos_cobertos ?? 0)}/{Number(cob.postos_ativos ?? 0)} postos com alocação</div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Escalas vigentes hoje</div>
                <div className={`font-semibold ${Number(pano.escalas?.vigentes_hoje ?? 0) === 0 ? 'text-amber-600' : ''}`}>{Number(pano.escalas?.vigentes_hoje ?? 0)}</div>
                <div className="text-[10px] text-gray-400">{Number(pano.escalas?.rascunhos ?? 0)} em rascunho</div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Ocorrências abertas</div>
                <div className={`font-semibold ${Number(pano.ocorrencias?.abertas ?? 0) > 0 ? 'text-red-600' : ''}`}>{Number(pano.ocorrencias?.abertas ?? 0)}</div>
                <div className="text-[10px] text-gray-400">{Number(pano.ocorrencias?.total ?? 0) === 0 ? 'nenhum registro (ponto cego)' : `${Number(pano.ocorrencias?.total ?? 0)} registradas`}</div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Afastados (INSS)</div>
                <div className="font-semibold">{Number(pano.funcionarios?.afastados_inss ?? 0)}</div>
              </div>
            </div>

            {Array.isArray(cob.postos_descobertos) && cob.postos_descobertos.length > 0 && (
              <div className="mt-3 pt-3 border-t flex flex-wrap gap-2 text-xs">
                <span className="font-medium text-gray-600">Postos descobertos:</span>
                {cob.postos_descobertos.map((p: string, i: number) => (
                  <span key={i} className="inline-flex items-center gap-1 rounded-full bg-red-50 border border-red-200 text-red-700 px-2 py-0.5">
                    <AlertTriangle className="h-3 w-3" /> {p}
                  </span>
                ))}
                <span className="text-gray-400">— pergunte ao COO "como cobrir?"</span>
              </div>
            )}

            {Array.isArray(pano.postos_alocados) && pano.postos_alocados.length > 0 && (
              <div className="mt-3 pt-3 border-t">
                <div className="text-xs font-medium text-gray-600 mb-1.5 flex items-center gap-1"><Users className="h-3.5 w-3.5" /> Postos ativos × efetivo alocado</div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-xs text-muted-foreground border-b">
                        <th className="py-1.5 pr-2 font-medium">Posto</th>
                        <th className="py-1.5 pr-2 font-medium text-right">Requerido</th>
                        <th className="py-1.5 pr-2 font-medium text-right">Alocados</th>
                        <th className="py-1.5 font-medium text-right">Situação</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {pano.postos_alocados.map((p: any, i: number) => (
                        <tr key={i}>
                          <td className="py-1.5 pr-2">{p.posto}</td>
                          <td className="py-1.5 pr-2 text-right">{Number(p.efetivo_requerido ?? 0)}</td>
                          <td className="py-1.5 pr-2 text-right font-semibold">{Number(p.alocados ?? 0)}</td>
                          <td className="py-1.5 text-right">
                            {p.coberto
                              ? <Badge variant="outline" className="text-xs border-sky-300 text-sky-700">coberto</Badge>
                              : <Badge className="bg-red-500 text-white text-xs">descoberto</Badge>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
            {pano.fonte && <p className="mt-2 text-[10px] text-muted-foreground">Fonte: {pano.fonte}</p>}
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base"><Bot className="h-4 w-4 text-sky-600" /> Pergunte ao COO</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <label className="text-xs font-medium text-muted-foreground">Lente</label>
                <div className="flex flex-wrap gap-2 mt-1">
                  {AREAS.map((a) => (
                    <button key={a.value} onClick={() => setArea(a.value)}
                      className={`px-3 py-1.5 rounded-md text-sm border transition-colors ${area === a.value ? 'bg-sky-600 text-white border-sky-600' : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'}`}>
                      {a.label}
                    </button>
                  ))}
                </div>
              </div>
              <Textarea
                value={pergunta}
                onChange={(e) => setPergunta(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder={arquivo ? 'Pergunta sobre o documento (opcional) — Enter para enviar' : 'Ex.: "Quais postos estão descobertos?" · "Tenho diarista disponível para cobrir uma falta amanhã?" (Enter envia)'}
                rows={4}
                disabled={loading}
              />
              {arquivo && (
                <div className="flex items-center gap-2 text-sm bg-sky-50 border border-sky-200 rounded px-3 py-1.5">
                  <Paperclip className="h-4 w-4 text-sky-600" />
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
                <Button onClick={consultar} disabled={loading || (!pergunta.trim() && !arquivo)} className="bg-sky-600 hover:bg-sky-700 text-white">
                  {loading ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Analisando...</> : <><Send className="h-4 w-4 mr-2" /> Perguntar</>}
                </Button>
              </div>
              {loading && <p className="text-xs text-muted-foreground text-center">O COO está analisando a operação — pode levar de 10 a 30 segundos.</p>}
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
              <CardHeader className="pb-3"><CardTitle className="text-base">Análise do COO</CardTitle></CardHeader>
              <CardContent className="space-y-4">
                {resposta.escalonar && (
                  <div className="flex items-start gap-2 rounded-md border border-orange-300 bg-orange-50 px-3 py-2 text-sm text-orange-800">
                    <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
                    <span>Situação sensível — valide com o supervisor de campo antes de agir.</span>
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
