'use client';

import { useState, useEffect } from 'react';
import { Scale, Bot, Send, Loader2, AlertTriangle, History } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';

const API_BASE = '/api/v1/juridico/consultor';

function getAuthHeaders() {
  const token = typeof window !== 'undefined' ? (localStorage.getItem('access_token') || localStorage.getItem('token')) : null;
  return { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) };
}

const AREAS = [
  { value: 'trabalhista', label: 'Trabalhista' },
  { value: 'civel', label: 'Cível' },
  { value: 'tributaria', label: 'Tributária' },
];

export default function ConsultorJuridicoPage() {
  const [area, setArea] = useState('trabalhista');
  const [pergunta, setPergunta] = useState('');
  const [loading, setLoading] = useState(false);
  const [resposta, setResposta] = useState<any>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [historico, setHistorico] = useState<any[]>([]);

  const carregarHistorico = async () => {
    try {
      const h = await fetch(`${API_BASE}/historico`, { headers: getAuthHeaders() })
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null);
      setHistorico((h?.consultas as any[]) || []);
    } catch { /* silencioso */ }
  };

  useEffect(() => { carregarHistorico(); }, []);

  const consultar = async () => {
    if (!pergunta.trim() || loading) return;
    setLoading(true);
    setErro(null);
    setResposta(null);
    try {
      const r = await fetch(`${API_BASE}/perguntar`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ area, pergunta }),
      });
      if (!r.ok) { setErro(`A IA não respondeu agora (HTTP ${r.status}). Tente novamente.`); return; }
      const data = await r.json();
      if (data?.indisponivel) { setErro('Consultor IA temporariamente indisponível.'); return; }
      setResposta(data);
      carregarHistorico();
    } catch {
      setErro('Falha de comunicação com o consultor IA. Tente novamente.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center gap-3">
        <Scale className="h-7 w-7 text-indigo-700" />
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Consultor Jurídico IA</h1>
          <p className="text-sm text-muted-foreground">Perguntas de direito trabalhista, cível e tributário — apoio, não parecer formal.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Coluna principal — chat */}
        <div className="lg:col-span-2 space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base"><Bot className="h-4 w-4 text-indigo-600" /> Nova consulta</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <label className="text-xs font-medium text-muted-foreground">Área</label>
                <div className="flex gap-2 mt-1">
                  {AREAS.map((a) => (
                    <button
                      key={a.value}
                      onClick={() => setArea(a.value)}
                      className={`px-3 py-1.5 rounded-md text-sm border transition-colors ${area === a.value ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'}`}
                    >
                      {a.label}
                    </button>
                  ))}
                </div>
              </div>
              <Textarea
                value={pergunta}
                onChange={(e) => setPergunta(e.target.value)}
                placeholder="Digite sua dúvida jurídica..."
                rows={4}
                disabled={loading}
              />
              <div className="flex justify-end">
                <Button onClick={consultar} disabled={loading || !pergunta.trim()}>
                  {loading ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Consultando...</> : <><Send className="h-4 w-4 mr-2" /> Consultar</>}
                </Button>
              </div>
              {loading && (
                <p className="text-xs text-muted-foreground text-center">A IA está analisando — isso pode levar de 10 a 30 segundos.</p>
              )}
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
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Resposta</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {resposta.escalonar && (
                  <div className="flex items-start gap-2 rounded-md border border-orange-300 bg-orange-50 px-3 py-2 text-sm text-orange-800">
                    <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
                    <span>Recomenda-se consultar o escritório para este caso.</span>
                  </div>
                )}

                <pre className="whitespace-pre-wrap font-sans text-sm text-gray-800 leading-relaxed">{resposta.resposta}</pre>

                {Array.isArray(resposta.fontes) && resposta.fontes.length > 0 && (
                  <div>
                    <div className="text-xs font-medium text-muted-foreground mb-1">Fontes</div>
                    <div className="flex flex-wrap gap-1.5">
                      {resposta.fontes.map((f: string, i: number) => (
                        <Badge key={i} variant="outline" className="text-xs">{f}</Badge>
                      ))}
                    </div>
                  </div>
                )}

                {resposta.disclaimer && (
                  <div className="border-t pt-3 text-xs text-muted-foreground italic">{resposta.disclaimer}</div>
                )}
              </CardContent>
            </Card>
          )}
        </div>

        {/* Coluna lateral — histórico */}
        <div>
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base"><History className="h-4 w-4 text-gray-500" /> Últimas consultas</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {historico.length === 0 ? (
                <p className="text-sm text-muted-foreground">Sem consultas registradas.</p>
              ) : (
                historico.map((h: any, i: number) => (
                  <div key={h.id ?? i} className="border rounded-md px-3 py-2 text-sm">
                    <div className="flex items-center justify-between gap-2 mb-1">
                      {h.area && <Badge variant="outline" className="text-xs capitalize">{h.area}</Badge>}
                      {h.escalonar && <Badge className="bg-orange-500 text-white text-xs">escalonada</Badge>}
                    </div>
                    <div className="text-gray-700 line-clamp-3">{h.pergunta || h.titulo || '—'}</div>
                    {(h.criado_em || h.data) && (
                      <div className="text-xs text-muted-foreground mt-1">{h.criado_em || h.data}</div>
                    )}
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
