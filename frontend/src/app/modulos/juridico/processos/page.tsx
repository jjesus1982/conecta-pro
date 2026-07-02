'use client';

import { useState, useEffect } from 'react';
import { Scale, AlertTriangle, Loader2, Upload, FileText, ShieldCheck, ShieldAlert, Search, CheckCircle2, XCircle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

const API_BASE = '/api/v1/juridico';

function authHeaders(json = true) {
  const token = typeof window !== 'undefined' ? (localStorage.getItem('access_token') || localStorage.getItem('token')) : null;
  return { ...(json ? { 'Content-Type': 'application/json' } : {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) };
}

const TIPOS = [
  { value: 'trabalhista', label: 'Trabalhista' },
  { value: 'civel', label: 'Cível' },
  { value: 'tributaria', label: 'Tributária' },
];

function riscoBadge(r: string) {
  const v = (r || '').toLowerCase();
  if (v === 'alto') return <Badge className="bg-red-600 text-white">risco alto</Badge>;
  if (v === 'medio' || v === 'médio') return <Badge className="bg-amber-500 text-white">risco médio</Badge>;
  if (v === 'baixo') return <Badge className="bg-green-600 text-white">risco baixo</Badge>;
  return <Badge variant="outline">{r || '—'}</Badge>;
}

export default function ProcessosPage() {
  const [lista, setLista] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const [tipo, setTipo] = useState('trabalhista');
  const [numero, setNumero] = useState('');
  const [employeeId, setEmployeeId] = useState('');
  const [texto, setTexto] = useState('');
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [analisando, setAnalisando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [res, setRes] = useState<any | null>(null);

  const carregar = async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API_BASE}/processos`, { headers: authHeaders() });
      const d = await r.json();
      setLista((d?.processos as any[]) || []);
    } catch { setLista([]); } finally { setLoading(false); }
  };
  useEffect(() => { carregar(); }, []);

  const analisar = async () => {
    setErro(null); setRes(null); setAnalisando(true);
    try {
      let r: Response;
      if (arquivo) {
        const fd = new FormData();
        fd.append('arquivo', arquivo);
        if (numero) fd.append('numero', numero);
        fd.append('tipo', tipo);
        if (employeeId) fd.append('employee_id', employeeId);
        r = await fetch(`${API_BASE}/processos/upload`, { method: 'POST', headers: authHeaders(false), body: fd });
      } else {
        if (texto.trim().length < 40) { setErro('Cole o texto do processo (ou envie o PDF).'); setAnalisando(false); return; }
        r = await fetch(`${API_BASE}/processos`, {
          method: 'POST', headers: authHeaders(),
          body: JSON.stringify({ texto, numero: numero || null, tipo, employee_id: employeeId || null }),
        });
      }
      if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e?.detail || `HTTP ${r.status}`); }
      const d = await r.json();
      setRes(d);
      carregar();
    } catch (e: any) {
      setErro(e?.message || 'Falha na análise.');
    } finally { setAnalisando(false); }
  };

  const [enviando, setEnviando] = useState(false);
  const [envioMsg, setEnvioMsg] = useState<string | null>(null);
  const [destinoCQB, setDestinoCQB] = useState('contato@cqbadvogados.com.br');

  const encaminharCQB = async () => {
    if (!res?.id) return;
    if (!window.confirm(`Encaminhar este processo (dossiê + defesa) para:\n\n${destinoCQB}\n\nConfirmar envio?`)) return;
    setEnviando(true); setEnvioMsg(null);
    try {
      const r = await fetch(`${API_BASE}/processos/${res.id}/enviar-cqb`, {
        method: 'POST', headers: authHeaders(),
        body: JSON.stringify({ confirmar: true, destinatario: destinoCQB }),
      });
      const d = await r.json();
      if (!r.ok || !d.enviado) throw new Error(d?.detail || d?.mensagem || 'Falha no envio');
      setEnvioMsg(`✅ Encaminhado para ${d.destinatario}`);
    } catch (e: any) {
      setEnvioMsg(`❌ ${e?.message || 'Falha no envio'}`);
    } finally { setEnviando(false); }
  };

  const analise = res?.analise || {};

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <Scale className="w-7 h-7 text-blue-600" />
        <div>
          <h1 className="text-2xl font-bold">Processos &amp; Defesa</h1>
          <p className="text-sm text-gray-500">Suba o processo — o Escritório Jurídico IA investiga o ERP inteiro e monta a análise de defesa com base no dado real.</p>
        </div>
      </div>

      {/* Formulário */}
      <Card>
        <CardHeader><CardTitle className="text-base flex items-center gap-2"><Search className="w-4 h-4" /> Novo processo</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <label className="text-xs text-gray-500">Área</label>
              <select value={tipo} onChange={e => setTipo(e.target.value)} className="w-full border rounded px-2 py-2 text-sm">
                {TIPOS.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-500">Nº do processo (opcional)</label>
              <input value={numero} onChange={e => setNumero(e.target.value)} placeholder="0001234-56.2026.5.11.0001" className="w-full border rounded px-2 py-2 text-sm" />
            </div>
            <div>
              <label className="text-xs text-gray-500">ID do funcionário (opcional, se nome ambíguo)</label>
              <input value={employeeId} onChange={e => setEmployeeId(e.target.value)} placeholder="uuid do funcionário" className="w-full border rounded px-2 py-2 text-sm" />
            </div>
          </div>

          <div>
            <label className="text-xs text-gray-500">Texto do processo (cole a petição) — ou envie o PDF abaixo</label>
            <textarea value={texto} onChange={e => setTexto(e.target.value)} rows={6} disabled={!!arquivo}
              placeholder="Cole aqui o inteiro teor / petição inicial do processo…"
              className="w-full border rounded px-3 py-2 text-sm font-mono disabled:bg-gray-100" />
          </div>

          <div className="flex items-center gap-3 flex-wrap">
            <label className="flex items-center gap-2 text-sm border rounded px-3 py-2 cursor-pointer hover:bg-gray-50">
              <Upload className="w-4 h-4" />
              {arquivo ? arquivo.name : 'Enviar PDF do processo'}
              <input type="file" accept=".pdf,.txt" className="hidden" onChange={e => setArquivo(e.target.files?.[0] || null)} />
            </label>
            {arquivo && <Button variant="ghost" size="sm" onClick={() => setArquivo(null)}>remover arquivo</Button>}
            <div className="flex-1" />
            <Button onClick={analisar} disabled={analisando} className="bg-blue-600 hover:bg-blue-700 text-white">
              {analisando ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Investigando o ERP…</> : <><Search className="w-4 h-4 mr-2" /> Analisar defesa</>}
            </Button>
          </div>
          {erro && <div className="text-sm text-red-600 flex items-center gap-2"><AlertTriangle className="w-4 h-4" /> {erro}</div>}
        </CardContent>
      </Card>

      {/* Resultado */}
      {res && (
        <div className="space-y-4">
          {/* Cabeçalho do resultado */}
          <Card className={res.escalonar ? 'border-amber-400' : ''}>
            <CardContent className="pt-4">
              <div className="flex flex-wrap items-center gap-3">
                <Badge className="bg-blue-600 text-white uppercase">{res.tipo}</Badge>
                {res.escalonar
                  ? <Badge className="bg-amber-500 text-white flex items-center gap-1"><ShieldAlert className="w-3 h-3" /> escalar ao escritório</Badge>
                  : <Badge className="bg-green-600 text-white flex items-center gap-1"><ShieldCheck className="w-3 h-3" /> tratável internamente</Badge>}
                {res.status === 'sujeito_nao_localizado' && <Badge className="bg-gray-400 text-white">parte não localizada no ERP</Badge>}
              </div>
              <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-2 text-sm">
                <div><span className="text-gray-500">Reclamante: </span><b>{res.entidades?.reclamante || '—'}</b></div>
                <div><span className="text-gray-500">No ERP: </span><b>{res.funcionario?.nome || '—'}</b> {res.funcionario?.cargo ? `(${res.funcionario.cargo})` : ''}</div>
                <div><span className="text-gray-500">Dossiê: </span><b>{res.dossie?.sintese?.cobertura || '—'}</b></div>
              </div>
              {res.entidades?.pedidos?.length > 0 && (
                <div className="mt-2 text-sm"><span className="text-gray-500">Pedidos: </span>{res.entidades.pedidos.join(' · ')}</div>
              )}
            </CardContent>
          </Card>

          {/* Análise por pedido */}
          {(analise.por_pedido || []).map((p: any, i: number) => (
            <Card key={i}>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center justify-between">
                  <span>{p.pedido}</span> {riscoBadge(p.risco)}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                {p.provas_favoraveis?.length > 0 && (
                  <div>
                    <div className="font-medium text-green-700 flex items-center gap-1"><CheckCircle2 className="w-4 h-4" /> Provas favoráveis</div>
                    <ul className="list-disc ml-6 text-gray-700">{p.provas_favoraveis.map((x: string, j: number) => <li key={j}>{x}</li>)}</ul>
                  </div>
                )}
                {p.provas_faltantes?.length > 0 && (
                  <div>
                    <div className="font-medium text-red-700 flex items-center gap-1"><XCircle className="w-4 h-4" /> Lacunas / a produzir</div>
                    <ul className="list-disc ml-6 text-gray-700">{p.provas_faltantes.map((x: string, j: number) => <li key={j}>{x}</li>)}</ul>
                  </div>
                )}
                {p.recomendacao && <div className="text-gray-800 bg-blue-50 rounded px-3 py-2"><b>Recomendação: </b>{p.recomendacao}</div>}
              </CardContent>
            </Card>
          ))}

          {/* Estratégia + docs + síntese */}
          {(analise.estrategia_geral || analise.documentos_a_juntar || analise.sintese) && (
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-2"><FileText className="w-4 h-4" /> Estratégia de defesa</CardTitle></CardHeader>
              <CardContent className="space-y-3 text-sm">
                {analise.estrategia_geral && <div><div className="font-medium">Tese central</div><p className="text-gray-700 whitespace-pre-line">{analise.estrategia_geral}</p></div>}
                {analise.documentos_a_juntar?.length > 0 && (
                  <div>
                    <div className="font-medium">Documentos a juntar</div>
                    <ul className="list-disc ml-6 text-gray-700">{analise.documentos_a_juntar.map((x: string, j: number) => <li key={j}>{x}</li>)}</ul>
                  </div>
                )}
                {analise.sintese && <div><div className="font-medium">Síntese</div><p className="text-gray-700 whitespace-pre-line">{analise.sintese}</p></div>}
              </CardContent>
            </Card>
          )}

          {/* Encaminhar ao CQB */}
          <Card className="border-blue-200">
            <CardContent className="pt-4 flex flex-wrap items-center gap-3">
              <div className="text-sm">
                <div className="font-medium">Encaminhar ao escritório (CQB Advogados)</div>
                <div className="text-gray-500">Envia o dossiê + defesa por e-mail (remetente noreply@conectamais.pro).</div>
              </div>
              <div className="flex-1" />
              <input value={destinoCQB} onChange={e => setDestinoCQB(e.target.value)}
                className="border rounded px-2 py-2 text-sm w-64" placeholder="destinatário" />
              <Button onClick={encaminharCQB} disabled={enviando} className="bg-blue-600 hover:bg-blue-700 text-white">
                {enviando ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Enviando…</> : <><FileText className="w-4 h-4 mr-2" /> Encaminhar</>}
              </Button>
              {envioMsg && <div className="w-full text-sm mt-1">{envioMsg}</div>}
            </CardContent>
          </Card>

          {res.disclaimer && <p className="text-xs text-gray-400 border-t pt-2">{res.disclaimer}</p>}
        </div>
      )}

      {/* Histórico */}
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base">Processos analisados</CardTitle></CardHeader>
        <CardContent>
          {loading ? <div className="text-sm text-gray-400 flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin" /> carregando…</div>
            : lista.length === 0 ? <div className="text-sm text-gray-400">Nenhum processo analisado ainda.</div>
            : (
              <div className="divide-y">
                {lista.map((p) => (
                  <div key={p.id} className="py-2 flex items-center justify-between text-sm">
                    <div>
                      <span className="font-medium">{p.numero || `Processo #${p.id}`}</span>
                      <span className="text-gray-500"> · {p.reclamante || '—'} · {p.tipo}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      {p.escalonar && <Badge className="bg-amber-500 text-white text-xs">escalar</Badge>}
                      <Badge variant="outline" className="text-xs">{p.status}</Badge>
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
