'use client';

import { useState, useEffect } from 'react';
import { msgFromDetail } from '@/lib/string';
import { ScanSearch, FileSearch, Loader2, ShieldAlert, AlertTriangle, CheckCircle2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Button } from '@/components/ui/button';

const API_BASE = '/api/v1/juridico';

function getAuthHeaders() {
  const token = typeof window !== 'undefined' ? (localStorage.getItem('access_token') || localStorage.getItem('token')) : null;
  return { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) };
}

const riscoBadge = (risco: string) => {
  const r = (risco || '').toLowerCase();
  if (r === 'alto') return <Badge className="bg-red-600 text-white">alto</Badge>;
  if (r === 'medio') return <Badge className="bg-yellow-500 text-white">médio</Badge>;
  return <Badge className="bg-green-600 text-white">baixo</Badge>;
};

const scoreColor = (s: number) => {
  if (s >= 70) return 'text-red-600';
  if (s >= 40) return 'text-yellow-600';
  return 'text-green-600';
};

export default function AnaliseContratoPage() {
  const [historico, setHistorico] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  const [nome, setNome] = useState('');
  const [conteudo, setConteudo] = useState('');
  const [analisando, setAnalisando] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [resultado, setResultado] = useState<any>(null);

  const carregar = async () => {
    setLoading(true);
    setErro(null);
    try {
      const r = await fetch(`${API_BASE}/analises`, { headers: getAuthHeaders() });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      setHistorico((d?.analises as any[]) || []);
    } catch (e: any) {
      setErro('Não foi possível carregar o histórico de análises.');
      setHistorico([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    carregar();
  }, []);

  const analisar = async () => {
    if (nome.trim().length < 1 || conteudo.trim().length < 20) {
      setFeedback('Informe o nome do contrato e cole o texto (mín. 20 caracteres).');
      return;
    }
    setAnalisando(true);
    setFeedback(null);
    setResultado(null);
    try {
      const r = await fetch(`${API_BASE}/analises`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ nome, conteudo }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(msgFromDetail(d?.detail) || `HTTP ${r.status}`);
      setResultado(d);
      if (d?.ia_disponivel === false) {
        setFeedback(d?.mensagem || 'IA indisponível — o pedido foi registrado.');
      }
      await carregar();
    } catch (e: any) {
      setFeedback(`Falha ao analisar contrato: ${e.message}`);
    } finally {
      setAnalisando(false);
    }
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center gap-3">
        <ScanSearch className="h-7 w-7 text-blue-700" />
        <div>
          <h1 className="font-display text-2xl font-bold text-[hsl(var(--foreground))]">Análise de Contrato IA</h1>
          <p className="text-sm text-muted-foreground">Revisão cláusula-a-cláusula contra o playbook da empresa.</p>
        </div>
      </div>

      {/* Disclaimer */}
      <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
        <ShieldAlert className="h-4 w-4 mt-0.5 shrink-0" />
        <span>
          Análise assistida por IA, de caráter opinativo. NÃO substitui a revisão de advogado habilitado (OAB). A
          certificação final é do responsável jurídico.
        </span>
      </div>

      {/* Form */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <FileSearch className="h-4 w-4 text-blue-600" /> Analisar novo contrato
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="text-sm font-medium">Nome / identificação do contrato</label>
            <input
              className="mt-1 w-full border rounded-md px-3 py-2 text-sm"
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              placeholder="Ex.: Contrato de portaria — Condomínio Aurora"
            />
          </div>
          <div>
            <label className="text-sm font-medium">Texto integral do contrato</label>
            <textarea
              className="mt-1 w-full border rounded-md px-3 py-2 text-sm min-h-[240px] font-mono"
              value={conteudo}
              onChange={(e) => setConteudo(e.target.value)}
              placeholder="Cole aqui o texto completo do contrato a revisar…"
            />
          </div>
          <Button onClick={analisar} disabled={analisando}>
            {analisando ? (
              <>
                <Loader2 className="h-4 w-4 mr-1 animate-spin" /> Analisando cláusula-a-cláusula (pode demorar)…
              </>
            ) : (
              'Analisar contrato'
            )}
          </Button>
          {feedback && <div className="text-sm text-blue-800">{feedback}</div>}
        </CardContent>
      </Card>

      {/* Resultado */}
      {resultado && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Card>
              <CardContent className="pt-6">
                <div className="text-xs text-muted-foreground">Score de risco</div>
                <div className={`text-4xl font-bold mt-1 ${scoreColor(resultado.score_risco || 0)}`}>
                  {resultado.score_risco ?? 0}
                  <span className="text-lg text-muted-foreground">/100</span>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="text-xs text-muted-foreground">Cláusulas críticas</div>
                <div className="text-4xl font-bold mt-1 text-red-600 flex items-center gap-2">
                  <AlertTriangle className="h-7 w-7" /> {resultado.clausulas_criticas ?? 0}
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="text-xs text-muted-foreground">Cláusulas analisadas</div>
                <div className="text-4xl font-bold mt-1 text-blue-600">
                  {(resultado.clausulas || []).length}
                </div>
              </CardContent>
            </Card>
          </div>

          {resultado.resumo && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Parecer geral</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm whitespace-pre-wrap">{resultado.resumo}</p>
              </CardContent>
            </Card>
          )}

          {(resultado.clausulas || []).length === 0 ? (
            <Card>
              <CardContent className="pt-6 text-sm text-muted-foreground">
                Nenhuma cláusula retornada — verifique se a IA está disponível ou revise o texto enviado.
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {resultado.clausulas.map((c: any, i: number) => {
                const r = (c.risco || '').toLowerCase();
                const border =
                  r === 'alto' ? 'border-l-red-500' : r === 'medio' ? 'border-l-yellow-500' : 'border-l-green-500';
                return (
                  <Card key={i} className={`border-l-4 ${border}`}>
                    <CardContent className="pt-4 space-y-2">
                      <div className="flex items-center justify-between">
                        <div className="font-semibold capitalize">{c.clausula}</div>
                        {riscoBadge(c.risco)}
                      </div>
                      {c.avaliacao && <p className="text-sm text-gray-700">{c.avaliacao}</p>}
                      {c.sugestao && (
                        <div className="flex items-start gap-2 text-sm text-blue-800 bg-blue-50 rounded-md px-3 py-2">
                          <CheckCircle2 className="h-4 w-4 mt-0.5 shrink-0" />
                          <span><b>Sugestão:</b> {c.sugestao}</span>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Histórico */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Histórico de análises ({historico.length})</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center h-32">
              <Loader2 className="h-6 w-6 animate-spin" />
            </div>
          ) : erro ? (
            <div className="text-sm text-red-600">{erro}</div>
          ) : historico.length === 0 ? (
            <div className="text-sm text-muted-foreground py-8 text-center">
              Nenhuma análise realizada ainda.
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Contrato</TableHead>
                  <TableHead>Score</TableHead>
                  <TableHead>Cláusulas críticas</TableHead>
                  <TableHead>Analisado em</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {historico.map((a) => (
                  <TableRow key={a.id}>
                    <TableCell className="font-medium">{a.nome}</TableCell>
                    <TableCell>
                      <span className={`font-bold ${scoreColor(a.score_risco || 0)}`}>{a.score_risco ?? 0}</span>
                      <span className="text-muted-foreground">/100</span>
                    </TableCell>
                    <TableCell>{a.clausulas_criticas ?? 0}</TableCell>
                    <TableCell className="text-sm">{a.created_at ? new Date(a.created_at).toLocaleString('pt-BR') : '—'}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
