'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { ArrowLeft, CheckCheck, Moon, RefreshCw, Send, Sun } from 'lucide-react';
import { toast } from 'sonner';
import { api } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';

// ── Tipos ────────────────────────────────────────────────────────────────────
interface Passagem {
  id: string;
  turno?: string;
  resumo?: string;
  pendencias?: string | null;
  data_turno?: string | null;
  created_at?: string | null;
  criado_em?: string | null;
  autor_nome?: string | null;
  registrado_por_nome?: string | null;
  post_name?: string | null;
  posto_nome?: string | null;
  lida?: boolean;
  lida_em?: string | null;
}

function formatarQuando(p: Passagem): string {
  const raw = p.data_turno || p.created_at || p.criado_em;
  if (!raw) return '';
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return String(raw);
  return d.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}

function TurnoBadge({ turno }: { turno?: string }) {
  if (!turno) return null;
  const noturno = turno.toLowerCase().includes('not');
  return (
    <Badge className={noturno ? 'bg-indigo-100 text-indigo-800' : 'bg-amber-100 text-amber-800'}>
      {noturno ? <Moon className="mr-1 h-3 w-3" /> : <Sun className="mr-1 h-3 w-3" />}
      {noturno ? 'Noturno' : 'Diurno'}
    </Badge>
  );
}

export default function PassagemTurnoPage() {
  const [anterior, setAnterior] = useState<Passagem | null>(null);
  const [items, setItems] = useState<Passagem[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erroCarga, setErroCarga] = useState<string | null>(null);

  // Form
  const [turno, setTurno] = useState<'diurno' | 'noturno' | ''>('');
  const [resumo, setResumo] = useState('');
  const [pendencias, setPendencias] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [marcandoLida, setMarcandoLida] = useState(false);

  const carregar = useCallback(async () => {
    setCarregando(true);
    setErroCarga(null);
    try {
      const res = await api.get('/api/v1/operacional/passagem-turno/', { params: { limit: 20 } });
      const dado = res.data || {};
      setItems(Array.isArray(dado.items) ? dado.items : Array.isArray(dado) ? dado : []);
      setAnterior(dado.anterior || null);
    } catch (err: unknown) {
      const e = err as { response?: { status?: number } };
      setErroCarga(
        e.response?.status === 403
          ? 'Sem permissão para ver passagens de turno.'
          : 'Não foi possível carregar as passagens.',
      );
    } finally {
      setCarregando(false);
    }
  }, []);

  useEffect(() => {
    carregar();
  }, [carregar]);

  const marcarLida = async () => {
    if (!anterior?.id) return;
    setMarcandoLida(true);
    try {
      await api.post(`/api/v1/operacional/passagem-turno/${anterior.id}/lida`);
      toast.success('Passagem marcada como lida');
      carregar();
    } catch {
      toast.error('Erro ao marcar como lida');
    } finally {
      setMarcandoLida(false);
    }
  };

  const enviar = async () => {
    if (!turno) {
      toast.error('Escolha o turno');
      return;
    }
    if (!resumo.trim()) {
      toast.error('Escreva o resumo do turno');
      return;
    }
    setEnviando(true);
    try {
      const payload: Record<string, unknown> = { turno, resumo: resumo.trim() };
      if (pendencias.trim()) payload.pendencias = pendencias.trim();
      await api.post('/api/v1/operacional/passagem-turno/', payload);
      toast.success('Passagem de turno registrada');
      setTurno('');
      setResumo('');
      setPendencias('');
      carregar();
    } catch (err: unknown) {
      const e = err as { response?: { status?: number; data?: { detail?: unknown } } };
      if (e.response?.status === 403) {
        toast.error('Sem permissão para registrar passagem de turno.');
      } else {
        const detail = e.response?.data?.detail;
        toast.error(typeof detail === 'string' ? detail : 'Erro ao registrar a passagem.');
      }
    } finally {
      setEnviando(false);
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
            <RefreshCw className="h-5 w-5 text-cyan-600" />
            Passagem de Turno
          </h1>
          <p className="text-sm text-muted-foreground">Receba e registre o rendimento do posto</p>
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

      {/* Passagem anterior */}
      <Card className="border-cyan-200">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Passagem anterior</CardTitle>
        </CardHeader>
        <CardContent>
          {carregando && !anterior ? (
            <p className="text-sm text-muted-foreground">Carregando…</p>
          ) : anterior ? (
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <TurnoBadge turno={anterior.turno} />
                <span className="text-xs text-muted-foreground">{formatarQuando(anterior)}</span>
                {(anterior.autor_nome || anterior.registrado_por_nome) && (
                  <span className="text-xs text-muted-foreground">
                    por {anterior.autor_nome || anterior.registrado_por_nome}
                  </span>
                )}
              </div>
              {anterior.resumo && <p className="whitespace-pre-wrap text-sm">{anterior.resumo}</p>}
              {anterior.pendencias && (
                <div className="rounded-lg bg-amber-50 p-2 text-sm text-amber-900">
                  <span className="font-semibold">Pendências: </span>
                  {anterior.pendencias}
                </div>
              )}
              {anterior.lida ? (
                <Badge variant="success">
                  <CheckCheck className="mr-1 h-3 w-3" /> Lida
                </Badge>
              ) : (
                <Button onClick={marcarLida} isLoading={marcandoLida} size="lg" className="w-full">
                  <CheckCheck className="mr-2 h-5 w-5" />
                  Marcar como lida
                </Button>
              )}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Nenhuma passagem registrada ainda.</p>
          )}
        </CardContent>
      </Card>

      {/* Nova passagem */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Registrar minha passagem</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => setTurno('diurno')}
              className={`flex min-h-[52px] items-center justify-center gap-2 rounded-xl border-2 px-3 py-3 text-sm font-semibold transition-colors ${
                turno === 'diurno'
                  ? 'border-amber-500 bg-amber-500 text-white'
                  : 'border-amber-400 text-amber-600 hover:bg-amber-50'
              }`}
            >
              <Sun className="h-5 w-5" /> Diurno
            </button>
            <button
              type="button"
              onClick={() => setTurno('noturno')}
              className={`flex min-h-[52px] items-center justify-center gap-2 rounded-xl border-2 px-3 py-3 text-sm font-semibold transition-colors ${
                turno === 'noturno'
                  ? 'border-indigo-600 bg-indigo-600 text-white'
                  : 'border-indigo-500 text-indigo-600 hover:bg-indigo-50'
              }`}
            >
              <Moon className="h-5 w-5" /> Noturno
            </button>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium">
              Resumo do turno <span className="text-red-500">*</span>
            </label>
            <Textarea
              value={resumo}
              onChange={(e) => setResumo(e.target.value)}
              placeholder="Como foi o turno? Rondas, visitantes, situações relevantes…"
              rows={4}
              className="text-base"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium">Pendências (opcional)</label>
            <Textarea
              value={pendencias}
              onChange={(e) => setPendencias(e.target.value)}
              placeholder="O que o próximo turno precisa acompanhar?"
              rows={2}
              className="text-base"
            />
          </div>

          <Button
            onClick={enviar}
            disabled={!turno || !resumo.trim() || enviando}
            isLoading={enviando}
            size="lg"
            className="w-full"
          >
            <Send className="mr-2 h-5 w-5" />
            Registrar passagem
          </Button>
        </CardContent>
      </Card>

      {/* Últimas passagens */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Últimas passagens</CardTitle>
        </CardHeader>
        <CardContent>
          {carregando ? (
            <p className="text-sm text-muted-foreground">Carregando…</p>
          ) : items.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nenhuma passagem registrada ainda.</p>
          ) : (
            <div className="space-y-3">
              {items.map((p) => (
                <div key={p.id} className="rounded-lg border border-[hsl(var(--border))] p-3">
                  <div className="mb-1 flex flex-wrap items-center gap-2">
                    <TurnoBadge turno={p.turno} />
                    <span className="text-xs text-muted-foreground">{formatarQuando(p)}</span>
                    {(p.post_name || p.posto_nome) && (
                      <span className="text-xs text-muted-foreground">{p.post_name || p.posto_nome}</span>
                    )}
                    {p.lida && (
                      <Badge variant="success" className="ml-auto">
                        <CheckCheck className="mr-1 h-3 w-3" /> Lida
                      </Badge>
                    )}
                  </div>
                  {p.resumo && <p className="whitespace-pre-wrap text-sm">{p.resumo}</p>}
                  {p.pendencias && (
                    <p className="mt-1 text-sm text-amber-700">
                      <span className="font-semibold">Pendências: </span>
                      {p.pendencias}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
