'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  ShieldCheck, Loader2, Download, RefreshCw, CheckCircle2, AlertTriangle, XCircle, Wand2,
  ExternalLink, Upload,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  emitirCnd, statusCnd, abrirPdfCnd, uploadCnd, PORTAL_LABEL, diasParaVencer,
  type CndStatus,
} from '@/services/gedeon/cndService';

function badgeValidade(validade: string | null) {
  const d = diasParaVencer(validade);
  if (d === null) return { txt: '—', cls: 'text-gray-400' };
  if (d < 0) return { txt: `vencida há ${-d}d`, cls: 'text-red-500' };
  if (d <= 30) return { txt: `vence em ${d}d`, cls: 'text-amber-500' };
  return { txt: `válida (${d}d)`, cls: 'text-emerald-600' };
}

function situacaoLabel(s: string | null): { txt: string; cls: string } {
  if (s === 'negativa') return { txt: 'Negativa', cls: 'text-emerald-600' };
  if (s === 'positiva_com_efeito_negativa') return { txt: 'Positiva c/ efeito de negativa', cls: 'text-amber-600' };
  if (s === 'positiva') return { txt: 'Positiva (com débito)', cls: 'text-red-500' };
  return { txt: s || '—', cls: 'text-gray-400' };
}

export default function EmitirCndPage() {
  const [data, setData] = useState<CndStatus | null>(null);
  const [emitindo, setEmitindo] = useState(false);
  const [baixando, setBaixando] = useState<string | null>(null);
  const [enviando, setEnviando] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ dt: string; txt: string; ok: boolean } | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const fileRefs = useRef<Record<string, HTMLInputElement | null>>({});

  const carregar = useCallback(async () => {
    try { setData(await statusCnd()); } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    carregar();
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [carregar]);

  const iniciar = async () => {
    setEmitindo(true);
    try {
      await emitirCnd();
      let polls = 0;
      pollRef.current = setInterval(async () => {
        polls++;
        const st = await statusCnd();
        setData(st);
        if (st.emissao.state === 'done' || polls > 80) {
          if (pollRef.current) clearInterval(pollRef.current);
          setEmitindo(false);
          carregar();
        }
      }, 5000);
    } catch {
      setEmitindo(false);
    }
  };

  const baixar = async (dt: string) => {
    setBaixando(dt);
    try { await abrirPdfCnd(dt); } finally { setBaixando(null); }
  };

  const enviarPdf = async (dt: string, f: File | undefined) => {
    if (!f) return;
    setEnviando(dt); setMsg(null);
    try {
      const r = await uploadCnd(dt, f);
      setMsg({ dt, ok: true, txt: `CND registrada (${r.situacao}${r.validade ? `, válida até ${r.validade}` : ''}) e adicionada aos kits.` });
      await carregar();
    } catch {
      setMsg({ dt, ok: false, txt: 'Falha ao enviar — confira se é o PDF da CND oficial.' });
    } finally {
      setEnviando(null);
      if (fileRefs.current[dt]) fileRefs.current[dt]!.value = '';
    }
  };

  const em = data?.emissao;
  const manuais = data?.manuais ? Object.entries(data.manuais) : [];
  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <ShieldCheck className="w-6 h-6 text-emerald-600" /> Certidões Negativas (CND)
        </h1>
        <p className="text-sm text-[hsl(var(--muted-foreground))] mt-1">
          Emita as CNDs direto pelo Conecta PRO — o sistema acessa os portais, resolve o captcha e
          baixa a certidão oficial. (SEFAZ-AM, Trabalhista e Prefeitura de Manaus.)
        </p>
      </div>

      <Card>
        <CardContent className="p-4 flex flex-wrap items-center gap-4">
          <button
            onClick={iniciar}
            disabled={emitindo}
            className="px-5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium flex items-center gap-2 disabled:opacity-60"
          >
            {emitindo ? <Loader2 className="w-4 h-4 animate-spin" /> : <Wand2 className="w-4 h-4" />}
            {emitindo ? 'Emitindo…' : 'Emitir CNDs agora'}
          </button>
          <button onClick={carregar} className="px-3 py-2 rounded-lg border border-[hsl(var(--border))] text-sm flex items-center gap-2">
            <RefreshCw className="w-4 h-4" /> Atualizar
          </button>
          {emitindo && em && (
            <span className="text-sm text-[hsl(var(--muted-foreground))]">
              {em.state === 'enfileirado' && 'na fila…'}
              {em.state === 'running' && `emitindo ${PORTAL_LABEL[em.atual || ''] || em.atual}…`}
              {em.state === 'done' && 'concluído'}
            </span>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">Certidões</CardTitle></CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[hsl(var(--border))] text-left text-[hsl(var(--muted-foreground))]">
                  <th className="px-4 py-2">Certidão</th>
                  <th className="px-3 py-2">Órgão</th>
                  <th className="px-3 py-2">Situação</th>
                  <th className="px-3 py-2">Validade</th>
                  <th className="px-3 py-2 text-center">PDF</th>
                </tr>
              </thead>
              <tbody>
                {(data?.certidoes || []).map((c) => {
                  const bv = badgeValidade(c.validade);
                  const sl = situacaoLabel(c.situacao);
                  return (
                    <tr key={c.document_type} className="border-b border-[hsl(var(--border))] last:border-0">
                      <td className="px-4 py-2 font-medium flex items-center gap-2">
                        {c.alerta ? <AlertTriangle className="w-4 h-4 text-amber-500" /> : <CheckCircle2 className="w-4 h-4 text-emerald-500" />}
                        {c.name}
                      </td>
                      <td className="px-3 py-2 text-[hsl(var(--muted-foreground))]">{c.orgao || '—'}</td>
                      <td className={`px-3 py-2 ${sl.cls}`}>{sl.txt}</td>
                      <td className="px-3 py-2">
                        <span className={bv.cls}>{c.validade || '—'}</span>
                        <span className="text-xs text-[hsl(var(--muted-foreground))] ml-1">{bv.txt !== '—' && `(${bv.txt})`}</span>
                      </td>
                      <td className="px-3 py-2 text-center">
                        {c.tem_pdf ? (
                          <button onClick={() => baixar(c.document_type)} disabled={baixando === c.document_type}
                            className="inline-flex items-center gap-1 text-emerald-600 hover:underline">
                            {baixando === c.document_type ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
                          </button>
                        ) : <XCircle className="w-4 h-4 text-gray-300 inline" />}
                      </td>
                    </tr>
                  );
                })}
                {(!data || data.certidoes.length === 0) && (
                  <tr><td colSpan={5} className="px-4 py-6 text-center text-[hsl(var(--muted-foreground))]">Nenhuma certidão. Clique em "Emitir CNDs agora".</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {manuais.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Certidões manuais (Federal e FGTS)</CardTitle>
          </CardHeader>
          <CardContent className="p-4 space-y-3">
            <p className="text-sm text-[hsl(var(--muted-foreground))]">
              Estes dois órgãos bloqueiam o robô (anti-fraude por IP). Emita no portal oficial em 1 clique
              e envie o PDF aqui — o Conecta PRO lê a validade, registra e adiciona aos kits automaticamente.
            </p>
            {manuais.map(([dt, p]) => {
              const cert = (data?.certidoes || []).find((c) => c.document_type === dt);
              const bv = cert ? badgeValidade(cert.validade) : null;
              return (
                <div key={dt} className="flex flex-wrap items-center gap-3 rounded-lg border border-[hsl(var(--border))] p-3">
                  <span className="font-medium flex-1 min-w-[180px]">{p.nome}</span>
                  {cert?.validade && (
                    <span className={`text-xs ${bv?.cls}`}>{cert.validade} {bv && bv.txt !== '—' && `(${bv.txt})`}</span>
                  )}
                  <a href={p.url} target="_blank" rel="noopener noreferrer"
                    className="px-3 py-1.5 rounded-lg border border-emerald-600 text-emerald-700 text-sm flex items-center gap-1.5 hover:bg-emerald-50">
                    <ExternalLink className="w-4 h-4" /> Abrir portal
                  </a>
                  <input type="file" accept="application/pdf" className="hidden"
                    ref={(el) => { fileRefs.current[dt] = el; }}
                    onChange={(e) => enviarPdf(dt, e.target.files?.[0])} />
                  <button onClick={() => fileRefs.current[dt]?.click()} disabled={enviando === dt}
                    className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-sm flex items-center gap-1.5 disabled:opacity-60">
                    {enviando === dt ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
                    Enviar PDF
                  </button>
                  {cert?.tem_pdf && (
                    <button onClick={() => baixar(dt)} disabled={baixando === dt}
                      className="inline-flex items-center gap-1 text-emerald-600 hover:underline text-sm">
                      {baixando === dt ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />} PDF
                    </button>
                  )}
                  {msg?.dt === dt && (
                    <span className={`w-full text-xs ${msg.ok ? 'text-emerald-600' : 'text-red-500'}`}>{msg.txt}</span>
                  )}
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
