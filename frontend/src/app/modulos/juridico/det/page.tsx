'use client';

import { useState, useEffect } from 'react';
import { msgFromDetail } from '@/lib/string';
import { ShieldCheck, Loader2, Upload, AlertTriangle, Landmark, FileText, RefreshCw, X } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

const API_BASE = '/api/v1/juridico/det';

function authHeaders(json = true) {
  const token = typeof window !== 'undefined' ? (localStorage.getItem('access_token') || localStorage.getItem('token')) : null;
  return { ...(json ? { 'Content-Type': 'application/json' } : {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) };
}

export default function DetPage() {
  const [status, setStatus] = useState<any>(null);
  const [lista, setLista] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [texto, setTexto] = useState('');
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [proc, setProc] = useState(false);
  const [res, setRes] = useState<any>(null);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = async () => {
    setLoading(true);
    try {
      const [s, c] = await Promise.all([
        fetch(`${API_BASE}/status`, { headers: authHeaders() }).then(r => r.json()).catch(() => null),
        fetch(`${API_BASE}/comunicacoes`, { headers: authHeaders() }).then(r => r.json()).catch(() => ({})),
      ]);
      setStatus(s); setLista(c?.comunicacoes || []);
    } finally { setLoading(false); }
  };
  useEffect(() => { carregar(); }, []);

  const processar = async () => {
    setErro(null); setRes(null); setProc(true);
    try {
      let r: Response;
      if (arquivo) {
        const fd = new FormData(); fd.append('arquivo', arquivo);
        r = await fetch(`${API_BASE}/comunicacao/upload`, { method: 'POST', headers: authHeaders(false), body: fd });
      } else {
        if (texto.trim().length < 30) { setErro('Cole o texto da comunicação (ou envie o PDF).'); setProc(false); return; }
        r = await fetch(`${API_BASE}/comunicacao`, { method: 'POST', headers: authHeaders(), body: JSON.stringify({ texto }) });
      }
      if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(msgFromDetail(e?.detail) || `HTTP ${r.status}`); }
      const d = await r.json();
      setRes(d); setTexto(''); setArquivo(null); carregar();
    } catch (e: any) { setErro(e?.message || 'Falha ao processar.'); }
    finally { setProc(false); }
  };

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <Landmark className="h-7 w-7 text-blue-700" />
        <div>
          <h1 className="font-display text-2xl font-bold">Monitoramento DET</h1>
          <p className="text-sm text-muted-foreground">Domicílio Eletrônico Trabalhista — comunicações e processos contra o CNPJ, tratados automaticamente.</p>
        </div>
      </div>

      {/* Status da conexão */}
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-green-600" /> Conexão (certificado A1)</CardTitle></CardHeader>
        <CardContent className="text-sm">
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : status?.certificado_ok ? (
            <div className="space-y-1">
              <div><b>Titular:</b> {status.titular}</div>
              <div><b>CNPJ:</b> {status.cnpj} · <b>Válido até:</b> {status.valido_ate?.slice(0, 10)} ({status.dias_para_expirar} dias)</div>
              <div className="flex items-center gap-2 mt-1">
                <Badge className="bg-amber-500 text-white">modo: ingestão assistida</Badge>
              </div>
              <div className="mt-2 rounded bg-amber-50 border border-amber-200 px-3 py-2 text-amber-800 text-xs">
                {status.explicacao}
              </div>
            </div>
          ) : <div className="text-red-600">{status?.mensagem || 'Certificado indisponível.'}</div>}
        </CardContent>
      </Card>

      {/* Ingestão de comunicação */}
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base">Registrar comunicação do DET</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <p className="text-xs text-muted-foreground">Baixe a comunicação/intimação no portal do DET e cole o texto ou envie o PDF. O sistema classifica, monta o dossiê e sinaliza o encaminhamento ao CQB automaticamente.</p>
          <textarea value={texto} onChange={e => setTexto(e.target.value)} rows={5} disabled={!!arquivo || proc}
            placeholder="Cole aqui o texto da comunicação/intimação do DET…"
            className="w-full border rounded px-3 py-2 text-sm font-mono disabled:bg-gray-100" />
          {arquivo && (
            <div className="flex items-center gap-2 text-sm bg-blue-50 border border-blue-200 rounded px-3 py-1.5">
              <FileText className="h-4 w-4 text-blue-600" /><span className="flex-1 truncate">{arquivo.name}</span>
              <button onClick={() => setArquivo(null)}><X className="h-4 w-4 text-gray-400" /></button>
            </div>
          )}
          <div className="flex items-center justify-between gap-2">
            <label className="flex items-center gap-1.5 text-sm border rounded px-3 py-2 cursor-pointer hover:bg-gray-50">
              <Upload className="h-4 w-4" /> Enviar PDF
              <input type="file" accept=".pdf,.txt" className="hidden" onChange={e => setArquivo(e.target.files?.[0] || null)} />
            </label>
            <Button onClick={processar} disabled={proc} className="bg-blue-600 hover:bg-blue-700 text-white">
              {proc ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Tratando…</> : 'Registrar e tratar'}
            </Button>
          </div>
          {erro && <div className="text-sm text-red-600 flex items-center gap-2"><AlertTriangle className="h-4 w-4" /> {erro}</div>}
          {res && (
            <div className="rounded border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-800">
              <b>{res.classificacao?.tipo || 'comunicação'}</b> — {res.proxima_acao}
              {res.processo_id && <> · dossiê #{res.processo_id}{res.escalonar && <Badge className="ml-2 bg-amber-500 text-white text-xs">escalar CQB</Badge>}</>}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Histórico */}
      <Card>
        <CardHeader className="pb-2 flex-row items-center justify-between">
          <CardTitle className="text-base">Comunicações recebidas</CardTitle>
          <button onClick={carregar} className="text-gray-400 hover:text-gray-700"><RefreshCw className="h-4 w-4" /></button>
        </CardHeader>
        <CardContent>
          {lista.length === 0 ? <p className="text-sm text-gray-400">Nenhuma comunicação registrada.</p> : (
            <div className="divide-y">
              {lista.map((c) => (
                <div key={c.id} className="py-2 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium">{c.titulo || c.numero || `Comunicação #${c.id}`}</span>
                    <div className="flex items-center gap-2">
                      {c.tipo && <Badge variant="outline" className="text-xs">{c.tipo}</Badge>}
                      {c.escalonar && <Badge className="bg-amber-500 text-white text-xs">escalar</Badge>}
                    </div>
                  </div>
                  {c.resumo && <div className="text-gray-600 text-xs mt-0.5">{c.resumo}</div>}
                  <div className="text-xs text-gray-400 mt-0.5">
                    {c.orgao && <>{c.orgao} · </>}{c.prazo && <>prazo: {c.prazo} · </>}{c.processo_id && <>dossiê #{c.processo_id} · </>}{c.status}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
