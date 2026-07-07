'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import {
  Bot, Send, Loader2, AlertTriangle, History, Paperclip, X,
  CheckCircle2, XCircle, Trash2, Package, Building2, Users, ClipboardList, Wand2,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { StatCard } from '@/components/ui/stat-card';

const API_BASE = '/api/v1/gedeon/consultor';
const API_KITS = '/api/v1/gedeon/kits';

function getAuthHeaders(json = true): Record<string, string> {
  const token = typeof window !== 'undefined' ? (localStorage.getItem('access_token') || localStorage.getItem('token')) : null;
  return { ...(json ? { 'Content-Type': 'application/json' } : {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) };
}

const AREAS = [
  { value: 'montagem', label: 'Montagem' },
  { value: 'checklist', label: 'Checklist' },
  { value: 'intercorrencias', label: 'Intercorrências' },
  { value: 'folha', label: 'Folha' },
] as const;

const TIPOS_INTERCORRENCIA = [
  { value: 'contratacao', label: 'Contratação' },
  { value: 'demissao', label: 'Demissão' },
  { value: 'falta', label: 'Falta' },
  { value: 'atraso', label: 'Atraso' },
  { value: 'suspensao', label: 'Suspensão' },
  { value: 'afastamento', label: 'Afastamento' },
  { value: 'ferias', label: 'Férias' },
  { value: 'advertencia', label: 'Advertência' },
  { value: 'acidente', label: 'Acidente' },
  { value: 'hora_extra', label: 'Hora extra' },
  { value: 'troca_posto', label: 'Troca de posto' },
  { value: 'outro', label: 'Outro' },
] as const;

const tipoLabel = (t: string) => TIPOS_INTERCORRENCIA.find((x) => x.value === t)?.label || t;

const brl = (v: unknown) => {
  const n = Number(v);
  return isNaN(n) ? '—' : n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
};

/** Competência padrão = mês anterior (salário em arrears), YYYY-MM. */
function competenciaPadrao(): string {
  const d = new Date();
  d.setDate(1);
  d.setMonth(d.getMonth() - 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

// ── Tipos (contrato com /gedeon/consultor) ───────────────────────────────────
interface KitInfo {
  montado: boolean;
  score: number | null;
  docs_total: number | null;
  montado_em: string | null;
}

interface CondominioItem {
  condominio: string;
  kit: KitInfo;
  intercorrencias_abertas: number;
  intercorrencias_total: number;
  funcionarios_alocados: number;
  pronto_para_fechar: boolean;
}

interface Panorama {
  competencia: string;
  condominios: CondominioItem[];
  total_condominios: number;
  kits_montados: number;
  intercorrencias_abertas: number;
  folha_competencia: { holerites: number; liquido: number };
  fonte?: string;
  gerado_em?: string;
}

interface Intercorrencia {
  id: number;
  condominio: string;
  competencia: string;
  tipo: string;
  funcionario: string | null;
  data_evento: string | null;
  descricao: string;
  impacto_folha: boolean;
  status: 'aberta' | 'tratada' | string;
  created_at?: string;
}

interface ConsultaResposta {
  resposta: string;
  escalonar: boolean;
  disclaimer?: string;
  id?: number | null;
  indisponivel?: boolean;
  panorama?: Panorama | null;
}

interface HistoricoItem {
  id?: number;
  area?: string;
  pergunta?: string;
  escalonar?: boolean;
  created_at?: string;
}

/** Render leve de Markdown (## títulos, **negrito**, listas, --- ). */
function Markdown({ text }: { text: string }) {
  const inline = (s: string, key: number) => {
    const parts = s.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean);
    return parts.map((p, i) =>
      p.startsWith('**') && p.endsWith('**') ? <strong key={i}>{p.slice(2, -2)}</strong>
      : p.startsWith('`') && p.endsWith('`') ? <code key={i} className="bg-muted px-1 rounded text-[13px]">{p.slice(1, -1)}</code>
      : <span key={i}>{p}</span>
    );
  };
  const lines = (text || '').split('\n');
  const out: React.ReactNode[] = [];
  let list: React.ReactNode[] = [];
  const flush = () => { if (list.length) { out.push(<ul key={`u${out.length}`} className="list-disc ml-5 my-1 space-y-0.5">{list}</ul>); list = []; } };
  lines.forEach((raw, i) => {
    const l = raw.trimEnd();
    if (/^#{1,4}\s/.test(l)) { flush(); const t = l.replace(/^#{1,4}\s/, ''); out.push(<h3 key={i} className="font-semibold text-emerald-500 mt-3 mb-1">{inline(t, i)}</h3>); }
    else if (/^(\s*[-*•]\s+)/.test(l)) { list.push(<li key={i}>{inline(l.replace(/^\s*[-*•]\s+/, ''), i)}</li>); }
    else if (/^\s*\d+[.)]\s+/.test(l)) { list.push(<li key={i}>{inline(l.replace(/^\s*\d+[.)]\s+/, ''), i)}</li>); }
    else if (/^\s*---+\s*$/.test(l)) { flush(); out.push(<hr key={i} className="my-2 border-border" />); }
    else if (l.trim() === '') { flush(); }
    else { flush(); out.push(<p key={i} className="my-1 leading-relaxed">{inline(l, i)}</p>); }
  });
  flush();
  return <div className="text-sm text-foreground">{out}</div>;
}

export default function ConsultorGedPage() {
  // ── Chat ──
  const [area, setArea] = useState<string>('montagem');
  const [condominioChat, setCondominioChat] = useState('');
  const [pergunta, setPergunta] = useState('');
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [resposta, setResposta] = useState<ConsultaResposta | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [historico, setHistorico] = useState<HistoricoItem[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);

  // ── Painel ──
  const [competencia, setCompetencia] = useState(competenciaPadrao());
  const [pano, setPano] = useState<Panorama | null>(null);
  const [montagemTasks, setMontagemTasks] = useState<Record<string, string>>({});
  const [montando, setMontando] = useState<string | null>(null);

  // ── Intercorrências ──
  const [intercorrencias, setIntercorrencias] = useState<Intercorrencia[]>([]);
  const [salvandoInterc, setSalvandoInterc] = useState(false);
  const [ni, setNi] = useState({ condominio: '', tipo: 'contratacao', funcionario: '', data_evento: '', descricao: '', impacto_folha: true });

  const carregarHistorico = useCallback(async () => {
    try {
      const h = await fetch(`${API_BASE}/historico`, { headers: getAuthHeaders() })
        .then((r) => (r.ok ? r.json() : null)).catch(() => null);
      setHistorico((h?.consultas as HistoricoItem[]) || []);
    } catch { /* */ }
  }, []);

  const carregarPanorama = useCallback(async (comp: string) => {
    try {
      const p = await fetch(`${API_BASE}/panorama?competencia=${encodeURIComponent(comp)}`, { headers: getAuthHeaders() })
        .then((r) => (r.ok ? r.json() : null)).catch(() => null);
      setPano(p as Panorama | null);
    } catch { /* */ }
  }, []);

  const carregarIntercorrencias = useCallback(async (comp: string) => {
    try {
      const d = await fetch(`${API_BASE}/intercorrencias?competencia=${encodeURIComponent(comp)}`, { headers: getAuthHeaders() })
        .then((r) => (r.ok ? r.json() : null)).catch(() => null);
      setIntercorrencias((d?.intercorrencias as Intercorrencia[]) || []);
    } catch { /* */ }
  }, []);

  useEffect(() => { carregarHistorico(); }, [carregarHistorico]);
  useEffect(() => { carregarPanorama(competencia); carregarIntercorrencias(competencia); }, [competencia, carregarPanorama, carregarIntercorrencias]);

  // ── Ações: montagem de kit ──
  const montarKit = async (nome: string) => {
    if (montando) return;
    setMontando(nome);
    try {
      const r = await fetch(`${API_KITS}/montagem`, {
        method: 'POST', headers: getAuthHeaders(),
        body: JSON.stringify({ condominios: [nome] }),
      });
      if (r.ok) {
        const data = await r.json();
        setMontagemTasks((t) => ({ ...t, [nome]: String(data?.task_id || '') }));
      } else {
        const e = await r.json().catch(() => ({}));
        setErro(e?.detail || `Falha ao enfileirar a montagem (HTTP ${r.status}).`);
      }
    } catch {
      setErro('Falha de comunicação ao enfileirar a montagem do kit.');
    } finally { setMontando(null); }
  };

  // ── Ações: intercorrências ──
  const salvarIntercorrencia = async () => {
    if (!ni.condominio || !ni.descricao.trim() || salvandoInterc) return;
    setSalvandoInterc(true);
    try {
      const body: Record<string, unknown> = {
        condominio: ni.condominio,
        tipo: ni.tipo,
        descricao: ni.descricao.trim(),
        competencia,
        impacto_folha: ni.impacto_folha,
      };
      if (ni.funcionario.trim()) body.funcionario = ni.funcionario.trim();
      if (ni.data_evento) body.data_evento = ni.data_evento;
      const r = await fetch(`${API_BASE}/intercorrencias`, { method: 'POST', headers: getAuthHeaders(), body: JSON.stringify(body) });
      if (r.status === 201 || r.ok) {
        setNi({ condominio: '', tipo: 'contratacao', funcionario: '', data_evento: '', descricao: '', impacto_folha: true });
        await Promise.all([carregarIntercorrencias(competencia), carregarPanorama(competencia)]);
      } else {
        const e = await r.json().catch(() => ({}));
        setErro(e?.detail || `Falha ao registrar intercorrência (HTTP ${r.status}).`);
      }
    } catch {
      setErro('Falha de comunicação ao registrar a intercorrência.');
    } finally { setSalvandoInterc(false); }
  };

  const tratarIntercorrencia = async (id: number) => {
    await fetch(`${API_BASE}/intercorrencias/${id}/tratar`, { method: 'PATCH', headers: getAuthHeaders() }).catch(() => null);
    await Promise.all([carregarIntercorrencias(competencia), carregarPanorama(competencia)]);
  };

  const excluirIntercorrencia = async (id: number) => {
    await fetch(`${API_BASE}/intercorrencias/${id}`, { method: 'DELETE', headers: getAuthHeaders() }).catch(() => null);
    await Promise.all([carregarIntercorrencias(competencia), carregarPanorama(competencia)]);
  };

  // ── Ações: chat ──
  const consultar = async () => {
    if ((!pergunta.trim() && !arquivo) || loading) return;
    setLoading(true); setErro(null); setResposta(null);
    try {
      let r: Response;
      if (arquivo) {
        const fd = new FormData();
        fd.append('arquivo', arquivo); fd.append('area', area); fd.append('pergunta', pergunta);
        if (condominioChat) fd.append('condominio', condominioChat);
        fd.append('competencia', competencia);
        r = await fetch(`${API_BASE}/perguntar-arquivo`, { method: 'POST', headers: getAuthHeaders(false), body: fd });
      } else {
        const body: Record<string, unknown> = { area, pergunta, competencia };
        if (condominioChat) body.condominio = condominioChat;
        r = await fetch(`${API_BASE}/perguntar`, { method: 'POST', headers: getAuthHeaders(), body: JSON.stringify(body) });
      }
      if (!r.ok) { const e = await r.json().catch(() => ({})); setErro(e?.detail || `O Consultor GED não respondeu agora (HTTP ${r.status}).`); return; }
      const data: ConsultaResposta = await r.json();
      if (data?.indisponivel) { setErro('Consultor GED IA temporariamente indisponível — os números do painel continuam reais.'); if (data?.panorama) setPano(data.panorama); return; }
      setResposta(data);
      if (data?.panorama) setPano(data.panorama);
      carregarHistorico();
    } catch {
      setErro('Falha de comunicação com o Consultor GED IA. Tente novamente.');
    } finally { setLoading(false); }
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); consultar(); }
  };

  const condominios = pano?.condominios || [];

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center gap-3">
        <Package className="h-7 w-7 text-emerald-500" />
        <div>
          <h1 className="font-display text-2xl font-semibold text-foreground">Consultor GED IA</h1>
          <p className="text-sm text-muted-foreground">Fechamento de kits por condomínio — intercorrências, checklist e folha perfeita.</p>
        </div>
      </div>

      {/* Painel real (fotografia dos kits agora) */}
      <Card className="bg-card border-border">
        <CardHeader className="pb-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <Building2 className="h-4 w-4 text-emerald-500" /> Kits por condomínio (dados reais)
            </CardTitle>
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              Competência
              <input
                type="month"
                value={competencia}
                onChange={(e) => e.target.value && setCompetencia(e.target.value)}
                className="bg-card border border-border rounded px-2 py-1 text-xs text-foreground font-data tabular-nums"
              />
            </label>
          </div>
        </CardHeader>
        <CardContent>
          {!pano ? (
            <p className="text-sm text-muted-foreground">Carregando panorama...</p>
          ) : (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <StatCard icon={<Building2 className="w-4 h-4" />} label="Condomínios" value={pano.total_condominios} color="#f97707" />
                <StatCard
                  icon={<Package className="w-4 h-4" />}
                  label="Kits montados"
                  value={`${pano.kits_montados}/${pano.total_condominios}`}
                  color="#10b981"
                />
                <StatCard
                  icon={<AlertTriangle className="w-4 h-4" />}
                  label="Intercorrências abertas"
                  value={pano.intercorrencias_abertas}
                  color={pano.intercorrencias_abertas > 0 ? '#f59e0b' : '#10b981'}
                />
                <StatCard
                  icon={<Users className="w-4 h-4" />}
                  label="Folha da competência"
                  value={pano.folha_competencia?.holerites ?? 0}
                  sub={`líquido ${brl(pano.folha_competencia?.liquido)}`}
                  color="#3b82f6"
                />
              </div>

              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-muted-foreground border-b border-border">
                      <th className="py-2 pr-2 font-medium">Condomínio</th>
                      <th className="py-2 pr-2 font-medium">Kit montado</th>
                      <th className="py-2 pr-2 font-medium">Intercorrências</th>
                      <th className="py-2 pr-2 font-medium">Funcionários</th>
                      <th className="py-2 pr-2 font-medium">Pronto p/ fechar</th>
                      <th className="py-2 font-medium text-right">Ação</th>
                    </tr>
                  </thead>
                  <tbody>
                    {condominios.length === 0 && (
                      <tr><td colSpan={6} className="py-3 text-muted-foreground">Nenhum condomínio no padrão GEDEON para esta competência.</td></tr>
                    )}
                    {condominios.map((c) => (
                      <tr key={c.condominio} className="border-b border-border/60 last:border-0">
                        <td className="py-2 pr-2 font-medium text-foreground">{c.condominio}</td>
                        <td className="py-2 pr-2">
                          {c.kit?.montado ? (
                            <Badge className="bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 gap-1">
                              <CheckCircle2 className="h-3 w-3" /> SIM{c.kit.score != null ? ` · score ${c.kit.score}` : ''}
                            </Badge>
                          ) : (
                            <Badge className="bg-muted text-muted-foreground border border-border gap-1">
                              <XCircle className="h-3 w-3" /> NÃO
                            </Badge>
                          )}
                        </td>
                        <td className="py-2 pr-2">
                          {c.intercorrencias_abertas > 0 ? (
                            <Badge className="bg-amber-500/10 text-amber-500 border border-amber-500/20 gap-1 font-data tabular-nums">
                              <AlertTriangle className="h-3 w-3" /> {c.intercorrencias_abertas} aberta(s)
                            </Badge>
                          ) : (
                            <span className="text-xs text-muted-foreground font-data tabular-nums">0</span>
                          )}
                        </td>
                        <td className="py-2 pr-2 font-data tabular-nums text-foreground">≈{c.funcionarios_alocados}</td>
                        <td className="py-2 pr-2">
                          {c.pronto_para_fechar ? (
                            <Badge className="bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 gap-1"><CheckCircle2 className="h-3 w-3" /> SIM</Badge>
                          ) : (
                            <Badge className="bg-red-500/10 text-red-500 border border-red-500/20 gap-1"><XCircle className="h-3 w-3" /> NÃO</Badge>
                          )}
                        </td>
                        <td className="py-2 text-right">
                          {montagemTasks[c.condominio] ? (
                            <Badge className="bg-blue-500/10 text-blue-500 border border-blue-500/20 font-data text-[10px]">
                              enfileirado (task {montagemTasks[c.condominio].slice(0, 8)}...)
                            </Badge>
                          ) : (
                            <Button
                              size="sm" variant="outline"
                              onClick={() => montarKit(c.condominio)}
                              disabled={montando !== null}
                              className="h-7 text-xs gap-1"
                            >
                              {montando === c.condominio ? <Loader2 className="h-3 w-3 animate-spin" /> : <Wand2 className="h-3 w-3" />} Montar kit
                            </Button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {pano.fonte && <p className="mt-2 text-[10px] text-muted-foreground">Fonte: {pano.fonte}</p>}
            </>
          )}
        </CardContent>
      </Card>

      {/* Intercorrências do mês (registrar antes de fechar o kit) */}
      <Card className="bg-card border-border">
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <ClipboardList className="h-4 w-4 text-emerald-500" /> Intercorrências do mês ({competencia})
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap items-end gap-2 border border-border rounded-md p-2 bg-muted/30">
            <select value={ni.condominio} onChange={(e) => setNi({ ...ni, condominio: e.target.value })} className="bg-card border border-border rounded px-2 py-1 text-xs text-foreground">
              <option value="">Condomínio...</option>
              {condominios.map((c) => <option key={c.condominio} value={c.condominio}>{c.condominio}</option>)}
            </select>
            <select value={ni.tipo} onChange={(e) => setNi({ ...ni, tipo: e.target.value })} className="bg-card border border-border rounded px-2 py-1 text-xs text-foreground">
              {TIPOS_INTERCORRENCIA.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
            <input value={ni.funcionario} onChange={(e) => setNi({ ...ni, funcionario: e.target.value })} placeholder="Funcionário (opcional)" className="bg-card border border-border rounded px-2 py-1 text-xs text-foreground w-44" />
            <input type="date" value={ni.data_evento} onChange={(e) => setNi({ ...ni, data_evento: e.target.value })} className="bg-card border border-border rounded px-2 py-1 text-xs text-foreground font-data tabular-nums" />
            <textarea
              value={ni.descricao}
              onChange={(e) => setNi({ ...ni, descricao: e.target.value })}
              placeholder="Descrição (ex.: faltou dia 12 sem atestado)"
              rows={1}
              className="bg-card border border-border rounded px-2 py-1 text-xs text-foreground flex-1 min-w-[200px] resize-y"
            />
            <label className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer select-none">
              <input type="checkbox" checked={ni.impacto_folha} onChange={(e) => setNi({ ...ni, impacto_folha: e.target.checked })} className="accent-emerald-500" />
              impacta folha
            </label>
            <Button onClick={salvarIntercorrencia} disabled={salvandoInterc || !ni.condominio || !ni.descricao.trim()} className="bg-emerald-600 hover:bg-emerald-700 text-white h-7 text-xs">
              {salvandoInterc ? <Loader2 className="h-3 w-3 animate-spin" /> : 'Registrar'}
            </Button>
          </div>

          <div className="divide-y divide-border text-sm">
            {intercorrencias.length === 0 ? (
              <p className="text-sm text-muted-foreground py-1">Nenhuma intercorrência registrada nesta competência.</p>
            ) : (
              intercorrencias.map((it) => (
                <div key={it.id} className="py-2 flex flex-wrap items-center gap-2">
                  <Badge variant="outline" className="text-xs shrink-0">{tipoLabel(it.tipo)}</Badge>
                  <span className="text-xs text-muted-foreground shrink-0">{it.condominio}</span>
                  {it.funcionario && <span className="text-xs text-foreground shrink-0">{it.funcionario}</span>}
                  <span className="flex-1 text-foreground/90 min-w-[160px]">{it.descricao}</span>
                  {it.data_evento && <span className="text-[10px] text-muted-foreground font-data tabular-nums">{it.data_evento}</span>}
                  {it.status === 'tratada' ? (
                    <Badge className="bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 gap-1"><CheckCircle2 className="h-3 w-3" /> tratada</Badge>
                  ) : (
                    <Badge className="bg-amber-500/10 text-amber-500 border border-amber-500/20 gap-1"><AlertTriangle className="h-3 w-3" /> aberta</Badge>
                  )}
                  {it.status !== 'tratada' && (
                    <Button size="sm" variant="outline" onClick={() => tratarIntercorrencia(it.id)} className="h-6 text-[11px]">Tratar</Button>
                  )}
                  <button onClick={() => excluirIntercorrencia(it.id)} className="text-muted-foreground/50 hover:text-red-500" title="Excluir registro">
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))
            )}
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-4">
          <Card className="bg-card border-border">
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base"><Bot className="h-4 w-4 text-emerald-500" /> Pergunte ao Consultor GED</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex flex-wrap items-end gap-4">
                <div>
                  <label className="text-xs font-medium text-muted-foreground">Lente</label>
                  <div className="flex flex-wrap gap-2 mt-1">
                    {AREAS.map((a) => (
                      <button key={a.value} onClick={() => setArea(a.value)}
                        className={`px-3 py-1.5 rounded-md text-sm border transition-colors ${area === a.value ? 'bg-emerald-600 text-white border-emerald-600' : 'bg-card text-foreground border-border hover:bg-muted'}`}>
                        {a.label}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground">Condomínio (opcional)</label>
                  <div className="mt-1">
                    <select value={condominioChat} onChange={(e) => setCondominioChat(e.target.value)} className="bg-card border border-border rounded-md px-2 py-1.5 text-sm text-foreground">
                      <option value="">Todos</option>
                      {condominios.map((c) => <option key={c.condominio} value={c.condominio}>{c.condominio}</option>)}
                    </select>
                  </div>
                </div>
              </div>
              <Textarea
                value={pergunta}
                onChange={(e) => setPergunta(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder={arquivo ? 'Pergunta sobre o documento (opcional) — Enter para enviar' : 'Ex.: "O kit do PRIME ARENA está pronto para fechar?" · "Quais intercorrências impactam a folha deste mês?" (Enter envia)'}
                rows={4}
                disabled={loading}
              />
              {arquivo && (
                <div className="flex items-center gap-2 text-sm bg-emerald-500/10 border border-emerald-500/20 rounded px-3 py-1.5">
                  <Paperclip className="h-4 w-4 text-emerald-500" />
                  <span className="flex-1 truncate">{arquivo.name}</span>
                  <button onClick={() => setArquivo(null)} className="text-muted-foreground hover:text-foreground"><X className="h-4 w-4" /></button>
                </div>
              )}
              <div className="flex items-center justify-between gap-2">
                <label className="flex items-center gap-1.5 text-sm text-muted-foreground border border-border rounded px-3 py-2 cursor-pointer hover:bg-muted">
                  <Paperclip className="h-4 w-4" /> Anexar (PDF/planilha)
                  <input ref={fileRef} type="file" accept=".pdf,.docx,.txt,.csv,.xls,.xlsx" className="hidden"
                    onChange={(e) => setArquivo(e.target.files?.[0] || null)} />
                </label>
                <Button onClick={consultar} disabled={loading || (!pergunta.trim() && !arquivo)} className="bg-emerald-600 hover:bg-emerald-700 text-white">
                  {loading ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Analisando...</> : <><Send className="h-4 w-4 mr-2" /> Perguntar</>}
                </Button>
              </div>
              {loading && <p className="text-xs text-muted-foreground text-center">O Consultor GED está analisando os kits — pode levar de 10 a 30 segundos.</p>}
            </CardContent>
          </Card>

          {erro && (
            <Card className="border-red-500/30 bg-red-500/5">
              <CardContent className="py-4 text-sm text-red-500 flex items-center gap-2">
                <AlertTriangle className="h-4 w-4" /> {erro}
              </CardContent>
            </Card>
          )}

          {resposta && (
            <Card className="bg-card border-border">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between gap-2">
                  <CardTitle className="text-base">Análise do Consultor GED</CardTitle>
                  {resposta.escalonar && (
                    <Badge className="bg-orange-500/10 text-orange-500 border border-orange-500/20 gap-1">
                      <AlertTriangle className="h-3 w-3" /> Escalar ao gestor
                    </Badge>
                  )}
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                {resposta.escalonar && (
                  <div className="flex items-start gap-2 rounded-md border border-orange-500/30 bg-orange-500/10 px-3 py-2 text-sm text-orange-400">
                    <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
                    <span>Decisão sensível — valide com o gestor do GED/DP antes de fechar o kit.</span>
                  </div>
                )}
                <Markdown text={resposta.resposta} />
                {resposta.disclaimer && <div className="border-t border-border pt-3 text-xs text-muted-foreground italic">{resposta.disclaimer}</div>}
              </CardContent>
            </Card>
          )}
        </div>

        <div>
          <Card className="bg-card border-border">
            <CardHeader className="pb-3"><CardTitle className="flex items-center gap-2 text-base"><History className="h-4 w-4 text-muted-foreground" /> Últimas análises</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              {historico.length === 0 ? (
                <p className="text-sm text-muted-foreground">Sem consultas registradas.</p>
              ) : (
                historico.map((h, i) => (
                  <div key={h.id ?? i} className="border border-border rounded-md px-3 py-2 text-sm">
                    <div className="flex items-center justify-between gap-2 mb-1">
                      {h.area && <Badge variant="outline" className="text-xs">{AREAS.find((a) => a.value === h.area)?.label || h.area}</Badge>}
                      {h.escalonar && <Badge className="bg-orange-500/10 text-orange-500 border border-orange-500/20 text-xs">atenção</Badge>}
                    </div>
                    <div className="text-foreground/90 line-clamp-3">{h.pergunta || '—'}</div>
                    {h.created_at && <div className="text-xs text-muted-foreground mt-1 font-data tabular-nums">{new Date(h.created_at).toLocaleString('pt-BR')}</div>}
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
