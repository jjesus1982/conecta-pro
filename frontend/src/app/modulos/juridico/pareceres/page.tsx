'use client';

import { useState, useEffect } from 'react';
import { msgFromDetail } from '@/lib/string';
import { Scale, FileText, AlertTriangle, Loader2, Plus, Download, ShieldAlert } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Button } from '@/components/ui/button';

const API_BASE = '/api/v1/juridico';

function getAuthHeaders() {
  const token = typeof window !== 'undefined' ? (localStorage.getItem('access_token') || localStorage.getItem('token')) : null;
  return { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) };
}

const AREAS = [
  { value: 'trabalhista', label: 'Trabalhista' },
  { value: 'civel', label: 'Cível' },
  { value: 'tributaria', label: 'Tributária' },
];

const statusBadge = (s: string) => {
  if (s === 'rascunho') return <Badge className="bg-blue-500 text-white">rascunho</Badge>;
  if (s === 'ia_indisponivel') return <Badge className="bg-gray-400 text-white">IA indisponível</Badge>;
  if (s === 'aprovado' || s === 'certificado') return <Badge className="bg-green-600 text-white">{s}</Badge>;
  return <Badge variant="outline">{s || '—'}</Badge>;
};

export default function PareceresPage() {
  const [pareceres, setPareceres] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  const [showForm, setShowForm] = useState(false);
  const [area, setArea] = useState('trabalhista');
  const [titulo, setTitulo] = useState('');
  const [contexto, setContexto] = useState('');
  const [gerando, setGerando] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [baixando, setBaixando] = useState<number | null>(null);

  const carregar = async () => {
    setLoading(true);
    setErro(null);
    try {
      const r = await fetch(`${API_BASE}/pareceres`, { headers: getAuthHeaders() });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      setPareceres((d?.pareceres as any[]) || []);
    } catch (e: any) {
      setErro('Não foi possível carregar os pareceres.');
      setPareceres([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    carregar();
  }, []);

  const gerar = async () => {
    if (titulo.trim().length < 3 || contexto.trim().length < 10) {
      setFeedback('Preencha título (mín. 3 caracteres) e contexto (mín. 10 caracteres).');
      return;
    }
    setGerando(true);
    setFeedback(null);
    try {
      const r = await fetch(`${API_BASE}/pareceres`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ area, titulo, contexto }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(msgFromDetail(d?.detail) || `HTTP ${r.status}`);
      if (d?.ia_disponivel === false) {
        setFeedback(d?.mensagem || 'IA indisponível — o pedido foi registrado.');
      } else {
        setFeedback('Parecer gerado como rascunho. A IA fundamenta, o humano certifica.');
      }
      setTitulo('');
      setContexto('');
      setShowForm(false);
      await carregar();
    } catch (e: any) {
      setFeedback(`Falha ao gerar parecer: ${e.message}`);
    } finally {
      setGerando(false);
    }
  };

  const baixarPdf = async (id: number) => {
    setBaixando(id);
    try {
      const r = await fetch(`${API_BASE}/pareceres/${id}/pdf`, { headers: getAuthHeaders() });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      window.open(url, '_blank');
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (e: any) {
      setFeedback(`Falha ao baixar PDF: ${e.message}`);
    } finally {
      setBaixando(null);
    }
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Scale className="h-7 w-7 text-blue-700" />
          <div>
            <h1 className="font-display text-2xl font-bold text-[hsl(var(--foreground))]">Pareceres Jurídicos IA</h1>
            <p className="text-sm text-muted-foreground">A IA fundamenta, o humano certifica — rascunhos opinativos.</p>
          </div>
        </div>
        <Button onClick={() => setShowForm((v) => !v)}>
          <Plus className="h-4 w-4 mr-1" /> Novo Parecer
        </Button>
      </div>

      {/* Disclaimer */}
      <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
        <ShieldAlert className="h-4 w-4 mt-0.5 shrink-0" />
        <span>
          Pareceres gerados com apoio de IA têm caráter meramente opinativo e NÃO substituem a análise e certificação de
          advogado habilitado (OAB). Nenhuma norma ou jurisprudência deve ser considerada válida sem conferência na fonte oficial.
        </span>
      </div>

      {feedback && (
        <div className="rounded-md border bg-blue-50 border-blue-200 px-4 py-2 text-sm text-blue-800">{feedback}</div>
      )}

      {/* Form */}
      {showForm && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <FileText className="h-4 w-4 text-blue-600" /> Novo parecer
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="text-sm font-medium">Área</label>
                <select
                  className="mt-1 w-full border rounded-md px-3 py-2 text-sm bg-white"
                  value={area}
                  onChange={(e) => setArea(e.target.value)}
                >
                  {AREAS.map((a) => (
                    <option key={a.value} value={a.value}>{a.label}</option>
                  ))}
                </select>
              </div>
              <div className="md:col-span-2">
                <label className="text-sm font-medium">Título / assunto</label>
                <input
                  className="mt-1 w-full border rounded-md px-3 py-2 text-sm"
                  value={titulo}
                  onChange={(e) => setTitulo(e.target.value)}
                  placeholder="Ex.: Legalidade da jornada 12x36 para agentes de portaria"
                />
              </div>
            </div>
            <div>
              <label className="text-sm font-medium">Contexto — fatos e questão posta</label>
              <textarea
                className="mt-1 w-full border rounded-md px-3 py-2 text-sm min-h-[140px]"
                value={contexto}
                onChange={(e) => setContexto(e.target.value)}
                placeholder="Descreva os fatos, o cenário e a questão jurídica a ser respondida."
              />
            </div>
            <div className="flex items-center gap-2">
              <Button onClick={gerar} disabled={gerando}>
                {gerando ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-1 animate-spin" /> Gerando parecer (pode demorar)…
                  </>
                ) : (
                  'Gerar parecer'
                )}
              </Button>
              <Button variant="outline" onClick={() => setShowForm(false)} disabled={gerando}>
                Cancelar
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Lista */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Pareceres ({pareceres.length})</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center h-32">
              <Loader2 className="h-6 w-6 animate-spin" />
            </div>
          ) : erro ? (
            <div className="text-sm text-red-600">{erro}</div>
          ) : pareceres.length === 0 ? (
            <div className="text-sm text-muted-foreground py-8 text-center">
              Nenhum parecer emitido ainda. Clique em “Novo Parecer”.
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Título</TableHead>
                  <TableHead>Área</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Escalonamento</TableHead>
                  <TableHead>Criado em</TableHead>
                  <TableHead className="text-right">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {pareceres.map((p) => (
                  <TableRow key={p.id}>
                    <TableCell className="font-medium">{p.titulo}</TableCell>
                    <TableCell className="capitalize">{p.area}</TableCell>
                    <TableCell>{statusBadge(p.status)}</TableCell>
                    <TableCell>
                      {p.escalonar ? (
                        <Badge className="bg-orange-500 text-white flex items-center gap-1 w-fit">
                          <AlertTriangle className="h-3 w-3" /> escalonar
                        </Badge>
                      ) : (
                        <span className="text-muted-foreground text-sm">—</span>
                      )}
                    </TableCell>
                    <TableCell className="text-sm">{p.created_at ? new Date(p.created_at).toLocaleString('pt-BR') : '—'}</TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => baixarPdf(p.id)}
                        disabled={baixando === p.id}
                      >
                        {baixando === p.id ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <>
                            <Download className="h-4 w-4 mr-1" /> Baixar PDF
                          </>
                        )}
                      </Button>
                    </TableCell>
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
