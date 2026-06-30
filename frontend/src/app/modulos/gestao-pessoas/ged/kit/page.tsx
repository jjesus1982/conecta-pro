'use client';

import { useState, useEffect, useCallback, useRef, Suspense } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import {
  Building2, Loader2, CheckCircle2, XCircle, Upload, Plus, Trash2, ExternalLink,
  FolderOpen, ArrowLeft, RefreshCw, UserPlus, UserMinus, Plane, Repeat, FileText, Stethoscope,
  Download, Search, Clock,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  getFicha, addEvento, delEvento, uploadKit, delArquivo, TIPO_LABEL, SUBPASTAS,
  type FichaKit, type EventoKit, type ArquivoKit,
} from '@/services/gedeon/kitFichaService';
import { dispararMontagem, statusMontagem, ETAPA_LABEL } from '@/services/gedeon/kitMontagemService';
import KitGestaoSecoes from './KitGestaoSecoes';

// Tipos de documento que o robô coleta (na ordem da montagem do kit), por condomínio
const BLOCOS_COLETA = [
  { key: 'folha', label: 'Folha e contracheques', sub: 'Folha e Pessoal' },
  { key: 'pagamentos', label: 'Salários, INSS e boletos', sub: 'Folha e Pessoal' },
  { key: 'ponto', label: 'Documentos assinados (Sólides)', sub: 'Folha e Pessoal' },
  { key: 'vavt', label: 'Vale Transporte / Alimentação', sub: 'Vale Transporte e Alimentação' },
  { key: 'guias', label: 'Guias e impostos (FGTS, DCTFWeb, INSS)', sub: 'Impostos e Certidões' },
  { key: 'rescisao', label: 'Rescisões (TRCT + verbas)', sub: 'Folha e Pessoal' },
  { key: 'cnds', label: 'Certidões (CND)', sub: 'Impostos e Certidões' },
  { key: 'nfse', label: 'Notas fiscais e boletos', sub: 'Faturamento' },
];

const TIPO_ICON: Record<string, React.ReactNode> = {
  contratacao: <UserPlus className="w-4 h-4 text-emerald-500" />,
  demissao: <UserMinus className="w-4 h-4 text-red-500" />,
  ferias: <Plane className="w-4 h-4 text-blue-500" />,
  migracao_posto: <Repeat className="w-4 h-4 text-amber-500" />,
  entrada_outro_posto: <Repeat className="w-4 h-4 text-amber-500" />,
  atestado: <Stethoscope className="w-4 h-4 text-purple-500" />,
  afastamento: <Stethoscope className="w-4 h-4 text-purple-500" />,
  observacao: <FileText className="w-4 h-4 text-gray-400" />,
};

function barColor(p: number) {
  if (p >= 100) return 'bg-emerald-600';
  if (p >= 70) return 'bg-blue-600';
  if (p >= 40) return 'bg-yellow-500';
  return 'bg-red-500';
}

function KitFichaInner() {
  const sp = useSearchParams();
  const router = useRouter();
  const cond = sp.get('cond') || '';
  const comp = sp.get('comp') || '';

  const [f, setF] = useState<FichaKit | null>(null);
  const [loading, setLoading] = useState(true);
  const [enviando, setEnviando] = useState(false);
  const [subpasta, setSubpasta] = useState(SUBPASTAS[0]);
  const [novoTipo, setNovoTipo] = useState('observacao');
  const [novaDesc, setNovaDesc] = useState('');
  const [novoFunc, setNovoFunc] = useState('');
  const [coleta, setColeta] = useState<Record<string, string>>({}); // bloco -> 'coletando'|'ok'|'erro'
  const [coletando, setColetando] = useState<string | null>(null);
  const [progresso, setProgresso] = useState<Record<string, string>>({}); // etapa -> running|ok|erro (ao vivo)
  const fileRef = useRef<HTMLInputElement | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const carregar = useCallback(async (refresh = false) => {
    if (!cond) return;
    setLoading(true);
    try { setF(await getFicha(cond, comp || undefined, refresh)); } catch { setF(null); }
    finally { setLoading(false); }
  }, [cond, comp]);

  useEffect(() => { carregar(); }, [carregar]);

  const onExcluirArquivo = async (a: ArquivoKit) => {
    if (!f || !a.id) return;
    if (!confirm(`Excluir "${a.name}"?\nVai para a lixeira do Drive (recuperável). Depois você pode buscar de novo pelo robô ou anexar o correto.`)) return;
    try { await delArquivo(cond, f.competencia, a.id, a.name); await carregar(); }
    catch { alert('Não foi possível excluir.'); }
  };

  const onUpload = async (file: File | undefined) => {
    if (!file || !f) return;
    setEnviando(true);
    try { await uploadKit(cond, f.competencia, file, subpasta); await carregar(); }
    finally { setEnviando(false); if (fileRef.current) fileRef.current.value = ''; }
  };

  // Coleta GUIADA de um tipo de documento (bloco) só para ESTE condomínio, com feedback ao vivo.
  const coletar = async (bloco: string) => {
    if (!f || coletando) return;
    setColetando(bloco);
    setColeta((s) => ({ ...s, [bloco]: 'coletando' }));
    try {
      const { task_id } = await dispararMontagem(f.competencia, [bloco], [cond]);
      let polls = 0;
      pollRef.current = setInterval(async () => {
        polls++;
        try {
          const st = await statusMontagem(task_id);
          if (st.progresso?.etapas) setProgresso(st.progresso.etapas); // feedback ao vivo
          const orqOk = st.state === 'SUCCESS';
          const orqFail = st.state === 'FAILURE';
          const pontoFim = ['done', 'error'].includes(st.ponto?.state || '');
          // bloco "ponto" (assinados) roda no host via ponte → espera o ponto terminar
          const pronto = bloco === 'ponto' ? (orqOk && pontoFim) : orqOk;
          if (pronto || orqFail || polls > 100) {
            if (pollRef.current) clearInterval(pollRef.current);
            setColeta((s) => ({ ...s, [bloco]: orqFail ? 'erro' : 'ok' }));
            setColetando(null);
            setProgresso({});
            await carregar(true); // refresh real: fura o cache p/ refletir o que o robô coletou
          }
        } catch { /* mantém polling */ }
      }, 3000);
    } catch {
      setColeta((s) => ({ ...s, [bloco]: 'erro' }));
      setColetando(null);
    }
  };

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  const onAddEvento = async () => {
    if (!f || !novaDesc.trim()) return;
    await addEvento({ condominio: cond, competencia: f.competencia, tipo: novoTipo,
      descricao: novaDesc.trim(), funcionario: novoFunc.trim() || undefined });
    setNovaDesc(''); setNovoFunc('');
    await carregar();
  };

  const onDelEvento = async (id?: string) => {
    if (!f || !id) return;
    await delEvento(cond, f.competencia, id);
    await carregar();
  };

  if (loading) return (
    <div className="flex items-center justify-center h-96 text-gray-500">
      <Loader2 className="w-6 h-6 animate-spin mr-2" /> Carregando ficha do kit…
    </div>
  );
  if (!f) return <div className="p-6 text-center text-gray-400">Não foi possível carregar o kit de "{cond}".</div>;

  const eventos = [...f.eventos.auto, ...f.eventos.manuais];
  const faltam = f.checklist.filter((c) => !c.presente);

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <button onClick={() => router.push('/modulos/gestao-pessoas/ged')} className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50">
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Building2 className="w-6 h-6 text-blue-600" /> {f.condominio}
            </h1>
            <p className="text-sm text-gray-500">Kit — competência {f.competencia} • montagem ponto a ponto</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {f.drive_link && (
            <a href={f.drive_link} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-blue-600 hover:underline text-sm">
              <FolderOpen className="w-4 h-4" /> Abrir no Drive <ExternalLink className="w-3 h-3" />
            </a>
          )}
          <button onClick={() => carregar(true)} className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50"><RefreshCw className="w-4 h-4" /></button>
          <div className="text-right">
            <div className="text-2xl font-bold">{f.completude}%</div>
            <div className="w-32 bg-gray-200 rounded-full h-2"><div className={`${barColor(f.completude)} h-2 rounded-full`} style={{ width: `${f.completude}%` }} /></div>
          </div>
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-5">
        {/* Checklist de documentos */}
        <Card className="border border-gray-200">
          <CardHeader className="pb-2"><CardTitle className="text-base">Checklist de documentos ({f.total_docs} no kit)</CardTitle></CardHeader>
          <CardContent>
            <ul className="space-y-1.5">
              {f.checklist.map((c) => (
                <li key={c.key} className="flex items-center gap-2 text-sm">
                  {c.presente ? <CheckCircle2 className="w-4 h-4 text-emerald-500" /> : <XCircle className="w-4 h-4 text-red-400" />}
                  <span className={c.presente ? '' : 'text-gray-500'}>{c.label}</span>
                  <span className="text-xs text-gray-400 ml-auto">{c.esperado > 1 ? `${c.encontrados}/${c.esperado}` : (c.encontrados > 1 ? c.encontrados : '')}</span>
                </li>
              ))}
            </ul>
            {faltam.length > 0 && <p className="text-xs text-amber-600 mt-3">Faltando: {faltam.map((c) => c.label).join(', ')}</p>}
          </CardContent>
        </Card>

        {/* Eventos do mês (checklist) */}
        <Card className="border border-gray-200">
          <CardHeader className="pb-2"><CardTitle className="text-base">Eventos do mês ({eventos.length})</CardTitle></CardHeader>
          <CardContent>
            {eventos.length === 0 && <p className="text-sm text-gray-400">Nenhum evento detectado.</p>}
            <ul className="space-y-1.5 max-h-56 overflow-y-auto">
              {eventos.map((e: EventoKit, i) => (
                <li key={e.id || `a${i}`} className="flex items-start gap-2 text-sm group">
                  {TIPO_ICON[e.tipo] || <FileText className="w-4 h-4 text-gray-400" />}
                  <div className="flex-1 min-w-0">
                    <span className="font-medium">{TIPO_LABEL[e.tipo] || e.tipo}</span>
                    {e.funcionario && <span className="text-gray-600"> — {e.funcionario}</span>}
                    <div className="text-xs text-gray-500 truncate">{e.descricao}</div>
                  </div>
                  {!e.auto
                    ? <button onClick={() => onDelEvento(e.id)} className="opacity-0 group-hover:opacity-100 text-gray-300 hover:text-red-500"><Trash2 className="w-3.5 h-3.5" /></button>
                    : <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-500">auto</span>}
                </li>
              ))}
            </ul>
            {/* adicionar evento manual */}
            <div className="mt-3 pt-3 border-t border-gray-100 space-y-2">
              <div className="flex gap-2">
                <select value={novoTipo} onChange={(e) => setNovoTipo(e.target.value)} className="text-xs border border-gray-200 rounded-lg px-2 py-1.5">
                  {f.tipos_evento.map((t) => <option key={t} value={t}>{TIPO_LABEL[t] || t}</option>)}
                </select>
                <input value={novoFunc} onChange={(e) => setNovoFunc(e.target.value)} placeholder="Funcionário (opcional)" className="text-xs border border-gray-200 rounded-lg px-2 py-1.5 flex-1" />
              </div>
              <div className="flex gap-2">
                <input value={novaDesc} onChange={(e) => setNovaDesc(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && onAddEvento()} placeholder="Descrição do evento…" className="text-xs border border-gray-200 rounded-lg px-2 py-1.5 flex-1" />
                <button onClick={onAddEvento} disabled={!novaDesc.trim()} className="px-3 py-1.5 rounded-lg bg-blue-600 text-white text-xs flex items-center gap-1 disabled:opacity-50"><Plus className="w-3.5 h-3.5" /> Adicionar</button>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Coleta guiada — item por item, só deste condomínio, com feedback ao vivo */}
      <Card className="border border-gray-200">
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2"><Search className="w-4 h-4 text-violet-500" /> Coleta de documentos — item por item</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-gray-500 mb-3">
            Clique em <strong>Buscar</strong> em cada tipo de documento — o robô coleta só deste condomínio,
            mostra o andamento e atualiza a lista. Confira item por item; ao final, revise tudo abaixo.
          </p>
          <div className="space-y-1.5">
            {BLOCOS_COLETA.map((b) => {
              const st = coleta[b.key];
              return (
                <div key={b.key} className="flex items-center gap-3 py-2 border-b border-gray-100 last:border-0">
                  <div className="flex items-center gap-2 w-5">
                    {st === 'coletando' ? <Loader2 className="w-4 h-4 animate-spin text-violet-500" />
                      : st === 'ok' ? <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                      : st === 'erro' ? <XCircle className="w-4 h-4 text-red-500" />
                      : <Clock className="w-4 h-4 text-gray-300" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium">{b.label}</div>
                    <div className="text-xs text-gray-400">→ {b.sub}</div>
                  </div>
                  {st === 'coletando' && <span className="text-xs text-violet-600 animate-pulse">coletando…</span>}
                  {st === 'ok' && <span className="text-xs text-emerald-600">coletado ✓</span>}
                  {st === 'erro' && <span className="text-xs text-red-500">falhou</span>}
                  <button
                    onClick={() => coletar(b.key)}
                    disabled={!!coletando}
                    className="px-3 py-1.5 rounded-lg border border-violet-300 text-violet-700 text-xs font-medium flex items-center gap-1.5 hover:bg-violet-50 disabled:opacity-40"
                  >
                    <Download className="w-3.5 h-3.5" /> Buscar
                  </button>
                </div>
              );
            })}
          </div>
          {/* Progresso ao vivo do orquestrador (etapas em running/ok/erro) */}
          {coletando && Object.keys(progresso).length > 0 && (
            <div className="mt-4 pt-3 border-t border-gray-100">
              <p className="text-xs font-medium text-gray-500 mb-2">Andamento do robô:</p>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(progresso).filter(([k]) => k !== '_concluido').map(([etapa, st]) => (
                  <span key={etapa} className={`text-[11px] px-2 py-0.5 rounded-full flex items-center gap-1 ${
                    st === 'ok' ? 'bg-emerald-100 text-emerald-700'
                    : st === 'erro' ? 'bg-red-100 text-red-600'
                    : 'bg-violet-100 text-violet-700'}`}>
                    {st === 'running' && <Loader2 className="w-3 h-3 animate-spin" />}
                    {st === 'ok' && <CheckCircle2 className="w-3 h-3" />}
                    {st === 'erro' && <XCircle className="w-3 h-3" />}
                    {ETAPA_LABEL[etapa] || etapa}
                  </span>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Gestão do kit: ATLAS, entrega, faturamento, assinaturas, visão funcionário, DP */}
      <KitGestaoSecoes cond={cond} comp={f.competencia} onChange={carregar} />

      {/* Upload de anexos */}
      <Card className="border border-gray-200">
        <CardHeader className="pb-2"><CardTitle className="text-base flex items-center gap-2"><Upload className="w-4 h-4" /> Anexar arquivo ao kit</CardTitle></CardHeader>
        <CardContent className="flex flex-wrap items-center gap-3">
          <span className="text-sm text-gray-500">Para TRCT digitalizado, atestado, ou qualquer doc que não vem do Sólides/Onvio/Inter.</span>
          <select value={subpasta} onChange={(e) => setSubpasta(e.target.value)} className="text-sm border border-gray-200 rounded-lg px-3 py-2">
            {SUBPASTAS.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <input ref={fileRef} type="file" className="hidden" onChange={(e) => onUpload(e.target.files?.[0])} />
          <button onClick={() => fileRef.current?.click()} disabled={enviando} className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-sm flex items-center gap-2 disabled:opacity-60">
            {enviando ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />} Enviar arquivo
          </button>
        </CardContent>
      </Card>

      {/* Arquivos no Drive por subpasta */}
      <Card className="border border-gray-200">
        <CardHeader className="pb-2"><CardTitle className="text-base">Arquivos no Drive</CardTitle></CardHeader>
        <CardContent>
          <div className="grid md:grid-cols-2 gap-4">
            {f.subpastas.map((sp2) => (
              <div key={sp2.nome}>
                <p className="text-sm font-medium text-gray-700 flex items-center gap-1.5 mb-1"><FolderOpen className="w-4 h-4 text-gray-400" /> {sp2.nome} <span className="text-gray-400">({sp2.docs})</span></p>
                {sp2.arquivos.length > 0 ? (
                  <ul className="ml-5 space-y-0.5">
                    {sp2.arquivos.map((a, i) => (
                      <li key={i} className="text-xs text-gray-600 flex items-center gap-1.5 group">
                        <span className="truncate flex-1">
                          {a.link ? <a href={a.link} target="_blank" rel="noreferrer" className="hover:text-blue-600 hover:underline">• {a.name}</a> : <span>• {a.name}</span>}
                        </span>
                        <button onClick={() => onExcluirArquivo(a)} title="Excluir (vai para a lixeira do Drive)"
                          className="opacity-0 group-hover:opacity-100 text-gray-300 hover:text-red-500 shrink-0">
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : <p className="ml-5 text-xs text-gray-400 italic">vazio</p>}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default function KitFichaPage() {
  return <Suspense fallback={<div className="p-6 text-gray-400">Carregando…</div>}><KitFichaInner /></Suspense>;
}
