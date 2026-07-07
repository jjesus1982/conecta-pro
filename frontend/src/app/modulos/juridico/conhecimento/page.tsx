'use client';

import { useState, useEffect } from 'react';
import { BookOpen, Scale, ListChecks, Loader2, FileText } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

const API_BASE = '/api/v1/juridico';

function authHeaders() {
  const token = typeof window !== 'undefined' ? (localStorage.getItem('access_token') || localStorage.getItem('token')) : null;
  return { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) };
}

const areaBadge = (a: string) => {
  const c = a === 'trabalhista' ? 'bg-indigo-600' : a === 'civel' ? 'bg-emerald-600' : 'bg-amber-600';
  return <Badge className={`${c} text-white text-xs capitalize`}>{a}</Badge>;
};

export default function ConhecimentoPage() {
  const [conh, setConh] = useState<any[]>([]);
  const [play, setPlay] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<'precedentes' | 'playbook'>('precedentes');

  useEffect(() => {
    (async () => {
      try {
        const [c, p] = await Promise.all([
          fetch(`${API_BASE}/conhecimento`, { headers: authHeaders() }).then(r => r.json()).catch(() => ({})),
          fetch(`${API_BASE}/playbook`, { headers: authHeaders() }).then(r => r.json()).catch(() => ({})),
        ]);
        setConh(c?.conhecimento || []);
        setPlay(p?.playbook || []);
      } finally { setLoading(false); }
    })();
  }, []);

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <BookOpen className="h-7 w-7 text-indigo-700" />
        <div>
          <h1 className="font-display text-2xl font-bold">Base de Conhecimento & Playbook</h1>
          <p className="text-sm text-muted-foreground">A memória jurídica da Conecta Mais — precedentes reais e os procedimentos de como agir. O Consultor e a análise de processos consultam isto automaticamente.</p>
        </div>
      </div>

      <div className="flex gap-2">
        <button onClick={() => setTab('precedentes')} className={`px-4 py-2 rounded-md text-sm border ${tab === 'precedentes' ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-white text-gray-700'}`}>
          <Scale className="h-4 w-4 inline mr-1" /> Precedentes ({conh.length})
        </button>
        <button onClick={() => setTab('playbook')} className={`px-4 py-2 rounded-md text-sm border ${tab === 'playbook' ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-white text-gray-700'}`}>
          <ListChecks className="h-4 w-4 inline mr-1" /> Playbook ({play.length})
        </button>
      </div>

      {loading ? (
        <div className="text-sm text-gray-400 flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin" /> carregando…</div>
      ) : tab === 'precedentes' ? (
        <div className="space-y-3">
          {conh.length === 0 && <p className="text-sm text-gray-400">Base ainda vazia.</p>}
          {conh.map((k) => (
            <Card key={k.id}>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center justify-between gap-2">
                  <span>{k.titulo}</span>{areaBadge(k.area)}
                </CardTitle>
              </CardHeader>
              <CardContent className="text-sm space-y-2">
                {k.resumo && <p className="text-gray-700">{k.resumo}</p>}
                {k.fundamentacao && <div><span className="font-medium text-gray-600">Fundamentação: </span>{k.fundamentacao}</div>}
                {k.desfecho && <div><span className="font-medium text-gray-600">Desfecho: </span>{k.desfecho}</div>}
                {k.fonte && <div className="text-xs text-gray-400 flex items-center gap-1"><FileText className="h-3 w-3" /> {k.fonte}</div>}
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <div className="space-y-3">
          {play.length === 0 && <p className="text-sm text-gray-400">Playbook ainda vazio.</p>}
          {play.map((p) => (
            <Card key={p.id}>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center justify-between gap-2">
                  <span>{p.situacao}</span>{areaBadge(p.area)}
                </CardTitle>
              </CardHeader>
              <CardContent className="text-sm space-y-2">
                {Array.isArray(p.passos) && (
                  <ol className="list-decimal ml-5 space-y-1 text-gray-700">
                    {p.passos.map((s: string, i: number) => <li key={i}>{s}</li>)}
                  </ol>
                )}
                {p.base_legal && <div><span className="font-medium text-gray-600">Base legal: </span>{p.base_legal}</div>}
                {Array.isArray(p.documentos) && p.documentos.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {p.documentos.map((d: string, i: number) => <Badge key={i} variant="outline" className="text-xs">{d}</Badge>)}
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
