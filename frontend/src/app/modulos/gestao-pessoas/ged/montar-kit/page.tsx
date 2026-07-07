'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Wand2, Loader2, CheckCircle2, XCircle, Clock, FolderOpen, RefreshCw, ExternalLink,
  CalendarClock, AlertTriangle, Download,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  dispararMontagem, statusMontagem, painelKits, cronogramaKits, ETAPA_LABEL, BLOCO_LABEL, BLOCOS_ETAPAS,
  type MontagemStatus, type PainelResponse, type CronogramaResponse,
} from '@/services/gedeon/kitMontagemService';

function fmtData(iso: string | null): string {
  if (!iso) return '—';
  const p = iso.split('-');
  return `${p[2]}/${p[1]}`;
}

function competenciaAnterior(): string {
  const h = new Date();
  let m = h.getMonth(); // 0-based = mês anterior (getMonth já é mês-1 do humano)
  let a = h.getFullYear();
  if (m < 1) { m = 12; a -= 1; }
  return `${String(m).padStart(2, '0')}.${a}`;
}

function ultimasCompetencias(n = 6): string[] {
  const out: string[] = [];
  const h = new Date();
  let m = h.getMonth(); let a = h.getFullYear();
  for (let i = 0; i < n; i++) {
    if (m < 1) { m = 12; a -= 1; }
    out.push(`${String(m).padStart(2, '0')}.${a}`);
    m -= 1;
  }
  return out;
}

export default function MontarKitPage() {
  const [competencia, setCompetencia] = useState(competenciaAnterior());
  const [montando, setMontando] = useState(false);
  const [blocoAtivo, setBlocoAtivo] = useState<string | null>(null); // null=tudo
  const [status, setStatus] = useState<MontagemStatus | null>(null);
  const [painel, setPainel] = useState<PainelResponse | null>(null);
  const [crono, setCrono] = useState<CronogramaResponse | null>(null);
  const [loadingPainel, setLoadingPainel] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const carregarPainel = useCallback(async (comp: string) => {
    setLoadingPainel(true);
    try { setPainel(await painelKits(comp)); }
    catch { setPainel(null); }
    finally { setLoadingPainel(false); }
  }, []);

  const carregarCrono = useCallback(async (comp: string) => {
    try { setCrono(await cronogramaKits(comp)); } catch { setCrono(null); }
  }, []);

  useEffect(() => {
    carregarPainel(competencia);
    carregarCrono(competencia);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [competencia, carregarPainel, carregarCrono]);

  // blocos=null → monta tudo; blocos=['cnds'] → incremental (só aquele bloco)
  const iniciarMontagem = async (blocos: string[] | null = null) => {
    if (montando) return;
    setMontando(true);
    setBlocoAtivo(blocos && blocos.length === 1 ? blocos[0] : null);
    const esperadas = blocos
      ? blocos.flatMap((b) => BLOCOS_ETAPAS[b] || [])
      : Object.keys(ETAPA_LABEL);
    setStatus({ task_id: '', state: 'PENDING', etapas_esperadas: esperadas });
    try {
      const { task_id } = await dispararMontagem(competencia, blocos);
      let polls = 0;
      pollRef.current = setInterval(async () => {
        polls++;
        try {
          const st = await statusMontagem(task_id);
          setStatus(st);
          const orqOk = st.state === 'SUCCESS';
          const pontoFim = ['done', 'error'].includes(st.ponto?.state || '');
          // para quando: a montagem falhou; OU concluiu E o ponto terminou; OU timeout (~5min)
          if (st.state === 'FAILURE' || (orqOk && pontoFim) || polls > 100) {
            if (pollRef.current) clearInterval(pollRef.current);
            setMontando(false);
            carregarPainel(competencia);
          } else if (orqOk) {
            carregarPainel(competencia); // atualiza o painel já com a montagem pronta
          }
        } catch { /* mantém polling */ }
      }, 3000);
    } catch {
      setMontando(false);
      setStatus({ task_id: '', state: 'FAILURE', etapas_esperadas: [], erro: 'Falha ao iniciar a montagem' });
    }
  };

  const etapas = status?.etapas_esperadas?.length ? status.etapas_esperadas : Object.keys(ETAPA_LABEL);

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div>
        <h1 className="font-display text-2xl font-bold flex items-center gap-2">
          <Wand2 className="w-6 h-6 text-violet-500" /> Montar Kit Documental
        </h1>
        <p className="text-sm text-[hsl(var(--muted-foreground))] mt-1">
          Monte o kit completo de uma vez, ou <strong>bloco a bloco conforme cada documento fica
          pronto</strong> (folha, salários, assinados, VT/VR, guias, NFS-e…). Também roda sozinho todo dia 28.
        </p>
      </div>

      {/* Controles */}
      <Card>
        <CardContent className="p-4 flex flex-wrap items-end gap-4">
          <div>
            <label className="block text-xs text-[hsl(var(--muted-foreground))] mb-1">Competência</label>
            <select
              value={competencia}
              onChange={(e) => setCompetencia(e.target.value)}
              disabled={montando}
              className="px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-sm"
            >
              {ultimasCompetencias().map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <button
            onClick={() => iniciarMontagem(null)}
            disabled={montando}
            className="px-5 py-2 rounded-lg bg-violet-600 hover:bg-violet-700 text-white text-sm font-medium flex items-center gap-2 disabled:opacity-60"
          >
            {montando && blocoAtivo === null ? <Loader2 className="w-4 h-4 animate-spin" /> : <Wand2 className="w-4 h-4" />}
            {montando && blocoAtivo === null ? 'Montando tudo…' : 'Montar kit completo'}
          </button>
          <button
            onClick={() => carregarPainel(competencia)}
            disabled={loadingPainel}
            className="px-3 py-2 rounded-lg border border-[hsl(var(--border))] text-sm flex items-center gap-2"
          >
            <RefreshCw className={`w-4 h-4 ${loadingPainel ? 'animate-spin' : ''}`} /> Atualizar painel
          </button>
        </CardContent>
      </Card>

      {/* Cronograma do mês — montagem incremental conforme cada documento fica pronto */}
      {crono && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <CalendarClock className="w-5 h-5 text-violet-500" />
              Cronograma — entrega {crono.mes_entrega}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-0">
            <p className="text-xs text-[hsl(var(--muted-foreground))] mb-3">
              Vá montando conforme os documentos chegam — sem deixar para a última hora. Clique em
              "Buscar" em cada etapa que já estiver pronta.
            </p>
            <div className="space-y-2">
              {crono.etapas.map((e, i) => {
                const acionavel = e.blocos.length > 0;
                const rodando = montando && blocoAtivo !== null && e.blocos.includes(blocoAtivo);
                return (
                  <div key={i} className="flex flex-wrap items-center gap-2 py-2 border-b border-[hsl(var(--border))] last:border-0">
                    <div className="flex items-center gap-2 min-w-[16px]">
                      {e.vencido
                        ? <CheckCircle2 className="w-4 h-4 text-emerald-500" title="data já passou" />
                        : <Clock className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />}
                    </div>
                    <div className="flex-1 min-w-[200px]">
                      <div className="text-sm font-medium flex items-center gap-2">
                        {e.titulo}
                        {e.prazo && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-500 border border-amber-500/30 flex items-center gap-0.5">
                            <AlertTriangle className="w-3 h-3" /> assinar até {fmtData(e.prazo)}
                          </span>
                        )}
                      </div>
                      {e.obs && <div className="text-xs text-[hsl(var(--muted-foreground))]">{e.obs}</div>}
                    </div>
                    <div className="text-sm text-[hsl(var(--muted-foreground))] w-16 text-right">{fmtData(e.data)}</div>
                    {acionavel && (
                      <button
                        onClick={() => iniciarMontagem(e.blocos)}
                        disabled={montando}
                        className="px-3 py-1.5 rounded-lg border border-violet-300 text-violet-700 text-xs font-medium flex items-center gap-1.5 hover:bg-violet-50 disabled:opacity-50"
                      >
                        {rodando ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
                        Buscar
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
            {/* atalho: botões por bloco soltos */}
            <div className="flex flex-wrap gap-2 mt-4 pt-3 border-t border-[hsl(var(--border))]">
              <span className="text-xs text-[hsl(var(--muted-foreground))] w-full">Ou monte um bloco específico:</span>
              {Object.entries(BLOCO_LABEL).map(([b, label]) => (
                <button
                  key={b}
                  onClick={() => iniciarMontagem([b])}
                  disabled={montando}
                  className="px-3 py-1.5 rounded-full border border-[hsl(var(--border))] text-xs hover:bg-[hsl(var(--muted))] disabled:opacity-50 flex items-center gap-1.5"
                >
                  {montando && blocoAtivo === b ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
                  {label}
                </button>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Progresso da montagem */}
      {status && (
        <Card>
          <CardHeader><CardTitle className="text-base">Progresso da montagem</CardTitle></CardHeader>
          <CardContent className="p-4 pt-0 space-y-2">
            {montando && (
              <p className="text-xs text-amber-500 bg-amber-500/10 border border-amber-500/30 rounded-lg px-3 py-2 mb-1">
                A montagem completa leva ~2-3 minutos (busca Onvio + Inter + Sólides + Drive). As etapas
                ficam girando e concluem juntas no fim. Para acompanhar <strong>item por item</strong>, use a
                ficha de cada condomínio (menu → Kits por Condomínio → clique no condomínio).
              </p>
            )}
            {etapas.map((k) => {
              const e = status.etapas?.[k];
              const done = status.state === 'SUCCESS' || status.state === 'FAILURE';
              let icon;
              if (e) icon = e.ok ? <CheckCircle2 className="w-4 h-4 text-emerald-500" /> : <XCircle className="w-4 h-4 text-red-500" />;
              else if (done) icon = <XCircle className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />;
              else icon = montando ? <Loader2 className="w-4 h-4 animate-spin text-violet-500" /> : <Clock className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />;
              return (
                <div key={k} className="flex items-center gap-2 text-sm">
                  {icon}
                  <span>{ETAPA_LABEL[k] || k}</span>
                  {e && !e.ok && e.erro && <span className="text-red-400 text-xs">— {e.erro.slice(0, 80)}</span>}
                </div>
              );
            })}
            {/* Ponto assinado — robô do host (Sólides), via ponte backend→host */}
            {(() => {
              const orqOk = status.state === 'SUCCESS';
              const ps = status.ponto?.state;
              let icon: React.ReactNode; let txt: string;
              if (!orqOk) { icon = <Clock className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />; txt = 'aguardando a montagem'; }
              else if (ps === 'done') { icon = <CheckCircle2 className="w-4 h-4 text-emerald-500" />; txt = status.ponto?.arquivados ? `${status.ponto.arquivados} novos arquivados` : 'concluído'; }
              else if (ps === 'error') { icon = <XCircle className="w-4 h-4 text-red-500" />; txt = 'falhou'; }
              else { icon = <Loader2 className="w-4 h-4 animate-spin text-violet-500" />; txt = ps === 'running' ? 'baixando do Sólides…' : 'na fila…'; }
              return (
                <div className="flex items-center gap-2 text-sm">
                  {icon}
                  <span>Documentos assinados (Sólides): folha de ponto + VT/VR + férias</span>
                  <span className="text-xs text-[hsl(var(--muted-foreground))]">— {txt}</span>
                </div>
              );
            })()}
            {status.resumo && (
              <div className="text-sm pt-2 font-medium">
                {status.resumo.etapas_falha === 0
                  ? <span className="text-emerald-500 inline-flex items-center gap-1"><CheckCircle2 className="w-3.5 h-3.5" /> Kit montado — {status.resumo.etapas_ok} etapas concluídas</span>
                  : <span className="text-amber-500">{status.resumo.etapas_ok} OK, {status.resumo.etapas_falha} com pendência</span>}
              </div>
            )}
            {status.erro && <div className="text-sm text-red-500">{status.erro}</div>}
          </CardContent>
        </Card>
      )}

      {/* Painel de completude */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">
            Painel dos kits {painel ? `— ${painel.mes_kit} (competência ${painel.competencia})` : ''}
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {loadingPainel && !painel ? (
            <div className="p-6 text-center text-sm text-[hsl(var(--muted-foreground))]">
              <Loader2 className="w-5 h-5 animate-spin inline" /> Carregando…
            </div>
          ) : !painel || painel.condominios.length === 0 ? (
            <div className="p-6 text-center text-sm text-[hsl(var(--muted-foreground))]">Nenhum kit para esta competência.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[hsl(var(--border))] text-left text-[hsl(var(--muted-foreground))]">
                    <th className="px-4 py-2">Condomínio</th>
                    {painel.condominios[0].subpastas.map((s) => (
                      <th key={s.nome} className="px-3 py-2 text-center whitespace-nowrap">{s.nome.replace(/^\d+\.\s*/, '')}</th>
                    ))}
                    <th className="px-3 py-2 text-center">Total</th>
                    <th className="px-3 py-2 text-center">Drive</th>
                  </tr>
                </thead>
                <tbody>
                  {painel.condominios.map((c) => (
                    <tr key={c.condominio} className="border-b border-[hsl(var(--border))] last:border-0">
                      <td className="px-4 py-2 font-medium">{c.condominio}</td>
                      {c.subpastas.map((s) => (
                        <td key={s.nome} className="px-3 py-2 text-center">
                          <span className={s.docs > 0 ? 'tabular-nums' : 'text-[hsl(var(--muted-foreground))] tabular-nums'}>{s.docs}</span>
                        </td>
                      ))}
                      <td className="px-3 py-2 text-center font-semibold">{c.total}</td>
                      <td className="px-3 py-2 text-center">
                        {c.drive_link ? (
                          <a href={c.drive_link} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-violet-600 hover:underline">
                            <FolderOpen className="w-4 h-4" /><ExternalLink className="w-3 h-3" />
                          </a>
                        ) : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
