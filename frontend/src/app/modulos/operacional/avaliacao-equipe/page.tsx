'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import {
  ArrowDownRight,
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  Check,
  MessageSquarePlus,
  RefreshCw,
  Star,
  Users,
} from 'lucide-react';
import { toast } from 'sonner';
import { api } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';

// ── Tipos ────────────────────────────────────────────────────────────────────
interface MembroEquipe {
  employee_id: string;
  nome: string;
  cargo?: string;
  post_id?: string;
}

interface Consolidado {
  employee_id: string;
  nome: string;
  cargo?: string;
  media?: number | null;
  total_avaliacoes?: number;
  tendencia?: string | null;
  ultima_nota?: number | null;
  ultima_em?: string | null;
}

function Tendencia({ valor }: { valor?: string | null }) {
  const v = (valor || '').toLowerCase();
  if (v.includes('sub') || v.includes('up') || v.includes('alta') || v.includes('melhor')) {
    return <ArrowUpRight className="h-4 w-4 text-green-600" aria-label="Em alta" />;
  }
  if (v.includes('desc') || v.includes('down') || v.includes('queda') || v.includes('baixa') || v.includes('pior')) {
    return <ArrowDownRight className="h-4 w-4 text-red-600" aria-label="Em queda" />;
  }
  return <ArrowRight className="h-4 w-4 text-muted-foreground" aria-label="Estável" />;
}

export default function AvaliacaoEquipePage() {
  const [equipe, setEquipe] = useState<MembroEquipe[]>([]);
  const [consolidado, setConsolidado] = useState<Consolidado[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erroCarga, setErroCarga] = useState<string | null>(null);

  // Estado por funcionário
  const [notas, setNotas] = useState<Record<string, number>>({});
  const [obs, setObs] = useState<Record<string, string>>({});
  const [obsAberta, setObsAberta] = useState<Record<string, boolean>>({});
  const [enviandoId, setEnviandoId] = useState<string | null>(null);
  const [avaliadosHoje, setAvaliadosHoje] = useState<Record<string, number>>({});

  const carregar = useCallback(async () => {
    setCarregando(true);
    setErroCarga(null);
    try {
      const [eq, cons] = await Promise.allSettled([
        api.get('/api/v1/operacional/avaliacoes/equipe'),
        api.get('/api/v1/operacional/avaliacoes/consolidado', { params: { dias: 30 } }),
      ]);
      if (eq.status === 'fulfilled') {
        const lista = Array.isArray(eq.value.data) ? eq.value.data : eq.value.data?.items || [];
        setEquipe(lista);
      } else {
        const e = eq.reason as { response?: { status?: number } };
        setErroCarga(
          e?.response?.status === 403
            ? 'Sem permissão para avaliar equipe.'
            : 'Não foi possível carregar a equipe.',
        );
      }
      if (cons.status === 'fulfilled') {
        const lista = Array.isArray(cons.value.data) ? cons.value.data : cons.value.data?.items || [];
        setConsolidado(lista);
      }
    } finally {
      setCarregando(false);
    }
  }, []);

  useEffect(() => {
    carregar();
  }, [carregar]);

  const avaliar = async (m: MembroEquipe) => {
    const nota = notas[m.employee_id];
    if (!nota) {
      toast.error(`Escolha a nota de ${m.nome.split(' ')[0]} (1 a 5 estrelas)`);
      return;
    }
    setEnviandoId(m.employee_id);
    try {
      const payload: Record<string, unknown> = { employee_id: m.employee_id, nota };
      const observacao = (obs[m.employee_id] || '').trim();
      if (observacao) payload.observacao = observacao;
      if (m.post_id) payload.post_id = m.post_id;
      await api.post('/api/v1/operacional/avaliacoes/', payload);
      setAvaliadosHoje((prev) => ({ ...prev, [m.employee_id]: nota }));
      toast.success(`${m.nome.split(' ')[0]} avaliado com nota ${nota}`);
      // Atualiza o consolidado em segundo plano
      api
        .get('/api/v1/operacional/avaliacoes/consolidado', { params: { dias: 30 } })
        .then((res) => {
          const lista = Array.isArray(res.data) ? res.data : res.data?.items || [];
          setConsolidado(lista);
        })
        .catch(() => undefined);
    } catch (err: unknown) {
      const e = err as { response?: { status?: number; data?: { detail?: unknown } } };
      if (e.response?.status === 403) {
        toast.error('Sem permissão para avaliar este funcionário.');
      } else {
        const detail = e.response?.data?.detail;
        toast.error(typeof detail === 'string' ? detail : 'Erro ao registrar a avaliação.');
      }
    } finally {
      setEnviandoId(null);
    }
  };

  return (
    <div className="mx-auto w-full max-w-lg space-y-4 p-4 pb-24">
      <div className="flex items-center gap-2">
        <Link href="/modulos/operacional">
          <Button variant="ghost" size="icon" aria-label="Voltar">
            <ArrowLeft className="h-5 w-5" />
          </Button>
        </Link>
        <div className="flex-1">
          <h1 className="flex items-center gap-2 text-xl font-bold">
            <Users className="h-5 w-5 text-cyan-600" />
            Avaliação de Equipe
          </h1>
          <p className="text-sm text-muted-foreground">Nota diária de 1 a 5 estrelas por funcionário</p>
        </div>
        <Button variant="ghost" size="icon" aria-label="Atualizar" onClick={carregar} disabled={carregando}>
          <RefreshCw className={`h-4 w-4 ${carregando ? 'animate-spin' : ''}`} />
        </Button>
      </div>

      {erroCarga && (
        <Card>
          <CardContent className="py-6 text-center text-sm text-muted-foreground">{erroCarga}</CardContent>
        </Card>
      )}

      {/* Equipe */}
      {carregando ? (
        <Card>
          <CardContent className="py-6 text-center text-sm text-muted-foreground">Carregando equipe…</CardContent>
        </Card>
      ) : equipe.length === 0 && !erroCarga ? (
        <Card>
          <CardContent className="py-6 text-center text-sm text-muted-foreground">
            Nenhum funcionário vinculado ao seu acesso.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {equipe.map((m) => {
            const notaAtual = notas[m.employee_id] || 0;
            const avaliadoCom = avaliadosHoje[m.employee_id];
            return (
              <Card key={m.employee_id}>
                <CardContent className="space-y-3 pt-4">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="font-semibold leading-tight">{m.nome}</p>
                      {m.cargo && <p className="text-xs text-muted-foreground">{m.cargo}</p>}
                    </div>
                    {avaliadoCom ? (
                      <Badge variant="success">
                        <Check className="mr-1 h-3 w-3" /> Avaliado hoje ({avaliadoCom}★)
                      </Badge>
                    ) : null}
                  </div>

                  <div className="flex items-center justify-between gap-1">
                    {[1, 2, 3, 4, 5].map((n) => (
                      <button
                        key={n}
                        type="button"
                        onClick={() => setNotas((prev) => ({ ...prev, [m.employee_id]: n }))}
                        aria-label={`Nota ${n}`}
                        className="flex h-12 w-12 items-center justify-center rounded-xl transition-colors hover:bg-[hsl(var(--secondary))]"
                      >
                        <Star
                          className={`h-8 w-8 ${
                            n <= notaAtual ? 'fill-amber-400 text-amber-400' : 'text-gray-300'
                          }`}
                        />
                      </button>
                    ))}
                  </div>

                  <button
                    type="button"
                    onClick={() =>
                      setObsAberta((prev) => ({ ...prev, [m.employee_id]: !prev[m.employee_id] }))
                    }
                    className="flex items-center gap-1 text-sm text-[hsl(var(--primary))]"
                  >
                    <MessageSquarePlus className="h-4 w-4" />
                    {obsAberta[m.employee_id] ? 'Ocultar observação' : 'Adicionar observação'}
                  </button>
                  {obsAberta[m.employee_id] && (
                    <Textarea
                      value={obs[m.employee_id] || ''}
                      onChange={(e) => setObs((prev) => ({ ...prev, [m.employee_id]: e.target.value }))}
                      placeholder="Observação (opcional)"
                      rows={2}
                      className="text-base"
                    />
                  )}

                  <Button
                    onClick={() => avaliar(m)}
                    disabled={!notaAtual || enviandoId === m.employee_id}
                    isLoading={enviandoId === m.employee_id}
                    size="lg"
                    className="w-full"
                    variant={avaliadoCom ? 'secondary' : 'primary'}
                  >
                    {avaliadoCom ? 'Avaliar novamente' : 'Enviar avaliação'}
                  </Button>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* Consolidado */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Consolidado (30 dias)</CardTitle>
        </CardHeader>
        <CardContent>
          {consolidado.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Ainda sem avaliações registradas nos últimos 30 dias.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs text-muted-foreground">
                    <th className="py-2 pr-2 font-medium">Nome</th>
                    <th className="py-2 pr-2 text-center font-medium">Média</th>
                    <th className="py-2 pr-2 text-center font-medium">Tend.</th>
                    <th className="py-2 text-center font-medium">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {consolidado.map((c) => (
                    <tr key={c.employee_id} className="border-b last:border-0">
                      <td className="py-2 pr-2">
                        <p className="font-medium leading-tight">{c.nome}</p>
                        {c.cargo && <p className="text-xs text-muted-foreground">{c.cargo}</p>}
                      </td>
                      <td className="py-2 pr-2 text-center font-semibold">
                        {typeof c.media === 'number' ? c.media.toFixed(1) : '—'}
                      </td>
                      <td className="py-2 pr-2">
                        <div className="flex justify-center">
                          <Tendencia valor={c.tendencia} />
                        </div>
                      </td>
                      <td className="py-2 text-center">{c.total_avaliacoes ?? '—'}</td>
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
